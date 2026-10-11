from rebeambox import control as c

def test_documented_frames():
    assert c.frame(0xDC, b"\x0C").hex(" ").upper() == "9E EB 02 DC 01 00 0C"
    assert c.frame(0xC6, b"\x01").hex(" ").upper() == "9E CA 02 C6 01 00 01"

def test_seq_in_flags():
    assert c.frame(0x60, bytes(3), seq=3)[2] == (3 << 3) | 2


def test_long_flag_only_over_20():
    assert c.frame(1, bytes(14))[2] & 4 == 0      # 14 + 6 = 20
    assert c.frame(1, bytes(15))[2] & 4 == 4

def test_parse_stream_split_and_bad_checksum():
    f = c.frame(0xC7, b"\x01" + bytes(12))
    frames, rest = c.parse_stream(f[:5])
    assert frames == [] and rest == f[:5]
    bad = b"\x9E\x00\x02\x01\x00\x00"                       # wrong checksum: dropped
    frames, rest = c.parse_stream(rest + f[5:] + bad + f)
    assert [x["cmd"] for x in frames] == [0xC7, 0xC7]

def test_bind_payload_layout():
    i = c.device_id("x")
    p = c.bind_payload(i)
    assert len(p) == 13 and p[1:7] == i and p[7:13] == i and p[0] == 2
    assert c.bind_payload(i, twelve_hour=True)[0] == 6

def test_time_payload():
    import datetime
    assert c.time_payload(datetime.datetime(2026, 10, 11, 18, 5, 9)).hex() == "ea070a0b120509"

def test_replies():
    r = c.parse_info_reply(bytes([1]) + bytes.fromhex("6801680168016801") + (4096).to_bytes(4, "little"))
    assert r == {"screen": (360, 360), "picture": (360, 360), "memory_kb": 4096}
    import struct
    p = struct.pack(">12H", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    d = c.parse_picsize_reply(p)
    assert d["album"] == (3, 4) and d["preview"] == (11, 12) and d["dial"] == (7, 8)
    assert c.parse_picsize_reply(p[:20])["preview"] == (128, 128)
    b = c.parse_bind_reply(bytes([0]) + b"2.9" + b"FW1".ljust(10, b"\0") + bytes(30))
    assert b["ok"] and b["protocol"] == 29 and b["firmware"] == "FW1"
    assert not c.parse_bind_reply(bytes([1]))["ok"]
