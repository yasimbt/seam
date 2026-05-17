"""Export .seam recordings to CSV.

Optional: pip install seam[pandas] for DataFrame export.
"""

import csv

from seam.recording import Recording


async def export_csv(
    rec: Recording, output: str, channel: str | None = None
) -> None:
    """Export a Recording to CSV format.

    If channel is specified, only that channel is exported.
    Otherwise all channels are exported with a channel column.
    """
    schema = rec._schema
    if schema is None:
        raise ValueError("Recording has no schema")
    channels = list(rec._channels.values())
    if channel:
        ch_def = None
        for c in channels:
            if c["name"] == channel:
                ch_def = c
                break
        if ch_def is None:
            raise ValueError(f"Unknown channel: {channel}")
        channels = [ch_def]

    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        header = ["timestamp_ms", "channel", "channel_id"]
        for ch in channels:
            fmt_values = _num_values_for_type(ch["type"])
            for i in range(fmt_values):
                header.append(f"{ch['name']}_{i}")
        writer.writerow(header)

        if channel:
            async for sample in rec.stream(channel):
                row = [sample.timestamp_ms, sample.channel, sample.channel_id]
                row.extend(sample.values)
                writer.writerow(row)
        else:
            async for sample in rec.stream_all():
                row = [sample.timestamp_ms, sample.channel, sample.channel_id]
                row.extend(sample.values)
                writer.writerow(row)


def _num_values_for_type(typ: str) -> int:
    return {
        "u8": 1, "u16": 1, "u32": 1,
        "i16": 1, "i32": 1, "f32": 1,
        "f32x3": 3, "f32x6": 6,
    }[typ]
