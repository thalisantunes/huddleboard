from aiohttp import web

from . import config
from .server import make_app

cfg = config.load()
web.run_app(make_app(cfg), host=cfg.bind, port=cfg.port)
