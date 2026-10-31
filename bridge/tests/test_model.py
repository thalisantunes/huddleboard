from kcdeck.model import build_screen, pick_buttons


def test_empty_inputs_do_not_break():
    s = build_screen({})
    assert s.approvals == [] and s.slots == []
    assert pick_buttons(s) == {}


def test_garbage_inputs_do_not_break():
    s = build_screen({"approvals": "x", "slots": None, "usage": {"billing": {"credits_used": "abc"}}, "tasks_summary": [1]})
    assert s.usage["credits_used"] is None


def test_buttons():
    s = build_screen({
        "approvals": [{"id": "a1", "tool": "Bash", "tool_input": "ls", "source": "cron"}],
        "slots": [{"key": "s1"}, {"key": "s2", "running": True}],
    })
    b = pick_buttons(s)
    assert (b["A"]["kind"], b["A"]["target_id"], b["A"]["approval"]["kind"]) == ("approve", "a1", "state")
    assert b["B"]["kind"] == "reject"
    assert b["C"] == {"kind": "stop", "target_id": "s2"}


def test_slot_approvals_native_and_coordinator_dedup():
    slots = [
        {"key": "s1", "pending_approval": True, "pending_approval_info": {
            "origin": "native", "tool": "Bash", "tool_input": "ls", "request_id": "r1", "request_mid": "m1"}},
        {"key": "s2", "pending_approval": True, "pending_approval_info": {
            "origin": "coordinator", "tool": "Edit", "id": "c1", "instance": "i1", "slot": "s2"}},
        {"key": "s3", "pending_approval": True, "pending_approval_info": None},
    ]
    s = build_screen({"slots": slots, "approvals": [{"id": "c1", "source": "subagent"}, {"id": "x9", "source": "cron"}]})
    kinds = [(a["kind"], a["id"]) for a in s.approvals]
    assert kinds == [("slot", "r1"), ("state", "c1"), ("state", "x9")]
    assert s.approvals[0]["request_mid"] == "m1" and s.approvals[1]["instance"] == "i1"
    assert s.slots[0]["state"] == "approval"


def test_tasks_and_usage_real_shapes():
    s = build_screen({
        "tasks_summary": {"depth": {"running": 2, "queued": 3, "by_state": {"FAILED": 1}}},
        "usage": {"billing": {"credits_used": 1.5, "credits_plan": 50, "percentage": 3, "resets": "2026-11-01T00:00:00Z"},
                  "sessions": {"today": {"messages": 7}}},
    })
    assert s.tasks == {"running": 2, "queued": 3, "failed": 1}
    assert s.usage == {"credits_used": 1.5, "credits_plan": 50.0, "percentage": 3.0, "cost_usd": None,
                       "resets": "2026-11-01T00:00:00Z", "msgs_today": 7}
