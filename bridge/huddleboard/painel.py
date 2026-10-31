"""Optional painel-tmux provider: Claude Code sessions in tmux, via GET /estado.json."""
import aiohttp

from .config import Config


async def fetch(cfg: Config) -> dict:
    headers = {"Authorization": f"Bearer {cfg.painel_token}"} if cfg.painel_token else {}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as s:
        async with s.get(cfg.painel_url + "/estado.json") as r:
            r.raise_for_status()
            return await r.json()
