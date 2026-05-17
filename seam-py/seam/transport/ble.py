import asyncio

from seam.exceptions import ConnectionError
from seam.codec import cobs_decode, cobs_encode

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class BLETransport:
    """BLE NUS transport via bleak."""

    def __init__(self, address: str):
        self._address = address
        self._client = None
        self._frame_queue: asyncio.Queue[bytes] | None = None

    async def connect(self) -> None:
        import asyncio

        from bleak import BleakClient

        self._frame_queue = asyncio.Queue()
        try:
            self._client = BleakClient(self._address)
            await self._client.connect()
            await self._client.start_notify(
                NUS_RX_CHAR_UUID, self._notification_handler
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to BLE device {self._address}: {e}"
            )

    def _notification_handler(self, _sender, data: bytearray) -> None:
        if self._frame_queue is not None:
            self._frame_queue.put_nowait(bytes(data))

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NUS_RX_CHAR_UUID)
            except Exception:
                pass
            await self._client.disconnect()
        self._client = None
        self._frame_queue = None

    async def read_frame(self) -> bytes:
        if not self._client or not self._frame_queue:
            raise ConnectionError("Transport not connected")
        buf = bytearray()
        while True:
            chunk = await self._frame_queue.get()
            buf.extend(chunk)
            if 0x00 in chunk:
                idx = buf.index(0x00)
                packet = bytes(buf[: idx + 1])
                del buf[: idx + 1]
                return cobs_decode(packet)

    async def write_frame(self, data: bytes) -> None:
        if not self._client:
            raise ConnectionError("Transport not connected")
        encoded = cobs_encode(data)
        await self._client.write_gatt_char(NUS_TX_CHAR_UUID, encoded)
