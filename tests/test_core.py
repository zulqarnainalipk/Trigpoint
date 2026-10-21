"""core.py: grid maths, windows, retry, and that importing it needs no outside project or Earth Engine."""
import math

import pytest

import core


def test_utm_zones_north_and_south():
    assert core.utm_epsg(27.0, 49.5) == 32639          # zone 39 north
    assert core.utm_epsg(-33.9, 18.4) == 32734         # zone 34 south
    assert core.utm_epsg(0.0, -179.99) == 32601
    assert core.utm_epsg(0.0, 179.99) == 32660
    assert core.utm_epsg(-0.0001, 10.0) == 32732       # just south of the equator


def test_grid_is_square_snapped_and_has_the_right_size():
    g = core.chip_grid_math(27.05, 49.56, 6.0)
    x0, y0, x1, y1 = g["bounds_utm"]
    assert g["dims"] == [384, 384] and g["epsg"] == 32639
    assert math.isclose(x1 - x0, 6000) and math.isclose(y1 - y0, 6000)
    assert math.isclose(g["gsd"], 6000 / 384)
    # origin is a whole number of pixels
    assert math.isclose((x0 / g["gsd"]) % 1, 0, abs_tol=1e-6) or math.isclose((x0 / g["gsd"]) % 1, 1, abs_tol=1e-6)
    assert g["transform"][0] == g["gsd"] and g["transform"][4] == -g["gsd"]


def test_the_site_centre_lies_inside_its_grid():
    from rasterio.warp import transform
    for lat, lon, box in [(27.05, 49.56, 6), (-33.9, 18.4, 1.5), (65.0, -170.0, 8), (0.01, 0.01, 3), (-0.01, 179.9, 2)]:
        g = core.chip_grid_math(lat, lon, box)
        x, y = transform("EPSG:4326", g["crs"], [lon], [lat])
        x0, y0, x1, y1 = g["bounds_utm"]
        assert x0 <= x[0] <= x1 and y0 <= y[0] <= y1


def test_pixel_count_can_be_set():
    assert core.chip_grid_math(10, 10, 4, chip_px=64)["dims"] == [64, 64]


def test_windows_cover_the_range_in_steps():
    w = core.generate_windows("2022-01-01", "2022-02-01")
    assert w[0] == "2022-01-01" and len(w) == 6 and w[1] == "2022-01-06"
    assert core.generate_windows("2022-01-01", "2022-01-03") == []
    assert len(core.generate_windows("2022-01-01", "2022-01-11", days=2)) == 5


def test_haversine():
    assert core.haversine_km((0, 0), (0, 0)) == 0
    assert math.isclose(core.haversine_km((0, 0), (0, 1)), 111.19, abs_tol=0.1)
    assert math.isclose(core.haversine_km((10, 10), (10, 11)), core.haversine_km((10, 11), (10, 10)))


def test_retry_succeeds_after_failures_and_gives_up():
    calls, naps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("temporary")
        return "ok"

    assert core.with_retry(flaky, "t", tries=4, base_sleep=1, sleep=naps.append) == "ok"
    assert len(calls) == 3 and len(naps) == 2 and naps[1] > naps[0]

    def always():
        raise ValueError("no")

    with pytest.raises(ValueError):
        core.with_retry(always, "t", tries=2, base_sleep=0, sleep=lambda s: None)


def test_chip_layout_constants():
    assert core.CHIP_BANDS == ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12", "SCL", "CLDPRB"]
    assert len(core.CHIP_BANDS) == 14


def test_slugify():
    assert core.slugify("  Ras Tanura (Refinery)! ") == "ras_tanura_refinery"
    assert core.slugify("???") == "site"


def test_core_imports_without_earth_engine_or_the_pipeline():
    import sys
    assert "pipeline" not in sys.modules
    with pytest.raises(AttributeError):
        core.not_a_thing
