import struct

import pytest

from seam.codec import (
    CMD_ACK,
    CMD_NACK,
    DATA,
    HOST_CMD,
    STRUCT_FMT,
    cobs_encode,
    parse_frame,
)
from seam.device import ConnectedDevice, Device, Sample
from seam.exceptions import (
    CommandNackError,
    UnknownChannelError,
    UnknownCommandError,
)
from conftest import LoopbackTransport


SCHEMA = {
    "device": {"name": "test", "transport": "usb-cdc"},
    "channels": [
        {"id": 0, "name": "accel", "type": "f32x3", "rate_hz": 100, "unit": "g"},
        {"id": 1, "name": "temp", "type": "f32", "rate_hz": 10, "unit": "celsius"},
    ],
    "commands": [
        {"id": 0, "name": "set_gain", "args": [{"name": "gain", "type": "f32"}]},
        {"id": 1, "name": "reset", "args": []},
    ],
}


def _make_data_frame(channel_id, timestamp, payload):
    raw = (
        bytes([DATA, channel_id])
        + struct.pack("<I", timestamp)
        + bytes([len(payload)])
        + payload
    )
    return raw


def _make_ack_frame(cmd_id):
    raw = bytes([CMD_ACK, cmd_id]) + struct.pack("<I", 0) + bytes([0])
    return raw


def _make_nack_frame(cmd_id):
    raw = bytes([CMD_NACK, cmd_id]) + struct.pack("<I", 0) + bytes([0])
    return raw


@pytest.fixture
def connected(loopback):
    return ConnectedDevice(loopback, SCHEMA)


class TestStream:
    async def test_stream_single_channel(self, connected, loopback):
        payload = struct.pack("<fff", 1.0, 2.0, 3.0)
        frame = _make_data_frame(0, 1000, payload)
        loopback.inject_frame(frame)

        samples = []
        async for s in connected.stream("accel"):
            samples.append(s)
            if len(samples) >= 1:
                break

        assert len(samples) == 1
        assert samples[0].channel == "accel"
        assert samples[0].channel_id == 0
        assert samples[0].timestamp_ms == 1000
        assert samples[0].values == (1.0, 2.0, 3.0)
        assert samples[0].unit == "g"
        assert samples[0].x == 1.0
        assert samples[0].y == 2.0
        assert samples[0].z == 3.0

    async def test_stream_filters_other_channels(self, connected, loopback):
        payload_other = struct.pack("<f", 25.0)
        frame_other = _make_data_frame(1, 500, payload_other)
        payload_target = struct.pack("<fff", 0.1, 0.2, 0.3)
        frame_target = _make_data_frame(0, 600, payload_target)
        loopback.inject_frame(frame_other)
        loopback.inject_frame(frame_target)

        samples = []
        async for s in connected.stream("accel"):
            samples.append(s)
            if len(samples) >= 1:
                break

        assert len(samples) == 1
        assert samples[0].channel == "accel"

    async def test_stream_all(self, connected, loopback):
        p1 = struct.pack("<fff", 1.0, 0.0, 0.0)
        p2 = struct.pack("<f", 22.5)
        loopback.inject_frame(_make_data_frame(0, 100, p1))
        loopback.inject_frame(_make_data_frame(1, 200, p2))

        samples = []
        async for s in connected.stream_all():
            samples.append(s)
            if len(samples) >= 2:
                break

        assert len(samples) == 2
        assert samples[0].channel == "accel"
        assert samples[1].channel == "temp"

    async def test_read_once(self, connected, loopback):
        payload = struct.pack("<f", 37.0)
        loopback.inject_frame(_make_data_frame(1, 999, payload))

        sample = await connected.read_once("temp")
        assert sample.channel == "temp"
        assert sample.values == (37.0,)
        assert sample.timestamp_ms == 999

    async def test_unknown_channel(self, connected):
        with pytest.raises(UnknownChannelError):
            await connected.read_once("nonexistent")


class TestSend:
    async def test_send_command_ack(self, connected, loopback):
        loopback.inject_frame(_make_ack_frame(0))
        result = await connected.send("set_gain", gain=2.0)
        assert "seq" in result
        assert len(loopback.written_frames) == 1

    async def test_send_command_nack(self, connected, loopback):
        loopback.inject_frame(_make_nack_frame(0))
        with pytest.raises(CommandNackError):
            await connected.send("set_gain", gain=1.0)

    async def test_send_unknown_command(self, connected):
        with pytest.raises(UnknownCommandError):
            await connected.send("nonexistent")


class TestSampleProperties:
    def test_f32x3_properties(self):
        s = Sample(
            channel="accel",
            channel_id=0,
            timestamp_ms=0,
            values=(1.0, 2.0, 3.0),
            unit="g",
            _channel_type="f32x3",
        )
        assert s.x == 1.0
        assert s.y == 2.0
        assert s.z == 3.0

    def test_f32x6_properties(self):
        s = Sample(
            channel="imu",
            channel_id=0,
            timestamp_ms=0,
            values=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
            unit=None,
            _channel_type="f32x6",
        )
        assert s.ax == 0.1
        assert s.ay == 0.2
        assert s.az == 0.3
        assert s.gx == 0.4
        assert s.gy == 0.5
        assert s.gz == 0.6

    def test_f32x3_raises_on_wrong_type(self):
        s = Sample(
            channel="temp",
            channel_id=1,
            timestamp_ms=0,
            values=(22.0,),
            unit="celsius",
            _channel_type="f32",
        )
        with pytest.raises(AttributeError):
            _ = s.x
