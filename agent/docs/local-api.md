# Local API v2: contract between rMirror.app (Swift) and rmirror-core (Python)

Status: agreed contract for rMirror for Mac 2.0. The Swift app is built against this document and the core
implements it. Change the document first, then both sides.

The legacy routes (`/api/status`, `/api/notebooks/tree`, …) and the Flask-rendered page stay as they are for the
legacy menu-bar mode. The native app uses **only** `/api/v2/*`, `/health`, `/auth/bridge` and `/auth/callback`.

## Process contract

The app starts the core as a plain child process:

```
<bundle>/Contents/Resources/core/rmirror-core --headless
```

| Aspect | Rule |
|---|---|
| Mode | `--headless`: no menu bar (rumps is never imported), no browser launch, no console prompts. Web server and sync loop only. |
| Environment | `RMIRROR_APP_TOKEN` (required in headless mode, 32+ random bytes, hex) and optional `RMIRROR_CONFIG_PATH`. |
| Listen address | `127.0.0.1` on `config.web.port` (default 5555). The port must stay fixed because the dashboard sign-in callback targets it. |
| Ready signal | One line on stdout once the server accepts connections: `RMIRROR_CORE_READY port=<port> api=2`. This is the only readiness signal: the app never treats an answer on the port as proof that its own core is ready, because another process could be listening there. |
| Parent watch | The core reads stdin on a background thread. EOF means the app is gone: shut down cleanly and exit 0 within 5 seconds. The app keeps the write end open for its whole life and never writes to it. |
| Stop | `SIGTERM` → clean shutdown (existing `Agent.shutdown()`), exit 0. |
| Exit codes | `0` clean stop · `3` port already in use (another rMirror is running) · `4` missing or too-short `RMIRROR_APP_TOKEN` · `1` anything else. |
| Logs | Unchanged: `~/.config/rmirror/agent.log`. Nothing sensitive on stdout/stderr. |

## Request rules

- Every `/api/v2/*` request must carry `X-RMirror-App-Token: <RMIRROR_APP_TOKEN>`. Compare in constant time.
  Missing or wrong → `401` with error code `bad_app_token`. This is in addition to the existing Host/Origin checks.
- `/health`, `/auth/bridge` and `/auth/callback` take no app token (the browser calls them). Their existing
  protections (one-time state, callback validation) are unchanged.
- JSON in, JSON out, UTF-8. Timestamps are ISO 8601 UTC strings or `null`.
- Errors: non-2xx with

```json
{"error": {"code": "not_signed_in", "detail": "technical text for the log, never shown to users"}}
```

Error codes: `bad_app_token` (401) · `not_signed_in` (401) · `invalid_request` (400) · `sync_already_running` (409)
· `core_not_ready` (503) · `cloud_timeout` (504) · `cloud_error` (502) · `internal` (500).

The core never returns user-facing sentences in v2. It returns codes and numbers; the app owns all wording.

## Endpoints

### `GET /api/v2/state`

The one call the app polls (every 2 s while a window is open, every 15 s otherwise). Must be cheap: no cloud
round-trip on the request path. Quota comes from a cache the core refreshes itself (at sign-in, after each
upload batch, and at most every 5 minutes).

```json
{
  "api_version": 2,
  "core_version": "2.0.0",
  "auth": {"signed_in": true, "email": "user@example.com", "sign_in_required": false},
  "environment": {"name": "production", "api_url": "https://rmirror.io/api/v1", "dashboard_url": "https://rmirror.io"},
  "folder": {"path": "/Users/x/Library/Containers/com.remarkable.desktop/…/desktop", "state": "ok"},
  "watcher": {"state": "running", "observer_alive": true, "last_event_at": null, "last_rescan_at": "2026-11-23T08:00:00Z"},
  "queue": {"pending": 0, "running": true, "paused_reason": null},
  "quota": {"used": 4, "limit": 200, "remaining": 196, "reset_at": "2026-12-01T00:00:00Z", "fetched_at": "2026-11-23T08:00:00Z"},
  "first_sync": {"completed": false},
  "sync": { "…same object as GET /api/v2/sync/progress…": 0 },
  "last_upload_at": null
}
```

- `auth.sign_in_required`: the stored sign-in was rejected by the cloud; the user must sign in again.
- `environment.name`: `production` | `staging` | `custom`.
- `folder.state`: `ok` | `missing` (path does not exist: reMarkable desktop app not installed or never synced)
  | `unreadable` (path exists but listing it raises a permission error: macOS privacy protection).
  The core re-checks on every call; this is what makes the permission screen clear itself.
- `watcher.state`: `idle` | `starting` | `running`.
- `queue.paused_reason`: `null` | `sign_in` | `quota` | `rate_limited` | `offline`. `sign_in` and `quota` are the
  queue's pauses; `rate_limited` (waiting for Retry-After) and `offline` (waiting to retry a network or 5xx error)
  are shown while the worker waits and clear by themselves.
- `quota`: `null` when signed out or never fetched. `limit` `-1` means unlimited, then `remaining` is `null`.
- `first_sync.completed`: true once any page has been uploaded for the current API host (decide from the upload
  manifest; do not add a new config location).

### `GET /api/v2/notebooks`

Flat list; the app does grouping, search and sorting.

```json
{
  "folder_state": "ok",
  "sync_all": false,
  "notebooks": [
    {"uuid": "…", "name": "Meeting Notes", "folder_path": ["Work", "2026"], "document_type": "notebook",
     "page_count": 12, "last_opened_at": "2026-11-20T10:00:00Z", "last_modified_at": "2026-11-20T10:05:00Z",
     "selected": true, "synced_pages": 12}
  ]
}
```

- Documents only (no folder entries, no trashed items). `folder_path` is the chain of parent folder names.
- `synced_pages`: pages already recorded in the upload manifest for the current host (0 if unknown).

### `PUT /api/v2/selection`

Body `{"sync_all": false, "selected_notebooks": ["uuid", …]}`. Persists to the config. Same semantics as the
legacy selection route, including baselining of unselected notebooks. Returns `{"ok": true}`.

### `GET /api/v2/first-run/suggestion?max=3`

The most recently opened notebooks (fall back to last modified) that together fit the remaining quota.

```json
{
  "notebooks": [{"uuid": "…", "name": "Meeting Notes", "page_count": 12}],
  "total_pages": 23,
  "quota": {"limit": 200, "remaining": 196},
  "reason": "ok"
}
```

- Never suggest more pages than `remaining`. Skip a notebook that does not fit and try the next one.
- `reason`: `ok` | `no_notebooks` | `quota_exhausted` | `not_signed_in` | `folder_unavailable`. With any reason
  other than `ok`, `notebooks` is empty.
- Unlimited quota: any `max` notebooks fit; `quota.remaining` is `null`.

### `POST /api/v2/sync/start`

Body `{"notebook_uuids": ["…"], "page_limit": null}`. Both optional.

- With `notebook_uuids`: save them as the selection (`sync_all` false), then start the initial sync. One request,
  no separate save step.
- Without: sync the current selection.
- `page_limit`: integer ≥ 1 sets and persists the page limit for this and later syncs. Omitted (or `null`): keep the limit already saved. To remove a limit use `PUT /api/v2/settings` with `"page_limit": null`.
- Reuses the existing initial-sync job. `202 {"ok": true}` on start; `409 sync_already_running`; `401 not_signed_in`.

### `GET /api/v2/sync/progress`

```json
{
  "state": "running",
  "outcome": null,
  "counts": {"uploaded": 4, "failed": 0, "left_out_by_page_limit": 0, "will_retry": 0,
             "notebooks_done": 1, "notebooks_total": 3, "pages_total": 23},
  "started_at": "2026-11-23T08:00:00Z",
  "finished_at": null
}
```

- `state`: `idle` | `running` | `done`.
- `outcome` (when `done`): `success` | `partial` (some pages failed) | `stopped_quota` | `stopped_sign_in` | `failed`.
- `will_retry`: pages deferred because the cloud asked to slow down. `pages_total` may be `null` if unknown.
- Every key of `counts` is always present (zeros while idle; `pages_total` `null` while idle or when the sync
  was not started through `/api/v2/sync/start`).
- `outcome` mapping: `stopped_quota` / `stopped_sign_in` when the content sync ran out of quota or lost its
  sign-in; otherwise `success` when no page failed (rate-limited pages count as `will_retry`, not as failed),
  `failed` when pages failed and none was uploaded (or the job itself crashed), `partial` otherwise.

### `POST /api/v2/sync/resume`

Resume a paused queue (what legacy "Sync Now" does). `{"ok": true}`.

All "ok" style responses are exactly `{"ok": true}` (plus `needs_sign_in` for `PUT /api/v2/settings`).

### `GET /api/v2/settings` · `PUT /api/v2/settings`

```json
{
  "page_limit": null,
  "source_directory": "/Users/x/Library/Containers/…/desktop",
  "environment": {"name": "production", "api_url": "https://rmirror.io/api/v1"},
  "environment_presets": {"production": "https://rmirror.io/api/v1", "staging": "https://staging.rmirror.io/api/v1"}
}
```

`PUT` accepts any subset of `page_limit`, `source_directory`, `environment` (`{"name": "custom", "api_url": "…"}`).
It always returns `{"ok": true, "needs_sign_in": true|false}` (`true` when no sign-in is stored for the current host).
Changing the environment keeps the existing behaviour (per-host sign-in, per-host manifest) and returns
`{"ok": true, "needs_sign_in": true|false}`.

### `POST /api/v2/auth/sign-out`

Removes the stored sign-in for the current host and stops the watcher. `{"ok": true}`.

### `GET /api/v2/deleted-notebooks` · `POST /api/v2/deleted-notebooks/<uuid>`

Same data as the legacy routes, reshaped:
`{"deleted_notebooks": [{"uuid": "…", "name": "…", "deleted_at": "<iso or null>"}]}` (empty list when signed out).
`POST` body `{"action": "resync" | "dismiss"}` returns `{"ok": true}`.

### `GET /api/v2/update-check`

Fallback when Sparkle is not configured. Same data as legacy `/api/updates/check`:
`{"has_update": false, "current_version": "2.0.0", "latest_version": "2.0.0", "download_url": null}`.

## Sign-in in headless mode

1. The app opens `http://localhost:<port>/auth/bridge` in the default browser. Unchanged.
2. The dashboard returns to `/auth/callback?state=…&token=…`. Validation and keychain storage unchanged.
3. On success in headless mode the callback renders a small page ("You're signed in. You can close this tab.")
   that also tries to open `rmirror://signed-in` so the app comes to the front. It does **not** redirect to `/`.
   On failure it renders the existing result page with plain wording and no technical terms.
4. The app notices `auth.signed_in` on its next state poll and moves on. The `rmirror://` link is a convenience,
   never a carrier of secrets.

## Removed in 2.0 (issue #47)

- Password sign-in: the `/auth/login` fallback in `cloud_sync.py` and the related UI. Old config keys
  (`email`, `password`, `use_clerk_auth`) are ignored on load without failing.
