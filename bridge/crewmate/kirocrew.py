"""Async KiroCrew REST client. Fields marked ? in the schema notes are unconfirmed: tolerate absence."""
import asyncio
import json
import logging
import os
import time
from urllib.parse import quote
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from .config import Config

log = logging.getLogger("crewmate")
_TOKEN_TTL = 240  # seconds a minted token is reused; its link claim expires after 5 min
_MINT_RETRY = 30  # seconds before retrying a failed mint, unless a request just got 401/403


def _now() -> float:
    return time.monotonic()


def safe_error(e: BaseException) -> str:
    """Loggable summary of an error. Never repr() aiohttp errors: ClientResponseError carries
    request headers (X-Internal-Secret, Cookie incl. the owner token, Authorization)."""
    if isinstance(e, aiohttp.ClientResponseError):
        return f"{e.request_info.method} {e.request_info.url.path} status {e.status}"
    return f"{type(e).__name__}"


FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"

_GET = {
    "status": ("/api/status", "status.json"),
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
        self._token = ""
        self._minted = 0.0
        self._mint_failed_at = None
        self._lock = asyncio.Lock()
        self.token_error = False  # last mint failed

    async def _mint(self) -> bool:
        """Owner token from /api/token/local, which wants the .local_secret value as X-Local-Secret."""
        code = ""
        try:
            async with self._http().get(self.cfg.kirocrew_url + "/api/token/local", params={"ttl": "20h"},
                                        headers={"X-Local-Secret": self._secret}) as r:
                if r.status >= 400:
                    try:
                        code = str((await r.json(content_type=None)).get("code", ""))[:40]
                    except (ValueError, AttributeError, aiohttp.ClientError):
                        pass
                    raise aiohttp.ClientResponseError(r.request_info, (), status=r.status)
                token = (await r.json(content_type=None)).get("token")
            if not isinstance(token, str) or not token:
                raise ValueError("no token in response")
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, AttributeError) as e:
            log.warning("kirocrew token mint failed: %s%s", safe_error(e), f" code {code}" if code else "")
            self._token, self._mint_failed_at, self.token_error = "", _now(), True
            return False
        self._token, self._minted, self._mint_failed_at, self.token_error = token, _now(), None, False
        return True

    async def _token_value(self, force=False) -> str:
        def fresh():
            return self._token and _now() - self._minted < _TOKEN_TTL

        if fresh():
            return self._token
        if not force and self._mint_failed_at is not None and _now() - self._mint_failed_at < _MINT_RETRY:
            return ""
        async with self._lock:  # startup fires several requests at once; mint once
            if fresh():
                return self._token
            await self._mint()
        return self._token

    def _headers(self, token: str = "") -> dict:
        h = {}
        if self._secret:
            h["X-Internal-Secret"] = self._secret
        cookies = [self.cfg.cookie] if self.cfg.cookie else []
        if token:  # session-cookie form of the owner token; keeps it out of URLs and access logs
            u = urlparse(self.cfg.kirocrew_url)
            cookies.append(f"mc_token_{u.port or (443 if u.scheme == 'https' else 80)}={token}")
        if cookies:
            h["Cookie"] = "; ".join(cookies)
        return h

    def _reload_secret(self):
        """The gateway generates a new secret on every restart."""
        self._secret = self.cfg.internal_secret or _read_secret_file()

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    async def _req(self, method: str, path: str, params=None, **kw):
        for attempt in (0, 1):
            token = await self._token_value(force=attempt == 1)  # status/approvals/tasks/usage need it
            url = self.cfg.kirocrew_url + path
            async with self._http().request(method, url, params=params, headers=self._headers(token), **kw) as r:
                if r.status in (401, 403) and attempt == 0:
                    self._reload_secret()  # the gateway restarted: new secret, old token invalid
                    self._token = ""
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
        return self._http().ws_connect(url, headers=self._headers(), heartbeat=30)

    async def get_status(self):
        return await self._get("status")

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
