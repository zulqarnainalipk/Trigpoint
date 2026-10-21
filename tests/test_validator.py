"""validator.py: every rule, the command line, and the odd inputs."""
import json
import os
import subprocess
import sys

import pytest

import validator as V

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def site(**kw):
    s = {"id": "a_site", "name": "A site", "role": "train", "center": [10.0, 10.0], "box_km": 3.0, "verified": True}
    s.update(kw)
    return s


def doc(*sites):
    return {"sites": list(sites)}


def test_a_good_file_has_no_errors():
    rep = V.validate_document(doc(site(), site(id="b_site", name="B site")))
    assert rep.ok and rep.errors == []


@pytest.mark.parametrize("bad", [None, [], "text", {"sites": "x"}, {}])
def test_document_must_have_a_sites_list(bad):
    rep = V.validate_document(bad)
    assert not rep.ok and "'sites' list" in rep.errors[0]


@pytest.mark.parametrize("field", list(V.REQUIRED))
def test_each_required_field_is_checked(field):
    s = site()
    del s[field]
    rep = V.validate_document(doc(s))
    assert any(f"required field '{field}'" in e for e in rep.errors)


def test_duplicate_ids_are_errors():
    rep = V.validate_document(doc(site(), site(name="Other")))
    assert any("duplicate site id" in e for e in rep.errors)


@pytest.mark.parametrize("role", ["", "Train", "validation", None, 3])
def test_role_must_be_known(role):
    rep = V.validate_document(doc(site(role=role)))
    assert any("role must be one of" in e for e in rep.errors)


@pytest.mark.parametrize("c", [[91, 0], [-91, 0], [0, 181], [0, -181], [1], [1, 2, 3], "1,2", [None, 1], [True, 1],
                               [float("nan"), 1], [float("inf"), 1]])
def test_centre_must_be_two_finite_numbers_in_range(c):
    rep = V.validate_document(doc(site(center=c)))
    assert any("center" in e for e in rep.errors)


@pytest.mark.parametrize("box", [0.99, 8.01, -1, 0, "3", None, True, float("nan")])
def test_box_must_be_a_number_in_range(box):
    rep = V.validate_document(doc(site(box_km=box)))
    assert any("box_km" in e for e in rep.errors)


@pytest.mark.parametrize("box", [1.0, 8.0, 4.25])
def test_box_limits_are_inclusive(box):
    assert V.validate_document(doc(site(box_km=box))).ok


def test_limits_can_be_changed():
    assert V.validate_document(doc(site(box_km=12)), max_box_km=15).ok
    assert not V.validate_document(doc(site(box_km=3)), min_box_km=4).ok


def test_name_must_not_be_blank():
    rep = V.validate_document(doc(site(name="   ")))
    assert any("name must be" in e for e in rep.errors)


def test_verified_must_be_boolean():
    rep = V.validate_document(doc(site(verified="yes")))
    assert any("verified must be" in e for e in rep.errors)


def test_entries_that_are_not_objects_are_errors_not_crashes():
    rep = V.validate_document({"sites": [1, "x", None]})
    assert len(rep.errors) == 3


def test_warnings_do_not_block():
    rep = V.validate_document(doc(site(id="Bad-Id", verified=False), site(id="b", name="a SITE", center=[0, 0])))
    assert rep.ok
    text = " ".join(rep.warnings)
    assert "lowercase" in text and "same name" in text and "placeholder" in text and "not verified" in text


def test_rejected_sites_do_not_count_as_unverified():
    rep = V.validate_document(doc(site(verified=False, rejected=True)))
    assert not any("not verified" in w for w in rep.warnings)


def test_extra_keys_are_allowed():
    assert V.validate_document({"_README": ["x"], "sites": [site(extra={"a": 1})], "other": 5}).ok


def test_validate_file_handles_missing_and_broken_files(tmp_path):
    assert "could not read" in V.validate_file(str(tmp_path / "nope.json")).errors[0]
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert "could not read" in V.validate_file(str(bad)).errors[0]
    notutf = tmp_path / "latin.json"
    notutf.write_bytes(b'{"sites": [{"name": "caf\xe9"}]}')
    assert not V.validate_file(str(notutf)).ok


def test_command_line_exit_codes_and_json(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(doc(site())), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc(site(box_km=99))), encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, os.path.join(HERE, "validator.py"), *a], capture_output=True, text=True)
    assert run(str(good)).returncode == 0
    r = run(str(bad))
    assert r.returncode == 1 and "box_km" in r.stdout
    j = json.loads(run(str(bad), "--json").stdout)
    assert j["ok"] is False and j["errors"]
    assert run().returncode == 2
