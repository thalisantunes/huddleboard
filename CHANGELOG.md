# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Renamed to huddleboard (Python package and distribution `huddleboard`).

## [0.1.1] - 2026-10-31

### Added
- Live preview web page at `/` (image, status line, A/B/C buttons that post the current action).
- `TRUSTED_PROXY_CIDR`: trust an authenticating proxy such as Cloudflare Access for the web page
  and its endpoints; devices keep using Bearer tokens.
- Owner token minted from the local gateway endpoint and sent as a session cookie, which unlocks
  status, approvals, tasks and usage.
- `INPUT_RECENT_MINUTES` (default 30): only slots waiting for input within that window raise the
  `INPUT: N` badge and the urgent 180 s refresh; older ones stay listed.

### Changed
- KiroCrew schema validated against a production gateway; the usage footer now shows credits,
  plan, percentage, cost, reset date and messages today.
- Slots show their title (key tail as fallback), are ordered by priority (approval, input, running,
  compacting, idle) and show a task line from the last prompt or message. Stop (button C) targets
  only slots that are actually working.
- Heltec V4 is now the primary hardware target.

### Fixed
- Credentials (internal secret, cookies, owner token) are never written to logs.

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
