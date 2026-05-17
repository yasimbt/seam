# Seam

Define your sensor channels once in `seam.toml`. Stream, record, inspect, and export — with no boilerplate.

```toml
# seam.toml
[device]
name      = "my-board"
transport = "usb-cdc"

[[channel]]
id      = 0
name    = "accel"
type    = "f32x3"
rate_hz = 100
unit    = "g"
```

```rust
// firmware — generated Channel enum, no manual byte offsets
sampler.send(Channel::Accel, [ax, ay, az]).await;
```

```python
# host — stream by name
async for sample in dev.stream("accel"):
    print(sample.x, sample.y, sample.z)
```

## Install

```bash
pip install seam                  # Python SDK + CLI
pip install seam[mcap]            # + MCAP export
pip install seam[rerun]           # + Rerun live bridge
pip install seam[pandas]          # + DataFrame export
```

Firmware crate (`Cargo.toml`):

```toml
[dependencies]
seam-fw = { version = "0.1", features = ["usb-cdc"] }

[build-dependencies]
seam-build = "0.1"
```

## Quick start

**1. Write `seam.toml`** — see [docs/seam-toml.md](docs/seam-toml.md)

**2. Firmware** — `build.rs` calls `seam_build::generate("seam.toml")`, then use the generated `Channel` enum in `main.rs` — see [docs/firmware.md](docs/firmware.md)

**3. Host** — connect and stream:

```python
from seam import Device

device = Device.from_config("seam.toml")
async with device.connect() as dev:
    async for sample in dev.stream("accel"):
        print(sample.timestamp_ms, sample.x, sample.y, sample.z)
```

Or just inspect live from the terminal:

```bash
seam inspect --config seam.toml
```

## Documentation

| Guide | Description |
|---|---|
| [seam.toml reference](docs/seam-toml.md) | All config keys, data types, validation rules |
| [Python SDK](docs/python-sdk.md) | `Device`, `ConnectedDevice`, `Sample`, exceptions |
| [Firmware SDK](docs/firmware.md) | `seam-fw`, `seam-build`, codegen, transport flags |
| [CLI](docs/cli.md) | `validate`, `record`, `inspect`, `export` |
| [Recording & replay](docs/recording.md) | `.seam` format, replay, offline testing |
| [Bidirectional commands](docs/commands.md) | Host-to-device commands, ACK/NACK |
| [Export bridges](docs/export.md) | MCAP, Rerun, CSV / pandas |
| [Multi-device](docs/multi-device.md) | `MultiDevice` — N devices simultaneously |
| [Wire protocol](docs/wire-protocol.md) | Frame layout, COBS, for alternative implementations |
| [Zephyr module](docs/zephyr.md) | `seam-zephyr` C/CMake module for Zephyr RTOS |
| [Development](docs/development.md) | Dev environment, running tests |

## Repository layout

```
seam/
├── seam-fw/          — no_std firmware crate (Embassy)
├── seam-build/       — build-time codegen crate
├── seam-inspect/     — terminal inspector (Python + textual)
├── seam-py/          — Python host SDK and CLI
├── seam-zephyr/      — C/CMake Zephyr module
├── docs/             — detailed documentation
└── examples/
    ├── accel-logger/ — complete minimal example
    └── multi-node/   — multi-device example
```

## License

MIT OR Apache-2.0
