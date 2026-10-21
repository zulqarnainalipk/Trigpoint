"""provenance.py: the record, its hash, the datasheet and the gaps."""
import copy
import json

import pytest

import provenance as P


def doc():
    return {"sites": [
        {"id": "a", "name": "A", "role": "train", "center": [10.0, 10.0], "box_km": 3.0, "verified": True,
         "region": "r1", "facility_type": "refinery", "coord_confidence": "high",
         "original_center": [10.0, 10.0], "comment": "private remark"},
        {"id": "b", "name": "B", "role": "test", "center": [20.0, 20.0], "box_km": 5.0, "verified": False,
         "region": "r2", "facility_type": "lng", "original_center": [20.0, 20.03]},
        {"id": "c", "name": "C", "role": "decoy", "center": [30.0, 30.0], "box_km": 2.0, "rejected": True},
    ]}


AUDIT = [{"ts": "2026-10-01T10:00:00+00:00", "action": "update", "site_id": "a"},
         {"ts": "2026-10-02T10:00:00+00:00", "action": "update", "site_id": "b"},
         {"ts": "2026-10-03T10:00:00+00:00", "action": "bulk_reject", "site_id": None}]
IMAGERY = [{"backend": "ee", "source": "median", "synthetic": False}, {"backend": "demo", "source": "single", "synthetic": True}]


def rec(**kw):
    return P.build_provenance(doc(), AUDIT, IMAGERY, tool_version="9.9", sites_name="s.json", now="2026-10-18T00:00:00+00:00",
                              env={"python": "x"}, **kw)


def test_roster_hash_ignores_key_order_and_changes_with_content():
    d = doc()
    reordered = {"sites": [dict(reversed(list(s.items()))) for s in d["sites"]]}
    assert P.roster_hash(d) == P.roster_hash(reordered)
    d2 = copy.deepcopy(d)
    d2["sites"][0]["box_km"] = 3.25
    assert P.roster_hash(d) != P.roster_hash(d2)


def test_record_counts_and_summary():
    r = rec()
    s = r["roster"]["summary"]
    assert s["sites_in_file"] == 3 and s["rejected"] == 1 and s["kept_or_pending"] == 2 and s["verified"] == 1
    assert s["by_role"] == {"test": 1, "train": 1} and s["by_coordinate_confidence"]["unknown"] == 1
    assert s["box_km"]["median"] in (3.0, 5.0) and s["centre_never_moved"] == 0
    assert 3.0 < s["centre_moved_km"]["max"] < 3.6                       # 0.03 degrees of latitude is about 3.3 km
    assert r["audit"]["actions"] == 3 and r["audit"]["sites_touched"] == 2 and r["audit"]["first"].startswith("2026-10-01")
    assert r["tool"]["version"] == "9.9" and r["roster"]["file"] == "s.json" and r["schema"] == P.SCHEMA


def test_synthetic_imagery_is_flagged():
    r = rec()
    assert r["imagery_used"]["real_images"] == 1 and r["imagery_used"]["synthetic_images"] == 1
    assert "not evidence" in r["imagery_used"]["note"]
    assert rec()["imagery_used"]["backends"] == {"demo": 1, "ee": 1}
    none = P.build_provenance(doc(), [], [], now="t", env={})
    assert none["imagery_used"]["note"] == "" and none["audit"]["first"] is None


def test_private_comments_only_when_asked():
    assert "comment" not in json.dumps(rec()["sites"])
    assert "private remark" in json.dumps(rec(include_comments=True)["sites"])
    assert rec()["comments_included"] is False


def test_the_record_is_json_serialisable_and_verifies_against_its_roster():
    r = json.loads(json.dumps(rec()))
    assert P.verify_provenance(r, doc()) == []
    changed = doc()
    changed["sites"][1]["center"] = [20.1, 20.1]
    assert any("changed" in p for p in P.verify_provenance(r, changed))
    assert any("schema" in p for p in P.verify_provenance({"schema": "x"}, doc()))


def test_environment_lists_versions_without_crashing():
    env = P.environment()
    assert env["python"] and "numpy" in env


def test_datasheet_has_all_sections_and_marks_what_is_unknown():
    r = rec()
    md = P.build_datasheet(doc(), r)
    assert P.datasheet_sections_present(md) == []
    gaps = P.datasheet_gaps(md)
    assert gaps["remaining"] == gaps["total"] == len(P.QUESTIONS)
    assert "2 active (1 verified) and 1 rejected" in md
    assert r["roster"]["sha256"] in md
    assert "| refinery | 1 |" in md and "| train | 1 |" in md
    assert "synthetic demo image" in md


def test_answers_fill_the_blanks():
    answers = {k: f"answer {k}" for k in P.QUESTIONS}
    md = P.build_datasheet(doc(), rec(), answers)
    assert P.datasheet_gaps(md)["remaining"] == 0 and "answer uses_intended" in md and P.BLANK not in md
    partial = P.build_datasheet(doc(), rec(), {"uses_intended": "  ", "maintenance_contact": "me@example.org"})
    assert P.datasheet_gaps(partial)["remaining"] == len(P.QUESTIONS) - 1


def test_datasheet_for_an_empty_roster_does_not_crash():
    empty = {"sites": []}
    r = P.build_provenance(empty, [], [], now="t", env={})
    md = P.build_datasheet(empty, r)
    assert "0 sites" in md and "No centre has been moved" in md


def test_missing_section_is_detected():
    assert P.datasheet_sections_present("# x\n## Motivation\n") == [s for s in P.REQUIRED_SECTIONS if s != "Motivation"]
