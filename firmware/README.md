# Firmware

PlatformIO / Arduino firmware for the ESP32-S3 client. It holds no layout logic:
it asks the bridge for the current screen, streams the pre-rendered 4 bpp image
(192000 bytes) to a Waveshare 7.3" e-Paper HAT (F) and goes back to deep sleep.

Display driver: GxEPD2 `GxEPD2_730c_ACeP_730` (800x480, 7 colours, no partial refresh).
Colour indices written by the bridge (0 black, 1 white, 2 green, 3 blue, 4 red,
5 yellow, 6 orange) are already the panel's native values, so no conversion happens on the device.

## Wiring

Primary target: Heltec WiFi LoRa 32 V4 (env `heltec_v4`, or `heltec_v4r8` for the 8 MB PSRAM variant).
Pins come from `-D` flags in `platformio.ini`; `src/config.h` holds the defaults (FireBeetle 2 ESP32-S3).

| Signal | Heltec V4 GPIO | V4R8 GPIO | FireBeetle S3 (generic example) |
|---|---|---|---|
| EPD SCK (CLK) | 39 | 39 | 17 |
| EPD MOSI (DIN) | 40 | 47 (not confirmed on header) | 15 |
| EPD CS | 41 | 41 | 18 |
| EPD DC | 42 | 42 | 3 |
| EPD RST | 38 | 38 | 38 |
| EPD BUSY (low = busy) | 34 | 34 | 14 |
| HAT supply (Vext) | 36 | 40 | always on (3V3) |
| Button A (approve) | 4 | 4 | 7 |
| Button B (reject) | 6 | 6 | 9 |
| Button C (stop) | 3, no wake | 3, no wake | 12 |
| Battery ADC | 1 (+ ADC_Ctrl 37) | same | 4 (assumed 2:1) |

Notes for the Heltec:
- Vext is driven on before the panel is used and held off during deep sleep. The datasheet says HIGH is on,
  espboards.dev says LOW. Sources disagree: test on the bench and change `VEXT_ON_LEVEL`.
- Battery: GPIO37 is driven HIGH, 10 ms later GPIO1 is read, then GPIO37 goes low. Vbat = Vadc x 4.9.
- Only buttons A and B wake the chip from deep sleep. Button C (GPIO3, a strapping pin) is not an
  ext1 source in this layout, so it only works while the chip is awake.
- The OLED and the LoRa radio are never initialised. OLED_RST (21), FEM_EN (2) and VFEM (7) are held LOW,
  also in deep sleep (pin numbers from the research notes; FEM polarity not confirmed). Before Vext is cut,
  the HAT signal pins go high-Z so the HAT is not back-powered, and ADC_Ctrl is held LOW.
- The V4R8 keeps PSRAM disabled (the firmware does not use it). If its PSRAM is octal, GPIO33-37 may be taken
  and BUSY 34 / ADC_Ctrl 37 would clash. Not verified.
- The SPI bus is started with explicit pins before the panel init; CS is driven by GxEPD2.

Buttons go to GND (internal pull-up). Wake needs RTC GPIOs (0 to 21).

## Build and flash

```sh
python3 -m venv .venv && .venv/bin/pip install platformio
cp src/secrets.example.h src/secrets.h   # then edit BRIDGE_URL and DEVICE_TOKEN
.venv/bin/pio run -e heltec_v4
.venv/bin/pio run -e heltec_v4 -t upload
.venv/bin/pio device monitor
```

`secrets.h` is gitignored. An `https://` bridge URL is accepted but the certificate is not validated.

The `firebeetle2_esp32s3` env is a generic ESP32-S3 example with the `config.h` default pins.

## Flash pelo navegador

`tools/merge_bin.sh` copies the merged image to `dist/crewmate-heltec-v4.bin` (offset 0, 16 MB layout, argument: env and output name).
CI does this on every run and, on a `v*` tag, stages it in `docs/flash/firmware/` next to `manifest.json`.
The page in `../docs/flash` uses ESP Web Tools: it needs Chrome or Edge (Web Serial) and HTTPS or localhost.
For a local test, copy the image into `docs/flash/firmware/` and run `python3 -m http.server` inside `docs/flash`.

> The release binary is built with `secrets.example.h` (example bridge URL and token). In v0.1 anyone using web flash must build their own binary with their own secrets; runtime configuration is planned for v0.2. The page also needs the `.bin` copied to `docs/flash/firmware/` (it comes from the CI artifact on a tag), otherwise it returns 404.

## Wi-Fi provisioning

With no stored credentials the device waits 5 minutes for Improv Wi-Fi over USB serial
(ESP Web Tools, or https://www.improv-wifi.com in Chrome or Edge). Credentials are stored in NVS and survive reflashes
of the app partition. There is no SoftAP portal. To forget the network, hold button A for 5 s while powering on or resetting
(not when waking from sleep by timer or button); the serial log prints `wifi credentials cleared`.
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
