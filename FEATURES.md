# TrigPoint feature list

This file tracks what exists and what is deliberately left out. See README.md for how to use each feature and CHANGELOG.md for the history.

## Layout

- Three columns: site list, map, details bar. The bottom panel is gone and the map gets the freed space.
- Both bars fold to a slim rail by button or by `[` and `]`, resize by dragging or with arrow keys on the edge handle, and remember their state and width.
- Focus mode (`F`) hides both bars and extra controls for a clean map, then restores them.
- Every section in both bars is an accordion with a chevron, remembered state, and expand-all and collapse-all buttons. Long information sections carry a one-line summary when collapsed.
- Quick edit strip (`E`) with name, role, centre, box and presets, verified, keep, reject and comment; works with the details bar folded.
- Type scale, spacing scale, card-style sections, short transitions that stop under reduced motion, slide-over bars on narrow windows.

## Review speed

- Review bar above the map with previous, next and next unreviewed, and keep, reject, skip and unreview buttons, each with a keyboard shortcut.
- Progress bar with kept, rejected and pending counts, plus the number of skipped sites.
- Keep saves your edits, sets verified and opens the next unreviewed site. Reject is a reversible flag. Skip is remembered in the browser.
- Moving to another site saves unsaved edits first (setting).
- Undo and redo cover keep, reject and bulk status changes, and restore the whole record.
- Filters for status, role, region, priority, facility type, setting, coordinate confidence and quality; free-text search over id, name, country, notes and comment; eight sort orders; region group headers in the list.
- Typical box size for the facility type, from the median of other sites of that type.
- Shortcut changes in 1.3.0: `-` and `+` change box size (was `[` and `]`), `Z` fits the map to the box (was `F`), `H` toggles the exact grid (was `E`).
- Autosave status indicator in the top bar.

## Information

- Information card with facility facts, priority, original and current centre, map links, screening numbers parsed from the notes with a plain-word reading, quality flags and neighbours within 150 km.
- Neighbour list for the pilot roster and other candidates, with the split each one forces, a split conflict warning, and a one-click role fix.
- Quality flags: box range, near-duplicate position, overlapping label windows, split conflict, role versus pilot split, screening flags, low confidence, verified but centre never moved.
- Original centre stored on the first edit (`original_center`), and an optional private comment per site.

## Map aids

- Fixed 10 km label window, 30 and 75 km background ring and 150 km split radius, each switchable.
- Read-only pilot roster layer with its boxes, loaded from `METHANE_REFERENCE_PATH` and never written.
- Paste `lat, lon`, hemisphere letters, degrees-minutes-seconds or a map link to jump, then move the box centre there.
- Links to OpenStreetMap, Google Maps and Google Earth, copy coordinates, scale bar, adjustable handle size, snap to 0.25 km, preset sizes, zoom behaviour setting.
- Marker shapes for kept, pending, rejected, skipped and pilot sites.
- Existing: drag pin, drag corners, exact UTM pixel grid, marker clustering, measure tool, basemap toggle, live Sentinel-2 preview with band views (needs Earth Engine).

## Accessibility

- Skip links, landmarks, labelled controls, visible focus, live-region announcements, native modal dialogs with focus trap.
- Keyboard-operable site list with roving focus, shortcut help overlay (`?`), keyboard-resizable editor panel.
- Dark, light and high contrast themes, status shown by shape and text as well as colour, text size 80 to 160 percent, reduced motion, layout for 200 percent zoom and narrow windows.

## Personalisation and ease of use

- Preferences in localStorage (always in try and catch): theme, text size, basemap, default box size, handle size, zoom, snap, advance, autosave, density, motion, overlays, filters, skipped sites, last opened site. Reset button.
- First-run tour, help panel, tooltips, empty states, confirm dialogs only for destructive actions.
- Export kept, verified, all or rejected sites as JSON or CSV, with or without comments. Merge another sites file with a preview and a skip, rename or replace policy.

## Existing features kept

Add, edit, duplicate and delete sites, place search, bulk import from CSV or JSON, multi-select bulk actions, compare view, gallery, roster statistics, backup browser with diff and restore, printable roster report, preflight and coverage checks, audit log, timestamped backups, validation through `pipeline.load_sites` on every write.

## Notes from implementation

- Preflight is not `pipeline.preflight()` reused as is. That function retries each collection with backoff and sorts collections globally, which can hang for minutes. The tool asks only whether each collection has data in range.
- The preset row used to share a container with the fit-view and coverage buttons, so the first render removed those buttons. They now have their own row.
- Rejected sites are left out of geometry warnings, neighbour lists and split groups, because they will not be in the final file.

## Not verified yet

- The live Earth Engine preview with the new layout was not exercised (no key used).
- Dragging a bar edge with a real mouse was not exercised; the keyboard resize path was.
- Screen reader behaviour was not tested with a real screen reader; the markup follows ARIA patterns and the live regions were checked in the DOM only.

## Planned for the tool note (not built; see ../PROPOSAL.md, section 1b)

Yield and availability forecast; coordinate grounding against open registries; placement-sensitivity study; split certificate; footprint-overlap groups; near-duplicate chip detector; domain-shift report; cloudless median composite; clear-sky layer; index and statistics views; log and square-root display transforms; gap-fill for no-data pixels; optional keyless STAC backend (solafune-tools, MIT); candidate-area overlay (aid only); provenance and datasheet export; built-in validator and container recipe. None needs a trained or pretrained model.

## Later

- Cancelable background jobs for preflight and coverage.
- Marker-cluster colouring by review state.
- Diff between two arbitrary backups.
- Vendored copy of Leaflet for fully offline use.

## Deliberately not planned

- Polygon areas of interest. The chip grid is a fixed square so every site has the same pixel count.
- A basemap date picker. The Esri layer is a fixed mosaic; the tool fetches a dated Sentinel-2 preview instead.
- Multi-user features such as authentication, per-user audit and live sync. This is a single-operator local tool.

## Imagery and records (1.4.0)

- Backends: demo (synthetic, labelled), Planetary Computer (no account), Earth Engine (your account); same 14-layer chip.
- Sources: single scene, cloudless median, clear-sky layer. Cached per place, box, backend, source and period.
- Views: 5 band composites, 18 indices, 4 display transforms (percentile, log, square root, linear).
- Gap fill: none, band mean, nearest scene; masking test reports the error of each on your own chip.
- Statistics with a plain-word reading; candidate-area outlines (an aid, never moves a site).
- Provenance record (roster hash, counts, imagery used), datasheet with blanks to complete, printable report.
- Help: ? on 63 controls, searchable guide, generated docs/FEATURE_GUIDE.md.
- Left out on purpose: any pretrained or learned model, automatic moving of sites, accounts or sign-in.

## Studies (1.5.0)

- Overlap groups, near-duplicate chips, shift between roles and the split certificate (Studies, Split safety).
- Yield and availability forecast with leave-cluster-out validation and a comparison with simpler models (Studies, Forecast).
- Coordinate grounding against registries (Studies, Coordinates).
- Placement study for the picture, the facility signal and the gas targets (Studies, Placement).
- Not included on purpose: automatic snapping of sites onto the facility (a simple score was tested and was worse than not snapping), and any learned model.
