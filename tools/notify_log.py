#!/usr/bin/env python3
"""Passive notification logger for a real badge: subscribes to every notifiable characteristic and prints what arrives. Writes nothing
to the badge's storage (it only enables notifications, which writes the standard CCCD descriptor).

    python tools/notify_log.py ADDRESS [--seconds 60] [--json out.jsonl]

Use it for hardware task HW-13 (touch events) and to catch anything the badge sends unprompted. Needs bleak and a Bluetooth adapter.
Output lines: seconds-since-start, characteristic uuid, length, hex. The address is never printed in full.
"""
import argparse
import asyncio
import json
import sys
import time


def mask(addr):
    return addr[:-8] + "xx:xx:xx" if len(addr) == 17 and addr.count(":") == 5 else addr[:4] + "..."


async def log_notifications(client, seconds, emit, clock=time.monotonic, sleep=asyncio.sleep):
    """Subscribe on `client` (a connected BleakClient-like object) to every characteristic with notify/indicate; call emit(dict) per event."""
    t0 = clock()
    subscribed = []

    def handler_for(uuid):
        def handler(_sender, data):
            emit({"t": round(clock() - t0, 3), "uuid": uuid, "len": len(data), "hex": bytes(data).hex()})
        return handler

    for svc in client.services:
        for ch in svc.characteristics:
            if "notify" in ch.properties or "indicate" in ch.properties:
                try:
                    await client.start_notify(ch.uuid, handler_for(str(ch.uuid).lower()))
                    subscribed.append(str(ch.uuid).lower())
                except Exception as e:  # noqa: BLE001
                    emit({"t": round(clock() - t0, 3), "uuid": str(ch.uuid).lower(), "error": str(e)})
    await sleep(seconds)
    for u in subscribed:
        try:
            await client.stop_notify(u)
        except Exception:  # noqa: BLE001
            pass
    return subscribed


async def main_async(a):
    from bleak import BleakClient
    out = open(a.json, "w") if a.json else None

    def emit(ev):
        line = ("%8.3f  %s  error: %s" % (ev["t"], ev["uuid"], ev["error"])) if "error" in ev else \
               ("%8.3f  %s  len=%-4d %s" % (ev["t"], ev["uuid"], ev["len"], ev["hex"]))
        print(line, flush=True)
        if out:
            out.write(json.dumps(ev) + "\n")
    print("connecting to %s ..." % mask(a.address))
    async with BleakClient(a.address, timeout=20.0) as client:
        subs = await log_notifications(client, a.seconds, emit)
        print("subscribed to %d characteristic(s): %s" % (len(subs), ", ".join(subs) or "none"))
    if out:
        out.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("address", help="Bluetooth address (macOS: the UUID that `rebeambox scan` prints)")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--json", help="also write one JSON object per event to this file")
    a = ap.parse_args(argv)
    try:
        return asyncio.run(main_async(a))
    except ImportError:
        print("bleak is not installed (pip install bleak)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
