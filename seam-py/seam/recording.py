import asyncio
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from seam.codec import DATA, STRUCT_FMT, decode_payload, parse_frame
from seam.device import Sample
from seam.exceptions import RecordingError, UnknownChannelError

MAGIC = b"SEAM"
FILE_VERSION = 0x01
WIRE_VERSION = 0x01


class Recording:
    """Read/write .seam recording files.

    API mirrors ConnectedDevice for seamless swap between live and replay.
    """

    def __init__(self):
        self._schema: dict | None = None
        self._frames: list[bytes] = []
        self._path: Path | None = None
        self._channels: dict[int, dict] = {}

    @classmethod
    async def open(cls, path: str) -> "Recording":
        """Open a .seam file for reading."""
        rec = cls()
        rec._path = Path(path)
        rec._read_file()
        return rec

    def _read_file(self) -> None:
        if not self._path or not self._path.exists():
            raise RecordingError(f"File not found: {self._path}")

        data = self._path.read_bytes()
        if len(data) < 8:
            raise RecordingError("File too short to contain header")

        magic = data[0:4]
        if magic != MAGIC:
            raise RecordingError(f"Invalid magic: {magic!r}, expected {MAGIC!r}")

        version = data[4]
        if version != FILE_VERSION:
            raise RecordingError(
                f"Unsupported file version: 0x{version:02x}, expected 0x{FILE_VERSION:02x}"
            )

        wire_ver = data[5]
        schema_len = struct.unpack_from("<H", data, 6)[0]

        schema_json = data[8 : 8 + schema_len].decode("utf-8")
        try:
            schema = json.loads(schema_json)
        except json.JSONDecodeError as e:
            raise RecordingError(f"Invalid embedded schema: {e}")

        self._schema = schema
        self._channels = {ch["id"]: ch for ch in schema.get("channels", [])}

        frame_data = data[8 + schema_len :]
        offset = 0
        while offset < len(frame_data):
            raw_len = self._probe_frame_length(frame_data, offset)
            if raw_len is None:
                break
            self._frames.append(frame_data[offset : offset + raw_len])
            offset += raw_len

    def _probe_frame_length(self, data: bytes, offset: int) -> int | None:
        if offset + 7 > len(data):
            return None
        payload_len = data[offset + 6]
        total = 7 + payload_len
        if offset + total > len(data):
            return None
        return total

    async def save(self, path: str | None = None) -> None:
        """Write the recording to a .seam file."""
        out = Path(path) if path else self._path
        if not out:
            raise RecordingError("No output path specified")
        if not self._schema:
            raise RecordingError("No schema to write")

        schema_json = json.dumps(self._schema).encode("utf-8")
        header = (
            MAGIC
            + bytes([FILE_VERSION, WIRE_VERSION])
            + struct.pack("<H", len(schema_json))
            + schema_json
        )

        with open(out, "wb") as f:
            f.write(header)
            for frame in self._frames:
                f.write(frame)

    async def stream(self, channel: str):
        """Async generator yielding Sample objects for a single channel."""
        ch_id = self._channel_id_by_name(channel)
        ch_def = self._channels[ch_id]
        fmt = STRUCT_FMT[ch_def["type"]]

        for raw in self._frames:
            frame = parse_frame(raw)
            if frame.frame_type != DATA:
                continue
            if frame.channel_or_cmd_id != ch_id:
                continue
            values = decode_payload(frame.payload, fmt)
            yield Sample(
                channel=channel,
                channel_id=ch_id,
                timestamp_ms=frame.timestamp_ms,
                values=values,
                unit=ch_def.get("unit"),
                _channel_type=ch_def["type"],
            )

    async def stream_all(self):
        """Async generator yielding Sample objects for all channels."""
        for raw in self._frames:
            frame = parse_frame(raw)
            if frame.frame_type != DATA:
                continue
            ch_id = frame.channel_or_cmd_id
            ch_def = self._channels.get(ch_id)
            if ch_def is None:
                raise UnknownChannelError(
                    f"Received data for unknown channel id: {ch_id}"
                )
            fmt = STRUCT_FMT[ch_def["type"]]
            values = decode_payload(frame.payload, fmt)
            yield Sample(
                channel=ch_def["name"],
                channel_id=ch_id,
                timestamp_ms=frame.timestamp_ms,
                values=values,
                unit=ch_def.get("unit"),
                _channel_type=ch_def["type"],
            )

    async def read_once(self, channel: str) -> Sample:
        """Read a single sample from the specified channel."""
        ch_id = self._channel_id_by_name(channel)
        ch_def = self._channels[ch_id]
        fmt = STRUCT_FMT[ch_def["type"]]

        for raw in self._frames:
            frame = parse_frame(raw)
            if frame.frame_type != DATA:
                continue
            if frame.channel_or_cmd_id != ch_id:
                continue
            values = decode_payload(frame.payload, fmt)
            return Sample(
                channel=channel,
                channel_id=ch_id,
                timestamp_ms=frame.timestamp_ms,
                values=values,
                unit=ch_def.get("unit"),
                _channel_type=ch_def["type"],
            )

        raise RecordingError(f"No samples found for channel: {channel}")

    async def send(self, command: str, **kwargs):
        """Not available on recordings. Use a live device instead."""
        raise NotImplementedError(
            "send() is not available on recordings. "
            "Use a live ConnectedDevice to send commands."
        )

    async def as_device(self, realtime: bool = False):
        """Return a ConnectedDevice-like object backed by this recording.

        If realtime=True, samples are yielded with timing matching the original
        recording intervals.
        """
        return _RecordingDevice(self, realtime=realtime)

    def _channel_id_by_name(self, name: str) -> int:
        for ch in self._channels.values():
            if ch["name"] == name:
                return ch["id"]
        raise UnknownChannelError(f"Unknown channel: {name}")

    def add_frame(self, raw: bytes) -> None:
        """Append a raw COBS-decoded frame to the recording."""
        self._frames.append(raw)

    @property
    def schema(self) -> dict:
        if self._schema is None:
            raise RecordingError("No schema loaded")
        return self._schema


class _RecordingDevice:
    """A ConnectedDevice-compatible wrapper around a Recording."""

    def __init__(self, recording: Recording, realtime: bool = False):
        self._recording = recording
        self._realtime = realtime
        self._channels = {ch["id"]: ch for ch in recording.schema.get("channels", [])}

    async def stream(self, channel: str):
        async for sample in self._recording.stream(channel):
            if self._realtime:
                await asyncio.sleep(0)
            yield sample

    async def stream_all(self):
        async for sample in self._recording.stream_all():
            if self._realtime:
                await asyncio.sleep(0)
            yield sample

    async def read_once(self, channel: str) -> Sample:
        return await self._recording.read_once(channel)

    async def send(self, command: str, **kwargs):
        raise NotImplementedError(
            "send() is not available on recordings. "
            "Use a live ConnectedDevice to send commands."
        )
