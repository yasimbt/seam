use crate::channel_info::ChannelInfo;
use crate::{FRAME_ACK, FRAME_CMD, FRAME_DATA, FRAME_NACK};

// ── Encode trait ────────────────────────────────────────────────────────────

/// Trait for types that can be encoded into a little-endian byte buffer.
///
/// Implementations write their byte representation into `buf` starting at
/// offset 0 and return the number of bytes written.
pub trait Encode {
    fn encode_into(&self, buf: &mut [u8]) -> usize;
}

impl Encode for u8 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[0] = *self;
        1
    }
}

impl Encode for u16 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[..2].copy_from_slice(&self.to_le_bytes());
        2
    }
}

impl Encode for u32 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[..4].copy_from_slice(&self.to_le_bytes());
        4
    }
}

impl Encode for i16 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[..2].copy_from_slice(&self.to_le_bytes());
        2
    }
}

impl Encode for i32 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[..4].copy_from_slice(&self.to_le_bytes());
        4
    }
}

impl Encode for f32 {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        buf[..4].copy_from_slice(&self.to_le_bytes());
        4
    }
}

impl Encode for [f32; 3] {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        let mut off = 0;
        for v in self {
            buf[off..off + 4].copy_from_slice(&v.to_le_bytes());
            off += 4;
        }
        off
    }
}

impl Encode for [f32; 6] {
    fn encode_into(&self, buf: &mut [u8]) -> usize {
        let mut off = 0;
        for v in self {
            buf[off..off + 4].copy_from_slice(&v.to_le_bytes());
            off += 4;
        }
        off
    }
}

// ── Byte size lookup ────────────────────────────────────────────────────────

/// Returns the wire byte size for a TOML type string.
pub fn payload_size_for(toml_type: &str) -> usize {
    match toml_type {
        "u8" => 1,
        "u16" => 2,
        "u32" => 4,
        "i16" => 2,
        "i32" => 4,
        "f32" => 4,
        "f32x3" => 12,
        "f32x6" => 24,
        _ => 0,
    }
}

// ── Constants ───────────────────────────────────────────────────────────────

/// Maximum raw (pre-COBS) frame size: type(1) + channel(1) + timestamp(4) + length(1) + payload(255)
pub const MAX_RAW_FRAME: usize = 262;
/// Maximum COBS-encoded frame size (raw + 1 byte overhead + sentinel)
pub const MAX_FRAME_SIZE: usize = MAX_RAW_FRAME + 2;
/// Maximum command frame raw size: type(1) + cmd_id(1) + seq(1) + length(1) + args(255)
pub const MAX_CMD_RAW: usize = 259;
pub const MAX_CMD_FRAME: usize = MAX_CMD_RAW + 2;

// ── Data frame encoder ──────────────────────────────────────────────────────

/// Encodes a typed data frame into `buf` and returns the COBS-encoded length.
///
/// Wire layout: type(1) | channel(1) | timestamp_ms(4 LE) | length(1) | payload
pub fn encode_data_frame<C: ChannelInfo, V: Encode>(
    channel: C,
    timestamp_ms: u32,
    value: V,
    buf: &mut [u8],
) -> Result<usize, EncodeError> {
    let payload_len = channel.payload_size();
    let raw_len = 1 + 1 + 4 + 1 + payload_len; // type + chan + ts + len + payload

    if buf.len() < raw_len {
        return Err(EncodeError::BufferTooSmall);
    }

    buf[0] = FRAME_DATA;
    buf[1] = channel.id();
    buf[2..6].copy_from_slice(&timestamp_ms.to_le_bytes());
    buf[6] = payload_len as u8;

    let mut payload_buf = [0u8; 24]; // max payload is f32x6 = 24 bytes
    let written = value.encode_into(&mut payload_buf);
    if written != payload_len {
        return Err(EncodeError::SizeMismatch);
    }
    buf[7..7 + payload_len].copy_from_slice(&payload_buf[..payload_len]);

    // COBS encode the raw frame (cobs 0.3 returns usize directly)
    let mut cobs_buf = [0u8; MAX_FRAME_SIZE];
    let encoded = cobs::encode(&buf[..raw_len], &mut cobs_buf);

    // Copy COBS output back into caller's buffer
    buf[..encoded].copy_from_slice(&cobs_buf[..encoded]);
    Ok(encoded)
}

// ── Command ACK/NACK encoders ───────────────────────────────────────────────

/// Encodes a command ACK frame. Returns the COBS-encoded length.
pub fn encode_cmd_ack(
    command_id: u8,
    seq: u8,
    buf: &mut [u8],
) -> Result<usize, EncodeError> {
    encode_cmd_response(FRAME_ACK, command_id, seq, buf)
}

/// Encodes a command NACK frame. Returns the COBS-encoded length.
pub fn encode_cmd_nack(
    command_id: u8,
    seq: u8,
    buf: &mut [u8],
) -> Result<usize, EncodeError> {
    encode_cmd_response(FRAME_NACK, command_id, seq, buf)
}

fn encode_cmd_response(
    frame_type: u8,
    command_id: u8,
    seq: u8,
    buf: &mut [u8],
) -> Result<usize, EncodeError> {
    let raw = [frame_type, command_id, seq, 0]; // length = 0 for ACK/NACK
    let mut cobs_buf = [0u8; 16];
    let encoded = cobs::encode(&raw, &mut cobs_buf);
    buf[..encoded].copy_from_slice(&cobs_buf[..encoded]);
    Ok(encoded)
}

// ── Decoded frame types ─────────────────────────────────────────────────────

/// A decoded incoming command frame from the host.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CmdFrame {
    pub command_id: u8,
    pub seq: u8,
    pub args_len: u8,
}

/// Result of decoding an incoming frame.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DecodedFrame {
    /// A data frame — unexpected from host, included for completeness.
    Data {
        channel_id: u8,
        timestamp_ms: u32,
        payload_len: u8,
    },
    /// A command frame from the host.
    Command(CmdFrame),
    /// A command ACK from the host — unusual but decodable.
    Ack { command_id: u8, seq: u8 },
    /// A command NACK from the host.
    Nack { command_id: u8, seq: u8 },
}

// ── Frame decoder ───────────────────────────────────────────────────────────

/// Decodes a COBS-encoded frame and returns the parsed frame type and fields.
pub fn decode_frame(encoded: &[u8]) -> Result<DecodedFrame, DecodeError> {
    let mut raw = [0u8; MAX_RAW_FRAME];
    let raw_len = cobs::decode(encoded, &mut raw)
        .map_err(|_| DecodeError::CobsError)?;

    if raw_len < 1 {
        return Err(DecodeError::FrameTooShort);
    }

    let frame_type = raw[0];

    match frame_type {
        FRAME_DATA => {
            if raw_len < 7 {
                return Err(DecodeError::FrameTooShort);
            }
            let channel_id = raw[1];
            let timestamp_ms = u32::from_le_bytes([raw[2], raw[3], raw[4], raw[5]]);
            let payload_len = raw[6];
            Ok(DecodedFrame::Data {
                channel_id,
                timestamp_ms,
                payload_len,
            })
        }
        FRAME_ACK | FRAME_NACK => {
            if raw_len < 4 {
                return Err(DecodeError::FrameTooShort);
            }
            let command_id = raw[1];
            let seq = raw[2];
            if frame_type == FRAME_ACK {
                Ok(DecodedFrame::Ack { command_id, seq })
            } else {
                Ok(DecodedFrame::Nack { command_id, seq })
            }
        }
        FRAME_CMD => decode_cmd_frame_from_raw(&raw[..raw_len]).map(DecodedFrame::Command),
        other => Err(DecodeError::UnknownFrameType(other)),
    }
}

/// Decodes a COBS-encoded command frame directly into a `CmdFrame`.
pub fn decode_cmd_frame(encoded: &[u8]) -> Result<CmdFrame, DecodeError> {
    let mut raw = [0u8; MAX_CMD_RAW];
    let raw_len = cobs::decode(encoded, &mut raw)
        .map_err(|_| DecodeError::CobsError)?;

    decode_cmd_frame_from_raw(&raw[..raw_len])
}

fn decode_cmd_frame_from_raw(raw: &[u8]) -> Result<CmdFrame, DecodeError> {
    if raw.len() < 4 {
        return Err(DecodeError::FrameTooShort);
    }
    if raw[0] != FRAME_CMD {
        return Err(DecodeError::UnknownFrameType(raw[0]));
    }
    let command_id = raw[1];
    let seq = raw[2];
    let args_len = raw[3];
    Ok(CmdFrame {
        command_id,
        seq,
        args_len,
    })
}

// ── Error types ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncodeError {
    BufferTooSmall,
    SizeMismatch,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DecodeError {
    CobsError,
    FrameTooShort,
    UnknownFrameType(u8),
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ── Stub ChannelInfo for tests ──────────────────────────────────────────

    struct TestChannel {
        id: u8,
        payload_size: usize,
    }

    impl ChannelInfo for TestChannel {
        fn id(&self) -> u8 {
            self.id
        }
        fn payload_size(&self) -> usize {
            self.payload_size
        }
    }

    // ── Encode trait tests ──────────────────────────────────────────────────

    #[test]
    fn test_encode_u8() {
        let mut buf = [0u8; 4];
        let n: u8 = 0xAB;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 1);
        assert_eq!(buf[0], 0xAB);
    }

    #[test]
    fn test_encode_u16() {
        let mut buf = [0u8; 4];
        let n: u16 = 0x1234;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 2);
        assert_eq!(&buf[..2], &[0x34, 0x12]);
    }

    #[test]
    fn test_encode_u32() {
        let mut buf = [0u8; 8];
        let n: u32 = 0x12345678;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 4);
        assert_eq!(&buf[..4], &[0x78, 0x56, 0x34, 0x12]);
    }

    #[test]
    fn test_encode_i16() {
        let mut buf = [0u8; 4];
        let n: i16 = -100;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 2);
        let decoded = i16::from_le_bytes([buf[0], buf[1]]);
        assert_eq!(decoded, -100);
    }

    #[test]
    fn test_encode_i32() {
        let mut buf = [0u8; 8];
        let n: i32 = -12345;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 4);
        let decoded = i32::from_le_bytes([buf[0], buf[1], buf[2], buf[3]]);
        assert_eq!(decoded, -12345);
    }

    #[test]
    fn test_encode_f32() {
        let mut buf = [0u8; 8];
        let n: f32 = 3.14159;
        let written = n.encode_into(&mut buf);
        assert_eq!(written, 4);
        let decoded = f32::from_le_bytes([buf[0], buf[1], buf[2], buf[3]]);
        assert!((decoded - n).abs() < 1e-6);
    }

    #[test]
    fn test_encode_f32x3() {
        let mut buf = [0u8; 16];
        let v: [f32; 3] = [1.0, 2.0, 3.0];
        let written = v.encode_into(&mut buf);
        assert_eq!(written, 12);
        let x = f32::from_le_bytes([buf[0], buf[1], buf[2], buf[3]]);
        let y = f32::from_le_bytes([buf[4], buf[5], buf[6], buf[7]]);
        let z = f32::from_le_bytes([buf[8], buf[9], buf[10], buf[11]]);
        assert!((x - 1.0).abs() < 1e-6);
        assert!((y - 2.0).abs() < 1e-6);
        assert!((z - 3.0).abs() < 1e-6);
    }

    #[test]
    fn test_encode_f32x6() {
        let mut buf = [0u8; 32];
        let v: [f32; 6] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6];
        let written = v.encode_into(&mut buf);
        assert_eq!(written, 24);
        for i in 0..6 {
            let val = f32::from_le_bytes([
                buf[i * 4],
                buf[i * 4 + 1],
                buf[i * 4 + 2],
                buf[i * 4 + 3],
            ]);
            let expected = (i as f32 + 1.0) * 0.1;
            assert!((val - expected).abs() < 1e-6, "mismatch at index {i}");
        }
    }

    #[test]
    fn test_payload_size_for_all_types() {
        assert_eq!(payload_size_for("u8"), 1);
        assert_eq!(payload_size_for("u16"), 2);
        assert_eq!(payload_size_for("u32"), 4);
        assert_eq!(payload_size_for("i16"), 2);
        assert_eq!(payload_size_for("i32"), 4);
        assert_eq!(payload_size_for("f32"), 4);
        assert_eq!(payload_size_for("f32x3"), 12);
        assert_eq!(payload_size_for("f32x6"), 24);
        assert_eq!(payload_size_for("unknown"), 0);
    }

    // ── COBS round-trip tests ───────────────────────────────────────────────

    #[test]
    fn test_cobs_roundtrip_empty() {
        // cobs 0.3 encodes an empty slice as 0 bytes (no overhead byte emitted).
        // Empty frames do not appear in the seam protocol; this documents the behaviour.
        let data: [u8; 0] = [];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&data, &mut encoded);
        assert_eq!(enc_len, 0);
    }

    #[test]
    fn test_cobs_roundtrip_no_zero() {
        let data = [0x01, 0x02, 0x03, 0x04, 0x05];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&data, &mut encoded);
        let mut decoded = [0u8; 16];
        let dec_len = cobs::decode(&encoded[..enc_len], &mut decoded).unwrap();
        assert_eq!(&decoded[..dec_len], &data[..]);
    }

    #[test]
    fn test_cobs_roundtrip_with_zeros() {
        let data = [0x01, 0x00, 0x02, 0x00, 0x03];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&data, &mut encoded);
        let mut decoded = [0u8; 16];
        let dec_len = cobs::decode(&encoded[..enc_len], &mut decoded).unwrap();
        assert_eq!(&decoded[..dec_len], &data[..]);
    }

    #[test]
    fn test_cobs_roundtrip_all_zeros() {
        let data = [0x00, 0x00, 0x00];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&data, &mut encoded);
        let mut decoded = [0u8; 16];
        let dec_len = cobs::decode(&encoded[..enc_len], &mut decoded).unwrap();
        assert_eq!(&decoded[..dec_len], &data[..]);
    }

    // ── Data frame encode/decode round-trip ─────────────────────────────────

    #[test]
    fn test_encode_decode_data_frame_f32() {
        let ch = TestChannel { id: 1, payload_size: 4 };
        let value: f32 = 1.5;
        let mut buf = [0u8; MAX_FRAME_SIZE];
        let enc_len = encode_data_frame(ch, 1000, value, &mut buf).unwrap();

        let decoded = decode_frame(&buf[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Data {
                channel_id,
                timestamp_ms,
                payload_len,
            } => {
                assert_eq!(channel_id, 1);
                assert_eq!(timestamp_ms, 1000);
                assert_eq!(payload_len, 4);
            }
            _ => panic!("expected Data frame"),
        }
    }

    #[test]
    fn test_encode_decode_data_frame_f32x3() {
        let ch = TestChannel { id: 2, payload_size: 12 };
        let value: [f32; 3] = [1.0, -2.5, 0.0];
        let mut buf = [0u8; MAX_FRAME_SIZE];
        let enc_len = encode_data_frame(ch, 5000, value, &mut buf).unwrap();

        let decoded = decode_frame(&buf[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Data {
                channel_id,
                timestamp_ms,
                payload_len,
            } => {
                assert_eq!(channel_id, 2);
                assert_eq!(timestamp_ms, 5000);
                assert_eq!(payload_len, 12);
            }
            _ => panic!("expected Data frame"),
        }
    }

    #[test]
    fn test_encode_decode_data_frame_u8() {
        let ch = TestChannel { id: 10, payload_size: 1 };
        let value: u8 = 0x42;
        let mut buf = [0u8; MAX_FRAME_SIZE];
        let enc_len = encode_data_frame(ch, 999, value, &mut buf).unwrap();

        let decoded = decode_frame(&buf[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Data { channel_id, payload_len, .. } => {
                assert_eq!(channel_id, 10);
                assert_eq!(payload_len, 1);
            }
            _ => panic!("expected Data frame"),
        }
    }

    #[test]
    fn test_decode_cmd_frame() {
        let raw = [FRAME_CMD, 1, 5, 2];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&raw, &mut encoded);

        let decoded = decode_frame(&encoded[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Command(cmd) => {
                assert_eq!(cmd.command_id, 1);
                assert_eq!(cmd.seq, 5);
                assert_eq!(cmd.args_len, 2);
            }
            _ => panic!("expected Command frame"),
        }
    }

    #[test]
    fn test_decode_ack_frame() {
        let raw = [FRAME_ACK, 1, 5, 0];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&raw, &mut encoded);

        let decoded = decode_frame(&encoded[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Ack { command_id, seq } => {
                assert_eq!(command_id, 1);
                assert_eq!(seq, 5);
            }
            _ => panic!("expected Ack frame"),
        }
    }

    #[test]
    fn test_decode_nack_frame() {
        let raw = [FRAME_NACK, 2, 10, 0];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&raw, &mut encoded);

        let decoded = decode_frame(&encoded[..enc_len]).unwrap();
        match decoded {
            DecodedFrame::Nack { command_id, seq } => {
                assert_eq!(command_id, 2);
                assert_eq!(seq, 10);
            }
            _ => panic!("expected Nack frame"),
        }
    }

    #[test]
    fn test_decode_frame_too_short() {
        let raw = [FRAME_DATA, 1];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&raw, &mut encoded);

        let result = decode_frame(&encoded[..enc_len]);
        assert!(result.is_err());
    }

    #[test]
    fn test_decode_unknown_frame_type() {
        let raw = [0xFF, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06];
        let mut encoded = [0u8; 16];
        let enc_len = cobs::encode(&raw, &mut encoded);

        let result = decode_frame(&encoded[..enc_len]);
        match result {
            Err(DecodeError::UnknownFrameType(0xFF)) => {}
            _ => panic!("expected UnknownFrameType(0xFF)"),
        }
    }

    #[test]
    fn test_encode_cmd_ack() {
        let mut buf = [0u8; 16];
        let len = encode_cmd_ack(1, 5, &mut buf).unwrap();
        assert!(len > 0);

        let decoded = decode_frame(&buf[..len]).unwrap();
        match decoded {
            DecodedFrame::Ack { command_id, seq } => {
                assert_eq!(command_id, 1);
                assert_eq!(seq, 5);
            }
            _ => panic!("expected Ack"),
        }
    }

    #[test]
    fn test_encode_cmd_nack() {
        let mut buf = [0u8; 16];
        let len = encode_cmd_nack(2, 10, &mut buf).unwrap();
        assert!(len > 0);

        let decoded = decode_frame(&buf[..len]).unwrap();
        match decoded {
            DecodedFrame::Nack { command_id, seq } => {
                assert_eq!(command_id, 2);
                assert_eq!(seq, 10);
            }
            _ => panic!("expected Nack"),
        }
    }

    #[test]
    fn test_encode_buffer_too_small() {
        let ch = TestChannel { id: 1, payload_size: 4 };
        let value: f32 = 1.0;
        let mut buf = [0u8; 4]; // too small
        let result = encode_data_frame(ch, 0, value, &mut buf);
        assert!(result.is_err());
    }

    #[test]
    fn test_encode_size_mismatch() {
        // Channel says payload is 12 bytes but we encode an f32 (4 bytes)
        let ch = TestChannel { id: 1, payload_size: 12 };
        let value: f32 = 1.0;
        let mut buf = [0u8; MAX_FRAME_SIZE];
        let result = encode_data_frame(ch, 0, value, &mut buf);
        assert_eq!(result, Err(EncodeError::SizeMismatch));
    }
}
