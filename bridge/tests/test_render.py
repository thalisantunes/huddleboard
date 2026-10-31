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
