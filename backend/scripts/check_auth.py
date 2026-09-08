"""
check_auth.py — end-to-end auth diagnostic.

Walks every layer between the browser and an authenticated /api call and prints
a checklist with the fix for each failure.

  python scripts/check_auth.py --email admin@ibvap.local --password admin123
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND, ".env"))
except Exception:
    pass

import jwt

OK, BAD, WARN = "  OK  ", " FAIL ", " WARN "
_fails = []


def line(status, msg, fix=""):
    print(f"[{status}] {msg}")
    if status == BAD and fix:
        print(f"        fix: {fix}")
        _fails.append(msg)


def http(method, url, headers=None, body=None, timeout=8):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="admin@ibvap.local")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--backend", default=f"http://127.0.0.1:{os.getenv('IBVAP_PORT', '8000')}")
    args = ap.parse_args()

    sb_url = (os.getenv("SUPABASE_URL") or "http://127.0.0.1:54321").rstrip("/")
    anon = os.getenv("SUPABASE_KEY", "")
    secret = os.getenv("SUPABASE_JWT_SECRET", "")
    service = os.getenv("SUPABASE_SERVICE_KEY", "")
    want_iss = os.getenv("SUPABASE_JWT_ISSUER", "").strip()

    print(f"SUPABASE_URL = {sb_url}")
    print(f"backend      = {args.backend}\n")

    # 1. stack up
    st, resp = http("GET", f"{sb_url}/auth/v1/health")
    if st == 200:
        line(OK, f"Supabase auth reachable ({json.loads(resp).get('version','?')})")
    else:
        line(BAD, f"Supabase auth NOT reachable: {resp}",
             "run `npx supabase start`; check SUPABASE_URL host matches `supabase status` API_URL")
        _summary(); return

    # 2. email provider
    st, resp = http("GET", f"{sb_url}/auth/v1/settings", {"apikey": anon})
    settings = json.loads(resp) if st == 200 else {}
    email_on = settings.get("external", {}).get("email")
    if email_on:
        line(OK, "email provider enabled")
    else:
        line(BAD, "email provider DISABLED (login impossible)",
             "set [auth.email] enable_signup = true in supabase/config.toml, then "
             "`npx supabase stop && npx supabase start`")
    if settings.get("disable_signup"):
        line(WARN, "self-signup disabled ([auth] enable_signup=false) — expected; existing users still log in")

    # 3. JWT secret matches the stack
    if secret and anon:
        try:
            jwt.decode(anon, secret, algorithms=["HS256"], options={"verify_aud": False})
            line(OK, "SUPABASE_JWT_SECRET verifies the stack's keys")
        except Exception as e:
            line(BAD, f"SUPABASE_JWT_SECRET does not match the stack: {e}",
                 "copy `JWT secret` from `npx supabase status` into backend/.env")
    else:
        line(WARN, "SUPABASE_JWT_SECRET or SUPABASE_KEY not set")

    # 4. password grant
    st, resp = http("POST", f"{sb_url}/auth/v1/token?grant_type=password",
                    {"apikey": anon, "Content-Type": "application/json"},
                    {"email": args.email, "password": args.password})
    token = None
    if st == 200:
        token = json.loads(resp).get("access_token")
        line(OK, f"password login works for {args.email}")
    else:
        err = json.loads(resp) if resp.startswith("{") else {"msg": resp}
        line(BAD, f"login failed for {args.email}: {err.get('msg') or err}",
             "if 'Email logins are disabled' -> fix #2 above; "
             "if 'Invalid login credentials' -> `python scripts/seed_users.py --defaults`")

    # 5. issuer
    if token:
        claims = jwt.decode(token, options={"verify_signature": False})
        iss = claims.get("iss")
        print(f"        token iss = {iss}")
        if want_iss and want_iss != iss:
            line(BAD, f"SUPABASE_JWT_ISSUER ({want_iss}) != token iss ({iss}) -> every /api call will 401",
                 f"set SUPABASE_JWT_ISSUER={iss} in backend/.env, or leave it blank")
        elif want_iss:
            line(OK, "SUPABASE_JWT_ISSUER matches the token")
        else:
            line(OK, "issuer check disabled (SUPABASE_JWT_ISSUER blank) — safe default")

    # 6. authenticated API call
    if token:
        st, _ = http("GET", f"{args.backend}/api/health")
        line(OK if st == 200 else BAD, f"backend /api/health -> {st}",
             f"start the backend: `python main.py` (port {os.getenv('IBVAP_PORT','8000')})")
        st, resp = http("GET", f"{args.backend}/api/cameras", {"Authorization": f"Bearer {token}"})
        if st == 200:
            line(OK, "authenticated GET /api/cameras -> 200")
        else:
            line(BAD, f"authenticated GET /api/cameras -> {st}: {resp[:120]}",
                 "check backend logs for 'JWT rejected'; usually an issuer/secret mismatch (fix #3/#5)")

    # 7. profile row / role
    if token and service:
        uid = jwt.decode(token, options={"verify_signature": False}).get("sub")
        st, resp = http("GET",
                        f"{sb_url}/rest/v1/user_profiles?id=eq.{uid}&select=role,allowed_areas",
                        {"apikey": service, "Authorization": f"Bearer {service}"})
        rows = json.loads(resp) if st == 200 and resp.startswith("[") else []
        if rows:
            line(OK, f"user_profiles row: role={rows[0].get('role')} areas={rows[0].get('allowed_areas')}")
        else:
            line(BAD, f"no user_profiles row for {args.email} -> resolves to 'operator', not admin",
                 "`npx supabase migration up` then `python scripts/seed_users.py --defaults`")

    _summary()
    if token:
        print(f"\naccess token (paste as Bearer for manual testing):\n{token}")


def _summary():
    print("\n" + "=" * 60)
    if _fails:
        print(f"{len(_fails)} problem(s) — see 'fix:' lines above.")
        sys.exit(1)
    print("All checks passed. Login should work end to end.")


if __name__ == "__main__":
    main()
