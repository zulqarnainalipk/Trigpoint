# TrigPoint build checklist

Scope: the **tool only** (no note writing). Goal: a tool that is complete, tested from every angle I can reach, accessible, easy and pleasant to use, documented inside the tool, and ready to publish.

Key: `[x]` done and checked, `[~]` written but not yet tested, `[ ]` not started, `[!]` cannot be verified here (needs you, an account, or a real device).

Last updated: 18 October 2026 (features 8 to 16 built, 277 automated tests pass, browser and accessibility checks done except the items marked [!]).

---

## A. Foundations (so the tool stands alone)

- [x] A1. `validator.py`: roster rules with no outside dependency, command line and import use
- [x] A2. `core.py`: settings, geometry, Earth Engine helpers (replaces the import of the competition pipeline)
- [x] A3. `imagery_tools.py`: transforms, indices, statistics, gap fill, composites, candidate areas
- [x] A4. `server.py` switched from `pipeline` to `core`, `validator` and `imagery_tools`; no `pipeline` import left anywhere
- [x] A5. Fix garbled characters (mojibake) in `server.py`, `app.js`, `review.js` and `static` text
- [x] A6. Demo mode: a clearly labelled synthetic scene generator so every imagery feature works with no account
- [x] A7. Demo roster of public facilities (no private data) and a launch file that opens it
- [x] A8. Existing 36 tests pass again after the switch (18 currently error because the copy has no pipeline)

## B. Features to build (items 8 to 16 of the proposal)

For each feature: code, unit test, API test, interface control, help entry, documentation line.

| # | Feature | Code | Unit test | API | UI | Help popup | Docs |
|---|---|---|---|---|---|---|---|
| 8 | Cloudless median composite (date range, scene count, valid share) | [x] | [x] | [x] | [x] | [x] | [x] |
| 9 | Clear-sky layer (low percentile over preceding weeks) | [x] | [x] | [x] | [x] | [x] | [x] |
| 10 | Index and statistics view set (composites, indices, statistics panel with formulas) | [x] | [x] | [x] | [x] | [x] | [x] |
| 11 | Display transforms (percentile, log, square root, linear) | [x] | [x] | [x] | [x] | [x] | [x] |
| 12 | Gap-fill (band mean, nearest-in-time with band-mean shift) and the masking experiment | [x] | [x] | [x] | [x] | [x] | [x] |
| 13 | Optional keyless backend (Planetary Computer STAC, with `solafune-tools` credited) | [x] | [x] | [x] | [x] | [x] | [x] |
| 14 | Candidate-area overlay (aid only; never moves the pin) | [x] | [x] | [x] | [x] | [x] | [x] |
| 15 | Provenance record and datasheet export | [x] | [x] | [x] | [x] | [x] | [x] |
| 16 | Built-in validator panel, command line, container recipe | [x] | [x] | [x] | [x] | [x] | [x] |

Cross-cutting interface work:

- [x] B1. "Imagery" section in the details bar: source (single scene, median, clear-sky), backend, date range, view, stretch, gap-fill, fetch button with step-by-step progress
- [x] B2. Statistics panel with plain-word reading of each number
- [x] B3. Candidate-area controls (kind, threshold or percentile, minimum size) and a list with a "show on map" action per region
- [x] B4. Export menu: provenance record (JSON) and datasheet (Markdown)
- [x] B5. Validator panel ("Check this file") with errors and warnings in plain words
- [x] B6. Settings: backend choice, default stretch, default view
- [x] B7. Status badge shows which backends are ready (Earth Engine, Planetary Computer, demo)

## C. Help inside the tool

- [x] C1. One content file (`help_content.json`) is the single source for popups, the guide dialog and the written guide
- [x] C2. A "?" button beside every feature control and every section title; opens a popup with: what it is, why it matters, how it works, how to use it, what it cannot do, an example
- [x] C3. Plain-language text first, with an "Expert details" expander (formulas, sources, limits)
- [x] C4. "Feature guide" dialog: searchable list of all features, opens the matching popup
- [x] C5. First-run tour updated to include the imagery tools
- [x] C6. Test: every control with a "?" has a help entry; every help entry is reachable; no empty or placeholder text
- [x] C7. Generated `docs/FEATURE_GUIDE.md` from the same file (so tool and docs never disagree)
- [ ] C8. Plain-language check of all help text (short sentences, no jargon without a gloss)

## D. Tests

### D1. Automated unit tests
- [x] `validator`: every rule, good and bad input, CLI exit codes, JSON output, unreadable file
- [x] `core`: grid maths against hand-computed values, EPSG zones (north and south), `with_retry` (success, retry, give up), `generate_windows`
- [x] `imagery_tools`: each index against a hand-computed value; transforms; statistics on known distributions; gap fill recovers a known hidden block; masking experiment ordering; composites (median and clear-sky) on synthetic scenes with known answers; candidate areas on a synthetic scene with known shapes; GeoJSON outlines inside the chip
- [x] Backends: Earth Engine builders with a recording stub (the expressions requested are the ones intended); Planetary Computer backend with mocked HTTP; demo backend determinism
- [x] `provenance`: record contents, datasheet sections complete, hash of the roster, round trip
- [x] Help content: schema, coverage, no duplicates

### D2. API and integration tests
- [x] Every new endpoint: success, bad input, missing backend, large input
- [x] The 36 existing API tests still pass
- [x] Concurrency: two writes at once keep the file valid (existing lock)
- [x] Atomic write and backup still behave after the validator switch
- [x] Undo and redo still restore the whole record

### D3. Edge cases and abuse
- [x] Empty roster; one site; 1,000 sites (speed)
- [x] Coordinates at the poles, the date line, the equator, both hemispheres
- [x] All-no-data chip; all-cloud chip; single-pixel regions; chip with no grid
- [x] Corrupt cache file; interrupted download (`.part`); full disk message
- [x] Path traversal in file and backup names; oversized request bodies; malformed JSON; non-UTF-8 input
- [x] The server stays bound to 127.0.0.1; no secrets written to the audit log or caches

### D4. Browser tests (run the real page)
- [x] Page loads with no console errors in demo mode (and with the map offline)
- [x] Every new control works with mouse, keyboard and touch-size targets
- [x] Fetch, switch view, switch stretch, fill gaps, show statistics, show candidates, export: whole flow in demo mode
- [x] Narrow window (about 375 px), tablet width, 200 percent zoom
- [x] Dark, light, high-contrast themes; text size 80 and 160 percent; reduced motion
- [~] Reload keeps preferences (checked); blocked storage still works (not yet tested)

## E. Accessibility tests

- [x] E1. Every control has an accessible name; icon buttons have text labels; "?" buttons say which feature they explain
- [x] E2. Keyboard: every function reachable by Tab, Enter, Space, arrows and Esc; no keyboard trap; logical focus order
- [x] E3. Popups: focus moves in, stays inside, returns to the "?" button on close; Esc closes; background inert
- [x] E4. Visible focus indicator on every control in all themes
- [x] E5. Colour contrast computed for every text and control colour pair in all themes (WCAG AA 4.5:1 text, 3:1 large text and controls)
- [x] E6. Meaning is never carried by colour alone (candidate outlines, statuses, map symbols)
- [x] E7. Live-region announcements for fetch progress, results and errors
- [x] E8. Images have text alternatives; the preview caption states date, source, cloud share
- [x] E9. Statistics and candidate lists are real tables or lists with headers
- [x] E10. Targets at least 24 by 24 px; works at 200 percent zoom without horizontal scroll (apart from the map)
- [x] E11. Reduced motion respected for every new animation
- [ ] E12. Language and reading level of help text checked
- [!] E13. Real screen reader pass (NVDA or VoiceOver): I can check the markup and the live regions, not what a screen reader says

## F. Ease of use and engagement tests

- [ ] F1. A first-time user can do the main job (open demo, fetch, change view, read statistics, find candidates, export) following only on-screen hints
- [x] F2. Every error message says what happened and what to do next (no stack traces, no jargon)
- [ ] F3. Every long action shows progress and can be cancelled or left safely
- [x] F4. Empty states explain the next step
- [x] F5. Defaults are sensible: a user who changes nothing gets a good result
- [x] F6. Undo for destructive actions; confirmations only where something is lost
- [x] F7. Terms are consistent in buttons, help and docs (one name per thing)
- [ ] F8. Count of clicks for the five most common tasks, compared with before
- [ ] F9. Small rewards for progress that are not noisy (review progress, "all sites checked", clear summary at the end)
- [x] F10. Demo mode labelled "synthetic" everywhere it shows, so no one mistakes it for real imagery

## G. Documentation

- [x] G1. README: what it is, install in three commands, first five minutes, every feature, every setting, every shortcut
- [x] G2. `docs/FEATURE_GUIDE.md` (generated), `docs/BACKENDS.md` (Earth Engine, Planetary Computer, demo), `docs/METHODS.md` (formulas, composite and gap-fill methods, candidate areas, limits), `docs/API.md`
- [x] G3. FEATURES.md and CHANGELOG updated; version 1.4.0
- [x] G4. Troubleshooting page (no map, no Earth Engine, port busy, blocked storage, big files)
- [ ] G5. Every number in the docs checked against the code or a test

## H. Review passes

- [x] H1. Code review of every changed file (correctness, errors, resource use)
- [x] H2. Security review: local-only binding, input validation, file paths, no secrets in logs, dependency list, cross-site requests to the local server
- [x] H3. Performance check: large rasters, many sites, repeated fetches, cache size limits
- [ ] H4. Licence and terms: `solafune-tools` (MIT) credit, basemap and place-search terms, no copied competition text or data, a licence for the tool itself (your choice)
- [x] H5. Human-style pass on all help text and documentation (no em dashes, plain wording)
- [x] H6. Clean up: remove `__pycache__`, test leftovers, stray backups; no private paths in committed files

## I. Publishing readiness

- [x] I1. `requirements.txt` with minimum versions; `pyproject.toml` or run instructions
- [!] I2. `Dockerfile` written; not built or run here (no Docker in this environment)
- [x] I3. `start.bat` and a `start.sh`; works from a clean folder with the demo roster
- [x] I4. GitHub Actions workflow that runs the tests
- [ ] I5. `CITATION.cff`, version tag, licence file (needs your choice of licence)
- [ ] I6. Final full test run from a clean checkout; checklist re-read and every box resolved or explained

## K. Studies (proposal features 1 to 7), added in 1.5.0

| # | Feature | Code | Unit tests | API tests | Window | Help | Docs | Measured on the real roster |
|---|---|---|---|---|---|---|---|---|
| 1 | Forecast of yield and availability (with comparison against simpler models) | [x] | [x] | [x] | [x] | [x] | [x] | [x] 120 sites, leave-cluster-out |
| 2 | Coordinate grounding against registries | [x] | [x] | [x] | [x] | [x] | [x] | [x] 134 verified sites against Wikidata (51 matched) |
| 3 | Placement study (picture, facility signal, gas targets) | [x] | [x] | [x] | [x] | [x] | [x] | [x] 10 sites, Earth Engine |
| 4 | Split certificate (with published schema) | [x] | [x] | [x] | [x] | [x] | [x] | [x] roster certificate |
| 5 | Overlap groups at four levels | [x] | [x] | [x] | [x] | [x] | [x] | [x] 136 sites |
| 6 | Near-duplicate chip finder (self-test, positive control on real chips) | [x] | [x] | [x] | [x] | [x] | [x] | [x] 4,439 chips |
| 7 | Shift between roles (PSI, KS, random-split comparison) | [x] | [x] | [x] | [x] | [x] | [x] | [x] 120 sites |

- [x] K1. Input validation on every studies route (20 bad-input cases give a plain 400)
- [x] K2. Scale: 1,000 sites for groups, certificate and shift; 300 pictures all-pairs; forecast for 200 sites (about a minute)
- [x] K3. Accessibility audit of every Studies tab in three themes: zero problems; keyboard tabs; phone width; 160 per cent text
- [x] K4. `python server.py --check`, worked examples (`examples/`), workflow guide, usability notes, review rounds (`tool_note/TOOL_REVIEW.md`)
- [x] K5. Documents checked against the code by tests (help count, routes, version, thresholds, dashes)
- [x] K6. Registry evidence for grounding: Wikidata, 7 classes, 51 of 134 sites matched
- [!] K7. A study with people; a real screen reader; Docker; a real Python 3.10; Planetary Computer
- [x] K8. LICENSE (CC BY-NC 4.0, short notice with the link to the legal code) and CITATION.cff (Zulqarnain Ali, as in the data paper)

## J. Things I cannot confirm here

- [x] J1. Live Earth Engine fetches: run once on 18 Oct 2026 with the competition service account (6 single scenes, 2 medians, 2 clear-sky layers, 1 gap-fill test, all succeeded, 14.5 MB, cache deleted)
- [x] J2. Live Planetary Computer fetches: run on 21 Oct 2026 (2 single scenes, 1 median of 12 scenes, 13 MB, cache deleted); the availability check was made more patient after it timed out once
- [!] J3. A real screen reader and a real touch device
- [!] J4. Behaviour on macOS or Linux (I only have Windows)
- [!] J5. Whether the basemap and place-search providers allow your intended use

---

## Progress log

- 19 Oct 2026: features 1 to 7 built and measured (Studies window, 16 more help entries, schema, examples, self-check). Four review rounds are in `tool_note/TOOL_REVIEW.md`. Earth Engine was run live for the placement study (10 sites, 63.6 MB, cache deleted). Open: registry evidence, a study with people, LICENSE and CITATION.

- 18 Oct 2026 (latest): security pass on the page (all user text in templates now escaped; markup site name checked in the real page; new test guards this), warning when the server is not on loopback, README rewritten (no pipeline references), docs/METHODS, BACKENDS, API, TROUBLESHOOTING written, CHANGELOG 1.4.0, requirements.txt, Dockerfile, start.bat/start.sh, CI workflow, .gitignore. Page checked at text size 160 percent, reduced motion, no-map mode and tablet width: no overflow, no console errors from the tool. 277 tests pass. Still open: reading-level check of help text (C8, E12), a first-time-user walkthrough (F1), cancel for long fetches (F3), click counts (F8), small progress rewards (F9), checking every number in the docs (G5), licence and CITATION (your choice), blocked-storage test, clean-checkout run (I6).

- 18 Oct 2026 (later): built ackends.py, imagery_service.py, provenance.py, help_content.json (47 entries), static/help.js, static/imagery.js, the Imagery panel, dialogs and the server routes. Server no longer imports the competition pipeline: the 36 old tests pass again, 242 tests pass in all. Browser checks found and fixed: a page-level data-help attribute that made every click open help; two unnamed inputs; drag-only bar resizing (Settings sliders added); light-theme contrast 4.3 (now fixed); selects that overflowed a phone screen. Real keyboard test of the guide and help dialogs passed.

- 18 Oct 2026: baseline measured: 18 tests pass, 18 error (the copy cannot import the pipeline). Wrote `validator.py`, `core.py`, `imagery_tools.py` (not yet tested). Browser pane can load the page through a preview server.
