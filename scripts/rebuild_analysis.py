#!/usr/bin/env python3
"""Rebuild analysis/ (XAPK, base APK, native split, jadx tree) from analysis/sources.env. No sudo. Idempotent.
Pure Python 3 standard library: runs the same on Linux, macOS and Windows (scripts/rebuild-analysis.sh is a thin wrapper).

Usage: scripts/rebuild-analysis.sh [options]      (or: python scripts/rebuild_analysis.py [options])
  --sources FILE      key=value file (default analysis/sources.env)
  --local-file PATH   use this XAPK instead of downloading it (hash is still verified)
  --url URL           download from this URL instead of URL in sources.env (hash is still verified)
  --accept-new-hash   on a hash mismatch print the new hash and continue; never edits any file
  --recover           after jadx, run scripts/recover-failed-methods.sh (CFR recovery; needs bash)
  --max-heap SIZE     JVM heap for jadx, for example 3g (overrides JADX_HEAP; default: 3g when the machine has under 8 GiB RAM)
  --force             redo every step, and downgrade a tool version mismatch to a warning
  --dry-run           print what would happen; no download, no extraction, no jadx
  --root DIR          repository root (default: parent of scripts/); used by tests
  -h, --help          this text
Exit codes: 0 ok, 2 usage or sources error, 3 hash mismatch, 4 missing tool or tool version, 5 step failed.
Needs: java and jadx (see scripts/setup_tools.py). Output (all git-ignored): analysis/apk, analysis/work, analysis/decompiled,
analysis/jadx.log, analysis/BUILD-INFO.txt.
"""
import datetime
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

SELF_DIR = os.path.dirname(os.path.abspath(__file__))
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Fail(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def say(msg):
    print("[rebuild] " + msg, flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()



def version_note(path, pinned):
    """If `path` is an XAPK with a manifest.json, say which version it really is (explains a hash mismatch after a vendor update)."""
    try:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read("manifest.json"))
        return "the file says version_name=%s version_code=%s; SOURCES pins version %s" % (m.get("version_name"), m.get("version_code"), pinned)
    except Exception:  # noqa: BLE001
        return ""


def tool_path():
    """PATH with the user-space toolchain installed by tools/setup_tools.py in front (works on all platforms)."""
    home = os.path.expanduser("~/tools")
    java_home = os.environ.get("JAVA_HOME") or os.path.join(home, "jdk")
    extra = [os.path.join(java_home, "bin"), os.path.join(home, "jadx", "bin"), os.path.join(home, "apktool")]
    return os.pathsep.join(extra + [os.environ.get("PATH", "")])


def total_ram_gib():
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 2 ** 30
    except (AttributeError, ValueError, OSError):
        return None


def parse_sources(path, root):
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    raw = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
            if not m:
                raise Fail(2, "bad line in %s: %s" % (rel, line))
            raw[m.group(1)] = m.group(2)
    for k in ("PACKAGE", "VERSION", "XAPK_NAME", "XAPK_SHA256", "BASE_APK_NAME", "BASE_APK_SHA256"):
        if not raw.get(k):
            raise Fail(2, "%s: missing %s" % (rel, k))
    for k in ("XAPK_SHA256", "BASE_APK_SHA256", "ABI_APK_SHA256"):
        if raw.get(k) and not HEX64.match(raw[k]):
            raise Fail(2, "%s: %s is not a lowercase 64-digit sha256" % (rel, k))
    if raw.get("ABI_APK_NAME") and not raw.get("ABI_APK_SHA256"):
        raise Fail(2, "%s: ABI_APK_NAME needs ABI_APK_SHA256" % rel)
    names = raw["XAPK_NAME"] + raw["BASE_APK_NAME"] + raw.get("ABI_APK_NAME", "")
    if "/" in names or "\\" in names or ".." in names:
        raise Fail(2, "file names in %s must not contain / or .." % rel)
    s = dict(raw, NAME_FILE=raw["XAPK_NAME"], SHA256=raw["XAPK_SHA256"], INNER_APK=raw["BASE_APK_NAME"],
             INNER_SHA256=raw["BASE_APK_SHA256"], ABI_APK=raw.get("ABI_APK_NAME", ""), ABI_SHA256=raw.get("ABI_APK_SHA256", ""))
    return s, rel, "xapk"


def parse_args(argv):
    o = dict(sources=None, local=None, url=None, accept=False, recover=False, force=False, dry=False,
             heap="", root=os.path.dirname(SELF_DIR), help=False)
    valued = {"--sources": "sources", "--local-file": "local", "--url": "url", "--root": "root", "--max-heap": "heap"}
    flags = {"--accept-new-hash": "accept", "--recover": "recover", "--force": "force", "--dry-run": "dry"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            o["help"] = True
        elif a in valued:
            if i + 1 >= len(argv):
                raise Fail(2, "%s needs a value" % a)
            o[valued[a]] = argv[i + 1]
            i += 1
        elif a in flags:
            o[flags[a]] = True
        elif a.startswith("-"):
            raise Fail(2, "unknown option: %s (try --help)" % a)
        else:
            raise Fail(2, "unexpected argument: %s (try --help)" % a)
        i += 1
    return o


class Run:
    def __init__(self, o):
        self.o = o
        self.mismatch_accepted = False
        self.pinned = ""

    def verify(self, path, expected, label):
        got = sha256_file(path)
        if got == expected:
            say("sha256 ok: " + label)
            return
        sys.stderr.write("error: sha256 mismatch for %s\n  expected: %s\n  actual:   %s\n" % (label, expected, got))
        note = version_note(path, self.pinned)
        if note:
            sys.stderr.write("  note: %s. A moved 'latest' URL is the usual cause: find the exact file, then pass --local-file or add it as URL2.\n" % note)
        if self.o["accept"]:
            sys.stderr.write("  --accept-new-hash given: continuing. Record this hash yourself in SOURCES if it is the new reference; no file was edited.\n")
            return
        sys.stderr.write("  refusing to continue. If the source legitimately changed, inspect it, then re-run with --accept-new-hash.\n")
        raise Fail(3, None)

    def download(self, url, dest):
        say("download " + url)
        if self.o["dry"]:
            say("would run: download %s -> %s" % (url, dest))
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        part = dest + ".part"
        last = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
                os.replace(part, dest)
                return
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1 + attempt)
        raise Fail(5, "download failed: %s" % last)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        return rebuild(argv)
    except Fail as f:
        if f.msg:
            sys.stderr.write("error: %s\n" % f.msg)
        return f.code


def rebuild(argv):
    o = parse_args(argv)
    if o["help"]:
        print(__doc__.split("Usage: ", 1)[1].rstrip())
        return 0
    if o["local"] and not os.path.isfile(o["local"]):
        raise Fail(2, "--local-file not found: %s" % o["local"])
    root = os.path.abspath(o["root"])
    A = os.path.join(root, "analysis")
    src = o["sources"] or os.path.join(A, "sources.env")
    if not os.path.isfile(src):
        raise Fail(2, "sources file not found: %s" % src)
    S, srel, kind = parse_sources(src, root)
    r = Run(o)
    r.pinned = S["VERSION"]
    dry, force = o["dry"], o["force"]
    art = os.path.join(A, "apk", S["NAME_FILE"])
    W, OUT = os.path.join(A, "work"), os.path.join(A, "decompiled")
    jadx_args = shlex.split(S.get("JADX_ARGS", "-j 4"))
    env = dict(os.environ, PATH=tool_path())

    say("target %s %s" % (S["PACKAGE"], S["VERSION"]))
    if dry:
        say("dry run: nothing will be written")

    # 1. acquire
    if o["local"]:
        fpath = o["local"]
        say("using local file " + fpath)
    elif os.path.isfile(art) and not force:
        fpath = art
        say("archive already present: " + art)
    else:
        urls = [o["url"]] if o["url"] else [S[k] for k in ("URL", "URL2", "URL3", "URL4") if S.get(k)]
        if not urls:
            raise Fail(2, "%s: no URL and %s not present (add URL or pass --local-file)" % (srel, "archive"))
        for i, url in enumerate(urls):
            r.download(url, art)
            if dry or not os.path.isfile(art) or sha256_file(art) == S["SHA256"] or i + 1 == len(urls):
                break
            say("hash does not match the file from this URL; trying the next URL (%d of %d)" % (i + 2, len(urls)))
        fpath = art
    if os.path.isfile(fpath):
        r.verify(fpath, S["SHA256"], "XAPK")
        if os.path.abspath(fpath) != os.path.abspath(art) and not dry:
            os.makedirs(os.path.dirname(art), exist_ok=True)
            shutil.copyfile(fpath, art)
    elif dry:
        say("(archive not present yet; hash would be checked after download)")

    # 2. extract (xapk only) and pick the APK to decompile
    base, base_sha = None, S["SHA256"]
    if kind == "xapk":
        base = os.path.join(W, S["INNER_APK"])
        abi = os.path.join(W, S["ABI_APK"]) if S.get("ABI_APK") else None
        ok = (not force and os.path.isfile(base) and sha256_file(base) == S["INNER_SHA256"]
              and (abi is None or (os.path.isfile(abi) and sha256_file(abi) == S["ABI_SHA256"])))
        if ok:
            say("extracted APKs already present and verified")
        else:
            if not dry and not os.path.isfile(fpath):
                raise Fail(5, "archive missing")
            members = [S["INNER_APK"]] + ([S["ABI_APK"]] if abi else [])
            say("extract %s into analysis/work" % " ".join(members))
            if dry:
                say("would run: extract %s" % " ".join(members))
            else:
                os.makedirs(W, exist_ok=True)
                try:
                    with zipfile.ZipFile(fpath) as z:
                        names = z.namelist()
                        for m in members:
                            cand = [n for n in names if n == m or n.endswith("/" + m)]
                            if not cand:
                                raise KeyError(m)
                            with z.open(cand[0]) as src_f, open(os.path.join(W, m), "wb") as dst:
                                shutil.copyfileobj(src_f, dst)
                except (KeyError, zipfile.BadZipFile, OSError) as e:
                    raise Fail(5, "could not extract %s from the archive (%s)" % (" ".join(members), e))
                r.verify(base, S["INNER_SHA256"], "base APK")
                if abi:
                    r.verify(abi, S["ABI_SHA256"], "ABI split")
        base_sha = S["INNER_SHA256"]
    elif kind == "apk":
        base = fpath
    else:
        say("KIND=other: download and verify only, no decompile")

    # 3. tools and jadx (apk kinds only)
    jadx_v = java_v = ""
    if True:
        def tool_problem(msg):
            if force:
                sys.stderr.write("warning: %s\n" % msg)
            else:
                raise Fail(4, "%s (re-run with --force to accept, or fix with scripts/setup_tools.py)" % msg)
        if not dry:
            if not shutil.which("java", path=env["PATH"]):
                raise Fail(4, "java not found; run scripts/setup_tools.py")
            jadx = shutil.which("jadx", path=env["PATH"])
            if not jadx:
                raise Fail(4, "jadx not found; run tools/setup-tools.sh")
            out = subprocess.run([jadx, "--version"], capture_output=True, text=True, env=env)
            jadx_v = (out.stdout.strip().splitlines() or [""])[0].strip()
            jo = subprocess.run([shutil.which("java", path=env["PATH"]), "-version"], capture_output=True, text=True, env=env)
            java_v = (jo.stderr.strip().splitlines() or [""])[0]
            if S.get("JADX_VERSION") and jadx_v != S["JADX_VERSION"]:
                tool_problem("jadx version is '%s', SOURCES pins %s" % (jadx_v, S["JADX_VERSION"]))
            if S.get("JAVA_MAJOR") and ('"%s' % S["JAVA_MAJOR"]) not in java_v:
                tool_problem("java is '%s', SOURCES pins major %s" % (java_v, S["JAVA_MAJOR"]))
        else:
            say("tool check skipped in dry run (pins: jadx %s, java %s)" % (S.get("JADX_VERSION", "any"), S.get("JAVA_MAJOR", "any")))

        # heap: explicit option, then SOURCES, then a safe default on small machines (jadx was OOM-killed on shared boxes)
        heap = o["heap"] or S.get("JADX_HEAP", "")
        if not heap and "JAVA_OPTS" not in os.environ and "-Xmx" not in os.environ.get("JADX_OPTS", ""):
            ram = total_ram_gib()
            if ram is not None and ram < 8:
                heap = "3g"
        if heap:
            if not re.match(r"^[0-9]+[kKmMgG]$", heap):
                raise Fail(2, "heap must look like 3g or 2048m, got '%s'" % heap)
            env["JAVA_OPTS"] = ("%s -Xmx%s" % (env.get("JAVA_OPTS", ""), heap)).strip()
            say("jadx heap capped at -Xmx%s" % heap)

        mark = os.path.join(A, "jadx.done")
        done = False
        if not force and os.path.isdir(OUT) and os.path.isfile(mark):
            txt = open(mark, encoding="utf-8").read()
            done = ("base_sha256=%s" % base_sha) in txt and re.search(r"^exit=(0|3) ", txt, re.M) is not None
        if done:
            say("decompiled tree already built for this APK (use --force to redo)")
        else:
            cmd = ["jadx"] + jadx_args + ["-d", OUT, base]
            say("jadx %s -> analysis/decompiled" % " ".join(jadx_args))
            if dry:
                say("would run: " + " ".join(cmd))
            else:
                os.makedirs(OUT, exist_ok=True)
                os.makedirs(W, exist_ok=True)
                cmd[0] = shutil.which("jadx", path=env["PATH"])
                start = time.time()
                with open(os.path.join(A, "jadx.log"), "w") as log:
                    rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
                with open(mark, "w") as f:
                    f.write("exit=%d seconds=%d base_sha256=%s\n" % (rc, time.time() - start, base_sha))
                if rc in (0, 3):
                    say("jadx finished (exit %d)" % rc)
                else:
                    hint = ""
                    if rc in (137, -9):
                        hint = " (killed, probably out of memory: retry with --max-heap 2g, or free memory)"
                    raise Fail(5, "jadx failed with exit %d%s, see analysis/jadx.log" % (rc, hint))

        if o["recover"]:
            if not shutil.which("bash"):
                raise Fail(4, "--recover needs bash (Git Bash or WSL on Windows)")
            say("CFR recovery")
            cmd = ["bash", os.path.join(SELF_DIR, "recover-failed-methods.sh")]
            if dry:
                say("would run: " + " ".join(cmd))
            elif subprocess.run(cmd, env=env).returncode != 0:
                raise Fail(5, "recovery script failed")

    # 4. build info
    if not dry:
        lines = ["built_at=" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "package=" + S["PACKAGE"], "version=" + S["VERSION"], "xapk_sha256=" + sha256_file(fpath),
                 "base_apk_sha256=" + sha256_file(base)]
        if S.get("ABI_APK"):
            lines.append("abi_apk_sha256=" + sha256_file(os.path.join(W, S["ABI_APK"])))
        lines += ["accepted_new_hash=%d" % (1 if o["accept"] else 0), "recover=%d" % (1 if o["recover"] else 0),
                  "jadx=" + jadx_v, "java=" + java_v, "jadx_args=" + " ".join(jadx_args),
                  "host=%s %s" % (platform.system(), platform.machine())]
        with open(os.path.join(A, "BUILD-INFO.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        say("wrote analysis/BUILD-INFO.txt")
    say("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
