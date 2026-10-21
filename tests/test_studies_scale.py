"""Speed with large rosters: the studies stay usable at a thousand sites."""
import time

import numpy as np

import splitsafety as SS
import studies as ST


def big_roster(n, seed=0):
    rng = np.random.default_rng(seed)
    sites = []
    for i in range(n):
        sites.append({"id": f"s{i}", "role": ["train", "test", "val"][i % 3], "region": f"r{i % 7}", "center": [float(rng.uniform(-60, 70)), float(rng.uniform(-170, 170))],
                      "box_km": float(rng.uniform(1, 8)), "notes": ""})
    return {"sites": sites}


def test_groups_and_certificate_for_a_thousand_sites_are_fast():
    doc = big_roster(1000)
    t = time.time()
    g = SS.group_summary(doc["sites"])
    c = SS.build_certificate(doc["sites"])
    assert time.time() - t < 20
    assert g["n_sites"] == 1000 and c["n_sites"] == 1000 and len(c["roster_sha256"]) == 64


def test_domain_shift_with_permutations_for_a_thousand_sites():
    rng = np.random.default_rng(1)
    rows = [{"id": i, "role": "train" if i % 2 else "test", "a": rng.normal(), "b": rng.normal(), "c": rng.normal()} for i in range(1000)]
    t = time.time()
    r = SS.shift_against_random(rows, ["a", "b", "c"], n_perm=100)
    assert time.time() - t < 30 and r["p_value"] > 0.05


def test_near_duplicates_for_three_hundred_pictures_is_fast_and_exact():
    rng = np.random.default_rng(2)
    imgs = {f"i{k}": SS._field(rng, 64) for k in range(300)}
    imgs["copy"] = imgs["i7"][::-1, :].copy()
    t = time.time()
    res = SS.near_duplicates(imgs)
    assert time.time() - t < 60
    assert [frozenset((p["a"], p["b"])) for p in res["found"]] == [frozenset(("i7", "copy"))]


def test_forecast_validation_stays_responsive_for_two_hundred_sites(tmp_path):
    import forecast as F
    rng = np.random.default_rng(3)
    rows = []
    for i in range(200):
        c = rng.uniform(0.1, 0.9)
        rows.append({"id": f"s{i}", "region": f"r{i % 5}", "lat": (i // 20) * 12.0 - 60, "lon": (i % 20) * 17.0 - 170, "clear_frac": c, "land_frac": rng.uniform(0.3, 1),
                     "yield": float(np.clip(0.1 + 0.8 * c + rng.normal(0, 0.05), 0, 1))})
    t = time.time()
    v = F.validate(rows, ["clear_frac", "land_frac"], "yield")
    assert time.time() - t < 120 and v["skill"] > 0.4
