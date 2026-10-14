#!/usr/bin/env python3
"""Mask personal data in a capture summary (btcap.py --json output or a text dump).

Deterministic and length-preserving, so frame lengths, opcodes, handles and CRC
positions stay where they were:
- Bluetooth addresses (AA:BB:CC:DD:EE:FF or aa-bb-...) -> 02:00:00:00:00:NN, one stable
  pseudonym per distinct address, numbered in order of first appearance.
- Bearer/token/key/password values in text -> same-length run of 'x'.
- --mask TEXT (repeatable): a literal you know is personal (serial, phone number,
  name); masked in plain text, as ASCII hex and as UTF-16LE hex inside payload hex.
  Hex masks keep the length and use 00 bytes, so a CRC over the payload will no
  longer match: the summary says how many payloads were touched.

    python tools/scrub_capture.py in.json -o out.json --mask SN12345 --mask "Alice"

It does not read raw btsnoop/pcap; run tools/btcap.py --json first. Review the
output before committing: a tool cannot know every secret.
"""
import argparse
import re
import sys

MAC = re.compile(r"\b([0-9A-Fa-f]{2})([:-])([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\2([0-9A-Fa-f]{2})\b")
TOKEN = re.compile(r"(?i)((?:bearer\s+|(?:access_?token|refresh_?token|token|api_?key|secret|password|passwd|auth)[\"']?\s*[:=]\s*[\"']?))([A-Za-z0-9._~+/=-]{4,})")


def scrub(text, masks=()):
    seen = {}

    def mac(m):
        key = "".join(m.group(i) for i in (1, 3, 4, 5, 6, 7)).upper()
        n = seen.setdefault(key, len(seen) + 1)
        return m.group(2).join(["02", "00", "00", "00", "%02X" % ((n >> 8) & 0xFF), "%02X" % (n & 0xFF)])

    text = MAC.sub(mac, text)
    text = TOKEN.sub(lambda m: m.group(1) + "x" * len(m.group(2)), text)
    hits = 0
    for s in masks:
        if not s:
            continue
        text = text.replace(s, "x" * len(s))
        for enc in ("ascii", "utf-16-le"):
            try:
                h = s.encode(enc).hex()
            except UnicodeEncodeError:
                continue
            for variant in (h, h.upper()):
                hits += text.count(variant)
                text = text.replace(variant, "00" * (len(variant) // 2))
    return text, len(seen), hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output", help="write here instead of stdout")
    ap.add_argument("--mask", action="append", default=[], help="literal personal string to mask (repeatable)")
    a = ap.parse_args(argv)
    with open(a.input, encoding="utf-8") as f:
        out, macs, hits = scrub(f.read(), a.mask)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
    print("scrub: %d address(es) pseudonymised, %d hex payload match(es) masked (CRCs over those no longer match)" % (macs, hits), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
