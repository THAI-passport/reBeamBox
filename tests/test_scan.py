from rebeambox import scan

def test_name_filters():
    assert scan.name_matches("NEO-1234") and scan.name_matches("B-Device_ab") and scan.name_matches("b device")
    assert not scan.name_matches("NEO BLE") and not scan.name_matches("Headset") and not scan.name_matches(None)
    assert scan.name_matches("PulseX", extra=["pulse"]) and scan.name_matches("MyPulse BLE", extra=["pulse"])

def test_adv_parse():
    raw = bytes([0xB3, 0x6D, 1, 2, 3, 4, 5, 6, 0x34, 0x12])
    a = scan.parse_adv(raw)
    assert a["kind"] == "badge" and a["shape"] == "circle" and a["id"] == "01:02:03:04:05:06" and a["project"] == 0x1234
    assert scan.parse_adv(raw[:9]) is None
    assert scan.adv_from_bleak({0x6DB3: bytes([1, 2, 3, 4, 5, 6, 0x34, 0x12])})["kind"] == "badge"
