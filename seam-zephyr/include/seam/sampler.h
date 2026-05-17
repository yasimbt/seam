/**
 * @file sampler.h
 * @brief Seam sampler — high-level send/receive API.
 *
 * The sampler wraps a transport and provides:
 *   - seam_sampler_send()    — encode and transmit a data frame
 *   - seam_sampler_run()     — event loop: receive command frames, dispatch handlers
 *   - seam_sampler_send_ack() / send_nack() — respond to commands
 *
 * Usage:
 *   1. Initialise a transport (e.g. seam_transport_usb_cdc_init()).
 *   2. Call seam_sampler_init().
 *   3. Register command handlers with seam_sampler_on_command().
 *   4. Call seam_sampler_run() from a dedicated Zephyr thread — it never returns.
 *   5. From sensor threads call seam_sampler_send().
 */

#ifndef SEAM_SAMPLER_H
#define SEAM_SAMPLER_H

#include <seam/codec.h>
#include <seam/transport.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Maximum number of command handlers that can be registered. */
#ifndef SEAM_MAX_CMD_HANDLERS
#define SEAM_MAX_CMD_HANDLERS CONFIG_SEAM_MAX_COMMANDS
#endif

/**
 * @brief Command handler callback.
 *
 * @param sampler    Pointer to the sampler (use seam_sampler_send_ack/nack).
 * @param command_id Received command identifier.
 * @param args       Argument bytes (little-endian, per seam.toml arg types).
 * @param args_len   Number of argument bytes.
 * @param seq        Sequence byte — must be echoed in ACK/NACK.
 */
struct seam_sampler;
typedef void (*seam_cmd_handler_fn)(struct seam_sampler *sampler,
                                    uint8_t command_id,
                                    const uint8_t *args, uint8_t args_len,
                                    uint8_t seq);

/** Registered command handler entry. */
typedef struct {
    uint8_t            command_id;
    seam_cmd_handler_fn handler;
} seam_cmd_entry_t;

/** Seam sampler state. */
typedef struct seam_sampler {
    seam_transport_t  *transport;
    seam_cmd_entry_t   handlers[SEAM_MAX_CMD_HANDLERS];
    uint8_t            handler_count;
    /* Internal RX accumulator for COBS frame reassembly */
    uint8_t            rx_buf[SEAM_MAX_COBS_FRAME];
    size_t             rx_len;
    uint8_t            decoded_buf[SEAM_MAX_RAW_FRAME];
} seam_sampler_t;

/**
 * @brief Initialise a sampler with the given transport.
 *
 * @param sampler    Sampler to initialise.
 * @param transport  Configured transport.
 */
void seam_sampler_init(seam_sampler_t *sampler, seam_transport_t *transport);

/**
 * @brief Register a handler for a specific command id.
 *
 * At most SEAM_MAX_CMD_HANDLERS handlers can be registered. Registering the
 * same command_id twice replaces the previous handler.
 *
 * @param sampler    Sampler instance.
 * @param command_id Command identifier (matches seam.toml `id`).
 * @param handler    Callback to invoke when this command is received.
 * @return 0 on success, -1 if the handler table is full.
 */
int seam_sampler_on_command(seam_sampler_t *sampler,
                            uint8_t command_id,
                            seam_cmd_handler_fn handler);

/**
 * @brief Encode and transmit a data frame.
 *
 * Thread-safe if the underlying transport write is thread-safe.
 *
 * @param sampler      Sampler instance.
 * @param channel_id   Channel identifier.
 * @param timestamp_ms Milliseconds since device boot.
 * @param payload      Payload bytes.
 * @param payload_len  Number of payload bytes.
 * @return 0 on success, negative errno on error.
 */
int seam_sampler_send(seam_sampler_t *sampler,
                      uint8_t channel_id, uint32_t timestamp_ms,
                      const uint8_t *payload, uint8_t payload_len);

/**
 * @brief Send a command ACK.
 *
 * @param sampler    Sampler instance.
 * @param command_id Command being acknowledged.
 * @param seq        Sequence byte from the received command.
 * @return 0 on success, negative errno on error.
 */
int seam_sampler_send_ack(seam_sampler_t *sampler,
                          uint8_t command_id, uint8_t seq);

/**
 * @brief Send a command NACK.
 *
 * @param sampler    Sampler instance.
 * @param command_id Command being rejected.
 * @param seq        Sequence byte from the received command.
 * @return 0 on success, negative errno on error.
 */
int seam_sampler_send_nack(seam_sampler_t *sampler,
                           uint8_t command_id, uint8_t seq);

/**
 * @brief Command receive/dispatch loop.
 *
 * Reads COBS frames from the transport, decodes them, and dispatches to
 * registered command handlers. Does not return.
 *
 * Run this from a dedicated Zephyr thread:
 *   K_THREAD_DEFINE(seam_rx_tid, 1024, seam_sampler_run, &sampler, NULL, NULL, 5, 0, 0);
 *
 * @param sampler Sampler instance (cast to void* for K_THREAD_DEFINE compatibility).
 */
void seam_sampler_run(void *sampler, void *unused1, void *unused2);

#ifdef __cplusplus
}
#endif

#endif /* SEAM_SAMPLER_H */
