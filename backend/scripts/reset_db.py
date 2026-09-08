"""
reset_db.py — DROP every table and recreate the schema.

DESTRUCTIVE and irreversible: destroys all events, alerts, tracks, identity/plate
results AND the audit log. Guarded so it cannot be run by accident or in prod.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.db import get_database
from src.database.models import Base


def reset_db(assume_yes: bool = False):
    if os.getenv("IBVAP_ENV", "").lower() == "production":
        sys.exit("Refusing to reset the database while IBVAP_ENV=production.")

    db = get_database()
    dsn = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(db.db_url))
    print(f"Target database: {dsn}")
    print("This DROPS every table (events, alerts, tracks, identities, plates, audit log).")

    if not assume_yes:
        confirm = input('Type "RESET" to proceed: ').strip()
        if confirm != "RESET":
            sys.exit("Aborted.")

    print("Dropping all tables...")
    Base.metadata.drop_all(bind=db.engine)
    print("Creating all tables...")
    Base.metadata.create_all(bind=db.engine)
    print("Database reset complete.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    reset_db(assume_yes=ap.parse_args().yes)
