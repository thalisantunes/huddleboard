from kcdeck.model import Screen, build_screen
from kcdeck.render import render, to_epd_bytes


def test_empty_screen_renders():
    img = render(Screen())
    assert img.size == (800, 480) and img.mode == "P"
    assert len(to_epd_bytes(img)) == 192000


def test_nibbles_in_range_with_content():
    s = build_screen({
        "approvals": [{"id": "1", "tool": "x" * 200, "source": "a"}] * 5,
        "slots": [{"key": "n", "stopping": True}, {"key": "m", "needs_input": True}, {"key": "k", "running": True, "project": "p"}, {"key": "i"}],
        "tasks_summary": {"depth": {"by_state": {"FAILED": 2}}},
    }, "12:00", 3.87)
    data = to_epd_bytes(render(s))
    assert len(data) == 192000
    assert all((b >> 4) <= 6 and (b & 15) <= 6 for b in data)
    assert any((b >> 4) == 4 for b in data)  # red present


def test_error_state_and_long_text_render():
    s = build_screen({"slots": [{"key": "n\n" * 50, "project": "t " * 300}]}, "12:00", None, 300, ["approvals"])
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
    # sha1 of the painel-off render, re-recorded after the real-schema fixtures
    assert hashlib.sha1(to_epd_bytes(render(s))).hexdigest() == "bdbbe3f3b9ae08fbf5ca4188b3781ec75478d916"


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


def test_usage_line_omits_absent_parts():
    from kcdeck.model import _usage
    from kcdeck.render import _usage_line
    full = _usage({"billing": {"credits_used": 0.02, "credits_plan": 50, "percentage": 0, "cost_usd": 1.5,
                               "resets": "2026-11-01T00:00:00Z"}, "sessions": {"today": {"messages": 4}}})
    assert _usage_line(full) == "credits 0.02 / 50 (0%) \u00b7 $1.50 \u00b7 resets 01/11 \u00b7 4 msgs today"
    assert _usage_line(_usage({"billing": {"credits_used": 3}})) == "credits 3"
    assert _usage_line(_usage(None)) == "usage n/a"


def test_input_badge_changes_render():
    base = {"slots": [{"key": "a", "title": "Title A", "running": True}]}
    waiting = {"slots": [{"key": "a", "title": "Title A", "needs_input": True}]}
    assert to_epd_bytes(render(build_screen(base))) != to_epd_bytes(render(build_screen(waiting)))
    assert any((b >> 4) == 6 for b in to_epd_bytes(render(build_screen(waiting))))  # orange badge
