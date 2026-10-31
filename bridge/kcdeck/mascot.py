"""Original pixel-art ghost (16x16, drawn here; not the Kiro logo) with five moods.

Characters: W body (foreground color), K eyes/mouth (background color), R red, Y yellow,
G green, O orange, '.' transparent.
"""

_BASE = [
    "................",
    ".....WWWWWW.....",
    "....WWWWWWWW....",
    "...WWWWWWWWWW...",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWWWWWWWWWWW..",
    "..WWW.WWWW.WWW..",
    "..WW...WW...WW..",
]

# (row, col, pixels) patches over the base ghost
_PATCHES = {
    "sleeping": [(6, 4, "KKK"), (6, 9, "KKK"), (9, 7, "KK")],  # closed eyes, tiny mouth
    "working": [(5, 5, "KK"), (6, 5, "KK"), (7, 5, "KK"), (5, 9, "KK"), (6, 9, "KK"), (7, 9, "KK"),
                (10, 6, "KKKK"),  # determined mouth
                (6, 1, "W"), (5, 1, "W"), (4, 0, "W"), (3, 0, "W"),  # arms up
                (6, 14, "W"), (5, 14, "W"), (4, 15, "W"), (3, 15, "W")],
    "attention": [(r, c, "KKK") for r in (4, 5, 6, 7) for c in (4, 9)]
                 + [(5, 5, "W"), (5, 10, "W")]  # wide eyes with a glint
                 + [(r, 7, "KK") for r in (9, 10, 11)],  # open mouth
    "waiting": [(5, 6, "KK"), (6, 6, "KK"), (7, 6, "KK"), (5, 10, "KK"), (6, 10, "KK"), (7, 10, "KK"),
                (10, 8, "KK")],  # eyes shifted to one side
    "error": [(5, 4, "R.R"), (6, 4, ".R."), (7, 4, "R.R"), (5, 9, "R.R"), (6, 9, ".R."), (7, 9, "R.R"),
              (10, 6, "KKKK"), (11, 5, "K"), (11, 10, "K")],  # X eyes, frown
}
PHRASE = {"sleeping": "all quiet", "working": "crunching...", "attention": "need you!",
          "waiting": "hmm?", "error": "can't reach crew"}
_ACTIVE = ("running", "starting", "compacting")


def _build(state):
    grid = [list(r) for r in _BASE]
    for r, c, px in _PATCHES.get(state, []):
        for i, ch in enumerate(px):
            if ch != ".":
                grid[r][c + i] = ch
    return ["".join(r) for r in grid]


ART = {s: _build(s) for s in PHRASE}


def pick_state(screen) -> str:
    """attention > error > working > waiting > sleeping."""
    if screen.approvals or screen.waiting_input or (screen.sessions and screen.sessions["waiting"]):
        return "attention"
    if screen.errors:
        return "error"
    if any(s["state"] in _ACTIVE for s in screen.slots):
        return "working"
    if any(s["state"] == "input" for s in screen.slots):
        return "waiting"  # stale input: nothing urgent
    return "sleeping"


def draw(d, state, x, y, scale, colors):
    """colors maps the art characters (W K R Y G O) to palette indices."""
    for r, row in enumerate(ART[state]):
        for c, ch in enumerate(row):
            if ch in colors:
                d.rectangle((x + c * scale, y + r * scale, x + (c + 1) * scale - 1, y + (r + 1) * scale - 1),
                            fill=colors[ch])
