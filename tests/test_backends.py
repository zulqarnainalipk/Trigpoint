"""backends.py with stand-ins for Earth Engine and the network. No live service is called."""
import numpy as np
import pytest

import backends as B
import core
import imagery_tools as it

LAT, LON = 27.05, 49.56


# ------------------------------------------------------------------ demo

def test_demo_is_deterministic_and_labelled_synthetic():
    d = B.DemoBackend(size=48)
    a, ma = d.fetch("s1", LAT, LON, 4)
    b, mb = d.fetch("s1", LAT, LON, 4)
    assert np.array_equal(a.bands["B8"], b.bands["B8"])
    assert ma["synthetic"] is True and ma["backend"] == "demo" and ma["n_scenes"] == 1
    c, _ = d.fetch("other", LAT, LON, 4)
    assert not np.array_equal(a.bands["B8"], c.bands["B8"])
    assert a.crs and a.transform                                      # has a grid, so overlays can be placed


def test_demo_sources_and_rank():
    d = B.DemoBackend(size=48)
    single, _ = d.fetch("s1", LAT, LON, 4, "single")
    second, _ = d.fetch("s1", LAT, LON, 4, "single", rank=2)
    med, mm = d.fetch("s1", LAT, LON, 4, "median", days=60)
    low, ml = d.fetch("s1", LAT, LON, 4, "clearsky", days=60, q=10)
    assert not np.array_equal(single.bands["B2"], second.bands["B2"])
    assert mm["n_scenes"] > 1 and ml["n_scenes"] == mm["n_scenes"] and ml["q"] == 10
    assert it.valid_share(med) > 0.9
    assert it.cloud_share(med) < it.cloud_share(single) + 0.05


def test_demo_always_available():
    assert B.DemoBackend().available()[0] is True


# ------------------------------------------------------------------ Earth Engine with a recording stand-in

class Rec:
    """Records every attribute access and call, and returns itself, so expression building can be inspected."""
    log = []

    def __init__(self, name="ee"):
        self._name = name

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return Rec(f"{self._name}.{item}")

    def __call__(self, *a, **k):
        Rec.log.append((self._name, a, k))
        return Rec(self._name + "()")


@pytest.fixture()
def fake_ee(monkeypatch):
    Rec.log = []
    ee = Rec("ee")
    monkeypatch.setattr(core, "chip_grid", lambda lat, lon, box: {**core.chip_grid_math(lat, lon, box), "geom": Rec("geom")})
    monkeypatch.setattr(core, "s2_joined", lambda geom, s, e: Rec("joined"))
    return ee


def names(log):
    return [n for n, _a, _k in log]


def test_ee_reports_why_it_is_unavailable():
    ok, why = B.EarthEngineBackend(ready=lambda: False, error=lambda: "no key").available()
    assert not ok and "no key" in why
    ok, why = B.EarthEngineBackend(ready=lambda: False).available()
    assert not ok and "docs/BACKENDS.md" in why
    assert B.EarthEngineBackend(ready=lambda: True).available()[0]


def test_ee_refuses_to_run_when_not_ready(tmp_path):
    with pytest.raises(B.BackendError):
        B.EarthEngineBackend(ready=lambda: False).fetch("s", LAT, LON, 4, dst=str(tmp_path / "x.tif"))


def test_ee_median_requests_a_clear_only_median_in_chip_layout(fake_ee, tmp_path, monkeypatch):
    sent = {}
    monkeypatch.setattr(Rec, "getInfo", lambda self: 5, raising=False)
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: sent.update(args=a))
    meta = be.fetch("s1", LAT, LON, 6, "median", days=60, dst=str(tmp_path / "m.tif"))
    log = names(Rec.log)
    assert any(n.endswith(".median") for n in log) and any(n.endswith(".updateMask") for n in log)
    assert any(n.endswith(".toUint16") for n in log) and any(n.endswith(".unmask") for n in log)
    _img, dst, desc, crs, transform, dims = sent["args"]
    g = core.chip_grid_math(LAT, LON, 6)
    assert crs == g["crs"] and transform == g["transform"] and dims == [384, 384]
    assert meta["source"] == "median" and meta["n_scenes"] == 5 and " to " in meta["date"] and meta["synthetic"] is False


def test_ee_clearsky_uses_the_requested_percentile(fake_ee, tmp_path, monkeypatch):
    monkeypatch.setattr(Rec, "getInfo", lambda self: 3, raising=False)
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: None)
    meta = be.fetch("s1", LAT, LON, 4, "clearsky", q=15, dst=str(tmp_path / "c.tif"))
    percentile_calls = [(n, a) for n, a, _k in Rec.log if n.endswith("Reducer.percentile")]
    assert percentile_calls and percentile_calls[0][1] == ([15],)
    assert meta["q"] == 15


def test_ee_composite_with_no_scenes_gives_a_clear_message(fake_ee, tmp_path, monkeypatch):
    monkeypatch.setattr(Rec, "getInfo", lambda self: 0, raising=False)
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: None)
    with pytest.raises(B.BackendError, match="No Sentinel-2 scenes"):
        be.fetch("s1", LAT, LON, 4, "median", dst=str(tmp_path / "c.tif"))


def test_ee_single_scene_uses_the_best_date_and_orbit(fake_ee, tmp_path, monkeypatch):
    picked = {}
    monkeypatch.setattr(core, "select_best_scene", lambda joined, grid, rank=1: type("S", (), {
        "getInfo": lambda self: {"best": {"date": "2025-03-04", "orbit": 7, "aoi_cloud_frac": 0.02}}})())
    monkeypatch.setattr(core, "build_day_col", lambda joined, d, o: picked.update(d=d, o=o) or Rec("day"))
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: None)
    meta = be.fetch("s1", LAT, LON, 4, "single", dst=str(tmp_path / "s.tif"))
    assert picked == {"d": "2025-03-04", "o": 7} and meta["date"] == "2025-03-04" and meta["cloud_frac"] == 0.02


def test_ee_single_scene_none_found(fake_ee, tmp_path, monkeypatch):
    monkeypatch.setattr(core, "select_best_scene", lambda *a, **k: type("S", (), {"getInfo": lambda self: {"best": None}})())
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: None)
    with pytest.raises(B.BackendError, match="No usable Sentinel-2 scene"):
        be.fetch("s1", LAT, LON, 4, "single", dst=str(tmp_path / "s.tif"))


def test_ee_unknown_source(fake_ee, tmp_path):
    be = B.EarthEngineBackend(ee_module=fake_ee, ready=lambda: True, downloader=lambda *a: None)
    with pytest.raises(B.BackendError, match="unknown source"):
        be.fetch("s1", LAT, LON, 4, "bogus", dst=str(tmp_path / "s.tif"))


# ------------------------------------------------------------------ Planetary Computer with a fake network

class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._p = payload or {}

    def json(self):
        return self._p


def item(date, cloud, baseline="05.09", tile="T39RUH"):
    assets = {k: {"href": f"https://x/{tile}/{date}/{k}.tif"} for k in list(B.PC_BANDS.values()) + ["SCL"]}
    return {"id": f"{tile}_{date}", "assets": assets,
            "properties": {"datetime": f"{date}T07:00:00Z", "eo:cloud_cover": cloud, "s2:processing_baseline": baseline}}


class FakeHttp:
    def __init__(self, items, search_status=200, fail=False):
        self.items, self.search_status, self.fail = items, search_status, fail
        self.posts, self.gets = [], []

    def get(self, url, timeout=None):
        if self.fail:
            raise ConnectionError("down")
        self.gets.append(url)
        if url.endswith("/sentinel-2-l2a"):
            return Resp(200, {"token": "sv=TOKEN"})
        return Resp(200, {})

    def post(self, url, json=None, timeout=None):
        if self.fail:
            raise ConnectionError("down")
        self.posts.append((url, json))
        return Resp(self.search_status, {"features": self.items})


def reader(href, grid):
    """Digital numbers: band k has DN 1000 + 100*k (+ cloud value from the date), scene class from the file name."""
    h, w = grid["dims"][1], grid["dims"][0]
    assert "TOKEN" in href, "the read token must be attached"
    name = href.split("?")[0].rsplit("/", 1)[1][:-4]
    if name == "SCL":
        return np.full((h, w), 4 if "2025-03-04" in href else 9, "uint16")
    k = list(B.PC_BANDS.values()).index(name)
    return np.full((h, w), 1000 + 100 * k, "uint16")


def test_pc_search_asks_for_the_box_and_cloud_limit_and_orders_by_cloud():
    http = FakeHttp([item("2025-03-04", 30), item("2025-03-09", 2)])
    be = B.PlanetaryComputerBackend(http=http, reader=reader)
    items = be.search(LAT, LON, 4, "2025-01-01", "2025-04-01")
    assert [i["properties"]["eo:cloud_cover"] for i in items] == [2, 30]
    url, body = http.posts[0]
    assert url.endswith("/search") and body["collections"] == ["sentinel-2-l2a"]
    assert body["query"]["eo:cloud_cover"]["lt"] == 60
    lon0, lat0, lon1, lat1 = body["bbox"]
    assert lon0 < LON < lon1 and lat0 < LAT < lat1


def test_pc_single_scene_scales_and_removes_the_offset():
    http = FakeHttp([item("2025-03-04", 5, baseline="05.09")])
    be = B.PlanetaryComputerBackend(http=http, reader=reader)
    chip, meta = be.fetch("s1", LAT, LON, 4, "single", days=400)
    assert meta["date"] == "2025-03-04" and meta["backend"] == "pc" and meta["synthetic"] is False
    # B1 has DN 1000; after removing the 1000 offset it is 0, so B2 (DN 1100) is 100 -> 0.01
    assert np.allclose(chip.bands["B2"], 0.01) and np.allclose(chip.bands["B1"], 0.0)
    assert chip.crs == "EPSG:32639" and chip.shape == (384, 384)
    assert (chip.scl == 4).all()


def test_pc_old_baseline_keeps_the_values_as_they_are():
    http = FakeHttp([item("2025-03-04", 5, baseline="03.00")])
    chip, _ = B.PlanetaryComputerBackend(http=http, reader=reader).fetch("s1", LAT, LON, 4, "single", days=400)
    assert np.allclose(chip.bands["B2"], 0.11) and np.allclose(chip.bands["B12"], (1000 + 100 * 11) * 1e-4)


def test_pc_offset_rule():
    assert B.reflectance_offset({"s2:processing_baseline": "04.00"}) == 1000
    assert B.reflectance_offset({"s2:processing_baseline": "05.10"}) == 1000
    assert B.reflectance_offset({"s2:processing_baseline": "03.99"}) == 0
    assert B.reflectance_offset({}) == 0 and B.reflectance_offset({"s2:processing_baseline": "x"}) == 0


def test_pc_mosaics_tiles_of_one_date():
    http = FakeHttp([item("2025-03-04", 5, tile="T39RUH"), item("2025-03-04", 8, tile="T39RVH")])
    chip, meta = B.PlanetaryComputerBackend(http=http, reader=reader).fetch("s1", LAT, LON, 4, "single", days=400)
    assert (chip.scl == 4).all() and meta["n_scenes"] == 1


def test_pc_cloud_probability_is_taken_from_the_scene_classes():
    http = FakeHttp([item("2025-03-09", 2)])
    chip, _ = B.PlanetaryComputerBackend(http=http, reader=reader).fetch("s1", LAT, LON, 4, "single", days=400)
    assert (chip.scl == 9).all() and (chip.cldprb == 100).all()
    assert it.cloud_share(chip) == 1.0


def test_pc_median_combines_scenes_and_skips_cloudy_ones():
    http = FakeHttp([item("2025-03-04", 5), item("2025-03-09", 2), item("2025-03-14", 9)])
    chip, meta = B.PlanetaryComputerBackend(http=http, reader=reader).fetch("s1", LAT, LON, 4, "median", days=400)
    assert meta["n_scenes"] == 3 and meta["source"] == "median"
    assert it.valid_share(chip) == 1.0
    assert np.allclose(chip.bands["B2"][it.valid_mask(chip)], 0.01)       # clear scene (SCL 4) supplies the values


def test_pc_errors_are_plain_messages():
    be = lambda http: B.PlanetaryComputerBackend(http=http, reader=reader)
    with pytest.raises(B.BackendError, match="No Sentinel-2 scenes"):
        be(FakeHttp([])).fetch("s", LAT, LON, 4)
    with pytest.raises(B.BackendError, match="search failed"):
        be(FakeHttp([], search_status=500)).fetch("s", LAT, LON, 4)
    with pytest.raises(B.BackendError, match="not reachable"):
        be(FakeHttp([], fail=True)).fetch("s", LAT, LON, 4)
    with pytest.raises(B.BackendError, match="unknown source"):
        be(FakeHttp([item("2025-03-04", 5)])).fetch("s", LAT, LON, 4, "bogus")


def test_pc_availability_check():
    assert B.PlanetaryComputerBackend(http=FakeHttp([])).available()[0] is True
    ok, why = B.PlanetaryComputerBackend(http=FakeHttp([], fail=True)).available()
    assert not ok and "not reachable" in why


def test_pc_token_is_requested_once():
    http = FakeHttp([item("2025-03-04", 5)])
    B.PlanetaryComputerBackend(http=http, reader=reader).fetch("s1", LAT, LON, 4, "single", days=400)
    assert sum(u.endswith("/sentinel-2-l2a") for u in http.gets) == 1


def test_registry_has_the_three_backends():
    r = B.registry()
    assert set(r) == {"demo", "ee", "pc"} and r["demo"].available()[0]
