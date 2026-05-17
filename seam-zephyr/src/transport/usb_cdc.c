/**
 * @file usb_cdc.c
 * @brief Seam USB CDC-ACM transport for Zephyr.
 *
 * Wraps Zephyr's USB CDC-ACM UART device. The sampler layer handles COBS
 * framing; this transport provides raw byte read/write over /dev/ttyACM0
 * (or equivalent).
 *
 * Requires CONFIG_SEAM_TRANSPORT_USB_CDC=y and CONFIG_USB_CDC_ACM=y.
 */

#include <seam/transport.h>

#ifdef CONFIG_SEAM_TRANSPORT_USB_CDC

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/usb/usb_device.h>
#include <string.h>

/** USB CDC-ACM transport context */
typedef struct {
    const struct device *uart_dev;
} usb_cdc_ctx_t;

static usb_cdc_ctx_t usb_cdc_ctx;

static int usb_cdc_write(seam_transport_ctx_t *ctx,
                         const uint8_t *data, size_t len)
{
    usb_cdc_ctx_t *c = (usb_cdc_ctx_t *)ctx;
    for (size_t i = 0; i < len; i++) {
        uart_poll_out(c->uart_dev, data[i]);
    }
    return 0;
}

static int usb_cdc_read(seam_transport_ctx_t *ctx,
                        uint8_t *buf, size_t max_len)
{
    usb_cdc_ctx_t *c = (usb_cdc_ctx_t *)ctx;
    size_t read = 0;

    /* Block until at least one byte is available */
    while (read == 0) {
        while (read < max_len) {
            int rc = uart_poll_in(c->uart_dev, &buf[read]);
            if (rc < 0) {
                break;  /* No more bytes available right now */
            }
            read++;
        }
    }
    return (int)read;
}

int seam_transport_usb_cdc_init(seam_transport_t *transport)
{
    const struct device *dev = DEVICE_DT_GET_ONE(zephyr_cdc_acm_uart);
    if (!device_is_ready(dev)) {
        return -ENODEV;
    }

    int rc = usb_enable(NULL);
    if (rc != 0 && rc != -EALREADY) {
        return rc;
    }

    usb_cdc_ctx.uart_dev = dev;

    transport->write = usb_cdc_write;
    transport->read  = usb_cdc_read;
    transport->ctx   = (seam_transport_ctx_t *)&usb_cdc_ctx;

    return 0;
}

#endif /* CONFIG_SEAM_TRANSPORT_USB_CDC */
