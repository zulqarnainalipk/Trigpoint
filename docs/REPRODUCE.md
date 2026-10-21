# Reproducing the reported results

1. **Install and check:** `pip install -r requirements.txt`, then `python server.py --check`. Every line should say ok.
2. **Tests:** `python -m pytest tests -q`. 462 tests pass (about nine minutes on a laptop); none needs the internet or an account.
3. **Demo workflow:** `python tools/make_examples.py` rebuilds `examples/` from the synthetic demo. Compare with the committed files; only timestamps and fingerprints of the certificate should differ.
4. **Public-data studies:** download the Zenodo record (doi:10.5281/zenodo.23450639), then follow `analysis/README.md`. The chip-based duplicate search needs no account; the placement study needs an Earth Engine account.
5. **Private-collection results:** these cannot be repeated without the private files. Their aggregate outputs are in `analysis/results/private_roster_aggregates.json`.

## Values to expect

| Study | Value | Tolerance |
|---|---|---|
| Public chips, near-duplicates across sites | 1,355 chips, 25 sites, 2,288 pairs passed the screen, 0 found | exact |
| Controlled copies of public chips (seed 7) | 120 of 120 found, 0 false alarms in 5,100 pairs | exact |
| Placement, public sites | see `analysis/results/placement_public_uncertainty.json` | chip-based numbers exact; gas numbers within a few per cent of the spread |

Fix the release before you cite it: the version is `1.5.0` in `server.py` and `CITATION.cff`. Tag the commit you used (`git tag v1.5.0`) so that the tag, not the branch, is what a reader runs.
