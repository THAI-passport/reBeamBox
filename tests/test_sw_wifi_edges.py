"""Software test 4 (docs/software-test-v1.md): Wi-Fi framing edge cases against the software Wi-Fi badge."""
import asyncio
import random

import pytest
from PIL import Image

from rebeambox import media, sim, wifi


def run(c):
    return asyncio.run(c)


def noise_image(seed=1, size=360):
    r = random.Random(seed)
    return Image.frombytes("RGB", (size, size), bytes(r.randrange(256) for _ in range(size * size * 3)))


async def _open(badge, name="ctrl"):
    ch = wifi.SimChannel(badge, name)
    await ch.open(None, None)
    return ch


def test_limit_constant_and_exact_limit_frame_header():
    assert wifi.MAX_JPEG == 30720
    f = wifi.camera_frame(b"\xAA" * 30720)
    assert f[:2] == b"\x78\x00" and f[-2:] == b"\x00\x00" and len(f) == 30724


def test_camera_frame_rejects_over_16_bit_length():
    assert wifi.camera_frame(b"\xAA" * 65535)[:2] == b"\xff\xff"
    with pytest.raises(ValueError):
        wifi.camera_frame(b"\xAA" * 65536)


def test_jpeg_under_never_exceeds_limit_for_hard_image():
    b = wifi.jpeg_under(noise_image())
    assert len(b) <= 30720 and media.is_jpeg(b)


def test_jpeg_under_gives_up_with_a_clear_error():
    with pytest.raises(media.MediaError):
        wifi.jpeg_under(noise_image(), limit=100)


def test_oversize_frames_are_dropped_not_sent():
    async def go():
        b = sim.SimWifiBadge()
        s = wifi.WifiSession(lambda n: wifi.SimChannel(b, n), pace=False)
        ok1 = b"\xFF\xD8\xFF" + b"\xAA" * 30717                     # exactly 30720
        too_big = b"\xFF\xD8\xFF" + b"\xAA" * 30718                 # 30721
        ok2 = b"\xFF\xD8\xFF\xD9"
        sent = await s.stream([ok1, too_big, ok2])
        return b, s, sent, ok1, ok2
    b, s, sent, ok1, ok2 = run(go())
    assert sent == 2 and s.dropped == 1 and b.frames == [ok1, ok2] and not b.camera_open


def test_embedded_stop_and_end_words_do_not_split_a_frame():
    async def go():
        b = sim.SimWifiBadge()
        ch = await _open(b)
        await ch.send(wifi.CMD_CAM_START)
        tricky = b"\xFF\xD8" + wifi.CMD_CAM_STOP + wifi.FRAME_END + wifi.CMD_QUERY + wifi.CMD_CAM_STOP + b"\xFF\xD9"
        await ch.send(wifi.camera_frame(tricky))
        await ch.send(wifi.camera_frame(b"\xFF\xD8\xFF\xD9"))
        return b, tricky
    b, tricky = run(go())
    assert b.frames == [tricky, b"\xFF\xD8\xFF\xD9"] and b.camera_open


def test_split_writes_across_length_and_payload_boundaries():
    async def go():
        b = sim.SimWifiBadge()
        ch = await _open(b)
        await ch.send(wifi.CMD_CAM_START)
        frame = wifi.camera_frame(b"\xAA" * 500)
        for i in range(0, len(frame), 7):                         # arbitrary TCP segmentation
            await ch.send(frame[i:i + 7])
        return b
    assert run(go()).frames == [b"\xAA" * 500]


def test_stop_word_between_length_prefixed_frames_ends_camera_mode():
    async def go():
        b = sim.SimWifiBadge()
        ch = await _open(b)
        await ch.send(wifi.CMD_CAM_START)
        await ch.send(wifi.camera_frame(b"\xAA" * 200))
        await ch.send(wifi.CMD_CAM_STOP)
        await ch.send(wifi.camera_frame(b"\xBB" * 200))           # after stop: not a camera frame any more
        return b, ch
    b, ch = run(go())
    assert b.frames == [b"\xAA" * 200] and not b.camera_open
    assert wifi.REPLY_CAM_CLOSED in [e[2] for e in ch.log if e[0] == "N"]


def test_frame_of_127_bytes_is_ambiguous_with_the_stop_word():
    """Documents problem_solution.md entry 37: a 127-byte frame has the length prefix 0x007F. The protocol has no
    type byte, so the simulator treats it as stop. Real firmware behaviour is unknown; JPEGs are never this small."""
    async def go():
        b = sim.SimWifiBadge()
        ch = await _open(b)
        await ch.send(wifi.CMD_CAM_START)
        await ch.send(wifi.camera_frame(b"\xAA" * 127))
        return b
    b = run(go())
    assert not b.camera_open and b.frames == []


def test_shutter_event_is_acknowledged_with_007d_during_stream():
    async def go():
        b = sim.SimWifiBadge()
        chans = []

        def mk(n):
            c = wifi.SimChannel(b, n)
            chans.append(c)
            return c
        s = wifi.WifiSession(mk, pace=False)
        jpeg = b"\xFF\xD8\xFF\xD9"

        def frames():                      # the badge button is pressed between frame 1 and frame 2
            yield jpeg
            chans[0].conn.shutter()
            yield jpeg
            yield jpeg
        await s.stream(frames())
        return s, chans[0]
    s, ch = run(go())
    writes = [e[2] for e in ch.log if e[0] == "W"]
    assert s.shots == 1 and wifi.CMD_SHOT_DONE in writes
