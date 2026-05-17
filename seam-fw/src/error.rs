/// Base error type for all Seam operations.
///
/// This enum has no catch-all variant. Each variant represents a specific
/// failure mode in the firmware.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeamError {
    /// Hardware transport failure (USB disconnect, BLE link loss, etc.)
    TransportError,
    /// COBS encode/decode failure or malformed frame structure
    CodecError,
    /// Received frame for a channel ID not in the schema
    UnknownChannel,
    /// Received command for a command ID not in the schema
    UnknownCommand,
    /// Device returned NACK for a sent command
    CommandNack,
    /// Frame structure is invalid (too short, bad length field, etc.)
    InvalidFrame,
}

impl core::fmt::Display for SeamError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            SeamError::TransportError => write!(f, "transport error"),
            SeamError::CodecError => write!(f, "codec error"),
            SeamError::UnknownChannel => write!(f, "unknown channel"),
            SeamError::UnknownCommand => write!(f, "unknown command"),
            SeamError::CommandNack => write!(f, "command nack"),
            SeamError::InvalidFrame => write!(f, "invalid frame"),
        }
    }
}
