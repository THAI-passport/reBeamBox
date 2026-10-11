"""Link abstraction: a GATT-like connection that sessions talk to (bleak, simulator, recorder)."""
import re


def short(uuid):
    u = uuid.lower()
    m = re.match(r"0000([0-9a-f]{4})-0000-1000-8000-00805f9b34fb$", u)
    return m.group(1) if m else u


class Link:
    mtu = 23

    def has_service(self, uuid):
        raise NotImplementedError

    async def write(self, uuid, data, response=False):
        raise NotImplementedError

    async def subscribe(self, uuid, callback):
        raise NotImplementedError

    async def close(self):
        pass


class BleakLink(Link):
    """Real Bluetooth link using bleak."""

    def __init__(self, address_or_device, timeout=20.0, mtu_hint=512):
        from bleak import BleakClient
        self._client = BleakClient(address_or_device, timeout=timeout)
        self.mtu = 23
        self._hint = mtu_hint

    async def connect(self):
        await self._client.connect()
        try:
            m = self._client.mtu_size          # populated by the backend where supported
            self.mtu = m if m and m > 23 else 23
        except Exception:
            self.mtu = 23
        return self

    def has_service(self, uuid):
        return any(s.uuid.lower() == uuid.lower() for s in self._client.services)

    async def write(self, uuid, data, response=False):
        await self._client.write_gatt_char(uuid, data, response=response)

    async def subscribe(self, uuid, callback):
        await self._client.start_notify(uuid, lambda _c, data: callback(bytes(data)))

    async def close(self):
        await self._client.disconnect()


class RecordingLink(Link):
    """Wraps a simulated badge and records every frame in order (dry run)."""

    def __init__(self, badge, mtu=512):
        self.badge = badge
        self.mtu = mtu
        self.events = []          # (direction 'W'|'N', short uuid, bytes)
        self._cbs = {}
        badge.attach(self)

    def has_service(self, uuid):
        return self.badge.has_service(uuid)

    async def write(self, uuid, data, response=False):
        self.events.append(("W", short(uuid), bytes(data)))
        self.badge.on_write(uuid.lower(), bytes(data))

    async def subscribe(self, uuid, callback):
        self._cbs[uuid.lower()] = callback
        self.badge.on_subscribe(uuid.lower())

    def push(self, uuid, data):
        """Called by the simulator: deliver a notification to the session."""
        self.events.append(("N", short(uuid), bytes(data)))
        cb = self._cbs.get(uuid.lower())
        if cb:
            import asyncio
            asyncio.get_running_loop().call_soon(cb, bytes(data))

    def dump(self):
        lines = []
        for d, u, b in self.events:
            lines.append("%s %s %4d %s" % (d, u, len(b), b.hex(" ").upper()))
        return "\n".join(lines) + "\n"
