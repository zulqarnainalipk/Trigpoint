"""Synthetic Sentinel-2-like scenes for the demo backend and for tests.

**These are not real images.** They are drawn from simple rules (water, fields, a facility with a flare, clouds,
haze, a no-data strip) so that every imagery feature of the curator can be tried without an account, and so that
tests have known answers. The curator labels everything made here "synthetic" wherever it is shown.
"""
import hashlib

import numpy as np

import core
import imagery_tools as it

# typical surface reflectance (0..1) per band: B1 B2 B3 B4 B5 B6 B7 B8 B8A B9 B11 B12
_SURFACES = {
    "desert": [0.16, 0.18, 0.22, 0.27, 0.29, 0.31, 0.32, 0.33, 0.33, 0.33, 0.42, 0.37],
    "field": [0.03, 0.04, 0.07, 0.04, 0.10, 0.30, 0.38, 0.42, 0.43, 0.43, 0.22, 0.10],
    "water": [0.06, 0.06, 0.05, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.01, 0.01],
    "facility": [0.20, 0.22, 0.25, 0.28, 0.29, 0.30, 0.31, 0.31, 0.31, 0.31, 0.48, 0.45],
    "flare": [0.20, 0.22, 0.26, 0.32, 0.38, 0.45, 0.55, 0.70, 0.72, 0.60, 0.90, 1.20],
    "cloud": [0.55, 0.58, 0.60, 0.62, 0.63, 0.63, 0.63, 0.64, 0.64, 0.62, 0.50, 0.42],
}
_ORDER = core.S2_BANDS


def seed_from(*parts):
    """A stable integer seed from any values (the same input gives the same scene on every machine)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)


def _blob(shape, rng, centre, radius):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(yy - centre[0], xx - centre[1]) / radius
    return (1.0 - (d + rng.normal(0, 0.05, shape)) / 1.35) > 0.15


def ground(seed=0, size=128, with_facility=True, with_flare=True):
    """The ground without weather: reflectance (12, H, W), scene classes, and the truth masks.

    The layout (coast, fields, facility block, flare) changes with the seed, so different sites look different; the facility
    always stays near the middle, like a well-centred box.
    """
    rng = np.random.default_rng(seed)
    h = w = size
    yy, xx = np.mgrid[0:h, 0:w]
    refl = np.array(_SURFACES["desert"], "float32")[:, None, None] * np.ones((1, h, w), "float32")
    # coast: a straight shoreline at a random angle and distance in one of the corners
    ang = rng.uniform(0, 2 * np.pi)
    edge = rng.uniform(0.18, 0.38)
    along = (xx - w / 2) * np.cos(ang) + (yy - h / 2) * np.sin(ang)
    water = along < -(0.5 - edge) * w * 1.1
    if rng.random() < 0.25:
        water = np.zeros((h, w), bool)
    field = np.zeros((h, w), bool)
    for _ in range(int(rng.integers(1, 4))):
        c = (h * rng.uniform(0.1, 0.9), w * rng.uniform(0.1, 0.9))
        if abs(c[0] - h / 2) < h * 0.22 and abs(c[1] - w / 2) < w * 0.22:
            c = (h * 0.85, w * 0.85)
        field |= _blob((h, w), rng, c, size * rng.uniform(0.06, 0.2))
    field &= ~water
    fac = np.zeros((h, w), bool)
    flare = np.zeros((h, w), bool)
    if with_facility:
        fh, fw = rng.uniform(0.16, 0.30), rng.uniform(0.16, 0.30)
        cy, cx = 0.5 + rng.uniform(-0.07, 0.07), 0.5 + rng.uniform(-0.07, 0.07)
        fac[int(h * (cy - fh / 2)):int(h * (cy + fh / 2)), int(w * (cx - fw / 2)):int(w * (cx + fw / 2))] = True
        fac &= ~water
        if with_flare:
            fr, fc = int(h * (cy - fh / 2 - 0.04)), int(w * (cx + fw / 2 - 0.05))
            flare[fr:fr + max(2, size // 40), fc:fc + max(2, size // 40)] = True
    for name, mask in (("water", water), ("field", field), ("facility", fac)):
        refl[:, mask] = np.array(_SURFACES[name], "float32")[:, None]
    period = int(rng.integers(4, 9))
    refl[:, fac & (((yy // period) + (xx // period)) % 2 == 0)] *= 1.12
    refl[:, flare] = np.array(_SURFACES["flare"], "float32")[:, None]
    # soft terrain so that desert areas differ from place to place
    from scipy import ndimage
    terrain = ndimage.gaussian_filter(rng.normal(size=(h, w)), size / 12.0)
    terrain = terrain / (np.abs(terrain).max() + 1e-9) * 0.08
    refl *= (1 + terrain)[None].astype("float32")
    refl *= (1 + rng.normal(0, 0.03, refl.shape)).astype("float32")
    scl = np.full((h, w), 5, "uint8")
    scl[field] = 4
    scl[water] = 6
    return refl, scl, {"water": water, "field": field, "facility": fac, "flare": flare}


def weather(refl, scl, rng, cloud=0.0, haze=0.0, nodata_strip=0.0):
    """Apply haze, clouds and a no-data strip to a ground scene. Returns reflectance, classes, cloud probability, masks."""
    refl = refl.copy()
    scl = scl.copy()
    n, h, w = refl.shape
    yy, xx = np.mgrid[0:h, 0:w]
    if haze > 0:
        veil = 0.5 + 0.5 * np.sin(xx / (w / 3.0) + rng.uniform(0, 3)) * np.cos(yy / (h / 4.0) + rng.uniform(0, 3))
        refl += haze * 0.18 * np.linspace(1.0, 0.15, n)[:, None, None] * veil[None]
    cloud_mask = np.zeros((h, w), bool)
    guard = 0
    while cloud > 0 and cloud_mask.mean() < cloud and guard < 200:
        cloud_mask |= _blob((h, w), rng, (rng.uniform(0, h), rng.uniform(0, w)), rng.uniform(h * 0.08, h * 0.22))
        guard += 1
    cl = np.array(_SURFACES["cloud"], "float32")[:, None]
    refl[:, cloud_mask] = cl * (1 + rng.normal(0, 0.03, (n, int(cloud_mask.sum())))).astype("float32")
    refl = np.clip(refl, 0.0005, 1.6)
    scl[cloud_mask] = 9
    cldprb = np.where(cloud_mask, rng.uniform(70, 100, (h, w)), rng.uniform(0, 8, (h, w))).astype("float32")
    nod = np.zeros((h, w), bool)
    if nodata_strip > 0:
        nod[: max(1, int(h * nodata_strip)), :] = True
        refl[:, nod] = 0.0
        scl[nod] = 0
        cldprb[nod] = 0
    return refl, scl, cldprb, {"cloud": cloud_mask, "nodata": nod}


def _chip(refl, scl, cldprb, lat, lon, box_km, meta):
    size = refl.shape[1]
    transform = crs = None
    if lat is not None and lon is not None:
        g = core.chip_grid_math(lat, lon, box_km, chip_px=size)
        transform, crs = g["transform"], g["crs"]
    return it.Chip({b: refl[i] for i, b in enumerate(_ORDER)}, scl, cldprb, transform, crs, meta)


def synthetic_chip(seed=0, size=128, cloud=0.0, haze=0.0, nodata_strip=0.0, with_facility=True, with_flare=True,
                   lat=None, lon=None, box_km=4.0):
    """One synthetic scene. Returns ``(chip, truth)``.

    ``cloud`` is the target share of cloudy pixels, ``haze`` adds a smooth bright veil (0 to 1) that raises the
    short-wavelength bands, ``nodata_strip`` is the share of rows at the top that have no data. ``truth`` holds the
    masks of the facility, the flare, the water, the fields, the clouds and the no-data strip.
    """
    refl, scl, truth = ground(seed, size, with_facility, with_flare)
    rng = np.random.default_rng(seed + 7)
    refl, scl, cldprb, wx = weather(refl, scl, rng, cloud, haze, nodata_strip)
    truth.update(wx)
    return _chip(refl, scl, cldprb, lat, lon, box_km, {"synthetic": True, "seed": int(seed)}), truth


def synthetic_series(site_id, n=6, size=128, lat=None, lon=None, box_km=4.0):
    """Scenes of the same synthetic place on different days, with different cloud, haze and gaps.

    Returns a list of ``(chip, truth)``. The ground is identical in all of them, so composites and gap fill have a
    known answer: the ground reflectance itself.
    """
    base = seed_from(site_id)
    refl0, scl0, truth0 = ground(base, size)
    plan = [(0.05, 0.0, 0.0), (0.30, 0.3, 0.0), (0.0, 0.0, 0.06), (0.45, 0.7, 0.0), (0.10, 0.0, 0.0), (0.20, 0.3, 0.0)]
    out = []
    for k in range(n):
        c, h, s = plan[k % len(plan)]
        rng = np.random.default_rng(base + 100 + k)
        refl, scl, cldprb, wx = weather(refl0, scl0, rng, c, h, s)
        truth = dict(truth0)
        truth.update(wx)
        truth["ground_refl"] = refl0
        out.append((_chip(refl, scl, cldprb, lat, lon, box_km, {"synthetic": True, "scene": k, "days_ago": 5 * k}), truth))
    return out
