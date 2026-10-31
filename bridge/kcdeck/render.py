import re

from PIL import Image, ImageDraw, ImageFont

from . import mascot
from .model import Screen, pick_buttons

W, H = 800, 480
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = range(7)
_RGB = [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0), (255, 128, 0)]
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _clip(d, text, font, max_w):
    text = " ".join(text.split())
    while text and d.textlength(text, font=font) > max_w:
        text = text[:-1]
    return text


def _usage_line(u) -> str:
    parts = []
    if u["credits_used"] is not None:
        parts.append(f"credits {u['credits_used']:g}" + (f"/{u['credits_plan']:g}" if u["credits_plan"] else ""))
    if u["resets"]:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", u["resets"])
        parts.append("resets " + (f"{m[3]}/{m[2]}" if m else u["resets"][:10]))
    return " \u00b7 ".join(parts) or "usage n/a"


_ACTIVE = ("running", "starting", "compacting")


def _card(d, box, label, value, fill, fg, small):
    """Big-number card: solid fill when it needs attention, outline when idle."""
    x0, y0, x1, y1 = box
    on = fill is not None
    txt = (WHITE if fill == RED else BLACK) if on else fg
    d.rectangle(box, fill=fill if on else None, outline=fg, width=3 if on else 1)
    lf = _font(_BOLD, 16 if small else 18)
    d.text(((x0 + x1) // 2, y0 + 10), label, font=lf, fill=txt, anchor="ma")
    num = str(value)
    d.text(((x0 + x1) // 2, y0 + 92), num, font=_font(_BOLD, 72 if len(num) < 3 else 48), fill=txt, anchor="mm")


def render(screen: Screen, theme: str = "dark") -> Image.Image:
    # The palette has no grey: hierarchy comes from size, weight and accent colors, not tones.
    dark = theme != "light"
    bg, fg = (BLACK, WHITE) if dark else (WHITE, BLACK)
    title = YELLOW if dark else BLUE
    warn = ORANGE if dark else RED  # warning text; red on black is too dim to read
    lw = 1 if dark else 2
    img = Image.new("P", (W, H), bg)
    pal = [c for rgb in _RGB for c in rgb]
    img.putpalette(pal + [0] * (768 - len(pal)))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no antialiasing: pure palette colors only
    f, fb, fs = _font(_FONT, 22), _font(_BOLD, 22), _font(_FONT, 18)

    # left column: mascot, mood phrase, clock and battery
    state = mascot.pick_state(screen)
    mascot.draw(d, state, 66, 40, 8, {"W": fg, "K": bg, "R": RED, "Y": YELLOW, "G": GREEN, "O": ORANGE})
    if state == "sleeping":
        d.text((196, 28), "zZ", font=_font(_BOLD, 36), fill=YELLOW)
    elif state == "attention":
        d.text((200, 8), "!", font=_font(_BOLD, 80), fill=RED)
    d.text((130, 184), mascot.PHRASE[state], font=fb, fill=fg, anchor="ma")
    if screen.errors:
        d.text((130, 216), _clip(d, "! " + ", ".join(screen.errors), fs, 236), font=fs, fill=warn, anchor="ma")
    d.text((130, 330), screen.updated_at or "--:--", font=_font(_BOLD, 40), fill=fg, anchor="ma")
    batt = f"{screen.battery_v:.2f}V" if screen.battery_v is not None else "--V"
    d.text((130, 386), batt, font=f, fill=fg, anchor="ma")
    d.line((260, 12, 260, 424), fill=fg, width=lw)

    # right column: cards
    n = len(screen.approvals)
    failed = "approvals" in screen.errors or "slots" in screen.errors  # approvals come from both
    running = sum(1 for s in screen.slots if s["state"] in _ACTIVE)
    cards = [("APPROVALS", "?" if failed else n, ORANGE if failed else RED if n else None),
             ("INPUT", screen.waiting_input, ORANGE if screen.waiting_input else None),
             ("RUNNING", running, GREEN if running else None)]
    if screen.sessions is not None:
        cards.append(("CLAUDE", screen.sessions["waiting"], RED if screen.sessions["waiting"] else None))
    gap, x_left, x_right = 10, 276, 784
    cw = (x_right - x_left - gap * (len(cards) - 1)) // len(cards)
    for i, (label, value, fill) in enumerate(cards):
        x0 = x_left + i * (cw + gap)
        _card(d, (x0, 16, x0 + cw, 166), label, value, fill, fg, len(cards) > 3)

    # "needs you" list: approvals, recent input, waiting Claude Code windows; else what is working
    names = {s["key"]: s["name"] for s in screen.slots}
    rows = [("!", RED, f"{a['title']} \u00b7 {names.get(a['agent'], a['agent'])}") for a in screen.approvals]
    rows += [("!", ORANGE, f"{s['name']} {s['task']}".strip()) for s in screen.recent_input]
    rows += [("!", RED, f"{w['name']} {w['minutes']}m") for w in screen.waiting]
    head = "NEEDS YOU"
    if not rows:
        rows = [("\u25b6", GREEN, f"{s['name']} {s['task']}".strip()) for s in screen.slots if s["state"] in _ACTIVE]
        head = "WORKING" if rows else "NEEDS YOU"
        if not rows:
            rows = [("-", fg, "nothing right now")]
    d.text((x_left, 180), head, font=fb, fill=title)
    y = 214
    for g, col, text in rows[:4]:
        d.text((x_left, y), g, font=fb, fill=col)
        d.text((x_left + 30, y), _clip(d, text, f, x_right - x_left - 30), font=f, fill=fg)
        y += 34
    t = screen.tasks
    if t["queued"] or t["failed"]:
        d.text((x_left, 366), f"queued {t['queued']}", font=fs, fill=fg)
        d.text((x_left + 130, 366), f"failed {t['failed']}", font=fs, fill=warn if t["failed"] else fg)

    # footer
    d.line((0, 432, W, 432), fill=fg, width=lw)
    legend = "   ".join(f"[{b}] {a['kind']}" for b, a in pick_buttons(screen).items())
    right = _usage_line(screen.usage)
    rw = d.textlength(right, font=fs)
    d.text((16, 446), _clip(d, legend, fs, W - 48 - rw), font=fs, fill=fg)
    d.text((W - 16 - rw, 446), right, font=fs, fill=fg)
    return img


def to_epd_bytes(img: Image.Image) -> bytes:
    """Pack palette indices 2 px/byte, high nibble = left pixel, row-major from the top."""
    px = img.tobytes()
    return bytes((a << 4) | b for a, b in zip(px[0::2], px[1::2]))
