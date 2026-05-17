import asyncio
from dataclasses import dataclass, field

from seam.device import ConnectedDevice, Device, Sample
from seam.schema import load_schema


@dataclass
class TaggedSample(Sample):
    device: str = field(default="")


class MultiDevice:
    """Manage multiple devices simultaneously."""

    def __init__(self, configs: dict[str, str]):
        """
        Args:
            configs: dict mapping device name -> path to seam.toml
        """
        self._configs = configs
        self._devices: dict[str, Device] = {}
        self._connected: dict[str, ConnectedDevice] = {}

    @classmethod
    def from_configs(cls, configs: dict[str, str]) -> "MultiDevice":
        return cls(configs)

    async def connect(self) -> "ConnectedFleet":
        for name, path in self._configs.items():
            dev = Device.from_config(path)
            conn = await dev.connect()
            self._devices[name] = dev
            self._connected[name] = conn
        return ConnectedFleet(self._connected)

    async def disconnect(self) -> None:
        for name, dev in self._devices.items():
            try:
                await dev.disconnect()
            except Exception:
                pass
        self._devices.clear()
        self._connected.clear()


class ConnectedFleet:
    """A fleet of connected devices."""

    def __init__(self, devices: dict[str, ConnectedDevice]):
        self._devices = devices

    async def stream_all(self):
        """Async generator yielding TaggedSample from any device.

        Samples are interleaved as they arrive.
        """
        queues: dict[str, asyncio.Queue] = {}
        tasks = []

        for name, conn in self._devices.items():
            q: asyncio.Queue = asyncio.Queue()
            queues[name] = q
            tasks.append(asyncio.create_task(self._forward(conn, q, name)))

        try:
            while tasks:
                done = []
                for name, q in queues.items():
                    try:
                        sample = q.get_nowait()
                        yield sample
                    except asyncio.QueueEmpty:
                        pass
                await asyncio.sleep(0.001)
        finally:
            for t in tasks:
                t.cancel()

    async def _forward(
        self, conn: ConnectedDevice, queue: asyncio.Queue, name: str
    ):
        try:
            async for sample in conn.stream_all():
                tagged = TaggedSample(
                    channel=sample.channel,
                    channel_id=sample.channel_id,
                    timestamp_ms=sample.timestamp_ms,
                    values=sample.values,
                    unit=sample.unit,
                    _channel_type=sample._channel_type,
                    device=name,
                )
                await queue.put(tagged)
        except asyncio.CancelledError:
            pass
