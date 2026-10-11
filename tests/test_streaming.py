"""Streaming prototype: sources, quality control, rate control, Wi-Fi and BLE sinks, CLI, benchmark tool."""
import asyncio
import io
import os
import sys

import pytest
from PIL import Image

from rebeambox import cli, link, safewrite, sim, streaming, wifi

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import bench_stream  # noqa: E402


def run(c):
    return asyncio.run(c)


class FakeSink:
    """Records when frames are sent; can take `cost` virtual seconds per frame."""

    def __init__(self, clock, min_interval=0.3, max_bytes=30720, size=360, cost=0.0, close_after=None):
        self.clock, self.min_interval, self.max_bytes, self.size, self.cost, self.close_after = clock, min_interval, max_bytes, size, cost, close_after
        self.times, self.finished, self.started = [], False, False

    async def start(self):
        self.started = True

    async def send(self, jpeg, img, stats):
        self.times.append(self.clock.now())
        await self.clock.sleep(self.cost)
        stats.sent += 1
        stats.bytes += len(jpeg)
        return not (self.close_after and len(self.times) >= self.close_after)

    async def finish(self, stats):
        self.finished = True


# sources and clocks --------------------------------------------------------------------------------------------------

def test_virtual_clock_advances_only_when_slept():
    c = streaming.VirtualClock()
    run(c.sleep(1.5))
    run(c.sleep(-3))
    assert c.now() == 1.5


def test_synthetic_source_is_deterministic_and_timed():
    a = list(streaming.SyntheticSource(size=64, fps=10, seconds=1.0, detail=0.2, seed=3).frames())
    b = list(streaming.SyntheticSource(size=64, fps=10, seconds=1.0, detail=0.2, seed=3).frames())
    assert len(a) == 10 and [t for t, _ in a] == [i / 10 for i in range(10)]
    assert all(x[1].tobytes() == y[1].tobytes() for x, y in zip(a, b))
    c = list(streaming.SyntheticSource(size=64, fps=10, seconds=1.0, detail=0.2, seed=4).frames())
    assert any(x[1].tobytes() != y[1].tobytes() for x, y in zip(a, c))


def test_gif_source_uses_frame_delays(tmp_path):
    fr = [Image.new("RGB", (20, 20), (i * 40, 0, 0)) for i in range(4)]
    p = tmp_path / "a.gif"
    fr[0].save(p, save_all=True, append_images=fr[1:], duration=[100, 200, 300, 400])
    src = streaming.gif_source(str(p))
    assert [round(t, 2) for t, _ in src.frames()] == [0.0, 0.1, 0.3, 0.6]
    assert len(list(streaming.gif_source(str(p), max_seconds=0.25).frames())) == 2


def test_open_source_dispatch(tmp_path):
    assert isinstance(streaming.open_source("synthetic"), streaming.SyntheticSource)
    assert isinstance(streaming.open_source("synthetic:x"), streaming.SyntheticSource)
    g = tmp_path / "x.gif"
    Image.new("RGB", (8, 8)).save(g)
    assert isinstance(streaming.open_source(str(g)), streaming.ImageListSource)


# quality control -----------------------------------------------------------------------------------------------------

def test_quality_controller_fits_the_limit_and_adapts():
    noisy = next(iter(streaming.SyntheticSource(size=360, detail=1.0, fps=1, seconds=1).frames()))[1]
    ctl = streaming.QualityController(30720)
    b, q = ctl.encode(noisy)
    assert b is not None and len(b) <= 30720 and q <= 50
    plain = Image.new("RGB", (360, 360), (10, 20, 30))
    qs = [ctl.encode(plain)[1] for _ in range(8)]
    assert qs[-1] > qs[0] or qs[-1] == ctl.top                       # climbs when frames are small
    assert max(qs) <= ctl.top


def test_quality_controller_reports_impossible_frames():
    noisy = next(iter(streaming.SyntheticSource(size=360, detail=1.0, fps=1, seconds=1).frames()))[1]
    b, q = streaming.QualityController(500).encode(noisy)
    assert b is None and q == streaming.QUALITIES[-1]


# pipeline rate control -----------------------------------------------------------------------------------------------

def test_pipeline_never_sends_faster_than_the_sink_interval():
    clock = streaming.VirtualClock()
    sink = FakeSink(clock, min_interval=0.3)
    src = streaming.SyntheticSource(size=64, fps=30, seconds=3.0, detail=0)
    st = run(streaming.Pipeline(src, sink, 20.0, True, clock).run())
    gaps = [b - a for a, b in zip(sink.times, sink.times[1:])]
    assert gaps and min(gaps) >= 0.3 - 1e-6
    assert st.sent == len(sink.times) and 9 <= st.sent <= 11
    assert st.frames_in == 90 and st.dropped_rate == st.frames_in - st.sent
    assert sink.started and sink.finished


def test_pipeline_honours_a_lower_target_fps():
    clock = streaming.VirtualClock()
    sink = FakeSink(clock, min_interval=0.0)
    st = run(streaming.Pipeline(streaming.SyntheticSource(size=64, fps=30, seconds=4.0, detail=0), sink, 2.0, True, clock).run())
    assert 7 <= st.sent <= 9 and abs(st.fps() - 2.0) < 0.15


def test_slow_sink_makes_stale_frames_drop_instead_of_queueing():
    clock = streaming.VirtualClock()
    sink = FakeSink(clock, min_interval=0.0, cost=1.0)
    st = run(streaming.Pipeline(streaming.SyntheticSource(size=64, fps=10, seconds=5.0, detail=0), sink, 10.0, True, clock).run())
    assert st.dropped_late > 0 and st.sent <= 6
    assert st.elapsed <= 6.5                                          # did not fall behind the source clock


def test_oversize_frames_are_counted_not_sent():
    clock = streaming.VirtualClock()
    sink = FakeSink(clock, min_interval=0.0, max_bytes=400)
    st = run(streaming.Pipeline(streaming.SyntheticSource(size=200, fps=5, seconds=1.0, detail=1.0), sink, 5.0, True, clock).run())
    assert st.dropped_oversize == 5 and st.sent == 0


def test_sink_closing_stops_the_pipeline_and_still_finishes():
    clock = streaming.VirtualClock()
    sink = FakeSink(clock, min_interval=0.0, close_after=2)
    st = run(streaming.Pipeline(streaming.SyntheticSource(size=64, fps=10, seconds=3.0, detail=0), sink, 10.0, True, clock).run())
    assert st.sent == 2 and sink.finished


def test_pipeline_rejects_bad_fps():
    with pytest.raises(ValueError):
        streaming.Pipeline(streaming.SyntheticSource(), FakeSink(streaming.VirtualClock()), 0)


def test_stats_summary_text():
    st = streaming.Stats()
    assert "sent 0" in st.summary() and st.fps() == 0.0


# Wi-Fi end to end ----------------------------------------------------------------------------------------------------

def test_wifi_pipeline_end_to_end_against_the_software_badge():
    async def go():
        clock = streaming.VirtualClock()
        badge = sim.SimWifiBadge()
        sess = wifi.WifiSession(lambda n: wifi.SimChannel(badge, n), pace=False)
        sink = streaming.WifiSink(sess.live(), clock, streaming.WIFI_MODEL)
        st = await streaming.Pipeline(streaming.SyntheticSource(fps=30, seconds=3.0, detail=0.3), sink, 5.0, True, clock).run()
        return st, badge, sink
    st, badge, sink = run(go())
    assert st.sent == len(badge.frames) == len(sink.sent_jpegs) and st.sent >= 8
    assert not badge.camera_open                                       # stop word was sent
    for f in badge.frames:
        assert len(f) <= wifi.MAX_JPEG
        im = Image.open(io.BytesIO(f))
        assert im.size == (360, 360) and im.format == "JPEG"
        assert max(im.getpixel((0, 0))) <= 4                           # circular mask on black (JPEG rounding)
    assert st.fps() <= 1.0 / wifi.MIN_FRAME_INTERVAL + 0.05


def test_wifi_live_counts_oversize_and_pads_small_frames():
    async def go():
        badge = sim.SimWifiBadge()
        sess = wifi.WifiSession(lambda n: wifi.SimChannel(badge, n), pace=False, log=lambda m: None)
        live = sess.live()
        await live.start()
        r = [await live.send(b"\xff\xd8" + b"\x00" * 40000 + b"\xff\xd9", 0.001),
             await live.send(b"\xff\xd8\xff\xd9", 0.001)]
        await live.stop()
        await live.close()
        return r, badge, sess
    r, badge, sess = run(go())
    assert r == ["dropped", "sent"] and sess.dropped == 1 and len(badge.frames) == 1 and len(badge.frames[0]) == wifi.MIN_JPEG


def test_wifi_live_start_failure_closes_the_channel():
    class Mute(wifi.SimChannel):
        async def recv(self, timeout):
            return b""
    chans = []

    def mk(n):
        c = Mute(sim.SimWifiBadge(), n)
        chans.append(c)
        return c
    live = wifi.WifiSession(mk, pace=False).live()
    with pytest.raises(wifi.WifiError):
        run(live.start())
    assert live.ctrl is None


# BLE clips -----------------------------------------------------------------------------------------------------------

def _ble_run(min_interval_s, segment=3, seconds=20.0, delta=True, sub=""):
    async def go():
        clock = streaming.VirtualClock()
        gate = safewrite.Gate("t", safewrite.Policy(True, False, delta, min_interval_s, 0, 0),
                              safewrite.Store(_ble_run.dir + sub), now=lambda: 1e6 + clock.now())
        links = []

        async def open_link():
            lk = link.RecordingLink(sim.SimNn20())
            links.append(lk)
            return lk
        up = streaming.clip_uploader(open_link, "nn20", 368, gate, lambda m: None, fast=True)
        sink = streaming.BleSegmentSink(up, clock, segment, 500, streaming.BLE_MODEL, 368)
        st = await streaming.Pipeline(streaming.SyntheticSource(fps=10, seconds=seconds, detail=0.1), sink, 2.0, True, clock).run()
        return st, sink, links
    return run(go())


@pytest.fixture(autouse=True)
def _dir(tmp_path):
    _ble_run.dir = str(tmp_path / "state")


def test_ble_clips_are_type5_containers_and_counted():
    st, sink, links = _ble_run(0)
    assert st.uploads == len(sink.payloads) == len(links) >= 2
    assert all(p[:4] == b"\x78\x56\x34\x12" for p in sink.payloads)      # 0x12345678 container magic, little endian
    assert st.sent >= 6 and st.dropped_policy == 0
    assert any(e[0] == "W" for e in links[0].events)


def test_ble_min_interval_blocks_extra_clips_and_counts_the_frames():
    free, _, _ = _ble_run(0, sub="a")
    st, sink, _ = _ble_run(30, sub="b")
    assert st.uploads == 1 and st.dropped_policy > 0
    assert st.sent + st.dropped_policy + st.dropped_late + st.dropped_rate <= st.frames_in
    assert free.uploads > st.uploads
    assert safewrite.Store(_ble_run.dir + "b").data["total"] == 1


def test_ble_delivered_rate_is_far_below_the_wifi_cap():
    st, _, _ = _ble_run(0)
    assert 0 < st.sent / st.elapsed < 1.0


def test_ble_sink_validates_segment_size():
    with pytest.raises(ValueError):
        streaming.BleSegmentSink(None, streaming.VirtualClock(), 0)


def test_ble_partial_last_clip_is_flushed():
    async def go():
        clock = streaming.VirtualClock()
        got = []

        async def up(images, interval):
            got.append(len(images))
            return b"x"
        sink = streaming.BleSegmentSink(up, clock, 4, 500, None, 368)
        st = await streaming.Pipeline(streaming.SyntheticSource(size=64, fps=2, seconds=3.0, detail=0), sink, 2.0, True, clock).run()
        return got, st
    got, st = run(go())
    assert got == [4, 2] and st.uploads == 2 and st.sent == 6


# CLI -----------------------------------------------------------------------------------------------------------------

def test_cli_stream_synthetic_wifi_dry_run(tmp_path, capsys):
    out = tmp_path / "s.txt"
    assert cli.main(["stream", "synthetic", "--max-seconds", "3", "--fps", "3", "--dry-run", str(out), "--quiet"]) == 0
    txt = out.read_text()
    assert "W ctrl 2 00 79" in txt and "N ctrl 2 00 7B" in txt and "00 7F" in txt
    assert (tmp_path / "s.txt.payload").read_bytes()[:3] == b"\xff\xd8\xff"
    assert "frames in" in capsys.readouterr().out


@pytest.mark.parametrize("transport", ["nn20", "badge"])
def test_cli_stream_synthetic_ble_dry_run(tmp_path, capsys, transport):
    out = tmp_path / "b.txt"
    args = ["stream", "synthetic", "--max-seconds", "6", "--fps", "2", "--segment-frames", "3", "--transport", transport,
            "--dry-run", str(out), "--quiet"]
    if transport == "badge":
        pytest.importorskip("rebeambox.control")
    code = cli.main(args)
    text = capsys.readouterr()
    assert code == 0, text.err
    assert "uploads" in text.out and "# clip 1" in out.read_text()
    payload = (tmp_path / "b.txt.payload").read_bytes()
    assert payload[:4] == b"\x78\x56\x34\x12" if transport == "nn20" else payload[:4] == b"RIFF"


def test_cli_stream_flags():
    a = cli.build_parser().parse_args(["stream", "synthetic"])
    assert a.fps == 2.0 and a.source_fps == 10.0 and a.segment_frames == 6 and a.max_seconds == 10.0


# benchmark tool ------------------------------------------------------------------------------------------------------

def test_bench_rows_are_deterministic_and_respect_limits():
    a = run(bench_stream.wifi_row(5.0, 0.1, 3))
    b = run(bench_stream.wifi_row(5.0, 0.1, 3))
    assert a == b
    assert a["max_frame"] <= wifi.MAX_JPEG and a["frames_at_badge"] == a["sent"] and a["delivered_fps"] <= 3.4


def test_bench_ble_row_shows_policy_effect():
    free = run(bench_stream.ble_row(3, 10, 0))
    capped = run(bench_stream.ble_row(3, 10, 30))
    assert free["uploads"] >= capped["uploads"] == 1 and capped["dropped_policy"] >= 0
