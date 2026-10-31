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


def test_dark_is_default_and_light_still_renders():
    import hashlib
    s = build_screen(_fx(), "12:00", 3.87, 180)
    dark, light = to_epd_bytes(render(s)), to_epd_bytes(render(s, "light"))
    assert hashlib.sha1(dark).hexdigest() == "8a996b4f50cd209660e02768e6268ae1fe040e91"
    assert dark[0] >> 4 == 0 and light[0] >> 4 == 1  # black vs white background
    assert dark != light and len(dark) == len(light) == 192000


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
    assert _usage_line(full) == "credits 0.02/50 \u00b7 resets 01/11"
    assert _usage_line(_usage({"billing": {"credits_used": 3}})) == "credits 3"
    assert _usage_line(_usage(None)) == "usage n/a"


def test_input_badge_changes_render():
    base = {"slots": [{"key": "a", "title": "Title A", "running": True}]}
    waiting = {"slots": [{"key": "a", "title": "Title A", "needs_input": True, "last_activity_ts": 1000.0}]}
    s = build_screen(waiting, now=1060.0)
    assert to_epd_bytes(render(build_screen(base))) != to_epd_bytes(render(s))
    assert any((b >> 4) == 6 for b in to_epd_bytes(render(s)))  # orange badge


def _states():
    from kcdeck.model import build_screen as b
    return {
        "sleeping": b({"slots": [{"key": "a", "title": "Idle one"}]}),
        "working": b({"slots": [{"key": "a", "title": "Busy", "running": True}]}),
        "attention": b({"approvals": [{"id": "1", "tool": "Bash", "source": "cron"}]}),
        "waiting": b({"slots": [{"key": "a", "title": "Old", "needs_input": True, "last_activity_ts": 1000.0}]}, now=1e9),
        "error": b({}, errors=["status"]),
    }


def test_mascot_states_and_renders():
    from kcdeck import mascot
    for name, s in _states().items():
        assert mascot.pick_state(s) == name
        assert len(mascot.ART[name]) == 16 and all(len(r) == 16 for r in mascot.ART[name])
        for theme in ("dark", "light"):
            data = to_epd_bytes(render(s, theme))
            assert len(data) == 192000 and all((x >> 4) <= 6 and (x & 15) <= 6 for x in data), (name, theme)
    assert len({tuple(v) for v in mascot.ART.values()}) == 5  # five distinct faces


def test_mascot_state_priority():
    from kcdeck import mascot
    s = build_screen({"approvals": [{"id": "1"}]}, errors=["usage"])
    assert mascot.pick_state(s) == "attention"  # a pending approval beats an unrelated error
    s = build_screen({"slots": [{"key": "a", "running": True}]}, errors=["usage"])
    assert mascot.pick_state(s) == "error"
    s = build_screen({"slots": [{"key": "a", "running": True}]}, now=1.0)
    s.sessions = {"waiting": 1, "working": 0, "stopped": 0, "unknown": 0}
    assert mascot.pick_state(s) == "attention"  # a waiting Claude Code window needs the human too
