"""imagery_tools.py on synthetic scenes with known answers."""
import math

import numpy as np
import pytest

import core
import demo_scene as ds
import imagery_tools as it

LAT, LON = 27.05, 49.56


@pytest.fixture(scope="module")
def clean():
    chip, truth = ds.synthetic_chip(seed=3, size=96, lat=LAT, lon=LON, box_km=4)
    return chip, truth


@pytest.fixture(scope="module")
def series():
    return ds.synthetic_series("unit_site", n=6, size=96, lat=LAT, lon=LON, box_km=4)


# ------------------------------------------------------------------ indices and views

def bands_of(**kw):
    base = {b: np.full((2, 2), 0.2, "float32") for b in core.S2_BANDS}
    for k, v in kw.items():
        base[k] = np.full((2, 2), v, "float32")
    return base


def test_ndvi_matches_the_formula():
    b = bands_of(B8=0.5, B4=0.1)
    assert np.allclose(it.compute_index("ndvi", b), (0.5 - 0.1) / (0.5 + 0.1))


def test_every_index_is_finite_and_inside_its_clamp_even_for_awkward_input():
    for scene in (bands_of(), bands_of(B8=0.0, B4=0.0, B12=0.0, B11=0.0), bands_of(B1=1.6, B2=0.0005)):
        for name, (_, _, (lo, hi), _) in it.INDICES.items():
            v = it.compute_index(name, scene)
            assert np.isfinite(v).all(), name
            assert v.min() >= lo - 1e-6 and v.max() <= hi + 1e-6, name


def test_aerosol_index_rises_with_haze_in_the_coastal_band():
    clear = bands_of(B1=0.10, B2=0.10)
    hazy = bands_of(B1=0.20, B2=0.12)
    assert it.compute_index("aero_b1b2", hazy).mean() > it.compute_index("aero_b1b2", clear).mean()


def test_unknown_names_raise():
    with pytest.raises(KeyError):
        it.compute_index("nope", bands_of())
    with pytest.raises(KeyError):
        it.render_view(ds.synthetic_chip(size=32)[0], "nope")


def test_every_view_renders_an_image_in_range(clean):
    chip, _ = clean
    for view in it.all_views():
        img = it.render_view(chip, view)
        assert img.shape == chip.shape + (3,) and img.dtype == np.float32, view
        assert img.min() >= 0 and img.max() <= 1, view
        assert img.std() > 0.01, view            # not a flat image


def test_every_stretch_works_and_no_data_is_black():
    chip, truth = ds.synthetic_chip(seed=1, size=64, nodata_strip=0.1)
    for mode in it.STRETCHES:
        img = it.render_view(chip, "true_color", stretch=mode)
        assert np.all(img[truth["nodata"]] == 0), mode
        assert img[~truth["nodata"]].max() > 0.5, mode
    with pytest.raises(ValueError):
        it.render_view(chip, "true_color", stretch="bogus")


def test_log_and_sqrt_open_up_dark_pixels():
    dark = np.array([0.01, 0.02, 0.03], "float32")
    lin = it.apply_transform(dark, "linear")
    sq = it.apply_transform(dark, "sqrt")
    lg = it.apply_transform(dark, "log")
    assert np.allclose(lin, dark)
    # ratio of the darkest to brightest of the three is closer to 1 after the transform
    assert sq[0] / sq[2] > lin[0] / lin[2]
    assert lg[0] / lg[2] > lin[0] / lin[2]
    with pytest.raises(ValueError):
        it.apply_transform(dark, "wrong")


# ------------------------------------------------------------------ masks and statistics

def test_masks_follow_the_truth(clean):
    chip, truth = clean
    assert not it.valid_mask(chip)[truth["nodata"]].any()
    cl = it.clear_mask(chip)
    assert not cl[truth["cloud"]].any()
    assert it.valid_share(chip) == 1.0


def test_cloud_and_nodata_are_detected():
    chip, truth = ds.synthetic_chip(seed=2, size=96, cloud=0.3, nodata_strip=0.1)
    assert math.isclose(it.valid_share(chip), 1 - truth["nodata"].mean(), abs_tol=1e-6)
    assert it.cloud_share(chip) > 0.2
    assert it.clear_mask(chip).mean() < it.valid_mask(chip).mean()


def test_statistics_of_a_known_distribution():
    d = it.describe(np.array([1, 2, 3, 4, 5], float))
    assert d["n"] == 5 and d["mean"] == 3 and math.isclose(d["std"], math.sqrt(2)) and abs(d["skew"]) < 1e-9
    assert d["p50"] == 3
    skewed = it.describe(np.array([1] * 20 + [50], float))
    assert skewed["skew"] > 1
    assert it.describe(np.array([np.nan, np.inf]))["n"] == 0
    assert it.describe(np.array([2.0, 2.0, 2.0]))["skew"] == 0.0


def test_chip_statistics_structure(clean):
    chip, _ = clean
    s = it.chip_statistics(chip)
    assert set(s["bands"]) == set(core.S2_BANDS) and {"ndvi", "aero_b1b2"} <= set(s["indices"])
    assert s["valid_share"] == 1.0 and s["pixels_used"] == chip.shape[0] * chip.shape[1]
    assert s["bands"]["B8"]["mean"] > s["bands"]["B2"]["mean"]
    only_clear = it.chip_statistics(ds.synthetic_chip(seed=2, size=64, cloud=0.4)[0], clear_only=True)
    assert only_clear["pixels_used"] < 64 * 64


# ------------------------------------------------------------------ gap fill

def test_fill_mean_fills_every_gap_with_the_band_mean():
    chip, truth = ds.synthetic_chip(seed=4, size=64, nodata_strip=0.15)
    out, info = it.fill_mean(chip)
    assert info["filled"] == int(truth["nodata"].sum()) and info["remaining"] == 0
    assert it.valid_mask(out).all()
    ok = ~truth["nodata"]
    for b in core.S2_BANDS:
        assert math.isclose(float(out.bands[b][truth["nodata"]].mean()), float(chip.bands[b][ok].mean()), rel_tol=1e-4)


def test_fill_nearest_uses_the_other_scene_with_a_brightness_shift():
    chip, truth = ds.synthetic_chip(seed=5, size=64, nodata_strip=0.2)
    other = chip.copy()
    for b in core.S2_BANDS:
        other.bands[b] = chip.bands[b] + 0.05              # a brighter day
    # give the other scene data where this one has none (the donor holds the truth + 0.05)
    clean_chip, _ = ds.synthetic_chip(seed=5, size=64)
    for b in core.S2_BANDS:
        other.bands[b] = clean_chip.bands[b] + 0.05
    out, info = it.fill_nearest(chip, other)
    assert info["remaining"] == 0 and info["filled"] == int(truth["nodata"].sum())
    err = np.abs(out.bands["B8"][truth["nodata"]] - clean_chip.bands["B8"][truth["nodata"]]).mean()
    assert err < 0.02                                       # the shift removed the 0.05 offset


def test_fill_nearest_leaves_gaps_the_donor_cannot_fill():
    a, ta = ds.synthetic_chip(seed=6, size=48, nodata_strip=0.2)
    b, tb = ds.synthetic_chip(seed=6, size=48, nodata_strip=0.1)
    out, info = it.fill_nearest(a, b)
    assert info["remaining"] == int((ta["nodata"] & tb["nodata"]).sum()) > 0


def test_fill_rejects_mismatched_shapes():
    a = ds.synthetic_chip(size=32)[0]
    b = ds.synthetic_chip(size=40)[0]
    with pytest.raises(ValueError):
        it.fill_nearest(a, b)


def test_masking_experiment_ranks_nearest_ahead_of_mean(series):
    chip = series[0][0]
    other = series[4][0]                                      # a clean-ish second scene
    res = it.masking_experiment(chip, other, fraction=0.1, seed=1, block=6)
    assert 0.05 < res["fraction"] < 0.2
    assert res["nearest"] < res["mean"]
    assert res["mean"] < 3 * res["reference_std"]


# ------------------------------------------------------------------ composites

def test_median_composite_is_closer_to_the_ground_than_a_cloudy_scene(series):
    chips = [c for c, _ in series]
    truth = series[0][1]
    comp, info = it.composite(chips, "median")
    ground = truth["ground_refl"]
    cloudy_idx = max(range(len(series)), key=lambda i: series[i][1]["cloud"].mean())
    worst = chips[cloudy_idx]
    ok = ~truth["nodata"]
    err = lambda c: float(np.abs(np.stack([c.bands[b] for b in core.S2_BANDS]) - ground)[:, ok].mean())
    assert err(comp) < err(worst)
    assert info["n_scenes"] == 6 and info["observed_share"] > 0.99
    assert it.clear_mask(comp).mean() > 0.9


def test_clear_sky_layer_is_darker_than_the_median_in_the_blue_when_there_is_haze(series):
    chips = [c for c, _ in series]
    med, _ = it.composite(chips, "median")
    low, info = it.composite(chips, "clearsky", q=10)
    assert info["q"] == 10
    assert float(low.bands["B1"][it.valid_mask(low)].mean()) <= float(med.bands["B1"][it.valid_mask(med)].mean()) + 1e-6


def test_composite_needs_scenes_of_one_shape_and_a_known_method(series):
    with pytest.raises(ValueError):
        it.composite([])
    with pytest.raises(ValueError):
        it.composite([series[0][0], ds.synthetic_chip(size=40)[0]])
    with pytest.raises(ValueError):
        it.composite([series[0][0]], "mean")


def test_a_pixel_never_clear_stays_empty_in_the_composite():
    a, ta = ds.synthetic_chip(seed=8, size=48, cloud=0.0, nodata_strip=0.25)
    b, tb = ds.synthetic_chip(seed=8, size=48, cloud=0.0, nodata_strip=0.25)
    comp, info = it.composite([a, b])
    assert info["observed_share"] < 0.8
    assert not it.valid_mask(comp)[ta["nodata"]].any()


# ------------------------------------------------------------------ candidate areas

def test_built_up_candidates_find_the_facility(clean):
    chip, truth = clean
    res = it.candidate_areas(chip, "built_up", percentile=80, min_pixels=20)
    assert res["regions"], "expected at least one region"
    top = res["regions"][0]
    cx, cy = map(int, top["centroid_px"])
    near = truth["facility"][max(cy - 3, 0):cy + 4, max(cx - 3, 0):cx + 4].any() or top["pixels"] > 200
    assert near
    assert top["area_km2"] > 0 and 0 < top["compactness"] <= 1 and top["elongation"] >= 1


def test_hot_candidates_find_the_flare(clean):
    chip, truth = clean
    res = it.candidate_areas(chip, "hot", threshold=1.6, min_pixels=2)
    assert res["regions"]
    cx, cy = res["regions"][0]["centroid_px"]
    ys, xs = np.nonzero(truth["flare"])
    assert abs(cx - xs.mean()) < 4 and abs(cy - ys.mean()) < 4


def test_outlines_are_valid_geojson_inside_the_chip(clean):
    chip, _ = clean
    res = it.candidate_areas(chip, "built_up", percentile=80, min_pixels=20)
    fc = res["geojson"]
    assert fc["type"] == "FeatureCollection" and fc["features"]
    g = core.chip_grid_math(LAT, LON, 4, chip_px=96)
    from rasterio.warp import transform
    x0, y0, x1, y1 = g["bounds_utm"]                                 # a square in UTM is not a rectangle in longitude and latitude,
    lons, lats = transform(g["crs"], "EPSG:4326", [x0, x0, x1, x1], [y0, y1, y0, y1])   # so use all four corners
    for f in fc["features"]:
        ring = f["geometry"]["coordinates"][0]
        for lon, lat in ring:
            assert min(lons) - 1e-4 <= lon <= max(lons) + 1e-4 and min(lats) - 1e-4 <= lat <= max(lats) + 1e-4
    r = res["regions"][0]
    assert "centroid_lonlat" in r and abs(r["centroid_lonlat"][1] - LAT) < 0.05


def test_candidates_without_a_grid_have_no_outlines():
    chip, _ = ds.synthetic_chip(seed=3, size=64)               # no lat/lon, so no grid
    res = it.candidate_areas(chip, "built_up", percentile=80, min_pixels=10)
    assert res["geojson"]["features"] == [] and all(r["area_km2"] is None for r in res["regions"])


def test_min_pixels_and_max_regions_are_respected(clean):
    chip, _ = clean
    many = it.candidate_areas(chip, "bright", percentile=50, min_pixels=1, max_regions=3)
    assert len(many["regions"]) <= 3
    none = it.candidate_areas(chip, "bright", percentile=50, min_pixels=10 ** 6)
    assert none["regions"] == []


def test_empty_chip_gives_no_candidates_and_no_crash():
    chip = ds.synthetic_chip(seed=1, size=32, nodata_strip=1.0)[0]
    res = it.candidate_areas(chip, "built_up")
    assert res["regions"] == [] and res["mask_share"] == 0.0
    with pytest.raises(KeyError):
        it.candidate_areas(chip, "nope")


# ------------------------------------------------------------------ files

def test_chip_round_trips_through_a_geotiff(tmp_path, clean):
    chip, _ = clean
    p = tmp_path / "c.tif"
    it.save_chip(chip, str(p))
    back = it.load_chip(str(p))
    assert back.shape == chip.shape and back.crs == chip.crs
    assert np.allclose(back.transform, chip.transform)
    for b in core.S2_BANDS:
        assert np.allclose(back.bands[b], chip.bands[b], atol=1e-4)
    assert (back.scl == chip.scl).all()


def test_from_array_checks_the_layer_count():
    with pytest.raises(ValueError):
        it.from_array(np.zeros((3, 4, 4)))


def test_fast_percentile_matches_numpy_and_handles_empty_pixels():
    rng = np.random.default_rng(0)
    arr = rng.normal(size=(7, 9, 11)).astype("float32")
    arr[rng.random(arr.shape) < 0.35] = np.nan
    arr[:, 0, 0] = np.nan                                             # a pixel with no observation
    for q in (0, 10, 20, 50, 90, 100):
        ours = it.nan_percentile(arr, q)
        theirs = np.nanpercentile(arr, q, axis=0)
        assert np.allclose(ours, theirs, equal_nan=True, atol=1e-5), q
    assert np.isnan(it.nan_percentile(arr, 20)[0, 0])