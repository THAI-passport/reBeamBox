"""Command line: python -m rebeambox <scan|send-image|send-gif|send-video|send-text>."""
import argparse
import asyncio
import sys

from . import __version__, client, link, media, models, safewrite, session, scan as scanmod, sim, streaming, wifi


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
    p.add_argument("--packet-interval-ms", type=float, default=20.0, help="nn20 gap between packets in ms (default 20)")
    p.add_argument("--post-upload-hold-s", type=float, default=None, help="nn20: seconds to stay connected after an upload so the badge shows it at once (default %.0f, 0 = off)" % session.POST_UPLOAD_HOLD_S)
    p.add_argument("--ack-batch-size", type=int, default=4, help="nn20 ACK mode: packets per batch (default 4, falls back to 1 after errors)")
    g = p.add_argument_group("safe-write policy (flash protection, docs/safe-write.md; not applied to --dry-run)")
    g.add_argument("--min-interval-s", type=float, default=safewrite.DEFAULT_MIN_INTERVAL_S, help="minimum seconds between writes to one badge (default 30)")
    g.add_argument("--warn-per-day", type=int, default=safewrite.DEFAULT_WARN_PER_DAY, help="warn above this many writes in 24 h (default 40, 0 = off)")
    g.add_argument("--max-per-day", type=int, default=safewrite.DEFAULT_MAX_PER_DAY, help="hard cap on writes per badge in 24 h (default 50, 0 = no cap)")
    g.add_argument("--warn-total", type=int, default=safewrite.DEFAULT_WARN_TOTAL, help="warn above this many writes per badge (default 10000, 0 = off)")
    g.add_argument("--force", action="store_true", help="ignore the minimum interval and the unchanged-image skip")
    g.add_argument("--no-delta", action="store_true", help="do not skip an upload identical to the last one")
    g.add_argument("--no-safe-write", action="store_true", help="turn the whole policy off (no counting either)")
    g.add_argument("--badge-id", help="name the badge for the counter (default: its address, or the Wi-Fi host)")
    g.add_argument("--state-dir", help="where the counter file lives (default ~/.local/state/rebeambox or $REBEAMBOX_STATE_DIR)")
    p.add_argument("--quiet", action="store_true")


def make_gate(args, badge_id, log):
    if args.dry_run or args.no_safe_write:
        return None
    pol = safewrite.Policy(True, args.force, not args.no_delta, args.min_interval_s, args.warn_per_day, args.warn_total, args.max_per_day)
    return safewrite.Gate(args.badge_id or badge_id, pol, safewrite.Store(args.state_dir), log=log)


def build_parser():
    ap = argparse.ArgumentParser(prog="rebeambox", description="Open client for Beambox-style round badges (untested on hardware).")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="list nearby badges")
    s.add_argument("--name", action="append", default=[])
    s.add_argument("--timeout", type=float, default=8.0)
    s.add_argument("--all", action="store_true", help="show every device")
    s.add_argument("--model", choices=sorted(models.PROFILES))
    p = sub.add_parser("probe", help="connect and dump GATT services (use for the first-session record)")
    p.add_argument("address", nargs="?"); p.add_argument("--json", help="also write the dump to this file")
    p.add_argument("--qualify", action="store_true", help="first-contact qualification: scan, MTU, GATT, transport, read-only handshake, write a report")
    p.add_argument("--model", choices=sorted(models.PROFILES)); p.add_argument("--name", action="append", default=[])
    p.add_argument("--timeout", type=float, default=8.0, help="scan seconds")
    p.add_argument("--report-dir", default="reports"); p.add_argument("--no-redact", action="store_true", help="keep the full Bluetooth address in the report")
    p.add_argument("--no-wifi-check", action="store_true"); p.add_argument("--wait", type=float, default=3.0, help="seconds to wait for the handshake reply")
    p.add_argument("--simulate", choices=["nn20", "badge"], help="run against a software badge (no Bluetooth)")
    p = sub.add_parser("uploads", help="show or reset the local upload counter used by the safe-write policy")
    p.add_argument("--state-dir"); p.add_argument("--reset", action="store_true", help="forget all counts and hashes")
    p = sub.add_parser("send-image", help="send a JPG/PNG still"); p.add_argument("path"); _add_common(p)
    p.add_argument("--quality", type=int, default=90)
    p = sub.add_parser("send-gif", help="send an animated GIF"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=None, help="cap in seconds (default 3, or the --model profile)")
    p = sub.add_parser("send-video", help="send a video (first 3 s)"); p.add_argument("path"); _add_common(p)
    p.add_argument("--max-seconds", type=float, default=None, help="cap in seconds (default 3, or the --model profile)")
    p.add_argument("--fps", type=int, default=15)
    p = sub.add_parser("stream", help="stream frames from a video, GIF or 'synthetic': Wi-Fi camera mode (default) or BLE clips (--transport nn20|badge)")
    p.add_argument("path", help="video or GIF file, or the word synthetic for a generated test pattern"); _add_common(p)
    p.add_argument("--fps", type=float, default=2.0, help="target frames per second (Wi-Fi is capped at 3.3 by the app's 300 ms spacing)")
    p.add_argument("--source-fps", type=float, default=10.0, help="frame rate of the synthetic source or of video decoding")
    p.add_argument("--max-seconds", type=float, default=10.0)
    p.add_argument("--segment-frames", type=int, default=6, help="BLE only: frames per clip (each clip is a flash write)")
    p = sub.add_parser("send-text", help="render text or a name tag and send it"); p.add_argument("text"); _add_common(p)
    p.add_argument("--subtitle"); p.add_argument("--fg", default="#ffffff"); p.add_argument("--bg", default="#000000")
    p.add_argument("--font", help="path to a .ttf (use a Thai-capable font for Thai text)")
    p.add_argument("--save-preview", metavar="PNG", help="also save the rendered image")
    return ap


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def check_pacing(args):
    if getattr(args, "packet_interval_ms", 20) < 0 or getattr(args, "ack_batch_size", 4) < 1:
        raise ValueError("--packet-interval-ms must be >= 0 and --ack-batch-size >= 1")


def apply_model(args):
    """Fill defaults from the --model profile; explicit flags win. Returns the profile or None."""
    prof = models.get(getattr(args, "model", None))
    if prof:
        args.name = list(args.name) + list(prof.names)
        # The profile size is only the fallback inside the client (368 when the badge reports nothing); it must not
        # override the size the badge reports, so args.size stays None unless --size is given.
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


async def _find_address(args, log):
    from .scan import scan
    if args.address:
        return args.address
    found = [d for d in await scan(args.timeout, args.name) if d["match"]]
    if not found:
        return None
    log("using %s (%s)" % (found[0]["name"], found[0]["address"]))
    return found[0]["address"]


async def _run_stream(args, log):
    apply_model(args)
    transport = args.transport or "wifi"
    dry = bool(args.dry_run)
    clock = streaming.VirtualClock() if dry else streaming.RealClock()
    src = streaming.open_source(args.path, args.source_fps, args.max_seconds)
    events, sink = [], None
    if transport == "wifi":
        if dry:
            badge = sim.SimWifiBadge()
            mk = lambda name: wifi.SimChannel(badge, name, events)
        else:
            mk = lambda name: wifi.TcpChannel()
        sess = wifi.WifiSession(mk, args.host, args.port, log, pace=not dry)
        sink = streaming.WifiSink(sess.live(), clock, streaming.WIFI_MODEL if dry else None)
        if args.size:
            sink.size = args.size
    else:
        size = args.size or 368
        if dry:
            lks = []

            async def open_link():
                lk = link.RecordingLink(sim.SimNn20() if transport == "nn20" else sim.SimBadgeSdk(picture=tuple(args.pic)))
                lks.append(lk)
                return lk
            gate = None
        else:
            addr = await _find_address(args, log)
            if not addr:
                print("no badge found; press the badge Bluetooth button, or pass --address / --name", file=sys.stderr)
                return 2

            async def open_link():
                lk = link.BleakLink(addr)
                await lk.connect()
                return lk
            gate = make_gate(args, addr, log)
        period_ms = int(round(1000.0 / args.fps))
        sink = streaming.BleSegmentSink(streaming.clip_uploader(open_link, transport, size, gate, log, fast=dry), clock,
                                        args.segment_frames, period_ms, streaming.BLE_MODEL if dry else None, size)
    pipe = streaming.Pipeline(src, sink, args.fps, not args.square, clock)
    st = await pipe.run()
    print(st.summary())
    if dry:
        if transport == "wifi":
            _wifi_dump(args.dry_run, events, b"".join(sink.sent_jpegs))
        else:
            with open(args.dry_run, "w") as fh:
                fh.write("# rebeambox stream dry run (%d clips): W = written by us, N = simulated badge notification\n" % len(lks))
                for i, lk in enumerate(lks):
                    fh.write("# clip %d\n" % (i + 1))
                    fh.write(lk.dump())
            with open(args.dry_run + ".payload", "wb") as fh:
                fh.write(sink.payloads[-1] if sink.payloads else b"")
        log("wrote %s" % args.dry_run)
    return 0


async def _run_wifi(args, log):
    prof = models.get(getattr(args, "model", None))
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
                                         None if args.quiet else (lambda p: print("\r%3d%%" % p, end="", file=sys.stderr)), pace,
                                         gate=make_gate(args, "wifi:%s:%s" % (args.host, args.port), log))
    if args.dry_run:
        _wifi_dump(args.dry_run, events, payload)
        log("wrote %d events to %s (payload %d bytes in %s.payload)" % (len(events), args.dry_run, len(payload), args.dry_run))
    return 0


async def _run_send(args):
    check_pacing(args)
    log = (lambda *_: None) if args.quiet else (lambda m: print(m, file=sys.stderr))
    if args.cmd == "stream":
        return await _run_stream(args, log)
    if args.transport == "wifi":
        apply_model(args)
        return await _run_wifi(args, log)
    job = make_job(args)
    if args.dry_run:
        tr = args.transport or ("nn20" if args.model else "badge")
        badge = sim.SimNn20() if tr == "nn20" else sim.SimBadgeSdk(picture=tuple(args.pic))
        lk = link.RecordingLink(badge)
        payload = await client.send(lk, job, tr,
                                    args.size, log, fast=True, packet_interval_ms=args.packet_interval_ms,
                                    ack_batch_size=args.ack_batch_size)
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
    gate = make_gate(args, addr, log)
    lk = link.BleakLink(addr)
    await lk.connect()
    try:
        await client.send(lk, job, args.transport, args.size, log, progress=None if args.quiet else
                          (lambda p: print("\r%3d%%" % p, end="", file=sys.stderr)),
                          packet_interval_ms=args.packet_interval_ms, ack_batch_size=args.ack_batch_size, gate=gate,
                          hold_s=args.post_upload_hold_s)
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
                print("    services: %s  manufacturer: %s" % (", ".join(d["services"]) or "-", d["mfr"] or "-"))
            if not res:
                print("no badges found")
            return 0
        if args.cmd == "probe" and args.qualify:
            from . import qualify
            path, res = asyncio.run(qualify.run(args.address, args.name, args.model, args.timeout, args.simulate, args.report_dir,
                                                args.no_redact, not args.no_wifi_check, args.wait,
                                                command="rebeambox " + " ".join(sys.argv[1:] if argv is None else argv)))
            print("%s: transport %s, report %s" % (res["verdict"], res["transport"], path))
            return 1 if res["verdict"] == "FAIL" else 0
        if args.cmd == "probe":
            if not args.address:
                print("error: probe needs an address (or use --qualify)", file=sys.stderr)
                return 2
            import json
            res = asyncio.run(scanmod.probe(args.address))
            text = json.dumps(res, indent=2)
            print(text)
            if args.json:
                open(args.json, "w").write(text)
            return 0
        if args.cmd == "uploads":
            st = safewrite.Store(args.state_dir)
            if args.reset:
                st.reset()
                print("upload counter cleared")
            print(safewrite.report(st))
            return 0
        return asyncio.run(_run_send(args))
    except safewrite.Skipped as e:
        print("skipped: %s (use --force to write anyway)" % e, file=sys.stderr)
        return 0
    except safewrite.Blocked as e:
        print("not sent: %s" % e, file=sys.stderr)
        return 2
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
