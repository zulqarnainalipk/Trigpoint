# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Near-duplicate chips and split-safety numbers on the real roster and dataset chips (offline, read-only)."""
import csv, glob, json, os, re, sys, time, collections
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
ROOT = os.environ.get("OBSCURA_PRIVATE_ROOT", "")   # the private collection; not distributed
import imagery_tools as it, splitsafety as SS

doc = json.load(open(os.path.join(ROOT, "pipeline", "sites.json"), encoding="utf-8"))
sites = doc["sites"]
res = {"n_sites": len(sites)}

# ---- overlap groups at every level and the certificate of the actual train/test split
res["groups"] = {k: v for k, v in SS.group_summary(sites)["levels"].items()}
pairs = SS.group_summary(sites)["pairs"]
res["pairs_ring"] = len(pairs)
res["pairs_background"] = sum(1 for p in pairs if "background" in p["relations"])
res["pairs_label"] = sum(1 for p in pairs if "label" in p["relations"])
res["pairs_box"] = sum(1 for p in pairs if "box" in p["relations"])
res["pairs_crossing_roles"] = [p for p in pairs if len(p["roles"]) > 1]
tab = {r["id"]: r for r in csv.DictReader(open(os.path.join(HERE, "site_table.csv"), encoding="utf-8"))}
targets = {s: float(tab[s]["mean_no2"]) for s in tab if tab[s]["mean_no2"] != ""}
cert = SS.build_certificate(sites, tool_version="analysis", targets=targets, time_info=None)
res["certificate_checks"] = {c["id"]: [c["status"], c["detail"]] for c in cert["checks"]}
res["certificate_verdict"] = cert["verdict"]
res["spatial_dependence"] = cert["spatial_dependence"]
res["min_distance_between_roles_km"] = cert["min_distance_between_roles_km"]

# ---- domain shift: actual split against random splits, and region split
rows = []
for r in tab.values():
    if r["has_screening"] != "True":
        continue
    d = {"id": r["id"], "role": r["role"], "region": r["region"]}
    for f in ("land_frac", "clear_frac", "fire_days", "aai_site", "no2_contrast", "co_contrast"):
        d[f] = float(r[f]) if r[f] != "" else None
    rows.append(d)
feats = ["land_frac", "clear_frac", "fire_days", "aai_site", "no2_contrast", "co_contrast"]
res["shift_train_test"] = SS.domain_shift(rows, feats, "train", "test")
res["shift_train_test_vs_random"] = SS.shift_against_random(rows, feats, "train", "test", n_perm=500, seed=1)
regs = collections.Counter(r["region"] for r in rows)
big = [k for k, _ in regs.most_common(2)]
reg_rows = [dict(r, role="a" if r["region"] == big[0] else "b") for r in rows if r["region"] in big]
res["shift_region_split"] = {"regions": big, "n": len(reg_rows), "vs_random": SS.shift_against_random(reg_rows, feats, "a", "b", n_perm=500, seed=2)}
print("groups/shift done", flush=True)

# ---- near duplicates on the real chips: one chip per site, then every chip against chips of other sites
json.dump(res, open(os.path.join(HERE, "split_results.json"), "w", encoding="utf-8"), indent=1, default=str)
cache = os.path.join(HERE, "previews.npz")
geo = glob.glob(os.path.join(ROOT, "outputs", "final", "private", "geo", "*_s2.tif"))
by_site = collections.defaultdict(list)
for f in geo:
    m = re.match(r"(.+)_(\d{4}-\d{2}-\d{2})_s2\.tif$", os.path.basename(f))
    if m:
        by_site[m.group(1)].append((m.group(2), f))
res["n_chip_files"] = len(geo)
t0 = time.time()
if os.path.exists(cache):
    z = np.load(cache, allow_pickle=False)
    prev = {k: z[k] for k in z.files}
else:
    prev = {}
    for sid, lst in by_site.items():
        for date, f in lst:
            prev[f"{sid}|{date}"] = SS.chip_preview(it.load_chip(f))
    np.savez_compressed(cache, **prev)
res["n_chips_loaded"] = len(prev)
print("previews", len(prev), round(time.time() - t0), "s", flush=True)
site_of = lambda k: k.split("|")[0]
role_of = {s["id"]: s["role"] for s in sites}
one = {sid: prev[f"{sid}|{sorted(d for d, _ in lst)[0]}"] for sid, lst in by_site.items()}
for cm in (0.5, 0.8):
    r1 = SS.near_duplicates(one, candidate_min=cm)
    res[f"one_chip_per_site_cm{cm}"] = {"n_images": r1["n_images"], "n_pairs": r1["n_pairs"], "examined": r1["pairs_examined"], "found": r1["found"]}
    print("site level", cm, "examined", r1["pairs_examined"], "found", len(r1["found"]), flush=True)
json.dump(res, open(os.path.join(HERE, "split_results.json"), "w", encoding="utf-8"), indent=1, default=str)
t0 = time.time()
r2 = SS.near_duplicates(prev, candidate_min=0.8, pair_filter=lambda a, b: site_of(a) != site_of(b))
res["all_chips_cross_site"] = {"candidate_min": 0.8, "n_images": r2["n_images"], "n_pairs": r2["n_pairs"], "examined": r2["pairs_examined"], "n_found": len(r2["found"]),
                               "found_top": r2["found"][:40], "secs": round(time.time() - t0),
                               "cross_role": sum(1 for p in r2["found"] if role_of.get(site_of(p["a"])) != role_of.get(site_of(p["b"])))}
print("all chips", r2["n_images"], "examined", r2["pairs_examined"], "found", len(r2["found"]), flush=True)
json.dump(res, open(os.path.join(HERE, "split_results.json"), "w", encoding="utf-8"), indent=1, default=str)
print("done")
