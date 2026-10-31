# huddleboard

*an ambient status board for your AI agents — e-paper desk gadget today, Android TV next. Works with Kiro Crew and Kiro.*

A desk e-paper gadget that monitors and controls a [KiroCrew](https://github.com/kirodotdev/KiroCrew) instance:
pending approvals, agent slots, task counts and usage on a 7.3" 7-color screen, with three
physical buttons to approve, reject or stop.

## Architecture

```
 KiroCrew REST  <--  bridge (Python, aiohttp + Pillow)  <--  ESP32-S3 + e-paper
 /api/status         aggregates, renders 800x480 7-color     wakes, GET /api/display,
 /api/approvals      frame, serves packed 4bpp bytes         streams .bin to the panel,
 /api/chat/slots     POST /api/action <- buttons             deep sleep
```

The firmware never parses business JSON nor renders text; the bridge does both.
See [docs/adr/001-architecture.md](docs/adr/001-architecture.md).

## Bridge quickstart

```sh
cd bridge
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
FIXTURES=1 DEVICE_TOKENS=dev python -m huddleboard   # http://127.0.0.1:5480/preview.png
```

Configuration and KiroCrew auth notes: [bridge/README.md](bridge/README.md).

## Try it without hardware

```sh
cd bridge && FIXTURES=1 DEVICE_TOKENS=dev .venv/bin/python -m huddleboard &   # terminal 1
bridge/.venv/bin/python tools/device_sim.py --out frame.png               # one firmware cycle
bridge/.venv/bin/python tools/device_sim.py --press A --out frame.png     # press button A first
```

`tools/device_sim.py` makes the same calls as the firmware (state in `tools/.device_state.json`); `--loop` repeats every `refresh_rate`.

## Firmware

See [firmware/](firmware/). Hardware assembly and BOM: [docs/hardware/assembly.md](docs/hardware/assembly.md).

## Device buttons

`GET /api/display` returns `"buttons": {"A": "approve", "B": "reject", "C": "stop"}`.
A button with no action on the current screen is `"none"`; firmware must ignore it.

## Roadmap

- 0.2: runtime configuration (portal or custom Improv) and testing on real hardware.
- Heltec V4 support and the 7.3" (E) Spectra 6 panel.
- OTA firmware updates.
- 3D-printed case.
- Native KiroCrew integration: compact endpoint and approval event.
- Android TV / Google TV app showing the same rendered board.

## License

MIT

## Trademarks

Kiro and Kiro Crew are trademarks of Amazon.com, Inc. or its affiliates. huddleboard is an
independent community project, not affiliated with or endorsed by Amazon or the Kiro team.
