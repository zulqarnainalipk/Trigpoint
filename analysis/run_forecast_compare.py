# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import forecast as F
rows = []
for r in csv.DictReader(open(os.path.join(HERE, "site_table.csv"), encoding="utf-8")):
    rows.append({k: (float(v) if v != "" and k not in ("id", "role", "region", "country", "verified", "has_screening") else v) for k, v in r.items()})
rows = [r for r in rows if r["has_screening"] == "True"]
out = {}
for t in ("yield", "avail_ch4"):
    rr = [r for r in rows if r.get(t) not in ("", None)]
    out[t] = F.compare_models(rr, ["clear_frac", "land_frac", "fire_days", "aai_site", "no2_contrast", "co_contrast"], t, region_correction=False)
    print(t, out[t]["reading"], [(m["model"], m["mae"], m["skill"]) for m in out[t]["models"]], flush=True)
json.dump(out, open(os.path.join(HERE, "forecast_compare.json"), "w"), indent=1)
