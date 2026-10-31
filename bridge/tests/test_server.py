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
    assert (await r.json())["crew_name"] == "Kiro Crew"
