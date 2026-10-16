"""Software tests 5, 6, 7, 8 (docs/software-test-v1.md): media conversion, scan filter matrix per model,
transport auto-selection from mock GATT services, Thai text rendering."""
import io
import os
import subprocess

import pytest
from PIL import Image

from rebeambox import client, link, media, models, nn20, control, scan, sim
from rebeambox.session import AE00, ProtocolError


# ---------------- test 5: media conversion ----------------
def test_tall_image_is_center_cropped():
    im = Image.new("RGB", (300, 500), (0, 0, 255))
    im.paste((255, 0, 0), (0, 0, 300, 250))                      # top half red, bottom half blue
    out = media.fit_square(im, 360, circular=True)
    assert out.size == (360, 360)
    r, g, b = out.getpixel((180, 60))
    assert r > 200 and b < 60
    r, g, b = out.getpixel((180, 300))
    assert b > 200 and r < 60


def test_wide_image_is_center_cropped():
    im = Image.new("RGB", (600, 200), (255, 255, 0))
    im.paste((0, 200, 0), (0, 0, 300, 200))                      # left half green, right half yellow
    out = media.fit_square(im, 360, circular=True)
    assert out.getpixel((90, 180))[1] > 150 and out.getpixel((90, 180))[0] < 60
    assert out.getpixel((270, 180))[0] > 200


def test_circular_mask_blanks_corners_for_any_aspect():
    for wh in [(500, 300), (300, 500), (360, 360), (50, 50)]:
        out = media.fit_square(Image.new("RGB", wh, (255, 255, 255)), 360, True)
        assert out.getpixel((0, 0)) == (0, 0, 0) and out.getpixel((359, 0)) == (0, 0, 0)
        assert out.getpixel((0, 359)) == (0, 0, 0) and out.getpixel((180, 180)) == (255, 255, 255)


def test_transparent_png_is_flattened_on_black(tmp_path):
    p = tmp_path / "t.png"
    im = Image.new("RGBA", (64, 64), (255, 255, 255, 0))          # fully transparent
    im.paste((255, 255, 255, 128), (32, 0, 64, 64))               # right half half transparent white
    im.save(p)
    out = media.fit_square(Image.open(p), 64, circular=False)
    assert out.getpixel((8, 32)) == (0, 0, 0)
    r, g, b = out.getpixel((56, 32))
    assert 120 <= r <= 135 and 120 <= g <= 135 and 120 <= b <= 135
    jpg = media.still_to_jpeg(str(p), 64, circular=False)
    assert media.is_jpeg(jpg)
    dec = Image.open(io.BytesIO(jpg)).convert("RGB")
    assert dec.getpixel((8, 32))[0] < 12 and 112 <= dec.getpixel((56, 32))[0] <= 143


def test_palette_png_with_transparency(tmp_path):
    p = tmp_path / "pal.png"
    im = Image.new("P", (32, 32), 0)
    im.putpalette([255, 0, 0] + [0, 0, 0] * 255)
    im.save(p, transparency=0)
    assert media.fit_square(Image.open(p), 32, circular=False).getpixel((5, 5)) == (0, 0, 0)


def _gif(path, durations):
    fr = [Image.new("RGB", (48, 48), (i * 30 % 256, 20 + i, 90)) for i in range(len(durations))]
    fr[0].save(path, save_all=True, append_images=fr[1:], duration=durations, loop=0)


def test_uneven_gif_durations_average_to_one_interval(tmp_path):
    p = tmp_path / "u.gif"
    _gif(p, [50, 200, 100, 50, 200, 100])
    frames, interval = media.load_gif_frames(str(p), 360, True, 3.0)
    assert len(frames) == 6 and interval == 117 and all(f.size == (360, 360) for f in frames)


def test_gif_very_short_delays_are_clamped(tmp_path):
    p = tmp_path / "f.gif"
    _gif(p, [20] * 8)
    frames, interval = media.load_gif_frames(str(p), 64, True, 3.0)
    assert interval >= media.MIN_INTERVAL_MS and len(frames) == 8


@pytest.mark.parametrize("key,cap", [("nikko", 10.0), ("nano", 3.0), ("niji", 5.0)])
def test_long_gif_is_capped_to_the_model_limit(tmp_path, key, cap):
    p = tmp_path / "long.gif"
    _gif(p, [100] * 100)                                          # 10 s
    prof = models.get(key)
    assert prof.video_max_s == cap
    frames, interval = media.load_gif_frames(str(p), 64, True, prof.video_max_s)
    assert interval == 100 and len(frames) == int(cap * 1000 // 100)


def _make_video(path, seconds):
    if not media.have_ffmpeg():
        pytest.skip("ffmpeg not installed")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=duration=%d:size=160x120:rate=10" % seconds, "-pix_fmt", "yuvj420p", "-c:v", "mjpeg", str(path)],
                       capture_output=True)
    if r.returncode != 0:
        pytest.skip("ffmpeg could not create a test video: %s" % r.stderr[-200:])


@pytest.mark.parametrize("key", ["nano", "niji"])
def test_video_longer_than_model_cap_is_trimmed(tmp_path, key):
    v = tmp_path / "long.avi"
    _make_video(v, 8)
    cap = models.get(key).video_max_s
    frames = media.load_video_frames(str(v), 64, True, 10, cap)
    assert cap * 10 - 2 <= len(frames) <= cap * 10 + 1 < 80


def test_video_to_avi_is_an_avi(tmp_path):
    v = tmp_path / "v.avi"
    _make_video(v, 4)
    assert media.is_avi(media.video_to_avi(str(v), 64, True, 10, 3.0))


# ---------------- test 6: scan filter matrix per model ----------------
#  name -> expected result for (no model, nikko, nano, niji)
MATRIX = {
    "NEO-0001":         (True, True, True, True),
    "NEO-0001(BLE)":    (False, False, False, False),
    "B-Device 7":       (True, True, True, True),
    "E-badge":          (True, True, True, True),
    "E-badge(BLE)":     (False, True, True, True),     # model profiles carry E-badge, which overrides the BLE exclusion
    "Nikko-badge(BLE)": (False, True, False, False),
    "Nikko-badge":      (False, True, False, False),
    "Nano-01":          (False, False, True, False),
    "NIJI_touch":       (False, False, False, True),
    "niji(BLE)":        (False, False, False, True),
    "Random Speaker":   (False, False, False, False),
    "":                 (False, False, False, False),
    "   ":              (False, False, False, False),
    None:               (False, False, False, False),
}


@pytest.mark.parametrize("name", list(MATRIX))
def test_scan_filter_matrix(name):
    for model, expected in zip((None, "nikko", "nano", "niji"), MATRIX[name]):
        extra = models.get(model).names if model else ()
        assert scan.name_matches(name, extra) is expected, "%r with model %s" % (name, model)


def test_scan_filter_is_case_and_punctuation_insensitive():
    for n in ("neo", "N.E.O 12", "b device", "B_DEVICE", "e badge", "xxE-BADGEyy"):
        assert scan.name_matches(n)


def test_scan_extra_name_beats_ble_exclusion_only_when_configured():
    assert not scan.name_matches("Pulse (BLE)")
    assert scan.name_matches("Pulse (BLE)", ["Pulse"])


# ---------------- test 7: transport auto-selection from mock GATT services ----------------
class MockLink:
    def __init__(self, *uuids):
        self.uuids = {u.lower() for u in uuids}

    def has_service(self, uuid):
        return uuid.lower() in self.uuids


def test_transport_from_mock_services():
    assert client.detect_transport(MockLink(control.SERVICE)) == "badge"
    assert client.detect_transport(MockLink(AE00)) == "badge"
    assert client.detect_transport(MockLink(nn20.SERVICE)) == "nn20"
    assert client.detect_transport(MockLink(nn20.SERVICE, "0000180a-0000-1000-8000-00805f9b34fb")) == "nn20"


def test_transport_badge_wins_when_both_present():
    assert client.detect_transport(MockLink(nn20.SERVICE, control.SERVICE)) == "badge"


def test_transport_unknown_services_is_an_error():
    for l in (MockLink(), MockLink("0000180a-0000-1000-8000-00805f9b34fb", "0000180f-0000-1000-8000-00805f9b34fb")):
        with pytest.raises(ProtocolError):
            client.detect_transport(l)


def test_transport_with_software_badges():
    assert client.detect_transport(link.RecordingLink(sim.SimNn20())) == "nn20"
    assert client.detect_transport(link.RecordingLink(sim.SimBadgeSdk())) == "badge"


# ---------------- test 8: Thai text rendering ----------------
THAI_FONT_PATHS = [os.environ.get("REBEAMBOX_THAI_FONT", ""), "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
                   "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf", "/usr/share/fonts/truetype/tlwg/Loma.ttf",
                   "/usr/share/fonts/truetype/tlwg/Garuda.ttf", "/usr/share/fonts/opentype/noto/NotoSansThai-Regular.ttf",
                   "/System/Library/Fonts/Thonburi.ttc", "C:\\Windows\\Fonts\\tahoma.ttf"]


def _thai_font():
    for p in THAI_FONT_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def test_thai_text_renders_inside_circle_with_known_font():
    font = _thai_font()
    if font is None:
        pytest.skip("no Thai font found (set REBEAMBOX_THAI_FONT)")
    a = media.render_text("สวัสดี", "กรุงเทพ", 360, font_path=font)
    b = media.render_text("ขอบคุณ", "เชียงใหม่", 360, font_path=font)
    assert a.size == (360, 360) and a.getbbox() is not None
    assert a.getpixel((0, 0)) == (0, 0, 0) and a.getpixel((359, 359)) == (0, 0, 0)
    assert a.tobytes() != b.tobytes()               # missing glyphs would draw identical boxes for both strings
    bbox = a.getbbox()
    assert bbox[0] > 20 and bbox[2] < 340            # stays inside the safe area


def test_thai_text_without_font_does_not_crash():
    im = media.render_text("สวัสดี", None, 120, font_path="/nonexistent/font.ttf")
    assert im.size == (120, 120)
