# Wire Protocol

This document is for contributors and integrators building alternative host or firmware implementations. If you're only using the Python SDK and `seam-fw`, you don't need this — it's all handled automatically.

---

## COBS framing

All frames are [COBS](https://en.wikipedia.org/wiki/Consistent_Overhead_Byte_Stuffing)-encoded on the wire. `0x00` is the unambiguous frame delimiter and never appears inside an encoded frame.

- Standard COBS — no custom variant.
- After a device reset or a partial frame, the host re-syncs on the next `0x00` with no state to reset.
- Rust: `cobs` crate. Python: implemented directly in `codec.py`. C (Zephyr): `seam-zephyr/src/codec.c`.

The COBS sentinel byte (`0x00`) is appended after the encoded data. The sentinel is not included in any length field.

---

## Data frame (device → host)

After COBS decoding:

```
┌────────┬──────────┬────────────────┬──────────┬──────────────────────┐
│  type  │ channel  │  timestamp_ms  │  length  │       payload        │
│ 1 byte │  1 byte  │    4 bytes LE  │  1 byte  │    0–255 bytes LE    │
└────────┴──────────┴────────────────┴──────────┴──────────────────────┘
```

| Field | Value | Notes |
|---|---|---|
| `type` | `0x01` | Data frame type byte |
| `channel` | u8 | Matches `id` in `[[channel]]` blocks |
| `timestamp_ms` | u32 LE | Milliseconds since device boot |
| `length` | u8 | Byte count of payload only |
| `payload` | 0–255 bytes LE | Typed values per channel type |

---

## Command ACK / NACK (device → host)

```
┌────────┬────────────┬─────┬──────────┐
│  type  │ command_id │ seq │  length  │
│ 1 byte │   1 byte   │ 1 B │ 1 byte=0 │
└────────┴────────────┴─────┴──────────┘
```

| Field | ACK value | NACK value |
|---|---|---|
| `type` | `0x02` | `0x03` |
| `command_id` | echoed from command frame | echoed |
| `seq` | echoed from command frame | echoed |
| `length` | `0x00` | `0x00` |

---

## Command frame (host → device)

```
┌────────┬────────────┬─────┬──────────┬──────────────────────┐
│  type  │ command_id │ seq │  length  │        args          │
│ 1 byte │   1 byte   │ 1 B │  1 byte  │    0–255 bytes LE    │
└────────┴────────────┴─────┴──────────┴──────────────────────┘
```

| Field | Value | Notes |
|---|---|---|
| `type` | `0x10` | Host-to-device command type byte |
| `command_id` | u8 | Matches `id` in `[[command]]` blocks |
| `seq` | u8 | Rolling counter; echoed in ACK/NACK for response matching |
| `length` | u8 | Byte count of args only |
| `args` | 0–255 bytes LE | Typed arguments in order of definition |

---

## Payload encoding

All multi-byte values are **little-endian**.

| TOML type | Bytes | Encoding |
|---|---|---|
| `u8` | 1 | raw byte |
| `u16` | 2 | u16 LE |
| `u32` | 4 | u32 LE |
| `i16` | 2 | i16 LE two's complement |
| `i32` | 4 | i32 LE two's complement |
| `f32` | 4 | IEEE 754 single LE |
| `f32x3` | 12 | three consecutive `f32` LE values |
| `f32x6` | 24 | six consecutive `f32` LE values |

---

## Type byte summary

| Value | Direction | Meaning |
|---|---|---|
| `0x01` | device → host | Data frame |
| `0x02` | device → host | Command ACK |
| `0x03` | device → host | Command NACK |
| `0x10` | host → device | Command |

---

## Versioning

The wire protocol is versioned with a single `wire_version` byte embedded in `.seam` file headers (currently `0x01`). Any breaking change requires:

1. Incrementing the version byte in both `seam-fw/src/codec.rs` and `seam-py/seam/codec.py`
2. Writing a migration note in the changelog
3. Maintaining backward-compatible decoders for all previous versions in the Python SDK

The on-wire version is not transmitted during live sessions — it is only stored in recordings so decoders can select the correct parsing logic when replaying older files.
