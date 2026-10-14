"""Dynamic chunking from the MTU, pacing flags, and the no-ACK to ACK-batch fallback."""
import asyncio
import io
import json
import struct

import pytest
from PIL import Image

from rebeambox import cli, client, link, media, nn20, sim
from rebeambox.session import Nn20Session, ProtocolError


def run(c):
    return asyncio.run(c)


@pytest.mark.parametrize("mtu,p", [(10, 11), (23, 11), (24, 12), (100, 88), (247, 235), (458, 446), (517, 446), (9999, 446)])
def test_data_per_packet_rule(mtu, p):
    assert nn20.data_per_packet(mtu) == p


@pytest.mark.parametrize("mtu", [23, 50, 185, 247, 517])
def test_frames_fit_in_one_att_write(mtu):
    frames = nn20.build_frames(5, bytes(range(256)) * 20, mtu)
    assert all(len(f) <= max(23, mtu) - 3 for f in frames)


def _session(badge, mtu, **kw):
    lk = link.RecordingLink(badge, mtu=mtu)
    s = Nn20Session(lk, guard_scale=0.0, interval=0.0, **kw)
    return lk, s


def test_ack_batch_size_limits_unacknowledged_writes():
    for batch in (1, 2, 4):
        b = sim.SimNn20(time_mode=0)
        lk, s = _session(b, 23, ack_batch=batch)

        async def go():
            await s.start()
            await s.send(5, bytes(300))
        run(go())
        runs, cur = [], 0
        for d, u, _ in lk.events:
            if d == "W" and u == "01f1":
                cur += 1
            elif d == "N" and u == "01f2" and cur:
                runs.append(cur)
                cur = 0
        assert max(runs) <= batch
        assert b.stream().startswith(b'{"type":5,"data":')


def test_session_rejects_bad_pacing():
    lk = link.RecordingLink(sim.SimNn20())
    with pytest.raises(ValueError):
        Nn20Session(lk, ack_batch=0)
    with pytest.raises(ValueError):
        Nn20Session(lk, interval=-1)


def test_cli_pacing_defaults_and_overrides():
    p = cli.build_parser()
    a = p.parse_args(["send-image", "x.jpg"])
    assert (a.packet_interval_ms, a.ack_batch_size) == (20.0, 4)
    a = p.parse_args(["send-image", "x.jpg", "--packet-interval-ms", "5", "--ack-batch-size", "2"])
    assert (a.packet_interval_ms, a.ack_batch_size) == (5.0, 2)


def test_cli_rejects_zero_batch(tmp_path, capsys):
    img = tmp_path / "a.png"
    Image.new("RGB", (40, 40), (9, 9, 9)).save(img)
    rc = cli.main(["send-image", str(img), "--model", "niji", "--dry-run", str(tmp_path / "o.txt"), "--ack-batch-size", "0"])
    assert rc == 1 and "ack-batch-size" in capsys.readouterr().err


def test_cli_dry_run_accepts_pacing(tmp_path):
    img = tmp_path / "a.png"
    Image.new("RGB", (40, 40), (9, 9, 9)).save(img)
    out = tmp_path / "o.txt"
    assert cli.main(["send-image", str(img), "--model", "niji", "--dry-run", str(out), "--packet-interval-ms", "1",
                     "--ack-batch-size", "2", "--quiet"]) == 0
    assert out.exists()


def test_fallback_from_noack_to_ack_on_reported_drop():
    b = sim.SimNn20(time_mode=1, noack_fail_at=5)
    lk, s = _session(b, 100)
    payload = bytes(range(256)) * 12

    async def go():
        await s.start()
        await s.send(5, payload)
    run(go())
    assert s.modes == ["noack", "ack"]
    assert b.stream() == b'{"type":5,"data":' + payload + b"}"


def test_noack_without_drop_stays_noack():
    b = sim.SimNn20(time_mode=1)
    lk, s = _session(b, 100)

    async def go():
        await s.start()
        await s.send(5, bytes(1000))
    run(go())
    assert s.modes == ["noack"]
    assert not [e for e in lk.events if e[0] == "N" and b"GetPacket" in e[2]]


class FlakyLink(link.RecordingLink):
    def __init__(self, badge, fail_on, **kw):
        super().__init__(badge, **kw)
        self.fail_on, self.writes, self.reconnects = fail_on, 0, 0

    async def write(self, uuid, data, response=False):
        self.writes += 1
        if self.writes == self.fail_on:
            raise OSError("link lost")
        await super().write(uuid, data, response)

    async def reconnect(self):
        self.reconnects += 1
        self.badge.time_mode = 0        # after reconnect the simulated badge answers in ACK mode


def test_fallback_after_disconnect_reconnects_and_restarts():
    b = sim.SimNn20(time_mode=1)
    lk = FlakyLink(b, fail_on=4, mtu=100)
    s = Nn20Session(lk, guard_scale=0.0, interval=0.0)
    payload = bytes(range(200)) * 8

    async def go():
        await s.start()
        await s.send(5, payload)
    run(go())
    assert lk.reconnects == 1 and s.modes == ["noack", "ack"]
    assert b.stream() == b'{"type":5,"data":' + payload + b"}"


def test_disconnect_without_reconnect_support_raises():
    b = sim.SimNn20(time_mode=1)
    lk = FlakyLink(b, fail_on=2, mtu=100)

    async def no(self):
        raise NotImplementedError
    lk.reconnect = no.__get__(lk)
    s = Nn20Session(lk, guard_scale=0.0, interval=0.0)

    async def go():
        await s.start()
        await s.send(5, bytes(1000))
    with pytest.raises(ProtocolError):
        run(go())


def _still():
    return client.Job("still", lambda s: ([media.fit_square(Image.new("RGB", (500, 300), (255, 255, 255)), s)], 0))


def test_default_nn20_still_is_one_frame_type5_3000ms():
    t, payload = _still().nn20_payload(360)
    assert t == nn20.TYPE_GIF
    magic, _sz, n, interval = struct.unpack_from("<IIII", payload, 0)
    assert (magic, n, interval) == (0x12345678, 1, 3000)


def test_album_flag_gives_type6_imb():
    j = _still()
    j.still_mode = "album"
    t, payload = j.nn20_payload(360)
    assert t == nn20.TYPE_ALBUM and payload[:4] == b"IMB\x00"


def test_cli_nn20_still_flag_parses():
    a = cli.build_parser().parse_args(["send-image", "x.jpg", "--nn20-still", "album"])
    assert a.nn20_still == "album"


@pytest.mark.parametrize("size_text,expected", [("360,360", 360), ("368,368", 368)])
def test_badge_reported_size_selects_container_size(size_text, expected):
    b = sim.SimNn20(size=size_text)
    lk = link.RecordingLink(b)
    run(client.send(lk, _still(), "nn20", None, lambda *_: None, fast=True))
    env = b.stream()
    payload = env[len(b'{"type":5,"data":'):-1]
    w, h = struct.unpack_from("<hh", payload, 32 + 16 + 12)
    assert (w, h) == (expected, expected)
    jpeg_len = struct.unpack_from("<i", payload, 32 + 16 + 20)[0]
    img = Image.open(io.BytesIO(payload[32 + 16 + 32:32 + 16 + 32 + jpeg_len]))
    assert img.size == (expected, expected)


def test_circular_mask_is_black_in_corners_on_white_image():
    t, payload = _still().nn20_payload(360)
    jl = struct.unpack_from("<i", payload, 32 + 16 + 20)[0]
    img = Image.open(io.BytesIO(payload[32 + 16 + 32:32 + 16 + 32 + jl])).convert("RGB")
    assert sum(img.getpixel((2, 2))) < 40 and sum(img.getpixel((180, 180))) > 700


# values corrected from the app's smali (docs/tasks/results/S2-2026-10-12.md) -------------------------------------------------

def test_free_space_margin_is_one_mib_like_the_app():
    from rebeambox import session
    assert session.FREE_SPACE_MARGIN == 1024 * 1024
    payload = bytes(100 * 1024)
    for free_kb, ok in ((100 + 1024, True), (100 + 1023, False), (100 + 64, False)):      # 64 KiB margin would have accepted the last two
        b = sim.SimNn20(freespace=free_kb)
        lk, s = _session(b, 247)

        async def go():
            await s.start()
            await s.send(5, payload)
        if ok:
            run(go())
        else:
            with pytest.raises(ProtocolError, match="free space"):
                run(go())


def test_ack_mode_gives_up_on_the_third_failure_like_the_app():
    b = sim.SimNn20(time_mode=0, fail_packets={0, 1, 2, 3, 4, 5, 6, 7, 8, 9})
    lk, s = _session(b, 247, ack_batch=1)

    async def go():
        await s.start()
        await s.send(5, bytes(400))
    with pytest.raises(ProtocolError):
        run(go())
