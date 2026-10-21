import numpy as np
import pytest

import demo_scene
import splitsafety as S


def site(i, lat, lon, role="train", box=3.0, **kw):
    return {"id": i, "center": [lat, lon], "role": role, "box_km": box, **kw}


# ---------------------------------------------------------------- relations and groups

def test_relations_at_each_distance():
    a = site("a", 26.0, 50.0)
    km = 1 / 111.32
    assert S.relations(a, site("b", 26.0 + 0.5 * km, 50.0)) >= {"box", "label", "background", "ring"}      # half a km: boxes overlap
    near = S.relations(a, site("c", 26.0 + 5 * km, 50.0))
    assert "label" in near and "box" not in near                                                     # 5 km: labels overlap, boxes do not
    mid = S.relations(a, site("d", 26.0 + 50 * km, 50.0))
    assert mid == {"ring", "background"}                                                            # 50 km: in the other's background ring
    far = S.relations(a, site("e", 26.0 + 100 * km, 50.0))
    assert far == {"ring"}                                                                           # 100 km: only the outer rings meet
    assert S.relations(a, site("f", 26.0 + 160 * km, 50.0)) == set()                                 # beyond twice the outer radius


def test_groups_chain_and_levels():
    km = 1 / 111.32
    sites = [site("a", 10.0, 20.0, "train"), site("b", 10.0 + 100 * km, 20.0, "train"), site("c", 10.0 + 200 * km, 20.0, "test")]
    ring = S.overlap_groups(sites, "ring")
    assert ring["n_groups"] == 1 and ring["n_mixed_role_groups"] == 1
    label = S.overlap_groups(sites, "label")
    assert label["n_groups"] == 3 and label["n_mixed_role_groups"] == 0
    ids = {g["id"] for g in ring["groups"]}
    assert ids == {"g001"}
    assert set(ring["group_of"].values()) == {"g001"}


def test_rejected_sites_are_ignored_and_bad_level_raises():
    km = 1 / 111.32
    sites = [site("a", 0, 0), site("b", 0, 5 * km, rejected=True)]
    assert S.overlap_graph(sites) == []
    with pytest.raises(ValueError):
        S.overlap_groups(sites, "nonsense")


def test_group_summary_counts_pairs_and_groups():
    km = 1 / 111.32
    sites = [site("a", 0, 0), site("b", 0, 3 * km), site("c", 50 * km, 0), site("d", 300 * km, 0)]
    g = S.group_summary(sites)
    assert g["n_sites"] == 4
    assert g["levels"]["label"]["n_groups"] == 3          # a and b share; c and d alone
    assert g["levels"]["ring"]["n_groups"] == 2           # a, b, c join; d alone
    assert any("box" in p["relations"] for p in g["pairs"])


def test_group_ids_are_deterministic():
    km = 1 / 111.32
    sites = [site("z", 0, 0), site("y", 0, 2 * km), site("x", 30, 30)]
    a = S.overlap_groups(sites, "label")["group_of"]
    b = S.overlap_groups(list(reversed(sites)), "label")["group_of"]
    assert (a["z"] == a["y"]) and (b["z"] == b["y"]) and a["x"] != a["z"]


# ---------------------------------------------------------------- spatial dependence

def test_semivariogram_rises_for_a_smooth_field_and_flags_small_bins():
    rng = np.random.default_rng(0)
    pts = [(float(rng.uniform(0, 30)), float(rng.uniform(0, 30))) for _ in range(120)]
    smooth = [p[0] * 0.5 + p[1] * 0.2 for p in pts]
    v = S.semivariogram(pts, smooth)
    sv = [b["semivariance"] for b in v["bins"] if b["reliable"]]
    assert sv == sorted(sv) and sv[-1] > 5 * sv[0]
    noise = list(rng.normal(size=len(pts)))
    vn = S.semivariogram(pts, noise)
    flat = [b["semivariance"] for b in vn["bins"] if b["reliable"]]
    assert max(flat) < 2.0 * min(flat)
    few = S.semivariogram(pts[:5], noise[:5])
    assert any(not b["reliable"] for b in few["bins"])
    assert S.semivariogram(pts[:2], noise[:2])["bins"] == []


def test_semivariogram_skips_missing_values():
    pts = [(0, 0), (0, 1), (1, 0), (1, 1)]
    v = S.semivariogram(pts, [1, None, float("nan"), 2])
    assert v["n_sites"] == 2 and v["bins"] == []


# ---------------------------------------------------------------- domain shift

def _rows(n, shift_by_region=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        reg = "north" if i % 2 else "south"
        base = shift_by_region if reg == "north" else 0.0
        rows.append({"id": f"s{i}", "region": reg, "f1": rng.normal(base), "f2": rng.normal(base * 0.5), "f3": rng.normal()})
    return rows


def test_psi_is_zero_for_identical_and_large_for_shifted():
    rng = np.random.default_rng(1)
    a = rng.normal(size=500)
    assert S.psi(a, a) < 1e-9
    assert S.psi(a, a + 2.0) > 0.25
    assert S.psi(a[:3], a[:3]) is None
    assert S.psi_level(0.05) == "small" and S.psi_level(0.15) == "moderate" and S.psi_level(0.4) == "large" and S.psi_level(None) == "not enough data"


def test_domain_shift_ranks_the_shifted_feature_first():
    rows = _rows(300, shift_by_region=2.0)
    for r in rows:
        r["role"] = "test" if r["region"] == "north" else "train"
    out = S.domain_shift(rows, ["f1", "f2", "f3"])
    assert out["features"][0]["feature"] == "f1" and out["features"][0]["psi_level"] == "large"
    assert out["features"][-1]["feature"] == "f3" and out["features"][-1]["psi"] < 0.25
    assert "f1" in out["most_different"]


def test_region_split_shifts_more_than_random_split():
    rows = _rows(200, shift_by_region=1.5)
    region = [dict(r, role="test" if r["region"] == "north" else "train") for r in rows]
    rng = np.random.default_rng(3)
    rand = [dict(r, role="test" if k else "train") for r, k in zip(rows, rng.permutation([0, 1] * 100))]
    a = S.shift_against_random(region, ["f1", "f2"], n_perm=60)
    b = S.shift_against_random(rand, ["f1", "f2"], n_perm=60)
    assert a["observed_median_psi"] > 1.5 * b["observed_median_psi"]
    assert a["observed_median_psi"] > a["random_split_median_psi_p95"]
    assert a["p_value"] < 0.05 < b["p_value"]


def test_domain_shift_handles_missing_values_and_small_groups():
    rows = [{"id": "a", "role": "train", "f": 1.0}, {"id": "b", "role": "test", "f": None}]
    out = S.domain_shift(rows, ["f"])
    assert out["features"][0]["psi_level"] == "not enough data" and out["median_psi"] is None
    assert S.shift_against_random(rows, ["f"])["observed_median_psi"] is None


# ---------------------------------------------------------------- near duplicates

def _fields(n, seed=0):
    rng = np.random.default_rng(seed)
    return {f"i{k}": S._field(rng) for k in range(n)}


@pytest.mark.parametrize("name,fn", S.TRANSFORMS[1:])
def test_every_flip_and_rotation_is_found(name, fn):
    imgs = _fields(10, seed=4)
    imgs["copy"] = fn(imgs["i3"]).copy()
    res = S.near_duplicates(imgs)
    pairs = {frozenset((p["a"], p["b"])) for p in res["found"]}
    assert frozenset(("i3", "copy")) in pairs
    assert len(pairs) == 1


def test_recoloured_and_noisy_copies_are_found_and_unrelated_are_not():
    imgs = _fields(12, seed=5)
    rng = np.random.default_rng(9)
    imgs["bright"] = imgs["i2"] * 1.4 + 3
    z = (imgs["i5"] - imgs["i5"].min()) / np.ptp(imgs["i5"])
    imgs["gamma"] = z ** 0.6
    imgs["noisy"] = imgs["i7"] + rng.normal(scale=0.2 * imgs["i7"].std(), size=imgs["i7"].shape)
    res = S.near_duplicates(imgs)
    pairs = {frozenset((p["a"], p["b"])) for p in res["found"]}
    assert pairs == {frozenset(("i2", "bright")), frozenset(("i5", "gamma")), frozenset(("i7", "noisy"))}


def test_hist_match_ncc_and_ssim_basics():
    rng = np.random.default_rng(2)
    a, b = rng.normal(size=(32, 32)), rng.normal(size=(32, 32))
    m = S.hist_match(a, b)
    assert np.allclose(np.sort(m.ravel()), np.sort(b.ravel()))
    assert S.ncc(a, a) == pytest.approx(1.0) and abs(S.ncc(a, b)) < 0.2
    assert S.ssim(a, a) == pytest.approx(1.0, abs=1e-6) and S.ssim(a, b) < 0.2
    assert S.ncc(np.ones((4, 4)), np.arange(16.0).reshape(4, 4)) == 0.0


def test_small_downsamples_by_area_and_fills_nan():
    a = np.arange(64.0).reshape(8, 8)
    s = S.small(a, 4)
    assert s.shape == (4, 4) and s[0, 0] == pytest.approx(a[:2, :2].mean())
    b = a.copy()
    b[0, 0] = np.nan
    assert np.isfinite(S.small(b, 4)).all()


def test_near_duplicates_with_one_image_or_none():
    assert S.near_duplicates({})["found"] == []
    assert S.near_duplicates({"a": np.random.rand(32, 32)})["n_pairs"] == 0


def test_synthetic_benchmark_reports_high_detection_and_no_false_alarms():
    r = S.synthetic_benchmark(n_base=20, seed=11)
    assert r["overall_detection_rate"] >= 0.9
    assert r["false_alarms"] == 0
    assert set(r["per_kind"]) == set(S.AUGMENTATIONS)
    again = S.synthetic_benchmark(n_base=20, seed=11)
    assert again["per_kind"] == r["per_kind"]               # same seed, same answer


def test_chip_preview_from_a_demo_chip():
    chip, _truth = demo_scene.synthetic_chip(seed=1, size=64)
    p = S.chip_preview(chip)
    assert p.shape == (S.SIZE, S.SIZE) and np.isfinite(p).all()


# ---------------------------------------------------------------- certificate

def test_certificate_passes_for_a_safe_split_and_lists_what_was_not_run():
    km = 1 / 111.32
    sites = [site("a", 0, 0, "train"), site("b", 400 * km, 0, "test")]
    c = S.build_certificate(sites, tool_version="t")
    status = {x["id"]: x["status"] for x in c["checks"]}
    assert status["min_distance"] == "pass" and status["overlap_ring"] == "pass"
    assert c["verdict"] == "conditional"                       # some checks were not run
    assert {"time_gap", "spatial_dependence", "near_duplicates", "domain_shift"} <= set(c["not_run"])
    assert c["schema"].startswith("site-curator-certificate") and len(c["roster_sha256"]) == 64


def test_certificate_fails_when_roles_are_too_close():
    km = 1 / 111.32
    sites = [site("a", 0, 0, "train"), site("b", 40 * km, 0, "test")]
    c = S.build_certificate(sites)
    status = {x["id"]: x["status"] for x in c["checks"]}
    assert c["verdict"] == "fail" and status["min_distance"] == "fail" and status["overlap_ring"] == "fail" and status["overlap_background"] == "fail"
    assert c["overlap_groups"]["mixed_role_groups"]


def test_certificate_with_all_inputs_and_pass_verdict():
    km = 1 / 111.32
    sites = [site(f"s{i}", i * 400 * km, 0, "train" if i % 2 else "test") for i in range(8)]
    targets = {s["id"]: float(i) for i, s in enumerate(sites)}
    dups = {"n_images": 8, "found": [], "n_pairs": 28}
    shift = {"median_psi": 0.02, "n_large": 0, "most_different": []}
    c = S.build_certificate(sites, targets=targets, time_info={"train_end": "2023-12-31", "test_start": "2024-01-01"}, duplicates=dups, shift=shift)
    assert c["verdict"] == "pass" and c["not_run"] == []
    bad_time = S.build_certificate(sites, time_info={"train_end": "2024-02-01", "test_start": "2024-01-01"})
    assert {x["id"]: x["status"] for x in bad_time["checks"]}["time_gap"] == "fail"
    bad_date = S.build_certificate(sites, time_info={"train_end": "x", "test_start": "y"})
    assert {x["id"]: x["status"] for x in bad_date["checks"]}["time_gap"] == "not_run"


def test_certificate_flags_duplicates_across_roles_and_large_shift():
    km = 1 / 111.32
    sites = [site("a", 0, 0, "train"), site("b", 400 * km, 0, "test")]
    dups = {"n_images": 2, "n_pairs": 1, "found": [{"a": "a", "b": "b"}]}
    c = S.build_certificate(sites, duplicates=dups, shift={"median_psi": 0.5, "n_large": 3, "most_different": ["f1"]})
    st = {x["id"]: x["status"] for x in c["checks"]}
    assert st["near_duplicates"] == "fail" and st["domain_shift"] == "warn" and c["verdict"] == "fail"


def test_roster_hash_ignores_order_and_changes_with_position():
    a = [site("a", 1, 2), site("b", 3, 4)]
    assert S.roster_hash(a) == S.roster_hash(list(reversed(a)))
    b = [site("a", 1, 2.1), site("b", 3, 4)]
    assert S.roster_hash(a) != S.roster_hash(b)


def test_certificate_is_json_serialisable():
    import json
    km = 1 / 111.32
    sites = [site("a", 0, 0, "train"), site("b", 400 * km, 0, "test")]
    json.dumps(S.build_certificate(sites, targets={"a": 1.0, "b": 2.0, "c": 3.0}))


def test_pair_filter_skips_pairs_that_should_not_be_compared():
    imgs = _fields(6, seed=8)
    imgs["copy"] = imgs["i1"][:, ::-1].copy()
    assert len(S.near_duplicates(imgs)["found"]) == 1
    assert S.near_duplicates(imgs, pair_filter=lambda a, b: {a, b} != {"i1", "copy"})["found"] == []


def test_a_decoy_counts_as_the_test_side():
    km = 1 / 111.32
    sites = [site('a', 0, 0, 'train'), site('b', 30 * km, 0, 'decoy'), site('c', 400 * km, 0, 'test')]
    c = S.build_certificate(sites)
    st = {x['id']: x['status'] for x in c['checks']}
    assert st['min_distance'] == 'fail' and c['role_sides']['decoy'] == 'test'                 # decoy b is too close to train a
    assert c['min_distance_between_roles_km']['test|train']['km'] < 40
    safe = [site('a', 0, 0, 'train'), site('b', 400 * km, 0, 'decoy'), site('c', 410 * km, 0, 'test')]
    cs = S.build_certificate(safe)
    assert {x['id']: x['status'] for x in cs['checks']}['min_distance'] == 'pass'
    g = S.overlap_groups([site('a', 0, 0, 'test'), site('b', 20 * km, 0, 'decoy')], 'ring')
    assert g['n_mixed_role_groups'] == 0                                                          # test and decoy are the same side
