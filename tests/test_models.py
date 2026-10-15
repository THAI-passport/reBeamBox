import argparse
import pytest
from rebeambox import cli, models, scan

def parse(argv):
    return cli.build_parser().parse_args(argv)

def test_profiles_exist_and_are_consistent():
    assert set(models.PROFILES) == {"nikko", "nano", "niji"}
    assert models.get("NIJI").video_max_s == 5.0           # code: trimmer caps NIJI at 5 s
    assert models.get("nikko").video_max_s == 10.0          # [H] Pulse plays a 10 s clip (problem 90)
    assert all(p.size == 368 for p in models.PROFILES.values())
    assert models.get("pulse") is None

def test_model_defaults_applied_and_overridable():
    a = parse(["send-video", "x.mp4", "--model", "niji"]); cli.apply_model(a)
    assert a.max_seconds == 5.0 and a.size is None and "Niji" in a.name and "E-badge" in a.name
    a = parse(["send-video", "x.mp4", "--model", "niji", "--max-seconds", "2", "--size", "360"]); cli.apply_model(a)
    assert a.max_seconds == 2.0 and a.size == 360
    a = parse(["send-gif", "x.gif"]); cli.apply_model(a)
    assert a.max_seconds == 3.0 and a.still_mode == "gif" and a.size is None
    a = parse(["send-image", "x.png", "--nn20-still", "album"]); cli.apply_model(a)
    assert a.still_mode == "album"

def test_names_seen_on_hardware_match():
    assert scan.name_matches("E-badge")
    assert not scan.name_matches("Nikko-badge(BLE)")                   # the app hides BLE-suffixed names
    assert scan.name_matches("Nikko-badge(BLE)", extra=models.get("nikko").names)

def test_model_dry_run(tmp_path):
    from PIL import Image
    img = tmp_path / "a.png"; Image.new("RGB", (50, 50), (1, 2, 3)).save(img)
    out = tmp_path / "o.txt"
    assert cli.main(["send-image", str(img), "--model", "nano", "--dry-run", str(out), "--transport", "nn20", "--quiet"]) == 0
    assert (tmp_path / "o.txt.payload").read_bytes()[:4] == bytes.fromhex("78563412")


def test_model_does_not_override_the_size_the_badge_reports(monkeypatch, tmp_path):
    from PIL import Image
    seen = {}

    async def fake_send(lk, job, transport, size, *a, **k):
        seen["size"] = size
        return b""
    monkeypatch.setattr(cli.client, "send", fake_send)
    img = tmp_path / "i.png"
    Image.new("RGB", (8, 8)).save(img)
    assert cli.main(["send-image", str(img), "--model", "nikko", "--dry-run", str(tmp_path / "o.txt"), "--quiet"]) == 0
    assert seen["size"] is None                      # client then uses what the badge reports, 368 only as the last fallback
