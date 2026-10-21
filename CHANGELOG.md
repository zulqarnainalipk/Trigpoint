# Changelog

## 1.5.0

Renamed from Site Curator to TrigPoint, with a new logo (nested squares: box, label window, ring). Internal names (Python modules, environment variables, request header, storage keys, file-format identifiers) are unchanged.

Studies (new, Tools menu)
- Overlap groups at four levels (boxes, label windows, background rings, distance rule) with group ids written into the roster on request.
- Near-duplicate chip finder (flips, turns, small shifts, recolouring) with a self-test on generated pictures.
- Shift between two roles (PSI, KS, comparison with random splits).
- Split certificate: one JSON file listing every check, with not-run checks never counted as passed.
- Forecast of yield or availability with leave-cluster-out validation, interval, region correction, a what-would-it-save table and a comparison with simpler models.
- `python server.py --check` tests an installation; `examples/` holds the output of every study on the demo roster.
- Coordinate grounding against registries you supply (CSV, GeoJSON, Wikidata result), with an error evaluation on verified sites.
- Placement study: how much the picture, the facility signal and the gas targets change when the box is shifted.
- Provenance record now says what the studies found. Synthetic demo files for every study.
- 16 new help entries (63 in all). Synthetic demo scenes now differ from site to site.

## 1.4.0

Standalone
- Runs on its own, without the collection pipeline it was first written for: a new validator replaces that pipeline's site loader, and the tool opens a demo roster by default.

Imagery (new)
- Backends: demo (synthetic, always labelled), Planetary Computer (no account), Earth Engine (your account). All give the same 14-layer chip.
- Sources: single scene, cloudless median, clear-sky layer. 5 band composites, 18 indices, 4 display transforms.
- Gap fill (none, band mean, nearest scene) with a masking test; statistics with a plain-word reading.
- Candidate-area outlines as an aid (never moves a site).
- Provenance record with roster hash, datasheet with blanks, printable report.

Help and access
- A ? button on 47 controls, a searchable feature guide, and a generated docs/FEATURE_GUIDE.md.
- Keyboard alternatives to dragging, 24 px targets, contrast checked in dark, light and high-contrast themes, reduced motion, screen reader announcements.

Safety and speed
- Host check, write header, 5 MB body cap, escaped report and escaped front-end templates, NaN-safe JSON.
- Vectorised neighbour and split checks (1000 sites analysed in seconds).

Packaging
- requirements.txt, Dockerfile, start.sh, CI workflow, and docs for methods, backends, the HTTP interface and troubleshooting.

## 1.3.0

Layout
- Three columns: site list on the left, map in the middle, details on the right. The bottom panel is removed and everything it held moved to the right bar.
- Both bars fold to a rail, resize, and persist their state and width. `[` and `]` fold them. Focus mode on `F` hides both bars and extra controls.
- Every section in both bars is a collapsible accordion with remembered state and expand-all and collapse-all buttons; information sections show a one-line summary.
- Quick edit strip on `E` with the essential fields.
- Name and role are now editable in the details bar.
- Visual refresh: type and spacing scales, card sections, brand mark, rail labels, friendly empty state, short transitions that honour reduced motion.
- Narrow windows: both bars become slide-overs; Esc closes them.
- Help and the first-run tour describe the new layout.

Changed shortcuts
- `-` and `+` change the box size (were `[` and `]`), `Z` zooms to the box (was `F`), `H` toggles the exact pixel grid (was `E`).

Fixes
- A save from the quick edit strip no longer leaves the site marked as having unsaved edits.

Tests
- `tests/test_curator_static.py` checks that every element id the scripts use exists in the HTML.

## 1.2.0

Review workflow
- Review bar, keep, reject (reversible) and skip, next unreviewed, progress bar, keyboard shortcuts.
- Filters and sort for status, role, region, priority, facility type, setting, confidence and quality.
- Information card with screening numbers, priority, quality flags and neighbours within 150 km.
- Read-only pilot roster layer; label window, background ring and split radius overlays.
- Paste coordinates or map links to jump; links to OpenStreetMap, Google Maps and Google Earth.
- Export kept, verified, all or rejected sites as JSON or CSV; merge another sites file with a preview.
- Original centre stored on the first edit; optional private comment.

Accessibility and preferences
- Skip links, landmarks, live regions, native dialogs, keyboard site list, shortcut help.
- Dark, light and high contrast themes, text size, reduced motion, narrow window layout.
- Preferences in localStorage with a reset button; first-run tour.

Backend
- New `curator_logic.py`; new endpoints `/api/reference`, `/api/analysis`, `/api/neighbors`, `/api/sites/import`; `/api/sites/export` takes optional `scope`, `format` and `comments`; `/api/sites/bulk` accepts `reject`, `unreject` and `pending`.
- Undo and redo restore the whole record and cover bulk status changes; a failed undo leaves the entry on the stack.
- Rejected sites are ignored by geometry warnings.
- Cache, backup and audit paths can be set by environment variables; the validation scratch file now goes to the system temp folder.
- Static files are served with `Cache-Control: no-cache`.

Fixes
- The fit-view and coverage buttons no longer disappear after the first preset render.
- Local storage failures no longer break layout saving.

Tests
- `tests/` with unit tests for the review logic and HTTP integration tests, all on temporary files.

## 1.1.0

Initial curator: map editing, previews, gallery, stats, backups, bulk import, audit log.

