"""Image tools for TrigPoint. Everything here works on plain numpy arrays and needs no trained model.

A chip is the 14-layer array the curator caches: Sentinel-2 L2A bands B1 to B8, B8A, B9, B11, B12 as
reflectance times 10,000, then the scene classification (SCL) and the cloud probability (CLDPRB). Pixels
with no data are zero in every band.

What is here, in the order of the feature list:

* display transforms (percentile, log, square root, linear stretch)
* a registry of spectral indices with their formulas, and of three-band composites
* band and index statistics (mean, spread, skew, percentiles)
* gap fill (band mean, or the nearest-in-time scene with a band-mean shift) and a masking experiment that
  measures how well each method works on the chip itself
* cloudless median and clear-sky (low percentile) composites from a list of scenes
* candidate areas: connected regions of a simple index mask, as outlines with shape numbers, for a person to look at
"""
import math
import warnings

import numpy as np

import core

BANDS = core.CHIP_BANDS
BAND_INDEX = {b: i for i, b in enumerate(BANDS)}
REFLECTANCE_BANDS = core.S2_BANDS
SCALE = 1e-4

# --------------------------------------------------------------------------------------------------------
# loading and masks
# --------------------------------------------------------------------------------------------------------


class Chip:
    """The arrays of one chip: reflectance bands in 0..1, scene classes, cloud probability, and the grid."""

    def __init__(self, bands, scl, cldprb, transform=None, crs=None, meta=None):
        self.bands = {k: np.asarray(v, dtype="float32") for k, v in bands.items()}
        self.scl = np.asarray(scl)
        self.cldprb = np.asarray(cldprb, dtype="float32")
        self.transform = transform          # affine as a six-number list (gsd, 0, x0, 0, -gsd, y1) or None
        self.crs = crs
        self.meta = meta or {}
        h, w = self.scl.shape
        self.shape = (h, w)

    @property
    def gsd_m(self):
        return abs(self.transform[0]) if self.transform else None

    def copy(self):
        return Chip({k: v.copy() for k, v in self.bands.items()}, self.scl.copy(), self.cldprb.copy(),
                    self.transform, self.crs, dict(self.meta))


def from_array(arr, transform=None, crs=None, meta=None):
    """Build a :class:`Chip` from a (14, H, W) array in the chip layout (reflectance times 10,000)."""
    arr = np.asarray(arr)
    if arr.shape[0] != len(BANDS):
        raise ValueError(f"expected {len(BANDS)} layers, got {arr.shape[0]}")
    bands = {b: arr[i].astype("float32") * SCALE for i, b in enumerate(REFLECTANCE_BANDS)}
    return Chip(bands, arr[BAND_INDEX["SCL"]], arr[BAND_INDEX["CLDPRB"]], transform, crs, meta)


def to_array(chip):
    """Back to the (14, H, W) uint16 layout."""
    h, w = chip.shape
    out = np.zeros((len(BANDS), h, w), dtype="uint16")
    for i, b in enumerate(REFLECTANCE_BANDS):
        out[i] = np.clip(np.nan_to_num(chip.bands[b], nan=0.0) / SCALE, 0, 65535).round().astype("uint16")
    out[BAND_INDEX["SCL"]] = chip.scl.astype("uint16")
    out[BAND_INDEX["CLDPRB"]] = np.clip(np.nan_to_num(chip.cldprb, nan=0.0), 0, 65535).astype("uint16")
    return out


def load_chip(path):
    """Read a cached chip GeoTIFF."""
    import rasterio
    from rasterio.errors import NotGeoreferencedWarning

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path) as ds:
            arr = ds.read()
            t = ds.transform
            transform = [t.a, t.b, t.c, t.d, t.e, t.f] if ds.crs else None
            crs = ds.crs.to_string() if ds.crs else None
    return from_array(arr, transform, crs)


def save_chip(chip, path):
    """Write a chip as a 14-band GeoTIFF on its grid (the same layout the curator downloads)."""
    import rasterio
    from rasterio.transform import Affine

    arr = to_array(chip)
    kw = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype="uint16")
    if chip.transform and chip.crs:
        kw.update(crs=chip.crs, transform=Affine(*chip.transform[:6]))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with rasterio.open(path, "w", **kw) as ds:
            ds.write(arr)
            ds.descriptions = tuple(BANDS)


def nodata_mask(chip):
    """True where a pixel has no data: zero in every reflectance band."""
    stack = np.stack([chip.bands[b] for b in REFLECTANCE_BANDS])
    return ~np.isfinite(stack).any(axis=0) | (np.nan_to_num(stack, nan=0.0) <= 0).all(axis=0)


def valid_mask(chip):
    """True where the pixel has data."""
    return ~nodata_mask(chip)


def clear_mask(chip, cloud_prob=None):
    """True for valid pixels that are not cloud: cloud probability below the threshold and a clear scene class."""
    thr = core.CFG["cloud_prob_thresh"] if cloud_prob is None else cloud_prob
    cloudy_class = np.isin(chip.scl, core.SCL_CLOUDY)
    return valid_mask(chip) & (chip.cldprb < thr) & ~cloudy_class


def valid_share(chip):
    return float(valid_mask(chip).mean())


def cloud_share(chip, cloud_prob=None):
    """Share of valid pixels that are cloud, by probability or scene class."""
    thr = core.CFG["cloud_prob_thresh"] if cloud_prob is None else cloud_prob
    v = valid_mask(chip)
    if not v.any():
        return float("nan")
    cloudy = (chip.cldprb >= thr) | np.isin(chip.scl, core.SCL_CLOUDY)
    return float((cloudy & v).sum() / v.sum())


# --------------------------------------------------------------------------------------------------------
# display transforms
# --------------------------------------------------------------------------------------------------------

STRETCHES = {
    "percentile": "Each channel stretched between its 2nd and 98th percentile (default)",
    "log": "Log base 2 of the reflectance, then percentile stretch; opens up dark areas of skewed images",
    "sqrt": "Square root of the reflectance, then percentile stretch; a milder version of log",
    "linear": "Fixed linear stretch from 0 to 0.3 reflectance; the same scale for every image, so images compare",
}


def apply_transform(arr, name):
    """Transform reflectance values (0..1) before display or feature extraction."""
    arr = np.asarray(arr, dtype="float32")
    if name in (None, "percentile", "linear"):
        return arr
    if name == "log":
        return np.log2(np.clip(arr, 1e-4, None) * 1e4)       # 1 to about 14 for reflectance 0.0001 to 1.6
    if name == "sqrt":
        return np.sqrt(np.clip(arr, 0, None))
    raise ValueError(f"unknown transform {name!r}; choose from {list(STRETCHES)}")


def stretch_channels(channels, mode="percentile", valid=None):
    """Stack three reflectance channels into a (H, W, 3) image in 0..1.

    ``valid`` limits the percentile statistics to valid pixels; invalid pixels come out black.
    """
    if mode not in STRETCHES:
        raise ValueError(f"unknown stretch {mode!r}; choose from {list(STRETCHES)}")
    chans = [np.nan_to_num(c, nan=0.0) for c in channels]
    if valid is None:
        valid = np.ones(chans[0].shape, bool)
    out = np.zeros(chans[0].shape + (len(chans),), dtype="float32")
    for i, c in enumerate(chans):
        if mode == "linear":
            out[..., i] = np.clip(c / 0.3, 0.0, 1.0)
            continue
        t = apply_transform(c, mode)
        vals = t[valid & (c > 0)]
        if vals.size < 100:
            out[..., i] = np.clip(t / max(float(np.nanmax(t)) if t.size else 1.0, 1e-6), 0, 1)
            continue
        lo, hi = np.percentile(vals, 2), np.percentile(vals, 98)
        out[..., i] = np.clip((t - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    out[~valid] = 0.0
    return out


# --------------------------------------------------------------------------------------------------------
# indices and composites
# --------------------------------------------------------------------------------------------------------


def _nd(a, b):
    return (a - b) / np.clip(a + b, 1e-6, None)


# name: (formula text, function of the band dict, (low, high) clamp, plain description)
INDICES = {
    "ndvi": ("(B8 - B4) / (B8 + B4)", lambda r: _nd(r["B8"], r["B4"]), (-1, 1),
             "Green vegetation. High over crops and forest, near zero over bare ground and buildings."),
    "evi": ("2.5 (B8 - B4) / (B8 + 6 B4 - 7.5 B2 + 1)",
            lambda r: 2.5 * (r["B8"] - r["B4"]) / (r["B8"] + 6 * r["B4"] - 7.5 * r["B2"] + 1), (-1, 3),
            "Vegetation, less saturated than NDVI over dense canopy."),
    "savi": ("1.5 (B8 - B4) / (B8 + B4 + 0.5)", lambda r: 1.5 * (r["B8"] - r["B4"]) / (r["B8"] + r["B4"] + 0.5),
             (-1.5, 1.5), "Vegetation with a correction for bright soil."),
    "ndre": ("(B8A - B5) / (B8A + B5)", lambda r: _nd(r["B8A"], r["B5"]), (-1, 1),
             "Red-edge vegetation signal."),
    "ndwi": ("(B3 - B8) / (B3 + B8)", lambda r: _nd(r["B3"], r["B8"]), (-1, 1), "Open water. High over water."),
    "mndwi": ("(B3 - B11) / (B3 + B11)", lambda r: _nd(r["B3"], r["B11"]), (-1, 1),
              "Open water, separates water from buildings better than NDWI."),
    "awei": ("4 (B3 - B11) - (0.25 B8 + 2.75 B12)",
             lambda r: 4 * (r["B3"] - r["B11"]) - (0.25 * r["B8"] + 2.75 * r["B12"]), (-2, 2), "Automated water extraction."),
    "nmdi": ("(B8 - (B11 - B12)) / (B8 + (B11 - B12))",
             lambda r: (r["B8"] - (r["B11"] - r["B12"])) / np.where(np.abs(r["B8"] + (r["B11"] - r["B12"])) < 1e-6, 1e-6,
                                                                  r["B8"] + (r["B11"] - r["B12"])), (-5, 5), "Moisture."),
    "nbri": ("(B8 - B12) / (B8 + B12)", lambda r: _nd(r["B8"], r["B12"]), (-1, 1),
             "Burnt or hot ground: low where short-wave infrared is high."),
    "nbr2": ("(B11 - B12) / (B11 + B12)", lambda r: _nd(r["B11"], r["B12"]), (-1, 1),
             "Contrast of the two short-wave infrared bands: dry and hot surfaces."),
    "bsi": ("((B11 + B4) - (B8 + B2)) / ((B11 + B4) + (B8 + B2))",
            lambda r: _nd(r["B11"] + r["B4"], r["B8"] + r["B2"]), (-1, 1), "Bare soil and built-up ground."),
    "bi": ("sqrt((B4^2 + B3^2 + B2^2) / 3)", lambda r: np.sqrt((r["B4"] ** 2 + r["B3"] ** 2 + r["B2"] ** 2) / 3), (0, 1.5),
           "Brightness in the visible bands."),
    "swir_ratio": ("B11 / B12", lambda r: r["B11"] / np.clip(r["B12"], 1e-6, None), (0, 10), "Ratio of the two short-wave bands."),
    "ndii": ("(B8 - B11) / (B8 + B11)", lambda r: _nd(r["B8"], r["B11"]), (-1, 1), "Moisture in vegetation and soil."),
    "hsfi": ("B12 / B8", lambda r: r["B12"] / np.clip(r["B8"], 1e-6, None), (0, 10),
             "Hot-surface ratio: high where B12 is large compared with the near infrared (flares, hot ground)."),
    "ohi": ("(B12 - B3) / (B12 + B3)", lambda r: _nd(r["B12"], r["B3"]), (-1, 1), "Hot objects against the green band."),
    "aero_b1b2": ("(B1 - B2) / (B1 + B2)", lambda r: _nd(r["B1"], r["B2"]), (-1, 1),
                  "Coastal-blue contrast. Haze and aerosol raise B1 relative to B2; used by aerosol-estimation work."),
    "aero_b3b7": ("(B3 - B7) / (B3 + B7)", lambda r: _nd(r["B3"], r["B7"]), (-1, 1),
                  "Green against red-edge: sensitive to aerosol over vegetated and bare surfaces."),
}

# three-band composites: (bands, plain description)
COMPOSITES = {
    "true_color": (("B4", "B3", "B2"), "As the eye sees it."),
    "false_color_ir": (("B8", "B4", "B3"), "Vegetation red; strong structure contrast."),
    "swir": (("B12", "B11", "B4"), "Bare ground and industry stand out; water is dark; flares and hot ground glow orange."),
    "agriculture": (("B11", "B8", "B2"), "Healthy vegetation green; separates desert from cultivated land."),
    "aerosol": (("B4", "B2", "B1"), "Red, blue and coastal blue: haze and smoke look blue-white. Useful to spot aerosol."),
    "urban": (("B12", "B11", "B4"), "Short-wave infrared composite; built-up surfaces are pale."),
}
COMPOSITES.pop("urban")        # same bands as swir; kept out to avoid two names for one view

SINGLE_BAND_VIEWS = tuple(INDICES)

# Sequential blue ramp, light (low) to dark (high), used for every index view.
RAMP = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
        "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def compute_index(name, bands):
    """The index as a float32 array. ``bands`` is a dict of reflectance arrays (0..1) keyed B1..B12."""
    if name not in INDICES:
        raise KeyError(f"unknown index {name!r}; choose from {list(INDICES)}")
    formula, fn, (lo, hi), _ = INDICES[name]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = fn(bands)
    out = np.clip(out, lo, hi).astype("float32")
    return out


def colour_ramp(t):
    """Map values in 0..1 onto the blue ramp, returning (..., 3) floats."""
    ramp = np.array([[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)] for h in RAMP], dtype="float32") / 255.0
    t = np.clip(np.nan_to_num(t, nan=0.0), 0.0, 1.0)
    f = t * (len(ramp) - 1)
    i0 = np.floor(f).astype(int)
    i1 = np.clip(i0 + 1, 0, len(ramp) - 1)
    frac = (f - i0)[..., None]
    return (ramp[i0] * (1 - frac) + ramp[i1] * frac).astype("float32")


def render_view(chip, view="true_color", stretch="percentile", mask_nodata=True):
    """A (H, W, 3) float image of a chip for one view.

    ``view`` is a composite name (true_color, false_color_ir, swir, agriculture, aerosol), an index name
    (ndvi, nbr2, bsi, ...) or ``"ndvi"``. Index views use the sequential ramp scaled between the 2nd and 98th
    percentile of the index over valid pixels; composites use ``stretch``.
    """
    v = valid_mask(chip)
    if view in COMPOSITES:
        bands = COMPOSITES[view][0]
        return stretch_channels([chip.bands[b] for b in bands], stretch, v if mask_nodata else None)
    if view in INDICES:
        idx = compute_index(view, chip.bands)
        vals = idx[v]
        if vals.size < 100:
            t = np.zeros_like(idx)
        else:
            lo, hi = np.percentile(vals, 2), np.percentile(vals, 98)
            t = (idx - lo) / max(hi - lo, 1e-6)
        out = colour_ramp(t)
        if mask_nodata:
            out[~v] = 0.0
        return out
    raise KeyError(f"unknown view {view!r}; choose from {list(COMPOSITES) + list(INDICES)}")


def all_views():
    """View names with a plain description, composites first."""
    d = {k: v[1] for k, v in COMPOSITES.items()}
    d.update({k: f"Index {k.upper()}: {v[3]}" for k, v in INDICES.items()})
    return d


def save_png(rgb, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    mpimg.imsave(path, np.clip(rgb, 0, 1))


# --------------------------------------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------------------------------------

PERCENTILES = (5, 25, 50, 75, 95)


def describe(values):
    """Mean, standard deviation, skewness and percentiles of a 1-D array of finite values."""
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0, "mean": None, "std": None, "skew": None, **{f"p{p}": None for p in PERCENTILES}}
    mean = float(v.mean())
    std = float(v.std())
    skew = float(np.mean(((v - mean) / std) ** 3)) if std > 0 else 0.0
    pct = np.percentile(v, PERCENTILES)
    return {"n": int(v.size), "mean": mean, "std": std, "skew": skew, **{f"p{p}": float(q) for p, q in zip(PERCENTILES, pct)}}


def chip_statistics(chip, indices=("ndvi", "ndwi", "nbr2", "bsi", "aero_b1b2"), clear_only=False):
    """Statistics of the reflectance bands and the chosen indices over the valid (or clear) pixels."""
    m = clear_mask(chip) if clear_only else valid_mask(chip)
    out = {"valid_share": float(valid_mask(chip).mean()), "clear_share": float(clear_mask(chip).mean()),
           "cloud_share": cloud_share(chip), "pixels_used": int(m.sum()), "bands": {}, "indices": {}}
    for b in REFLECTANCE_BANDS:
        out["bands"][b] = describe(chip.bands[b][m])
    for name in indices:
        out["indices"][name] = describe(compute_index(name, chip.bands)[m])
    return out


# --------------------------------------------------------------------------------------------------------
# gap fill
# --------------------------------------------------------------------------------------------------------


def fill_mean(chip, mask=None):
    """Fill the pixels in ``mask`` (default: no-data pixels) with the mean of the valid pixels of each band."""
    out = chip.copy()
    gap = nodata_mask(chip) if mask is None else mask
    ok = valid_mask(chip) & ~gap
    n_fill = int(gap.sum())
    if n_fill and ok.any():
        for b in REFLECTANCE_BANDS:
            out.bands[b][gap] = float(chip.bands[b][ok].mean())
    return out, {"method": "mean", "filled": n_fill if ok.any() else 0, "remaining": 0 if ok.any() else n_fill}


def fill_nearest(chip, other, mask=None, clear_only=True):
    """Fill gap pixels from another scene of the same place, shifting each band by the mean difference.

    The shift is the mean of (this scene minus the other) over pixels usable in both, which puts the donor
    pixels on the brightness level of the scene being repaired. With ``clear_only`` (the default) a donor pixel is
    usable only if it is clear (not cloud), so clouds of the donor scene are never copied in. Pixels the donor
    cannot fill stay empty.
    """
    if chip.shape != other.shape:
        raise ValueError("the two scenes must have the same shape")
    out = chip.copy()
    gap = nodata_mask(chip) if mask is None else mask
    donor_ok = clear_mask(other) if clear_only else valid_mask(other)
    base_ok = clear_mask(chip) if clear_only else valid_mask(chip)
    both = base_ok & donor_ok & ~gap
    fill = gap & donor_ok
    for b in REFLECTANCE_BANDS:
        shift = float(chip.bands[b][both].mean() - other.bands[b][both].mean()) if both.any() else 0.0
        out.bands[b][fill] = np.clip(other.bands[b][fill] + shift, 1e-4, None)
    return out, {"method": "nearest", "filled": int(fill.sum()), "remaining": int((gap & ~donor_ok).sum()),
                 "overlap_pixels": int(both.sum())}


def fill_gaps(chip, other=None, mask=None):
    """The fill the curator applies: the nearest scene first (if given), then the band mean for what is left.

    Returns the filled chip and a dict with how many pixels each step filled.
    """
    gap = nodata_mask(chip) if mask is None else mask
    steps = {"gap_pixels": int(gap.sum()), "nearest": 0, "mean": 0, "remaining": 0}
    out = chip
    if other is not None and gap.any():
        out, info = fill_nearest(chip, other, gap)
        steps["nearest"] = info["filled"]
        gap = gap & nodata_mask(out)
    if gap.any():
        out, info = fill_mean(out, gap)
        steps["mean"] = info["filled"]
        steps["remaining"] = info["remaining"]
    return out, steps


def masking_experiment(chip, other=None, fraction=0.10, seed=0, block=8):
    """Measure how well each fill method works, on this chip.

    Square blocks of valid pixels covering about ``fraction`` of the chip are hidden, each method fills them,
    and the root mean squared reflectance error against the hidden truth is reported per method. Needs
    ``other`` (a second scene) for the nearest-scene method.
    """
    rng = np.random.default_rng(seed)
    v = clear_mask(chip)                      # only clear pixels are hidden, so the truth is the surface
    h, w = chip.shape
    hide = np.zeros((h, w), bool)
    target = int(fraction * v.sum())
    tries = 0
    while hide.sum() < target and tries < 10000:
        r, c = int(rng.integers(0, max(h - block, 1))), int(rng.integers(0, max(w - block, 1)))
        hide[r:r + block, c:c + block] = True
        tries += 1
    hide &= v
    broken = chip.copy()
    for b in REFLECTANCE_BANDS:
        broken.bands[b][hide] = 0.0
    broken.cldprb[hide] = 0.0
    broken.scl[hide] = 0
    res = {"hidden_pixels": int(hide.sum()), "fraction": float(hide.mean())}

    def rmse(filled):
        d = np.stack([(filled.bands[b] - chip.bands[b])[hide] for b in REFLECTANCE_BANDS])
        return float(np.sqrt(np.mean(d ** 2))) if d.size else float("nan")

    res["mean"] = rmse(fill_mean(broken, hide)[0])
    if other is not None:
        filled, steps = fill_gaps(broken, other, hide)
        res["nearest"] = rmse(filled)                       # nearest scene first, band mean for the rest
        res["nearest_share"] = steps["nearest"] / max(steps["gap_pixels"], 1)
    # reference: how large the reflectance spread is, so the errors can be read against it
    res["reference_std"] = float(np.mean([chip.bands[b][v].std() for b in REFLECTANCE_BANDS])) if v.sum() > 1 else None
    return res


# --------------------------------------------------------------------------------------------------------
# composites from several scenes
# --------------------------------------------------------------------------------------------------------


def _stack_bands(chips, masks):
    """Per band, an array (n_scenes, H, W) with NaN where the scene is not usable."""
    out = {}
    for b in REFLECTANCE_BANDS:
        arr = np.stack([np.where(m, c.bands[b], np.nan) for c, m in zip(chips, masks)]).astype("float32")
        out[b] = arr
    return out


def nan_percentile(arr, q):
    """Percentile ``q`` (0 to 100) along axis 0 ignoring NaN, linear interpolation like numpy.

    Much faster than ``numpy.nanpercentile`` on stacks of scenes (that one loops over pixels). Pixels with no value give NaN.
    """
    arr = np.asarray(arr, dtype="float32")
    srt = np.sort(arr, axis=0)                                   # NaN sorts to the end
    n = np.sum(~np.isnan(arr), axis=0)
    pos = np.clip((n - 1) * (q / 100.0), 0, None)
    lo = np.floor(pos).astype(int)
    hi = np.minimum(np.ceil(pos).astype(int), np.maximum(n - 1, 0))
    frac = (pos - lo).astype("float32")
    a = np.take_along_axis(srt, lo[None], axis=0)[0]
    b = np.take_along_axis(srt, hi[None], axis=0)[0]
    out = a + (b - a) * frac
    out[n == 0] = np.nan
    return out


def composite(chips, method="median", q=20, require_clear=True, cloud_prob=None):
    """Combine scenes of the same place into one chip.

    ``method`` is ``"median"`` (the cloudless median: the middle value of the clear observations at each pixel)
    or ``"clearsky"`` (a low percentile ``q`` of the clear observations, which keeps the darkest, least
    hazy values and so shows the surface beneath clouds and thin haze). Returns the composite chip and a dict
    with the number of scenes, the share of pixels with at least one clear observation and the scene count
    per pixel.
    """
    if not chips:
        raise ValueError("no scenes to combine")
    shape = chips[0].shape
    if any(c.shape != shape for c in chips):
        raise ValueError("all scenes must have the same shape")
    masks = [clear_mask(c, cloud_prob) if require_clear else valid_mask(c) for c in chips]
    stack = _stack_bands(chips, masks)
    n_obs = np.sum(np.stack(masks), axis=0)
    out_bands = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for b, arr in stack.items():
            if method == "median":
                comp = np.nanmedian(arr, axis=0)
            elif method == "clearsky":
                comp = nan_percentile(arr, q)
            else:
                raise ValueError("method must be 'median' or 'clearsky'")
            out_bands[b] = np.nan_to_num(comp, nan=0.0).astype("float32")
    # In a composite every pixel comes from clear observations. CLDPRB is 100 where no scene was ever clear
    # (a hole the composite could not fill) and 0 elsewhere, so the same masks work on composites and scenes.
    any_valid = np.any(np.stack([valid_mask(c) for c in chips]), axis=0)
    cldprb = np.where((n_obs == 0) & any_valid, 100.0, 0.0).astype("float32")
    scl = np.where(n_obs > 0, 4, 0).astype("uint8")                 # 4 = vegetation class: marks "clear observed"
    res = Chip(out_bands, scl, cldprb, chips[0].transform, chips[0].crs,
               {"composite": method, "n_scenes": len(chips)})
    info = {"method": method, "n_scenes": len(chips), "observed_share": float((n_obs > 0).mean()),
            "median_observations": float(np.median(n_obs)), "q": q if method == "clearsky" else None,
            "n_obs": n_obs}
    return res, info


# --------------------------------------------------------------------------------------------------------
# candidate areas (an aid for the eye; it never moves a site)
# --------------------------------------------------------------------------------------------------------

MASK_KINDS = {
    "built_up": ("Bare or built-up ground: BSI above the threshold and NDVI below 0.25",
                 lambda b: (compute_index("bsi", b), compute_index("ndvi", b) < 0.25)),
    "hot": ("Hot ground or flare: hot-surface ratio B12 / B8 above the threshold",
            lambda b: (compute_index("hsfi", b), np.ones(b["B12"].shape, bool))),
    "bare": ("Dry bare surface: NBR2 above the threshold and NDVI below 0.2",
             lambda b: (compute_index("nbr2", b), compute_index("ndvi", b) < 0.2)),
    "bright": ("Bright surfaces: visible brightness above the threshold",
               lambda b: (compute_index("bi", b), np.ones(b["B4"].shape, bool))),
}


def label_regions(mask):
    """Label 8-connected regions of a boolean mask. Returns (labels, count)."""
    try:
        from scipy import ndimage
        return ndimage.label(mask, structure=np.ones((3, 3), int))
    except ImportError:                                   # pragma: no cover - scipy ships with the tool's requirements
        labels = np.zeros(mask.shape, int)
        n = 0
        for r, c in zip(*np.nonzero(mask)):
            if labels[r, c]:
                continue
            n += 1
            stack = [(r, c)]
            labels[r, c] = n
            while stack:
                y, x = stack.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < mask.shape[0] and 0 <= xx < mask.shape[1] and mask[yy, xx] and not labels[yy, xx]:
                            labels[yy, xx] = n
                            stack.append((yy, xx))
        return labels, n


def candidate_areas(chip, kind="built_up", threshold=None, percentile=90.0, min_pixels=30, max_regions=25):
    """Connected regions of a simple index mask, with shape numbers, for a person to look at.

    ``threshold`` is a value of the mask's index; when it is None the ``percentile`` of the index over valid pixels is
    used, so the result adapts to each chip. Regions smaller than ``min_pixels`` are dropped. Each region has its
    area in pixels and square kilometres, its centroid (pixel and, when the chip has a grid, longitude and latitude),
    its distance from the chip centre, compactness (1 for a circle) and elongation (1 for round, larger for long),
    and an outline as GeoJSON when the chip has a grid. Nothing here moves a site: it only draws candidates.
    """
    if kind not in MASK_KINDS:
        raise KeyError(f"unknown mask {kind!r}; choose from {list(MASK_KINDS)}")
    v = valid_mask(chip)
    score, gate = MASK_KINDS[kind][1](chip.bands)
    if threshold is None:
        threshold = float(np.percentile(score[v], percentile)) if v.any() else 0.0
    mask = (score >= threshold) & gate & v
    labels, n = label_regions(mask)
    h, w = chip.shape
    gsd = chip.gsd_m
    px_area_km2 = (gsd / 1000.0) ** 2 if gsd else None
    regions = []
    sizes = np.bincount(labels.ravel(), minlength=n + 1)
    for lab in np.nonzero(sizes[1:] >= min_pixels)[0] + 1:        # only regions big enough are examined
        ys, xs = np.nonzero(labels == lab)
        cy, cx = float(ys.mean()), float(xs.mean())
        cov = np.cov(np.stack([xs, ys])) if ys.size > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
        elong = float(math.sqrt(ev[0] / max(ev[1], 1e-9))) if ev[0] > 0 else 1.0
        # perimeter: count of exposed pixel edges
        m = labels == lab
        perim = int((m[:, :-1] != m[:, 1:]).sum() + (m[:-1, :] != m[1:, :]).sum() + m[0, :].sum() + m[-1, :].sum()
                    + m[:, 0].sum() + m[:, -1].sum())
        compact = float(4 * math.pi * ys.size / max(perim, 1) ** 2)
        reg = {"id": int(lab), "pixels": int(ys.size), "area_km2": (ys.size * px_area_km2) if px_area_km2 else None,
               "centroid_px": [cx, cy], "distance_from_centre_px": float(math.hypot(cx - (w - 1) / 2, cy - (h - 1) / 2)),
               "compactness": min(compact, 1.0), "elongation": elong, "mean_score": float(score[m].mean())}
        if gsd:
            reg["distance_from_centre_m"] = reg["distance_from_centre_px"] * gsd
        regions.append((ys.size, reg, m))
    regions.sort(key=lambda t: -t[0])
    regions = regions[:max_regions]
    features = []
    out = []
    for rank, (_, reg, m) in enumerate(regions, 1):
        reg["rank"] = rank
        out.append(reg)
        if chip.transform and chip.crs:
            features.extend(_outline_features(m, chip, rank))
        if chip.transform and chip.crs:
            lon, lat = _px_to_lonlat(chip, *reg["centroid_px"])
            reg["centroid_lonlat"] = [lon, lat]
    return {"kind": kind, "description": MASK_KINDS[kind][0], "threshold": float(threshold),
            "mask_share": float(mask.mean()), "regions": out,
            "geojson": {"type": "FeatureCollection", "features": features}}


def _px_to_lonlat(chip, col, row):
    from rasterio.transform import Affine
    from rasterio.warp import transform as warp_transform

    t = Affine(*chip.transform[:6])
    cx, cy = col + 0.5, row + 0.5
    x, y = t.a * cx + t.b * cy + t.c, t.d * cx + t.e * cy + t.f
    lon, lat = warp_transform(chip.crs, "EPSG:4326", [x], [y])
    return float(lon[0]), float(lat[0])


def _outline_features(mask, chip, rank):
    """GeoJSON outlines (WGS 84) of one region, with pixel-edge precision."""
    from rasterio import features
    from rasterio.transform import Affine
    from rasterio.warp import transform_geom

    t = Affine(*chip.transform[:6])
    feats = []
    for geom, val in features.shapes(mask.astype("uint8"), mask=mask, transform=t, connectivity=8):
        g = transform_geom(chip.crs, "EPSG:4326", geom, precision=6)
        feats.append({"type": "Feature", "properties": {"rank": rank}, "geometry": g})
    return feats
