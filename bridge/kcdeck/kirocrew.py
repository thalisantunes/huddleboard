"""Async KiroCrew REST client. Fields marked ? in the schema notes are unconfirmed: tolerate absence."""
import json
import os
from urllib.parse import quote
from pathlib import Path

import aiohttp

from .config import Config

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

_GET = {
    "status": ("/api/status", "status.json"),
    "agents": ("/api/agents", "agents.json"),
    "slots": ("/api/chat/slots", "slots.json"),
    "approvals": ("/api/approvals", "approvals.json"),
    "tasks_summary": ("/api/tasks/summary", "tasks_summary.json"),
    "usage": ("/api/usage", "usage.json"),
}


def _read_secret_file() -> str:
    home = os.environ.get("KIROCREW_HOME") or str(Path.home() / ".kiro" / "crew")
    try:
        return (Path(home) / ".local_secret").read_text().strip()
    except OSError:
        return ""


class KiroCrew:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._secret = cfg.internal_secret or _read_secret_file()
        self._session = None

    def _headers(self) -> dict:
        h = {}
        if self._secret:
            h["X-Internal-Secret"] = self._secret
        if self.cfg.cookie:
            h["Cookie"] = self.cfg.cookie
        return h

    def _reload_secret(self) -> bool:
        """The gateway generates a new secret on every restart. True if it changed."""
        new = self.cfg.internal_secret or _read_secret_file()
        changed, self._secret = new != self._secret, new
        return changed

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    async def _req(self, method: str, path: str, **kw):
        for attempt in (0, 1):
            async with self._http().request(method, self.cfg.kirocrew_url + path, headers=self._headers(), **kw) as r:
                if r.status in (401, 403) and attempt == 0 and self._reload_secret():
                    continue
                r.raise_for_status()
                return await r.json(content_type=None)

    async def _get(self, name: str):
        path, fixture = _GET[name]
        if self.cfg.fixtures:
            return json.loads((FIXTURE_DIR / fixture).read_text())
        return await self._req("GET", path)

    def ws_connect(self):
        """Async context manager for ws(s)://<KIROCREW_URL>/api/ws, same auth headers."""
        url = "ws" + self.cfg.kirocrew_url[4:] + "/api/ws"  # http->ws, https->wss
        return self._http().ws_connect(url, headers=self._headers())

    async def get_status(self):
        return await self._get("status")

    async def get_agents(self):
        return await self._get("agents")

    async def get_slots(self):
        return await self._get("slots")

    async def get_approvals(self):
        return await self._get("approvals")

    async def get_tasks_summary(self):
        return await self._get("tasks_summary")

    async def get_usage(self):
        return await self._get("usage")

    async def decide(self, approval: dict, decision: str):
        """decision: approve | reject. `approval` is a model approval record."""
        if self.cfg.fixtures:
            return {"ok": True}
        if approval["kind"] == "slot":
            # The slot route wants past-tense actions; plain reject (not reject_once) was chosen.
            action = {"approve": "approved", "reject": "rejected"}[decision]
            return await self._req("POST", f"/api/chat/slots/{quote(approval['slot'], safe='')}/approve", json={
                "origin": "native", "request_id": approval["request_id"],
                "request_mid": approval["request_mid"], "action": action})
        # ?: origin/slot/instance are sent whenever known; state approvals from /api/approvals carry them too.
        q = {"origin": "coordinator", "slot": approval["slot"], "instance": approval["instance"]}
        params = {k: v for k, v in q.items() if v}
        return await self._req("POST", f"/api/approvals/{quote(approval['id'], safe='')}/{decision}", params=params)

    async def stop_slot(self, slot: str):
        if self.cfg.fixtures:
            return {"ok": True}
        return await self._req("POST", f"/api/chat/slots/{quote(slot, safe='')}/stop", params={"force": "true"})
