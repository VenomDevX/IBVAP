"""
seed_users.py — provision / reset login accounts (self-signup is locked).

Creates the Supabase auth user (or resets its password if it exists) and upserts
its application role + allowed_areas into `public.user_profiles`.

Env is auto-loaded from backend/.env — needs SUPABASE_URL and SUPABASE_SERVICE_KEY.
Run `npx supabase migration up` first so `user_profiles` exists.

Usage:
  python scripts/seed_users.py --defaults
      # admin@ibvap.local / operator@ibvap.local
      # Passwords come from IBVAP_ADMIN_PASSWORD / IBVAP_OPERATOR_PASSWORD.
      # If those are unset a strong random password is generated and printed ONCE.

  python scripts/seed_users.py --email admin@ibvap.local --password '<pw>' --role admin
  python scripts/seed_users.py --email guard@ibvap.local --password '<pw>' --role operator --areas CAM_STREET,CAM_PEOPLE
"""

import argparse
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BACKEND, ".env"))
except Exception:
    pass

from supabase import create_client

ROLES = ("admin", "supervisor", "operator", "auditor")


def _password(env_var: str) -> tuple[str, bool]:
    """Return (password, was_generated)."""
    val = os.getenv(env_var)
    if val:
        return val, False
    return secrets.token_urlsafe(15), True


def seed_one(sb, email, password, role, areas, full_name):
    user_id = None
    try:
        users = sb.auth.admin.list_users()
        match = next((u for u in users if getattr(u, "email", None) == email), None)
        if match:
            user_id = match.id
    except Exception as e:
        print(f"  (list_users failed: {e})")

    if user_id:
        sb.auth.admin.update_user_by_id(user_id, {"password": password, "email_confirm": True})
        print(f"  reset password for existing {email} ({user_id})")
    else:
        res = sb.auth.admin.create_user({
            "email": email, "password": password, "email_confirm": True,
        })
        user_id = res.user.id
        print(f"  created {email} ({user_id})")

    sb.table("user_profiles").upsert({
        "id": user_id,
        "role": role,
        "full_name": full_name or email.split("@")[0],
        "allowed_areas": areas,
    }).execute()
    print(f"  user_profiles: role={role}  allowed_areas={areas or 'ALL'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--defaults", action="store_true",
                    help="seed admin@ibvap.local + operator@ibvap.local")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--role", default="operator", choices=ROLES)
    ap.add_argument("--areas", default="", help="comma-separated camera ids; empty = all")
    ap.add_argument("--full-name", default="")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_KEY not found (checked env and backend/.env).")

    sb = create_client(url, key)
    areas = [a.strip() for a in args.areas.split(",") if a.strip()]

    if args.defaults:
        admin_pw, admin_gen = _password("IBVAP_ADMIN_PASSWORD")
        op_pw, op_gen = _password("IBVAP_OPERATOR_PASSWORD")
        print("Seeding default accounts:")
        seed_one(sb, "admin@ibvap.local", admin_pw, "admin", [], "Administrator")
        seed_one(sb, "operator@ibvap.local", op_pw, "operator", [], "Operator")
        print("\n--- credentials (store these now; not shown again) ---")
        print(f"  admin@ibvap.local    {'(generated) ' + admin_pw if admin_gen else '(from IBVAP_ADMIN_PASSWORD)'}")
        print(f"  operator@ibvap.local {'(generated) ' + op_pw if op_gen else '(from IBVAP_OPERATOR_PASSWORD)'}")
        return

    if not args.email or not args.password:
        sys.exit("give --defaults, or both --email and --password")
    print(f"Seeding {args.email}:")
    seed_one(sb, args.email, args.password, args.role, areas, args.full_name)


if __name__ == "__main__":
    main()
