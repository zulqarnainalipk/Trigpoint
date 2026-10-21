# Reproducing the reported results

1. **Install and check:** `pip install -r requirements.txt`, then `python server.py --check`. Every line should say ok.
2. **Tests:** `python -m pytest tests -q`. 465 tests pass (about eight minutes on a laptop); none needs the internet or an account.
3. **Demo workflow:** `python tools/make_examples.py` rebuilds `examples/` from the synthetic demo. Compare with the committed files; only timestamps and fingerprints of the certificate should differ.
4. **The reported studies:** download the Zenodo record (doi:10.5281/zenodo.23450639) and follow `analysis/README.md`. The duplicate search needs no account; the placement study and the screening need an Earth Engine account; the registry check needs the internet.

## Values to expect

| Study | Value | Tolerance |
|---|---|---|
| Public chips, near-duplicates across sites | 1,355 chips, 25 sites, 2,288 pairs passed the screen, 0 found | exact |
| Controlled copies of public chips (seed 7) | 120 of 120 found, 0 false alarms in 5,100 pairs; 120 pairs passed the screen | exact |
| Two dates of one site | 12 of 25 sites flagged | exact |
| Overlap groups, 25 sites | 2 pairs under the 150 km rule, 23 groups | exact |
| Forecast, 25 sites | see `analysis/results/public_extras_results.json` | screening numbers within a few per cent |
| Registry check | 6 of 25 sites matched | may change as Wikidata changes |
| Placement | see `analysis/results/placement_public_uncertainty.json` | chip-based numbers exact; gas numbers within a few per cent of the spread |

Fix the release before you cite it: the version is `1.5.0` in `server.py` and `CITATION.cff`. Tag the commit you used (`git tag v1.5.0`) so that the tag, not the branch, is what a reader runs.
