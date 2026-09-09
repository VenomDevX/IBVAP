# Secret Rotation & Git-History Purge (audit item H21)

The repo's **current tree** no longer contains live secrets — only placeholders
(`backend/.env.example`) and, until now, the weak demo password `admin123` in a
few scripts/docs (removed in the accompanying change). Real secrets live only in
untracked `.env` files.

**Git history** still contains earlier states. Anyone with a clone (or the
GitHub repo, if it was ever pushed public) can read them. Two things to do:

---

## 1. Rotate the secrets (do this regardless of the history purge)

Rotation invalidates anything already leaked, so it's the higher-priority step.

| Secret | Where | How to rotate |
|---|---|---|
| **Supabase JWT secret** (`SUPABASE_JWT_SECRET`) | backend `.env` | Supabase dashboard → Project Settings → API → **JWT Settings → Generate new secret**. All existing sessions are invalidated (users re-login). Update `backend/.env` + your deploy env. |
| **`service_role` key** (`SUPABASE_SERVICE_KEY`) | backend `.env` | Same page → **Reveal / rotate `service_role`**. This key bypasses RLS — treat as root. Update backend `.env` + deploy env. |
| **`anon` key** (`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_KEY`) | frontend build env, backend `.env` | Same page → rotate `anon`. Lower urgency — the anon key is *designed* to be public and is only as strong as your RLS — but rotate it for hygiene. Rebuild the frontend, update backend `.env`. |
| **Demo account passwords** | Supabase Auth users | `python backend/scripts/seed_users.py --defaults` with `IBVAP_ADMIN_PASSWORD` / `IBVAP_OPERATOR_PASSWORD` set to strong values (or let it generate + print them once). |
| **SMTP / Twilio creds** (if configured) | backend `.env` | Rotate at the provider if the values ever appeared in a commit. |

After rotating, run `python backend/scripts/check_auth.py` to confirm login still works end to end.

---

## 2. (Optional) Purge the strings from history

Only worth doing if the repo is or will be shared and you want the old values
gone. **It rewrites every commit hash** — every existing clone must be re-cloned
or hard-reset, and any open PR must be recreated.

### Prerequisites
- `pip install git-filter-repo` (or `brew install git-filter-repo`)
- A fresh **mirror** clone: `git clone --mirror <url> ibvap-purge && cd ibvap-purge`
- Tell every collaborator to stop pushing until you're done.

### Run
```bash
# from the repo root
bash scripts/purge_git_secrets.sh
```
That script feeds `scripts/secret-replacements.txt` to `git filter-repo
--replace-text`. Edit that file first to add any real leaked values (the old
anon key / JWT secret string) — one `literal:<value>==><REDACTED>` per line.

### After
```bash
git push --force --mirror <url>          # from the mirror clone
# every collaborator:
git fetch origin && git reset --hard origin/main   # or re-clone
```
Then, on GitHub: Settings → **rotate any deploy keys / Actions secrets**, and
consider asking GitHub Support to expire cached views of old commits.

> If the repo has **never left this machine**, the purge is lower value than the
> rotation — a local-only history leak has no external reader.
