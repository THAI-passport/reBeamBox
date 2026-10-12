#!/usr/bin/env python3
"""Install the reverse-engineering toolchain into ~/tools without admin rights. Linux, macOS and Windows. Idempotent.

    python scripts/setup_tools.py [--full | --emulation] [--no-venv] [--check]

  default      JDK 17 (Temurin), jadx, apktool in ~/tools; a venv at .venv with the project installed (core + test extras)
  --emulation  also unicorn, capstone, pyelftools (failure is reported, not fatal); --full is the same
  --no-venv    skip the venv
  --check      only print what would be downloaded for this machine
Environment: JADX_VERSION (1.5.6), APKTOOL_VERSION (3.0.3), JDK_MAJOR (17). Set JADX_SHA256 / APKTOOL_SHA256 to verify the
downloads; the computed hashes are always printed so you can pin them.
Linux/macOS: scripts/setup-tools.sh is a wrapper. Windows: run this file with Python from PowerShell.
"""
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JADX_VERSION = os.environ.get("JADX_VERSION", "1.5.6")
APKTOOL_VERSION = os.environ.get("APKTOOL_VERSION", "3.0.3")
JDK_MAJOR = os.environ.get("JDK_MAJOR", "17")


def host():
    sysname = {"Linux": "linux", "Darwin": "mac", "Windows": "windows"}.get(platform.system())
    m = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "aarch64", "aarch64": "aarch64"}.get(m)
    if not sysname or not arch:
        raise SystemExit("unsupported platform: %s %s" % (platform.system(), platform.machine()))
    return sysname, arch


def jdk_url():
    s, a = host()
    return "https://api.adoptium.net/v3/binary/latest/%s/ga/%s/%s/jdk/hotspot/normal/eclipse" % (JDK_MAJOR, s, a)


def jadx_url():
    return "https://github.com/skylot/jadx/releases/download/v%s/jadx-%s.zip" % (JADX_VERSION, JADX_VERSION)


def apktool_url():
    return "https://github.com/iBotPeaches/Apktool/releases/download/v%s/apktool_%s.jar" % (APKTOOL_VERSION, APKTOOL_VERSION)


def fetch(url, dest, expect=None, label=""):
    print("download %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
            f.write(chunk)
    print("  sha256 %s %s" % (h.hexdigest(), label))
    if expect and h.hexdigest() != expect.lower():
        os.remove(dest)
        raise SystemExit("sha256 mismatch for %s (expected %s)" % (label or url, expect))


def extract(archive, dest):
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            if hasattr(tarfile, "data_filter"):
                t.extractall(dest, filter="data")      # refuses absolute paths, links outside dest, device files
            else:
                t.extractall(dest)


def find_java_home(root):
    for dp, _dn, fns in os.walk(root):
        if os.path.basename(dp) == "bin" and ("java" in fns or "java.exe" in fns):
            return os.path.dirname(dp)
    return None


def install_jdk(tools):
    jdk = os.path.join(tools, "jdk")
    if os.path.isdir(jdk):
        print("jdk present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        arc = os.path.join(tmp, "jdk.zip" if host()[0] == "windows" else "jdk.tgz")
        fetch(jdk_url(), arc, label="JDK")
        out = os.path.join(tmp, "x")
        os.makedirs(out)
        extract(arc, out)
        home = find_java_home(out)
        if not home:
            raise SystemExit("could not find bin/java in the JDK archive")
        shutil.move(home, jdk)               # on macOS this lifts Contents/Home to ~/tools/jdk
    print("jdk installed")


def install_jadx(tools):
    d = os.path.join(tools, "jadx")
    if os.path.isdir(d):
        print("jadx present")
        return
    with tempfile.TemporaryDirectory() as tmp:
        arc = os.path.join(tmp, "jadx.zip")
        fetch(jadx_url(), arc, os.environ.get("JADX_SHA256"), "jadx %s" % JADX_VERSION)
        os.makedirs(d)
        extract(arc, d)
    for n in ("jadx", "jadx-gui"):
        p = os.path.join(d, "bin", n)
        if os.path.isfile(p):
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("jadx installed")


def install_apktool(tools):
    d = os.path.join(tools, "apktool")
    jar = os.path.join(d, "apktool.jar")
    if os.path.isfile(jar):
        print("apktool present")
        return
    os.makedirs(d, exist_ok=True)
    fetch(apktool_url(), jar, os.environ.get("APKTOOL_SHA256"), "apktool %s" % APKTOOL_VERSION)
    java = os.path.join(tools, "jdk", "bin", "java.exe" if host()[0] == "windows" else "java")
    if host()[0] == "windows":
        open(os.path.join(d, "apktool.bat"), "w").write('@echo off\r\n"%s" -jar "%s" %%*\r\n' % (java, jar))
    else:
        p = os.path.join(d, "apktool")
        open(p, "w").write('#!/bin/sh\nexec "%s" -jar "%s" "$@"\n' % (java, jar))
        os.chmod(p, 0o755)
    print("apktool installed")


def persist_path(tools):
    if host()[0] == "windows":
        print("Add to PATH (PowerShell, once):\n  setx JAVA_HOME \"%s\\jdk\"\n  setx PATH \"%%JAVA_HOME%%\\bin;%s\\jadx\\bin;%s\\apktool;%%PATH%%\"" % (tools, tools, tools))
        print("scripts/rebuild_analysis.py finds ~/tools without this.")
        return
    line = 'export JAVA_HOME="$HOME/tools/jdk"; export PATH="$JAVA_HOME/bin:$HOME/tools/jadx/bin:$HOME/tools/apktool:$PATH"'
    for rc in (".bashrc", ".zshrc") if host()[0] == "mac" else (".bashrc",):
        p = os.path.join(os.path.expanduser("~"), rc)
        old = open(p).read() if os.path.exists(p) else ""
        if "tools/jadx/bin" not in old and (rc != ".zshrc" or os.path.exists(p) or host()[0] == "mac"):
            with open(p, "a") as f:
                f.write(("\n" if old and not old.endswith("\n") else "") + line + "\n")
            print("added PATH line to ~/%s" % rc)


def make_venv(emulation):
    venv = os.path.join(ROOT, ".venv")
    if not os.path.isdir(venv):
        subprocess.check_call([sys.executable, "-m", "venv", venv])
    py = os.path.join(venv, "Scripts" if host()[0] == "windows" else "bin", "python" + (".exe" if host()[0] == "windows" else ""))
    subprocess.check_call([py, "-m", "pip", "install", "-q", "-e", ".[test]"], cwd=ROOT)
    if emulation:
        if subprocess.call([py, "-m", "pip", "install", "-q", "-e", ".[emulation]"], cwd=ROOT) == 0:
            print("emulation extras installed")
        else:
            print("emulation extras could not be installed (no wheel or no build chain); core and test are fine, emulation tests will skip", file=sys.stderr)


def main(argv=None):
    args = set(sys.argv[1:] if argv is None else argv)
    if args & {"-h", "--help"}:
        print(__doc__)
        return 0
    unknown = args - {"--full", "--emulation", "--no-venv", "--check"}
    if unknown:
        print("unknown option: %s" % " ".join(sorted(unknown)), file=sys.stderr)
        return 2
    if "--check" in args:
        print("host: %s/%s\njdk: %s\njadx: %s\napktool: %s" % (*host(), jdk_url(), jadx_url(), apktool_url()))
        return 0
    tools = os.path.join(os.path.expanduser("~"), "tools")
    os.makedirs(tools, exist_ok=True)
    install_jdk(tools)
    install_jadx(tools)
    install_apktool(tools)
    persist_path(tools)
    if "--no-venv" not in args:
        make_venv(bool(args & {"--full", "--emulation"}))
    if not shutil.which("tshark"):
        hint = {"mac": "brew install wireshark", "linux": "apt install tshark (needs root)", "windows": "install Wireshark"}[host()[0]]
        print("tshark not found (optional; tools/btcap.py reads captures without it): %s" % hint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
