"""OTA must be unreachable: Jieli OTA runs on the normal 0xAE00 RCSP link, so opcodes are blocked."""
import asyncio

import pytest

from rebeambox import rcsp, safewrite
from rebeambox.link import RecordingLink


class _Badge:
    def attach(self, link): pass
    def has_service(self, uuid): return True
    def on_write(self, uuid, data): pass


def test_pack_refuses_ota_opcodes():
    assert 0xE5 in rcsp.OTA_OPCODES
    for op in (0xE0, 0xE5, 0xEF):
        with pytest.raises(ValueError):
            rcsp.pack(op, b"\x00")
    with pytest.raises(ValueError):
        rcsp.pack(rcsp.OP_DATA, b"", xm_opcode=0xE5)
    rcsp.pack(rcsp.OP_PREPARE_ENV, b"\x00")          # normal commands still build


def test_is_ota_frame_top_level_inner_and_first_chunk():
    top = bytes.fromhex("FEDCBAC0E5000101EF")
    inner_cmd = bytes.fromhex("FEDCBA80010002" "01E5" "EF")
    inner_resp = bytes.fromhex("FEDCBA00010003" "0001E5" "EF")
    for f in (top, top[:5], inner_cmd, inner_resp):
        assert rcsp.is_ota_frame(f), f.hex()
    assert not rcsp.is_ota_frame(rcsp.pack(rcsp.OP_PREPARE_ENV, b"\x00"))
    assert not rcsp.is_ota_frame(b"\xe5" * 10)        # not an RCSP frame at all


def test_link_refuses_hand_made_ota_frame():
    link = RecordingLink(_Badge())
    with pytest.raises(PermissionError):
        asyncio.run(link.write("0000ae01-0000-1000-8000-00805f9b34fb", bytes.fromhex("FEDCBAC0E5000101EF")))
    assert link.events == []


def test_damaged_ledger_fails_closed_even_with_force(tmp_path):
    good = safewrite.Store(str(tmp_path))
    gate = safewrite.Gate("AA:BB", safewrite.Policy(min_interval_s=0), good)
    gate.check(b"x"); gate.commit(b"x")
    with open(good.path, "w") as fh:
        fh.write("{truncated")
    st = safewrite.Store(str(tmp_path))
    assert st.error and "unreadable" in st.error
    for pol in (safewrite.Policy(min_interval_s=0), safewrite.Policy(force=True)):
        with pytest.raises(safewrite.Blocked):
            safewrite.Gate("AA:BB", pol, st).check(b"y")
    assert "ERROR" in safewrite.report(st)
    with open(st.path) as fh:                          # damaged file kept as evidence
        assert fh.read() == "{truncated"
    st.reset()
    safewrite.Gate("AA:BB", safewrite.Policy(min_interval_s=0), st).check(b"y")
