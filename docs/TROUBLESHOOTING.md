# Troubleshooting

**The page opens but the map is grey.** The map tiles and Leaflet come from the internet. Without a connection, use the list, review buttons and information card (`/?nomap=1`).

**"Another TrigPoint is already running."** Another copy uses the port. Close it, or set `SITE_CURATOR_PORT` to a different number.

**A save is refused.** The validator found a problem (bad role, box outside 1 to 8 km, repeated id, centre outside the valid range). The message names the site and the field. Nothing was written.

**I changed something by mistake.** `Ctrl+Z` undoes it in the session. Every save also makes a backup; open the backups list to see the difference and restore.

**Imagery says Earth Engine is not ready.** Switch the backend to `pc` or `demo`, or follow [BACKENDS.md](BACKENDS.md) to set up a key.

**Imagery is slow the first time.** The first fetch for a place downloads scenes. After that, view, stretch and fill changes use the saved copy. The cache is in `cache/` and is trimmed to `SITE_CURATOR_CACHE_MB` (default 500).

**"The saved image was damaged and has been removed."** A cache file was cut short, for example by a closed computer. Fetch again.

**The picture looks black in places.** Those pixels have no data. Try the band mean or nearest scene fill, or the cloudless median source.

**Text is too small or the page hurts to read.** Open Settings: larger text sizes, light, dark and high-contrast themes, reduced motion, and sliders in place of dragging.

**I want to know whether an installation works.** Run `python server.py --check`. It lists what passed and what failed, with advice for each.

**The tests fail with a missing module.** Install the requirements (`pip install -r requirements.txt`) in the same Python you run `pytest` with.

