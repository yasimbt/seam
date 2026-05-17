import asyncio
import pytest

from seam.codec import cobs_encode


class LoopbackTransport:
    """Test transport that yields pre-encoded frames.

    Accepts a list of pre-encoded (raw, COBS-decoded) frames.
    Yields them from read_frame() in order.
    Captures frames written via write_frame().
    """

    def __init__(self, frames: list[bytes] | None = None):
        self._frames = list(frames) if frames else []
        self._written: list[bytes] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        for f in self._frames:
            self._queue.put_nowait(f)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def read_frame(self) -> bytes:
        return await self._queue.get()

    async def write_frame(self, data: bytes) -> None:
        self._written.append(data)

    @property
    def written_frames(self) -> list[bytes]:
        return list(self._written)

    def inject_frame(self, raw: bytes) -> None:
        self._queue.put_nowait(raw)


@pytest.fixture
def loopback():
    return LoopbackTransport()
