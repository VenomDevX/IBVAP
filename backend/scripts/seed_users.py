"""
seed_users.py — provision operator accounts (signup is locked).

Uses the Supabase service-role key to create auth users and set their
application role + allowed_areas in `user_profiles`.

Usage:
  # env: SUPABASE_URL, SUPABASE_SERVICE_KEY
  python scripts/seed_users.py --email admin@ibvap.local    --password '<pw>' --role admin
  python scripts/seed_users.py --email operator@ibvap.local --password '<pw>' --role operator --areas cam_north,cam_south
"""

import argparse
import os
import sys

from supabase import create_client

ROLES = ("admin", "supervisor", "operator", "auditor")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--role", default="operator", choices=ROLES)
    ap.add_argument("--areas", default="", help="comma-separated camera ids; empty = all")
    ap.add_argument("--full-name", default="")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment.")

    sb = create_client(url, key)

    # create (or fetch) the auth user
    try:
        res = sb.auth.admin.create_user({
            "email": args.email,
            "password": args.password,
            "email_confirm": True,
        })
        user_id = res.user.id
        print(f"created auth user {args.email} ({user_id})")
    except Exception as e:
        print(f"create_user failed ({e}); looking up existing user...")
        users = sb.auth.admin.list_users()
        match = next((u for u in users if getattr(u, "email", None) == args.email), None)
        if not match:
            sys.exit("could not create or find the user")
        user_id = match.id
        print(f"found existing user {args.email} ({user_id})")

    areas = [a.strip() for a in args.areas.split(",") if a.strip()]
    sb.table("user_profiles").upsert({
        "id": user_id,
        "role": args.role,
        "full_name": args.full_name or args.email.split("@")[0],
        "allowed_areas": areas,
    }).execute()
    print(f"user_profiles set: role={args.role} allowed_areas={areas or 'ALL'}")


if __name__ == "__main__":
    main()
