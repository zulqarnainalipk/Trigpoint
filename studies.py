"""The studies behind the curator's split-safety, forecast, grounding and placement tools.

This module joins the pure functions (``splitsafety``, ``forecast``, ``grounding``, ``sensitivity``) to a roster, the
imagery service and a small folder on disk where uploaded tables, registries and the fitted forecast are kept. It has
no HTTP in it, so every call can be tested directly.
"""
import csv
import io
import json
import math
import os
import threading

import curator_logic as CL
import forecast as FC
import grounding as GR
import backends as _B
import imagery_tools as it
import sensitivity as SN
import splitsafety as SS

B_TARGETS = _B.TARGETS
MAX_TABLE_ROWS = 20000
MAX_REGISTRY_ENTRIES = 200000
SCREEN_MAP = {"land_pct": ("land_frac", 0.01), "clear_pct": ("clear_frac", 0.01), "fire_days": ("fire_days", 1.0),
              "no2_contrast": ("no2_contrast", 1.0), "co_contrast": ("co_contrast", 1.0)}
TEXT_COLUMNS = {"id", "name", "role", "region", "country", "notes"}


class StudyError(ValueError):
    """A request that cannot be served, with a message for the person using the tool."""


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def as_list(v, name, kind=str, max_len=50):
    """A list of ``kind`` from a request value, or a StudyError that names the field."""
    if v is None:
        return None
    if not isinstance(v, (list, tuple)):
        raise StudyError(f"{name} must be a list.")
    if len(v) > max_len:
        raise StudyError(f"{name} has too many entries (the limit is {max_len}).")
    out = []
    for x in v:
        try:
            if kind is str and not isinstance(x, str):
                raise TypeError
            out.append(kind(x))
        except (TypeError, ValueError):
            raise StudyError(f"{name} must hold only {'text' if kind is str else 'numbers'}.") from None
    return out


def as_text(v, name, max_len=4 * 1024 * 1024):
    if not isinstance(v, str):
        raise StudyError(f"{name} must be text.")
    if len(v) > max_len:
        raise StudyError(f"{name} is too long.")
    return v


def as_number(v, name, lo, hi, kind=float):
    try:
        x = kind(v)
    except (TypeError, ValueError):
        raise StudyError(f"{name} must be a number.") from None
    if not (lo <= x <= hi) or (kind is float and not math.isfinite(x)):
        raise StudyError(f"{name} must be between {lo} and {hi}.")
    return x


class Studies:
    def __init__(self, data_dir, service=None, backends=None, version=""):
        self.dir = data_dir
        self.service = service
        self.backends = backends or {}
        self.version = version
        self.lock = threading.Lock()
        self.last = {}
        os.makedirs(self.dir, exist_ok=True)

    # ------------------------------------------------------------------ small storage

    def _path(self, name):
        return os.path.join(self.dir, name)

    def _load(self, name, default=None):
        try:
            with open(self._path(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self, name, obj):
        tmp = self._path(name) + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, self._path(name))

    # ------------------------------------------------------------------ outcomes table

    def set_outcomes(self, text):
        """Store a table with one row per site: ``id`` and any numbers (screening features, windows, ok_windows, targets)."""
        text = (text or "").lstrip("﻿")
        if not text.strip():
            raise StudyError("The table is empty.")
        rd = csv.DictReader(io.StringIO(text))
        if not rd.fieldnames or "id" not in [f.strip().lower() for f in rd.fieldnames]:
            raise StudyError("The table needs a column called id (the site id), then one column per number.")
        rows, seen = [], set()
        for raw in rd:
            row = {(k or "").strip(): v for k, v in raw.items() if k is not None}
            row = {("id" if k.lower() == "id" else k): v for k, v in row.items()}
            sid = (row.get("id") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            out = {"id": sid}
            for k, v in row.items():
                if k == "id" or not k:
                    continue
                if k in TEXT_COLUMNS:
                    out[k] = v.strip() if isinstance(v, str) and v.strip() else None
                else:
                    out[k] = _num(v)
            w, ok = out.get("windows"), out.get("ok_windows")
            if w and ok is not None and "yield" not in out:
                out["yield"] = round(ok / w, 6)
            rows.append(out)
            if len(rows) > MAX_TABLE_ROWS:
                raise StudyError(f"At most {MAX_TABLE_ROWS} rows are allowed.")
        if not rows:
            raise StudyError("No usable rows (each row needs an id).")
        self._save("outcomes.json", rows)
        return self.outcomes_summary()

    def outcomes(self):
        return self._load("outcomes.json", [])

    def outcomes_summary(self):
        rows = self.outcomes()
        cols = {}
        for r in rows:
            for k, v in r.items():
                if k != "id" and isinstance(v, (int, float)):
                    cols[k] = cols.get(k, 0) + 1
        return {"n_rows": len(rows), "numeric_columns": dict(sorted(cols.items())), "ids": [r["id"] for r in rows][:5]}

    def clear_outcomes(self):
        try:
            os.remove(self._path("outcomes.json"))
        except OSError:
            pass

    # ------------------------------------------------------------------ rows for the roster

    def rows_for_roster(self, doc, with_outcomes=True):
        """One row per active site: position, role, region, screening numbers from its notes, then the uploaded table over them."""
        table = {r["id"]: r for r in self.outcomes()} if with_outcomes else {}
        rows = []
        for s in doc.get("sites", []):
            if s.get("rejected"):
                continue
            row = {"id": s["id"], "role": s.get("role"), "region": s.get("region") or "unknown", "lat": s["center"][0], "lon": s["center"][1],
                   "box_km": s.get("box_km"), "country": s.get("country", "")}
            scr = CL.parse_screening(s.get("notes", "")) or {}
            for k, (name, mul) in SCREEN_MAP.items():
                if scr.get(k) is not None:
                    row[name] = scr[k] * mul
            for k, v in table.get(s["id"], {}).items():
                if k != "id" and v is not None and k not in ("role", "region", "country", "name", "notes"):
                    row[k] = v
                elif k in ("region",) and v and row["region"] == "unknown":
                    row["region"] = v
            rows.append(row)
        return rows

    def numeric_features(self, rows, min_share=0.5):
        skip = {"lat", "lon", "box_km", "windows", "ok_windows", "yield"}
        counts = {}
        for r in rows:
            for k, v in r.items():
                if k not in skip and not k.startswith(("avail_", "mean_")) and isinstance(v, (int, float)):
                    counts[k] = counts.get(k, 0) + 1
        return [k for k, n in counts.items() if n >= min_share * max(len(rows), 1)]

    # ------------------------------------------------------------------ overlap groups

    def groups(self, doc, level="background", cfg=None):
        sites = doc.get("sites", [])
        try:
            res = SS.overlap_groups(sites, level, cfg)
        except ValueError as e:
            raise StudyError(str(e)) from e
        summary = SS.group_summary(sites, cfg)
        res["summary"] = {"levels": summary["levels"]}
        res["pairs"] = summary["pairs"][:500]
        res["n_pairs_total"] = len(summary["pairs"])
        return res

    # ------------------------------------------------------------------ shift

    def shift(self, doc, role_a="train", role_b="test", features=None, permutations=200):
        rows = self.rows_for_roster(doc)
        feats = [f for f in (features or self.numeric_features(rows)) if f]
        if not feats:
            raise StudyError("No numeric features to compare. Upload a table or add screening numbers to the site notes.")
        res = SS.domain_shift(rows, feats, role_a, role_b)
        res["against_random"] = SS.shift_against_random(rows, feats, role_a, role_b, n_perm=int(max(20, min(permutations, 1000))))
        return res

    # ------------------------------------------------------------------ duplicates

    def duplicates(self, doc, backend="demo", source="single", fetch=False, limit=60, rule=None):
        """Near-duplicate chips among the roster's sites. Uses pictures already cached for this backend and source; with
        ``fetch`` it downloads the missing ones (at most ``limit`` in one call)."""
        if self.service is None:
            raise StudyError("No imagery service.")
        images, missing, fetched, errors = {}, [], 0, {}
        for s in doc.get("sites", []):
            if s.get("rejected"):
                continue
            lat, lon = s["center"]
            try:
                p = self.service.clean({"backend": backend, "source": source, "box_km": s["box_km"]})
            except Exception as e:
                raise StudyError(str(e)) from e
            if self.service.cached(s["id"], lat, lon, p):
                chip, _m, _k = self.service.get_chip(s["id"], lat, lon, p)
                images[s["id"]] = SS.chip_preview(chip)
            elif fetch and fetched < limit:
                try:
                    chip, _m, _k = self.service.get_chip(s["id"], lat, lon, p)
                    images[s["id"]] = SS.chip_preview(chip)
                    fetched += 1
                except Exception as e:
                    errors[s["id"]] = str(e)[:200]
                    missing.append(s["id"])
            else:
                missing.append(s["id"])
        res = SS.near_duplicates(images, rule)
        res.update({"backend": backend, "source": source, "missing": missing, "fetched_now": fetched, "errors": errors,
                    "synthetic": backend == "demo",
                    "note": "Chips are compared as small grey previews. Sites without a cached picture were not compared."})
        self.last["duplicates"] = res
        return res

    # ------------------------------------------------------------------ certificate

    def certificate(self, doc, params=None):
        p = params or {}
        sites = doc.get("sites", [])
        rows = self.rows_for_roster(doc)
        targets = None
        col = p.get("target_column")
        if col:
            targets = {r["id"]: r.get(col) for r in rows if r.get(col) is not None}
            if not targets:
                raise StudyError(f"No site has a value in column {col!r}.")
        dup = self.last.get("duplicates") if p.get("use_last_duplicates", True) else None
        shift = None
        if p.get("include_shift", True):
            roles = sorted({r["role"] for r in rows if r.get("role")})
            a, b = p.get("role_a", "train"), p.get("role_b", "test")
            feats = self.numeric_features(rows)
            if a in roles and b in roles and feats:
                shift = SS.domain_shift(rows, feats, a, b)
        cert = SS.build_certificate(sites, cfg=p.get("settings"), tool_version=self.version, targets=targets, time_info=p.get("time_info"),
                                    duplicates=dup, shift=shift)
        self.last["certificate"] = cert
        return cert

    # ------------------------------------------------------------------ forecast

    def forecast_validate(self, doc, target="yield", features=None, region_correction=True, cluster_km=FC.CLUSTER_KM):
        rows = self.rows_for_roster(doc)
        have = [r for r in rows if r.get(target) is not None]
        if len(have) < 10:
            raise StudyError(f"Only {len(have)} site(s) have a value for {target!r}; at least 10 are needed. Upload a table with one row per site.")
        wanted = features or list(FC.DEFAULT_FEATURES)
        feats = [f for f in wanted if sum(1 for r in have if r.get(f) is not None) >= 0.5 * len(have)]
        dropped = [f for f in wanted if f not in feats]
        if not feats:
            raise StudyError("No screening numbers found (land_frac, clear_frac, fire_days, aai_site, no2_contrast, co_contrast). Add them to the table.")
        res = FC.validate(have, feats, target, cluster_km=cluster_km, region_correction=region_correction)
        if all(r.get("windows") is not None and r.get("ok_windows") is not None for r in have) and target == "yield":
            res["effort_saved"] = FC.effort_saved(have, {s["id"]: s["forecast"] for s in res["sites"]})
        res["dropped_features"] = dropped
        self.last["forecast_validation"] = {k: v for k, v in res.items() if k != "sites"}
        return res

    def forecast_compare(self, doc, target="yield", features=None, region_correction=True, cluster_km=FC.CLUSTER_KM):
        rows = [r for r in self.rows_for_roster(doc) if r.get(target) is not None]
        if len(rows) < 10:
            raise StudyError(f"Only {len(rows)} site(s) have a value for {target!r}; at least 10 are needed.")
        wanted = features or list(FC.DEFAULT_FEATURES)
        feats = [f for f in wanted if sum(1 for r in rows if r.get(f) is not None) >= 0.5 * len(rows)]
        if not feats:
            raise StudyError("No screening numbers found to compare.")
        return FC.compare_models(rows, feats, target, cluster_km, region_correction)

    def forecast_fit(self, doc, target="yield", features=None, region_correction=True, cluster_km=FC.CLUSTER_KM):
        val = self.forecast_validate(doc, target, features, region_correction, cluster_km)
        rows = [r for r in self.rows_for_roster(doc) if r.get(target) is not None]
        model = FC.fit_final(rows, val["features"], target, cluster_km=cluster_km, region_correction=region_correction)
        model["validation"] = {k: v for k, v in val.items() if k not in ("sites", "effort_saved")}
        self._save("forecast_model.json", model)
        return model

    def forecast_model(self):
        return self._load("forecast_model.json")

    def forecast_predictions(self, doc):
        model = self.forecast_model()
        if not model:
            raise StudyError("No forecast model yet. Check the forecast on your table, then fit it.")
        out = {}
        for r in self.rows_for_roster(doc):
            out[r["id"]] = FC.predict(model, r)
        return {"target": model["target"], "n_sites": model["n_sites"], "validation": model.get("validation"), "predictions": out}

    # ------------------------------------------------------------------ registries and grounding

    def add_registry(self, name, text, fmt=None, licence=""):
        name = (name or "").strip()[:60] or "registry"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        try:
            reg = GR.parse_registry(text, name, fmt)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            raise StudyError(f"Could not read the registry: {e}") from e
        if not reg["entries"]:
            raise StudyError("No usable entries (each needs a name, a latitude and a longitude).")
        if len(reg["entries"]) > MAX_REGISTRY_ENTRIES:
            raise StudyError(f"At most {MAX_REGISTRY_ENTRIES} entries are allowed.")
        reg["licence"] = str(licence or "")[:300]
        self._save(f"registry_{safe}.json", reg)
        return {"name": name, "file": f"registry_{safe}.json", "n_entries": len(reg["entries"]), "skipped": reg["skipped"], "format": reg["format"],
                "licence": reg["licence"]}

    def registries(self):
        out = []
        for fn in sorted(os.listdir(self.dir)):
            if fn.startswith("registry_") and fn.endswith(".json"):
                reg = self._load(fn)
                if reg:
                    out.append(reg)
        return out

    def registry_list(self):
        return [{"name": r["source"], "n_entries": len(r["entries"]), "skipped": r.get("skipped", 0), "format": r.get("format"),
                 "licence": r.get("licence", "")} for r in self.registries()]

    def delete_registry(self, name):
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or ""))
        try:
            os.remove(self._path(f"registry_{safe}.json"))
            return True
        except OSError:
            return False

    def grounding(self, doc, use_original=True, **kw):
        regs = self.registries()
        if not regs:
            raise StudyError("No registry loaded. Add one (a CSV, GeoJSON or Wikidata result) first.")
        res = GR.ground_roster(doc.get("sites", []), regs, use_original=use_original, **kw)
        res["registries"] = [{"name": r["source"], "licence": r.get("licence", ""), "n_entries": len(r["entries"])} for r in regs]
        self.last["grounding"] = {k: res[k] for k in ("n_sites", "counts", "registries")}
        return res

    def grounding_evaluate(self, doc, **kw):
        regs = self.registries()
        if not regs:
            raise StudyError("No registry loaded.")
        return GR.evaluate(doc.get("sites", []), regs, **kw)

    # ------------------------------------------------------------------ placement sensitivity

    def sensitivity(self, doc, site_id, backend="demo", distances=SN.DISTANCES_KM, bearings=SN.BEARINGS_8, kind="built_up",
                    targets=(), window_km=10.0, period_days=365):
        if self.service is None:
            raise StudyError("No imagery service.")
        site = next((s for s in doc.get("sites", []) if s["id"] == site_id), None)
        if site is None:
            raise KeyError(site_id)
        distances = as_list(list(distances), "distances", float, 8)
        if not distances or any(not math.isfinite(d) or d <= 0 or d > 25 for d in distances):
            raise StudyError("Shift distances must be between 0 and 25 km.")
        bearings = [b % 360 for b in (as_list(list(bearings), "bearings", int, 16) or [])] or list(SN.BEARINGS_8)
        if kind not in it.MASK_KINDS:
            raise StudyError(f"kind must be one of {list(it.MASK_KINDS)}.")
        targets = as_list(list(targets or ()), "targets", str, 8) or []
        for t in targets:
            if t not in B_TARGETS:
                raise StudyError(f"unknown target {t!r}; choose from {list(B_TARGETS)}.")
        window_km = as_number(window_km, "window_km", 1.0, 50.0)
        box = float(site["box_km"])
        ctx = round(SN.context_km_needed(box, max(distances)), 2)
        if ctx > 40:
            raise StudyError(f"The largest shift needs a {ctx:g} km wide picture; the limit is 40 km. Use smaller shifts or a smaller box.")
        lat, lon = site["center"]
        if abs(lat) > 80:
            raise StudyError("The placement study does not work within 10 degrees of the poles (the map grid is not defined there).")
        try:
            p = self.service.clean({"backend": backend, "source": "single", "box_km": ctx}, max_box=40)
        except Exception as e:
            raise StudyError(str(e)) from e
        chip, meta, _key = self.service.get_chip(site_id, lat, lon, p)
        try:
            natural = self.service.get_donor(site_id, lat, lon, p)
        except Exception:
            natural = None
        res = SN.placement_study(chip, ctx, box, distances, bearings, natural_chip=natural, kind=kind)
        res["meta"] = meta
        res["synthetic"] = bool(meta.get("synthetic"))
        res["site_id"] = site_id
        res["tolerance_sweep"] = {"keeps_facility": SN.tolerance_sweep(res["by_distance"], "median_retained", (0.25, 0.5, 0.75)),
                                  "picture_correlation": SN.tolerance_sweep(res["by_distance"], "median_ncc", (0.5, 0.8, 0.9))}
        res["tolerance_km"] = {"keeps_facility": SN.tolerance_km(res["by_distance"], "median_retained", 0.5),
                               "picture_correlation_0_8": SN.tolerance_km(res["by_distance"], "median_ncc", 0.8)}
        if targets:
            bk = self.backends.get(backend)
            if bk is None or not hasattr(bk, "target_windows"):
                raise StudyError("This backend cannot give gas targets.")
            offs = SN.offsets(distances, bearings)
            positions = [(lat, lon)] + [SN.shifted_centre(lat, lon, o["de_km"], o["dn_km"]) for o in offs]
            tw = bk.target_windows(site_id, positions, window_km, list(targets))
            shifted = [{"distance_km": o["distance_km"], "bearing": o["bearing"], "values": s["values"]} for o, s in zip(offs, tw["shifted"])]
            res["targets"] = SN.target_sensitivity(tw["control"], shifted)
            res["targets_synthetic"] = bool(tw.get("synthetic"))
        self.last["sensitivity"] = {k: v for k, v in res.items() if k != "rows"}
        return res
