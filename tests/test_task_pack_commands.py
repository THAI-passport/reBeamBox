"""The recon task pack must not mention a command, flag or script that does not exist (a weaker agent would trip on it)."""
import argparse
import os
import re
import shlex

import pytest

from rebeambox import cli

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = [os.path.join(ROOT, "docs", "tasks", f) for f in ("README.md", "SW-RECON.md", "HW-RECON.md", "ASSUMPTIONS.md", "QUICKSTART.md")]
CMD = re.compile(r"(?:^|[$`(] ?|\s)(rebeambox(?:\s+[^`|\n]+)?)")
SCRIPT = re.compile(r"(?:python3?|bash)\s+((?:tools|scripts)/[\w./-]+)")


def subparsers():
    parser = cli.build_parser()
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            return a.choices
    raise AssertionError("no subcommands")


def doc_text(path):
    if not os.path.exists(path):
        pytest.skip("missing " + path)
    return open(path, encoding="utf-8").read()


@pytest.mark.parametrize("path", DOCS, ids=[os.path.basename(p) for p in DOCS])
def test_every_rebeambox_command_and_flag_exists(path):
    subs = subparsers()
    bad = []
    for line in doc_text(path).splitlines():
        for m in CMD.finditer(line):
            try:
                words = shlex.split(m.group(1).replace("...", ""))
            except ValueError:
                continue
            if len(words) < 2 or words[0] != "rebeambox" or words[1].startswith(("-", "<")) or not re.match(r"^[a-z][a-z-]+$", words[1]):
                continue
            sub = words[1]
            if sub not in subs:
                if sub in ("is", "the", "and", "or", "to", "for", "scan-all"):      # prose
                    continue
                bad.append((line.strip()[:90], "unknown subcommand " + sub))
                continue
            known = set()
            for act in subs[sub]._actions:
                known.update(act.option_strings)
            for w in words[2:]:
                if w.startswith("--") and w.split("=")[0] not in known:
                    bad.append((line.strip()[:90], "unknown flag %s for %s" % (w, sub)))
    assert not bad, bad


@pytest.mark.parametrize("path", DOCS, ids=[os.path.basename(p) for p in DOCS])
def test_every_script_path_exists(path):
    bad = [m for m in SCRIPT.findall(doc_text(path)) if not os.path.exists(os.path.join(ROOT, m.rstrip(".,)")))]
    assert not bad, bad
