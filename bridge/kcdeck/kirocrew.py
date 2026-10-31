"""Async KiroCrew REST client. Schemas are unconfirmed, so callers must tolerate missing fields."""
import json
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


class KiroCrew:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        headers = {}
        if cfg.kirocrew_token:
            headers["Authorization"] = f"Bearer {cfg.kirocrew_token}"
        if cfg.internal_secret:
            headers["X-Internal-Secret"] = cfg.internal_secret
        self._headers = headers
        self._session = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    async def _get(self, name: str):
        path, fixture = _GET[name]
        if self.cfg.fixtures:
            return json.loads((FIXTURE_DIR / fixture).read_text())
        async with self._http().get(self.cfg.kirocrew_url + path) as r:
            r.raise_for_status()
            return await r.json()

    async def _post(self, path: str):
        if self.cfg.fixtures:
            return {"ok": True}
        async with self._http().post(self.cfg.kirocrew_url + path) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

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

    async def approve(self, approval_id: str, action: str):
        """action: approve | reject | reject_once"""
        return await self._post(f"/api/approvals/{approval_id}/{action}")

    async def stop_slot(self, slot: str, force: bool = True):
        return await self._post(f"/api/chat/slots/{slot}/stop?force={'true' if force else 'false'}")
