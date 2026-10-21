# Where each number in the note comes from

All numbers are for the public record OBSCURA-Open-25 (doi:10.5281/zenodo.23450639). Files are in this folder; keys are given as `file: path`.

| Number in the note | Source |
|---|---|
| 25 sites, 15 countries, 1,355 chips, 1,825 windows, boxes 1.5 to 7.75 km, yields 47 to 99% | the record's `sites.csv`; `dup_public_results.json: n_chips, n_sites` |
| A 1 km shift keeps 62% (IQR 53 to 77%), fewer than half at 17% of sites; 2 km keeps 31%; 5 km almost none | `placement_public_uncertainty.json: facility_kept, share_sites_below_half_kept` |
| Gas change at 1 km 0.7 to 3% of the day-to-day spread; at 10 km 6 to 32% | `placement_public_uncertainty.json: gas_change_over_spread` (medians over sites) |
| Forecast: 0.103 against 0.120; difference 0.017 (-0.010 to 0.044); clear-scene share alone 0.099; R2 0.21; 23 clusters | `public_extras_results.json: forecast` |
| Registry: 6 of 25 sites matched, within 1.6 km, median 0.87 km, about 21,000 entries | `public_extras_results.json: registry` |
| Overlap: no box or label overlap; 2 pairs under 150 km (99 and 127 km); 23 groups | `public_extras_results.json: overlap` |
| Duplicates: 2,288 pairs passed the screen, none found | `dup_public_results.json: pairs_examined, found_cross_site` |
| Controlled test: 120 of 120 found; 5,100 unrelated pairs; 0 false alarms; 120 pairs passed the screen | `dup_public_results.json: positive_control` |
| Two dates of one site flagged for 12 of 25 sites | `dup_public_results.json: same_site_two_dates` |
| Figure 1 | `figure1.png`, made by `../make_figure1.py` from `placement_public_results.json` and `public_extras_results.json` |

Each file was written by the script of the same name in the parent folder (see `../README.md`). The numbers were checked against these files one by one before submission.
