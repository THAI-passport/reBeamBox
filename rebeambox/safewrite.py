"""Safe-write policy: protect the badge flash from needless rewrites (docs/safe-write.md).

The badge stores every sent picture or animation in on-board flash (a FAT volume written in 4 KiB pages, docs/recon-web.md).
This module keeps a local, per-badge upload counter and the hash of the last payload, skips an upload that would write the
same bytes again, enforces a minimum interval between writes, and warns when daily or lifetime counts get high.
Nothing leaves the machine; the state file holds a hash of the badge address, never the address itself.
"""
import hashlib
import json
import os
import time

DEFAULT_MIN_INTERVAL_S = 30.0
DEFAULT_WARN_PER_DAY = 100
DEFAULT_WARN_TOTAL = 10000
KEEP_TIMES = 1000          # newest write times kept per badge
DAY = 86400.0


class Skipped(Exception):
    """The payload is identical to the last one written to this badge."""


class Blocked(Exception):
    """A write would break the minimum interval."""


def state_dir(override=None):
    if override:
        return override
    if os.environ.get("REBEAMBOX_STATE_DIR"):
        return os.environ["REBEAMBOX_STATE_DIR"]
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "rebeambox")


def badge_key(badge_id):
    return hashlib.sha256(str(badge_id).strip().lower().encode()).hexdigest()[:16]


def payload_hash(payload):
    return hashlib.sha256(payload).hexdigest()


class Store:
    def __init__(self, directory=None):
        self.dir = state_dir(directory)
        self.path = os.path.join(self.dir, "uploads.json")
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path) as fh:
                d = json.load(fh)
            if not isinstance(d, dict) or not isinstance(d.get("badges"), dict):
                raise ValueError("bad shape")
            d.setdefault("total", 0)
            return d
        except FileNotFoundError:
            return {"version": 1, "total": 0, "badges": {}}
        except (ValueError, OSError):
            try:                                   # keep the damaged file, start a fresh count
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
            return {"version": 1, "total": 0, "badges": {}}

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    def badge(self, key):
        return self.data["badges"].setdefault(key, {"count": 0, "first": None, "last": None, "last_hash": None, "times": []})

    def reset(self):
        self.data = {"version": 1, "total": 0, "badges": {}}
        self.save()


class Policy:
    def __init__(self, enabled=True, force=False, delta=True, min_interval_s=DEFAULT_MIN_INTERVAL_S,
                 warn_per_day=DEFAULT_WARN_PER_DAY, warn_total=DEFAULT_WARN_TOTAL):
        if min_interval_s < 0 or warn_per_day < 0 or warn_total < 0:
            raise ValueError("safe-write thresholds must not be negative")
        self.enabled, self.force, self.delta = enabled, force, delta
        self.min_interval_s, self.warn_per_day, self.warn_total = float(min_interval_s), int(warn_per_day), int(warn_total)


class Gate:
    """Call check(payload) before writing to the badge and commit(payload) after a successful upload."""

    def __init__(self, badge_id, policy=None, store=None, now=time.time, log=lambda m: None):
        self.policy = policy or Policy()
        self.store = store or Store()
        self.key = badge_key(badge_id)
        self.now, self.log = now, log
        self.warnings = []

    def writes_last_day(self):
        t = self.now()
        return sum(1 for x in self.store.badge(self.key)["times"] if t - x < DAY)

    def check(self, payload):
        p = self.policy
        if not p.enabled:
            return []
        b = self.store.badge(self.key)
        t = self.now()
        if p.delta and not p.force and b["last_hash"] == payload_hash(payload):
            raise Skipped("identical to the last payload written to this badge (%d bytes); not writing again" % len(payload))
        if not p.force and b["last"] is not None and 0 <= t - b["last"] < p.min_interval_s:
            raise Blocked("last write was %.0f s ago; minimum interval is %.0f s (wait, or use --force)" % (t - b["last"], p.min_interval_s))
        self.warnings = []
        day = self.writes_last_day()
        if p.warn_per_day and day + 1 > p.warn_per_day:
            self.warnings.append("this will be write %d in 24 hours (warning threshold %d); every write erases and programs flash pages" % (day + 1, p.warn_per_day))
        if p.warn_total and b["count"] + 1 > p.warn_total:
            self.warnings.append("this will be write %d for this badge (warning threshold %d); flash endurance is finite" % (b["count"] + 1, p.warn_total))
        for w in self.warnings:
            self.log("warning: " + w)
        return self.warnings

    def commit(self, payload):
        if not self.policy.enabled:
            return
        b = self.store.badge(self.key)
        t = self.now()
        b["count"] += 1
        b["first"] = b["first"] if b["first"] is not None else t
        b["last"] = t
        b["last_hash"] = payload_hash(payload)
        b["times"] = (b["times"] + [t])[-KEEP_TIMES:]
        self.store.data["total"] += 1
        self.store.save()


def report(store, now=time.time):
    t = now()
    lines = ["state file: %s" % store.path, "total uploads recorded: %d" % store.data["total"]]
    for key, b in sorted(store.data["badges"].items()):
        day = sum(1 for x in b["times"] if t - x < DAY)
        last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(b["last"])) if b["last"] else "-"
        lines.append("badge %s: %d writes, %d in the last 24 h, last %s" % (key, b["count"], day, last))
    if not store.data["badges"]:
        lines.append("no uploads recorded yet")
    return "\n".join(lines)
