"""Integration tests: the real Handler over HTTP, on temporary files."""
import json
import os

from conftest import SITES_FILE, REF_FILE, make_sites


def disk():
    with open(SITES_FILE, encoding="utf-8") as f:
        return json.load(f)


def site(doc, sid):
    return next(s for s in doc["sites"] if s["id"] == sid)


def test_status_and_existing_routes_still_work(http):
    code, j, _ = http("GET", "/api/status")
    assert code == 200 and j["version"] == "1.5.0"
    assert "review" in j["features"] and j["split_radius_km"] == 150.0
    assert j["min_box_km"] == 1.0 and j["max_box_km"] == 8.0
    code, j, _ = http("GET", "/api/sites")
    assert code == 200 and len(j["sites"]) == 6 and j["extra_top_level"] == {"keep": True}
    code, j, _ = http("GET", "/api/warnings")
    assert code == 200 and j["stats"]["total"] == 6 and j["stats"]["rejected"] == 0
    assert http("GET", "/api/nope")[0] == 404


def test_static_files_served(http):
    for path, ctype in (("/", "text/html"), ("/app.js", "javascript"),
                        ("/review.js", "javascript"), ("/style.css", "text/css")):
        code, body, headers = http("GET", path, raw=True)
        assert code == 200 and ctype in headers["Content-Type"] and len(body) > 100, path


def test_keep_reject_unreject_and_extra_fields_preserved(http):
    code, j, _ = http("POST", "/api/sites/c_far", {"verified": True})
    assert code == 200 and j["site"]["verified"] is True
    code, j, _ = http("POST", "/api/sites/c_far", {"rejected": True})
    assert j["site"]["rejected"] is True and j["site"]["verified"] is False
    code, j, _ = http("POST", "/api/sites/c_far", {"verified": True})       # keeping clears a reject
    assert "rejected" not in j["site"] and j["site"]["verified"] is True
    code, j, _ = http("POST", "/api/sites/c_far", {"verified": True, "rejected": True})
    assert code == 400
    d = disk()
    assert d["_README"] == ["test file"] and d["extra_top_level"] == {"keep": True}
    s = site(d, "c_far")
    assert s["region"] == "test_region" and s["facility_type"] == "refinery"
    assert s["coord_confidence"] == "high" and "priority" in s


def test_original_center_recorded_once_and_comment(http):
    http("POST", "/api/sites/b_site", {"center": [10.6, 10.1]})
    s = site(disk(), "b_site")
    assert s["original_center"] == [10.5, 10.0] and s["center"] == [10.6, 10.1]
    http("POST", "/api/sites/b_site", {"center": [10.7, 10.2], "comment": "check the flare"})
    s = site(disk(), "b_site")
    assert s["original_center"] == [10.5, 10.0] and s["comment"] == "check the flare"
    http("POST", "/api/sites/b_site", {"comment": "   "})
    assert "comment" not in site(disk(), "b_site")
    # a save that does not move the centre records nothing
    http("POST", "/api/sites/c_far", {"center": [40.0, 40.0], "notes": "x"})
    assert "original_center" not in site(disk(), "c_far")


def test_undo_redo_cover_verify_reject_and_remove_added_fields(http):
    http("POST", "/api/sites/c_far", {"rejected": True})
    assert site(disk(), "c_far")["rejected"] is True
    code, j, _ = http("POST", "/api/undo")
    assert code == 200
    s = site(disk(), "c_far")
    assert "rejected" not in s and s["verified"] is False
    http("POST", "/api/redo")
    assert site(disk(), "c_far")["rejected"] is True
    # first-move undo removes original_center again
    http("POST", "/api/sites/b_site", {"center": [10.6, 10.1]})
    http("POST", "/api/undo")
    s = site(disk(), "b_site")
    assert s["center"] == [10.5, 10.0] and "original_center" not in s


def test_undo_with_nothing_returns_400(http):
    code, j, _ = http("POST", "/api/undo")
    assert code == 400 and "nothing to undo" in j["error"]


def test_bulk_reject_pending_and_bulk_undo(http):
    code, j, _ = http("POST", "/api/sites/bulk", {"action": "reject", "ids": ["a_site", "b_site"]})
    assert code == 200
    d = disk()
    assert site(d, "a_site")["rejected"] is True and site(d, "b_site")["verified"] is False
    http("POST", "/api/sites/bulk", {"action": "verify", "ids": ["a_site"]})
    assert "rejected" not in site(disk(), "a_site") and site(disk(), "a_site")["verified"] is True
    http("POST", "/api/undo")                                   # undo the bulk verify
    assert site(disk(), "a_site")["rejected"] is True
    http("POST", "/api/undo")                                   # undo the bulk reject
    assert "rejected" not in site(disk(), "b_site")
    code, j, _ = http("POST", "/api/sites/bulk", {"action": "pending", "ids": ["zzz"]})
    assert code == 404


def test_rejected_sites_leave_geometry_warnings(http):
    code, j, _ = http("GET", "/api/warnings")
    assert any(w["severity"] == "critical" and {w["a"], w["b"]} == {"a_site", "f_dup"}
               for w in j["warnings"])
    http("POST", "/api/sites/f_dup", {"rejected": True})
    code, j, _ = http("GET", "/api/warnings")
    assert not any("f_dup" in (w["a"], w["b"]) for w in j["warnings"])
    assert j["stats"]["rejected"] == 1 and j["stats"]["pending"] == 5


def test_reference_is_read_only_and_listed(http):
    code, j, _ = http("GET", "/api/reference")
    assert code == 200 and not j["same_file"] and len(j["sites"]) == 3
    assert {s["id"] for s in j["sites"]} == {"pilot_test", "pilot_train", "pilot_test2"}
    before = open(REF_FILE, "rb").read()
    http("POST", "/api/sites/c_far", {"verified": True})
    assert open(REF_FILE, "rb").read() == before


def test_reference_empty_when_editing_the_pilot_file(srv, http, monkeypatch):
    monkeypatch.setattr(srv, "REFERENCE_PATH", SITES_FILE)
    code, j, _ = http("GET", "/api/reference")
    assert j["same_file"] is True and j["sites"] == []


def test_analysis_endpoint(http):
    code, j, _ = http("GET", "/api/analysis")
    assert code == 200 and j["summary"]["total"] == 6 and j["summary"]["reference_count"] == 3
    a = j["sites"]
    assert a["a_site"]["screening"]["priority"] == "C"
    assert a["d_near_pilot"]["neighbors"][0]["id"] == "pilot_test"
    assert a["d_near_pilot"]["required_role"] == "test"
    assert a["e_between"]["split_conflict"] is True
    assert a["f_dup"]["worst"] == "critical"


def test_neighbors_endpoint(http):
    code, j, _ = http("GET", "/api/neighbors?lat=-20.2&lon=100.0&exclude=d_near_pilot")
    assert code == 200 and j["required_role"] == "test" and not j["conflict"]
    assert j["neighbors"][0]["id"] == "pilot_test"
    code, j, _ = http("GET", "/api/neighbors?lat=0&lon=0")
    assert j["conflict"] is True and j["pilot_roles"] == ["test", "train"]
    assert http("GET", "/api/neighbors?lat=abc&lon=0")[0] == 400


def test_export_default_is_unchanged_full_file(http):
    code, body, headers = http("GET", "/api/sites/export", raw=True)
    assert code == 200 and "attachment" in headers["Content-Disposition"]
    assert json.loads(body) == disk()


def test_export_scopes_csv_and_comments(http):
    http("POST", "/api/sites/a_site", {"verified": True, "comment": "private note"})
    http("POST", "/api/sites/b_site", {"rejected": True})
    code, body, h = http("GET", "/api/sites/export?scope=kept&comments=0", raw=True)
    d = json.loads(body)
    assert len(d["sites"]) == 5 and "kept" in h["Content-Disposition"]
    assert all("comment" not in s and "rejected" not in s for s in d["sites"])
    code, body, _ = http("GET", "/api/sites/export?scope=verified", raw=True)
    d = json.loads(body)
    assert [s["id"] for s in d["sites"]] == ["a_site"] and d["sites"][0]["comment"] == "private note"
    code, body, h = http("GET", "/api/sites/export?scope=rejected", raw=True)
    assert [s["id"] for s in json.loads(body)["sites"]] == ["b_site"]
    code, body, h = http("GET", "/api/sites/export?scope=kept&format=csv", raw=True)
    assert "text/csv" in h["Content-Type"] and body.decode().startswith("id,name,role,lat,lon")
    assert h["Content-Disposition"].endswith('.csv"')
    assert http("GET", "/api/sites/export?scope=bogus")[0] == 400
    assert http("GET", "/api/sites/export?format=xml")[0] == 400


def test_import_preview_then_apply_and_audit(http, srv):
    incoming = [
        {"id": "a_site", "name": "A again", "role": "train", "center": [10.0, 10.0], "box_km": 3},
        {"id": "fresh", "name": "Fresh", "role": "train", "center": [60.0, 20.0], "box_km": 99,
         "notes": "n", "custom": 1},
        {"name": "broken"},
    ]
    code, j, _ = http("POST", "/api/sites/import", {"sites": incoming, "policy": "skip"})
    assert code == 200 and j["applied"] is False
    assert j["counts"]["new"] == 1 and j["counts"]["skipped"] == 1 and j["counts"]["invalid"] == 1
    assert len(disk()["sites"]) == 6                       # preview wrote nothing
    code, j, _ = http("POST", "/api/sites/import",
                      {"doc": {"sites": incoming}, "policy": "rename", "apply": True})
    assert code == 200 and j["applied"] is True
    d = disk()
    assert len(d["sites"]) == 8
    assert site(d, "fresh")["box_km"] == 8.0 and site(d, "fresh")["custom"] == 1
    assert site(d, "a_site_2")["name"] == "A again"
    assert d["extra_top_level"] == {"keep": True}
    assert len(os.listdir(os.environ["SITE_CURATOR_BACKUP_DIR"])) >= 1
    audit = [json.loads(l) for l in open(os.environ["SITE_CURATOR_AUDIT_PATH"], encoding="utf-8")]
    assert any(r["action"] == "import" for r in audit)


def test_import_errors(http):
    assert http("POST", "/api/sites/import", {"sites": "nope"})[0] == 400
    assert http("POST", "/api/sites/import", {"sites": [], "policy": "wipe"})[0] == 400
    code, j, _ = http("POST", "/api/sites/import",
                      {"sites": [{"id": "a_site", "name": "x", "center": [1, 1]}],
                       "policy": "skip", "apply": True})
    assert code == 400 and "nothing to import" in j["error"]


def test_every_write_still_passes_the_validator(http):
    code, j, _ = http("POST", "/api/sites/c_far", {"box_km": 50})   # clamped, not rejected
    assert j["site"]["box_km"] == 8.0
    code, j, _ = http("POST", "/api/sites/c_far", {"role": "banana"})
    assert code == 400
    assert site(disk(), "c_far")["role"] == "train"


def test_delete_still_works_and_undo_restores(http):
    code, j, _ = http("DELETE", "/api/sites/f_dup")
    assert code == 200 and len(disk()["sites"]) == 5
    http("POST", "/api/undo")
    assert len(disk()["sites"]) == 6
