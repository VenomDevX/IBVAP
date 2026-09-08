"""
IBVAP — Database Manager
SQLite database connection and schema initialization.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from src.database.models import Base

# Default database path
DEFAULT_DB_URL = "sqlite:///./ibvap.db"


class Database:
    """SQLite database manager using SQLAlchemy."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
        is_sqlite = self.db_url.startswith("sqlite")
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
                cur.close()
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self._initialized = False

    def init_db(self):
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)
        self._initialized = True
        # Mask password in log output
        import re
        safe_url = re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', self.db_url)
        logger.success(f"Database initialized: {safe_url}")

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
