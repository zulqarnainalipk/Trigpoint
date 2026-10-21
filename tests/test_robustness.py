"""Hard cases: damaged caches, parallel requests, odd places, empty or cloudy pictures, big rosters, bad numbers."""
import json
import math
import os
import threading
import time

import numpy as np
import pytest

import backends as B
import core
import demo_scene as ds
import imagery_service as IS
import imagery_tools as it
import provenance as PV


class CountingBackend:
    """A backend that counts how often it is asked, and can be told what to return."""
    name = "demo"
    label = "counting"

    def __init__(self, chip_fn=None, delay=0.0):
        self.calls = 0
        self.ranks = []
        self.delay = delay
        self.chip_fn = chip_fn or (lambda **k: ds.synthetic_chip(seed=1, size=48, lat=k["lat"], lon=k["lon"], box_km=k["box_km"])[0])

    def available(self):
        return True, "ok"

    def fetch(self, **kw):
        self.calls += 1
        self.ranks.append(kw.get("rank", 1))
        time.sleep(self.delay)
        chip = self.chip_fn(**kw)
        return chip, {"backend": "demo", "source": kw["source"], "synthetic": True, "date": "2026-01-01", "n_scenes": 1}


def service(tmp_path, backend=None):
    return IS.ImageryService(str(tmp_path), {"demo": backend or CountingBackend()}, max_mb=50)


def P(svc, **kw):
    return svc.clean({"backend": "demo", "box_km": 3, **kw})


# ------------------------------------------------------------------ cache and parallel use

def test_ids_that_clean_to_the_same_text_get_different_cache_files(tmp_path):
    svc = service(tmp_path)
    a = svc.key("a/b", 1.0, 2.0, P(svc))
    b = svc.key("a_b", 1.0, 2.0, P(svc))
    assert a != b and "/" not in a and ".." not in a
    assert IS.site_token("x") == IS.site_token("x")


def test_key_changes_with_every_parameter_that_changes_the_picture(tmp_path):
    svc = service(tmp_path)
    base = svc.key("s", 1.0, 2.0, P(svc))
    for kw in ({"source": "median"}, {"days": 60}, {"box_km": 4}):
        assert svc.key("s", 1.0, 2.0, P(svc, **kw)) != base, kw
    assert svc.key("s", 1.0001, 2.0, P(svc)) != base and svc.key("s", 1.0, 2.0001, P(svc)) != base
    p1, p2 = P(svc, source="clearsky", q=10), P(svc, source="clearsky", q=20)
    assert svc.key("s", 1.0, 2.0, p1) != svc.key("s", 1.0, 2.0, p2)
    # view, stretch and fill do not change the downloaded chip
    assert svc.key("s", 1.0, 2.0, P(svc, view="swir", stretch="log", fill="mean")) == base


def test_a_damaged_cache_file_is_removed_with_a_clear_message_and_then_refetched(tmp_path):
    be = CountingBackend()
    svc = service(tmp_path, be)
    p = P(svc)
    svc.get_chip("s", 10.0, 10.0, p)
    key = svc.key("s", 10.0, 10.0, p)
    tif = svc.paths(key)[0]
    with open(tif, "wb") as f:
        f.write(b"not a tiff")
    with pytest.raises(IS.ImageryError, match="damaged"):
        svc.get_chip("s", 10.0, 10.0, p)
    assert not os.path.exists(tif)
    chip, meta, _ = svc.get_chip("s", 10.0, 10.0, p)
    assert chip.shape == (48, 48) and be.calls == 2


def test_same_picture_requested_in_parallel_is_fetched_once(tmp_path):
    be = CountingBackend(delay=0.3)
    svc = service(tmp_path, be)
    p = P(svc)
    errors = []

    def go():
        try:
            svc.get_chip("s", 10.0, 10.0, p)
        except Exception as e:                                        # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and be.calls == 1


def test_different_pictures_in_parallel_do_not_block_each_other(tmp_path):
    be = CountingBackend(delay=0.4)
    svc = service(tmp_path, be)
    t0 = time.time()
    threads = [threading.Thread(target=svc.get_chip, args=(f"s{i}", 10.0, 10.0, P(svc))) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert time.time() - t0 < 1.4 and be.calls == 4


def test_no_partial_files_are_left_after_a_fetch_and_force_replaces_the_chip(tmp_path):
    be = CountingBackend()
    svc = service(tmp_path, be)
    svc.get_chip("s", 10.0, 10.0, P(svc))
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".part")]
    svc.get_chip("s", 10.0, 10.0, P(svc), force=True)
    assert be.calls == 2


def test_donor_scene_is_second_best_and_cached(tmp_path):
    be = CountingBackend()
    svc = service(tmp_path, be)
    p = P(svc, fill="nearest")
    svc.prepared("s", 10.0, 10.0, p)
    svc.prepared("s", 10.0, 10.0, p)
    assert be.ranks == [1, 2] and be.calls == 2


def test_the_cache_is_pruned_oldest_first(tmp_path):
    svc = service(tmp_path)
    for i in range(5):
        f = tmp_path / f"f{i}.bin"
        f.write_bytes(b"x" * 400_000)
        os.utime(f, (1000 + i, 1000 + i))
    removed = svc.prune(max_mb=1)
    left = sorted(os.listdir(tmp_path))
    assert removed >= 3 and "f4.bin" in left and "f0.bin" not in left


def test_cache_can_be_cleared_while_in_use_without_crashing(tmp_path):
    svc = service(tmp_path)
    svc.get_chip("s", 10.0, 10.0, P(svc))
    for f in os.listdir(tmp_path):
        os.remove(tmp_path / f)
    chip, _, _ = svc.get_chip("s", 10.0, 10.0, P(svc))
    assert chip.shape == (48, 48)


# ------------------------------------------------------------------ odd places and sizes

@pytest.mark.parametrize("lat,lon", [(89.9, 0.0), (-89.9, 10.0), (0.0, 179.999), (0.0, -179.999), (0.0, 0.0), (-33.9, 18.4),
                                     (78.2, 15.6), (-0.0001, 0.0001)])
@pytest.mark.parametrize("box", [1.0, 8.0])
def test_every_view_renders_anywhere_on_earth_at_the_box_limits(tmp_path, lat, lon, box):
    svc = service(tmp_path, B.DemoBackend(size=48))
    for view in ("true_color", "swir", "ndvi", "aerosol"):
        path, meta = svc.render("s", lat, lon, P(svc, box_km=box, view=view))
        assert os.path.getsize(path) > 100 and meta["synthetic"] is True


def test_numbers_that_are_not_finite_are_refused():
    svc = IS.ImageryService("x_unused", {"demo": B.DemoBackend()}) if False else None
    for bad in ("nan", "inf", "-inf"):
        with pytest.raises(IS.ImageryError):
            IS.ImageryService.clean(type("S", (), {"backends": {"demo": 1}})(), {"backend": "demo", "box_km": bad})


# ------------------------------------------------------------------ empty and fully cloudy pictures

def empty_chip(**k):
    return ds.synthetic_chip(seed=1, size=40, nodata_strip=1.0, lat=k["lat"], lon=k["lon"], box_km=k["box_km"])[0]


def cloudy_chip(**k):
    return ds.synthetic_chip(seed=1, size=40, cloud=0.99, lat=k["lat"], lon=k["lon"], box_km=k["box_km"])[0]


@pytest.mark.parametrize("fn", [empty_chip, cloudy_chip])
def test_every_product_survives_an_empty_or_fully_cloudy_picture(tmp_path, fn):
    svc = service(tmp_path, CountingBackend(chip_fn=fn))
    p = P(svc)
    for view in list(it.COMPOSITES) + ["ndvi", "nbr2"]:
        path, _ = svc.render("s", 10.0, 10.0, P(svc, view=view))
        assert os.path.exists(path)
    for fill in ("mean", "nearest"):
        svc.render("s", 10.0, 10.0, P(svc, fill=fill))
    st = svc.statistics("s", 10.0, 10.0, p, ["ndvi", "aero_b1b2"], clear_only=True)
    assert st["reading"] and st["pixels_used"] >= 0
    assert svc.candidates("s", 10.0, 10.0, p, "built_up", 90.0, None, 5)["regions"] is not None
    res = svc.gapfill_test("s", 10.0, 10.0, p)
    assert "hidden_pixels" in res


def test_results_with_nan_become_valid_json_in_the_http_layer(http, srv, monkeypatch):
    monkeypatch.setattr(srv.SERVICE, "gapfill_test", lambda *a, **k: {"mean": float("nan"), "nearest": float("inf"), "x": [1, float("nan")]})
    code, j, _ = http("GET", "/api/imagery/a_site/gapfill_test?backend=demo&box_km=3")
    assert code == 200 and j == {"mean": None, "nearest": None, "x": [1, None]}


def test_fully_cloudy_composite_leaves_a_marked_hole():
    chips = [ds.synthetic_chip(seed=1, size=40, cloud=0.99)[0] for _ in range(3)]
    comp, info = it.composite(chips)
    assert info["observed_share"] < 0.9
    assert (comp.cldprb[~it.clear_mask(comp)] >= 0).all()


def test_describe_and_statistics_handle_no_pixels():
    chip = ds.synthetic_chip(seed=1, size=40, nodata_strip=1.0)[0]
    s = it.chip_statistics(chip)
    assert s["pixels_used"] == 0 and s["bands"]["B2"]["mean"] is None and math.isnan(s["cloud_share"])


# ------------------------------------------------------------------ big rosters

def test_a_thousand_sites_validate_and_analyse_quickly(tmp_path):
    import curator_logic as CL
    import validator as V
    sites = [{"id": f"s{i}", "name": f"S{i}", "role": "train", "center": [(i % 160) - 80 + 0.01 * i, ((i * 7) % 340) - 170], "box_km": 3.0,
              "verified": i % 2 == 0, "region": f"r{i % 8}", "facility_type": "refinery"} for i in range(1000)]
    t0 = time.time()
    assert V.validate_document({"sites": sites}).ok
    PV.build_provenance({"sites": sites}, [], [], now="t", env={})
    assert time.time() - t0 < 5
    t0 = time.time()
    CL.build_analysis({"sites": sites}, [], {"min_box_km": 1, "max_box_km": 8, "label_box_km": 10}, 150.0)
    assert time.time() - t0 < 20


# ------------------------------------------------------------------ parameters

def test_parameter_boundaries(tmp_path):
    svc = service(tmp_path)
    assert svc.clean({"backend": "demo", "box_km": 1.0, "days": 5, "q": 1})["days"] == 5
    assert svc.clean({"backend": "demo", "box_km": 8.0, "days": 1100, "q": 50})["q"] == 50
    for bad in ({"days": 4}, {"days": 1101}, {"q": 0}, {"q": 51}, {"box_km": 0.99}, {"box_km": 8.01}, {"box_km": "x"}):
        with pytest.raises((IS.ImageryError, ValueError)):
            svc.clean({"backend": "demo", "box_km": 3, **bad})


def test_vectorised_neighbours_and_groups_match_a_plain_loop():
    """The fast distance code gives the same answers as the simple haversine loop, on a random roster with close pairs."""
    import curator_logic as CL
    rng = np.random.default_rng(3)
    sites = [{"id": f"s{i}", "name": f"S{i}", "role": "train", "center": [float(rng.uniform(-60, 60)), float(rng.uniform(-170, 170))],
              "box_km": 3.0, "rejected": bool(i % 11 == 0)} for i in range(90)]
    for i in range(0, 40, 5):                                           # make some sites close together
        sites[i + 1]["center"] = [sites[i]["center"][0] + 0.4, sites[i]["center"][1] + 0.4]
    ref = [{"id": "p1", "role": "test", "name": "P1", "center": [sites[0]["center"][0] + 0.2, sites[0]["center"][1]]}]
    for s in sites[:25]:
        got = CL.find_neighbors(s["center"], sites, ref, s["id"], 150.0)
        want = []
        for src, pool in (("pilot", ref), ("candidate", [x for x in sites if not x.get("rejected")])):
            for o in pool:
                if o["id"] != s["id"] and CL.haversine_km(s["center"], o["center"]) < 150.0:
                    want.append((src, o["id"], round(CL.haversine_km(s["center"], o["center"]), 1)))
        assert sorted((n["source"], n["id"], n["distance_km"]) for n in got) == sorted(want), s["id"]
    groups = CL.split_groups(sites, ref, 150.0)
    # groups by brute force: connected components under the same rule
    nodes = [(("p", "p1"), ref[0]["center"])] + [(("c", s["id"]), s["center"]) for s in sites if not s.get("rejected")]
    comp = {k: k for k, _ in nodes}

    def find(x):
        while comp[x] != x:
            x = comp[x]
        return x
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if CL.haversine_km(nodes[i][1], nodes[j][1]) < 150.0:
                comp[find(nodes[i][0])] = find(nodes[j][0])
    for s in sites:
        if s.get("rejected"):
            continue
        size = sum(1 for k, _ in nodes if find(k) == find(("c", s["id"])))
        assert groups[s["id"]]["group_size"] == size, s["id"]