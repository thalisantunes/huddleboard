# bridge

Python service that aggregates KiroCrew (and optionally painel-tmux), renders the 800x480
7-color frame and serves it to the e-paper device. See the root README for the architecture.

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `KIROCREW_URL` | `http://127.0.0.1:5476` | KiroCrew gateway |
| `KIROCREW_INTERNAL_SECRET` | file below | `X-Internal-Secret` value |
| `KIROCREW_COOKIE` | empty | optional `Cookie` header (plan B, see below) |
| `KIROCREW_WS` | `0` | `1` = recollect on any WebSocket message |
| `PAINEL_TMUX_URL` / `PAINEL_TMUX_TOKEN` | empty | optional painel-tmux provider |
| `DEVICE_TOKENS` | empty | comma-separated Bearer tokens accepted from devices |
| `POLL_SECONDS` / `REFRESH_SECONDS` / `REFRESH_SECONDS_URGENT` | 60 / 300 / 180 | poll and device refresh |
| `INPUT_RECENT_MINUTES` | `30` | slots waiting for input count as urgent (badge, 180 s refresh) only if active this recently |
| `FIXTURES` | `0` | `1` = read `fixtures/*.json` instead of KiroCrew |
| `BIND` / `PORT` | `127.0.0.1` / `5480` | listen address |

## KiroCrew auth

The bridge authenticates to KiroCrew only with `X-Internal-Secret`. The value comes from
`KIROCREW_INTERNAL_SECRET` or, when empty, from `$KIROCREW_HOME/.local_secret`
(default `~/.kiro/crew/.local_secret`). The gateway generates a new secret on every
restart, so the bridge rereads the file on 401/403 and retries once.

**Known risk, untested against a real gateway.** `_internal_session_approval_refusal`
(`slot_approval.py:49-68` in KiroCrew) may refuse the internal secret when approving through
`/api/chat/slots/{slot}/approve` and `/api/approvals/{id}/{action}`; the code path for
`origin=coordinator` seems to accept it, contradicting the docstring. Listing slots and
stopping them is expected to work. If approvals are refused, plan B is to set
`KIROCREW_COOKIE` to the owner's session cookie; the bridge then sends it as a `Cookie` header
and does nothing else with it.

## Notes

- A consumed `screen_id` accepts no retry. After an upstream failure the device gets a 502
  and must fetch a new `/api/display`.
- Whether the WebSocket accepts `X-Internal-Secret` alone as the owner is unconfirmed; if not,
  the bridge only sees what a non-owner sees and the poll loop is the fallback.
- `TRUSTED_PROXY_CIDR` (empty = off): requests from a peer in this CIDR that carry
  `Cf-Access-Authenticated-User-Email` count as authenticated for `/`, `/preview.png`,
  `/api/model.json`, `/api/display` and `/api/action`. Set it only when the bridge is reachable
  solely through that proxy, since the header is otherwise forgeable. `GET /` is the live preview page.
