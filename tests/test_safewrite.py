"""Safe-write policy: counter persistence, delta skipping, interval, warnings, client and CLI wiring."""
import asyncio
import json
import os

import pytest
from PIL import Image

from rebeambox import cli, client, link, safewrite, sim, wifi


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def gate(tmp_path, clock, badge="AA:BB:CC:DD:EE:FF", **kw):
    return safewrite.Gate(badge, safewrite.Policy(**kw), safewrite.Store(str(tmp_path)), now=clock, log=lambda m: None)


def test_first_write_passes_and_is_counted_and_persisted(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk)
    assert g.check(b"one") == []
    g.commit(b"one")
    st = safewrite.Store(str(tmp_path))
    assert st.data["total"] == 1
    b = st.badge(g.key)
    assert b["count"] == 1 and b["last"] == clk.t and b["last_hash"] == safewrite.payload_hash(b"one")


def test_state_file_stores_a_hash_not_the_address(tmp_path):
    g = gate(tmp_path, Clock(), badge="AA:BB:CC:DD:EE:FF")
    g.commit(b"x")
    text = open(os.path.join(str(tmp_path), "uploads.json")).read()
    assert "AA:BB:CC" not in text and "aa:bb:cc" not in text and g.key in text
    assert safewrite.badge_key("aa:bb:cc:dd:ee:ff") == safewrite.badge_key(" AA:BB:CC:DD:EE:FF ")


def test_identical_payload_is_skipped_but_different_one_passes(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=0)
    g.commit(b"img")
    clk.t += 5
    with pytest.raises(safewrite.Skipped):
        g.check(b"img")
    g.check(b"img2")


def test_skip_is_per_badge(tmp_path):
    clk = Clock()
    gate(tmp_path, clk, badge="one", min_interval_s=0).commit(b"img")
    gate(tmp_path, clk, badge="two", min_interval_s=0).check(b"img")     # other badge: no skip


def test_force_and_no_delta_bypass_the_skip(tmp_path):
    clk = Clock()
    gate(tmp_path, clk, min_interval_s=0).commit(b"img")
    gate(tmp_path, clk, min_interval_s=0, force=True).check(b"img")
    gate(tmp_path, clk, min_interval_s=0, delta=False).check(b"img")


def test_minimum_interval_blocks_then_allows(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=30)
    g.commit(b"a")
    clk.t += 10
    with pytest.raises(safewrite.Blocked) as e:
        g.check(b"b")
    assert "10 s ago" in str(e.value)
    clk.t += 20
    g.check(b"b")
    with pytest.raises(safewrite.Blocked):
        gate(tmp_path, Clock(clk.t - 25), min_interval_s=30).check(b"c")      # fresh gate sees the persisted time


def test_force_ignores_interval(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=600, force=True)
    g.commit(b"a")
    clk.t += 1
    g.check(b"b")


def test_daily_and_total_warnings(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=0, warn_per_day=3, warn_total=5)
    for i in range(3):
        assert g.check(b"p%d" % i) == []
        g.commit(b"p%d" % i)
        clk.t += 1
    w = g.check(b"p3")
    assert len(w) == 1 and "4 in 24 hours" in w[0]
    g.commit(b"p3"); clk.t += 1
    g.commit(b"p4"); clk.t += 1
    w = g.check(b"p5")
    assert any("write 6 for this badge" in x for x in w)
    clk.t += safewrite.DAY                                          # a day later the daily count drops, the lifetime stays
    w = g.check(b"p6")
    assert not any("24 hours" in x for x in w) and any("for this badge" in x for x in w)


def test_zero_thresholds_turn_warnings_off(tmp_path):
    g = gate(tmp_path, Clock(), min_interval_s=0, warn_per_day=0, warn_total=0)
    for i in range(5):
        assert g.check(b"%d" % i) == []
        g.commit(b"%d" % i)


def test_disabled_policy_neither_checks_nor_counts(tmp_path):
    g = gate(tmp_path, Clock(), enabled=False)
    g.commit(b"a")
    g.check(b"a")
    assert not os.path.exists(os.path.join(str(tmp_path), "uploads.json"))


def test_negative_thresholds_rejected():
    with pytest.raises(ValueError):
        safewrite.Policy(min_interval_s=-1)


def test_times_list_is_bounded(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=0, delta=False)
    for _ in range(safewrite.KEEP_TIMES + 10):
        g.commit(b"x")
        clk.t += 1
    st = safewrite.Store(str(tmp_path))
    assert len(st.badge(g.key)["times"]) == safewrite.KEEP_TIMES and st.badge(g.key)["count"] == safewrite.KEEP_TIMES + 10


def test_corrupt_state_file_refuses_writes_until_reset(tmp_path):
    # Fail closed: a damaged ledger must not silently become a zero count (see test_ota_block too).
    for bad in ("{not json", "[]", '{"badges": 3}'):
        open(os.path.join(str(tmp_path), "uploads.json"), "w").write(bad)
        st = safewrite.Store(str(tmp_path))
        assert st.error
        with pytest.raises(safewrite.Blocked):
            safewrite.Gate("x", safewrite.Policy(min_interval_s=0), st).check(b"img")
        assert open(os.path.join(str(tmp_path), "uploads.json")).read() == bad
    st.reset()
    assert safewrite.Store(str(tmp_path)).error is None


def test_state_dir_resolution(monkeypatch, tmp_path):
    monkeypatch.delenv("REBEAMBOX_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert safewrite.state_dir() == os.path.join(str(tmp_path), "rebeambox")
    monkeypatch.setenv("REBEAMBOX_STATE_DIR", "/x/y")
    assert safewrite.state_dir() == "/x/y" and safewrite.state_dir("/z") == "/z"


def test_report_lists_counts(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk)
    g.commit(b"a")
    text = safewrite.report(safewrite.Store(str(tmp_path)), clk)
    assert "total uploads recorded: 1" in text and g.key in text and "1 writes, 1 in the last 24 h" in text
    assert "no uploads recorded yet" in safewrite.report(safewrite.Store(str(tmp_path / "empty")))


# client wiring ----------------------------------------------------------------------------------------------------

def _job(tmp_path, colour):
    from rebeambox import cli as c
    p = tmp_path / "img.png"
    Image.new("RGB", (64, 64), colour).save(p)
    args = c.build_parser().parse_args(["send-image", str(p), "--dry-run", "x", "--model", "nikko"])
    return c.make_job(args)


def run(c):
    return asyncio.run(c)


def test_client_send_nn20_skips_the_second_identical_upload(tmp_path):
    clk = Clock()
    g1 = gate(tmp_path, clk, min_interval_s=0)
    job = _job(tmp_path, (200, 30, 30))
    lk = link.RecordingLink(sim.SimNn20())
    first = run(client.send(lk, job, "nn20", None, lambda m: None, fast=True, gate=g1))
    assert first and safewrite.Store(str(tmp_path)).data["total"] == 1
    writes_before = len([e for e in lk.events if e[0] == "W"])
    lk2 = link.RecordingLink(sim.SimNn20())
    with pytest.raises(safewrite.Skipped):
        run(client.send(lk2, job, "nn20", None, lambda m: None, fast=True, gate=gate(tmp_path, clk, min_interval_s=0)))
    assert [e for e in lk2.events if e[0] == "W"] == [] and writes_before > 0           # nothing written to the badge
    assert safewrite.Store(str(tmp_path)).data["total"] == 1                              # and not counted


def test_client_send_counts_only_after_success(tmp_path):
    g = gate(tmp_path, Clock(), min_interval_s=0)
    job = _job(tmp_path, (1, 2, 3))

    class FailLink(link.RecordingLink):
        async def write(self, *a, **k):
            raise OSError("link lost")
    lk = FailLink(sim.SimNn20())
    with pytest.raises(Exception):
        run(client.send(lk, job, "nn20", None, lambda m: None, fast=True, gate=g))
    assert safewrite.Store(str(tmp_path)).data["total"] == 0


def test_client_send_badge_transport_is_gated_and_counted(tmp_path):
    g = gate(tmp_path, Clock(), min_interval_s=0)
    job = _job(tmp_path, (9, 99, 199))
    run(client.send(link.RecordingLink(sim.SimBadgeSdk()), job, "badge", None, lambda m: None, fast=True, gate=g))
    assert safewrite.Store(str(tmp_path)).data["total"] == 1
    with pytest.raises(safewrite.Skipped):
        run(client.send(link.RecordingLink(sim.SimBadgeSdk()), job, "badge", None, lambda m: None, fast=True,
                        gate=gate(tmp_path, Clock(), min_interval_s=0)))


def test_wifi_send_is_gated(tmp_path):
    job = _job(tmp_path, (50, 60, 70))
    badge = sim.SimWifiBadge()
    mk = lambda n: wifi.SimChannel(badge, n)
    run(client.send_wifi(job, mk, pace=False, gate=gate(tmp_path, Clock(), min_interval_s=0), log=lambda m: None))
    assert safewrite.Store(str(tmp_path)).data["total"] == 1
    with pytest.raises(safewrite.Skipped):
        run(client.send_wifi(job, mk, pace=False, gate=gate(tmp_path, Clock(), min_interval_s=0), log=lambda m: None))


# CLI wiring --------------------------------------------------------------------------------------------------------

def test_cli_flags_and_defaults():
    a = cli.build_parser().parse_args(["send-image", "x.png"])
    assert a.min_interval_s == 30 and a.warn_per_day == 40 and a.warn_total == 10000
    assert not a.force and not a.no_delta and not a.no_safe_write and a.badge_id is None and a.state_dir is None
    a = cli.build_parser().parse_args(["send-gif", "x.gif", "--min-interval-s", "5", "--warn-per-day", "7", "--warn-total", "9",
                                       "--force", "--no-delta", "--badge-id", "desk", "--state-dir", "/tmp/q"])
    assert (a.min_interval_s, a.warn_per_day, a.warn_total, a.force, a.no_delta, a.badge_id, a.state_dir) == (5, 7, 9, True, True, "desk", "/tmp/q")


def test_make_gate_is_off_for_dry_run_and_no_safe_write(tmp_path):
    p = cli.build_parser()
    assert cli.make_gate(p.parse_args(["send-image", "x", "--dry-run", "f", "--state-dir", str(tmp_path)]), "id", print) is None
    assert cli.make_gate(p.parse_args(["send-image", "x", "--no-safe-write", "--state-dir", str(tmp_path)]), "id", print) is None
    g = cli.make_gate(p.parse_args(["send-image", "x", "--badge-id", "desk", "--state-dir", str(tmp_path), "--force"]), "addr", print)
    assert g.key == safewrite.badge_key("desk") and g.policy.force


def test_dry_run_never_touches_the_counter(tmp_path, capsys):
    img = tmp_path / "i.png"
    Image.new("RGB", (32, 32), (5, 5, 5)).save(img)
    sd = tmp_path / "state"
    for _ in range(2):
        assert cli.main(["send-image", str(img), "--dry-run", str(tmp_path / "o.txt"), "--model", "nikko", "--state-dir", str(sd), "--quiet"]) == 0
    assert not (sd / "uploads.json").exists()


def test_uploads_command_shows_and_resets(tmp_path, capsys):
    sd = str(tmp_path / "s")
    gate(tmp_path / "s", Clock()).commit(b"a")
    assert cli.main(["uploads", "--state-dir", sd]) == 0
    assert "total uploads recorded: 1" in capsys.readouterr().out
    assert cli.main(["uploads", "--state-dir", sd, "--reset"]) == 0
    out = capsys.readouterr().out
    assert "cleared" in out and "no uploads recorded yet" in out


def test_main_maps_skip_to_exit_0_and_block_to_exit_2(monkeypatch, capsys):
    async def skipped(args):
        raise safewrite.Skipped("same")

    async def blocked(args):
        raise safewrite.Blocked("too soon")
    monkeypatch.setattr(cli, "_run_send", skipped)
    assert cli.main(["send-image", "x.png"]) == 0 and "skipped" in capsys.readouterr().err
    monkeypatch.setattr(cli, "_run_send", blocked)
    assert cli.main(["send-image", "x.png"]) == 2 and "not sent" in capsys.readouterr().err


# daily hard cap --------------------------------------------------------------------------------------------------------

def test_defaults_include_a_50_per_day_cap():
    assert safewrite.Policy().max_per_day == 50 and safewrite.DEFAULT_WARN_PER_DAY < safewrite.DEFAULT_MAX_PER_DAY
    a = cli.build_parser().parse_args(["send-image", "x.png"])
    assert a.max_per_day == 50 and a.warn_per_day == 40


def test_cap_blocks_the_next_write_and_is_a_blocked_subclass(tmp_path):
    clk = Clock()
    g = gate(tmp_path, clk, min_interval_s=0, delta=False, max_per_day=3, warn_per_day=0)
    for _ in range(3):
        g.check(b"x")
        g.commit(b"x")
        clk.t += 60
    with pytest.raises(safewrite.CapReached) as e:
        g.check(b"x")
    assert isinstance(e.value, safewrite.Blocked) and "daily cap reached: 3 writes" in str(e.value)
    assert safewrite.Store(str(tmp_path)).data["total"] == 3                 # a refused write is not counted


def test_cap_is_per_badge_and_rolling(tmp_path):
    clk = Clock()
    a = gate(tmp_path, clk, badge="a", min_interval_s=0, delta=False, max_per_day=2)
    for _ in range(2):
        a.commit(b"x")
        clk.t += 10
    with pytest.raises(safewrite.CapReached):
        a.check(b"x")
    gate(tmp_path, clk, badge="b", min_interval_s=0, delta=False, max_per_day=2).check(b"x")     # other badge is unaffected
    clk.t += safewrite.DAY                                                                          # the day rolls over
    a.check(b"x")


def test_cap_override_flags(tmp_path):
    clk = Clock()
    base = dict(min_interval_s=0, delta=False, max_per_day=1)
    gate(tmp_path, clk, **base).commit(b"x")
    clk.t += 1
    with pytest.raises(safewrite.CapReached):
        gate(tmp_path, clk, **base).check(b"x")
    gate(tmp_path, clk, force=True, **base).check(b"x")                        # --force
    gate(tmp_path, clk, **dict(base, max_per_day=0)).check(b"x")               # --max-per-day 0 = no cap
    gate(tmp_path, clk, **dict(base, max_per_day=5)).check(b"x")               # raised cap
    gate(tmp_path, clk, enabled=False, **base).check(b"x")                     # --no-safe-write
    with pytest.raises(ValueError):
        safewrite.Policy(max_per_day=-1)


def test_cap_makes_cli_exit_2(monkeypatch, capsys):
    async def capped(args):
        raise safewrite.CapReached("daily cap reached: 50 writes")
    monkeypatch.setattr(cli, "_run_send", capped)
    assert cli.main(["send-image", "x.png", "--max-per-day", "50"]) == 2 and "daily cap" in capsys.readouterr().err


def test_make_gate_passes_the_cap(tmp_path):
    a = cli.build_parser().parse_args(["send-image", "x", "--max-per-day", "7", "--state-dir", str(tmp_path)])
    assert cli.make_gate(a, "id", print).policy.max_per_day == 7
