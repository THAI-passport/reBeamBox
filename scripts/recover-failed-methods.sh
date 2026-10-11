#!/usr/bin/env bash
# Re-decompile the base APK with other decompiler settings and CFR, to recover methods jadx's default mode fails on.
# Output stays under analysis/work (git-ignored). Needs the setup-tools.sh toolchain (Java, jadx).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-$HOME/tools/jdk}"; export PATH="$JAVA_HOME/bin:$HOME/tools/jadx/bin:$PATH"
W="$ROOT/analysis/work"; APK="$W/com.guangshen.beambox.apk"
# 1. simple mode keeps going where the region maker overflows (63 errors -> 35 on this APK)
jadx -m simple --show-bad-code -j 4 -d "$W/jadx-simple" --no-res --log-level ERROR "$APK" || true
# 2. CFR on one class: dex -> jar with dex2jar, then CFR with a jar filter
mkdir -p "$HOME/tools/cfr"; cd "$HOME/tools/cfr"
[ -f cfr.jar ] || curl -sSL -o cfr.jar https://repo1.maven.org/maven2/org/benf/cfr/0.152/cfr-0.152.jar
[ -d dex-tools-v2.4 ] || { curl -sSL -o d2j.zip https://github.com/pxb1988/dex2jar/releases/download/v2.4/dex-tools-v2.4.zip && unzip -qo d2j.zip; }
DEX="${1:-classes2.dex}"; CLASS="${2:-com.example.nn20.utils.BadgeMediaFileBuilder}"
cd "$W"; unzip -p "$APK" "$DEX" > "$W/cls.dex"
"$HOME/tools/cfr/dex-tools-v2.4/d2j-dex2jar.sh" "$W/cls.dex" -o "$W/cls.jar" --force
java -jar "$HOME/tools/cfr/cfr.jar" "$W/cls.jar" --jarfilter "$CLASS" --outputdir "$W/cfr-out"
echo "CFR output under $W/cfr-out"
