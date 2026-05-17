# Export Bridges

Seam can export `.seam` recordings to several external formats. Bridges are optional — install only what you need.

---

## MCAP (Foxglove-compatible)

MCAP is a structured binary format supported by [Foxglove Studio](https://foxglove.dev).

```bash
pip install seam[mcap]
```

### Via CLI

```bash
seam export --input session.seam --format mcap --output session.mcap
```

### From Python

```python
from seam.bridge.mcap import export_mcap

export_mcap("session.seam", "session.mcap")
```

Open the `.mcap` in Foxglove — all channels appear as typed topics on a shared timeline with units preserved.

---

## Rerun (live bridge)

[Rerun](https://rerun.io) is a real-time data visualisation platform.

```bash
pip install seam[rerun]
```

### Live forwarding

```python
from seam import Device
from seam.bridge.rerun import RerunBridge

device = Device.from_config("seam.toml")
async with device.connect() as dev:
    await RerunBridge(app_name="my-sensor").run(dev)
```

This launches a Rerun viewer and streams all channels in real time. Each channel is logged as a separate Rerun entity.

### Replay to Rerun

```python
from seam import Recording
from seam.bridge.rerun import RerunBridge

rec = await Recording.open("session.seam")
async with rec.as_device() as dev:
    await RerunBridge(app_name="replay").run(dev)
```

---

## CSV / pandas

No extra install for CSV. `pandas` is optional.

### Via CLI

```bash
# Single channel
seam export --input session.seam --format csv --channel accel --output accel.csv

# All channels to a directory
seam export --input session.seam --format csv --output ./data/
# writes: ./data/accel.csv, ./data/temperature.csv, ...
```

### DataFrame via Python

```bash
pip install seam[pandas]
```

```python
from seam import Recording

rec = await Recording.open("session.seam")

# Single channel
df = rec.to_dataframe("accel")
# columns for f32x3: timestamp_ms, x, y, z
# columns for scalar: timestamp_ms, <channel_name>

print(df.head())
print(df["x"].mean())

# All channels
dfs = rec.to_dataframes()
for name, df in dfs.items():
    print(name, df.shape)
```

### CSV column layout

| Channel type | Columns |
|---|---|
| scalar (`f32`, `u8`, etc.) | `timestamp_ms`, `<channel_name>` |
| `f32x3` | `timestamp_ms`, `x`, `y`, `z` |
| `f32x6` | `timestamp_ms`, `ax`, `ay`, `az`, `gx`, `gy`, `gz` |
