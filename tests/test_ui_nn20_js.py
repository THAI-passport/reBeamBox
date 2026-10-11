"""ui/nn20.js must produce the same bytes as rebeambox/nn20.py (needs Node; skipped otherwise)."""
import json
import os
import shutil
import subprocess

import pytest

from rebeambox import nn20

ROOT = os.path.join(os.path.dirname(__file__), "..")
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

SCRIPT = r"""
const N = require(process.argv[1]);
const jpg = Uint8Array.from(Buffer.from(process.argv[2], "hex"));
const out = {};
out.container = N.toHex(N.gifContainer([jpg], 3000, 360, 360));
out.frames = {};
[23, 100, 247, 517].forEach(m => { out.frames[m] = N.buildFrames(5, N.gifContainer([jpg], 3000, 360, 360), m).map(N.toHex); });
out.dpp = [10, 23, 100, 247, 517, 9999].map(N.dataPerPacket);
out.replies = N.parseReplies(Uint8Array.from(Buffer.from(process.argv[3], "hex"))).msgs;
console.log(JSON.stringify(out));
"""


def test_js_matches_python():
    jpg = bytes(range(256)) * 3
    reply = nn20.make_reply(1, '{"freespace":100,"allspace":5,"time_mode":0,"size":"360,360"}')
    r = subprocess.run(["node", "-e", SCRIPT, os.path.join(ROOT, "ui", "nn20.js"), jpg.hex(), reply.hex()],
                       capture_output=True, text=True, check=True)
    out = json.loads(r.stdout)
    cont = nn20.gif_container([jpg], 3000, 360, 360)
    assert out["container"] == cont.hex()
    for m in (23, 100, 247, 517):
        assert out["frames"][str(m)] == [f.hex() for f in nn20.build_frames(5, cont, m)]
    assert out["dpp"] == [nn20.data_per_packet(m) for m in (10, 23, 100, 247, 517, 9999)]
    assert out["replies"][0]["type"] == 1 and "360,360" in out["replies"][0]["text"]


def test_ui_has_no_network_or_emoji():
    for name in ("index.html", "app.js", "nn20.js"):
        t = open(os.path.join(ROOT, "ui", name), encoding="utf-8").read()
        assert "http://" not in t.replace("http://localhost", "") and "https://" not in t
        assert not any(ord(c) > 0x2000 for c in t), name
        for bad in ("fetch(", "XMLHttpRequest", "WebSocket", "sendBeacon"):
            assert bad not in t, (name, bad)
