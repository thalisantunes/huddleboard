from kcdeck import server

AUTH = {"Authorization": "Bearer tok"}


async def test_display_image_action_flow(client):
    r = await client.get("/api/display?battery=3.87", headers=AUTH)
    assert r.status == 200
    d = await r.json()
    assert d["refresh_rate"] == 180  # fixtures have pending approvals
    assert d["buttons"] == {"A": "approve", "B": "reject", "C": "stop"}
    r = await client.get(d["image_url"], headers=AUTH)
    assert r.status == 200 and len(await r.read()) == 192000
    r = await client.post("/api/action", json={"screen_id": d["screen_id"], "button": "A"}, headers=AUTH)
    assert r.status == 200 and (await r.json()) == {"ok": True, "result": "approved"}


async def test_unauthorized(client):
    assert (await client.get("/api/display")).status == 401
    assert (await client.get("/api/display", headers={"Authorization": "Bearer bad"})).status == 401


async def test_wrong_screen_id_is_409(client):
    await client.get("/api/display", headers=AUTH)
    r = await client.post("/api/action", json={"screen_id": "nope", "button": "A"}, headers=AUTH)
    assert r.status == 409


async def test_preview_model_health(client):
    r = await client.get("/preview.png")
    assert r.status == 200 and (await r.read())[:4] == b"\x89PNG"
    assert (await client.get("/healthz")).status == 200
    r = await client.get("/api/model.json", headers=AUTH)
    assert (await r.json())["crew_name"] == "KiroCrew"


async def _display(client, fresh=True):
    if fresh:  # display only reads the cache; force a recollect
        await server.refresh(client.app)
    return await (await client.get("/api/display", headers=AUTH)).json()


async def test_action_replay_is_409(client):
    d = await _display(client)
    body = {"screen_id": d["screen_id"], "button": "A"}
    assert (await client.post("/api/action", json=body, headers=AUTH)).status == 200
    assert (await client.post("/api/action", json=body, headers=AUTH)).status == 409


async def test_concurrent_replay_executes_once(client):
    import asyncio
    calls = []
    kc = client.app["kc"]
    orig = kc.decide

    async def slow(*a):
        calls.append(a)
        await asyncio.sleep(0.05)
        return await orig(*a)

    kc.decide = slow
    d = await _display(client)
    body = {"screen_id": d["screen_id"], "button": "A"}
    rs = await asyncio.gather(*[client.post("/api/action", json=body, headers=AUTH) for _ in range(2)])
    assert sorted(r.status for r in rs) == [200, 409] and len(calls) == 1


async def test_screen_id_follows_data_not_image(client, monkeypatch):
    import datetime as dt
    from kcdeck import server
    now = [dt.datetime(2026, 1, 1, 12, 0)]
    monkeypatch.setattr(server, "datetime", type("D", (), {"now": staticmethod(lambda: now[0])}))
    a = await _display(client)
    now[0] = dt.datetime(2026, 1, 1, 12, 1)  # clock changes the image only
    b = await _display(client)
    assert a["image_hash"] != b["image_hash"] and a["screen_id"] == b["screen_id"]
    # actionable data changes -> new id, previous still honored
    orig = client.app["kc"].get_approvals

    async def fewer():
        return (await orig())[:1]

    client.app["kc"].get_approvals = fewer
    c = await _display(client)
    assert c["screen_id"] != a["screen_id"]
    r = await client.post("/api/action", json={"screen_id": a["screen_id"], "button": "B"}, headers=AUTH)
    assert r.status == 200


async def test_missing_endpoint_marks_error(aiohttp_client, cfg, monkeypatch, tmp_path):
    import shutil
    from kcdeck import kirocrew
    from kcdeck.server import make_app
    shutil.copytree(kirocrew.FIXTURE_DIR, tmp_path / "f")
    (tmp_path / "f" / "approvals.json").unlink()
    monkeypatch.setattr(kirocrew, "FIXTURE_DIR", tmp_path / "f")
    c = await aiohttp_client(make_app(cfg))
    m = await (await c.get("/api/model.json", headers=AUTH)).json()
    assert m["errors"] == ["approvals"]
    assert [a["kind"] for a in m["approvals"]] == ["slot"]  # slot approvals still come through


async def test_open_endpoints_need_auth_off_loopback(aiohttp_client, cfg, monkeypatch):
    from kcdeck import config
    from kcdeck.server import make_app
    monkeypatch.setenv("BIND", "0.0.0.0")
    c = await aiohttp_client(make_app(config.load()))
    assert (await c.get("/preview.png")).status == 401
    assert (await c.get("/api/model.json")).status == 401
    assert (await c.get("/preview.png", headers=AUTH)).status == 200


async def test_bad_body_400_and_upstream_502(client):
    import aiohttp
    r = await client.post("/api/action", data="nope", headers=AUTH)
    assert r.status == 400
    r = await client.post("/api/action", json={"x": 1}, headers=AUTH)
    assert r.status == 400

    async def boom(*a):
        raise aiohttp.ClientError()

    client.app["kc"].decide = boom
    d = await _display(client)
    r = await client.post("/api/action", json={"screen_id": d["screen_id"], "button": "A"}, headers=AUTH)
    assert r.status == 502 and (await r.json()) == {"ok": False, "result": "upstream_error"}


async def test_display_reads_cache_only(client):
    calls = []
    kc = client.app["kc"]
    orig = kc._get

    async def counted(name):
        calls.append(name)
        return await orig(name)

    kc._get = counted
    for _ in range(3):
        assert (await client.get("/api/display", headers=AUTH)).status == 200
    assert calls == []


async def test_image_has_content_length_not_chunked(client):
    d = await _display(client, fresh=False)
    r = await client.get(d["image_url"], headers=AUTH)
    assert r.headers["Content-Length"] == "192000"
    assert "Transfer-Encoding" not in r.headers


async def test_ws_message_triggers_debounced_refresh(aiohttp_client, aiohttp_server, cfg, monkeypatch):
    import asyncio
    import dataclasses
    from aiohttp import web

    async def ws_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for _ in range(3):  # burst: must coalesce
            await ws.send_str("{}")
        await asyncio.sleep(0.5)
        return ws

    fake = web.Application()
    fake.add_routes([web.get("/api/ws", ws_handler)])
    srv = await aiohttp_server(fake)
    monkeypatch.setattr(server, "DEBOUNCE", 0.05)
    calls = []
    orig = server.KiroCrew._get

    async def counted(self, name):
        calls.append(name)
        return await orig(self, name)

    monkeypatch.setattr(server.KiroCrew, "_get", counted)
    c = dataclasses.replace(cfg, ws=True, poll_seconds=3600, kirocrew_url=f"http://127.0.0.1:{srv.port}")
    await aiohttp_client(server.make_app(c))
    assert len(calls) == 5  # startup render
    for _ in range(40):
        await asyncio.sleep(0.05)
        if len(calls) >= 10:
            break
    await asyncio.sleep(0.2)
    assert len(calls) == 10  # exactly one coalesced recollect


async def _painel_server(aiohttp_server, status=200):
    import json
    from aiohttp import web
    from kcdeck.kirocrew import FIXTURE_DIR
    body = (FIXTURE_DIR / "painel_estado.json").read_text()

    async def h(request):
        return web.Response(text=body, status=status, content_type="application/json")

    app = web.Application()
    app.add_routes([web.get("/estado.json", h)])
    return await aiohttp_server(app)


async def test_painel_on_sessions_and_urgent(aiohttp_client, aiohttp_server, cfg):
    import dataclasses
    srv = await _painel_server(aiohttp_server)
    c = await aiohttp_client(server.make_app(dataclasses.replace(cfg, painel_url=f"http://127.0.0.1:{srv.port}")))
    m = await (await c.get("/api/model.json", headers=AUTH)).json()
    assert m["sessions"]["waiting"] == 2 and m["errors"] == []


async def test_painel_waiting_alone_is_urgent(aiohttp_client, aiohttp_server, cfg, monkeypatch):
    import dataclasses
    srv = await _painel_server(aiohttp_server)
    c = await aiohttp_client(server.make_app(dataclasses.replace(cfg, painel_url=f"http://127.0.0.1:{srv.port}")))
    c.app["state"]["frame"] = None
    async def none():
        return []
    c.app["kc"].get_approvals = c.app["kc"].get_slots = none
    d = await _display(c)
    assert d["refresh_rate"] == 180


async def test_painel_failure_is_error(aiohttp_client, aiohttp_server, cfg):
    import dataclasses
    srv = await _painel_server(aiohttp_server, status=500)
    c = await aiohttp_client(server.make_app(dataclasses.replace(cfg, painel_url=f"http://127.0.0.1:{srv.port}")))
    m = await (await c.get("/api/model.json", headers=AUTH)).json()
    assert m["errors"] == ["painel"] and m["sessions"]["waiting"] == 0


async def test_display_after_consumed_id_issues_new_id(client):
    a = await _display(client, fresh=False)
    r = await client.post("/api/action", json={"screen_id": a["screen_id"], "button": "A"}, headers=AUTH)
    assert r.status == 200
    r = await client.get("/api/display", headers=AUTH)
    assert r.status == 200
    b = await r.json()
    assert b["screen_id"] != a["screen_id"]
    c = await (await client.get("/api/display", headers=AUTH)).json()
    assert c["screen_id"] == b["screen_id"]
