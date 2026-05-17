#![no_std]

pub mod channel_info;
pub mod codec;
pub mod error;
pub mod transport;

pub use codec::{encode_cmd_ack, encode_cmd_nack, encode_data_frame, decode_frame, decode_cmd_frame, Encode, DecodedFrame, CmdFrame};
pub use error::SeamError;
pub use transport::Transport;

// ── Generated code from seam.toml ───────────────────────────────────────────

include!(concat!(env!("OUT_DIR"), "/seam_generated.rs"));

// ── Wire protocol constants ─────────────────────────────────────────────────

/// Frame type: data frame (device → host)
pub const FRAME_DATA: u8 = 0x01;
/// Frame type: command ACK (device → host)
pub const FRAME_ACK: u8 = 0x02;
/// Frame type: command NACK (device → host)
pub const FRAME_NACK: u8 = 0x03;
/// Frame type: command (host → device)
pub const FRAME_CMD: u8 = 0x10;

// ── Sampler ─────────────────────────────────────────────────────────────────

/// The core sampler that manages streaming data and command handling.
///
/// `Sampler` wraps a `Transport` implementation and provides typed methods
/// for sending sensor data and handling incoming host commands.
pub struct Sampler<T: Transport> {
    transport: T,
    handler: Option<fn(&mut T, Command)>,
}

impl<T: Transport> Sampler<T> {
    /// Creates a new `Sampler` with the given transport.
    pub fn new(transport: T) -> Self {
        Self {
            transport,
            handler: None,
        }
    }

    /// Sends a typed data frame on the given channel.
    ///
    /// The value is encoded according to the channel's type and sent
    /// as a COBS-framed TLV data frame to the host.
    pub async fn send<V: Encode>(&mut self, channel: Channel, value: V) -> Result<(), SeamError> {
        #[cfg(target_os = "none")]
        let timestamp_ms = embassy_time::Instant::now().as_millis() as u32;
        #[cfg(not(target_os = "none"))]
        let timestamp_ms = 0u32;
        let mut buf = [0u8; codec::MAX_FRAME_SIZE];
        let encoded_len = encode_data_frame(channel, timestamp_ms, value, &mut buf)
            .map_err(|_| SeamError::CodecError)?;
        self.transport
            .write_frame(&buf[..encoded_len])
            .await
    }

    /// Registers a command handler closure.
    ///
    /// The handler receives the decoded `Command` enum and the mutable
    /// transport reference, allowing it to respond via `send()` or
    /// direct transport writes.
    ///
    /// Only one handler can be registered at a time. The handler should
    /// pattern-match on the `Command` enum to dispatch per-command logic.
    pub fn on_command(&mut self, handler: fn(&mut T, Command)) {
        self.handler = Some(handler);
    }

    /// Runs the main event loop.
    ///
    /// Continuously reads incoming frames from the transport, decodes them,
    /// and dispatches command frames to the registered handler. Data frames
    /// received from the host are ignored (data flows device → host only).
    pub async fn run(&mut self) -> ! {
        // Staging buffer to copy command bytes out of the transport buffer
        // before releasing the borrow so we can pass &mut transport to the handler.
        let mut cmd_buf = [0u8; 260]; // 4-byte header + up to 255 args + 1 spare
        loop {
            let cmd_len = {
                let frame = match self.transport.read_frame().await {
                    Ok(f) => f,
                    Err(_) => continue,
                };
                // frame is COBS-decoded TLV; transport handles COBS internally.
                if frame.len() >= 4 && frame[0] == FRAME_CMD {
                    let copy_len = frame.len().min(cmd_buf.len());
                    cmd_buf[..copy_len].copy_from_slice(&frame[..copy_len]);
                    Some(copy_len)
                } else {
                    None
                }
            }; // transport borrow released

            if let Some(frame_len) = cmd_len {
                let command_id = cmd_buf[1];
                let args_len = cmd_buf[3] as usize;
                let args_end = (4 + args_len).min(frame_len);
                let args = &cmd_buf[4..args_end];
                if let Some(cmd) = Command::from_bytes(command_id, args) {
                    let handler = self.handler;
                    if let Some(handler) = handler {
                        handler(&mut self.transport, cmd);
                    }
                }
            }
        }
    }

    /// Sends an ACK for a command with the given sequence number.
    pub async fn send_ack(&mut self, command_id: u8, seq: u8) -> Result<(), SeamError> {
        let mut buf = [0u8; 8];
        let len = encode_cmd_ack(command_id, seq, &mut buf)
            .map_err(|_| SeamError::CodecError)?;
        self.transport.write_frame(&buf[..len]).await
    }

    /// Sends a NACK for a command with the given sequence number.
    pub async fn send_nack(&mut self, command_id: u8, seq: u8) -> Result<(), SeamError> {
        let mut buf = [0u8; 8];
        let len = encode_cmd_nack(command_id, seq, &mut buf)
            .map_err(|_| SeamError::CodecError)?;
        self.transport.write_frame(&buf[..len]).await
    }
}
