"""Fetching, caching and rendering imagery for the curator server.

The server asks this module for four things: a rendered picture of a site, the statistics of that picture,
candidate areas on it, and a test of the gap fill. All of them work on one cached chip per (site, place, box,
backend, source, period), so changing the view, the stretch or the fill never downloads anything again.
"""
import glob
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone

import backends as B
import core
import imagery_tools as it

SAFE = re.compile(r"[^A-Za-z0-9._-]+")
FILLS = ("none", "mean", "nearest")
DEFAULTS = {"source": "single", "view": "true_color", "stretch": "percentile", "fill": "none", "days": 120, "q": 20}


class ImageryError(ValueError):
    """A request that cannot be served, with a message for the person using the tool."""


def safe(name):
    """A file-name-safe version of any text (no path separators, no dots-only names)."""
    s = SAFE.sub("_", str(name)).strip("._")
    return s or "x"


def site_token(site_id):
    """A file-name-safe token for a site id that stays unique: ids that clean to the same text (a/b and a_b) still differ."""
    return f"{safe(site_id)}-{hashlib.sha1(str(site_id).encode('utf-8')).hexdigest()[:6]}"


class ImageryService:
    def __init__(self, cache_dir, backend_registry, max_mb=500):
        self.cache_dir = cache_dir
        self.max_mb = max_mb
        self.backends = backend_registry
        self._locks = {}
        self._guard = threading.Lock()
        os.makedirs(cache_dir, exist_ok=True)

    # ---------------------------------------------------------------- parameters

    def clean(self, p, max_box=None):
        """Validate and complete request parameters. Raises ImageryError with a plain message.

        ``max_box`` raises the largest allowed box (used for the wider context picture of the placement study).
        """
        out = dict(DEFAULTS)
        out.update({k: v for k, v in p.items() if v not in (None, "")})
        if out["source"] not in B.SOURCES:
            raise ImageryError(f"unknown source {out['source']!r}; choose from {list(B.SOURCES)}")
        if out["stretch"] not in it.STRETCHES:
            raise ImageryError(f"unknown stretch {out['stretch']!r}; choose from {list(it.STRETCHES)}")
        if out["fill"] not in FILLS:
            raise ImageryError(f"unknown fill {out['fill']!r}; choose from {list(FILLS)}")
        if out["view"] not in it.COMPOSITES and out["view"] not in it.INDICES:
            raise ImageryError(f"unknown view {out['view']!r}; choose from {list(it.COMPOSITES) + list(it.INDICES)}")
        try:
            out["days"] = int(out["days"])
            out["q"] = int(out["q"])
        except (TypeError, ValueError):
            raise ImageryError("days and q must be whole numbers") from None
        if not 5 <= out["days"] <= 1100:
            raise ImageryError("days must be between 5 and 1100")
        if not 1 <= out["q"] <= 50:
            raise ImageryError("q (the percentile of the clear-sky layer) must be between 1 and 50")
        b = out.get("backend")
        if b not in self.backends:
            raise ImageryError(f"unknown backend {b!r}; choose from {list(self.backends)}")
        box = out.get("box_km")
        top = max_box or core.CFG["max_box_km"]
        if box is None or not core.CFG["min_box_km"] <= float(box) <= top:
            raise ImageryError(f"box_km must be between {core.CFG['min_box_km']} and {top}")
        out["box_km"] = float(box)
        return out

    def key(self, site_id, lat, lon, p):
        return "_".join([site_token(site_id), f"{lat:.5f}", f"{lon:.5f}", f"{p['box_km']:.2f}", p["backend"], p["source"],
                         str(p["days"]), f"q{p['q']}" if p["source"] == "clearsky" else "q0"])

    def paths(self, key):
        base = os.path.join(self.cache_dir, key)
        return base + ".tif", base + ".json", base + "_donor.tif"

    def png_path(self, key, p):
        return os.path.join(self.cache_dir, f"{key}__{p['view']}__{p['stretch']}__{p['fill']}.png")

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    # ---------------------------------------------------------------- chips

    def cached(self, site_id, lat, lon, p):
        tif, meta, _ = self.paths(self.key(site_id, lat, lon, p))
        return os.path.exists(tif) and os.path.exists(meta)

    def _fetch_to(self, site_id, lat, lon, p, tif, rank=1):
        bk = self.backends[p["backend"]]
        ok, why = bk.available()
        if not ok and p["backend"] != "ee":
            raise B.BackendError(why)
        args = dict(site_key=site_id, lat=lat, lon=lon, box_km=p["box_km"], source=p["source"], days=p["days"], q=p["q"], rank=rank)
        if p["backend"] == "ee":
            meta = bk.fetch(dst=tif, **args)
            return meta
        chip, meta = bk.fetch(**args)
        it.save_chip(chip, tif)
        return meta

    def get_chip(self, site_id, lat, lon, p, force=False):
        """The cached chip for these parameters, fetching it first when needed (or when ``force``)."""
        key = self.key(site_id, lat, lon, p)
        tif, metap, _ = self.paths(key)
        with self._lock(key):
            if force or not (os.path.exists(tif) and os.path.exists(metap)):
                for stale in glob.glob(os.path.join(self.cache_dir, key + "__*.png")):
                    _remove(stale)
                _remove(tif.replace(".tif", "_donor.tif"))
                tmp = tif + ".part"
                meta = self._fetch_to(site_id, lat, lon, p, tmp)
                if os.path.exists(tmp) and not tmp == tif:
                    os.replace(tmp, tif)
                meta = {**meta, "site_id": site_id, "lat": lat, "lon": lon, "box_km": p["box_km"], "key": key,
                        "fetched_at": datetime.now(timezone.utc).isoformat()}
                with open(metap, "w", encoding="utf-8") as f:
                    json.dump(meta, f)
                self.prune(self.max_mb)
            else:
                with open(metap, "r", encoding="utf-8") as f:
                    meta = json.load(f)
        try:
            chip = it.load_chip(tif)
        except Exception as e:
            _remove(tif)
            _remove(metap)
            raise ImageryError(f"The saved image was damaged and has been removed. Fetch it again. ({type(e).__name__})") from e
        return chip, meta, key

    def get_donor(self, site_id, lat, lon, p):
        """A second, different scene of the same place, used to repair gaps. Cached next to the chip."""
        key = self.key(site_id, lat, lon, p)
        donor_tif = self.paths(key)[2]
        with self._lock(key + "_donor"):
            if not os.path.exists(donor_tif):
                q = dict(p, source="single")
                tmp = donor_tif + ".part"
                self._fetch_to(site_id, lat, lon, q, tmp, rank=2)
                if os.path.exists(tmp):
                    os.replace(tmp, donor_tif)
        return it.load_chip(donor_tif)

    # ---------------------------------------------------------------- products

    def prepared(self, site_id, lat, lon, p, force=False):
        """Chip after the chosen fill, with its metadata and the fill report."""
        chip, meta, key = self.get_chip(site_id, lat, lon, p, force)
        report = {"method": "none", "gap_pixels": int(it.nodata_mask(chip).sum())}
        if p["fill"] == "mean":
            chip, info = it.fill_mean(chip)
            report = {**info, "gap_pixels": report["gap_pixels"]}
        elif p["fill"] == "nearest":
            donor = self.get_donor(site_id, lat, lon, p)
            chip, steps = it.fill_gaps(chip, donor)
            report = {"method": "nearest", **steps}
        return chip, meta, key, report

    def render(self, site_id, lat, lon, p, force=False):
        """PNG path and metadata for the picture. Rendering is cached per view, stretch and fill."""
        chip, meta, key, report = self.prepared(site_id, lat, lon, p, force)
        path = self.png_path(key, p)
        if force or not os.path.exists(path):
            it.save_png(it.render_view(chip, p["view"], p["stretch"]), path)
        info = {**meta, "view": p["view"], "stretch": p["stretch"], "fill": report,
                "valid_share": it.valid_share(chip), "cloud_share": it.cloud_share(chip)}
        return path, info

    def statistics(self, site_id, lat, lon, p, indices, clear_only):
        chip, meta, _key, report = self.prepared(site_id, lat, lon, p)
        for n in indices:
            if n not in it.INDICES:
                raise ImageryError(f"unknown index {n!r}")
        out = it.chip_statistics(chip, indices, clear_only)
        out["meta"] = meta
        out["fill"] = report
        out["reading"] = reading(out)
        return out

    def candidates(self, site_id, lat, lon, p, kind, percentile, threshold, min_pixels):
        chip, meta, _key, _r = self.prepared(site_id, lat, lon, p)
        if kind not in it.MASK_KINDS:
            raise ImageryError(f"unknown kind {kind!r}; choose from {list(it.MASK_KINDS)}")
        if not 50 <= percentile <= 99.9:
            raise ImageryError("percentile must be between 50 and 99.9")
        res = it.candidate_areas(chip, kind, threshold, percentile, min_pixels)
        res["meta"] = meta
        return res

    def gapfill_test(self, site_id, lat, lon, p):
        chip, meta, _key = self.get_chip(site_id, lat, lon, p)
        try:
            donor = self.get_donor(site_id, lat, lon, p)
        except Exception:
            donor = None
        res = it.masking_experiment(chip, donor)
        res["donor_available"] = donor is not None
        res["meta"] = meta
        return res

    # ---------------------------------------------------------------- housekeeping

    def prune(self, max_mb=500):
        """Delete the oldest cached files until the cache is under ``max_mb``. Returns the number of files removed."""
        files = [(os.path.getmtime(f), os.path.getsize(f), f) for f in glob.glob(os.path.join(self.cache_dir, "*"))
                 if os.path.isfile(f)]
        total = sum(s for _m, s, _f in files)
        removed = 0
        for _m, s, f in sorted(files):
            if total <= max_mb * 1024 * 1024:
                break
            _remove(f)
            total -= s
            removed += 1
        return removed


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def reading(stats):
    """Plain-word reading of the statistics, one sentence per point."""
    out = []
    v, c, cl = stats["valid_share"], stats["clear_share"], stats["cloud_share"]
    out.append(f"{v * 100:.0f}% of the box has data." + ("" if v > 0.97 else " Some of it is empty (no data): consider the gap fill."))
    if cl == cl:                                             # not NaN
        out.append(f"{cl * 100:.0f}% of the pixels with data are cloud or cloud shadow."
                   + (" The picture is mostly obscured." if cl > 0.5 else ""))
    nd = stats["indices"].get("ndvi")
    if nd and nd["mean"] is not None:
        m = nd["mean"]
        out.append("Mean NDVI is " + f"{m:.2f}: " + ("mostly bare or built-up ground." if m < 0.15 else
                                                    "some vegetation." if m < 0.4 else "mostly vegetation."))
    nw = stats["indices"].get("ndwi")
    if nw and nw["mean"] is not None and nw["p95"] is not None:
        out.append("Part of the box looks like water." if nw["p95"] > 0.3 else "No obvious open water in the box.")
    ab = stats["indices"].get("aero_b1b2")
    if ab and ab["mean"] is not None:
        out.append("The coastal-blue contrast is " + f"{ab['mean']:.2f}; higher values mean hazier air than in a clear scene of the same place.")
    return out
