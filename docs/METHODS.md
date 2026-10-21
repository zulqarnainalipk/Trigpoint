# Methods

What the imagery features compute, in enough detail to repeat them, and what they cannot do. The in-tool help says the same things in shorter form.

## Chips

Every backend returns a chip: 14 layers on a 384 by 384 pixel UTM grid centred on the site. Twelve are Sentinel-2 reflectance bands (B1 to B8, B8A, B9, B11, B12), stored as reflectance times 10,000; the other two are the scene classification (SCL) and the cloud probability (CLDPRB). The grid is computed by `core.chip_grid_math` from the site centre and the box size, so the exact pixel grid drawn on the map is the grid of the chip.

A pixel is **valid** when it has data. It is **clear** when it is valid, its cloud probability is below 40 and its scene class is not cloud, cloud shadow or cirrus (classes 3, 8, 9, 10). The threshold is `CFG["cloud_prob_thresh"]` in `core.py`.

## Sources

* **Single scene.** The clearest scene in the look-back period (default 120 days).
* **Cloudless median.** At each pixel and in each band, the median of the values from scenes where that pixel is clear. A pixel with no clear observation stays empty.
* **Clear-sky layer.** The same, but a low percentile (default 20, allowed 1 to 50) instead of the median. Low values are the least hazy, so this shows the surface under thin cloud and haze. It is darker than the median and slightly biased towards shadow; use it to look, not to measure.

Percentiles are computed by sorting each pixel's clear values (`nan_percentile`), which matches `numpy.nanpercentile` and is much faster on stacks.

## Views

Five band composites (true colour, false colour infrared, short-wave infrared, agriculture, aerosol) and 18 indices. Each index has its formula, value range and a one-line reading in the in-tool help. Formulas are listed in `imagery_tools.INDICES`.

Display transforms change only the picture, never the stored values: percentile (2nd to 98th percentile per channel, default), log (log base 2 of reflectance, then percentile stretch), square root, and linear (fixed 0 to 0.3 reflectance, so pictures compare between sites).

## Gap fill

* **None.** Empty pixels stay black.
* **Band mean.** Empty pixels get the mean of the valid pixels of each band. Flat, honest about being a guess, and good enough to remove black holes for display.
* **Nearest scene.** Empty pixels are copied from a second scene (the next best one), after shifting each band by the mean difference between the two scenes over the pixels both can see. Donor pixels that are cloudy are not used. Pixels the donor cannot fill fall back to the band mean.

**Masking test.** The tool hides square blocks of clear pixels (about 10 per cent of the box, 8 pixel blocks, fixed seed), fills them with each method and reports the root mean squared error against the hidden truth. This tells you which fill is better for this place. It does not prove the fill is right for the pixels that were really empty.

## Statistics

Mean, standard deviation, 5th, 50th and 95th percentile and share of valid pixels for the chosen indices, over all valid pixels or only clear ones. The plain-word reading is rule based (for example mean NDVI below 0.15 reads as mostly bare or built-up ground).

## Candidate areas

A threshold on one simple mask (built-up, hot ground, bare, bright). By default the threshold is a percentile of the index over valid pixels, so it adapts to each chip. Connected regions smaller than the minimum size are dropped; for each remaining region the tool reports area, centroid, distance from the centre, compactness and elongation, and draws the outline. **It never moves the site.** It is an aid for your eye, and a bright roof, a salt flat and a real facility can look alike.

## Provenance and datasheet

The provenance record lists the tool version, the roster's SHA-256 (computed on a canonical form of the sites, so key order and spacing do not matter), counts, the audit summary and the imagery that was cached for each site (backend, source, dates, number of scenes, whether synthetic). The datasheet follows the sections of Gebru et al., "Datasheets for Datasets", fills what the tool knows and leaves `[TO COMPLETE]` where only you know the answer.

## Studies

### Overlap groups

For every pair of active sites the tool decides which footprints overlap, using flat distances in kilometres (east and north offsets): the chip boxes (squares of the box sizes), the 10 km label windows (squares), the background rings (annuli from 30 to 75 km) and the outer rings. Four levels follow, each stronger than the next: `box`, `label`, `background` (one site's label window reaches into the other's ring, or the label windows overlap) and `ring` (the rings overlap, which is the same as the 150 km distance rule). Sites linked at the chosen level, directly or through others, form a group with a stable id (`g001`, `g002`, ...). A decoy counts as part of the test side, so a test site and a decoy in one group are not a conflict. Groups that mix roles are the ones a split would cut. The levels are listed side by side so the cost of each rule can be seen.

### Near-duplicate chips

Each chip becomes a 32 by 32 grey preview (mean of the visible bands, area-averaged). Stage one ranks the pixels of a coarse 12 by 12 version and takes the correlation of every image with all eight flips and rotations of every other, as one matrix product; the rank step makes it blind to any monotone change of brightness or colour. Pairs above 0.5 go to stage two: the best of the eight orientations is tried with shifts of up to one pixel (32 px scale), the pixel values of one are matched to the other by rank (histogram matching), and the pair is a near-duplicate when the correlation is at least 0.85 and the structural similarity (7 pixel window) at least 0.75. A 63-bit perceptual hash (low-frequency DCT against its median) is reported for reference. The tool's default for the first screen is 0.5; the studies in the note used 0.6. The thresholds were chosen on generated pictures and on the synthetic demo scenes, before the real chips were examined. The self-test (Studies, Split safety) shows detection and false alarms for twelve kinds of copy; on 30 generated pictures per seed over three seeds it found 98 to 100 per cent of the copies with no false alarm among about 9,000 unrelated pairs per seed. On the 1,355 public chips of OBSCURA-Open-25, no pair from different sites was a near-duplicate (2,288 pairs passed the first screen). In a controlled test, ten copies of each of 20 public chips from different sites were made in each of the twelve ways (fixed seed), and all 120 were found with no false alarm among 5,100 unrelated pairs (only the 120 true pairs passed the first screen). That shows detection under those conditions, not that every natural near-duplicate would be found. Two dates of the same site were flagged for 12 of 25 sites, because the ground looks alike; this is why the tool compares one picture per site, and it also means an entry that shows the same ground as another (a facility entered twice) is flagged. Shifts of more than about a pixel at preview scale, crops and scale changes are not handled.

### Shift between roles

For each numeric feature the tool takes the sites of one role as the reference, bins them by quantiles, and computes the population stability index (PSI) of the other role against it, plus the two-sample Kolmogorov-Smirnov statistic and its p value. The number of bins is one per 20 sites of the smaller group, between 3 and 10, because PSI is biased upwards for small groups (roughly the number of bins minus one, times the sum of 1/n over both groups). To show what chance gives, the comparison is repeated for random splits of the same sizes (default 200), and the tool reports the observed median PSI against the mean and 95th percentile of the random ones and a permutation p value. PSI below 0.1 is read as small, 0.1 to 0.25 moderate and above 0.25 large; these are conventions from credit scoring, not laws.

### Split certificate

A JSON record (`site-curator-certificate/1`) with a fingerprint of the roster and one entry per check: closest pair of sites in different roles against the 150 km rule; overlaps across roles at each of the four levels; the gap between the end of training and the start of testing (when dates are given); the spatial dependence of one per-site number (an empirical semivariogram in bins of 0 to 50, 150, 300, 600, 1200, 2500 and 6000 km, with bins of fewer than ten pairs marked not reliable, plus the median nearest-neighbour distance and the share of sites with a neighbour within 150 km); near-duplicates across roles; and the shift between two roles. Each check is pass, fail, warn or not run. The verdict is fail if any check fails, conditional if any was not run or warns, and pass only when every check ran and passed. A check that was not run never counts as passed.

### Forecast

The forecast predicts the share of collection windows that produce a usable sample (the yield), or another number between 0 and 1 such as the share of samples with a given target. Inputs are standardised screening numbers (land share, clear-scene share, fire days on a log scale, aerosol index, NO2 and CO contrast); a missing value is replaced by the training median. The model is ridge regression with the strength chosen from six values by leave-cluster-out error. Clusters are sets of sites joined by distances under 150 km, so no site is ever predicted from a neighbour. A per-region correction (the mean held-out residual of the region, multiplied by n / (n + 3)) is fitted inside each training part. The interval is the 80th percentile of the absolute held-out residuals. Validation repeats all of this for each held-out cluster, so the regularisation, the region correction and the interval never see the cluster they are scored on; it reports the mean absolute error against guessing the training mean, R squared, the rank correlation, the share of sites inside their interval, and what dropping the lowest-forecast sites would have saved. The shipped model is fitted on every site. With fewer than 30 sites the tool warns that the numbers are rough, and it refuses fewer than 10. "Compare with simpler models" repeats the same held-out check for each number alone and for all together, next to guessing the mean, so you can see whether the extra numbers earn their place. A forecast of a number that is not a share between 0 and 1 is not clipped.

### Coordinate grounding

A registry is a list of names with latitude and longitude (CSV, GeoJSON or a Wikidata query result). A site is matched to an entry when the countries are compatible, the entry lies within 100 km, and the name score is at least 0.5, where the score is half the Jaccard overlap and half the containment of the two sets of name words after accents, case and generic words (plant, refinery, complex, gas, power ...) are removed. The position compared is the position before you moved the site when the site records one. The distance gives the flag: agree up to 2 km, differ up to 5 km, disagree beyond. The evaluation uses verified sites that have a recorded starting position and reports, against the verified centre, the error of the starting position, of the registry position where a match was found, and of a combined rule (registry when matched, else the starting position), plus the area under the curve for whether disagreement between the two positions predicts a starting error above 5 km. On the 25 public sites of OBSCURA-Open-25 and seven Wikidata classes (about 21,000 entries), 6 sites matched an entry, and the registry positions were within 1.6 km of the verified centres (median 0.87 km). The starting coordinates of that record are not published, so they were not compared. An earlier run on a different collection with a 300 km search distance let one wrong match 173 km away through, which is why the default is 100 km. It cannot say anything about sites a registry does not list, and the starting positions it measures are whatever you started from.

### Placement study

One wider picture is taken, as wide as the box plus twice the largest shift (at most 40 km), once for the original date and once for a second date. The box is cut out at the original position and at shifted positions (the chosen distances in 4 or 8 directions) at the resolution of the wider picture. For each shift the tool reports the share of the box that overlaps the original, the correlation of the visible brightness and the normalised difference of six bands over pixels valid in both, and the share of the facility-like pixels of the original box that remain in view (facility-like means the top ten per cent of a simple index such as bare or built-up ground, over the wider picture). The tolerance is the largest tested distance whose median keeps at least half of those pixels. For gas targets the value at each shifted position is the mean of the window minus the mean of a 30 to 75 km background ring on the long-term mean image of a Sentinel-5P product (one year by default); the change is compared with the day-to-day standard deviation of the window mean at the original position and with the standard error of the yearly mean. The target tolerance is the largest distance whose median change stays within a quarter of the day-to-day spread. Because any single threshold is a choice, the tool also reports the tolerance for looser and stricter thresholds (facility signal kept at least 25, 50 and 75 per cent; picture correlation at least 0.5, 0.8 and 0.9; gas change within 0.1, 0.25 and 0.5 of the spread).

## Limits

* No pretrained or learned model is used anywhere. The forecast is a linear model fitted on your own table in seconds.
* Demo scenes are synthetic. Nothing derived from them is evidence about a real place.
* Live Earth Engine and Planetary Computer fetches depend on the services and on your account; the tests use stand-ins for both. See [BACKENDS.md](BACKENDS.md).
* Sentinel-2 at 20 m cannot see small things. A box of 1 to 8 km is the supported range.
