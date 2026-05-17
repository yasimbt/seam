/**
 * @file ble_nus.c
 * @brief Seam BLE Nordic UART Service (NUS) transport for Zephyr.
 *
 * Wraps the Zephyr BT NUS service. The sampler layer handles COBS framing;
 * this transport shuttles raw bytes over BLE NUS notifications/writes.
 *
 * Requires CONFIG_SEAM_TRANSPORT_BLE_NUS=y, CONFIG_BT=y, CONFIG_BT_NUS=y.
 */

#include <seam/transport.h>

#ifdef CONFIG_SEAM_TRANSPORT_BLE_NUS

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <bluetooth/services/nus.h>
#include <zephyr/kernel.h>
#include <string.h>

#define BLE_NUS_RX_RING_BUF_SIZE 512

/** BLE NUS transport context */
typedef struct {
    struct bt_conn *conn;
    /* Simple ring buffer for received bytes */
    uint8_t    ring_buf[BLE_NUS_RX_RING_BUF_SIZE];
    uint16_t   ring_head;
    uint16_t   ring_tail;
    struct k_sem rx_sem;
} ble_nus_ctx_t;

static ble_nus_ctx_t ble_nus_ctx;

static inline uint16_t ring_next(uint16_t idx)
{
    return (idx + 1u) % BLE_NUS_RX_RING_BUF_SIZE;
}

static void ring_push(ble_nus_ctx_t *c, const uint8_t *data, uint16_t len)
{
    for (uint16_t i = 0; i < len; i++) {
        uint16_t next = ring_next(c->ring_tail);
        if (next != c->ring_head) {  /* not full */
            c->ring_buf[c->ring_tail] = data[i];
            c->ring_tail = next;
        }
        /* Drop bytes silently on overflow — host will resync on next 0x00 */
    }
    k_sem_give(&c->rx_sem);
}

static uint8_t ring_pop(ble_nus_ctx_t *c)
{
    uint8_t b = c->ring_buf[c->ring_head];
    c->ring_head = ring_next(c->ring_head);
    return b;
}

static bool ring_empty(const ble_nus_ctx_t *c)
{
    return c->ring_head == c->ring_tail;
}

/* ── BT NUS callbacks ──────────────────────────────────────────────── */

static void nus_received(struct bt_conn *conn,
                         const uint8_t *data, uint16_t len)
{
    (void)conn;
    ring_push(&ble_nus_ctx, data, len);
}

static void nus_sent(struct bt_conn *conn)
{
    (void)conn;
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err == 0) {
        ble_nus_ctx.conn = bt_conn_ref(conn);
    }
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    (void)reason;
    if (ble_nus_ctx.conn == conn) {
        bt_conn_unref(ble_nus_ctx.conn);
        ble_nus_ctx.conn = NULL;
    }
}

static struct bt_nus_cb nus_cb = {
    .received = nus_received,
    .sent     = nus_sent,
};

BT_CONN_CB_DEFINE(conn_callbacks) = {
    .connected    = connected,
    .disconnected = disconnected,
};

/* ── Transport vtable ─────────────────────────────────────────────── */

static int ble_nus_write(seam_transport_ctx_t *ctx,
                         const uint8_t *data, size_t len)
{
    ble_nus_ctx_t *c = (ble_nus_ctx_t *)ctx;
    if (c->conn == NULL) {
        return -ENOTCONN;
    }
    /* NUS send splits at MTU automatically in the SDK */
    return bt_nus_send(c->conn, data, (uint16_t)len);
}

static int ble_nus_read(seam_transport_ctx_t *ctx,
                        uint8_t *buf, size_t max_len)
{
    ble_nus_ctx_t *c = (ble_nus_ctx_t *)ctx;

    /* Block until at least one byte is in the ring buffer */
    k_sem_take(&c->rx_sem, K_FOREVER);

    size_t read = 0;
    while (read < max_len && !ring_empty(c)) {
        buf[read++] = ring_pop(c);
    }
    return (int)read;
}

int seam_transport_ble_nus_init(seam_transport_t *transport)
{
    memset(&ble_nus_ctx, 0, sizeof(ble_nus_ctx));
    k_sem_init(&ble_nus_ctx.rx_sem, 0, 1);

    int rc = bt_enable(NULL);
    if (rc != 0 && rc != -EALREADY) {
        return rc;
    }

    rc = bt_nus_init(&nus_cb);
    if (rc != 0) {
        return rc;
    }

    transport->write = ble_nus_write;
    transport->read  = ble_nus_read;
    transport->ctx   = (seam_transport_ctx_t *)&ble_nus_ctx;

    return 0;
}

#endif /* CONFIG_SEAM_TRANSPORT_BLE_NUS */
