"""
Database initialization script.

Usage:
    python -m backend.db.init_db            # create missing tables
    python -m backend.db.init_db --reset    # DEV ONLY: wipe everything, recreate

NOTE: create_all never alters existing tables. After changing a model in
dev, use --reset. Later, switch to Alembic migrations.
"""
import sys

from sqlalchemy import text

from backend.db.session import engine, Base

# Importing the models registers their tables on Base.metadata.
from backend.db import models  # noqa: F401


def reset_db() -> None:
    """Drop the whole public schema (also removes old tables not in models)."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    print("[RESET] public schema dropped and recreated")


def init_db(reset: bool = False) -> None:
    print(f"Connecting to: {engine.url.render_as_string(hide_password=True)}")
    if reset:
        reset_db()
    Base.metadata.create_all(bind=engine)
    for table in sorted(Base.metadata.tables):
        print(f"  [OK] {table}")
    print("Database initialization complete.")


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv)