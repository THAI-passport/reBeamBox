"""Jieli RCSP framing and large-file-transfer payloads (BadgeSdk path).

Pure functions, no I/O. Layouts are documented in docs/PROTOCOL.md section 3.7.
"""
import re
import struct

HEAD = b"\xFE\xDC\xBA"
TAIL = b"\xEF"

OP_DATA = 0x01
OP_GET_TARGET_INFO = 0x03
OP_GET_SYS_INFO = 0x07
OP_START_LARGE = 0x1B
OP_STOP_LARGE = 0x1C
OP_LARGE_OP = 0x1D
OP_CANCEL_LARGE = 0x1E
OP_GET_NAME = 0x20
OP_PREPARE_ENV = 0x21
OP_DEVICE_EXTEND = 0x27


def crc16_xmodem(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def pack(opcode, payload=b"", *, command=True, want_response=False, sn=0, status=0, xm_opcode=None):
    """Build one RCSP frame. For opcode 0x01 (data) xm_opcode is the inner opcode."""
    flag = (0x80 if command else 0) | (0x40 if want_response else 0)
    body = bytes([sn]) if command else bytes([status, sn])
    if opcode == OP_DATA:
        body += bytes([xm_opcode])
    body += payload
    return HEAD + bytes([flag, opcode]) + struct.pack(">H", len(body)) + body + TAIL


def unpack(buf):
    """Parse one frame at the start of buf. Returns (dict, rest) or (None, buf)."""
    i = buf.find(HEAD)
    if i < 0 or len(buf) < i + 7:
        return None, buf
    flag, opcode = buf[i + 3], buf[i + 4]
    (n,) = struct.unpack_from(">H", buf, i + 5)
    end = i + 7 + n
    if len(buf) < end + 1:
        return None, buf
    body = buf[i + 7:end]
    command = bool(flag & 0x80)
    f = {"command": command, "want_response": bool(flag & 0x40), "opcode": opcode}
    p = 0
    if not command:
        f["status"] = body[0]; p = 1
    f["sn"] = body[p]; p += 1
    if opcode == OP_DATA:
        f["xm_opcode"] = body[p]; p += 1
    f["payload"] = body[p:]
    return f, buf[end + 1:]


# --- commands the app sends -------------------------------------------------
def get_target_info(sn, mask=0xFFFFFFFF, platform=0):
    return pack(OP_GET_TARGET_INFO, struct.pack(">IB", mask, platform), want_response=True, sn=sn)

def get_storage_info(sn):
    """GetSysInfo(function 0xFF, mask 4): attribute type 2 = storage devices."""
    return pack(OP_GET_SYS_INFO, struct.pack(">BI", 0xFF, 4), want_response=True, sn=sn)

def prepare_env_large_file(sn):
    return pack(OP_PREPARE_ENV, b"\x00", want_response=True, sn=sn)

def device_extend_file_transfer(sn, dev_handle, app_has_crc16=True):
    return pack(OP_DEVICE_EXTEND, struct.pack(">BIB", 0, dev_handle, 1 if app_has_crc16 else 0),
                want_response=True, sn=sn)

def start_large_file(sn, size, crc16, path_bytes):
    return pack(OP_START_LARGE, struct.pack(">IH", size, crc16) + path_bytes, want_response=True, sn=sn)

def data_chunks(file_bytes, offset, buf_size, mtu, with_crc16, sn_start, first_seq=0):
    """Frames answering one device LargeFileTransferOp read request (offset, buf_size)."""
    seg = file_bytes[offset:offset + min(buf_size, len(file_bytes) - offset)]
    frames, seq = [], first_seq
    for i in range(0, len(seg), mtu):
        part = seg[i:i + mtu]
        if with_crc16:
            body = bytes([seq & 0xFF]) + struct.pack(">H", crc16_xmodem(part)) + part
        else:
            body = bytes([seq & 0xFF]) + part
        frames.append(pack(OP_DATA, body, command=True, want_response=False,
                           sn=(sn_start + len(frames)) & 0xFF, xm_opcode=OP_LARGE_OP))
        seq += 1
    return frames

def temp_name_payload(file_name, mtime_ms, out_dir=None):
    """Remote temp path sent in StartLargeFileTransfer: '%08x.tmp\\0' of Java String.hashCode."""
    h = 0
    raw = (file_name + str(mtime_ms)).encode("utf-16-be")
    for (unit,) in struct.iter_unpack(">H", raw):   # Java String.hashCode over UTF-16 units
        h = (31 * h + unit) & 0xFFFFFFFF
    name = "%08x.tmp\0" % h
    if out_dir:
        name = out_dir.rstrip("/") + "/" + name
    return name.encode()

def get_name_response_payload(name, retry=0):
    """Payload of the response to the device's GetName request (opcode 0x20)."""
    name = re.sub(r"[\x00-\x1f/:<>\\\"]", "", name)
    dot = name.rfind(".")
    stem, ext = (name[:dot], name[dot:]) if dot != -1 else (name, "")
    suffix = ("000" + str(retry))[-3:] if retry > 0 else ""
    short = stem + suffix
    gb = short.encode("gbk", "replace")
    if len(gb) < 9 and len(ext) < 5:
        return (short + ext).encode("gbk", "replace") + b"\x00\x00"
    return b"\\U" + (stem + suffix + ext).encode("utf-16-le") + b"\x00\x00"

# --- parsing of device replies ---------------------------------------------
def parse_start_response(payload):
    """StartLargeFileTransfer response payload: u16 transfer MTU (big endian)."""
    return struct.unpack(">H", payload[:2])[0]

def parse_read_request(payload):
    """LargeFileTransferOp payload from the device: op(0)=read, u16 size, u32 offset."""
    op = payload[0]
    if op != 0:
        raise ValueError("unsupported op %d" % op)
    size, offset = struct.unpack(">HI", payload[1:7])
    return offset, size

AUTH_RESET_FRAME = bytes.fromhex("FEDCBAC00600020001EF")  # raw: flag C0, opcode 06, len 2, payload 00 01 (no sn byte)


# --- device info parsing -----------------------------------------------------
def parse_ltv(buf):
    """Records `len type data` where len counts the type byte plus data."""
    out, i = [], 0
    while i < len(buf):
        n = buf[i]
        if n < 1 or i + 1 + n > len(buf):
            break
        out.append((buf[i + 1], bytes(buf[i + 2:i + 1 + n])))
        i += 1 + n
    return out

def parse_target_info(payload):
    """GetTargetInfo reply -> dict(mtu, crc16). Defaults: MTU 530, no packet CRC."""
    info = {"mtu": 530, "crc16": False, "raw": dict(parse_ltv(payload))}
    for t, d in parse_ltv(payload):
        if t == 13 and len(d) >= 2:
            info["mtu"] = struct.unpack(">H", d[:2])[0]
        elif t == 21 and len(d) >= 4:
            info["crc16"] = bool(struct.unpack(">I", d[:4])[0] & 1)
    return info

STORAGE_NAMES = {0: "USB", 1: "SD Card 0", 2: "SD Card 1", 3: "Flash", 4: "LineIn", 5: "Flash2", 6: "Flash3"}

def parse_sys_info(payload):
    """GetSysInfo reply -> {attr_type: bytes}. First byte is the function code."""
    attrs, i = {}, 1
    while i < len(payload):
        n = payload[i]
        if n < 1 or i + 1 + n > len(payload):
            break
        attrs[payload[i + 1]] = bytes(payload[i + 2:i + 1 + n])
        i += 1 + n
    return attrs

def parse_storage(data):
    """Storage attribute -> list of dict(index, name, online, handle)."""
    out = []
    if not data:
        return out
    if data[0] == 0xFF:                       # new layout: FF version LTV...
        for t, d in parse_ltv(data[2:]):
            if t == 1:
                i = 0
                while i + 2 <= len(d):
                    online, idx = d[i] == 1, d[i + 1]
                    handle = None
                    n = 2
                    if online and i + 6 <= len(d):
                        handle = struct.unpack(">I", d[i + 2:i + 6])[0]; n = 6
                    out.append({"index": idx, "name": STORAGE_NAMES.get(idx, "?"), "online": online, "handle": handle})
                    i += n
    else:                                     # legacy: online bitmask then u32 handles (index 4 has none)
        mask, i = data[0], 1
        for idx in range(6):
            handle = None
            if idx != 4:
                if i + 4 > len(data):
                    break
                handle = struct.unpack(">I", data[i:i + 4])[0]; i += 4
            out.append({"index": idx, "name": STORAGE_NAMES.get(idx, "?"), "online": bool(mask >> idx & 1), "handle": handle})
    return out

def pick_storage(entries):
    """App rule: online 'SD Card 1' first, else first online USB or SD (indices 0,1,2)."""
    on = [e for e in entries if e["online"] and e["handle"] is not None]
    for e in on:
        if e["index"] == 2:
            return e
    for e in on:
        if e["index"] in (0, 1, 2):
            return e
    return None
