# HTTP interface

The browser page talks to the local server through this interface. You can use it from scripts too. Write requests (POST, DELETE) must carry the header `X-Site-Curator: 1` (any value), bodies are limited to 5 MB, and the `Host` header must name the local server. Errors come back as JSON `{"error": "..."}` with a plain message.

Roster and review: see the table in the [README](../README.md#api).

## Imagery and records

| Request | Purpose |
|---|---|
| `GET /api/backends[?check=1]` | The backends, whether each is ready, and why not if it is not |
| `GET /api/views` | Band composites, indices (with formulas), stretches, sources, mask kinds |
| `GET /api/preview/<id>?backend=&source=&view=&stretch=&fill=&days=&q=&box_km=&lat=&lon=[&force=1][&check_only=1]` | PNG of the chosen view. Cached per place, box, backend, source and period; changing view, stretch or fill never downloads again |
| `GET /api/imagery/<id>/stats?indices=ndvi,ndwi&clear=0\|1&...` | Statistics and the plain-word reading |
| `GET /api/imagery/<id>/candidates?kind=&percentile=&threshold=&min_px=&...` | Candidate regions with outlines (GeoJSON) |
| `GET /api/imagery/<id>/gapfill_test?...` | Masking test of the fill methods |
| `GET /api/provenance[?download=1&comments=1]` | Provenance record |
| `GET /api/datasheet[?download=1]` | Datasheet text with blanks |
| `POST /api/datasheet` | Datasheet with your answers filled in |
| `POST /api/validate` | Check a sites document without saving it |
| `GET /api/help` | The help content the tool and the written guide are built from |

The shared parameters (`backend`, `source`, `days`, `q`, `box_km`, `lat`, `lon`) are checked; a bad value returns a message that names the allowed values.

## Studies

All write routes need the `X-Site-Curator` header. Plain errors come back as `{"error": "..."}`.

| Request | Purpose |
|---|---|
| `GET /api/studies/status` | What is loaded: table of outcomes, registries, fitted forecast, last validation |
| `GET /api/studies/groups?level=box\|label\|background\|ring` | Overlap groups at one level, with pairs and a summary of all four levels |
| `POST /api/studies/groups` `{level, apply}` | Same; with `apply: true` writes `overlap_group` into every site (undoable) |
| `POST /api/studies/duplicates` `{backend, source, fetch, limit}` | Near-duplicate chips among cached pictures; `fetch` downloads missing ones (at most `limit`) |
| `GET /api/studies/duplicates/benchmark?n_base=&seed=` | Self-test of the finder on generated pictures |
| `POST /api/studies/shift` `{role_a, role_b, features, permutations}` | PSI and KS per feature, and the comparison with random splits |
| `POST /api/studies/certificate` `{time_info, target_column, role_a, role_b, download}` | The split certificate (`download: true` returns the JSON file); its shape is in `docs/split_certificate.schema.json` |
| `POST /api/studies/outcomes` `{csv}`, `GET`, `DELETE /api/studies/outcomes` | The table of outcomes |
| `POST /api/studies/forecast` `{action: "validate", "compare" or "fit", target, features, region_correction}` | Leave-cluster-out check, comparison with simpler models, or fit and save the model |
| `GET /api/studies/forecast/predictions` | Forecast and interval for every site |
| `POST /api/studies/registry` `{name, text, format}`, `GET /api/studies/registries`, `DELETE /api/studies/registry/<name>` | Registries |
| `POST /api/studies/registry/wikidata` `{class_ids, country, confirm}` | Query Wikidata; refused unless `confirm` is true |
| `POST /api/studies/grounding` `{use_original}` | Compare every site with the registries |
| `POST /api/studies/grounding/evaluate` | Error of starting and registry positions on verified sites |
| `POST /api/studies/sensitivity` `{site_id, backend, distances, bearings, kind, targets, window_km}` | Placement study, with gas targets when `targets` is given |
| `GET /api/studies/demo/outcomes`, `GET /api/studies/demo/registry` | Synthetic example files for the demo roster |
