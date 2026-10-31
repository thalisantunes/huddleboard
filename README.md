# kiro-crew-deck

A desk e-paper gadget that monitors and controls a [KiroCrew](https://github.com/) instance:
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
FIXTURES=1 DEVICE_TOKENS=dev python -m kcdeck   # http://127.0.0.1:5480/preview.png
```

Configuration is via environment variables, see `bridge/kcdeck/config.py`.

## Try it without hardware

```sh
cd bridge && FIXTURES=1 DEVICE_TOKENS=dev .venv/bin/python -m kcdeck &   # terminal 1
bridge/.venv/bin/python tools/device_sim.py --out frame.png               # one firmware cycle
bridge/.venv/bin/python tools/device_sim.py --press A --out frame.png     # press button A first
```

`tools/device_sim.py` makes the same calls as the firmware (state in `tools/.device_state.json`); `--loop` repeats every `refresh_rate`.

## Firmware

See [firmware/](firmware/). Hardware assembly and BOM: [docs/hardware/assembly.md](docs/hardware/assembly.md).

## License

MIT

## Device buttons

`GET /api/display` returns `"buttons": {"A": "approve", "B": "reject", "C": "stop"}`.
A button with no action on the current screen is `"none"`; firmware must ignore it.
