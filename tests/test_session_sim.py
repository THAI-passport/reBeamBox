import asyncio
import pytest
from PIL import Image
from rebeambox import client, link, media, sim, rcsp, nn20

def job(kind="still", n=6):
    if kind == "still":
        return client.Job("still", lambda s: ([media.fit_square(Image.new("RGB", (500, 400), (200, 30, 30)), s)], 0))
    fr = lambda s: ([media.fit_square(Image.new("RGB", (80, 80), (i * 30, 10, 10)), s) for i in range(n)], 100)
    return client.Job("anim", fr, name="a.avi")

def run(coro):
    return asyncio.run(coro)

def test_badge_still_end_to_end():
    b = sim.SimBadgeSdk(read_size=700); l = link.RecordingLink(b)
    data = run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert media.is_jpeg(data) and b.file_ok is True and b.received == data
    assert b"".join(b.names)             # GetName answered
    assert any(e[1] == "ae01" for e in l.events)

def test_badge_respects_reported_size():
    b = sim.SimBadgeSdk(picture=(240, 240)); l = link.RecordingLink(b)
    data = run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert Image.open(__import__("io").BytesIO(data)).size == (240, 240)

def test_badge_without_packet_crc():
    b = sim.SimBadgeSdk(packet_crc=False, read_size=300, transfer_mtu=100); l = link.RecordingLink(b)
    data = run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert b.file_ok is True and b.received == data

@pytest.mark.skipif(not media.have_ffmpeg(), reason="ffmpeg not installed")
def test_badge_animation_sends_avi_with_filetype_handshake():
    b = sim.SimBadgeSdk(); l = link.RecordingLink(b)
    data = run(client.send(l, job("anim"), fast=True, log=lambda *_: None))
    assert media.is_avi(data) and b.received == data
    assert any(e[0] == "W" and e[2][3:4] == b"\xDC" for e in l.events)

def test_badge_too_big_for_memory():
    b = sim.SimBadgeSdk(memory_kb=1); l = link.RecordingLink(b)
    with pytest.raises(Exception, match="exceeds"):
        run(client.send(l, job(), fast=True, log=lambda *_: None))

def test_nn20_still_and_stream_integrity():
    b = sim.SimNn20(); l = link.RecordingLink(b)
    payload = run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert b.stream() == b'{"type":5,"data":' + payload + b"}"
    assert int.from_bytes(payload[:4], "little") == 0x12345678 and int.from_bytes(payload[8:12], "little") == 1
    assert int.from_bytes(payload[12:16], "little") == 3000

def test_nn20_album_mode_uses_imb():
    b = sim.SimNn20(); l = link.RecordingLink(b)
    j = job(); j.still_mode = "album"
    payload = run(client.send(l, j, fast=True, log=lambda *_: None))
    assert b.stream() == b'{"type":6,"data":' + payload + b"}" and payload[:4] == b"IMB\x00"

def test_nn20_noack_mode_and_retry():
    b = sim.SimNn20(time_mode=1); l = link.RecordingLink(b)
    run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert b.n_seen > 5
    b = sim.SimNn20(fail_packets={3}); l = link.RecordingLink(b)
    payload = run(client.send(l, job(), fast=True, log=lambda *_: None))
    assert b.n_seen > len(nn20.build_frames(5, payload))     # resent after the failure

def test_nn20_free_space_refusal():
    b = sim.SimNn20(freespace=10); l = link.RecordingLink(b)
    with pytest.raises(Exception, match="free space"):
        run(client.send(l, job(), fast=True, log=lambda *_: None))

def test_detect_transport():
    assert client.detect_transport(link.RecordingLink(sim.SimNn20())) == "nn20"
    assert client.detect_transport(link.RecordingLink(sim.SimBadgeSdk())) == "badge"
