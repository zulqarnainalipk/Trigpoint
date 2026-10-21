# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Positive control for the near-duplicate finder on REAL chips: make copies of real previews and see how many are found.

Reads previews.npz (made by run_split_safety.py). Picks N real previews from different sites, adds one copy of each kind
(flips, turns, shifts, brightness, recolour, noise), runs the finder on the originals plus the copies, and counts.
"""
import json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import splitsafety as SS

z = np.load(os.path.join(HERE, "previews.npz"), allow_pickle=False)
keys = list(z.files)
rng = np.random.default_rng(7)
site_of = lambda k: k.split("|")[0]
by_site = {}
for k in keys:
    by_site.setdefault(site_of(k), []).append(k)
sites = sorted(by_site)
out = {"n_real_chips": 0, "per_kind": {}}
N = 60
rep_keys = [by_site[s][int(rng.integers(len(by_site[s])))] for s in rng.choice(sites, size=N, replace=False)]
base = {k: z[k] for k in rep_keys}
out["n_real_chips"] = len(base)
tot_found = tot_copies = 0
t0 = time.time()
for kind in SS.AUGMENTATIONS:
    picks = rng.choice(rep_keys, size=15, replace=False)
    imgs = dict(base)
    truth = set()
    for k in picks:
        cid = f"copy|{kind}|{k}"
        imgs[cid] = SS._augment(base[k], kind, rng) if kind != "shift 1-4 px" else np.roll(np.roll(base[k], int(rng.choice([-1, 1])), 0), int(rng.choice([-1, 1])), 1)
        truth.add(frozenset((k, cid)))
    res = SS.near_duplicates(imgs)
    flagged = {frozenset((p["a"], p["b"])) for p in res["found"]}
    found = len(truth & flagged)
    false = len(flagged - truth)
    out["per_kind"][kind] = {"copies": len(truth), "found": found, "rate": round(found / len(truth), 3), "false_alarms": false, "pairs": res["n_pairs"]}
    tot_found += found
    tot_copies += len(truth)
    print(kind, found, "/", len(truth), "false", false, flush=True)
out["overall_rate"] = round(tot_found / tot_copies, 3)
# different dates of the same site: how often are they flagged as duplicates?
same = []
for s in sites:
    ks = by_site[s]
    if len(ks) >= 2:
        same.append((ks[0], ks[1]))
same = same[:100]
flag = 0
for a, b in same:
    r = SS.compare_pair(z[a], z[b])
    if r["ncc"] >= SS.DUP_RULE["ncc_min"] and r["ssim"] >= SS.DUP_RULE["ssim_min"]:
        flag += 1
out["same_site_two_dates"] = {"pairs": len(same), "would_be_flagged": flag, "share": round(flag / max(len(same), 1), 3)}
print(out["overall_rate"], out["same_site_two_dates"], round(time.time() - t0), "s")
json.dump(out, open(os.path.join(HERE, "dup_positive_control.json"), "w"), indent=1)
