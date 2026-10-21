"""Roster validator: the rules a sites file must satisfy, with no dependency on any other project.

Use it three ways:

    python validator.py sites.json              # print errors and warnings, exit code 1 if there are errors
    python validator.py sites.json --json       # machine-readable report
    from validator import validate_document     # inside the curator, before every write

A sites file is a JSON object with a ``sites`` list. Each site needs ``id``, ``name``, ``role``
(train, test or decoy), ``center`` as [latitude, longitude] and ``box_km`` inside the allowed range.
Other keys are kept untouched. Errors stop a save; warnings are advice.
"""
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field

VALID_ROLES = ("train", "test", "decoy")
MIN_BOX_KM = 1.0
MAX_BOX_KM = 8.0
REQUIRED = ("id", "name", "role", "center", "box_km")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_document(doc, min_box_km=MIN_BOX_KM, max_box_km=MAX_BOX_KM, roles=VALID_ROLES):
    """Check a parsed sites document. Returns a :class:`Report`.

    The messages name the site and the field so that a person can fix the file without reading code.
    """
    rep = Report()
    if not isinstance(doc, dict) or "sites" not in doc or not isinstance(doc["sites"], list):
        rep.errors.append("doc missing a 'sites' list")
        return rep
    seen, names = {}, {}
    for pos, s in enumerate(doc["sites"]):
        if not isinstance(s, dict):
            rep.errors.append(f"entry {pos} is not an object")
            continue
        missing = [k for k in REQUIRED if k not in s]
        if missing:
            rep.errors.append(f"site missing required field '{missing[0]}': {s}")
            continue
        sid = s["id"]
        if not isinstance(sid, str) or not sid:
            rep.errors.append(f"entry {pos}: id must be a non-empty string")
            continue
        if sid in seen:
            rep.errors.append(f"duplicate site id: {sid}")
        seen[sid] = pos
        if not ID_RE.match(sid):
            rep.warnings.append(f"site {sid}: ids work best as lowercase letters, digits and underscores")
        if not isinstance(s["name"], str) or not s["name"].strip():
            rep.errors.append(f"site {sid}: name must be a non-empty string")
        elif s["name"].strip().lower() in names:
            rep.warnings.append(f"site {sid}: same name as site {names[s['name'].strip().lower()]}")
        else:
            names[s["name"].strip().lower()] = sid
        if s["role"] not in roles:
            rep.errors.append(f"site {sid}: role must be one of {tuple(roles)}, got {s['role']!r}")
        c = s["center"]
        if not (isinstance(c, (list, tuple)) and len(c) == 2 and _is_number(c[0]) and _is_number(c[1])):
            rep.errors.append(f"site {sid}: center must be [latitude, longitude] as numbers, got {c!r}")
        else:
            lat, lon = c
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                rep.errors.append(f"site {sid}: center out of range {c}")
            elif lat == 0 and lon == 0:
                rep.warnings.append(f"site {sid}: centre is exactly 0, 0 (probably a placeholder)")
        box = s["box_km"]
        if not _is_number(box):
            rep.errors.append(f"site {sid}: box_km must be a number, got {box!r}")
        elif not (min_box_km <= box <= max_box_km):
            rep.errors.append(f"site {sid}: box_km {box} outside [{min_box_km}, {max_box_km}]")
        if "verified" in s and not isinstance(s["verified"], bool):
            rep.errors.append(f"site {sid}: verified must be true or false")
    active = [s for s in doc["sites"] if isinstance(s, dict) and s.get("role") in roles and not s.get("rejected")]
    unverified = [s.get("id") for s in active if not s.get("verified")]
    if unverified:
        rep.warnings.append(f"{len(unverified)} of {len(active)} sites are not verified yet")
    return rep


def validate_file(path, **kw):
    """Read and check a sites file. A file that is not valid JSON gives an error, not an exception."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        rep = Report()
        rep.errors.append(f"could not read {os.path.basename(path)}: {e}")
        return rep
    return validate_document(doc, **kw)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    rep = validate_file(argv[0])
    if "--json" in argv:
        print(json.dumps(rep.as_dict(), indent=2))
    else:
        for e in rep.errors:
            print("ERROR  ", e)
        for w in rep.warnings:
            print("warning", w)
        print("ok" if rep.ok else f"{len(rep.errors)} error(s)")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
