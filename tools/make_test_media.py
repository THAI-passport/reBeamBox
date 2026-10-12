#!/usr/bin/env python3
"""Generate the test media the hardware plans ask for (Pillow; ffmpeg only for the video clips). No downloads, no vendor data.

    python tools/make_test_media.py [--out testmedia] [--no-video]

Files (all synthetic):
  gradient_label.png   800x800 colour gradient with TL/TR/BL/BR corner labels and a centre cross: shows rotation, mirroring, crop, circle mask
  red.png, blue.png    solid 800x800: the type 5 versus type 6 still test (H2)
  noise.png            800x800 pseudo-random blocks: a poorly compressible still, large payload, for the free-space test (H8)
  photo.jpg            800x800 smooth photo-like image (general sends)
  party.gif            20-frame 400x400 animation with a frame counter
  clip2.mp4 ... clip10.mp4  testsrc2 video, 2/3/4/5/8/10 seconds, 360x360, 15 fps (H7; needs ffmpeg)
The folder is git-ignored. Re-running overwrites; output is deterministic (fixed seeds) except for ffmpeg encoder details.
"""
import argparse
import os
import random
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

CLIP_SECONDS = (2, 3, 4, 5, 8, 10)


def gradient_label(n=800):
    im = Image.new("RGB", (n, n))
    px = im.load()
    for y in range(n):
        for x in range(n):
            px[x, y] = (int(255 * x / (n - 1)), int(255 * y / (n - 1)), 128)
    d = ImageDraw.Draw(im)
    for text, xy in (("TL", (12, 8)), ("TR", (n - 60, 8)), ("BL", (12, n - 40)), ("BR", (n - 60, n - 40))):
        d.rectangle([xy[0] - 6, xy[1] - 4, xy[0] + 52, xy[1] + 28], fill=(0, 0, 0))
        d.text(xy, text, fill=(255, 255, 255))
    d.line([(n // 2 - 40, n // 2), (n // 2 + 40, n // 2)], fill=(0, 0, 0), width=4)
    d.line([(n // 2, n // 2 - 40), (n // 2, n // 2 + 40)], fill=(0, 0, 0), width=4)
    return im


def noise(n=800, block=8):
    rnd = random.Random(1234)
    im = Image.new("RGB", (n, n))
    d = ImageDraw.Draw(im)
    for y in range(0, n, block):
        for x in range(0, n, block):
            d.rectangle([x, y, x + block - 1, y + block - 1], fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    return im


def photo(n=800):
    im = Image.new("RGB", (n, n))
    d = ImageDraw.Draw(im)
    for y in range(n):
        d.line([(0, y), (n, y)], fill=(40 + y * 120 // n, 80 + y * 100 // n, 200 - y * 90 // n))
    d.ellipse([n // 4, n // 4, 3 * n // 4, 3 * n // 4], fill=(240, 200, 60), outline=(120, 80, 0), width=6)
    d.polygon([(n // 2, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, 2 * n // 3)], fill=(200, 40, 40))
    return im


def party_gif(path, frames=20, n=400):
    imgs = []
    for i in range(frames):
        im = Image.new("RGB", (n, n), ((i * 13) % 256, (i * 37) % 256, (255 - i * 11) % 256))
        d = ImageDraw.Draw(im)
        d.ellipse([20 + i * 10, 150, 120 + i * 10, 250], fill=(255, 255, 255))
        d.text((10, 10), "frame %02d" % i, fill=(0, 0, 0))
        imgs.append(im)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=100, loop=0)


def clips(out):
    ff = shutil.which("ffmpeg")
    if not ff:
        print("ffmpeg not found: skipping video clips (install ffmpeg, then re-run)", file=sys.stderr)
        return []
    made = []
    for s in CLIP_SECONDS:
        p = os.path.join(out, "clip%d.mp4" % s)
        cmd = [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=360x360:rate=15", "-t", str(s),
               "-pix_fmt", "yuv420p", "-c:v", "libx264", p]
        if subprocess.run(cmd).returncode != 0:
            print("ffmpeg failed for %s" % p, file=sys.stderr)
            continue
        made.append(p)
    return made


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="testmedia")
    ap.add_argument("--no-video", action="store_true")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    gradient_label().save(os.path.join(a.out, "gradient_label.png"))
    Image.new("RGB", (800, 800), (255, 0, 0)).save(os.path.join(a.out, "red.png"))
    Image.new("RGB", (800, 800), (0, 0, 255)).save(os.path.join(a.out, "blue.png"))
    noise().save(os.path.join(a.out, "noise.png"))
    photo().save(os.path.join(a.out, "photo.jpg"), quality=90)
    party_gif(os.path.join(a.out, "party.gif"))
    made = [] if a.no_video else clips(a.out)
    print("wrote %s: gradient_label.png red.png blue.png noise.png photo.jpg party.gif %s" % (a.out, " ".join(os.path.basename(m) for m in made)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
