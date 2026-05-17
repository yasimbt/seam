import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from seam.cli import cli


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

[[command]]
id = 0
name = "reset"
"""

INVALID_TOML = """
[device]
name = "test"
transport = "invalid-transport"

[[channel]]
id = 0
name = "x"
type = "f64"
rate_hz = 10
"""


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_config():
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
        f.write(VALID_TOML)
        return f.name


@pytest.fixture
def invalid_config():
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
        f.write(INVALID_TOML)
        return f.name


class TestValidate:
    def test_valid_config(self, runner, valid_config):
        result = runner.invoke(cli, ["validate", "--config", valid_config])
        assert result.exit_code == 0
        assert "VALID" in result.output
        assert "test-node" in result.output
        assert "usb-cdc" in result.output
        assert "accel" in result.output
        assert "f32x3" in result.output
        assert "temp" in result.output
        assert "reset" in result.output

    def test_invalid_config(self, runner, invalid_config):
        result = runner.invoke(cli, ["validate", "--config", invalid_config])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_missing_config(self, runner):
        result = runner.invoke(cli, ["validate", "--config", "/nonexistent.toml"])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_valid_config_shows_channels(self, runner, valid_config):
        result = runner.invoke(cli, ["validate", "--config", valid_config])
        assert "[0] accel" in result.output
        assert "[1] temp" in result.output

    def test_valid_config_shows_commands(self, runner, valid_config):
        result = runner.invoke(cli, ["validate", "--config", valid_config])
        assert "[0] reset()" in result.output


class TestRecord:
    def test_record_requires_config(self, runner):
        result = runner.invoke(cli, ["record"])
        assert result.exit_code != 0


class TestInspect:
    def test_inspect_requires_config(self, runner):
        result = runner.invoke(cli, ["inspect"])
        assert result.exit_code != 0

    def test_inspect_valid_config(self, runner, valid_config):
        from unittest.mock import MagicMock, patch

        mock_mod = MagicMock()
        mock_mod.run_inspector = MagicMock()
        with patch.dict("sys.modules", {
            "seam_inspect": mock_mod,
            "seam_inspect.__main__": mock_mod,
        }):
            result = runner.invoke(cli, ["inspect", "--config", valid_config])
        assert result.exit_code == 0
        mock_mod.run_inspector.assert_called_once_with(
            config=valid_config, replay=None
        )


class TestExport:
    def test_export_requires_input(self, runner):
        result = runner.invoke(cli, ["export"])
        assert result.exit_code != 0

    def test_export_unknown_format(self, runner):
        result = runner.invoke(cli, [
            "export", "--input", "test.seam", "--format", "xml", "--output", "out.xml"
        ])
        assert result.exit_code != 0
