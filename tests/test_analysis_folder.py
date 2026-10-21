"""The analysis folder: scripts parse, results are valid JSON for the public dataset, and nothing personal is in it."""
import ast
import glob
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(HERE, "analysis")


def load(name):
    with open(os.path.join(AN, "results", name), encoding="utf-8") as f:
        return json.load(f)


def test_every_analysis_script_parses_and_has_no_personal_path():
    scripts = glob.glob(os.path.join(AN, "*.py"))
    assert {os.path.basename(s) for s in scripts} == {"run_placement_public.py", "run_dup_public.py", "run_public_extras.py", "uncertainty_public.py", "make_figure1.py"}
    for f in scripts:
        text = open(f, encoding="utf-8").read()
        ast.parse(text)
        assert "ZA Research" not in text and "C:\\Users" not in text and "OBSCURA_PRIVATE_ROOT" not in text, f


def test_placement_and_duplicate_results_cover_the_public_record():
    r = load("placement_public_results.json")
    assert len(r["sites"]) == 25 and not [k for k, v in r["sites"].items() if "error" in v]
    u = load("placement_public_uncertainty.json")
    assert u["n_sites"] == 25 and "1.0" in u["facility_kept"]
    d = load("dup_public_results.json")
    assert d["n_chips"] == 1355 and d["n_sites"] == 25 and d["found_cross_site"] == 0
    pc = d["positive_control"]
    assert pc["found"] == pc["copies"] == 120 and pc["false_alarms"] == 0 and pc["unrelated_pairs"] == 5100 and pc["pairs_passed_screen"] > 0


def test_forecast_registry_and_overlap_results_are_from_25_sites():
    x = load("public_extras_results.json")
    assert x["n_sites"] == 25 and x["forecast"]["sites"] == 25 and x["forecast"]["clusters"] == 23
    assert x["registry"]["of"] == 25 and 0 < x["registry"]["matched"] < 25
    assert x["overlap"]["pairs_by_level"]["ring"] == 2 and x["overlap"]["groups_by_level"]["ring"] == 23


def test_the_figure_and_the_number_map_are_there():
    assert os.path.exists(os.path.join(AN, "results", "figure1.png")) and os.path.exists(os.path.join(AN, "results", "RESULTS.md"))


def test_no_result_file_mentions_a_private_collection():
    for f in glob.glob(os.path.join(AN, "results", "*.json")):
        text = open(f, encoding="utf-8").read().lower()
        assert "private" not in text and "competition" not in text, f
