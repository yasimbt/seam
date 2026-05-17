# Seam — Market Research & Feature Plan

---

## The Competitive Landscape

### Who exists and what they do

| Tool | Target user | What it does well | What it doesn't do |
|---|---|---|---|
| **Edge Impulse Data Forwarder** | ML engineers on nRF/Arduino | Collects sensor data via serial for ML training in the cloud | Tied to Edge Impulse platform, cloud-dependent, not general-purpose streaming, no Rust firmware SDK |
| **Rerun** | Robotics / CV engineers | Stunning multimodal visualisation (3D, images, time series), Rust+Python+C++ SDKs | Built for robotics teams, requires a running Rerun server, massive dependency, overkill for small embedded projects, no firmware side at all |
| **Foxglove + MCAP** | Robotics teams (ROS) | Best-in-class data platform, MCAP log format, team collaboration | ROS-centric, no firmware SDK, no embedded transport layer, paid beyond 3 users, heavyweight setup |
| **RoKiX (Rohm)** | IMU evaluation engineers | Firmware + Python client for their specific sensor nodes, USB/BLE | Locked to Rohm hardware, no TOML config, no general-purpose channel types, no Rust |
| **nRF Connect for Desktop** | Nordic SDK users | BLE device management, UART terminal, basic logging | No structured streaming, no Python SDK, not programmable, no data model |
| **pyserial / bleak (raw)** | Any embedded developer | Universal, widely known | Requires every developer to write their own framing, codec, reconnect logic, and schema by hand — every single project |
| **defmt + probe-rs** | Embedded Rust developers | Excellent structured logging *from* device for debugging | Debug/logging only, not for application-level data streaming to a host app |
| **PlotJuggler** | Engineers doing data analysis | Excellent live time-series plotting from ROS/CSV/UDP | Not an SDK, requires manual integration, no embedded firmware side |

### The gap Seam fills

Every tool above is either:
- **Platform-locked** (Edge Impulse, RoKiX, nRF Connect) — tied to a vendor ecosystem
- **Robotics-first and heavyweight** (Rerun, Foxglove) — massive setup, ROS assumptions, overkill for a single nRF dev board
- **Raw plumbing** (pyserial, bleak) — gives you bytes, leaves all structure to you
- **Debug-only** (defmt, probe-rs) — wrong direction: device → developer, not device → application

**Nobody owns the "one config file, drop in the crate, stream to Python in 10 minutes" workflow for embedded Rust + nRF.**

That is Seam's lane.

---

## Gap Analysis → Feature Additions

The original plan was solid for MVP. The gaps in the market justify expanding it significantly.
Features are grouped into implementation phases so nothing gets bloated before it's needed.

---

## Phase 1 — Core (original MVP, revised)

What was already planned, hardened:

- `seam.toml` as single source of truth for channels, types, transport
- `seam-fw` Rust crate: `no_std`, Embassy, USB CDC transport, COBS+TLV wire protocol
- `seam-build` codegen crate: reads TOML → typed `Channel` enum in `$OUT_DIR`
- `seam` Python SDK: `Device.from_config()`, async `stream()`, `stream_all()`, typed `Sample`
- BLE NUS transport (alongside USB CDC)

---

## Phase 2 — Recording & Replay

**Gap identified:** Every tool forces you to choose: live view OR recorded file. There is no lightweight embedded-native record/replay that isn't tied to ROS or Foxglove.

**Features:**

### `seam record` CLI
A command-line tool that connects to a device and writes a `.seam` file — a dead-simple binary log format built on the same COBS+TLV frames already used on the wire. No new encoding to learn.

```bash
seam record --config seam.toml --output session_2024-01-15.seam
seam record --config seam.toml --duration 60s --output calibration.seam
```

### `.seam` file format
A minimal container: file header (schema snapshot from the TOML) + chronological frames verbatim from the wire. Because the schema is embedded in the file, recordings are self-describing — you can replay them years later without the original TOML.

```
[seam file header]
  magic: b"SEAM"
  version: u8
  schema_json: variable length  ← snapshot of channels from seam.toml at record time
[frames]
  ... raw COBS-decoded frames in arrival order
```

### Replay in Python
```python
from seam import Recording

rec = Recording.open("session_2024-01-15.seam")
for sample in rec.stream("accel"):
    process(sample)

# Same API as live Device — swap Device for Recording with no code changes
```

### Replay as a live device (for testing)
```python
# Feed a recording back through the SDK as if it were a live device
# Lets you develop and test your host application against real data
# without needing the hardware plugged in
rec = Recording.open("calibration.seam")
async with rec.as_device(realtime=True) as dev:
    async for sample in dev.stream("accel"):
        ...
```

**Why this matters:** Developers can record data in the lab, iterate on their Python analysis code on the train, then reconnect to hardware. No cloud, no ROS bag, no Foxglove account.

---

## Phase 3 — `seam inspector` (built-in live viewer)

**Gap identified:** Rerun and Foxglove are the only decent live visualisers, but both require substantial setup and are aimed at robotics teams with 3D data. There is nothing lightweight for "I just want to see my ADC channel on a scrolling plot right now."

**Feature:** A built-in terminal UI (TUI) live inspector, launched with a single command. No Python script needed.

```bash
seam inspect --config seam.toml
```

Renders in the terminal using `ratatui` (Rust):
- Scrolling sparkline per channel, auto-scaled
- Channel list with live rate (actual Hz measured)
- Timestamps, min/max/current values
- Colour-coded by channel ID
- Press `r` to start/stop recording to `.seam`

```
┌─ seam inspector ─────────────────────────────────────────┐
│ accel [f32x3] @ 98.4 Hz                                  │
│ x ▁▂▃▅▆▇▇▆▄▂▁  y ▄▄▃▃▄▅▅▄▃▃▄  z ▇▇▇▇▇▇▇▇▇▇▇             │
│ x: +0.023g  y: -0.011g  z: +0.981g                      │
├──────────────────────────────────────────────────────────┤
│ temperature [f32] @ 9.9 Hz                               │
│ ▄▄▅▅▅▅▅▅▅▆▆                                              │
│ 24.3 °C  (min 23.9  max 24.7)                            │
├──────────────────────────────────────────────────────────┤
│ [r] record  [q] quit  [space] pause   USB-CDC connected  │
└──────────────────────────────────────────────────────────┘
```

**Why this matters:** The most common developer action is "is my sensor reading anything sensible?" Currently that requires writing Python. This removes that friction entirely.

---

## Phase 4 — Bidirectional Commands

**Gap identified:** Every existing tool treats the device as read-only. Nobody provides a clean general-purpose mechanism for the host to *send* commands back to firmware.

**Feature:** An optional command channel baked into the protocol. The host can send typed commands; the firmware registers handlers.

### In `seam.toml`:
```toml
[[command]]
id     = 0
name   = "set_rate"
args   = [{ name = "channel_id", type = "u8" }, { name = "rate_hz", type = "u16" }]

[[command]]
id     = 1
name   = "trigger_sample"
args   = []

[[command]]
id     = 2
name   = "set_gain"
args   = [{ name = "channel_id", type = "u8" }, { name = "gain", type = "f32" }]
```

### Firmware side:
```rust
sampler.on_command(Command::SetRate, |args| {
    let channel_id = args.u8();
    let rate_hz    = args.u16();
    set_channel_rate(channel_id, rate_hz);
});
```

### Python side:
```python
await dev.send("set_rate", channel_id=1, rate_hz=50)
await dev.send("trigger_sample")
```

**Why this matters:** Enables calibration workflows, dynamic configuration, triggered capture, gain adjustment — all from the same Python session that reads data. None of the existing tools provide this in a general-purpose, schema-driven way.

---

## Phase 5 — Seam Bridge (MCAP / Rerun export)

**Gap identified:** Seam targets a different user than Foxglove/Rerun, but some users will eventually want to bring their `.seam` recordings *into* those tools for deeper analysis or collaboration. Currently there is no bridge.

**Features:**

### Export `.seam` → MCAP
```bash
seam export --input session.seam --format mcap --output session.mcap
```

Opens the recording in Foxglove with zero additional work.

### Live forward to Rerun
```python
from seam import Device
from seam.bridge import RerunBridge

device = Device.from_config("seam.toml")
bridge = RerunBridge(device, app_name="my-sensor")

async with device.connect() as dev:
    await bridge.run(dev)  # forwards all channels to Rerun viewer in real time
```

### Export `.seam` → CSV / pandas DataFrame
```python
from seam import Recording
import pandas as pd

rec = Recording.open("session.seam")
df = rec.to_dataframe("accel")   # columns: timestamp_ms, x, y, z
```

**Why this matters:** Seam users don't get locked in. They can graduate to heavier tooling when they need it, and their data travels with them. This also makes Seam attractive to researchers who need reproducible, portable recordings.

---

## Phase 6 — Multi-device

**Gap identified:** No tool in the embedded/non-ROS space makes it easy to stream from *multiple devices simultaneously* and time-synchronise their data.

**Feature:** `MultiDevice` — stream from N devices in a single async context, with software timestamp alignment.

```python
from seam import MultiDevice

devices = MultiDevice.from_configs([
    "node_a/seam.toml",
    "node_b/seam.toml",
])

async with devices.connect() as fleet:
    async for sample in fleet.stream_all():
        # sample.device identifies which node it came from
        print(sample.device, sample.channel, sample.values)
```

**Use cases:** Distributed vibration sensing, multi-point temperature logging, synchronised IMU arrays.

---

## Phase 7 — Zephyr / nRF Connect SDK module

**Gap identified:** Embassy is the right choice for pure Rust firmware, but many nRF developers are already in the Zephyr / nRF Connect SDK ecosystem. Seam being Embassy-only locks out a large audience.

**Feature:** `seam-zephyr` — a Zephyr module that exposes the same `Sampler` API and reads the same `seam.toml` at build time, using Kconfig/CMake instead of Embassy.

```cmake
# CMakeLists.txt
list(APPEND ZEPHYR_EXTRA_MODULES path/to/seam-zephyr)
```

```c
// main.c — same mental model, C API
SEAM_CHANNEL_SEND(CHANNEL_ACCEL, (float[]){x, y, z});
```

The Python SDK is transport-agnostic, so it works unchanged regardless of whether the firmware uses Embassy or Zephyr.

---

## Full Feature Roadmap

| Phase | Feature | Value |
|---|---|---|
| **1** | Core: TOML config, Embassy fw crate, Python SDK, USB+BLE | Zero-boilerplate live streaming |
| **2** | `seam record`, `.seam` file format, replay API | Offline development, no cloud needed |
| **3** | `seam inspect` TUI | Instant visual feedback, no Python script |
| **4** | Bidirectional commands in `seam.toml` | Dynamic configuration from host |
| **5** | MCAP/Rerun/CSV export bridges | Interoperability, no lock-in |
| **6** | `MultiDevice` multi-node streaming | Distributed sensor networks |
| **7** | Zephyr / nRF Connect SDK module | Broader nRF ecosystem reach |

---

## Who Seam is for (refined)

After the market research, three user personas are clear:

**Persona 1 — The hardware prototype engineer**
Building a custom sensor board, wants to validate it quickly. Writes Rust firmware. Doesn't want to set up ROS or a cloud account to see if the accelerometer is reading correctly. Seam Phase 1+3 serves them.

**Persona 2 — The data collection researcher**
Needs repeatable, labelled sensor recordings for ML training or analysis. Currently cobbles together pyserial + custom CSV writers every project. Seam Phase 1+2+5 gives them a reusable, self-describing recording pipeline.

**Persona 3 — The maker / nRF ecosystem builder**
Building an nRF-based product (your original vision — the Unexpected Maker model for nRF). Wants an SDK that board buyers can drop into their project with one TOML file. Seam Phase 1+3+4 is the developer experience story.

---

## What Seam deliberately is not

- Not a cloud platform (no accounts, no telemetry sent anywhere)
- Not a robotics framework (no ROS, no transforms, no 3D scene graph)
- Not a general IoT platform (no MQTT broker, no device management)
- Not a dashboarding tool (no hosted web UI)

These are the things Rerun, Foxglove, and Edge Impulse do. Seam is the layer *below* them — the clean, config-driven pipe that gets data from the device into Python, in a format that can feed any of them.

---

## Risks & Mitigations

### 1. Codegen fragility

`seam.toml` → Rust enum via `seam-build` is elegant but is a common failure point. A malformed `seam.toml` produces a cryptic build error, not a runtime one.

**Mitigation:** `seam-build` must produce *excellent* error messages — point to the exact line, show what was expected, show what was found. Add a `seam validate` CLI command that parses `seam.toml` and prints all derived channel/command info without requiring `cargo build`.

### 2. Wire protocol versioning

Breaking the wire protocol makes every existing `.seam` file unreadable unless there's a migration layer.

**Mitigation:** Add a `wire_version` byte to the `.seam` file header. Maintain backward-compatible decoders for each wire version. Document a migration path for every protocol bump.

### 3. Type table is narrow

`f32x3`/`f32x6` cover IMUs well but miss 4-channel ADCs, GPIO state arrays, or other common sensor patterns.

**Mitigation:** Consider whether a generic `[type; N]` syntax in TOML (e.g. `type = "u16x4"`) is worth adding before Phase 1 ships. At minimum, add `u8x8` and `u16x4` to the type table.

### 4. BLE transport complexity

BLE NUS on nRF with Embassy is non-trivial — connection drops, MTU negotiation, bonding. The "it just works" story will be harder than USB CDC.

**Mitigation:** Make USB CDC the golden path for Phase 1. Treat BLE as "works but expect rough edges." Ship USB CDC first, stabilize it, then add BLE.

### 5. `seam-inspect` language choice

CLAUDE.md says the Rust inspector binary "connects via Python transport layer." This means either embedding a Python interpreter in the Rust binary or reimplementing the transport — both are significant overhead.

**Decision:** Implement `seam-inspect` as a **Python module** using `textual` (modern TUI framework) instead of Rust + ratatui. This shares the transport code directly, avoids FFI complexity, and keeps the codebase unified. The `seam inspect` CLI entry point remains the same.

---

## Implementation Notes

### Codec tests first

The wire protocol is the most critical piece. Before building any UI or CLI:

1. Round-trip encode/decode tests for every type in the type table
2. Edge cases: empty payload, max-length payload (255 bytes), COBS boundary conditions
3. Command encode tests for every argument type
4. Tests in both `seam-fw/src/codec.rs` (Rust) and `seam-py/seam/codec.py` (Python)

### `examples/accel-logger` as integration test

This example should build and run end-to-end. If it doesn't, nothing else matters. It serves as:
- The "10-minute quick start" demo
- A smoke test for the entire pipeline
- A template for new users

### `seam validate` CLI

New CLI command to add:

```bash
seam validate --config seam.toml
```

Parses `seam.toml`, runs all validation rules, and prints:
- All channels with their types, rates, and units
- All commands with their argument signatures
- Any warnings (duplicate names, suspicious rate values, etc.)
- Exit code 0 if valid, 1 if not

No hardware connection required. Catches config errors before `cargo build`.

---

## Updated Roadmap (with implementation order)

| Phase | Feature | Notes |
|---|---|---|
| **1** | Core: TOML config, Embassy fw crate, Python SDK, USB CDC | USB CDC first, BLE later in phase |
| **1a** | `seam validate` CLI | Catches config errors before build |
| **1b** | BLE NUS transport | After USB CDC is stable |
| **2** | `seam record`, `.seam` file format, replay API | Embed `wire_version` in header |
| **3** | `seam inspect` TUI (Python + textual) | Not Rust + ratatui — see decision above |
| **4** | Bidirectional commands in `seam.toml` | Type-safe dispatch on both sides |
| **5** | MCAP/Rerun/CSV export bridges | Optional deps, keep core lean |
| **6** | `MultiDevice` multi-node streaming | Software timestamp alignment |
| **7** | Zephyr / nRF Connect SDK module | Broader nRF ecosystem reach |
