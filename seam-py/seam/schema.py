import re
import tomllib
from pathlib import Path

from seam.exceptions import ConfigError

VALID_TYPES = {"u8", "u16", "u32", "i16", "i32", "f32", "f32x3", "f32x6"}
VALID_TRANSPORTS = {"usb-cdc", "ble-nus"}
_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def load_schema(path: str | Path) -> dict:
    """Parse and validate a seam.toml file.

    Returns a schema dict with keys: device, channels, commands.
    Raises ConfigError on any validation failure.
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")

    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {p}: {e}")

    _validate_device(data)
    channels = _validate_channels(data)
    commands = _validate_commands(data)

    return {
        "device": data["device"],
        "channels": channels,
        "commands": commands,
    }


def _validate_device(data: dict) -> None:
    if "device" not in data:
        raise ConfigError("Missing [device] section")
    dev = data["device"]
    if "name" not in dev:
        raise ConfigError("Missing device.name")
    if "transport" not in dev:
        raise ConfigError("Missing device.transport")
    if dev["transport"] not in VALID_TRANSPORTS:
        raise ConfigError(
            f"Invalid transport '{dev['transport']}'. Must be one of {VALID_TRANSPORTS}"
        )


def _validate_channels(data: dict) -> list[dict]:
    raw = data.get("channel", [])
    if not isinstance(raw, list):
        raise ConfigError("[[channel]] must be a list")

    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    channels = []

    for ch in raw:
        _validate_channel_entry(ch, seen_ids, seen_names)
        channels.append(ch)

    return channels


def _validate_channel_entry(ch: dict, seen_ids: set, seen_names: set) -> None:
    if "id" not in ch:
        raise ConfigError("Channel missing 'id'")
    if "name" not in ch:
        raise ConfigError("Channel missing 'name'")
    if "type" not in ch:
        raise ConfigError(f"Channel '{ch['name']}' missing 'type'")
    if "rate_hz" not in ch:
        raise ConfigError(f"Channel '{ch['name']}' missing 'rate_hz'")

    if not isinstance(ch["id"], int) or not (0 <= ch["id"] <= 255):
        raise ConfigError(f"Channel id must be u8, got {ch['id']}")
    if ch["id"] in seen_ids:
        raise ConfigError(f"Duplicate channel id: {ch['id']}")
    seen_ids.add(ch["id"])

    name = ch["name"]
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ConfigError(
            f"Channel name must be lowercase ASCII with underscores, got '{name}'"
        )
    if name in seen_names:
        raise ConfigError(f"Duplicate channel name: {name}")
    seen_names.add(name)

    if ch["type"] not in VALID_TYPES:
        raise ConfigError(
            f"Channel '{name}' has invalid type '{ch['type']}'. Must be one of {VALID_TYPES}"
        )
    if not isinstance(ch["rate_hz"], int) or ch["rate_hz"] <= 0:
        raise ConfigError(f"Channel '{name}' rate_hz must be a positive integer")


def _validate_commands(data: dict) -> list[dict]:
    raw = data.get("command", [])
    if not isinstance(raw, list):
        raise ConfigError("[[command]] must be a list")

    seen_ids: set[int] = set()
    seen_names: set[str] = set()
    commands = []

    for cmd in raw:
        _validate_command_entry(cmd, seen_ids, seen_names)
        commands.append(cmd)

    return commands


def _validate_command_entry(cmd: dict, seen_ids: set, seen_names: set) -> None:
    if "id" not in cmd:
        raise ConfigError("Command missing 'id'")
    if "name" not in cmd:
        raise ConfigError("Command missing 'name'")

    if not isinstance(cmd["id"], int) or not (0 <= cmd["id"] <= 255):
        raise ConfigError(f"Command id must be u8, got {cmd['id']}")
    if cmd["id"] in seen_ids:
        raise ConfigError(f"Duplicate command id: {cmd['id']}")
    seen_ids.add(cmd["id"])

    name = cmd["name"]
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ConfigError(
            f"Command name must be lowercase ASCII with underscores, got '{name}'"
        )
    if name in seen_names:
        raise ConfigError(f"Duplicate command name: {name}")
    seen_names.add(name)

    args = cmd.get("args", [])
    if not isinstance(args, list):
        raise ConfigError(f"Command '{name}' args must be a list")
    for arg in args:
        if "name" not in arg:
            raise ConfigError(f"Command '{name}' arg missing 'name'")
        if "type" not in arg:
            raise ConfigError(f"Command '{name}' arg '{arg['name']}' missing 'type'")
        if arg["type"] not in VALID_TYPES:
            raise ConfigError(
                f"Command '{name}' arg '{arg['name']}' has invalid type '{arg['type']}'"
            )
