"""Where the imagery comes from.

Three backends give the curator scenes and composites in the same 14-layer chip layout:

* ``demo``: synthetic scenes drawn from simple rules. Always available. **Not real imagery.**
* ``ee``: Google Earth Engine (needs an account and a key).
* ``pc``: Microsoft Planetary Computer through its public STAC API (no account; a short-lived read token is
  requested automatically). Its approach (STAC search, then a cloudless median of clear observations) follows
  the open-source ``solafune-tools`` package (MIT licence, Solafune Inc.); this tool does not import it, so
  there are fewer dependencies and each step can be tested.

Each backend returns ``(Chip, meta)``. ``meta`` always says which backend, which kind of source, the date or
date range, the number of scenes and whether the data are synthetic. Network and Earth Engine code is written
so that it can be tested with stand-ins: both take the clients they use as arguments.
"""
import math
import os
from datetime import datetime, timedelta, timezone

import numpy as np

import core
import demo_scene
import imagery_tools as it

SOURCES = {
    "single": "The clearest single scene in the look-back period",
    "median": "Cloudless median: the middle value of the clear observations at each pixel",
    "clearsky": "Clear-sky layer: a low percentile of the clear observations, which shows the surface beneath cloud and thin haze",
}


class BackendError(RuntimeError):
    """Raised with a message a person can act on."""


def _today():
    return datetime.now(timezone.utc).date()


def _meta(backend, source, **kw):
    m = {"backend": backend, "source": source, "synthetic": backend == "demo",
         "fetched_at": datetime.now(timezone.utc).isoformat()}
    m.update(kw)
    return m


# --------------------------------------------------------------------------------------------------------
# targets (satellite gas columns), used by the placement study
# --------------------------------------------------------------------------------------------------------

TARGETS = {
    "no2": {"collection": "COPERNICUS/S5P/OFFL/L3_NO2", "band": "tropospheric_NO2_column_number_density", "scale": 1e6, "unit": "umol/m2",
            "label": "Nitrogen dioxide column"},
    "co": {"collection": "COPERNICUS/S5P/OFFL/L3_CO", "band": "CO_column_number_density", "scale": 1e3, "unit": "mmol/m2",
           "label": "Carbon monoxide column"},
    "ch4": {"collection": "COPERNICUS/S5P/OFFL/L3_CH4", "band": "CH4_column_volume_mixing_ratio_dry_air_bias_corrected", "scale": 1.0, "unit": "ppb",
            "label": "Methane column"},
    "aai": {"collection": "COPERNICUS/S5P/OFFL/L3_AER_AI", "band": "absorbing_aerosol_index", "scale": 1.0, "unit": "index",
            "label": "Absorbing aerosol index"},
}
S5P_SCALE_M = 1113.2
RING_KM = (30.0, 75.0)


def _positions_ok(positions):
    if not positions or len(positions) > 400:
        raise BackendError("between 1 and 400 positions are allowed")
    return [(float(a), float(b)) for a, b in positions]


# --------------------------------------------------------------------------------------------------------
# demo
# --------------------------------------------------------------------------------------------------------

class DemoBackend:
    name = "demo"
    label = "Demo (synthetic scenes, not real imagery)"

    def __init__(self, size=192):
        self.size = size
        self._memo = {}

    def available(self):
        return True, "Always available. The scenes are synthetic."

    def _series(self, site_key, lat, lon, box_km, n=8):
        """The synthetic scenes of a place, built once per place and handed out as copies."""
        key = (site_key, round(lat, 5), round(lon, 5), box_km, self.size, n)
        if key not in self._memo:
            if len(self._memo) > 12:
                self._memo.clear()
            self._memo[key] = demo_scene.synthetic_series(site_key, n=n, size=self.size, lat=lat, lon=lon, box_km=box_km)
        return [(c.copy(), t) for c, t in self._memo[key]]

    def target_windows(self, site_key, positions, window_km, targets, start=None, end=None, **_):
        """Synthetic target values: a smooth regional level plus a bump over the first position (the facility), so the demo
        shows the effect the study measures. Not real data."""
        pos = _positions_ok(positions)
        rng = np.random.default_rng(demo_scene.seed_from(site_key, "targets"))
        out_control, shifted = {}, []
        lat0, lon0 = pos[0]
        for t in targets:
            if t not in TARGETS:
                raise BackendError(f"unknown target {t!r}; choose from {list(TARGETS)}")
            level, amp, spread = {"no2": (20.0, 25.0, 4.0), "co": (1.0, 1.5, 6.0), "ch4": (1900.0, 12.0, 10.0), "aai": (0.0, 0.8, 8.0)}[t]
            sd = max(abs(level) * 0.15, 0.1 * amp)
            n = 120
            def value(lat, lon):
                d = math.hypot((lat - lat0) * 111.32, (lon - lon0) * 111.32 * math.cos(math.radians(lat0)))
                return amp * math.exp(-(d / spread) ** 2)
            out_control[t] = {"mean": value(lat0, lon0), "sd": sd, "n": n}
            for i, (la, lo) in enumerate(pos[1:]):
                if len(shifted) <= i:
                    shifted.append({"values": {}})
                shifted[i]["values"][t] = value(la, lo) + float(rng.normal(0, sd / math.sqrt(n)))
        return {"control": out_control, "shifted": shifted, "synthetic": True, "window_km": window_km}

    def fetch(self, site_key, lat, lon, box_km, source="single", days=120, q=20, rank=1, **_):
        series = self._series(f"{site_key}|{round(lat, 3)}|{round(lon, 3)}", lat, lon, box_km)
        if source == "single":
            order = sorted(range(len(series)), key=lambda i: it.cloud_share(series[i][0]) + (1 - it.valid_share(series[i][0])))
            i = order[min(rank - 1, len(order) - 1)]
            chip = series[i][0]
            when = (_today() - timedelta(days=series[i][0].meta["days_ago"])).isoformat()
            return chip, _meta("demo", source, date=when, n_scenes=1, cloud_frac=it.cloud_share(chip),
                               gsd_m=chip.gsd_m, box_km=box_km)
        chips = [c for c, _t in series if c.meta["days_ago"] <= max(days, 5)] or [series[0][0]]
        comp, info = it.composite(chips, "median" if source == "median" else "clearsky", q=q)
        start = (_today() - timedelta(days=days)).isoformat()
        return comp, _meta("demo", source, date=f"{start} to {_today().isoformat()}", n_scenes=len(chips),
                           observed_share=info["observed_share"], cloud_frac=it.cloud_share(comp), gsd_m=comp.gsd_m,
                           box_km=box_km, q=q if source == "clearsky" else None)


# --------------------------------------------------------------------------------------------------------
# Earth Engine
# --------------------------------------------------------------------------------------------------------

class EarthEngineBackend:
    """Earth Engine. ``ee_module`` and ``downloader`` can be replaced in tests."""
    name = "ee"
    label = "Earth Engine"

    def __init__(self, ee_module=None, downloader=None, ready=lambda: False, error=lambda: ""):
        self._ee = ee_module
        self._download = downloader or core.download_ee_geotiff
        self._ready, self._error = ready, error

    @property
    def ee(self):
        return self._ee if self._ee is not None else core.ee

    def available(self):
        if self._ready():
            return True, "Earth Engine is ready."
        return False, self._error() or "Earth Engine is not set up (no credentials). See docs/BACKENDS.md."

    def _composite_image(self, grid, start, end, source, q):
        """Server-side image in the chip layout for a composite over the date range."""
        ee = self.ee
        joined = core.s2_joined(grid["geom"], start, end)
        thr = core.CFG["cloud_prob_thresh"]
        cloudy = list(core.SCL_CLOUDY)

        def clear_only(img):
            img = ee.Image(img)
            scl = img.select("SCL")
            ok = img.select("CLDPRB").lt(thr)
            for c in cloudy:
                ok = ok.And(scl.neq(c))
            return img.select(core.S2_BANDS).updateMask(ok).copyProperties(img, ["system:time_start"])

        masked = joined.map(clear_only)
        if source == "median":
            comp = masked.median()
        else:
            comp = masked.reduce(ee.Reducer.percentile([q])).rename(core.S2_BANDS)
        observed = masked.select("B2").count().gt(0)
        scl = ee.Image.constant(4).updateMask(observed).unmask(0).rename("SCL")
        # 100 where no scene was ever clear, 0 elsewhere (same meaning as in the local composite)
        cldprb = ee.Image.constant(100).updateMask(observed.Not()).unmask(0).rename("CLDPRB")
        return comp.addBands(scl).addBands(cldprb).select(core.CHIP_BANDS).unmask(0).toUint16(), joined

    def target_windows(self, site_key, positions, window_km, targets, start=None, end=None, **_):
        """Enhancement of each target (window mean minus the mean of a 30 to 75 km background ring) at every position.

        One server-side call per target covers all positions on the long-term mean image; the day-to-day spread of the
        window mean is taken once, at the first position (the original one).
        """
        if not self._ready():
            raise BackendError(self.available()[1])
        pos = _positions_ok(positions)
        ee = self.ee
        end_d = end or _today().isoformat()
        start_d = start or (datetime.fromisoformat(end_d) - timedelta(days=365)).date().isoformat()
        windows, rings = [], []
        for la, lo in pos:
            p = ee.Geometry.Point([lo, la])
            windows.append(p.buffer(window_km * 500.0).bounds())
            rings.append(p.buffer(RING_KM[1] * 1000.0).difference(p.buffer(RING_KM[0] * 1000.0)))
        out_control, shifted = {}, [{"values": {}} for _ in pos[1:]]
        for t in targets:
            if t not in TARGETS:
                raise BackendError(f"unknown target {t!r}; choose from {list(TARGETS)}")
            spec = TARGETS[t]
            col = ee.ImageCollection(spec["collection"]).filterDate(start_d, end_d).select(spec["band"])
            mean_img = col.mean()
            def region_means(geoms):
                fc = ee.FeatureCollection([ee.Feature(g, {"i": i}) for i, g in enumerate(geoms)])
                res = mean_img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=S5P_SCALE_M).getInfo()
                vals = {f["properties"]["i"]: f["properties"].get("mean") for f in res["features"]}
                return [vals.get(i) for i in range(len(geoms))]
            wm = core.with_retry(lambda: region_means(windows), f"{site_key} {t} windows")
            rm = core.with_retry(lambda: region_means(rings), f"{site_key} {t} rings")
            enh = [None if (a is None or b is None) else (a - b) * spec["scale"] for a, b in zip(wm, rm)]
            def daily():
                feats = col.map(lambda img: ee.Feature(None, {"v": ee.Image(img).reduceRegion(ee.Reducer.mean(), windows[0], S5P_SCALE_M).get(spec["band"])}))
                return ee.FeatureCollection(feats).aggregate_array("v").getInfo()
            series = [v for v in core.with_retry(daily, f"{site_key} {t} daily") if v is not None]
            sd = float(np.std(np.asarray(series) * spec["scale"], ddof=1)) if len(series) > 2 else None
            out_control[t] = {"mean": enh[0], "sd": sd, "n": len(series), "unit": spec["unit"]}
            for i, v in enumerate(enh[1:]):
                shifted[i]["values"][t] = v
        return {"control": out_control, "shifted": shifted, "synthetic": False, "window_km": window_km, "start": start_d, "end": end_d}

    def fetch(self, site_key, lat, lon, box_km, source="single", days=None, q=20, rank=1, dst=None, **_):
        if not self._ready():
            raise BackendError(self.available()[1])
        if dst is None:
            raise BackendError("internal: no destination file")
        days = days or core.CFG["preview_lookback_days"]
        end = _today()
        start = end - timedelta(days=days)
        grid = core.chip_grid(lat, lon, box_km)
        ee = self.ee
        if source == "single":
            joined = core.s2_joined(grid["geom"], start.isoformat(), end.isoformat())
            sel = core.with_retry(lambda: core.select_best_scene(joined, grid, rank).getInfo(), f"{site_key} select scene")
            best = sel.get("best") if sel else None
            if not best:
                raise BackendError(f"No usable Sentinel-2 scene in the last {days} days for this box. Try a longer period.")
            day_col = core.build_day_col(joined, best["date"], best["orbit"])
            image = day_col.mosaic().select(core.CHIP_BANDS).unmask(0).toUint16()
            meta = _meta("ee", source, date=best["date"], cloud_frac=best.get("aoi_cloud_frac"), n_scenes=1,
                         gsd_m=round(grid["gsd"], 2), box_km=box_km)
        elif source in ("median", "clearsky"):
            image, joined = self._composite_image(grid, start.isoformat(), end.isoformat(), source, q)
            n = core.with_retry(lambda: joined.size().getInfo(), f"{site_key} count scenes")
            if not n:
                raise BackendError(f"No Sentinel-2 scenes in the last {days} days for this box. Try a longer period.")
            meta = _meta("ee", source, date=f"{start.isoformat()} to {end.isoformat()}", n_scenes=int(n),
                         gsd_m=round(grid["gsd"], 2), box_km=box_km, q=q if source == "clearsky" else None)
        else:
            raise BackendError(f"unknown source {source!r}; choose from {list(SOURCES)}")
        self._download(image, dst, f"{site_key} imagery {source}", grid["crs"], grid["transform"], grid["dims"])
        return meta


# --------------------------------------------------------------------------------------------------------
# Planetary Computer (keyless)
# --------------------------------------------------------------------------------------------------------

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
PC_BANDS = {"B1": "B01", "B2": "B02", "B3": "B03", "B4": "B04", "B5": "B05", "B6": "B06", "B7": "B07", "B8": "B08",
            "B8A": "B8A", "B9": "B09", "B11": "B11", "B12": "B12"}
SCL_TO_CLOUD_PROB = {3: 80, 8: 100, 9: 100, 10: 60}       # no s2cloudless on this backend: classes stand in for it


def reflectance_offset(properties):
    """Digital-number offset to remove: 1000 for processing baseline 04.00 and later (from 25 January 2022), else 0.

    Matches how Earth Engine's harmonized collection treats the same files, so chips from both backends agree.
    """
    pb = str(properties.get("s2:processing_baseline", "")).strip()
    try:
        return 1000 if float(pb) >= 4.0 else 0
    except ValueError:
        return 0


def read_window(href, grid, nodata=0):
    """Read one raster of a scene onto the chip grid (nearest neighbour). Needs network access."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.vrt import WarpedVRT

    t = Affine(*grid["transform"][:6])
    with rasterio.open(href) as src:
        with WarpedVRT(src, crs=grid["crs"], transform=t, width=grid["dims"][0], height=grid["dims"][1],
                       resampling=Resampling.nearest, nodata=nodata) as vrt:
            return vrt.read(1)


class PlanetaryComputerBackend:
    """Planetary Computer through STAC. ``http`` is a requests-like object; ``reader`` reads a signed raster
    onto the chip grid (both replaced in tests)."""
    name = "pc"
    label = "Planetary Computer (no account)"

    def __init__(self, http=None, reader=read_window, max_cloud=60, max_scenes=12):
        self._http = http
        self._reader = reader
        self.max_cloud = max_cloud
        self.max_scenes = max_scenes
        self._token = None

    @property
    def http(self):
        if self._http is None:
            import requests
            self._http = requests
        return self._http

    def target_windows(self, *a, **k):
        raise BackendError("Gas targets need the Earth Engine backend (or the demo backend for a synthetic example).")

    def available(self):
        last = None
        for _attempt in range(2):                     # the service can be slow to answer the first time (seen live: a 8 s timeout, then a fetch that worked)
            try:
                r = self.http.get(PC_STAC, timeout=25)
                if getattr(r, "status_code", 200) != 200:
                    return False, f"Planetary Computer answered {r.status_code}."
                return True, "Planetary Computer is reachable (no account needed)."
            except Exception as e:
                last = e
        return False, f"Planetary Computer is not reachable: {type(last).__name__}. Check the internet connection, then try again."

    def _sign(self, href):
        if self._token is None:
            r = self.http.get(PC_TOKEN, timeout=20)
            if r.status_code != 200:
                raise BackendError(f"Could not get a read token from Planetary Computer ({r.status_code}).")
            self._token = r.json()["token"]
        return href + ("&" if "?" in href else "?") + self._token

    def search(self, lat, lon, box_km, start, end):
        """STAC items over the box, least cloudy first."""
        half = box_km / 2 * 1.2
        dlat = half / 111.32
        dlon = half / (111.32 * max(math.cos(math.radians(lat)), 0.05))
        body = {"collections": ["sentinel-2-l2a"], "bbox": [lon - dlon, lat - dlat, lon + dlon, lat + dlat],
                "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100,
                "query": {"eo:cloud_cover": {"lt": self.max_cloud}}}
        r = self.http.post(f"{PC_STAC}/search", json=body, timeout=40)
        if r.status_code != 200:
            raise BackendError(f"Planetary Computer search failed ({r.status_code}).")
        items = r.json().get("features", [])
        items.sort(key=lambda f: f["properties"].get("eo:cloud_cover", 100))
        return items

    def _chip_from_items(self, items, grid):
        """Mosaic the items of one date into a chip (first non-empty value wins)."""
        h, w = grid["dims"][1], grid["dims"][0]
        refl = np.zeros((len(core.S2_BANDS), h, w), "float32")
        scl = np.zeros((h, w), "uint8")
        filled = np.zeros((h, w), bool)
        for item in items:
            off = reflectance_offset(item["properties"])
            sc = self._reader(self._sign(item["assets"]["SCL"]["href"]), grid)
            take = ~filled & (sc > 0)
            if not take.any():
                continue
            for i, b in enumerate(core.S2_BANDS):
                dn = self._reader(self._sign(item["assets"][PC_BANDS[b]]["href"]), grid).astype("float32")
                refl[i][take] = np.clip(dn[take] - off, 0, None) * it.SCALE
            scl[take] = sc[take]
            filled |= take
        cldprb = np.zeros((h, w), "float32")
        for cls, p in SCL_TO_CLOUD_PROB.items():
            cldprb[scl == cls] = p
        chip = it.Chip({b: refl[i] for i, b in enumerate(core.S2_BANDS)}, scl, cldprb, grid["transform"], grid["crs"])
        return chip

    def fetch(self, site_key, lat, lon, box_km, source="single", days=None, q=20, rank=1, **_):
        days = days or core.CFG["preview_lookback_days"]
        end = _today()
        start = end - timedelta(days=days)
        grid = core.chip_grid_math(lat, lon, box_km)
        try:
            items = self.search(lat, lon, box_km, start.isoformat(), end.isoformat())
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(f"Planetary Computer is not reachable ({type(e).__name__}). Check the internet connection.") from e
        if not items:
            raise BackendError(f"No Sentinel-2 scenes found in the last {days} days. Try a longer period or a higher cloud limit.")
        by_date = {}
        for f in items:
            by_date.setdefault(f["properties"]["datetime"][:10], []).append(f)
        dates = sorted(by_date, key=lambda d: min(x["properties"].get("eo:cloud_cover", 100) for x in by_date[d]))
        if source == "single":
            d = dates[min(rank - 1, len(dates) - 1)]
            chip = self._chip_from_items(by_date[d], grid)
            return chip, _meta("pc", source, date=d, n_scenes=1, cloud_frac=it.cloud_share(chip),
                               gsd_m=round(grid["gsd"], 2), box_km=box_km)
        if source not in ("median", "clearsky"):
            raise BackendError(f"unknown source {source!r}; choose from {list(SOURCES)}")
        chosen = dates[: self.max_scenes]
        chips = [self._chip_from_items(by_date[d], grid) for d in chosen]
        comp, info = it.composite(chips, "median" if source == "median" else "clearsky", q=q)
        return comp, _meta("pc", source, date=f"{start.isoformat()} to {end.isoformat()}", n_scenes=len(chips),
                           observed_share=info["observed_share"], cloud_frac=it.cloud_share(comp),
                           gsd_m=round(grid["gsd"], 2), box_km=box_km, q=q if source == "clearsky" else None)


def registry(ee_ready=lambda: False, ee_error=lambda: ""):
    """The backends the server offers, by name."""
    return {"demo": DemoBackend(), "ee": EarthEngineBackend(ready=ee_ready, error=ee_error), "pc": PlanetaryComputerBackend()}
