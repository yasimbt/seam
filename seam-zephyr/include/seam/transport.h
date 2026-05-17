/**
 * @file transport.h
 * @brief Seam transport interface.
 *
 * A transport provides byte-stream I/O between the Seam sampler and the host.
 * All COBS framing is handled by the codec layer; the transport sees raw bytes.
 *
 * Implementations must fill a seam_transport_t with function pointers and pass
 * it to seam_sampler_init().
 */

#ifndef SEAM_TRANSPORT_H
#define SEAM_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Opaque transport context pointer — cast to implementation-specific struct. */
typedef void seam_transport_ctx_t;

/**
 * @brief Write bytes to the host.
 *
 * Must block (or return an error) until all @p len bytes are sent.
 *
 * @param ctx  Transport context.
 * @param data Bytes to send.
 * @param len  Number of bytes.
 * @return 0 on success, negative errno on error.
 */
typedef int (*seam_transport_write_fn)(seam_transport_ctx_t *ctx,
                                      const uint8_t *data, size_t len);

/**
 * @brief Read bytes from the host into @p buf.
 *
 * Blocks until at least one byte is available. Returns the number of bytes
 * actually read (may be less than @p max_len).
 *
 * @param ctx     Transport context.
 * @param buf     Destination buffer.
 * @param max_len Size of @p buf.
 * @return Number of bytes read (>0), or negative errno on error.
 */
typedef int (*seam_transport_read_fn)(seam_transport_ctx_t *ctx,
                                     uint8_t *buf, size_t max_len);

/** Seam transport vtable + context. */
typedef struct {
    seam_transport_write_fn write;
    seam_transport_read_fn  read;
    seam_transport_ctx_t   *ctx;
} seam_transport_t;

#ifdef SEAM_TRANSPORT_USB_CDC
/**
 * @brief Initialise the USB CDC-ACM transport.
 *
 * @param transport  Transport struct to populate.
 * @return 0 on success, negative errno on error.
 */
int seam_transport_usb_cdc_init(seam_transport_t *transport);
#endif

#ifdef SEAM_TRANSPORT_BLE_NUS
/**
 * @brief Initialise the BLE NUS transport.
 *
 * @param transport  Transport struct to populate.
 * @return 0 on success, negative errno on error.
 */
int seam_transport_ble_nus_init(seam_transport_t *transport);
#endif

#ifdef __cplusplus
}
#endif

#endif /* SEAM_TRANSPORT_H */
