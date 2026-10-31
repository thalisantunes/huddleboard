"""Render the README screenshots from the bundled fixtures with a fixed clock.

Run from anywhere: bridge/.venv/bin/python bridge/tools/make_screenshots.py
"""
import json
from pathlib import Path

from huddleboard.kirocrew import FIXTURE_DIR
from huddleboard.model import build_screen
from huddleboard.render import render

OUT = Path(__file__).resolve().parents[2] / "docs" / "images"


def _load(name):
    return json.loads((FIXTURE_DIR / name).read_text())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = {"status": _load("status.json"), "slots": _load("slots.json"), "approvals": _load("approvals.json"),
           "tasks_summary": _load("tasks_summary.json"), "usage": _load("usage.json")}
    idle = {**raw, "approvals": [], "tasks_summary": {},
            "slots": [{"key": k, "title": t} for k, t in (("main", "Refactor billing API"), ("scratch", "Scratch notes"))]}
    shots = {"board-attention": (raw, "dark"), "board-idle": (idle, "dark"), "board-light": (raw, "light")}
    for name, (data, theme) in shots.items():
        screen = build_screen(data, "09:41", 3.87, 180 if data["approvals"] else 300)
        render(screen, theme).convert("RGB").save(OUT / f"{name}.png")
        print("wrote", OUT / f"{name}.png")


if __name__ == "__main__":
    main()
