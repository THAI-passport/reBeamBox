#!/usr/bin/env python3
"""Run E1 (function_E1test) from libjl_auth.so (arm64) under unicorn to get ground truth.
Usage: emulate_jl_auth.py path/to/libjl_auth.so  (library not shipped in this repo)."""
import sys
from unicorn import *
from unicorn.arm64_const import *

def load(path):
    from elftools.elf.elffile import ELFFile
    f = open(path, 'rb'); e = ELFFile(f)
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, 0x20000)
    for s in e.iter_segments():
        if s['p_type'] == 'PT_LOAD':
            f.seek(s['p_offset']); mu.mem_write(s['p_vaddr'], f.read(s['p_filesz']))
    mu.mem_map(0x100000, 0x10000)   # stack
    mu.mem_map(0x200000, 0x10000)   # heap + tls
    mu.mem_map(0x300000, 0x1000)    # io
    mu.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)
    mu.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x2f0000 - 0)  # canary slot
    mu.mem_write(0x200000 + 0xf000 + 0x28, b'\xAA' * 8)
    mu.reg_write(UC_ARM64_REG_TPIDR_EL0, 0x200000 + 0xf000)
    heap = [0x200000]
    def hook(uc, addr, size, ud):
        if addr == 0x20d0:
            n = uc.reg_read(UC_ARM64_REG_X0); p = heap[0]; heap[0] += (n + 15) & ~15
            uc.reg_write(UC_ARM64_REG_X0, p)
        elif addr == 0x20e0:
            pass
        else:
            return
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))
    mu.hook_add(UC_HOOK_CODE, hook, begin=0x20d0, end=0x20e8)
    return mu

def e1(mu, addr6, rand16, key16):
    io = 0x300000
    mu.mem_write(io, addr6); mu.mem_write(io + 0x10, rand16)
    mu.mem_write(io + 0x20, key16)
    mu.reg_write(UC_ARM64_REG_X0, io); mu.reg_write(UC_ARM64_REG_X1, io + 0x10)
    mu.reg_write(UC_ARM64_REG_X2, io + 0x20); mu.reg_write(UC_ARM64_REG_X3, io + 0x40)
    mu.reg_write(UC_ARM64_REG_SP, 0x10f000); mu.reg_write(UC_ARM64_REG_X30, 0x1000)
    try:
        mu.emu_start(0x10cc, 0x1000, count=200000)
    except UcError as ex:
        print('emu error', ex, hex(mu.reg_read(UC_ARM64_REG_PC))); raise
    return bytes(mu.mem_read(io + 0x40, 16))

if __name__ == '__main__':
    mu = load(sys.argv[1])
    KEY = bytes.fromhex('06775f87918dd423005df1d8cf0c142b'); ADDR = bytes.fromhex('112233332211')
    import os
    for r in [bytes(16), bytes(range(16)), bytes.fromhex('00112233445566778899aabbccddeeff')] + [os.urandom(16) for _ in range(3)]:
        print(r.hex(), e1(mu, ADDR, r, KEY).hex())
