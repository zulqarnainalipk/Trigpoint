"""The written documents say what the code does: numbers, routes, versions."""
import json
import os
import re

import splitsafety as SS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as f:
        return f.read()


def test_the_readme_help_count_matches_the_help_file():
    n = len(json.loads(read("help_content.json"))["features"])
    assert f"? buttons on {n} controls" in read("README.md")
    assert f"? on {n} controls" in read("FEATURES.md")
    assert f"{n} in all" in read("CHANGELOG.md")


def test_every_studies_route_is_in_the_api_document():
    server = read("server.py")
    routes = set(re.findall(r'"(/api/studies/[a-z/]+)"', server))
    routes |= {"/api/studies/registry/<name>"} if "/api/studies/registry/" in server else set()
    doc = read("docs", "API.md")
    missing = sorted(r for r in routes if r.rstrip("/") not in doc and r.replace("/demo/", "/demo/") not in doc)
    assert not missing, missing


def test_the_changelog_top_entry_is_the_server_version():
    version = re.search(r'VERSION = "([^"]+)"', read("server.py")).group(1)
    assert re.search(r"^## (\d+\.\d+\.\d+)", read("CHANGELOG.md"), re.M).group(1) == version


def test_the_duplicate_rule_and_split_radius_in_the_methods_are_the_code_values():
    m = read("docs", "METHODS.md")
    assert str(SS.DUP_RULE["ncc_min"]) in m and str(SS.DUP_RULE["ssim_min"]) in m
    assert "150 km" in m and f"{SS.DEFAULTS['bg_inner_km']:g} to {SS.DEFAULTS['bg_outer_km']:g} km" in m
    assert f"{SS.DEFAULTS['label_km']:g} km label" in m


def test_the_methods_name_the_forecast_settings_the_code_uses():
    import forecast as F
    m = read("docs", "METHODS.md")
    assert f"under {F.CLUSTER_KM:g} km" in m and "n / (n + 3)" in m and "at least 10" not in m or "refuses fewer than 10" in m
    assert len(F.ALPHAS) == 6 and "six values" in m


def test_no_document_uses_a_long_dash():
    for name in ("README.md", "CHANGELOG.md", "FEATURES.md", "docs/METHODS.md", "docs/API.md", "docs/BACKENDS.md", "docs/TROUBLESHOOTING.md",
                 "docs/USABILITY.md", "examples/README.md"):
        text = read(*name.split("/"))
        assert "\u2014" not in text and "\u2013" not in text, name


def test_the_demo_files_exist_and_are_labelled_synthetic():
    assert os.path.exists(os.path.join(HERE, "demo", "outcomes_demo.csv")) and os.path.exists(os.path.join(HERE, "demo", "registry_demo.csv"))
    assert "synthetic" in read("demo", "registry_demo.csv")
    for f in os.listdir(os.path.join(HERE, "examples")):
        if f.endswith(".json"):
            assert json.loads(read("examples", f)).get("synthetic") is True, f
