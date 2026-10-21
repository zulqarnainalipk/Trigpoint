"""Write worked examples of every study on the demo roster into examples/ (all synthetic, repeatable).

Usage: python tools/make_examples.py
The outputs are what the Studies window shows, saved as files, so a reader can see them without running the tool.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import backends as B
import imagery_service as IS
import studies as ST
import provenance as PV

OUT = os.path.join(HERE, "examples")
os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp(prefix="curator_examples_")
try:
    reg = {"demo": B.DemoBackend()}
    svc = IS.ImageryService(os.path.join(tmp, "cache"), reg)
    st = ST.Studies(os.path.join(tmp, "studies"), svc, reg, "examples")
    doc = json.load(open(os.path.join(HERE, "demo", "sites_demo.json"), encoding="utf-8"))
    note = {"synthetic": True, "note": "Made from the demo roster, the demo table and the demo registry. Nothing here is evidence about a real place."}

    def save(name, obj):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump({**note, **obj} if isinstance(obj, dict) else obj, f, indent=1, default=str)
        print("wrote", name)

    save("overlap_groups.json", st.groups(doc, "background"))
    st.duplicates(doc, "demo", "single", fetch=True)
    save("near_duplicates.json", {k: v for k, v in st.last["duplicates"].items() if k != "errors"})
    st.set_outcomes(open(os.path.join(HERE, "demo", "outcomes_demo.csv"), encoding="utf-8").read())
    save("domain_shift.json", st.shift(doc, "train", "test", permutations=200))
    val = st.forecast_validate(doc)
    save("forecast_validation.json", val)
    st.add_registry("demo-registry", open(os.path.join(HERE, "demo", "registry_demo.csv"), encoding="utf-8").read())
    save("grounding.json", st.grounding(doc, use_original=False))
    save("placement_demo.json", {k: v for k, v in st.sensitivity(doc, "ras_tanura_refinery", "demo", distances=(1, 2, 5), bearings=(0, 90, 180, 270), targets=("no2",)).items() if k != "rows"})
    cert = st.certificate(doc, {"time_info": {"train_end": "2023-12-31", "test_start": "2024-01-01"}, "target_column": "yield"})
    save("split_certificate.json", cert)
    save("provenance_demo.json", PV.build_provenance(doc, [], [], "examples", "sites_demo.json", False, studies={"split_certificate": {"verdict": cert["verdict"]}}))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
