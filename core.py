"""Settings, geometry and Earth Engine helpers for TrigPoint.

Everything the curator needs from the outside lives here, so the tool runs on its own: no other project
has to be installed. Earth Engine is optional and imported only when it is used.

The chip grid follows the convention of the OBSCURA-Open-25 chips: a square box in the local UTM zone,
snapped to whole pixels, with a fixed number of pixels (default 384) so every site has the same array size.
"""
import json
import logging
import math
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone

LOG = logging.getLogger("site_curator")

CFG = {
    "chip_px": 384,              # pixels per side of every chip
    "min_box_km": 1.0,
    "max_box_km": 8.0,
    "label_box_km": 10.0,        # fixed window the gas targets are averaged over
    "bg_inner_km": 30.0,         # background ring
    "bg_outer_km": 75.0,
    "min_split_distance_km": 150.0,
    "cloud_prob_thresh": 40,     # s2cloudless probability at or above this counts as cloud
    "max_cloud_frac": 0.30,
    "preview_lookback_days": 120,
    "s2_scale_m": 20,
    "window_days": 5,
}

S2_BANDS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"]
CHIP_BANDS = S2_BANDS + ["SCL", "CLDPRB"]      # the 14 layers of a chip, in this order

# Named three-band composites for the preview. Every band is already inside a chip.
BAND_VIEWS = {
    "true_color": ("B4", "B3", "B2"),
    "false_color_ir": ("B8", "B4", "B3"),
    "swir": ("B12", "B11", "B4"),
    "agriculture": ("B11", "B8", "B2"),
}

S2_ID = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD_ID = "COPERNICUS/S2_CLOUD_PROBABILITY"
S5P_ID = "COPERNICUS/S5P/OFFL/L3_CH4"
S5P_NO2_ID = "COPERNICUS/S5P/OFFL/L3_NO2"
S5P_CO_ID = "COPERNICUS/S5P/OFFL/L3_CO"
S5P_AAI_ID = "COPERNICUS/S5P/OFFL/L3_AER_AI"
FIRMS_ID = "FIRMS"
ERA5L_DAILY_ID = "ECMWF/ERA5_LAND/DAILY_AGGR"
ERA5L_HOURLY_ID = "ECMWF/ERA5_LAND/HOURLY"

# Scene classification classes that are not clear ground: cloud shadow, cloud (medium and high), thin cirrus
SCL_CLOUDY = (3, 8, 9, 10)


def __getattr__(name):
    """``core.ee`` imports the Earth Engine client the first time it is touched."""
    if name == "ee":
        import ee
        return ee
    raise AttributeError(name)


def date_range_default():
    """The default window for coverage checks: from 1 January 2022 to today."""
    return "2022-01-01", datetime.now(timezone.utc).date().isoformat()


def generate_windows(start=None, end=None, days=None):
    """Start dates of consecutive windows of ``days`` days (default 5)."""
    d0 = datetime.strptime(start or date_range_default()[0], "%Y-%m-%d")
    d1 = datetime.strptime(end or date_range_default()[1], "%Y-%m-%d")
    step = timedelta(days=days or CFG["window_days"])
    out = []
    while d0 + step <= d1:
        out.append(d0.strftime("%Y-%m-%d"))
        d0 += step
    return out


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def utm_epsg(lat, lon):
    zone = int((lon + 180.0) // 6.0) + 1
    return (32600 if lat >= 0 else 32700) + zone


def chip_grid_math(lat, lon, box_km, chip_px=None):
    """The pixel grid of a chip, without Earth Engine.

    Returns the EPSG code, the affine transform as a six-number list, the pixel size and the corner
    coordinates in UTM. Matches the grid the OBSCURA-Open-25 chips were exported on (apart from the small random
    offset those chips carry).
    """
    from rasterio.warp import transform as warp_transform

    px = chip_px or CFG["chip_px"]
    epsg = utm_epsg(lat, lon)
    crs = f"EPSG:{epsg}"
    xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
    size = box_km * 1000.0
    gsd = size / px
    half = size / 2.0
    x0 = math.floor((xs[0] - half) / gsd) * gsd
    y1 = math.ceil((ys[0] + half) / gsd) * gsd
    return {"epsg": epsg, "crs": crs, "transform": [gsd, 0, x0, 0, -gsd, y1], "dims": [px, px],
            "box_km": box_km, "gsd": gsd, "bounds_utm": [x0, y1 - size, x0 + size, y1]}


def chip_grid(lat, lon, box_km):
    """Like :func:`chip_grid_math` plus an Earth Engine rectangle under the key ``geom``."""
    g = chip_grid_math(lat, lon, box_km)
    x0, y0, x1, y1 = g["bounds_utm"]
    g["geom"] = __getattr__("ee").Geometry.Rectangle([x0, y0, x1, y1], g["crs"], False)
    return g


def with_retry(fn, desc, tries=4, base_sleep=5.0, sleep=time.sleep):
    """Run ``fn``; retry transient failures with exponential backoff and jitter."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if attempt == tries:
                raise
            wait = base_sleep * (2 ** (attempt - 1)) * (1.0 + 0.5 * random.random())
            LOG.warning("RETRY | %s | attempt %d/%d: %s: %s | sleep %.0fs", desc, attempt, tries, type(e).__name__, e, wait)
            sleep(wait)


def init_earth_engine():
    """Start Earth Engine with a service-account key (EE_SERVICE_ACCOUNT_JSON or EE_SERVICE_ACCOUNT_KEY_FILE)
    or the credentials of ``earthengine authenticate``. Raises when neither works."""
    import ee

    key_json = os.environ.get("EE_SERVICE_ACCOUNT_JSON")
    key_file = os.environ.get("EE_SERVICE_ACCOUNT_KEY_FILE")
    if not key_json and key_file and os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as f:
            key_json = f.read()
    if key_json:
        info = json.loads(key_json)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=key_json)
        project = info.get("project_id") or os.environ.get("EE_PROJECT")
        ee.Initialize(creds, project=project) if project else ee.Initialize(creds)
    else:
        project = os.environ.get("EE_PROJECT")
        ee.Initialize(project=project) if project else ee.Initialize()
    ee.data.setDeadline(120000)


def s2_joined(geom, start, end):
    """Sentinel-2 surface reflectance scenes with the s2cloudless probability attached as band CLDPRB."""
    ee = __getattr__("ee")
    s2 = ee.ImageCollection(S2_ID).filterBounds(geom).filterDate(start, end)
    prob = ee.ImageCollection(S2_CLOUD_ID).filterBounds(geom).filterDate(start, end)
    joined = ee.ImageCollection(ee.Join.saveFirst("cloud_prob").apply(
        s2, prob, ee.Filter.equals(leftField="system:index", rightField="system:index")))

    def attach(img):
        img = ee.Image(img)
        p = ee.Image(img.get("cloud_prob")).select(["probability"], ["CLDPRB"])
        return img.addBands(p)

    return joined.map(attach)


def select_best_scene(joined, grid, rank=1):
    """The rank-th least cloudy scene over the box (rank 1 is the clearest), as an Earth Engine dictionary."""
    ee = __getattr__("ee")

    def score(img):
        img = ee.Image(img)
        cf = (img.select("CLDPRB").gte(CFG["cloud_prob_thresh"])
              .reduceRegion(reducer=ee.Reducer.mean(), geometry=grid["geom"], scale=60, maxPixels=1e8)
              .get("CLDPRB"))
        return img.set("aoi_cloud_frac", cf)

    cand = ee.ImageCollection(joined.map(score)).filter(ee.Filter.notNull(["aoi_cloud_frac"])).sort("aoi_cloud_frac")
    best = ee.Image(cand.toList(rank).get(rank - 1))
    return ee.Dictionary({
        "n_candidates": cand.size(),
        "best": ee.Algorithms.If(cand.size().gte(rank), ee.Dictionary({
            "date": best.date().format("YYYY-MM-dd"),
            "orbit": best.get("SENSING_ORBIT_NUMBER"),
            "aoi_cloud_frac": best.get("aoi_cloud_frac")}), None),
    })


def build_day_col(joined, date_str, orbit):
    """All granules of one date and orbit, so tile seams are covered when mosaicked."""
    ee = __getattr__("ee")
    day = ee.Date(date_str)
    return joined.filter(ee.Filter.eq("SENSING_ORBIT_NUMBER", orbit)).filterDate(day, day.advance(1, "day"))


def download_ee_geotiff(image, dst, desc, crs, crs_transform, dims):
    """Download an Earth Engine image as a GeoTIFF on the given grid, atomically."""
    import requests

    params = {"format": "GEO_TIFF", "crs": crs, "crs_transform": crs_transform, "dimensions": f"{dims[0]}x{dims[1]}"}

    def go():
        url = image.getDownloadURL(params)
        r = requests.get(url, timeout=600)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(r.content)
        os.replace(tmp, dst)

    with_retry(go, desc)


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "site"
