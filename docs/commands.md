# Bidirectional Commands

Seam supports host-to-device commands alongside data channels. Commands are defined in `seam.toml`, codegen'd into a typed `Command` enum on the firmware side, and sent by name from Python.

---

## Define commands in seam.toml

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
# no args

[[command]]
id   = 2
name = "set_led"
args = [
  { name = "r", type = "u8" },
  { name = "g", type = "u8" },
  { name = "b", type = "u8" },
]
```

Command IDs are independent from channel IDs — command 0 and channel 0 can coexist. Never renumber IDs.

---

## Python side

### Sending a command

```python
# Named arguments must match the args defined in seam.toml
await dev.send("set_rate", channel_id=1, rate_hz=50)
await dev.send("trigger_capture")
await dev.send("set_led", r=255, g=0, b=128)
```

`send()` encodes the arguments, transmits the frame, and waits for an ACK from the device. It returns `None` on success.

### Errors

| Exception | When |
|---|---|
| `UnknownCommandError` | Command name not in schema |
| `CommandNackError` | Device responded with NACK |

```python
try:
    await dev.send("set_rate", channel_id=99, rate_hz=999)
except CommandNackError:
    print("Device rejected the command")
```

---

## Firmware side

`seam-build` generates a `Command` enum from your `seam.toml`:

```rust
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Command {
    SetRate { channel_id: u8, rate_hz: u16 },
    TriggerCapture,
    SetLed { r: u8, g: u8, b: u8 },
}
```

### Registering a handler

```rust
sampler.on_command(|transport, cmd| {
    match cmd {
        Command::SetRate { channel_id, rate_hz } => {
            if set_channel_rate(channel_id, rate_hz).is_ok() {
                // ACK is sent automatically when the handler returns normally
            }
        }
        Command::TriggerCapture => {
            trigger_one_shot();
        }
        Command::SetLed { r, g, b } => {
            set_rgb_led(r, g, b);
        }
    }
});
```

The sampler sends an ACK automatically when the handler returns. To send a NACK (e.g. invalid argument):

```rust
sampler.on_command(|transport, cmd| {
    match cmd {
        Command::SetRate { channel_id, rate_hz } => {
            if channel_id < NUM_CHANNELS && rate_hz <= MAX_RATE {
                set_channel_rate(channel_id, rate_hz);
                // implicit ACK
            } else {
                sampler.send_nack(cmd.id(), cmd.seq()).await;
                return;
            }
        }
    }
});
```

### Starting the receive loop

Commands are received and dispatched by `sampler.run()`. Run it from a dedicated Embassy task:

```rust
#[embassy_executor::task]
async fn rx_task(mut sampler: Sampler<UsbCdc<'static, Driver<'static>>>) {
    sampler.run().await;
}
```

---

## Command wire frame

Command frames sent host→device:

```
type(1=0x10) | command_id(1) | seq(1) | length(1) | args(0-255 LE)
```

- `seq` is a rolling u8 counter maintained by the Python SDK; the device echoes it in ACK/NACK for response matching.
- Arguments are packed little-endian in the order they appear in `seam.toml`.

ACK / NACK frames sent device→host:

```
type(1=0x02 or 0x03) | command_id(1) | seq(1) | length(1=0x00)
```

See [wire-protocol.md](wire-protocol.md) for the full frame layout.
