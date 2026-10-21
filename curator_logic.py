"""
Pure review logic for TrigPoint: no HTTP and no Earth Engine. server.py passes
the numbers it reads from core.CFG, so these functions are cheap to unit test
and cannot drift from the real limits.

Covers: screening flags written into notes by build_incubator.py, neighbours
within the split radius (pilot roster and other candidates), quality warnings,
export scopes (all / kept / verified / rejected, JSON and CSV) and a safe
import-merge planner.
"""

import copy
import csv
import io
import math
import re

import numpy as np

SPLIT_RADIUS_KM = 150.0     # candidates closer than this share a train/test split
DUPLICATE_KM = 2.0          # closer than this is treated as the same place
MOVED_EPS_DEG = 1e-7

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
EXPORT_SCOPES = ("all", "kept", "verified", "rejected")

CSV_COLUMNS = [
    "id", "name", "role", "lat", "lon", "box_km", "verified", "rejected", "priority",
    "country", "region", "facility_type", "setting", "coord_confidence",
    "original_lat", "original_lon", "notes", "comment",
]


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


class Pool:
    """A list of sites with their coordinates in arrays, so that distances to many sites are one numpy call.

    The review checks compare every site with every other site; in plain Python that is too slow for large rosters.
    """

    def __init__(self, sites):
        self.sites = list(sites)
        pts = [s["center"] for s in self.sites]
        self.lat = np.radians([p[0] for p in pts]) if pts else np.empty(0)
        self.lon = np.radians([p[1] for p in pts]) if pts else np.empty(0)
        self.cos = np.cos(self.lat)

    def dist(self, center):
        """Great-circle distance in km from ``center`` to every site of the pool."""
        if not self.sites:
            return np.empty(0)
        la, lo = math.radians(center[0]), math.radians(center[1])
        h = np.sin((self.lat - la) / 2) ** 2 + math.cos(la) * self.cos * np.sin((self.lon - lo) / 2) ** 2
        return 2 * 6371.0 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    return s or "site"


def review_state(site):
    """'rejected', 'verified' or 'pending'."""
    if site.get("rejected"):
        return "rejected"
    if site.get("verified"):
        return "verified"
    return "pending"


def centre_moved(site):
    """True when the centre differs from the stored original. A site with no
    stored original has never been moved through the curator."""
    orig = site.get("original_center")
    if not orig or len(orig) != 2:
        return False
    c = site["center"]
    return abs(c[0] - orig[0]) > MOVED_EPS_DEG or abs(c[1] - orig[1]) > MOVED_EPS_DEG


# ---------------------------------------------------------------------------
# screening flags written into notes by incubator/build_incubator.py
# ---------------------------------------------------------------------------

def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_screening(notes):
    """Read the screening sentence and the priority sentence out of a notes
    string. Returns None when the notes hold neither."""
    if not notes:
        return None
    out = {}
    m = re.search(r"land\s+(\d+(?:\.\d+)?)%", notes)
    if m:
        out["land_pct"] = float(m.group(1))
    m = re.search(r"(\d+)\s+of\s+(\d+)\s+Sentinel-2 scenes clear", notes)
    if m:
        out["s2_clear"], out["s2_all"] = int(m.group(1)), int(m.group(2))
        out["clear_pct"] = round(100.0 * out["s2_clear"] / out["s2_all"], 1) if out["s2_all"] else None
    m = re.search(r"NO2 contrast\s+(-?\d+(?:\.\d+)?|n/a)", notes)
    if m:
        out["no2_contrast"] = _num(m.group(1))
    m = re.search(r"CO contrast\s+(-?\d+(?:\.\d+)?|n/a)", notes)
    if m:
        out["co_contrast"] = _num(m.group(1))
    m = re.search(r"fire detection days\s+(\d+|n/a)", notes)
    if m:
        out["fire_days"] = _num(m.group(1))
    m = re.search(r"Priority\s+([ABC])(?:;\s*(.*?))?\.(?:\s|$)", notes)
    flags = []
    if m:
        out["priority"] = m.group(1)
        if m.group(2):
            flags = [f.strip() for f in m.group(2).split(";") if f.strip()]
    out["flags"] = flags
    if len(out) == 1 and not flags:      # only the empty "flags" key: nothing found
        return None
    return out


# ---------------------------------------------------------------------------
# neighbours and split groups
# ---------------------------------------------------------------------------

def _active(sites):
    return [s for s in sites if not s.get("rejected")]


def find_neighbors(center, sites, reference, exclude_id=None, radius=SPLIT_RADIUS_KM, pools=None):
    """Pilot sites and non-rejected candidates within `radius` km of `center`.

    ``pools`` is an optional ``(reference_pool, candidate_pool)`` of :class:`Pool` objects, so that a caller that asks many
    times (the full analysis) builds the arrays once.
    """
    ref_pool, cand_pool = pools or (Pool(reference), Pool(_active(sites)))
    out = []
    for source, pool in (("pilot", ref_pool), ("candidate", cand_pool)):
        d = pool.dist(center)
        for i in np.nonzero(d < radius)[0]:
            s = pool.sites[i]
            if s.get("id") == exclude_id:
                continue
            if source == "pilot":
                cons = f"Shares the {s.get('role', '?')} split of pilot site {s['id']}."
            else:
                cons = f"Same split group as candidate {s['id']}; the split is assigned later."
            out.append({"id": s["id"], "name": s.get("name", s["id"]), "source": source,
                        "role": s.get("role"), "distance_km": round(float(d[i]), 1),
                        "center": list(s["center"]), "consequence": cons})
    out.sort(key=lambda n: n["distance_km"])
    return out


class _DSU:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def split_groups(sites, reference, radius=SPLIT_RADIUS_KM):
    """Connected groups under the 'closer than radius' rule, over the pilot
    roster plus non-rejected candidates. Returns {candidate_id: info} with the
    pilot roles present in the group."""
    nodes = []   # (key, center, source, role)
    for s in reference:
        nodes.append((("pilot", s["id"]), s["center"], "pilot", s.get("role")))
    for s in _active(sites):
        nodes.append((("candidate", s["id"]), s["center"], "candidate", s.get("role")))
    dsu = _DSU([n[0] for n in nodes])
    pool = Pool([{"center": n[1]} for n in nodes])
    for i in range(len(nodes)):
        d = pool.dist(nodes[i][1])
        for j in np.nonzero(d[i + 1:] < radius)[0]:
            dsu.union(nodes[i][0], nodes[i + 1 + j][0])
    roles, members = {}, {}
    for key, _c, source, role in nodes:
        r = dsu.find(key)
        members.setdefault(r, []).append(key)
        if source == "pilot":
            roles.setdefault(r, set()).add(role)
    out = {}
    for key, _c, source, _role in nodes:
        if source != "candidate":
            continue
        r = dsu.find(key)
        pr = sorted(x for x in roles.get(r, set()) if x)
        out[key[1]] = {"group_size": len(members[r]), "pilot_roles": pr,
                       "conflict": len(pr) > 1,
                       "required_role": pr[0] if len(pr) == 1 else None}
    return out


# ---------------------------------------------------------------------------
# quality warnings
# ---------------------------------------------------------------------------

def quality_flags(site, sites, reference, groups, cfg, pools=None):
    """Warnings for one site. `cfg` needs min_box_km, max_box_km, label_box_km."""
    flags = []

    def add(code, severity, message):
        flags.append({"code": code, "severity": severity, "message": message})

    box = site.get("box_km")
    if box is None or not (cfg["min_box_km"] <= box <= cfg["max_box_km"]):
        add("box_range", "critical",
            f"Box size {box} km is outside {cfg['min_box_km']:g} to {cfg['max_box_km']:g} km; "
            "the file check will refuse this file.")

    if site.get("rejected"):
        return flags     # rejected sites are out of the final file; skip the rest

    label_km = cfg["label_box_km"]
    ref_pool, cand_pool = pools or (Pool(reference), Pool(_active(sites)))
    for source, pool in (("pilot site", ref_pool), ("candidate", cand_pool)):
        dist = pool.dist(site["center"])
        for i in np.nonzero(dist < max(label_km, DUPLICATE_KM))[0]:
            o, d = pool.sites[i], float(dist[i])
            if o.get("id") == site["id"]:
                continue
            if d < DUPLICATE_KM:
                add("duplicate_position", "critical",
                    f"Near-duplicate position: {source} {o['id']} is {d:.1f} km away.")
            elif d < label_km:
                add("label_overlap", "warning",
                    f"The {label_km:g} km label window overlaps {source} {o['id']} ({d:.1f} km away).")

    g = groups.get(site["id"])
    if g and g["conflict"]:
        add("split_conflict", "critical",
            "The 150 km group around this site holds pilot sites in both "
            f"{' and '.join(g['pilot_roles'])}, so no single split fits.")
    elif g and g["required_role"] and site.get("role") != g["required_role"]:
        add("split_role_mismatch", "info",
            f"Role is {site.get('role')} but the pilot sites within 150 km are "
            f"{g['required_role']}; this site must take the {g['required_role']} split.")

    sc = parse_screening(site.get("notes", ""))
    if sc:
        for f in sc.get("flags", []):
            if "mostly water" in f:
                add("mostly_water", "warning", "Screening: " + f + ".")
            else:
                add("screening_flag", "info", "Screening: " + f + ".")

    conf = site.get("coord_confidence")
    if conf == "low" and not site.get("verified"):
        add("low_confidence", "info", "Coordinate confidence is low; check the centre and box carefully.")
    if site.get("verified") and not centre_moved(site) and conf != "high":
        add("centre_unchanged", "warning",
            "Marked verified but the centre is still the original value "
            f"(confidence {conf or 'unknown'}). Confirm it sits on the facility.")
    if not site.get("verified"):
        add("not_verified", "info", "Not verified yet.")

    flags.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])
    return flags


def build_analysis(doc, reference, cfg, radius=SPLIT_RADIUS_KM):
    sites = doc["sites"]
    groups = split_groups(sites, reference, radius)
    pools = (Pool(reference), Pool(_active(sites)))
    per = {}
    n_crit = n_warn = 0
    for s in sites:
        nb = find_neighbors(s["center"], sites, reference, s["id"], radius, pools)
        q = quality_flags(s, sites, reference, groups, cfg, pools)
        worst = min((SEVERITY_ORDER[f["severity"]] for f in q if f["code"] != "not_verified"),
                    default=3)
        if not s.get("rejected"):
            n_crit += worst == 0
            n_warn += worst == 1
        pilots = [n for n in nb if n["source"] == "pilot"]
        g = groups.get(s["id"], {})
        per[s["id"]] = {
            "state": review_state(s),
            "screening": parse_screening(s.get("notes", "")),
            "neighbors": nb,
            "nearest_pilot_km": pilots[0]["distance_km"] if pilots else None,
            "required_role": g.get("required_role"),
            "split_conflict": bool(g.get("conflict")),
            "quality": q,
            "worst": ["critical", "warning", "info", None][worst],
            "moved": centre_moved(s),
        }
    counts = {"total": len(sites), "verified": 0, "rejected": 0, "pending": 0}
    for s in sites:
        counts[review_state(s)] += 1
    return {"radius_km": radius, "sites": per,
            "summary": {**counts, "critical": n_crit, "warning": n_warn,
                        "reference_count": len(reference)}}


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def export_doc(doc, scope="all", comments=True):
    """Return a copy of the document limited to `scope`. With scope 'all' and
    comments=True the result equals the stored document."""
    if scope not in EXPORT_SCOPES:
        raise ValueError(f"scope must be one of {EXPORT_SCOPES}")
    out = {k: copy.deepcopy(v) for k, v in doc.items() if k != "sites"}
    sites = doc["sites"]
    if scope == "kept":
        sites = [s for s in sites if not s.get("rejected")]
    elif scope == "verified":
        sites = [s for s in sites if s.get("verified") and not s.get("rejected")]
    elif scope == "rejected":
        sites = [s for s in sites if s.get("rejected")]
    sites = copy.deepcopy(sites)
    for s in sites:
        if scope in ("kept", "verified"):
            s.pop("rejected", None)
        if not comments:
            s.pop("comment", None)
    out["sites"] = sites
    return out


def export_csv(doc, scope="all", comments=True):
    sub = export_doc(doc, scope, comments)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for s in sub["sites"]:
        orig = s.get("original_center") or ["", ""]
        row = {
            "id": s["id"], "name": s.get("name", ""), "role": s.get("role", ""),
            "lat": s["center"][0], "lon": s["center"][1], "box_km": s.get("box_km", ""),
            "verified": "true" if s.get("verified") else "false",
            "rejected": "true" if s.get("rejected") else "false",
            "priority": s.get("priority") or "", "country": s.get("country", ""),
            "region": s.get("region", ""), "facility_type": s.get("facility_type", ""),
            "setting": s.get("setting", ""), "coord_confidence": s.get("coord_confidence", ""),
            "original_lat": orig[0], "original_lon": orig[1],
            "notes": s.get("notes", ""), "comment": s.get("comment", "") if comments else "",
        }
        w.writerow([row[c] for c in CSV_COLUMNS])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# import / merge planning
# ---------------------------------------------------------------------------

IMPORT_POLICIES = ("skip", "rename", "overwrite")


def _clean_incoming(raw, index, cfg):
    """Validate and normalise one incoming site. Returns (site, note) or
    raises ValueError with the reason."""
    if not isinstance(raw, dict):
        raise ValueError("not an object")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("missing name")
    role = raw.get("role", "train")
    if role not in ("train", "test", "decoy"):
        raise ValueError(f"role {role!r} is not train, test or decoy")
    c = raw.get("center")
    if c is None and "lat" in raw and "lon" in raw:
        c = [raw["lat"], raw["lon"]]
    try:
        lat, lon = float(c[0]), float(c[1])
    except (TypeError, ValueError, IndexError, KeyError):
        raise ValueError("centre must be [lat, lon] numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"centre {lat}, {lon} is out of range")
    note = None
    try:
        box = float(raw.get("box_km", 3.0))
    except (TypeError, ValueError):
        raise ValueError("box_km must be a number")
    lo, hi = cfg["min_box_km"], cfg["max_box_km"]
    if not (lo <= box <= hi):
        note = f"box_km {box:g} clamped to {lo:g} to {hi:g}"
        box = min(max(box, lo), hi)
    site = {k: copy.deepcopy(v) for k, v in raw.items() if k not in ("lat", "lon")}
    site["id"] = str(raw.get("id") or "").strip() or slugify(name)
    site["name"], site["role"] = name, role
    site["center"] = [round(lat, 6), round(lon, 6)]
    site["box_km"] = round(box, 2)
    site["verified"] = bool(raw.get("verified", False))
    site["notes"] = str(raw.get("notes", ""))[:2000]
    if site.get("rejected") is not None:
        site["rejected"] = bool(site["rejected"])
        if not site["rejected"]:
            site.pop("rejected")
    return site, note


def plan_import(existing_sites, incoming, policy, cfg, near_km=DUPLICATE_KM):
    """Work out what merging `incoming` into `existing_sites` would do.

    policy decides what happens when an incoming id already exists:
      skip       keep the existing site, drop the incoming one
      rename     import the incoming site under a new id (id_2, id_3, ...)
      overwrite  replace the existing site (its private comment and stored
                 original centre are kept when the incoming one has none)
    Nothing is mutated; the caller writes `result_sites` if it applies the plan.
    """
    if policy not in IMPORT_POLICIES:
        raise ValueError(f"policy must be one of {IMPORT_POLICIES}")
    result = [copy.deepcopy(s) for s in existing_sites]
    by_id = {s["id"]: i for i, s in enumerate(result)}
    plan = {"new": [], "skipped": [], "renamed": [], "overwritten": [],
            "invalid": [], "clamped": [], "near": []}
    for idx, raw in enumerate(incoming):
        try:
            site, note = _clean_incoming(raw, idx, cfg)
        except ValueError as e:
            rid = raw.get("id") if isinstance(raw, dict) else None
            plan["invalid"].append({"index": idx, "id": rid, "reason": str(e)})
            continue
        if note:
            plan["clamped"].append({"id": site["id"], "note": note})
        sid = site["id"]
        policy_here = policy            # an id repeated inside the incoming file is handled like any other clash
        if sid in by_id:
            if policy_here == "skip":
                plan["skipped"].append({"id": sid, "reason": "id already exists"})
                continue
            if policy_here == "overwrite":
                old = result[by_id[sid]]
                for keep in ("comment", "original_center"):
                    if keep in old and keep not in site:
                        site[keep] = old[keep]
                result[by_id[sid]] = site
                plan["overwritten"].append({"id": sid})
                continue
            n = 2
            while f"{sid}_{n}" in by_id:
                n += 1
            new_id = f"{sid}_{n}"
            plan["renamed"].append({"from": sid, "to": new_id})
            site["id"] = new_id
            sid = new_id
        for other in result:
            if other["id"] == sid or other.get("rejected"):
                continue
            d = haversine_km(site["center"], other["center"])
            if d < near_km:
                plan["near"].append({"id": sid, "other": other["id"], "distance_km": round(d, 2)})
        by_id[sid] = len(result)
        result.append(site)
        plan["new"].append({"id": sid})
    plan["result_sites"] = result
    plan["counts"] = {k: len(plan[k]) for k in
                      ("new", "skipped", "renamed", "overwritten", "invalid", "clamped", "near")}
    return plan
