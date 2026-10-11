#!/usr/bin/env python3
"""Repository rules lint. Fails (exit 1) on:

  emoji           any emoji or emoji modifier in a text file (code, docs, tests, workflows, UI)
  analytics-host  a hostname of a known analytics, advertising or crash-reporting service
  code-url        a URL in client code (rebeambox/, tools/, ui/ scripts) whose host is not local
                  (localhost, 127.0.0.1, the badge address 192.168.8.1)

    python tools/check_repo_rules.py [--root DIR]

Skipped: .git, node_modules, analysis/, .venv, caches, binary files (the captures in fixtures/captures are binary; their
MANIFEST.md is checked). The host lists live in this file, so this file and its test are exempt from the host rules only.
"""
import argparse
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "analysis", ".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", ".mypy_cache"}
SKIP_SUFFIX = (".egg-info",)
TEXT_EXT = {".py", ".md", ".js", ".html", ".css", ".yml", ".yaml", ".toml", ".txt", ".json", ".sh", ".cfg", ".ini", ".svg", ""}
HOST_RULE_EXEMPT = {"tools/check_repo_rules.py", "tests/test_check_repo_rules.py"}
CODE_PREFIXES = ("rebeambox/", "tools/", "ui/")
CODE_EXT = {".py", ".js", ".html"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "192.168.8.1"}

EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x231A, 0x231B), (0x23E9, 0x23F3), (0x23F8, 0x23FA),
                (0x2B1B, 0x2B1C), (0x2B50, 0x2B50), (0x2B55, 0x2B55), (0x2934, 0x2935), (0x3030, 0x3030),
                (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299), (0xFE0F, 0xFE0F), (0x20E3, 0x20E3), (0x200D, 0x200D)]

ANALYTICS_HOSTS = [
    "google-analytics.com", "googletagmanager.com", "app-measurement.com", "firebaseio.com", "firebaseinstallations.googleapis.com",
    "crashlytics.com", "doubleclick.net", "googleadservices.com", "googlesyndication.com", "umeng.com", "umeng.cn", "umsns.com",
    "bugly.qq.com", "gdt.qq.com", "pangolin-sdk-toutiao.com", "pangle.io", "byteoversea.com", "snssdk.com", "mintegral.com",
    "applovin.com", "unityads.unity3d.com", "sentry.io", "mixpanel.com", "amplitude.com", "appsflyer.com", "adjust.com",
    "jpush.cn", "jiguang.cn", "getui.com", "igexin.com", "mob.com", "growingio.com", "talkingdata.com",
]
HOST_RX = re.compile(r"(?<![A-Za-z0-9-])(?:[A-Za-z0-9-]+\.)*(%s)(?![A-Za-z0-9-])" % "|".join(re.escape(h) for h in ANALYTICS_HOSTS), re.I)
URL_RX = re.compile(r"https?://([A-Za-z0-9.-]+)", re.I)


def is_emoji(ch):
    c = ord(ch)
    return any(a <= c <= b for a, b in EMOJI_RANGES)


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(SKIP_SUFFIX))
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT or fn == "package-lock.json":
                continue
            yield full, rel, ext


def check_text(rel, ext, text):
    """Yield (line number, rule, detail) for one file's text."""
    code = rel.startswith(CODE_PREFIXES) and ext in CODE_EXT
    host_exempt = rel in HOST_RULE_EXEMPT
    for n, line in enumerate(text.splitlines(), 1):
        bad = sorted({"U+%04X" % ord(c) for c in line if is_emoji(c)})
        if bad:
            yield n, "emoji", ", ".join(bad)
        if host_exempt:
            continue
        m = HOST_RX.search(line)
        if m:
            yield n, "analytics-host", m.group(0)
        if code:
            for u in URL_RX.finditer(line):
                if u.group(1).lower() not in LOCAL_HOSTS:
                    yield n, "code-url", u.group(0)


def scan(root):
    out = []
    for full, rel, ext in iter_files(root):
        try:
            data = open(full, "rb").read()
            if b"\x00" in data:
                continue
            text = data.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, rule, detail in check_text(rel, ext, text):
            out.append((rel, n, rule, detail))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    a = ap.parse_args(argv)
    v = scan(a.root)
    for rel, n, rule, detail in v:
        print("%s:%d: %s: %s" % (rel, n, rule, detail))
    print("%d violation(s)" % len(v) if v else "repo rules: ok")
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
