"""Protocol sessions over a Link: BadgeSdk (control channel + Jieli RCSP) and nn20."""
import asyncio
import json
import time

from . import control, jl_auth, nn20, rcsp

FREE_SPACE_MARGIN = 1024 * 1024    # [C] the app refuses when payload + 1 MiB (0x100000 in smali) exceeds the reported free KB * 1024
STATUS_WAIT_S = 2.0                # [H] the Pulse pushes its status JSON shortly after notify is enabled; its time_mode picks no-ACK vs ACK
ACK_ABORT_FAILURES = 3            # [C] the app gives up on the third failure of one upload (two retries, waits 500 and 1000 ms)
AE00 = "0000ae00-0000-1000-8000-00805f9b34fb"
AE01 = "0000ae01-0000-1000-8000-00805f9b34fb"
AE02 = "0000ae02-0000-1000-8000-00805f9b34fb"


class ProtocolError(RuntimeError):
    pass


class RcspError(ProtocolError):
    pass


class RcspSession:
    """Jieli RCSP over service 0xAE00: auth, commands, large file transfer."""

    def __init__(self, link, log=lambda *_: None, key=jl_auth.DEFAULT_KEY):
        self.link, self.log, self.key = link, log, key
        self.authed = False
        self._auth_q = asyncio.Queue()
        self._buf = b""
        self._sn = 0
        self._pending = {}
        self._done = None
        self._file = None

    # --- transport ---
    async def _write(self, data):
        step = max(20, self.link.mtu - 3)
        for i in range(0, len(data), step):
            await self.link.write(AE01, data[i:i + step], response=False)

    def _next_sn(self):
        sn = self._sn
        self._sn = (self._sn + 1) & 0xFF
        return sn

    def _on_notify(self, data):
        if not self.authed:
            self._auth_q.put_nowait(data)
            return
        self._buf += data
        while True:
            f, self._buf = rcsp.unpack(self._buf)
            if f is None:
                break
            self._dispatch(f)

    def _dispatch(self, f):
        if f["command"]:
            asyncio.ensure_future(self._on_device_command(f))
        else:
            fut = self._pending.pop((f["opcode"], f["sn"]), None)
            if fut and not fut.done():
                fut.set_result(f)

    # --- auth (docs/PROTOCOL.md 3.7.1) ---
    async def open(self, auth_timeout=5.0):
        await self.link.subscribe(AE02, self._on_notify)
        await self._auth(auth_timeout)

    async def _expect(self, pred, timeout):
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise ProtocolError("auth timeout")
            data = await asyncio.wait_for(self._auth_q.get(), left)
            if pred(data):
                return data

    async def _auth(self, timeout):
        rnd = jl_auth.random_challenge()
        await self.link.write(AE01, jl_auth.AUTH_RESET, response=False)
        await asyncio.sleep(0.05)
        await self.link.write(AE01, rnd, response=False)
        ans = await self._expect(lambda d: len(d) == 17 and d[0] == 1, timeout)
        if ans != jl_auth.encrypt_challenge(rnd, self.key):
            raise ProtocolError("badge answer to our auth challenge is wrong")
        await self.link.write(AE01, jl_auth.AUTH_OK, response=False)
        dev = await self._expect(lambda d: len(d) == 17 and d[0] == 0, timeout)
        await self.link.write(AE01, jl_auth.encrypt_challenge(dev, self.key), response=False)
        await self._expect(lambda d: d[:5] == jl_auth.AUTH_OK, timeout)
        self.authed = True
        self.log("rcsp auth ok")

    # --- commands ---
    async def call(self, opcode, payload=b"", timeout=5.0):
        sn = self._next_sn()
        fut = asyncio.get_running_loop().create_future()
        self._pending[(opcode, sn)] = fut
        await self._write(rcsp.pack(opcode, payload, want_response=True, sn=sn))
        try:
            f = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop((opcode, sn), None)
            raise RcspError("timeout waiting for opcode 0x%02X" % opcode)
        if f["status"] != 0:
            raise RcspError("opcode 0x%02X failed with status %d" % (opcode, f["status"]))
        return f["payload"]

    async def _respond(self, f, payload=b"", status=0):
        await self._write(rcsp.pack(f["opcode"], payload, command=False, status=status, sn=f["sn"]))

    async def _on_device_command(self, f):
        try:
            op = f["opcode"]
            if self._file is None:
                self.log("ignoring device command 0x%02X outside a transfer" % op)
                return
            st = self._file
            if op == rcsp.OP_LARGE_OP:
                offset, size = rcsp.parse_read_request(f["payload"])
                if (offset, f["sn"]) == st["last"]:
                    return
                st["last"] = (offset, f["sn"])
                st["progress"] = time.monotonic()
                st["offset"] = offset
                frames = rcsp.data_chunks(st["data"], offset, size, st["mtu"], st["crc"], self._sn)
                self._sn = (self._sn + len(frames)) & 0xFF
                for fr in frames:
                    await self._write(fr)
                st["progress"] = time.monotonic()
                if st["cb"]:
                    st["cb"](min(100, 100 * (offset + size) // max(1, len(st["data"]))))
            elif op == rcsp.OP_GET_NAME:
                limit = 32 if len(st["name"]) > 9 else 9
                status = 1 if st["retry"] >= limit else 0
                await self._respond(f, rcsp.get_name_response_payload(st["name"], st["retry"]), status)
                st["retry"] += 1
            elif op == rcsp.OP_STOP_LARGE:
                reason = f["payload"][0] if f["payload"] else 0
                await self._respond(f)
                if not st["done"].done():
                    st["done"].set_result(reason)
            elif op == rcsp.OP_CANCEL_LARGE:
                await self._respond(f)
                if not st["done"].done():
                    st["done"].set_exception(RcspError("badge cancelled the transfer"))
            else:
                self.log("unhandled device command 0x%02X" % op)
        except Exception as e:                     # never let a callback task die silently
            st = self._file
            if st and not st["done"].done():
                st["done"].set_exception(e)

    async def send_file(self, data, name, mtime_ms=None, progress=None, watchdog=20.0):
        """RCSP large file transfer (docs/PROTOCOL.md 3.7)."""
        if not self.authed:
            raise ProtocolError("not authenticated")
        info = rcsp.parse_target_info(await self.call(rcsp.OP_GET_TARGET_INFO, b"\xFF\xFF\xFF\xFF\x00"))
        sysinfo = rcsp.parse_sys_info(await self.call(rcsp.OP_GET_SYS_INFO, b"\xFF\x00\x00\x00\x04"))
        target = rcsp.pick_storage(rcsp.parse_storage(sysinfo.get(2, b"")))
        if target is None:
            raise ProtocolError("badge reports no online storage")
        self.log("storage %s handle 0x%08X, badge mtu %d, crc16 %s" % (target["name"], target["handle"], info["mtu"], info["crc16"]))
        await self.call(rcsp.OP_PREPARE_ENV, b"\x00")
        pkt_crc = False
        if info["crc16"]:
            import struct
            r = await self.call(rcsp.OP_DEVICE_EXTEND, struct.pack(">BIB", 0, target["handle"], 1))
            pkt_crc = len(r) >= 2 and r[1] == 1
        import struct
        path = rcsp.temp_name_payload(name, mtime_ms if mtime_ms is not None else int(time.time() * 1000))
        loop = asyncio.get_running_loop()
        self._file = {"data": data, "mtu": 265, "crc": pkt_crc, "last": None, "retry": 0, "name": name,
                      "done": loop.create_future(), "progress": time.monotonic(), "cb": progress}
        try:
            resp = await self.call(rcsp.OP_START_LARGE, struct.pack(">IH", len(data), rcsp.crc16_xmodem(data)) + path)
            mtu = rcsp.parse_start_response(resp) if len(resp) >= 2 else 265
            if mtu <= 0:
                raise RcspError("badge returned transfer mtu 0")
            self._file["mtu"] = mtu
            st = self._file
            while not st["done"].done():
                if time.monotonic() - st["progress"] > watchdog:
                    await self._write(rcsp.pack(rcsp.OP_CANCEL_LARGE, b"", want_response=True, sn=self._next_sn()))
                    raise RcspError("no progress for %d s" % watchdog)
                await asyncio.sleep(0.02)
            reason = st["done"].result()
            if reason != 0:
                raise RcspError("transfer stopped with reason %d" % reason)
            if progress:
                progress(100)
        finally:
            self._file = None


class BadgeSession:
    """BadgeSdk path: 0x9E control channel, then RCSP for the file."""

    def __init__(self, link, log=lambda *_: None, bind_delay=1.55, device_seed=None, twelve_hour=False):
        self.link, self.log = link, log
        self.bind_delay, self.dev_id, self.twelve = bind_delay, control.device_id(device_seed), twelve_hour
        self._buf = b""
        self._wait = {}
        self._seq = 0
        self.bind = self.info = self.picsize = None
        self.rcsp = RcspSession(link, log)

    def _on_ctl(self, data):
        self._buf += data
        frames, self._buf = control.parse_stream(self._buf)
        for f in frames:
            if f["wants_ack"] and f["cmd"] != control.CMD_GENERIC:
                asyncio.ensure_future(self._send(control.ack_frame(f["cmd"])))
            key = f["cmd"]
            if key == control.CMD_GENERIC and len(f["payload"]) >= 2:
                key = ("ack", f["payload"][0])
            fut = self._wait.pop(key, None)
            if fut and not fut.done():
                fut.set_result(f)

    async def _send(self, frame_bytes):
        step = max(14, self.link.mtu - 6)
        for i in range(0, len(frame_bytes), step):
            await self.link.write(control.WRITE, frame_bytes[i:i + step], response=False)
            if i + step < len(frame_bytes):
                await asyncio.sleep(0.005)

    def _next_seq(self):
        s = self._seq
        self._seq = (self._seq + 1) & 0x0F
        return s

    async def request(self, cmd, payload, reply, timeout=5.0):
        fut = asyncio.get_running_loop().create_future()
        self._wait[reply] = fut
        await self._send(control.frame(cmd, payload, self._next_seq()))
        try:
            return (await asyncio.wait_for(fut, timeout))["payload"]
        except asyncio.TimeoutError:
            self._wait.pop(reply, None)
            raise ProtocolError("timeout waiting for control reply 0x%02X" % (reply if isinstance(reply, int) else reply[1]))

    async def start(self):
        await self.link.subscribe(control.NOTIFY1, self._on_ctl)
        await self.link.subscribe(control.NOTIFY2, self._on_ctl)
        await asyncio.sleep(self.bind_delay)
        self.bind = control.parse_bind_reply(await self.request(
            control.CMD_BIND, control.bind_payload(self.dev_id, self.twelve), control.CMD_BIND_REPLY))
        if not self.bind["ok"]:
            raise ProtocolError("bind refused, state %d (press the badge Bluetooth button and retry)" % self.bind["state"])
        await self._send(control.frame(control.CMD_TIME, control.time_payload(), self._next_seq()))
        self.info = control.parse_info_reply(await self.request(control.CMD_INFO, b"\x01", control.CMD_INFO_REPLY))
        try:
            self.picsize = control.parse_picsize_reply(await self.request(control.CMD_PICSIZE, b"", control.CMD_PICSIZE_REPLY, 3.0))
        except ProtocolError:
            self.picsize = None
        if not self.link.has_service(AE00):
            raise ProtocolError("badge does not expose the Jieli service 0xAE00 on this connection")
        await self.rcsp.open()

    def picture_size(self, default=360):
        if self.info and all(self.info["picture"]):
            return self.info["picture"][0] if self.info["picture"][0] == self.info["picture"][1] else min(self.info["picture"])
        if self.picsize and all(self.picsize["preview"]):
            return min(self.picsize["preview"])
        return default

    async def send_media(self, data, is_avi, name, progress=None):
        if self.info and len(data) > self.info["memory_kb"] * 1024:
            raise ProtocolError("file %d bytes exceeds badge memory %d KB" % (len(data), self.info["memory_kb"]))
        if is_avi:                                       # stills skip the handshake (app behaviour)
            await self.request(control.CMD_FILETYPE, bytes([control.FILETYPE_BADGE_MEDIA]), ("ack", control.CMD_FILETYPE))
        await self.rcsp.send_file(data, name, progress=progress)


class Nn20Session:
    """nn20 path: service 0x01F0.

    Packet size comes from the negotiated MTU (P = min(446, mtu - 12), ATT minimum 23). `interval` is the gap in
    seconds between packets, `ack_batch` the largest ACK batch. When the badge reports time_mode 1 the stream is sent
    without per-batch ACKs; on a GetPacketFail or a write error (drop or disconnect) the session falls back to ACK
    batches and restarts the transfer from the first packet (the first packet of a stream starts a new upload)."""

    def __init__(self, link, log=lambda *_: None, guard_scale=1.0, interval=0.02, ack_batch=4):
        if interval < 0 or ack_batch < 1:
            raise ValueError("interval must be >= 0 and ack_batch >= 1")
        self.link, self.log, self.guard_scale, self.interval = link, log, guard_scale, interval
        self.ack_batch = ack_batch
        self.status = {}
        self.status_log = []        # every status JSON the badge pushed, in order (free space before and after a write)
        self.modes = []             # trace of the modes used, for logs and tests
        self._buf = b""
        self._acks = asyncio.Queue()

    def _on_notify(self, data):
        self._buf += data
        msgs, self._buf = nn20.parse_reply_stream(self._buf)
        for _t, text in msgs:
            if "GetPacketSuccess" in text:
                self._acks.put_nowait("ok")
                self.log("badge reply: GetPacketSuccess")
            elif "GetPacketFail" in text:
                self._acks.put_nowait("fail")
            elif len(text) > 30:
                try:
                    self.status = json.loads(text)
                except ValueError:
                    continue
                self.status_log.append(dict(self.status))
                self.log("badge status: size=%s freespace=%s KB allspace=%s KB time_mode=%s" % (
                    self.status.get("size"), self.status.get("freespace"), self.status.get("allspace"), self.status.get("time_mode")))

    async def start(self):
        await self.link.subscribe(nn20.NOTIFY, self._on_notify)
        await asyncio.sleep(0.05)
        end = asyncio.get_running_loop().time() + STATUS_WAIT_S
        while not self.status and asyncio.get_running_loop().time() < end:
            await asyncio.sleep(0.05)
        if not self.status:
            self.log("no status JSON within %.1f s: time_mode unknown, using ACK mode" % STATUS_WAIT_S)
        self.log("MTU %d, %d data bytes per packet" % (self.link.mtu, nn20.data_per_packet(self.link.mtu)))

    async def _wr(self, f):
        await self.link.write(nn20.WRITE, f, response=False)

    async def send(self, type_, payload, animation_type=None, progress=None):
        free = self.status.get("freespace")
        if free is not None and len(payload) + FREE_SPACE_MARGIN > int(free) * 1024:
            raise ProtocolError("not enough free space on badge (%s KB)" % free)
        if animation_type is not None:
            await self._wr(nn20.settings_frame({"animation_type": animation_type}))
            await asyncio.sleep(0.2 * self.guard_scale)
        frames = nn20.build_frames(type_, payload, self.link.mtu)
        n = len(frames)
        if int(self.status.get("time_mode", 0)) == 1:
            self.modes.append("noack")
            if not await self._send_noack(frames, progress):
                self.log("drop or disconnect in no-ACK mode: falling back to ACK batches of up to %d" % self.ack_batch)
                self.modes.append("ack")
                await self._send_acked(frames, progress)
        else:
            self.modes.append("ack")
            await self._send_acked(frames, progress)
        await asyncio.sleep(nn20.guard_time_ms(n) / 1000 * self.guard_scale)

    def _saw_fail(self):
        failed = False
        while not self._acks.empty():
            if self._acks.get_nowait() == "fail":
                failed = True
        return failed

    async def _recover(self, err):
        try:
            await self.link.reconnect()
        except NotImplementedError:
            raise ProtocolError("link lost (%s) and cannot reconnect" % err)
        self._buf = b""
        await self.start()

    async def _send_noack(self, frames, progress):
        """Returns True when every packet was written without a reported drop."""
        n = len(frames)
        for i, f in enumerate(frames):
            try:
                await self._wr(f)
            except Exception as e:
                self.log("write failed at packet %d: %s" % (i, e))
                await self._recover(e)
                return False
            await asyncio.sleep(self.interval)
            await asyncio.sleep(0)
            if self._saw_fail():
                return False
            if progress:
                progress(100 * (i + 1) // n)
        return True

    async def _send_acked(self, frames, progress):
        n, i, batch, retries = len(frames), 0, self.ack_batch, 0
        while i < n:
            part = frames[i:i + batch]
            while not self._acks.empty():
                self._acks.get_nowait()
            for f in part:
                try:
                    await self._wr(f)
                except Exception as e:
                    self.log("write failed at packet %d: %s" % (i, e))
                    retries += 1
                    if retries >= ACK_ABORT_FAILURES:
                        raise ProtocolError("link lost while sending packet %d" % i)
                    await self._recover(e)
                    i = 0           # the badge lost its place: start the stream again
                    break
                await asyncio.sleep(self.interval)
            else:
                good = 0
                failed = False
                for _ in part:
                    try:
                        r = await asyncio.wait_for(self._acks.get(), self.interval * len(part) + 2.5)
                    except asyncio.TimeoutError:
                        failed = True
                        break
                    if r == "ok":
                        good += 1
                    else:
                        failed = True
                        break
                i += good
                if failed:
                    retries += 1
                    if retries >= ACK_ABORT_FAILURES:
                        raise ProtocolError("badge did not acknowledge packet %d" % i)
                    batch = 1
                    await asyncio.sleep(min(0.5 * 2 ** (retries - 1), 2.0))
                elif batch < self.ack_batch:
                    batch = min(self.ack_batch, batch * 2)
                if progress:
                    progress(100 * i // n)
                continue
            batch = 1               # after a reconnect resend the same packets one at a time
