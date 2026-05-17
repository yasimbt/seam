class SeamError(Exception):
    """Base exception for all Seam errors."""


class ConnectionError(SeamError):
    """Device not found, port unavailable, or BLE scan timeout."""


class FrameDecodeError(SeamError):
    """COBS failure or malformed frame structure."""


class UnknownChannelError(SeamError):
    """Received frame for channel ID not in schema."""


class UnknownCommandError(SeamError):
    """send() called with name not in schema."""


class CommandNackError(SeamError):
    """Device returned NACK for a sent command."""


class ConfigError(SeamError):
    """seam.toml missing, malformed, or fails validation."""


class RecordingError(SeamError):
    """.seam file corrupt, version unsupported, or schema invalid."""
