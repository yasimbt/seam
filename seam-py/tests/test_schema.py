import pytest
import tempfile
from pathlib import Path

from seam.exceptions import ConfigError
from seam.schema import load_schema, VALID_TYPES, VALID_TRANSPORTS


VALID_TOML = """
[device]
name = "test-node"
transport = "usb-cdc"

[[channel]]
id = 0
name = "accel"
type = "f32x3"
rate_hz = 100
unit = "g"

[[channel]]
id = 1
name = "temp"
type = "f32"
rate_hz = 10
unit = "celsius"

[[command]]
id = 0
name = "set_gain"
args = [
    { name = "gain", type = "f32" }
]

[[command]]
id = 1
name = "reset"
"""


def _write_toml(content: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
        f.write(content)
        return f.name


class TestValidSchema:
    def test_load_valid(self):
        path = _write_toml(VALID_TOML)
        schema = load_schema(path)
        assert schema["device"]["name"] == "test-node"
        assert schema["device"]["transport"] == "usb-cdc"
        assert len(schema["channels"]) == 2
        assert len(schema["commands"]) == 2

    def test_channel_fields(self):
        path = _write_toml(VALID_TOML)
        schema = load_schema(path)
        accel = schema["channels"][0]
        assert accel["id"] == 0
        assert accel["name"] == "accel"
        assert accel["type"] == "f32x3"
        assert accel["rate_hz"] == 100
        assert accel["unit"] == "g"

    def test_command_with_args(self):
        path = _write_toml(VALID_TOML)
        schema = load_schema(path)
        cmd = schema["commands"][0]
        assert cmd["name"] == "set_gain"
        assert len(cmd["args"]) == 1
        assert cmd["args"][0]["name"] == "gain"
        assert cmd["args"][0]["type"] == "f32"

    def test_command_without_args(self):
        path = _write_toml(VALID_TOML)
        schema = load_schema(path)
        cmd = schema["commands"][1]
        assert cmd["name"] == "reset"
        assert cmd.get("args", []) == []

    def test_ble_transport(self):
        toml = """
[device]
name = "ble-node"
transport = "ble-nus"

[[channel]]
id = 0
name = "data"
type = "u8"
rate_hz = 50
"""
        path = _write_toml(toml)
        schema = load_schema(path)
        assert schema["device"]["transport"] == "ble-nus"


class TestInvalidSchema:
    def test_missing_device(self):
        toml = """
[[channel]]
id = 0
name = "x"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Missing \\[device\\]"):
            load_schema(path)

    def test_missing_device_name(self):
        toml = """
[device]
transport = "usb-cdc"

[[channel]]
id = 0
name = "x"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Missing device.name"):
            load_schema(path)

    def test_invalid_transport(self):
        toml = """
[device]
name = "test"
transport = "spi"

[[channel]]
id = 0
name = "x"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Invalid transport"):
            load_schema(path)

    def test_duplicate_channel_id(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[channel]]
id = 0
name = "a"
type = "u8"
rate_hz = 10

[[channel]]
id = 0
name = "b"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Duplicate channel id"):
            load_schema(path)

    def test_invalid_channel_type(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[channel]]
id = 0
name = "x"
type = "f64"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="invalid type"):
            load_schema(path)

    def test_invalid_channel_name(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[channel]]
id = 0
name = "InvalidName"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Channel name must be lowercase"):
            load_schema(path)

    def test_channel_name_leading_digit(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[channel]]
id = 0
name = "1bad"
type = "u8"
rate_hz = 10
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError):
            load_schema(path)

    def test_missing_file(self):
        with pytest.raises(ConfigError, match="not found"):
            load_schema("/nonexistent/path/seam.toml")

    def test_duplicate_command_id(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[command]]
id = 0
name = "a"

[[command]]
id = 0
name = "b"
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="Duplicate command id"):
            load_schema(path)

    def test_invalid_command_arg_type(self):
        toml = """
[device]
name = "test"
transport = "usb-cdc"

[[command]]
id = 0
name = "bad_cmd"
args = [{ name = "x", type = "f64" }]
"""
        path = _write_toml(toml)
        with pytest.raises(ConfigError, match="invalid type"):
            load_schema(path)


class TestConstants:
    def test_valid_types(self):
        assert VALID_TYPES == {"u8", "u16", "u32", "i16", "i32", "f32", "f32x3", "f32x6"}

    def test_valid_transports(self):
        assert VALID_TRANSPORTS == {"usb-cdc", "ble-nus"}
