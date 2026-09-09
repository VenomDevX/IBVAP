import os
import sys

import sqlalchemy
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database.db import get_database
from src.database.models import Base


def migrate_db():
    db = get_database()
    engine = db.engine

    with engine.connect() as conn:
        print("Checking and migrating database schema...")

        # 1. Add snapshot_hash to alerts
        try:
            conn.execute(text("ALTER TABLE alerts ADD COLUMN snapshot_hash VARCHAR(64)"))
            print("Added snapshot_hash to alerts.")
        except sqlalchemy.exc.OperationalError:
            print("snapshot_hash already exists in alerts or table missing.")

        # 2. Add evidence_hash to events
        try:
            conn.execute(text("ALTER TABLE events ADD COLUMN evidence_hash VARCHAR(64)"))
            print("Added evidence_hash to events.")
        except sqlalchemy.exc.OperationalError:
            print("evidence_hash already exists in events or table missing.")

        # 3. Add latitude and longitude to cameras
        try:
            conn.execute(text("ALTER TABLE cameras ADD COLUMN latitude FLOAT"))
            conn.execute(text("ALTER TABLE cameras ADD COLUMN longitude FLOAT"))
            print("Added latitude and longitude to cameras.")
        except sqlalchemy.exc.OperationalError:
            print("latitude/longitude already exists in cameras or table missing.")

        conn.commit()

    print("Creating any missing tables (like audit_logs)...")
    Base.metadata.create_all(bind=engine)
    print("Migration complete.")


if __name__ == "__main__":
    migrate_db()
