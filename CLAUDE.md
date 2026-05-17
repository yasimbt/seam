# CLAUDE.md

This is the authoritative guide for any Claude Code agent working on the Seam project.
Read it entirely before touching any code, creating any file, or running any command.

---

## What Seam Is

Seam is a config-driven SDK for streaming live sensor data from nRF microcontrollers to Python.

You define your channels once in `seam.toml`. The Rust firmware crate reads it at build time
via codegen and the Python SDK reads it at runtime. Both sides derive their entire schema from
that one file — no duplication, no manual byte offsets, no per-project glue code.

Beyond live streaming, Seam provides: a recording format (`.seam`), a terminal live inspector
(`seam inspect`), bidirectional host-to-device commands, and export bridges to MCAP/Rerun/CSV.

### Components

| Component | Language | Role |
|---|---|---|
| `seam-fw` | Rust · no_std · Embassy | Firmware crate — runs on the nRF device |
| `seam-build` | Rust · build-time · std | Codegen: reads `seam.toml` → typed `Channel` + `Command` enums |
| `seam` (Python) | Python 3.11+ · asyncio | Host SDK: connect, stream, record, replay, export |
| `seam-inspect` | Python 3.11+ · textual | Terminal live inspector — shares transport code with Python SDK |
| `seam-zephyr` | C / CMake | Zephyr module (future phase) |

---

## Repository Layout

```
seam/
├── CLAUDE.md                          ← you are here
├── README.md
│
├── seam-fw/                           ← no_std firmware crate
│   ├── Cargo.toml
│   ├── build.rs                       ← calls seam_build::generate()
│   └── src/
│       ├── lib.rs                     ← Sampler, public API, include! of generated code
│       ├── codec.rs                   ← COBS framer, TLV encoder/decoder
│       ├── error.rs                   ← SeamError enum
│       └── transport/
│           ├── mod.rs                 ← Transport trait
│           ├── usb_cdc.rs             ← USB CDC ACM  (feature = "usb-cdc")
│           └── ble_nus.rs             ← BLE Nordic UART Service  (feature = "ble-nus")
│
├── seam-build/                        ← build-time codegen (std, host only)
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs                     ← pub fn generate(path: &str)
│       ├── schema.rs                  ← TOML → DeviceSchema, ChannelDef, CommandDef
│       └── codegen.rs                 ← schema → Rust source string
│
├── seam-inspect/                      ← terminal inspector (Python + textual)
│   ├── pyproject.toml
│   └── seam_inspect/
│       └── __main__.py                ← textual TUI, uses Python transport layer
│
├── seam-py/                           ← Python host SDK and CLI
│   ├── pyproject.toml
│   └── seam/
│       ├── __init__.py                ← public re-exports and exception classes
│       ├── device.py                  ← Device, ConnectedDevice
│       ├── recording.py               ← Recording — .seam file reader/writer
│       ├── multi.py                   ← MultiDevice — N devices simultaneously
│       ├── schema.py                  ← TOML parser → channel + command registry
│       ├── codec.py                   ← COBS decode, TLV frame parser, command encoder
│       ├── cli.py                     ← seam record / inspect / export CLI entry points
│       ├── bridge/
│       │   ├── __init__.py
│       │   ├── mcap.py                ← .seam → .mcap
│       │   ├── rerun.py               ← live forward to Rerun viewer
│       │   └── csv.py                 ← .seam → CSV / pandas DataFrame
│       └── transport/
│           ├── __init__.py            ← Transport protocol (structural subtype)
│           ├── serial.py              ← USB CDC via pyserial-asyncio
│           └── ble.py                 ← BLE NUS via bleak
│
└── examples/
    ├── accel-logger/                  ← complete minimal example
    │   ├── seam.toml
    │   ├── Cargo.toml
    │   ├── src/main.rs
    │   └── plot.py
    └── multi-node/                    ← MultiDevice example
        ├── node_a/seam.toml
        ├── node_b/seam.toml
        └── fuse.py
```

---

## Wire Protocol

This is the contract between firmware and host. Any change requires coordinated updates to
`seam-fw/src/codec.rs` AND `seam-py/seam/codec.py`. Never change one without the other.
Any breaking change requires bumping the version byte and writing a migration note.

### Data frame (device → host)

All frames are COBS-encoded on the wire. `0x00` is the packet delimiter and never appears
inside an encoded frame. After COBS decoding, the payload layout is:

```
┌────────┬──────────┬────────────────┬──────────┬──────────────────────┐
│  type  │ channel  │  timestamp_ms  │  length  │       payload        │
│ 1 byte │  1 byte  │    4 bytes LE  │  1 byte  │    0–255 bytes LE    │
└────────┴──────────┴────────────────┴──────────┴──────────────────────┘
```

- `type`: `0x01` = data frame · `0x02` = command ACK · `0x03` = command NACK
- `channel`: u8 matching `id` in `seam.toml` for data frames; echoed command id for ACK/NACK
- `timestamp_ms`: u32 little-endian — milliseconds since device boot
- `length`: u8 — byte count of payload only
- `payload`: little-endian values per the channel's type

### Command frame (host → device)

```
┌────────┬────────────┬─────┬──────────┬──────────────────────┐
│  type  │ command_id │ seq │  length  │        args          │
│ 1 byte │   1 byte   │ 1 B │  1 byte  │    0–255 bytes LE    │
└────────┴────────────┴─────┴──────────┴──────────────────────┘
```

- `type`: always `0x10` for host→device commands
- `command_id`: u8 matching `id` in a `[[command]]` block
- `seq`: u8 — rolling sequence counter; firmware echoes it in ACK/NACK for response matching
- `args`: little-endian encoded arguments per the command's `args` list in `seam.toml`

### Channel / command arg data types

| TOML type | Bytes | Rust type  | Python struct |
|-----------|-------|------------|---------------|
| `u8`      | 1     | `u8`       | `B`           |
| `u16`     | 2     | `u16`      | `<H`          |
| `u32`     | 4     | `u32`      | `<I`          |
| `i16`     | 2     | `i16`      | `<h`          |
| `i32`     | 4     | `i32`      | `<i`          |
| `f32`     | 4     | `f32`      | `<f`          |
| `f32x3`   | 12    | `[f32; 3]` | `<fff`        |
| `f32x6`   | 24    | `[f32; 6]` | `<ffffff`     |

The same type table applies to channel payloads and command arguments.

### COBS rules

- Standard COBS — no custom variant
- Rust: `cobs` crate (already in `Cargo.toml`)
- Python: implemented directly in `codec.py`, no external dependency

---

## seam.toml Schema Reference

### `[device]`

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `name` | string | yes | BLE advertising name and inspector display name |
| `transport` | string | yes | `"usb-cdc"` or `"ble-nus"` |

### `[[channel]]`

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `id` | u8 | yes | Wire identifier. **Never renumber.** Breaking change if changed. |
| `name` | string | yes | snake_case ASCII. Must be valid as a Python identifier and Rust variant. |
| `type` | string | yes | One of the eight types in the table above. |
| `rate_hz` | integer | yes | Advisory. Used for Python buffer sizing. Not enforced by firmware. |
| `unit` | string | no | Physical unit e.g. `"g"`, `"hPa"`, `"celsius"`. In `Sample.unit`. |

### `[[command]]`

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `id` | u8 | yes | Wire identifier. Separate namespace from channel ids. Never renumber. |
| `name` | string | yes | snake_case. Used as a Python `await dev.send("name", ...)` call and Rust enum variant. |
| `args` | array | no | `[{ name = "x", type = "u8" }, ...]` — zero or more typed arguments. |

### Validation rules (enforced by seam-build and schema.py)

- Channel `id` values must be unique within `[[channel]]` blocks.
- Command `id` values must be unique within `[[command]]` blocks.
- Channel and command `id` namespaces are independent.
- All `name` values: lowercase ASCII, underscores allowed, no leading digits.
- `type` must be exactly one of the eight strings in the type table.

---

## .seam Recording Format

Any agent reading or writing `.seam` files must follow this spec exactly.

```
[File header — fixed section]
  magic       : 4 bytes  — ASCII b"SEAM"
  version     : 1 byte   — 0x01 (file format version)
  wire_version: 1 byte   — 0x01 (wire protocol version at time of recording)
  schema_len  : 2 bytes  — little-endian u16, byte length of schema_json

[File header — schema section]
  schema_json : schema_len bytes — UTF-8 JSON snapshot of all channel defs from seam.toml

[Frames — repeated until EOF]
  Each entry is a raw COBS-decoded data frame payload (same layout as wire protocol).
  Written in arrival order. No additional framing between entries.
```

The schema is embedded in the file so it is self-describing. A `.seam` file must decode
correctly using only the embedded schema, without the original `seam.toml`.

The `wire_version` byte records which wire protocol version was in use when the recording
was made. If the wire protocol changes in a future version, decoders can use this byte to
select the correct parsing logic. Any breaking change to the wire protocol requires:
1. Incrementing the wire version byte
2. Maintaining backward-compatible decoders for all previous versions
3. Writing a migration note in the changelog

---

## Rust Conventions

### seam-fw (no_std)

- Strictly `no_std`. No `std`. No `alloc` unless an explicit Cargo feature enables it.
- Embassy runtime only: `embassy-executor`, `embassy-time`, `embassy-nrf`.
- Transport variants are Cargo features. All transport-specific code behind `#[cfg(feature = "...")]`.
- No `unwrap()` or `expect()` in library code. Return `Result<_, SeamError>` everywhere.
- `SeamError` is in `error.rs`. Never add a catch-all `Other(String)` variant.
- All COBS and TLV logic lives in `codec.rs`. Nothing else touches raw bytes.
- Command handler registration is done via closures passed to `sampler.on_command()`. The
  generated `Command` enum is passed as the first argument. Do not hardcode command IDs.

### seam-build (std, build-time)

- `std` crate, runs on the host machine during `cargo build`. May use `std::fs`, `std::io`.
- Generated file always goes to `$OUT_DIR/seam_generated.rs`. Never anywhere else.
- `include!` it in `seam-fw/src/lib.rs`:
  `include!(concat!(env!("OUT_DIR"), "/seam_generated.rs"));`
- Run `rustfmt` on generated source before writing. Output must be valid formatted Rust.
- Generated `Channel` enum: `#[derive(Copy, Clone, Debug, PartialEq, Eq)]`
- Generated `Command` enum: same derives.
- Never commit generated files. They are build artifacts.

### Rust testing

- Codec encode/decode tests in `codec.rs` under `#[cfg(test)]`.
- Tests run on host (`cargo test`), not cross-compiled.
- Stub hardware peripherals with `#[cfg(test)]`.
- Every channel type needs a round-trip encode→decode test.
- Every command arg type needs an encode test.

---

## Python Conventions

### General

- Python 3.11+. Use `tomllib` from stdlib.
- All public methods are `async`. No blocking I/O on the event loop thread.
- Public surface: `Device`, `Recording`, `MultiDevice`, `Sample` and exceptions from `__init__.py`.
  Everything else is internal.
- `Recording` must expose the same streaming methods as `ConnectedDevice`. Same signatures, same
  behaviour where meaningful. Where a method cannot apply (e.g. `send()` on a replay), raise
  `NotImplementedError` with a clear message explaining why.

### Transport protocol

```python
class Transport(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read_frame(self) -> bytes: ...        # one decoded frame payload, blocks until available
    async def write_frame(self, data: bytes) -> None: ...  # sends encoded bytes to device
```

### Sample dataclass

```python
@dataclass
class Sample:
    channel:      str
    channel_id:   int
    timestamp_ms: int
    values:       tuple
    unit:         str | None

# Auto-added convenience properties:
# f32x3 → .x  .y  .z
# f32x6 → .ax .ay .az .gx .gy .gz
```

### Exceptions

All inherit from `SeamError`.

| Exception | Raised when |
|---|---|
| `SeamError` | Base class |
| `ConnectionError` | Device not found, port unavailable, BLE scan timeout |
| `FrameDecodeError` | COBS failure or malformed frame structure |
| `UnknownChannelError` | Received frame for channel ID not in schema |
| `UnknownCommandError` | `send()` called with name not in schema |
| `CommandNackError` | Device returned NACK for a sent command |
| `ConfigError` | `seam.toml` missing, malformed, or fails validation |
| `RecordingError` | `.seam` file corrupt, version unsupported, or schema invalid |

Never silently swallow exceptions in transport code. Always re-raise or wrap in a `SeamError`.

### Approved runtime dependencies

| Package | Use | Install |
|---|---|---|
| `pyserial-asyncio` | USB CDC transport | core |
| `bleak` | BLE transport | core |
| `click` | CLI subcommands | core |
| `mcap` | MCAP export bridge | `pip install seam[mcap]` |
| `rerun-sdk` | Rerun live bridge | `pip install seam[rerun]` |
| `pandas` | DataFrame export | `pip install seam[pandas]` |

Any addition to the core install requires explicit justification in the PR.

### Python testing

- `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`).
- `LoopbackTransport` in `tests/conftest.py` — accepts a list of pre-encoded frames, yields
  them from `read_frame()`. Use for all unit tests that don't need hardware.
- Hardware tests: `@pytest.mark.hardware`, skipped by default in CI.
- Tests: `seam-py/tests/`

---

## Common Extension Tasks

### Adding a new transport

**Firmware side** (`seam-fw/src/transport/`):
1. Create `your_transport.rs` implementing the `Transport` trait
2. Gate with `#[cfg(feature = "your-transport")]`
3. Re-export from `transport/mod.rs` under the same gate
4. Add the feature to `seam-fw/Cargo.toml`
5. Add the transport string to `VALID_TRANSPORTS` in `seam-build/src/schema.rs`

**Python side** (`seam-py/seam/transport/`):
1. Create `your_transport.py` implementing all four methods of the `Transport` protocol
2. Register it in `device.py` → `_transport_for()` factory
3. Add the transport string to validation in `schema.py`

### Adding a new channel or command data type

All five steps are required. Do not skip any.

1. Add to `VALID_TYPES` in `seam-build/src/schema.rs`
2. Add Rust mapping in `seam-build/src/codegen.rs` → `rust_type_for()`
3. Add byte size in `seam-fw/src/codec.rs` → `payload_size_for()`
4. Add struct format in `seam-py/seam/codec.py` → `STRUCT_FMT`
5. Add round-trip test in `codec.rs` and `codec.py`
6. Update the type table in `CLAUDE.md` and `README.md`

### Adding a new CLI subcommand

1. Add function in `seam-py/seam/cli.py` with `@cli.command()` and `click` decorators
2. Add test in `seam-py/tests/test_cli.py`
3. Document in the CLI section of `README.md`

### Adding `seam validate` CLI

Parses `seam.toml`, runs all validation rules, and prints derived channel/command info.
No hardware connection required.

1. Add `validate()` function in `seam-py/seam/cli.py` with `@cli.command()` and `click` decorators
2. Reuse schema validation from `schema.py` — do not duplicate validation logic
3. Print channels with types/rates/units, commands with argument signatures, any warnings
4. Exit code 0 if valid, 1 if not
5. Add test in `seam-py/tests/test_cli.py` with valid and invalid TOML fixtures
6. Document in the CLI section of `README.md`

### Adding a new export bridge

1. Create `seam-py/seam/bridge/your_format.py`
2. Add an optional dependency entry to `pyproject.toml`
3. Add a `seam export --format your-format` branch in `cli.py`
4. Add documentation and example to `README.md`

---

## Hard Rules — Never Do These

- **Never hardcode a channel ID, channel name, or command ID.** All identifiers come from
  `seam.toml` via codegen (Rust) or schema parsing (Python).
- **Never break the wire protocol** without bumping the version byte and writing migration notes.
- **Never add `std` to `seam-fw`.** It must remain `no_std`.
- **Never write generated code into the source tree.** Only to `$OUT_DIR`.
- **Never use `unwrap()` or `expect()` in library code.** Only in examples and tests.
- **Never renumber `channel.id` or `command.id` values.** They are wire identifiers. Changing them
  silently corrupts existing `.seam` recordings and live sessions.
- **Never add a core Python runtime dependency** without justification. Keep `pip install seam` lean.
- **Never break `Recording` / `Device` API symmetry.** If `ConnectedDevice` gains a method,
  `Recording` must implement it or raise `NotImplementedError` with a clear message.
- **Never silently swallow exceptions** in transport adapters or codec functions.

---

## PR Checklist

- [ ] `cargo clippy --all-features -- -D warnings` — zero warnings
- [ ] `cargo test -p seam-fw` and `cargo test -p seam-build` pass
- [ ] `pytest -m "not hardware"` passes in `seam-py/`
- [ ] Wire protocol tables in this file are current if framing changed
- [ ] Wire version byte incremented and migration note written if protocol changed
- [ ] `.seam` format spec in this file is current if recording format changed
- [ ] Type table updated in both `CLAUDE.md` and `README.md` if types changed
- [ ] All new public API has `///` doc comments (Rust) or docstrings (Python)
- [ ] `examples/accel-logger/` still builds and `plot.py` still runs
- [ ] `README.md` updated if public API, CLI, or `seam.toml` schema changed

---

## Useful Commands

```bash
# ── Rust ──────────────────────────────────────────────────────

# Build firmware (ARM target + nRF HAL required)
cd seam-fw
cargo build --target thumbv7em-none-eabihf --features usb-cdc

# Host-side tests
cargo test -p seam-fw
cargo test -p seam-build

# Lint everything
cargo clippy --all --all-features -- -D warnings

# ── Python ────────────────────────────────────────────────────

# Install in dev mode with all optional deps
cd seam-py
pip install -e ".[dev,mcap,rerun,pandas]"

# Run unit tests (no hardware required)
pytest -m "not hardware"

# Run all tests including hardware
pytest

# ── CLI ───────────────────────────────────────────────────────

seam validate --config seam.toml
seam record    --config seam.toml --output session.seam
seam inspect   --config seam.toml
seam export    --input session.seam --format mcap --output session.mcap
seam export    --input session.seam --format csv  --channel accel --output accel.csv

# ── Examples ──────────────────────────────────────────────────

cd examples/accel-logger
cargo build --target thumbv7em-none-eabihf
python plot.py
```

---

## Design Decisions — Do Not Reverse Without Documentation

**Why TOML and not proc-macros?**
Proc-macros are Rust-only. TOML is read by both the Rust build step and the Python runtime.
A proc-macro approach would require channels to be defined twice, which defeats the single source
of truth principle that the entire project is built on.

**Why COBS and not length-prefix framing?**
COBS is self-synchronising. After a device reset mid-stream, the host re-syncs on the next
`0x00` delimiter with no state to reset. Length-prefix framing can get permanently desynchronised
on a single corrupted length byte.

**Why a custom `.seam` format and not MCAP directly?**
MCAP is excellent but carries a non-trivial binary size and has C++ heritage. `.seam` is trivially
implemented in both Rust and Python with zero dependencies, keeps the core install lean, and
exports to MCAP via the optional bridge. Users who need MCAP get it; users who don't are not
burdened by it.

**Why is `Recording` API-identical to `ConnectedDevice`?**
The primary use case for recordings is developing and testing the host application without hardware.
If the APIs diverged, every developer would maintain two code paths. Symmetry is a hard constraint.

**Why asyncio?**
Sensor streaming is I/O-bound. Blocking APIs force manual thread management. asyncio-native code
composes correctly with async data pipelines, async queues, and `async for` loops in notebooks.

**Why Embassy and not RTIC or bare metal?**
Embassy's async task model maps directly onto the firmware use case. The `Transport` trait is
intentionally swappable so a Zephyr implementation can be added later without changing `Sampler`.
