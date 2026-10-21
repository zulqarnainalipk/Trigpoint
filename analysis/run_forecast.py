# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Forecast evaluation on the roster: leave-cluster-out error against guessing the mean, with ablations."""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import forecast as F

def load():
    rows = []
    for r in csv.DictReader(open(os.path.join(HERE, "site_table.csv"), encoding="utf-8")):
        rows.append({k: (float(v) if v != "" and k not in ("id", "role", "region", "country", "verified", "has_screening") else v) for k, v in r.items()})
    return [r for r in rows if r["has_screening"] == "True"]

rows = load()
out = {"n_sites": len(rows), "yield": {}, "availability": {}}
variants = {"clear_frac only": ["clear_frac"], "clear_frac + land_frac": ["clear_frac", "land_frac"], "all six screening numbers": F.DEFAULT_FEATURES}
for name, feats in variants.items():
    for rc in (False, True):
        v = F.validate(rows, feats, "yield", region_correction=rc)
        v.pop("sites")
        out["yield"][f"{name} | region correction {'on' if rc else 'off'}"] = v
        print(name, rc, v["mae"], v["mae_baseline"], v["skill"], v["r2"], v["spearman"], v["interval_coverage"], flush=True)
best = F.validate(rows, F.DEFAULT_FEATURES, "yield", region_correction=False)
fc = {s["id"]: s["forecast"] for s in best["sites"]}
out["yield_sites"] = best["sites"]
out["effort_saved"] = F.effort_saved(rows, fc)
for t in ("avail_ch4", "avail_no2", "avail_co", "avail_aai"):
    rr = [r for r in rows if r.get(t) not in ("", None)]
    v = F.validate(rr, F.DEFAULT_FEATURES, t, region_correction=False)
    v.pop("sites")
    out["availability"][t] = v
    print(t, v["n_sites"], v["mae"], v["mae_baseline"], v["skill"], v["spearman"], v["interval_coverage"], flush=True)
json.dump(out, open(os.path.join(HERE, "forecast_results.json"), "w"), indent=1)
print(json.dumps(out["effort_saved"], indent=1))
