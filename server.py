#!/usr/bin/env python3
"""
TrigPoint - a local tool for curating a list of sites (facilities) for an Earth observation dataset.

You open each site on a satellite map, fix its centre and box size, look at imagery in many ways (single
scenes, cloudless composites, indices, statistics, gap fill, candidate areas), then keep or reject it. Every
save is checked by the built-in validator, so a file that breaks the rules is never written. Provenance and
datasheet exports describe how the roster was made.

The tool stands alone: Python with numpy, scipy, rasterio, matplotlib and requests. Earth Engine is optional;
Planetary Computer needs no account; demo mode needs nothing.

Run (from this folder):
    python server.py
    -> open http://127.0.0.1:8765
"""
import copy
import glob
import html
import json
import math
import os
import re
import sys
import threading
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backends as BK  # noqa: E402
import core as P  # noqa: E402  (settings, geometry, Earth Engine helpers)
import curator_logic as CL  # noqa: E402  (review logic)
import imagery_service as IS  # noqa: E402
import imagery_tools as IT  # noqa: E402
import provenance as PV  # noqa: E402
import splitsafety as SS  # noqa: E402
import studies as ST  # noqa: E402
import validator as V  # noqa: E402
from rasterio.warp import transform as warp_transform  # noqa: E402

STATIC_DIR = os.path.join(HERE, "static")
DEMO_DIR = os.path.join(HERE, "demo")
# Cache, backup and audit locations can be redirected (tests and dry runs use this);
# the defaults are the folders next to this file.
CACHE_DIR = os.environ.get("SITE_CURATOR_CACHE_DIR", os.path.join(HERE, "cache"))
BACKUP_DIR = os.environ.get("SITE_CURATOR_BACKUP_DIR", os.path.join(HERE, "backups"))
STUDIES_DIR = os.environ.get("SITE_CURATOR_STUDIES_DIR", os.path.join(HERE, "studies"))
AUDIT_PATH = os.environ.get("SITE_CURATOR_AUDIT_PATH", os.path.join(HERE, "audit.log.jsonl"))
SITES_PATH = (os.environ.get("SITE_CURATOR_SITES") or os.environ.get("METHANE_SITES_PATH")
              or os.path.join(DEMO_DIR, "sites_demo.json"))
# Read-only second roster shown as a reference layer while editing another file (optional).
REFERENCE_PATH = os.environ.get("SITE_CURATOR_REFERENCE") or os.environ.get("METHANE_REFERENCE_PATH") or ""
HOST = os.environ.get("SITE_CURATOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("SITE_CURATOR_PORT", "8765"))
MAX_BODY = 5 * 1024 * 1024
VERSION = "1.5.0"
import sensitivity as _SN  # noqa: E402
SN_DEFAULT_DISTANCES = list(_SN.DISTANCES_KM)
SN_DEFAULT_BEARINGS = list(_SN.BEARINGS_8)

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

P.LOG.disabled = True

VALID_ROLES = ("train", "test", "decoy")

_ee_ready = False
_ee_error = ""


def try_init_ee():
    global _ee_ready, _ee_error
    try:
        P.init_earth_engine()
        _ee_ready = True
        print("[server] Earth Engine ready.")
    except Exception as e:
        _ee_error = f"{type(e).__name__}: {e}"
        print(f"[server] Earth Engine is not available ({_ee_error}). Demo mode and Planetary Computer "
              f"still work; see docs/BACKENDS.md to set up Earth Engine.")


# ---------------------------------------------------------------------------
# geometry helpers that do NOT require Earth Engine (pure rasterio/math) —
# mirrors core.chip_grid_math exactly, so the "exact grid"
# overlay works even without EE credentials.
# ---------------------------------------------------------------------------

def exact_grid_corners(lat, lon, box_km):
    epsg = P.utm_epsg(lat, lon)
    crs = f"EPSG:{epsg}"
    xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
    px = P.CFG["chip_px"]
    size = box_km * 1000.0
    gsd = size / px
    half = size / 2.0
    x0 = math.floor((xs[0] - half) / gsd) * gsd
    y1 = math.ceil((ys[0] + half) / gsd) * gsd
    x1, y0 = x0 + size, y1 - size
    lons, lats = warp_transform(crs, "EPSG:4326", [x0, x1, x1, x0], [y0, y0, y1, y1])
    return {"corners": [[lats[i], lons[i]] for i in range(4)],
            "gsd_m": round(gsd, 3), "epsg": epsg}


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "site"


# ---------------------------------------------------------------------------
# SiteStore — all sites.json reads/writes/validation/audit go through here.
# Kept separate from the HTTP layer on purpose: this is the part that would
# get reused if this tool ever grows into a shared service (swap the
# transport, keep the store).
# ---------------------------------------------------------------------------

class ValidationError(ValueError):
    pass


class SiteStore:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def _read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _validate(self, doc):
        """Refuse to write a file that breaks the rules (see validator.py). Raises ValidationError with the first problem."""
        rep = V.validate_document(doc, P.CFG["min_box_km"], P.CFG["max_box_km"], VALID_ROLES)
        if rep.errors:
            raise ValidationError(rep.errors[0])

    def _write(self, doc, action, site_id, detail=None):
        self._validate(doc)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup = os.path.join(BACKUP_DIR, f"sites_{ts}.json")
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f, \
                 open(backup, "w", encoding="utf-8") as bf:
                bf.write(f.read())
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)
        self._audit(action, site_id, detail)

    def _audit(self, action, site_id, detail=None):
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "action": action,
               "site_id": site_id, "detail": detail or {}}
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def list(self):
        return self._read()

    def get(self, site_id):
        doc = self._read()
        s = next((x for x in doc["sites"] if x["id"] == site_id), None)
        if s is None:
            raise KeyError(site_id)
        return s

    def create(self, fields):
        with self.lock:
            doc = self._read()
            name = (fields.get("name") or "").strip()
            if not name:
                raise ValidationError("name is required")
            role = fields.get("role", "train")
            if role not in VALID_ROLES:
                raise ValidationError(f"role must be one of {VALID_ROLES}")
            center = fields.get("center")
            if not center or len(center) != 2:
                raise ValidationError("center must be [lat, lon]")
            try:
                lat, lon = float(center[0]), float(center[1])
            except (TypeError, ValueError):
                raise ValidationError("center must be two numbers")
            box_km = float(fields.get("box_km", 3.0))
            box_km = min(max(box_km, P.CFG["min_box_km"]), P.CFG["max_box_km"])

            raw_id = (fields.get("id") or "").strip() or slugify(name)
            existing_ids = {s["id"] for s in doc["sites"]}
            site_id, n = raw_id, 2
            while site_id in existing_ids:
                site_id = f"{raw_id}_{n}"
                n += 1

            site = {
                "id": site_id, "name": name, "role": role,
                "center": [round(lat, 6), round(lon, 6)],
                "box_km": round(box_km, 2),
                "verified": bool(fields.get("verified", False)),
                "notes": str(fields.get("notes", ""))[:2000],
            }
            doc["sites"].append(site)
            self._write(doc, "create", site_id, {"site": site})
            return site

    def update(self, site_id, patch):
        with self.lock:
            doc = self._read()
            site = next((s for s in doc["sites"] if s["id"] == site_id), None)
            if site is None:
                raise KeyError(site_id)
            before = copy.deepcopy(site)
            if "verified" in patch and "rejected" in patch \
                    and patch["verified"] and patch["rejected"]:
                raise ValidationError("a site cannot be both verified and rejected")
            if "center" in patch:
                lat, lon = patch["center"]
                new_center = [round(float(lat), 6), round(float(lon), 6)]
                # Remember the value the site had before the first edit, so the
                # review can show how far the centre moved and warn if it never did.
                if "original_center" not in site and \
                        CL.haversine_km(site["center"], new_center) > 1e-6:
                    site["original_center"] = list(site["center"])
                site["center"] = new_center
            if "box_km" in patch:
                box = float(patch["box_km"])
                box = min(max(box, P.CFG["min_box_km"]), P.CFG["max_box_km"])
                site["box_km"] = round(box, 2)
            if "verified" in patch:
                site["verified"] = bool(patch["verified"])
                if site["verified"]:
                    site.pop("rejected", None)       # keeping a site clears a reject
            if "rejected" in patch:
                if patch["rejected"]:
                    site["rejected"] = True
                    if "verified" not in patch:
                        site["verified"] = False     # a rejected site is never verified
                else:
                    site.pop("rejected", None)
            if "notes" in patch:
                site["notes"] = str(patch["notes"])[:2000]
            if "comment" in patch:
                comment = str(patch["comment"] or "")[:2000]
                if comment.strip():
                    site["comment"] = comment
                else:
                    site.pop("comment", None)
            if patch.get("name"):
                site["name"] = str(patch["name"])[:200]
            if "role" in patch:
                if patch["role"] not in VALID_ROLES:
                    raise ValidationError(f"role must be one of {VALID_ROLES}")
                site["role"] = patch["role"]
            self._write(doc, "update", site_id, {"before": before, "after": copy.deepcopy(site)})
            return site

    def replace_site(self, site_id, new_site):
        """Swap in a whole site record (used by undo and redo, so fields the
        edit added, such as rejected or original_center, also come back off)."""
        with self.lock:
            doc = self._read()
            idx = next((i for i, s in enumerate(doc["sites"]) if s["id"] == site_id), None)
            if idx is None:
                raise KeyError(site_id)
            if new_site.get("id") != site_id:
                raise ValidationError("replace_site cannot change the id")
            before = doc["sites"][idx]
            doc["sites"][idx] = new_site
            self._write(doc, "replace", site_id, {"before": before, "after": new_site})
            return new_site

    def replace_many(self, new_sites, action="replace_many"):
        """Swap in several whole site records in one write (bulk undo and redo)."""
        with self.lock:
            doc = self._read()
            index = {s["id"]: i for i, s in enumerate(doc["sites"])}
            missing = [s["id"] for s in new_sites if s["id"] not in index]
            if missing:
                raise KeyError(sorted(missing))
            for s in new_sites:
                doc["sites"][index[s["id"]]] = s
            self._write(doc, action, None, {"ids": [s["id"] for s in new_sites]})
            return new_sites

    def delete(self, site_id):
        with self.lock:
            doc = self._read()
            site = next((s for s in doc["sites"] if s["id"] == site_id), None)
            if site is None:
                raise KeyError(site_id)
            doc["sites"] = [s for s in doc["sites"] if s["id"] != site_id]
            self._write(doc, "delete", site_id, {"deleted": site})
            return site

    def insert_exact(self, site, action="restore"):
        """Insert a site object verbatim (id preserved, not re-slugified/
        deduped) — used by undo-of-delete, redo-of-create, and backup
        restore, where the id must come back exactly as it was."""
        with self.lock:
            doc = self._read()
            if any(s["id"] == site["id"] for s in doc["sites"]):
                raise ValidationError(f"a site with id {site['id']!r} already exists")
            doc["sites"].append(site)
            self._write(doc, action, site["id"], {"site": site})
            return site

    def duplicate(self, site_id):
        with self.lock:
            doc = self._read()
            src = next((s for s in doc["sites"] if s["id"] == site_id), None)
            if src is None:
                raise KeyError(site_id)
            raw_id = f"{src['id']}_copy"
            existing_ids = {s["id"] for s in doc["sites"]}
            new_id, n = raw_id, 2
            while new_id in existing_ids:
                new_id = f"{raw_id}{n}"
                n += 1
            clone = {**src, "id": new_id, "name": f"{src.get('name', src['id'])} (copy)",
                     "verified": False}
            doc["sites"].append(clone)
            self._write(doc, "duplicate", new_id, {"from": site_id, "site": clone})
            return clone

    def bulk_create(self, items):
        with self.lock:
            doc = self._read()
            created = []
            existing_ids = {s["id"] for s in doc["sites"]}
            for fields in items:
                name = (fields.get("name") or "").strip()
                if not name:
                    raise ValidationError(f"name is required (row: {fields})")
                role = fields.get("role", "train")
                if role not in VALID_ROLES:
                    raise ValidationError(f"{name}: role must be one of {VALID_ROLES}")
                try:
                    lat, lon = float(fields["lat"]), float(fields["lon"])
                except (KeyError, TypeError, ValueError):
                    raise ValidationError(f"{name}: lat/lon must be numbers")
                box_km = float(fields.get("box_km", 3.0))
                box_km = min(max(box_km, P.CFG["min_box_km"]), P.CFG["max_box_km"])
                raw_id = (fields.get("id") or "").strip() or slugify(name)
                site_id, n = raw_id, 2
                while site_id in existing_ids:
                    site_id = f"{raw_id}_{n}"
                    n += 1
                existing_ids.add(site_id)
                site = {
                    "id": site_id, "name": name, "role": role,
                    "center": [round(lat, 6), round(lon, 6)],
                    "box_km": round(box_km, 2), "verified": False,
                    "notes": str(fields.get("notes", ""))[:2000],
                }
                doc["sites"].append(site)
                created.append(site)
            if not created:
                raise ValidationError("no rows to import")
            self._write(doc, "bulk_create", None,
                       {"count": len(created), "ids": [s["id"] for s in created]})
            return created

    def bulk_update(self, ids, patch):
        with self.lock:
            doc = self._read()
            touched = []
            for site in doc["sites"]:
                if site["id"] not in ids:
                    continue
                if "verified" in patch:
                    site["verified"] = bool(patch["verified"])
                    if site["verified"]:
                        site.pop("rejected", None)
                if "rejected" in patch:
                    if patch["rejected"]:
                        site["rejected"] = True
                        if "verified" not in patch:
                            site["verified"] = False
                    else:
                        site.pop("rejected", None)
                if "role" in patch:
                    if patch["role"] not in VALID_ROLES:
                        raise ValidationError(f"role must be one of {VALID_ROLES}")
                    site["role"] = patch["role"]
                touched.append(site["id"])
            missing = set(ids) - set(touched)
            if missing:
                raise KeyError(sorted(missing))
            self._write(doc, "bulk_update", None, {"ids": touched, "patch": patch})
            return touched

    def bulk_delete(self, ids):
        with self.lock:
            doc = self._read()
            present = {s["id"] for s in doc["sites"]}
            missing = set(ids) - present
            if missing:
                raise KeyError(sorted(missing))
            deleted = [s for s in doc["sites"] if s["id"] in ids]
            doc["sites"] = [s for s in doc["sites"] if s["id"] not in ids]
            self._write(doc, "bulk_delete", None, {"ids": list(ids)})
            return deleted

    def list_backups(self):
        rows = []
        for fn in os.listdir(BACKUP_DIR):
            if not fn.endswith(".json"):
                continue
            fp = os.path.join(BACKUP_DIR, fn)
            st = os.stat(fp)
            rows.append({"filename": fn, "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        rows.sort(key=lambda r: r["modified"], reverse=True)
        return rows

    def _backup_path(self, filename):
        # no path traversal: must be a bare filename already known to us
        if filename != os.path.basename(filename) or not filename.endswith(".json"):
            raise ValidationError("invalid backup filename")
        fp = os.path.join(BACKUP_DIR, filename)
        if not os.path.isfile(fp):
            raise KeyError(filename)
        return fp

    def read_backup(self, filename):
        with open(self._backup_path(filename), "r", encoding="utf-8") as f:
            return json.load(f)

    def restore_backup(self, filename):
        with self.lock:
            doc = self.read_backup(filename)
            self._write(doc, "restore_backup", None, {"filename": filename})
            return doc

    def warnings(self):
        doc = self._read()
        sites = doc["sites"]
        label_km = P.CFG["label_box_km"]
        bg_outer = P.CFG["bg_outer_km"]
        out = []
        live = [s for s in sites if not s.get("rejected")]   # rejected sites leave the final file
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                a, b = live[i], live[j]
                d = haversine_km(a["center"], b["center"])
                if d < label_km:
                    out.append({
                        "a": a["id"], "b": b["id"], "distance_km": round(d, 1),
                        "severity": "critical",
                        "message": f"{a['id']} ↔ {b['id']} are {d:.1f} km apart "
                                   f"— their {label_km:.0f} km label windows overlap directly.",
                    })
                elif d < bg_outer:
                    out.append({
                        "a": a["id"], "b": b["id"], "distance_km": round(d, 1),
                        "severity": "info",
                        "message": f"{a['id']} ↔ {b['id']} are {d:.1f} km apart "
                                   f"— each sits inside the other's {bg_outer:.0f} km "
                                   f"background ring. This is only worth knowing: a facility inside "
                                   f"the ring can raise the background level, so check that "
                                   f"the ring still has enough valid pixels.",
                    })
        stats = {
            "total": len(sites),
            "train": sum(1 for s in sites if s["role"] == "train"),
            "test": sum(1 for s in sites if s["role"] == "test"),
            "decoy": sum(1 for s in sites if s["role"] == "decoy"),
            "verified": sum(1 for s in sites if s.get("verified")),
            "unverified": sum(1 for s in sites if not s.get("verified")),
            "rejected": sum(1 for s in sites if s.get("rejected")),
            "pending": sum(1 for s in sites if CL.review_state(s) == "pending"),
        }
        return {"warnings": out, "stats": stats}

    # -- review helpers (read-only) ----------------------------------------

    def reference(self):
        """The pilot roster, read fresh and never written. Empty when the
        curator is editing the pilot file itself (it is already the main layer)."""
        same = os.path.abspath(REFERENCE_PATH) == os.path.abspath(self.path)
        sites = []
        if not same and os.path.isfile(REFERENCE_PATH):
            try:
                with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f).get("sites", [])
                for s in raw:
                    if "id" in s and "center" in s:
                        sites.append({k: s[k] for k in
                                      ("id", "name", "role", "center", "box_km",
                                       "facility_type", "region", "country") if k in s})
            except (OSError, ValueError):
                sites = []
        return {"path": REFERENCE_PATH, "same_file": same,
                "available": os.path.isfile(REFERENCE_PATH), "sites": sites}

    def _cfg(self):
        return {"min_box_km": P.CFG["min_box_km"], "max_box_km": P.CFG["max_box_km"],
                "label_box_km": P.CFG["label_box_km"]}

    def split_radius(self):
        return float(P.CFG.get("min_split_distance_km", CL.SPLIT_RADIUS_KM))

    def analysis(self):
        return CL.build_analysis(self._read(), self.reference()["sites"], self._cfg(),
                                 self.split_radius())

    def neighbors_at(self, lat, lon, exclude_id=None):
        doc = self._read()
        ref = self.reference()["sites"]
        radius = self.split_radius()
        nb = CL.find_neighbors([lat, lon], doc["sites"], ref, exclude_id, radius)
        roles = sorted({n["role"] for n in nb if n["source"] == "pilot" and n["role"]})
        return {"radius_km": radius, "neighbors": nb,
                "pilot_roles": roles, "conflict": len(roles) > 1,
                "required_role": roles[0] if len(roles) == 1 else None}

    # -- export and import -------------------------------------------------

    def export(self, scope="all", fmt="json", comments=True):
        doc = self._read()
        try:
            sub = CL.export_doc(doc, scope, comments)
        except ValueError as e:
            raise ValidationError(str(e))
        if fmt == "csv":
            return CL.export_csv(doc, scope, comments), "text/csv", "csv"
        if fmt != "json":
            raise ValidationError("format must be json or csv")
        self._validate(sub)         # an exported file must also pass the validator
        return json.dumps(sub, indent=2, ensure_ascii=False), "application/json", "json"

    def import_sites(self, incoming, policy="skip", apply=False):
        """Preview or apply a merge of another sites file into this one."""
        if not isinstance(incoming, list):
            raise ValidationError("incoming sites must be a list")
        with self.lock:
            doc = self._read()
            try:
                plan = CL.plan_import(doc["sites"], incoming, policy, self._cfg())
            except ValueError as e:
                raise ValidationError(str(e))
            result = plan.pop("result_sites")
            plan["applied"] = False
            if apply:
                if not (plan["new"] or plan["overwritten"]):
                    raise ValidationError("nothing to import with this policy")
                doc["sites"] = result
                self._write(doc, "import", None,
                            {"policy": policy, "counts": plan["counts"],
                             "new": [x["id"] for x in plan["new"]],
                             "overwritten": [x["id"] for x in plan["overwritten"]]})
                plan["applied"] = True
            return plan

    def audit_tail(self, limit=50):
        if not os.path.exists(AUDIT_PATH):
            return []
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(l) for l in lines if l.strip()]


store = SiteStore(SITES_PATH)

# ---------------------------------------------------------------------------
# in-session undo/redo — a convenience on top of the permanent audit log +
# backups (which remain the durable record). Cleared on server restart;
# covers single-site create/update/delete/duplicate (update includes keep,
# reject and unreject) and bulk verify/reject/role changes; bulk delete,
# import and backup restore are not on the stack (restore a backup instead).
# ---------------------------------------------------------------------------

UNDO_STACK = []
REDO_STACK = []
MAX_UNDO = 50


def push_undo(entry):
    UNDO_STACK.append(entry)
    del UNDO_STACK[:-MAX_UNDO]
    REDO_STACK.clear()


def do_undo():
    if not UNDO_STACK:
        raise ValidationError("nothing to undo")
    entry = UNDO_STACK.pop()
    try:
        _apply_undo(entry)
    except (KeyError, ValidationError) as e:
        UNDO_STACK.append(entry)     # leave the entry in place so nothing is lost
        raise ValidationError(f"cannot undo: {e}")
    REDO_STACK.append(entry)
    del REDO_STACK[:-MAX_UNDO]
    return entry


def _apply_undo(entry):
    t = entry["type"]
    if t in ("create", "duplicate"):
        store.delete(entry["site_id"])
    elif t == "update":
        # whole-record restore, so fields the edit added (rejected,
        # original_center, comment) are removed again too
        store.replace_site(entry["site_id"], copy.deepcopy(entry["before"]))
    elif t == "bulk_update":
        store.replace_many(copy.deepcopy(entry["before"]), action="undo_bulk_update")
    elif t == "delete":
        store.insert_exact(entry["before"], action="undo_delete")


def do_redo():
    if not REDO_STACK:
        raise ValidationError("nothing to redo")
    entry = REDO_STACK.pop()
    try:
        _apply_redo(entry)
    except (KeyError, ValidationError) as e:
        REDO_STACK.append(entry)
        raise ValidationError(f"cannot redo: {e}")
    UNDO_STACK.append(entry)
    return entry


def _apply_redo(entry):
    t = entry["type"]
    if t in ("create", "duplicate"):
        store.insert_exact(entry["after"], action="redo_create")
    elif t == "update":
        store.replace_site(entry["site_id"], copy.deepcopy(entry["after"]))
    elif t == "bulk_update":
        store.replace_many(copy.deepcopy(entry["after"]), action="redo_bulk_update")
    elif t == "delete":
        store.delete(entry["site_id"])


# ---------------------------------------------------------------------------
# imagery: fetching, caching and rendering are in imagery_service.py
# ---------------------------------------------------------------------------

def ee_ready():
    return _ee_ready


def ee_error():
    return _ee_error


BACKENDS = BK.registry(ee_ready, ee_error)
SERVICE = IS.ImageryService(CACHE_DIR, BACKENDS, int(os.environ.get("SITE_CURATOR_CACHE_MB", "500")))
SERVICE.prune(SERVICE.max_mb)
STUDIES = ST.Studies(STUDIES_DIR, SERVICE, BACKENDS, VERSION)


def default_backend():
    return "ee" if _ee_ready else "demo"


def thumb_data_uri(site):
    """Newest cached true-colour picture of this site as a data: URI, and whether it is synthetic.

    Self-contained so the report still works after Save-As or Print-to-PDF. Returns (None, False) when no
    picture has been fetched.
    """
    import base64
    pattern = os.path.join(CACHE_DIR, f"{IS.site_token(site['id'])}_*__true_color__percentile__none.png")
    matches = glob.glob(pattern)
    if not matches:
        return None, False
    matches.sort(key=os.path.getmtime, reverse=True)
    synthetic = False
    meta = os.path.basename(matches[0]).split("__")[0] + ".json"
    try:
        with open(os.path.join(CACHE_DIR, meta), "r", encoding="utf-8") as f:
            synthetic = bool(json.load(f).get("synthetic"))
    except (OSError, ValueError):
        pass
    with open(matches[0], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}", synthetic


def audit_entries(limit=100000):
    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def cached_imagery_meta():
    """Metadata of the cached images that belong to sites of the roster that is open (the cache can hold other rosters)."""
    ids = {s.get("id") for s in store.list().get("sites", [])}
    out = []
    for p in glob.glob(os.path.join(CACHE_DIR, "*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if m.get("site_id") in ids:
            out.append(m)
    return out


def studies_summary():
    """What the studies found the last time they were run in this session, for the provenance record."""
    out = {}
    cert = STUDIES.last.get("certificate")
    if cert:
        out["split_certificate"] = {"verdict": cert["verdict"], "roster_sha256": cert["roster_sha256"], "created": cert["created"],
                                    "checks": {c["id"]: c["status"] for c in cert["checks"]}}
    fv = STUDIES.last.get("forecast_validation")
    if fv:
        out["forecast_validation"] = {k: fv.get(k) for k in ("target", "n_sites", "mae", "mae_baseline", "skill", "r2", "spearman", "interval_coverage", "features", "cluster_km")}
    if STUDIES.last.get("grounding"):
        out["grounding"] = STUDIES.last["grounding"]
    dup = STUDIES.last.get("duplicates")
    if dup:
        out["near_duplicates"] = {"n_images": dup["n_images"], "pairs_found": len(dup["found"]), "synthetic": dup.get("synthetic")}
    return out


def provenance_record(include_comments=False):
    return PV.build_provenance(store.list(), audit_entries(), cached_imagery_meta(), VERSION,
                               os.path.basename(SITES_PATH), include_comments, studies=studies_summary())


def generate_report_html():
    doc = store.list()
    sites = sorted(doc["sites"], key=lambda s: (s["role"] != "train", s["role"], s["id"]))
    w = store.warnings()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = []
    for s in sites:
        thumb, synthetic = thumb_data_uri(s)
        img_html = (f'<img src="{thumb}" class="thumb" alt="Satellite view of {html.escape(str(s.get("name", s["id"])))}">'
                    + ('<div class="sub">synthetic demo image</div>' if synthetic else "") if thumb
                    else '<div class="thumb placeholder">no preview cached</div>')
        badge = "verified" if s.get("verified") else "unverified"
        rows.append(f"""
        <div class="card">
          {img_html}
          <div class="meta">
            <div class="name">{html.escape(str(s.get('name', s['id'])))}</div>
            <div class="sub mono">{html.escape(str(s['id']))} &middot; {html.escape(str(s['role']))} &middot; {s['box_km']} km
              &middot; <span class="badge {badge}">{badge}</span></div>
            <div class="sub mono">{s['center'][0]:.5f}, {s['center'][1]:.5f}</div>
            {f'<div class="notes">{html.escape(str(s["notes"]))}</div>' if s.get('notes') else ''}
          </div>
        </div>""")

    warn_rows = "".join(
        f'<li class="{html.escape(str(ww["severity"]))}">{html.escape(str(ww["message"]))}</li>' for ww in w["warnings"]
    ) or "<li>None.</li>"

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Site roster — {ts}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; background: #0d1117; color: #e6edf3;
         margin: 0; padding: 24px; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 15px; color: #8b949e; font-weight: 600;
        margin-top: 28px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
  .stats {{ font-size: 13px; color: #8b949e; margin-bottom: 4px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }}
  .card {{ border: 1px solid #30363d; border-radius: 8px; overflow: hidden; background: #161b22; }}
  .thumb {{ width: 100%; height: 160px; object-fit: cover; display: block; background: #000; }}
  .thumb.placeholder {{ display: flex; align-items: center; justify-content: center;
                        color: #8b949e; font-size: 12px; }}
  .meta {{ padding: 10px 12px; }}
  .name {{ font-weight: 600; font-size: 13px; }}
  .sub {{ font-size: 11px; color: #8b949e; margin-top: 3px; }}
  .mono {{ font-family: ui-monospace, Consolas, monospace; }}
  .notes {{ font-size: 11px; color: #c3c2b7; margin-top: 6px; font-style: italic; }}
  .badge {{ padding: 1px 6px; border-radius: 8px; }}
  .badge.verified {{ background: #16311a; color: #3fb950; }}
  .badge.unverified {{ background: #2a2313; color: #d29922; }}
  ul {{ font-size: 12px; padding-left: 18px; }}
  li.critical {{ color: #f85149; }} li.info {{ color: #58a6ff; }}
  @media print {{ body {{ background: #fff; color: #000; }}
                 .card {{ background: #fff; border-color: #ccc; }} }}
</style></head><body>
  <h1>Site roster report</h1>
  <div class="stats">Generated {ts} &middot; {w['stats']['total']} sites
    &middot; {w['stats']['train']} train &middot; {w['stats']['test']} test
    &middot; {w['stats']['decoy']} decoy &middot; {w['stats']['verified']} verified
    &middot; {w['stats']['unverified']} unverified</div>
  <div class="stats">Use your browser's Print → Save as PDF for a shareable file.</div>

  <h2>Geometry warnings</h2>
  <ul>{warn_rows}</ul>

  <h2>Sites</h2>
  <div class="grid">{''.join(rows)}</div>
</body></html>"""


def geocode(query):
    import requests
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 6},
        headers={"User-Agent": "TrigPoint/1.5 (local dev tool)"},
        timeout=8,
    )
    r.raise_for_status()
    return [{"display_name": it["display_name"], "lat": float(it["lat"]), "lon": float(it["lon"])}
            for it in r.json()]


def run_preflight():
    """Lightweight collection-availability check for the UI button.

    Deliberately NOT pipeline.preflight(): that one (a) wraps each check in
    a 4-attempt exponential-backoff retry meant for a patient, unattended
    build, and (b) sorts each collection to find the "latest available
    date". Diagnosed live 2026-07-21: that sort — even bounded to a 60-day
    tail — scans/sorts the collection GLOBALLY (no spatial filter, since
    preflight checks dataset availability, not any one site), and for a
    busy global collection like Sentinel-2 that can hang for minutes on
    Earth Engine's backend regardless of client retry policy or network
    conditions. This version only asks "does this collection have ANY data
    in the configured date range" via `.limit(1).size()`, which short-
    circuits without sorting — cheap and reliable — at the cost of not
    reporting the latest available date. One attempt per collection, no
    retry loop, so a genuinely degraded EE session still fails fast.
    """
    if not _ee_ready:
        raise RuntimeError(f"Earth Engine not initialized: {_ee_error or 'no credentials'}")
    checks = {
        "Sentinel-2 SR": P.S2_ID, "S2 cloud probability": P.S2_CLOUD_ID,
        "S5P L3 CH4": P.S5P_ID, "S5P L3 NO2": P.S5P_NO2_ID,
        "S5P L3 CO": P.S5P_CO_ID, "S5P L3 aerosol index": P.S5P_AAI_ID,
        "FIRMS thermal": P.FIRMS_ID,
        "ERA5-Land daily": P.ERA5L_DAILY_ID, "ERA5-Land hourly": P.ERA5L_HOURLY_ID,
    }
    report = {}
    for name, cid in checks.items():
        n = (P.ee.ImageCollection(cid)
             .filterDate(*P.date_range_default())
             .limit(1).size().getInfo())
        report[name] = "AVAILABLE" if n else "NO_DATA"
    return report


def estimate_coverage(lat, lon, box_km):
    """Fast, approximate coverage signal for one site: total scene/granule
    counts over the full configured date range for this box — NOT a true
    per-5-day-window pass rate (that would mean hundreds of EE calls per
    site). Two collection-size queries, a few seconds total."""
    if not _ee_ready:
        raise RuntimeError(f"Earth Engine not initialized: {_ee_error or 'no credentials'}")
    grid = P.chip_grid(lat, lon, box_km)
    s2 = (P.ee.ImageCollection(P.S2_ID).filterBounds(grid["geom"])
          .filterDate(*P.date_range_default())
          .filterMetadata("CLOUDY_PIXEL_PERCENTAGE", "less_than", P.CFG["max_cloud_frac"] * 100))
    s5p = (P.ee.ImageCollection(P.S5P_ID).filterBounds(grid["geom"])
           .filterDate(*P.date_range_default()))
    counts = P.ee.Dictionary({"s2": s2.size(), "s5p": s5p.size()}).getInfo()
    n_windows = len(P.generate_windows())
    return {
        "s2_scenes_lt_cloud_gate": counts["s2"],
        "s5p_granules": counts["s5p"],
        "possible_windows": n_windows,
        "note": ("Approximate signal, not the real per-window pass rate: "
                "counts raw scenes/granules over the full date range for "
                "this box, ignoring per-window pairing/QA gates the real "
                "build applies."),
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

STATIC_FILES = {
    "/app.js": "application/javascript; charset=utf-8",
    "/review.js": "application/javascript; charset=utf-8",
    "/style.css": "text/css; charset=utf-8",
    "/help.js": "application/javascript; charset=utf-8",
    "/imagery.js": "application/javascript; charset=utf-8",
    "/studies.js": "application/javascript; charset=utf-8",
    "/logo.svg": "image/svg+xml",
}


def finite(obj):
    """Replace NaN and infinity by null, which is the only valid JSON for them (browsers refuse the literal NaN)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [finite(v) for v in obj]
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return finite(obj.item())
    except ImportError:                                         # pragma: no cover
        pass
    return obj


class NotFound(KeyError):
    pass


def backend_report(check=False):
    """Which imagery backends can be used now, and why not. Planetary Computer needs the network, so it is
    only probed when asked (check=True)."""
    out = []
    for name, bk in BACKENDS.items():
        if name == "pc" and not check:
            out.append({"name": name, "label": bk.label, "ready": None, "reason": "Not checked yet. It needs internet access; press Check."})
            continue
        ok, why = bk.available()
        out.append({"name": name, "label": bk.label, "ready": ok, "reason": why, "synthetic": name == "demo"})
    return out


def views_report():
    return {
        "composites": {k: {"bands": list(v[0]), "description": v[1]} for k, v in IT.COMPOSITES.items()},
        "indices": {k: {"formula": v[0], "description": v[3]} for k, v in IT.INDICES.items()},
        "stretches": IT.STRETCHES, "sources": BK.SOURCES, "fills": list(IS.FILLS),
        "mask_kinds": {k: v[0] for k, v in IT.MASK_KINDS.items()},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[server] {self.address_string()} {fmt % args}")

    def _json(self, obj, status=200):
        body = json.dumps(finite(obj), default=str, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")   # pick up edits on reload
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > MAX_BODY:
            raise ValidationError(f"request too large (limit {MAX_BODY // (1024 * 1024)} MB)")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except ValueError as e:
            raise ValidationError(f"the request is not valid JSON: {e}") from None

    def _allowed(self, write):
        """Local-use guards: the Host header must name this server (blocks pages that point another name at it),
        and anything that changes data must carry the X-Site-Curator header, which a page on another site cannot send."""
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        okhosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if HOST not in ("127.0.0.1", "localhost", "::1"):
            okhosts.add(f"{HOST}:{port}".lower())
        if host and host not in okhosts:
            self._json({"error": "this request was not addressed to the local TrigPoint server"}, 403)
            return False
        if write and not self.headers.get("X-Site-Curator"):
            self._json({"error": "missing X-Site-Curator header (requests must come from the TrigPoint page)"}, 403)
            return False
        return True

    def _err(self, e):
        if isinstance(e, NotFound):
            return self._json({"error": str(e.args[0])}, 404)
        if isinstance(e, (ValidationError, IS.ImageryError, ST.StudyError)):
            return self._json({"error": str(e)}, 400)
        if isinstance(e, BK.BackendError):
            return self._json({"error": str(e)}, 502)
        traceback.print_exc()
        return self._json({"error": str(e)}, 500)

    def _imagery_request(self, site_id, qs):
        """Site, position and cleaned imagery parameters from a request (the on-screen position wins over the saved one)."""
        site_id = unquote(site_id)
        try:
            site = store.get(site_id)
        except KeyError:
            raise NotFound(f"unknown site {site_id}") from None
        lat = float(qs["lat"][0]) if "lat" in qs else site["center"][0]
        lon = float(qs["lon"][0]) if "lon" in qs else site["center"][1]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise IS.ImageryError("latitude or longitude out of range")
        raw = {k: qs[k][0] for k in ("source", "view", "stretch", "fill", "days", "q", "backend") if k in qs}
        raw["box_km"] = qs.get("box_km", [site["box_km"]])[0]
        raw.setdefault("backend", default_backend())
        return site, lat, lon, SERVICE.clean(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)
        if not self._allowed(False):
            return
        try:
            if path in ("/", "/index.html"):
                return self._file(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
            if path in STATIC_FILES:
                return self._file(os.path.join(STATIC_DIR, path[1:]), STATIC_FILES[path])

            if path in ("/api/status", "/api/health"):
                return self._json({
                    "status": "ok", "version": VERSION,
                    "ee_ready": _ee_ready, "ee_error": _ee_error,
                    "sites_path": SITES_PATH,
                    "min_box_km": P.CFG["min_box_km"], "max_box_km": P.CFG["max_box_km"],
                    "chip_px": P.CFG["chip_px"],
                    "label_box_km": P.CFG["label_box_km"],
                    "bg_inner_km": P.CFG["bg_inner_km"], "bg_outer_km": P.CFG["bg_outer_km"],
                    "valid_roles": VALID_ROLES,
                    "band_views": list(IT.COMPOSITES) + list(IT.INDICES),
                    "backends": backend_report(), "default_backend": default_backend(),
                    "sources": list(BK.SOURCES), "stretches": list(IT.STRETCHES), "fills": list(IS.FILLS),
                    "defaults": IS.DEFAULTS,
                    "split_radius_km": store.split_radius(),
                    "duplicate_km": CL.DUPLICATE_KM,
                    "reference_path": REFERENCE_PATH,
                    "features": ["review", "analysis", "reference", "neighbors", "export_scopes", "import_merge",
                                 "imagery", "composites", "indices", "statistics", "gapfill", "candidates",
                                 "validator", "provenance", "datasheet", "help", "overlap_groups", "certificate", "duplicates",
                                 "domain_shift", "forecast", "grounding", "placement"],
                })

            if path == "/api/sites":
                return self._json(store.list())

            if path == "/api/sites/export":
                # No query: the full file, as before. scope, format and comments
                # are optional (scope=all|kept|verified|rejected, format=json|csv,
                # comments=0 drops the private comment field).
                scope = qs.get("scope", ["all"])[0]
                fmt = qs.get("format", ["json"])[0]
                comments = qs.get("comments", ["1"])[0] != "0"
                try:
                    text, ctype, ext = store.export(scope, fmt, comments)
                except ValidationError as e:
                    return self._json({"error": str(e)}, 400)
                body = text.encode("utf-8")
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                label = "" if scope == "all" else f"_{scope}"
                self.send_response(200)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="sites{label}_{ts}.{ext}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/reference":
                return self._json(store.reference())

            if path == "/api/analysis":
                return self._json(store.analysis())

            if path == "/api/neighbors":
                try:
                    lat, lon = float(qs["lat"][0]), float(qs["lon"][0])
                except (KeyError, ValueError):
                    return self._json({"error": "lat and lon are required numbers"}, 400)
                return self._json(store.neighbors_at(lat, lon, qs.get("exclude", [None])[0]))

            if path == "/api/warnings":
                return self._json(store.warnings())

            if path == "/api/audit":
                limit = int(qs.get("limit", ["50"])[0])
                return self._json(store.audit_tail(limit))

            if path == "/api/backups":
                return self._json(store.list_backups())

            if path.startswith("/api/backups/"):
                filename = path.split("/api/backups/", 1)[1]
                try:
                    return self._json(store.read_backup(filename))
                except KeyError:
                    return self._json({"error": f"unknown backup {filename}"}, 404)

            if path == "/api/preflight":
                try:
                    return self._json(run_preflight())
                except Exception as e:
                    return self._json({"error": str(e)}, 502)

            if path == "/api/coverage":
                lat = float(qs["lat"][0])
                lon = float(qs["lon"][0])
                box_km = float(qs["box_km"][0])
                try:
                    return self._json(estimate_coverage(lat, lon, box_km))
                except Exception as e:
                    return self._json({"error": str(e)}, 502)

            if path == "/api/report":
                body = generate_report_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/geom":
                lat = float(qs["lat"][0])
                lon = float(qs["lon"][0])
                box_km = float(qs["box_km"][0])
                return self._json(exact_grid_corners(lat, lon, box_km))

            if path == "/api/geocode":
                q = qs.get("q", [""])[0].strip()
                if not q:
                    return self._json({"error": "missing q"}, 400)
                try:
                    return self._json({"results": geocode(q)})
                except Exception as e:
                    return self._json({"error": f"geocoding failed: {e}"}, 502)

            if path == "/api/views":
                return self._json(views_report())

            if path == "/api/backends":
                return self._json({"backends": backend_report(check=qs.get("check", ["0"])[0] == "1"),
                                   "default": default_backend()})

            if path == "/api/help":
                return self._file(os.path.join(HERE, "help_content.json"), "application/json; charset=utf-8")

            if path == "/api/validate":
                return self._json(V.validate_document(store.list(), P.CFG["min_box_km"], P.CFG["max_box_km"], VALID_ROLES).as_dict())

            if path == "/api/provenance":
                rec = provenance_record(qs.get("comments", ["0"])[0] == "1")
                body = json.dumps(rec, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                if qs.get("download", ["0"])[0] == "1":
                    self.send_header("Content-Disposition", 'attachment; filename="provenance.json"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/datasheet":
                md = PV.build_datasheet(store.list(), provenance_record(False)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                if qs.get("download", ["0"])[0] == "1":
                    self.send_header("Content-Disposition", 'attachment; filename="datasheet.md"')
                self.send_header("Content-Length", str(len(md)))
                self.end_headers()
                self.wfile.write(md)
                return

            m = re.match(r"^/api/imagery/([^/]+)/(stats|candidates|gapfill_test)$", path)
            if m:
                site_id, what = unquote(m.group(1)), m.group(2)
                site, lat, lon, p = self._imagery_request(site_id, qs)
                if what == "stats":
                    idx = [x for x in qs.get("indices", ["ndvi,ndwi,nbr2,bsi,aero_b1b2"])[0].split(",") if x]
                    return self._json(SERVICE.statistics(site_id, lat, lon, p, idx, qs.get("clear", ["0"])[0] == "1"))
                if what == "candidates":
                    thr = qs.get("threshold", [""])[0]
                    return self._json(SERVICE.candidates(
                        site_id, lat, lon, p, qs.get("kind", ["built_up"])[0], float(qs.get("percentile", ["90"])[0]),
                        float(thr) if thr != "" else None, int(qs.get("min_px", ["30"])[0])))
                return self._json(SERVICE.gapfill_test(site_id, lat, lon, p))

            if path.startswith("/api/preview/"):
                site_id = unquote(path.split("/api/preview/", 1)[1])
                site, lat, lon, p = self._imagery_request(site_id, qs)
                if qs.get("check_only", ["0"])[0] == "1":
                    # gallery: is a picture already cached? Never triggers a fetch.
                    key = SERVICE.key(site_id, lat, lon, p)
                    return self._json({"cached": SERVICE.cached(site_id, lat, lon, p),
                                       "view_rendered": os.path.exists(SERVICE.png_path(key, p))})
                try:
                    png_path, meta = SERVICE.render(site_id, lat, lon, p, force=qs.get("force", ["0"])[0] == "1")
                except (IS.ImageryError, BK.BackendError):
                    raise
                except Exception as e:
                    traceback.print_exc()
                    return self._json({"error": f"Could not get imagery: {type(e).__name__}: {e}"}, 502)
                with open(png_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("X-Preview-Meta", json.dumps(meta))
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return


            if path == "/api/studies/status":
                return self._json({"outcomes": STUDIES.outcomes_summary(), "registries": STUDIES.registry_list(),
                                   "forecast_model": bool(STUDIES.forecast_model()),
                                   "forecast_validation": STUDIES.last.get("forecast_validation"),
                                   "backends_with_targets": [k for k, b in BACKENDS.items() if k != "pc"]})

            if path in ("/api/studies/demo/outcomes", "/api/studies/demo/registry"):
                fn = "outcomes_demo.csv" if path.endswith("outcomes") else "registry_demo.csv"
                return self._file(os.path.join(DEMO_DIR, fn), "text/csv; charset=utf-8")

            if path == "/api/studies/groups":
                return self._json(STUDIES.groups(store.list(), qs.get("level", ["background"])[0]))

            if path == "/api/studies/duplicates/benchmark":
                n = int(qs.get("n_base", ["30"])[0])
                if not 10 <= n <= 80:
                    raise ValidationError("n_base must be between 10 and 80")
                return self._json(SS.synthetic_benchmark(n_base=n, seed=int(qs.get("seed", ["0"])[0])))

            if path == "/api/studies/forecast/predictions":
                return self._json(STUDIES.forecast_predictions(store.list()))

            if path == "/api/studies/registries":
                return self._json({"registries": STUDIES.registry_list()})

            if path == "/api/studies/outcomes":
                return self._json(STUDIES.outcomes_summary())

            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._err(e)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._allowed(True):
            return
        try:
            if path == "/api/studies/outcomes":
                body = self._body_json()
                return self._json({"ok": True, **STUDIES.set_outcomes(ST.as_text(body.get("csv", ""), "csv"))})

            if path == "/api/studies/groups":
                body = self._body_json()
                level = body.get("level", "background")
                res = STUDIES.groups(store.list(), level)
                if body.get("apply"):
                    doc = store.list()
                    snapshot = [copy.deepcopy(s) for s in doc["sites"]]
                    new_sites = []
                    for s in doc["sites"]:
                        s2 = copy.deepcopy(s)
                        gid = res["group_of"].get(s["id"])
                        if gid:
                            s2["overlap_group"] = gid
                        else:
                            s2.pop("overlap_group", None)
                        new_sites.append(s2)
                    store.replace_many(new_sites, action="overlap_groups")
                    push_undo({"type": "bulk_update", "site_id": None, "before": snapshot, "after": [copy.deepcopy(s) for s in new_sites]})
                    res["applied"] = True
                return self._json(res)

            if path == "/api/studies/shift":
                b = self._body_json()
                return self._json(STUDIES.shift(store.list(), ST.as_text(b.get("role_a", "train"), "role_a"), ST.as_text(b.get("role_b", "test"), "role_b"),
                                                ST.as_list(b.get("features"), "features", str, 40), int(ST.as_number(b.get("permutations", 200), "permutations", 1, 5000, int))))

            if path == "/api/studies/duplicates":
                b = self._body_json()
                return self._json(STUDIES.duplicates(store.list(), ST.as_text(b.get("backend") or default_backend(), "backend"), ST.as_text(b.get("source", "single"), "source"),
                                                     bool(b.get("fetch", False)), int(ST.as_number(b.get("limit", 60), "limit", 1, 200, int))))

            if path == "/api/studies/certificate":
                b = self._body_json()
                cert = STUDIES.certificate(store.list(), b)
                if b.get("download"):
                    body = json.dumps(cert, indent=2).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="split_certificate.json"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self._json(cert)

            if path == "/api/studies/forecast":
                b = self._body_json()
                kw = dict(target=ST.as_text(b.get("target", "yield"), "target"), features=ST.as_list(b.get("features"), "features", str, 40),
                          region_correction=bool(b.get("region_correction", True)))
                if b.get("action") == "fit":
                    return self._json(STUDIES.forecast_fit(store.list(), **kw))
                if b.get("action") == "compare":
                    return self._json(STUDIES.forecast_compare(store.list(), **kw))
                return self._json(STUDIES.forecast_validate(store.list(), **kw))

            if path == "/api/studies/registry":
                b = self._body_json()
                return self._json({"ok": True, **STUDIES.add_registry(b.get("name"), ST.as_text(b.get("text", ""), "text"), b.get("format") or None, ST.as_text(b.get("licence", ""), "licence", 300))})

            if path == "/api/studies/registry/wikidata":
                b = self._body_json()
                if not b.get("confirm"):
                    raise ValidationError("This sends a query to wikidata.org. Confirm that you want to go online.")
                import grounding as GR
                try:
                    query = GR.wikidata_query(ST.as_list(b.get("class_ids"), "class_ids", str, 20) or [], b.get("country") or None,
                                              int(ST.as_number(b.get("limit", 5000), "limit", 1, 20000, int)))
                except ValueError as e:
                    raise ST.StudyError(str(e)) from e
                try:
                    text = GR.fetch_wikidata(query)
                except Exception as e:
                    raise BK.BackendError(f"Wikidata could not be reached or refused the query ({type(e).__name__}). Check the internet connection and the class ids.") from e
                return self._json({"ok": True, **STUDIES.add_registry(b.get("name") or "wikidata", text, "wikidata", "Wikidata (CC0 1.0)")})

            if path == "/api/studies/grounding":
                b = self._body_json()
                return self._json(STUDIES.grounding(store.list(), bool(b.get("use_original", True))))

            if path == "/api/studies/grounding/evaluate":
                return self._json(STUDIES.grounding_evaluate(store.list()))

            if path == "/api/studies/sensitivity":
                b = self._body_json()
                sid = b.get("site_id")
                try:
                    return self._json(STUDIES.sensitivity(
                        store.list(), ST.as_text(sid, "site_id"), ST.as_text(b.get("backend") or default_backend(), "backend"),
                        b.get("distances") or SN_DEFAULT_DISTANCES, b.get("bearings") or SN_DEFAULT_BEARINGS,
                        ST.as_text(b.get("kind", "built_up"), "kind"), b.get("targets") or (), b.get("window_km", 10.0)))
                except KeyError:
                    raise NotFound(f"unknown site {sid}") from None

            if path == "/api/validate":
                body = self._body_json()
                doc = body.get("doc") if isinstance(body, dict) and "doc" in body else store.list()
                return self._json(V.validate_document(doc, P.CFG["min_box_km"], P.CFG["max_box_km"], VALID_ROLES).as_dict())

            if path == "/api/datasheet":
                body = self._body_json()
                rec = provenance_record(False)
                md = PV.build_datasheet(store.list(), rec, body.get("answers") or {})
                return self._json({"markdown": md, "gaps": PV.datasheet_gaps(md), "missing_sections": PV.datasheet_sections_present(md),
                                   "questions": {k: {"section": s, "question": q} for k, (s, q) in PV.QUESTIONS.items()}})

            if path == "/api/sites":
                fields = self._body_json()
                site = store.create(fields)
                push_undo({"type": "create", "site_id": site["id"], "before": None, "after": site})
                return self._json({"ok": True, "site": site}, 201)

            if path == "/api/sites/bulk_create":
                body = self._body_json()
                created = store.bulk_create(body.get("items", []))
                return self._json({"ok": True, "created": created, "count": len(created)}, 201)

            if path == "/api/sites/bulk":
                body = self._body_json()
                ids, action = body.get("ids", []), body.get("action")
                try:
                    snapshot = [copy.deepcopy(s) for s in store.list()["sites"] if s["id"] in set(ids)]
                except Exception:
                    snapshot = []
                try:
                    if action == "verify":
                        touched = store.bulk_update(ids, {"verified": True})
                    elif action == "unverify":
                        touched = store.bulk_update(ids, {"verified": False})
                    elif action == "reject":
                        touched = store.bulk_update(ids, {"rejected": True})
                    elif action in ("unreject", "pending"):
                        touched = store.bulk_update(ids, {"rejected": False, "verified": False})
                    elif action == "set_role":
                        touched = store.bulk_update(ids, {"role": body.get("role")})
                    else:
                        return self._json({"error": f"unknown bulk action {action!r}"}, 400)
                except KeyError as e:
                    return self._json({"error": f"unknown site ids: {e.args[0]}"}, 404)
                after = [copy.deepcopy(s) for s in store.list()["sites"] if s["id"] in set(touched)]
                push_undo({"type": "bulk_update", "site_id": None, "before": snapshot, "after": after})
                return self._json({"ok": True, "ids": touched})

            if path == "/api/sites/import":
                # Body: {sites:[...] (or doc:{sites:[...]}), policy:"skip"|"rename"|"overwrite",
                #        apply:false}. apply=false only reports what would happen.
                body = self._body_json()
                incoming = body.get("sites")
                if incoming is None and isinstance(body.get("doc"), dict):
                    incoming = body["doc"].get("sites")
                plan = store.import_sites(incoming, body.get("policy", "skip"),
                                          bool(body.get("apply", False)))
                return self._json({"ok": True, **plan})

            if path == "/api/sites/bulk_delete":
                body = self._body_json()
                try:
                    deleted = store.bulk_delete(body.get("ids", []))
                except KeyError as e:
                    return self._json({"error": f"unknown site ids: {e.args[0]}"}, 404)
                return self._json({"ok": True, "deleted": deleted})

            if path.startswith("/api/sites/") and path.endswith("/duplicate"):
                site_id = path[len("/api/sites/"):-len("/duplicate")].rstrip("/")
                try:
                    clone = store.duplicate(site_id)
                except KeyError:
                    return self._json({"error": f"unknown site {site_id}"}, 404)
                push_undo({"type": "duplicate", "site_id": clone["id"], "before": None, "after": clone})
                return self._json({"ok": True, "site": clone}, 201)

            if path.startswith("/api/backups/") and path.endswith("/restore"):
                filename = path[len("/api/backups/"):-len("/restore")].rstrip("/")
                try:
                    doc = store.restore_backup(filename)
                except KeyError:
                    return self._json({"error": f"unknown backup {filename}"}, 404)
                return self._json({"ok": True, "sites_count": len(doc["sites"])})

            if path == "/api/undo":
                try:
                    entry = do_undo()
                except ValidationError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "undone": entry})

            if path == "/api/redo":
                try:
                    entry = do_redo()
                except ValidationError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True, "redone": entry})

            if path.startswith("/api/sites/"):
                site_id = path.split("/api/sites/", 1)[1]
                patch = self._body_json()
                try:
                    before = dict(store.get(site_id))
                    updated = store.update(site_id, patch)
                except KeyError:
                    return self._json({"error": f"unknown site {site_id}"}, 404)
                push_undo({"type": "update", "site_id": site_id, "before": before, "after": dict(updated)})
                return self._json({"ok": True, "site": updated})

            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._err(e)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._allowed(True):
            return
        try:
            if path.startswith("/api/studies/registry/"):
                name = unquote(path.split("/api/studies/registry/", 1)[1])
                return self._json({"ok": STUDIES.delete_registry(name)})
            if path == "/api/studies/outcomes":
                STUDIES.clear_outcomes()
                return self._json({"ok": True})
            if path.startswith("/api/sites/"):
                site_id = path.split("/api/sites/", 1)[1]
                try:
                    deleted = store.delete(site_id)
                except KeyError:
                    return self._json({"error": f"unknown site {site_id}"}, 404)
                push_undo({"type": "delete", "site_id": site_id, "before": deleted, "after": None})
                return self._json({"ok": True, "deleted": deleted})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._err(e)


def self_check():
    """``python server.py --check``: does this installation work? Prints one line per check and returns the number of failures."""
    problems = 0

    def report(ok, text, advice=""):
        nonlocal problems
        print(("  ok    " if ok else "  FAIL  ") + text + ("" if ok else (" " + advice if advice else "")))
        problems += 0 if ok else 1

    print(f"TrigPoint v{VERSION} self-check")
    report(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "(3.10 or newer is needed)")
    for name, why in (("numpy", ""), ("scipy", ""), ("rasterio", ""), ("matplotlib", ""), ("requests", "")):
        try:
            mod = __import__(name)
            report(True, f"{name} {getattr(mod, '__version__', '')}".strip())
        except Exception as e:
            report(False, f"{name} is not installed ({type(e).__name__})", "Run: pip install -r requirements.txt")
    try:
        import ee  # noqa: F401
        print("  info  earthengine-api is installed (optional)")
    except Exception:
        print("  info  earthengine-api is not installed (optional; only the Earth Engine backend needs it)")
    res = V.validate_document(store.list(), P.CFG["min_box_km"], P.CFG["max_box_km"], VALID_ROLES)
    report(res.ok, f"sites file {SITES_PATH}: {len(store.list()['sites'])} sites, {len(res.errors)} error(s), {len(res.warnings)} warning(s)",
           "Open the file check in the tool for the messages.")
    for label, folder in (("cache", CACHE_DIR), ("backups", BACKUP_DIR), ("studies", STUDIES_DIR)):
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".write_test")
            with open(probe, "w") as f:
                f.write("x")
            os.remove(probe)
            report(True, f"can write to the {label} folder")
        except OSError as e:
            report(False, f"cannot write to the {label} folder {folder} ({e.strerror})", "Set a different folder with the matching SITE_CURATOR_*_DIR variable.")
    try:
        chip, _meta = BACKENDS["demo"].fetch(site_key="check", lat=10.0, lon=10.0, box_km=3.0, source="single")
        report(chip.shape[0] > 8, "the demo backend makes a picture")
    except Exception as e:
        report(False, f"the demo backend failed ({type(e).__name__}: {e})")
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        busy = s.connect_ex((HOST, PORT)) == 0
    finally:
        s.close()
    report(not busy, f"port {PORT} is free", "Another copy is running, or set SITE_CURATOR_PORT.")
    print("All checks passed." if not problems else f"{problems} check(s) failed.")
    return problems


def main():
    if "--check" in sys.argv[1:]:
        raise SystemExit(1 if self_check() else 0)
    # Windows lets two servers listen on one port, so a second copy would silently share
    # requests with the first and the browser could show the wrong site list. Refuse instead.
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        in_use = probe.connect_ex((HOST, PORT)) == 0
    finally:
        probe.close()
    if in_use:
        print(f"[server] Another TrigPoint is already running on http://{HOST}:{PORT}.")
        print("[server] Close its window (or stop its python process) and start this one again,")
        print(f"[server] or set SITE_CURATOR_PORT to a free port. This copy would have edited: {SITES_PATH}")
        raise SystemExit(1)
    threading.Thread(target=try_init_ee, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"[server] WARNING: listening on {HOST}. The tool has no sign-in; anyone who can reach this address can edit your sites file.")
    print(f"[server] TrigPoint v{VERSION} running at http://{HOST}:{PORT}")
    print(f"[server] editing: {SITES_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
