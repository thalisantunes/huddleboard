from PIL import Image, ImageDraw, ImageFont

from .model import Screen, pick_buttons

W, H = 800, 480
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = range(7)
_RGB = [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255), (255, 0, 0), (255, 255, 0), (255, 128, 0)]
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_GLYPH = {"idle": ("-", BLACK), "approval": ("!", RED), "input": ("?", ORANGE), "stopping": ("■", RED)}


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


def render(screen: Screen) -> Image.Image:
    img = Image.new("P", (W, H), WHITE)
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
    d.text((16, 12), _clip(d, screen.crew_name, fh, W - 32 - rw - 16), font=fh, fill=BLACK)
    d.text((W - 16 - rw, 16), right, font=f, fill=BLACK)
    d.ellipse((W - 30, 4, W - 20, 14), fill=RED if screen.errors else GREEN)
    d.line((0, 52, W, 52), fill=BLACK, width=2)

    # block 1: approvals
    n = len(screen.approvals)
    failed = "approvals" in screen.errors or "slots" in screen.errors  # approvals come from both
    d.rectangle((0, 58, W, 90), fill=ORANGE if failed else RED if n else GREEN)
    d.text((16, 60), f"APPROVALS: {'?' if failed else n}", font=fb, fill=WHITE)
    y = 96
    for a in screen.approvals[:3]:
        line = f"{a['agent']}: {a['title']}" if a["agent"] else a["title"]
        d.text((16, y), _clip(d, line, f, W - 32), font=f, fill=RED)
        y += 28
    legend = "   ".join(f"[{b}] {a['kind']}" for b, a in pick_buttons(screen).items())
    if legend:
        d.text((16, 180), legend, font=fs, fill=BLACK)

    # block 2: slots
    d.line((0, 206, W, 206), fill=BLACK, width=2)
    d.text((16, 212), "SLOTS", font=fb, fill=BLUE)
    half = screen.sessions is not None  # painel provider on: slots yield the right half
    name_w, text_x, limit = (130, 190, 390) if half else (164, 220, W - 16)
    y = 244
    for s in screen.slots[:5]:
        g, col = _GLYPH.get(s["state"], ("▶", GREEN))
        d.text((16, y), g, font=f, fill=col)
        d.text((48, y), _clip(d, s["name"], fbs, name_w), font=fbs, fill=BLACK)
        d.text((text_x, y), _clip(d, f"{s['state']} {s['task']}".strip(), f, limit - text_x), font=f, fill=BLACK)
        y += 28
    if half:
        ss = screen.sessions
        d.line((400, 206, 400, 392), fill=BLACK, width=2)
        d.text((416, 212), "CLAUDE CODE", font=fb, fill=BLUE)
        parts = [("!", RED, ss["waiting"]), ("\u25b6", GREEN, ss["working"]), ("\u25a0", BLACK, ss["stopped"])]
        if ss["unknown"]:
            parts.append(("?", ORANGE, ss["unknown"]))
        x = 416
        for g, col, n in parts:
            d.text((x, 246), g, font=fbs, fill=col)
            d.text((x + 24, 246), str(n), font=fbs, fill=BLACK)
            x += 24 + d.textlength(str(n), font=fbs) + 24
        y = 284
        for w in screen.waiting:
            d.text((416, y), _clip(d, f"! {w['name']} {w['minutes']}m", f, W - 16 - 416), font=f, fill=RED)
            y += 28

    # block 3: tasks
    d.line((0, 392, W, 392), fill=BLACK, width=2)
    t = screen.tasks
    d.text((16, 400), f"TASKS  running {t['running']}   queued {t['queued']}", font=f, fill=BLACK)
    d.text((430, 400), f"failed {t['failed']}", font=f, fill=RED if t["failed"] else BLACK)

    # footer
    u = screen.usage
    nxt = f"next {screen.next_refresh_s}s"
    nw = d.textlength(nxt, font=fs)
    win = f" / {u['window_days']}d" if u["window_days"] else ""
    left = f"credits {u['credits']:.1f}{win}   {u['turns']} turns"
    d.text((16, 440), _clip(d, left, fs, W - 48 - nw), font=fs, fill=BLACK)
    d.text((W - 16 - nw, 440), nxt, font=fs, fill=BLACK)
    return img


def to_epd_bytes(img: Image.Image) -> bytes:
    """Pack palette indices 2 px/byte, high nibble = left pixel, row-major from the top."""
    px = img.tobytes()
    return bytes((a << 4) | b for a, b in zip(px[0::2], px[1::2]))
