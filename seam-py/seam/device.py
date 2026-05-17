import asyncio
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from seam.codec import (
    CMD_ACK,
    CMD_NACK,
    DATA,
    HOST_CMD,
    STRUCT_FMT,
    decode_payload,
    encode_command_args,
    encode_command_frame,
    parse_frame,
)
from seam.exceptions import (
    CommandNackError,
    ConnectionError,
    FrameDecodeError,
    UnknownChannelError,
    UnknownCommandError,
)
from seam.schema import load_schema


@dataclass
class Sample:
    channel: str
    channel_id: int
    timestamp_ms: int
    values: tuple
    unit: str | None
    _channel_type: str = field(default="", repr=False)

    @property
    def x(self) -> float:
        if self._channel_type != "f32x3":
            raise AttributeError("x is only available for f32x3 channels")
        return self.values[0]

    @property
    def y(self) -> float:
        if self._channel_type != "f32x3":
            raise AttributeError("y is only available for f32x3 channels")
        return self.values[1]

    @property
    def z(self) -> float:
        if self._channel_type != "f32x3":
            raise AttributeError("z is only available for f32x3 channels")
        return self.values[2]

    @property
    def ax(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("ax is only available for f32x6 channels")
        return self.values[0]

    @property
    def ay(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("ay is only available for f32x6 channels")
        return self.values[1]

    @property
    def az(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("az is only available for f32x6 channels")
        return self.values[2]

    @property
    def gx(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("gx is only available for f32x6 channels")
        return self.values[3]

    @property
    def gy(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("gy is only available for f32x6 channels")
        return self.values[4]

    @property
    def gz(self) -> float:
        if self._channel_type != "f32x6":
            raise AttributeError("gz is only available for f32x6 channels")
        return self.values[5]


class ConnectedDevice:
    """A device that has been connected. Provides streaming and command APIs."""

    def __init__(self, transport, schema: dict):
        self._transport = transport
        self._schema = schema
        self._channels = {ch["id"]: ch for ch in schema["channels"]}
        self._commands = {cmd["name"]: cmd for cmd in schema["commands"]}
        self._seq = 0

    async def stream(self, channel: str):
        """Async generator yielding Sample objects for a single channel."""
        ch_id = self._channel_id_by_name(channel)
        ch_def = self._channels[ch_id]
        fmt = STRUCT_FMT[ch_def["type"]]

        while True:
            raw = await self._transport.read_frame()
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
        while True:
            raw = await self._transport.read_frame()
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

        while True:
            raw = await self._transport.read_frame()
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

    async def send(self, command: str, **kwargs) -> dict:
        """Send a command to the device and wait for ACK/NACK."""
        cmd_def = self._commands.get(command)
        if cmd_def is None:
            raise UnknownCommandError(f"Unknown command: {command}")

        arg_defs = cmd_def.get("args", [])
        arg_values = [kwargs[a["name"]] for a in arg_defs]
        args_bytes = encode_command_args(arg_values, arg_defs)

        seq = self._seq
        self._seq = (self._seq + 1) % 256

        frame = encode_command_frame(cmd_def["id"], seq, args_bytes)
        await self._transport.write_frame(frame)

        while True:
            raw = await self._transport.read_frame()
            parsed = parse_frame(raw)
            if parsed.frame_type == CMD_ACK and parsed.channel_or_cmd_id == cmd_def["id"]:
                return {"seq": seq}
            elif parsed.frame_type == CMD_NACK and parsed.channel_or_cmd_id == cmd_def["id"]:
                raise CommandNackError(f"Command '{command}' was NACKed by device")

    def _channel_id_by_name(self, name: str) -> int:
        for ch in self._channels.values():
            if ch["name"] == name:
                return ch["id"]
        raise UnknownChannelError(f"Unknown channel: {name}")


class Device:
    """Entry point for connecting to a device from a config file."""

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._schema = load_schema(config_path)
        self._connected: ConnectedDevice | None = None

    @classmethod
    def from_config(cls, path: str) -> "Device":
        return cls(path)

    async def connect(self) -> ConnectedDevice:
        transport = self._make_transport()
        await transport.connect()
        self._connected = ConnectedDevice(transport, self._schema)
        return self._connected

    async def disconnect(self) -> None:
        if self._connected:
            await self._connected._transport.disconnect()
            self._connected = None

    @asynccontextmanager
    async def session(self):
        """Async context manager for connect/disconnect."""
        conn = await self.connect()
        try:
            yield conn
        finally:
            await self.disconnect()

    def _make_transport(self):
        transport_type = self._schema["device"]["transport"]
        if transport_type == "usb-cdc":
            from seam.transport.serial import SerialTransport

            port = self._schema["device"].get("port", "/dev/ttyACM0")
            return SerialTransport(port)
        elif transport_type == "ble-nus":
            from seam.transport.ble import BLETransport

            address = self._schema["device"].get("address", "")
            return BLETransport(address)
        else:
            raise ConnectionError(f"Unsupported transport: {transport_type}")
