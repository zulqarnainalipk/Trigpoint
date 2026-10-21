# Usability and accessibility notes

What was checked, how, and what was not. Written so that a reader can tell a measurement from a claim.

## Task analysis (counted, not timed)

The number of deliberate actions (a click, a key press, a choice or typing a value) to do each job from a fresh start with the demo roster. Counted by walking through the interface; a key press and a click count the same.

| Job | Actions | Where |
|---|---|---|
| Open the first unreviewed site and keep it | 2 (`N`, `V`) | review bar |
| See a site in true colour from the demo backend | 2 (open the Imagery section, Fetch image) | details bar |
| Switch to a cloudless median and read the statistics | 4 (source, Fetch image, Statistics) | details bar |
| Find sites that overlap and would be split | 3 (Tools, Studies, Find groups) | Studies, Split safety |
| Build the split certificate | 3 (Tools, Studies, Build the certificate) | Studies, Split safety |
| Check a forecast on the demo table | 4 (Tools, Studies, Forecast tab, Try the demo table), then Check the forecast (5) | Studies, Forecast |
| See what a 2 km shift does to a site | 5 (open a site, Tools, Studies, Placement tab, Run) | Studies, Placement |
| Export the kept sites | 3 (Export, choose Kept sites, Download) | Export |

## Accessibility checks that were run

* An in-page audit (`tools/a11y_audit.js`) was run in the dark, light and high-contrast themes on every tab of the Studies window and on the main page: every control has a name, every target is at least 24 by 24 pixels (labels count for checkboxes), no text is below the contrast limit (4.5:1, or 3:1 for large text), and every form control has a label.
* Keyboard: every function can be reached with Tab, Enter, Space, Escape and the arrow keys. The Studies tabs follow the tabs pattern (arrow keys, Home and End). Dialogs are native `dialog` elements that trap focus and return it on close.
* Colour is never the only signal: results have a symbol and a word (pass, fail, look at this, not run).
* Charts have a text alternative and the same numbers in a table.
* Results regions are announced politely; errors are announced as alerts.
* Reduced motion is respected; text size can go to 160 per cent without horizontal scrolling.

## Where it was tested

* Windows 10 (build 19045), Python 3.12.10, numpy 2.5, scipy 1.18, rasterio 1.5, matplotlib 3.11.
* A Chromium-based browser (the one built into the Claude desktop app). Layout was checked at a desktop width, a 768 px tablet width and a 375 px phone width, at 100 and 160 per cent text size, in the dark, light and high-contrast themes.
* Earth Engine with a service account and Planetary Computer, live (see `docs/BACKENDS.md`).
* The GitHub Actions file (Ubuntu, Python 3.10 and 3.12) is written but has not run; other browsers and operating systems are untested.

## Not tested

* A real screen reader (NVDA, JAWS, VoiceOver) and a real touch device.
* People. No user study has been run, so there is no measured completion time or error rate. The count above is a lower bound on effort, not a measure of how easy the tool is. A short study (three to five people, five tasks, thinking aloud) is the next step.
* Other browsers than the one used here.
