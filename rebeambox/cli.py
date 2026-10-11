"""Command line: python -m rebeambox <scan|send-image|send-gif|send-video|send-text>."""
import argparse
import asyncio
import sys

from . import __version__, client, link, media, models, scan as scanmod, sim, wifi


def _add_common(p):
    p.add_argument("--address", help="Bluetooth address (or macOS UUID); skips scanning")
    p.add_argument("--name", action="append", default=[], help="extra device name filter (repeatable)")
    p.add_argument("--timeout", type=float, default=8.0, help="scan seconds")
    p.add_argument("--size", type=int, help="override picture size (default: what the badge reports, else 360)")
    p.add_argument("--square", action="store_true", help="do not apply the circular mask")
    p.add_argument("--transport", choices=["badge", "nn20", "wifi"], help="force a transport (default: BLE service discovery; wifi needs the badge access point joined)")
    p.add_argument("--host", default=wifi.HOST, help="Wi-Fi badge address")
    p.add_argument("--port", type=int, default=wifi.PORT, help="Wi-Fi badge TCP port")
    p.add_argument("--wifi-still", choices=["imb", "gif"], default="imb", help="Wi-Fi still container (imb = app behaviour)")
    p.add_argument("--dry-run", metavar="FILE", help="no Bluetooth: write every frame to FILE (and FILE.payload)")
    p.add_argument("--pic", type=int, nargs=2, metavar=("W", "H"), default=(360, 360),
                   help="simulated badge picture size for --dry-run")
    p.add_argument("--model", choices=sorted(models.PROFILES), help="badge model: adds its name filter, sets default size, video cap and still encoding")
    p.add_argument("--nn20-still", choices=["gif", "album"], help="nn20 stills: gif = type 5 one-frame container (default), album = type 6 IMB")
    p.add_argument("--quiet", action="store_true")


def build_parser():
    ap = argparse.ArgumentParser(prog="rebeambox", description="Open client for Beambox-style round badges (untested on hardware).")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="list nearby badges")
    s.add_argument("--name", action="append", default=[])
    s.add_argument("--timeout", type=float, default=8.0)
    s.add_argument("--all", action="store_true", help="show every device")
    s.add_argument("--model", choices=sorted(models.PROFILES))
    p = sub.add_parser("send-image", help="send a JPG/PNG still"); p.add_argument("path"); _add_common(p)
    p.add_argument("--quality", type=int, default=90)
    p = sub.add_parser("send-gif", help="send an animated GIF"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=None, help="cap in seconds (default 3, or the --model profile)")
    p = sub.add_parser("send-video", help="send a video (first 3 s)"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=None, help="cap in seconds (default 3, or the --model profile)")
    p.add_argument("--fps", type=int, default=15)
    p = sub.add_parser("stream", help="Wi-Fi live frames from a video or GIF (max 3.3 fps, 30 KB per frame)")
    p.add_argument("path"); _add_common(p); p.add_argument("--fps", type=float, default=2.0)
    p.add_argument("--max-seconds", type=float, default=10.0)
    p = sub.add_parser("send-text", help="render text or a name tag and send it"); p.add_argument("text"); _add_common(p)
    p.add_argument("--subtitle"); p.add_argument("--fg", default="#ffffff"); p.add_argument("--bg", default="#000000")
    p.add_argument("--font", help="path to a .ttf (use a Thai-capable font for Thai text)")
    p.add_argument("--save-preview", metavar="PNG", help="also save the rendered image")
    return ap


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def apply_model(args):
    """Fill defaults from the --model profile; explicit flags win. Returns the profile or None."""
    prof = models.get(getattr(args, "model", None))
    if prof:
        args.name = list(args.name) + list(prof.names)
        if args.size is None:
            args.size = prof.size
    if hasattr(args, "max_seconds") and args.max_seconds is None:
        args.max_seconds = prof.video_max_s if prof else media.MAX_SECONDS
    args.still_mode = args.nn20_still or (prof.still_mode if prof else "gif")
    return prof


def make_job(args):
    circ = not args.square
    apply_model(args)
    if args.cmd == "send-image":
        from PIL import Image
        def fn(size):
            with Image.open(args.path) as im:
                return [media.fit_square(im, size, circ)], 0
        return client.Job("still", fn, quality=args.quality, still_mode=args.still_mode)
    if args.cmd == "send-text":
        def fn(size):
            im = media.render_text(args.text, args.subtitle, size, _hex(args.fg), _hex(args.bg), args.font, circ)
            if args.save_preview:
                im.save(args.save_preview)
            return [im], 0
        return client.Job("still", fn, name="text.jpg", still_mode=args.still_mode)
    if args.cmd == "send-gif":
        return client.Job("anim", lambda size: media.load_gif_frames(args.path, size, circ, args.max_seconds), name="anim.avi")
    return client.Job("anim", lambda size: _video(args, size, circ), name="video.avi")


def _video(args, size, circ):
    frames = media.load_video_frames(args.path, size, circ, args.fps, args.max_seconds)
    return frames, 1000 // args.fps


def _wifi_dump(path, log_events, payload):
    with open(path, "w") as fh:
        fh.write("# rebeambox wifi dry run: W = written by us, N = simulated badge reply\n")
        fh.write("# columns: direction, connection, length, bytes (long writes truncated to 64 bytes in this log)\n")
        for d, name, b in log_events:
            fh.write("%s %s %d %s%s\n" % (d, name, len(b), b[:64].hex(" ").upper(), " ..." if len(b) > 64 else ""))
    with open(path + ".payload", "wb") as fh:
        fh.write(payload)


def _stream_frames(args):
    frames = media.load_video_frames(args.path, wifi.WIFI_SIZE, not args.square, max(1, round(args.fps)), args.max_seconds) \
        if not args.path.lower().endswith(".gif") else media.load_gif_frames(args.path, wifi.WIFI_SIZE, not args.square, args.max_seconds)[0]
    return [wifi.jpeg_under(f) for f in frames]


async def _run_wifi(args, log):
    prof = models.get(getattr(args, "model", None))
    if prof and args.size == prof.size:
        args.size = None          # the profile size is a BLE value; Wi-Fi uses 360 unless --size is given
    pace = not args.dry_run
    events = []
    if args.dry_run:
        badge = sim.SimWifiBadge()
        mk = lambda name: wifi.SimChannel(badge, name, events)
    else:
        mk = lambda name: wifi.TcpChannel()
    if args.cmd == "stream":
        frames = _stream_frames(args)
        s = wifi.WifiSession(mk, args.host, args.port, log, pace)
        n = await s.stream(frames, args.fps)
        log("sent %d frames" % n)
        payload = b"".join(frames)
    else:
        payload = await client.send_wifi(make_job(args), mk, args.host, args.port, args.size, args.wifi_still, log,
                                         None if args.quiet else (lambda p: print("\r%3d%%" % p, end="", file=sys.stderr)), pace)
    if args.dry_run:
        _wifi_dump(args.dry_run, events, payload)
        log("wrote %d events to %s (payload %d bytes in %s.payload)" % (len(events), args.dry_run, len(payload), args.dry_run))
    return 0


async def _run_send(args):
    log = (lambda *_: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    if args.cmd == "stream" or args.transport == "wifi":
        apply_model(args)
        return await _run_wifi(args, log)
    job = make_job(args)
    if args.dry_run:
        tr = args.transport or ("nn20" if args.model else "badge")
        badge = sim.SimNn20() if tr == "nn20" else sim.SimBadgeSdk(picture=tuple(args.pic))
        lk = link.RecordingLink(badge)
        payload = await client.send(lk, job, tr,
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
            if args.model:
                args.name = list(args.name) + list(models.get(args.model).names)
            res = asyncio.run(scanmod.scan(args.timeout, args.name, args.all))
            for d in res:
                a = d["adv"]
                extra = " %s/%s" % (a["kind"], a["shape"]) if a else ""
                print("%s  %-24s rssi %s%s%s" % (d["address"], d["name"], d["rssi"], extra, "" if d["match"] else "  (no match)"))
            if not res:
                print("no badges found")
            return 0
        return asyncio.run(_run_send(args))
    except media.MediaError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        hint = "no Bluetooth adapter or BlueZ/D-Bus not available" if "No such file" in str(e) and not getattr(e, "filename", None) else "file not found"
        print("error: %s (%s)" % (hint, e), file=sys.stderr)
        return 1
    except Exception as e:
        print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
