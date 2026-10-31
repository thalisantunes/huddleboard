import re

from PIL import Image, ImageDraw, ImageFont

from .model import Screen, pick_buttons

W, H = 800, 480
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = range(7)
_RGB = [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0), (255, 128, 0)]
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_GLYPH = {"idle": ("-", BLACK), "approval": ("!", RED), "input": ("!", RED), "stopping": ("■", RED)}


_LABEL = {"input": "waiting input"}


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
        c = f"credits {u['credits_used']:g}"
        if u["credits_plan"]:
            c += f" / {u['credits_plan']:g}"
        if u["percentage"] is not None:
            c += f" ({u['percentage']:g}%)"
        parts.append(c)
    if u["cost_usd"] is not None:
        parts.append(f"${u['cost_usd']:.2f}")
    if u["resets"]:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", u["resets"])
        parts.append("resets " + (f"{m[3]}/{m[2]}" if m else u["resets"][:10]))
    if u["msgs_today"] is not None:
        parts.append(f"{u['msgs_today']} msgs today")
    return " \u00b7 ".join(parts) or "usage n/a"


def render(screen: Screen, theme: str = "dark") -> Image.Image:
    # The palette has no grey: hierarchy comes from font size/weight and accent colors, not tones.
    dark = theme != "light"
    bg, fg = (BLACK, WHITE) if dark else (WHITE, BLACK)
    title = YELLOW if dark else BLUE  # section titles
    warn = ORANGE if dark else RED  # warning text; red on black is too dim to read
    lw = 1 if dark else 2  # divider width
    img = Image.new("P", (W, H), bg)
    pal = [c for rgb in _RGB for c in rgb]
    img.putpalette(pal + [0] * (768 - len(pal)))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # no antialiasing: pure palette colors only
    f, fb, fs, fbs = _font(_FONT, 22), _font(_BOLD, 24), _font(_FONT, 18), _font(_BOLD, 22)

    # header
    right = f"{screen.updated_at}  "
    right += f"{screen.battery_v:.2f}V" if screen.battery_v is not None else "--V"
    rw = d.textlength(right, font=f)
    fh = _font(_BOLD, 28)
    d.text((16, 12), _clip(d, screen.crew_name, fh, W - 32 - rw - 16), font=fh, fill=fg)
    d.text((W - 16 - rw, 16), right, font=f, fill=fg)
    d.ellipse((W - 30, 4, W - 20, 14), fill=RED if screen.errors else GREEN)
    d.line((0, 52, W, 52), fill=fg, width=lw)

    # block 1: approvals
    n = len(screen.approvals)
    failed = "approvals" in screen.errors or "slots" in screen.errors  # approvals come from both
    d.rectangle((0, 58, W, 90), fill=ORANGE if failed else RED if n else GREEN)
    bar_fg = BLACK if dark and not n and not failed else WHITE  # white on bright green is unreadable on black
    d.text((16, 60), f"APPROVALS: {'?' if failed else n}", font=fb, fill=bar_fg)
    if screen.waiting_input:
        d.rectangle((W - 200, 60, W - 10, 88), fill=ORANGE, outline=BLACK, width=2)
        d.text((W - 190, 60), f"INPUT: {screen.waiting_input}", font=fb, fill=BLACK)
    y = 96
    for a in screen.approvals[:3]:
        line = f"{a['agent']}: {a['title']}" if a["agent"] else a["title"]
        d.text((16, y), _clip(d, line, f, W - 32), font=f, fill=warn)
        y += 28
    legend = "   ".join(f"[{b}] {a['kind']}" for b, a in pick_buttons(screen).items())
    if legend:
        d.text((16, 180), legend, font=fs, fill=fg)

    # block 2: slots
    d.line((0, 206, W, 206), fill=fg, width=lw)
    d.text((16, 212), "SLOTS", font=fb, fill=title)
    half = screen.sessions is not None  # painel provider on: slots yield the right half
    name_w, text_x, limit = (150, 205, 390) if half else (230, 290, W - 16)
    y = 244
    for s in screen.slots[:5]:
        g, col = _GLYPH.get(s["state"], ("\u25b6", GREEN))
        if s["state"] == "idle":
            col = fg
        d.text((16, y), g, font=f, fill=col)
        nf = f if dark and s["state"] == "idle" else fbs  # idle rows recede: regular weight
        d.text((48, y), _clip(d, s["name"], nf, name_w), font=nf, fill=fg)
        d.text((text_x, y), _clip(d, f"{_LABEL.get(s['state'], s['state'])} {s['task']}".strip(), f, limit - text_x), font=f, fill=fg)
        y += 28
    if half:
        ss = screen.sessions
        d.line((400, 206, 400, 392), fill=fg, width=lw)
        d.text((416, 212), "CLAUDE CODE", font=fb, fill=title)
        parts = [("!", RED, ss["waiting"]), ("\u25b6", GREEN, ss["working"]), ("\u25a0", fg, ss["stopped"])]
        if ss["unknown"]:
            parts.append(("?", ORANGE, ss["unknown"]))
        x = 416
        for g, col, n in parts:
            d.text((x, 246), g, font=fbs, fill=col)
            d.text((x + 24, 246), str(n), font=fbs, fill=fg)
            x += 24 + d.textlength(str(n), font=fbs) + 24
        y = 284
        for w in screen.waiting:
            d.text((416, y), _clip(d, f"! {w['name']} {w['minutes']}m", f, W - 16 - 416), font=f, fill=warn)
            y += 28

    # block 3: tasks
    d.line((0, 392, W, 392), fill=fg, width=lw)
    t = screen.tasks
    d.text((16, 400), f"TASKS  running {t['running']}   queued {t['queued']}", font=f, fill=fg)
    d.text((430, 400), f"failed {t['failed']}", font=f, fill=warn if t["failed"] else fg)

    # footer
    u = screen.usage
    nxt = f"next {screen.next_refresh_s}s"
    nw = d.textlength(nxt, font=fs)
    left = _usage_line(u)
    d.text((16, 440), _clip(d, left, fs, W - 48 - nw), font=fs, fill=fg)
    d.text((W - 16 - nw, 440), nxt, font=fs, fill=fg)
    return img


def to_epd_bytes(img: Image.Image) -> bytes:
    """Pack palette indices 2 px/byte, high nibble = left pixel, row-major from the top."""
    px = img.tobytes()
    return bytes((a << 4) | b for a, b in zip(px[0::2], px[1::2]))
