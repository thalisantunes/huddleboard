# ADR 001: Architecture

## Decisions

1. **TRMNL-like architecture.** A `bridge` service (Python 3.11+, aiohttp, Pillow) runs near
   KiroCrew, aggregates its REST/WS APIs, renders 800x480 in 7 colors and serves ready bytes.
   The firmware does not parse business JSON or render text. Reasons: the KiroCrew token has a
   20h cap and a pinned IP, there is no compact endpoint, the firmware stays trivial, and the
   layout evolves without reflashing.
2. **Hardware:** DFRobot FireBeetle 2 ESP32-S3 (N16R8). Alternative: Heltec WiFi LoRa 32 V4.
3. **Screen:** Waveshare 7.3" (F) ACeP. No partial refresh; a refresh takes ~35s; minimum
   interval 180s, default 300s, 180s while an approval is pending. Fixed 7-color palette, no
   dithering.
4. **Firmware:** PlatformIO Arduino, GxEPD2, deep sleep, buttons wake via ext1, Improv Wi-Fi and
   ESP Web Tools for browser flashing.
5. **License:** MIT. Independent open-source project, not tied to a KiroCrew fork or theme.

## Device contract (v0)

Auth: `Authorization: Bearer <device_token>`.

- `GET /api/display` returns image URL, hash, refresh rate, `screen_id`, button map.
- `GET /api/image/<hash>.bin` returns 192000 bytes: 800x480, 4bpp, high nibble is the left
  pixel. Indices: 0 black, 1 white, 2 green, 3 blue, 4 red, 5 yellow, 6 orange.
- `POST /api/action` with `{screen_id, button}`; the bridge resolves the action from what was
  on screen, never from the raw button.
