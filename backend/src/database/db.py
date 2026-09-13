"""
IBVAP — Database Manager
Database connection and schema initialization (PostgreSQL & SQLite).
"""

import os
import re
from datetime import datetime

from loguru import logger
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import Base
from src.paths import default_database_url

# Default database path
DEFAULT_DB_URL = default_database_url()


class Database:
    """Database manager using SQLAlchemy."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
        is_sqlite = self.db_url.startswith("sqlite")
        is_postgres = self.db_url.startswith("postgres")
        
        if is_postgres:
            connect_args = {
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5
            }
            self.engine = create_engine(
                self.db_url,
                pool_size=20,
                max_overflow=10,
                pool_timeout=30,
                connect_args=connect_args,
                echo=False,
                hide_parameters=True,
            )
        else:
            connect_args = {"check_same_thread": False, "timeout": 5} if is_sqlite else {}
            self.engine = create_engine(
                self.db_url,
                connect_args=connect_args,
                echo=False,
                hide_parameters=True,
            )

        if is_sqlite:
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _rec):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._initialized = False

    def init_db(self):
        """Create all tables and add any columns missing from an older DB."""
        Base.metadata.create_all(bind=self.engine)
        self._run_migrations()
        self._initialized = True
        
        # Mask password in log output
        safe_url = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", self.db_url)
        logger.success(f"Database initialized: {safe_url}")

    def _run_migrations(self):
        """Apply small, versioned and idempotent runtime schema migrations."""
        from sqlalchemy import inspect, text

        with self.engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at DATETIME NOT NULL)"
            ))
            applied = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}

        migrations = [
            (1, self._migration_columns),
            (2, self._migration_indexes),
            (3, self._migration_incident_workflow),
            (4, self._migration_camera_runtime),
        ]
        for version, migration in migrations:
            if version in applied:
                continue
            migration(inspect(self.engine), text)
            with self.engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO schema_migrations(version, applied_at) VALUES (:v, :at)"),
                    {"v": version, "at": datetime.utcnow()},
                )
            logger.info("db: applied schema migration {}", version)

    def _migration_columns(self, insp, text):
        wanted = {
            "zones": {"deleted": "BOOLEAN NOT NULL DEFAULT FALSE" if self.db_url.startswith("postgres") else "BOOLEAN NOT NULL DEFAULT 0"},
            "events": {"prev_hash": "VARCHAR(64)", "chain_hash": "VARCHAR(64)"},
            "alerts": {"prev_hash": "VARCHAR(64)", "chain_hash": "VARCHAR(64)"},
        }
        with self.engine.begin() as conn:
            for table, cols in wanted.items():
                if not insp.has_table(table):
                    continue
                existing = {c["name"] for c in insp.get_columns(table)}
                for name, ddl in cols.items():
                    if name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

    def _migration_indexes(self, _insp, text):
        statements = (
            "CREATE INDEX IF NOT EXISTS ix_tracks_camera_id ON tracks(camera_id)",
            "CREATE INDEX IF NOT EXISTS ix_identity_results_camera_id ON identity_results(camera_id)",
            "CREATE INDEX IF NOT EXISTS ix_anpr_results_camera_id ON anpr_results(camera_id)",
            "CREATE INDEX IF NOT EXISTS ix_zones_camera_id ON zones(camera_id)",
            "CREATE INDEX IF NOT EXISTS ix_alerts_event_id ON alerts(event_id)",
        )
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def _migration_incident_workflow(self, insp, text):
        columns = {
            "status": "VARCHAR(30) NOT NULL DEFAULT 'open'",
            "disposition": "VARCHAR(30)",
            "assignee": "VARCHAR(100)",
            "acknowledged_at": "TIMESTAMP" if self.db_url.startswith("postgres") else "DATETIME",
            "resolved_at": "TIMESTAMP" if self.db_url.startswith("postgres") else "DATETIME",
        }
        with self.engine.begin() as conn:
            existing = {c["name"] for c in insp.get_columns("alerts")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE alerts ADD COLUMN {name} {ddl}"))
            for statement in (
                "CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status)",
                "CREATE INDEX IF NOT EXISTS ix_alerts_disposition ON alerts(disposition)",
                "CREATE INDEX IF NOT EXISTS ix_alerts_assignee ON alerts(assignee)",
            ):
                conn.execute(text(statement))

    def _migration_camera_runtime(self, insp, text):
        columns = {
            "fps_limit": "INTEGER NOT NULL DEFAULT 15",
            "resolution": "JSONB" if self.db_url.startswith("postgres") else "JSON",
        }
        with self.engine.begin() as conn:
            existing = {c["name"] for c in insp.get_columns("cameras")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE cameras ADD COLUMN {name} {ddl}"))

    def get_session(self) -> Session:
        """Get a new database session."""
        if not self._initialized:
            self.init_db()
        return self.SessionLocal()

    def close(self):
        """Close the database engine."""
        self.engine.dispose()


# Singleton instance
_db_instance: Database = None


def get_database(db_url: str = None) -> Database:
    """Get or create the database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_url)
        _db_instance.init_db()
    return _db_instance


def get_session() -> Session:
    """Get a database session from the singleton."""
    return get_database().get_session()
