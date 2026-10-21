"""Uncertainty for the placement study: spread across sites and a bootstrap over sites (the site is the unit).

Usage: python uncertainty_public.py [--results placement_public_results.json] [--out placement_public_uncertainty.json]
Each site's value at a shift is already the median over the eight directions; this script summarises those values over sites.
"""
import argparse, json, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--results", default="placement_public_results.json")
ap.add_argument("--out", default="placement_public_uncertainty.json")
a = ap.parse_args()
d = json.load(open(os.path.join(HERE, a.results), encoding="utf-8"))
ok = {k: v for k, v in d["sites"].items() if "error" not in v}
rng = np.random.default_rng(5)
B = 5000
def summ(v):
    v = np.asarray(v, float)
    idx = rng.integers(0, len(v), (B, len(v)))
    med = np.median(v[idx], axis=1)
    q1, q3 = np.quantile(v, [0.25, 0.75])
    return {"n": int(len(v)), "median": round(float(np.median(v)), 4), "iqr": [round(float(q1), 4), round(float(q3), 4)], "min": round(float(v.min()), 4), "max": round(float(v.max()), 4),
            "median_ci95": [round(float(np.quantile(med, 0.025)), 4), round(float(np.quantile(med, 0.975)), 4)]}
out = {"n_sites": len(ok), "failed": [k for k in d["sites"] if k not in ok], "facility_kept": {}, "gas_change_over_spread": {}, "share_sites_below_half_kept": {}, "box_km": summ([v["roster"]["box_km"] for v in ok.values()])}
for dist in d["distances"]:
    vals = [[x for x in v["by_distance"] if x["distance_km"] == dist][0]["median_retained"] for v in ok.values()]
    vals = [x for x in vals if x is not None]
    out["facility_kept"][str(dist)] = summ(vals)
    out["share_sites_below_half_kept"][str(dist)] = round(float(np.mean(np.array(vals) < 0.5)), 3)
for t in d["targets"]:
    out["gas_change_over_spread"][t] = {}
    for dist in d["distances"]:
        vals = []
        for v in ok.values():
            tv = (v.get("targets") or {}).get(t)
            if tv and "rows" in tv:
                r = [x for x in tv["rows"] if x["distance_km"] == dist]
                if r:
                    vals.append(r[0]["change_over_spread"])
        if vals:
            out["gas_change_over_spread"][t][str(dist)] = summ(vals)
json.dump(out, open(os.path.join(HERE, a.out), "w"), indent=1)
f = out["facility_kept"]
print("sites", out["n_sites"], "| kept at 1 km:", f["1.0"]["median"], f["1.0"]["iqr"], f["1.0"]["median_ci95"], "| below half:", out["share_sites_below_half_kept"]["1.0"])
for t, g in out["gas_change_over_spread"].items():
    print(t, {k: (v["median"], v["iqr"]) for k, v in g.items() if k in ("1.0", "10.0")})
