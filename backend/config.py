"""
Application configuration loaded from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project root directory (t2-rag/)
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    """Central configuration for the T2-RAG platform."""

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/twin_db"
    )

    # ── LLM (Groq) ───────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    # ── Vector Store (ChromaDB) ───────────────────────────────
    CHROMA_PERSIST_DIR: str = os.getenv(
        "CHROMA_PERSIST_DIR",
        str(BASE_DIR / "data" / "chroma_db")
    )
    CHROMA_COLLECTION_NAME: str = os.getenv(
        "CHROMA_COLLECTION_NAME", "twin_knowledge"
    )

    # ── Embeddings ────────────────────────────────────────────
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

    # ── File Storage ──────────────────────────────────────────
    UPLOAD_DIR: str = os.getenv(
        "UPLOAD_DIR", str(BASE_DIR / "data" / "uploads")
    )
    RAW_DIR: str = os.getenv(
        "RAW_DIR", str(BASE_DIR / "data" / "raw")
    )

    # ── Chunking Defaults ─────────────────────────────────────
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))


settings = Settings()