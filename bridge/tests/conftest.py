import pytest

from kcdeck import config
from kcdeck.server import make_app


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setenv("FIXTURES", "1")
    monkeypatch.setenv("DEVICE_TOKENS", "tok")
    return config.load()


@pytest.fixture
async def client(aiohttp_client, cfg):
    return await aiohttp_client(make_app(cfg))
