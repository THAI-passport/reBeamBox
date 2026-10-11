#!/usr/bin/env python3
"""Generate the SYNTHETIC reference captures in fixtures/captures/ (deterministic, no vendor data, no hardware).

    python tools/make_fixtures.py            # (re)write fixtures/captures/*.btsnoop, *.pcapng, MANIFEST.md
    python tools/make_fixtures.py --check    # exit 1 if the committed files differ from a fresh generation

Every capture is built from this repository's own frame builders (rebeambox.nn20, rcsp, jl_auth) and a fixed 16x16
test JPEG, wrapped as ATT writes and notifications inside HCI ACL packets (with L2CAP fragmentation). They exercise
tools/replay_pcap.py; they are not recordings of any badge or of the vendor app.
"""
import argparse
import base64
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from rebeambox import jl_auth, nn20, rcsp  # noqa: E402

OUT = os.path.join(ROOT, "fixtures", "captures")
CONN = 0x0040
H_NN_W, H_NN_N = 0x0012, 0x0014          # nn20 write and notify value handles
H_RC_W, H_RC_N = 0x0030, 0x0032          # RCSP write and notify value handles
BASE_US = 0x00dcddb30f2f8000 + 1_700_000_000_000_000   # fixed timestamp base (2023-11-14 UTC), microseconds

JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgy"
    "PC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABAD"
    "ASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKB"
    "kaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZ"
    "mqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQF"
    "BgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5"
    "OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX"
    "2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDz+x0Lp8ldNYaF0+SulsNC6fJXT2OhdPkrTF5r5i4fzvbU/9k=")


def frame_jpeg(i):
    """Three distinct 'frames': the fixed JPEG with a different COM segment after SOI (still a valid JPEG)."""
    com = b"\xff\xfe" + struct.pack(">H", 2 + 8) + (b"frame-%02d" % i)
    return JPEG[:2] + com + JPEG[2:]


# --- capture building blocks -----------------------------------------------------------------------
def att_write(handle, value):
    return bytes([0x52]) + struct.pack("<H", handle) + value


def att_notify(handle, value):
    return bytes([0x1B]) + struct.pack("<H", handle) + value


def acl(att, split=None):
    l2 = struct.pack("<HH", len(att), 4) + att
    if split is None:
        return [b"\x02" + struct.pack("<HH", CONN, len(l2)) + l2]
    a, b = l2[:split], l2[split:]
    return [b"\x02" + struct.pack("<HH", CONN, len(a)) + a, b"\x02" + struct.pack("<HH", CONN | 0x1000, len(b)) + b]


def discovery(*chars):
    """Read By Type response with characteristic declarations (16-bit UUIDs): chars = [(decl handle, value handle, uuid16)]."""
    items = b"".join(struct.pack("<HBHH", d, 0x14, v, u) for d, v, u in chars)
    return bytes([0x09, 7]) + items


def btsnoop(entries):
    out = b"btsnoop\x00" + struct.pack(">II", 1, 1002)
    for i, (d, pkt) in enumerate(entries):
        out += struct.pack(">IIIIQ", len(pkt), len(pkt), 0 if d == "tx" else 1, 0, BASE_US + i * 5000) + pkt
    return out


def pcapng(entries):
    def block(t, body):
        pad = (-len(body)) % 4
        n = 12 + len(body) + pad
        return struct.pack("<II", t, n) + body + b"\0" * pad + struct.pack("<I", n)
    out = block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    out += block(1, struct.pack("<HHI", 201, 0, 0))
    for i, (d, pkt) in enumerate(entries):
        raw = struct.pack(">I", 0 if d == "tx" else 1) + pkt
        ts = BASE_US + i * 5000
        out += block(6, struct.pack("<IIIII", 0, ts >> 32, ts & 0xFFFFFFFF, len(raw), len(raw)) + raw)
    return out


def tx(att, split=None):
    return [("tx", p) for p in acl(att, split)]


def rx(att, split=None):
    return [("rx", p) for p in acl(att, split)]


# --- the three scenarios ---------------------------------------------------------------------------
def nn20_scenario(mtu=100, ack_batch=4, mutate=None):
    """Discovery, status push, settings frame, animation container of 3 frames in P=88 byte packets with
    fragmented ACL packets, and GetPacketSuccess replies after every batch. mutate(frames) may corrupt or drop frames."""
    container = nn20.gif_container([frame_jpeg(i) for i in range(3)], 100, 368, 368)
    frames = nn20.build_frames(5, container, mtu)
    ents = rx(discovery((0x0011, H_NN_W, 0x01F1), (0x0013, H_NN_N, 0x01F2)))
    status = nn20.make_reply(1, json.dumps({"allspace": 32000, "freespace": 20000, "time_mode": 0, "size": "368,368",
                                            "devname": "SYNTHETIC", "brand": "none", "type": 13}, separators=(",", ":")))
    ents += rx(att_notify(H_NN_N, status))
    ents += tx(att_write(H_NN_W, nn20.settings_frame({"animation_type": 1})))
    sent = mutate(list(frames)) if mutate else list(frames)
    for i, f in enumerate(sent):
        ents += tx(att_write(H_NN_W, f), split=10 if i % 3 == 0 else None)
        if (i + 1) % ack_batch == 0 or i == len(sent) - 1:
            for _ in range(ack_batch if (i + 1) % ack_batch == 0 else (i + 1) % ack_batch):
                ents += rx(att_notify(H_NN_N, nn20.make_reply(5, '{"msg":"GetPacketSuccess"}')))
    return ents, container, len(frames)


R_APP = b"\x00" + bytes(range(1, 17))
R_DEV = b"\x00" + bytes(range(0xA0, 0xB0))


def rcsp_auth_scenario():
    """Complete Jieli auth (reset, 00|R, 01|E1(R), 02 pass, 00|Rdev, 01|E1(Rdev), 02 pass) then GetTargetInfo."""
    ents = rx(discovery((0x002F, H_RC_W, 0xAE01), (0x0031, H_RC_N, 0xAE02)))
    ents += tx(att_write(H_RC_W, jl_auth.AUTH_RESET))
    ents += tx(att_write(H_RC_W, R_APP))
    ents += rx(att_notify(H_RC_N, jl_auth.encrypt_challenge(R_APP)))
    ents += tx(att_write(H_RC_W, jl_auth.AUTH_OK))
    ents += rx(att_notify(H_RC_N, R_DEV))
    ents += tx(att_write(H_RC_W, jl_auth.encrypt_challenge(R_DEV)))
    ents += rx(att_notify(H_RC_N, jl_auth.AUTH_OK))
    ents += tx(att_write(H_RC_W, rcsp.get_target_info(1)))
    return ents


def rcsp_chunks(data, mtu=60, bad_crc_index=None, drop_index=None, sn_start=1):
    out = []
    for k, i in enumerate(range(0, len(data), mtu)):
        part = data[i:i + mtu]
        crc = rcsp.crc16_xmodem(part) ^ (0x5555 if k == bad_crc_index else 0)
        body = bytes([k & 0xFF]) + struct.pack(">H", crc) + part
        fr = rcsp.pack(rcsp.OP_DATA, body, command=True, want_response=False, sn=(sn_start + k) & 0xFF, xm_opcode=rcsp.OP_LARGE_OP)
        if k != drop_index:
            out.append(fr)
    return out


def malformed_scenario():
    """nn20 transfer with a bad checksum in packet 2 and packet 5 dropped; RCSP file chunks with a bad CRC16 in
    chunk 1 and chunk 3 dropped (sequence jumps 2 to 4)."""
    def mutate(frames):
        bad = bytearray(frames[2])
        bad[-1] ^= 0xFF
        frames[2] = bytes(bad)
        del frames[5]
        return frames
    ents, _container, _n = nn20_scenario(mutate=mutate)
    ents += rx(discovery((0x002F, H_RC_W, 0xAE01), (0x0031, H_RC_N, 0xAE02)))
    for fr in rcsp_chunks(JPEG, bad_crc_index=1, drop_index=3):
        ents += tx(att_write(H_RC_W, fr))
    return ents


def build():
    out = {}
    nn_ents, container, n = nn20_scenario()
    out["nn20_animation_ack"] = nn_ents
    out["rcsp_auth_session"] = rcsp_auth_scenario()
    out["malformed"] = malformed_scenario()
    return out, {"container": container, "packets": n}


def render():
    """Return {filename: bytes} for every fixture file."""
    scenarios, _meta = build()
    files = {}
    for name, ents in scenarios.items():
        files[name + ".btsnoop"] = btsnoop(ents)
        files[name + ".pcapng"] = pcapng(ents)
    rows = ["| file | sha256 | bytes |", "|---|---|---|"]
    for fn in sorted(files):
        rows.append("| %s | %s | %d |" % (fn, hashlib.sha256(files[fn]).hexdigest(), len(files[fn])))
    files["MANIFEST.md"] = ("# Synthetic capture fixtures\n\n"
        "SYNTHETIC. Generated by `tools/make_fixtures.py` from this repository's own frame builders and a fixed test JPEG. "
        "They contain no vendor data and are not recordings of any badge or of the vendor app. Each scenario exists as "
        "btsnoop (HCI H4, datalink 1002) and pcapng (linktype 201).\n\n"
        "- `nn20_animation_ack`: discovery, status push, settings frame, a 3-frame 368x368 animation container in 88-byte "
        "packets (MTU 100) with fragmented ACL packets and GetPacketSuccess replies in batches of 4.\n"
        "- `rcsp_auth_session`: complete Jieli auth (reset, 00|R, 01|E1(R), 02 pass, 00|Rdev, 01|E1(Rdev), 02 pass) and a "
        "GetTargetInfo command.\n"
        "- `malformed`: an nn20 transfer with a bad checksum (packet 2) and a dropped packet (5), plus RCSP file chunks "
        "with a bad CRC16 (chunk 1) and a dropped sequence number (chunk 3).\n\n"
        "Regenerate with `python tools/make_fixtures.py`; `--check` verifies the committed files.\n\n"
        + "\n".join(rows) + "\n").encode()
    return files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    files = render()
    if a.check:
        bad = [fn for fn, b in files.items() if not os.path.exists(os.path.join(a.out, fn)) or open(os.path.join(a.out, fn), "rb").read() != b]
        print("fixtures differ: %s" % bad if bad else "fixtures up to date")
        return 1 if bad else 0
    os.makedirs(a.out, exist_ok=True)
    for fn, b in files.items():
        open(os.path.join(a.out, fn), "wb").write(b)
        print("wrote", os.path.join(a.out, fn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
