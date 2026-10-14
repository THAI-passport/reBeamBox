#!/usr/bin/env sh
# Thin wrapper: the installer is scripts/setup_tools.py (Python 3 standard library; Linux, macOS, Windows).
# Usage: scripts/setup-tools.sh [--full | --emulation] [--no-venv] [--check]
d=$(cd "$(dirname "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then exec python3 "$d/setup_tools.py" "$@"; fi
exec python "$d/setup_tools.py" "$@"
