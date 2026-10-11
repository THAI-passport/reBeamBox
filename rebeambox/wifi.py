"""Wi-Fi transport: the badge runs an access point (192.168.8.1). TCP 8080 carries 2-byte control words,
the live camera frame stream, and a minimal HTTP POST /upload for container files. See docs/wifi-protocol.md.
Joining the access point is the operating system's job (nmcli, networksetup, netsh); this module only opens sockets."""
import asyncio
import random
import re

from . import media

HOST = "192.168.8.1"
PORT = 8080
SSID_HINT = "E-Badge"          # app default; the server product list can override (signal name)

CMD_QUERY = b"\x00\x69"        # ask free space / start an upload session
CMD_FINISH = b"\x00\x5f"       # sent after an upload, then the app closes the socket
CMD_CAM_START = b"\x00\x79"
CMD_SHOT_DONE = b"\x00\x7d"    # phone saved a photo after a shutter event
CMD_CAM_STOP = b"\x00\x7f"
FRAME_END = b"\x00\x00"
REPLY_OK = b"\x00\x6a"
REPLY_FAIL = b"\x00\x6b"
REPLY_CAM_OPEN = b"\x00\x7b"
REPLY_SHOT = b"\x00\x7a"
REPLY_CAM_CLOSED = b"\x00\x7f"

CHUNK = 6144
MAX_JPEG = 30720
MIN_FRAME_INTERVAL = 0.3       # the app drops frames closer than 300 ms (<= 3.3 fps)
WIFI_SIZE = 360


def build_post(host, filename, length):
    if not filename.endswith(".bin"):
        filename += ".bin"
    return ("POST /upload HTTP/1.1\r\nHost: %s\r\nX-Filename: %s\r\nContent-Type: application/octet-stream\r\n"
            "Content-Length: %d\r\nConnection: keep-alive\r\n\r\n" % (host, filename, length)).encode("utf-8")


def pace_for(remaining):
    """Per-chunk sleep in seconds, from the number of bytes still to send."""
    return 0.003 if remaining > 102400 else 0.002 if remaining > 51200 else 0.001


def parse_free_kb(reply):
    """Reply to CMD_QUERY: ASCII 'SD:<n>KB' followed by two code bytes. Returns KB or None."""
    text = bytes(reply).decode("latin-1")
    m = re.search(r"SD:\s*(\d+)\s*kb", text, re.I)
    return int(m.group(1)) if m else None


MIN_JPEG = 256     # lengths below 256 have a zero high byte, the same shape as the control words (0x0069 ... 0x007F)


def pad_jpeg(jpeg, minimum=MIN_JPEG):
    """Insert a JPEG comment segment after SOI so a frame is at least `minimum` bytes. The length prefix of a smaller
    frame would look like a control word (docs/wifi-protocol.md 5.1). Real 360x360 frames are far larger."""
    if len(jpeg) >= minimum:
        return jpeg
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    need = max(4, minimum - len(jpeg))
    return jpeg[:2] + b"\xff\xfe" + (need - 2).to_bytes(2, "big") + bytes(need - 4) + jpeg[2:]


def camera_frame(jpeg):
    if len(jpeg) > 0xFFFF:
        raise ValueError("frame too large")
    return len(jpeg).to_bytes(2, "big") + jpeg + FRAME_END


def jpeg_under(img, limit=MAX_JPEG):
    """Encode a PIL image as JPEG at the highest quality that fits the badge frame limit."""
    for q in (60, 50, 40, 30, 20, 15, 10, 7, 5):
        b = media.to_jpeg(img, q)
        if len(b) <= limit:
            return b
    raise media.MediaError("cannot fit frame into %d bytes" % limit)


def file_name():
    return "%02d.bin" % random.randint(0, 99)


class WifiError(RuntimeError):
    pass


class Channel:
    async def open(self, host, port):
        raise NotImplementedError

    async def send(self, data):
        raise NotImplementedError

    async def recv(self, timeout):
        raise NotImplementedError

    async def close(self):
        pass


class TcpChannel(Channel):
    async def open(self, host, port, timeout=10.0):
        try:
            self.r, self.w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except (OSError, asyncio.TimeoutError) as e:
            raise WifiError("cannot connect to %s:%d (%s). Join the badge Wi-Fi access point first." % (host, port, e))
        return self

    async def send(self, data):
        self.w.write(data)
        await self.w.drain()

    async def recv(self, timeout):
        try:
            return await asyncio.wait_for(self.r.read(4096), timeout)
        except asyncio.TimeoutError:
            return b""

    async def close(self):
        self.w.close()
        try:
            await self.w.wait_closed()
        except Exception:
            pass


class SimChannel(Channel):
    """In-process channel to a software badge; records every write (W) and reply (N) when `log` is a list."""

    def __init__(self, badge, name="ctrl", log=None):
        self.badge, self.name, self.log = badge, name, log if log is not None else []
        self._q = asyncio.Queue()

    async def open(self, host, port):
        self.conn = self.badge.new_conn(self._push)
        return self

    def _push(self, data):
        self.log.append(("N", self.name, bytes(data)))
        self._q.put_nowait(bytes(data))

    async def send(self, data):
        self.log.append(("W", self.name, bytes(data)))
        self.conn.feed(bytes(data))

    async def recv(self, timeout):
        try:
            return await asyncio.wait_for(self._q.get(), timeout)
        except asyncio.TimeoutError:
            return b""


class WifiSession:
    def __init__(self, open_channel, host=HOST, port=PORT, log=lambda *_: None, pace=True):
        """open_channel(name) -> Channel (not yet opened)."""
        self._mk, self.host, self.port, self.log, self.pace = open_channel, host, port, log, pace
        self.shots = 0
        self.dropped = 0

    async def _open(self, name):
        ch = self._mk(name)
        await ch.open(self.host, self.port)
        return ch

    async def send_file(self, data, name=None, progress=None):
        name = name or file_name()
        ctrl = await self._open("ctrl")
        try:
            await ctrl.send(CMD_QUERY)
            reply = await ctrl.recv(5.0)
            if reply == REPLY_FAIL or not reply:
                raise WifiError("badge refused or ignored the upload query")
            free = parse_free_kb(reply)
            self.log("badge free space: %s KB" % free)
            if free is not None and len(data) > free * 1024:
                raise WifiError("file %d bytes does not fit in %d KB" % (len(data), free))
            up = await self._open("upload")
            try:
                await up.send(build_post(self.host, name, len(data)))
                await asyncio.sleep(0.01 if self.pace else 0)
                sent = 0
                while sent < len(data):
                    n = min(CHUNK, len(data) - sent)
                    await up.send(data[sent:sent + n])
                    sent += n
                    if self.pace:
                        await asyncio.sleep(pace_for(len(data) - sent))
                    if progress:
                        progress(100 * sent // len(data))
                resp = await up.recv(3.0)
                if resp and not re.search(rb"200|204|OK", resp):
                    raise WifiError("badge answered: %s" % resp.split(b"\r\n")[0].decode("latin-1"))
            finally:
                await up.close()
            await ctrl.send(CMD_FINISH)
        finally:
            await ctrl.close()

    async def stream(self, frames, fps=2.0, progress=None):
        """frames: iterable of JPEG bytes (each <= 30720). fps is clamped to the app's 300 ms spacing."""
        interval = max(MIN_FRAME_INTERVAL, 1.0 / fps)
        ctrl = await self._open("ctrl")
        try:
            await ctrl.send(CMD_CAM_START)
            if (await ctrl.recv(5.0)) != REPLY_CAM_OPEN:
                raise WifiError("badge did not confirm camera mode (expected 007B)")
            n = 0
            for jpeg in frames:
                if len(jpeg) > MAX_JPEG:       # the app only warns; the client drops (badge buffer limit is probably 30 KB)
                    self.dropped += 1
                    self.log("dropped frame of %d bytes (limit %d)" % (len(jpeg), MAX_JPEG))
                    continue
                if len(jpeg) < MIN_JPEG:
                    jpeg = pad_jpeg(jpeg)
                await ctrl.send(camera_frame(jpeg))
                n += 1
                if progress:
                    progress(n)
                r = await ctrl.recv(interval if self.pace else 0.001)
                if REPLY_SHOT in r:
                    self.shots += 1
                    self.log("badge shutter event")
                    await ctrl.send(CMD_SHOT_DONE)
                if REPLY_CAM_CLOSED in r:
                    self.log("badge closed camera mode")
                    return n
            await ctrl.send(CMD_CAM_STOP + FRAME_END)
            await ctrl.recv(2.0 if self.pace else 0.001)
            return n
        finally:
            await ctrl.close()
