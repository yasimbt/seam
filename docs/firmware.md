# Firmware SDK

Seam's firmware side is split into two crates:

- **`seam-build`** — a build-time std crate that reads `seam.toml` and generates Rust code.
- **`seam-fw`** — a no_std runtime crate that provides `Sampler`, the `Transport` trait, and codec logic.

---

## Setup

### `Cargo.toml`

```toml
[dependencies]
seam-fw = { version = "0.1", features = ["usb-cdc"] }
# or "ble-nus" or both

[build-dependencies]
seam-build = "0.1"
```

### `build.rs`

```rust
fn main() {
    seam_build::generate("seam.toml");
}
```

This reads `seam.toml`, validates it, and writes `$OUT_DIR/seam_generated.rs` containing:

- `Channel` enum — one variant per `[[channel]]` entry
- `Command` enum — one variant per `[[command]]` entry
- `ChannelInfo` impl — maps each variant to its name, id, rate, and unit
- `Command::from_bytes(id, args)` — decodes a raw command frame into a typed enum variant

Generated code is never written into the source tree. If `seam.toml` is invalid, the build fails with a clear error.

### `src/main.rs`

```rust
#![no_std]
#![no_main]

use embassy_executor::Spawner;
use seam_fw::{Sampler, transport::UsbCdc};

// Pull in the generated Channel + Command enums
include!(concat!(env!("OUT_DIR"), "/seam_generated.rs"));

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = embassy_nrf::init(Default::default());
    let mut sampler = Sampler::new(UsbCdc::new(p.USBD));
    sampler.transport.init().await.unwrap();

    loop {
        let [ax, ay, az] = read_accel();
        sampler.send(Channel::Accel, [ax, ay, az]).await;

        let temp = read_temperature();
        sampler.send(Channel::Temperature, temp).await;

        embassy_time::Timer::after_millis(10).await;
    }
}
```

---

## `Sampler`

```rust
pub struct Sampler<T: Transport> { /* ... */ }
```

### `Sampler::new(transport)`

```rust
let mut sampler = Sampler::new(UsbCdc::new(p.USBD));
```

### `sampler.send(channel, value).await`

```rust
sampler.send(Channel::Accel, [ax, ay, az]).await;
sampler.send(Channel::Temperature, temp).await;
```

Encodes the value into a TLV data frame, COBS-encodes it, and writes it to the transport. The channel type is checked at compile time — passing the wrong value type is a compile error.

### `sampler.on_command(handler)`

```rust
sampler.on_command(|transport, cmd| {
    match cmd {
        Command::SetRate { channel_id, rate_hz } => {
            update_rate(channel_id, rate_hz);
            // respond with ACK (optional — sampler ACKs automatically)
        }
        Command::TriggerCapture => {
            trigger();
        }
    }
});
```

Registers a handler called whenever a command frame is received from the host. The `Command` enum is generated from `seam.toml`. See [commands.md](commands.md) for full details.

### `sampler.run().await`

```rust
// In a separate Embassy task
#[embassy_executor::task]
async fn rx_task(mut sampler: Sampler<UsbCdc>) {
    sampler.run().await;
}
```

Starts the receive/dispatch loop. Reads frames from the transport, decodes them, dispatches command handlers. Does not return. Run this from a dedicated task if you need concurrent send and receive.

### `sampler.send_ack(command_id, seq).await` / `sampler.send_nack(...).await`

Manual ACK/NACK — use these inside a command handler if you want to defer the response:

```rust
sampler.on_command(|transport, cmd| {
    match cmd {
        Command::Calibrate => {
            if start_calibration().is_ok() {
                sampler.send_ack(cmd.id(), cmd.seq()).await;
            } else {
                sampler.send_nack(cmd.id(), cmd.seq()).await;
            }
        }
    }
});
```

---

## Transport feature flags

Select the transport at compile time via Cargo features:

```toml
# USB CDC-ACM — development, wired, low latency
seam-fw = { version = "0.1", features = ["usb-cdc"] }

# BLE Nordic UART Service — wireless
seam-fw = { version = "0.1", features = ["ble-nus"] }

# Both simultaneously
seam-fw = { version = "0.1", features = ["usb-cdc", "ble-nus"] }
```

### `UsbCdc`

```rust
use seam_fw::transport::UsbCdc;

let transport = UsbCdc::new(class);    // pass an embassy-usb CdcAcmClass
```

### `BleNus`

```rust
use seam_fw::transport::BleNus;

let mut transport = BleNus::new();
transport.set_connected(true);         // call from your BLE connection callback
transport.feed_bytes(&rx_data);        // call from your NUS RX notification handler
```

---

## `no_std` rules

`seam-fw` is strictly `no_std`. No `std`, no `alloc` unless an explicit Cargo feature enables it. All allocation-free. If you see a compile error about `std` or `alloc`, check that you haven't accidentally enabled a dependency that brings them in.

---

## Codegen details

`seam-build` generates code like this for a two-channel, one-command schema:

```rust
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Channel {
    Accel,
    Temperature,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Command {
    SetRate { channel_id: u8, rate_hz: u16 },
}

impl Command {
    pub fn from_bytes(id: u8, args: &[u8]) -> Option<Self> {
        match id {
            0 => Some(Command::SetRate {
                channel_id: args[0],
                rate_hz: u16::from_le_bytes([args[1], args[2]]),
            }),
            _ => None,
        }
    }
}
```

The generated file is always formatted with `rustfmt` before writing. Never commit it — it's in `$OUT_DIR` and reproduced every build.
