"""
SQLAlchemy ORM models for the T2-RAG Digital Twin platform (schema v2).

Design rule
-----------
Postgres stores WHO and WHAT EXISTS (users, twins, access grants, source/media
registries, schedule, audit log). Qdrant stores WHAT IS KNOWN (chunked knowledge
+ per-visitor memory, as vectors). Knowledge/memory TEXT is never duplicated here.

Tenancy & identity
------------------
`users` is a single identity table for BOTH twin owners and visitors — a person
can own one twin and be a named visitor on someone else's, so one identity graph
avoids maintaining two parallel account systems. `password_hash` is nullable:
visitor accounts may be passwordless (magic-link only).

`access_grants` is how "share with specific named people" works. It replaces
trusting a client-supplied tier string: a conversation's `access_tier` must be
resolved server-side from the visitor's active grant (or default to "public"),
never read off the request body.

Twin scope (session 21)
------------------------
A twin is no longer modeled as "a whole person" (arbitrary life facts, a
calendar) — it's the owner's identity (name/photo/voice) applied to ONE
declared domain of knowledge (`twins.domain`, required, e.g. "React &
TypeScript development"). `twin_attributes` and `schedule_entries` existed
to store small always-on facts and availability for a whole-life twin; both
are removed outright, not deprecated, since they don't fit a domain-scoped
expert. `twins.domain` is injected into the agent's system prompt
(backend/agent/nodes.py) alongside `persona_prompt` so the twin can
correctly decline questions outside its declared scope instead of guessing.

Tables
------
users                 : both owner and visitor identities
twins                 : digital twin profiles = the tenant boundary (one domain each)
access_grants         : twin_id -> named visitor (or pending email invite) -> tier
access_tiers          : which visibilities each tier name may see, per twin
sources               : registry of ingested knowledge material (no text)
media_assets          : raw voice/video recordings used to clone voice/avatar
conversations         : chat/call sessions (visitor or owner)
messages              : individual messages + audit trail
call_sessions         : call-specific metadata for a voice/video conversation
visitor_profile_facts : small always-on facts the twin has learned about ONE visitor
memory_chunks         : registry for per-visitor memory text embedded in Qdrant
knowledge_gaps        : unanswered visitor questions, queued for the owner to answer

Logical (non-FK) links to Qdrant
----------------------------------
Each twin has its OWN Qdrant collection (name derived from twin_id) — tenant
isolation is physical (a separate collection), not a shared-pool payload filter.
Within one twin's collection, point payload still carries point_kind
('knowledge'|'memory') so a single collection serves both the twin's documents
and per-visitor memory:
  knowledge point -> source_id, visibility
  memory point    -> visitor_id, memory_chunk_id
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base


# ── Allowed values (single source of truth) ──────────────────

class Visibility(str, enum.Enum):
    PUBLIC = "public"
    FRIENDS = "friends"
    PRIVATE = "private"


class SourceType(str, enum.Enum):
    UPLOAD = "upload"
    GITHUB = "github"
    LINKEDIN = "linkedin"
    MANUAL = "manual"
    VOICE_TRANSCRIPT = "voice_transcript"
    VIDEO_TRANSCRIPT = "video_transcript"
    ESCALATION_ANSWER = "escalation_answer"


class SourceStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MediaAssetType(str, enum.Enum):
    VOICE_SAMPLE = "voice_sample"
    VIDEO_SAMPLE = "video_sample"


class ConversationChannel(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"


class MessageRole(str, enum.Enum):
    VISITOR = "visitor"
    TWIN = "twin"
    SYSTEM = "system"


class PolicyDecision(str, enum.Enum):
    ANSWER = "answer"
    DECLINE = "decline"
    ESCALATE = "escalate"


class KnowledgeGapStatus(str, enum.Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    DISMISSED = "dismissed"


def _in_list(column: str, enum_cls: type[enum.Enum]) -> str:
    """Build a SQL CHECK expression: column IN ('a','b',...)."""
    values = ", ".join(f"'{m.value}'" for m in enum_cls)
    return f"{column} IN ({values})"


# ── Helpers ──────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _uuid_pk() -> Mapped[str]:
    # as_uuid=False: Postgres stores a real UUID, Python sees a plain str.
    return mapped_column(Uuid(as_uuid=False), primary_key=True, default=_new_uuid)


def _uuid_fk(target: str, *, nullable: bool = False, index: bool = True) -> Mapped[str]:
    return mapped_column(
        Uuid(as_uuid=False),
        ForeignKey(target, ondelete="CASCADE"),
        nullable=nullable,
        index=index,
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


# ─────────────────────────────────────────────────────────────
# users — single identity table for owners AND visitors
# ─────────────────────────────────────────────────────────────

class User(Base):
    """A platform identity. May own twins, and/or be a named visitor on others'
    twins. password_hash is nullable: visitor accounts may be passwordless."""
    __tablename__ = "users"

    id: Mapped[str] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created()

    twins: Mapped[list["Twin"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


# ─────────────────────────────────────────────────────────────
# twins
# ─────────────────────────────────────────────────────────────

class Twin(Base):
    """
    A digital twin. This is the TENANT BOUNDARY: every source, grant,
    conversation, and Qdrant point (twin_id payload field) belongs to one twin.
    """
    __tablename__ = "twins"

    id: Mapped[str] = _uuid_pk()
    owner_id: Mapped[str] = _uuid_fk("users.id")
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(
        String(500), comment="Relative path under AVATAR_DIR; served at /media/<this>"
    )
    bio: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="The one topic/expertise this twin's knowledge is scoped to, "
        "e.g. 'React & TypeScript development' — required at creation, "
        "injected into the agent's system prompt alongside persona_prompt.",
    )
    persona_prompt: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    owner: Mapped["User"] = relationship(back_populates="twins")
    sources: Mapped[list["Source"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )
    access_grants: Mapped[list["AccessGrant"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )
    access_tiers: Mapped[list["AccessTier"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )
    media_assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_gaps: Mapped[list["KnowledgeGap"]] = relationship(
        back_populates="twin", cascade="all, delete-orphan", passive_deletes=True
    )


# ─────────────────────────────────────────────────────────────
# access_grants — WHO may read a twin's non-public material
# ─────────────────────────────────────────────────────────────

class AccessGrant(Base):
    """
    Names a specific visitor (or a pending email invite) and the tier they've been
    granted on a twin. Soft-revoked (revoked_at), never hard-deleted, so there's an
    audit trail of who had access and when. A conversation's access_tier is
    resolved from the single ACTIVE grant for that visitor at session-start time —
    the server decides this, the client never supplies it.
    """
    __tablename__ = "access_grants"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    visitor_id: Mapped[str | None] = _uuid_fk("users.id", nullable=True)
    invited_email: Mapped[str | None] = mapped_column(String(255))
    tier_name: Mapped[str] = mapped_column(String(50), nullable=False)
    granted_by: Mapped[str] = _uuid_fk("users.id")
    granted_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    twin: Mapped["Twin"] = relationship(back_populates="access_grants")
    visitor: Mapped["User | None"] = relationship(foreign_keys=[visitor_id])

    __table_args__ = (
        CheckConstraint(
            "visitor_id IS NOT NULL OR invited_email IS NOT NULL",
            name="ck_access_grants_identity",
        ),
        Index(
            "uq_access_grants_active_visitor",
            "twin_id", "visitor_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND visitor_id IS NOT NULL"),
        ),
    )


# ─────────────────────────────────────────────────────────────
# access_tiers
# ─────────────────────────────────────────────────────────────

class AccessTier(Base):
    """
    Maps an audience tier to the visibilities it may read.
    e.g. friends -> "public,friends". Orthogonal to access_grants: this defines
    WHAT a tier can see, access_grants defines WHO holds a tier.
    """
    __tablename__ = "access_tiers"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    tier_name: Mapped[str] = mapped_column(String(50), nullable=False)
    allowed_visibilities: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Comma-separated, e.g. 'public,friends'",
    )

    twin: Mapped["Twin"] = relationship(back_populates="access_tiers")

    __table_args__ = (
        UniqueConstraint("twin_id", "tier_name", name="uq_access_tier_twin_name"),
    )

    @property
    def visibility_list(self) -> list[str]:
        return [v.strip() for v in self.allowed_visibilities.split(",") if v.strip()]


# ─────────────────────────────────────────────────────────────
# sources — registry of ingested knowledge (no text; chunks live in Qdrant)
# ─────────────────────────────────────────────────────────────

class Source(Base):
    """
    Registry entry for one piece of ingested material (a CV file, a GitHub
    import, a pasted note, or a transcript of a voice/video sample). Holds NO
    text. The chunks live in Qdrant with payload source_id = this row's id.

    Deleting a source means: delete Qdrant points where source_id = id,
    then delete this row.
    """
    __tablename__ = "sources"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    media_asset_id: Mapped[str | None] = _uuid_fk(
        "media_assets.id", nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    visibility: Mapped[str] = mapped_column(
        String(50), default=Visibility.PUBLIC.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default=SourceStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    storage_path: Mapped[str | None] = mapped_column(
        String(500), comment="Where the original file lives on disk (for re-chunking)"
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    twin: Mapped["Twin"] = relationship(back_populates="sources")
    media_asset: Mapped["MediaAsset | None"] = relationship()

    __table_args__ = (
        CheckConstraint(_in_list("source_type", SourceType), name="ck_sources_type"),
        CheckConstraint(_in_list("visibility", Visibility), name="ck_sources_visibility"),
        CheckConstraint(_in_list("status", SourceStatus), name="ck_sources_status"),
    )


# ─────────────────────────────────────────────────────────────
# media_assets — raw voice/video recordings (training material, not knowledge)
# ─────────────────────────────────────────────────────────────

class MediaAsset(Base):
    """
    A raw voice or video recording used to clone the twin's voice / build an
    avatar — NOT a knowledge source. Feeds a different downstream consumer
    (a voice/avatar model) than `sources` does (the RAG retriever), which is
    why it's a separate table. `consent_confirmed_at` is enforced: a recording
    of a real person's voice/likeness cannot be marked ready without it.
    """
    __tablename__ = "media_assets"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    format: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), default=SourceStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    twin: Mapped["Twin"] = relationship(back_populates="media_assets")

    __table_args__ = (
        CheckConstraint(_in_list("asset_type", MediaAssetType), name="ck_media_assets_type"),
        CheckConstraint(_in_list("status", SourceStatus), name="ck_media_assets_status"),
        CheckConstraint(
            "status <> 'completed' OR consent_confirmed_at IS NOT NULL",
            name="ck_media_consent_before_ready",
        ),
    )


# ─────────────────────────────────────────────────────────────
# conversations
# ─────────────────────────────────────────────────────────────

class Conversation(Base):
    """
    One chat or call session.

    SECURITY: access_tier is resolved by the SERVER from the visitor's active
    AccessGrant (or defaulted to "public"), never copied from the request body.
    is_owner_session = True is the only way a 'memory' record may later be
    written for the owner's own account instead of a third-party visitor.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    visitor_id: Mapped[str | None] = _uuid_fk(
        "users.id", nullable=True,
        index=True,
    )
    visitor_name: Mapped[str] = mapped_column(
        String(255), default="Anonymous", nullable=False
    )
    channel: Mapped[str] = mapped_column(
        String(20), default=ConversationChannel.TEXT.value, nullable=False
    )
    access_tier: Mapped[str] = mapped_column(
        String(50), default=Visibility.PUBLIC.value, nullable=False
    )
    is_owner_session: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = _created()

    twin: Mapped["Twin"] = relationship(back_populates="conversations")
    visitor: Mapped["User | None"] = relationship()
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
    call_session: Mapped["CallSession | None"] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True,
        uselist=False,
    )

    __table_args__ = (
        CheckConstraint(_in_list("channel", ConversationChannel), name="ck_conversations_channel"),
    )


# ─────────────────────────────────────────────────────────────
# messages
# ─────────────────────────────────────────────────────────────

class Message(Base):
    """
    One message. Twin replies carry the audit trail: which chunks were used
    (sources_json), the policy decision, retrieval confidence, and latency.
    """
    __tablename__ = "messages"

    id: Mapped[str] = _uuid_pk()
    conversation_id: Mapped[str] = _uuid_fk("conversations.id")
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    policy_decision: Mapped[str | None] = mapped_column(String(20))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    sources_json: Mapped[list | dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint(_in_list("role", MessageRole), name="ck_messages_role"),
        CheckConstraint(
            "policy_decision IS NULL OR " + _in_list("policy_decision", PolicyDecision),
            name="ck_messages_policy",
        ),
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────────
# call_sessions — call-specific metadata layered on a conversation
# ─────────────────────────────────────────────────────────────

class CallSession(Base):
    """
    Metadata for a voice (later: video) call. Turn-by-turn content still flows
    through `messages` (ASR transcript as a visitor message, generated reply as
    a twin message) — this table only carries what's specific to the call itself.
    """
    __tablename__ = "call_sessions"

    id: Mapped[str] = _uuid_pk()
    conversation_id: Mapped[str] = _uuid_fk("conversations.id")
    started_at: Mapped[datetime] = _created()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_path: Mapped[str | None] = mapped_column(String(500))
    recording_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(50))

    conversation: Mapped["Conversation"] = relationship(back_populates="call_session")

    __table_args__ = (
        UniqueConstraint("conversation_id", name="uq_call_session_conversation"),
    )


# ─────────────────────────────────────────────────────────────
# visitor_profile_facts — small always-on facts about ONE visitor
# ─────────────────────────────────────────────────────────────

class VisitorProfileFact(Base):
    """
    Small, stable facts the twin has learned about one specific visitor
    ("stated_role": "recruiter").
    Always injected into context for that visitor's conversations — no retrieval
    step, so a key fact can never be missed by a weak semantic match.
    """
    __tablename__ = "visitor_profile_facts"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    visitor_id: Mapped[str] = _uuid_fk("users.id")
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_id: Mapped[str | None] = _uuid_fk(
        "messages.id", nullable=True, index=True
    )
    updated_at: Mapped[datetime] = _updated()

    twin: Mapped["Twin"] = relationship()
    visitor: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("twin_id", "visitor_id", "key", name="uq_visitor_fact_key"),
    )


# ─────────────────────────────────────────────────────────────
# memory_chunks — registry for per-visitor memory text embedded in Qdrant
# ─────────────────────────────────────────────────────────────

class MemoryChunk(Base):
    """
    Mirrors what `sources` is for documents: a lifecycle/deletion registry for
    free-text memory embedded in Qdrant as point_kind='memory'. Exists so "a
    visitor asks the twin to forget what it knows about them" is a precise
    `DELETE FROM memory_chunks WHERE visitor_id=?` (giving the exact Qdrant
    point ids to purge) instead of a payload scan.
    """
    __tablename__ = "memory_chunks"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    visitor_id: Mapped[str] = _uuid_fk("users.id")
    origin_conversation_id: Mapped[str | None] = _uuid_fk(
        "conversations.id", nullable=True, index=True
    )
    created_at: Mapped[datetime] = _created()

    twin: Mapped["Twin"] = relationship()
    visitor: Mapped["User"] = relationship()
    origin_conversation: Mapped["Conversation | None"] = relationship()

    __table_args__ = (
        Index("ix_memory_chunks_twin_visitor", "twin_id", "visitor_id"),
    )


# ─────────────────────────────────────────────────────────────
# knowledge_gaps — the feedback loop: a visitor asked something the twin
# couldn't answer; queued for the owner; the owner's answer becomes knowledge.
# ─────────────────────────────────────────────────────────────

class KnowledgeGap(Base):
    """
    Created when a visitor's question can't be answered (policy_decision=escalate
    from the agent graph — see backend/agent/). Sits PENDING until the owner is
    next active and answers it; answering writes a new `Source` (source_type=
    escalation_answer) chunked + embedded into THIS TWIN'S OWN Qdrant collection,
    so the same question is answerable next time. This is the "the twin learns
    from what it doesn't know" loop.

    `question_text` is denormalized off `question_message_id` deliberately: a
    small, controlled duplication that keeps a listing/notification query from
    needing a join, and survives even though messages cascade-delete with their
    conversation.
    """
    __tablename__ = "knowledge_gaps"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = _uuid_fk("twins.id")
    conversation_id: Mapped[str] = _uuid_fk("conversations.id")
    question_message_id: Mapped[str] = _uuid_fk("messages.id")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=KnowledgeGapStatus.PENDING.value, nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SET NULL, not CASCADE: if the resulting source is later deleted, the
    # historical record that this gap was identified and answered should stay.
    resulting_source_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = _created()

    twin: Mapped["Twin"] = relationship(back_populates="knowledge_gaps")
    conversation: Mapped["Conversation"] = relationship()
    question_message: Mapped["Message"] = relationship()
    resulting_source: Mapped["Source | None"] = relationship()

    __table_args__ = (
        CheckConstraint(_in_list("status", KnowledgeGapStatus), name="ck_knowledge_gaps_status"),
        Index("ix_knowledge_gaps_twin_status", "twin_id", "status"),
    )
