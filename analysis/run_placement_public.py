"""Placement study on the 25 PUBLIC sites of OBSCURA-Open-25 (doi:10.5281/zenodo.23450639), so anyone can repeat it.

Needs the record's sites.csv and an Earth Engine account (EE_SERVICE_ACCOUNT_KEY_FILE or `earthengine authenticate`, and EE_PROJECT).
Usage: python run_placement_public.py --sites-csv path/to/sites.csv [--out placement_public_results.json] [--limit N]
"""
import argparse, csv, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--sites-csv", required=True)
ap.add_argument("--out", default="placement_public_results.json")
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--first", type=int, default=0, help="start at this site (0-based), so several runs can share the work")
ap.add_argument("--targets", default="no2,co,ch4,aai")
ap.add_argument("--distances", default="1,2,5,10")
ap.add_argument("--tool", default=os.path.abspath(os.path.join(HERE, "..")))
ap.add_argument("--cache", default=os.path.join(os.environ.get("TEMP", "."), "placement_public_cache"))
a = ap.parse_args()
sys.path.insert(0, a.tool)
import core, backends as B, imagery_service as IS, studies as ST
core.init_earth_engine()
reg = B.registry(ee_ready=lambda: True)
svc = IS.ImageryService(a.cache, reg)
st = ST.Studies(os.path.join(a.cache, "studies"), svc, reg, "analysis")
sites = []
for r in csv.DictReader(open(a.sites_csv, encoding="utf-8")):
    sites.append({"id": r["site_id"], "name": r["site_name"], "role": "train", "center": [float(r["latitude"]), float(r["longitude"])], "box_km": float(r["box_km"]),
                  "facility_type": r["facility_type"], "region": r["region"]})
if a.limit:
    sites = sites[:a.limit]
sites = sites[a.first:]
doc = {"sites": sites}
dist = [float(x) for x in a.distances.split(",")]
outp = os.path.join(HERE, a.out)
out = json.load(open(outp, encoding="utf-8")) if os.path.exists(outp) else {"distances": dist, "targets": a.targets.split(","), "sites": {}}
for s in sites:
    sid = s["id"]
    if sid in out["sites"] and "error" not in out["sites"][sid]:
        continue
    t = time.time()
    try:
        r = st.sensitivity(doc, sid, "ee", distances=dist, bearings=[0, 45, 90, 135, 180, 225, 270, 315], kind="built_up", targets=[x for x in a.targets.split(",") if x])
        r.pop("rows", None)
        r["roster"] = {"box_km": s["box_km"], "facility_type": s["facility_type"], "region": s["region"], "name": s["name"]}
        out["sites"][sid] = r
        print(sid, "ok", round(time.time() - t), "s", r["tolerance_km"], flush=True)
    except Exception as e:
        out["sites"][sid] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
        print(sid, "FAILED", out["sites"][sid]["error"], flush=True)
    json.dump(out, open(outp, "w", encoding="utf-8"), indent=1, default=str)
