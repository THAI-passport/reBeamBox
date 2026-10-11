import pytest
from PIL import Image
from rebeambox import media

def test_fit_square_circle_corners_black():
    im = Image.new("RGB", (500, 300), (255, 255, 255))
    out = media.fit_square(im, 360, circular=True)
    assert out.size == (360, 360) and out.getpixel((0, 0)) == (0, 0, 0) and out.getpixel((180, 180)) == (255, 255, 255)
    assert media.fit_square(im, 360, circular=False).getpixel((0, 0)) == (255, 255, 255)

def test_png_alpha_flattened():
    im = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    assert media.fit_square(im, 64, circular=False).getpixel((10, 10)) == (0, 0, 0)

def test_still_jpeg(tmp_path):
    p = tmp_path / "a.png"; Image.new("RGB", (100, 80), (10, 200, 10)).save(p)
    b = media.still_to_jpeg(str(p), 360)
    assert media.is_jpeg(b)
    assert Image.open(__import__("io").BytesIO(b)).size == (360, 360)

def test_render_text_fits_inside_circle():
    im = media.render_text("Somchai Jaidee", "Bangkok", 360)
    assert im.size == (360, 360)
    assert im.getpixel((0, 0)) == (0, 0, 0) and im.getpixel((359, 359)) == (0, 0, 0)
    assert im.getbbox() is not None

def test_avi_command_matches_documented_builder():
    c = media.avi_command("f_%05d.jpg", 15, 360, 3, "o.avi")
    s = " ".join(c)
    assert "-r 15.000 -i f_%05d.jpg" in s and "scale=360:360:force_original_aspect_ratio=disable,setsar=1" in s
    assert "-c:v mjpeg -q:v 5 -t 3.000 -an -f avi o.avi" in s
    a = " ".join(media.avi_command("f", 15, 360, 3, "o", audio="a.wav"))
    assert "-i f -i a.wav -vf" in a and "-map 0:v:0 -map 1:a:0? -c:v mjpeg -q:v 5 -c:a pcm_s16le -ar 16000 -ac 1 -t 3.000 -shortest -f avi o" in a


def test_app_interval_rule_and_fractional_fps():
    assert media.app_interval_ms(3000, 12) == 250 and media.app_interval_ms(1000, 100) == 50 and media.app_interval_ms(500, 0) == 100
    assert " ".join(media.avi_command("f", 1000 / 30, 360, 1, "o")).count("-r 33.333") == 1

def _gif(p, n=12, delay=100):
    fr = [Image.new("RGB", (64, 64), (i * 5, 0, 0)) for i in range(n)]
    fr[0].save(p, save_all=True, append_images=fr[1:], duration=delay, loop=0)

def test_gif_frames_capped_at_3_seconds(tmp_path):
    p = tmp_path / "a.gif"; _gif(p, 50, 100)
    frames, interval = media.load_gif_frames(str(p), 64)
    assert interval == 100 and len(frames) == 30

@pytest.mark.skipif(not media.have_ffmpeg(), reason="ffmpeg not installed")
def test_gif_to_avi(tmp_path):
    p = tmp_path / "a.gif"; _gif(p, 10, 100)
    avi = media.gif_to_avi(str(p), 64)
    assert media.is_avi(avi) and b"MJPG" in avi[:400]

@pytest.mark.skipif(not media.have_ffmpeg(), reason="ffmpeg not installed")
def test_video_cap(tmp_path):
    import subprocess
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "6", str(v)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = media.load_video_frames(str(v), 64, fps=10, max_seconds=3)
    assert 29 <= len(frames) <= 31
