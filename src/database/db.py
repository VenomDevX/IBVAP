"""
IBVAP — Database Manager
SQLite database connection and schema initialization.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from src.database.models import Base

# Default database path
DEFAULT_DB_URL = "sqlite:///./ibvap.db"


class Database:
    """SQLite database manager using SQLAlchemy."""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", DEFAULT_DB_URL)
        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False},  # SQLite threading
            echo=False,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self._initialized = False

    def init_db(self):
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)
        self._initialized = True
        logger.success(f"Database initialized: {self.db_url}")

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
