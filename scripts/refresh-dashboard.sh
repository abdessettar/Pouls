#!/usr/bin/env bash
# Rebuild the warehouse from data/, then the Pouls dashboard from scratch.
#
#   scripts/refresh-dashboard.sh           parse + build + diff, clear the loader cache, build the site
#   scripts/refresh-dashboard.sh --build   skip parsing: rebuild curated/derived/marts from staging
#   scripts/refresh-dashboard.sh --serve   ... then serve dashboard/dist on http://127.0.0.1:3001
#   scripts/refresh-dashboard.sh --lan     ... then serve it to other devices on the home network
set -euo pipefail
cd "$(dirname "$0")/.."

step=all
serve=0
for arg in "$@"; do
  case "$arg" in
    --build) step=build ;;
    --serve) serve=1 ;;
    --lan) serve=lan ;;
    -h | --help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

# Place names for map areas (a public GeoNames file, fetched once); without it areas keep time-zone names.
[ -f reference/geonames/cities15000.zip ] || scripts/fetch-place-names.sh || echo "place names: download failed; using time-zone cities"

uv run apple-health "$step"

cd dashboard
[ -d node_modules ] || npm install
npm run clean   # loaders are cached by source file, not by warehouse contents
npm run build

case "$serve" in
  1) exec npm run serve ;;
  lan) exec npm run serve:lan ;;
esac
