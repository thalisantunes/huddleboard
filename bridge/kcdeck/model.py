import time
from dataclasses import dataclass, field


@dataclass
class Screen:
    crew_name: str = "KiroCrew"
    updated_at: str = ""
    approvals: list = field(default_factory=list)  # {id, title, agent}
    slots: list = field(default_factory=list)  # {name, state, task}
    tasks: dict = field(default_factory=lambda: {"running": 0, "queued": 0, "failed": 0})
    usage: dict = field(default_factory=lambda: {"today_usd": 0.0, "week_usd": 0.0, "tokens_today": 0})
    battery_v: float | None = None
    next_refresh_s: int = 300
    errors: list = field(default_factory=list)  # endpoints that failed this cycle
    sessions: dict | None = None  # {waiting, working, stopped, unknown}; None = painel provider off
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


def build_screen(raw: dict, updated_at: str = "", battery_v=None, next_refresh_s: int = 300, errors=()) -> Screen:
    """raw keys: status, slots, approvals, tasks_summary, usage (each possibly empty)."""
    status = raw.get("status") or {}
    tasks = raw.get("tasks_summary") or {}
    usage = raw.get("usage") or {}
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
    return Screen(
        crew_name=str(status.get("name") or status.get("crew") or "KiroCrew"),
        updated_at=updated_at,
        approvals=[
            {
                "id": str(a.get("id", "")),
                "title": str(a.get("title") or a.get("summary") or a.get("tool") or "approval"),
                "agent": str(a.get("agent") or a.get("agent_name") or ""),
            }
            for a in _items(raw.get("approvals"), "approvals")
        ],
        slots=[
            {
                "name": str(s.get("name") or s.get("slot") or s.get("id") or "?"),
                "state": str(s.get("state") or "idle"),
                "task": str(s.get("task") or s.get("current_task") or ""),
            }
            for s in _items(raw.get("slots"), "slots")
        ],
        tasks={k: _num(tasks, k, int) for k in ("running", "queued", "failed")},
        usage={
            "today_usd": _num(usage, "today_usd", float),
            "week_usd": _num(usage, "week_usd", float),
            "tokens_today": _num(usage, "tokens_today", int),
        },
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
        first = screen.approvals[0]["id"]
        out["A"] = {"kind": "approve", "target_id": first}
        out["B"] = {"kind": "reject", "target_id": first}
    for s in screen.slots:
        if s["state"] not in ("idle", "killing"):
            out["C"] = {"kind": "stop", "target_id": s["name"]}
            break
    return out
