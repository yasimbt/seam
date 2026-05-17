# Seam

Define your sensor channels once. Stream, record, inspect, and export — with no boilerplate.

Seam is a config-driven SDK for streaming live data from nRF microcontrollers to Python. You write a `seam.toml` describing your channels and transport. The Rust firmware crate and the Python host SDK both read it. Everything else — frame encoding, type checking, channel naming, transport selection — is handled automatically.

```toml
# seam.toml — the only file you write
[device]
name      = "my-board"
transport = "usb-cdc"

[[channel]]
id      = 0
name    = "accel"
type    = "f32x3"
rate_hz = 100
unit    = "g"

[[channel]]
id      = 1
name    = "temperature"
type    = "f32"
rate_hz = 10
unit    = "celsius"
```

```rust
// main.rs — this is all you write
sampler.send(Channel::Accel, [x, y, z]).await;
sampler.send(Channel::Temperature, temp).await;
```

```python
# plot.py — this is all you write
async for sample in dev.stream("accel"):
    print(sample.x, sample.y, sample.z)
```

---

## Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [seam.toml Reference](#seamtoml-reference)
- [Python SDK](#python-sdk)
- [Firmware SDK](#firmware-sdk)
- [CLI](#cli)
- [Recording and Replay](#recording-and-replay)
- [Bidirectional Commands](#bidirectional-commands)
- [Export Bridges](#export-bridges)
- [Multi-device](#multi-device)
- [Wire Protocol](#wire-protocol)
- [Roadmap](#roadmap)

---

## Installation

**Python SDK and CLI:**
```bash
pip install seam
```

**Firmware crate** — add to `Cargo.toml`:
```toml
[dependencies]
seam-fw = { version = "0.1", features = ["usb-cdc"] }

[build-dependencies]
seam-build = "0.1"
```

**Optional extras:**
```bash
pip install seam[mcap]    # MCAP export (Foxglove-compatible)
pip install seam[rerun]   # Rerun live visualisation bridge
pip install seam[pandas]  # DataFrame export
```

---

## Quick Start

### 1. Write seam.toml

```toml
[device]
name      = "sensor-node"
transport = "usb-cdc"

[[channel]]
id      = 0
name    = "accel"
type    = "f32x3"
rate_hz = 100
unit    = "g"

[[channel]]
id      = 1
name    = "temperature"
type    = "f32"
rate_hz = 10
unit    = "celsius"
```

### 2. Set up the firmware crate

`build.rs`:
```rust
fn main() {
    seam_build::generate("seam.toml");
}
```

`src/main.rs`:
```rust
#![no_std]
#![no_main]

use embassy_executor::Spawner;
use seam_fw::{Sampler, transport::UsbCdc};

// Generated from seam.toml: Channel::Accel, Channel::Temperature
include!(concat!(env!("OUT_DIR"), "/seam_generated.rs"));

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_nrf::init(Default::default());
    let mut sampler = Sampler::new(UsbCdc::new(p.USBD));

    loop {
        sampler.send(Channel::Accel, read_accel()).await;
        sampler.send(Channel::Temperature, read_temperature()).await;
        embassy_time::Timer::after_millis(10).await;
    }
}
```

### 3. Stream on the host

```python
import asyncio
from seam import Device

async def main():
    device = Device.from_config("seam.toml")
    async with device.connect() as dev:
        async for sample in dev.stream("accel"):
            print(f"{sample.timestamp_ms}ms  "
                  f"x={sample.x:+.3f}  y={sample.y:+.3f}  z={sample.z:+.3f} {sample.unit}")

asyncio.run(main())
```

### 4. Or just use the inspector

```bash
seam inspect --config seam.toml
```

```
┌─ seam inspector — sensor-node ────────────────────────────────┐
│ accel [f32x3] @ 98.4 Hz                                       │
│ x ▁▂▃▅▆▇▇▆▄▂▁  y ▄▄▃▃▄▅▅▄▃▃▄  z ▇▇▇▇▇▇▇▇▇▇▇                 │
│ x: +0.023g  y: -0.011g  z: +0.981g                           │
├───────────────────────────────────────────────────────────────┤
│ temperature [f32] @ 9.9 Hz                                    │
│ ▄▄▅▅▅▅▅▅▅▆▆                                                   │
│ 24.3 °C   (min 23.9  max 24.7)                                │
├───────────────────────────────────────────────────────────────┤
│ [r] record   [q] quit   [space] pause     USB-CDC connected   │
└───────────────────────────────────────────────────────────────┘
```

---

## seam.toml Reference

### `[device]`

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Device name. Used as BLE advertising name and inspector title. |
| `transport` | string | yes | `"usb-cdc"` or `"ble-nus"` |

### `[[channel]]`

One block per data channel. Repeat for each sensor output.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | integer | yes | Wire identifier (u8). Must be unique. **Never renumber** — existing recordings will decode incorrectly. |
| `name` | string | yes | Channel name. Used in `dev.stream("name")` and generated as `Channel::Name` in Rust. snake_case ASCII only. |
| `type` | string | yes | Payload type — see table below. |
| `rate_hz` | integer | yes | Nominal sample rate. Advisory — SDK uses it for buffer sizing. |
| `unit` | string | no | Physical unit string e.g. `"g"`, `"hPa"`, `"celsius"`. Appears in `sample.unit`. |

### `[[command]]`

Optional. One block per host-to-device command.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | integer | yes | Wire identifier (u8). Separate namespace from channels. Never renumber. |
| `name` | string | yes | Command name. Used in `await dev.send("name", ...)`. snake_case ASCII. |
| `args` | array | no | `[{ name = "x", type = "u8" }]` — zero or more typed arguments. |

### Channel and command data types

| Type | Bytes | Description | Python `sample.values` |
|------|-------|-------------|------------------------|
| `u8` | 1 | Unsigned 8-bit integer | `(int,)` |
| `u16` | 2 | Unsigned 16-bit integer | `(int,)` |
| `u32` | 4 | Unsigned 32-bit integer | `(int,)` |
| `i16` | 2 | Signed 16-bit integer | `(int,)` |
| `i32` | 4 | Signed 32-bit integer | `(int,)` |
| `f32` | 4 | 32-bit float | `(float,)` |
| `f32x3` | 12 | Three floats (e.g. XYZ vector) | `(float, float, float)` |
| `f32x6` | 24 | Six floats (e.g. IMU accel + gyro) | `(float,) × 6` |

---

## Python SDK

### `Device`

```python
Device.from_config(path: str | Path) -> Device
```
Create a `Device` by reading `seam.toml`. Does not connect yet.

```python
device.connect(auto_reconnect: bool = False) -> AsyncContextManager[ConnectedDevice]
```
Connect to the device. Use as an async context manager; the connection closes on exit.

### `ConnectedDevice`

```python
dev.stream(channel: str) -> AsyncIterator[Sample]
```
Yield `Sample` objects for a single named channel until the connection closes or the loop is broken.

```python
dev.stream_all() -> AsyncIterator[Sample]
```
Yield `Sample` objects for all channels interleaved in arrival order.

```python
await dev.read_once(channel: str) -> Sample
```
Return the next single sample from a channel, then stop.

```python
await dev.send(command: str, **kwargs) -> None
```
Send a command to the device. Keyword arguments must match the `args` defined in `seam.toml`.
Raises `CommandNackError` if the device rejects the command.

### `Sample`

```python
@dataclass
class Sample:
    channel:      str        # channel name from seam.toml
    channel_id:   int        # channel id from seam.toml
    timestamp_ms: int        # milliseconds since device boot
    values:       tuple      # typed payload values
    unit:         str | None # unit from seam.toml, or None
```

Convenience properties for typed channels:

| Channel type | Properties |
|---|---|
| `f32x3` | `.x` `.y` `.z` |
| `f32x6` | `.ax` `.ay` `.az` `.gx` `.gy` `.gz` |

### Exceptions

All inherit from `seam.SeamError`.

| Exception | When |
|---|---|
| `ConnectionError` | Device not found, port unavailable, BLE scan timeout |
| `FrameDecodeError` | COBS failure or malformed frame |
| `UnknownChannelError` | Frame arrived for unknown channel ID |
| `UnknownCommandError` | `send()` called with name not in schema |
| `CommandNackError` | Device returned NACK for a command |
| `ConfigError` | `seam.toml` missing, malformed, or invalid |
| `RecordingError` | `.seam` file corrupt or version mismatch |

---

## Firmware SDK

### `Sampler`

```rust
pub struct Sampler<T: Transport> { /* ... */ }

impl<T: Transport> Sampler<T> {
    pub fn new(transport: T) -> Self;

    // Send a typed data frame for a channel
    pub async fn send<V: Encode>(&mut self, channel: Channel, value: V);

    // Register a handler for an incoming command (Phase 4)
    pub fn on_command<F>(&mut self, command: Command, handler: F)
    where
        F: Fn(CommandArgs) + Send + 'static;
}
```

`Channel` and `Command` are generated from your `seam.toml`. The type system enforces that each
channel only accepts the value type declared for it — a type mismatch is a compile error.

### Transport feature flags

```toml
# USB CDC (development, low latency)
seam-fw = { version = "0.1", features = ["usb-cdc"] }

# BLE Nordic UART Service (wireless)
seam-fw = { version = "0.1", features = ["ble-nus"] }

# Both simultaneously
seam-fw = { version = "0.1", features = ["usb-cdc", "ble-nus"] }
```

```rust
use seam_fw::transport::{UsbCdc, BleNus};

let transport = UsbCdc::new(p.USBD);
// or
let transport = BleNus::new(p.RNG, p.ECB, p.RADIO);
```

---

## CLI

Install the CLI with `pip install seam`. All subcommands read `seam.toml` by default.

```bash
# Validate seam.toml — no hardware connection required
seam validate --config seam.toml

# Live terminal inspector — no Python script required
seam inspect --config seam.toml

# Record a session to a .seam file
seam record --config seam.toml --output session.seam

# Record for a fixed duration
seam record --config seam.toml --duration 60s --output calibration.seam

# Export to MCAP (requires pip install seam[mcap])
seam export --input session.seam --format mcap --output session.mcap

# Export a single channel to CSV
seam export --input session.seam --format csv --channel accel --output accel.csv

# Replay a recording to the inspector (no hardware needed)
seam inspect --replay session.seam
```

---

## Recording and Replay

Seam recordings are self-describing `.seam` files. The schema from `seam.toml` is embedded in the
file header, so a recording is readable years later even without the original config.

### Recording from Python

```python
from seam import Device

async def main():
    device = Device.from_config("seam.toml")
    async with device.connect() as dev:
        async with dev.record("session.seam") as rec:
            async for sample in dev.stream_all():
                process(sample)
                # writes automatically happen in the background
```

### Replaying a recording

```python
from seam import Recording

rec = Recording.open("session.seam")

# Iterate over a single channel
for sample in rec.stream("accel"):
    print(sample.x, sample.y, sample.z)

# Or use it exactly like a live device — same API
async with rec.as_device(realtime=True) as dev:
    async for sample in dev.stream("accel"):
        print(sample.timestamp_ms, sample.values)
```

`realtime=True` replays at the original timestamps. `realtime=False` replays as fast as possible —
useful for batch processing and testing.

### Testing without hardware

Because `Recording.as_device()` is API-identical to `Device.connect()`, you can develop and
test your entire host application against a real recording without the hardware connected.

```python
# In production
device = Device.from_config("seam.toml")
source = device.connect()

# In tests / offline development — swap one line
source = Recording.open("calibration.seam").as_device()

# The rest of the code is identical
async with source as dev:
    async for sample in dev.stream("accel"):
        ...
```

---

## Bidirectional Commands

Define commands in `seam.toml` alongside your channels:

```toml
[[command]]
id   = 0
name = "set_rate"
args = [
  { name = "channel_id", type = "u8" },
  { name = "rate_hz",    type = "u16" },
]

[[command]]
id   = 1
name = "trigger_capture"
args = []
```

### Firmware side

The generated `Command` enum provides type-safe dispatch:

```rust
sampler.on_command(Command::SetRate, |args| {
    let channel_id = args.u8();
    let rate_hz    = args.u16();
    update_channel_rate(channel_id, rate_hz);
});

sampler.on_command(Command::TriggerCapture, |_| {
    start_one_shot_capture();
});
```

### Python side

```python
# Send a command with named arguments
await dev.send("set_rate", channel_id=1, rate_hz=50)
await dev.send("trigger_capture")
```

Commands wait for an ACK before returning. `CommandNackError` is raised on NACK.

---

## Export Bridges

### To MCAP (Foxglove-compatible)

```bash
# Via CLI
seam export --input session.seam --format mcap --output session.mcap
```

```python
# From Python
from seam.bridge.mcap import export_mcap
export_mcap("session.seam", "session.mcap")
```

Open the resulting `.mcap` in [Foxglove](https://foxglove.dev) — all channels appear as
typed topics on a shared timeline.

### Live forward to Rerun

```python
from seam import Device
from seam.bridge.rerun import RerunBridge

device = Device.from_config("seam.toml")
async with device.connect() as dev:
    await RerunBridge(app_name="my-sensor").run(dev)
```

Launches a Rerun viewer and streams all channels in real time.

### To pandas / CSV

```python
from seam import Recording

rec = Recording.open("session.seam")

# Single channel as DataFrame
df = rec.to_dataframe("accel")
# columns: timestamp_ms, x, y, z

# All channels
dfs = rec.to_dataframes()
# dict of channel_name → DataFrame
```

```bash
seam export --input session.seam --format csv --channel accel --output accel.csv
```

---

## Multi-device

Stream from multiple devices simultaneously and receive samples tagged by device:

```python
from seam import MultiDevice

fleet = MultiDevice.from_configs({
    "node_a": "node_a/seam.toml",
    "node_b": "node_b/seam.toml",
})

async with fleet.connect() as dev:
    async for sample in dev.stream_all():
        print(f"[{sample.device}] {sample.channel}  {sample.values}")
```

`sample.device` is the key string provided to `from_configs()`.

Timestamps from each device use that device's own boot clock. Seam does not fuse clocks
automatically — if you need clock alignment, record and align in post using a shared event
(e.g. a GPIO trigger on both boards).

---

## Wire Protocol

For contributors and integrators building alternative host implementations.

### Frame layout (after COBS decode)

```
┌────────┬──────────┬────────────────┬──────────┬──────────────────────┐
│  type  │ channel  │  timestamp_ms  │  length  │       payload        │
│ 1 byte │  1 byte  │    4 bytes LE  │  1 byte  │    0–255 bytes LE    │
└────────┴──────────┴────────────────┴──────────┴──────────────────────┘
```

Type byte values: `0x01` data frame · `0x02` command ACK · `0x03` command NACK

### Command frame layout (host → device)

```
┌────────┬────────────┬─────┬──────────┬──────────────────────┐
│  type  │ command_id │ seq │  length  │        args          │
│ 1 byte │   1 byte   │ 1 B │  1 byte  │    0–255 bytes LE    │
└────────┴────────────┴─────┴──────────┴──────────────────────┘
```

Type byte: always `0x10` for host→device.

### COBS framing

Standard COBS encoding. `0x00` is the unambiguous frame delimiter and never appears inside an
encoded frame. After a device reset or partial frame, the host re-syncs on the next `0x00` with
no state to reset.

---

## Repository Layout

```
seam/
├── seam-fw/          — no_std firmware crate (Embassy)
├── seam-build/       — build-time codegen crate
├── seam-inspect/     — terminal inspector (Python + textual)
├── seam-py/          — Python host SDK and CLI
└── examples/
    ├── accel-logger/ — complete minimal example
    └── multi-node/   — multi-device example
```

---

## Roadmap

- [x] USB CDC transport
- [x] BLE NUS transport
- [x] TOML-driven codegen (channels)
- [x] Python streaming API
- [x] `seam record` + `.seam` format
- [x] `seam validate` — config validation without hardware
- [x] `seam inspect` terminal viewer
- [x] Bidirectional commands (TOML-driven)
- [x] MCAP / Rerun / CSV export bridges
- [x] `MultiDevice` — N devices simultaneously
- [ ] `seam-zephyr` — Zephyr / nRF Connect SDK module
- [ ] `seam export --format reductstore` — ReductStore integration
- [ ] Jupyter notebook widget for inline live plots
- [ ] nRF54L15-DK and nRF5340-DK verified board configs

---

## Development

### Environment setup (NixOS / devenv)

The repo ships a [devenv](https://devenv.sh) environment with `gcc`, `pkg-config`, and Python 3.12.
[direnv](https://direnv.net) activates it automatically on `cd`.

```bash
# One-time: allow direnv
direnv allow

# The shell activates automatically from then on.
# Rust toolchain is managed separately via rustup:
rustup toolchain install stable
rustup target add thumbv7em-none-eabihf   # for firmware cross-compilation
```

Alternatively, use the legacy `nix-shell` wrapper:

```bash
nix-shell shell.nix
```

### Running tests

```bash
# Rust (host target — codec, codegen, schema tests)
cargo test -p seam-build -p seam-fw

# Rust clippy (zero warnings enforced)
cargo clippy --all --all-features -- -D warnings

# Firmware cross-compile verification (no hardware needed)
cargo build -p seam-fw --target thumbv7em-none-eabihf --features usb-cdc
cargo build -p seam-fw --target thumbv7em-none-eabihf --features ble-nus

# Python (no hardware)
cd seam-py
pip install -e ".[dev]"
pytest -m "not hardware"

# Python (including hardware tests — requires device connected)
pytest
```

### Installing seam-inspect for development

```bash
pip install -e seam-inspect/
```

---

## License

MIT OR Apache-2.0
