# CLI Reference

Install: `pip install seam`

All subcommands default to reading `seam.toml` in the current directory. Override with `--config`.

---

## `seam validate`

Parse `seam.toml` and print the derived schema. No hardware connection required.

```bash
seam validate
seam validate --config path/to/seam.toml
```

Output on success:
```
Device:   my-board  (usb-cdc)

Channels:
  0  accel        f32x3   100 Hz   g
  1  temperature  f32      10 Hz   celsius

Commands:
  0  set_rate      args: channel_id:u8  rate_hz:u16
  1  trigger_capture  (no args)

seam.toml is valid.
```

Exit code `0` on success, `1` on validation error.

---

## `seam inspect`

Live terminal inspector. Connects to the device and shows per-channel sparklines and statistics.

```bash
seam inspect
seam inspect --config path/to/seam.toml

# Replay a recording instead of connecting to hardware
seam inspect --replay session.seam
```

Key bindings:
- `space` — pause / resume
- `r` — start/stop recording to a timestamped `.seam` file
- `q` — quit

```
┌─ seam inspector — my-board ───────────────────────────────────┐
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

## `seam record`

Connect to the device and write all frames to a `.seam` file.

```bash
seam record --output session.seam
seam record --config path/to/seam.toml --output session.seam

# Stop automatically after a duration
seam record --output calibration.seam --duration 60s
seam record --output burst.seam --duration 500ms
```

Press `Ctrl-C` to stop early. The file is finalised on exit — partial recordings are valid and readable.

The `.seam` file embeds the full schema from `seam.toml` in its header. You don't need the original config to replay it later.

---

## `seam export`

Convert a `.seam` recording to another format.

### MCAP (Foxglove-compatible)

```bash
pip install seam[mcap]
seam export --input session.seam --format mcap --output session.mcap
```

Open the result in [Foxglove Studio](https://foxglove.dev) — all channels appear as typed topics on a shared timeline.

### CSV

```bash
seam export --input session.seam --format csv --channel accel --output accel.csv
```

Writes one row per sample. Column names are `timestamp_ms` plus one column per value component (`x,y,z` for `f32x3`; the channel name for scalar types).

Export all channels to a directory:

```bash
seam export --input session.seam --format csv --output ./data/
# writes: ./data/accel.csv, ./data/temperature.csv, ...
```

### Format summary

| `--format` | Extra install | Output |
|---|---|---|
| `mcap` | `seam[mcap]` | Single `.mcap` file |
| `csv` | _(none)_ | One `.csv` per channel |
