# Firmware

PlatformIO / Arduino firmware for the ESP32-S3 client. It holds no layout logic:
it asks the bridge for the current screen, streams the pre-rendered 4 bpp image
(192000 bytes) to a Waveshare 7.3" e-Paper HAT (F) and goes back to deep sleep.

Display driver: GxEPD2 `GxEPD2_730c_ACeP_730` (800x480, 7 colours, no partial refresh).
Colour indices written by the bridge (0 black, 1 white, 2 green, 3 blue, 4 red,
5 yellow, 6 orange) are already the panel's native values, so no conversion happens on the device.

## Wiring (FireBeetle 2 ESP32-S3)

| Signal | GPIO | Board label | Note |
|---|---|---|---|
| EPD SCK (CLK) | 17 | SCK | board default SPI, fixed by `SPI.begin()` |
| EPD MOSI (DIN) | 15 | MOSI | board default SPI |
| EPD CS | 18 | D6 | |
| EPD DC | 3 | D2 | |
| EPD RST | 38 | D3 | |
| EPD BUSY | 14 | D10 | low = busy |
| EPD VCC / GND | 3V3 / GND | | HAT accepts 3.3 V or 5 V |
| Button A (approve) | 7 | D5 | to GND, internal pull-up |
| Button B (reject) | 9 | D7 | to GND |
| Button C (stop) | 12 | D12 | to GND |
| Battery sense | 4 | A0 | assumed 2:1 divider, see `config.h` |

All pins live in `src/config.h`. Buttons must stay on RTC GPIOs (0 to 21) to wake the chip.
The battery pin and ratio are an assumption and must be checked against the board schematic.

## Build and flash

```sh
python3 -m venv .venv && .venv/bin/pip install platformio
cp src/secrets.example.h src/secrets.h   # then edit BRIDGE_URL and DEVICE_TOKEN
.venv/bin/pio run -e firebeetle2_esp32s3
.venv/bin/pio run -e firebeetle2_esp32s3 -t upload
.venv/bin/pio device monitor
```

`secrets.h` is gitignored. An `https://` bridge URL is accepted but the certificate is not validated.

The `heltec_wifi_lora_32_V3` env is a compile-only placeholder for the Heltec V4 (PlatformIO has no V4 board).
Its pins are not remapped.

## Wi-Fi provisioning

With no stored credentials the device waits 5 minutes for Improv Wi-Fi over USB serial
(ESP Web Tools, or https://www.improv-wifi.com in Chrome or Edge). Credentials are stored in NVS and survive reflashes
of the app partition. There is no SoftAP portal. To forget the network, hold button A for 5 s while powering on or resetting
(not when waking from sleep); the serial log prints `wifi credentials cleared`.
A wrong password for a stored SSID is not detected as such: the device retries
every 5 minutes until you clear the credentials this way, then re-provision.

## Cycle

1. Wake by timer or by a button (ext1, any button pulled low).
2. Connect Wi-Fi. On failure sleep 300 s.
3. If a button woke it, `POST /api/action` with the `screen_id` saved in RTC memory.
4. `GET /api/display?battery=<volts>` with the bearer token.
5. If `image_hash` differs from the saved one, stream `GET <image_url>` in 4000-byte strips (10 rows) to the panel,
   turn Wi-Fi off, refresh (about 35 s) and hibernate the panel.
6. Save hash and `screen_id` in RTC memory, deep sleep for `refresh_rate` (minimum 180 s).

The bridge must send `Content-Length` on the image (no chunked encoding); the device rejects any
other size than 192000 bytes. `/api/display` bodies over 4096 bytes are rejected. `refresh_rate` is clamped to 180..3600 s.

A button press whose Wi-Fi connection failed is kept in RTC memory and sent on the next successful connection.
Buttons the bridge maps to `none` do not post anything and only refresh the display.
Button presses during the ~35 s refresh are lost. No PSRAM is needed.
