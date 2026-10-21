# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Fetch facility registries from Wikidata (CC0) with the tool's own query builder, one class at a time, and evaluate grounding."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.path.join(HERE, ".."), os.path.join(HERE, "..", "..", "trigpoint")):
    if os.path.exists(os.path.join(_c, "splitsafety.py")):
        sys.path.insert(0, os.path.abspath(_c))
        break
import grounding as GR, studies as ST
ROOT = os.environ.get("OBSCURA_PRIVATE_ROOT", "")   # the private collection; not distributed
classes = {"oil refinery": "Q12353044", "natural gas processing plant": "Q91396496", "LNG terminal": "Q15709854", "chemical plant": "Q905286",
           "mine": "Q820477", "steel mill": "Q2069494", "landfill": "Q152810", "power station": "Q159719"}
tmp = os.path.join(os.environ.get("TEMP", "."), "wikidata_studies")
st = ST.Studies(tmp, None, {}, "analysis")
log = {}
for name, qid in classes.items():
    t = time.time()
    try:
        text = GR.fetch_wikidata(GR.wikidata_query([qid], None, 20000))
        info = st.add_registry(f"wikidata-{name.replace(' ', '-')}", text, "wikidata", "Wikidata (CC0 1.0)")
        log[name] = {"qid": qid, "entries": info["n_entries"], "skipped": info["skipped"], "bytes": len(text), "secs": round(time.time() - t)}
    except Exception as e:
        log[name] = {"qid": qid, "error": f"{type(e).__name__}: {str(e)[:160]}", "secs": round(time.time() - t)}
    print(name, log[name], flush=True)
    time.sleep(2)
doc = json.load(open(os.path.join(ROOT, "pipeline", "sites.json"), encoding="utf-8"))
ev = st.grounding_evaluate(doc)
gr = st.grounding(doc, use_original=True)
sites = ev.pop("sites")
out = {"fetch": log, "evaluation": ev, "per_site": sites, "grounding_counts": gr["counts"], "registries": gr["registries"]}
json.dump(out, open(os.path.join(HERE, "grounding_results.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in ev.items() if k != "status_counts"}, indent=1))
print(ev["status_counts"], gr["counts"])
