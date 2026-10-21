# NOTE: this script needs the private 136-site collection (set OBSCURA_PRIVATE_ROOT); it is included so the method can be audited, not so it can be run.
"""Build one table of the 136-site roster from the collection records, for the tool evaluation.

Reads (never writes) the competition outputs. Writes site_table.csv next to this file.
"""
import csv, json, os, collections
import numpy as np

ROOT = os.environ.get("OBSCURA_PRIVATE_ROOT", "")   # the private collection; not distributed
HERE = os.path.dirname(os.path.abspath(__file__))
sites = {s["id"]: s for s in json.load(open(os.path.join(ROOT, "pipeline", "sites.json"), encoding="utf-8"))["sites"]}
scr = {r["id"]: r for r in csv.DictReader(open(os.path.join(ROOT, "site-curator", "incubator", "screening.csv"), encoding="utf-8"))}
cnt = collections.defaultdict(collections.Counter)
vals = collections.defaultdict(lambda: collections.defaultdict(list))
avail = collections.defaultdict(lambda: collections.defaultdict(int))
nok = collections.Counter()
seen = {}
bad_lines = collections.Counter()
rep_dir = os.path.join(ROOT, "outputs", "collection_report")
for fn in os.listdir(rep_dir):
    if not fn.endswith("_records.jsonl"):
        continue
    for line in open(os.path.join(rep_dir, fn), encoding="utf-8-sig"):
        line = line.replace("\x00", "").strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            bad_lines[fn] += 1
            continue
        if r["key"] in seen and (seen[r["key"]] == "ok" or r["status"] != "ok"):
            continue
        if r["key"] in seen:
            raise SystemExit("a key appears first as not-ok then ok; handle explicitly: " + r["key"])
        seen[r["key"]] = r["status"]
        sid = r["site_id"]
        cnt[sid][r["status"]] += 1
        if r["status"] != "ok":
            continue
        nok[sid] += 1
        raw = r.get("targets_raw") or {}
        has = {"ch4": r.get("ch4_site_mean") is not None, "no2": raw.get("no2") is not None,
               "co": raw.get("co") is not None, "aai": raw.get("aai") is not None, "firms": raw.get("firms") is not None}
        for t, h in has.items():
            avail[sid][t] += int(h)
        if has["ch4"]:
            vals[sid]["ch4"].append(r["ch4_site_mean"] - (r.get("ch4_bg_median") or r["ch4_site_mean"]))
        for t in ("no2", "co", "aai"):
            if raw.get(t) is not None:
                vals[sid][t].append(raw[t])
rows = []
for sid, s in sites.items():
    c = cnt[sid]
    w = sum(c.values())
    sc = scr.get(sid, {})
    def f(k):
        v = sc.get(k)
        return float(v) if v not in (None, "") else ""
    row = {"id": sid, "role": s["role"], "region": s.get("region", ""), "country": s.get("country", ""), "lat": s["center"][0], "lon": s["center"][1],
           "box_km": s["box_km"], "verified": s.get("verified", False),
           "orig_lat": (s.get("original_center") or [None, None])[0], "orig_lon": (s.get("original_center") or [None, None])[1],
           "land_frac": f("land_frac"), "clear_frac": f("clear_frac"), "fire_days": f("fire_days"), "aai_site": f("aai_site"),
           "no2_contrast": f("no2_contrast"), "co_contrast": f("co_contrast"), "has_screening": bool(sc),
           "windows": w, "ok_windows": nok[sid], "yield": round(nok[sid] / w, 4) if w else ""}
    for t in ("ch4", "no2", "co", "aai", "firms"):
        row["avail_" + t] = round(avail[sid][t] / nok[sid], 4) if nok[sid] else ""
    for t in ("ch4", "no2", "co", "aai"):
        v = vals[sid][t]
        row["mean_" + t] = round(float(np.mean(v)), 5) if len(v) >= 3 else ""
    rows.append(row)
with open(os.path.join(HERE, "site_table.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("unreadable lines:", dict(bad_lines), "; unique windows:", len(seen))
print(len(rows), "rows;", sum(1 for r in rows if r["has_screening"]), "with screening;", sum(1 for r in rows if r["yield"] != ""), "with outcomes")

