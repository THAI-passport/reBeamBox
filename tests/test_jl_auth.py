from rebeambox import jl_auth as J

# Vectors produced by emulating the native function_E1test of libjl_auth.so (arm64) under unicorn.
VEC = [
    ("00000000000000000000000000000000", "9e43df377b3a46ce751634667e215de5"),
    ("000102030405060708090a0b0c0d0e0f", "e5807e887bde07630b4d0e715b3e8991"),
    ("00112233445566778899aabbccddeeff", "26a69c072324c5e660c28ff912dcd857"),
    ("2291d8cdc310411e7ec27378a661c935", "223d39bf2b97f1ff9a650052be0d99dc"),
]

def test_e1_default_key():
    for r, out in VEC:
        assert J.e1(J.FIXED_ADDR, bytes.fromhex(r), J.DEFAULT_KEY).hex() == out

def test_e1_custom_key_and_addr():
    k = bytes(range(0x10, 0x20)); a = bytes.fromhex("a1b2c3d4e5f6")
    assert J.e1(a, bytes(range(16)), k).hex() == "16b0e5f913881954a73188c9d9f69c07"

def test_encrypt_challenge_frame():
    c = b"\x00" + bytes(16)
    assert J.encrypt_challenge(c) == b"\x01" + bytes.fromhex(VEC[0][1])
