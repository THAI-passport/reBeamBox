from rebeambox import rcsp

def test_crc16_check_value():
    assert rcsp.crc16_xmodem(b"123456789") == 0x31C3

def test_pack_unpack_roundtrip():
    f = rcsp.start_large_file(5, 1000, 0xBEEF, b"/a.tmp\x00")
    d, rest = rcsp.unpack(f)
    assert rest == b"" and d["opcode"] == 0x1B and d["command"] and d["want_response"] and d["sn"] == 5
    assert d["payload"] == bytes.fromhex("000003e8beef") + b"/a.tmp\x00"

def test_known_frames():
    assert rcsp.prepare_env_large_file(1).hex() == "fedcbac021000201" + "00" + "ef"
    assert rcsp.device_extend_file_transfer(2, 0x11223344).hex() == "fedcbac0270007" + "02" + "00" + "11223344" + "01" + "ef"
    assert rcsp.get_target_info(3).hex() == "fedcbac0030006" + "03" + "ffffffff" + "00" + "ef"
    assert rcsp.get_storage_info(4).hex() == "fedcbac0070006" + "04" + "ff" + "00000004" + "ef"

def test_data_chunk_layout():
    data = bytes(range(10))
    fr = rcsp.data_chunks(data, 0, 10, 4, True, 9)
    assert len(fr) == 3
    d, _ = rcsp.unpack(fr[0])
    assert d["opcode"] == 1 and d["xm_opcode"] == 0x1D and not d["want_response"]
    assert d["payload"][0] == 0 and d["payload"][3:] == bytes([0, 1, 2, 3])
    assert int.from_bytes(d["payload"][1:3], "big") == rcsp.crc16_xmodem(bytes([0, 1, 2, 3]))
    d2, _ = rcsp.unpack(rcsp.data_chunks(data, 0, 10, 4, False, 9)[0])
    assert d2["payload"] == b"\x00" + bytes([0, 1, 2, 3])

def test_name_encodings():
    assert rcsp.get_name_response_payload("a.jpg") == b"a.jpg\x00\x00"
    assert rcsp.get_name_response_payload("a.jpg", 1) == b"a001.jpg\x00\x00"
    long_ = rcsp.get_name_response_payload("holiday_photo.jpg")
    assert long_ == b"\\U" + "holiday_photo.jpg".encode("utf-16-le") + b"\x00\x00"

def test_temp_name_hash():
    # Java: "ab1".hashCode() == 96354 -> "00017962"? computed below by reference
    h = 0
    for ch in "photo.jpg1700000000000":
        h = (31 * h + ord(ch)) & 0xFFFFFFFF
    assert rcsp.temp_name_payload("photo.jpg", 1700000000000) == ("%08x.tmp\0" % h).encode()

def test_parsers():
    assert rcsp.parse_start_response(bytes.fromhex("0200")) == 512
    assert rcsp.parse_read_request(bytes.fromhex("00" + "0200" + "00000400")) == (1024, 512)
