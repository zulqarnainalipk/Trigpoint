# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Uncertainty for the private-roster results: bootstrap over sites (coordinates) and over clusters of sites (forecast)."""
import csv, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import forecast as F, grounding as G
rng = np.random.default_rng(11)
B = 5000
out = {}

# ---- coordinates: matched sites at the default 100 km search distance
gr = json.load(open(os.path.join(HERE, "grounding_results.json")))
rows = [r for r in gr["per_site"] if r["registry_error_km"] is not None]
rec = np.array([r["recalled_error_km"] for r in rows]); reg = np.array([r["registry_error_km"] for r in rows]); dis = np.array([r["disagreement_km"] for r in rows])
big = rec > 5.0
n = len(rows)
aucs, dmed, share1 = [], [], []
for _ in range(B):
    i = rng.integers(0, n, n)
    a = G.auc(dis[i], big[i])
    if a is not None:
        aucs.append(a)
    dmed.append(np.median(rec[i]) - np.median(reg[i]))
    share1.append(np.mean(reg[i] <= 1) - np.mean(rec[i] <= 1))
ci = lambda v: [round(float(np.quantile(v, 0.025)), 3), round(float(np.quantile(v, 0.975)), 3)]
out["coordinates"] = {"matched": n, "positives_start_error_over_5km": int(big.sum()), "negatives": int((~big).sum()), "auc": round(float(G.auc(dis, big)), 3), "auc_ci95": ci(aucs),
                      "median_start": round(float(np.median(rec)), 2), "median_registry": round(float(np.median(reg)), 2), "median_difference_ci95": ci(dmed),
                      "share_within_1km_difference_ci95": ci(share1), "registry_wrong_over_5km": int((reg > 5).sum()), "registry_within_5km": int((reg <= 5).sum()),
                      "unmatched": 134 - n}
print(out["coordinates"], flush=True)

# ---- forecast: paired cluster bootstrap of the held-out error against the training mean, and full model against one number
tab = []
for r in csv.DictReader(open(os.path.join(HERE, "site_table.csv"), encoding="utf-8")):
    tab.append({k: (float(v) if v != "" and k not in ("id", "role", "region", "country", "verified", "has_screening") else v) for k, v in r.items()})
tab = [r for r in tab if r["has_screening"] == "True"]
full = F.validate(tab, F.DEFAULT_FEATURES, "yield", region_correction=False)
one = F.validate(tab, ["clear_frac"], "yield", region_correction=False)
ids = [s["id"] for s in full["sites"]]
byid = {r["id"]: r for r in tab}
rr = [byid[i] for i in ids]
y = np.array([r["yield"] for r in rr]); cl = F.clusters(rr, 150.0)
base = np.array([y[cl != c].mean() for c in cl])
ef = np.abs(np.array([s["forecast"] for s in full["sites"]]) - y)
e1 = np.abs(np.array([s["forecast"] for s in one["sites"]]) - y)
eb = np.abs(base - y)
ucl = np.unique(cl)
members = [np.nonzero(cl == c)[0] for c in ucl]
d_full, d_one, d_fo = [], [], []
for _ in range(B):
    pick = rng.integers(0, len(ucl), len(ucl))
    idx = np.concatenate([members[p] for p in pick])
    d_full.append(eb[idx].mean() - ef[idx].mean()); d_one.append(eb[idx].mean() - e1[idx].mean()); d_fo.append(e1[idx].mean() - ef[idx].mean())
out["forecast"] = {"sites": len(y), "clusters": int(len(ucl)), "sites_per_cluster_max": int(max(len(m) for m in members)), "clusters_with_one_site": int(sum(1 for m in members if len(m) == 1)),
                   "mae_baseline": round(float(eb.mean()), 4), "mae_full": round(float(ef.mean()), 4), "mae_one_number": round(float(e1.mean()), 4),
                   "baseline_minus_full_ci95": ci(d_full), "baseline_minus_one_ci95": ci(d_one), "one_minus_full_ci95": ci(d_fo),
                   "interval_coverage_full": full["interval_coverage"], "windows_per_site_median": float(np.median([r["windows"] for r in rr]))}
print(out["forecast"], flush=True)
json.dump(out, open(os.path.join(HERE, "uncertainty_private.json"), "w"), indent=1)
