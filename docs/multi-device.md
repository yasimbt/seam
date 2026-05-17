# Multi-device

`MultiDevice` lets you connect to N devices simultaneously and receive samples tagged by device name. Each device has its own `seam.toml` and its own transport connection.

---

## Basic usage

```python
from seam import MultiDevice

fleet = MultiDevice.from_configs({
    "node_a": "node_a/seam.toml",
    "node_b": "node_b/seam.toml",
})

async with fleet.connect() as dev:
    async for sample in dev.stream_all():
        print(f"[{sample.device}] {sample.channel}  {sample.values}")
```

`sample.device` is the key string provided to `from_configs()`.

---

## Streaming a single channel across all devices

```python
async with fleet.connect() as dev:
    async for sample in dev.stream("accel"):
        # samples from node_a and node_b, interleaved
        print(sample.device, sample.timestamp_ms, sample.x, sample.y, sample.z)
```

---

## Sending commands to a specific device

```python
async with fleet.connect() as dev:
    await dev.send("node_a", "set_rate", channel_id=0, rate_hz=200)
    await dev.send("node_b", "trigger_capture")
```

---

## Clock alignment

Each device uses its own boot clock for `timestamp_ms`. Seam does not fuse clocks automatically.

If you need aligned timestamps:
- Record a shared hardware event (e.g. a GPIO trigger on both boards) as a channel sample and use that as a sync point in post-processing.
- Or synchronise the device clocks externally (e.g. PPS signal, BLE sync) before recording.

---

## Example: `examples/multi-node/`

The repo includes a complete multi-device example:

```
examples/multi-node/
├── node_a/seam.toml    — accel channel on node A
├── node_b/seam.toml    — pressure channel on node B
└── fuse.py             — connects both, prints interleaved samples
```

Run it:

```bash
cd examples/multi-node
python fuse.py
```
