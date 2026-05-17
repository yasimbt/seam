/**
 * @file codec.h
 * @brief Seam COBS+TLV codec — wire protocol encode/decode.
 *
 * All frames are COBS-encoded on the wire with 0x00 as the packet delimiter.
 * After COBS decoding the layout is:
 *
 * Data frame (device → host):
 *   type(1) | channel(1) | timestamp_ms(4 LE) | length(1) | payload(0-255 LE)
 *
 * Command frame (host → device):
 *   type(1) | command_id(1) | seq(1) | length(1) | args(0-255 LE)
 *
 * Response frame (device → host, ACK or NACK):
 *   type(1) | command_id(1) | seq(1) | length(1) [length is always 0]
 */

#ifndef SEAM_CODEC_H
#define SEAM_CODEC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Frame type bytes */
#define SEAM_FRAME_DATA  0x01u
#define SEAM_FRAME_ACK   0x02u
#define SEAM_FRAME_NACK  0x03u
#define SEAM_FRAME_CMD   0x10u

/** Minimum decoded frame sizes */
#define SEAM_DATA_FRAME_HEADER_LEN 7u  /* type + channel + ts(4) + length */
#define SEAM_CMD_FRAME_HEADER_LEN  4u  /* type + cmd_id + seq + length */

/** Maximum raw (pre-COBS) payload size */
#define SEAM_MAX_PAYLOAD CONFIG_SEAM_MAX_FRAME_PAYLOAD

/** COBS overhead: at most 1 extra byte per 254 bytes + 1 sentinel */
#define SEAM_MAX_RAW_FRAME  (SEAM_DATA_FRAME_HEADER_LEN + SEAM_MAX_PAYLOAD)
#define SEAM_MAX_COBS_FRAME (SEAM_MAX_RAW_FRAME + (SEAM_MAX_RAW_FRAME / 254) + 2u)

/**
 * @brief Encode a data frame into a COBS-framed output buffer.
 *
 * @param out         Output buffer (must hold at least SEAM_MAX_COBS_FRAME bytes).
 * @param out_size    Size of output buffer.
 * @param channel_id  Channel identifier (matches seam.toml `id`).
 * @param timestamp_ms Milliseconds since device boot (u32 LE on wire).
 * @param payload     Raw payload bytes (little-endian values per channel type).
 * @param payload_len Number of payload bytes.
 * @return Number of bytes written to @p out (including 0x00 sentinel), or 0 on error.
 */
size_t seam_encode_data_frame(uint8_t *out, size_t out_size,
                              uint8_t channel_id, uint32_t timestamp_ms,
                              const uint8_t *payload, uint8_t payload_len);

/**
 * @brief Encode a command ACK frame.
 *
 * @param out        Output buffer.
 * @param out_size   Size of output buffer.
 * @param command_id Command identifier being acknowledged.
 * @param seq        Sequence byte echoed from the received command frame.
 * @return Number of bytes written, or 0 on error.
 */
size_t seam_encode_cmd_ack(uint8_t *out, size_t out_size,
                           uint8_t command_id, uint8_t seq);

/**
 * @brief Encode a command NACK frame.
 *
 * @param out        Output buffer.
 * @param out_size   Size of output buffer.
 * @param command_id Command identifier being rejected.
 * @param seq        Sequence byte echoed from the received command frame.
 * @return Number of bytes written, or 0 on error.
 */
size_t seam_encode_cmd_nack(uint8_t *out, size_t out_size,
                            uint8_t command_id, uint8_t seq);

/**
 * @brief Decoded command frame fields.
 */
typedef struct {
    uint8_t        command_id;
    uint8_t        seq;
    const uint8_t *args;
    uint8_t        args_len;
} seam_cmd_frame_t;

/**
 * @brief Parse a raw (post-COBS) command frame.
 *
 * @param raw     Decoded frame bytes (COBS delimiter already stripped).
 * @param raw_len Length of @p raw.
 * @param out     Populated on success; @p args points into @p raw (no copy).
 * @return 0 on success, -1 if the frame is malformed or not a command frame.
 */
int seam_decode_cmd_frame(const uint8_t *raw, size_t raw_len,
                          seam_cmd_frame_t *out);

/**
 * @brief COBS-encode src into dst, appending a 0x00 sentinel.
 *
 * Standard COBS (no custom variant). The sentinel byte is included in the
 * returned length.
 *
 * @param src      Input bytes.
 * @param src_len  Number of input bytes.
 * @param dst      Output buffer (must hold at least src_len + src_len/254 + 2 bytes).
 * @param dst_size Size of @p dst.
 * @return Number of bytes written (including sentinel), or 0 if @p dst is too small.
 */
size_t seam_cobs_encode(const uint8_t *src, size_t src_len,
                        uint8_t *dst, size_t dst_size);

/**
 * @brief COBS-decode src into dst.
 *
 * The input must NOT include the trailing 0x00 sentinel.
 *
 * @param src      COBS-encoded bytes (no sentinel).
 * @param src_len  Number of input bytes.
 * @param dst      Output buffer.
 * @param dst_size Size of @p dst.
 * @return Number of decoded bytes written, or SIZE_MAX on error.
 */
size_t seam_cobs_decode(const uint8_t *src, size_t src_len,
                        uint8_t *dst, size_t dst_size);

#ifdef __cplusplus
}
#endif

#endif /* SEAM_CODEC_H */
