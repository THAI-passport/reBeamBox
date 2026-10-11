"""First-contact qualification: identify the transport of an unknown badge without changing anything on it.

Steps (each failure is recorded, the report is always written):
  1. find the badge in the advertisements (name filter or address)
  2. connect, read the negotiated MTU, enumerate GATT
  3. decide the transport: nn20 (0x01F0), BadgeSdk (C2E6FD00 or 0xAE00), both, or none
  4. non-destructive handshake: nn20 = listen on 0x01F2 for the pushed status JSON (nothing is written);
     BadgeSdk = subscribe and send the read-only info query (0xC6), nothing is stored on the badge
  5. Wi-Fi hint: SSIDs containing E-Badge in the host Wi-Fi list (nmcli, Linux only) and a bare TCP connect
     to 192.168.8.1:8080 (no bytes sent)
  6. write reports/first-contact-<timestamp>.md in the layout of docs/hardware-test-v1.md
"""
import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess

from . import __version__, control, link as linkmod, nn20, scan as scanmod, sim, wifi
from .session import AE00


def redact(addr):
    """Mask the device-specific half of a Bluetooth address before it goes into a report."""
    if re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", addr or ""):
        return ":".join(addr.split(":")[:3] + ["xx"] * 3)
    return (addr[:8] + "-xxxx") if addr else ""


def classify_services(uuids):
    u = {x.lower() for x in uuids}
    nn = nn20.SERVICE.lower() in u
    bd = control.SERVICE.lower() in u or AE00 in u
    if nn and bd:
        return "both"
    return "nn20" if nn else "badge" if bd else "none"


async def handshake_nn20(lk, wait=3.0):
    """Listen for the status JSON the badge pushes on 0x01F2. Writes nothing."""
    raw, status = [], None
    buf = b""

    def on(data):
        nonlocal buf, status
        raw.append(data.hex())
        buf += data
        msgs, buf = nn20.parse_reply_stream(buf)
        for _t, text in msgs:
            if len(text) > 30:
                try:
                    status = json.loads(text)
                except ValueError:
                    pass
    await lk.subscribe(nn20.NOTIFY, on)
    end = asyncio.get_running_loop().time() + wait
    while status is None and asyncio.get_running_loop().time() < end:
        await asyncio.sleep(0.05)
    return {"kind": "nn20 status push on 0x01F2", "ok": status is not None, "status": status, "raw": raw,
            "detail": "status JSON received" if status else "no status JSON within %.1f s (it may need a write to wake it)" % wait}


async def handshake_badge(lk, wait=3.0):
    """Subscribe to the control notify characteristic and send the read-only info query 0xC6."""
    got, buf = [], b""

    def on(data):
        nonlocal buf
        fr, buf = control.parse_stream(buf + data)
        got.extend(fr)
    await lk.subscribe(control.NOTIFY1, on)
    await lk.write(control.WRITE, control.frame(control.CMD_INFO, b"\x01"), response=False)
    end = asyncio.get_running_loop().time() + wait
    info = None
    while info is None and asyncio.get_running_loop().time() < end:
        await asyncio.sleep(0.05)
        for f in got:
            if f["cmd"] == control.CMD_INFO_REPLY:
                info = control.parse_info_reply(f["payload"])
    cmds = sorted({"0x%02X" % f["cmd"] for f in got})
    return {"kind": "control info query 0xC6", "ok": info is not None, "info": info, "commands_seen": cmds,
            "detail": "info reply received" if info else
            "no 0xC7 reply within %.1f s (the badge may need bind 0x60 first); commands seen: %s" % (wait, cmds or "none")}


def list_ssids():
    """Wi-Fi SSIDs visible to the host, or None when it cannot be determined (nmcli only)."""
    if not shutil.which("nmcli"):
        return None
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "SSID", "dev", "wifi"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    return sorted({x for x in out.splitlines() if x})


async def tcp_reachable(host=wifi.HOST, port=wifi.PORT, timeout=1.5):
    try:
        _r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        w.close()
        return True
    except Exception:
        return False


async def wifi_check(ssids=list_ssids, tcp=tcp_reachable):
    names = ssids()
    hits = [s for s in (names or []) if "e-badge" in s.lower() or "ebadge" in s.lower()]
    return {"ssids_checked": names is not None, "ssid_hits": hits, "tcp_8080": bool(await tcp())}


def verdict(res):
    if res.get("error") and not res.get("services"):
        return "FAIL"
    t = res.get("transport", "none")
    if t == "none":
        return "FAIL"
    hs = res.get("handshake") or {}
    return "PASS" if hs.get("ok") else "PARTIAL"


def next_steps(res):
    t = res.get("transport")
    if t == "nn20":
        return ["rebeambox send-image photo.jpg --transport nn20 --address <ADDRESS>   (H2, type 5 default)",
                "rebeambox send-image photo.jpg --transport nn20 --nn20-still album --address <ADDRESS>   (H2, type 6)",
                "adjust --packet-interval-ms / --ack-batch-size if the badge drops packets (H4)"]
    if t in ("badge", "both"):
        return ["rebeambox send-image photo.jpg --transport badge --address <ADDRESS>   (H3 with auth)",
                "capture the vendor app first (HCI snoop) and replay with tools/replay_pcap.py to compare frames"]
    return ["run nRF Connect and attach its export; the badge may use a service this client does not know",
            "try --name <exact advertised name> and a longer --timeout; check the badge is on its pairing screen"]


def render_report(res):
    ad = res.get("adv") or {}
    hs = res.get("handshake") or {}
    w = res.get("wifi") or {}
    v = verdict(res)
    L = []
    L.append("# First contact report")
    L.append("")
    L.append("Generated by `rebeambox probe --qualify` (rebeambox %s). Nothing was written to the badge's storage." % __version__)
    L.append("")
    L.append("```")
    L.append("test id (H1..H7):            H1        model: %s        date: %s" % (res.get("model") or "unknown", res["timestamp"]))
    L.append("badge firmware / app version: %s" % (res.get("firmware") or "unknown (fill in)"))
    L.append("command(s) run:              %s" % res["command"])
    L.append("log file(s) / captures attached: (attach nRF Connect export and HCI snoop log if taken)")
    L.append("measured values (name, services, bytes, seconds, fps):")
    L.append("  name: %s   address: %s   rssi: %s" % (ad.get("name"), res.get("address_shown"), ad.get("rssi")))
    L.append("  advertised services: %s" % (", ".join(ad.get("services") or []) or "-"))
    L.append("  manufacturer data: %s" % (ad.get("mfr") or "-"))
    L.append("  MTU: %s   data bytes per nn20 packet: %s" % (res.get("mtu"), nn20.data_per_packet(res["mtu"]) if res.get("mtu") else "-"))
    L.append("  transport decision: %s" % res.get("transport"))
    L.append("  accepted container (type 5 or type 6): not tested (run H2, then write 'accepted container: type 5' or 'type 6')")
    L.append("  handshake: %s -> %s" % (hs.get("kind", "not run"), "ok" if hs.get("ok") else "no reply"))
    L.append("PASS / FAIL / PARTIAL:       %s" % v)
    L.append("observations (display, sound, reboot, disconnect): %s" % (res.get("observations") or "(fill in what the badge did)"))
    L.append("code or doc change needed:   %s" % ("none identified" if v == "PASS" else "see findings below"))
    L.append("```")
    L.append("")
    L.append("## Findings")
    L.append("")
    L.append("- Name filter match: %s" % ("yes" if ad.get("match") else "no or not scanned"))
    if hs.get("detail"):
        L.append("- Handshake: %s" % hs["detail"])
    if hs.get("status"):
        L.append("- Status JSON keys: %s" % ", ".join(sorted(hs["status"])))
        L.append("- Reported picture size: %s, free space KB: %s, time_mode: %s" % (
            hs["status"].get("size"), hs["status"].get("freespace"), hs["status"].get("time_mode")))
    if hs.get("info"):
        L.append("- Info reply: %s" % hs["info"])
    L.append("- Wi-Fi: SSID check %s; E-Badge SSIDs: %s; TCP %s:%s %s" % (
        "done" if w.get("ssids_checked") else "not possible on this host", w.get("ssid_hits") or "none",
        wifi.HOST, wifi.PORT, "reachable" if w.get("tcp_8080") else "not reachable (expected unless joined to the badge AP)") if w else
        "- Wi-Fi: not checked")
    for e in res.get("errors", []):
        L.append("- Error: %s" % e)
    L.append("")
    L.append("## GATT")
    L.append("")
    for s in res.get("services", []):
        L.append("- service %s" % s["service"])
        for c in s["characteristics"]:
            L.append("  - %s [%s] handle %s" % (c["uuid"], ",".join(c["properties"]), c.get("handle")))
    if not res.get("services"):
        L.append("(none enumerated)")
    L.append("")
    L.append("## Suggested next commands")
    L.append("")
    for n in next_steps(res):
        L.append("- `%s`" % n if n.startswith("rebeambox") else "- %s" % n)
    L.append("")
    L.append("Report in the repository issue \"First session: <model> <date>\" (docs/first-session-checklist.md) and append problems to docs/problem_solution.md.")
    L.append("")
    return "\n".join(L)


def _sim_adv(kind):
    if kind == "nn20":
        return {"name": "E-badge-SIM", "address": "AA:BB:CC:00:00:01", "rssi": -50, "services": [nn20.SERVICE], "mfr": {}, "match": True}
    return {"name": "NEO-SIM", "address": "AA:BB:CC:00:00:02", "rssi": -50, "services": [control.SERVICE], "mfr": {"0x05D6": "b3"}, "match": True}


async def run(address=None, names=(), model=None, timeout=8.0, simulate=None, report_dir="reports", no_redact=False,
              do_wifi=True, wait=3.0, now=None, wifi_probe=None, command="rebeambox probe --qualify", log=lambda *_: None):
    """Run the qualification and write the report. Returns (path, result)."""
    now = now or datetime.datetime.now().astimezone()
    res = {"timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z").strip(), "command": command, "model": model, "errors": []}
    lk = None
    try:
        if simulate:
            res["adv"] = _sim_adv(simulate)
            address = res["adv"]["address"]
            lk = linkmod.RecordingLink(sim.SimNn20() if simulate == "nn20" else sim.SimBadgeSdk())
        else:
            if model:
                from . import models
                names = list(names) + list(models.PROFILES[model].names)
            found = await scanmod.scan(timeout, names, all_devices=bool(address))
            pick = None
            for d in found:
                if (address and d["address"].lower() == address.lower()) or (not address and d["match"]):
                    pick = d
                    break
            if pick is None:
                res["errors"].append("no matching device in the advertisements (%d seen)" % len(found))
                if not address:
                    raise LookupError("badge not found")
            else:
                res["adv"] = pick
                address = pick["address"]
            log("connecting to %s" % address)
            lk = await linkmod.BleakLink(address).connect()
        res["address_shown"] = address if no_redact else redact(address)
        res["mtu"] = lk.mtu
        res["services"] = lk.describe()
        res["transport"] = classify_services(lk.service_uuids())
        log("MTU %s, transport %s" % (lk.mtu, res["transport"]))
        if res["transport"] in ("nn20", "both"):
            res["handshake"] = await handshake_nn20(lk, wait)
        elif res["transport"] == "badge":
            res["handshake"] = await handshake_badge(lk, wait)
    except Exception as e:
        res["errors"].append("%s: %s" % (type(e).__name__, e))
    finally:
        if lk is not None:
            try:
                await lk.close()
            except Exception:
                pass
    res.setdefault("transport", "none")
    res.setdefault("address_shown", redact(address) if address and not no_redact else address)
    if do_wifi:
        try:
            res["wifi"] = await (wifi_probe or wifi_check)()
        except Exception as e:
            res["errors"].append("wifi check: %s" % e)
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, "first-contact-%s.md" % now.strftime("%Y%m%d-%H%M%S"))
    with open(path, "w") as fh:
        fh.write(render_report(res))
    res["verdict"] = verdict(res)
    return path, res
