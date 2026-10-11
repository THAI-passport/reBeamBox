"""Software badges used for --dry-run and tests. They implement the badge side of the documented protocol."""
import json
import re
import os
import struct

from . import control, jl_auth, nn20, rcsp, wifi

AE00 = "0000ae00-0000-1000-8000-00805f9b34fb"
AE01 = "0000ae01-0000-1000-8000-00805f9b34fb"
AE02 = "0000ae02-0000-1000-8000-00805f9b34fb"


class SimBadge:
    def attach(self, link):
        self.link = link

    def on_subscribe(self, uuid):
        pass


class SimBadgeSdk(SimBadge):
    """Answers bind/info/picture size, runs Jieli auth and a device-pulled RCSP file transfer."""

    def __init__(self, picture=(360, 360), memory_kb=4096, read_size=1024, transfer_mtu=265, packet_crc=True):
        self.picture, self.memory_kb, self.read_size = picture, memory_kb, read_size
        self.transfer_mtu, self.packet_crc = transfer_mtu, packet_crc
        self._cbuf = b""
        self._rbuf = b""
        self.authed = False
        self.dev_rand = b"\x00" + bytes(range(1, 17))
        self._sn = 0x40
        self.received = None
        self.file_ok = None
        self.names = []
        self._xfer = None

    def has_service(self, uuid):
        return uuid.lower() in (control.SERVICE, AE00)

    # ---- control channel ----
    def _ctl(self, cmd, payload):
        self.link.push(control.NOTIFY1, control.frame(cmd, payload))

    def on_write(self, uuid, data):
        if uuid == control.WRITE:
            self._cbuf += data
            frames, self._cbuf = control.parse_stream(self._cbuf)
            for f in frames:
                self._on_ctl(f)
        elif uuid == AE01:
            self._on_ae01(data)

    def _on_ctl(self, f):
        c = f["cmd"]
        if c == control.CMD_BIND:
            p = bytes([0]) + b"2.9" + b"SIM-FW-1".ljust(10, b"\0")[:10] + bytes([1, 1, 0]) + bytes(4) + bytes(4) + bytes(8) + b"UI001"
            self._ctl(control.CMD_BIND_REPLY, p.ljust(40, b"\0"))
        elif c == control.CMD_INFO:
            w, h = self.picture
            self._ctl(control.CMD_INFO_REPLY, bytes([1]) + struct.pack("<HHHHI", w, h, w, h, self.memory_kb))
        elif c == control.CMD_PICSIZE:
            w, h = self.picture
            vals = [128, 128, w, h, 128, 128, w, h, w, h, w, h]
            self._ctl(control.CMD_PICSIZE_REPLY, struct.pack(">12H", *vals))
        elif c == control.CMD_FILETYPE:
            self._ctl(control.CMD_GENERIC, bytes([c, 0]))
        elif c in (control.CMD_TIME, control.CMD_LANG):
            self._ctl(control.CMD_GENERIC, bytes([c, 0]))

    # ---- RCSP ----
    def _out(self, data):
        self.link.push(AE02, data)

    def _on_ae01(self, data):
        if not self.authed and not data.startswith(rcsp.HEAD):
            self._auth_msg(data)
            return
        if data.startswith(jl_auth.AUTH_RESET):
            return
        self._rbuf += data
        while True:
            f, self._rbuf = rcsp.unpack(self._rbuf)
            if f is None:
                break
            self._rcsp(f)

    def _auth_msg(self, d):
        if len(d) == 17 and d[0] == 0:                     # app challenge
            self._out(jl_auth.encrypt_challenge(d))
        elif d[:5] == jl_auth.AUTH_OK:                     # app accepted us: send our challenge
            self._out(self.dev_rand)
        elif len(d) == 17 and d[0] == 1:                   # app answer to our challenge
            if d == jl_auth.encrypt_challenge(self.dev_rand):
                self._out(jl_auth.AUTH_OK)
                self.authed = True

    def _resp(self, f, payload=b"", status=0):
        self._out(rcsp.pack(f["opcode"], payload, command=False, status=status, sn=f["sn"]))

    def _cmd(self, opcode, payload):
        self._sn = (self._sn + 1) & 0xFF
        self._out(rcsp.pack(opcode, payload, command=True, want_response=True, sn=self._sn))

    def _rcsp(self, f):
        op = f["opcode"]
        if f["command"]:
            if op == rcsp.OP_GET_TARGET_INFO:
                ltv = bytes([3, 13]) + struct.pack(">H", 512) + bytes([5, 21]) + struct.pack(">I", 1 if self.packet_crc else 0)
                self._resp(f, ltv)
            elif op == rcsp.OP_GET_SYS_INFO:
                entries = bytes([1, 2]) + struct.pack(">I", 0xA1B2C3D4)
                data = b"\xFF\x00" + bytes([1 + len(entries), 1]) + entries
                self._resp(f, b"\xFF" + bytes([1 + len(data), 2]) + data)
            elif op == rcsp.OP_PREPARE_ENV:
                self._resp(f)
            elif op == rcsp.OP_DEVICE_EXTEND:
                self._resp(f, bytes([0, 1 if self.packet_crc else 0]))
            elif op == rcsp.OP_START_LARGE:
                size, crc = struct.unpack(">IH", f["payload"][:6])
                self._xfer = {"size": size, "crc": crc, "buf": bytearray(), "off": 0, "pend": 0, "expect": 0, "path": f["payload"][6:]}
                self._resp(f, struct.pack(">H", self.transfer_mtu))
                self._cmd(rcsp.OP_GET_NAME, b"")
                self._request_more()
            elif op == rcsp.OP_GET_NAME or op == rcsp.OP_STOP_LARGE:
                pass
            elif op == rcsp.OP_DATA:
                pass
        else:
            pass
        if f["command"] and op == rcsp.OP_DATA and f.get("xm_opcode") == rcsp.OP_LARGE_OP:
            self._data(f["payload"])
        elif (not f["command"]) and op == rcsp.OP_GET_NAME:
            self.names.append(f["payload"])

    def _request_more(self):
        x = self._xfer
        if x["off"] >= x["size"]:
            self._cmd(rcsp.OP_STOP_LARGE, b"\x00")
            return
        n = min(self.read_size, x["size"] - x["off"])
        x["pend"], x["expect"], x["seq"] = n, n, 0
        self._cmd(rcsp.OP_LARGE_OP, b"\x00" + struct.pack(">HI", n, x["off"]))

    def _data(self, p):
        x = self._xfer
        seq = p[0]
        if self.packet_crc:
            crc = struct.unpack(">H", p[1:3])[0]
            chunk = p[3:]
            if crc != rcsp.crc16_xmodem(chunk):
                self.file_ok = False
                return
        else:
            chunk = p[1:]
        if seq != x["seq"] & 0xFF:
            self.file_ok = False
        x["seq"] += 1
        x["buf"] += chunk
        x["pend"] -= len(chunk)
        if x["pend"] <= 0:
            x["off"] += x["expect"]
            if x["off"] >= x["size"]:
                self.received = bytes(x["buf"])
                ok = rcsp.crc16_xmodem(self.received) == x["crc"] and len(self.received) == x["size"]
                self.file_ok = ok if self.file_ok is None else (self.file_ok and ok)
            self._request_more()


class SimNn20(SimBadge):
    """nn20 badge: pushes a status record, acknowledges every packet."""

    def __init__(self, time_mode=0, freespace=20000, fail_packets=(), noack_fail_at=None, size="368,368"):
        self.time_mode, self.freespace, self.size = time_mode, freespace, size
        self.noack_fail_at = noack_fail_at      # in no-ACK mode report a drop at this write number, then ACK
        self.fail = set(fail_packets)
        self.packets = []
        self.n_seen = 0

    def has_service(self, uuid):
        return uuid.lower() == nn20.SERVICE

    def on_subscribe(self, uuid):
        st = json.dumps({"freespace": self.freespace, "allspace": 32000, "time_mode": self.time_mode,
                         "devname": "SIM-NN20", "brand": "sim", "type": 13, "size": self.size}, separators=(",", ":"))
        self.link.push(nn20.NOTIFY, nn20.make_reply(1, st))

    def on_write(self, uuid, data):
        if uuid != nn20.WRITE or data[0] != 0xF1 or data[1] == nn20.TYPE_SETTINGS:
            return
        assert nn20.checksum(data[:-1]) == data[-1]
        n_total, remaining = int.from_bytes(data[2:4], "big"), int.from_bytes(data[4:6], "big")
        if n_total and remaining == n_total - 1:      # first packet of a stream: a new upload starts
            self.packets = []
        self.packets.append(data)
        self.n_seen += 1
        if self.time_mode == 1:
            if self.noack_fail_at is not None and self.n_seen == self.noack_fail_at:
                self.time_mode = 0
                self.link.push(nn20.NOTIFY, nn20.make_reply(data[1], '{"msg":"GetPacketFail"}'))
            return
        ok = self.n_seen not in self.fail
        self.link.push(nn20.NOTIFY, nn20.make_reply(data[1], '{"msg":"%s"}' % ("GetPacketSuccess" if ok else "GetPacketFail")))

    def stream(self):
        """Reassembled envelope bytes."""
        return b"".join(p[8:-1] for p in self.packets)


class SimWifiBadge:
    """Software badge for the Wi-Fi path. Handles both connection kinds on one port: control words /
    camera frames, and HTTP POST /upload."""

    def __init__(self, free_kb=12000, refuse=False):
        self.free_kb, self.refuse = free_kb, refuse
        self.files = {}          # name -> bytes
        self.frames = []         # camera frames received
        self.finished = 0
        self.camera_open = False
        self.conns = []

    def new_conn(self, push):
        c = _WifiConn(self, push)
        self.conns.append(c)
        return c


class _WifiConn:
    def __init__(self, badge, push):
        self.b, self.push, self.buf = badge, push, b""
        self.http = None

    def feed(self, data):
        self.buf += data
        while self._step():
            pass

    def _step(self):
        b = self.b
        if self.http is None and self.buf[:5] == b"POST ":
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                return False
            head = self.buf[:end].decode("latin-1")
            name = re.search(r"X-Filename:\s*(\S+)", head, re.I).group(1)
            length = int(re.search(r"Content-Length:\s*(\d+)", head, re.I).group(1))
            self.http = (name, length)
            self.buf = self.buf[end + 4:]
        if self.http is not None:
            name, length = self.http
            if len(self.buf) < length:
                return False
            b.files[name] = self.buf[:length]
            self.buf = self.buf[length:]
            self.http = None
            self.push(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            return True
        if len(self.buf) < 2:
            return False
        w = self.buf[:2]
        if not b.camera_open:
            self.buf = self.buf[2:]
            if w == wifi.CMD_QUERY:
                if b.refuse:
                    self.push(wifi.REPLY_FAIL)
                else:
                    self.push(b"SD:%dKB" % b.free_kb + wifi.REPLY_OK)
            elif w == wifi.CMD_FINISH:
                b.finished += 1
            elif w == wifi.CMD_CAM_START:
                b.camera_open = True
                self.push(wifi.REPLY_CAM_OPEN)
            return True
        # camera mode: [len16][jpeg][0000] frames or stop word
        n = int.from_bytes(w, "big")
        if w == wifi.CMD_CAM_STOP:
            self.buf = self.buf[2:]
            b.camera_open = False
            self.push(wifi.REPLY_CAM_CLOSED)
            return True
        if n == 0 or w == wifi.CMD_SHOT_DONE:
            self.buf = self.buf[2:]
            return True
        if len(self.buf) < 2 + n + 2:
            return False
        b.frames.append(self.buf[2:2 + n])
        self.buf = self.buf[2 + n + 2:]
        return True

    def shutter(self):
        self.push(wifi.REPLY_SHOT)
