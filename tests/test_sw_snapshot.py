"""Software test 9 (docs/software-test-v1.md): dry-run snapshots locked to hex.
The JPEG below is a fixed 16x16 gradient (Pillow quality 75, embedded as base64) so the locked values do not depend on
the installed JPEG encoder. If a lock fails after an intentional protocol change, regenerate the values with
scripts/spec_vectors.py style code and update docs/software-test-v1.md."""
import base64
import hashlib

from PIL import Image

from rebeambox import cli, nn20, wifi

JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgy"
    "PC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAQABAD"
    "ASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKB"
    "kaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZ"
    "mqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQF"
    "BgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5"
    "OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX"
    "2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDz+x0Lp8ldNYaF0+SulsNC6fJXT2OhdPkrTF5r5i4fzvbU/9k=")


def test_fixture_is_the_expected_jpeg():
    assert len(JPEG) == 659 and JPEG[:3] == b"\xff\xd8\xff" and JPEG[-2:] == b"\xff\xd9"


def test_nn20_animation_frames_locked():
    frames = nn20.build_frames(5, nn20.gif_container([JPEG], 3000, 368, 368))
    assert [len(f) for f in frames] == [455, 320]
    assert frames[0][:40].hex() == "f1050002000101be7b2274797065223a352c2264617461223a785634122800000001000000b80b00"[:80]
    assert hashlib.sha256(b"".join(frames)).hexdigest() == "67aa2a4b1a1d56781b22e74aaa57b0cb15554a9e7e7dbda14dbe03dd20037a4a"


def test_imb_header_locked():
    imb = nn20.imb(360, 360, JPEG)
    assert imb[:36].hex() == "494d420004000000b30200000b0000006801680124000000930200000000000000000000"
    assert hashlib.sha256(imb).hexdigest() == "56281b5e8c3b8f1d1373ba7a39512259306c2218f2b0614bea19e807fe258f55"


def test_animation_container_header_locked():
    g = nn20.gif_container([JPEG], 3000, 368, 368)
    assert g[:32].hex() == "785634122800000001000000b80b00006f75747075742f333030306de20200006672616d655f30303030312e3000000030000000300000000b00000070017001"[:64]
    assert hashlib.sha256(g).hexdigest() == "0cf46d398c84fc424489559b049ea65d8273a7fc42200c80423316692ba4c61b"


def test_wifi_post_header_locked():
    imb = nn20.imb(360, 360, JPEG)
    assert wifi.build_post("192.168.8.1", "07", len(imb)) == (
        b"POST /upload HTTP/1.1\r\nHost: 192.168.8.1\r\nX-Filename: 07.bin\r\nContent-Type: application/octet-stream\r\n"
        b"Content-Length: 695\r\nConnection: keep-alive\r\n\r\n")


def test_cli_dry_run_of_known_image_is_self_consistent(tmp_path):
    img = tmp_path / "grad.png"
    im = Image.new("RGB", (16, 16))
    for y in range(16):
        for x in range(16):
            im.putpixel((x, y), (x * 16, y * 16, 128))
    im.save(img)
    out = tmp_path / "d.txt"
    assert cli.main(["send-image", str(img), "--transport", "nn20", "--dry-run", str(out), "--quiet"]) == 0
    payload = (tmp_path / "d.txt.payload").read_bytes()
    frames = []
    for line in out.read_text().splitlines():
        if line.startswith("W 01f1"):
            f = bytes.fromhex(line.split(None, 3)[3])
            if f[1] == nn20.TYPE_GIF:
                frames.append(f)
    assert frames and all(nn20.checksum(f[:-1]) == f[-1] for f in frames)
    env = b"".join(f[8:-1] for f in frames)
    assert env == b'{"type":5,"data":' + payload + b"}"
    assert payload[:4].hex() == "78563412"


def test_cli_dry_run_is_deterministic(tmp_path):
    img = tmp_path / "g.png"
    Image.new("RGB", (16, 16), (10, 120, 200)).save(img)
    outs = []
    for i in range(2):
        o = tmp_path / ("d%d.txt" % i)
        assert cli.main(["send-image", str(img), "--transport", "nn20", "--dry-run", str(o), "--quiet"]) == 0
        outs.append(o.read_text())
    assert outs[0] == outs[1]
