/**
 * @file codec.c
 * @brief Seam COBS+TLV codec implementation.
 *
 * Implements standard COBS (no custom variant) matching the wire protocol
 * in seam-fw/src/codec.rs and seam-py/seam/codec.py exactly.
 */

#include <seam/codec.h>
#include <string.h>

/* ── COBS ─────────────────────────────────────────────────────────────── */

size_t seam_cobs_encode(const uint8_t *src, size_t src_len,
                        uint8_t *dst, size_t dst_size)
{
    if (src == NULL || dst == NULL) {
        return 0;
    }

    /* Conservative upper bound: src_len + ceil(src_len/254) + 2 */
    size_t max_out = src_len + (src_len / 254) + 2;
    if (dst_size < max_out) {
        return 0;
    }

    size_t read_idx  = 0;
    size_t write_idx = 0;
    size_t code_idx  = write_idx++;  /* reserve first byte for code */
    uint8_t code     = 1;

    while (read_idx < src_len) {
        if (src[read_idx] == 0x00) {
            dst[code_idx] = code;
            code_idx  = write_idx++;
            code      = 1;
        } else {
            dst[write_idx++] = src[read_idx];
            ++code;
            if (code == 0xFF) {
                dst[code_idx] = code;
                code_idx  = write_idx++;
                code      = 1;
            }
        }
        ++read_idx;
    }

    dst[code_idx] = code;
    dst[write_idx++] = 0x00;  /* sentinel */
    return write_idx;
}

size_t seam_cobs_decode(const uint8_t *src, size_t src_len,
                        uint8_t *dst, size_t dst_size)
{
    if (src == NULL || dst == NULL || src_len == 0) {
        return SIZE_MAX;
    }

    size_t read_idx  = 0;
    size_t write_idx = 0;

    while (read_idx < src_len) {
        uint8_t code = src[read_idx++];
        if (code == 0x00) {
            return SIZE_MAX;  /* 0x00 inside COBS stream is malformed */
        }

        for (uint8_t i = 1; i < code; i++) {
            if (read_idx >= src_len) {
                return SIZE_MAX;
            }
            if (write_idx >= dst_size) {
                return SIZE_MAX;
            }
            dst[write_idx++] = src[read_idx++];
        }

        if (code < 0xFF && read_idx < src_len) {
            if (write_idx >= dst_size) {
                return SIZE_MAX;
            }
            dst[write_idx++] = 0x00;
        }
    }

    return write_idx;
}

/* ── Frame encoding helpers ───────────────────────────────────────────── */

static size_t encode_response(uint8_t *out, size_t out_size,
                               uint8_t type, uint8_t command_id, uint8_t seq)
{
    /* Raw layout: type(1) + command_id(1) + seq(1) + length(1) = 4 bytes */
    uint8_t raw[4];
    raw[0] = type;
    raw[1] = command_id;
    raw[2] = seq;
    raw[3] = 0x00;  /* length = 0 */
    return seam_cobs_encode(raw, sizeof(raw), out, out_size);
}

size_t seam_encode_data_frame(uint8_t *out, size_t out_size,
                              uint8_t channel_id, uint32_t timestamp_ms,
                              const uint8_t *payload, uint8_t payload_len)
{
    if (out == NULL || (payload == NULL && payload_len > 0)) {
        return 0;
    }

    /* Raw layout: type(1) + channel(1) + ts(4 LE) + length(1) + payload */
    size_t raw_len = 7u + payload_len;
    uint8_t raw[SEAM_DATA_FRAME_HEADER_LEN + SEAM_MAX_PAYLOAD];
    if (raw_len > sizeof(raw)) {
        return 0;
    }

    raw[0] = SEAM_FRAME_DATA;
    raw[1] = channel_id;
    raw[2] = (uint8_t)(timestamp_ms & 0xFFu);
    raw[3] = (uint8_t)((timestamp_ms >> 8) & 0xFFu);
    raw[4] = (uint8_t)((timestamp_ms >> 16) & 0xFFu);
    raw[5] = (uint8_t)((timestamp_ms >> 24) & 0xFFu);
    raw[6] = payload_len;
    if (payload_len > 0) {
        memcpy(&raw[7], payload, payload_len);
    }

    return seam_cobs_encode(raw, raw_len, out, out_size);
}

size_t seam_encode_cmd_ack(uint8_t *out, size_t out_size,
                           uint8_t command_id, uint8_t seq)
{
    return encode_response(out, out_size, SEAM_FRAME_ACK, command_id, seq);
}

size_t seam_encode_cmd_nack(uint8_t *out, size_t out_size,
                            uint8_t command_id, uint8_t seq)
{
    return encode_response(out, out_size, SEAM_FRAME_NACK, command_id, seq);
}

/* ── Command frame decode ─────────────────────────────────────────────── */

int seam_decode_cmd_frame(const uint8_t *raw, size_t raw_len,
                          seam_cmd_frame_t *out)
{
    if (raw == NULL || out == NULL) {
        return -1;
    }
    if (raw_len < SEAM_CMD_FRAME_HEADER_LEN) {
        return -1;
    }
    if (raw[0] != SEAM_FRAME_CMD) {
        return -1;
    }

    out->command_id = raw[1];
    out->seq        = raw[2];
    out->args_len   = raw[3];

    size_t args_end = 4u + out->args_len;
    if (args_end > raw_len) {
        out->args_len = (uint8_t)(raw_len - 4u);
    }
    out->args = (out->args_len > 0) ? &raw[4] : NULL;

    return 0;
}
