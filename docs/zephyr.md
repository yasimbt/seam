# seam-zephyr

`seam-zephyr` is a C/CMake Zephyr module that implements the Seam wire protocol for the [Zephyr RTOS](https://zephyrproject.org). It provides the same COBS+TLV codec and sampler API as `seam-fw`, but targeting Zephyr's driver model instead of Embassy.

---

## Adding to a Zephyr project

Add `seam-zephyr` as a west module in `west.yml`:

```yaml
manifest:
  projects:
    - name: seam
      url: https://github.com/yasimbt/seam
      path: modules/seam
      revision: main
```

Then run:

```bash
west update
```

---

## Kconfig

Enable in your `prj.conf`:

```ini
CONFIG_SEAM=y

# Choose transport
CONFIG_SEAM_TRANSPORT_USB_CDC=y
# or
CONFIG_SEAM_TRANSPORT_BLE_NUS=y

# Optional tuning
CONFIG_SEAM_MAX_CHANNELS=16
CONFIG_SEAM_MAX_COMMANDS=16
CONFIG_SEAM_MAX_FRAME_PAYLOAD=255
```

---

## Usage

### 1. Initialise transport and sampler

```c
#include <seam/sampler.h>
#include <seam/transport.h>

static seam_sampler_t sampler;
static seam_transport_t transport;

void main(void)
{
    seam_transport_usb_cdc_init(&transport);  /* or ble_nus_init */
    seam_sampler_init(&sampler, &transport);

    /* Register command handlers */
    seam_sampler_on_command(&sampler, CMD_SET_RATE, on_set_rate);

    /* Start RX loop in a dedicated thread (see below) */
}
```

### 2. Send data frames

```c
/* Pack a float32 value little-endian */
float temp = read_temperature();
uint8_t payload[4];
memcpy(payload, &temp, 4);

seam_sampler_send(&sampler,
                  CHANNEL_TEMPERATURE,
                  k_uptime_get_32(),
                  payload, sizeof(payload));
```

For `f32x3` channels:

```c
float accel[3] = { ax, ay, az };
seam_sampler_send(&sampler,
                  CHANNEL_ACCEL,
                  k_uptime_get_32(),
                  (uint8_t *)accel, sizeof(accel));
```

### 3. Handle commands

```c
static void on_set_rate(seam_sampler_t *sampler,
                        uint8_t command_id,
                        const uint8_t *args, uint8_t args_len,
                        uint8_t seq)
{
    if (args_len < 3) {
        seam_sampler_send_nack(sampler, command_id, seq);
        return;
    }
    uint8_t  channel_id = args[0];
    uint16_t rate_hz;
    memcpy(&rate_hz, &args[1], 2);   /* little-endian */

    if (set_channel_rate(channel_id, rate_hz) == 0) {
        seam_sampler_send_ack(sampler, command_id, seq);
    } else {
        seam_sampler_send_nack(sampler, command_id, seq);
    }
}
```

### 4. Start the RX thread

```c
K_THREAD_DEFINE(seam_rx_tid,
                1024,
                seam_sampler_run,
                &sampler, NULL, NULL,
                5, 0, 0);
```

`seam_sampler_run` matches the Zephyr thread entry signature `(void*, void*, void*)` and never returns.

---

## API reference

### `seam_sampler_init`

```c
void seam_sampler_init(seam_sampler_t *sampler, seam_transport_t *transport);
```

### `seam_sampler_on_command`

```c
int seam_sampler_on_command(seam_sampler_t *sampler,
                            uint8_t command_id,
                            seam_cmd_handler_fn handler);
```

Returns `0` on success, `-1` if the handler table is full (`CONFIG_SEAM_MAX_COMMANDS`).

### `seam_sampler_send`

```c
int seam_sampler_send(seam_sampler_t *sampler,
                      uint8_t channel_id, uint32_t timestamp_ms,
                      const uint8_t *payload, uint8_t payload_len);
```

Returns `0` on success, negative errno on transport error.

### `seam_sampler_send_ack` / `seam_sampler_send_nack`

```c
int seam_sampler_send_ack(seam_sampler_t *sampler, uint8_t command_id, uint8_t seq);
int seam_sampler_send_nack(seam_sampler_t *sampler, uint8_t command_id, uint8_t seq);
```

### `seam_sampler_run`

```c
void seam_sampler_run(void *sampler, void *unused1, void *unused2);
```

Zephyr-compatible thread entry. Reads COBS frames, decodes them, dispatches registered command handlers. Does not return.

---

## Codec functions

Lower-level functions for custom integrations:

```c
#include <seam/codec.h>

/* Encode a data frame (COBS-framed, ready to write to transport) */
size_t seam_encode_data_frame(uint8_t *out, size_t out_size,
                              uint8_t channel_id, uint32_t timestamp_ms,
                              const uint8_t *payload, uint8_t payload_len);

/* Encode ACK / NACK */
size_t seam_encode_cmd_ack(uint8_t *out, size_t out_size, uint8_t command_id, uint8_t seq);
size_t seam_encode_cmd_nack(uint8_t *out, size_t out_size, uint8_t command_id, uint8_t seq);

/* Decode a raw (post-COBS) command frame */
int seam_decode_cmd_frame(const uint8_t *raw, size_t raw_len, seam_cmd_frame_t *out);

/* Raw COBS encode/decode */
size_t seam_cobs_encode(const uint8_t *src, size_t src_len, uint8_t *dst, size_t dst_size);
size_t seam_cobs_decode(const uint8_t *src, size_t src_len, uint8_t *dst, size_t dst_size);
```

All encode functions return the number of bytes written (including the COBS `0x00` sentinel), or `0` on error. `seam_cobs_decode` returns the decoded byte count, or `SIZE_MAX` on error.
