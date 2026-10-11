"""Command line: python -m rebeambox <scan|send-image|send-gif|send-video|send-text>."""
import argparse
import asyncio
import sys

from . import __version__, client, link, media, scan as scanmod, sim


def _add_common(p):
    p.add_argument("--address", help="Bluetooth address (or macOS UUID); skips scanning")
    p.add_argument("--name", action="append", default=[], help="extra device name filter (repeatable)")
    p.add_argument("--timeout", type=float, default=8.0, help="scan seconds")
    p.add_argument("--size", type=int, help="override picture size (default: what the badge reports, else 360)")
    p.add_argument("--square", action="store_true", help="do not apply the circular mask")
    p.add_argument("--transport", choices=["badge", "nn20"], help="force a transport (default: service discovery)")
    p.add_argument("--dry-run", metavar="FILE", help="no Bluetooth: write every frame to FILE (and FILE.payload)")
    p.add_argument("--pic", type=int, nargs=2, metavar=("W", "H"), default=(360, 360),
                   help="simulated badge picture size for --dry-run")
    p.add_argument("--quiet", action="store_true")


def build_parser():
    ap = argparse.ArgumentParser(prog="rebeambox", description="Open client for Beambox-style round badges (untested on hardware).")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="list nearby badges")
    s.add_argument("--name", action="append", default=[])
    s.add_argument("--timeout", type=float, default=8.0)
    s.add_argument("--all", action="store_true", help="show every device")
    p = sub.add_parser("send-image", help="send a JPG/PNG still"); p.add_argument("path"); _add_common(p)
    p.add_argument("--quality", type=int, default=90)
    p = sub.add_parser("send-gif", help="send an animated GIF"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=media.MAX_SECONDS)
    p = sub.add_parser("send-video", help="send a video (first 3 s)"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=media.MAX_SECONDS)
    p.add_argument("--fps", type=int, default=15)
    p = sub.add_parser("send-text", help="render text or a name tag and send it"); p.add_argument("text"); _add_common(p)
    p.add_argument("--subtitle"); p.add_argument("--fg", default="#ffffff"); p.add_argument("--bg", default="#000000")
    p.add_argument("--font", help="path to a .ttf (use a Thai-capable font for Thai text)")
    p.add_argument("--save-preview", metavar="PNG", help="also save the rendered image")
    return ap


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def make_job(args):
    circ = not args.square
    if args.cmd == "send-image":
        from PIL import Image
        def fn(size):
            with Image.open(args.path) as im:
                return [media.fit_square(im, size, circ)], 0
        return client.Job("still", fn, quality=args.quality)
    if args.cmd == "send-text":
        def fn(size):
            im = media.render_text(args.text, args.subtitle, size, _hex(args.fg), _hex(args.bg), args.font, circ)
            if args.save_preview:
                im.save(args.save_preview)
            return [im], 0
        return client.Job("still", fn, name="text.jpg")
    if args.cmd == "send-gif":
        return client.Job("anim", lambda size: media.load_gif_frames(args.path, size, circ, args.max_seconds), name="anim.avi")
    return client.Job("anim", lambda size: _video(args, size, circ), name="video.avi")


def _video(args, size, circ):
    frames = media.load_video_frames(args.path, size, circ, args.fps, args.max_seconds)
    return frames, 1000 // args.fps


async def _run_send(args):
    log = (lambda *_: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    job = make_job(args)
    if args.dry_run:
        badge = sim.SimNn20() if args.transport == "nn20" else sim.SimBadgeSdk(picture=tuple(args.pic))
        lk = link.RecordingLink(badge)
        payload = await client.send(lk, job, args.transport or ("nn20" if args.transport == "nn20" else "badge"),
                                    args.size, log, fast=True)
        with open(args.dry_run, "w") as fh:
            fh.write("# rebeambox dry run: W = written by us, N = simulated badge notification\n")
            fh.write("# columns: direction, short uuid, length, bytes\n")
            fh.write(lk.dump())
        with open(args.dry_run + ".payload", "wb") as fh:
            fh.write(payload)
        log("wrote %d events to %s and payload %d bytes to %s.payload" % (len(lk.events), args.dry_run, len(payload), args.dry_run))
        return 0
    from .scan import scan
    addr = args.address
    if not addr:
        found = [d for d in await scan(args.timeout, args.name) if d["match"]]
        if not found:
            print("no badge found; press the badge Bluetooth button, or pass --address / --name", file=sys.stderr)
            return 2
        addr = found[0]["address"]
        log("using %s (%s)" % (found[0]["name"], addr))
    lk = link.BleakLink(addr)
    await lk.connect()
    try:
        await client.send(lk, job, args.transport, args.size, log, progress=None if args.quiet else
                          (lambda p: print("\r%3d%%" % p, end="", file=sys.stderr)))
        log("\ndone")
    finally:
        await lk.close()
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "scan":
            res = asyncio.run(scanmod.scan(args.timeout, args.name, args.all))
            for d in res:
                a = d["adv"]
                extra = " %s/%s" % (a["kind"], a["shape"]) if a else ""
                print("%s  %-24s rssi %s%s%s" % (d["address"], d["name"], d["rssi"], extra, "" if d["match"] else "  (no match)"))
            if not res:
                print("no badges found")
            return 0
        return asyncio.run(_run_send(args))
    except (media.MediaError, FileNotFoundError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except Exception as e:
        print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
