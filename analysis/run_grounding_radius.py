# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import grounding as GR, studies as ST
ROOT = os.environ.get("OBSCURA_PRIVATE_ROOT", "")   # the private collection; not distributed
st = ST.Studies(os.path.join(os.environ["TEMP"], "wikidata_studies"), None, {}, "analysis")
doc = json.load(open(os.path.join(ROOT, "pipeline", "sites.json"), encoding="utf-8"))
regs = st.registries()
out = {}
for km in (300, 100, 50, 30):
    ev = GR.evaluate(doc["sites"], regs, search_km=float(km))
    ev.pop("sites")
    out[str(km)] = {k: ev[k] for k in ("n_with_registry_match", "recalled_on_matched_sites", "registry_on_matched_sites", "combined_policy", "disagreement_predicts_big_error_auc", "n_big_recalled_errors_among_matched", "status_counts")}
    r, c = ev["registry_on_matched_sites"], ev["recalled_on_matched_sites"]
    print(km, "matched", ev["n_with_registry_match"], "| recalled med/mean/max", c["median_km"], c["mean_km"], c["max_km"], "| registry med/mean/max/<=1km", r["median_km"], r["mean_km"], r["max_km"], r["within_1km"], "| combined med/mean", ev["combined_policy"]["median_km"], ev["combined_policy"]["mean_km"], "| AUC", ev["disagreement_predicts_big_error_auc"])
json.dump(out, open(os.path.join(HERE, "grounding_search_radius.json"), "w"), indent=1, default=str)
