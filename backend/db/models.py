"""
SQLAlchemy ORM models for the T2-RAG Digital Twin platform.

Tables
------
- users             : Platform user accounts (twin owners)
- twins             : Digital twin profiles
- documents         : Uploaded / ingested source documents
- document_chunks   : Text chunks extracted from documents
- owner_qa_entries  : Manual Q&A pairs added by the owner
- access_tiers      : Permission levels for visitor access
- conversations     : Chat sessions between visitors and twins
- messages          : Individual messages within conversations

Design notes
------------
- All IDs are UUID-v4 strings (36 chars). Using String instead of native
  UUID for portability and simpler debugging.
- `twin_id` is denormalized onto `document_chunks` to avoid a JOIN on
  every retrieval query.
- `char_start` / `char_end` on chunks reference offsets in
  `documents.raw_text` so gold-span evaluation works across chunking
  strategies.
- `chromadb_id` on chunks and QA entries is the explicit link between
  PostgreSQL and ChromaDB. When a chunk is deleted, its vector is too.
- Every message records `policy_decision`, `sources_json`,
  `confidence_score`, and `latency_ms` for the audit log and evaluation.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Text, ForeignKey, DateTime, Integer,
    Boolean, Float, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


# ── Helpers ───────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────

class User(Base):
    """Platform user account — the person who owns one or more twins."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    twins: Mapped[list["Twin"]] = relationship(
        "Twin", back_populates="owner", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────
# Twins
# ─────────────────────────────────────────────────────────────

class Twin(Base):
    """
    A digital twin profile. Holds the persona config and acts as the
    tenant boundary — every knowledge chunk is scoped to a twin_id.
    """
    __tablename__ = "twins"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    persona_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="System-level instructions that shape the twin's style",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="twins")
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="twin", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="twin", cascade="all, delete-orphan"
    )
    qa_entries: Mapped[list["OwnerQAEntry"]] = relationship(
        "OwnerQAEntry", back_populates="twin", cascade="all, delete-orphan"
    )
    access_tiers: Mapped[list["AccessTier"]] = relationship(
        "AccessTier", back_populates="twin", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="twin", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────

class Document(Base):
    """
    A source document uploaded or synced for a twin.

    Tracks its ingestion lifecycle (pending → processing → completed/failed)
    and stores the cleaned raw_text so the same document can be re-chunked
    with a different strategy without re-parsing the original file.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    twin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="File type: pdf, docx, txt, md",
    )
    source_type: Mapped[str] = mapped_column(
        String(50), default="upload",
        comment="Origin: upload, github, linkedin, manual",
    )
    visibility: Mapped[str] = mapped_column(
        String(50), default="public",
        comment="Access level: public, friends, private",
    )
    ingestion_status: Mapped[str] = mapped_column(
        String(50), default="pending",
        comment="Lifecycle: pending, processing, completed, failed",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Cleaned text extracted from the file (for re-chunking)",
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────
# Document Chunks
# ─────────────────────────────────────────────────────────────

class DocumentChunk(Base):
    """
    A text chunk extracted from a document.

    twin_id is denormalized (also reachable via document.twin_id) because
    every retrieval query needs it and we want to avoid a JOIN.

    char_start / char_end are character offsets into document.raw_text,
    enabling gold-span evaluation regardless of chunking strategy.
    """
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    twin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(50), default="public",
        comment="Inherited from the parent document's visibility",
    )
    char_start: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Start offset in document.raw_text",
    )
    char_end: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="End offset in document.raw_text",
    )
    heading_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Section hierarchy, e.g. 'Education > BSc > Courses'",
    )
    chromadb_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True,
        comment="ID in ChromaDB — explicit PG↔Chroma link",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", back_populates="chunks"
    )
    twin: Mapped["Twin"] = relationship("Twin", back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_twin_visibility", "twin_id", "visibility"),
    )


# ─────────────────────────────────────────────────────────────
# Owner Q&A Entries
# ─────────────────────────────────────────────────────────────

class OwnerQAEntry(Base):
    """
    A manually-added question-answer pair by the twin owner.
    Treated as an atomic chunk that is always kept whole (never split).
    """
    __tablename__ = "owner_qa_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    twin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(50), default="public")
    chromadb_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True,
        comment="ID in ChromaDB — explicit PG↔Chroma link",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="qa_entries")


# ─────────────────────────────────────────────────────────────
# Access Tiers
# ─────────────────────────────────────────────────────────────

class AccessTier(Base):
    """
    Defines what visibility levels each audience tier can access for a twin.

    Example: the 'public' tier can see chunks with visibility='public',
    while 'friends' can see 'public' and 'friends'.
    """
    __tablename__ = "access_tiers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    twin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tier_name: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="e.g. public, friends, recruiter, private",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_visibilities: Mapped[str] = mapped_column(
        String(255), default="public",
        comment="Comma-separated: 'public' or 'public,friends'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="access_tiers")

    __table_args__ = (
        Index(
            "ix_access_tier_twin_name", "twin_id", "tier_name", unique=True
        ),
    )


# ─────────────────────────────────────────────────────────────
# Conversations
# ─────────────────────────────────────────────────────────────

class Conversation(Base):
    """
    A chat session between a visitor and a twin.
    Tracks which access tier the visitor was assigned for this session.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    twin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("twins.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    visitor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    visitor_name: Mapped[str] = mapped_column(
        String(255), default="Anonymous"
    )
    access_tier: Mapped[str] = mapped_column(
        String(50), default="public",
        comment="Resolved tier for this session",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    twin: Mapped["Twin"] = relationship("Twin", back_populates="conversations")
    visitor: Mapped["User | None"] = relationship(
        "User", foreign_keys=[visitor_user_id]
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────
# Messages
# ─────────────────────────────────────────────────────────────

class Message(Base):
    """
    A single message in a conversation.

    Twin responses include:
    - sources_json  : which chunks the answer is based on
    - policy_decision : answer / decline / escalate
    - confidence_score : retrieval confidence
    - latency_ms    : end-to-end response time

    This forms the audit log for evaluation (faithfulness, leakage, etc.).
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="visitor, twin, or system",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON array of cited chunk IDs and snippets",
    )
    policy_decision: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="answer, decline, or escalate",
    )
    is_escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Retrieval confidence (0.0 to 1.0)",
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="End-to-end response time in milliseconds",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )