/**
 * @file sampler.c
 * @brief Seam sampler — frame dispatch and send helpers.
 */

#include <seam/sampler.h>
#include <string.h>

void seam_sampler_init(seam_sampler_t *sampler, seam_transport_t *transport)
{
    memset(sampler, 0, sizeof(*sampler));
    sampler->transport = transport;
}

int seam_sampler_on_command(seam_sampler_t *sampler,
                            uint8_t command_id,
                            seam_cmd_handler_fn handler)
{
    /* Replace existing entry if command_id already registered */
    for (uint8_t i = 0; i < sampler->handler_count; i++) {
        if (sampler->handlers[i].command_id == command_id) {
            sampler->handlers[i].handler = handler;
            return 0;
        }
    }

    if (sampler->handler_count >= SEAM_MAX_CMD_HANDLERS) {
        return -1;
    }

    sampler->handlers[sampler->handler_count].command_id = command_id;
    sampler->handlers[sampler->handler_count].handler    = handler;
    sampler->handler_count++;
    return 0;
}

int seam_sampler_send(seam_sampler_t *sampler,
                      uint8_t channel_id, uint32_t timestamp_ms,
                      const uint8_t *payload, uint8_t payload_len)
{
    uint8_t out[SEAM_MAX_COBS_FRAME];
    size_t  out_len = seam_encode_data_frame(out, sizeof(out),
                                             channel_id, timestamp_ms,
                                             payload, payload_len);
    if (out_len == 0) {
        return -1;
    }
    return sampler->transport->write(sampler->transport->ctx, out, out_len);
}

int seam_sampler_send_ack(seam_sampler_t *sampler,
                          uint8_t command_id, uint8_t seq)
{
    uint8_t out[SEAM_MAX_COBS_FRAME];
    size_t  out_len = seam_encode_cmd_ack(out, sizeof(out), command_id, seq);
    if (out_len == 0) {
        return -1;
    }
    return sampler->transport->write(sampler->transport->ctx, out, out_len);
}

int seam_sampler_send_nack(seam_sampler_t *sampler,
                           uint8_t command_id, uint8_t seq)
{
    uint8_t out[SEAM_MAX_COBS_FRAME];
    size_t  out_len = seam_encode_cmd_nack(out, sizeof(out), command_id, seq);
    if (out_len == 0) {
        return -1;
    }
    return sampler->transport->write(sampler->transport->ctx, out, out_len);
}

/* ── RX event loop ────────────────────────────────────────────────────── */

/**
 * Try to extract and decode the first complete COBS frame from rx_buf.
 * Returns the decoded length on success, 0 if no complete frame yet.
 */
static size_t try_extract_frame(seam_sampler_t *sampler)
{
    /* Find 0x00 delimiter */
    size_t delim = SIZE_MAX;
    for (size_t i = 0; i < sampler->rx_len; i++) {
        if (sampler->rx_buf[i] == 0x00) {
            delim = i;
            break;
        }
    }
    if (delim == SIZE_MAX) {
        return 0;
    }

    size_t decoded_len = seam_cobs_decode(sampler->rx_buf, delim,
                                          sampler->decoded_buf,
                                          sizeof(sampler->decoded_buf));

    /* Shift remaining bytes to front regardless of decode result */
    size_t remaining = sampler->rx_len - delim - 1;
    if (remaining > 0) {
        memmove(sampler->rx_buf, &sampler->rx_buf[delim + 1], remaining);
    }
    sampler->rx_len = remaining;

    return (decoded_len == SIZE_MAX) ? 0 : decoded_len;
}

void seam_sampler_run(void *arg, void *unused1, void *unused2)
{
    seam_sampler_t *sampler = (seam_sampler_t *)arg;

    (void)unused1;
    (void)unused2;

    for (;;) {
        /* Read more bytes from transport */
        int n = sampler->transport->read(
            sampler->transport->ctx,
            &sampler->rx_buf[sampler->rx_len],
            sizeof(sampler->rx_buf) - sampler->rx_len);

        if (n <= 0) {
            /* Transport error — reset accumulator and retry */
            sampler->rx_len = 0;
            continue;
        }
        sampler->rx_len += (size_t)n;

        /* Process all complete frames in the accumulator */
        size_t decoded_len;
        while ((decoded_len = try_extract_frame(sampler)) > 0) {
            seam_cmd_frame_t cmd;
            if (seam_decode_cmd_frame(sampler->decoded_buf, decoded_len,
                                      &cmd) != 0) {
                /* Not a command frame or malformed — ignore */
                continue;
            }

            /* Dispatch to registered handler */
            for (uint8_t i = 0; i < sampler->handler_count; i++) {
                if (sampler->handlers[i].command_id == cmd.command_id) {
                    sampler->handlers[i].handler(sampler,
                                                 cmd.command_id,
                                                 cmd.args,
                                                 cmd.args_len,
                                                 cmd.seq);
                    break;
                }
            }
        }

        /* Guard against a full buffer with no delimiter — discard and resync */
        if (sampler->rx_len >= sizeof(sampler->rx_buf)) {
            sampler->rx_len = 0;
        }
    }
}
