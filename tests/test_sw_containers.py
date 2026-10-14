"""Software tests 1, 2 and 10 (docs/software-test-v1.md): container round trips, checksum edge cases,
property-style round trips of random valid frames (seeded, no extra dependency)."""
import random
import struct

import pytest

from rebeambox import control, nn20, rcsp

RNG = random.Random(20261011)


def rnd(n):
    return bytes(RNG.randrange(256) for _ in range(n))


def jpeg_like(n):
    return b"\xff\xd8\xff\xe0" + rnd(n) + b"\xff\xd9"


# ---------------- helpers that parse what the builders produce ----------------
def parse_imb(b):
    assert b[:4] == b"IMB\x00"
    f = struct.unpack_from("<iiBBhhhiiii", b, 4)
    return {"const": f[0], "size_field": f[1], "fmt": f[2], "comp": f[3], "w": f[5], "h": f[6],
            "data_off": f[7], "data_len": f[8], "jpeg": b[f[7]:f[7] + f[8]]}


def parse_gif_container(b):
    magic, size_field, n, interval = struct.unpack_from("<IIII", b, 0)
    total = struct.unpack_from("<I", b, 28)[0]
    frames, offs = [], []
    for i in range(n):
        name = b[32 + i * 16:32 + i * 16 + 12]
        off = struct.unpack_from("<I", b, 32 + i * 16 + 12)[0]
        cur, nxt = struct.unpack_from("<II", b, off)
        fmt, comp, _z, w, h, doff, ln, _a, _b = struct.unpack_from("<BBhhhiiii", b, off + 8)
        offs.append(off)
        frames.append({"name": name, "off": off, "cur": cur, "next": nxt, "w": w, "h": h, "doff": doff,
                       "jpeg": b[doff:doff + ln]})
    return {"magic": magic, "size_field": size_field, "n": n, "interval": interval, "total": total,
            "label": b[16:28], "frames": frames}


def reassemble(frames, type_):
    out = b""
    for i, f in enumerate(frames):
        assert f[0] == 0xF1 and f[1] == type_
        assert nn20.checksum(f[:-1]) == f[-1]
        n, rem, ln = struct.unpack(">HHH", f[2:8])
        assert n == len(frames) and rem == n - 1 - i and len(f) == 8 + ln + 1
        out += f[8:8 + ln]
    prefix = b'{"type":%d,"data":' % type_
    assert out.startswith(prefix) and out.endswith(b"}")
    return out[len(prefix):-1]


# ---------------- test 1: round trip IMB and animation containers ----------------
@pytest.mark.parametrize("size,expect", [(360, 360), (368, 368), (240, 360)])
def test_imb_round_trip(size, expect):
    j = jpeg_like(500)
    p = parse_imb(nn20.imb(size, size, j))
    assert p["jpeg"] == j and p["const"] == 4 and p["fmt"] == 11 and p["comp"] == 0
    assert p["w"] == p["h"] == expect            # only 368 is kept, everything else is written as 360
    assert p["data_off"] == 36 and p["size_field"] == len(j) + 32


@pytest.mark.parametrize("n", [1, 2, 5, 17])
@pytest.mark.parametrize("wifi", [False, True])
def test_animation_container_round_trip(n, wifi):
    jpegs = [jpeg_like(RNG.randrange(10, 400)) for _ in range(n)]
    blob = nn20.gif_container(jpegs, 120, 368, 368, wifi=wifi)
    c = parse_gif_container(blob)
    assert c["magic"] == 0x12345678 and c["n"] == n and c["interval"] == 120
    assert c["size_field"] == n * 16 + (32 if wifi else 24)
    assert c["total"] == len(blob) - 1
    assert [f["jpeg"] for f in c["frames"]] == jpegs
    for i, f in enumerate(c["frames"]):
        assert f["name"] == (b"frame_%05d." % (i + 1))
        assert f["cur"] == f["off"] and f["doff"] == f["off"] + 32 and (f["w"], f["h"]) == (368, 368)
        assert f["next"] == c["frames"][(i + 1) % n]["off"]      # last frame points back to the first


def test_animation_container_label_and_interval_field():
    c = parse_gif_container(nn20.gif_container([jpeg_like(8)], 44, 360, 360))
    assert c["label"].rstrip(b"\0") == b"output/44ms"


# ---------------- test 2: checksum edge cases ----------------
def test_nn20_checksum_edges():
    assert nn20.checksum(b"") == 0
    assert nn20.checksum(b"\xff" * 256) == 0
    for _ in range(50):
        b = rnd(RNG.randrange(0, 600))
        assert (sum(b) + nn20.checksum(b)) & 0xFF == 0


def test_nn20_empty_payload_frame():
    fr = nn20.build_frames(5, b"")
    assert len(fr) == 1 and reassemble(fr, 5) == b""


def test_nn20_max_packet_count_boundary():
    mtu = 23                                   # 11 data bytes per packet, so 65535 packets is cheap to reach
    p = nn20.data_per_packet(mtu)
    overhead = len(b'{"type":5,"data":') + 1
    ok = nn20.build_frames(5, bytes(65535 * p - overhead), mtu)
    assert len(ok) == 65535
    with pytest.raises(ValueError):
        nn20.build_frames(5, bytes(65535 * p - overhead + 1), mtu)


def test_nn20_max_data_per_packet_is_446():
    assert nn20.data_per_packet(512) == 446 and nn20.data_per_packet(10000) == 446 and nn20.data_per_packet(23) == 11


def test_nn20_reply_length_limits_and_bad_checksum():
    ok = nn20.make_reply(1, "x" * 255)
    assert nn20.parse_reply_stream(ok) == ([(1, "x" * 255)], b"")
    with pytest.raises(ValueError):
        nn20.make_reply(1, "x" * 256)
    assert nn20.parse_reply_stream(nn20.make_reply(2, "")) == ([(2, "")], b"")
    bad = bytearray(nn20.make_reply(3, '{"a":1}'))
    bad[-1] ^= 0x55
    assert nn20.parse_reply_stream(bytes(bad))[0] == []
    good = nn20.make_reply(4, "ok")
    assert nn20.parse_reply_stream(bytes(bad) + good)[0] == [(4, "ok")]       # resynchronises after a bad frame


def test_control_checksum_empty_and_max_payload():
    assert control.checksum(b"") == 0
    f = control.frame(0x01)
    frames, rest = control.parse_stream(f)
    assert len(frames) == 1 and frames[0]["payload"] == b"" and rest == b""
    big = bytes(65535)
    frames, rest = control.parse_stream(control.frame(0x77, big))
    assert frames[0]["cmd"] == 0x77 and frames[0]["payload"] == big and rest == b""
    with pytest.raises(struct.error):
        control.frame(0x77, bytes(65536))


def test_control_known_bad_checksum_rejected():
    good = control.frame(0xC6, b"\x01")
    bad = bytearray(good)
    bad[1] ^= 0x01
    assert control.parse_stream(bytes(bad))[0] == []
    assert control.parse_stream(bytes(bad) + good)[0][0]["cmd"] == 0xC6
    flipped_payload = bytearray(control.frame(0x10, b"\x01\x02\x03"))
    flipped_payload[-1] ^= 0xFF
    assert control.parse_stream(bytes(flipped_payload))[0] == []


def test_crc16_xmodem_known_values():
    assert rcsp.crc16_xmodem(b"") == 0
    assert rcsp.crc16_xmodem(b"123456789") == 0x31C3          # standard CRC-16/XMODEM check value
    part = rcsp.crc16_xmodem(b"1234")
    assert rcsp.crc16_xmodem(b"56789", part) == 0x31C3        # incremental use


def test_rcsp_incomplete_frames_wait():
    f = rcsp.pack(0x03, b"abc", sn=1)
    assert rcsp.unpack(f[:-1]) == (None, f[:-1])
    assert rcsp.unpack(f[:4])[0] is None


# ---------------- test 10: property style, random valid frames always round trip ----------------
def chunked(data, rng):
    i = 0
    while i < len(data):
        n = rng.randrange(1, 40)
        yield data[i:i + n]
        i += n


def test_property_control_frames_round_trip_any_chunking():
    for _ in range(200):
        cmd, seq = RNG.randrange(256), RNG.randrange(16)
        payload = rnd(RNG.randrange(0, 300))
        f = control.frame(cmd, payload, seq=seq, flag1=bool(RNG.getrandbits(1)))
        got, rest = [], b""
        for piece in chunked(f, RNG):
            frames, rest = control.parse_stream(rest + piece)
            got += frames
        assert rest == b"" and len(got) == 1
        assert got[0]["cmd"] == cmd and got[0]["payload"] == payload and (got[0]["flags"] >> 3) & 15 == seq


def test_property_control_stream_of_many_frames():
    sent = [(RNG.randrange(256), rnd(RNG.randrange(0, 60))) for _ in range(30)]
    blob = b"".join(control.frame(c, p, seq=i & 15) for i, (c, p) in enumerate(sent))
    got, rest = [], b""
    for piece in chunked(blob, RNG):
        frames, rest = control.parse_stream(rest + piece)
        got += frames
    assert [(f["cmd"], f["payload"]) for f in got] == sent and rest == b""


def test_property_nn20_frames_reassemble():
    for _ in range(100):
        t = RNG.choice([nn20.TYPE_GIF, nn20.TYPE_ALBUM])
        payload = rnd(RNG.randrange(0, 3000))
        mtu = RNG.choice([23, 100, 185, 247, 512])
        fr = nn20.build_frames(t, payload, mtu)
        assert all(len(f) <= nn20.data_per_packet(mtu) + 9 for f in fr)
        assert reassemble(fr, t) == payload


def test_property_nn20_reply_stream():
    sent = [(RNG.randrange(1, 20), "".join(RNG.choice("abcdefgh{}\":,0123456789") for _ in range(RNG.randrange(0, 120))))
            for _ in range(40)]
    blob = b"".join(nn20.make_reply(t, s) for t, s in sent)
    got, rest = [], b""
    for piece in chunked(blob, RNG):
        frames, rest = nn20.parse_reply_stream(rest + piece)
        got += frames
    assert got == sent and rest == b""


def test_property_rcsp_pack_unpack():
    for _ in range(200):
        opcode = RNG.choice([0x03, 0x07, 0x1B, 0x1C, 0x1D, 0x20, 0x21, 0x27, 0x01])
        command = bool(RNG.getrandbits(1))
        sn, status = RNG.randrange(256), RNG.randrange(256)
        xm = RNG.choice([x for x in range(256) if x not in rcsp.OTA_OPCODES]) if opcode == 0x01 else None   # OTA range is refused, see test_ota_block
        payload = rnd(RNG.randrange(0, 200))
        f = rcsp.pack(opcode, payload, command=command, want_response=bool(RNG.getrandbits(1)), sn=sn, status=status,
                      xm_opcode=xm)
        tail = rnd(5)
        parsed, rest = rcsp.unpack(f + tail)
        assert parsed["opcode"] == opcode and parsed["command"] == command and parsed["sn"] == sn
        assert parsed["payload"] == payload and rest == tail
        if not command:
            assert parsed["status"] == status
        if xm is not None:
            assert parsed["xm_opcode"] == xm
