import asyncio
import hashlib
import hmac
import ipaddress
import io
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime

import aiohttp
from aiohttp import web

from . import config
from . import painel
from .kirocrew import KiroCrew
from .kirocrew import safe_error as _safe
from .model import build_screen, pick_buttons
from .render import render, to_epd_bytes
from .web import INDEX

log = logging.getLogger("crewmate")
_KEYS = ("status", "slots", "approvals", "tasks_summary", "usage")
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_VALID_IDS = 2  # current + previous screen_id (and image)
_WS_TYPES = {"approval", "approval_resolved", "slots", "slot_patch", "slot_clear", "chat_done"}
DEBOUNCE = 2  # seconds to coalesce WS-triggered refreshes


async def refresh(app, battery=None) -> dict:
    """Fetch, build and cache the current frame. Failed endpoints are recorded in screen.errors."""
    cfg, kc, state = app["cfg"], app["kc"], app["state"]
    if battery is None:
        battery = state.get("battery")
    calls = [kc.get_status(), kc.get_slots(), kc.get_approvals(), kc.get_tasks_summary(), kc.get_usage()]
    keys = _KEYS
    if cfg.painel_url:
        keys, calls = keys + ("painel",), calls + [painel.fetch(cfg)]
    results = await asyncio.gather(*calls, return_exceptions=True)
    raw, errors = {}, []
    for k, r in zip(keys, results):
        if isinstance(r, Exception):
            log.warning("kirocrew %s failed: %s", k, _safe(r))
            errors.append(k)
            r = {}
        raw[k] = r
    if kc.token_error:
        errors.append("token")
    screen = build_screen(raw, datetime.now().strftime("%H:%M"), battery, cfg.refresh, errors,
                          input_recent_min=cfg.input_recent_minutes)
    if screen.approvals or screen.waiting_input or (screen.sessions and screen.sessions["waiting"]):
        screen.next_refresh_s = cfg.refresh_urgent
    img = render(screen, cfg.theme)
    data = to_epd_bytes(img)
    h = hashlib.sha1(data).hexdigest()[:12]
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")

    valid = state.setdefault("valid", OrderedDict())  # screen_id -> buttons
    cur = state.get("frame")
    # screen_id follows actionable data only, so the clock in the image does not invalidate it
    dk = json.dumps([[a["id"] for a in screen.approvals], [[x["key"], x["state"]] for x in screen.slots]])
    if cur and cur["data_key"] == dk and cur["screen_id"] in valid:
        sid = cur["screen_id"]
    else:
        sid = str(uuid.uuid4())
    valid[sid] = pick_buttons(screen)
    while len(valid) > _VALID_IDS:
        valid.popitem(last=False)
    images = state.setdefault("images", OrderedDict())  # hash -> bytes; device may fetch the previous one
    images.pop(h, None)
    images[h] = data
    while len(images) > _VALID_IDS:
        images.popitem(last=False)
    state["frame"] = {"screen": screen, "bytes": data, "png": buf.getvalue(), "hash": h, "screen_id": sid, "data_key": dk}
    return state["frame"]


def _via_trusted_proxy(request) -> bool:
    """Behind a proxy that already authenticates people (e.g. Cloudflare Access)."""
    net = request.app["trusted_net"]
    if net is None or not request.headers.get("Cf-Access-Authenticated-User-Email"):
        return False
    try:
        return ipaddress.ip_address(request.remote) in net
    except ValueError:
        return False


def _authed(request) -> bool:
    if _via_trusted_proxy(request):
        return True
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
    if battery is not None:
        request.app["state"]["battery"] = battery  # shown on the next render
    state = request.app["state"]
    fr = state.get("frame")
    if not fr or fr["screen_id"] not in state["valid"]:  # none yet, or its id was consumed by an action
        fr = await refresh(request.app)
    buttons = state["valid"][fr["screen_id"]]
    return web.json_response({
        "image_url": f"/api/image/{fr['hash']}.bin",
        "image_hash": fr["hash"],
        "refresh_rate": fr["screen"].next_refresh_s,
        "screen_id": fr["screen_id"],
        "buttons": {b: buttons.get(b, {}).get("kind", "none") for b in "ABC"},
    })


async def image(request):
    _need_auth(request)
    data = request.app["state"].get("images", {}).get(request.match_info["hash"])
    if data is None:
        raise web.HTTPNotFound()
    return web.Response(body=data, content_type="application/octet-stream")


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
            await kc.decide(spec["approval"], kind)
            result = "approved" if kind == "approve" else "rejected"
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("kirocrew action failed: %s", _safe(e))
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


async def index(request):
    _need_auth_unless_loopback(request)
    return web.Response(text=INDEX, content_type="text/html", headers={"Cache-Control": "no-store"})


async def healthz(request):
    return web.json_response({"ok": True})


async def _poller(app):
    wake, poll = app["state"]["wake"], app["cfg"].poll_seconds
    while True:
        try:
            await asyncio.wait_for(wake.wait(), poll)
            await asyncio.sleep(DEBOUNCE)
        except asyncio.TimeoutError:
            pass
        wake.clear()
        try:
            await refresh(app)
        except Exception:
            log.exception("refresh failed")


def _ws_relevant(text) -> bool:
    try:
        return json.loads(text).get("type") in _WS_TYPES
    except (ValueError, AttributeError):
        return False


async def _ws_loop(app):
    wake, delay = app["state"]["wake"], 5
    while True:
        try:
            async with app["kc"].ws_connect() as ws:
                delay = 5
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT and _ws_relevant(msg.data):
                        wake.set()
        except asyncio.CancelledError:
            raise
        except aiohttp.ClientError as e:
            log.warning("kirocrew ws: %s", _safe(e))
        except Exception:
            log.exception("kirocrew ws")
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


async def _background(app):
    app["state"]["wake"] = asyncio.Event()
    await refresh(app)  # first render before serving
    tasks = [asyncio.create_task(_poller(app))]
    if app["cfg"].ws:
        tasks.append(asyncio.create_task(_ws_loop(app)))
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await app["kc"].close()


def make_app(cfg=None) -> web.Application:
    cfg = cfg or config.load()
    app = web.Application()
    app["cfg"] = cfg
    app["kc"] = KiroCrew(cfg)
    app["state"] = {}
    app["trusted_net"] = ipaddress.ip_network(cfg.trusted_proxy_cidr, strict=False) if cfg.trusted_proxy_cidr else None
    app.cleanup_ctx.append(_background)
    app.add_routes([
        web.get("/", index),
        web.get("/api/display", display),
        web.get("/api/image/{hash}.bin", image),
        web.post("/api/action", action),
        web.get("/preview.png", preview),
        web.get("/api/model.json", model_json),
        web.get("/healthz", healthz),
    ])
    return app
