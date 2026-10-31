from huddleboard.model import build_screen, pick_buttons


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


def test_slot_labels_priority_task_and_input_count():
    slots = [
        {"key": "slack_1793358208.441229", "title": "Check the 14900k", "running": True, "workspace": "default"},
        {"key": "slack_1793324134.318149", "title": "hi", "needs_input": True, "workspace": "default",
         "last_message": "  Which   one? "},
        {"key": "slack_1793315164.791249", "title": "Gui, report", "waiting_for_input": True, "workspace": "ops",
         "prompt_preview": "do the thing"},
        {"key": "slack_1793294163.802569", "title": "Idle one", "workspace": "default"},
    ]
    s = build_screen({"slots": slots})
    assert [x["state"] for x in s.slots] == ["input", "input", "running", "idle"]  # input first, idle last
    assert s.waiting_input == 0  # no timestamps: nothing counts as recent
    by_key = {x["key"][-4:]: x for x in s.slots}
    assert by_key["1229"]["name"] == "Check the 14900k" and by_key["1229"]["task"] == ""  # "default" omitted
    assert by_key["8149"]["name"] == slots[1]["key"][-8:]  # title too short: use the key tail
    assert by_key["8149"]["task"] == "Which one?"
    assert by_key["1249"]["task"] == "do the thing"
    # Stop targets running work, never a slot that is only waiting for the human
    assert pick_buttons(s)["C"]["target_id"] == slots[0]["key"]
    assert "C" not in pick_buttons(build_screen({"slots": slots[1:3]}))


def test_only_recent_input_is_counted():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)
    iso = lambda mins: (now - timedelta(minutes=mins)).isoformat()
    slots = [
        {"key": "a", "needs_input": True, "last_activity_ts": iso(5)},  # ISO, recent
        {"key": "b", "needs_input": True, "last_activity_ts": now.timestamp() - 29 * 60},  # epoch, recent
        {"key": "c", "needs_input": True, "last_activity_ts": iso(31)},  # stale
        {"key": "d", "needs_input": True, "last_activity_ts": "garbage"},
        {"key": "e", "needs_input": True},
        {"key": "f", "running": True, "last_activity_ts": iso(1)},  # not input
    ]
    s = build_screen({"slots": slots}, now=now.timestamp())
    assert s.waiting_input == 2
    assert [x["state"] for x in s.slots].count("input") == 5  # all still listed
    assert build_screen({"slots": slots}, now=now.timestamp(), input_recent_min=60).waiting_input == 3
