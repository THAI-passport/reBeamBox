"""Streaming prototype: frame source -> crop and resize -> JPEG encode -> rate control -> Wi-Fi or BLE sink.

Two sinks, because the badge has two very different paths (docs/streaming-plan.md):
- WifiSink: the camera mode of the Wi-Fi path, one JPEG per frame, at most about 3.3 frames per second, 30720 bytes per frame.
- BleSegmentSink: there is no live mode over BLE, so frames are collected into short clips (type 5 container or AVI) and each
  clip is a normal upload that writes flash. The safe-write gate therefore limits how often a clip may be sent.
Everything runs against the software badges with a virtual clock (instant, deterministic) or against hardware with the real clock.
"""
import asyncio
import math
import random
import time

from PIL import Image, ImageDraw

from . import client, media, safewrite, wifi


# --- clocks and link models ------------------------------------------------------------------------------------------

class RealClock:
    def now(self):
        return time.monotonic()

    async def sleep(self, dt):
        if dt > 0:
            await asyncio.sleep(dt)


class VirtualClock:
    """Time that advances only when something sleeps: runs a 30 s stream in milliseconds."""

    def __init__(self, t=0.0):
        self.t = t

    def now(self):
        return self.t

    async def sleep(self, dt):
        self.t += max(0.0, dt)


class LinkModel:
    """Transfer time model used only with the virtual clock. The numbers are assumptions (docs/streaming-plan.md appendix)."""

    def __init__(self, bytes_per_s, per_message_s, name):
        self.bytes_per_s, self.per_message_s, self.name = float(bytes_per_s), float(per_message_s), name

    def seconds(self, n_bytes):
        return self.per_message_s + n_bytes / self.bytes_per_s


WIFI_MODEL = LinkModel(150_000, 0.015, "wifi (assumed 150 KB/s, 15 ms per frame)")
BLE_MODEL = LinkModel(22_000, 3.0, "ble (assumed 22 KB/s from 446 bytes per 20 ms, 3 s connect and handshake)")


# --- sources ---------------------------------------------------------------------------------------------------------

class SyntheticSource:
    """Deterministic moving test pattern. `detail` 0..1 adds noise (bigger JPEGs)."""

    def __init__(self, size=480, fps=10.0, seconds=3.0, detail=0.3, seed=1):
        self.size, self.fps, self.seconds, self.detail, self.seed = size, float(fps), float(seconds), detail, seed

    def frames(self):
        rnd = random.Random(self.seed)
        n = int(round(self.seconds * self.fps))
        noise_px = int(self.detail * self.size * self.size / 20)
        for i in range(n):
            im = Image.new("RGB", (self.size, self.size), (20 + (i * 7) % 60, 30, 90))
            d = ImageDraw.Draw(im)
            ang = 2 * math.pi * i / max(1, n)
            cx, cy = self.size / 2 + 0.3 * self.size * math.cos(ang), self.size / 2 + 0.3 * self.size * math.sin(ang)
            r = self.size * 0.12
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(240, 200, 40))
            d.rectangle((0, self.size - 30, self.size * (i + 1) // n, self.size), fill=(40, 200, 120))
            for _ in range(noise_px):
                d.point((rnd.randrange(self.size), rnd.randrange(self.size)), fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
            yield i / self.fps, im


class ImageListSource:
    """Frames already in memory with a constant rate, or explicit timestamps."""

    def __init__(self, images, fps=10.0, times=None):
        self.images, self.fps, self.times = list(images), float(fps), times

    def frames(self):
        for i, im in enumerate(self.images):
            yield (self.times[i] if self.times else i / self.fps), im


def gif_source(path, max_seconds=None):
    from PIL import ImageSequence
    images, times, t = [], [], 0.0
    with Image.open(path) as im:
        for fr in ImageSequence.Iterator(im):
            images.append(fr.copy().convert("RGBA"))
            times.append(t)
            t += (int(fr.info.get("duration", 100)) or 100) / 1000.0
            if max_seconds and t >= max_seconds:
                break
    return ImageListSource(images, times=times)


def video_source(path, fps=10.0, max_seconds=10.0):
    if not media.have_ffmpeg():
        raise media.MediaError("ffmpeg not found; install it to stream a video (see README)")
    frames = media.load_video_frames(path, 480, False, max(1, round(fps)), max_seconds)
    return ImageListSource(frames, fps=max(1, round(fps)))


def open_source(spec, fps=10.0, max_seconds=10.0):
    if spec == "synthetic" or spec.startswith("synthetic:"):
        return SyntheticSource(fps=fps, seconds=max_seconds)
    if spec.lower().endswith(".gif"):
        return gif_source(spec, max_seconds)
    return video_source(spec, fps, max_seconds)


# --- encode and rate control -----------------------------------------------------------------------------------------

QUALITIES = (75, 70, 60, 50, 40, 30, 20, 15, 10, 7, 5)


class QualityController:
    """Starts at 50, steps up when frames come out well under the limit and down after a frame that did not fit."""

    def __init__(self, limit, start=50, top=75):
        self.limit, self.q, self.top = limit, start, top

    def encode(self, img):
        """Returns (jpeg bytes, quality) with len <= limit, or (None, quality) if even the lowest quality is too big."""
        for q in [x for x in QUALITIES if x <= self.q] or [QUALITIES[-1]]:
            b = media.to_jpeg(img, q)
            if len(b) <= self.limit:
                if len(b) < 0.6 * self.limit:
                    self.q = min(self.top, next((x for x in reversed(QUALITIES) if x > self.q), self.q))
                else:
                    self.q = q
                return b, q
        self.q = QUALITIES[-1]
        return None, self.q


class Stats:
    def __init__(self):
        self.frames_in = 0
        self.sent = 0
        self.dropped_rate = 0         # arrived before the next send was allowed
        self.dropped_late = 0         # stale by the time the sink was free (keep-latest)
        self.dropped_oversize = 0     # could not be encoded under the byte limit
        self.dropped_policy = 0       # refused by the safe-write gate (BLE clips)
        self.uploads = 0              # BLE clips written
        self.bytes = 0
        self.qualities = []
        self.send_seconds = []
        self.first = None
        self.last = None
        self.elapsed = 0.0           # whole run, including time spent waiting

    def fps(self):
        if self.sent < 2 or self.last is None or self.last <= self.first:
            return 0.0
        return (self.sent - 1) / (self.last - self.first)

    def summary(self):
        avg = (self.bytes / self.sent) if self.sent else 0
        return ("frames in %d, sent %d (%.2f fps), dropped: rate %d, late %d, oversize %d, policy %d; "
                "uploads %d; bytes %d (avg %.0f per frame); mean quality %.0f; delivered %.2f frames/s over %.1f s" %
                (self.frames_in, self.sent, self.fps(), self.dropped_rate, self.dropped_late, self.dropped_oversize,
                 self.dropped_policy, self.uploads, self.bytes, avg,
                 (sum(self.qualities) / len(self.qualities)) if self.qualities else 0,
                 (self.sent / self.elapsed) if self.elapsed > 0 else 0.0, self.elapsed))


# --- sinks -----------------------------------------------------------------------------------------------------------

class WifiSink:
    min_interval = wifi.MIN_FRAME_INTERVAL
    max_bytes = wifi.MAX_JPEG
    size = wifi.WIFI_SIZE

    def __init__(self, live, clock, model=None):
        self.live, self.clock, self.model = live, clock, model
        self.sent_jpegs = []

    async def start(self):
        await self.live.start()

    async def send(self, jpeg, img, stats):
        t0 = self.clock.now()
        state = await self.live.send(jpeg, 0.001)
        if self.model:
            await self.clock.sleep(self.model.seconds(len(jpeg)))
        if state == "dropped":
            stats.dropped_oversize += 1
            return False
        stats.sent += 1
        stats.bytes += len(jpeg)
        self.sent_jpegs.append(jpeg)
        stats.send_seconds.append(self.clock.now() - t0)
        return state != "closed"

    async def finish(self, stats):
        try:
            await self.live.stop()
        finally:
            await self.live.close()


class BleSegmentSink:
    """Collects frames into clips. `uploader(images, interval_ms)` performs one real or simulated upload."""
    min_interval = 0.0
    max_bytes = 20_000
    size = 368

    def __init__(self, uploader, clock, segment_frames=6, frame_interval_ms=500, model=None, size=368):
        if segment_frames < 1:
            raise ValueError("segment_frames must be at least 1")
        self.uploader, self.clock, self.segment_frames = uploader, clock, segment_frames
        self.interval_ms, self.model, self.size = frame_interval_ms, model, size
        self.pending = []
        self.payloads = []

    async def start(self):
        return None

    async def send(self, jpeg, img, stats):
        self.pending.append((jpeg, img))
        stats.sent += 1
        stats.bytes += len(jpeg)
        if len(self.pending) >= self.segment_frames:
            await self._flush(stats)
        return True

    async def _flush(self, stats):
        batch, self.pending = self.pending, []
        n_bytes = sum(len(j) for j, _ in batch)
        t0 = self.clock.now()
        try:
            payload = await self.uploader([im for _, im in batch], self.interval_ms)
            if payload is not None:
                self.payloads.append(payload)
        except (safewrite.Blocked, safewrite.Skipped):
            stats.sent -= len(batch)
            stats.bytes -= n_bytes
            stats.dropped_policy += len(batch)
            return
        if self.model:
            await self.clock.sleep(self.model.seconds(n_bytes))
        stats.uploads += 1
        stats.send_seconds.append(self.clock.now() - t0)

    async def finish(self, stats):
        if self.pending:
            await self._flush(stats)


# --- pipeline --------------------------------------------------------------------------------------------------------

class Pipeline:
    def __init__(self, source, sink, fps=2.0, circular=True, clock=None, max_lag=None, controller=None):
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.source, self.sink, self.fps, self.circular = source, sink, float(fps), circular
        self.clock = clock or RealClock()
        self.period = max(1.0 / self.fps, sink.min_interval)
        self.max_lag = max_lag if max_lag is not None else 2.0 * self.period
        self.controller = controller or QualityController(sink.max_bytes)
        self.stats = Stats()

    async def run(self):
        st = self.stats
        start = self.clock.now()
        next_ok = start
        await self.sink.start()
        try:
            for t, img in self.source.frames():
                due = start + t
                if due > self.clock.now():
                    await self.clock.sleep(due - self.clock.now())
                st.frames_in += 1
                now = self.clock.now()
                if now - due > self.max_lag:
                    st.dropped_late += 1          # keep-latest: a frame that waited too long is not worth sending
                    continue
                if now + 1e-6 < next_ok:
                    st.dropped_rate += 1
                    continue
                prepared = media.fit_square(img, self.sink.size, self.circular)
                jpeg, q = self.controller.encode(prepared)
                if jpeg is None:
                    st.dropped_oversize += 1
                    continue
                st.qualities.append(q)
                t0 = self.clock.now()
                st.first = st.first if st.first is not None else t0
                ok = await self.sink.send(jpeg, prepared, st)
                st.last = self.clock.now()
                next_ok = max(t0 + self.period, st.last)
                if not ok:
                    break
        finally:
            await self.sink.finish(st)
            st.elapsed = self.clock.now() - start
        return st


# --- BLE clip uploader -----------------------------------------------------------------------------------------------

def clip_uploader(open_link, transport, size, gate=None, log=lambda m: None, fast=False):
    """Returns an async function (images, interval_ms) -> payload bytes that sends one clip as a normal upload."""
    async def upload(images, interval_ms):
        job = client.Job("gif", lambda s: (images, interval_ms), name="stream.gif")
        lk = await open_link()
        try:
            return await client.send(lk, job, transport, size, log, fast=fast, gate=gate)
        finally:
            await lk.close()
    return upload
