import copy

import pytest

import curator_logic as CL
from conftest import make_sites, make_ref, NOTE_SCREENED

CFG = {"min_box_km": 1.0, "max_box_km": 8.0, "label_box_km": 10.0}


def test_parse_screening_full():
    sc = CL.parse_screening(NOTE_SCREENED)
    assert sc["land_pct"] == 25.0
    assert (sc["s2_clear"], sc["s2_all"]) == (12, 80)
    assert sc["clear_pct"] == 15.0
    assert sc["no2_contrast"] == 5.2
    assert sc["co_contrast"] is None          # "n/a"
    assert sc["fire_days"] == 3
    assert sc["priority"] == "C"
    assert sc["flags"] == ["window is mostly water (gas values would be blank)",
                           "few clear Sentinel-2 scenes (cloudy)"]


def test_parse_screening_priority_without_flags_and_missing():
    sc = CL.parse_screening("Setting: inland. Priority A. Within 150 km of x.")
    assert sc["priority"] == "A" and sc["flags"] == []
    assert CL.parse_screening("Setting: inland. Coordinates: high confidence.") is None
    assert CL.parse_screening("") is None
    assert CL.parse_screening(None) is None


def test_review_state_and_centre_moved():
    assert CL.review_state({}) == "pending"
    assert CL.review_state({"verified": True}) == "verified"
    assert CL.review_state({"verified": True, "rejected": True}) == "rejected"
    s = {"center": [1.0, 2.0]}
    assert not CL.centre_moved(s)
    s["original_center"] = [1.0, 2.0]
    assert not CL.centre_moved(s)
    s["center"] = [1.001, 2.0]
    assert CL.centre_moved(s)


def test_find_neighbors_pilot_and_candidate_and_rejected():
    doc, ref = make_sites(), make_ref()["sites"]
    nb = CL.find_neighbors([10.0, 10.0], doc["sites"], ref, "a_site")
    ids = [n["id"] for n in nb]
    assert ids[:2] == ["f_dup", "b_site"] and all(n["source"] == "candidate" for n in nb)
    nb = CL.find_neighbors([-20.0, 100.0], doc["sites"], ref, "d_near_pilot")
    assert nb[0]["id"] == "pilot_test" and nb[0]["source"] == "pilot"
    assert "test split" in nb[0]["consequence"]
    # rejected candidates no longer count
    doc["sites"][1]["rejected"] = True
    nb = CL.find_neighbors([10.0, 10.0], doc["sites"], ref, "a_site")
    assert "b_site" not in [n["id"] for n in nb]


def test_split_groups_conflict_and_required_role():
    doc, ref = make_sites(), make_ref()["sites"]
    g = CL.split_groups(doc["sites"], ref)
    assert g["d_near_pilot"]["required_role"] == "test" and not g["d_near_pilot"]["conflict"]
    assert g["e_between"]["conflict"] and g["e_between"]["required_role"] is None
    assert g["c_far"]["pilot_roles"] == []
    assert g["a_site"]["group_size"] == 3        # a, b and f_dup


def test_split_groups_chain_through_candidates():
    # candidate B is within 150 km of pilot (test); candidate C is within 150 km of B
    # only, so C also has to take the test split.
    ref = [{"id": "p", "role": "test", "center": [0.0, 0.0]}]
    sites = [{"id": "b", "center": [0.0, 1.0]}, {"id": "c", "center": [0.0, 2.2]}]
    g = CL.split_groups(sites, ref)
    assert g["c"]["required_role"] == "test"


def test_quality_flags_cover_each_rule():
    doc, ref = make_sites(), make_ref()["sites"]
    ref_groups = CL.split_groups(doc["sites"], ref)
    by = {s["id"]: s for s in doc["sites"]}

    def codes(sid, **over):
        s = dict(by[sid], **over)
        return {f["code"] for f in CL.quality_flags(s, doc["sites"], ref, ref_groups, CFG)}

    c = codes("a_site")
    assert {"duplicate_position", "mostly_water", "screening_flag", "not_verified"} <= c
    assert "duplicate_position" in codes("f_dup")
    assert "label_overlap" not in codes("b_site")                # 55 km from a_site
    assert "box_range" in codes("c_far", box_km=9.5)
    assert "box_range" not in codes("c_far")
    assert "split_conflict" in codes("e_between")
    assert "split_role_mismatch" in codes("d_near_pilot")        # role train, pilots are test
    assert "split_role_mismatch" not in codes("d_near_pilot", role="test")
    assert "low_confidence" in codes("c_far", coord_confidence="low")
    # verified but never moved, medium confidence
    assert "centre_unchanged" in codes("b_site", verified=True)
    assert "centre_unchanged" not in codes("c_far", verified=True)          # high confidence
    assert "centre_unchanged" not in codes(
        "b_site", verified=True, original_center=[10.4, 10.0])               # moved
    # rejected sites only report box problems
    assert codes("a_site", rejected=True) == set()


def test_label_overlap_between_close_sites():
    sites = [{"id": "x", "center": [0.0, 0.0], "box_km": 3, "verified": True},
             {"id": "y", "center": [0.0, 0.05], "box_km": 3}]       # 5.5 km
    f = CL.quality_flags(sites[0], sites, [], {}, CFG)
    assert any(x["code"] == "label_overlap" for x in f)


def test_build_analysis_summary_and_nearest_pilot():
    doc, ref = make_sites(), make_ref()["sites"]
    doc["sites"][2]["verified"] = True
    doc["sites"][3]["rejected"] = True
    a = CL.build_analysis(doc, ref, CFG)
    assert a["summary"]["total"] == 6
    assert a["summary"]["verified"] == 1 and a["summary"]["rejected"] == 1
    assert a["summary"]["pending"] == 4
    assert a["sites"]["d_near_pilot"]["nearest_pilot_km"] == 55.6
    assert a["sites"]["e_between"]["split_conflict"] is True
    assert a["sites"]["e_between"]["worst"] == "critical"
    assert a["sites"]["a_site"]["screening"]["priority"] == "C"
    assert a["radius_km"] == 150.0


def test_export_scopes_and_comment_stripping():
    doc = make_sites()
    doc["sites"][0].update(verified=True, comment="private")
    doc["sites"][1].update(rejected=True)
    full = CL.export_doc(doc, "all", True)
    assert full == doc
    kept = CL.export_doc(doc, "kept", False)
    assert [s["id"] for s in kept["sites"]] == ["a_site", "c_far", "d_near_pilot", "e_between", "f_dup"]
    assert all("comment" not in s and "rejected" not in s for s in kept["sites"])
    assert kept["extra_top_level"] == {"keep": True}
    assert [s["id"] for s in CL.export_doc(doc, "verified")["sites"]] == ["a_site"]
    assert [s["id"] for s in CL.export_doc(doc, "rejected")["sites"]] == ["b_site"]
    assert CL.export_doc(doc, "verified", True)["sites"][0]["comment"] == "private"
    # the source document is not modified
    assert doc["sites"][1]["rejected"] is True and doc["sites"][0]["comment"] == "private"
    with pytest.raises(ValueError):
        CL.export_doc(doc, "nonsense")


def test_export_csv_has_header_rows_and_originals():
    doc = make_sites()
    doc["sites"][0].update(original_center=[9.9, 9.9], comment='say "hi", ok')
    text = CL.export_csv(doc, "all", True)
    lines = text.strip().split("\n")
    assert lines[0].split(",")[:6] == ["id", "name", "role", "lat", "lon", "box_km"]
    assert len(lines) == 1 + 6
    import csv, io
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["original_lat"] == "9.9" and rows[0]["comment"] == 'say "hi", ok'
    nocomment = list(csv.DictReader(io.StringIO(CL.export_csv(doc, "all", False))))
    assert nocomment[0]["comment"] == ""


def _incoming(**kw):
    s = {"id": "new_one", "name": "New one", "role": "train", "center": [50.0, 5.0],
         "box_km": 3, "notes": "", "verified": False, "custom_field": 7}
    s.update(kw)
    return s


def test_plan_import_policies():
    existing = make_sites()["sites"]
    existing[0]["comment"] = "mine"
    existing[0]["original_center"] = [1.0, 1.0]
    inc = [_incoming(), _incoming(id="a_site", name="A from other", center=[11.0, 11.0])]

    skip = CL.plan_import(existing, copy.deepcopy(inc), "skip", CFG)
    assert [x["id"] for x in skip["new"]] == ["new_one"]
    assert skip["skipped"][0]["id"] == "a_site"
    assert len(skip["result_sites"]) == 7

    ren = CL.plan_import(existing, copy.deepcopy(inc), "rename", CFG)
    assert ren["renamed"] == [{"from": "a_site", "to": "a_site_2"}]
    assert len(ren["result_sites"]) == 8

    ov = CL.plan_import(existing, copy.deepcopy(inc), "overwrite", CFG)
    a = next(s for s in ov["result_sites"] if s["id"] == "a_site")
    assert a["name"] == "A from other" and a["comment"] == "mine" and a["original_center"] == [1.0, 1.0]
    assert len(ov["result_sites"]) == 7
    assert next(s for s in ov["result_sites"] if s["id"] == "new_one")["custom_field"] == 7
    # input untouched
    assert existing[0]["name"] == "A site"


def test_plan_import_validation_clamp_and_near_duplicates():
    existing = make_sites()["sites"]
    inc = [{"name": "no centre"},
           _incoming(id="bad_role", role="validation"),
           _incoming(id="oob", center=[95, 0]),
           _incoming(id="big", box_km=20),
           {"name": "Needs slug", "center": [30.0, 30.0]},
           _incoming(id="near_c", center=[40.001, 40.0])]            # next to c_far
    plan = CL.plan_import(existing, inc, "skip", CFG)
    assert len(plan["invalid"]) == 3
    assert plan["clamped"][0]["id"] == "big"
    ids = [x["id"] for x in plan["new"]]
    assert "needs_slug" in ids and "big" in ids
    assert next(s for s in plan["result_sites"] if s["id"] == "big")["box_km"] == 8.0
    assert plan["near"] == [{"id": "near_c", "other": "c_far", "distance_km": 0.11}]
    with pytest.raises(ValueError):
        CL.plan_import(existing, [], "wipe", CFG)
