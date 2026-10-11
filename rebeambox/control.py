"""BadgeSdk 0x9E control channel (service C2E6FD00-E966-1000-8000-BEF9C223DF6A)."""
import datetime
import hashlib
import struct

SERVICE = "c2e6fd00-e966-1000-8000-bef9c223df6a"
NOTIFY1 = "c2e6fd01-e966-1000-8000-bef9c223df6a"
WRITE = "c2e6fd02-e966-1000-8000-bef9c223df6a"
NOTIFY2 = "c2e6fd03-e966-1000-8000-bef9c223df6a"

CMD_BIND = 0x60
CMD_BIND_REPLY = 0x61
CMD_TIME = 0x02
CMD_LANG = 0x16
CMD_INFO = 0xC6
CMD_INFO_REPLY = 0xC7
CMD_PICSIZE = 0xDA
CMD_PICSIZE_REPLY = 0xDB
CMD_FILETYPE = 0xDC
CMD_GENERIC = 0xFF
FILETYPE_BADGE_MEDIA = 0x0C


def checksum(body):
    return sum(body) & 0xFF


def frame(cmd, payload=b"", seq=0, flag1=True):
    """Build a control frame. Bit2 of flags is set when payload+6 > 20."""
    long_ = len(payload) + 6 > 20
    flags = (4 if long_ else 0) | (2 if flag1 else 0) | ((seq & 0x0F) << 3)
    body = bytes([flags, cmd]) + struct.pack("<H", len(payload)) + payload
    return bytes([0x9E, checksum(body)]) + body


def parse_stream(buf):
    """Extract complete valid frames from a byte buffer. Returns (frames, rest)."""
    frames = []
    buf = bytes(buf)
    while True:
        i = buf.find(b"\x9E")
        if i < 0:
            return frames, b""
        buf = buf[i:]
        if len(buf) < 6:
            return frames, buf
        n = struct.unpack_from("<H", buf, 4)[0]
        if len(buf) < 6 + n:
            return frames, buf
        if checksum(buf[2:6 + n]) != buf[1]:
            buf = buf[1:]
            continue
        frames.append({"flags": buf[2], "cmd": buf[3], "payload": buf[6:6 + n], "wants_ack": bool(buf[2] & 2)})
        buf = buf[6 + n:]


def ack_frame(cmd, status=0):
    return frame(CMD_GENERIC, bytes([cmd, status]))


def device_id(seed=None):
    """6-byte id, little endian 32-bit value. The app hashes Build fields; any stable value works [I]."""
    seed = seed or "rebeambox"
    v = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:4], "little")
    return struct.pack("<I", v) + b"\x00\x00"


def bind_payload(dev_id, twelve_hour=False, non_chinese=True):
    flags = (4 if twelve_hour else 0) | (2 if non_chinese else 0)
    return bytes([flags]) + dev_id + dev_id


def time_payload(dt=None):
    dt = dt or datetime.datetime.now()
    return struct.pack("<HBBBBB", dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


def parse_bind_reply(p):
    r = {"state": p[0], "ok": p[0] == 0}
    if len(p) >= 23:
        ver = p[1:4].rstrip(b"\x00").decode("ascii", "replace")
        r["protocol_text"] = ver
        try:
            r["protocol"] = int(ver.replace(".", ""))
        except ValueError:
            r["protocol"] = 23
        r["firmware"] = p[4:14].rstrip(b"\x00").decode("ascii", "replace")
        r["platform"] = p[14]
    return r


def parse_info_reply(p):
    if not p or p[0] != 1 or len(p) < 13:
        return None
    sw, sh, pw, ph = struct.unpack_from("<HHHH", p, 1)
    (kb,) = struct.unpack_from("<I", p, 9)
    return {"screen": (sw, sh), "picture": (pw, ph), "memory_kb": kb}


def parse_picsize_reply(p):
    if len(p) < 20:
        return None
    v = struct.unpack(">" + "H" * (len(p) // 2 if len(p) < 24 else 12), p[:24 if len(p) >= 24 else 20])
    out = {"album_shrink": v[0:2], "album": v[2:4], "dial_shrink": v[4:6], "dial": v[6:8], "map": v[8:10],
           "preview": (128, 128)}
    if len(v) >= 12:
        out["preview"] = v[10:12]
    return out
