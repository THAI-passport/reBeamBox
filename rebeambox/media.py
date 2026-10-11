"""Media conversion: stills, text tags, GIF/video to MJPEG AVI. No network access."""
import io
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence

DEFAULT_SIZE = 360
MAX_SECONDS = 3.0
MIN_INTERVAL_MS = 30


class MediaError(RuntimeError):
    pass


def fit_square(img, size=DEFAULT_SIZE, circular=True, bg=(0, 0, 0)):
    """Center-crop to a square, resize, optionally blank the corners outside the inscribed circle."""
    img = ImageOps.exif_transpose(img).convert("RGBA")
    flat = Image.new("RGB", img.size, bg)
    flat.paste(img, mask=img.split()[3])
    img = ImageOps.fit(flat, (size, size), Image.LANCZOS, centering=(0.5, 0.5))
    if circular:
        mask = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        out = Image.new("RGB", (size, size), bg)
        out.paste(img, mask=mask)
        img = out
    return img


def to_jpeg(img, quality=90):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def still_to_jpeg(path, size=DEFAULT_SIZE, circular=True, quality=90):
    with Image.open(path) as im:
        return to_jpeg(fit_square(im, size, circular), quality)


_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf", "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
    "/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf", "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Thonburi.ttc",
    "C:\\Windows\\Fonts\\tahomabd.ttf", "C:\\Windows\\Fonts\\arialbd.ttf",
]


def load_font(size, font_path=None):
    for p in ([font_path] if font_path else []) + _FONT_CANDIDATES:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def render_text(text, subtitle=None, size=DEFAULT_SIZE, fg=(255, 255, 255), bg=(0, 0, 0), font_path=None,
                circular=True):
    """Centered, auto-fitted text (and optional smaller second line) on a square image."""
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)
    safe = int(size * (0.70 if circular else 0.92))   # a text box that fits inside the circle
    lines = [(text, 1.0)] + ([(subtitle, 0.45)] if subtitle else [])
    fs = int(size * 0.5)
    while fs > 8:
        fonts = [load_font(max(8, int(fs * k)), font_path) for _, k in lines]
        boxes = [d.textbbox((0, 0), t, font=f) for (t, _), f in zip(lines, fonts)]
        w = max(b[2] - b[0] for b in boxes)
        h = sum(b[3] - b[1] for b in boxes) + 10 * (len(lines) - 1)
        if w <= safe and h <= safe:
            break
        fs -= 4
    y = (size - h) // 2
    for (t, _), f, b in zip(lines, fonts, boxes):
        d.text(((size - (b[2] - b[0])) // 2 - b[0], y - b[1]), t, font=f, fill=fg)
        y += b[3] - b[1] + 10
    return img


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def _run(cmd):
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise MediaError("ffmpeg not found; install it to send GIFs or videos (see README)")
    except subprocess.CalledProcessError as e:
        raise MediaError("ffmpeg failed: " + e.stderr.decode("utf-8", "replace")[-400:])


def avi_command(frames_pattern, fps, size, seconds, out_path, audio=None, ffmpeg="ffmpeg", height=None):
    """The exact argument order of BadgeMediaFileBuilder.a (docs/PROTOCOL.md 3.6.1): fps and duration with three
    decimals, mjpeg quality 5, avi container; with audio PCM 16 kHz mono and -shortest."""
    h = height or size
    vf = "scale=%d:%d:force_original_aspect_ratio=disable,setsar=1" % (size, h)
    cmd = [ffmpeg, "-y", "-r", "%.3f" % fps, "-i", frames_pattern]
    if audio:
        cmd += ["-i", audio, "-vf", vf, "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "mjpeg", "-q:v", "5",
                "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", "-t", "%.3f" % seconds, "-shortest"]
    else:
        cmd += ["-vf", vf, "-c:v", "mjpeg", "-q:v", "5", "-t", "%.3f" % seconds, "-an"]
    return cmd + ["-f", "avi", out_path]


def app_interval_ms(duration_ms, n_frames):
    """a8.a.c in the app: interval = max(50, round(duration / frames)); 100 when there are no frames."""
    if n_frames <= 0:
        return 100
    return max(50, round(max(1, duration_ms) / n_frames))


def frames_to_avi(frames, fps, size=DEFAULT_SIZE, seconds=MAX_SECONDS, audio=None):
    """frames: list of PIL images (already square). Returns AVI bytes."""
    if not frames:
        raise MediaError("no frames")
    fps = min(float(fps), 1000.0 / MIN_INTERVAL_MS)          # app: interval is at least 30 ms
    seconds = len(frames) / fps if seconds is None else min(seconds, len(frames) / fps)
    with tempfile.TemporaryDirectory() as td:
        for i, f in enumerate(frames, 1):
            f.convert("RGB").save(os.path.join(td, "frame_%05d.jpg" % i), "JPEG", quality=90)
        out = os.path.join(td, "out.avi")
        _run(avi_command(os.path.join(td, "frame_%05d.jpg"), fps, size, seconds, out, audio))
        with open(out, "rb") as fh:
            data = fh.read()
    if not is_avi(data):
        raise MediaError("ffmpeg output is not an AVI")
    return data


def is_avi(b):
    return len(b) > 12 and b[:4] == b"RIFF" and b[8:12] == b"AVI "


def is_jpeg(b):
    return b[:3] == b"\xff\xd8\xff"


def load_gif_frames(path, size=DEFAULT_SIZE, circular=True, max_seconds=MAX_SECONDS):
    """Return (frames, interval_ms). Interval is the mean delay clamped to 30 ms; capped at max_seconds."""
    frames, delays = [], []
    with Image.open(path) as im:
        for fr in ImageSequence.Iterator(im):
            delays.append(int(fr.info.get("duration", 100)) or 100)
            frames.append(fit_square(fr.copy(), size, circular))
    interval = max(MIN_INTERVAL_MS, round(sum(delays) / len(delays)))
    keep = max(1, int(max_seconds * 1000 // interval)) if max_seconds else len(frames)
    return frames[:keep], interval


def load_video_frames(path, size=DEFAULT_SIZE, circular=True, fps=15, max_seconds=MAX_SECONDS):
    if not have_ffmpeg():
        raise MediaError("ffmpeg not found; install it to send videos (see README)")
    with tempfile.TemporaryDirectory() as td:
        _run(["ffmpeg", "-y", "-i", path, "-t", "%g" % max_seconds, "-vf", "fps=%d" % fps,
              os.path.join(td, "v_%05d.png")])
        names = sorted(n for n in os.listdir(td) if n.startswith("v_"))
        if not names:
            raise MediaError("no frames decoded from video")
        frames = []
        for n in names:
            with Image.open(os.path.join(td, n)) as im:
                frames.append(fit_square(im.copy(), size, circular))
    return frames


def gif_to_avi(path, size=DEFAULT_SIZE, circular=True, max_seconds=MAX_SECONDS):
    frames, interval = load_gif_frames(path, size, circular, max_seconds)
    return frames_to_avi(frames, 1000.0 / interval, size, max_seconds)


def video_to_avi(path, size=DEFAULT_SIZE, circular=True, fps=15, max_seconds=MAX_SECONDS, keep_audio=False):
    frames = load_video_frames(path, size, circular, fps, max_seconds)
    return frames_to_avi(frames, fps, size, max_seconds, audio=path if keep_audio else None)
