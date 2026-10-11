"""probe --qualify: transport detection, read-only handshake, report layout."""
import asyncio
import os

import pytest

from rebeambox import cli, control, link, nn20, qualify, sim


def run(c):
    return asyncio.run(c)


def test_redact():
    assert qualify.redact("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:xx:xx:xx"
    assert qualify.redact("12345678-1234-1234-1234-123456789012").endswith("-xxxx")


@pytest.mark.parametrize("uuids,expected", [
    ([nn20.SERVICE], "nn20"), ([control.SERVICE], "badge"), (["0000ae00-0000-1000-8000-00805f9b34fb"], "badge"),
    ([nn20.SERVICE, control.SERVICE], "both"), (["0000180f-0000-1000-8000-00805f9b34fb"], "none"), ([], "none")])
def test_classify(uuids, expected):
    assert qualify.classify_services(uuids) == expected


def _qual(tmp_path, kind, **kw):
    return run(qualify.run(simulate=kind, report_dir=str(tmp_path), do_wifi=False, wait=0.5, **kw))


@pytest.mark.parametrize("kind,transport", [("nn20", "nn20"), ("badge", "badge")])
def test_simulated_qualify_passes_and_writes_report(tmp_path, kind, transport):
    path, res = _qual(tmp_path, kind)
    assert res["transport"] == transport and res["verdict"] == "PASS"
    text = open(path).read()
    assert os.path.basename(path).startswith("first-contact-") and path.endswith(".md")
    for field in ("test id (H1..H7):", "PASS / FAIL / PARTIAL:", "measured values", "observations", "code or doc change needed:"):
        assert field in text
    assert "xx:xx:xx" in text and "## GATT" in text


def test_nn20_handshake_reads_status_and_writes_nothing(tmp_path):
    b = sim.SimNn20(size="360,360")
    lk = link.RecordingLink(b)
    r = run(qualify.handshake_nn20(lk, 0.5))
    assert r["ok"] and r["status"]["size"] == "360,360"
    assert not [e for e in lk.events if e[0] == "W"]


def test_badge_handshake_sends_only_the_info_query():
    lk = link.RecordingLink(sim.SimBadgeSdk())
    r = run(qualify.handshake_badge(lk, 0.5))
    writes = [e for e in lk.events if e[0] == "W"]
    assert r["ok"] and len(writes) == 1
    f, _ = control.parse_stream(writes[0][2])
    assert f[0]["cmd"] == control.CMD_INFO


def test_silent_badge_gives_partial():
    class Silent(sim.SimNn20):
        def on_subscribe(self, uuid):
            pass
    lk = link.RecordingLink(Silent())
    hs = run(qualify.handshake_nn20(lk, 0.2))
    assert not hs["ok"]
    assert qualify.verdict({"transport": "nn20", "services": [1], "handshake": hs}) == "PARTIAL"
    assert qualify.verdict({"transport": "none", "services": []}) == "FAIL"
    assert qualify.verdict({"error": "x", "transport": "none"}) == "FAIL"


def test_wifi_probe_injected_is_reported(tmp_path):
    async def probe():
        return {"ssids_checked": True, "ssid_hits": ["E-Badge-1234"], "tcp_8080": True}
    path, res = run(qualify.run(simulate="nn20", report_dir=str(tmp_path), wait=0.3, wifi_probe=probe))
    text = open(path).read()
    assert "E-Badge-1234" in text and "reachable" in text


def test_wifi_check_uses_injected_helpers():
    async def tcp():
        return False
    r = run(qualify.wifi_check(lambda: ["home", "E-Badge-77"], tcp))
    assert r["ssid_hits"] == ["E-Badge-77"] and r["tcp_8080"] is False
    r = run(qualify.wifi_check(lambda: None, tcp))
    assert r["ssids_checked"] is False


def test_cli_qualify_simulated(tmp_path, capsys):
    rc = cli.main(["probe", "--qualify", "--simulate", "nn20", "--report-dir", str(tmp_path), "--no-wifi-check", "--wait", "0.5"])
    assert rc == 0 and "PASS" in capsys.readouterr().out
    assert len(list(tmp_path.glob("first-contact-*.md"))) == 1


def test_cli_probe_without_address_or_qualify(capsys):
    assert cli.main(["probe"]) == 2
