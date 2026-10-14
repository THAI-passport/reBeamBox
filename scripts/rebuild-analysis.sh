#!/usr/bin/env sh
# Thin wrapper: the implementation is scripts/rebuild_analysis.py (Python 3 standard library; Linux, macOS, Windows).
# Usage: scripts/rebuild-analysis.sh [options]   (see --help)
d=$(cd "$(dirname "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then exec python3 "$d/rebuild_analysis.py" "$@"; fi
exec python "$d/rebuild_analysis.py" "$@"
