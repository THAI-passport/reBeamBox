import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import notify_log  # noqa: E402


class FakeClient:
    def __init__(self):
        self.services = [NS(characteristics=[NS(uuid="000001f2-0000-1000-8000-00805f9b34fb", properties=["notify"]),
                                              NS(uuid="000001f1-0000-1000-8000-00805f9b34fb", properties=["write-without-response"])])]
        self.handlers, self.stopped = {}, []

    async def start_notify(self, uuid, cb):
        self.handlers[uuid] = cb

    async def stop_notify(self, uuid):
        self.stopped.append(uuid)


def test_subscribes_only_to_notifiable_characteristics_and_logs_events():
    c, events = FakeClient(), []

    async def fake_sleep(_):
        for cb in c.handlers.values():
            cb(None, bytearray(b"\xa0\x01\x02"))

    subs = asyncio.run(notify_log.log_notifications(c, 1, events.append, sleep=fake_sleep))
    assert len(subs) == 1 and subs[0].startswith("000001f2")
    assert events[0]["hex"] == "a00102" and events[0]["len"] == 3
    assert c.stopped == subs


def test_mask_hides_last_three_bytes():
    assert notify_log.mask("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:xx:xx:xx"
    assert "..." in notify_log.mask("2B1F8A2C-3C0B-4C5E-9D2A-1234567890AB")
