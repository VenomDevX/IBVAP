import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.db import get_database
from src.database.models import Base

def reset_db():
    db = get_database()
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=db.engine)
    print("Creating all tables...")
    Base.metadata.create_all(bind=db.engine)
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
