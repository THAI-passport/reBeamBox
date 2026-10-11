#!/usr/bin/env python3
"""Replay a phone capture of the vendor app: read btsnoop_hci.log or pcap/pcapng, pull the ATT writes to the badge
characteristics (0x01F1 nn20, C2E6FD02 control, 0xAE01 RCSP), reassemble the streams and decode them with
rebeambox.nn20 / control / rcsp. Offline only, no Bluetooth, no network.

    python tools/replay_pcap.py btsnoop_hci.log --out extracted/
    python tools/replay_pcap.py capture.pcapng --json report.json
    python tools/replay_pcap.py btsnoop_hci.log --handle 0x0012=nn20     # when the capture lacks GATT discovery

Handles are mapped to UUIDs from the discovery traffic in the capture (Read By Type / Find Information responses).
If a handle is unknown, writes are classified by their shape (F1 frame with a consistent length field = nn20, 9E = control,
FE DC BA = RCSP). Everything is labelled so a wrong guess is visible.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rebeambox import control, nn20, rcsp  # noqa: E402

ROLES = {"nn20": "01f1", "control": "c2e6fd02", "rcsp": "ae01"}
NOTIFY_ROLES = {"01f2": "nn20", "c2e6fd01": "control", "c2e6fd03": "control", "ae02": "rcsp"}
BTSNOOP_MAGIC = b"btsnoop\x00"


# --- capture containers ----------------------------------------------------------------------------
def read_capture(path):
    """Return a list of (ts_seconds, direction, h4_bytes). direction: 'tx' host to controller, 'rx', or None."""
    data = open(path, "rb").read()
    if data[:8] == BTSNOOP_MAGIC:
        return _btsnoop(data)
    if data[:4] == b"\x0a\x0d\x0d\x0a":
        return _pcapng(data)
    if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
        return _pcap(data)
    raise ValueError("not a btsnoop, pcap or pcapng file")


def _btsnoop(d):
    _ver, link = struct.unpack(">II", d[8:16])
    if link not in (1001, 1002):
        raise ValueError("btsnoop datalink %d not supported (need 1001 or 1002)" % link)
    out, i = [], 16
    while i + 24 <= len(d):
        _orig, incl, flags, _drops, ts = struct.unpack(">IIIIQ", d[i:i + 24])
        pkt = d[i + 24:i + 24 + incl]
        i += 24 + incl
        direction = "rx" if flags & 1 else "tx"
        if link == 1001:                       # no packet indicator: bit 1 of flags marks command/event
            if flags & 2:
                continue
            pkt = b"\x02" + pkt
        out.append(((ts - 0x00dcddb30f2f8000) / 1e6, direction, pkt))
    return out


def _wrap_h4(link, raw):
    if link == 187:
        return None, raw
    if link == 201:
        return ("tx" if struct.unpack(">I", raw[:4])[0] == 0 else "rx"), raw[4:]
    raise ValueError("pcap linktype %d not supported (need 187 or 201)" % link)


def _pcap(d):
    big = d[:4] in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")
    e = ">" if big else "<"
    nano = d[:4] in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    link = struct.unpack(e + "I", d[20:24])[0]
    out, i = [], 24
    while i + 16 <= len(d):
        sec, frac, incl, _orig = struct.unpack(e + "IIII", d[i:i + 16])
        raw = d[i + 16:i + 16 + incl]
        i += 16 + incl
        direction, h4 = _wrap_h4(link, raw)
        out.append((sec + frac / (1e9 if nano else 1e6), direction, h4))
    return out


def _pcapng(d):
    out, i, e, links = [], 0, "<", []
    while i + 12 <= len(d):
        if d[i:i + 4] == b"\x0a\x0d\x0d\x0a":
            e = "<" if d[i + 8:i + 12] == b"\x4d\x3c\x2b\x1a" else ">"
            links = []
        btype, blen = struct.unpack(e + "II", d[i:i + 8])
        body = d[i + 8:i + blen - 4]
        if btype == 1:
            links.append(struct.unpack(e + "H", body[:2])[0])
        elif btype == 6:
            iface, hi, lo, cap, _orig = struct.unpack(e + "IIIII", body[:20])
            direction, h4 = _wrap_h4(links[iface], body[20:20 + cap])
            out.append((((hi << 32) | lo) / 1e6, direction, h4))
        if blen < 12:
            break
        i += blen
    return out


# --- HCI ACL, L2CAP, ATT ---------------------------------------------------------------------------
def att_events(packets):
    """Yield dicts {ts, dir, conn, opcode, pdu} for every complete L2CAP ATT PDU (CID 4), reassembling ACL fragments."""
    pend = {}
    for ts, direction, pkt in packets:
        if not pkt or pkt[0] != 0x02 or len(pkt) < 5:
            continue
        hf, ln = struct.unpack("<HH", pkt[1:5])
        conn, pb = hf & 0x0FFF, (hf >> 12) & 3
        chunk = pkt[5:5 + ln]
        key = (direction, conn)
        if pb in (0, 2):
            if len(chunk) < 4:
                continue
            l2len, cid = struct.unpack("<HH", chunk[:4])
            pend[key] = [cid, l2len, bytearray(chunk[4:])]
        elif pb == 1 and key in pend:
            pend[key][2] += chunk
        else:
            continue
        cid, l2len, buf = pend[key]
        if len(buf) >= l2len:
            del pend[key]
            if cid == 4 and l2len:
                yield {"ts": ts, "dir": direction, "conn": conn, "opcode": buf[0], "pdu": bytes(buf[:l2len])}


def uuid_text(raw):
    """2-byte or 16-byte little-endian UUID to lower-case text: 4 hex digits for Bluetooth base UUIDs."""
    if len(raw) == 2:
        return "%04x" % struct.unpack("<H", raw)[0]
    h = raw[::-1].hex()
    full = "%s-%s-%s-%s-%s" % (h[:8], h[8:12], h[12:16], h[16:20], h[20:])
    if full.endswith("-0000-1000-8000-00805f9b34fb") and full.startswith("0000"):
        return full[4:8]
    return full


def handle_map(events):
    """value handle -> uuid text, from characteristic declarations and Find Information responses."""
    m = {}
    for ev in events:
        p = ev["pdu"]
        if ev["opcode"] == 0x09 and len(p) > 2 and p[1] in (7, 21):         # Read By Type response, characteristics
            n = p[1]
            for k in range(2, len(p) - n + 1, n):
                item = p[k:k + n]
                vh = struct.unpack("<H", item[3:5])[0]
                m[vh] = uuid_text(item[5:])
        elif ev["opcode"] == 0x05 and len(p) > 2:                           # Find Information response
            w = 4 if p[1] == 1 else 18
            for k in range(2, len(p) - w + 1, w):
                h = struct.unpack("<H", p[k:k + 2])[0]
                u = uuid_text(p[k + 2:k + w])
                if u not in ("2800", "2801", "2802", "2803", "2900", "2901", "2902", "2903", "2904"):
                    m.setdefault(h, u)
    return m


def role_of(uuid):
    u = (uuid or "").lower()
    for role, key in ROLES.items():
        if u == key or u.startswith(key + "-"):
            return role
    return None


def guess_role(value):
    if len(value) >= 9 and value[0] == 0xF1 and struct.unpack(">H", value[6:8])[0] == len(value) - 9:
        return "nn20"
    if value[:1] == b"\x9e" and len(value) >= 6 and control.checksum(value[2:]) == value[1]:
        return "control"
    if value[:3] == rcsp.HEAD:
        return "rcsp"
    return None


# --- decoders --------------------------------------------------------------------------------------
def decode_nn20(values):
    """Group F1 frames into transfers. Returns list of dicts with the reassembled envelope.
    Reports bad checksums and sequence gaps (dropped or repeated packets) instead of failing."""
    out, cur = [], None
    for v in values:
        if len(v) < 9 or v[0] != 0xF1:
            continue
        ok = nn20.checksum(v[:-1]) == v[-1]
        typ = v[1]
        n, rem, ln = struct.unpack(">HHH", v[2:8])
        data = v[8:8 + ln]
        if n == 0:                                   # settings frame
            out.append({"type": typ, "packets": 1, "bad_checksums": 0 if ok else 1, "settings": data.decode("utf-8", "replace")})
            continue
        if rem == n - 1 or cur is None:
            cur = {"type": typ, "packets": n, "bad_checksums": 0, "got": 0, "env": bytearray(), "gaps": [], "expected": n - 1}
            out.append(cur)
        if rem != cur["expected"]:
            cur["gaps"].append({"expected_remaining": cur["expected"], "got_remaining": rem})
        cur["expected"] = rem - 1
        cur["got"] += 1
        cur["env"] += data
        cur["bad_checksums"] += 0 if ok else 1
    for t in out:
        if "env" in t:
            t.pop("expected")
            t["complete"] = t["got"] == t["packets"] and not t["gaps"]
            t["envelope"] = bytes(t.pop("env"))
            pre = b'{"type":%d,"data":' % t["type"]
            if not t["complete"]:
                t["container"] = {"kind": "incomplete", "frames": []}
            elif t["envelope"].startswith(pre) and t["envelope"].endswith(b"}"):
                t["payload"] = t["envelope"][len(pre):-1]
                t["container"] = decode_container(t["payload"])
            else:
                t["container"] = {"kind": "bad envelope", "frames": []}
    return out


def decode_container(b):
    """IMB still or 0x12345678 animation container -> dict with JPEG frames. Never raises."""
    try:
        return _decode_container(b)
    except (struct.error, IndexError, ValueError):
        return {"kind": "corrupt", "frames": []}


def _decode_container(b):
    if b[:4] == b"IMB\x00" and len(b) >= 36:
        ln = struct.unpack_from("<i", b, 24)[0]
        w, h = struct.unpack_from("<hh", b, 16)
        return {"kind": "imb", "width": w, "height": h, "frames": [b[36:36 + ln]]}
    if b[:4] == b"\x78\x56\x34\x12" and len(b) >= 32:
        _m, _sz, n, interval = struct.unpack_from("<IIII", b, 0)
        frames, w, h = [], None, None
        for i in range(n):
            off = struct.unpack_from("<I", b, 32 + i * 16 + 12)[0]
            w, h = struct.unpack_from("<hh", b, off + 12)
            doff, dlen = struct.unpack_from("<ii", b, off + 16)
            frames.append(b[doff:doff + dlen])
        return {"kind": "animation", "frames": frames, "interval_ms": interval, "width": w, "height": h}
    return {"kind": "unknown", "frames": []}


def decode_control(values):
    frames, _rest = control.parse_stream(b"".join(values))
    return [{"cmd": "0x%02X" % f["cmd"], "len": len(f["payload"]), "payload": f["payload"].hex()} for f in frames]


def decode_rcsp(values):
    """Reassemble the AE01 write stream. Reports per-chunk CRC16 errors and sequence gaps of the file data."""
    buf, frames, raw, data_chunks = b"".join(values), [], [], []
    while buf:
        i = buf.find(rcsp.HEAD)
        if i < 0:
            raw.append(buf.hex())
            break
        if i:
            raw.append(buf[:i].hex())                 # auth exchange bytes are not framed
        try:
            f, rest = rcsp.unpack(buf[i:])
        except (struct.error, IndexError):
            break
        if f is None:
            break
        frames.append(f)
        buf = rest
    for f in frames:
        if f["opcode"] == rcsp.OP_DATA and f.get("xm_opcode") == rcsp.OP_LARGE_OP and f["command"] and len(f["payload"]) >= 1:
            data_chunks.append(f["payload"])

    def crc_ok(c):
        return len(c) >= 3 and rcsp.crc16_xmodem(c[3:]) == struct.unpack(">H", c[1:3])[0]
    with_crc = any(crc_ok(c) for c in data_chunks)
    crc_errors = [k for k, c in enumerate(data_chunks) if with_crc and not crc_ok(c)]
    seq_gaps, prev = [], None
    for k, c in enumerate(data_chunks):
        if prev is not None and c[0] != (prev + 1) & 0xFF:
            seq_gaps.append({"index": k, "expected_seq": (prev + 1) & 0xFF, "got_seq": c[0]})
        prev = c[0]
    body = b"".join(c[3:] if with_crc else c[1:] for c in data_chunks)
    kind = "jpeg" if body[:2] == b"\xff\xd8" else "avi" if body[:4] == b"RIFF" else "unknown" if body else "none"
    return {"frames": len(frames), "opcodes": sorted({"0x%02X" % f["opcode"] for f in frames}),
            "unframed_chunks": raw, "file_chunks": len(data_chunks), "chunk_crc16": with_crc,
            "crc_errors": crc_errors, "seq_gaps": seq_gaps,
            "file": body, "file_kind": kind}


def decode_auth(seq):
    """seq: ordered [(dir, bytes)] on AE01 (tx) and AE02 (rx). Checks the Jieli challenge-response against E1 with the
    default key. Returns None when no auth traffic is present."""
    from rebeambox import jl_auth
    steps, st = [], {"complete": False}
    app_r = dev_r = None
    for d, b in seq:
        if d == "tx" and len(b) == 17 and b[0] == 0:
            app_r = b
            steps.append("app challenge")
        elif d == "rx" and len(b) == 17 and b[0] == 1 and app_r is not None and "badge_response_valid" not in st:
            st["badge_response_valid"] = b == jl_auth.encrypt_challenge(app_r)
            steps.append("badge response (%s)" % ("valid" if st["badge_response_valid"] else "WRONG"))
        elif d == "tx" and b[:5] == jl_auth.AUTH_OK and len(b) == 5:
            steps.append("app pass")
        elif d == "rx" and len(b) == 17 and b[0] == 0:
            dev_r = b
            steps.append("badge challenge")
        elif d == "tx" and len(b) == 17 and b[0] == 1 and dev_r is not None:
            st["app_response_valid"] = b == jl_auth.encrypt_challenge(dev_r)
            steps.append("app response (%s)" % ("valid" if st["app_response_valid"] else "WRONG"))
        elif d == "rx" and b[:5] == jl_auth.AUTH_OK and len(b) == 5 and "app_response_valid" in st:
            st["complete"] = True
            steps.append("badge pass")
    if not steps:
        return None
    st["steps"] = steps
    st["ok"] = bool(st["complete"] and st.get("badge_response_valid") and st.get("app_response_valid"))
    return st


# --- analysis --------------------------------------------------------------------------------------
def analyze(path, overrides=None):
    packets = read_capture(path)
    evs = list(att_events(packets))
    hmap = handle_map(evs)
    for h, role in (overrides or {}).items():
        hmap[h] = ROLES[role]
    writes = {"nn20": [], "control": [], "rcsp": []}
    notifs = {"nn20": [], "control": []}
    rcsp_seq = []
    unmatched = 0
    for ev in evs:
        p = ev["pdu"]
        if ev["opcode"] in (0x12, 0x52) and len(p) >= 3 and ev["dir"] in ("tx", None):
            h, value = struct.unpack("<H", p[1:3])[0], p[3:]
            role = role_of(hmap.get(h)) or guess_role(value)
            if role:
                writes[role].append(value)
                if role == "rcsp":
                    rcsp_seq.append(("tx", value))
            else:
                unmatched += 1
        elif ev["opcode"] == 0x1B and len(p) >= 3 and ev["dir"] in ("rx", None):
            h = struct.unpack("<H", p[1:3])[0]
            r = next((role for key, role in NOTIFY_ROLES.items() if hmap.get(h, "").startswith(key)), None)
            if r == "rcsp":
                rcsp_seq.append(("rx", p[3:]))
            if r in notifs:
                notifs[r].append(p[3:])
    res = {"file": path, "hci_packets": len(packets), "att_pdus": len(evs), "mapped_handles": {"0x%04X" % h: u for h, u in hmap.items()},
           "write_counts": {k: len(v) for k, v in writes.items()}, "unmatched_writes": unmatched}
    res["nn20"] = decode_nn20(writes["nn20"])
    res["control"] = decode_control(writes["control"])
    res["rcsp"] = decode_rcsp(writes["rcsp"]) if writes["rcsp"] else None
    res["rcsp_auth"] = decode_auth(rcsp_seq)
    res["warnings"] = warnings(res)
    nn_replies, _ = nn20.parse_reply_stream(b"".join(notifs["nn20"]))
    res["nn20_replies"] = [t for _ty, t in nn_replies]
    return res


def warnings(res):
    w = []
    for k, t in enumerate(res["nn20"]):
        if "settings" in t:
            continue
        if t["bad_checksums"]:
            w.append("nn20 transfer #%d: %d packet(s) with a bad checksum" % (k, t["bad_checksums"]))
        for g in t["gaps"]:
            w.append("nn20 transfer #%d: sequence gap, expected remaining %d, got %d" % (k, g["expected_remaining"], g["got_remaining"]))
        if not t["complete"]:
            w.append("nn20 transfer #%d incomplete: %d of %d packets" % (k, t["got"], t["packets"]))
    r = res.get("rcsp")
    if r:
        if r["crc_errors"]:
            w.append("rcsp file chunks with a bad CRC16: %s" % r["crc_errors"])
        for g in r["seq_gaps"]:
            w.append("rcsp file chunk %d: sequence %d, expected %d" % (g["index"], g["got_seq"], g["expected_seq"]))
    a = res.get("rcsp_auth")
    if a and not a["ok"]:
        w.append("rcsp authentication did not complete cleanly: %s" % ", ".join(a["steps"]))
    return w


def save_extracts(res, outdir):
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for k, t in enumerate(res["nn20"]):
        c = t.get("container")
        if c:
            for j, jpg in enumerate(c["frames"]):
                p = os.path.join(outdir, "nn20_%02d_frame_%03d.jpg" % (k, j))
                open(p, "wb").write(jpg)
                paths.append(p)
    r = res.get("rcsp")
    if r and r["file"]:
        p = os.path.join(outdir, "rcsp_file.%s" % {"jpeg": "jpg", "avi": "avi"}.get(r["file_kind"], "bin"))
        open(p, "wb").write(r["file"])
        paths.append(p)
    return paths


def to_jsonable(o):
    if isinstance(o, (bytes, bytearray)):
        return {"bytes": len(o)}
    if isinstance(o, dict):
        return {k: to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(x) for x in o]
    return o


def summary(res):
    L = ["capture %s: %d HCI packets, %d ATT PDUs" % (res["file"], res["hci_packets"], res["att_pdus"]),
         "writes: %s, unmatched: %d" % (res["write_counts"], res["unmatched_writes"])]
    for k, t in enumerate(res["nn20"]):
        if "settings" in t:
            L.append("nn20 #%d type %d settings %s" % (k, t["type"], t["settings"]))
            continue
        c = t.get("container") or {}
        L.append("nn20 #%d type %d: %d packets (%s), bad checksums %d, %s %s frames%s" % (
            k, t["type"], t["packets"], "complete" if t["complete"] else "INCOMPLETE", t["bad_checksums"],
            c.get("kind", "no container"), len(c.get("frames", [])),
            ", interval %d ms, %dx%d" % (c["interval_ms"], c["width"], c["height"]) if c.get("kind") == "animation" else
            (", %dx%d" % (c["width"], c["height"]) if c.get("kind") == "imb" else "")))
    if res["control"]:
        L.append("control frames: " + ", ".join(f["cmd"] for f in res["control"]))
    r = res["rcsp"]
    if r:
        L.append("rcsp: %d frames, opcodes %s, %d file chunks (crc16 %s), file %s %d bytes, %d unframed (auth) chunks" % (
            r["frames"], ",".join(r["opcodes"]), r["file_chunks"], r["chunk_crc16"], r["file_kind"], len(r["file"]), len(r["unframed_chunks"])))
    if res.get("rcsp_auth"):
        L.append("rcsp auth: %s (%s)" % ("ok" if res["rcsp_auth"]["ok"] else "NOT ok", ", ".join(res["rcsp_auth"]["steps"])))
    for w in res.get("warnings", []):
        L.append("WARNING: " + w)
    if res["nn20_replies"]:
        L.append("nn20 replies: %d (first: %s)" % (len(res["nn20_replies"]), res["nn20_replies"][0][:80]))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("capture")
    ap.add_argument("--out", help="directory for extracted JPEG frames and RCSP file")
    ap.add_argument("--json", help="write the decoded report to this file")
    ap.add_argument("--handle", action="append", default=[], metavar="0xHHHH=nn20|control|rcsp", help="force a handle to a role")
    a = ap.parse_args(argv)
    ov = {}
    for item in a.handle:
        h, role = item.split("=")
        ov[int(h, 0)] = role
    res = analyze(a.capture, ov)
    print(summary(res))
    if a.out:
        for p in save_extracts(res, a.out):
            print("wrote", p)
    if a.json:
        json.dump(to_jsonable(res), open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
