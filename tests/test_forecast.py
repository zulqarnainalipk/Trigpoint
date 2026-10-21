import json

import numpy as np
import pytest

import forecast as F


def make_rows(n=90, seed=0, noise=0.05, regions=("a", "b", "c"), spread=40.0):
    """Sites on a grid far enough apart to be their own clusters, with a known linear outcome."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        clear = rng.uniform(0.1, 0.95)
        land = rng.uniform(0.3, 1.0)
        reg = regions[i % len(regions)]
        y = 0.1 + 0.7 * clear + 0.05 * land + {"a": 0.0, "b": 0.06, "c": -0.06}[reg] + rng.normal(0, noise)
        rows.append({"id": f"s{i}", "region": reg, "lat": (i // 10) * 3.0, "lon": (i % 10) * 3.0 + spread * 0, "clear_frac": clear, "land_frac": land,
                     "windows": 70, "ok_windows": int(round(70 * min(max(y, 0), 1))), "yield": float(min(max(y, 0), 1))})
    return rows


def test_clusters_join_nearby_sites_only():
    rows = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.5}, {"lat": 0, "lon": 20}, {"lat": 0, "lon": 20.4}, {"lat": 40, "lon": 0}]
    cl = F.clusters(rows, 150)
    assert cl[0] == cl[1] and cl[2] == cl[3] and len({cl[0], cl[2], cl[4]}) == 3


def test_fast_cluster_cv_matches_a_brute_force_ridge():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(40, 3))
    y = X @ [1.0, -0.5, 0.2] + rng.normal(0, 0.1, 40)
    cl = np.repeat(np.arange(20), 2)
    fast = F._oof_multi(X, y, cl, (0.1, 3.0))
    mu, sd = X.mean(0), X.std(0)
    Z = (X - mu) / sd
    for a in (0.1, 3.0):
        ref = np.zeros(40)
        for c in np.unique(cl):
            te = cl == c
            tr = ~te
            m, ym = Z[tr].mean(0), y[tr].mean()
            Zc = Z[tr] - m
            w = np.linalg.solve(Zc.T @ Zc + a * tr.sum() * np.eye(3), Zc.T @ (y[tr] - ym))
            ref[te] = (Z[te] - m) @ w + ym
        assert np.allclose(fast[a], ref, atol=1e-9)


def test_validation_beats_the_baseline_on_a_known_relation():
    v = F.validate(make_rows(), ["clear_frac", "land_frac"], "yield", region_correction=True)
    assert v["mae"] < 0.6 * v["mae_baseline"] and v["skill"] > 0.4
    assert v["spearman"] > 0.8 and v["r2"] > 0.6
    assert 0.6 <= v["interval_coverage"] <= 1.0
    assert v["n_clusters"] == 90 and len(v["sites"]) == 90


def test_region_correction_helps_when_regions_differ():
    rows = make_rows(n=150, noise=0.03)
    off = F.validate(rows, ["clear_frac", "land_frac"], "yield", region_correction=False)
    on = F.validate(rows, ["clear_frac", "land_frac"], "yield", region_correction=True)
    assert on["mae"] < off["mae"]


def test_noise_only_outcome_gives_no_skill():
    rng = np.random.default_rng(3)
    rows = make_rows()
    for r in rows:
        r["yield"] = float(np.clip(rng.normal(0.5, 0.15), 0, 1))
    v = F.validate(rows, ["clear_frac", "land_frac"], "yield", region_correction=False)
    assert v["skill"] < 0.1                       # the validation does not invent skill


def test_nearby_sites_are_held_out_together():
    """Two sites within 150 km always fall in the same fold, so a duplicate-like neighbour cannot leak its outcome."""
    rows = make_rows(n=40)
    twin = dict(rows[0], id="twin", lat=rows[0]["lat"] + 0.1)
    twin["yield"] = rows[0]["yield"]
    cl = F.clusters(rows + [twin])
    assert cl[0] == cl[-1]


def test_too_few_sites_raise():
    with pytest.raises(ValueError):
        F.validate(make_rows(8), ["clear_frac"], "yield")


def test_missing_values_are_filled_with_the_training_median_and_fire_days_use_a_log():
    rows = [{"id": "a", "clear_frac": 0.2, "fire_days": 0}, {"id": "b", "clear_frac": None, "fire_days": 99}, {"id": "c", "clear_frac": 0.8, "fire_days": ""}]
    X, fit = F.design(rows, ["clear_frac", "fire_days"])
    assert X[1, 0] == pytest.approx(0.5)
    assert X[0, 1] == 0 and X[1, 1] == pytest.approx(np.log1p(99))
    X2, _ = F.design([{"clear_frac": None, "fire_days": None}], ["clear_frac", "fire_days"], fit)
    assert X2[0, 0] == pytest.approx(0.5)


def test_final_model_predicts_with_an_interval_and_is_json_safe():
    rows = make_rows()
    m = F.fit_final(rows, ["clear_frac", "land_frac"], "yield")
    json.dumps(m)
    hi = F.predict(m, {"clear_frac": 0.9, "land_frac": 0.9, "region": "b"})
    lo = F.predict(m, {"clear_frac": 0.1, "land_frac": 0.5, "region": "b"})
    assert hi["forecast"] > lo["forecast"] + 0.3 and hi["low"] <= hi["forecast"] <= hi["high"]
    assert 0 <= lo["low"] and hi["high"] <= 1
    partial = F.predict(m, {"clear_frac": 0.9})
    assert partial["missing_features"] == ["land_frac"]
    assert F.predict(m, {"clear_frac": 0.9, "land_frac": 0.9, "region": "never seen"})["region_adjustment"] == 0.0
    assert m["region_bias"]["b"] > m["region_bias"]["c"]


def test_effort_saved_saves_more_than_it_loses_for_a_good_forecast():
    rows = make_rows()
    fc = {r["id"]: r["yield"] for r in rows}                           # a perfect forecast
    out = F.effort_saved(rows, fc)
    for r in out["rows"]:
        assert r["windows_saved_share"] == pytest.approx(r["drop_share_of_sites"], abs=0.03)    # same windows per site here
        assert r["samples_lost_share"] < r["windows_saved_share"]
    assert out["rows"][0]["sites_dropped"] == 4
    bad = F.effort_saved(rows, {r["id"]: -r["yield"] for r in rows})    # a backwards forecast drops the best sites first
    assert bad["rows"][-1]["samples_lost_share"] > bad["rows"][-1]["windows_saved_share"]


def test_ridge_shrinks_with_alpha():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(50, 2))
    y = X[:, 0] + rng.normal(0, 0.1, 50)
    w1 = np.abs(F.ridge_fit(X, y, 0.01)["w"]).sum()
    w2 = np.abs(F.ridge_fit(X, y, 30)["w"]).sum()
    assert w2 < w1 / 2


def test_region_bias_is_shrunk_towards_zero():
    resid = np.array([0.1] * 2 + [0.1] * 40)
    b = F._region_bias(["small"] * 2 + ["big"] * 40, resid)
    assert abs(b["small"]) < abs(b["big"]) < 0.1


def test_validate_returns_json_safe_numbers():
    json.dumps(F.validate(make_rows(), ["clear_frac"], "yield"))


def test_small_samples_carry_a_warning():
    assert F.validate(make_rows(20), ["clear_frac"], "yield")["warning"]
    assert F.validate(make_rows(90), ["clear_frac"], "yield")["warning"] is None



def test_compare_models_lists_the_baseline_each_number_and_all_together():
    rows = make_rows(60)
    out = F.compare_models(rows, ["clear_frac", "land_frac"], "yield")
    names = [m["model"] for m in out["models"]]
    assert names == ["Guess the training average", "clear_frac alone", "land_frac alone", "All numbers together"]
    assert out["best_single"] == "clear_frac alone" and out["reading"]
    assert out["models"][1]["mae"] < out["models"][0]["mae"] and out["models"][1]["skill"] > 0.3
    one = F.compare_models(rows, ["clear_frac"], "yield")
    assert [m["model"] for m in one["models"]] == ["Guess the training average", "clear_frac alone"] and one["reading"] is None


def test_forecasts_of_numbers_outside_zero_to_one_are_not_squashed():
    rows = make_rows(60)
    for r in rows:
        r['level'] = 20 + 50 * r['yield']                          # a gas-level-like number, far above 1
    v = F.validate(rows, ['clear_frac', 'land_frac'], 'level', region_correction=False)
    assert max(s['forecast'] for s in v['sites']) > 5 and v['skill'] > 0.3
    m = F.fit_final(rows, ['clear_frac', 'land_frac'], 'level')
    p = F.predict(m, {'clear_frac': 0.9, 'land_frac': 0.9, 'region': 'a'})
    assert p['forecast'] > 20 and p['high'] > p['forecast'] > p['low'] > 1
    assert m['bounds'] == [None, None] and F.fit_final(rows, ['clear_frac'], 'yield')['bounds'] == [0.0, 1.0]
    json.dumps(m)
