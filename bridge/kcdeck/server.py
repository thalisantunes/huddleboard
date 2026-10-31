import asyncio
import hashlib
import io
import logging
import uuid
from datetime import datetime

from aiohttp import web

from . import config
from .kirocrew import KiroCrew
from .model import build_screen, pick_buttons
from .render import render, to_epd_bytes

log = logging.getLogger("kcdeck")
_KEYS = ("status", "slots", "approvals", "tasks_summary", "usage")


async def refresh(app, battery=None) -> dict:
    """Fetch, build and cache the current frame. Failed endpoints degrade to empty data."""
    cfg, kc = app["cfg"], app["kc"]
    calls = [kc.get_status(), kc.get_slots(), kc.get_approvals(), kc.get_tasks_summary(), kc.get_usage()]
    results = await asyncio.gather(*calls, return_exceptions=True)
    raw = {}
    for k, r in zip(_KEYS, results):
        if isinstance(r, Exception):
            log.warning("kirocrew %s failed: %s", k, r)
            r = {}
        raw[k] = r
    probe = build_screen(raw)
    rate = cfg.refresh_urgent if probe.approvals else cfg.refresh
    screen = build_screen(raw, datetime.now().strftime("%H:%M"), battery, rate)
    img = render(screen)
    data = to_epd_bytes(img)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    app["state"]["frame"] = {
        "screen": screen,
        "bytes": data,
        "png": buf.getvalue(),
        "hash": hashlib.sha1(data).hexdigest()[:12],
        "screen_id": str(uuid.uuid4()),
        "buttons": pick_buttons(screen),
        "raw": raw,
    }
    return app["state"]["frame"]


def _authed(request) -> bool:
    h = request.headers.get("Authorization", "")
    return h.startswith("Bearer ") and h[7:] in request.app["cfg"].device_tokens


def _need_auth(request):
    if not _authed(request):
        raise web.HTTPUnauthorized()


async def display(request):
    _need_auth(request)
    try:
        battery = float(request.query["battery"]) if "battery" in request.query else None
    except ValueError:
        battery = None
    fr = await refresh(request.app, battery)
    return web.json_response({
        "image_url": f"/api/image/{fr['hash']}.bin",
        "image_hash": fr["hash"],
        "refresh_rate": fr["screen"].next_refresh_s,
        "screen_id": fr["screen_id"],
        "buttons": {b: fr["buttons"].get(b, {}).get("kind", "none") for b in "ABC"},
    })


async def image(request):
    _need_auth(request)
    fr = request.app["state"].get("frame")
    if not fr or fr["hash"] != request.match_info["hash"]:
        raise web.HTTPNotFound()
    return web.Response(body=fr["bytes"], content_type="application/octet-stream")


async def action(request):
    _need_auth(request)
    body = await request.json()
    fr = request.app["state"].get("frame")
    if not fr or body.get("screen_id") != fr["screen_id"]:
        raise web.HTTPConflict(text="stale or unknown screen_id")
    spec = fr["buttons"].get(body.get("button"))
    if not spec:
        return web.json_response({"ok": False, "result": "no_action"})
    kc = request.app["kc"]
    kind = spec["kind"]
    if kind == "stop":
        await kc.stop_slot(spec["target_id"], force=True)
        result = "stopped"
    else:
        await kc.approve(spec["target_id"], kind)
        result = "approved" if kind == "approve" else "rejected"
    return web.json_response({"ok": True, "result": result})


async def preview(request):
    fr = request.app["state"].get("frame") or await refresh(request.app)
    return web.Response(body=fr["png"], content_type="image/png")


async def model_json(request):
    _need_auth(request)
    fr = request.app["state"].get("frame") or await refresh(request.app)
    from dataclasses import asdict
    return web.json_response(asdict(fr["screen"]))


async def healthz(request):
    return web.json_response({"ok": True})


async def _close(app):
    await app["kc"].close()


def make_app(cfg=None) -> web.Application:
    cfg = cfg or config.load()
    app = web.Application()
    app["cfg"] = cfg
    app["kc"] = KiroCrew(cfg)
    app["state"] = {}
    app.on_cleanup.append(_close)
    app.add_routes([
        web.get("/api/display", display),
        web.get("/api/image/{hash}.bin", image),
        web.post("/api/action", action),
        web.get("/preview.png", preview),
        web.get("/api/model.json", model_json),
        web.get("/healthz", healthz),
    ])
    return app
