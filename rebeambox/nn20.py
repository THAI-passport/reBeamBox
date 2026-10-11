"""nn20 path (service 0x01F0): frames, IMB still container, 0x12345678 animation container."""
import json
import struct

SERVICE = "000001f0-0000-1000-8000-00805f9b34fb"
WRITE = "000001f1-0000-1000-8000-00805f9b34fb"
NOTIFY = "000001f2-0000-1000-8000-00805f9b34fb"

TYPE_GIF = 5
TYPE_ALBUM = 6
TYPE_SETTINGS = 13
MAX_DATA = 446


def checksum(b):
    return (-sum(b)) & 0xFF


def data_per_packet(mtu):
    return min(MAX_DATA, max(23, mtu) - 12)


def build_frames(type_, payload, mtu=512):
    """Envelope {"type":T,"data":<payload>} split into frames (A1/F1 head, big endian counters)."""
    env = b'{"type":%d,"data":' % type_ + payload + b"}"
    p = data_per_packet(mtu)
    n = (len(env) + p - 1) // p
    if n > 65535:
        raise ValueError("payload too large")
    frames = []
    for i in range(n):
        chunk = env[i * p:(i + 1) * p]
        f = bytes([0xF1, type_]) + struct.pack(">HHH", n, n - 1 - i, len(chunk)) + chunk
        frames.append(f + bytes([checksum(f)]))
    return frames


def settings_frame(obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    if len(data) > MAX_DATA:
        raise ValueError("settings JSON too long")
    f = bytes([0xF1, TYPE_SETTINGS]) + struct.pack(">HHH", 0, 0, len(data)) + data
    return f + bytes([checksum(f)])


def imb(width, height, jpeg):
    """36-byte IMB header + JPEG. Size field is 368 only for 368, else 360 (app behaviour)."""
    if (width, height) == (368, 368):
        w = h = 368
    else:
        w = h = 360
    return b"IMB\x00" + struct.pack("<iiBBhhhiiii", 4, len(jpeg) + 32, 11, 0, 0, w, h, 36, len(jpeg), 0, 0) + jpeg


def gif_container(frames, interval_ms, width=368, height=368, wifi=False):
    n = len(frames)
    head_len = n * 16 + 32
    buf = bytearray(head_len)
    struct.pack_into("<IIII", buf, 0, 0x12345678, n * 16 + (32 if wifi else 24), n, interval_ms)
    buf[16:28] = (b"output/%dms" % interval_ms)[:12].ljust(12, b"\0")
    offs, pos = [], head_len
    for f in frames:
        offs.append(pos)
        pos += 32 + len(f)
    for i in range(n):
        buf[32 + i * 16:32 + i * 16 + 12] = (b"frame_%05d." % (i + 1))[:12].ljust(12, b"\0")
        struct.pack_into("<I", buf, 32 + i * 16 + 12, offs[i])
    body = bytearray()
    for i, f in enumerate(frames):
        nxt = offs[i + 1] if i < n - 1 else offs[0]
        body += struct.pack("<II", offs[i], nxt)
        body += struct.pack("<BBhhhiiii", 11, 0, 0, width, height, offs[i] + 32, len(f), 0, 0) + f
    out = bytearray(buf + body)
    struct.pack_into("<I", out, 28, len(out) - 1)
    return bytes(out)


def parse_reply_stream(buf):
    """Badge replies on 0x01F2: A0 type u16 u8(len) json checksum. Returns (list of (type, json_text), rest)."""
    out, buf = [], bytes(buf)
    while True:
        i = buf.find(b"\xA0")
        if i < 0:
            return out, b""
        buf = buf[i:]
        if len(buf) < 6:
            return out, buf
        L = buf[4]
        if len(buf) < L + 6:
            return out, buf
        if checksum(buf[:5 + L]) != buf[5 + L]:
            buf = buf[1:]
            continue
        out.append((buf[1], buf[5:5 + L].decode("utf-8", "replace")))
        buf = buf[L + 6:]


def make_reply(type_, text):
    b = text.encode()
    f = bytes([0xA0, type_, 0, 0, len(b)]) + b
    return f + bytes([checksum(f)])


def guard_time_ms(n_packets):
    return min(((n_packets + 999) // 1000) * 800 + 800, 3000)
