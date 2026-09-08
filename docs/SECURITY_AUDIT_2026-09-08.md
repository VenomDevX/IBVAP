# IBVAP — Security & Robustness Audit (2026-09-08)

Audit of the FastAPI backend, React frontend, Supabase layer, and Docker deployment.
Findings are de-duplicated from three parallel reviews. Severity accounts for this being a
border-surveillance system whose output is intended for legal proceedings.

Status legend: **[PLANNED]** done this pass · **[NEEDS DECISION]** blocked on a product/deploy call · **[TODO]** safe but not yet done

---

## CRITICAL

### C1 — `/snapshots` evidence images served with zero authentication  **[FIXED]**
`backend/src/api/app.py` mounted `StaticFiles` at `/snapshots` with no guard. Every other route is
gated; this one served ~630 real JPEGs of detected people / vehicles / plates. Filenames are
predictable (`{camera_id}_{event_id}_{unix_ts}.jpg`) and `nginx.conf` cached them `public, 6M`.
Fix: replaced with an authenticated route (`require_auth`) that resolves a filename **inside** the
snapshots dir only (path-traversal safe) and sends `Cache-Control: private, no-store`.

### C2 — `require_admin` is decorative; there is no application RBAC  **[FIXED]**
`auth.py` reads the JWT `role` claim, which Supabase sets to the literal `"authenticated"` for
every human user. The real role lives in `user_profiles.role` and is **never read anywhere in the
backend**. `allowed_areas` (per-user camera scoping) is defined in 3 places and read in 0.
Consequences: real admins get 403 on the zone endpoints; every authenticated user has identical
full access; the 3-tier operator / supervisor / admin model exists only in the schema.
Fix needs a Supabase service-role client to look up `user_profiles.role` (cached). Ties into C3.

### C3 — Supabase RLS is `USING (true)` for `authenticated` on every table  **[FIXED]** (RLS lockdown migration; datastore = SQLite)
`supabase/migrations/...init.sql` grants every logged-in user SELECT on `cameras` (incl. GPS +
RTSP URLs), `events`, `alerts`, `zones`, and **`user_profiles`** (everyone's UUID / role / name).
`alerts` + `events` are in the realtime publication, so any user can subscribe to the live alert
firehose straight off PostgREST — bypassing the API, its auth, rate-limiting and logging entirely.
Compounding: the pipeline actually writes to **SQLite**, not Postgres, so the RLS protects empty
tables while the populated store has no row-level control at all. Two divergent evidence stores
(`docker-compose` sets `DATABASE_URL` to Postgres; `python main.py` uses SQLite).
Fix: pick one datastore, then real policies keyed on `auth.uid()` + `allowed_areas`.

### C4 — Open self-registration -> stranger gets full operator access  **[FIXED]**
`[auth] enable_signup = false` blocks the signup endpoint; the `/signup` page is dev-build-only; accounts are provisioned by `scripts/seed_users.py`. NOTE: `[auth.email] enable_signup` must stay `true` — the CLI otherwise disables ALL email login. Regression fixed 2026-09-08.
`supabase/config.toml`: `enable_signup = true`, `enable_confirmations = false`, captcha commented
out. `frontend/src/pages/Signup.tsx` synthesizes `<username>@ibvap.local` so no real mailbox is
needed. No approval step, no domain allow-list, no `user_profiles` row created. An attacker
self-provisions in seconds; every `require_auth` endpoint then accepts the token: live video,
camera coordinates, all alerts / events / tracks / zones, the audit log, and the ability to mark
alerts "reviewed" (suppressing operator attention during a real intrusion).
If this is a judged demo you may want signup on temporarily — but it must be `false` for any real
or networked deployment, with operators provisioned by invite.

### C5 — `user["username"]` KeyError breaks alert-review & zone endpoints  **[FIXED]**
`require_auth` returns `{token, user_id, email, role}` — no `username`. `alerts.py` and `zones.py`
call `user["username"]` **after** the DB mutation has committed -> the alert is marked reviewed,
then the request 500s, the audit row is never written, and the session leaks. The `.get()`
fallback also let the client choose the `reviewed_by` attribution.
Fix: switched to `user.get("email")`, wrapped sessions in `try/finally`, dropped the
client-controlled `reviewed_by` field.

### C6 — Live alerting is silently dead (`broadcast_sync` no-op)  **[FIXED]**
`websocket.py::broadcast_sync` did `asyncio.get_event_loop()` on the camera worker thread, caught
the `RuntimeError`, and `pass`ed — so **operators received zero live alerts**. Frontend
`useWebSocket.ts` also never sent `?token=`, so every socket was rejected + reconnect-stormed.
Fix: backend captures the main loop at startup and uses `run_coroutine_threadsafe`; frontend sends
the Supabase access token in `?token=` (the backend only accepts it that way today).
Interim mitigation applied: `access_log off` for `/ws/` in nginx.conf so the token is not
persisted. **Proper fix (deferred):** a WS subprotocol header `new WebSocket(url, ['bearer', token])`
validated server-side, or a short-lived single-use ticket from an authenticated endpoint —
both touch the backend WS handler. Tracked under Decisions / Out-of-scope.

### C7 — Unbounded `_tracks` dict -> guaranteed OOM + FPS decay on a 24/7 run  **[FIXED]**
`MultiObjectTracker._tracks` never deleted entries; `_age_tracks` only flipped `is_active`, and the
per-frame loop iterated the entire history. Memory and per-frame CPU grew without bound.
Fix: inactive tracks past a TTL are evicted; the per-frame iteration is bounded.

### C8 — `supervision>=0.18.0` unpinned; `ByteTrack` removed in v0.31  **[FIXED]**
`tracker.py` calls `sv.ByteTrack(...)` outside the import guard. Any clean `pip install` that
resolves 0.31+ makes the app refuse to start.
Fix: pinned `supervision==0.30.2`; wrapped the `sv.ByteTrack(...)` construction so a missing class
degrades to basic mode instead of crashing boot.

### C9 — Every HTTP response 500s with the installed Starlette  **[FIXED]**
Found while verifying Phase 1. `backend/src/api/middleware/security.py` called
`response.headers.pop("server", None)` — `MutableHeaders` has **no `.pop()`** in Starlette 1.6.0
(the version `fastapi>=0.104` resolves). `SecurityHeadersMiddleware` raised `AttributeError` on
every response; `RequestLoggingMiddleware` logged it and re-raised -> **the API returned 500 to
every request**, including `/api/health`. (The old log files predate this Starlette bump.)
Fix: guarded `del response.headers["server"]`. Underscores the H14 point — pin the deps.


---

## HIGH

| # | Finding | Status |
|---|---|---|
| H1 | `snapshot_hash` computed, returned by the API, but **never persisted** (`repository.create_alert` omits it) | **[FIXED]** |
| H2 | 9 more unbounded collections grow forever | **[FIXED]** deque(maxlen) + TTL-pruned cooldown dicts |
| H3 | Plaintext generated password would be logged if the dead `_create_default_users` path were revived | **[FIXED]** path deleted (local `users` table unused; auth is Supabase) |
| H4 | Threaded SQLite, no WAL / busy-timeout -> dropped evidence under load | **[FIXED]** WAL + 5s busy_timeout + synchronous=NORMAL |
| H5 | SQL bound-parameters written verbatim into logs on query error | **[FIXED]** `hide_parameters=True` |
| H6 | Raw PyJWT exception text returned to unauthenticated callers (signature vs. expiry vs. audience oracle) | **[FIXED]** |
| H7 | JWT: no issuer binding / no required-claims check | **[FIXED]** issuer + require:[exp,sub,aud]; revocation still bounded by exp (documented) |
| H8 | `X-Forwarded-For` trusted unconditionally | **[FIXED]** only when `TRUSTED_PROXY=1`; whitespace-stripped, 64-char cap |
| H9 | `scripts/reset_db.py` — unguarded, irreversible `drop_all()` + `create_all()` | **[FIXED]** (type-RESET confirm / `--yes`, blocked when `IBVAP_ENV=production`) |
| H10 | `events.py` `offset` has no `ge=0` and no upper bound | **[FIXED]** |
| H11 | `notifiers.py` unbounded thread/alert, no SMTP timeout | **[FIXED]** 2-worker pool + 10s timeout + redacted contact logging |
| H12 | No TLS — bearer JWTs cleartext | **[PARTIAL]** `frontend/nginx-tls.conf` + `docker-compose.tls.yml` + `docs/DEPLOYMENT.md` ready (HSTS, redirect, TRUSTED_PROXY); needs a cert at deploy time |
| H13 | Supabase session (incl. refresh token) in `localStorage` | **[NEEDS DECISION]** needs a BFF/cookie model — larger change |
| H14 | All backend deps are `>=` lower bounds, no lockfile; `roboflow` / `paddlepaddle` / `paddleocr` / `insightface` declared but **never imported by the runtime** (~GB of attack surface for zero function) | **[PLANNED]** (split into `requirements-training.txt`; runtime deps pinned `==`) |
| H15 | Compose shipped dev mode / no secrets / backend on host | **[FIXED]** IBVAP_ENV=production, env_file, expose(not ports), healthcheck, no-new-privileges, cap_drop, mem limit; prod boot-asserts on missing SUPABASE_JWT_SECRET |
| H16 | Frontend build had no Supabase env -> dummy key | **[FIXED]** Dockerfile build args via compose; supabase.ts fails loud; base image nginx-unprivileged |
| H17 | `/api/audit` any-operator readable; audit trail never written | **[FIXED]** route -> require_role('auditor'); `RequestLoggingMiddleware` now writes an `AuditLogModel` row for every successful mutating request + evidence read (actor from the token) |
| H18 | Zero tests, zero CI | **[PARTIAL]** starter suite (`test_auth_guards.py`, `test_core_logic.py`: risk-engine golden, evidence-chain tamper-detect, bounded-collections) + `.github/workflows/ci.yml`; not full coverage yet |
| H19 | Evidence "integrity" was only a data-quality check | **[FIXED]** append-only HMAC hash-chain over `events`/`alerts` (`src/alerts/evidence.py`, `scripts/verify_evidence_chain.py`); TRD/README amended to say tamper-EVIDENT not tamper-PROOF + KMS/anchoring recommended for prod |
| H20 | No retention/deletion (biometric/PII kept forever) | **[FIXED]** `configs/retention.yaml` + `scripts/purge_expired.py --dry-run` (rows + orphaned snapshot files); defaults snapshots/events 90-180d, identity/plate 30d, audit 2y |
| H21 | git history still contains the removed Supabase anon key + JWT-secret fallback + `admin123` | **[NEEDS DECISION]** (rotate keys; `git filter-repo` to purge) |
| H22 | MJPEG generator is a sync `while True` with no disconnect check — a handful of `/api/stream` requests exhaust the AnyIO threadpool and hang the whole API | **[PLANNED]** (disconnect check + frame cap) |

---

## MEDIUM  (hardening — lower blast radius)

- Rate limiter is one **global** bucket behind nginx (`get_remote_address` always sees the nginx IP); no per-route limits.
- `InputValidationMiddleware` — bypassable denylist (checks the still-encoded query string only, never request bodies), over-broad (`on\w+=` 400s `?online=true`), and `validate_image_file` / `sanitize_camera_id` are defined but never called.
- WebSocket: token in query string, payload discarded (no per-connection identity / scoping), no re-validation.
- Missing DB indexes on `events.camera_id`, `alerts.camera_id`, `alerts.reviewed`, `tracks.camera_id`, `audit_logs.username`; Postgres migration declares no indexes at all.
- nginx `add_header` inside the static-asset block voided the 5 server-level security headers. **[FIXED]** headers repeated in each `location` with `always`.
- nginx served `/snapshots/*.jpg` via the image-caching **regex** block (`Cache-Control: public, 6M`), overriding the backend's `no-store`. **[FIXED]** `location ^~ /snapshots/` now wins.
- `get_heatmap` runs a pure-Python loop over up to 50k points + a 41x41 GaussianBlur **on the event loop**, polled every 5s per visible camera.
- Docker: no `.dockerignore` -> `COPY . .` bakes `venv/`, `ibvap.db`, `*.pt`, and `.env` if present into an image layer; no `HEALTHCHECK`; app code `chown`ed writable by the runtime user; SQLite DB not on a volume -> lost on restart.
- `docker-compose.yml` has hardcoded `postgres:postgres` DSN, no resource limits, no `no-new-privileges` / `cap_drop`, frontend nginx runs as root.
- Session-timeout hook is per-tab and in-memory; a reload resets the 30-min clock; the already-issued access JWT stays valid ~1h after "logout" (no denylist).
- `notifiers.py` logs operator email + phone at INFO on every critical alert; SMTP uses opportunistic `starttls()` with no cert verification.
- CORS `allow_credentials=True` on a pure bearer API; default list has invalid `http://localhost:80`.
- Client-side-only role gating: `Settings.tsx` hardcodes `role='operator'`; `App.tsx` `ProtectedRoute` checks only `isAuthenticated` — no admin route guard.
- Dead `localStorage.getItem('ibvap_token')` reads in `HeatmapOverlay.tsx`; `Alerts.tsx` sends client-set `reviewed_by`.

---

## What is already done right (do not "fix" these away)

- **No SQL injection** anywhere in `backend/src/` — everything goes through SQLAlchemy ORM with bound params.
- `limit` capped at 500 on the list endpoints.
- JWT: `algorithms=["HS256"]` pinned (no `alg:none`), `audience="authenticated"`, fails closed when no secret is set.
- WebSocket authenticates before `accept()`.
- API docs disabled when `IBVAP_ENV=production`; TrustedHost + explicit CORS list + rate limiting + security headers all wired.
- `backend/Dockerfile` creates and runs as a non-root `appuser`.
- `.gitignore` is thorough; `.env` and `*.db` genuinely untracked; DB password masked in the init log.
- Good bounded-collection patterns already exist to copy: `Track.trajectory` (cap 500), `HeatmapTracker.points` (`deque(maxlen=50000)`), `FrameBuffer` (`deque(maxlen=...)`), `AlertEngine._rate_counter` (60s window prune).

---

## Decisions needed from you

1. **One datastore** — SQLite or Supabase/Postgres? Everything about RLS (C2 / C3) and "two evidence stores" hangs on this.
2. **Signup** — leave `enable_signup=true` for the judged demo, or lock it now?
3. **`require_admin`** — implement the real `user_profiles.role` lookup (needs a service-role key in the backend env)? Yes / no.
4. **TLS / deployment** (H12 / H15 / H16) — is there a real deployment target, or is this localhost-only for SIH? Determines how much nginx / compose hardening is worth doing now.
5. **Evidence integrity** (H19) — build real tamper-evidence (signing + hash chain + external anchor), or amend the TRD / README to describe the data-quality check that actually exists?
6. **Retention** (H20) — what window for snapshots / events / identity / plate results?
7. **Secret rotation** (H21) — rotate the Supabase anon key + JWT secret? (Recommended regardless.)
