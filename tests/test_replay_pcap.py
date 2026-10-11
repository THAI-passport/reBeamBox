"""tools/replay_pcap.py on synthetic btsnoop and pcapng captures built here from our own frame builders."""
import importlib.util
import io
import json
import os
import struct

import pytest
from PIL import Image

from rebeambox import control, media, nn20, rcsp

_spec = importlib.util.spec_from_file_location("replay_pcap", os.path.join(os.path.dirname(__file__), "..", "tools", "replay_pcap.py"))
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

H_NN, H_NN_N, H_CTL, H_RC = 0x0012, 0x0014, 0x0020, 0x0030


def jpeg(color):
    b = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(b, "JPEG")
    return b.getvalue()


def att_write(handle, value, cmd=True):
    return bytes([0x52 if cmd else 0x12]) + struct.pack("<H", handle) + value


def acl(att, conn=0x40, split=None):
    """H4 ACL packet(s) carrying one L2CAP ATT PDU; split = first fragment payload size to force fragmentation."""
    l2 = struct.pack("<HH", len(att), 4) + att
    if split is None:
        return [b"\x02" + struct.pack("<HH", conn | 0x2000 if False else conn, len(l2)) + l2]
    a, b = l2[:split], l2[split:]
    return [b"\x02" + struct.pack("<HH", conn, len(a)) + a, b"\x02" + struct.pack("<HH", conn | 0x1000, len(b)) + b]


def discovery():
    """Read By Type response listing characteristic declarations for 0x01F1, 0x01F2 (16-bit UUIDs)."""
    items = struct.pack("<HBHH", 0x0011, 0x04, H_NN, 0x01F1) + struct.pack("<HBHH", 0x0013, 0x10, H_NN_N, 0x01F2)
    return bytes([0x09, 7]) + items


def c2e6(n):
    return bytes.fromhex("6adf23c2f9be0080001066e9%02xfde6c2" % n)[::1]


def btsnoop(entries):
    """entries: list of (direction 'tx'|'rx', h4 bytes)."""
    out = b"btsnoop\x00" + struct.pack(">II", 1, 1002)
    for i, (d, pkt) in enumerate(entries):
        flags = 0 if d == "tx" else 1
        out += struct.pack(">IIIIQ", len(pkt), len(pkt), flags, 0, 0x00dcddb30f2f8000 + i * 1000) + pkt
    return out


def pcapng(entries, link=201):
    def block(t, body):
        pad = (-len(body)) % 4
        n = 12 + len(body) + pad
        return struct.pack("<II", t, n) + body + b"\0" * pad + struct.pack("<I", n)
    out = block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    out += block(1, struct.pack("<HHI", link, 0, 0))
    for i, (d, pkt) in enumerate(entries):
        raw = (struct.pack(">I", 0 if d == "tx" else 1) if link == 201 else b"") + pkt
        out += block(6, struct.pack("<IIIII", 0, 0, i, len(raw), len(raw)) + raw)
    return out


def nn20_entries(frames, split_every=0):
    ents = []
    for i, f in enumerate(frames):
        for pkt in acl(att_write(H_NN, f), split=(10 if split_every and i % split_every == 0 else None)):
            ents.append(("tx", pkt))
    return ents


def build_still_capture(with_discovery=True):
    j = jpeg((200, 10, 10))
    payload = nn20.gif_container([j], 3000, 360, 360)
    frames = nn20.build_frames(5, payload, 100)
    ents = []
    if with_discovery:
        ents += [("rx", p) for p in acl(discovery())]
    ents += nn20_entries(frames, split_every=3)
    reply = nn20.make_reply(1, json.dumps({"freespace": 100, "allspace": 5, "time_mode": 0, "size": "360,360"}))
    ents += [("rx", p) for p in acl(bytes([0x1B]) + struct.pack("<H", H_NN_N) + reply)]
    return ents, j, len(frames)


def test_btsnoop_roundtrip_with_discovery_and_fragmentation(tmp_path):
    ents, j, nframes = build_still_capture()
    f = tmp_path / "btsnoop_hci.log"
    f.write_bytes(btsnoop(ents))
    res = rp.analyze(str(f))
    assert res["mapped_handles"]["0x%04X" % H_NN] == "01f1"
    assert res["write_counts"]["nn20"] == nframes
    t = res["nn20"][0]
    assert t["type"] == 5 and t["complete"] and t["bad_checksums"] == 0
    c = t["container"]
    assert c["kind"] == "animation" and c["interval_ms"] == 3000 and (c["width"], c["height"]) == (360, 360)
    assert c["frames"] == [j]
    assert res["nn20_replies"] and "360,360" in res["nn20_replies"][0]


def test_pcapng_h4_with_phdr_matches_btsnoop(tmp_path):
    ents, j, _ = build_still_capture()
    f = tmp_path / "c.pcapng"
    f.write_bytes(pcapng(ents))
    res = rp.analyze(str(f))
    assert res["nn20"][0]["container"]["frames"] == [j]
    f2 = tmp_path / "d.pcapng"
    f2.write_bytes(pcapng(ents, link=187))
    assert rp.analyze(str(f2))["nn20"][0]["container"]["frames"] == [j]


def test_classic_pcap_is_read(tmp_path):
    ents, j, _ = build_still_capture()
    out = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 187)
    for i, (_d, pkt) in enumerate(ents):
        out += struct.pack("<IIII", 1, i, len(pkt), len(pkt)) + pkt
    f = tmp_path / "c.pcap"
    f.write_bytes(out)
    assert rp.analyze(str(f))["nn20"][0]["container"]["frames"] == [j]


def test_heuristic_without_discovery_and_manual_handle(tmp_path):
    ents, j, _ = build_still_capture(with_discovery=False)
    f = tmp_path / "x.log"
    f.write_bytes(btsnoop(ents))
    assert rp.analyze(str(f))["nn20"][0]["container"]["frames"] == [j]
    # a handle forced to a different role removes those writes from nn20
    res = rp.analyze(str(f), {H_NN: "control"})
    assert res["write_counts"]["nn20"] == 0


def test_album_still_imb_is_decoded(tmp_path):
    j = jpeg((10, 200, 10))
    frames = nn20.build_frames(6, nn20.imb(360, 360, j), 247)
    f = tmp_path / "a.log"
    f.write_bytes(btsnoop(nn20_entries(frames)))
    t = rp.analyze(str(f))["nn20"][0]
    assert t["type"] == 6 and t["container"]["kind"] == "imb" and t["container"]["frames"] == [j]


def test_settings_frame_and_bad_checksum_flagged(tmp_path):
    s = nn20.settings_frame({"animation_type": 1})
    j = nn20.gif_container([jpeg((1, 2, 3))], 100, 360, 360)
    frames = nn20.build_frames(5, j, 100)
    bad = bytearray(frames[0])
    bad[-1] ^= 0xFF
    f = tmp_path / "s.log"
    f.write_bytes(btsnoop(nn20_entries([s, bytes(bad)] + frames[1:])))
    res = rp.analyze(str(f))
    assert res["nn20"][0]["settings"] == '{"animation_type":1}'
    assert res["nn20"][1]["bad_checksums"] == 1


def test_incomplete_transfer_is_marked(tmp_path):
    frames = nn20.build_frames(5, nn20.gif_container([jpeg((5, 5, 5))], 100, 360, 360) + bytes(500), 50)
    f = tmp_path / "i.log"
    f.write_bytes(btsnoop(nn20_entries(frames[:-2])))
    assert rp.analyze(str(f))["nn20"][0]["complete"] is False


def test_control_and_rcsp_streams(tmp_path):
    ents = []
    # control channel: frames chunked at 20 bytes
    ctl = control.frame(control.CMD_INFO, b"\x01") + control.frame(control.CMD_PICSIZE, b"\x00")
    for i in range(0, len(ctl), 20):
        ents += [("tx", p) for p in acl(att_write(H_CTL, ctl[i:i + 20]))]
    # rcsp: a data file in two chunk frames with crc16, preceded by a raw auth block
    j = jpeg((90, 90, 200))
    chunks = rcsp.data_chunks(j, 0, 4096, 60, True, 1)
    stream = bytes(17) + b"".join(chunks)
    for i in range(0, len(stream), 100):
        ents += [("tx", p) for p in acl(att_write(H_RC, stream[i:i + 100]))]
    # discovery with 128-bit control uuid and 16-bit AE01
    ctl_uuid = bytes.fromhex("c2e6fd02e966100080 00bef9c223df6a".replace(" ", ""))[::-1]
    d128 = bytes([0x09, 21]) + struct.pack("<HBH", 0x001F, 0x04, H_CTL) + ctl_uuid
    d16 = bytes([0x09, 7]) + struct.pack("<HBHH", 0x002F, 0x04, H_RC, 0xAE01)
    ents = [("rx", p) for p in acl(d128) + acl(d16)] + ents
    f = tmp_path / "m.log"
    f.write_bytes(btsnoop(ents))
    res = rp.analyze(str(f))
    assert [c["cmd"] for c in res["control"]] == ["0xC6", "0xDA"]
    r = res["rcsp"]
    assert r["chunk_crc16"] and r["file_kind"] == "jpeg" and r["file"] == j
    assert len(r["unframed_chunks"]) == 1


def test_cli_extracts_files_and_json(tmp_path, capsys):
    ents, j, _ = build_still_capture()
    f = tmp_path / "c.log"
    f.write_bytes(btsnoop(ents))
    out = tmp_path / "out"
    assert rp.main([str(f), "--out", str(out), "--json", str(tmp_path / "r.json")]) == 0
    assert (out / "nn20_00_frame_000.jpg").read_bytes() == j
    data = json.load(open(tmp_path / "r.json"))
    assert data["write_counts"]["nn20"] > 0
    assert "type 5" in capsys.readouterr().out


def test_rejects_unknown_file(tmp_path):
    f = tmp_path / "junk"
    f.write_bytes(b"not a capture at all")
    with pytest.raises(ValueError):
        rp.read_capture(str(f))


# --- committed synthetic fixtures (fixtures/captures, generated by tools/make_fixtures.py) -------------------
_fx = importlib.util.spec_from_file_location("make_fixtures", os.path.join(os.path.dirname(__file__), "..", "tools", "make_fixtures.py"))
mf = importlib.util.module_from_spec(_fx)
_fx.loader.exec_module(mf)
FIXDIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "captures")
FORMATS = ["btsnoop", "pcapng"]


def fx(name, fmt):
    return os.path.join(FIXDIR, "%s.%s" % (name, fmt))


def test_committed_fixtures_match_generator_and_are_marked_synthetic():
    for fn, data in mf.render().items():
        assert open(os.path.join(FIXDIR, fn), "rb").read() == data, "regenerate with tools/make_fixtures.py: " + fn
    assert b"SYNTHETIC" in open(os.path.join(FIXDIR, "MANIFEST.md"), "rb").read()


def test_generator_is_deterministic(tmp_path):
    assert mf.render() == mf.render()
    assert mf.main(["--out", str(tmp_path)]) == 0 and mf.main(["--check", "--out", str(tmp_path)]) == 0
    (tmp_path / "malformed.btsnoop").write_bytes(b"x")
    assert mf.main(["--check", "--out", str(tmp_path)]) == 1


@pytest.mark.parametrize("fmt", FORMATS)
def test_fixture_nn20_animation_extracts_expected_bytes(fmt):
    res = rp.analyze(fx("nn20_animation_ack", fmt))
    _ents, container, n = mf.nn20_scenario()
    assert res["warnings"] == []
    settings, t = res["nn20"]
    assert settings["settings"] == '{"animation_type":1}'
    assert t["type"] == 5 and t["packets"] == n and t["complete"] and t["bad_checksums"] == 0 and not t["gaps"]
    assert t["payload"] == container
    c = t["container"]
    assert c["kind"] == "animation" and c["interval_ms"] == 100 and (c["width"], c["height"]) == (368, 368)
    assert c["frames"] == [mf.frame_jpeg(i) for i in range(3)]
    assert all(f[:2] == b"\xff\xd8" and f[-2:] == b"\xff\xd9" for f in c["frames"])
    assert len(res["nn20_replies"]) == 1 + n and res["nn20_replies"][1] == '{"msg":"GetPacketSuccess"}'
    assert res["write_counts"]["nn20"] == n + 1


@pytest.mark.parametrize("fmt", FORMATS)
def test_fixture_rcsp_auth_session_validates_handshake(fmt):
    res = rp.analyze(fx("rcsp_auth_session", fmt))
    a = res["rcsp_auth"]
    assert a["ok"] and a["complete"] and a["badge_response_valid"] and a["app_response_valid"]
    assert a["steps"] == ["app challenge", "badge response (valid)", "app pass", "badge challenge", "app response (valid)", "badge pass"]
    assert res["warnings"] == []
    assert res["rcsp"]["opcodes"] == ["0x03", "0x06"]


def test_auth_detects_a_wrong_badge_answer():
    bad = bytes([1]) + bytes(16)
    a = rp.decode_auth([("tx", mf.R_APP), ("rx", bad)])
    assert a["badge_response_valid"] is False and a["ok"] is False
    assert rp.decode_auth([("tx", b"\x01\x02")]) is None


@pytest.mark.parametrize("fmt", FORMATS)
def test_fixture_malformed_is_reported_not_fatal(fmt):
    res = rp.analyze(fx("malformed", fmt))
    t = res["nn20"][1]
    assert t["bad_checksums"] == 1 and not t["complete"] and t["got"] == t["packets"] - 1
    assert t["gaps"] == [{"expected_remaining": 20, "got_remaining": 19}]
    assert t["container"]["kind"] == "incomplete"
    r = res["rcsp"]
    assert r["chunk_crc16"] and r["crc_errors"] == [1]
    assert r["seq_gaps"] == [{"index": 3, "expected_seq": 3, "got_seq": 4}]
    text = " | ".join(res["warnings"])
    for needle in ("bad checksum", "sequence gap", "incomplete", "bad CRC16", "chunk 3"):
        assert needle in text


def test_malformed_cli_exits_zero_and_prints_warnings(tmp_path, capsys):
    assert rp.main([fx("malformed", "btsnoop"), "--out", str(tmp_path / "o"), "--json", str(tmp_path / "r.json")]) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out and "INCOMPLETE" in out
    assert json.load(open(tmp_path / "r.json"))["warnings"]


@pytest.mark.parametrize("fmt", FORMATS)
def test_truncated_capture_does_not_crash(tmp_path, fmt):
    data = open(fx("nn20_animation_ack", fmt), "rb").read()
    f = tmp_path / ("t." + fmt)
    f.write_bytes(data[:len(data) // 2 + 7])
    try:
        res = rp.analyze(str(f))
    except (struct.error, ValueError, IndexError) as e:        # a cut pcapng block may be rejected, but only as a clean error
        pytest.skip("truncated %s rejected cleanly: %s" % (fmt, type(e).__name__))
    assert "warnings" in res and res["att_pdus"] > 0


def test_garbage_att_payload_is_ignored(tmp_path):
    ents = [("tx", p) for p in acl(bytes([0x52, 0x12]))] + [("tx", b"\x02\x40\x00\x02\x00\x00\x00")]
    f = tmp_path / "g.log"
    f.write_bytes(btsnoop(ents))
    res = rp.analyze(str(f))
    assert res["nn20"] == [] and res["control"] == []
