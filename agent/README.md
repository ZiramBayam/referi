# agent/ — HTTP API

Two HTTP servers, both **loopback only**, both started by hand (`make demo` does not launch
them). This file documents the HTTP surface only; the reasoning behind the design lives in
each module's docstring.

## 1. The 402 gate — `POST /jobs/register`

Module `agent/payment_402.py` (ADR-010 — **not** x402). Run it:

```
cd agent && uv run python -m agent.payment_402 --host 127.0.0.1 --port 8000
```

In short: no payment → `402` plus `WWW-Authenticate: OnchainPayment …`; an
`Authorization: OnchainPayment tx="0x…"` header that verifies on-chain → `200`. Under
`DEMO_MODE` a dummy header passes, and the `200` labels itself (`X-Payment-Mode: demo`,
`verified_onchain: false`). Full details: `agent/agent/payment_402.py`.

## 2. Wipe the demo memory — `POST /demo/memory/reset`

Module `agent/demo_reset.py`. The "wipe memory" control in `/panel` calls it, so a judge
really deletes the file instead of reading an `rm` procedure.

**Without `DEMO_MODE` this endpoint does not exist.** Its route table is empty, so the path
answers `404` like any made-up path — not `403`. The gate fails closed: an env var that is
PRESENT but empty (`DEMO_MODE= uv run python -m agent.demo_reset`) means OFF and no longer
falls back to `.env` — that fallback used to turn it ON, because `.env` holds `DEMO_MODE=true`.

Run it:

```
cd agent && DEMO_MODE=1 uv run python -m agent.demo_reset --host 127.0.0.1 --port 8010
```

Without `DEMO_MODE` the process exits with code 1 and binds no port.

### Request

```
POST /demo/memory/reset
Host: 127.0.0.1:8010
Content-Type: application/json

{"db": "memory.db"}      # optional; empty body = "memory.db"
```

**REQUIRED headers** (cross-origin gate; a server-side caller satisfies them with no changes
at all):

| Header | Rule | Fails → |
|---|---|---|
| `Content-Type` | EXACTLY `application/json` (a `charset` parameter is allowed) | `415 unsupported_media_type` |
| `Host` | `127.0.0.1:<port>`, `localhost:<port>`, or `[::1]:<port>` — the port must be the server's port | `403 bad_host` |
| `Origin` | **must be absent entirely** (there is no origin allowlist) | `403 cross_origin_request` |
| `Sec-Fetch-Site` | may be absent; if present it must be `none`/`same-origin` | `403 cross_origin_request` |
| `Sec-Fetch-Mode` | may be absent; `no-cors`/`navigate`/`websocket` are rejected | `403 cross_origin_request` |

Why: "loopback only" is no defence against a browser — the judge's browser sits on loopback
too. One hostile tab with `<form method=POST action="http://127.0.0.1:8010/demo/memory/reset">`
sends `Content-Type: text/plain`, which is on the CORS safelist and therefore passes without
a preflight; the attacker never needs to read the reply, because the deletion already
happened. Requiring `application/json` forces a preflight, and the `OPTIONS` preflight here
answers `501` with no `Access-Control-Allow-*` header.

`db` is a **file name**, not a path: `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. Anything holding `/`,
`\`, `..`, NUL, or a space is rejected with `400`, and no file is touched. The working
directory is always `agent/data/demo/` — derived from the package root, never from the
request, and no env var can move it.

### `200` response

The sweep always covers three files: `<db>`, `<db>-wal`, `<db>-shm`.

```json
{
  "ok": true,
  "reason": "ok",
  "root": "data/demo",
  "db": "memory.db",
  "deleted": ["memory.db", "memory.db-wal", "memory.db-shm"],
  "missing": [],
  "refused": []
}
```

- `deleted` — files this call actually removed;
- `missing` — already gone (on a second call all three land here and `deleted` is empty —
  render "nothing was deleted");
- `refused` — present but NOT deleted, because it is a symlink or a directory.

`root` is a path RELATIVE to the agent package (`data/demo`); this reply crosses a proxy to
the browser, and the UI needs neither the judge's username nor their disk layout for anything.

`memory.db.lock` is DELIBERATELY left out of the sweep: it is not memory content but the
holder of the mutual-exclusion `flock`, and deleting it while another process holds the lock
produces two processes that both believe they hold it.

Calling it twice is legal and still returns `200`.

### Error responses

Every one takes the shape `{"ok": false, "reason": "<code>"}` — no path is echoed back.

| Status | `reason` | When |
|---|---|---|
| 404 | `not_found` | `DEMO_MODE` is off, or any other path |
| 405 | `method_not_allowed` | a method other than `POST` on a registered path |
| 400 | `invalid_db_name` | `db` fails the name pattern |
| 400 | `path_outside_demo_dir` | the result lands outside `agent/data/demo/` |
| 400 | `malformed_json` | the body is not a JSON object |
| 413 | `body_too_large` | body > 4 KiB |
| 415 | `unsupported_media_type` | `Content-Type` is not `application/json` |
| 403 | `cross_origin_request` | `Origin` is present, or `Sec-Fetch-*` marks a cross-origin context |
| 403 | `bad_host` | `Host` is not loopback + this server's port (e.g. DNS rebinding) |
| 500 | `delete_failed` | the file exists but deletion failed (e.g. permissions) |
| 500 | `root_is_symlink` | `agent/data/demo` turns out to be a symlink → zero deletions |
