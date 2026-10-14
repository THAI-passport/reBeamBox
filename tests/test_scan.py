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

def test_device_tags_match_the_sdk_enum():
    # tags of the SDK device-type enum (smali, S6): watch 0xB9, phone case 0xB0, alarm clock 0xB1, speaker 0xB2, badge 0xB3
    assert scan.DEVICE_TAGS == {0xB9: "watch", 0xB0: "phone case", 0xB1: "alarm clock", 0xB2: "speaker", 0xB3: "badge"}
    assert scan.parse_adv(bytes([0xB9, 0x6C, 1, 2, 3, 4, 5, 6, 0, 0]))["kind"] == "watch"

def test_client_is_broader_than_the_app_filter_on_purpose():
    # the app hides every name containing BLE, even when the stored signal name matches; the client keeps a name the user gave with --name
    assert scan.name_matches("Nikko-badge(BLE)", extra=["Nikko"])
    assert not scan.name_matches("Nikko-badge(BLE)")
    # the app compares the raw upper-cased name with the signal name, the client ignores punctuation as well
    assert scan.name_matches("E badge") and scan.name_matches("e-badge")
