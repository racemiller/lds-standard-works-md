#!/bin/bash

 
URLS="genconf_organizer/conf-urls.txt"
PY="/home/race/conference/.venv/bin/python"
SCRAPER="generalconference_scraper/simple_gcscraper_byperiod_patched.py"
 
while IFS= read -r line; do
    [ -z "$line" ] && continue          # skip blank lines
    echo "Processing $line"
    "$PY" "$SCRAPER" "$line" </dev/null
done < "$URLS"