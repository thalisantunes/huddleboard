import dataclasses

from aiohttp import web

from crewmate.kirocrew import KiroCrew

SLOT_APPROVAL = {"kind": "slot", "id": "rq1", "slot": "coder 1", "request_id": "rq1", "request_mid": "m1",
                 "instance": "", "title": "t", "agent": "coder 1"}
STATE_APPROVAL = {"kind": "state", "id": "ap/7", "slot": "cron:n", "request_id": "", "request_mid": "",
                  "instance": "i1", "title": "t", "agent": "cron"}


def _cfg(cfg, srv, **kw):
    return dataclasses.replace(cfg, fixtures=False, kirocrew_url=f"http://127.0.0.1:{srv.port}", **kw)


async def test_slot_approve_url_and_body(aiohttp_server, cfg):
    seen = []

    async def h(request):
        seen.append((request.path_qs, await request.json(), request.headers.get("X-Internal-Secret"),
                     request.headers.get("Authorization")))
        return web.json_response({"ok": True})

    app = web.Application()
    app.add_routes([web.post("/api/chat/slots/{slot}/approve", h)])
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(app), internal_secret="sek"))
    await kc.decide(SLOT_APPROVAL, "reject")
    await kc.close()
    assert seen == [("/api/chat/slots/coder%201/approve",
                     {"origin": "native", "request_id": "rq1", "request_mid": "m1", "action": "rejected"},
                     "sek", None)]


async def test_state_approve_url_and_stop(aiohttp_server, cfg):
    seen = []

    async def h(request):
        seen.append((request.method, request.path_qs))
        return web.json_response({"ok": True})

    app = web.Application()
    app.add_routes([web.post("/api/approvals/{id}/{action}", h), web.post("/api/chat/slots/{slot}/stop", h)])
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(app), internal_secret="sek"))
    await kc.decide(STATE_APPROVAL, "approve")
    await kc.stop_slot("coder-1")
    await kc.close()
    assert seen == [("POST", "/api/approvals/ap%2F7/approve?origin=coordinator&slot=cron:n&instance=i1"),
                    ("POST", "/api/chat/slots/coder-1/stop?force=true")]


async def test_secret_file_reloaded_after_403(aiohttp_server, cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("KIROCREW_HOME", str(tmp_path))
    (tmp_path / ".local_secret").write_text("old\n")
    calls = []

    async def h(request):
        got = request.headers.get("X-Internal-Secret")
        calls.append(got)
        return web.json_response({"ok": True}) if got == "new" else web.Response(status=403)

    app = web.Application()
    app.add_routes([web.get("/api/status", h)])
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(app)))
    (tmp_path / ".local_secret").write_text("new\n")  # gateway restarted
    assert await kc.get_status() == {"ok": True}
    await kc.close()
    assert calls == ["old", "new"]


async def test_cookie_header_optional(aiohttp_server, cfg):
    seen = []

    async def h(request):
        seen.append(request.headers.get("Cookie"))
        return web.json_response({})

    app = web.Application()
    app.add_routes([web.get("/api/status", h)])
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(app), internal_secret="s", cookie="sid=abc"))
    await kc.get_status()
    await kc.close()
    assert seen == ["sid=abc"]


def _token_server(state):
    """Fake gateway: /api/token/local mints TOK<n>; other routes accept only TOK<accept>."""
    async def mint(request):
        if request.headers.get("X-Local-Secret") != "sek":
            return web.json_response({"code": "invalid_secret"}, status=403)
        state["mints"] += 1
        state["ttl"] = request.query.get("ttl")
        return web.json_response({"token": f"TOK{state['mints']}", "expires_in": 72000})

    async def guarded(request):
        cookie = request.cookies.get(f"mc_token_{request.url.port}")
        state["seen"].append((request.path_qs, cookie))
        if cookie != f"TOK{state['accept']}":
            return web.Response(status=403)
        return web.json_response({"ok": True})

    app = web.Application()
    app.add_routes([web.get("/api/token/local", mint), web.get("/api/status", guarded),
                    web.post("/api/approvals/{id}/{action}", guarded)])
    return app


async def test_token_minted_reused_and_sent_as_cookie(aiohttp_server, cfg, monkeypatch):
    from crewmate import kirocrew
    state = {"mints": 0, "accept": 1, "seen": []}
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(_token_server(state)), internal_secret="sek"))
    t = [1000.0]
    monkeypatch.setattr(kirocrew, "_now", lambda: t[0])
    await kc.get_status()
    await kc.get_status()
    assert state["mints"] == 1 and state["ttl"] == "20h"
    assert state["seen"] == [("/api/status", "TOK1")] * 2
    t[0] += 241  # past the 4 min reuse window
    state["accept"] = 2
    await kc.get_status()
    assert state["mints"] == 2 and state["seen"][-1] == ("/api/status", "TOK2")
    await kc.close()


async def test_token_reminted_after_403(aiohttp_server, cfg):
    state = {"mints": 0, "accept": 1, "seen": []}
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(_token_server(state)), internal_secret="sek"))
    await kc.get_status()
    state["accept"] = 2  # gateway restarted: TOK1 no longer valid
    assert await kc.get_status() == {"ok": True}
    assert state["mints"] == 2 and state["seen"][-2:] == [("/api/status", "TOK1"), ("/api/status", "TOK2")]
    await kc.close()


async def test_token_on_state_decision_keeps_origin_params(aiohttp_server, cfg):
    state = {"mints": 0, "accept": 1, "seen": []}
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(_token_server(state)), internal_secret="sek"))
    await kc.decide(STATE_APPROVAL, "approve")
    await kc.close()
    assert state["seen"] == [("/api/approvals/ap%2F7/approve?origin=coordinator&slot=cron:n&instance=i1", "TOK1")]


async def test_mint_failure_sets_token_error_and_request_proceeds(aiohttp_server, cfg):
    state = {"mints": 0, "accept": 1, "seen": []}
    kc = KiroCrew(_cfg(cfg, await aiohttp_server(_token_server(state)), internal_secret="wrong"))
    try:
        await kc.get_status()
    except Exception:
        pass
    assert kc.token_error and state["seen"][0] == ("/api/status", None)  # went out without a token
    await kc.close()
