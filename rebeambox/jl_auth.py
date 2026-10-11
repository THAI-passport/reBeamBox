"""Jieli RCSP challenge/response ("jl_auth") reference implementation.

Derived from static analysis of libjl_auth.so: the exported function_E1test is the
Bluetooth Core E1 construction on a SAFER+ block cipher (Ar and Ar').
See docs/PROTOCOL.md section on RCSP authentication.
"""
import os

DEFAULT_KEY = bytes.fromhex("06775f87918dd423005df1d8cf0c142b")  # .data default link key
FIXED_ADDR = bytes.fromhex("112233332211")                         # .data constant "address"

EXP = [pow(45, i, 257) % 256 for i in range(256)]
LOG = [0] * 256
for _i in range(256):
    LOG[EXP[_i]] = _i
_BIAS = [[pow(45, pow(45, 17 * p + i + 1, 257), 257) % 256 for i in range(16)] for p in range(2, 18)]
_SHUF = [8, 11, 12, 15, 2, 1, 6, 5, 10, 9, 14, 13, 0, 7, 4, 3]
_NL_EXP = (0, 3, 4, 7, 8, 11, 12, 15)


def _rotl3(b):
    return ((b << 3) | (b >> 5)) & 0xFF


def key_schedule(key):
    """17 round keys (K1..K17), each 16 bytes."""
    k = list(key)
    par = 0
    for b in k:
        par ^= b
    k.append(par)
    keys = [list(key)]
    for r in range(1, 17):
        k = [_rotl3(b) for b in k]
        keys.append([(k[(i + r) % 17] + _BIAS[r - 1][i]) & 0xFF for i in range(16)])
    return keys


def _xor_add(x, k):
    return [(x[i] ^ k[i]) if i % 4 in (0, 3) else (x[i] + k[i]) & 0xFF for i in range(16)]


def _add_xor(x, k):
    return [(x[i] + k[i]) & 0xFF if i % 4 in (0, 3) else (x[i] ^ k[i]) for i in range(16)]


def _pht_layer(x):
    out = []
    for i in range(0, 16, 2):
        a, b = x[i], x[i + 1]
        out += [(2 * a + b) & 0xFF, (a + b) & 0xFF]
    return out


def _linear(x):
    for n in range(4):
        x = _pht_layer(x)
        if n < 3:
            x = [x[_SHUF[i]] for i in range(16)]
    return x


def safer_plus(block, key, prime=False):
    keys = key_schedule(key)
    x = list(block)
    inp = list(block)
    for r in range(8):
        if prime and r == 2:
            x = _xor_add(x, inp)  # round-1 input folded into round-3 input (Ar')
        x = _xor_add(x, keys[2 * r])
        x = [EXP[v] if i in _NL_EXP else LOG[v] for i, v in enumerate(x)]
        x = _add_xor(x, keys[2 * r + 1])
        x = _linear(x)
    return bytes(_xor_add(x, keys[16]))


def e1(addr6, rand16, key16):
    """Native function_E1test(addr, rand, key, out): returns the 16 output bytes."""
    t = safer_plus(rand16, key16)
    mix = bytes(((t[i] ^ rand16[i]) + addr6[i % 6]) & 0xFF for i in range(16))
    return safer_plus(mix, _ktilde_native(key16), prime=True)


def _ktilde_native(key):
    # exactly the byte operations seen at 0x1324-0x13e4 of the native code
    k = list(key)
    ops = [("sub", 0x17), ("xor", 0xE5), ("sub", 0x21), ("xor", 0xC1), ("sub", 0x4D), ("xor", 0xA7),
           ("sub", 0x6B), ("xor", 0x83), ("xor", 0xE9), ("sub", 0x1B), ("xor", 0xDF), ("sub", 0x3F),
           ("xor", 0xB3), ("sub", 0x59), ("xor", 0x95), ("sub", 0x7D)]
    return bytes(((b - v) & 0xFF) if op == "sub" else (b ^ v) for b, (op, v) in zip(k, ops))


def random_challenge():
    return b"\x00" + os.urandom(16)


def encrypt_challenge(challenge17, key=DEFAULT_KEY):
    """getEncryptedAuthData: 17-byte [0x00|rand16] -> 17-byte [0x01|E1(addr,rand,key)]."""
    if len(challenge17) != 17:
        raise ValueError("challenge must be 17 bytes")
    return b"\x01" + e1(FIXED_ADDR, challenge17[1:], key)


AUTH_RESET = bytes.fromhex("FEDCBAC00600020001EF")
AUTH_OK = bytes([2, 0x70, 0x61, 0x73, 0x73])
