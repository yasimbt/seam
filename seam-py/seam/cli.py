import asyncio
import sys

import click

from seam.exceptions import ConfigError
from seam.schema import load_schema


@click.group()
def cli():
    """Seam — sensor streaming SDK for nRF microcontrollers."""


@cli.command()
@click.option("--config", "-c", required=True, help="Path to seam.toml")
def validate(config: str):
    """Validate a seam.toml configuration file."""
    try:
        schema = load_schema(config)
    except ConfigError as e:
        click.echo(f"INVALID: {e}", err=True)
        sys.exit(1)

    click.echo("VALID")
    click.echo("")

    dev = schema["device"]
    click.echo(f"Device: {dev['name']}")
    click.echo(f"Transport: {dev['transport']}")
    click.echo("")

    channels = schema["channels"]
    if channels:
        click.echo(f"Channels ({len(channels)}):")
        for ch in channels:
            unit = f" [{ch['unit']}]" if ch.get("unit") else ""
            click.echo(
                f"  [{ch['id']}] {ch['name']}  type={ch['type']}  "
                f"rate={ch['rate_hz']}Hz{unit}"
            )
        click.echo("")

    commands = schema["commands"]
    if commands:
        click.echo(f"Commands ({len(commands)}):")
        for cmd in commands:
            args = cmd.get("args", [])
            if args:
                sig = ", ".join(f"{a['name']}: {a['type']}" for a in args)
                click.echo(f"  [{cmd['id']}] {cmd['name']}({sig})")
            else:
                click.echo(f"  [{cmd['id']}] {cmd['name']}()")
        click.echo("")

    sys.exit(0)


@cli.command()
@click.option("--config", "-c", required=True, help="Path to seam.toml")
@click.option("--output", "-o", required=True, help="Output .seam file path")
@click.option("--duration", "-d", type=float, help="Recording duration in seconds")
def record(config: str, output: str, duration: float | None):
    """Record sensor data from a device to a .seam file."""
    from seam.device import Device
    from seam.recording import Recording

    async def _run():
        dev = Device.from_config(config)
        async with dev.session() as conn:
            rec = Recording()
            rec._schema = conn._schema
            rec._channels = conn._channels

            click.echo(f"Recording to {output}...")
            if duration:
                click.echo(f"Duration: {duration}s")

            start = asyncio.get_event_loop().time()
            count = 0
            try:
                async for sample in conn.stream_all():
                    count += 1
                    ch = rec._channels[sample.channel_id]
                    import struct as _struct
                    from seam.codec import DATA, STRUCT_FMT
                    from seam.codec import cobs_encode

                    fmt = STRUCT_FMT[ch["type"]]
                    payload = _struct.pack(fmt, *sample.values)
                    raw = bytes([
                        DATA,
                        sample.channel_id,
                        *sample.timestamp_ms.to_bytes(4, "little"),
                        len(payload),
                    ]) + payload
                    rec.add_frame(raw)

                    if duration and (asyncio.get_event_loop().time() - start) >= duration:
                        break
            except KeyboardInterrupt:
                pass

            await rec.save(output)
            click.echo(f"Saved {count} samples to {output}")

    asyncio.run(_run())


@cli.command()
@click.option("--config", "-c", required=False, help="Path to seam.toml (live mode)")
@click.option("--replay", "-r", type=str, help="Replay from .seam file (offline mode)")
def inspect(config: str | None, replay: str | None):
    """Live terminal inspector for sensor data."""
    if not config and not replay:
        raise click.UsageError("Either --config or --replay is required.")
    try:
        from seam_inspect.__main__ import run_inspector
    except ImportError:
        click.echo(
            "seam-inspect is not installed.\n"
            "Install it with: pip install seam-inspect",
            err=True,
        )
        sys.exit(1)
    run_inspector(config=config, replay=replay)


@cli.command()
@click.option("--input", "-i", required=True, help="Input .seam file")
@click.option("--format", "-f", required=True, help="Output format: mcap, csv, rerun")
@click.option("--output", "-o", required=True, help="Output file path")
@click.option("--channel", help="Filter to specific channel name")
def export(input: str, format: str, output: str, channel: str | None):
    """Export a .seam recording to another format."""
    from seam.recording import Recording

    async def _run():
        rec = await Recording.open(input)

        if format == "csv":
            from seam.bridge.csv import export_csv
            await export_csv(rec, output, channel=channel)
        elif format == "mcap":
            from seam.bridge.mcap import export_mcap
            await export_mcap(rec, output, channel=channel)
        elif format == "rerun":
            from seam.bridge.rerun import RerunBridge
            bridge = RerunBridge()
            await bridge.export(rec, output, channel=channel)
        else:
            click.echo(f"Unknown format: {format}", err=True)
            sys.exit(1)

        click.echo(f"Exported to {output}")

    asyncio.run(_run())
