"""Provenance record and datasheet for a curated sites file.

The provenance record is a JSON document that says what the roster is, who and what touched it, and which
software and imagery were used, with a hash that ties the record to the exact file. The datasheet is a Markdown
document in the sections of "Datasheets for Datasets" (Gebru et al., 2021), filled in from the roster and the
audit log wherever the tool can know the answer, and with a marked blank wherever only a person can.

Nothing here needs the network or Earth Engine. Private comments are left out unless asked for.
"""
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone

import core

SCHEMA = "site-curator-provenance/1"
BLANK = "[TO COMPLETE]"

# What only a person can say. Each has a question shown in the tool and a datasheet section.
QUESTIONS = {
    "motivation_purpose": ("Motivation", "For what purpose was this roster created? What task or benchmark is it for?"),
    "motivation_who": ("Motivation", "Who created it, and who funded the work?"),
    "composition_sampling": ("Composition", "Is this a sample of a larger set of facilities? How were the facilities chosen?"),
    "composition_missing": ("Composition", "Is anything missing from the roster that users should know about (regions, facility types)?"),
    "collection_sources": ("Collection process", "Where did the starting coordinates come from (lists, registries, memory of a person or a model)?"),
    "collection_review": ("Collection process", "Who checked each site against imagery, and how many people reviewed each one?"),
    "preprocessing_notes": ("Preprocessing and labelling", "Were any sites changed, merged or dropped for reasons not visible in the audit log?"),
    "uses_intended": ("Uses", "What should this roster be used for? What should it not be used for?"),
    "distribution_licence": ("Distribution", "How will the roster be shared, and under which licence?"),
    "maintenance_contact": ("Maintenance", "Who maintains it, and how can people report a problem?"),
}


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def roster_hash(doc):
    """Hash of the roster in a canonical form (sorted keys, no whitespace differences)."""
    return sha256_text(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def moved_km(site):
    o, c = site.get("original_center"), site.get("center")
    if not o or not c:
        return None
    return core.haversine_km(o, c)


def environment():
    env = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("numpy", "rasterio", "scipy", "matplotlib", "ee", "requests"):
        try:
            mod = __import__(name)
            env[name] = getattr(mod, "__version__", "installed")
        except Exception:
            env[name] = None
    return env


def _count(values):
    return dict(sorted(Counter(v if v not in (None, "") else "unknown" for v in values).items()))


def _quantiles(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    pick = lambda q: xs[min(int(q * (len(xs) - 1) + 0.5), len(xs) - 1)]
    return {"n": len(xs), "min": xs[0], "median": pick(0.5), "max": xs[-1]}


def summarise_roster(doc):
    sites = doc.get("sites", [])
    active = [s for s in sites if not s.get("rejected")]
    moves = [moved_km(s) for s in active]
    return {
        "sites_in_file": len(sites),
        "kept_or_pending": len(active),
        "rejected": len(sites) - len(active),
        "verified": sum(1 for s in active if s.get("verified")),
        "by_role": _count(s.get("role") for s in active),
        "by_region": _count(s.get("region") for s in active),
        "by_facility_type": _count(s.get("facility_type") for s in active),
        "by_coordinate_confidence": _count(s.get("coord_confidence") for s in active),
        "box_km": _quantiles([s.get("box_km") for s in active]),
        "centre_moved_km": _quantiles(moves),
        "centre_never_moved": sum(1 for s in active if s.get("original_center") is None),
    }


def summarise_audit(entries):
    entries = list(entries)
    stamps = sorted(e.get("ts", "") for e in entries if e.get("ts"))
    return {"actions": len(entries), "by_action": _count(e.get("action") for e in entries),
            "first": stamps[0] if stamps else None, "last": stamps[-1] if stamps else None,
            "sites_touched": len({e.get("site_id") for e in entries if e.get("site_id")})}


def build_provenance(doc, audit_entries=(), imagery=(), tool_version="", sites_name="", include_comments=False,
                     now=None, env=None, studies=None):
    """The provenance record as a dictionary.

    ``imagery`` is a list of metadata dictionaries of fetched images (backend, source, date, whether synthetic) so
    that the record states what evidence the checks used. Synthetic demo images are counted separately and flagged.
    """
    now = now or datetime.now(timezone.utc).isoformat()
    per_site = []
    for s in doc.get("sites", []):
        item = {"id": s.get("id"), "role": s.get("role"), "center": s.get("center"), "box_km": s.get("box_km"),
                "verified": bool(s.get("verified")), "rejected": bool(s.get("rejected")),
                "original_center": s.get("original_center"),
                "centre_moved_km": None if moved_km(s) is None else round(moved_km(s), 3)}
        if include_comments and s.get("comment"):
            item["comment"] = s["comment"]
        per_site.append(item)
    imagery = list(imagery)
    real = [m for m in imagery if not m.get("synthetic")]
    synth = [m for m in imagery if m.get("synthetic")]
    return {
        "schema": SCHEMA,
        "generated_at": now,
        "tool": {"name": "TrigPoint", "version": tool_version},
        "environment": env if env is not None else environment(),
        "roster": {"file": sites_name, "sha256": roster_hash(doc), "summary": summarise_roster(doc)},
        "limits": {k: core.CFG[k] for k in ("min_box_km", "max_box_km", "chip_px", "label_box_km", "bg_inner_km",
                                             "bg_outer_km", "min_split_distance_km")},
        "audit": summarise_audit(audit_entries),
        "imagery_used": {"real_images": len(real), "synthetic_images": len(synth),
                         "backends": _count(m.get("backend") for m in imagery),
                         "sources": _count(m.get("source") for m in imagery),
                         "note": ("Synthetic demo images were fetched; they are not evidence about any real place."
                                  if synth else "")},
        "sites": per_site,
        "comments_included": bool(include_comments),
        "studies": studies or {},
    }


def verify_provenance(record, doc):
    """Check that a provenance record belongs to this roster. Returns a list of problems (empty if it matches)."""
    problems = []
    if record.get("schema") != SCHEMA:
        problems.append(f"unknown schema {record.get('schema')!r}")
    want = record.get("roster", {}).get("sha256")
    if want != roster_hash(doc):
        problems.append("the roster has changed since this record was made (hash differs)")
    return problems


def _table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _counts_table(d, label):
    return _table(sorted(d.items(), key=lambda kv: (-kv[1], str(kv[0]))), [label, "Sites"])


def build_datasheet(doc, record, answers=None):
    """Datasheet in Markdown. ``answers`` maps keys of ``QUESTIONS`` to text; missing answers stay marked."""
    ans = answers or {}
    A = lambda k: (ans.get(k) or "").strip() or f"{BLANK} {QUESTIONS[k][1]}"
    s = record["roster"]["summary"]
    box, mv = s["box_km"], s["centre_moved_km"]
    au, im = record["audit"], record["imagery_used"]
    lines = [f"# Datasheet for the roster `{record['roster']['file'] or 'sites.json'}`", "",
             f"Made with TrigPoint {record['tool']['version']} on {record['generated_at'][:10]}. "
             f"Roster hash (SHA-256): `{record['roster']['sha256']}`. "
             "Numbers come from the file and the audit log; marked blanks need a person.", "",
             "## Motivation", "", A("motivation_purpose"), "", A("motivation_who"), "",
             "## Composition", "",
             f"The file holds {s['sites_in_file']} sites: {s['kept_or_pending']} active ({s['verified']} verified) and "
             f"{s['rejected']} rejected. Each site is a facility with a centre (latitude, longitude), a square image box "
             f"({core.CFG['min_box_km']} to {core.CFG['max_box_km']} km) and a role (train, test or decoy).", ""]
    if box:
        lines += [f"Box size: median {box['median']} km (range {box['min']} to {box['max']} km).", ""]
    lines += ["**Roles**", "", _counts_table(s["by_role"], "Role"), "", "**Regions**", "", _counts_table(s["by_region"], "Region"), "",
              "**Facility types**", "", _counts_table(s["by_facility_type"], "Type"), "",
              "**Coordinate confidence (starting coordinates)**", "", _counts_table(s["by_coordinate_confidence"], "Confidence"), "",
              A("composition_sampling"), "", A("composition_missing"), "",
              "## Collection process", "", A("collection_sources"), "", A("collection_review"), "",
              f"Review log: {au['actions']} recorded actions on {au['sites_touched']} sites"
              + (f", from {au['first'][:10]} to {au['last'][:10]}" if au["first"] else "") + ".", ""]
    if au["by_action"]:
        lines += [_counts_table(au["by_action"], "Action"), ""]
    lines += ["## Preprocessing, cleaning and labelling", "",
              (f"Centres were moved by a median of {mv['median']:.2f} km (largest {mv['max']:.2f} km) from the starting "
               f"coordinates for the {mv['n']} sites that were moved; {s['centre_never_moved']} sites were never moved.")
              if mv else "No centre has been moved from its starting position.", "",
              "Every save was checked by the built-in validator (required fields, role, range of the centre, box limits, "
              "unique identifiers) and a timestamped backup was kept.", "",
              (f"Imagery used as evidence: {im['real_images']} real image(s) and {im['synthetic_images']} synthetic demo image(s)."
               + (" " + im["note"] if im["note"] else "")), "", A("preprocessing_notes"), "",
              "## Uses", "", A("uses_intended"), "",
              "Known limits of any roster built this way: starting coordinates can be wrong by kilometres, a box may miss part "
              "of a large facility, and a role assignment is only as good as the distance check between train and test sites "
              f"({core.CFG['min_split_distance_km']:.0f} km in this tool).", "",
              "## Distribution", "", A("distribution_licence"), "",
              "## Maintenance", "", A("maintenance_contact"), ""]
    return "\n".join(lines)


def datasheet_gaps(markdown):
    """How many marked blanks are still left, and which questions they are."""
    left = [q for key, (_sec, q) in QUESTIONS.items() if f"{BLANK} {q}" in markdown]
    return {"remaining": len(left), "questions": left, "total": len(QUESTIONS)}


REQUIRED_SECTIONS = ("Motivation", "Composition", "Collection process", "Preprocessing, cleaning and labelling",
                     "Uses", "Distribution", "Maintenance")


def datasheet_sections_present(markdown):
    """Names of the required datasheet sections that are missing (empty list when complete)."""
    return [s for s in REQUIRED_SECTIONS if f"## {s}" not in markdown]
