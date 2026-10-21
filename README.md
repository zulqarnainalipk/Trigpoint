<p><img src="static/logo.svg" width="72" height="72" alt="TrigPoint logo: a filled square inside two larger squares"></p>

# TrigPoint

TrigPoint (formerly Site Curator) is a local tool for curating a list of sites on satellite imagery and checking that a benchmark built from them is sound. You open each site on a map, fix its centre and box size, look at it through several views, then keep or reject it. Every save is checked by the tool's own validator, so a file with a bad role, an out-of-range box or a repeated id is never written. Everything you do is backed up and logged.

It runs on your own computer, needs no account for the demo, and does not need any trained model.

## Start it (three commands)

```bash
pip install -r requirements.txt
python server.py
# open http://127.0.0.1:8765
```

On Windows you can double-click `start.bat` instead. The first start opens a demo roster of twelve facilities with synthetic scenes, so you can try every feature at once. Synthetic scenes are always labelled as synthetic on screen.

To open your own file, point the tool at it:

```powershell
$env:SITE_CURATOR_SITES = "C:\path\to\sites.json"
$env:SITE_CURATOR_REFERENCE = "C:\path\to\other_sites.json"   # optional, shown read-only for context
python server.py
```

The file format is described in the in-tool Help (Feature guide, "Validator") and checked by `validator.py`.

The server listens on 127.0.0.1 only and has no sign-in. It prints a warning if you change `SITE_CURATOR_HOST` to something else. The map uses Leaflet from a CDN, so it needs internet; without it the list, review buttons, filters and information card still work (open `/?nomap=1` to see that mode).

Other settings: `SITE_CURATOR_PORT`, `SITE_CURATOR_BACKUP_DIR`, `SITE_CURATOR_CACHE_DIR`, `SITE_CURATOR_CACHE_MB`, `SITE_CURATOR_AUDIT_PATH`. Imagery sources and step-by-step key setup are in [docs/BACKENDS.md](docs/BACKENDS.md).

## First five minutes

1. Press `N` to open the first site that is not reviewed. The map frames its box.
2. Press the ? beside any control to read what it does, why it matters and what it cannot do. The same text is in [docs/FEATURE_GUIDE.md](docs/FEATURE_GUIDE.md).
3. Open the Imagery section on the right. Pick a view (true colour, short-wave infrared, an index), a stretch and a source (single scene, cloudless median, clear-sky layer).
4. Press `V` to keep the site or `X` to reject it. `Ctrl+Z` undoes either.
5. Open Export, choose "Kept sites" and download the cleaned file. Open the records dialog ("Records about this roster") to save the provenance file and the datasheet.

## What is in the tool

| Area | Features |
|---|---|
| Review | keep, reject, skip, undo and redo, filters, search, bulk actions, quick edit, backups with diff and restore |
| Imagery | 5 band composites and 18 indices, four display transforms, single scene, cloudless median and clear-sky layer, gap fill (none, mean, nearest scene) with a masking test, statistics with a plain-word reading |
| Aids | candidate-area outlines (an aid for your eye, never moves a site), exact pixel grid, neighbour and overlap checks |
| Studies | overlap groups, near-duplicate chip finder, shift between roles, split certificate, yield forecast with honest validation, coordinate grounding against registries, placement study |
| Records | provenance record with a roster hash, datasheet with blanks for you to complete, printable report, audit log |
| Backends | demo (offline), Google Earth Engine (your account), Planetary Computer (no account) |
| Help | ? buttons on 63 controls, searchable guide, generated written guide |

Open **Studies** in the Tools menu for the split-safety, forecast, coordinate and placement tools; each tab has a "try the demo" path that needs no files. A suggested order for using all the parts is in [docs/WORKFLOW.md](docs/WORKFLOW.md). Method details and limits are in [docs/METHODS.md](docs/METHODS.md). The split certificate has a published schema (`docs/split_certificate.schema.json`), and `examples/` holds the output of every study on the demo roster. What was and was not checked for ease of use is in [docs/USABILITY.md](docs/USABILITY.md). Problems are in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). The HTTP interface is in [docs/API.md](docs/API.md).

## Layout

The window has three columns: the site list on the left, the map in the middle and the details of the open site on the right. The review bar sits above the map.

- Fold either bar with its chevron button or with `[` (site list) and `]` (details bar). A folded bar leaves a slim rail with a vertical label (the pending count on the left, the open site's name on the right); click the rail button to open it again. Drag the edge of a bar to resize it, or focus the edge and use the left and right arrow keys (Home resets). Whether each bar is open and how wide it is are remembered.
- Press `F` (or "Focus map" in the top bar) to hide both bars, the review bar and the map controls for a clean map. Press `F` or Esc again to bring everything back as it was.
- Every section in both bars is an accordion with a chevron: the overview, filter groups and map layers on the left, and site and review, position and box, notes and comment, facility, links, screening numbers, quality flags, neighbours and preview on the right. The double-arrow button at the top of each bar opens or closes all of its sections. Each remembers its state. Editing sections start open; the long information sections start closed with a one-line summary (for example "land 86%, clear 42%" or "4 nearby, test split").
- Press `E` (or "Quick edit") to open the quick edit strip over the map. It holds name, role, centre, box size with presets, verified, Keep, Reject and a comment, and it works while the details bar is folded. Enter saves, Esc closes it. Choosing another site updates the strip.
- On a window narrower than 860 px the bars become slide-overs that start closed; open them with the "Sites" and "Details" buttons or `[` and `]`, and close them with Esc.

## Reviewing a list of candidates

1. Press `N` (or "Next unreviewed") to open the first site that is not reviewed yet. The map frames its box.
2. Check the imagery. Drag the pin to centre the box and drag a corner square to size it. The arrow keys nudge the box, `-` and `+` step through the preset sizes and `T` applies the typical size for the facility type.
3. Open the sections of the details bar on the right (see below), or press `E` for the quick edit strip when you only need the essentials.
4. Press `V` to keep the site (saves your edits, ticks verified, opens the next unreviewed site), `X` to reject it, or `S` to skip it and come back later. `U` returns a site to not reviewed.
5. Open Export, choose "Kept sites" and download the cleaned file.

The bar above the map shows reviewed, kept, rejected and pending counts. Moving to another site saves unsaved edits first (this can be turned off in Settings), and Ctrl+Z undoes keep and reject as well as edits.

Reject is reversible. A rejected site stays in the file with `"rejected": true`, drops out of geometry warnings and neighbour checks, and is left out of the "kept" and "verified" exports. Delete removes a site for good after a confirmation.

### Filters and sort

Open "Filters and sort" in the sidebar. You can filter by status (pending, kept, rejected, skipped), role, region, priority A/B/C, facility type, setting (inland, coastal, island and so on), coordinate confidence, and quality (has a critical or warning flag, within 150 km of a pilot site, centre never moved). The search box matches id, name, country, region, facility type, setting, notes and your comment. Sort by file order, role, name, region, priority, status, confidence or distance to the nearest pilot site. Filters and sort are remembered.

### The details bar and information sections

For the open site the bar shows editable fields (name, role, centre, box, notes, comment, review buttons) and, in collapsible sections, facility type, region, setting, coordinate confidence and priority; the current and original centre with the distance moved, links to OpenStreetMap, Google Maps and Google Earth, and a button to copy the coordinates or reset to the original centre; the typical box size for the facility type (median of the other sites of that type, using verified ones when there are at least three); the screening numbers parsed from the notes (land share of the 10 km window, clear Sentinel-2 scenes, NO2 and CO contrast, fire days, priority and its flags) with a plain-word reading of each; quality flags; and every pilot site and other candidate within 150 km with what that means for the split. If pilot sites in both splits are within reach, the card says no single split fits. If they all agree, it offers "Set role to ..." when the site's role differs.

Quality flags cover a box outside 1 to 8 km, near-duplicate positions (under 2 km), overlapping 10 km label windows, a split conflict, a role that differs from the pilot split, screening flags, low coordinate confidence, and a site marked verified whose centre was never moved when confidence is not high.

### Map aids

The Map layers box toggles: the fixed 10 km label window around the site, the 30 and 75 km background ring, the 150 km split radius (with lines to neighbours), the read-only pilot roster (triangles, with their boxes), and the other candidates. The pilot roster is read from `METHANE_REFERENCE_PATH` and is never written. Kept sites are circles, pending sites diamonds, rejected sites crosses and skipped sites leaf shapes, so colour is never the only cue.

Paste `lat, lon` into the box above the map and press Enter. It also reads `27.05N 49.56E`, degrees-minutes-seconds, and Google Maps or OpenStreetMap links; pasting anywhere outside a text field works too. "Move box here" then moves the selected site's centre. The scale bar is always on. Drag handle size, snapping the box to 0.25 km, and the zoom used when a site opens are in Settings. `H` toggles the exact pixel grid.

## Accessibility

The page has a skip link, landmarks, labelled controls, visible focus and live-region announcements for review actions, saves and toasts. Dialogs are native modal dialogs with focus trapping. The site list is a keyboard list: arrow keys, Home and End move through it, Enter opens a site and Shift+Space ticks it for bulk actions. Themes are dark, light, high contrast, or follow the system. Text size runs from 80 to 160 percent, motion can be reduced, and the layout works at 200 percent zoom and on a narrow window, where the site list becomes a slide-over. Press `?` for the full shortcut list: `J` `K` `N` move, `V` `X` `S` `U` decide, `E` quick edit, `[` `]` fold the bars, `F` focus on the map, `Z` zoom to the box, `-` `+` box size, `L` `B` `R` `P` `O` `H` layers.

## Preferences

Theme, text size, basemap, default box size, handle size, zoom behaviour, snapping, advance and autosave behaviour, list density, overlays, filters and sort, accordion states, bar widths and open state, skipped sites and the last opened site are stored in the browser's localStorage. Settings has a Reset preferences button. If storage is blocked the tool works and simply forgets between sessions. Each site can also carry a private comment, saved in the file as `comment`; exports leave it out unless you tick "Include my private comments".

## Export and import

Export offers kept sites (everything not rejected), verified sites only, everything, or rejected sites only, as JSON or CSV. JSON exports are checked by the validator. "Download all" in the top bar is the unchanged full file. Tools, then "Import or merge a sites file" previews a merge before it writes anything: new sites, id clashes (skip, rename or replace), invalid rows, clamped box sizes and sites within 2 km of an existing one.

## Other features

Add a site by place name or map click, bulk import from CSV or JSON, duplicate, copy as JSON, multi-select with bulk keep, reject, pending, role and delete, compare view, gallery of cached previews, roster statistics, backup browser with diff and restore, printable roster report, measure tool, preflight and coverage checks, and the exact pixel-grid overlay computed with the same UTM maths the chips use. Live Sentinel-2 views need an Earth Engine account or the Planetary Computer backend; the demo backend works offline.

## Why the saved file is safe

Every write goes through `SiteStore._write`, which validates required fields, roles, ranges and unique ids, passes the candidate file through the validator, makes a timestamped backup in `backups/`, writes atomically and appends to `audit.log.jsonl`. Fields the tool does not know about are kept on every save, including top-level keys such as `_README`.

Fields the tool adds to a site: `rejected` (only present when true), `original_center` (the centre before the first edit) and `comment`.

## Files

| File or folder | Role |
|---|---|
| `server.py` | HTTP backend (Python standard library): the sites store, the request handler, `--check` |
| `validator.py`, `core.py` | The file check; settings, map grid and Earth Engine helpers |
| `curator_logic.py` | Review logic: screening numbers, neighbours and split groups, quality flags, export and import |
| `imagery_tools.py`, `imagery_service.py`, `backends.py`, `demo_scene.py` | Indices, composites, gap fill and candidate outlines; fetching and caching; the demo, Earth Engine and Planetary Computer backends; synthetic scenes |
| `provenance.py` | Provenance record and datasheet |
| `splitsafety.py`, `forecast.py`, `grounding.py`, `sensitivity.py`, `studies.py` | Overlap groups, duplicates, shift and certificate; forecast; coordinate grounding; placement study; the glue that runs them on a roster |
| `static/` | The page (vanilla JavaScript with Leaflet): `index.html`, `app.js`, `review.js`, `imagery.js`, `studies.js`, `help.js`, `style.css`, `logo.svg` |
| `help_content.json` | The one source of every help popup and of `docs/FEATURE_GUIDE.md` |
| `demo/`, `examples/` | Demo roster, table and registry (synthetic); the output of every study on them |
| `docs/` | Methods, backends, API, workflow, usability notes, troubleshooting, feature guide, certificate schema |
| `tests/`, `tools/` | The test suite (temporary files only); the guide generator, accessibility audit and example builder |
| `cache/`, `backups/`, `studies/`, `audit.log.jsonl` | Created when you run it: picture cache, whole-file backups, uploaded tables and registries, the change log (all ignored by git) |

Run the tests with `python -m pytest tests -q` from this folder.

## API

| Method and path | Purpose |
|---|---|
| `GET /api/health`, `/api/status` | Version, Earth Engine state, box limits, label and background sizes, split radius, reference path, feature list |
| `GET /api/sites` | The full sites document |
| `GET /api/sites/export` | The full file as a download. Optional `scope=all\|kept\|verified\|rejected`, `format=json\|csv`, `comments=0` |
| `POST /api/sites` | Create a site |
| `POST /api/sites/<id>` | Update any of `center`, `box_km`, `verified`, `rejected`, `notes`, `comment`, `name`, `role` |
| `DELETE /api/sites/<id>` | Delete a site |
| `POST /api/sites/<id>/duplicate` | Clone a site |
| `POST /api/sites/bulk_create` | Create many sites from `{items:[...]}` |
| `POST /api/sites/bulk` | `{action:"verify"\|"unverify"\|"reject"\|"unreject"\|"pending"\|"set_role", ids, role?}`; undoable |
| `POST /api/sites/bulk_delete` | `{ids}` |
| `POST /api/sites/import` | `{sites:[...], policy:"skip"\|"rename"\|"overwrite", apply:false}`; with `apply:false` it only reports |
| `POST /api/undo`, `POST /api/redo` | In-session undo and redo, whole-record, including keep, reject and bulk status changes |
| `GET /api/reference` | The read-only pilot roster |
| `GET /api/analysis` | Per-site screening, neighbours, nearest pilot, quality flags and summary counts |
| `GET /api/neighbors?lat=&lon=&exclude=` | Neighbours within the split radius of any position |
| `GET /api/warnings` | Pairwise overlap checks and roster counts |
| `GET /api/geom?lat=&lon=&box_km=` | Exact UTM pixel-grid corners |
| `GET /api/geocode?q=` | Place search through OpenStreetMap Nominatim |
| `GET /api/preview/<id>?...` | Rendered view PNG (demo, Earth Engine or Planetary Computer) |
| `GET /api/coverage`, `/api/preflight` | Approximate coverage and collection availability |
| `GET /api/report` | Printable roster report |
| `GET /api/backups`, `/api/backups/<file>`, `POST /api/backups/<file>/restore` | Backups |
| `GET /api/audit?limit=` | Recent mutation history |

## Notes

- Local only, no authentication. Do not expose the port.
- Sites closer than the split radius cannot sit in different splits; the tool warns about this but does not assign splits for you.
- The id of a site is set at creation and cannot be edited.
- Your sites file may be private. Keep it, the backups and the audit log out of anything you publish.

## Licence and how to cite

TrigPoint is licensed under the Creative Commons Attribution-NonCommercial 4.0 International licence (CC BY-NC 4.0; see `LICENSE`). You may use and adapt it for research and other non-commercial purposes if you give credit. Commercial use is not allowed without the author's permission. If you use it in research, cite it as in `CITATION.cff` (Zulqarnain Ali, ORCID 0009-0009-0281-882X).

Creative Commons licences are written for creative and data works, and the Creative Commons organisation does not recommend them for software; this licence also does not meet the Open Source Definition because it forbids commercial use. The Planetary Computer backend follows the approach of `solafune-tools` (MIT licence, Solafune Inc.); no code from it is included.

## Contributing and security

See `CONTRIBUTING.md` and `SECURITY.md`.

## Names you will still see

The tool was first called Site Curator. The visible name is now TrigPoint, but names that other things may depend on were left as they were, so nothing breaks: the Python files and modules (`server.py`, `curator_logic.py` and so on), the environment variables (`SITE_CURATOR_SITES`, `SITE_CURATOR_PORT` and the others), the `X-Site-Curator` request header, the browser storage keys, and the file-format identifiers (`site-curator-certificate/1`, `site-curator-provenance/1`). A trig point is a surveying pillar, a fixed reference point; the logo shows a box, a label window and a ring around a point.
