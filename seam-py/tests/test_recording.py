import json
import struct
import tempfile
from pathlib import Path

import pytest

from seam.codec import DATA, STRUCT_FMT, cobs_encode
from seam.exceptions import RecordingError, UnknownChannelError
from seam.recording import Recording, MAGIC, FILE_VERSION


def _make_seam_file(schema, frames, path):
    schema_json = json.dumps(schema).encode("utf-8")
    header = (
        MAGIC
        + bytes([FILE_VERSION, 0x01])
        + struct.pack("<H", len(schema_json))
        + schema_json
    )
    with open(path, "wb") as f:
        f.write(header)
        for frame in frames:
            f.write(frame)


SCHEMA = {
    "device": {"name": "test", "transport": "usb-cdc"},
    "channels": [
        {"id": 0, "name": "accel", "type": "f32x3", "rate_hz": 100, "unit": "g"},
        {"id": 1, "name": "temp", "type": "f32", "rate_hz": 10, "unit": "celsius"},
    ],
    "commands": [],
}


def _data_frame(channel_id, timestamp, payload):
    return (
        bytes([DATA, channel_id])
        + struct.pack("<I", timestamp)
        + bytes([len(payload)])
        + payload
    )


class TestRecordingOpen:
    async def test_open_valid_file(self):
        frames = [
            _data_frame(0, 1000, struct.pack("<fff", 1.0, 2.0, 3.0)),
            _data_frame(1, 2000, struct.pack("<f", 25.0)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, frames, path)

        rec = await Recording.open(path)
        assert rec._schema == SCHEMA
        assert len(rec._frames) == 2
        Path(path).unlink()

    async def test_open_missing_file(self):
        with pytest.raises(RecordingError, match="not found"):
            await Recording.open("/nonexistent/file.seam")

    async def test_open_invalid_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            f.write(b"XXXX" + b"\x00" * 20)
            path = f.name
        with pytest.raises(RecordingError, match="Invalid magic"):
            await Recording.open(path)
        Path(path).unlink()

    async def test_open_invalid_version(self):
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            f.write(MAGIC + bytes([0xFF, 0x01]) + b"\x00" * 20)
            path = f.name
        with pytest.raises(RecordingError, match="Unsupported file version"):
            await Recording.open(path)
        Path(path).unlink()


class TestRecordingStream:
    async def test_stream_channel(self):
        frames = [
            _data_frame(0, 1000, struct.pack("<fff", 1.0, 2.0, 3.0)),
            _data_frame(0, 2000, struct.pack("<fff", 4.0, 5.0, 6.0)),
            _data_frame(1, 3000, struct.pack("<f", 25.0)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, frames, path)

        rec = await Recording.open(path)
        samples = []
        async for s in rec.stream("accel"):
            samples.append(s)

        assert len(samples) == 2
        assert samples[0].values == (1.0, 2.0, 3.0)
        assert samples[1].values == (4.0, 5.0, 6.0)
        Path(path).unlink()

    async def test_stream_all(self):
        frames = [
            _data_frame(0, 1000, struct.pack("<fff", 1.0, 0.0, 0.0)),
            _data_frame(1, 1500, struct.pack("<f", 22.0)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, frames, path)

        rec = await Recording.open(path)
        samples = []
        async for s in rec.stream_all():
            samples.append(s)

        assert len(samples) == 2
        assert samples[0].channel == "accel"
        assert samples[1].channel == "temp"
        Path(path).unlink()

    async def test_read_once(self):
        frames = [
            _data_frame(1, 500, struct.pack("<f", 37.0)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, frames, path)

        rec = await Recording.open(path)
        sample = await rec.read_once("temp")
        assert sample.values == (37.0,)
        assert sample.timestamp_ms == 500
        Path(path).unlink()

    async def test_read_once_no_samples(self):
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, [], path)

        rec = await Recording.open(path)
        with pytest.raises(RecordingError, match="No samples found"):
            await rec.read_once("accel")
        Path(path).unlink()

    async def test_unknown_channel(self):
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, [], path)

        rec = await Recording.open(path)
        with pytest.raises(UnknownChannelError):
            async for _ in rec.stream("nonexistent"):
                pass
        Path(path).unlink()


class TestRecordingSend:
    async def test_send_raises_not_implemented(self):
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, [], path)

        rec = await Recording.open(path)
        with pytest.raises(NotImplementedError, match="not available on recordings"):
            await rec.send("reset")
        Path(path).unlink()


class TestRecordingSave:
    async def test_save_and_reload(self):
        frames = [
            _data_frame(0, 1000, struct.pack("<fff", 1.0, 2.0, 3.0)),
        ]
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            path = f.name
        _make_seam_file(SCHEMA, frames, path)

        rec = await Recording.open(path)
        with tempfile.NamedTemporaryFile(suffix=".seam", delete=False) as f:
            out_path = f.name

        await rec.save(out_path)

        rec2 = await Recording.open(out_path)
        assert rec2._schema == SCHEMA
        assert len(rec2._frames) == 1
        Path(path).unlink()
        Path(out_path).unlink()
