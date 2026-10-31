from kcdeck.model import build_screen, pick_buttons


def test_empty_inputs_do_not_break():
    s = build_screen({})
    assert s.approvals == [] and s.slots == []
    assert pick_buttons(s) == {}


def test_garbage_inputs_do_not_break():
    s = build_screen({"approvals": "x", "slots": None, "usage": {"today_usd": "abc"}, "tasks_summary": []})
    assert s.usage["today_usd"] == 0.0


def test_buttons():
    s = build_screen({
        "approvals": [{"id": "a1", "title": "t"}],
        "slots": [{"name": "s1", "state": "idle"}, {"name": "s2", "state": "soft_pending"}],
    })
    b = pick_buttons(s)
    assert b["A"] == {"kind": "approve", "target_id": "a1"}
    assert b["B"]["kind"] == "reject"
    assert b["C"] == {"kind": "stop", "target_id": "s2"}
