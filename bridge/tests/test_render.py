from kcdeck.model import Screen, build_screen
from kcdeck.render import render, to_epd_bytes


def test_empty_screen_renders():
    img = render(Screen())
    assert img.size == (800, 480) and img.mode == "P"
    assert len(to_epd_bytes(img)) == 192000


def test_nibbles_in_range_with_content():
    s = build_screen({
        "approvals": [{"id": "1", "title": "x" * 200, "agent": "a"}] * 5,
        "slots": [{"name": "n", "state": st, "task": "t"} for st in ("idle", "soft_pending", "killing", "busy")],
        "tasks_summary": {"failed": 2},
    }, "12:00", 3.87)
    data = to_epd_bytes(render(s))
    assert len(data) == 192000
    assert all((b >> 4) <= 6 and (b & 15) <= 6 for b in data)
    assert any((b >> 4) == 4 for b in data)  # red present


def test_error_state_and_long_text_render():
    s = build_screen({"slots": [{"name": "n\n" * 50, "state": "idle", "task": "t " * 300}]}, "12:00", None, 300, ["approvals"])
    s.crew_name = "x" * 300
    assert len(to_epd_bytes(render(s))) == 192000


def _fx(painel=None):
    import json
    from kcdeck.kirocrew import FIXTURE_DIR
    L = lambda n: json.loads((FIXTURE_DIR / n).read_text())
    raw = {"status": L("status.json"), "slots": L("slots.json"), "approvals": L("approvals.json"),
           "tasks_summary": L("tasks_summary.json"), "usage": L("usage.json")}
    if painel is not None:
        raw["painel"] = painel
    return raw


def test_painel_off_render_is_unchanged():
    import hashlib
    s = build_screen(_fx(), "12:00", 3.87, 180)
    # sha1 recorded before the painel provider existed
    assert hashlib.sha1(to_epd_bytes(render(s))).hexdigest() == "43a8193faa43fd95a3ec78b6685e486e6d7cdcd7"


def test_painel_on_counts_and_renders():
    import json
    from kcdeck.kirocrew import FIXTURE_DIR
    p = json.loads((FIXTURE_DIR / "painel_estado.json").read_text())
    s = build_screen(_fx(p), "12:00", 3.87, 180)
    assert s.sessions == {"waiting": 2, "working": 3, "stopped": 3, "unknown": 0}
    assert [w["minutes"] for w in s.waiting] == [23, 7]  # longest waiting first
    data = to_epd_bytes(render(s))
    assert len(data) == 192000 and all((b >> 4) <= 6 and (b & 15) <= 6 for b in data)
    assert data != to_epd_bytes(render(build_screen(_fx(), "12:00", 3.87, 180)))
