"""The imagery, validator, provenance and help routes of the server, plus the local-use guards."""
import http.client
import json
import os

import pytest

PNG = b"\x89PNG\r\n\x1a\n"
Q = "backend=demo&box_km=3"


def png(http, path):
    code, body, hdr = http("GET", path, raw=True)
    return code, body, hdr


def test_views_and_backends_report(http):
    code, j, _ = http("GET", "/api/views")
    assert code == 200 and {"true_color", "swir", "aerosol"} <= set(j["composites"]) and "ndvi" in j["indices"]
    assert j["indices"]["nbr2"]["formula"] == "(B11 - B12) / (B11 + B12)"
    assert set(j["sources"]) == {"single", "median", "clearsky"} and j["fills"] == ["none", "mean", "nearest"]
    code, j, _ = http("GET", "/api/backends")
    names = {b["name"]: b for b in j["backends"]}
    assert names["demo"]["ready"] is True and names["demo"]["synthetic"] is True
    assert names["ee"]["ready"] is False and names["ee"]["reason"]
    assert names["pc"]["ready"] is None                         # not probed unless asked
    assert j["default"] == "demo"


def test_status_lists_the_new_controls(http):
    _, j, _ = http("GET", "/api/status")
    assert "aerosol" in j["band_views"] and "ndvi" in j["band_views"]
    assert j["default_backend"] == "demo" and {"single", "median", "clearsky"} <= set(j["sources"])
    assert {"imagery", "validator", "provenance", "datasheet", "help"} <= set(j["features"])


def test_preview_returns_a_png_and_says_it_is_synthetic(http):
    code, body, hdr = png(http, f"/api/preview/a_site?{Q}")
    assert code == 200 and body[:8] == PNG
    meta = json.loads(hdr["X-Preview-Meta"])
    assert meta["synthetic"] is True and meta["backend"] == "demo" and meta["view"] == "true_color"
    assert 0 < meta["valid_share"] <= 1


def test_every_source_view_stretch_and_fill_renders(http):
    for extra in ("source=median&days=60", "source=clearsky&days=60&q=10", "view=ndvi", "view=swir&stretch=log",
                  "view=aerosol&stretch=sqrt", "view=bsi&stretch=linear", "fill=mean", "fill=nearest"):
        code, body, hdr = png(http, f"/api/preview/a_site?{Q}&{extra}")
        assert code == 200 and body[:8] == PNG, extra
    meta = json.loads(hdr["X-Preview-Meta"])
    assert meta["fill"]["method"] == "nearest"


def test_second_request_uses_the_cache_and_force_refreshes(http, srv):
    png(http, f"/api/preview/a_site?{Q}")
    before = {f: os.path.getmtime(os.path.join(srv.CACHE_DIR, f)) for f in os.listdir(srv.CACHE_DIR) if f.endswith(".tif") and "donor" not in f}
    png(http, f"/api/preview/a_site?{Q}&view=swir")
    after = {f: os.path.getmtime(os.path.join(srv.CACHE_DIR, f)) for f in before}
    assert before == after                                     # a new view did not re-download
    png(http, f"/api/preview/a_site?{Q}&force=1")
    assert any(os.path.getmtime(os.path.join(srv.CACHE_DIR, f)) > before[f] for f in before)


def test_check_only_never_fetches(http, srv):
    q = "backend=demo&box_km=3.5&lat=11&lon=11"
    code, j, _ = http("GET", f"/api/preview/a_site?{q}&check_only=1")
    assert j == {"cached": False, "view_rendered": False}
    assert not [f for f in os.listdir(srv.CACHE_DIR) if f.startswith("a_site_11.00000")]
    png(http, f"/api/preview/a_site?{q}")
    code, j, _ = http("GET", f"/api/preview/a_site?{q}&check_only=1")
    assert j["cached"] is True and j["view_rendered"] is True


@pytest.mark.parametrize("query,msg", [
    ("source=bogus", "unknown source"), ("view=bogus", "unknown view"), ("stretch=bogus", "unknown stretch"),
    ("fill=bogus", "unknown fill"), ("backend=bogus", "unknown backend"), ("days=2", "days must be"),
    ("days=abc", "whole numbers"), ("source=clearsky&q=99", "percentile"), ("box_km=0.2", "box_km must be"),
    ("box_km=50", "box_km must be"), ("lat=95", "out of range"), ("lon=-200", "out of range"),
])
def test_bad_parameters_get_plain_400s(http, query, msg):
    base = {"backend": "demo", "box_km": "3"}
    parts = dict(p.split("=") for p in query.split("&"))
    base.update(parts)
    q = "&".join(f"{k}={v}" for k, v in base.items())
    code, j, _ = http("GET", f"/api/preview/a_site?{q}")
    assert code == 400 and msg in j["error"]


def test_unknown_site_is_404_and_traversal_is_harmless(http, srv):
    assert http("GET", f"/api/preview/nope?{Q}")[0] == 404
    assert http("GET", f"/api/preview/..%2F..%2Fetc%2Fpasswd?{Q}")[0] == 404
    assert http("GET", f"/api/imagery/nope/stats?{Q}")[0] == 404
    assert not any(".." in f or "/" in f for f in os.listdir(srv.CACHE_DIR))


def test_earth_engine_when_not_ready_is_a_clear_502(http):
    code, j, _ = http("GET", "/api/preview/a_site?backend=ee&box_km=3")
    assert code == 502 and "Earth Engine" in j["error"]


def test_statistics_endpoint(http):
    code, j, _ = http("GET", f"/api/imagery/a_site/stats?{Q}&indices=ndvi,bsi")
    assert code == 200 and set(j["indices"]) == {"ndvi", "bsi"} and set(j["bands"]) >= {"B1", "B8A", "B12"}
    assert 0 < j["valid_share"] <= 1 and j["reading"] and all(isinstance(x, str) for x in j["reading"])
    assert j["meta"]["synthetic"] is True
    clear = http("GET", f"/api/imagery/a_site/stats?{Q}&clear=1")[1]
    assert clear["pixels_used"] <= j["pixels_used"]
    assert http("GET", f"/api/imagery/a_site/stats?{Q}&indices=nope")[0] == 400


def test_candidates_endpoint(http):
    code, j, _ = http("GET", f"/api/imagery/a_site/candidates?{Q}&kind=built_up&percentile=80&min_px=20")
    assert code == 200 and j["regions"] and j["geojson"]["type"] == "FeatureCollection"
    r = j["regions"][0]
    assert r["rank"] == 1 and r["pixels"] >= 20 and "centroid_lonlat" in r
    assert j["description"] and j["meta"]["synthetic"] is True
    assert http("GET", f"/api/imagery/a_site/candidates?{Q}&kind=nope")[0] == 400
    assert http("GET", f"/api/imagery/a_site/candidates?{Q}&percentile=10")[0] == 400
    code, hot, _ = http("GET", f"/api/imagery/a_site/candidates?{Q}&kind=hot&threshold=1.6&min_px=2")
    assert code == 200 and isinstance(hot["regions"], list)


def test_gap_fill_test_endpoint(http):
    code, j, _ = http("GET", f"/api/imagery/a_site/gapfill_test?{Q}")
    assert code == 200 and j["donor_available"] and j["nearest"] <= j["mean"] + 1e-6 and j["hidden_pixels"] > 0


def test_validator_routes(http, srv):
    code, j, _ = http("GET", "/api/validate")
    assert code == 200 and j["ok"] is True and j["errors"] == []
    bad = {"sites": [{"id": "x", "name": "X", "role": "bogus", "center": [0, 0], "box_km": 3}]}
    code, j, _ = http("POST", "/api/validate", {"doc": bad})
    assert code == 200 and j["ok"] is False and "role" in j["errors"][0]


def test_provenance_and_datasheet_routes(http):
    http("GET", f"/api/preview/a_site?{Q}", raw=True)
    code, j, hdr = http("GET", "/api/provenance")
    assert code == 200 and j["schema"].startswith("site-curator-provenance") and j["roster"]["summary"]["sites_in_file"] == 6
    assert j["imagery_used"]["synthetic_images"] >= 1 and "comment" not in json.dumps(j["sites"])
    code, body, hdr = http("GET", "/api/provenance?download=1", raw=True)
    assert "attachment" in hdr["Content-Disposition"]
    code, body, hdr = http("GET", "/api/datasheet?download=1", raw=True)
    assert code == 200 and b"## Composition" in body and "datasheet.md" in hdr["Content-Disposition"]
    code, j, _ = http("POST", "/api/datasheet", {"answers": {"uses_intended": "Testing."}})
    assert code == 200 and j["gaps"]["remaining"] == j["gaps"]["total"] - 1 and j["missing_sections"] == []
    assert "uses_intended" in j["questions"] and "Testing." in j["markdown"]


def test_help_route_serves_every_feature(http):
    code, j, _ = http("GET", "/api/help")
    assert code == 200 and j["features"] and "imagery_panel" in j["features"]


def test_report_escapes_text(http, srv):
    http("POST", "/api/sites", {"name": "<script>alert(1)</script>", "role": "train", "center": [5, 5], "box_km": 3, "notes": "<img src=x onerror=1>"})
    code, body, _ = http("GET", "/api/report", raw=True)
    assert code == 200 and b"<script>alert(1)</script>" not in body and b"&lt;script&gt;" in body
    assert b"<img src=x onerror=1>" not in body


# ------------------------------------------------------------------ local-use guards

def raw_request(srv, method, path, headers=None, body=None):
    from http.server import ThreadingHTTPServer
    import threading
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)
        conn.putrequest(method, path, skip_host=True)
        for k, v in (headers or {}).items():
            conn.putheader(k, v.replace("{port}", str(httpd.server_address[1])))
        conn.endheaders(body)
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_writes_without_the_curator_header_are_refused(srv):
    port_free = {"Host": "127.0.0.1"}
    body = json.dumps({"name": "Z", "role": "train", "center": [1, 2], "box_km": 3}).encode()
    status, _ = raw_request(srv, "POST", "/api/sites", {**port_free, "Content-Type": "application/json", "Content-Length": str(len(body))}, body)
    assert status == 403
    status, _ = raw_request(srv, "DELETE", "/api/sites/a_site", port_free)
    assert status == 403
    ids = [s["id"] for s in srv.store.list()["sites"]]
    assert "a_site" in ids and not any(i.startswith("z") for i in ids)


def test_requests_for_another_host_name_are_refused(srv):
    status, body = raw_request(srv, "GET", "/api/sites", {"Host": "evil.example"})
    assert status == 403 and b"not addressed" in body


def test_oversized_bodies_are_refused(srv):
    status, body = raw_request(srv, "POST", "/api/validate", {"Host": "127.0.0.1:{port}", "X-Site-Curator": "1",
                                                          "Content-Length": str(10 * 1024 * 1024)})
    assert status == 400 and b"too large" in body


def test_broken_json_is_a_400_not_a_crash(srv):
    status, body = raw_request(srv, "POST", "/api/validate", {"Host": "127.0.0.1:{port}", "X-Site-Curator": "1", "Content-Length": "5"}, b"{nope")
    assert status == 400 and b"not valid JSON" in body
