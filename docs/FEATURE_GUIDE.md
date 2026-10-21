# Feature guide

Every feature of TrigPoint, in plain words. The same text opens in the tool when you press the ? button beside a control, or search it with the Guide button. This file is generated from `help_content.json`; do not edit it by hand.

## Contents

* [Start here](#start-here)
* [Sites and review](#sites-and-review)
* [Map and geometry](#map-and-geometry)
* [Imagery](#imagery)
* [Studies](#studies)
* [Checks and records](#checks-and-records)
* [Settings and access](#settings-and-access)

## Start here

### How help works in this tool

*Every control with a ? button explains itself.*

**What it is.** Next to most controls you will see a small ? button. Press it to open a short explanation of that control: what it is, why it matters, how to use it, and what it cannot do.

**Why it matters.** You should never have to guess what a button does. The same text is in the written guide, so the tool and the documentation always agree.

**How to use it.**

1. Press the ? next to a control, or press Tab to reach it and then Enter.
2. Press Esc to close the explanation. Focus returns to where you were.
3. Open Help, then Feature guide, to search every explanation.

**How it works.** All explanations come from one file that the tool reads when it starts.

**What it cannot do.** The explanations describe the tool. They are not instructions for choosing sites in your own project.

### Feature guide

*A searchable list of every feature.*

**What it is.** A list of all features of the tool, grouped by area, with a search box. Choosing one opens its explanation.

**Why it matters.** It is the quickest way to find out whether the tool can do something.

**How to use it.**

1. Open it from the top bar (Guide) or from Help.
2. Type a word, for example flare, grid or export.
3. Press Enter on a result to read it.

**How it works.** The search looks at the title, the short description and the text of each explanation.

**What it cannot do.** It searches the explanations only, not your sites.

### Demo mode (synthetic scenes)

*Try every imagery feature without an account.*

**What it is.** Demo mode makes pretend satellite scenes from simple rules: a sea, fields, a facility with a flare, clouds, haze and a strip with no data. They look like real scenes in the right layout.

**Why it matters.** You can learn the imagery tools, or test a workflow, without an Earth Engine account or an internet connection to a satellite service.

**How to use it.**

1. Choose Demo in the imagery source list.
2. Fetch an image and use every view and tool as usual.
3. Switch to Earth Engine or Planetary Computer when you want real imagery.

**How it works.** The scenes are drawn from the site name and place, so the same site always gives the same pictures.

**What it cannot do.** Demo scenes are NOT real. They say nothing about any real place and must never be used as evidence to keep or move a site. The tool labels them synthetic wherever they appear.

## Sites and review

### Site list

*All sites, with their review state.*

**What it is.** The left bar lists every site in the file with its name, role and whether you kept it, rejected it, skipped it or have not looked at it yet.

**Why it matters.** It shows how much of the review is done and lets you jump to any site.

**How to use it.**

1. Click a site, or use J and K to move down and up.
2. Press N to jump to the next site you have not reviewed.
3. Tick sites with Shift and Space to act on several at once.

**How it works.** The list follows the filters and sort order you chose.

**What it cannot do.** It shows only the file you opened.

### Filters and sort

*Narrow the list and change its order.*

**What it is.** Choose which sites the list shows (by review state, role, region, priority, facility type, setting, confidence or quality flags) and how they are sorted.

**Why it matters.** Reviewing in groups, for example one region at a time or the least certain coordinates first, is faster and more consistent.

**How to use it.**

1. Open Filters and sort.
2. Pick values in any menu; the list updates at once.
3. Press Clear filters to start again.

**How it works.** Filters combine: a site must pass all of them. Your choices are remembered in this browser.

**What it cannot do.** Filters hide sites from the list only. Nothing is changed or removed from the file.

### Keep, reject, skip

*Record your decision for each site.*

**What it is.** Keep means you checked the site and its centre and box are right. Reject removes it from the final list, but it stays in the file and you can bring it back. Skip means come back later.

**Why it matters.** A clear decision for every site is what turns a list of candidates into a trustworthy roster.

**How to use it.**

1. Check the imagery and the box.
2. Press V to keep, X to reject or S to skip.
3. Press U to mark a site as not reviewed again.

**How it works.** Keep saves your edits, ticks verified and opens the next unreviewed site. Reject adds a flag. Both can be undone.

**What it cannot do.** Reject is not delete. To remove a site for good, use Delete and confirm.

### Quick edit strip

*The essentials in one small panel over the map.*

**What it is.** A small panel with name, role, centre, box size, a comment and the keep and reject buttons.

**Why it matters.** When you only need to nudge a box and decide, it keeps the map large and your hands in one place.

**How to use it.**

1. Press E to open it.
2. Change a field. Press Enter to save, Esc to close.

**How it works.** It edits the same record as the details bar, so both always agree.

**What it cannot do.** It has no screening numbers or flags. Open the details bar for those.

### Undo and redo

*Take back the last change.*

**What it is.** Undo restores the whole record of the last site you changed, including keep, reject and bulk changes. Redo puts it back.

**Why it matters.** You can work quickly because mistakes are cheap to fix.

**How to use it.**

1. Press Ctrl and Z to undo, Ctrl, Shift and Z to redo, or use the top bar buttons.

**How it works.** The tool keeps a list of changes made in this session.

**What it cannot do.** The list is cleared when you close the tool. For older versions, use the backup browser.

### Bulk actions

*Act on many sites at once.*

**What it is.** Tick several sites in the list and keep, reject, unreview, change role or delete them together, or compare them side by side.

**Why it matters.** It saves time when many sites need the same decision, for example a whole region that you rejected.

**How to use it.**

1. Tick sites with Shift and Space, or the boxes in the list.
2. Choose an action in the bar that appears.
3. Undo if you change your mind.

**How it works.** Each action is checked by the validator and written once.

**What it cannot do.** Delete is permanent after the confirmation. Prefer reject.

### Add a site

*Create a site by place name or by clicking the map.*

**What it is.** Search for a place, click the map or type coordinates, give the site a name and role, and create it. You can also paste many sites at once (bulk import).

**Why it matters.** Rosters grow. New sites arrive with the same checks as old ones.

**How to use it.**

1. Press Add site.
2. Search a place or enter latitude and longitude.
3. Set the box size and press Create.

**How it works.** The place search uses OpenStreetMap Nominatim. The new site must pass the validator.

**What it cannot do.** Place search needs internet and follows the provider's usage rules. Coordinates from a search can be several kilometres off a large facility: check them on the imagery.

## Map and geometry

### Box size

*The side length of the square image of a site.*

**What it is.** Each site has a square box, from 1 to 8 km on a side. Chips are cut to this box, always with the same number of pixels, so a bigger box means a larger pixel.

**Why it matters.** A box that is too small cuts a facility off. A box that is too large fills with surroundings and makes each pixel coarser.

**How to use it.**

1. Drag a corner square, or type a value, or press minus and plus to step through presets.
2. Press T for the typical size of this kind of facility.

**How it works.** Pixel size is the box divided by the pixel count (shown next to the box). The typical size is the median of other sites of the same type.

**What it cannot do.** The tool cannot know how big your facility really is. Look at the imagery.

### Label window (10 km)

*The fixed area that gas measurements are averaged over.*

**What it is.** A dashed square, 10 km on a side, around the site centre. Satellite gas values are averaged inside it.

**Why it matters.** It shows which surroundings affect the measurement, and whether two sites share the same measurements.

**How to use it.**

1. Switch it on with L or in Map layers.

**How it works.** It is drawn in the local map projection around the centre, and does not change with the box size.

**What it cannot do.** It is a guide. It does not mean the measurement is sharp to 10 km: satellite pixels are several kilometres wide.

### Background ring (30 to 75 km)

*The ring used as the regional background.*

**What it is.** Two dashed circles at 30 and 75 km from the centre. The ring between them gives the background level that is subtracted from the gas value inside the label window.

**Why it matters.** Another facility inside the ring would raise the background and spoil the measurement. Seeing the ring shows where that could happen.

**How to use it.**

1. Switch it on with B or in Map layers.

**How it works.** The curator only draws it. The data pipeline decides what to exclude.

**What it cannot do.** It does not know about land and sea. Over a coast, part of the ring is water.

### Split radius (150 km)

*Sites inside it must share the same train or test group.*

**What it is.** A dotted circle of 150 km. Sites inside it are too close to be split between training and testing.

**Why it matters.** If a training site and a test site are close, their data are similar. A model could score well by recognising the area, not by learning the task. This is called leakage.

**How to use it.**

1. Switch it on with R.
2. Read the neighbour list for what each nearby site forces.

**How it works.** The radius is twice the outer background radius, so the background rings of sites in different groups never overlap.

**What it cannot do.** It is a distance rule. It does not prove two areas are different in weather or industry.

### Reference (pilot) sites

*A read-only second roster shown as triangles.*

**What it is.** Sites from another file, shown with their boxes, so you can see how new candidates relate to an existing roster.

**Why it matters.** New sites must not sit too close to sites that are already fixed in a split.

**How to use it.**

1. Switch on Pilot sites in Map layers or press P.
2. Set the file with the METHANE_REFERENCE_PATH variable.

**How it works.** The file is only read. It is never changed.

**What it cannot do.** If no reference file is set, the layer is empty.

### Exact pixel grid

*The real pixel layout of the chip.*

**What it is.** Draws the box exactly as it will be cut: snapped to whole pixels in the local UTM map projection.

**Why it matters.** What you see is what the chip will contain, not an approximation.

**How to use it.**

1. Tick Show exact pixel grid, or press H.

**How it works.** The tool computes the projection and the snapping with the same rules as the chip export.

**What it cannot do.** Real chips can carry a small random shift of the grid; the drawn grid is the unshifted one.

### Jump to coordinates

*Paste a position and go there.*

**What it is.** Accepts latitude and longitude in decimal degrees, with N, S, E, W letters, in degrees, minutes and seconds, or a Google Maps or OpenStreetMap link.

**Why it matters.** Coordinates arrive in many forms. Typing them by hand invites mistakes.

**How to use it.**

1. Press G or click the box above the map, paste, press Enter.
2. Press Move box here to set the centre of the open site.

**How it works.** The text is read by a small parser and the map flies to the point.

**What it cannot do.** If the text is ambiguous the tool asks you to correct it. It never guesses a hemisphere.

### Measure distance

*Click points on the map to measure a distance.*

**What it is.** Click two or more points to see the length of the path in kilometres.

**Why it matters.** Useful for judging a facility size or the gap between two sites.

**How to use it.**

1. Open Tools, then Measure distance.
2. Click points. Press Esc to stop.

**How it works.** Distances use the great-circle formula on the sphere.

**What it cannot do.** Accurate to well under 1 percent at the sizes used here, not for survey work.

## Imagery

### Imagery panel

*Look at the site from space, in many ways.*

**What it is.** Fetches satellite imagery for the open site and shows it in different views. It also gives statistics, repairs missing pixels and suggests areas of interest.

**Why it matters.** Imagery is the evidence for where the facility is and how big its box should be. Different views show different things: a flare, bare ground, haze, water.

**How to use it.**

1. Pick an imagery source and what to show.
2. Press Fetch image.
3. Change the view, the stretch or the fill and the picture updates without a new download.

**How it works.** The image is a 14-layer chip: 12 Sentinel-2 bands, a scene classification and a cloud probability. It is saved on your computer, so switching views is instant.

**What it cannot do.** Imagery shows the surface on the day or days it was taken. It cannot tell you which company owns a facility.

### Imagery backend

*Where the imagery comes from.*

**What it is.** Earth Engine (needs a Google account and a key), Planetary Computer (free, no account, needs internet) or Demo (synthetic, always works).

**Why it matters.** You can use the tool with whatever access you have.

**How to use it.**

1. Choose in the list. A badge says which ones are ready and why not.
2. See docs/BACKENDS.md to set up Earth Engine.

**How it works.** All three give the same kind of chip, so every view and tool works with all of them.

**What it cannot do.** Earth Engine and Planetary Computer can differ slightly for the same day because of how scenes are tiled and corrected.

### Single scene

*The clearest single day in the look-back period.*

**What it is.** Picks the satellite pass with the least cloud over your box.

**Why it matters.** A real picture of one day, the way a user of the chips will see it.

**How to use it.**

1. Choose Single scene, set the look-back days, press Fetch.

**How it works.** Scenes are ranked by the share of cloud inside the box.

**What it cannot do.** One day can still have haze, smoke or a gap. Try the cloudless median for a cleaner view.

### Cloudless median composite

*A clean image built from many days.*

**What it is.** At each pixel it takes the middle value of all the clear observations in the period. Clouds and shadows are ignored.

**Why it matters.** It gives a stable, cloud-free picture of the ground, good for judging the footprint of a facility.

**How to use it.**

1. Choose Cloudless median and a period (a few months is typical), press Fetch.
2. Read the scene count and the share of pixels observed.

**How it works.** Cloud and cloud shadow are removed using the scene classification and the cloud probability. The median of what is left is taken for each band.

**What it cannot do.** It blends different days, so short-lived things (a flare on one day, a moving ship) fade. It can hide changes during the period.

### Clear-sky layer

*A low percentile of clear days: the surface under haze.*

**What it is.** At each pixel it takes a low percentile (20 by default) of the clear observations. Haze and thin cloud make values brighter, so low values are the clearest.

**Why it matters.** It shows the surface beneath thin cloud and haze. Researchers use such a layer because it describes the place rather than the weather of one day.

**How to use it.**

1. Choose Clear-sky layer, set the period, press Fetch.

**How it works.** Same cloud removal as the median, then the chosen low percentile of each band.

**What it cannot do.** Dark surfaces and shadows are favoured by a low percentile, so the layer looks slightly darker than a real day.

### Look-back period

*How many days back to search.*

**What it is.** The number of days before today that the tool searches for scenes.

**Why it matters.** A longer period finds more clear scenes, but blends more of the year.

**How to use it.**

1. Type a number of days, or use the presets.

**How it works.** The period ends today.

**What it cannot do.** Very long periods for composites take longer to fetch.

### Colour views

*Three bands shown as red, green and blue.*

**What it is.** True colour looks like a photograph. False-colour IR shows plants in red. SWIR shows bare ground, industry and hot spots (flares glow orange) and makes water dark. Agriculture separates desert from fields. Aerosol (red, blue, coastal blue) makes haze and smoke look blue-white.

**Why it matters.** A facility, a flare, a field and a lake look different in different views. Switching views helps you place the centre and box with confidence.

**How to use it.**

1. Press a view button. The picture updates at once.

**How it works.** Each view picks three of the 12 bands and stretches them for display.

**What it cannot do.** The colours are display colours. They are not measurements.

### Index views

*One number per pixel, drawn as a blue scale.*

**What it is.** Spectral indices combine bands to bring out one thing: vegetation (NDVI), water (NDWI, MNDWI), bare or built-up ground (BSI), hot or dry ground (NBR2, hot-surface ratio), haze (coastal-blue contrast). Dark blue means high.

**Why it matters.** An index can show a facility boundary or a flare that a colour picture hides.

**How to use it.**

1. Choose an index. Press ? beside it to see its formula and meaning.
2. The scale is stretched between the 2nd and 98th percentile of the picture.

**How it works.** Each index is a formula on the band values, limited to a fixed range so that division by a tiny number cannot blow up.

**What it cannot do.** Index values differ between images and places, so the scale is relative to the picture, not an absolute reading.

### Display stretch

*How brightness is spread over the screen range.*

**What it is.** Percentile stretches each channel between its 2nd and 98th percentile. Log and square root open up dark areas of skewed images. Linear uses one fixed range so images can be compared.

**Why it matters.** Satellite values are bunched near the dark end. A good stretch shows detail in shadows and bright ground at once.

**How to use it.**

1. Choose a stretch. The picture updates at once.

**How it works.** Transforms are applied to reflectance before the percentile stretch. They change only how the picture looks.

**What it cannot do.** A stretch does not change the data or the statistics.

### Statistics

*Numbers that describe the picture.*

**What it is.** For each band and chosen indices: mean, spread (standard deviation), skew and the 5th, 25th, 50th, 75th and 95th percentiles, plus the share of valid, clear and cloudy pixels.

**Why it matters.** A few numbers let you compare sites and spot odd images, such as one that is mostly cloud or mostly water.

**How to use it.**

1. Open Statistics after fetching. Choose whether to use clear pixels only.
2. Each row has a plain-word reading.

**How it works.** Statistics are computed on the pixels inside the box that have data (and, if chosen, are clear).

**What it cannot do.** They describe this picture only. One image is not a climatology.

### Gap fill

*Repair pixels that have no data.*

**What it is.** Fills empty pixels. Band mean uses the average of the valid pixels. Nearest scene copies the same pixels from another day and shifts each band to match brightness, then uses the mean for whatever is still empty.

**Why it matters.** Empty strips and holes make pictures and statistics misleading. A repair is easier to read, and statistics do not shrink towards zero.

**How to use it.**

1. Choose a fill method. The picture shows filled pixels exactly like the rest, so check the caption for how many were filled.

**How it works.** The nearest scene method uses only clear donor pixels and matches the donor to the scene by the average difference of the two over pixels clear in both.

**What it cannot do.** Filled pixels are estimates. Never use them as evidence of what is on the ground at that spot.

### Test the gap fill

*Measure how good each fill method is on this picture.*

**What it is.** Hides about 10 percent of the clear pixels in small blocks, fills them with each method, and reports the average error against the hidden truth.

**Why it matters.** It tells you how much to trust a fill on this kind of scene instead of taking it on faith.

**How to use it.**

1. Press Test the gap fill after fetching.
2. A smaller error is better. Read it against the picture's own spread.

**How it works.** The hidden blocks are chosen at random with a fixed seed, so the same picture gives the same answer.

**What it cannot do.** It measures error on pixels that were hidden on purpose. Real gaps (for example under a cloud) can be harder.

### Candidate areas

*Outlines of regions that look like built-up, hot, bare or bright ground.*

**What it is.** Marks connected regions where a simple index is above a threshold and lists their size, distance from the centre, compactness and elongation.

**Why it matters.** It can help you see where the facility is, or whether your centre sits on an obvious feature.

**How to use it.**

1. Choose a kind and a strictness, press Find candidates.
2. Press a region to show it on the map.

**How it works.** A threshold on an index gives a mask. Neighbouring masked pixels are joined into regions, small ones are dropped, and outlines are drawn on the map.

**What it cannot do.** It is only an aid for your eyes. It never moves a site. A simple score can pick the wrong part of a large industrial area, so always check the imagery.

## Studies

### Studies

*Checks and forecasts that go beyond one site at a time.*

**What it is.** A window with four tabs. Split safety checks that train and test sites do not overlap or copy each other. Forecast predicts how many usable samples a site will give. Coordinates compares your positions with public lists. Placement shows what a misplaced box costs.

**Why it matters.** A benchmark is only as good as its split and its coordinates. These checks turn those worries into numbers you can read and keep.

**How to use it.**

1. Open Studies from the Tools menu.
2. Pick a tab and press its main button.
3. Press the ? beside any heading for details.

**How it works.** Each tab calls a small, open calculation on your roster. Nothing uses a trained model, and nothing changes a site unless a button says it will.

**What it cannot do.** The studies only know what is in your roster, your table and the pictures you fetch. They cannot tell you whether a site is a good idea.

### Overlap groups

*Sites that overlap must stay together in one fold.*

**What it is.** Finds every pair of sites whose boxes, 10 km label windows or background rings overlap, joins the linked sites into groups, and gives each group an id.

**Why it matters.** If two overlapping sites land in different splits, the test set shares ground truth with the training set. Groups let you split whole groups, never parts of one.

**How to use it.**

1. Choose how strict the link should be.
2. Press Find groups and read the table.
3. Press Write group ids into the roster if you want the ids saved in each site. You can undo it.

**How it works.** It compares every pair using flat distances in kilometres. Linked sites are joined into groups with a simple union step, so a chain of overlaps becomes one group.

**What it cannot do.** It uses the box sizes you set. If a box is wrong, the groups are wrong, and it cannot see overlap between sites that are not in this roster.

### Near-duplicate chips

*Finds pictures that are flipped, turned, shifted or recoloured copies.*

**What it is.** Compares small grey previews of all the pictures and lists pairs that match after a flip, a turn of 90 degrees, a shift of a pixel or two, or a change of brightness or colour.

**Why it matters.** Copies of the same picture in train and test make a test score look better than it is. In some competitions this was a real problem.

**How to use it.**

1. Choose where the pictures come from.
2. Tick the box if the tool should download pictures that are not saved yet.
3. Press Look for near-duplicates.

**How it works.** A fast rank-correlation screen keeps likely pairs. Each pair is then tried in all eight flips and turns with small shifts, brightness is matched, and correlation and structural similarity must both be high.

**What it cannot do.** It only sees the pictures it has. Two pictures of the same place on different dates are often flagged too, because the ground looks alike; that helps when one facility was entered twice.

### Self-test of the duplicate finder

*Measures how well the finder works on made-up copies.*

**What it is.** Builds a set of generated pictures, makes copies with known changes, runs the finder, and reports how many copies it found and how many false alarms it raised.

**Why it matters.** A checker you cannot test is a checker you must trust. This shows what it can and cannot catch.

**How to use it.**

1. Press Run the self-test.
2. Read the rate for each kind of copy.
3. A rate below 100 percent means some copies of that kind are missed.

**How it works.** Every picture comes from a fixed random seed, so the same test gives the same numbers every time.

**What it cannot do.** Generated pictures are simpler than satellite scenes. Treat the numbers as a lower bound on how clean the test is, not as a promise for real data.

### Shift between two roles

*Shows how different train sites are from test sites.*

**What it is.** Compares each number that describes the sites (for example cloud-free share or land share) between two roles, with a population stability index and a two-sample test.

**Why it matters.** A model that does well on training sites can fail on test sites that look different. This shows how big the gap is before you collect anything.

**How to use it.**

1. Choose the two roles.
2. Press Compare the two roles.
3. Read the sentence at the top, then the table.

**How it works.** The index compares how sites fall into bins. The tool also repeats the comparison for random splits of the same sizes so you can see what chance alone gives.

**What it cannot do.** With few sites the index is noisy and biased upwards. It cannot tell you why two roles differ.

### Split certificate

*One file that says whether a split is safe.*

**What it is.** Collects the checks into a single JSON record: closest sites in different roles, overlaps across roles, the time gap, the spread of a target over distance, near-duplicate pictures and the shift between roles.

**Why it matters.** You can hand the file to a reader or a reviewer. It states what was checked, what passed and what was never run.

**How to use it.**

1. Optionally enter the end of the training period and the start of the test period.
2. Optionally choose a target column.
3. Press Build the certificate, then download it.

**How it works.** Each check gives pass, fail, look at this, or not run. The file also holds a fingerprint of the roster so it cannot be confused with another version.

**What it cannot do.** A pass means the checks that were run found nothing. It does not prove a split is perfect, and checks that were not run say nothing.

### Table of outcomes

*The numbers the forecast learns from.*

**What it is.** A CSV with one row per site. The first column is the site id. The other columns hold numbers such as how many collection windows there were, how many gave a sample, and screening values.

**Why it matters.** The forecast needs to see how sites turned out in the past. Without a table, it cannot be checked or fitted.

**How to use it.**

1. Choose a CSV file or paste the text.
2. Press Load the table.
3. Check the summary line for the columns that were found.

**How it works.** The tool joins rows to your sites by id. When windows and ok_windows are given, it works out the yield (the share of windows that gave a sample).

**What it cannot do.** Rows with an id that is not in the roster are ignored. Text in a number column is treated as missing.

### Forecast

*Predicts how many usable samples a site will give.*

**What it is.** Estimates the share of collection windows that will give a usable sample, or the share with a given target, from cheap screening numbers, with a range around each estimate.

**Why it matters.** Collection takes time. If a site is likely to give little, you can find out before you spend that time.

**How to use it.**

1. Load a table of outcomes.
2. Choose what to forecast and which numbers to use.
3. Press Check the forecast first, then Fit it and use it.

**How it works.** A plain linear model (ridge regression) on the chosen numbers, with a small correction for each region that is pulled towards zero when a region has few sites.

**What it cannot do.** It learns only from your sites. A forecast for a very different kind of place can be wrong, and the range is only as good as the held-out errors it came from.

### Check the forecast

*Tests the forecast on sites it has not seen.*

**What it is.** Holds out whole clusters of nearby sites, predicts them from the rest, and reports the error against simply guessing the average, plus how often the true value fell inside the range.

**Why it matters.** A forecast that is only tested on sites close to its training sites looks better than it is. Holding out clusters stops neighbours from helping.

**How to use it.**

1. Press Check the forecast.
2. Read the first sentence, then the table and the chart.
3. Look at the table of dropped sites to see what the forecast would have saved.

**How it works.** Sites within 150 km are one cluster. Each cluster is predicted from all the others, and settings are chosen without looking at the held-out cluster.

**What it cannot do.** It is an honest estimate for places like the ones in your table. With only a few dozen sites the numbers move when you add or remove one.

### Fit and use the forecast

*Fits the forecast on every site and applies it to all of them.*

**What it is.** Fits the model on all sites that have an outcome, saves it, and lists a forecast with a range for every site in the roster, lowest first.

**Why it matters.** The sites with the lowest forecast are the ones to look at before you spend collection time on them.

**How to use it.**

1. Press Check the forecast first.
2. Press Fit it and use it for every site.
3. Download the list if you want to keep it.

**How it works.** The final model uses all the data. Its range comes from the held-out errors found in the check.

**What it cannot do.** A low forecast is a reason to look, not a reason to drop a site. Check the picture and the reasons first.

### Registries

*Public lists of facilities with coordinates.*

**What it is.** A registry is a file of facility names and positions from a public source, for example Wikidata or a Global Energy Monitor table. You add one or more and the tool compares your sites against them.

**Why it matters.** Positions written from memory can be several kilometres off. A second source shows where to look first.

**How to use it.**

1. Give the registry a name and choose the file, or paste the text.
2. Press Add the registry.
3. Optionally use the Wikidata lookup, which needs your confirmation to go online.

**How it works.** The tool reads CSV, GeoJSON or a Wikidata result and keeps the name, country, latitude and longitude of each entry.

**What it cannot do.** Registries are incomplete and sometimes wrong. Check each source's licence before you use it.

### Compare with registries

*Flags sites whose position differs from a registry.*

**What it is.** Matches each site to a registry entry by name, country and distance, then says whether the two positions agree, differ a little, disagree, or whether no match was found.

**Why it matters.** A site that disagrees with a registry by several kilometres is the first one to check against the picture.

**How to use it.**

1. Add at least one registry.
2. Press Compare all sites.
3. Open a flagged site and check the picture. Move the site yourself if the registry is right.

**How it works.** Names are compared after dropping generic words such as plant or refinery. Positions agree within 2 km, differ up to 5 km, and disagree beyond that.

**What it cannot do.** A wrong name match can point at the wrong place, and the tool never moves a site on its own.

### Error on verified sites

*Measures how good the starting positions and the registries were.*

**What it is.** For sites you have already checked on the map, compares the position before you edited it, and the registry position, with the position you settled on.

**Why it matters.** It turns the question of how far off recalled coordinates are into a number, and shows whether a registry helps.

**How to use it.**

1. Add a registry and compare all sites.
2. Press Measure the error on verified sites.
3. Read the median error and the share within 1, 2 and 5 km.

**How it works.** The verified position is the truth. Errors are great-circle distances in kilometres, summarised for each source and for a combined rule.

**What it cannot do.** It only covers sites that are verified and have a recorded starting position, and it measures the source of the starting positions, not coordinates in general.

### Placement study

*Shows what a misplaced box costs.*

**What it is.** Moves the box by several distances in several directions and measures how much the picture changes and how much of the facility stays inside.

**Why it matters.** Coordinates are never exact. This shows how large an error you can live with for a given box size.

**How to use it.**

1. Open a site first.
2. Choose the shifts and the kind of facility signal.
3. Press Run the study and read the sentence at the top.

**How it works.** One wider picture is fetched once. The box is cut out of it at each shifted position, and the cut-outs are compared with the original.

**What it cannot do.** Pictures are compared at the resolution of the wider picture, so small shifts are only rough. The facility signal is a simple index, not a recognised facility.

### Gas targets in the placement study

*Shows how a shifted label window changes the gas value.*

**What it is.** Computes the gas value (window minus the background ring) at each shifted position from satellite gas columns, and compares the change with the day-to-day spread at the original position.

**Why it matters.** It shows whether shifting the box matters for the gas values you will predict, or only for the picture.

**How to use it.**

1. Tick one or more gases.
2. Run the study. With Earth Engine this reads real satellite data.
3. Read the tolerance in each table heading.

**How it works.** A shift is small if the typical change stays within a quarter of the day-to-day spread. The tool also shows the change in standard errors of the average.

**What it cannot do.** Gas pixels are several kilometres wide and the daily maps are smoothed, so small shifts may show almost no change. The demo backend gives synthetic values for practice only.

### Compare with simpler models

*Checks whether the extra numbers are worth collecting.*

**What it is.** Scores the forecast with each screening number alone and with all of them together, using the same held-out check, and compares them with guessing the average.

**Why it matters.** If one cheap number does as well as six, you can collect only that one. If the larger model is no better than guessing, the forecast is not worth using.

**How to use it.**

1. Press Check the forecast first to make sure the table is loaded.
2. Press Compare with simpler models and wait.
3. Read the sentence at the top, then the table.

**How it works.** Each row repeats the leave-cluster-out check, so it takes about as long as the forecast check once for every number.

**What it cannot do.** The numbers are only as stable as your sample. With few sites a small difference between two rows is not worth reading into.

## Checks and records

### Quality flags

*Warnings about a site.*

**What it is.** Flags for a box outside the allowed range, two sites very close, overlapping label windows, a split conflict, a role that differs from nearby sites, low coordinate confidence, and a site marked verified whose centre was never moved.

**Why it matters.** They point you to the sites most likely to be wrong, so you spend time where it matters.

**How to use it.**

1. Open Quality flags in the details bar.
2. Use the Quality filter to list only flagged sites.

**How it works.** Flags are computed from the roster and the screening numbers, with fixed limits.

**What it cannot do.** A flag is a reason to look, not a verdict. No flag does not mean a site is right.

### Neighbours within 150 km

*Nearby sites and what they force on the split.*

**What it is.** Lists every other site within the split radius, with its distance and role.

**Why it matters.** It tells you whether a site can go to training, to testing, or neither.

**How to use it.**

1. Open Neighbours in the details bar.
2. Use Set role to follow the rule in one click.

**How it works.** Distances are great-circle distances between centres. Rejected sites are ignored.

**What it cannot do.** It checks centres only. Large facilities can reach further.

### Screening numbers

*Quick facts about how well a site can be measured.*

**What it is.** Numbers copied from the notes: share of land in the 10 km window, how many clear satellite scenes there were, gas contrast, and fire days.

**Why it matters.** A site over water, or hidden by cloud most of the year, will give few usable samples.

**How to use it.**

1. Open Screening numbers. Each has a plain-word reading.

**How it works.** The tool reads them from the notes field.

**What it cannot do.** If the notes do not contain them, nothing is shown.

### Data availability check (preflight)

*Does each data source have data for the period?*

**What it is.** Asks Earth Engine whether each satellite and weather collection has data in the date range.

**Why it matters.** It finds missing data sources before a long collection run.

**How to use it.**

1. Open Tools, then Check data availability.

**How it works.** One small request per collection.

**What it cannot do.** Needs Earth Engine. It checks that collections exist, not that every site is covered.

### Estimate coverage

*A rough count of scenes for a box.*

**What it is.** Counts Sentinel-2 scenes with little cloud and Sentinel-5P granules for the box, and compares with the number of time windows.

**Why it matters.** A site with very few clear scenes will yield few samples.

**How to use it.**

1. Press Estimate coverage in Position and box.

**How it works.** Counts are made in Earth Engine over the date range.

**What it cannot do.** Rough only. It is not the real pass rate of a collection run.

### File check (validator)

*Check a roster file against the rules.*

**What it is.** Reads the file and lists errors (the file cannot be used) and warnings (advice). It checks required fields, roles, centres, box sizes, unique identifiers and more.

**Why it matters.** A bad file stops a later step, often far from the cause. The check finds the problem now, in plain words.

**How to use it.**

1. Open Tools, then Check this file.
2. Or run: python validator.py sites.json

**How it works.** The same checker runs before every save, so the file on disk is always valid. It needs no other software.

**What it cannot do.** It checks structure and ranges. It cannot tell whether a centre is on the right facility.

### Provenance record

*A file that says how the roster was made.*

**What it is.** A JSON file with counts, the review history summary, the tool and library versions, which imagery was used as evidence, and a fingerprint (hash) of the exact roster.

**Why it matters.** Anyone can later check that the roster they hold is the one the record describes, and how it was produced.

**How to use it.**

1. Open Export, then Provenance record.
2. Tick Include my comments only if you want them in the file.

**How it works.** The hash is computed from the roster in a fixed form. Change one value and the hash changes.

**What it cannot do.** It records what the tool knows. It cannot prove who was at the keyboard.

### Datasheet

*A document describing the roster, in seven standard sections.*

**What it is.** A Markdown document (Motivation, Composition, Collection process, Preprocessing, Uses, Distribution, Maintenance) filled in from the roster and review log. Questions only you can answer are marked [TO COMPLETE].

**Why it matters.** A clear description helps others use the roster properly and is expected when you share data.

**How to use it.**

1. Open Export, then Datasheet.
2. Fill the questions in the form, or edit the downloaded file.

**How it works.** Numbers come from the file. The tool counts how many questions are still open.

**What it cannot do.** It does not write your answers for you. A datasheet with blanks is shown as incomplete.

### Review log

*A record of every change.*

**What it is.** Every save, keep, reject, delete and import is written to a log with the time and the site.

**Why it matters.** You can see what changed and when, and it feeds the provenance record.

**How to use it.**

1. Open Tools, then Backup browser to see changes, or read audit.log.jsonl.

**How it works.** One line per change, added to the end of the file.

**What it cannot do.** The log is a local file. Anyone who can edit the folder can edit the log.

### Backups

*A copy of the file before every save.*

**What it is.** Before each write the tool copies the previous file into a backups folder with a time stamp. The backup browser shows differences and restores a copy.

**Why it matters.** You can go back to any earlier state, even after closing the tool.

**How to use it.**

1. Open Tools, then Backup browser.
2. Pick a backup, read the differences, press Restore.

**How it works.** Restoring is itself saved as a change, so it can be undone.

**What it cannot do.** Backups use disk space. Delete old ones in the folder when you no longer need them.

### Export

*Download kept, verified, rejected or all sites.*

**What it is.** Choose which sites and a format (JSON or CSV). Provenance and datasheet downloads are here too.

**Why it matters.** The cleaned file is the result of your review.

**How to use it.**

1. Press Export in the top bar.
2. Choose, then press Download.

**How it works.** A JSON export is checked by the validator before it is offered.

**What it cannot do.** Private comments are left out unless you tick the box.

### Import or merge a file

*Bring in sites from another file, with a preview.*

**What it is.** Reads another sites file and shows new sites, identifier clashes and sites very close to existing ones before anything changes.

**Why it matters.** Merging by hand is a common source of duplicate sites.

**How to use it.**

1. Open Tools, then Import or merge.
2. Pick the file and a rule for clashes.
3. Read the preview, then press Apply.

**How it works.** Nothing is written until Apply. The result is validated.

**What it cannot do.** It cannot decide which of two near-duplicate sites is right. You decide.

### Roster report

*A printable summary of all sites.*

**What it is.** A web page with a table of every site, small pictures if you fetched them, and the warnings. Print it to PDF.

**Why it matters.** A page you can share with someone who does not use the tool.

**How to use it.**

1. Open Tools, then Open roster report.

**How it works.** It is built from the file and the picture cache.

**What it cannot do.** Pictures appear only for sites where you fetched imagery.

## Settings and access

### Themes and accessibility

*Dark, light, high contrast, text size, reduced motion.*

**What it is.** Choose a theme, scale the text from 80 to 160 percent, reduce motion, and make the drag handles larger.

**Why it matters.** The tool should be comfortable for everyone, in any light.

**How to use it.**

1. Open Settings.

**How it works.** Your choices are saved in this browser.

**What it cannot do.** If your browser blocks storage the tool still works but forgets your choices.

### Focus mode

*Hide everything except the map.*

**What it is.** Hides both side bars and extra controls for a clean map.

**Why it matters.** A large clean map is the best way to place a box.

**How to use it.**

1. Press F. Press F or Esc to bring everything back.

**How it works.** The tool remembers what was open and restores it.

**What it cannot do.** Review shortcuts still work, but their buttons are hidden.

### Keyboard shortcuts

*Do everything without the mouse.*

**What it is.** Single keys for the common actions, for example J and K to move, V, X and S to decide, E for quick edit, F for focus.

**Why it matters.** Reviewing hundreds of sites is much faster by keyboard.

**How to use it.**

1. Press ? to see the full list.

**How it works.** Shortcuts are ignored while you type in a field.

**What it cannot do.** Some screen readers use the same keys. Turn the shortcuts off in Settings if they get in the way.
