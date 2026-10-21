import csv
import io

import numpy as np
import pytest

import backends as B
import imagery_service as IS
import splitsafety as SS
import studies as ST


def sites_doc(n=24, seed=0):
    """Sites spread over the globe in two regions, with screening text in their notes."""
    rng = np.random.default_rng(seed)
    sites = []
    for i in range(n):
        reg = "north" if i % 2 else "south"
        clear = rng.uniform(10, 90)
        sites.append({"id": f"s{i}", "name": f"Site {i}", "role": "train" if i % 3 else "test", "region": reg,
                      "center": [(i // 6) * 25.0 - 40 + (5 if reg == "north" else 0), (i % 6) * 55.0 - 150], "box_km": 3.0, "verified": True,
                      "notes": f"Screening (2025): land {rng.uniform(40, 100):.0f}% of the 10 km window, {int(clear)} of 100 Sentinel-2 scenes clear, "
                               f"NO2 contrast {rng.uniform(0, 30):.1f} umol/m2, CO contrast 0.5 mmol/m2, fire detection days {int(rng.integers(0, 50))}."})
    return {"sites": sites}


def outcome_csv(doc, seed=1):
    rng = np.random.default_rng(seed)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "windows", "ok_windows", "aai_site", "avail_ch4"])
    for s in doc["sites"]:
        clear = float(s["notes"].split("Sentinel-2")[0].split(",")[-1].strip().split(" ")[0]) / 100
        y = min(max(0.1 + 0.8 * clear + rng.normal(0, 0.03), 0), 1)
        w.writerow([s["id"], 70, int(round(70 * y)), round(rng.normal(), 3), round(y * 0.5, 3)])
    return buf.getvalue()


@pytest.fixture()
def st(tmp_path):
    return ST.Studies(str(tmp_path / "studies"), None, {}, "t")


@pytest.fixture()
def st_img(tmp_path):
    reg = {"demo": B.DemoBackend(size=96)}
    svc = IS.ImageryService(str(tmp_path / "cache"), reg)
    return ST.Studies(str(tmp_path / "studies"), svc, reg, "t")


def test_outcomes_round_trip_and_derived_yield(st):
    doc = sites_doc()
    info = st.set_outcomes(outcome_csv(doc))
    assert info["n_rows"] == 24 and info["numeric_columns"]["windows"] == 24
    rows = st.outcomes()
    assert rows[0]["yield"] == pytest.approx(rows[0]["ok_windows"] / rows[0]["windows"], abs=1e-5)
    st.clear_outcomes()
    assert st.outcomes() == []


@pytest.mark.parametrize("text,msg", [("", "empty"), ("a,b\n1,2\n", "id"), ("id,x\n,1\n", "usable")])
def test_outcomes_reject_bad_tables(st, text, msg):
    with pytest.raises(ST.StudyError) as e:
        st.set_outcomes(text)
    assert msg in str(e.value)


def test_outcomes_ignore_duplicate_ids_and_text_in_numeric_columns(st):
    st.set_outcomes("ID,x,region\na,1,north\na,2,south\nb,oops,south\n")
    rows = {r["id"]: r for r in st.outcomes()}
    assert rows["a"]["x"] == 1.0 and rows["b"]["x"] is None and rows["b"]["region"] == "south"


def test_rows_for_roster_use_screening_text_then_the_table(st):
    doc = sites_doc()
    r0 = st.rows_for_roster(doc)[0]
    assert 0 <= r0["clear_frac"] <= 1 and 0.4 <= r0["land_frac"] <= 1 and "no2_contrast" in r0 and r0["region"] in ("north", "south")
    st.set_outcomes("id,clear_frac\ns0,0.123\n")
    assert st.rows_for_roster(doc)[0]["clear_frac"] == 0.123
    assert "clear_frac" in st.numeric_features(st.rows_for_roster(doc))
    doc["sites"][1]["rejected"] = True
    assert len(st.rows_for_roster(doc)) == 23


def test_groups_shift_and_certificate(st):
    doc = sites_doc()
    g = st.groups(doc, "ring")
    assert g["n_sites"] == 24 and set(g["summary"]["levels"]) == set(SS.LEVELS)
    sh = st.shift(doc, "train", "test", permutations=30)
    assert sh["features"] and "against_random" in sh
    cert = st.certificate(doc, {"include_shift": True, "time_info": {"train_end": "2023-01-01", "test_start": "2023-06-01"}})
    ids = {c["id"]: c["status"] for c in cert["checks"]}
    assert ids["time_gap"] == "pass" and ids["domain_shift"] in ("pass", "warn") and cert["tool_version"] == "t"
    with pytest.raises(ST.StudyError):
        st.certificate(doc, {"target_column": "nothing_here"})


def test_shift_needs_features(st):
    with pytest.raises(ST.StudyError):
        st.shift({"sites": [{"id": "a", "role": "train", "center": [0, 0], "box_km": 3, "notes": ""}]})


def test_forecast_validate_fit_and_predict(st):
    doc = sites_doc(60)
    with pytest.raises(ST.StudyError):
        st.forecast_validate(doc)
    st.set_outcomes(outcome_csv(doc))
    v = st.forecast_validate(doc)
    assert v["skill"] > 0.3 and v["n_sites"] == 60 and "effort_saved" in v
    m = st.forecast_fit(doc)
    assert m["validation"]["skill"] == v["skill"]
    pr = st.forecast_predictions(doc)
    assert len(pr["predictions"]) == 60 and all(0 <= p["forecast"] <= 1 for p in pr["predictions"].values())
    assert ST.Studies(st.dir, None, {}, "t").forecast_predictions(doc)["target"] == "yield"      # the model is on disk


def test_forecast_predictions_before_fit_say_so(st):
    with pytest.raises(ST.StudyError) as e:
        st.forecast_predictions(sites_doc(5))
    assert "fit" in str(e.value)


def test_registry_lifecycle_and_grounding(st):
    doc = {"sites": [{"id": "a", "name": "Alpha refinery", "center": [10.0, 20.0], "box_km": 3, "country": "SA", "verified": True,
                      "original_center": [10.0, 20.05]}]}
    with pytest.raises(ST.StudyError):
        st.grounding(doc)
    with pytest.raises(ST.StudyError):
        st.add_registry("bad", "name,lat,lon\n,1,1\n")
    info = st.add_registry("my reg!", "name,lat,lon,country\nAlpha refinery,10.0,20.0,SA\nOther,1,1,SA\n")
    assert info["n_entries"] == 2 and info["file"] == "registry_my_reg_.json"
    assert st.registry_list()[0]["name"] == "my reg!"
    assert st.grounding(doc)["sites"][0]["status"] in ("differ", "disagree")
    ev = st.grounding_evaluate(doc)
    assert ev["n_verified_sites"] == 1 and ev["n_with_registry_match"] == 1
    assert st.delete_registry("my reg!") and not st.delete_registry("my reg!")
    assert st.registry_list() == []


def test_corrupt_files_in_the_studies_folder_are_ignored(st):
    with open(st._path("outcomes.json"), "w") as f:
        f.write("{not json")
    assert st.outcomes() == [] and st.forecast_model() is None


# ---------------------------------------------------------------- imagery based studies (demo backend)

def test_duplicates_use_cached_pictures_and_can_fetch_missing_ones(st_img):
    doc = sites_doc(8)
    none = st_img.duplicates(doc, "demo", "single", fetch=False)
    assert none["n_images"] == 0 and len(none["missing"]) == 8
    got = st_img.duplicates(doc, "demo", "single", fetch=True, limit=5)
    assert got["n_images"] == 5 and got["fetched_now"] == 5 and len(got["missing"]) == 3 and got["synthetic"] is True
    again = st_img.duplicates(doc, "demo", "single", fetch=False)
    assert again["n_images"] == 5                                      # the earlier pictures are reused
    assert st_img.last["duplicates"] is again


def test_duplicates_find_a_flipped_copy_of_a_site(st_img):
    doc = sites_doc(3)
    # make the demo scene of s1 identical to s0 flipped by caching a flipped copy of s0's chip under s1's key
    p0 = st_img.service.clean({"backend": "demo", "source": "single", "box_km": 3.0})
    chip0, _m, _k = st_img.service.get_chip("s0", *doc["sites"][0]["center"], p0)
    import imagery_tools as it
    flipped = it.Chip({k: v[:, ::-1].copy() for k, v in chip0.bands.items()}, chip0.scl[:, ::-1].copy(), chip0.cldprb[:, ::-1].copy())
    tif, metap, _ = st_img.service.paths(st_img.service.key("s1", *doc["sites"][1]["center"], p0))
    it.save_chip(flipped, tif)
    import json
    with open(metap, "w") as f:
        json.dump({"synthetic": True}, f)
    res = st_img.duplicates(doc, "demo", "single", fetch=True)
    pairs = {frozenset((p["a"], p["b"])) for p in res["found"]}
    assert frozenset(("s0", "s1")) in pairs
    cert = st_img.certificate(doc, {"include_shift": False})
    assert {c["id"]: c["status"] for c in cert["checks"]}["near_duplicates"] in ("pass", "fail")


def test_sensitivity_with_the_demo_backend_including_targets(st_img):
    doc = sites_doc(2)
    r = st_img.sensitivity(doc, "s0", "demo", distances=(1, 3), bearings=(0, 90, 180, 270), targets=("no2", "ch4"))
    assert r["synthetic"] and r["context_km"] == pytest.approx(9.0) and r["meta"]["synthetic"]
    by = {b["distance_km"]: b for b in r["by_distance"]}
    assert by[1.0]["median_ncc"] > by[3.0]["median_ncc"] - 0.5
    assert r["targets_synthetic"] and set(r["targets"]) == {"no2", "ch4"}
    assert r["targets"]["no2"]["rows"][0]["distance_km"] == 1.0
    assert "keeps_facility" in r["tolerance_km"]


def test_sensitivity_input_checks(st_img):
    doc = sites_doc(2)
    with pytest.raises(KeyError):
        st_img.sensitivity(doc, "nope")
    with pytest.raises(ST.StudyError):
        st_img.sensitivity(doc, "s0", distances=(0,))
    with pytest.raises(ST.StudyError):
        st_img.sensitivity(doc, "s0", distances=(30,))
    with pytest.raises(ST.StudyError):
        st_img.sensitivity(doc, "s0", distances=(19,))                 # needs a 41 km picture
    with pytest.raises(ST.StudyError):
        st_img.sensitivity(doc, "s0", backend="ee")                    # not set up here


def test_features_without_enough_values_are_dropped_and_reported(st):
    doc = sites_doc(30)
    st.set_outcomes(outcome_csv(doc))
    v = st.forecast_validate(doc, features=['clear_frac', 'fire_days', 'no_such_number'])
    assert v['features'] == ['clear_frac', 'fire_days'] and v['dropped_features'] == ['no_such_number']



def test_sensitivity_refuses_sites_near_the_poles(st_img):
    doc = sites_doc(2)
    doc['sites'][0]['center'] = [85.0, 10.0]
    with pytest.raises(ST.StudyError) as e:
        st_img.sensitivity(doc, 's0', 'demo', distances=(1,))
    assert 'poles' in str(e.value)


def test_sensitivity_returns_a_tolerance_sweep(st_img):
    r = st_img.sensitivity(sites_doc(2), 's0', 'demo', distances=(1, 3), bearings=(0, 180), targets=('no2',))
    assert set(r['tolerance_sweep']['keeps_facility']) == {'0.25', '0.5', '0.75'} and set(r['targets']['no2']['tolerance_sweep']) == {'0.1', '0.25', '0.5'}


def test_registry_licence_is_kept_and_shown_in_the_grounding_result(st):
    st.add_registry('gem', 'name,lat,lon\nAlpha,10,20\n', None, 'CC BY 4.0')
    assert st.registry_list()[0]['licence'] == 'CC BY 4.0'
    doc = {'sites': [{'id': 'a', 'name': 'Alpha plant', 'center': [10.0, 20.0], 'box_km': 3}]}
    g = st.grounding(doc)
    assert g['registries'] == [{'name': 'gem', 'licence': 'CC BY 4.0', 'n_entries': 1}]
    assert st.last['grounding']['registries'][0]['licence'] == 'CC BY 4.0'
    assert st.add_registry('x', 'name,lat,lon\nB,1,1\n')['licence'] == ''
