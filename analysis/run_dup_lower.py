# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
import json, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import splitsafety as SS
z = np.load(os.path.join(HERE, "previews.npz"), allow_pickle=False)
prev = {k: z[k] for k in z.files}
site_of = lambda k: k.split("|")[0]
ids = list(prev)
res = {}
for cm in (0.6, 0.5):
    t = time.time()
    r = SS.near_duplicates(prev, candidate_min=cm, pair_filter=lambda a, b: site_of(a) != site_of(b))
    res[f"cm{cm}"] = {"examined": r["pairs_examined"], "found": len(r["found"]), "top": r["found"][:10], "secs": round(time.time() - t)}
    print(cm, "examined", r["pairs_examined"], "found", len(r["found"]), round(time.time() - t), "s", flush=True)
    if r["pairs_examined"] > 60000:
        break
json.dump(res, open(os.path.join(HERE, "dup_lower_threshold.json"), "w"), indent=1, default=str)
