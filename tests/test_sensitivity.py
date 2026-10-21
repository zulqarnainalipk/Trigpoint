import math

import numpy as np
import pytest

import demo_scene
import imagery_tools as it
import sensitivity as S
from splitsafety import haversine_km


def blank_chip(size=100, value=0.1):
    bands = {b: np.full((size, size), value, dtype="float32") for b in it.REFLECTANCE_BANDS}
    return it.Chip(bands, np.full((size, size), 4), np.zeros((size, size), dtype="float32"))


def facility_chip(size=200, at=(100, 100), r=8):
    """A dark landscape with one bright, bare block, like a facility."""
    c = blank_chip(size, 0.08)
    rng = np.random.default_rng(0)
    for b in c.bands:
        c.bands[b] += rng.normal(0, 0.005, (size, size)).astype("float32")
    yy, xx = np.mgrid[:size, :size]
    m = (abs(yy - at[0]) < r) & (abs(xx - at[1]) < r)
    for b, v in (("B2", 0.25), ("B3", 0.27), ("B4", 0.30), ("B8", 0.32), ("B11", 0.40), ("B12", 0.38)):
        c.bands[b][m] = v
    return c


def test_offsets_cover_every_distance_and_bearing():
    o = S.offsets((1, 5), (0, 90, 180, 270))
    assert len(o) == 8
    north = [x for x in o if x["bearing"] == 0 and x["distance_km"] == 5][0]
    assert north["dn_km"] == pytest.approx(5) and abs(north["de_km"]) < 1e-9
    east = [x for x in o if x["bearing"] == 90][0]
    assert east["de_km"] == pytest.approx(1) and abs(east["dn_km"]) < 1e-6
    assert len(S.offsets()) == 4 * 8


def test_shifted_centre_moves_by_the_requested_distance():
    for lat in (0, 45, -60):
        for de, dn in ((3, 0), (0, 4), (3, 4), (-7, 2)):
            nlat, nlon = S.shifted_centre(lat, 30.0, de, dn)
            assert haversine_km((lat, 30.0), (nlat, nlon)) == pytest.approx(math.hypot(de, dn), rel=0.01)


def test_box_overlap_share():
    assert S.box_overlap_share(4, 0, 0) == 1
    assert S.box_overlap_share(4, 2, 0) == pytest.approx(0.5)
    assert S.box_overlap_share(4, 2, 2) == pytest.approx(0.25)
    assert S.box_overlap_share(4, 5, 0) == 0


def test_crop_has_a_fixed_size_and_none_outside_the_picture():
    c = blank_chip(100)
    a = S.crop(c, 10.0, 2.0)                       # 0.1 km per pixel, 20 pixels
    b = S.crop(c, 10.0, 2.0, de_km=1.3, dn_km=-0.7)
    assert a.shape == b.shape == (20, 20)
    assert S.crop(c, 10.0, 2.0, de_km=4.5) is None
    assert S.crop(c, 10.0, 2.0, dn_km=4.5) is None


def test_crop_follows_east_and_north():
    c = blank_chip(100)
    c.bands["B4"][:, 70:] = 0.9                    # the right-hand (east) part is bright
    east = S.crop(c, 10.0, 2.0, de_km=2.0)
    west = S.crop(c, 10.0, 2.0, de_km=-2.0)
    assert east.bands["B4"].mean() > west.bands["B4"].mean()
    c2 = blank_chip(100)
    c2.bands["B4"][:30, :] = 0.9                   # the top (north) part is bright
    assert S.crop(c2, 10.0, 2.0, dn_km=2.0).bands["B4"].mean() > S.crop(c2, 10.0, 2.0, dn_km=-2.0).bands["B4"].mean()


def test_chip_difference_identical_and_different():
    a = facility_chip()
    same = S.chip_difference(a, a)
    assert same["nrmse"] == 0 and same["ncc"] == pytest.approx(1.0) and same["index_change"]["bsi"] == 0
    other = facility_chip(at=(40, 40))
    d = S.chip_difference(a, other)
    assert d["nrmse"] > 1 and d["ncc"] < 0.5
    assert S.chip_difference(a, blank_chip(50)) is None            # shapes differ
    assert S.chip_difference(None, a) is None


def test_chip_difference_ignores_pixels_without_data():
    a, b = facility_chip(), facility_chip()
    b.bands["B4"][:, :] = 0.0
    for k in b.bands:
        b.bands[k][:100] = 0.0                                      # half of b has no data
    d = S.chip_difference(a, b)
    assert d is not None and d["n_px"] <= 200 * 100


def test_retained_signal_falls_with_distance():
    c = facility_chip()
    ctx, box = 20.0, 2.0                       # 0.1 km per pixel; the block is 16 pixels = 1.6 km wide, in the middle
    m = S.facility_mask(c)
    near = S.retained_signal(c, ctx, box, 0.2, 0.0, m)
    far = S.retained_signal(c, ctx, box, 1.0, 0.0, m)
    gone = S.retained_signal(c, ctx, box, 3.0, 0.0, m)
    assert near["retained"] > far["retained"] > gone["retained"] == 0
    assert S.retained_signal(c, ctx, box, 50.0, 0.0, m) is None     # outside the picture


def test_placement_study_summarises_by_distance_and_finds_a_tolerance():
    c = facility_chip()
    nat = facility_chip()
    r = S.placement_study(c, 20.0, 2.0, distances=(0.5, 1.0, 2.0, 4.0), bearings=(0, 90, 180, 270), natural_chip=nat)
    assert r["natural_change"]["nrmse"] == 0
    by = {b["distance_km"]: b for b in r["by_distance"]}
    assert by[0.5]["median_retained"] > by[2.0]["median_retained"]
    assert by[0.5]["median_ncc"] > by[4.0]["median_ncc"]
    assert by[4.0]["share_missing_facility"] == 1.0 and by[0.5]["share_missing_facility"] == 0.0
    tol = S.tolerance_km(r["by_distance"], "median_retained", 0.5)
    assert 0.5 <= tol < 2.0
    assert S.tolerance_km([{"distance_km": 1, "median_retained": None}]) == 0.0
    assert S.tolerance_km(r["by_distance"], "median_nrmse", 1.0, below_is_bad=False) >= 0.0


def test_placement_study_rejects_a_context_that_is_too_small():
    with pytest.raises(ValueError):
        S.placement_study(blank_chip(100), 1.0, 2.0)


def test_placement_study_skips_shifts_that_leave_the_picture():
    r = S.placement_study(facility_chip(), 6.0, 2.0, distances=(1.0, 5.0), bearings=(0, 90))
    far = [x for x in r["rows"] if x["distance_km"] == 5.0]
    assert all(not x["inside_context"] for x in far)
    assert [b for b in r["by_distance"] if b["distance_km"] == 5.0][0]["median_nrmse"] is None


def test_study_works_on_a_demo_scene():
    chip, _ = demo_scene.synthetic_chip(seed=3, size=160)
    r = S.placement_study(chip, 20.0, 3.0, distances=(1.0, 3.0), bearings=(0, 180))
    assert all(b["median_nrmse"] is not None for b in r["by_distance"])


def test_target_sensitivity_units_and_tolerance():
    control = {"no2": {"mean": 10.0, "sd": 4.0, "n": 100}, "ch4": {"mean": 1900.0, "sd": 20.0, "n": 50}, "co": {"mean": None, "sd": 1, "n": 5}}
    shifted = [{"distance_km": d, "bearing": b, "values": {"no2": 10.0 + s * d, "ch4": 1900.0 + (0.1 * d) * s}}
               for d in (1, 2, 5, 10) for b, s in ((0, 1), (90, -1), (180, 1), (270, -1))]
    out = S.target_sensitivity(control, shifted, tol_ratio=0.25)
    no2 = out["no2"]
    assert no2["se"] == pytest.approx(0.4) and no2["n_days"] == 100
    row5 = [r for r in no2["rows"] if r["distance_km"] == 5][0]
    assert row5["median_abs_change"] == pytest.approx(5) and row5["change_over_spread"] == pytest.approx(1.25) and row5["change_over_se"] == pytest.approx(12.5)
    assert no2["tolerance_km"] == 1                                   # change 1 = 0.25 of the spread; 2 is 0.5
    assert out["ch4"]["tolerance_km"] == 10                           # tiny change compared with the spread
    assert out["co"]["note"].startswith("not enough")


def test_target_sensitivity_ignores_missing_and_nan_values():
    control = {"no2": {"mean": 1.0, "sd": 1.0, "n": 10}}
    shifted = [{"distance_km": 1, "bearing": 0, "values": {"no2": None}}, {"distance_km": 1, "bearing": 90, "values": {"no2": float("nan")}},
               {"distance_km": 2, "bearing": 0, "values": {"no2": 1.5}}]
    out = S.target_sensitivity(control, shifted)
    assert [r["distance_km"] for r in out["no2"]["rows"]] == [2]


def test_shifted_centre_wraps_at_the_date_line_and_stays_on_the_globe():
    lat, lon = S.shifted_centre(0.0, 179.99, 10.0, 0.0)
    assert -180 <= lon < 0 and haversine_km((0.0, 179.99), (lat, lon)) == pytest.approx(10.0, rel=0.02)
    lat2, lon2 = S.shifted_centre(0.0, -179.99, -10.0, 0.0)
    assert 0 < lon2 <= 180
    assert S.shifted_centre(89.99, 0.0, 0.0, 50.0)[0] <= 90.0


def test_tolerance_sweep_grows_as_the_threshold_loosens():
    c = facility_chip()
    r = S.placement_study(c, 20.0, 2.0, distances=(0.5, 1.0, 2.0, 4.0), bearings=(0, 90, 180, 270))
    sw = S.tolerance_sweep(r['by_distance'], 'median_retained', (0.25, 0.5, 0.75))
    assert sw['0.25'] >= sw['0.5'] >= sw['0.75'] >= 0
    t = S.target_sensitivity({'no2': {'mean': 10.0, 'sd': 4.0, 'n': 100}}, [{'distance_km': d, 'bearing': 0, 'values': {'no2': 10.0 + d}} for d in (1, 2, 5, 10)])['no2']
    assert t['tolerance_sweep'] == {'0.1': 0, '0.25': 1, '0.5': 2} and t['tolerance_km'] == 1
