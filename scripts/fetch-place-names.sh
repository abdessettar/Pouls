#!/usr/bin/env bash
# Download GeoNames' list of cities with 15,000+ people (CC BY 4.0, https://www.geonames.org), used
# to name map areas after real places. Only this public file is fetched; nothing is sent about you.
set -euo pipefail
cd "$(dirname "$0")/.."
dest=reference/geonames/cities15000.zip
mkdir -p "$(dirname "$dest")"
curl -fsSL --retry 2 -o "$dest.part" https://download.geonames.org/export/dump/cities15000.zip
mv "$dest.part" "$dest"
echo "wrote $dest ($(du -h "$dest" | cut -f1))"
