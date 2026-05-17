import struct

import pytest

from seam.codec import (
    CMD_ACK,
    CMD_NACK,
    DATA,
    HOST_CMD,
    STRUCT_FMT,
    cobs_decode,
    cobs_encode,
    decode_payload,
    encode_command_args,
    encode_command_frame,
    parse_frame,
)
from seam.exceptions import FrameDecodeError


class TestCOBS:
    def test_decode_empty(self):
        assert cobs_decode(b"\x01\x00") == b""

    def test_decode_simple(self):
        encoded = cobs_encode(b"hello")
        assert cobs_decode(encoded) == b"hello"

    def test_decode_with_zeros(self):
        data = b"hel\x00lo\x00world"
        encoded = cobs_encode(data)
        assert cobs_decode(encoded) == data

    def test_decode_all_zeros(self):
        data = b"\x00\x00\x00"
        encoded = cobs_encode(data)
        assert cobs_decode(encoded) == data

    def test_encode_roundtrip(self):
        for data in [
            b"",
            b"\x00",
            b"hello",
            b"\x00\x00\x00",
            bytes(range(1, 254)),
            b"\x00" + bytes(range(1, 200)),
            bytes([0xFF] * 100),
        ]:
            assert cobs_decode(cobs_encode(data)) == data

    def test_decode_invalid_zero_code(self):
        with pytest.raises(FrameDecodeError):
            cobs_decode(b"\x0a\x01\x02\x00")

    def test_decode_truncated(self):
        with pytest.raises(FrameDecodeError):
            cobs_decode(b"\x10\x01\x02\x00")


class TestParseFrame:
    def _make_frame(self, frame_type, channel, timestamp, payload):
        return (
            bytes([frame_type, channel])
            + struct.pack("<I", timestamp)
            + bytes([len(payload)])
            + payload
        )

    def test_parse_data_frame(self):
        payload = struct.pack("<f", 3.14)
        raw = self._make_frame(DATA, 1, 1000, payload)
        frame = parse_frame(raw)
        assert frame.frame_type == DATA
        assert frame.channel_or_cmd_id == 1
        assert frame.timestamp_ms == 1000
        assert frame.payload == payload

    def test_parse_frame_too_short(self):
        with pytest.raises(FrameDecodeError):
            parse_frame(b"\x01\x02\x03")

    def test_parse_frame_payload_mismatch(self):
        raw = self._make_frame(DATA, 1, 1000, b"\x01\x02")
        raw = raw[:-1]
        with pytest.raises(FrameDecodeError):
            parse_frame(raw)


class TestDecodePayload:
    def test_decode_f32(self):
        raw = struct.pack("<f", 1.5)
        assert decode_payload(raw, "<f") == (1.5,)

    def test_decode_f32x3(self):
        raw = struct.pack("<fff", 1.0, 2.0, 3.0)
        assert decode_payload(raw, "<fff") == (1.0, 2.0, 3.0)

    def test_decode_u8(self):
        raw = struct.pack("B", 42)
        assert decode_payload(raw, "B") == (42,)

    def test_decode_size_mismatch(self):
        with pytest.raises(FrameDecodeError):
            decode_payload(b"\x01\x02", "<f")


class TestEncodeCommand:
    def test_encode_simple(self):
        frame = encode_command_frame(1, 0, b"")
        decoded = cobs_decode(frame)
        assert decoded[0] == HOST_CMD
        assert decoded[1] == 1
        assert decoded[2] == 0
        assert decoded[3] == 0

    def test_encode_with_args(self):
        args = struct.pack("<f", 2.5)
        frame = encode_command_frame(5, 3, args)
        decoded = cobs_decode(frame)
        assert decoded[0] == HOST_CMD
        assert decoded[1] == 5
        assert decoded[2] == 3
        assert decoded[3] == 4
        assert decoded[4:] == args

    def test_encode_command_args(self):
        defs = [{"type": "u8"}, {"type": "f32"}]
        encoded = encode_command_args([10, 3.14], defs)
        expected = struct.pack("B", 10) + struct.pack("<f", 3.14)
        assert encoded == expected


class TestRoundTrip:
    def _make_frame(self, frame_type, channel, timestamp, payload):
        return (
            bytes([frame_type, channel])
            + struct.pack("<I", timestamp)
            + bytes([len(payload)])
            + payload
        )

    def test_f32_roundtrip(self):
        payload = struct.pack("<f", -42.5)
        raw = self._make_frame(DATA, 0, 500, payload)
        frame = parse_frame(raw)
        values = decode_payload(frame.payload, "<f")
        assert values == (-42.5,)

    def test_f32x3_roundtrip(self):
        payload = struct.pack("<fff", 1.0, -2.0, 3.5)
        raw = self._make_frame(DATA, 1, 1000, payload)
        frame = parse_frame(raw)
        values = decode_payload(frame.payload, "<fff")
        assert values == (1.0, -2.0, 3.5)

    def test_f32x6_roundtrip(self):
        payload = struct.pack("<ffffff", 0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
        raw = self._make_frame(DATA, 2, 2000, payload)
        frame = parse_frame(raw)
        values = decode_payload(frame.payload, "<ffffff")
        assert values == pytest.approx((0.1, 0.2, 0.3, 0.4, 0.5, 0.6))

    def test_u16_roundtrip(self):
        payload = struct.pack("<H", 65535)
        raw = self._make_frame(DATA, 3, 3000, payload)
        frame = parse_frame(raw)
        values = decode_payload(frame.payload, "<H")
        assert values == (65535,)

    def test_i32_roundtrip(self):
        payload = struct.pack("<i", -100000)
        raw = self._make_frame(DATA, 4, 4000, payload)
        frame = parse_frame(raw)
        values = decode_payload(frame.payload, "<i")
        assert values == (-100000,)

    def test_ack_frame(self):
        raw = self._make_frame(CMD_ACK, 5, 0, b"")
        frame = parse_frame(raw)
        assert frame.frame_type == CMD_ACK
        assert frame.channel_or_cmd_id == 5

    def test_nack_frame(self):
        raw = self._make_frame(CMD_NACK, 7, 0, b"")
        frame = parse_frame(raw)
        assert frame.frame_type == CMD_NACK
        assert frame.channel_or_cmd_id == 7
