//! USB CDC ACM transport implementation.
//!
//! Uses `embassy-usb` to provide a CDC ACM serial interface.
//! The COBS framing is handled internally — `read_frame` returns
//! decoded payloads and `write_frame` accepts raw bytes.

use crate::codec::{MAX_FRAME_SIZE, MAX_RAW_FRAME};
use crate::error::SeamError;
use crate::transport::Transport;
use embassy_usb::class::cdc_acm::CdcAcmClass;
use embassy_usb::driver::{Driver, EndpointError};

/// COBS-encoded buffer size with sentinel
const COBS_BUF_SIZE: usize = MAX_FRAME_SIZE + 1;

/// USB CDC ACM transport.
///
/// Wraps an `embassy-usb` CDC ACM class and handles COBS framing
/// for frame boundary detection.
pub struct UsbCdc<'d, D: Driver<'d>> {
    class: CdcAcmClass<'d, D>,
    /// Accumulator for incoming bytes — holds COBS-encoded data
    /// up to the next 0x00 delimiter.
    rx_buf: [u8; COBS_BUF_SIZE],
    rx_len: usize,
    /// Static buffer for decoded frame output (returned from read_frame)
    decoded_buf: [u8; MAX_RAW_FRAME],
    decoded_len: usize,
}

impl<'d, D: Driver<'d>> UsbCdc<'d, D> {
    /// Creates a new `UsbCdc` transport from an initialised CDC ACM class.
    ///
    /// The caller is responsible for creating and running the `embassy-usb`
    /// `UsbDevice` with the same driver.
    pub fn new(class: CdcAcmClass<'d, D>) -> Self {
        Self {
            class,
            rx_buf: [0u8; COBS_BUF_SIZE],
            rx_len: 0,
            decoded_buf: [0u8; MAX_RAW_FRAME],
            decoded_len: 0,
        }
    }

    /// Runs the USB device initialisation and waits for the host to configure.
    ///
    /// This must be called once before `read_frame` / `write_frame`.
    pub async fn init(&mut self) -> Result<(), SeamError> {
        self.class.wait_connection().await;
        Ok(())
    }

    /// Reads a single byte from the USB CDC endpoint.
    async fn read_byte(&mut self) -> Result<u8, SeamError> {
        let mut buf = [0u8; 1];
        match self.class.read_packet(&mut buf).await {
            Ok(n) if n > 0 => Ok(buf[0]),
            Ok(_) => Err(SeamError::TransportError),
            Err(EndpointError::BufferOverflow) => Err(SeamError::CodecError),
            Err(EndpointError::Disabled) => Err(SeamError::TransportError),
        }
    }

    /// Finds the next COBS frame in the rx buffer, decodes it, and returns the decoded length.
    /// Returns `None` if no complete frame (0x00 delimiter) is found.
    fn try_extract_frame(&mut self) -> Option<usize> {
        // Find the next 0x00 delimiter
        let delimiter_pos = self.rx_buf[..self.rx_len]
            .iter()
            .position(|&b| b == 0x00)?;

        // Decode the COBS frame (excluding the delimiter)
        let encoded = &self.rx_buf[..delimiter_pos];
        match cobs::decode(encoded, &mut self.decoded_buf) {
            Ok(len) => {
                self.decoded_len = len;
                // Shift remaining data to the front
                let remaining = self.rx_len - delimiter_pos - 1;
                if remaining > 0 {
                    self.rx_buf.copy_within(delimiter_pos + 1..delimiter_pos + 1 + remaining, 0);
                }
                self.rx_len = remaining;
                Some(len)
            }
            Err(_) => {
                // Discard bad frame and continue
                let remaining = self.rx_len - delimiter_pos - 1;
                if remaining > 0 {
                    self.rx_buf.copy_within(delimiter_pos + 1..delimiter_pos + 1 + remaining, 0);
                }
                self.rx_len = remaining;
                None
            }
        }
    }
}

impl<'d, D: Driver<'d>> Transport for UsbCdc<'d, D> {
    async fn read_frame(&mut self) -> Result<&[u8], SeamError> {
        loop {
            // Check if we already have a complete frame
            if let Some(len) = self.try_extract_frame() {
                return Ok(&self.decoded_buf[..len]);
            }

            // Read more bytes
            let byte = self.read_byte().await?;

            if self.rx_len < COBS_BUF_SIZE {
                self.rx_buf[self.rx_len] = byte;
                self.rx_len += 1;
            } else {
                // Buffer overflow — discard and resync
                self.rx_len = 0;
            }
        }
    }

    async fn write_frame(&mut self, data: &[u8]) -> Result<(), SeamError> {
        let mut cobs_buf = [0u8; COBS_BUF_SIZE];
        let encoded_len = cobs::encode(data, &mut cobs_buf);
        // Append the COBS 0x00 packet delimiter
        cobs_buf[encoded_len] = 0x00;
        let total_len = encoded_len + 1;

        // Write the COBS-encoded frame including the 0x00 delimiter
        let mut offset = 0;
        while offset < total_len {
            let chunk_len = (total_len - offset).min(256);
            let mut tx_buf = [0u8; 256];
            tx_buf[..chunk_len].copy_from_slice(&cobs_buf[offset..offset + chunk_len]);
            self.class
                .write_packet(&tx_buf[..chunk_len])
                .await
                .map_err(|_| SeamError::TransportError)?;
            offset += chunk_len;
        }

        Ok(())
    }
}
