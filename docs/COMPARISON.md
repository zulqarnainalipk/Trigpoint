# Where TrigPoint sits next to a spatial cross-validation package

This page compares TrigPoint with one package whose capabilities were checked against its documentation: **blockCV** (Valavi et al. 2019; R; CRAN reference manual, read on 21 October 2026). No other tool was assessed, so nothing is said about any other software. The point is to say what TrigPoint adds, not that blockCV is lacking: blockCV does a different job, and the two can be used together.

| Capability | blockCV | TrigPoint |
|---|---|---|
| Builds train and test folds that are separated in space | Yes: spatial blocks, buffers and clusters, and environmental blocking | Gives group identifiers so linked sites stay on one side; does not build folds |
| Estimates the distance over which data are spatially dependent | Yes (spatial autocorrelation range, used to choose block size or buffer) | An empirical semivariogram of one number per site, marked indicative when bins are thin |
| Works on point locations and raster predictors | Yes | Works on a site list with a box per site and satellite chips |
| Checks that boxes, label windows and background rings of different sites overlap | Not part of its documented functions | Yes (four levels) |
| Looks for flipped, rotated, shifted or recoloured copies of a picture | Not part of its documented functions | Yes (with a self-test) |
| Compares site coordinates with public registries | Not part of its documented functions | Yes (Wikidata or your own file) |
| Shows what a misplaced box does to the picture and to a gas label | Not part of its documented functions | Yes (placement study) |
| Forecasts how many usable samples a site will give | Not part of its documented functions | Yes (validated on held-out clusters) |
| Writes one record of the checks that were and were not run | Not part of its documented functions | Yes (split certificate with a schema) |

"Not part of its documented functions" means the function list in the reference manual has no such function; it does not mean that nothing can be built from the package.
