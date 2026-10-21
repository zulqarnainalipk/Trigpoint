# A workflow for building a benchmark roster

The order that uses the tool's parts without redoing work. Each step says what you will have at the end and which window to use. The demo roster lets you rehearse all of it first.

1. **Load or start a roster.** Point the tool at your sites file (`SITE_CURATOR_SITES`) or add sites by place name or on the map. Fix every box and centre against a picture. You end with a roster the validator accepts.
2. **Look at the picture the right way.** In Imagery choose the cloudless median or the clear-sky layer for cloudy places, and an index view where colour is not enough. Use the candidate outlines as a guide, never as a decision. You end with positions you have checked by eye.
3. **Ground the positions** (Studies, Coordinates). Add a registry and compare. Open every site that disagrees and decide. You end with fewer sites whose position rests on memory alone.
4. **Decide how tight a position has to be** (Studies, Placement). Run the study on a few typical sites. If a 1 km shift already loses half the facility, the box needs a careful look; if the gas label does not change for several kilometres, the label does not need the same care. You end with a stated tolerance.
5. **Forecast before you collect** (Studies, Forecast). Load a table of screening numbers (and, after a first collection, outcomes). Check the forecast, compare it with simpler models, and fit it. Look first at the sites with the lowest forecast. You end with a list of sites to examine before spending collection time.
6. **Assign roles and keep overlapping sites together** (Studies, Split safety, Overlap groups). Write the group ids into the roster and give whole groups to one side.
7. **Check for copies and shift** (Studies, Split safety). Fetch pictures, look for near-duplicates, and compare the two sides. You end with a list of copies (hopefully empty) and a number for how different the sides are.
8. **Build the certificate.** Enter the training and test periods and a target column if you have one. Fix every failure, run it again, and keep the file with the roster.
9. **Write the records.** Export the kept sites, the provenance record and the datasheet. The record names the certificate and the forecast check you ran.

Things that are easy to get wrong:

* A certificate that says conditional has checks that were not run. Read the list.
* A forecast checked on a few dozen sites moves when one site changes. Report the sample size with the error.
* The tool measures what it is given. A registry with the wrong coordinates, a table with the wrong ids, or boxes of the wrong size give wrong answers without an error.
