# Recording and Replay

Seam recordings are self-describing `.seam` files. The schema from `seam.toml` is embedded in the file header, so a recording is readable years later without the original config file.

---

## Recording from Python

```python
from seam import Device

device = Device.from_config("seam.toml")
async with device.connect() as dev:
    async with dev.record("session.seam") as rec:
        async for sample in dev.stream_all():
            process(sample)   # frames are written automatically in the background
```

Or from the CLI without writing any Python:

```bash
seam record --output session.seam
seam record --output calibration.seam --duration 60s
```

---

## Replaying a recording

```python
from seam import Recording

rec = await Recording.open("session.seam")

# Stream a single channel
async for sample in rec.stream("accel"):
    print(sample.x, sample.y, sample.z)

# Stream all channels interleaved
async for sample in rec.stream_all():
    print(sample.channel, sample.timestamp_ms, sample.values)
```

### Replay as a live device

```python
# realtime=True  — replays with original timestamps (wall-clock delay between frames)
# realtime=False — replays as fast as possible (default)
async with rec.as_device(realtime=True) as dev:
    async for sample in dev.stream("accel"):
        print(sample.timestamp_ms, sample.values)
```

`as_device()` returns an object with the full `ConnectedDevice` API. This is the same interface as a live connection — see [python-sdk.md](python-sdk.md).

---

## Testing without hardware

Because `Recording.as_device()` is API-identical to `Device.connect()`, you can develop and test your entire host application against a real recording:

```python
# In production
source = Device.from_config("seam.toml").connect()

# In tests — swap one line, nothing else changes
source = (await Recording.open("tests/fixtures/accel_session.seam")).as_device()

async with source as dev:
    async for sample in dev.stream("accel"):
        assert -2.0 < sample.x < 2.0
```

Record a short session once with real hardware, commit the `.seam` file as a test fixture, and all future CI runs work without a device.

---

## `.seam` file format

The file is binary. Layout:

```
[Fixed header — 8 bytes]
  magic        : 4 bytes   — ASCII "SEAM"
  version      : 1 byte    — 0x01 (file format version)
  wire_version : 1 byte    — 0x01 (wire protocol version at record time)
  schema_len   : 2 bytes   — little-endian u16, length of the JSON schema

[Schema — schema_len bytes]
  schema_json  : UTF-8 JSON snapshot of all channel definitions

[Frames — repeated until EOF]
  Each entry is a raw COBS-decoded TLV frame payload (same layout as the wire protocol).
  Written in arrival order. No additional framing between entries.
```

The embedded schema is sufficient to decode all frames — the original `seam.toml` is not needed.

### Versioning

`wire_version` records which version of the wire protocol was active when the file was recorded. If the wire protocol ever changes, decoders select parsing logic based on this byte. Backward-compatible decoders for all prior versions must be maintained.

---

## Pandas / DataFrame export

```python
# requires: pip install seam[pandas]
rec = await Recording.open("session.seam")

df  = rec.to_dataframe("accel")
# columns: timestamp_ms, x, y, z  (f32x3)

df  = rec.to_dataframe("temperature")
# columns: timestamp_ms, temperature  (scalar — column named after channel)

dfs = rec.to_dataframes()
# dict[str, DataFrame] — one entry per channel
```

Via CLI:

```bash
seam export --input session.seam --format csv --channel accel --output accel.csv
```
