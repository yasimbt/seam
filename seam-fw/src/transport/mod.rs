use crate::SeamError;

/// Transport trait — the abstraction over the physical link to the host.
///
/// Implementations handle COBS framing internally. `read_frame` returns
/// the decoded (post-COBS) frame payload. `write_frame` accepts raw
/// (pre-COBS) bytes and handles encoding + delimiter emission.
///
/// The lifetime on `read_frame` is tied to `&mut self`; implementations
/// typically use an internal buffer and return a slice into it.
pub trait Transport {
    /// Reads one decoded frame from the transport.
    ///
    /// Blocks until a complete frame is available. Returns the decoded
    /// payload (after COBS decoding). The returned slice is valid until
    /// the next call to `read_frame` or `write_frame`.
    fn read_frame(&mut self) -> impl core::future::Future<Output = Result<&[u8], SeamError>>;

    /// Writes a raw (pre-COBS) frame to the transport.
    ///
    /// The implementation handles COBS encoding and packet delimiter
    /// emission.
    fn write_frame(
        &mut self,
        data: &[u8],
    ) -> impl core::future::Future<Output = Result<(), SeamError>>;
}

// ── Transport implementations ───────────────────────────────────────────────

#[cfg(all(feature = "usb-cdc", target_os = "none"))]
pub mod usb_cdc;

#[cfg(all(feature = "ble-nus", target_os = "none"))]
pub mod ble_nus;

#[cfg(all(feature = "usb-cdc", target_os = "none"))]
pub use usb_cdc::UsbCdc;

#[cfg(all(feature = "ble-nus", target_os = "none"))]
pub use ble_nus::BleNus;
