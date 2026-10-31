# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-10-31

### Added
- **Bridge:** background poll loop with a cached frame, optional KiroCrew WebSocket trigger,
  optional painel-tmux provider, client aligned with the real KiroCrew API schema, and the
  device API (`/api/display`, `/api/image`, `/api/action`, preview and model endpoints).
- **Firmware:** FireBeetle 2 ESP32-S3 with a Waveshare 7.3" (F) panel, deep sleep, three
  buttons, Improv Wi-Fi setup, 16 MB flash layout.
- **Tools:** device simulator that replays the firmware calls and writes a PNG.
- **Docs:** architecture decision record, hardware notes, browser flash page.

### Known limitations
- Not tested on hardware or against a real KiroCrew gateway.
- Approving with `X-Internal-Secret` may be refused by KiroCrew; plan B is `KIROCREW_COOKIE`.
- The release binary ships example secrets; runtime configuration arrives in 0.2.
- The battery voltage reaches the image one refresh cycle late.
