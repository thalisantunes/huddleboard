import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kirocrew_url: str
    internal_secret: str
    cookie: str
    device_tokens: frozenset
    refresh: int
    refresh_urgent: int
    fixtures: bool
    bind: str
    port: int
    poll_seconds: int
    ws: bool
    painel_url: str
    painel_token: str


def load() -> Config:
    e = os.environ.get
    cfg = Config(
        kirocrew_url=e("KIROCREW_URL", "http://127.0.0.1:5476").rstrip("/"),
        internal_secret=e("KIROCREW_INTERNAL_SECRET", ""),
        cookie=e("KIROCREW_COOKIE", ""),  # plan B if the internal secret cannot approve
        device_tokens=frozenset(t.strip() for t in e("DEVICE_TOKENS", "").split(",") if t.strip()),
        refresh=int(e("REFRESH_SECONDS", "300")),
        refresh_urgent=int(e("REFRESH_SECONDS_URGENT", "180")),
        fixtures=e("FIXTURES", "0") == "1",
        bind=e("BIND", "127.0.0.1"),
        port=int(e("PORT", "5480")),
        poll_seconds=int(e("POLL_SECONDS", "60")),
        ws=e("KIROCREW_WS", "0") == "1",
        painel_url=e("PAINEL_TMUX_URL", "").rstrip("/"),
        painel_token=e("PAINEL_TMUX_TOKEN", ""),
    )
    if not cfg.device_tokens:
        logging.getLogger("kcdeck").warning("DEVICE_TOKENS is empty: every device request will be rejected")
    return cfg
