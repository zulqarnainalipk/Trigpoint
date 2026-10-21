import json

import pytest

import grounding as G


def reg(entries, source="r"):
    return {"source": source, "skipped": 0, "format": "csv", "entries": [G._entry(*e[:3], source, *e[3:]) for e in entries]}


def site(i, name, lat, lon, country="", **kw):
    return {"id": i, "name": name, "center": [lat, lon], "country": country, **kw}


KM = 1 / 111.32


def test_name_score_ignores_generic_words_and_accents():
    assert G.name_score("Ras Tanura refinery", "Ras Tanura Refinery (Saudi Aramco)") >= 0.7
    assert G.name_score("Hawiyah gas plant, Saudi Arabia", "Hawiyah") >= 0.5
    assert G.name_score("Sines refinery", "Raffinerie de Sines") > 0.4
    assert G.name_score("Tengiz processing plant", "Tengiz") >= 0.5
    assert G.name_score("Jubail industrial city", "Yanbu refinery") == 0.0
    assert G.name_score("", "x") == 0.0
    assert G.name_score("Cartagena reficar", "Cartagéna Reficar") == pytest.approx(1.0)


def test_parse_csv_with_common_headers_and_skipped_rows():
    text = "Plant name,Latitude,Longitude,Country/Area\nAlpha,10.5,20.5,SA\nBeta,x,5,SA\n,1,1,SA\nGamma,95,0,SA\n"
    r = G.parse_registry(text, "gem")
    assert [e["name"] for e in r["entries"]] == ["Alpha"] and r["skipped"] == 3
    assert r["entries"][0]["country"] == "SA" and r["source"] == "gem"


def test_parse_geojson_and_wikidata():
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [50.1, 26.6]}, "properties": {"name": "Ras Tanura", "country": "SA"}},
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {"name": "poly"}}]}
    r = G.parse_registry(json.dumps(gj), "x")
    assert r["format"] == "geojson" and len(r["entries"]) == 1 and r["skipped"] == 1 and r["entries"][0]["lat"] == 26.6
    wd = {"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "Foo refinery"}, "coord": {"value": "Point(10.5 45.25)"}, "countryCode": {"value": "IT"}},
        {"itemLabel": {"value": "No coord"}}]}}
    w = G.parse_registry(json.dumps(wd), "wikidata")
    assert w["format"] == "wikidata" and w["entries"][0]["id"] == "Q1" and w["entries"][0]["lat"] == 45.25 and w["entries"][0]["lon"] == 10.5 and w["skipped"] == 1
    with pytest.raises(ValueError):
        G.parse_registry("x", fmt="bogus")


def test_match_uses_name_country_and_distance():
    entries = [G._entry("Alpha refinery", 10.0, 20.0, "r", "SA"), G._entry("Alpha refinery", 10.0, 20.0, "r", "FR"), G._entry("Beta", 10.01, 20.0, "r", "SA")]
    s = site("a", "Alpha refinery", 10.0, 20.01, "SA")
    best, near = G.match_site(s, entries)
    assert best["entry"]["country"] == "SA" and best["name_score"] > 0.9 and best["distance_km"] < 2
    assert near["distance_km"] < 2
    assert G.match_site(site("z", "Nothing like it", 10, 20, "SA"), entries)[0] is None
    far = G.match_site(site("a", "Alpha refinery", 30, 40, "SA"), entries)[0]
    assert far is None                                                  # outside the search distance


def test_status_thresholds():
    assert [G.status_for(d) for d in (None, 0.5, 2.0, 3.0, 5.0, 5.1)] == ["not_found", "agree", "agree", "differ", "differ", "disagree"]


def test_ground_site_flags_disagreement_and_suggests_a_centre():
    r1 = reg([("Alpha refinery", 10.0, 20.0, "SA")], "wikidata")
    r2 = reg([("Alpha refinery", 10.0, 20.0 + 8 * KM, "SA")], "gem")
    s = site("a", "Alpha refinery", 10.0, 20.0 + 20 * KM, "SA")
    g = G.ground_site(s, [r1, r2])
    assert g["status"] == "disagree" and g["suggested_centre"] is not None
    assert g["registry_spread_km"] == pytest.approx(8, abs=1)
    ok = G.ground_site(site("b", "Alpha refinery", 10.0, 20.0 + 0.5 * KM, "SA"), [r1])
    assert ok["status"] == "agree" and ok["registry_spread_km"] is None
    assert G.ground_site(site("c", "Unknown", 0, 0), [r1])["status"] == "not_found"


def test_ground_roster_compares_the_original_position_when_asked():
    r1 = reg([("Alpha refinery", 10.0, 20.0, "SA")])
    s = site("a", "Alpha refinery", 10.0, 20.0, "SA", original_center=[10.0, 20.0 + 30 * KM])
    assert G.ground_roster([s], [r1], use_original=True)["sites"][0]["status"] == "disagree"
    assert G.ground_roster([s], [r1], use_original=False)["sites"][0]["status"] == "agree"
    assert G.ground_roster([dict(s, rejected=True)], [r1])["n_sites"] == 0


def test_evaluate_reports_errors_and_whether_disagreement_predicts_them():
    entries, sites = [], []
    for i in range(20):
        truth = (10.0 + i, 20.0)
        err_km = 1.0 if i % 2 == 0 else 9.0                             # odd sites were recalled far from the truth
        entries.append(("Place %d" % (i * 7 + 100), truth[0], truth[1] + 0.3 * KM, "SA"))
        sites.append(site(f"s{i}", "Place %d" % (i * 7 + 100), truth[0], truth[1], "SA", verified=True,
                          original_center=[truth[0], truth[1] + err_km * KM]))
    r = G.evaluate(sites, [reg(entries)])
    assert r["n_verified_sites"] == 20 and r["n_with_registry_match"] == 20
    assert r["registry_on_matched_sites"]["median_km"] < 1 < r["recalled"]["median_km"]
    assert r["combined_policy"]["median_km"] < r["recalled"]["median_km"]
    assert r["disagreement_predicts_big_error_auc"] == pytest.approx(1.0)


def test_evaluate_skips_unverified_and_handles_no_matches():
    s = site("a", "X", 1, 1, "SA", verified=False, original_center=[1, 1.1])
    assert G.evaluate([s], [reg([("Y", 5, 5, "SA")])])["n_verified_sites"] == 0
    s2 = dict(s, verified=True)
    r = G.evaluate([s2], [reg([("Y", 5, 5, "SA")])])
    assert r["n_with_registry_match"] == 0 and r["registry_on_matched_sites"] == {"n": 0}


def test_auc_basic():
    assert G.auc([1, 2, 3, 4], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert G.auc([4, 3, 2, 1], [0, 0, 1, 1]) == pytest.approx(0.0)
    assert G.auc([1, 1, 1, 1], [0, 1, 0, 1]) == pytest.approx(0.5)
    assert G.auc([1, 2], [1, 1]) is None


def test_wikidata_query_checks_its_inputs_and_fetch_uses_the_http_object():
    with pytest.raises(ValueError):
        G.wikidata_query(["not an id"])
    q = G.wikidata_query(["Q123", "Q456"], "sa")
    assert "wd:Q123 wd:Q456" in q and '"sa"' in q and "wdt:P625" in q
    assert 'wdt:P297 "' not in G.wikidata_query(["Q1"]).split("OPTIONAL")[0]

    class R:
        text = '{"results": {"bindings": []}}'
        def raise_for_status(self): pass

    class H:
        def get(self, url, params, headers, timeout):
            self.seen = (url, params["format"], headers["User-Agent"])
            return R()
    h = H()
    assert G.fetch_wikidata("SELECT 1", http=h).startswith("{")
    assert h.seen[0] == G.WIKIDATA_ENDPOINT and "SiteCurator" in h.seen[2]


def test_query_text_rejects_injection_in_country_code():
    assert 'P297 "' not in G.wikidata_query(["Q1"], 'SA" } DROP').split("SERVICE")[0].split("OPTIONAL { ?item wdt:P17 ?c2")[1]
