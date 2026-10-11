"""tools/check_repo_rules.py and the CI workflow."""
import importlib.util
import os

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
_s = importlib.util.spec_from_file_location("check_repo_rules", os.path.join(ROOT, "tools", "check_repo_rules.py"))
cr = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cr)

EMOJI = chr(0x1F600)
HOST = "www." + "google-analytics" + ".com"


def put(root, rel, text, mode="w"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "w":
        p.write_text(text, encoding="utf-8")
    else:
        p.write_bytes(text)


def rules(root):
    return sorted({(rel, rule) for rel, _n, rule, _d in cr.scan(str(root))})


def test_repository_is_clean():
    assert cr.scan(ROOT) == []
    assert cr.main(["--root", ROOT]) == 0


@pytest.mark.parametrize("cp", [0x1F600, 0x1F680, 0x2705, 0x2764, 0x2728, 0x26A0, 0x2B50, 0x231A, 0xFE0F, 0x200D, 0x1F1F9])
def test_emoji_codepoints_are_flagged(tmp_path, cp):
    put(tmp_path, "docs/a.md", "text %s text" % chr(cp))
    assert rules(tmp_path) == [("docs/a.md", "emoji")]


@pytest.mark.parametrize("cp", [0x2192, 0x00E9, 0x0E01, 0x2022, 0x00B0, 0x2014])
def test_plain_symbols_and_thai_are_allowed(tmp_path, cp):
    put(tmp_path, "docs/a.md", "x %s y" % chr(cp))
    assert rules(tmp_path) == []


def test_emoji_in_each_area(tmp_path):
    for rel in ("rebeambox/a.py", "tests/test_x.py", "ui/app.js", "ui/index.html", "README.md", ".github/workflows/ci.yml", "docs/b.md"):
        put(tmp_path, rel, "# %s\n" % EMOJI)
    assert {r for r, _ in rules(tmp_path)} == {"rebeambox/a.py", "tests/test_x.py", "ui/app.js", "ui/index.html", "README.md",
                                              ".github/workflows/ci.yml", "docs/b.md"}


def test_analytics_host_flagged_in_docs_and_code(tmp_path):
    put(tmp_path, "docs/x.md", "see %s here" % HOST)
    put(tmp_path, "rebeambox/y.py", "H = '%s'" % HOST)
    assert rules(tmp_path) == [("docs/x.md", "analytics-host"), ("rebeambox/y.py", "analytics-host")]


def test_similar_but_different_host_is_not_flagged(tmp_path):
    put(tmp_path, "docs/x.md", "notgoogle-analytics-like and adjust.community and mob.company")
    assert rules(tmp_path) == []


def test_code_url_rule(tmp_path):
    put(tmp_path, "rebeambox/a.py", "u = 'http://localhost:8000/x'\nv = 'http://192.168.8.1/upload'\nw = 'https://example.org/p'\n")
    put(tmp_path, "ui/app.js", "fetch('https://example.net/')")
    put(tmp_path, "README.md", "see https://github.com/x/y")
    put(tmp_path, "docs/z.md", "see https://example.org")
    got = [(r, rule, d) for r, _n, rule, d in cr.scan(str(tmp_path))]
    assert ("rebeambox/a.py", "code-url", "https://example.org") in got and ("ui/app.js", "code-url", "https://example.net") in got
    assert not [g for g in got if g[0] in ("README.md", "docs/z.md")]
    assert not [g for g in got if "localhost" in g[2] or "192.168" in g[2]]


def test_skipped_dirs_and_binaries(tmp_path):
    for d in ("node_modules/x", "analysis/decompiled", ".venv/lib", ".git", "pkg.egg-info"):
        put(tmp_path, d + "/f.md", EMOJI + HOST)
    put(tmp_path, "fixtures/captures/a.btsnoop", b"\x00" + EMOJI.encode() + HOST.encode(), mode="wb")
    put(tmp_path, "ui/package-lock.json", EMOJI)
    assert rules(tmp_path) == []


def test_fixture_manifest_is_checked(tmp_path):
    put(tmp_path, "fixtures/captures/MANIFEST.md", EMOJI)
    assert rules(tmp_path) == [("fixtures/captures/MANIFEST.md", "emoji")]


def test_host_rule_exempt_files_still_get_emoji_rule(tmp_path):
    put(tmp_path, "tools/check_repo_rules.py", "H = '%s'\n" % HOST)
    assert rules(tmp_path) == []
    put(tmp_path, "tests/test_check_repo_rules.py", "H = '%s' %s\n" % (HOST, EMOJI))
    assert rules(tmp_path) == [("tests/test_check_repo_rules.py", "emoji")]


def test_cli_exit_codes_and_output(tmp_path, capsys):
    put(tmp_path, "docs/a.md", "clean")
    assert cr.main(["--root", str(tmp_path)]) == 0
    put(tmp_path, "docs/b.md", "a\nb %s\n" % EMOJI)
    assert cr.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "docs/b.md:2: emoji: U+1F600" in out and "1 violation" in out


def _read_ci():
    """The workflow lives in .github/workflows/ci.yml."""
    return open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()


def test_ci_workflow_has_required_steps():
    text = _read_ci()
    for needle in ('branches: [main]', "pull_request:", 'python-version: ["3.10", "3.11", "3.12"]', "actions/setup-node",
                   'pip install -e ".[test]"', "pytest -q", "tests/test_no_vendor_calls.py", "tools/check_repo_rules.py",
                   "tools/make_fixtures.py --check"):
        assert needle in text, needle
    try:
        import yaml
    except ImportError:
        return
    doc = yaml.safe_load(text)
    assert set(doc["jobs"]["test"]["strategy"]["matrix"]["python-version"]) == {"3.10", "3.11", "3.12"}
    assert "push" in doc[True] and "pull_request" in doc[True]      # YAML 1.1 reads the key "on" as True
