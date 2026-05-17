# Seam — Build Progress

Last updated: 2026-05-18

---

## Done

### seam-py (Python SDK) — ✓ COMPLETE — 73 tests passing
- `seam/schema.py` — TOML parser, channel/command registry, all validation rules
- `seam/codec.py` — COBS decode, TLV frame parser, command encoder
- `seam/device.py` — `Device`, `ConnectedDevice`, transport factory (`_transport_for`)
- `seam/recording.py` — `.seam` file reader/writer; `Recording` API-symmetric with `ConnectedDevice`
- `seam/multi.py` — `MultiDevice` for N simultaneous devices
- `seam/__init__.py` — public re-exports, all exception classes (`SeamError`, `ConnectionError`, etc.)
- `seam/transport/serial.py` — USB CDC via pyserial-asyncio
- `seam/transport/ble.py` — BLE NUS via bleak
- `seam/bridge/mcap.py` — `.seam` → `.mcap` export bridge
- `seam/bridge/rerun.py` — live forward to Rerun viewer
- `seam/bridge/csv.py` — `.seam` → CSV / pandas DataFrame
- `seam/cli.py` — `seam validate`, `seam record`, `seam inspect`, `seam export`
- `tests/` — 73 tests, all passing

### seam-build (Rust codegen) — ✓ COMPLETE — 13 tests passing
- `src/schema.rs` — TOML → `DeviceSchema`, `ChannelDef`, `CommandDef`; all validation
- `src/codegen.rs` — generates `Channel` + `Command` enums; `ChannelInfo` impl; `Command::from_bytes` dispatch with typed arg decoding for all 8 types

### seam-fw (Rust no_std firmware) — ✓ COMPLETE — 25 tests passing, 0 clippy warnings
- `src/channel_info.rs` — `ChannelInfo` trait
- `src/codec.rs` — COBS+TLV encoder/decoder; all 8 types; `encode_data_frame`, `encode_cmd_ack/nack`, `decode_frame`, `decode_cmd_frame`
- `src/error.rs` — `SeamError` enum
- `src/transport/mod.rs` — `Transport` trait
- `src/transport/usb_cdc.rs` — USB CDC ACM with COBS framing (feature + `target_os = "none"` gated)
- `src/lib.rs` — `Sampler`: `send()`, `on_command()`, `run()` event loop, `send_ack/nack()`
- `build.rs` — calls `seam_build::generate()`

### seam-inspect (Python TUI) — ✓ COMPLETE
- `seam_inspect/__main__.py` — textual TUI; per-channel cards with sparklines + live stats; pause/resume; `run_inspector()` entry point
- `pyproject.toml`

### Infrastructure
- `shell.nix` — NixOS dev shell providing `gcc` for Rust linking (legacy fallback)
- `devenv.nix` — devenv environment: gcc, pkg-config, Python 3.12
- `devenv.yaml` — declares nixpkgs-unstable input
- `.envrc` — direnv entry point; auto-activates devenv on `cd` into the repo
- `.devenv-direnvrc` — local copy of devenv's direnv integration (regenerate with `devenv direnvrc > .devenv-direnvrc`)

### examples/accel-logger — ✓ COMPLETE
- `seam.toml`, `Cargo.toml`, `build.rs`, `src/main.rs` (no_std Embassy), `plot.py`

### examples/multi-node — ✓ COMPLETE
- `node_a/seam.toml`, `node_b/seam.toml`, `fuse.py` using `MultiDevice`

---

## To Do

### Verification
- [x] Verify `seam-inspect` installs and launches: `pip install -e seam-inspect/` — imports OK
- [x] Verify `examples/accel-logger` cross-compiles for ARM: both `usb-cdc` and `ble-nus` features build clean
- [x] Run `examples/accel-logger/plot.py` end-to-end: 200 accel + 20 temp samples from `fixture.seam` — OK

### Documentation
- [x] `README.md` — complete: quickstart, CLI reference, SDK docs, wire protocol, dev setup

### Future / Nice-to-have
- [x] `seam-fw/src/transport/ble_nus.rs` — BLE NUS stub implemented (COBS framing + feed_bytes API; TX wiring left to application)
- [x] `seam-zephyr` — C/CMake Zephyr module: CMakeLists.txt, Kconfig, zephyr/module.yml, codec.h/c (COBS+TLV), transport.h, sampler.h/c, usb_cdc.c, ble_nus.c
