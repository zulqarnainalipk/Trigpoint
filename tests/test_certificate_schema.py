"""The split certificate follows its published schema, and the verdict follows from the checks."""
import json
import os
import re

import pytest

import splitsafety as S

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = json.load(open(os.path.join(HERE, "docs", "split_certificate.schema.json"), encoding="utf-8"))


def validate(value, schema, path="$"):
    """A small JSON Schema checker: type, enum, const, required, properties, items, minItems, minimum and pattern."""
    errs = []
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "null": type(None), "boolean": bool}
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in {schema['enum']}")
    t = schema.get("type")
    if t:
        ok = any(isinstance(value, types[x]) and not (x == "integer" and isinstance(value, bool)) for x in ([t] if isinstance(t, str) else t))
        if not ok:
            errs.append(f"{path}: wrong type {type(value).__name__}")
            return errs
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: missing {k}")
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                errs += validate(value[k], sub, f"{path}.{k}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: too few items")
        if "items" in schema:
            for i, v in enumerate(value):
                errs += validate(v, schema["items"], f"{path}[{i}]")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errs.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        errs.append(f"{path}: below minimum")
    return errs


def site(i, lat, lon, role):
    return {"id": i, "center": [lat, lon], "role": role, "box_km": 3.0}


KM = 1 / 111.32


def test_the_checker_itself_rejects_wrong_documents():
    assert validate({"schema": "x"}, SCHEMA)
    assert validate([], SCHEMA)
    assert any("pattern" in e or "match" in e for e in validate({**S.build_certificate([site("a", 0, 0, "train"), site("b", 10, 10, "test")]), "roster_sha256": "zz"}, SCHEMA))


@pytest.mark.parametrize("sites,kw", [
    ([site("a", 0, 0, "train"), site("b", 400 * KM, 0, "test")], {}),
    ([site("a", 0, 0, "train"), site("b", 40 * KM, 0, "test")], {}),
    ([site("a", 0, 0, "train")], {}),
    ([], {}),
    ([site(f"s{i}", i * 400 * KM, 0, "train" if i % 2 else "test") for i in range(8)],
     {"targets": {f"s{i}": float(i) for i in range(8)}, "time_info": {"train_end": "2023-01-01", "test_start": "2023-06-01"},
      "duplicates": {"n_images": 8, "n_pairs": 28, "found": []}, "shift": {"median_psi": 0.02, "n_large": 0, "most_different": []}}),
])
def test_certificates_follow_the_schema(sites, kw):
    c = S.build_certificate(sites, **kw)
    assert validate(json.loads(json.dumps(c)), SCHEMA) == []


def test_the_verdict_follows_from_the_checks():
    for sites, kw in [([site("a", 0, 0, "train"), site("b", 400 * KM, 0, "test")], {}), ([site("a", 0, 0, "train"), site("b", 40 * KM, 0, "test")], {})]:
        c = S.build_certificate(sites, **kw)
        statuses = [x["status"] for x in c["checks"]]
        expect = "fail" if "fail" in statuses else "conditional" if ("warn" in statuses or "not_run" in statuses) else "pass"
        assert c["verdict"] == expect
        assert c["not_run"] == [x["id"] for x in c["checks"] if x["status"] == "not_run"]


def test_the_example_certificate_follows_the_schema():
    c = json.load(open(os.path.join(HERE, "examples", "split_certificate.json"), encoding="utf-8"))
    assert validate(c, SCHEMA) == []


def test_the_api_certificate_follows_the_schema(http):
    http("POST", "/api/sites/b_site", {"role": "test"})
    code, c, _ = http("POST", "/api/studies/certificate", {})
    assert code == 200 and validate(c, SCHEMA) == []
