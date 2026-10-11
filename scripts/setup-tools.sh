#!/usr/bin/env bash
# Installs RE tools into ~/tools without sudo. Idempotent.
# Usage: scripts/setup-tools.sh [--full | --emulation]
#   default      JDK, jadx, apktool, and a venv with core + test only (bleak, pillow, pytest); never needs a compiler
#   --emulation  also install the emulation extras (unicorn, capstone, pyelftools); a failed build is reported, not fatal
#   --full       same as --emulation
set -euo pipefail
EMU=0
for a in "$@"; do
  case "$a" in
    --full|--emulation) EMU=1 ;;
    -h|--help) sed -n 2,6p "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
T="$HOME/tools"; mkdir -p "$T"; cd "$T"
if [ ! -d "$T/jdk" ]; then
  curl -fL "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse" -o jdk.tgz
  mkdir jdk && tar xzf jdk.tgz -C jdk --strip-components=1 && rm jdk.tgz
fi
export JAVA_HOME="$T/jdk" PATH="$T/jdk/bin:$PATH"
if [ ! -d "$T/jadx" ]; then
  V=$(curl -fsSL https://api.github.com/repos/skylot/jadx/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"].lstrip("v"))')
  curl -fL "https://github.com/skylot/jadx/releases/download/v$V/jadx-$V.zip" -o jadx.zip
  mkdir jadx && unzip -q jadx.zip -d jadx && rm jadx.zip
fi
if [ ! -f "$T/apktool/apktool.jar" ]; then
  mkdir -p apktool
  U=$(curl -fsSL https://api.github.com/repos/iBotPeaches/Apktool/releases/latest | python3 -c 'import sys,json;print([a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith(".jar")][0])')
  curl -fL "$U" -o apktool/apktool.jar
  printf '#!/usr/bin/env bash\nexec "%s/jdk/bin/java" -jar "%s/apktool/apktool.jar" "$@"\n' "$T" "$T" > apktool/apktool
  chmod +x apktool/apktool
fi
LINE='export JAVA_HOME="$HOME/tools/jdk"; export PATH="$JAVA_HOME/bin:$HOME/tools/jadx/bin:$HOME/tools/apktool:$PATH"'
grep -qF 'tools/jadx/bin' ~/.bashrc || echo "$LINE" >> ~/.bashrc
cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -e ".[test]"
if [ "$EMU" = 1 ]; then
  if .venv/bin/pip install -q -e ".[emulation]"; then echo "emulation extras installed"
  else echo "emulation extras could not be installed (no wheel or no build chain); core and test are fine, emulation tests will skip" >&2; fi
fi
command -v tshark >/dev/null || (apt-get install -y tshark 2>/dev/null || echo "tshark unavailable without root")
