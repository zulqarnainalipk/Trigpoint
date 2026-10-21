# Analysis scripts

These scripts produced the numbers in the TrigPoint note. They run the tool's own functions on the public dataset **OBSCURA-Open-25** (Zenodo, doi:10.5281/zenodo.23450639, CC BY 4.0), so anyone can repeat them. Download the record and keep its files in one folder (`RECORD`).

| Script | Needs | Writes | What it does |
|---|---|---|---|
| `run_placement_public.py --sites-csv RECORD/sites.csv` | Earth Engine (your own account) and `EE_PROJECT` | `placement_public_results.json` | The placement study for every public site: shifts of 1, 2, 5 and 10 km in eight directions, the picture and the four Sentinel-5P labels. About 3 to 5 minutes and 6 MB per site (temporary files). `--first N` starts at site N so runs can share the work. |
| `uncertainty_public.py` | the file above | `placement_public_uncertainty.json` | Median, interquartile range and a bootstrap interval over sites |
| `run_dup_public.py --record-dir RECORD` | the `chips_*.zip` files | `dup_public_results.json` | Near-duplicate search across sites; a controlled test with made copies of real chips (fixed seed); how often two dates of one site are flagged |
| `run_public_extras.py --sites-csv RECORD/sites.csv` | Earth Engine and the internet | `public_extras_results.json` | Screening numbers (clear-scene share and land share, for 2021), the leave-cluster-out forecast of yield with cluster-bootstrap intervals, overlap groups, and the Wikidata registry check against the verified centres |
| `make_figure1.py` | the results above | `results/figure1.png`, `.pdf` | Figure 1 of the note |

Expected values are in `results/` (made on 21 October 2026); `results/RESULTS.md` says which file holds each number in the note. Earth Engine's gas maps are re-processed over time and Wikidata changes, so the gas, screening and registry numbers may drift a little; the chip-based numbers should repeat exactly.

## What the demo reproduces

`python tools/make_examples.py` rebuilds the example outputs in `examples/` from the synthetic demo roster. That checks the software workflow; it says nothing about real places.

## Honest limits

* The 25 sites were chosen for the dataset by a quality score, not at random, and their boxes and yields are favourable.
* Placement: one picture per site, medians over eight directions; gas maps are regridded and several kilometres wide.
* Forecast: 25 sites, 23 clusters; too few to show a clear gain.
* Registry: six of the 25 sites matched; the starting coordinates of the record are not published, so they are not compared.
* The 100 km registry search distance was chosen after seeing a first result on a different collection.
* Nothing here has been checked on a second collection.
