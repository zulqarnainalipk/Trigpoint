# Analysis scripts

These scripts produced the numbers in the TrigPoint note. They run the tool's own functions, so the results are what a user of the tool gets.

## What can be repeated by anyone (public data)

The 25 public sites and 1,355 chips of **OBSCURA-Open-25** (Zenodo, doi:10.5281/zenodo.23450639, CC BY 4.0). Download the record and keep the files in one folder (`RECORD`).

| Script | Needs | Writes | What it does |
|---|---|---|---|
| `run_placement_public.py --sites-csv RECORD/sites.csv` | Earth Engine (your own account) and `EE_PROJECT` | `placement_public_results.json` | The placement study for every public site: shifts of 1, 2, 5 and 10 km in eight directions, the picture and the four Sentinel-5P labels. About 3 to 5 minutes per site and about 6 MB downloaded per site, into a temporary folder. |
| `uncertainty_public.py` | the file above | `placement_public_uncertainty.json` | Median, interquartile range and a bootstrap interval over sites |
| `run_dup_public.py --record-dir RECORD` | the `chips_*.zip` files | `dup_public_results.json` | Near-duplicate search across sites and a controlled test with made copies of real chips (fixed seed) |

Expected values are in `results/` (made on 21 October 2026). Earth Engine's gas maps are updated and re-processed over time, so the gas numbers may drift by a little; the chip-based numbers should repeat exactly.

## What cannot be repeated (private collection)

The forecast, coordinate and split results come from a private collection of 136 industrial facilities with 7,976 collection windows. The scripts below are included so the method can be audited; they need the private files (set `OBSCURA_PRIVATE_ROOT`).

`build_tables.py`, `run_forecast.py`, `run_forecast_compare.py`, `run_split_safety.py`, `run_dup_lower.py`, `run_dup_positive_control.py`, `run_grounding.py`, `run_grounding_radius.py`, `run_uncertainty_private.py`.

Their aggregate outputs, with every site name and identifier removed, are in `results/private_roster_aggregates.json`.

## What the demo reproduces

`python tools/make_examples.py` rebuilds the example outputs in `examples/` from the synthetic demo roster. That checks the software workflow; it says nothing about real places.

## Honest limits

* Placement: 25 sites, one picture per site, medians over eight directions; gas maps are regridded and several kilometres wide.
* The 100 km registry search distance was chosen after seeing a first run at 300 km.
* No result here has been checked on a second collection.
