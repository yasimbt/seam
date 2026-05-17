import struct
from dataclasses import dataclass

from seam.exceptions import FrameDecodeError

STRUCT_FMT = {
    "u8": "B",
    "u16": "<H",
    "u32": "<I",
    "i16": "<h",
    "i32": "<i",
    "f32": "<f",
    "f32x3": "<fff",
    "f32x6": "<ffffff",
}

DATA = 0x01
CMD_ACK = 0x02
CMD_NACK = 0x03
HOST_CMD = 0x10


def cobs_decode(data: bytes) -> bytes:
    """Standard COBS decode.

    Expects data with trailing 0x00 delimiter (as received on wire).
    Raises FrameDecodeError on invalid input.
    """
    if not data:
        raise FrameDecodeError("COBS decode: empty input")

    if data[-1] == 0x00:
        data = data[:-1]

    if not data:
        return b""

    result = bytearray()
    i = 0
    length = len(data)

    while i < length:
        code = data[i]
        i += 1
        if code == 0:
            raise FrameDecodeError("COBS decode: zero code byte in stream")
        if i + code - 1 > length:
            raise FrameDecodeError("COBS decode: code extends past end of data")
        for _ in range(1, code):
            result.append(data[i])
            i += 1
        if i < length:
            result.append(0)

    return bytes(result)


def cobs_encode(data: bytes) -> bytes:
    """Standard COBS encode."""
    result = bytearray()
    i = 0
    length = len(data)

    while i < length:
        run_start = i
        code = 1
        while i < length and data[i] != 0 and code < 0xFF:
            i += 1
            code += 1
        result.append(code)
        result.extend(data[run_start : run_start + code - 1])
        if i < length and data[i] == 0:
            i += 1

    if length == 0 or data[-1] == 0:
        result.append(1)

    result.append(0)
    return bytes(result)


@dataclass
class ParsedFrame:
    frame_type: int
    channel_or_cmd_id: int
    timestamp_ms: int
    payload: bytes


def parse_frame(raw: bytes, schema: dict | None = None) -> ParsedFrame:
    """Parse a COBS-decoded data frame payload.

    Frame layout:
        type(1) | channel(1) | timestamp_ms(4 LE) | length(1) | payload(N)
    """
    if len(raw) < 7:
        raise FrameDecodeError(
            f"Frame too short: {len(raw)} bytes, need at least 7"
        )

    frame_type = raw[0]
    channel_id = raw[1]
    timestamp_ms = struct.unpack_from("<I", raw, 2)[0]
    payload_len = raw[6]

    expected = 7 + payload_len
    if len(raw) < expected:
        raise FrameDecodeError(
            f"Frame payload mismatch: declared {payload_len}, "
            f"only {len(raw) - 7} bytes available"
        )

    payload = raw[7:expected]

    return ParsedFrame(
        frame_type=frame_type,
        channel_or_cmd_id=channel_id,
        timestamp_ms=timestamp_ms,
        payload=payload,
    )


def decode_payload(payload: bytes, fmt: str) -> tuple:
    """Decode raw bytes using a struct format string.

    Raises FrameDecodeError on size mismatch.
    """
    expected = struct.calcsize(fmt)
    if len(payload) != expected:
        raise FrameDecodeError(
            f"Payload size mismatch: got {len(payload)}, expected {expected}"
        )
    return struct.unpack(fmt, payload)


def encode_command_frame(
    command_id: int, seq: int, args_bytes: bytes
) -> bytes:
    """Encode a host-to-device command frame.

    Frame layout:
        type(1) | command_id(1) | seq(1) | length(1) | args(N)

    Returns COBS-encoded bytes ready for wire transmission.
    """
    if not (0 <= command_id <= 255):
        raise ValueError(f"command_id out of range: {command_id}")
    if not (0 <= seq <= 255):
        raise ValueError(f"seq out of range: {seq}")
    if len(args_bytes) > 255:
        raise ValueError(f"args too long: {len(args_bytes)} bytes")

    raw = bytes([HOST_CMD, command_id, seq, len(args_bytes)]) + args_bytes
    return cobs_encode(raw)


def encode_command_args(args: list, arg_defs: list[dict]) -> bytes:
    """Encode command arguments according to their type definitions.

    Args:
        args: list of Python values in order
        arg_defs: list of dicts with 'type' key from schema
    """
    if len(args) != len(arg_defs):
        raise ValueError(
            f"Argument count mismatch: got {len(args)}, expected {len(arg_defs)}"
        )

    parts = []
    for value, defn in zip(args, arg_defs):
        fmt = STRUCT_FMT.get(defn["type"])
        if fmt is None:
            raise ValueError(f"Unknown arg type: {defn['type']}")
        size = struct.calcsize(fmt)
        if fmt.count("<") > 0 or fmt[0] == "<":
            pass
        parts.append(struct.pack(fmt, value))

    return b"".join(parts)
