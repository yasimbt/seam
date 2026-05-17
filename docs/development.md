# Development

## Environment setup

The repo ships a [devenv](https://devenv.sh) environment providing `gcc`, `pkg-config`, and Python. [direnv](https://direnv.net) activates it automatically when you `cd` into the repo.

```bash
# One-time: install devenv and direnv (NixOS / nixpkgs)
nix profile install nixpkgs#devenv nixpkgs#direnv

# One-time: allow direnv in this repo
direnv allow

# The environment activates automatically on every subsequent cd
```

Rust is managed separately via [rustup](https://rustup.rs):

```bash
rustup toolchain install stable
rustup target add thumbv7em-none-eabihf   # ARM firmware cross-compilation
```

Alternative: use the legacy nix-shell wrapper:

```bash
nix-shell shell.nix
```

---

## Running tests

### Rust

```bash
export PATH="$HOME/.cargo/bin:$PATH"

# seam-build codegen — 13 tests
cargo test -p seam-build

# seam-fw firmware (host target, no hardware) — 25 tests
cargo test -p seam-fw

# Both at once
cargo test -p seam-build -p seam-fw

# Clippy — zero warnings enforced
cargo clippy --all --all-features -- -D warnings
```

### Firmware cross-compile verification (no hardware needed)

```bash
cargo build -p seam-fw --target thumbv7em-none-eabihf --features usb-cdc
cargo build -p seam-fw --target thumbv7em-none-eabihf --features ble-nus
```

### Python

The system Python on NixOS is immutable. Use a venv:

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -e seam-py/
pip install -e seam-inspect/

# Unit tests — no hardware required (73 tests)
cd seam-py
pytest -m "not hardware"

# All tests including hardware (device must be connected)
pytest
```

### End-to-end smoke test

```bash
python examples/accel-logger/plot.py examples/accel-logger/fixture.seam
# Expected: "Loaded 200 accel samples, 20 temperature samples"
```

---

## Project structure

```
seam/
├── seam-fw/          — no_std Embassy firmware crate
│   ├── src/codec.rs  — COBS+TLV encoder/decoder (all 8 types)
│   ├── src/lib.rs    — Sampler public API
│   └── src/transport/
│       ├── usb_cdc.rs
│       └── ble_nus.rs
├── seam-build/       — build-time codegen (std, runs on host)
│   ├── src/schema.rs — TOML → DeviceSchema, ChannelDef, CommandDef
│   └── src/codegen.rs
├── seam-py/          — Python host SDK + CLI
│   ├── seam/codec.py — must stay in sync with seam-fw/src/codec.rs
│   └── tests/
├── seam-inspect/     — Textual TUI inspector
├── seam-zephyr/      — C/CMake Zephyr module
└── examples/
    ├── accel-logger/ — complete Embassy/nRF example + plot.py
    └── multi-node/   — MultiDevice example
```

---

## Adding a new data type

All five steps are required:

1. Add to `VALID_TYPES` in `seam-build/src/schema.rs`
2. Add Rust mapping in `seam-build/src/codegen.rs` → `rust_type_for()`
3. Add byte size in `seam-fw/src/codec.rs` → `payload_size_for()`
4. Add struct format in `seam-py/seam/codec.py` → `STRUCT_FMT`
5. Add round-trip test in both `codec.rs` and `codec.py`
6. Update the type table in `CLAUDE.md`, `README.md` (if shown), and `docs/seam-toml.md`

## Adding a new transport

**Firmware (`seam-fw/src/transport/`):**
1. Create `your_transport.rs` implementing the `Transport` trait
2. Gate with `#[cfg(feature = "your-transport")]`
3. Re-export from `transport/mod.rs` under the same gate
4. Add the feature to `seam-fw/Cargo.toml`
5. Add the transport string to `VALID_TRANSPORTS` in `seam-build/src/schema.rs`

**Python (`seam-py/seam/transport/`):**
1. Create `your_transport.py` implementing `connect`, `disconnect`, `read_frame`, `write_frame`
2. Register in `device.py` → `_transport_for()`
3. Add to validation in `schema.py`

---

## PR checklist

- [ ] `cargo clippy --all-features -- -D warnings` — zero warnings
- [ ] `cargo test -p seam-build -p seam-fw` passes
- [ ] `pytest -m "not hardware"` passes
- [ ] Wire protocol tables in `CLAUDE.md` and `docs/wire-protocol.md` are current
- [ ] Wire version byte incremented + migration note written if protocol changed
- [ ] Type table updated in `CLAUDE.md` and `docs/seam-toml.md` if types changed
- [ ] `examples/accel-logger` still builds and `plot.py` still runs
- [ ] Docs updated if public API, CLI, or `seam.toml` schema changed
