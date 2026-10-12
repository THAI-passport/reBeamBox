"""scripts/rebuild-analysis.sh: argument parsing, sources parsing and the hash safety paths, all offline."""
import hashlib
import os
import shutil
import stat
import subprocess
import zipfile

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "scripts", "rebuild-analysis.sh")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("unzip") is None or shutil.which("sha256sum") is None,
                                reason="needs bash, unzip and sha256sum")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def make_repo(tmp_path, xapk_hash=None, base_hash=None, extra=""):
    """A throwaway repo root holding a tiny fake XAPK (a zip with a fake base APK and ABI split) and a matching sources.env."""
    base, abi = b"fake base apk", b"fake abi split"
    xapk = tmp_path / "fake.xapk"
    with zipfile.ZipFile(xapk, "w") as z:
        z.writestr("com.example.app.apk", base)
        z.writestr("config.arm64_v8a.apk", abi)
    (tmp_path / "analysis").mkdir(exist_ok=True)
    (tmp_path / "analysis" / "sources.env").write_text(
        "PACKAGE=com.example.app\nVERSION=1.0\nURL=http://127.0.0.1:9/never\nXAPK_NAME=fake.xapk\n"
        "XAPK_SHA256=%s\nBASE_APK_NAME=com.example.app.apk\nBASE_APK_SHA256=%s\n"
        "ABI_APK_NAME=config.arm64_v8a.apk\nABI_APK_SHA256=%s\nJADX_VERSION=1.5.6\n%s"
        % (xapk_hash or sha(xapk.read_bytes()), base_hash or sha(base), sha(abi), extra))
    return xapk


def fake_tools(tmp_path, version="1.5.6", rc=0):
    """A fake jadx and java on PATH so the decompile step runs without the real toolchain."""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "jadx").write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo %s; exit 0; fi\n'
                            'while [ $# -gt 0 ]; do [ "$1" = "-d" ] && mkdir -p "$2/sources"; shift; done\n'
                            'echo ran >> "%s/jadx-calls"\nexit %d\n' % (version, tmp_path, rc))
    (b / "java").write_text('#!/bin/sh\necho \'openjdk version "17.0.1" 2024-01-01\' >&2\n')
    for f in b.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return str(b)


def run(tmp_path, *args, path=None, env=None):
    e = dict(os.environ, HOME=str(tmp_path / "home"))
    e["PATH"] = (path + os.pathsep if path else "") + e["PATH"]
    e["JAVA_HOME"] = str(tmp_path / "nojdk")
    if env:
        e.update(env)
    return subprocess.run(["bash", SCRIPT, "--root", str(tmp_path), *args], capture_output=True, text=True, env=e)


def test_help_and_unknown_option(tmp_path):
    r = subprocess.run(["bash", SCRIPT, "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--accept-new-hash" in r.stdout and "--dry-run" in r.stdout and "--recover" in r.stdout
    r = subprocess.run(["bash", SCRIPT, "--bogus"], capture_output=True, text=True)
    assert r.returncode == 2 and "unknown option: --bogus" in r.stderr
    r = subprocess.run(["bash", SCRIPT, "--local-file"], capture_output=True, text=True)
    assert r.returncode == 2 and "needs a value" in r.stderr


def test_missing_sources_and_missing_local_file(tmp_path):
    assert "sources file not found" in run(tmp_path).stderr and run(tmp_path).returncode == 2
    make_repo(tmp_path)
    r = run(tmp_path, "--local-file", str(tmp_path / "nope.xapk"))
    assert r.returncode == 2 and "--local-file not found" in r.stderr


@pytest.mark.parametrize("bad,msg", [("PACKAGE=x\nGARBAGE LINE\n", "bad line"), ("PACKAGE=x\n", "missing VERSION")])
def test_sources_validation(tmp_path, bad, msg):
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "sources.env").write_text(bad)
    r = run(tmp_path)
    assert r.returncode == 2 and msg in r.stderr


def test_sources_hash_format_and_path_traversal_rejected(tmp_path):
    xapk = make_repo(tmp_path, xapk_hash="ABC")
    r = run(tmp_path, "--local-file", str(xapk))
    assert r.returncode == 2 and "not a lowercase 64-digit sha256" in r.stderr
    make_repo(tmp_path)
    s = tmp_path / "analysis" / "sources.env"
    s.write_text(s.read_text().replace("XAPK_NAME=fake.xapk", "XAPK_NAME=../evil.xapk"))
    assert run(tmp_path, "--local-file", str(xapk)).returncode == 2


def test_sources_file_is_parsed_not_executed(tmp_path):
    xapk = make_repo(tmp_path)
    s = tmp_path / "analysis" / "sources.env"
    marker = tmp_path / "pwned"
    s.write_text(s.read_text() + "X=$(touch %s)\n" % marker)
    run(tmp_path, "--dry-run", "--local-file", str(xapk))
    assert not marker.exists()


def test_xapk_hash_mismatch_refuses_and_writes_nothing(tmp_path):
    xapk = make_repo(tmp_path, xapk_hash="0" * 64)
    r = run(tmp_path, "--local-file", str(xapk), path=fake_tools(tmp_path))
    assert r.returncode == 3
    assert "sha256 mismatch for XAPK" in r.stderr and "expected: " + "0" * 64 in r.stderr and "refusing to continue" in r.stderr
    assert not (tmp_path / "analysis" / "work").exists() and not (tmp_path / "analysis" / "decompiled").exists()
    assert not (tmp_path / "analysis" / "BUILD-INFO.txt").exists()


def test_base_apk_hash_mismatch_refuses(tmp_path):
    xapk = make_repo(tmp_path, base_hash="1" * 64)
    r = run(tmp_path, "--local-file", str(xapk), path=fake_tools(tmp_path))
    assert r.returncode == 3 and "sha256 mismatch for base APK" in r.stderr
    assert not (tmp_path / "analysis" / "BUILD-INFO.txt").exists()


def test_accept_new_hash_prints_hash_continues_and_edits_no_file(tmp_path):
    xapk = make_repo(tmp_path, xapk_hash="0" * 64)
    before = (tmp_path / "analysis" / "sources.env").read_text()
    r = run(tmp_path, "--local-file", str(xapk), "--accept-new-hash", path=fake_tools(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "actual:   " + sha(xapk.read_bytes()) in r.stderr and "no file was edited" in r.stderr
    assert (tmp_path / "analysis" / "sources.env").read_text() == before
    assert "accepted_new_hash=1" in (tmp_path / "analysis" / "BUILD-INFO.txt").read_text()


def test_dry_run_writes_nothing_and_runs_no_tools(tmp_path):
    xapk = make_repo(tmp_path)
    r = run(tmp_path, "--dry-run", "--local-file", str(xapk), path=fake_tools(tmp_path))
    assert r.returncode == 0 and "dry run" in r.stdout and "would run: jadx" in r.stdout
    assert sorted(os.listdir(tmp_path / "analysis")) == ["sources.env"]
    assert not (tmp_path / "jadx-calls").exists()


def test_full_run_extracts_verifies_decompiles_and_is_idempotent(tmp_path):
    xapk = make_repo(tmp_path)
    tools = fake_tools(tmp_path, rc=3)                    # exit 3 is the normal "some methods failed" result
    r = run(tmp_path, "--local-file", str(xapk), path=tools)
    assert r.returncode == 0, r.stderr
    a = tmp_path / "analysis"
    assert (a / "work" / "com.example.app.apk").read_bytes() == b"fake base apk"
    assert (a / "work" / "config.arm64_v8a.apk").read_bytes() == b"fake abi split"
    assert (a / "decompiled" / "sources").is_dir() and (a / "apk" / "fake.xapk").exists()
    info = (a / "BUILD-INFO.txt").read_text()
    for k in ("built_at=", "package=com.example.app", "xapk_sha256=" + sha(xapk.read_bytes()), "jadx=1.5.6", "java=openjdk version"):
        assert k in info
    assert (tmp_path / "jadx-calls").read_text().count("ran") == 1
    r2 = run(tmp_path, path=tools)                                    # second run: archive is already in place, nothing is redone
    assert r2.returncode == 0 and "already built" in r2.stdout and "already present and verified" in r2.stdout
    assert (tmp_path / "jadx-calls").read_text().count("ran") == 1
    r3 = run(tmp_path, "--force", "--local-file", str(xapk), path=tools)
    assert r3.returncode == 0 and (tmp_path / "jadx-calls").read_text().count("ran") == 2


def test_tampered_extracted_apk_is_detected_on_rerun(tmp_path):
    xapk = make_repo(tmp_path)
    tools = fake_tools(tmp_path)
    assert run(tmp_path, "--local-file", str(xapk), path=tools).returncode == 0
    (tmp_path / "analysis" / "work" / "com.example.app.apk").write_bytes(b"tampered")
    assert run(tmp_path, path=tools).returncode == 0      # re-extracted from the verified archive, not trusted
    assert (tmp_path / "analysis" / "work" / "com.example.app.apk").read_bytes() == b"fake base apk"


def test_jadx_version_pin_enforced_and_force_downgrades(tmp_path):
    xapk = make_repo(tmp_path)
    tools = fake_tools(tmp_path, version="9.9.9")
    r = run(tmp_path, "--local-file", str(xapk), path=tools)
    assert r.returncode == 4 and "jadx version is '9.9.9'" in r.stderr
    r = run(tmp_path, "--local-file", str(xapk), "--force", path=tools)
    assert r.returncode == 0 and "warning: jadx version" in r.stderr


def test_missing_tools_give_a_clear_error(tmp_path):
    xapk = make_repo(tmp_path)
    r = run(tmp_path, "--local-file", str(xapk), env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 4 and ("java not found" in r.stderr or "jadx not found" in r.stderr)


def test_jadx_hard_failure_reported(tmp_path):
    xapk = make_repo(tmp_path)
    r = run(tmp_path, "--local-file", str(xapk), path=fake_tools(tmp_path, rc=1))
    assert r.returncode == 5 and "jadx failed with exit 1" in r.stderr


def test_repo_sources_file_matches_sources_md():
    env = dict(l.split("=", 1) for l in open(os.path.join(ROOT, "analysis", "sources.env")).read().splitlines()
               if l and not l.startswith("#"))
    md = open(os.path.join(ROOT, "analysis", "SOURCES.md")).read()
    for k in ("XAPK_SHA256", "BASE_APK_SHA256", "VERSION", "PACKAGE"):
        assert env[k] in md, k


def test_build_info_is_git_ignored():
    assert "analysis/BUILD-INFO.txt" in open(os.path.join(ROOT, ".gitignore")).read()
