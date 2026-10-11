"""Software test 3 (docs/software-test-v1.md): auth fuzzing. Python E1 against the native arm64 library run under
the unicorn emulator. The library is not in the repo; the test skips unless unicorn, pyelftools and the .so are
available (default path analysis/work/so/lib/arm64-v8a/libjl_auth.so, or set JL_AUTH_SO).
Counts: default 20 (REBEAMBOX_FUZZ_N), larger run with `pytest -m slow` (REBEAMBOX_FUZZ_SLOW_N, default 500)."""
import importlib.util
import os
import random

import pytest

from rebeambox import jl_auth as J

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.environ.get("JL_AUTH_SO") or os.path.join(ROOT, "analysis", "work", "so", "lib", "arm64-v8a", "libjl_auth.so")
N = int(os.environ.get("REBEAMBOX_FUZZ_N", "20"))
N_SLOW = int(os.environ.get("REBEAMBOX_FUZZ_SLOW_N", "500"))


def _emulator_module():
    pytest.importorskip("unicorn")
    pytest.importorskip("elftools")
    if not os.path.exists(LIB):
        pytest.skip("libjl_auth.so not present (set JL_AUTH_SO)")
    spec = importlib.util.spec_from_file_location("emulate_jl_auth", os.path.join(ROOT, "tools", "emulate_jl_auth.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fuzz(count, seed):
    emu = _emulator_module()
    rng = random.Random(seed)
    mu = emu.load(LIB)
    for i in range(count):
        if i and i % 25 == 0:
            mu = emu.load(LIB)                     # fresh heap, the emulator's bump allocator never frees
        rand = bytes(rng.randrange(256) for _ in range(16))
        if i % 4 == 0:                             # default key and fixed address, as used on the wire
            key, addr = J.DEFAULT_KEY, J.FIXED_ADDR
        else:                                      # arbitrary key and address (cipher correctness, not just the constants)
            key = bytes(rng.randrange(256) for _ in range(16))
            addr = bytes(rng.randrange(256) for _ in range(6))
        assert J.e1(addr, rand, key) == emu.e1(mu, addr, rand, key), "mismatch for rand=%s key=%s addr=%s" % (
            rand.hex(), key.hex(), addr.hex())


def test_native_vs_python_random_challenges():
    _fuzz(N, 1)


@pytest.mark.slow
def test_native_vs_python_random_challenges_large():
    _fuzz(N_SLOW, 2)


def test_python_e1_shape_and_determinism():
    rng = random.Random(3)
    for _ in range(100):
        rand = bytes(rng.randrange(256) for _ in range(16))
        a = J.e1(J.FIXED_ADDR, rand, J.DEFAULT_KEY)
        assert len(a) == 16 and a == J.e1(J.FIXED_ADDR, rand, J.DEFAULT_KEY)


def test_python_e1_avalanche_on_challenge_bit_flip():
    rng = random.Random(4)
    for _ in range(50):
        rand = bytearray(rng.randrange(256) for _ in range(16))
        base = J.e1(J.FIXED_ADDR, bytes(rand), J.DEFAULT_KEY)
        rand[rng.randrange(16)] ^= 1 << rng.randrange(8)
        other = J.e1(J.FIXED_ADDR, bytes(rand), J.DEFAULT_KEY)
        diff = sum(bin(a ^ b).count("1") for a, b in zip(base, other))
        assert diff >= 16                          # 128 output bits, a good cipher flips about half


def test_encrypt_challenge_matches_e1_for_random_challenges():
    rng = random.Random(5)
    for _ in range(50):
        c = b"\x00" + bytes(rng.randrange(256) for _ in range(16))
        out = J.encrypt_challenge(c)
        assert out[0] == 1 and out[1:] == J.e1(J.FIXED_ADDR, c[1:], J.DEFAULT_KEY) and len(out) == 17
    ch = J.random_challenge()
    assert len(ch) == 17 and ch[0] == 0
    with pytest.raises(ValueError):
        J.encrypt_challenge(bytes(16))


def test_key_and_address_change_the_answer():
    r = bytes(range(16))
    base = J.e1(J.FIXED_ADDR, r, J.DEFAULT_KEY)
    assert J.e1(J.FIXED_ADDR, r, bytes(16)) != base
    assert J.e1(bytes(6), r, J.DEFAULT_KEY) != base
