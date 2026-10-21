# Contributing

Thank you for looking at TrigPoint. It is a research tool (CC BY-NC 4.0, see `LICENSE`), so contributions are welcome on the same terms.

* **Reporting a problem:** open an issue with what you did, what you expected and what happened. If it involves imagery, say which backend (demo, Earth Engine or Planetary Computer). Run `python server.py --check` first and paste its output.
* **Running the tests:** `pip install -r requirements.txt`, then `python -m pytest tests -q`. They use temporary files and never touch your sites file, and no test needs the internet or an account.
* **Changing the help text:** edit `help_content.json` only, then run `python tools/make_guide.py` to rebuild `docs/FEATURE_GUIDE.md`. A test fails if the two disagree, if a sentence is too long to read easily, or if a help button has no entry.
* **Changing numbers in the documents** (thresholds, counts, routes): a test checks them against the code, so change both.
* **Keep it accessible:** every new control needs a name, a target of at least 24 by 24 pixels and a help entry; run `tools/a11y_audit.js` in the page in all three themes.
* **No learned models:** the tool is deliberately free of trained or pretrained models.
* **Please do not commit** key files, real sites files from private projects, or anything from `cache/`, `backups/` or `studies/`.
