# ADR-001 — Application datastore: SQLite (canonical), Postgres for auth only

**Status:** Accepted (2026-09-09) — closes the open decision in TRD §17 and
audit item #1 in `SECURITY_AUDIT_2026-09-08.md`.

## Context

Two schemas existed in parallel:

- **SQLite** (`backend/src/database/models.py`, SQLAlchemy) — created on first
  run, `DATABASE_URL`-overridable. The pipeline, the API's `Repository`, evidence
  hashing, audit logging and retention all read/write here. `docker-compose.yml`
  sets `DATABASE_URL=sqlite:////app/data/ibvap.db`.
- **Postgres** (`supabase/migrations/`) — `cameras / tracks / events / alerts /
  zones` tables plus a realtime publication and RLS policies. **Nothing writes
  to these.** The RLS-lockdown migration therefore protected empty tables while
  the populated SQLite store had no row-level control (audit C3).

## Decision

**SQLite is the single source of truth for all application data** (cameras,
tracks, events, alerts, zones, audit log, evidence metadata).

**Postgres (Supabase-hosted) is used only for authentication identity** — the
`user_profiles` table (role + `allowed_areas`), read by the service-role client
in `src/api/auth.py`. Access scoping is enforced in the API layer
(`scoped_cameras`, `require_role`), not by Postgres RLS, because the data it
would protect does not live in Postgres.

## Consequences

- The `cameras / tracks / events / alerts / zones` tables and the realtime
  publication in `supabase/migrations/20260906000000_init.sql` are **vestigial**.
  They are kept for reference / a possible future migration but are marked
  unused in that file's header. Do **not** rely on Supabase realtime for alerts —
  the WebSocket (`/ws/alerts`) is the only live channel.
- "Two divergent evidence stores" (audit C3) is resolved: there is one store.
- Moving to Postgres later means: point `DATABASE_URL` at it, run the SQLAlchemy
  models against it (they are dialect-neutral), backfill, then real RLS keyed on
  `auth.uid()` + `allowed_areas` becomes worthwhile. Not planned.
- SQLite is configured for the 24/7 workload: WAL, `busy_timeout=5s`,
  `synchronous=NORMAL` (audit H4).
