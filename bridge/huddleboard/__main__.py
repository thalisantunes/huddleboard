from aiohttp import web

from . import config
from .server import make_app

if __name__ == "__main__":
    cfg = config.load()
    web.run_app(make_app(cfg), host=cfg.bind, port=cfg.port)
