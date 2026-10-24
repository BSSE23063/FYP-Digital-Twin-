from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the T2-RAG platform. Every env var the codebase
    reads is declared here — nothing should reach for os.getenv() directly."""

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:yourpassword@localhost:5432/t2rag"

    # ── App ───────────────────────────────────────────────────
    SECRET_KEY: str = "supersecretkey"
    DEBUG: bool = True

    # ── LLM (Groq) ────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Vector store (Qdrant) ─────────────────────────────────
    # Silo model: one physical collection PER TWIN, named "{prefix}{twin_id}"
    # (see vectordb/collections.py). Chosen over a shared pool so a twin's
    # knowledge is isolated by construction, not by remembering a filter.
    QDRANT_PATH: str = "./qdrant_storage"
    QDRANT_COLLECTION_PREFIX: str = "twin_"

    # ── Embeddings & chunking ─────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # ── Uploads ───────────────────────────────────────────────
    UPLOAD_DIR: str = "./data/uploads"
    AVATAR_DIR: str = "./data/avatars"
    # Per-twin cloning reference clips, distinct from TTS_VOICE_SAMPLE_PATH
    # (below) — that one stays as the global fallback voice when a twin hasn't
    # uploaded its own.
    VOICE_SAMPLES_DIR: str = "./data/twin_voice_samples"

    # ── Voice (backend-only capability, no live call yet) ──────
    # CPU-only, measured slower than realtime (§9.3) — accepted for now per
    # the user's call; revisit speed later. "tiny.en" is the default because
    # it's small enough to download reliably; upgrade to "base.en"/"small.en"
    # for better accuracy once that's not a concern.
    ASR_MODEL_SIZE: str = "tiny.en"
    TTS_LANGUAGE: str = "english"
    TTS_QUANTIZE: bool = True
    # Catalog voice name — the fallback when TTS_VOICE_SAMPLE_PATH isn't set.
    TTS_DEFAULT_VOICE: str = "alba"
    # Path to a real recorded voice sample to clone. When set, this is used
    # instead of TTS_DEFAULT_VOICE everywhere a caller doesn't explicitly pass
    # its own voice_ref. Requires HF_TOKEN (below) and accepting Kyutai's terms
    # at huggingface.co/kyutai/pocket-tts — see CLAUDE.md §9.4.
    #
    # Deliberately points at a TRIMMED 12s clip, not the original 47s
    # recording: the full recording produced garbage/truncated output every
    # time (confirmed reproducible — see §9.4), almost certainly because its
    # tail end has off-topic trailing speech (the file is literally named
    # "testing") that the model partly echoes regardless of the requested
    # text. The first 12s alone clones correctly and reliably. Lesson for any
    # future recording: keep it to a clean, continuous 10-30s of just the
    # person talking, nothing before/after.
    #
    # Also confirmed: the cloning-capable model is itself a heavier checkpoint
    # than the preset-voice one and runs slower again (~0.3x realtime vs
    # ~0.9x) — a real cost of cloning specifically, not just Pocket TTS.
    TTS_VOICE_SAMPLE_PATH: str = "./data/voice_samples/umair_voice_sample_trimmed.wav"
    HF_TOKEN: str = ""

    # ── Profile import (session 15) ─────────────────────────────
    # Optional — unauthenticated GitHub API calls are capped at 60/hour per
    # IP, which is fine for occasional single-profile imports but easy to
    # exhaust while testing. A personal access token (no special scopes
    # needed, just "public repo" read, which is the default) raises that to
    # 5000/hour. Not required to use the feature at all.
    GITHUB_TOKEN: str = ""

    # ── Grounding (self-corrective agent graph) ───────────────
    # Knowledge chunks below this cosine score are dropped before generation.
    RETRIEVAL_MIN_SCORE: float = 0.25
    # If nothing clears MIN_SCORE but the top hit was at least this close, the
    # question was probably a knowledge lookup, just poorly phrased -- worth
    # one query rewrite + re-retrieval. Below this, it's probably not a
    # knowledge question at all (a greeting, a meta-question) and rewriting
    # would just waste a retrieval round-trip for nothing.
    RETRIEVAL_REWRITE_SCORE: float = 0.15

    # ── Chat input compression (session 22) ────────────────────
    # A single visitor message longer than this is truncated before it's
    # used as the chat content/retrieval query — a huge pasted block would
    # otherwise bloat the prompt directly, the same TPM pressure that broke
    # Housekeeping (CLAUDE.md session 20), just from one message instead of
    # many chunks.
    MAX_CHAT_MESSAGE_CHARS: int = 4_000
    # Only the most recent N messages (visitor + twin turns combined) are
    # replayed into the LLM's context on each turn — older turns are dropped
    # rather than summarized, since summarizing would itself cost an extra
    # Groq call on every overflow, working against the same TPM limit this
    # is meant to protect. A twin that needs to recall something from far
    # earlier in a long conversation is a real, accepted limitation of this
    # tradeoff, not an oversight.
    MAX_HISTORY_MESSAGES: int = 12

    # ── Ingestion ─────────────────────────────────────────────
    # Hard cap on raw text per source — CPU-only embedding generation (no GPU,
    # see CLAUDE.md §9.2) makes a pathologically large upload a real way to
    # stall the whole process, so this fails fast instead of churning for minutes.
    MAX_INGEST_CHARS: int = 500_000
    # Chunks are embedded in batches of this size rather than all at once, so
    # memory use stays flat regardless of how large a document is.
    INGEST_BATCH_SIZE: int = 64

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
