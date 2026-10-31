import asyncio
import hashlib
import hmac
import io
import logging
import uuid
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime

import aiohttp
from aiohttp import web

from . import config
from .kirocrew import KiroCrew
from .model import build_screen, pick_buttons
from .render import render, to_epd_bytes

log = logging.getLogger("kcdeck")
_KEYS = ("status", "slots", "approvals", "tasks_summary", "usage")
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_VALID_IDS = 2  # current + previous screen_id


async def refresh(app, battery=None) -> dict:
    """Fetch, build and cache the current frame. Failed endpoints are recorded in screen.errors."""
    cfg, kc, state = app["cfg"], app["kc"], app["state"]
    calls = [kc.get_status(), kc.get_slots(), kc.get_approvals(), kc.get_tasks_summary(), kc.get_usage()]
    results = await asyncio.gather(*calls, return_exceptions=True)
    raw, errors = {}, []
    for k, r in zip(_KEYS, results):
        if isinstance(r, Exception):
            log.warning("kirocrew %s failed: %r", k, r)
            errors.append(k)
            r = {}
        raw[k] = r
    screen = build_screen(raw, datetime.now().strftime("%H:%M"), battery, cfg.refresh, errors)
    if screen.approvals:
        screen.next_refresh_s = cfg.refresh_urgent
    img = render(screen)
    data = to_epd_bytes(img)
    h = hashlib.sha1(data).hexdigest()[:12]
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")

    valid = state.setdefault("valid", OrderedDict())  # screen_id -> buttons
    cur = state.get("frame")
    if cur and cur["hash"] == h and cur["screen_id"] in valid:
        sid = cur["screen_id"]
    else:
        sid = str(uuid.uuid4())
    valid[sid] = pick_buttons(screen)
    while len(valid) > _VALID_IDS:
        valid.popitem(last=False)
    state["frame"] = {"screen": screen, "bytes": data, "png": buf.getvalue(), "hash": h, "screen_id": sid}
    return state["frame"]


def _authed(request) -> bool:
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return False
    got = h[7:].encode()
    return any(hmac.compare_digest(got, t.encode()) for t in request.app["cfg"].device_tokens)


def _need_auth(request):
    if not _authed(request):
        raise web.HTTPUnauthorized()


def _need_auth_unless_loopback(request):
    if request.app["cfg"].bind not in _LOOPBACK:
        _need_auth(request)


async def display(request):
    _need_auth(request)
    try:
        battery = float(request.query["battery"]) if "battery" in request.query else None
    except ValueError:
        battery = None
    fr = await refresh(request.app, battery)
    buttons = request.app["state"]["valid"][fr["screen_id"]]
    return web.json_response({
        "image_url": f"/api/image/{fr['hash']}.bin",
        "image_hash": fr["hash"],
        "refresh_rate": fr["screen"].next_refresh_s,
        "screen_id": fr["screen_id"],
        "buttons": {b: buttons.get(b, {}).get("kind", "none") for b in "ABC"},
    })


async def image(request):
    _need_auth(request)
    fr = request.app["state"].get("frame")
    if not fr or fr["hash"] != request.match_info["hash"]:
        raise web.HTTPNotFound()
    return web.Response(body=fr["bytes"], content_type="application/octet-stream")


async def action(request):
    _need_auth(request)
    try:
        body = await request.json()
        sid, button = body["screen_id"], body["button"]
    except (ValueError, KeyError, TypeError):
        raise web.HTTPBadRequest(text="invalid body")
    valid = request.app["state"].get("valid", {})
    buttons = valid.get(sid)
    if buttons is None:
        raise web.HTTPConflict(text="stale or unknown screen_id")
    spec = buttons.get(button)
    if not spec:
        return web.json_response({"ok": False, "result": "no_action"})
    del valid[sid]  # consume synchronously, before any await: no replay
    kc, kind = request.app["kc"], spec["kind"]
    try:
        if kind == "stop":
            await kc.stop_slot(spec["target_id"])
            result = "stopped"
        else:
            await kc.approve(spec["target_id"], kind)
            result = "approved" if kind == "approve" else "rejected"
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("kirocrew action failed: %r", e)
        return web.json_response({"ok": False, "result": "upstream_error"}, status=502)
    return web.json_response({"ok": True, "result": result})


async def preview(request):
    _need_auth_unless_loopback(request)
    fr = request.app["state"].get("frame") or await refresh(request.app)
    return web.Response(body=fr["png"], content_type="image/png")


async def model_json(request):
    _need_auth_unless_loopback(request)
    fr = request.app["state"].get("frame") or await refresh(request.app)
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
