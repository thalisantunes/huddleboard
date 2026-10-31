import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Screen:
    crew_name: str = "KiroCrew"
    updated_at: str = ""
    # approval: {id, kind slot|state, slot, request_id, request_mid, instance, title, agent}
    approvals: list = field(default_factory=list)
    slots: list = field(default_factory=list)  # {name, state, task}
    tasks: dict = field(default_factory=lambda: {"running": 0, "queued": 0, "failed": 0})
    usage: dict = field(default_factory=lambda: _usage(None))
    battery_v: float | None = None
    next_refresh_s: int = 300
    errors: list = field(default_factory=list)  # endpoints that failed this cycle
    sessions: dict | None = None  # {waiting, working, stopped, unknown}; None = painel provider off
    waiting_input: int = 0  # slots waiting for the human
    waiting: list = field(default_factory=list)  # up to 3 {name, minutes}, longest waiting first


def _items(raw, key):
    """Accept either a bare list or a dict wrapping the list under `key`."""
    if isinstance(raw, list):
        return [i for i in raw if isinstance(i, dict)]
    if isinstance(raw, dict) and isinstance(raw.get(key), list):
        return [i for i in raw[key] if isinstance(i, dict)]
    return []


def _num(d, key, cast):
    try:
        return cast(d.get(key) or 0)
    except (TypeError, ValueError):
        return cast(0)


def _d(x):
    return x if isinstance(x, dict) else {}


def _s(x):
    return x if isinstance(x, str) else ""


def _slot_state(s):
    # The API has no single state enum, only booleans; first match wins.
    for flag, name in (("stopping", "stopping"), ("pending_approval", "approval"), ("needs_input", "input"),
                       ("waiting_for_input", "input"), ("compacting", "compacting"), ("interrupted", "interrupted"),
                       ("preparing", "starting"), ("wake_starting", "starting"), ("running", "running")):
        if s.get(flag):
            return name
    return "idle"


_PRIO = {"approval": 0, "input": 1, "stopping": 2, "running": 3, "starting": 3, "compacting": 4, "interrupted": 5}
_ACTIVE = ("approval", "running", "starting", "compacting")  # states where Stop makes sense


def _ts(v):
    """Epoch seconds from a number or an ISO string (the real API sends ISO); None if unusable."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) or None
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).timestamp()
        except ValueError:
            return None
    return None


def _slot_row(sl):
    key = str(sl.get("key") or "?")
    title = " ".join(_s(sl.get("title")).split())
    ws = _s(sl.get("workspace"))
    # title is the human label; keys share a long prefix, so fall back to the distinguishing tail
    task = " ".join((_s(sl.get("prompt_preview")) or _s(sl.get("last_message"))).split())
    return {"key": key, "name": title if len(title) >= 3 else key[-8:], "state": _slot_state(sl),
            "ts": _ts(sl.get("last_activity_ts")),
            "task": task or ("" if ws == "default" else ws)}


def _title(tool, tool_input):
    tool, tool_input = _s(tool), _s(tool_input)
    return f"{tool}: {tool_input}" if tool and tool_input else tool or tool_input or "approval"


def _approvals(slots_raw, approvals_raw):
    """Slot approvals (pending_approval_info) first, then state approvals from /api/approvals."""
    out = []
    for s in _items(slots_raw, "slots"):
        info = s.get("pending_approval_info")
        if not (s.get("pending_approval") and isinstance(info, dict)):
            continue
        slot = str(info.get("slot") or s.get("key") or "")
        native = info.get("origin") == "native"
        out.append({
            "id": str(info.get("request_id" if native else "id") or ""),
            "kind": "slot" if native else "state",  # coordinator approvals are decided via /api/approvals
            "slot": slot,
            "request_id": str(info.get("request_id") or ""),
            "request_mid": str(info.get("request_mid") or ""),
            "instance": str(info.get("instance") or ""),
            "title": _title(info.get("tool"), info.get("tool_input")),
            "agent": slot,
        })
    seen = {(a["kind"], a["id"]) for a in out}
    for a in _items(approvals_raw, "approvals"):
        key = ("state", str(a.get("id") or ""))
        if key in seen:
            continue
        out.append({
            "id": key[1], "kind": "state", "slot": str(a.get("slot") or ""), "request_id": "", "request_mid": "",
            "instance": str(a.get("instance") or ""), "title": _title(a.get("tool"), a.get("tool_input")),
            "agent": str(a.get("source") or ""),
        })
    return out


def _opt(d, key):
    try:
        return float(d[key])
    except (KeyError, TypeError, ValueError):
        return None


def _usage(raw):
    """From the real /api/usage: billing.* plus sessions.today.messages. Absent parts stay None."""
    raw = _d(raw)
    billing, today = _d(raw.get("billing")), _d(_d(raw.get("sessions")).get("today"))
    return {
        "credits_used": _opt(billing, "credits_used"), "credits_plan": _opt(billing, "credits_plan"),
        "percentage": _opt(billing, "percentage"), "cost_usd": _opt(billing, "cost_usd"),
        "resets": _s(billing.get("resets")),
        "msgs_today": int(_opt(today, "messages")) if _opt(today, "messages") is not None else None,
    }


def build_screen(raw: dict, updated_at: str = "", battery_v=None, next_refresh_s: int = 300, errors=(),
                 now: float | None = None, input_recent_min: int = 30) -> Screen:
    """raw keys: status, slots, approvals, tasks_summary, usage (each possibly empty)."""
    depth = _d(_d(raw.get("tasks_summary")).get("depth"))
    sessions, waiting = None, []
    if "painel" in raw:  # present (even empty) means the provider is enabled
        p = raw["painel"] if isinstance(raw["painel"], dict) else {}
        r = p.get("resumo") if isinstance(p.get("resumo"), dict) else {}
        sessions = {k: _num(r, pt, int) for k, pt in (
            ("waiting", "esperando"), ("working", "trabalhando"), ("stopped", "parada"), ("unknown", "desconhecido"))}
        now = _num(p, "gerado_em", float) or time.time()
        wins = sorted(
            (w for w in _items(p, "janelas") if w.get("estado") == "esperando"),
            key=lambda w: _num(w, "desde", float),
        )
        waiting = [
            {"name": f"{w.get('sessao', '?')}/{w.get('nome', '?')}", "minutes": max(0, int((now - _num(w, "desde", float)) // 60))}
            for w in wins[:3]
        ]
    now = time.time() if now is None else now
    slots = sorted((_slot_row(sl) for sl in _items(raw.get("slots"), "slots")), key=lambda s: _PRIO.get(s["state"], 6))
    return Screen(
        updated_at=updated_at,
        approvals=_approvals(raw.get("slots"), raw.get("approvals")),
        slots=slots,
        # only recent input counts as urgent: old Slack threads can wait for a human for days
        waiting_input=sum(1 for sl in slots if sl["state"] == "input" and sl["ts"] and now - sl["ts"] <= input_recent_min * 60),
        # ?: "failed" is read from depth.by_state["FAILED"]; the state list is partly unconfirmed
        tasks={"running": _num(depth, "running", int), "queued": _num(depth, "queued", int),
               "failed": _num(_d(depth.get("by_state")), "FAILED", int)},
        usage=_usage(raw.get("usage")),
        battery_v=battery_v,
        next_refresh_s=next_refresh_s,
        errors=list(errors),
        sessions=sessions,
        waiting=waiting,
    )


def pick_buttons(screen: Screen) -> dict:
    """Map A/B/C to the action each button triggers for what is on this screen."""
    out = {}
    if screen.approvals:
        first = screen.approvals[0]
        out["A"] = {"kind": "approve", "target_id": first["id"], "approval": first}
        out["B"] = {"kind": "reject", "target_id": first["id"], "approval": first}
    for s in screen.slots:
        if s["state"] in _ACTIVE:
            out["C"] = {"kind": "stop", "target_id": s["key"]}
            break
    return out
