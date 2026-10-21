"""Forecast, registry check and overlap groups on the 25 PUBLIC sites of OBSCURA-Open-25 (doi:10.5281/zenodo.23450639).

Needs the record's sites.csv, an Earth Engine account (screening numbers) and the internet (Wikidata). Writes public_extras_results.json.
Usage: python run_public_extras.py --sites-csv RECORD/sites.csv
"""
import argparse, csv, json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--sites-csv", required=True)
ap.add_argument("--tool", default=os.path.abspath(os.path.join(HERE, "..")))
ap.add_argument("--screen-year", default="2021")
ap.add_argument("--out", default="public_extras_results.json")
a = ap.parse_args()
sys.path.insert(0, a.tool)
import core, forecast as F, grounding as GR, splitsafety as SS, studies as ST, imagery_tools
rows = list(csv.DictReader(open(a.sites_csv, encoding="utf-8")))
sites = [{"id": r["site_id"], "name": r["site_name"], "role": "train", "country": r["country"], "region": r["region"], "center": [float(r["latitude"]), float(r["longitude"])],
          "box_km": float(r["box_km"]), "n_samples": int(r["n_samples"]), "n_windows": int(r["n_windows_attempted"])} for r in rows]
out = {"n_sites": len(sites)}

# ---- screening numbers from Earth Engine, for the year before the collection
core.init_earth_engine()
import ee
Y0, Y1 = f"{a.screen_year}-01-01", f"{int(a.screen_year) + 1}-01-01"
wm = ee.ImageCollection("MODIS/006/MOD44W").sort("system:time_start", False).first().select("water_mask")
land = wm.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=512).reproject(ee.Projection("EPSG:4326").atScale(1113.2)).lt(0.2)
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(Y0, Y1)
for s in sites:
    lat, lon = s["center"]
    pt = ee.Geometry.Point([lon, lat])
    win = pt.buffer(5000).bounds()
    lf = land.rename("v").reduceRegion(ee.Reducer.mean(), win, 1113.2).get("v")
    col = s2.filterBounds(pt)
    n_all = col.size(); n_clear = col.filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)).size()
    vals = core.with_retry(lambda: ee.Dictionary({"land": lf, "all": n_all, "clear": n_clear}).getInfo(), f"screen {s['id']}")
    s["land_frac"] = vals["land"]; s["s2_all"] = vals["all"]; s["clear_frac"] = (vals["clear"] / vals["all"]) if vals["all"] else None
    s["yield"] = s["n_samples"] / s["n_windows"]
    print("screened", s["id"], s["clear_frac"], s["land_frac"], flush=True)
out["screening"] = {"year": a.screen_year, "note": "share of Sentinel-2 scenes under 30% cloud over the site point; land share of the 10 km window (MODIS water mask)"}

# ---- forecast on 25 sites, leave-cluster-out
use = [s for s in sites if s["clear_frac"] is not None]
feats = ["clear_frac", "land_frac"]
for s in use:
    s["lat"], s["lon"] = s["center"]
full = F.validate(use, feats, "yield", region_correction=False)
one = F.validate(use, ["clear_frac"], "yield", region_correction=False)
ids = [x["id"] for x in full["sites"]]; byid = {s["id"]: s for s in use}; rr = [byid[i] for i in ids]
y = np.array([r["yield"] for r in rr]); cl = F.clusters(rr, 150.0)
base = np.array([y[cl != c].mean() for c in cl])
ef = np.abs(np.array([x["forecast"] for x in full["sites"]]) - y); e1 = np.abs(np.array([x["forecast"] for x in one["sites"]]) - y); eb = np.abs(base - y)
ucl = np.unique(cl); members = [np.nonzero(cl == c)[0] for c in ucl]
rng = np.random.default_rng(11); d_full, d_one, d_fo = [], [], []
for _ in range(5000):
    idx = np.concatenate([members[p] for p in rng.integers(0, len(ucl), len(ucl))])
    d_full.append(eb[idx].mean() - ef[idx].mean()); d_one.append(eb[idx].mean() - e1[idx].mean()); d_fo.append(e1[idx].mean() - ef[idx].mean())
ci = lambda v: [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)]
out["forecast"] = {"sites": len(y), "clusters": int(len(ucl)), "clusters_with_one_site": int(sum(1 for m in members if len(m) == 1)), "largest_cluster": int(max(len(m) for m in members)),
                   "mae_baseline": round(float(eb.mean()), 4), "mae_two_numbers": round(float(ef.mean()), 4), "mae_clear_scene_only": round(float(e1.mean()), 4),
                   "baseline_minus_two_ci95": ci(d_full), "baseline_minus_clear_ci95": ci(d_one), "clear_minus_two_ci95": ci(d_fo),
                   "r2_two": full["r2"], "spearman_two": full["spearman"], "interval_coverage_two": full["interval_coverage"], "yield_min": round(float(y.min()), 3), "yield_max": round(float(y.max()), 3),
                   "sites_detail": [{"observed": round(float(o), 4), "forecast": x["forecast"], "low": x["low"], "high": x["high"]} for o, x in zip(y, full["sites"])]}
print("forecast", {k: v for k, v in out["forecast"].items() if k != "sites_detail"}, flush=True)

# ---- overlap groups (all sites in one role: only the geometry is checked)
gs = SS.group_summary(sites)
out["overlap"] = {"pairs_by_level": {lv: v["n_pairs"] for lv, v in gs["levels"].items()}, "groups_by_level": {lv: v["n_groups"] for lv, v in gs["levels"].items()},
                  "multi_site_groups_at_ring": gs["levels"]["ring"]["n_multi_site_groups"], "pairs": [{"a": p["a"], "b": p["b"], "km": p["distance_km"], "levels": p["relations"]} for p in gs["pairs"]]}
print("overlap", out["overlap"]["pairs_by_level"], flush=True)

# ---- registry check against Wikidata (seven classes), error against the verified centre
classes = {"oil refinery": "Q12353044", "natural gas processing plant": "Q91396496", "LNG terminal": "Q15709854", "chemical plant": "Q905286", "mine": "Q820477", "steel mill": "Q2069494", "landfill": "Q152810"}
tmp = os.path.join(os.environ.get("TEMP", "."), "wikidata_public")
st = ST.Studies(tmp, None, {}, "analysis")
fetch = {}
for name, q in classes.items():
    try:
        text = GR.fetch_wikidata(GR.wikidata_query([q], None, 20000))
        info = st.add_registry("wikidata-" + name.replace(" ", "-"), text, "wikidata", "Wikidata (CC0 1.0)")
        fetch[name] = {"qid": q, "entries": info["n_entries"]}
    except Exception as e:
        fetch[name] = {"qid": q, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    print("wikidata", name, fetch[name], flush=True); time.sleep(2)
regs = st.registries()
rec_err, reg_err = [], []
detail = []
for s in sites:
    g = GR.ground_site(s, regs)
    top = max([m for m in g["matches"] if m["matched"]], key=lambda m: m["name_score"], default=None)
    if top:
        e = SS.haversine_km(s["center"], (top["entry"]["lat"], top["entry"]["lon"]))
        reg_err.append(e); detail.append({"registry_error_km": round(e, 2), "name_score": top["name_score"], "source": top["source"]})
sw = lambda v, t: round(float(np.mean(np.array(v) <= t)), 3) if len(v) else None
out["registry"] = {"classes": fetch, "entries_total": sum(v.get("entries", 0) for v in fetch.values()), "matched": len(reg_err), "of": len(sites),
                   "median_error_km": round(float(np.median(reg_err)), 2) if reg_err else None, "within_1km": sw(reg_err, 1), "within_2km": sw(reg_err, 2), "within_5km": sw(reg_err, 5),
                   "max_error_km": round(float(max(reg_err)), 2) if reg_err else None, "detail": detail,
                   "note": "error of the registry position against the verified centre; the starting coordinates of the public record are not published, so they are not compared"}
print("registry", {k: v for k, v in out["registry"].items() if k not in ("detail", "classes")}, flush=True)
json.dump(out, open(os.path.join(HERE, a.out), "w"), indent=1, default=str)
