import dataclasses
import logging

from aiohttp import web

from kcdeck import server

SECRETS = ("TOPSECRET123", "COOKIESECRET456", "OWNERTOKEN789")


async def test_credentials_never_logged(aiohttp_client, aiohttp_server, cfg, caplog):
    async def deny(request):
        return web.Response(status=403)

    async def mint(request):
        return web.json_response({"token": SECRETS[2]})

    fake = web.Application()
    fake.router.add_get("/api/token/local", mint)
    fake.router.add_route("*", "/{tail:.*}", deny)
    srv = await aiohttp_server(fake)
    c = dataclasses.replace(cfg, fixtures=False, kirocrew_url=f"http://127.0.0.1:{srv.port}",
                            internal_secret=SECRETS[0], cookie=f"sid={SECRETS[1]}")
    with caplog.at_level(logging.DEBUG):
        client = await aiohttp_client(server.make_app(c))  # startup recollect fails with 403
        sid = "s1"
        approval = {"kind": "slot", "id": "r", "slot": "x", "request_id": "r", "request_mid": "m",
                    "instance": "", "title": "t", "agent": "x"}
        client.app["state"]["valid"] = {sid: {"A": {"kind": "approve", "target_id": "r", "approval": approval}}}
        r = await client.post("/api/action", json={"screen_id": sid, "button": "A"},
                              headers={"Authorization": "Bearer tok"})
        assert r.status == 502
    text = "\n".join(f"{rec.getMessage()}\n{rec.exc_text or ''}" for rec in caplog.records
                     if rec.name != "aiohttp.access")  # the fake gateway's own access log is not ours
    assert "status 403" in text  # the failures were logged, just without credentials
    for secret in SECRETS:
        assert secret not in text
