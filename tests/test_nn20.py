import json
from rebeambox import nn20

def test_checksum_and_single_command():
    f = nn20.settings_frame({"animation_type": 1})
    assert f[:2] == b"\xF1\x0D" and nn20.checksum(f[:-1]) == f[-1]
    assert json.loads(f[8:-1]) == {"animation_type": 1}

def test_chunking_counters():
    fr = nn20.build_frames(6, bytes(1000), mtu=23)          # 11 data bytes per packet
    n = len(fr)
    assert nn20.data_per_packet(23) == 11 and nn20.data_per_packet(512) == 446
    assert int.from_bytes(fr[0][2:4], "big") == n and int.from_bytes(fr[0][4:6], "big") == n - 1
    assert int.from_bytes(fr[-1][4:6], "big") == 0
    env = b"".join(f[8:-1] for f in fr)
    assert env.startswith(b'{"type":6,"data":') and env.endswith(b"}") and len(env) == 1000 + len(b'{"type":6,"data":}')
    assert all(nn20.checksum(f[:-1]) == f[-1] for f in fr)

def test_imb_header():
    h = nn20.imb(368, 368, b"JPG")
    assert h[:4] == b"IMB\x00" and len(h) == 39
    assert int.from_bytes(h[8:12], "little") == 3 + 32 and h[12] == 11
    assert int.from_bytes(h[16:18], "little") == 368 and int.from_bytes(h[20:24], "little") == 36
    assert nn20.imb(300, 300, b"J")[16] == 360 & 255

def test_gif_container_offsets():
    g = nn20.gif_container([b"AAAA", b"BBBBBB"], 100, 368, 368)
    assert int.from_bytes(g[0:4], "little") == 0x12345678 and int.from_bytes(g[8:12], "little") == 2
    assert int.from_bytes(g[4:8], "little") == 2 * 16 + 24
    assert int.from_bytes(g[28:32], "little") == len(g) - 1
    off0 = int.from_bytes(g[32 + 12:32 + 16], "little"); off1 = int.from_bytes(g[48 + 12:48 + 16], "little")
    assert g[off0 + 32:off0 + 36] == b"AAAA" and g[off1 + 32:off1 + 38] == b"BBBBBB"
    assert int.from_bytes(g[off0 + 4:off0 + 8], "little") == off1      # next pointer
    assert int.from_bytes(g[off1 + 4:off1 + 8], "little") == off0      # last points to first

def test_reply_parser():
    msg = nn20.make_reply(6, '{"x":"GetPacketSuccess"}')
    out, rest = nn20.parse_reply_stream(b"\x00\x00" + msg[:7])
    assert out == [] 
    out, rest = nn20.parse_reply_stream(msg + msg)
    assert len(out) == 2 and "GetPacketSuccess" in out[0][1] and rest == b""

def test_guard_time():
    assert nn20.guard_time_ms(1) == 1600 and nn20.guard_time_ms(5000) == 3000
