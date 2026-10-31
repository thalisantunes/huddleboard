import logging
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kirocrew_url: str
    kirocrew_token: str
    internal_secret: str
    device_tokens: frozenset
    refresh: int
    refresh_urgent: int
    fixtures: bool
    bind: str
    port: int


def load() -> Config:
    e = os.environ.get
    cfg = Config(
        kirocrew_url=e("KIROCREW_URL", "http://127.0.0.1:5476").rstrip("/"),
        kirocrew_token=e("KIROCREW_TOKEN", ""),
        internal_secret=e("KIROCREW_INTERNAL_SECRET", ""),
        device_tokens=frozenset(t.strip() for t in e("DEVICE_TOKENS", "").split(",") if t.strip()),
        refresh=int(e("REFRESH_SECONDS", "300")),
        refresh_urgent=int(e("REFRESH_SECONDS_URGENT", "180")),
        fixtures=e("FIXTURES", "0") == "1",
        bind=e("BIND", "127.0.0.1"),
        port=int(e("PORT", "5480")),
    )
    if not cfg.device_tokens:
        logging.getLogger("kcdeck").warning("DEVICE_TOKENS is empty: every device request will be rejected")
    return cfg
