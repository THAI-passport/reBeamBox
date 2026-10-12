#!/usr/bin/env bash
# Rebuild analysis/ (APK, native split, jadx tree) from analysis/sources.env. No sudo. Idempotent.
#
# Usage: scripts/rebuild-analysis.sh [options]
#   --sources FILE      key=value file (default analysis/sources.env)
#   --local-file PATH   use this XAPK instead of downloading it (hash is still verified)
#   --accept-new-hash   on a hash mismatch print the new hash and continue; never edits any file
#   --recover           after jadx, run scripts/recover-failed-methods.sh (CFR recovery)
#   --force             redo every step, and downgrade a tool version mismatch to a warning
#   --dry-run           print what would happen; no download, no extraction, no jadx
#   --root DIR          repository root (default: parent of scripts/); used by tests
#   -h, --help          this text
# Exit codes: 0 ok, 2 usage or sources error, 3 hash mismatch, 4 missing tool or tool version, 5 step failed.
# Needs: unzip, sha256sum, curl (only when downloading), java and jadx (see scripts/setup-tools.sh).
# Output (all git-ignored): analysis/apk, analysis/work, analysis/decompiled, analysis/jadx.log, analysis/BUILD-INFO.txt.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SELF_DIR/.." && pwd)"
SOURCES="" LOCAL="" ACCEPT=0 RECOVER=0 FORCE=0 DRY=0

die() { echo "error: $2" >&2; exit "$1"; }
say() { echo "[rebuild] $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --sources) [ $# -ge 2 ] || die 2 "--sources needs a value"; SOURCES="$2"; shift 2 ;;
    --local-file) [ $# -ge 2 ] || die 2 "--local-file needs a value"; LOCAL="$2"; shift 2 ;;
    --root) [ $# -ge 2 ] || die 2 "--root needs a value"; ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --accept-new-hash) ACCEPT=1; shift ;;
    --recover) RECOVER=1; shift ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n 2,14p "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die 2 "unknown option: $1 (try --help)" ;;
  esac
done
[ -n "$SOURCES" ] || SOURCES="$ROOT/analysis/sources.env"
[ -f "$SOURCES" ] || die 2 "sources file not found: $SOURCES"
[ -z "$LOCAL" ] || [ -f "$LOCAL" ] || die 2 "--local-file not found: $LOCAL"

# Parse KEY=VALUE lines without executing anything.
declare -A S
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|'#'*) continue ;; esac
  [[ "$line" =~ ^([A-Z0-9_]+)=(.*)$ ]] || die 2 "bad line in $SOURCES: $line"
  S["${BASH_REMATCH[1]}"]="${BASH_REMATCH[2]}"
done < "$SOURCES"
for k in PACKAGE VERSION XAPK_NAME XAPK_SHA256 BASE_APK_NAME BASE_APK_SHA256; do
  [ -n "${S[$k]:-}" ] || die 2 "$SOURCES: missing $k"
done
[ -n "$LOCAL" ] || [ -n "${S[URL]:-}" ] || die 2 "$SOURCES: missing URL (or pass --local-file)"
for k in XAPK_SHA256 BASE_APK_SHA256 ABI_APK_SHA256; do
  [ -z "${S[$k]:-}" ] || [[ "${S[$k]}" =~ ^[0-9a-f]{64}$ ]] || die 2 "$SOURCES: $k is not a lowercase 64-digit sha256"
done
case "${S[XAPK_NAME]}${S[BASE_APK_NAME]}${S[ABI_APK_NAME]:-}" in */*|*..*) die 2 "file names in $SOURCES must not contain / or .." ;; esac

A="$ROOT/analysis"; XAPK="$A/apk/${S[XAPK_NAME]}"; W="$A/work"; OUT="$A/decompiled"
JADX_ARGS="${S[JADX_ARGS]:--j 4}"

run() { if [ "$DRY" = 1 ]; then say "would run: $*"; else "$@"; fi; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

# verify FILE EXPECTED LABEL: 0 on match (or accepted), exits 3 on mismatch
verify() {
  local got; got="$(sha "$1")"
  if [ "$got" = "$2" ]; then say "sha256 ok: $3"; return 0; fi
  echo "error: sha256 mismatch for $3" >&2
  echo "  expected: $2" >&2
  echo "  actual:   $got" >&2
  if [ "$ACCEPT" = 1 ]; then
    echo "  --accept-new-hash given: continuing. Record this hash yourself in analysis/sources.env and SOURCES.md if it is the new reference; no file was edited." >&2
    return 0
  fi
  echo "  refusing to continue. If the source legitimately changed, inspect it, then re-run with --accept-new-hash." >&2
  exit 3
}

say "target ${S[PACKAGE]} ${S[VERSION]}"
[ "$DRY" = 1 ] && say "dry run: nothing will be written"

# 1. acquire the XAPK
if [ -n "$LOCAL" ]; then
  SRC_FILE="$LOCAL"; say "using local file $LOCAL"
elif [ -f "$XAPK" ] && [ "$FORCE" = 0 ]; then
  SRC_FILE="$XAPK"; say "archive already present: $XAPK"
else
  command -v curl >/dev/null || die 4 "curl is required to download (or pass --local-file)"
  say "download ${S[URL]}"
  run mkdir -p "$A/apk"
  run curl -fL --retry 3 -o "$XAPK.part" "${S[URL]}" || die 5 "download failed"
  [ "$DRY" = 1 ] || mv "$XAPK.part" "$XAPK"
  SRC_FILE="$XAPK"
fi
if [ -f "$SRC_FILE" ]; then
  verify "$SRC_FILE" "${S[XAPK_SHA256]}" "XAPK"
  if [ ! "$SRC_FILE" -ef "$XAPK" ] && [ "$DRY" = 0 ]; then mkdir -p "$A/apk"; cp -f "$SRC_FILE" "$XAPK"; fi
elif [ "$DRY" = 1 ]; then say "(archive not present yet; hash would be checked after download)"
fi

# 2. extract base APK and ABI split
need_extract=1
if [ "$FORCE" = 0 ] && [ -f "$W/${S[BASE_APK_NAME]}" ] && [ "$(sha "$W/${S[BASE_APK_NAME]}")" = "${S[BASE_APK_SHA256]}" ]; then
  if [ -z "${S[ABI_APK_NAME]:-}" ] || { [ -f "$W/${S[ABI_APK_NAME]}" ] && [ "$(sha "$W/${S[ABI_APK_NAME]}")" = "${S[ABI_APK_SHA256]}" ]; }; then
    need_extract=0; say "extracted APKs already present and verified"
  fi
fi
if [ "$need_extract" = 1 ]; then
  command -v unzip >/dev/null || die 4 "unzip is required"
  [ "$DRY" = 1 ] || [ -f "$SRC_FILE" ] || die 5 "archive missing"
  run mkdir -p "$W"
  members=("${S[BASE_APK_NAME]}"); [ -z "${S[ABI_APK_NAME]:-}" ] || members+=("${S[ABI_APK_NAME]}")
  say "extract ${members[*]} into analysis/work"
  run unzip -oq -j "$SRC_FILE" "${members[@]}" -d "$W" || die 5 "could not extract ${members[*]} from the archive"
  if [ "$DRY" = 0 ]; then
    verify "$W/${S[BASE_APK_NAME]}" "${S[BASE_APK_SHA256]}" "base APK"
    [ -z "${S[ABI_APK_NAME]:-}" ] || verify "$W/${S[ABI_APK_NAME]}" "${S[ABI_APK_SHA256]}" "ABI split"
  fi
fi

# 3. tools
export JAVA_HOME="${JAVA_HOME:-$HOME/tools/jdk}"; export PATH="$JAVA_HOME/bin:$HOME/tools/jadx/bin:$PATH"
tool_problem() { if [ "$FORCE" = 1 ]; then echo "warning: $1" >&2; else die 4 "$1 (re-run with --force to accept, or fix with scripts/setup-tools.sh)"; fi; }
if [ "$DRY" = 0 ]; then
  command -v java >/dev/null || die 4 "java not found; run scripts/setup-tools.sh"
  command -v jadx >/dev/null || die 4 "jadx not found; run scripts/setup-tools.sh"
  JADX_V="$(jadx --version 2>/dev/null | head -1 | tr -d '\r' || true)"
  JAVA_V="$(java -version 2>&1 | head -1 || true)"
  [ -z "${S[JADX_VERSION]:-}" ] || [ "$JADX_V" = "${S[JADX_VERSION]}" ] || tool_problem "jadx version is '$JADX_V', sources.env pins ${S[JADX_VERSION]}"
  [ -z "${S[JAVA_MAJOR]:-}" ] || [[ "$JAVA_V" == *"\"${S[JAVA_MAJOR]}"* ]] || tool_problem "java is '$JAVA_V', sources.env pins major ${S[JAVA_MAJOR]}"
else
  say "tool check skipped in dry run (pins: jadx ${S[JADX_VERSION]:-any}, java ${S[JAVA_MAJOR]:-any})"
fi

# 4. jadx (exit 0 and 3 both mean a usable tree; 3 = some methods failed, see docs/SOP.md section 9)
MARK="$A/jadx.done"; BASE_SHA="${S[BASE_APK_SHA256]}"
if [ "$FORCE" = 0 ] && [ -d "$OUT" ] && [ -f "$MARK" ] && grep -q "base_sha256=$BASE_SHA" "$MARK" 2>/dev/null \
   && grep -qE '^exit=(0|3) ' "$MARK"; then
  say "decompiled tree already built for this APK (use --force to redo)"
else
  say "jadx $JADX_ARGS -> analysis/decompiled"
  if [ "$DRY" = 1 ]; then say "would run: jadx $JADX_ARGS -d $OUT $W/${S[BASE_APK_NAME]}"
  else
    mkdir -p "$OUT"; start=$(date +%s); rc=0
    # shellcheck disable=SC2086
    jadx $JADX_ARGS -d "$OUT" "$W/${S[BASE_APK_NAME]}" > "$A/jadx.log" 2>&1 || rc=$?
    echo "exit=$rc seconds=$(( $(date +%s) - start )) base_sha256=$BASE_SHA" > "$MARK"
    case "$rc" in 0|3) say "jadx finished (exit $rc)" ;; *) die 5 "jadx failed with exit $rc, see analysis/jadx.log" ;; esac
  fi
fi

# 5. optional CFR recovery
if [ "$RECOVER" = 1 ]; then
  say "CFR recovery"
  run bash "$SELF_DIR/recover-failed-methods.sh" || die 5 "recovery script failed"
fi

# 6. build info
if [ "$DRY" = 0 ]; then
  {
    echo "built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "package=${S[PACKAGE]}"; echo "version=${S[VERSION]}"
    echo "xapk_sha256=$(sha "$SRC_FILE")"; echo "base_apk_sha256=$(sha "$W/${S[BASE_APK_NAME]}")"
    [ -z "${S[ABI_APK_NAME]:-}" ] || echo "abi_apk_sha256=$(sha "$W/${S[ABI_APK_NAME]}")"
    echo "accepted_new_hash=$ACCEPT"; echo "recover=$RECOVER"
    echo "jadx=${JADX_V:-}"; echo "java=${JAVA_V:-}"; echo "jadx_args=$JADX_ARGS"
    echo "host=$(uname -sm)"
  } > "$A/BUILD-INFO.txt"
  say "wrote analysis/BUILD-INFO.txt"
fi
say "done"
