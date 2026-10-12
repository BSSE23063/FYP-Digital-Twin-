"""
Database initialization script.

Creates all tables and seeds default access tiers for new twins.

Usage:
    python -m backend.db.init_db
"""
from backend.db.session import engine, Base

# Import all models so Base.metadata registers their tables
from backend.db.models import (  # noqa: F401
    User, Twin, Document, DocumentChunk,
    OwnerQAEntry, AccessTier, Conversation, Message,
)


def init_db() -> None:
    """Create all tables in PostgreSQL."""
    print("=" * 60)
    print("T2-RAG Database Initialization")
    print("=" * 60)
    print(f"\nConnecting to: {engine.url}\n")

    Base.metadata.create_all(bind=engine)

    tables = sorted(Base.metadata.tables.keys())
    print(f"Created {len(tables)} tables:")
    for table in tables:
        print(f"  [OK] {table}")

    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)


if __name__ == "__main__":
    init_db()