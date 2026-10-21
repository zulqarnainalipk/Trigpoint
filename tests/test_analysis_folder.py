"""The analysis folder: scripts parse, results are valid JSON, and nothing private is in it."""
import ast
import glob
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(HERE, "analysis")


def test_every_analysis_script_parses_and_has_no_personal_path():
    scripts = glob.glob(os.path.join(AN, "*.py"))
    assert len(scripts) >= 12
    for f in scripts:
        text = open(f, encoding="utf-8").read()
        ast.parse(text)
        assert "ZA Research" not in text and "C:\\Users" not in text, f


def test_public_results_exist_and_are_complete():
    r = json.load(open(os.path.join(AN, "results", "placement_public_results.json"), encoding="utf-8"))
    assert len(r["sites"]) == 25 and not [k for k, v in r["sites"].items() if "error" in v]
    d = json.load(open(os.path.join(AN, "results", "dup_public_results.json"), encoding="utf-8"))
    assert d["n_chips"] == 1355 and d["found_cross_site"] == 0 and d["positive_control"]["found"] == d["positive_control"]["copies"]
    u = json.load(open(os.path.join(AN, "results", "placement_public_uncertainty.json"), encoding="utf-8"))
    assert u["n_sites"] == 25 and "1.0" in u["facility_kept"]


def test_the_private_aggregates_hold_no_site_names_or_ids():
    text = open(os.path.join(AN, "results", "private_roster_aggregates.json"), encoding="utf-8").read()
    data = json.loads(text)
    assert data["forecast"]["n_sites"] == 120 and data["coordinates"]["uncertainty"]["matched"] == 51

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    assert not {"id", "site_id", "name", "site_name"} & set(keys(data))
    assert "_refinery" not in text and "_plant" not in text and "_lng" not in text
