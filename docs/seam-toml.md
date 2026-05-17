# seam.toml Reference

`seam.toml` is the single source of truth for your Seam project. Both the Rust firmware crate (via `seam-build` codegen) and the Python host SDK read it. Channels and commands are defined once and never duplicated.

---

## `[device]`

```toml
[device]
name      = "my-board"
transport = "usb-cdc"
```

| Key | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Device name. Used as the BLE advertising name and the inspector window title. |
| `transport` | string | yes | `"usb-cdc"` for USB CDC-ACM or `"ble-nus"` for BLE Nordic UART Service. |

---

## `[[channel]]`

One block per data channel. Repeat for each sensor output.

```toml
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

| Key | Type | Required | Description |
|---|---|---|---|
| `id` | integer (u8) | yes | Wire identifier. Unique within `[[channel]]` blocks. **Never renumber** — existing `.seam` recordings will decode incorrectly if IDs change. |
| `name` | string | yes | Channel name. Used in `dev.stream("name")` and generated as `Channel::Name` in Rust. Must be lowercase ASCII with underscores, no leading digits. |
| `type` | string | yes | Payload type — see the type table below. |
| `rate_hz` | integer | yes | Nominal sample rate in Hz. Advisory — used by the SDK for buffer sizing, not enforced by firmware. |
| `unit` | string | no | Physical unit string e.g. `"g"`, `"hPa"`, `"celsius"`, `"rpm"`. Appears in `sample.unit`. |

---

## `[[command]]`

Optional. One block per host-to-device command.

```toml
[[command]]
id   = 0
name = "set_rate"
args = [
  { name = "channel_id", type = "u8"  },
  { name = "rate_hz",    type = "u16" },
]

[[command]]
id   = 1
name = "trigger_capture"
# no args — omit the args key entirely
```

| Key | Type | Required | Description |
|---|---|---|---|
| `id` | integer (u8) | yes | Wire identifier. Unique within `[[command]]` blocks. Independent namespace from channel IDs. Never renumber. |
| `name` | string | yes | Command name. Used as `await dev.send("name", ...)` in Python and as `Command::Name` in Rust. Same naming rules as channels. |
| `args` | array | no | Zero or more `{ name = "x", type = "u8" }` entries. Omit the key entirely for zero-arg commands. |

---

## Data types

| TOML type | Bytes | Rust type | Python `sample.values` |
|---|---|---|---|
| `u8` | 1 | `u8` | `(int,)` |
| `u16` | 2 | `u16` | `(int,)` |
| `u32` | 4 | `u32` | `(int,)` |
| `i16` | 2 | `i16` | `(int,)` |
| `i32` | 4 | `i32` | `(int,)` |
| `f32` | 4 | `f32` | `(float,)` |
| `f32x3` | 12 | `[f32; 3]` | `(float, float, float)` — also exposes `.x` `.y` `.z` |
| `f32x6` | 24 | `[f32; 6]` | `(float,) × 6` — also exposes `.ax` `.ay` `.az` `.gx` `.gy` `.gz` |

All multi-byte values are little-endian on the wire.

---

## Validation rules

These are enforced at build time (`seam-build`) and at runtime (Python `schema.py`):

- Channel `id` values must be unique within `[[channel]]` blocks.
- Command `id` values must be unique within `[[command]]` blocks.
- Channel and command `id` namespaces are independent (channel 0 and command 0 can coexist).
- All `name` values: lowercase ASCII, underscores allowed, no leading digits, valid as a Python identifier and Rust enum variant.
- `type` must be exactly one of the eight strings in the type table.
- `transport` must be `"usb-cdc"` or `"ble-nus"`.

---

## Full example

```toml
[device]
name      = "imu-logger"
transport = "usb-cdc"

[[channel]]
id      = 0
name    = "accel"
type    = "f32x3"
rate_hz = 200
unit    = "g"

[[channel]]
id      = 1
name    = "gyro"
type    = "f32x3"
rate_hz = 200
unit    = "dps"

[[channel]]
id      = 2
name    = "temperature"
type    = "f32"
rate_hz = 1
unit    = "celsius"

[[channel]]
id      = 3
name    = "pressure"
type    = "f32"
rate_hz = 10
unit    = "hPa"

[[command]]
id   = 0
name = "set_accel_range"
args = [{ name = "range_g", type = "u8" }]

[[command]]
id   = 1
name = "calibrate"

[[command]]
id   = 2
name = "set_sample_rate"
args = [
  { name = "channel_id", type = "u8"  },
  { name = "rate_hz",    type = "u16" },
]
```
