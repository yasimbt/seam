"""Seam terminal inspector — live sensor data viewer using Textual."""

from __future__ import annotations

import asyncio
import time
from collections import deque

import click
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.widgets import Footer, Header, Static


# ── Sparkline ────────────────────────────────────────────────────────────────

_SPARK = " ▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 50) -> str:
    if not values:
        return " " * width
    tail = values[-width:]
    mn = min(tail)
    mx = max(tail)
    span = mx - mn or 1.0
    n = len(_SPARK) - 1
    chars = [_SPARK[max(0, min(n, int((v - mn) / span * n)))] for v in tail]
    return "".join(chars).ljust(width)


# ── Per-channel card ─────────────────────────────────────────────────────────


class ChannelCard(Static):
    """Displays sparkline + live stats for one channel."""

    DEFAULT_CSS = """
    ChannelCard {
        border: round $primary-lighten-2;
        padding: 0 1;
        margin: 0 0 1 0;
        height: 5;
    }
    """

    def __init__(self, ch: dict, **kwargs):
        super().__init__(**kwargs)
        self._ch = ch
        self._buf: deque[float] = deque(maxlen=300)
        self._hz = 0.0
        self._last_t = 0.0
        self._render_card()

    def push(self, values: tuple) -> None:
        """Update with a new sample. Safe to call from async streaming code."""
        now = time.monotonic()
        self._buf.append(float(values[0]) if values else 0.0)
        if self._last_t > 0:
            alpha = 0.05
            self._hz = alpha / (now - self._last_t) + (1.0 - alpha) * self._hz
        self._last_t = now
        self._render_card()

    def _render_card(self) -> None:
        ch = self._ch
        unit = f" [{ch['unit']}]" if ch.get("unit") else ""
        vals = list(self._buf)

        header = f"[bold]{ch['name']}[/bold]  [dim]{ch['type']}{unit}  {ch['rate_hz']}Hz nominal[/dim]"
        if vals:
            spark = f"[green]{_sparkline(vals)}[/green]"
            cur, mn, mx = vals[-1], min(vals), max(vals)
            stats = (
                f"[dim]cur:[/dim] {cur:+.4f}  "
                f"[dim]min:[/dim] {mn:.4f}  "
                f"[dim]max:[/dim] {mx:.4f}  "
                f"[dim]rate:[/dim] {self._hz:.1f} Hz"
            )
        else:
            spark = "[dim]waiting for data...[/dim]"
            stats = "[dim]—[/dim]"

        self.update(f"{header}\n{spark}\n{stats}")


# ── App ──────────────────────────────────────────────────────────────────────


class SeamInspector(App):
    """Live Seam sensor inspector."""

    CSS = """
    Screen { background: $surface; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_pause", "Pause / Resume"),
    ]

    def __init__(self, schema: dict, source, **kwargs):
        super().__init__(**kwargs)
        self._schema = schema
        self._source = source
        self._cards: dict[str, ChannelCard] = {}
        self._paused = False
        self._stream_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        dev = self._schema["device"]
        self.title = f"seam inspect — {dev['name']}"
        self.sub_title = dev["transport"]
        yield Header(show_clock=True)
        with ScrollableContainer():
            for ch in self._schema["channels"]:
                card = ChannelCard(ch, id=f"card-{ch['name']}")
                self._cards[ch["name"]] = card
                yield card
        yield Footer()

    async def on_mount(self) -> None:
        self._stream_task = asyncio.ensure_future(self._stream_loop())

    async def _stream_loop(self) -> None:
        try:
            async for sample in self._source.stream_all():
                if not self._paused:
                    card = self._cards.get(sample.channel)
                    if card is not None:
                        card.push(sample.values)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.exit(message=f"Stream error: {exc}")
        else:
            # Generator exhausted (replay complete)
            self.sub_title = "replay complete — press q to quit"

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.sub_title = "PAUSED — space to resume"
        else:
            self.sub_title = self._schema["device"]["transport"]

    async def on_unmount(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass


# ── Public entry point ────────────────────────────────────────────────────────


def run_inspector(config: str | None = None, replay: str | None = None) -> None:
    """Launch the Seam inspector. Called by seam-py's CLI."""
    asyncio.run(_async_run(config, replay))


async def _async_run(config: str | None, replay: str | None) -> None:
    if replay:
        from seam.recording import Recording

        rec = await Recording.open(replay)
        schema = rec._schema
        if schema is None:
            raise SystemExit("Recording has no embedded schema.")
        app = SeamInspector(schema=schema, source=rec)
        await app.run_async()

    elif config:
        from seam.device import Device

        device = Device.from_config(config)
        async with device.session() as conn:
            app = SeamInspector(schema=conn._schema, source=conn)
            await app.run_async()

    else:
        raise SystemExit("Either --config or --replay must be provided.")


# ── Standalone CLI ────────────────────────────────────────────────────────────


@click.command()
@click.option("--config", "-c", required=False, help="Path to seam.toml (live mode)")
@click.option("--replay", "-r", required=False, help="Path to .seam file (replay mode)")
def main(config: str | None, replay: str | None) -> None:
    """Live terminal inspector for Seam sensor streams."""
    if not config and not replay:
        raise click.UsageError("Either --config or --replay is required.")
    run_inspector(config=config, replay=replay)


if __name__ == "__main__":
    main()
