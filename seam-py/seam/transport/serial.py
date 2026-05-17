import asyncio

import serial_asyncio

from seam.exceptions import ConnectionError
from seam.codec import cobs_decode, cobs_encode


class SerialTransport:
    """USB CDC transport via pyserial-asyncio."""

    def __init__(self, port: str, baudrate: int = 115200):
        self._port = port
        self._baudrate = baudrate
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
            )
        except Exception as e:
            raise ConnectionError(f"Failed to open serial port {self._port}: {e}")

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def read_frame(self) -> bytes:
        if not self._reader:
            raise ConnectionError("Transport not connected")
        buf = bytearray()
        while True:
            byte = await self._reader.read(1)
            if not byte:
                raise ConnectionError("Serial connection lost")
            buf.append(byte[0])
            if byte[0] == 0x00:
                break
        return cobs_decode(bytes(buf))

    async def write_frame(self, data: bytes) -> None:
        if not self._writer:
            raise ConnectionError("Transport not connected")
        encoded = cobs_encode(data)
        self._writer.write(encoded)
        await self._writer.drain()
