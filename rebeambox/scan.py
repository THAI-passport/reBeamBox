"""Scanning and name filtering. Mirrors the app: skip names containing BLE, accept NEO / B-Device
(case and punctuation insensitive substring) plus any configured names."""
import re
import struct

DEFAULT_NAMES = ("NEO", "B-Device", "E-badge")
DEVICE_TAGS = {0xB9: "watch",  # [C] smali of the app: WATCH is 0xB9 (an earlier version of this table said 0xB5)
               0xB0: "phone case", 0xB1: "alarm clock", 0xB2: "speaker", 0xB3: "badge"}
SHAPES = {0x6C: "square", 0x6D: "circle"}


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def name_matches(name, extra=(), defaults=DEFAULT_NAMES):
    if not name or not name.strip():
        return False
    n = norm(name)
    for e in extra:
        if norm(e) and norm(e) in n:
            return True
    if "BLE" in name.upper():
        return False
    return any(norm(d) in n for d in defaults)


def parse_adv(raw):
    """Manufacturer-specific AD payload (company id bytes included) -> dict or None. Needs >= 10 bytes."""
    if raw is None or len(raw) < 10:
        return None
    return {"tag": raw[0], "kind": DEVICE_TAGS.get(raw[0], "unknown"), "shape": SHAPES.get(raw[1], "unknown"),
            "id": ":".join("%02X" % b for b in raw[2:8]), "project": struct.unpack("<H", raw[8:10])[0]}


def adv_from_bleak(manufacturer_data):
    """bleak splits the first two payload bytes off as the company id; put them back (little endian)."""
    for cid, data in (manufacturer_data or {}).items():
        a = parse_adv(struct.pack("<H", cid) + bytes(data))
        if a:
            return a
    return None


async def scan(timeout=6.0, extra=(), all_devices=False):
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for addr, (dev, adv) in found.items():
        name = adv.local_name or dev.name
        a = adv_from_bleak(adv.manufacturer_data)
        match = name_matches(name, extra) or (a is not None and a["tag"] == 0xB3)
        if match or all_devices:
            out.append({"name": name, "address": addr, "rssi": adv.rssi, "adv": a, "match": match,
                        "services": [s for s in adv.service_uuids],
                        "mfr": {("0x%04X" % k): v.hex() for k, v in adv.manufacturer_data.items()}})
    out.sort(key=lambda d: -(d["rssi"] or -999))
    return out


async def probe(address, timeout=15.0):
    """Connect and list every service, characteristic, property and readable value (like an nRF Connect export)."""
    from bleak import BleakClient
    out = []
    async with BleakClient(address, timeout=timeout) as c:
        out.append({"mtu": getattr(c, "mtu_size", None)})
        for svc in c.services:
            item = {"service": str(svc.uuid), "characteristics": []}
            for ch in svc.characteristics:
                e = {"uuid": str(ch.uuid), "properties": list(ch.properties), "handle": ch.handle,
                     "descriptors": [str(d.uuid) for d in ch.descriptors]}
                if "read" in ch.properties:
                    try:
                        e["value"] = bytes(await c.read_gatt_char(ch)).hex()
                    except Exception as ex:
                        e["value_error"] = str(ex)
                item["characteristics"].append(e)
            out.append(item)
    return out
