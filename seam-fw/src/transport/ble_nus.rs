//! BLE Nordic UART Service (NUS) transport stub.
//!
//! This module provides the skeleton for BLE NUS transport. A full
//! implementation requires the nRF SoftDevice and `embassy-nrf`'s
//! BLE stack (`nrf-softdevice` or `embassy-nrf`'s built-in BLE).
//!
//! The trait implementation is provided here so the crate compiles
//! with `--features ble-nus`. Users must supply the SoftDevice
//! integration for a production build.

use crate::codec::{MAX_FRAME_SIZE, MAX_RAW_FRAME};
use crate::error::SeamError;
use crate::transport::Transport;

/// COBS-encoded buffer size with sentinel
const COBS_BUF_SIZE: usize = MAX_FRAME_SIZE + 1;

/// BLE NUS transport stub.
///
/// Implements the `Transport` trait for BLE Nordic UART Service.
/// The internal buffer management mirrors `UsbCdc` but the actual
/// BLE I/O must be wired to the SoftDevice by the application.
pub struct BleNus {
    rx_buf: [u8; COBS_BUF_SIZE],
    rx_len: usize,
    decoded_buf: [u8; MAX_RAW_FRAME],
    decoded_len: usize,
    /// Set to `true` when a BLE connection is established.
    connected: bool,
}

impl BleNus {
    /// Creates a new `BleNus` transport in the disconnected state.
    pub fn new() -> Self {
        Self {
            rx_buf: [0u8; COBS_BUF_SIZE],
            rx_len: 0,
            decoded_buf: [0u8; MAX_RAW_FRAME],
            decoded_len: 0,
            connected: false,
        }
    }

    /// Marks the transport as connected.
    ///
    /// In a real implementation this is called by the BLE stack
    /// when a central connects.
    pub fn set_connected(&mut self, connected: bool) {
        self.connected = connected;
    }

    /// Feeds raw received bytes into the COBS frame accumulator.
    ///
    /// Call this from the BLE NUS RX characteristic notification handler.
    /// Returns the decoded frame length if a complete frame was extracted.
    pub fn feed_bytes(&mut self, bytes: &[u8]) -> Option<usize> {
        for &b in bytes {
            if self.rx_len < COBS_BUF_SIZE {
                self.rx_buf[self.rx_len] = b;
                self.rx_len += 1;
            } else {
                // Buffer overflow — discard and resync
                self.rx_len = 0;
            }
        }
        self.try_extract_frame()
    }

    fn try_extract_frame(&mut self) -> Option<usize> {
        let delimiter_pos = self.rx_buf[..self.rx_len]
            .iter()
            .position(|&b| b == 0x00)?;

        let encoded = &self.rx_buf[..delimiter_pos];
        match cobs::decode(encoded, &mut self.decoded_buf) {
            Ok(len) => {
                self.decoded_len = len;
                let remaining = self.rx_len - delimiter_pos - 1;
                if remaining > 0 {
                    self.rx_buf.copy_within(
                        delimiter_pos + 1..delimiter_pos + 1 + remaining,
                        0,
                    );
                }
                self.rx_len = remaining;
                Some(len)
            }
            Err(_) => {
                let remaining = self.rx_len - delimiter_pos - 1;
                if remaining > 0 {
                    self.rx_buf.copy_within(
                        delimiter_pos + 1..delimiter_pos + 1 + remaining,
                        0,
                    );
                }
                self.rx_len = remaining;
                None
            }
        }
    }
}

impl Transport for BleNus {
    async fn read_frame(&mut self) -> Result<&[u8], SeamError> {
        // In a real implementation this would wait for BLE notifications.
        // The stub loops until `feed_bytes` has been called with a complete frame.
        loop {
            if let Some(len) = self.try_extract_frame() {
                return Ok(&self.decoded_buf[..len]);
            }
            // Yield to the executor — in production, await a BLE notification channel
            embassy_futures::yield_now().await;
        }
    }

    async fn write_frame(&mut self, data: &[u8]) -> Result<(), SeamError> {
        if !self.connected {
            return Err(SeamError::TransportError);
        }

        let mut cobs_buf = [0u8; COBS_BUF_SIZE];
        let encoded_len = cobs::encode(data, &mut cobs_buf);
        cobs_buf[encoded_len] = 0x00;
        let total_len = encoded_len + 1;

        // In a real implementation, write to the NUS TX characteristic.
        // The stub acknowledges success but does not actually transmit.
        let _ = &cobs_buf[..total_len];
        Ok(())
    }
}
