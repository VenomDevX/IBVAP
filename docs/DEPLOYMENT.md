# IBVAP — Deployment

## Local / SIH demo (no TLS)

```bash
# 1. Supabase (auth + user_profiles only)
npx supabase start
npx supabase migration up           # includes 20260908181145_rls_lockdown.sql

# 2. Backend env
cp backend/.env.example backend/.env
#   set SUPABASE_URL, SUPABASE_KEY (anon), SUPABASE_SERVICE_KEY (service_role),
#       SUPABASE_JWT_SECRET, EVIDENCE_HMAC_KEY (long random)

# 3. Seed operator accounts (signup is disabled)
cd backend
python scripts/seed_users.py --email admin@ibvap.local    --password '<pw>' --role admin
python scripts/seed_users.py --email operator@ibvap.local --password '<pw>' --role operator

# 4. Run
docker compose up --build
#   frontend on :80 -> nginx (:8080) -> backend (:8000, not published)
```

The compose file runs the backend in **production** mode: `/docs` is off, the backend
is not published to the host, and it **refuses to start without `SUPABASE_JWT_SECRET`**.

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
| Enforce retention (`configs/retention.yaml`) | `python scripts/purge_expired.py` (cron; `--dry-run` first) |
| Point the detector at trained weights | `configs/thresholds.yaml → detection.weights_path` |
| Reset the DB (destructive, blocked in prod) | `python scripts/reset_db.py --yes` |

## Still open (see `docs/SECURITY_AUDIT_2026-09-08.md`)

- Rotate the Supabase anon key + JWT secret; `git filter-repo` to purge the old
  values from history (they were committed and later removed cosmetically).
- Move the Supabase session out of `localStorage` (needs a BFF/cookie model).
- Replace the WebSocket `?token=` with a signed short-lived ticket.
- `EVIDENCE_HMAC_KEY` should come from a KMS, and the chain head should be
  periodically anchored to external WORM storage for true chain-of-custody.
