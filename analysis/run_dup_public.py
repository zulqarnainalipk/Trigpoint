"""Near-duplicate search on the PUBLIC chips of OBSCURA-Open-25 (the 25 chips_*.zip files of the Zenodo record), so anyone can repeat it.

Usage: python run_dup_public.py --record-dir path/to/record_files [--tool path/to/trigpoint]
Writes dup_public_results.json (aggregate numbers only).
"""
import argparse, glob, io, json, os, sys, time, zipfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--record-dir", required=True)
ap.add_argument("--tool", default=os.path.abspath(os.path.join(HERE, "..")))
a = ap.parse_args()
sys.path.insert(0, a.tool)
import rasterio
from rasterio.io import MemoryFile
import imagery_tools as it, splitsafety as SS
prev = {}
t0 = time.time()
for z in sorted(glob.glob(os.path.join(a.record_dir, "chips_*.zip"))):
    site = os.path.basename(z)[6:-4]
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if not n.lower().endswith(".tif"):
                continue
            with MemoryFile(zf.read(n)) as mf, mf.open() as ds:
                prev[f"{site}|{n}"] = SS.chip_preview(it.from_array(ds.read()))
print("previews", len(prev), round(time.time() - t0), "s", flush=True)
site_of = lambda k: k.split("|")[0]
res = {"n_chips": len(prev), "n_sites": len({site_of(k) for k in prev}), "n_pairs_all": len(prev) * (len(prev) - 1) // 2, "n_pairs_cross_site": None}
t0 = time.time()
r = SS.near_duplicates(prev, candidate_min=0.6, pair_filter=lambda x, y: site_of(x) != site_of(y))
same = sum(1 for k in prev) 
res.update({"candidate_min": 0.6, "pairs_examined": r["pairs_examined"], "found_cross_site": len(r["found"]), "found_top": [{k: v for k, v in p.items() if k in ("a", "b", "ncc", "ssim", "transform")} for p in r["found"][:10]], "secs": round(time.time() - t0)})
print("cross-site examined", r["pairs_examined"], "found", len(r["found"]), flush=True)
# positive control: copies of real public previews, twelve kinds
rng = np.random.default_rng(7)
keys = list(prev)
sites = sorted({site_of(k) for k in keys})
pick = [next(k for k in keys if site_of(k) == s) for s in rng.choice(sites, size=min(20, len(sites)), replace=False)]
base = {k: prev[k] for k in pick}
tot = found = false = pairs = 0
per = {}
for kind in SS.AUGMENTATIONS:
    chosen = rng.choice(pick, size=10, replace=False)
    imgs = dict(base); truth = set()
    for k in chosen:
        cid = f"copy|{kind}|{k}"
        imgs[cid] = SS._augment(base[k], kind, rng) if kind != "shift 1-4 px" else np.roll(np.roll(base[k], int(rng.choice([-1, 1])), 0), int(rng.choice([-1, 1])), 1)
        truth.add(frozenset((k, cid)))
    rr = SS.near_duplicates(imgs)
    fl = {frozenset((p["a"], p["b"])) for p in rr["found"]}
    f_ = len(truth & fl); fa = len(fl - truth)
    per[kind] = {"copies": len(truth), "found": f_, "false_alarms": fa}
    tot += len(truth); found += f_; false += fa; pairs += rr["n_pairs"] - len(truth)
res["positive_control"] = {"copies": tot, "found": found, "false_alarms": false, "unrelated_pairs": pairs, "per_kind": per}
print("control", found, "/", tot, "false alarms", false, "of", pairs, flush=True)
json.dump(res, open(os.path.join(HERE, "dup_public_results.json"), "w"), indent=1)
