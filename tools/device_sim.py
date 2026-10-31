#!/usr/bin/env python3
"""Simulates the e-paper firmware against a bridge: same calls, writes a PNG."""
import argparse, json, sys, time, urllib.error, urllib.request
from pathlib import Path
from PIL import Image

W, H = 800, 480
IMG_BYTES = W * H // 2
# Waveshare 7.3F indices: black, white, green, blue, red, yellow, orange
PALETTE = [(0, 0, 0), (255, 255, 255), (0, 128, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0), (255, 128, 0)]
STATE = Path(__file__).with_name(".device_state.json")


def call(args, path, body=None):
    req = urllib.request.Request(args.bridge.rstrip("/") + path, headers={"Authorization": f"Bearer {args.token}"})
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=15)


def unpack(data, out):
    px = bytearray()
    for b in data:
        px += bytes((b >> 4, b & 0x0F))
    if max(px) > 6:
        sys.exit("image has nibbles outside 0..6")
    img = Image.frombytes("P", (W, H), bytes(px))
    img.putpalette([c for rgb in PALETTE for c in rgb])
    img.convert("RGB").save(out)


def cycle(args):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.press:
        if state.get("screen_id") and state.get("buttons", {}).get(args.press) != "none":
            state["pending"] = {"screen_id": state["screen_id"], "button": args.press}
        else:
            print(f"button {args.press}: no screen_id or action is 'none', not posting")
    pending = state.get("pending")
    if pending:
        try:
            r = call(args, "/api/action", pending)
            print(f"action {pending['button']} -> {r.status} {r.read().decode()}")
            state.pop("pending")
        except urllib.error.HTTPError as e:  # bridge answered: drop it, like the firmware
            print(f"action {pending['button']} -> {e.code} {e.read().decode()}")
            state.pop("pending")
        except OSError as e:  # network error: keep it for the next cycle
            print(f"action {pending['button']} failed ({e}), kept pending")
    doc = json.load(call(args, f"/api/display?battery={args.battery}"))
    if doc["image_hash"] != state.get("image_hash"):
        r = call(args, doc["image_url"])
        data = r.read()
        if len(data) != IMG_BYTES or int(r.headers.get("Content-Length", -1)) != IMG_BYTES:
            sys.exit(f"bad image: {len(data)} bytes, Content-Length {r.headers.get('Content-Length')}")
        unpack(data, args.out)
        print(f"new image {doc['image_hash']} -> {args.out}")
    else:
        print("image unchanged")
    buttons = doc.get("buttons", {})
    rate = min(max(doc.get("refresh_rate", 180), 180), 3600)
    state.update(image_hash=doc["image_hash"], screen_id=doc["screen_id"], buttons=buttons)
    STATE.write_text(json.dumps(state))
    print(f"refresh_rate={rate} buttons={buttons}")
    return rate


p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--bridge", default="http://127.0.0.1:5480")
p.add_argument("--token", default="dev")
p.add_argument("--battery", type=float, default=3.9)
p.add_argument("--press", choices="ABC")
p.add_argument("--out", default="frame.png")
p.add_argument("--loop", action="store_true", help="repeat every refresh_rate")
a = p.parse_args()
while True:
    rate = cycle(a)
    if not a.loop:
        break
    a.press = None
    time.sleep(max(rate, 1))
