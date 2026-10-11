import asyncio
import pytest
from PIL import Image
from rebeambox import client, media, nn20, sim, wifi, cli

def run(c):
    return asyncio.run(c)

def job(kind="still", n=5):
    if kind == "still":
        return client.Job("still", lambda s: ([media.fit_square(Image.new("RGB", (400, 300), (10, 90, 200)), s)], 0))
    return client.Job("anim", lambda s: ([media.fit_square(Image.new("RGB", (60, 60), (i * 40, 5, 5)), s) for i in range(n)], 100), name="a.avi")

def test_post_header_exact():
    h = wifi.build_post("192.168.8.1", "07", 1234)
    assert h == (b"POST /upload HTTP/1.1\r\nHost: 192.168.8.1\r\nX-Filename: 07.bin\r\n"
                 b"Content-Type: application/octet-stream\r\nContent-Length: 1234\r\nConnection: keep-alive\r\n\r\n")

def test_helpers():
    assert wifi.parse_free_kb(b"SD:12345KB\x00\x6a") == 12345
    assert wifi.parse_free_kb(b"SD: 77 kb") == 77 and wifi.parse_free_kb(b"junk") is None
    assert wifi.camera_frame(b"abc") == b"\x00\x03abc\x00\x00"
    assert wifi.pace_for(200000) == 0.003 and wifi.pace_for(60000) == 0.002 and wifi.pace_for(10) == 0.001
    assert wifi.CMD_QUERY == b"\x00\x69" and wifi.CMD_CAM_START == b"\x00\x79" and wifi.CMD_CAM_STOP == b"\x00\x7f"

def test_jpeg_under_limit():
    import random
    r = random.Random(1)
    img = Image.frombytes("RGB", (360, 360), bytes(r.randrange(256) for _ in range(360 * 360 * 3)))
    b = wifi.jpeg_under(img)
    assert len(b) <= wifi.MAX_JPEG and media.is_jpeg(b)

def test_wifi_payloads():
    d = client.wifi_payload(job())
    assert d[:4] == b"IMB\x00" and int.from_bytes(d[16:18], "little") == 360
    g = client.wifi_payload(job("anim", 3))
    assert int.from_bytes(g[4:8], "little") == 3 * 16 + 32            # Wi-Fi address list length
    g2 = client.wifi_payload(job(), still_mode="gif")
    assert int.from_bytes(g2[:4], "little") == 0x12345678 and int.from_bytes(g2[4:8], "little") == 16 + 32

def test_upload_to_sim_badge():
    b = sim.SimWifiBadge()
    log = []
    data = run(client.send_wifi(job(), lambda n: wifi.SimChannel(b, n, log), log=lambda *_: None, pace=False))
    assert list(b.files.values()) == [data] and b.finished == 1
    assert [e[1] for e in log if e[0] == "W"][0] == "ctrl"
    assert any(e[0] == "N" and b"SD:12000KB" in e[2] for e in log)

def test_upload_refused_and_no_space():
    with pytest.raises(wifi.WifiError):
        run(client.send_wifi(job(), lambda n: wifi.SimChannel(sim.SimWifiBadge(refuse=True), n), log=lambda *_: None, pace=False))
    with pytest.raises(wifi.WifiError, match="does not fit"):
        run(client.send_wifi(job(), lambda n: wifi.SimChannel(sim.SimWifiBadge(free_kb=1), n), log=lambda *_: None, pace=False))

def test_camera_stream_and_shutter():
    async def go():
        b = sim.SimWifiBadge()
        chans = []
        def mk(n):
            c = wifi.SimChannel(b, n); chans.append(c); return c
        s = wifi.WifiSession(mk, pace=False)
        frames = [wifi.jpeg_under(media.fit_square(Image.new("RGB", (50, 50), (i * 30, 0, 0)), 360)) for i in range(4)]
        t = asyncio.ensure_future(s.stream(frames, fps=3))
        await asyncio.sleep(0.01)
        chans[0].conn.shutter()
        n = await t
        return b, frames, n, s
    b, frames, n, s = run(go())
    assert n == 4 and b.frames == frames and not b.camera_open

def test_fps_clamped_to_300ms():
    async def go():
        b = sim.SimWifiBadge()
        s = wifi.WifiSession(lambda n: wifi.SimChannel(b, n), pace=True)
        t0 = asyncio.get_event_loop().time()
        await s.stream([b"\xff\xd8\xff\xd9"] * 3, fps=100)
        return asyncio.get_event_loop().time() - t0
    assert run(go()) >= 0.85          # 3 frames x 0.3 s receive window

def test_real_tcp_loopback():
    async def go():
        badge = sim.SimWifiBadge()
        async def handle(r, w):
            conn = badge.new_conn(lambda d: (w.write(d)))
            while True:
                d = await r.read(4096)
                if not d:
                    break
                conn.feed(d)
                await w.drain()
            w.close()
        srv = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        data = await client.send_wifi(job(), lambda n: wifi.TcpChannel(), "127.0.0.1", port, log=lambda *_: None, pace=False)
        await asyncio.sleep(0.05)
        srv.close()
        return badge, data
    badge, data = run(go())
    assert list(badge.files.values()) == [data] and badge.finished == 1

def test_tcp_connect_error_message():
    with pytest.raises(wifi.WifiError, match="Wi-Fi access point"):
        run(wifi.TcpChannel().open("127.0.0.1", 1, timeout=1))

def test_cli_wifi_dry_run(tmp_path):
    img = tmp_path / "a.png"; Image.new("RGB", (80, 80), (9, 9, 9)).save(img)
    out = tmp_path / "w.txt"
    assert cli.main(["send-image", str(img), "--transport", "wifi", "--dry-run", str(out), "--quiet"]) == 0
    txt = out.read_text()
    assert "W ctrl 2 00 69" in txt and "W ctrl 2 00 5F" in txt and "W upload" in txt
    assert (tmp_path / "w.txt.payload").read_bytes()[:4] == b"IMB\x00"

def test_cli_stream_dry_run(tmp_path):
    g = tmp_path / "a.gif"
    fr = [Image.new("RGB", (40, 40), (i * 30, 0, 0)) for i in range(5)]
    fr[0].save(g, save_all=True, append_images=fr[1:], duration=100)
    out = tmp_path / "s.txt"
    assert cli.main(["stream", str(g), "--dry-run", str(out), "--quiet"]) == 0
    txt = out.read_text()
    assert "W ctrl 2 00 79" in txt and "N ctrl 2 00 7B" in txt and "00 7F" in txt
