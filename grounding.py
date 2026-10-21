"""Coordinate grounding: compare a site's recalled coordinates with open registries.

The registries are files you supply (CSV, GeoJSON or a Wikidata query result), for example Wikidata (CC0) and the Global
Energy Monitor trackers (CC BY 4.0). Matching uses place names and countries and the distance between positions; no
model is involved. The result is a flag (agree, differ, disagree, not found) and the nearest registry entry, so a
person knows where to look first. It never moves a site on its own.
"""
import csv
import io
import json
import math
import re
import unicodedata

import numpy as np
from scipy import stats

import splitsafety as SS

AGREE_KM = 2.0
DISAGREE_KM = 5.0
MATCH_MIN = 0.5
STOP = set("""the of and de du da di del la le el al an in at on for plant plants station stations complex complexes facility facilities
works site sites refinery refineries refining petrochemical petrochem petrochemicals gas processing process oil oilfield field fields
power energy lng lpg industrial industry city park zone terminal terminals unit units company co ltd limited corp corporation inc
mine mines mining coal copper steel chemical chemicals ctl gnl""".split())


def norm_tokens(text):
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 2 and t not in STOP]
    return toks


def name_score(a, b):
    """Overlap of two place names after dropping generic words (0 to 1): half Jaccard, half containment."""
    A, B = set(norm_tokens(a)), set(norm_tokens(b))
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return 0.5 * inter / len(A | B) + 0.5 * inter / min(len(A), len(B))


# ------------------------------------------------------------------------------------------------------
# registries
# ------------------------------------------------------------------------------------------------------

def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _entry(name, lat, lon, source, country="", eid="", kind="", aliases=()):
    lat, lon = _num(lat), _num(lon)
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or not str(name or "").strip():
        return None
    return {"name": str(name).strip(), "lat": lat, "lon": lon, "source": source, "country": str(country or "").strip(),
            "id": str(eid or ""), "kind": str(kind or ""), "aliases": [a for a in aliases if a]}


def parse_registry(text, source="registry", fmt=None):
    """Read a registry from text. ``fmt`` is 'csv', 'geojson' or 'wikidata' (guessed when omitted).

    CSV needs columns for the name, latitude and longitude (``name``/``lat``/``lon`` and common variants such as
    ``Plant name`` and ``Latitude`` are understood). Entries without a usable position or name are skipped and counted.
    """
    text = text.lstrip("﻿")
    if fmt is None:
        t = text.lstrip()[:1]
        fmt = "csv" if t not in "{[" else ("wikidata" if '"bindings"' in text[:2000] else "geojson")
    out, skipped = [], 0
    if fmt == "csv":
        rd = csv.DictReader(io.StringIO(text))
        low = {k: k for k in (rd.fieldnames or [])}
        def pick(row, *names):
            for k in low:
                if k.strip().lower() in names:
                    return row[k]
            return None
        for row in rd:
            e = _entry(pick(row, "name", "plant name", "unit name", "facility", "facility name", "refinery name", "project", "label", "itemlabel"),
                       pick(row, "lat", "latitude", "y"), pick(row, "lon", "lng", "longitude", "x"), source,
                       pick(row, "country", "country/area", "country code", "iso2") or "",
                       pick(row, "id", "gem id", "gem unit/phase id", "wiki id", "qid", "item") or "",
                       pick(row, "type", "kind", "class", "fuel") or "", [pick(row, "alias", "other names", "local name")])
            if e:
                out.append(e)
            else:
                skipped += 1
    elif fmt == "geojson":
        gj = json.loads(text)
        for f in gj.get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") != "Point":
                skipped += 1
                continue
            p = f.get("properties") or {}
            e = _entry(p.get("name") or p.get("label") or p.get("Plant name"), g["coordinates"][1], g["coordinates"][0], source,
                       p.get("country") or "", p.get("id") or p.get("qid") or "", p.get("type") or "")
            if e:
                out.append(e)
            else:
                skipped += 1
    elif fmt == "wikidata":
        for b in json.loads(text)["results"]["bindings"]:
            m = re.match(r"Point\(([-\d.eE+]+) ([-\d.eE+]+)\)", (b.get("coord") or {}).get("value", ""))
            if not m:
                skipped += 1
                continue
            e = _entry((b.get("itemLabel") or {}).get("value"), m.group(2), m.group(1), source,
                       (b.get("countryCode") or b.get("countryLabel") or {}).get("value", ""),
                       (b.get("item") or {}).get("value", "").rsplit("/", 1)[-1], (b.get("classLabel") or {}).get("value", ""))
            if e:
                out.append(e)
            else:
                skipped += 1
    else:
        raise ValueError("fmt must be 'csv', 'geojson' or 'wikidata'")
    return {"source": source, "entries": out, "skipped": skipped, "format": fmt}


# ------------------------------------------------------------------------------------------------------
# matching
# ------------------------------------------------------------------------------------------------------

def _country_ok(site_country, entry_country):
    a, b = (site_country or "").strip().lower(), (entry_country or "").strip().lower()
    return not a or not b or a == b or a in b or b in a


def match_site(site, entries, search_km=100.0, min_score=MATCH_MIN, centre=None):
    """Best registry entry for a site by name (within ``search_km`` (default 100 km)), and the nearest entry whatever its name.

    ``centre`` is the position to compare (default: the site's centre).
    """
    c = centre or site["center"]
    best = None
    nearest = None
    for e in entries:
        d = SS.haversine_km(c, (e["lat"], e["lon"]))
        if nearest is None or d < nearest["distance_km"]:
            nearest = {"entry": e, "distance_km": d}
        if d > search_km or not _country_ok(site.get("country"), e.get("country")):
            continue
        sc = max([name_score(site.get("name") or site["id"], e["name"])] + [name_score(site.get("name") or site["id"], a) for a in e.get("aliases", [])])
        if sc < min_score:
            continue
        key = (sc, -d)
        if best is None or key > best["_key"]:
            best = {"entry": e, "distance_km": d, "name_score": round(sc, 3), "_key": key}
    if best:
        best.pop("_key")
        best["distance_km"] = round(best["distance_km"], 2)
    if nearest:
        nearest["distance_km"] = round(nearest["distance_km"], 2)
    return best, nearest


def status_for(d_km, agree_km=AGREE_KM, disagree_km=DISAGREE_KM):
    if d_km is None:
        return "not_found"
    return "agree" if d_km <= agree_km else "differ" if d_km <= disagree_km else "disagree"


def ground_site(site, registries, centre=None, agree_km=AGREE_KM, disagree_km=DISAGREE_KM, search_km=100.0):
    """Grounding record for one site against several registries (each ``parse_registry`` output)."""
    c = centre or site["center"]
    matches = []
    for reg in registries:
        best, near = match_site(site, reg["entries"], search_km, centre=c)
        matches.append({"source": reg["source"], "matched": bool(best),
                        "entry": best["entry"] if best else None, "distance_km": best["distance_km"] if best else None,
                        "name_score": best["name_score"] if best else None,
                        "nearest_entry": near["entry"] if near else None, "nearest_km": near["distance_km"] if near else None,
                        "status": status_for(best["distance_km"] if best else None, agree_km, disagree_km)})
    found = [m for m in matches if m["matched"]]
    spread = None
    if len(found) >= 2:
        spread = max(SS.haversine_km((a["entry"]["lat"], a["entry"]["lon"]), (b["entry"]["lat"], b["entry"]["lon"]))
                     for i, a in enumerate(found) for b in found[i + 1:])
    if not found:
        overall = "not_found"
    else:
        order = {"disagree": 3, "differ": 2, "agree": 1}
        overall = max((m["status"] for m in found), key=lambda s: order[s])
    suggested = None
    if found:
        top = max(found, key=lambda m: m["name_score"])
        suggested = [round(top["entry"]["lat"], 6), round(top["entry"]["lon"], 6)]
    return {"id": site["id"], "centre": list(c), "status": overall, "matches": matches, "registry_spread_km": round(spread, 2) if spread is not None else None,
            "suggested_centre": suggested}


def ground_roster(sites, registries, use_original=True, **kw):
    """Ground every active site. With ``use_original`` the position compared is ``original_center`` when the site has one,
    which is how recalled coordinates are checked after you have already corrected them on the map."""
    out = []
    for s in sites:
        if s.get("rejected"):
            continue
        c = s.get("original_center") if use_original and s.get("original_center") else s["center"]
        out.append(ground_site(s, registries, centre=c, **kw))
    counts = {k: sum(1 for r in out if r["status"] == k) for k in ("agree", "differ", "disagree", "not_found")}
    return {"n_sites": len(out), "counts": counts, "sites": out}


# ------------------------------------------------------------------------------------------------------
# evaluation against verified centres
# ------------------------------------------------------------------------------------------------------

def _summ(errs):
    e = np.asarray(errs, float)
    if not len(e):
        return {"n": 0}
    return {"n": int(len(e)), "median_km": round(float(np.median(e)), 2), "mean_km": round(float(e.mean()), 2),
            "within_1km": round(float((e <= 1).mean()), 3), "within_2km": round(float((e <= 2).mean()), 3),
            "within_5km": round(float((e <= 5).mean()), 3), "max_km": round(float(e.max()), 2)}


def auc(score, positive):
    """Probability that a random positive has a larger score than a random negative (0.5 means no information)."""
    s = np.asarray(score, float)
    p = np.asarray(positive, bool)
    if p.all() or not p.any():
        return None
    ranks = stats.rankdata(s)
    return float((ranks[p].sum() - p.sum() * (p.sum() + 1) / 2) / (p.sum() * (~p).sum()))


def evaluate(sites, registries, truth_key="center", recalled_key="original_center", big_error_km=5.0, **kw):
    """Error of recalled coordinates and of registry coordinates against verified centres.

    Uses sites that have both the verified centre (``truth_key``) and the recalled position (``recalled_key``). Reports
    the error of the recalled position, of the registry position where a match was found, and of a combined policy
    (registry position when matched, else recalled). Also reports whether the distance between the recalled and the
    registry position predicts a large recalled error (the area under the curve; 0.5 means it does not).
    """
    rows = []
    for s in sites:
        if s.get("rejected") or not s.get("verified") or not s.get(recalled_key):
            continue
        truth, rec = s[truth_key], s[recalled_key]
        g = ground_site(s, registries, centre=rec, **kw)
        top = max([m for m in g["matches"] if m["matched"]], key=lambda m: m["name_score"], default=None)
        reg = (top["entry"]["lat"], top["entry"]["lon"]) if top else None
        rows.append({"id": s["id"], "recalled_error_km": SS.haversine_km(truth, rec),
                     "registry_error_km": SS.haversine_km(truth, reg) if reg else None,
                     "disagreement_km": top["distance_km"] if top else None, "status": g["status"],
                     "combined_error_km": SS.haversine_km(truth, reg) if reg else SS.haversine_km(truth, rec),
                     "country": s.get("country"), "facility_type": s.get("facility_type")})
    matched = [r for r in rows if r["registry_error_km"] is not None]
    out = {"n_verified_sites": len(rows), "n_with_registry_match": len(matched),
           "recalled": _summ([r["recalled_error_km"] for r in rows]),
           "recalled_on_matched_sites": _summ([r["recalled_error_km"] for r in matched]),
           "registry_on_matched_sites": _summ([r["registry_error_km"] for r in matched]),
           "combined_policy": _summ([r["combined_error_km"] for r in rows]),
           "status_counts": {k: sum(1 for r in rows if r["status"] == k) for k in ("agree", "differ", "disagree", "not_found")},
           "sites": rows}
    if len(matched) >= 8:
        big = [r["recalled_error_km"] > big_error_km for r in matched]
        out["disagreement_predicts_big_error_auc"] = auc([r["disagreement_km"] for r in matched], big) if any(big) and not all(big) else None
        out["big_error_km"] = big_error_km
        out["n_big_recalled_errors_among_matched"] = int(sum(big))
    return out


# ------------------------------------------------------------------------------------------------------
# optional live source (needs the internet; the caller decides when to use it)
# ------------------------------------------------------------------------------------------------------

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"


def wikidata_query(class_ids, country_code=None, limit=5000):
    """SPARQL text for items that are an instance of (or subclass of) the given classes and have a coordinate.

    ``class_ids`` are Wikidata class ids such as ``Q...``; check them before use. ``country_code`` is an ISO 3166-1 alpha-2
    code (property P297) and optional.
    """
    ids = [c for c in class_ids if re.fullmatch(r"Q\d+", c)]
    if not ids:
        raise ValueError("give at least one Wikidata class id like Q12345")
    values = " ".join(f"wd:{c}" for c in ids)
    filt = f'?item wdt:P17 ?cn. ?cn wdt:P297 "{country_code}".' if country_code and re.fullmatch(r"[A-Za-z]{2}", country_code) else ""
    return ("SELECT ?item ?itemLabel ?coord ?classLabel ?countryCode WHERE { VALUES ?class { " + values + " } "
            "?item wdt:P31/wdt:P279* ?class. ?item wdt:P625 ?coord. OPTIONAL { ?item wdt:P17 ?c2. ?c2 wdt:P297 ?countryCode. } "
            + filt + ' SERVICE wikibase:label { bd:serviceParam wikibase:language "en,[AUTO_LANGUAGE]". } } LIMIT ' + str(int(limit)))


def fetch_wikidata(sparql, http=None, user_agent="TrigPoint/1.5 (coordinate grounding; contact the tool owner)"):
    """Run a SPARQL query and return the JSON text. ``http`` is a requests-like object (replaced in tests)."""
    if http is None:
        import requests as http
    r = http.get(WIKIDATA_ENDPOINT, params={"query": sparql, "format": "json"}, headers={"User-Agent": user_agent, "Accept": "application/sparql-results+json"}, timeout=90)
    r.raise_for_status()
    return r.text
