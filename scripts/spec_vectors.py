#!/usr/bin/env python3
"""Reference calculations for docs/PROTOCOL.md worked examples. Not the client."""
import struct

def nn_checksum(b):            # nn20 stack: two's complement of byte sum
    return (-sum(b)) & 0xFF

def nn_frames(type_, payload, data_per_pkt):
    env = b'{"type":%d,"data":' % type_ + payload + b'}'
    n = (len(env) + data_per_pkt - 1) // data_per_pkt
    out = []
    for i in range(n):
        chunk = env[i*data_per_pkt:(i+1)*data_per_pkt]
        f = bytes([0xF1, type_]) + struct.pack(">HHH", n, n-1-i, len(chunk)) + chunk
        out.append(f + bytes([nn_checksum(f)]))
    return out

def nn_cmd(json_bytes, type_=13):
    f = bytes([0xF1, type_]) + struct.pack(">HHH", 0, 0, len(json_bytes)) + json_bytes
    return f + bytes([nn_checksum(f)])

def imb(w, h, jpeg):
    return (b"IMB\x00" + struct.pack("<iiBBhhhiiii", 4, len(jpeg)+32, 11, 0, 0, w, h, 36, len(jpeg), 0, 0)) + jpeg

def gif_container(frames, interval_ms, w, h, wifi=False):
    n = len(frames)
    addr_len = n*16 + (32 if wifi else 24)
    head_len = n*16 + 32
    buf = bytearray(head_len)
    struct.pack_into("<IIII", buf, 0, 0x12345678, addr_len, n, interval_ms)
    buf[16:28] = (b"output/%dms" % interval_ms)[:12].ljust(12, b"\0")
    offs = []
    pos = head_len
    for f in frames:
        offs.append(pos); pos += 32 + len(f)
    for i in range(n):
        name = (b"frame_%05d." % (i+1))[:12].ljust(12, b"\0")
        buf[32+i*16:32+i*16+12] = name
        struct.pack_into("<I", buf, 32+i*16+12, offs[i])
    body = bytearray()
    for i, f in enumerate(frames):
        nxt = offs[i+1] if i < n-1 else offs[0]
        body += struct.pack("<II", offs[i], nxt) + struct.pack("<BBhhhiiii", 11, 0, 0, w, h, offs[i]+32, len(f), 0, 0) + f
    out = bytearray(buf + body)
    struct.pack_into("<I", out, 28, len(out)-1)
    return bytes(out)

def ctl_frame(cmd, payload, seq=0, long_=False, resp=False):   # BadgeSdk control channel
    flags = ((1 if long_ else 0) << 2) | (1 << 1) | (1 if resp else 0) | (seq << 3)
    body = bytes([flags, cmd]) + struct.pack("<H", len(payload)) + payload
    return bytes([0x9E, sum(body) & 0xFF]) + body

def rcsp(opcode, params, sn=0, is_cmd=True, has_resp=True):
    flag = (0x80 if is_cmd else 0) | (0x40 if has_resp else 0)
    body = bytes([flag, opcode]) + struct.pack(">H", len(params)+1) + bytes([sn]) + params
    return b"\xFE\xDC\xBA" + body + b"\xEF"

def crc16_xmodem(data, c=0):
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c

if __name__ == "__main__":
    h = lambda b: b.hex(" ").upper()
    print("== A. nn20 command type 13");  print(h(nn_cmd(b'{"animation_type":1}')))
    jpeg = bytes.fromhex("FFD8FFE000104A46494600") + b"\xFF\xD9"      # fake 13-byte stand-in for a JPEG
    img = imb(368, 368, jpeg)
    print("== B. IMB wrapped stand-in image, %d bytes" % len(img)); print(h(img))
    fr = nn_frames(6, img, 11)   # MTU 23 -> 11 data bytes per packet
    print("== C. type 6 frames at MTU 23 (data 11), count", len(fr))
    for f in fr: print(h(f))
    print("== D. GIF container, 2 frames of 13-byte stand-in, 100 ms, 368x368, BLE")
    g = gif_container([jpeg, jpeg], 100, 368, 368); print(len(g)); print(h(g))
    print("== E. BadgeSdk control: file type 0x0C, cmd 0xDC"); print(h(ctl_frame(0xDC, b"\x0C")))
    print("== F. BadgeSdk control: get info 0xC6 [01]"); print(h(ctl_frame(0xC6, b"\x01")))
    print("== G. RCSP example (opcode 0x1B start large file, params size/crc/name)"); 
    name = "/x.jpg".encode("utf-16le")
    print(h(rcsp(0x1B, struct.pack(">IH", 1000, crc16_xmodem(b"abc")) + name)))
    print("CRC16 XMODEM('123456789') = %04X" % crc16_xmodem(b"123456789"))
