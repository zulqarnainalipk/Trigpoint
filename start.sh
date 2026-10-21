#!/usr/bin/env sh
# Starts TrigPoint on the demo roster (synthetic scenes). Set SITE_CURATOR_SITES to open your own file.
cd "$(dirname "$0")" || exit 1
python3 server.py
