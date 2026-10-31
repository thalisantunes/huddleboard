"""Live preview page: inline HTML, no framework, no external assets."""

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>crewmate</title>
<style>
  body { margin: 0; padding: 16px; background: #111; color: #ccc; font: 14px system-ui, sans-serif;
         display: flex; flex-direction: column; align-items: center; gap: 14px; }
  #frame { width: 100%; max-width: 840px; box-sizing: border-box; padding: 12px; background: #1c1c1c;
           border: 1px solid #333; border-radius: 12px; box-shadow: 0 4px 24px #000; }
  #img { display: block; width: 100%; height: auto; aspect-ratio: 800 / 480; background: #000; border-radius: 3px; }
  #status { text-align: center; }
  #buttons { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
  button { background: #2a2a2a; color: #eee; border: 1px solid #555; border-radius: 6px; padding: 10px 18px;
           font: inherit; cursor: pointer; }
  button:disabled { opacity: .35; cursor: default; }
</style>
</head>
<body>
<div id="frame"><img id="img" alt="e-paper preview"></div>
<div id="status">loading...</div>
<div id="buttons"></div>
<div id="msg"></div>
<script>
const $ = (id) => document.getElementById(id);
let screenId = null;

async function getJson(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

async function load() {
  $("img").src = "/preview.png?t=" + Date.now();
  try {
    const [m, d] = await Promise.all([getJson("/api/model.json"), getJson("/api/display")]);
    screenId = d.screen_id;
    const errs = m.errors && m.errors.length ? m.errors.join(", ") : "none";
    $("status").textContent = "updated " + m.updated_at + " \\u00b7 next refresh " + m.next_refresh_s + "s \\u00b7 errors: " + errs;
    const box = $("buttons");
    box.replaceChildren();
    for (const b of ["A", "B", "C"]) {
      const act = d.buttons[b] || "none";
      const el = document.createElement("button");
      el.textContent = b + " " + act;
      el.disabled = act === "none";
      el.onclick = () => press(b);
      box.appendChild(el);
    }
  } catch (e) {
    $("status").textContent = "error: " + e.message;
  }
}

async function press(button) {
  try {
    const r = await fetch("/api/action", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ screen_id: screenId, button }),
    });
    const j = await r.json().catch(() => ({}));
    $("msg").textContent = r.ok ? button + ": " + (j.result || "ok") : button + " failed (HTTP " + r.status + ")";
  } catch (e) {
    $("msg").textContent = "error: " + e.message;
  }
  load();
}

load();
setInterval(load, 30000);
</script>
</body>
</html>
"""
