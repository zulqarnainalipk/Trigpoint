import json

import pytest

from test_studies import outcome_csv, sites_doc


def load_roster(srv, doc):
    with open(srv.SITES_PATH, "w", encoding="utf-8") as f:
        json.dump({"sites": [dict(s, verified=True) for s in doc["sites"]]}, f)


def test_status_lists_the_new_features(http):
    code, j, _ = http("GET", "/api/status")
    assert code == 200
    for f in ("overlap_groups", "certificate", "duplicates", "domain_shift", "forecast", "grounding", "placement"):
        assert f in j["features"]
    code, s, _ = http("GET", "/api/studies/status")
    assert code == 200 and s["outcomes"]["n_rows"] == 0 and s["registries"] == [] and s["forecast_model"] is False


def test_write_routes_need_the_header(srv):
    import threading, urllib.request, urllib.error
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/studies/groups", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_groups_get_and_apply_with_undo(http, srv):
    code, g, _ = http("GET", "/api/studies/groups?level=ring")
    assert code == 200 and g["n_sites"] == 6 and g["level"] == "ring"
    code, g2, _ = http("GET", "/api/studies/groups?level=bogus")
    assert code == 400 and "level" in g2["error"]
    code, res, _ = http("POST", "/api/studies/groups", {"level": "ring", "apply": True})
    assert code == 200 and res["applied"] is True
    sites = http("GET", "/api/sites")[1]["sites"]
    assert all("overlap_group" in s for s in sites)
    near = {s["id"]: s["overlap_group"] for s in sites}
    assert near["a_site"] == near["b_site"] == near["f_dup"] and near["c_far"] != near["a_site"]
    code, u, _ = http("POST", "/api/undo", {})
    assert code == 200
    assert all("overlap_group" not in s for s in http("GET", "/api/sites")[1]["sites"])


def test_outcomes_upload_forecast_and_predictions(http, srv):
    doc = sites_doc(50)
    load_roster(srv, doc)
    code, j, _ = http("POST", "/api/studies/outcomes", {"csv": outcome_csv(doc)})
    assert code == 200 and j["n_rows"] == 50
    code, v, _ = http("POST", "/api/studies/forecast", {"action": "validate", "target": "yield"})
    assert code == 200 and v["skill"] > 0.3
    code, none, _ = http("GET", "/api/studies/forecast/predictions")
    assert code == 400 and "fit" in none["error"]
    code, m, _ = http("POST", "/api/studies/forecast", {"action": "fit", "target": "yield"})
    assert code == 200 and m["n_sites"] == 50
    code, p, _ = http("GET", "/api/studies/forecast/predictions")
    assert code == 200 and len(p["predictions"]) == 50
    code, s, _ = http("GET", "/api/studies/status")
    assert s["forecast_model"] is True and s["forecast_validation"]["target"] == "yield"
    assert http("DELETE", "/api/studies/outcomes")[0] == 200
    assert http("GET", "/api/studies/outcomes")[1]["n_rows"] == 0


def test_forecast_errors_are_plain(http):
    code, j, _ = http("POST", "/api/studies/forecast", {"action": "validate", "target": "yield"})
    assert code == 400 and "at least 10" in j["error"]
    code, j, _ = http("POST", "/api/studies/outcomes", {"csv": "a,b\n1,2\n"})
    assert code == 400 and "id" in j["error"]


def test_shift_and_certificate_routes(http, srv):
    doc = sites_doc(30)
    load_roster(srv, doc)
    code, sh, _ = http("POST", "/api/studies/shift", {"role_a": "train", "role_b": "test", "permutations": 20})
    assert code == 200 and sh["features"]
    code, c, _ = http("POST", "/api/studies/certificate", {"time_info": {"train_end": "2022-12-31", "test_start": "2023-01-01"}})
    assert code == 200 and c["schema"].startswith("site-curator-certificate") and c["verdict"] in ("pass", "conditional", "fail")
    code, raw, hdr = http("POST", "/api/studies/certificate", {"download": True}, raw=True)
    assert code == 200 and "split_certificate.json" in hdr["Content-Disposition"] and json.loads(raw)["roster_sha256"]


def test_certificate_needs_two_roles_and_then_flags_close_sites(http):
    code, c, _ = http("POST", "/api/studies/certificate", {})
    assert code == 200
    assert {x["id"]: x["status"] for x in c["checks"]}["min_distance"] == "not_run"       # every test site is a train site
    http("POST", "/api/sites/b_site", {"role": "test"})                                   # 55 km from a_site, a train site
    code, c, _ = http("POST", "/api/studies/certificate", {})
    st = {x["id"]: x["status"] for x in c["checks"]}
    assert st["min_distance"] == "fail" and st["overlap_ring"] == "fail" and c["verdict"] == "fail"


def test_duplicates_route_and_benchmark(http):
    code, r, _ = http("POST", "/api/studies/duplicates", {"backend": "demo", "fetch": True, "limit": 6})
    assert code == 200 and r["n_images"] == 6 and r["synthetic"] is True
    code, b, _ = http("GET", "/api/studies/duplicates/benchmark?n_base=12&seed=3")
    assert code == 200 and b["overall_detection_rate"] >= 0.8 and b["false_alarms"] == 0
    assert http("GET", "/api/studies/duplicates/benchmark?n_base=2")[0] == 400


def test_registry_and_grounding_routes_including_the_online_guard(http):
    http("POST", "/api/sites/a_site", {"name": "Alpha plant"})
    http("POST", "/api/sites/b_site", {"name": "Bravo plant"})
    csv_text = "name,lat,lon,country\nAlpha,10.0,10.0,\nBravo,10.5,10.0,\n"
    code, j, _ = http("POST", "/api/studies/registry", {"name": "test", "text": csv_text})
    assert code == 200 and j["n_entries"] == 2
    assert http("GET", "/api/studies/registries")[1]["registries"][0]["name"] == "test"
    code, g, _ = http("POST", "/api/studies/grounding", {"use_original": False})
    assert code == 200 and g["counts"]["agree"] >= 2
    code, ev, _ = http("POST", "/api/studies/grounding/evaluate", {})
    assert code == 200 and "recalled" in ev
    code, w, _ = http("POST", "/api/studies/registry/wikidata", {"class_ids": ["Q1"]})
    assert code == 400 and "wikidata.org" in w["error"]                 # never goes online without a yes
    assert http("DELETE", "/api/studies/registry/test")[1]["ok"] is True
    code, e, _ = http("POST", "/api/studies/grounding", {})
    assert code == 400


def test_sensitivity_route(http):
    code, r, _ = http("POST", "/api/studies/sensitivity", {"site_id": "a_site", "backend": "demo", "distances": [1, 2], "bearings": [0, 180],
                                                          "targets": ["no2"]})
    assert code == 200 and r["synthetic"] and "no2" in r["targets"] and r["by_distance"]
    assert http("POST", "/api/studies/sensitivity", {"site_id": "nope", "backend": "demo"})[0] == 404
    assert http("POST", "/api/studies/sensitivity", {"site_id": "a_site", "backend": "demo", "distances": [-1]})[0] == 400
    code, j, _ = http("POST", "/api/studies/sensitivity", {"site_id": "a_site", "backend": "pc", "targets": ["no2"], "distances": [1]})
    assert code in (400, 502)


def test_new_routes_are_not_open_to_other_hosts(srv):
    import threading, urllib.request, urllib.error
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{httpd.server_address[1]}/api/studies/status", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_provenance_records_what_the_studies_found(http, srv):
    http("POST", "/api/sites/b_site", {"role": "test"})
    http("POST", "/api/studies/certificate", {})
    http("POST", "/api/studies/duplicates", {"backend": "demo", "fetch": True, "limit": 4})
    code, rec, _ = http("GET", "/api/provenance")
    assert code == 200
    s = rec["studies"]
    assert s["split_certificate"]["verdict"] == "fail" and len(s["split_certificate"]["roster_sha256"]) == 64
    assert s["near_duplicates"]["n_images"] >= 4 and s["near_duplicates"]["synthetic"] is True


def test_forecast_compare_route(http, srv):
    doc = sites_doc(30)
    load_roster(srv, doc)
    http("POST", "/api/studies/outcomes", {"csv": outcome_csv(doc)})
    code, j, _ = http("POST", "/api/studies/forecast", {"action": "compare", "target": "yield"})
    assert code == 200 and j["models"][0]["model"].startswith("Guess") and j["best_single"]
    code, j, _ = http("POST", "/api/studies/forecast", {"action": "compare", "target": "nothing"})
    assert code == 400


@pytest.mark.parametrize('path,body', [
    ('/api/studies/shift', {'features': 'land_frac'}),
    ('/api/studies/shift', {'role_a': 5}),
    ('/api/studies/shift', {'permutations': 'many'}),
    ('/api/studies/shift', {'permutations': 10 ** 9}),
    ('/api/studies/duplicates', {'limit': -3}),
    ('/api/studies/duplicates', {'backend': ['demo']}),
    ('/api/studies/forecast', {'target': 7}),
    ('/api/studies/forecast', {'features': [1, 2]}),
    ('/api/studies/outcomes', {'csv': 5}),
    ('/api/studies/registry', {'name': 'x', 'text': 5}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'kind': 'nonsense'}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'targets': ['unobtainium']}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'targets': 'no2'}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'distances': 'one'}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'distances': [1, 'x']}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'window_km': 1000}),
    ('/api/studies/sensitivity', {'site_id': 'a_site', 'backend': 'demo', 'distances': [1] * 20}),
    ('/api/studies/sensitivity', {'site_id': 5}),
    ('/api/studies/registry/wikidata', {'confirm': True, 'class_ids': 'Q1'}),
    ('/api/studies/registry/wikidata', {'confirm': True, 'class_ids': []}),
])
def test_bad_inputs_get_a_plain_400_never_a_500(http, path, body):
    code, j, _ = http('POST', path, body)
    assert code == 400 and j['error'], (path, body, code, j)
