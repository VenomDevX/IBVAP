# IBVAP — Deployment

## Local dev runbook (order matters)

```bash
# 1. Local Supabase (auth + user_profiles only). Config edits need a full restart:
npx supabase stop && npx supabase start
npx supabase migration up          # 20260906… init, 20260908…_rls_lockdown, 20260908…_grants
npx supabase status                # copy API URL / anon / service_role / JWT secret

# 2. Backend env
cp backend/.env.example backend/.env
#   SUPABASE_URL           = the API URL from `supabase status` (keep the SAME host
#                            spelling — 127.0.0.1 — in frontend/.env too)
#   SUPABASE_KEY           = anon key          SUPABASE_SERVICE_KEY = service_role key
#   SUPABASE_JWT_SECRET    = the "JWT secret"  (used for the static keys / HS256 fallback;
#                            real user tokens are ES256 and verified via the project JWKS)
#   SUPABASE_JWT_ISSUER    = leave BLANK unless it exactly matches a real token's `iss`
#   EVIDENCE_HMAC_KEY      = a long random string
#   SUPABASE_SERVICE_KEY  = service_role key (required; RBAC downgrades to 'operator' without it)
#   IBVAP_PORT            = 8002   (frontend NEXT_PUBLIC_API_BASE points here in dev)

# 3. Create login accounts (self-signup is disabled by design)
cd backend
IBVAP_ADMIN_PASSWORD='<strong pw>' IBVAP_OPERATOR_PASSWORD='<strong pw>' \n  python scripts/seed_users.py --defaults
#   creates admin@ibvap.local / operator@ibvap.local. If the *_PASSWORD env
#   vars are unset the script generates a strong password and prints it once.

# 4. Run
python main.py --port 8002                     # backend
cd ../frontend && npm run dev                   # http://localhost:3001

# Diagnose any auth problem end to end:
IBVAP_ADMIN_PASSWORD='<pw>' python backend/scripts/check_auth.py --backend http://127.0.0.1:8002
```

**"Email logins are disabled"** = GoTrue's email provider is off. `[auth.email] enable_signup`
in `supabase/config.toml` must be `true` (the CLI mis-reads `false` as *disable the whole
provider*); open registration is blocked separately by `[auth] enable_signup = false`. Restart
the stack after editing (`supabase stop && start` — config does not hot-reload).

## Docker (production mode)

```bash
docker compose up --build
#   frontend :80 -> nginx (:8080) -> backend (:8000 inside the network, not published)
```

The compose file runs the backend in **production** mode: `/docs` is off, the backend
is not published to the host, and it **refuses to start without `SUPABASE_JWT_SECRET`**.

Compose also requires **`POSTGRES_PASSWORD`** in the `.env` next to `docker-compose.yml`
(the password is no longer hardcoded). An existing `ibvap_db` volume was initialised with
the old default, so either set `POSTGRES_PASSWORD=ibvap_password` once and rotate it with
`ALTER USER ibvap PASSWORD '...'`, or recreate the volume.

## GPU (NVIDIA)

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Installs `requirements-cuda.txt` into the image and reserves the host GPU (needs the NVIDIA
Container Toolkit; Docker Desktop on WSL2 includes it). Without this override the container
runs inference on CPU. TensorRT `.engine` files are tied to the GPU model and TensorRT
version that built them. If the engine fails at startup, re-run `scripts/export_tensorrt.py`
inside the container, or clear `detection.engine_path` in `configs/thresholds.yaml` (and move
any `.engine` next to the weights) so the `.pt` weights are used.

## With TLS (real deployment)

```bash
mkdir certs && cp fullchain.pem privkey.pem certs/     # or letsencrypt output
docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build
#   :443 HTTPS, :80 -> 301 redirect. Sets HSTS and TRUSTED_PROXY=1.
```

## Operations

| Task | Command |
|---|---|
| Verify evidence chain | `python scripts/verify_evidence_chain.py` |
| Enforce retention (`configs/retention.yaml`: rows, snapshots, clips) | `python scripts/purge_expired.py` (cron; `--dry-run` first) |
| Cap evidence clip disk use | `configs/thresholds.yaml → evidence.max_clips_per_hour / max_clip_storage_mb / min_free_storage_mb` |
| Point the detector at trained weights | `configs/thresholds.yaml → detection.weights_path` |
| Reset the DB (destructive, blocked in prod) | `python scripts/reset_db.py --yes` |

## Still open (see `docs/SECURITY_AUDIT_2026-09-08.md`)

- Rotate the Supabase anon key + JWT secret; `git filter-repo` to purge the old
  values from history (they were committed and later removed cosmetically).
- Move the Supabase session out of `localStorage` (needs a BFF/cookie model).
- Replace the WebSocket `?token=` with a signed short-lived ticket.
- `EVIDENCE_HMAC_KEY` should come from a KMS, and the chain head should be
  periodically anchored to external WORM storage for true chain-of-custody.
