# Python SDK

The Python SDK provides an async-native API for connecting to devices, streaming samples, sending commands, and working with recordings. All public methods are `async`.

Install: `pip install seam`

---

## `Device`

```python
from seam import Device
```

### `Device.from_config(path)`

```python
device = Device.from_config("seam.toml")
```

Reads `seam.toml` and creates a `Device`. Does not connect. Raises `ConfigError` if the file is missing, malformed, or fails validation.

### `device.connect(auto_reconnect=False)`

```python
async with device.connect() as dev:
    ...
```

Returns an async context manager that yields a `ConnectedDevice`. The connection is closed when the `async with` block exits. Pass `auto_reconnect=True` to reconnect automatically on disconnect.

---

## `ConnectedDevice`

Obtained from `device.connect()`. The same methods are available on `Recording` — you can swap between live and recorded data without changing your application code.

### `dev.stream(channel)`

```python
async for sample in dev.stream("accel"):
    print(sample.x, sample.y, sample.z)
```

Yields `Sample` objects for the named channel. Runs until the connection closes or the loop is broken. Raises `UnknownChannelError` if `channel` is not in the schema.

### `dev.stream_all()`

```python
async for sample in dev.stream_all():
    print(sample.channel, sample.values)
```

Yields `Sample` objects for all channels interleaved in arrival order.

### `await dev.read_once(channel)`

```python
sample = await dev.read_once("temperature")
```

Returns the next single sample from the named channel.

### `await dev.send(command, **kwargs)`

```python
await dev.send("set_rate", channel_id=1, rate_hz=50)
await dev.send("trigger_capture")
```

Encodes and sends a command to the device, then waits for ACK. Keyword arguments must match the `args` defined in `seam.toml`. Raises `UnknownCommandError` if the command name is unknown, `CommandNackError` if the device responds with NACK.

### `dev.record(path)`

```python
async with dev.record("session.seam") as rec:
    async for sample in dev.stream_all():
        process(sample)
```

Writes all incoming frames to a `.seam` file while the inner block runs. Frames are written as they arrive in the background — no additional code needed.

---

## `Recording`

```python
from seam import Recording
```

### `await Recording.open(path)`

```python
rec = await Recording.open("session.seam")
```

Opens a `.seam` file. The schema is read from the embedded header — no `seam.toml` needed. Raises `RecordingError` if the file is missing, corrupt, or uses an unsupported format version.

### `rec.stream(channel)` / `rec.stream_all()`

Identical signatures to `ConnectedDevice`. Iterates over the recorded frames for that channel.

```python
async for sample in rec.stream("accel"):
    process(sample)
```

### `rec.as_device(realtime=False)`

```python
async with rec.as_device(realtime=True) as dev:
    async for sample in dev.stream("accel"):
        ...
```

Returns an async context manager yielding an object with the full `ConnectedDevice` API. Use this to run live-device application code against a recording.

- `realtime=True` — replay at original timestamps (wall-clock delay between frames)
- `realtime=False` — replay as fast as possible (useful for batch processing and tests)

### `rec.to_dataframe(channel)` / `rec.to_dataframes()`

```python
# requires: pip install seam[pandas]
df  = rec.to_dataframe("accel")     # → DataFrame with columns: timestamp_ms, x, y, z
dfs = rec.to_dataframes()           # → dict[str, DataFrame], one per channel
```

---

## `MultiDevice`

```python
from seam import MultiDevice

fleet = MultiDevice.from_configs({
    "node_a": "node_a/seam.toml",
    "node_b": "node_b/seam.toml",
})

async with fleet.connect() as dev:
    async for sample in dev.stream_all():
        print(sample.device, sample.channel, sample.values)
```

`sample.device` is the key string provided to `from_configs()`. See [multi-device.md](multi-device.md) for details.

---

## `Sample`

```python
@dataclass
class Sample:
    channel:      str        # channel name from seam.toml
    channel_id:   int        # wire channel id
    timestamp_ms: int        # milliseconds since device boot
    values:       tuple      # payload values (typed per channel type)
    unit:         str | None # unit from seam.toml, or None
```

### Convenience properties

`f32x3` channels expose:

```python
sample.x   # values[0]
sample.y   # values[1]
sample.z   # values[2]
```

`f32x6` channels expose:

```python
sample.ax  # values[0]
sample.ay  # values[1]
sample.az  # values[2]
sample.gx  # values[3]
sample.gy  # values[4]
sample.gz  # values[5]
```

---

## Exceptions

All exceptions inherit from `seam.SeamError`.

| Exception | Raised when |
|---|---|
| `SeamError` | Base class — catch this to handle all Seam errors |
| `ConnectionError` | Device not found, port unavailable, BLE scan timeout |
| `FrameDecodeError` | COBS decode failure or malformed TLV frame |
| `UnknownChannelError` | Frame arrived for a channel ID not present in the schema |
| `UnknownCommandError` | `send()` called with a name not defined in `seam.toml` |
| `CommandNackError` | Device returned NACK for a sent command |
| `ConfigError` | `seam.toml` missing, malformed, or fails validation |
| `RecordingError` | `.seam` file corrupt, unsupported version, or invalid schema |

---

## Testing without hardware

Because `Recording.as_device()` is API-identical to `Device.connect()`, you can develop and test your entire application against a real recording:

```python
# Production
source = Device.from_config("seam.toml").connect()

# Tests / offline — swap one line
source = (await Recording.open("fixture.seam")).as_device()

# Everything else is identical
async with source as dev:
    async for sample in dev.stream("accel"):
        assert sample.unit == "g"
```

Hardware tests should use `@pytest.mark.hardware` so they're skipped in CI.
