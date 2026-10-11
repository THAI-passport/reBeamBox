"""High level send flows used by the CLI."""
import asyncio

from . import media, nn20, control
from .session import AE00, BadgeSession, Nn20Session, ProtocolError


class Job:
    """Media request. frames_fn(size) -> (list of PIL images, interval_ms); a still has one frame."""

    def __init__(self, kind, frames_fn, name="rebeambox.jpg", quality=90):
        self.kind, self.frames_fn, self.name, self.quality = kind, frames_fn, name, quality

    def badge_payload(self, size):
        frames, interval = self.frames_fn(size)
        if self.kind == "still":
            return media.to_jpeg(frames[0], self.quality), False, self.name
        fps = max(1, min(33, 1000 // max(media.MIN_INTERVAL_MS, interval)))
        return media.frames_to_avi(frames, fps, size, media.MAX_SECONDS), True, self.name.rsplit(".", 1)[0] + ".avi"

    def nn20_payload(self, size=368):
        frames, interval = self.frames_fn(size)
        jpegs = [media.to_jpeg(f, 90) for f in frames]
        if self.kind == "still":
            return nn20.TYPE_ALBUM, nn20.imb(size, size, jpegs[0])
        return nn20.TYPE_GIF, nn20.gif_container(jpegs, interval, size, size)


def detect_transport(link):
    if link.has_service(control.SERVICE) or link.has_service(AE00):
        return "badge"
    if link.has_service(nn20.SERVICE):
        return "nn20"
    raise ProtocolError("no known badge service (C2E6FD00 / 0xAE00 / 0x01F0) on this device")


async def send(link, job, transport=None, size_override=None, log=print, progress=None,
               fast=False, animation_type=1):
    """Send a Job over a connected Link. Returns the exact payload file bytes that were transferred."""
    transport = transport or detect_transport(link)
    log("transport: %s" % transport)
    if transport == "badge":
        s = BadgeSession(link, log, bind_delay=0.0 if fast else 1.55)
        await s.start()
        size = size_override or s.picture_size()
        log("badge picture size %d, memory %s KB" % (size, s.info["memory_kb"] if s.info else "?"))
        data, is_avi, name = job.badge_payload(size)
        await s.send_media(data, is_avi, name, progress)
        return data
    s = Nn20Session(link, log, guard_scale=0.0 if fast else 1.0, interval=0.0 if fast else 0.05)
    await s.start()
    type_, payload = job.nn20_payload(size_override or 368)
    await s.send(type_, payload, animation_type if job.kind != "still" else None, progress)
    return payload
