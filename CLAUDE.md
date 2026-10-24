# CLAUDE.md — T2-RAG Project Memory & Architecture Log

> **Purpose of this file:** single source of truth for architecture decisions, current
> implementation state, open problems, and the working plan for this FYP. Every time a
> change is made to the project (by Claude or by you), a dated entry is appended to the
> **Changelog** section at the bottom. Read top-to-bottom for context; read the bottom
> for "what just happened."

Last audited: **2026-10-24** (session 24 — real landing page, richer theme, animations across the app; see changelog for sessions 14-24).

---

## 1. Project Snapshot

**T2-RAG** — a text-only, multi-tenant "Digital Twin" RAG system. Each twin is a
persona (backed by an owner's documents/notes) that visitors can chat with. Answers
must be grounded in retrieved documents, access is tiered (`public` / `friends` /
`private`), and every reply should carry an audit trail (what was retrieved, policy
decision, confidence, latency).

Target stack (per project scope): **FastAPI + PostgreSQL + Qdrant + Groq + Streamlit**.

Repo root: `C:\Users\umairs\OneDrive\Desktop\FYP\t2-rag` (this is its own git repo;
the parent `FYP` folder is not). One commit exists on `main`.

### ⚠️ Current repo state — read this first

The project is **mid-migration** and the working tree does not match the last commit:

- The initial commit (`0b8d81f`) contains a **complete, different-generation stack**:
  FastAPI app (`main.py` + `api/health,twins,documents,chat.py`), a service layer
  (`twin_service`, `document_service`, `conversation_service`), a full ingestion
  pipeline (`parser.py`, `chunker.py`, `pipeline.py`), a Groq LLM client + prompt
  library (`llm/client.py`, `llm/prompts.py`), a **self-corrective LangGraph** RAG
  graph (`rag/graph.py` — retrieve → grade → generate → hallucination-check →
  retry/abstain), a **ChromaDB** vector store wrapper (`rag/vector_store.py`), and a
  full Streamlit frontend (`frontend/app.py`).
- All of the files above are **deleted in the working tree right now, uncommitted**.
  They were replaced with a new, smaller skeleton: `backend/vectordb/` (Qdrant client +
  collections + operations), `backend/agent/` (a minimal 2-node LangGraph: retrieve →
  generate), and edits to `backend/db/models.py`, `backend/config.py`,
  `backend/rag/embeddings.py`.
- **Nothing has been committed since.** This means: (a) there is no commit that
  captures the new Qdrant/agent code, and (b) a careless `git checkout .` or
  `git reset --hard` would silently resurrect the old ChromaDB stack *and* discard the
  new work. Treat this as fragile until a checkpoint commit is made (see Phase 0 below).
- The new direction (Qdrant + slim agent) is a **deliberate migration**, not accidental
  loss — the new `db/models.py` docstring explicitly documents "Postgres stores WHO/WHAT
  EXISTS, Qdrant stores WHAT IS KNOWN," and `qdrant_storage/` contains a real collection
  (`twin_test-twin-001`, 384-dim cosine) proving the new ingestion→retrieval→generation
  path has actually been run successfully end-to-end at least once via
  `test_rag_pipeline.py`.

So: **the core RAG loop (chunk → embed → upsert to Qdrant → retrieve → generate via
Groq) works today**, proven by a manual script. Everything *around* it — the HTTP API,
the service layer wiring Postgres to Qdrant, file ingestion, the frontend, and the
self-corrective grounding logic — currently does not exist in the working tree.

### Scope expansion (session 2, 2026-10-15)

The project's real scope is bigger than "text-only RAG chatbot": a user builds a full
profile of themself (schedule, knowledge, preferences, **voice samples, video of
themself speaking**), chooses who can reach their twin (public, or **named specific
people**), and visitors can eventually **voice/video call** the twin. New
conversations must accumulate into **long-term memory scoped to that specific
visitor**, not just logged per-conversation.

Four architecture decisions were made to support this (see §6 for the full reasoning
each time this is revisited):

1. **Qdrant tenancy: collection-per-twin ("silo" model), reversed from the pool
   model this was originally built with (session 3).** The user decided isolation
   should be physical (a separate collection per twin) rather than a shared
   collection with a `twin_id` payload filter. Tradeoff accepted knowingly: this
   won't scale as cleanly past many twins (fixed per-collection overhead — its own
   HNSW graph, segments, threads) as the pool model would have, in exchange for
   isolation that doesn't depend on every query remembering a filter. See §8.
2. **Visitor identity: real (passwordless) visitor accounts + explicit grants**, not
   invite-link tokens and not a free-typed tier string. Required because *both*
   "share with named people" and "remember this visitor across sessions" need the
   same missing primitive — a stable visitor identifier.
3. **Calls: voice-only MVP this phase, video deferred.** Proves the real-time
   ASR → RAG/LLM → TTS loop without the much harder talking-avatar problem.
4. **Memory: two-tier, same pattern as the twin's own profile.** Small structured
   facts live in Postgres and are always injected into context; larger free-text
   memories are embedded and retrieved semantically from this twin's own Qdrant
   collection, tagged `point_kind = memory` instead of `knowledge`.
5. **Feedback loop (added session 4): a visitor's unanswerable question becomes a
   queued "knowledge gap," not a dead end.** When the twin can't answer, the
   question is saved for the owner; when the owner is next active, they answer it;
   that answer is chunked/embedded into this same twin's collection as a new
   `Source`, so the same question is answerable next time. "Not for the random
   person who communicates with it" — the gap is owned by the twin, answered by
   the twin's real owner, not by whoever happened to ask.

Schema implemented in §8 (session 3 + session 4 changes).

---

## 2. Architecture

### 2.1 Target architecture (where this is heading)

```mermaid
flowchart LR
    subgraph Client
        ST[Streamlit Frontend]
    end

    subgraph API["FastAPI (backend/main.py) — IMPLEMENTED session 7"]
        R1[/twins/]
        R2[/twins/{id}/sources/]
        R3[/twins/{id}/chat/]
    end

    subgraph Services["Service layer — IMPLEMENTED session 7"]
        TS[TwinService]
        DS[SourceService]
        CS[ConversationService]
    end

    subgraph Data
        PG[(PostgreSQL\nusers, twins, sources,\naccess_tiers, conversations, messages)]
        QD[(Qdrant\ncollection per twin:\n twin_&lt;twin_id&gt;)]
    end

    subgraph Agent["LangGraph Agent (backend/agent/)"]
        RET[retrieve_node]
        GEN[generate_node]
    end

    LLM[Groq LLM\nvia langchain-groq]

    ST -->|HTTP| API
    R1 --> TS --> PG
    R2 --> DS --> PG
    R2 --> DS --> QD
    R3 --> CS --> PG
    CS --> Agent
    RET --> QD
    GEN --> LLM
    RET --> GEN
```

### 2.2 What actually runs today (verified by `test_rag_pipeline.py`)

```mermaid
flowchart LR
    TXT[Raw text string] --> CHK["RecursiveCharacterTextSplitter\n(chunk_size=500, overlap=50)"]
    CHK --> EMB["FastEmbed\nBAAI/bge-small-en-v1.5 (384-dim)"]
    EMB --> UP["upsert_chunks()\nbackend/vectordb/operations.py"]
    UP --> QD[(Qdrant collection\ntwin_&lt;twin_id&gt;)]

    Q[User question] --> EMB2[embed query] --> SRCH["search_twin_knowledge()\nvisibility filter"]
    QD --> SRCH
    SRCH --> CTX[context_documents]
    CTX --> GRAPH

    subgraph GRAPH["LangGraph: backend/agent/graph.py (2 nodes, linear)"]
        RN[retrieve_node] --> GN[generate_node]
    end
    GN --> GROQ[ChatGroq / Groq API] --> ANS[Answer string]
```

Note what's **missing** from this picture vs. the target: no Postgres write anywhere
in this path (no `Source` row, no `Conversation`/`Message` row), no document grading, no
hallucination check, no query-rewrite retry, no `policy_decision`/`confidence_score`
output — the graph always answers, never declines/escalates.

### 2.3 Data model (current, uncommitted `backend/db/models.py`)

```mermaid
erDiagram
    USERS ||--o{ TWINS : owns
    TWINS ||--o{ SOURCES : "has (registry only, no text)"
    TWINS ||--o{ ACCESS_TIERS : defines
    TWINS ||--o{ CONVERSATIONS : hosts
    CONVERSATIONS ||--o{ MESSAGES : contains

    USERS {
        uuid id PK
        string email
        string password_hash
        string display_name
    }
    TWINS {
        uuid id PK
        uuid owner_id FK
        string name
        text bio
        text persona_prompt
    }
    SOURCES {
        uuid id PK
        uuid twin_id FK
        string source_type "upload/github/linkedin/manual"
        string visibility "public/friends/private"
        string status "pending/processing/completed/failed"
        int chunk_count
        string storage_path
    }
    ACCESS_TIERS {
        uuid id PK
        uuid twin_id FK
        string tier_name
        string allowed_visibilities "csv"
    }
    CONVERSATIONS {
        uuid id PK
        uuid twin_id FK
        string visitor_name
        string access_tier
        bool is_owner_session
    }
    MESSAGES {
        uuid id PK
        uuid conversation_id FK
        string role "visitor/twin/system"
        text content
        string policy_decision "answer/decline/escalate"
        float confidence_score
        int latency_ms
        jsonb sources_json
    }
```

`SOURCES` intentionally holds **no document text** — that lives only in Qdrant, linked
back by `source_id` in the point payload (a logical, non-FK link). This is a real
design upgrade over the original schema (which had `documents` + `document_chunks`
tables storing raw text and char offsets in Postgres as well as in Chroma — duplicated
storage). The tradeoff: the old chunker tracked exact `char_start`/`char_end` offsets
for gold-span evaluation; the new chunker (`RecursiveCharacterTextSplitter`) does not
preserve offsets at all. Flagged as an open decision in §5.

---

## 3. Component-by-component status

| Component | File(s) | Status | Notes |
|---|---|---|---|
| FastAPI app / routers | `backend/main.py`, `backend/api/*` | ✅ **Implemented (session 7)** | `/twins`, `/twins/{id}/sources/{upload,text}`, `/twins/{id}/chat`, `/health`. Verified against a real running server, not just imports. No auth layer yet — `owner_id`/`visitor_id` are trusted directly from request bodies, flagged clearly in both router files. |
| Service layer | `backend/services/*` | ✅ **Implemented (session 7)** | `TwinService` (create+seed tiers, delete incl. Qdrant collection), `SourceService` (thin wrapper over `IngestionPipeline`), `ConversationService` (resolves access tier server-side from `AccessGrant` — never client input — loads prior turns for real multi-turn context, invokes the agent, persists the audit trail). |
| DB session/engine | `backend/db/session.py` | ✅ Working | SQLAlchemy 2.0 style, `get_db()` FastAPI dependency ready to reuse. |
| DB models | `backend/db/models.py` | ✅ **v2 implemented** (uncommitted) | 13 tables, all 4 scope-expansion decisions built in. No Alembic migrations — needs a destructive reset against the existing dev DB (see §8.1). |
| DB init script | `backend/db/init_db.py` | ✅ Working | `create_all()` only; `--reset` drops the whole schema (dev-only, destructive). |
| Config | `backend/config.py` | ✅ **Consolidated** | `Settings` now owns every env var (`GROQ_API_KEY`, `GROQ_MODEL`, `QDRANT_PATH`, `QDRANT_COLLECTION_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `CHUNK_SIZE`, `CHUNK_OVERLAP`) — no more raw `os.getenv()` in application code. |
| Embeddings + chunking | `backend/rag/embeddings.py` | ✅ **Session 6: offsets + batching added** | FastEmbed model + splitter still built lazily. `chunk_text()` now uses `add_start_index=True` to attach exact `char_start`/`char_end` per chunk (verified: `text[start:end] == chunk`). `embed_texts()` now batches (`INGEST_BATCH_SIZE`) instead of one unbounded call. File parsing now exists — `backend/ingestion/parser.py` (PDF/DOCX/TXT/MD). |
| Qdrant client/collections/ops | `backend/vectordb/*` | ✅ **Silo model (reverted from pool, session 4)** | One collection PER TWIN again (`twin_<twin_id>`), by the user's decision — isolation is physical, not a remembered filter. `client.py` is still a lazy `get_client()` singleton (that part of session 3 stayed). `operations.py` still tags every point `point_kind` (`knowledge`/`memory`) within a twin's own collection — that tagging dimension didn't go away, only the twin_id payload field did (redundant once the collection itself is the tenant boundary). `collections.py` now also has `delete_twin_collection()` — dropping a whole collection is the natural "delete everything for this twin" op in the silo model, no filtered bulk-delete needed. The local-Qdrant payload-index caveat found in session 3 still applies, now scoped to `point_kind`/`visitor_id` indexes instead of `twin_id` (which would've been pointless to index anyway — constant within a single-twin collection). |
| Retriever | `backend/rag/retriever.py` | ✅ **Rebuilt for silo** | `search_twin_knowledge` + `search_visitor_memory` resolve `twin_collection_name(twin_id)` and check `collection_exists()` first, returning `[]` for a brand-new twin with nothing ingested yet instead of raising — this fixes the original "fragile" bug properly this time (session 1 just flagged it; session 3's pool model made it moot by accident; session 4 fixes it for real now that silo brought the original failure mode back). |
| LangGraph agent | `backend/agent/{graph,nodes,state}.py` | ✅ **Self-corrective (Phase 4, session 8)** | `retrieve → grade_documents → [conditional: transform_query once if plausibly-relevant-but-weak] → generate`. `generate_node` uses structured output (`TwinReply{answer, grounded}`) instead of prose pattern-matching — `grounded=False` becomes `policy_decision="escalate"`. Fixed the session-7 bug (ignored conversation history for meta-questions) by splitting the prompt into "conversational — use history freely" vs "factual claims about the twin — must be grounded"; verified live: "what is my name?" after "my name is Sarah" now correctly answers "Sarah" instead of "I don't know." `ChatGroq` still lazy. |
| LLM client wrapper | `backend/llm/*` | ❌ **Deleted, not rebuilt** | No dedicated client/prompt-template module yet — `get_llm()` lives directly in `nodes.py`. Fine for now; revisit when Phase 4 adds grading prompts. |
| Ingestion pipeline/orchestrator | `backend/ingestion/*` | ✅ **Implemented (session 6); GitHub import added (session 15)** | `IngestionPipeline.ingest_file()`/`.ingest_text()`: parse → chunk+offsets → batch-embed → idempotent delete-then-upsert → `Source` status/chunk_count. Full design + embedding-strategy reasoning in [`backend/ingestion/FLOW.md`](backend/ingestion/FLOW.md). `fetchers.py` (session 15) adds `fetch_github_profile()` — a public GitHub profile+repos import feeding the same `ingest_text()` path; LinkedIn deliberately not built (ToS blocks scraping — user's explicit call, paste it as a text note instead). Verified end-to-end by `test_ingestion_pipeline.py` against live Postgres + Qdrant (text, .txt, .md ingestion; retrieval; idempotent reprocess; parse failure; oversized-doc rejection), and the GitHub path verified live through the real UI (see session 15 changelog). |
| Frontend | `frontend/` (React 19 + TS + Vite + MUI v9) | ✅ **Rewritten from Streamlit (session 13); discovery gallery + mandatory avatar/voice (session 14); whole-app visual redesign + sidebar nav + Conversations (session 19)** | Streamlit fully removed. Real SPA: owner/visitor auth, twin CRUD incl. mandatory avatar+voice at creation (3-step wizard), a visitor-facing click-to-talk gallery (no handle needed), knowledge ingestion (text/file/voice note/GitHub), access grants, knowledge gaps (multi-agent clustering), housekeeping (duplicate/contradiction scan), **conversation history browsing (session 19, new)**, text chat, push-to-talk voice messages, and a VAD-based hands-free "Call Mode." Twin management pages use a persistent sidebar with live badge counts (session 19), not a flat tab bar. Each twin clones its own owner-recorded voice for spoken replies. Verified live end to end against the real API every session — see session 19's changelog entry for the latest full pass. A real MUI v9 breaking-API bug was found and fixed across 14 files (session 13); a Fast-Refresh/AuthContext fragility was found and fixed (session 16). |
| Auth | `backend/services/auth_service.py`, `backend/api/{auth,deps}.py` | ✅ **Implemented (session 9)** | bcrypt password hashing for owners, JWT bearer tokens (7-day TTL, `HS256`, signed with `SECRET_KEY`) for both owners and passwordless visitors. Closes the session-7 gap for real: `owner_id`/`visitor_id` are no longer client-supplied fields anywhere — derived from the token via `get_current_user`/`get_current_user_optional`. Honest limitation, stated in the code: visitor login is passwordless by design (§8) but nothing verifies the visitor actually controls the email they log in with — that needs a real magic-link flow, not built. |
| Access grants API | `backend/services/access_service.py`, `backend/api/grants.py` | ✅ **Implemented (session 9)** | `access_grants` (schema since session 4) finally has a create/list/revoke API. Verified live: a visitor denied private content before a grant, allowed after, denied again after revocation. Simplification stated in the code: always find-or-creates the visitor's `User` row immediately rather than using `AccessGrant.invited_email`'s pending-claim path — that flow is real future work, not needed to make granting access function end to end today. |
| Knowledge-gap API | `backend/services/knowledge_gap_service.py`, `backend/api/knowledge_gaps.py` | ✅ **Implemented (session 9); multi-agent clustering + curation (session 17)** | `knowledge_gaps` (schema since session 4, got a live *creation* trigger in session 8) finally has the other half: list pending questions, answer one (routes through the exact same `IngestionPipeline` as any other source — `source_type=escalation_answer`), or dismiss it. Session 17 adds two agents on top: `backend/agent/gap_analyst.py` clusters pending gaps by topic, `backend/agent/curator.py` drafts clean knowledge-base text + a suggested visibility tier from the owner's raw answer — draft-only, owner approves before anything saves. Verified live end to end, including proving the Analyst genuinely merges near-duplicate questions rather than passing them through 1:1. |
| Housekeeping (duplicate/contradiction scan) | — | ❌ **Removed (session 20)** | Built session 18, removed session 20. Worked correctly on small test data (see session 18's verification) but couldn't be made to perform acceptably on a real twin's full knowledge base within a synchronous HTTP request — see session 20's changelog entry for the full story. All of `backend/agent/housekeeper.py`, `backend/services/housekeeping_service.py`, `backend/api/housekeeping.py`, the frontend tab, and the orphaned vectordb helper functions were deleted outright, not deprecated in place. |
| Tests | `test_db.py`, `test_rag_pipeline.py`, `test_ingestion_pipeline.py`, `test_api_auth_flow.py` | ⚠️ Smoke scripts, now v2-complete | `test_db.py` round-trips all 14 tables once, including `knowledge_gaps`. `test_rag_pipeline.py` verified end-to-end against the per-twin Qdrant collection + real Groq call. `test_ingestion_pipeline.py` (session 6) verified ingestion correctness and idempotency. `test_api_auth_flow.py` (session 9, requires a running server) verified the full auth → grant → chat → revoke → knowledge-gap-answered loop against real HTTP calls. Still no `pytest`/CI (Phase 5). |
| Dependency manifest | `requirements.txt` | ✅ **Cleaned up** | Removed `chromadb`/`langchain-chroma`/`sentence-transformers`/`langchain-huggingface` (unused). Added `qdrant-client`, `fastembed`, `pydantic-settings`, `langchain-text-splitters` (all actually imported). `alembic` removed until Phase 6 actually adds migrations. |
| Migrations | — | ❌ Missing | `alembic` is in `requirements.txt` but **not installed** in `.venv`, and no `alembic/` dir exists. Schema changes currently require a destructive `--reset`. |
| Voice (backend-only) | `backend/voice/{audio_utils,asr,tts,pipeline}.py` | ✅ **Real cloning confirmed (session 11)** | `voice_chat()`: audio in → faster-whisper → the existing `ConversationService` (unchanged) → Pocket TTS (now the user's actual cloned voice by default) → audio out. No live call, no WebRTC — callable as a Python function / `test_voice_pipeline.py` only, no API route yet (deliberate). Real bug found and fixed this session: the full 47s reference recording produced reproducible garbage output; a trimmed 12s clip fixed it — see §9.5. Confirmed: cloning-capable model is itself ~3x slower than the preset-voice one. |
| Docs | — | ❌ Missing | No README anywhere in the repo prior to this file. |

---

## 4. Environment variables (names only — see local `.env`, never commit values)

All consolidated into `backend/config.py Settings` now — nothing reads `os.getenv()`
directly anywhere in the codebase:
- `DATABASE_URL` — Postgres connection string
- `SECRET_KEY`, `DEBUG` — declared, not actually used anywhere yet
- `GROQ_API_KEY`, `GROQ_MODEL` (default `llama-3.3-70b-versatile`; local `.env`
  currently overrides this to `openai/gpt-oss-120b`)
- `QDRANT_PATH` (default `./qdrant_storage`), `QDRANT_COLLECTION_PREFIX` (default
  `twin_` — each twin's collection is `{prefix}{twin_id}`, see §8)
- `EMBEDDING_MODEL` (default `BAAI/bge-small-en-v1.5`), `EMBEDDING_DIM` (default
  `384`, must match the Qdrant collection's vector size), `CHUNK_SIZE` (500),
  `CHUNK_OVERLAP` (50)

`.env` still has the old commented-out `CHROMA_PERSIST_DIR` / `CHROMA_COLLECTION_NAME`
/ `EMBEDDING_MODEL` / `CHUNK_SIZE` / `CHUNK_OVERLAP` block from the ChromaDB era —
fully superseded by `Settings` defaults now, safe to delete whenever, not touched by
this session (didn't want to edit a file holding live secrets unnecessarily).

`QDRANT_PATH` still points at a **local embedded/file-mode** Qdrant client
(`QdrantClient(path=...)`), confirmed during session 3's verification: the client
itself prints `Payload indexes have no effect in the local Qdrant. Please use server
Qdrant if you need payload indexes`. Filtering still works correctly (brute-force scan
over payloads), it just isn't index-accelerated yet — now relevant to the
`point_kind`/`visitor_id` indexes inside each twin's own collection rather than a
cross-tenant `twin_id` index (silo model, §8, doesn't need that one at all). Also
still single-process-only — will conflict with a running FastAPI server (especially
`--reload`/multiple workers) touching the same path concurrently. Decision needed
before Phase 3 (see §6 roadmap).

---

## 5. Open decisions / known traps for the next phase

1. **Chunk provenance**: new chunker doesn't track `char_start`/`char_end` like the old
   one did. Needed only if gold-span evaluation is part of the FYP evaluation chapter —
   otherwise fine to leave as-is.
2. **Qdrant deployment mode**: embedded file client vs. a real Qdrant server (Docker).
   Recommendation: keep embedded for now (simplicity for a single FastAPI dev process),
   revisit only if concurrent access becomes a real problem.
3. **Field-name drift vs. the old (deleted) service/API code**: if any of that old code
   is referenced while rebuilding, note these renames in the new schema:
   - `Twin.description` (old) → `Twin.bio` (new)
   - `User.hashed_password` (old) → `User.password_hash` (new)
   - old `Message.is_escalated: bool` → folded into `Message.policy_decision` enum
     (`ESCALATE` is one of its values now) — don't re-add the boolean column.
4. **Config duplication**: decide to fully migrate all env access through
   `backend/config.py Settings`, and stop reading `os.getenv()` directly in
   `vectordb/client.py` and `agent/nodes.py`.
5. **Module-level singletons** (`ChatGroq(...)` in `nodes.py`, `TextEmbedding(...)` in
   `embeddings.py`, `QdrantClient(...)` in `vectordb/client.py`) all execute at import
   time. Fine for a script; will cause import-order/crash problems once these modules
   are imported by a FastAPI app or test collector without credentials available. Should
   become lazy factory functions (`get_llm()`, `get_embedder()`, `get_client()`).

---

## 6. Phased plan (preserves everything that currently works)

**Phase 0 — Safety checkpoint**
Commit the current working-tree state (the ChromaDB→Qdrant migration + new agent
skeleton) so it's no longer at risk of being discarded by an accidental git operation.
Clean up `requirements.txt` to match actual imports.

**Phase 1 — Config & lifecycle consolidation**
Move all env vars into `Settings`. Convert the module-level `ChatGroq` / `TextEmbedding`
/ `QdrantClient` singletons into lazy factory functions.

**Phase 2 — Ingestion pipeline — ✅ done (session 6).**
See [`backend/ingestion/FLOW.md`](backend/ingestion/FLOW.md) for the full flow,
embedding/chunking reasoning, and known limitations. Reused the old `parser.py`
logic as-is (confirmed Chroma-agnostic, as predicted here). Built
`IngestionPipeline` (`backend/ingestion/pipeline.py`) as the one place allowed to
write knowledge chunks, idempotent by construction (delete-then-upsert on every
attempt, including retries).

**Phase 3 — Service + API layer — ✅ done (session 7).**
`backend/main.py` + routers (health, twins, sources, chat) + `TwinService`/
`SourceService`/`ConversationService`. `Conversation`/`Message` rows now get
persisted with `latency_ms`/`sources_json` populated for real;
`policy_decision` is set to a static `"answer"` and `confidence_score` stays
`None` until Phase 4 actually produces them from grading — not faked here.
Verified against a real running server (see changelog) — including a finding
that matters for Phase 4: multi-turn history is correctly wired through to the
LLM, but `generate_node`'s current prompt is strict enough about "answer ONLY
from retrieved context" that it refuses to use that history even for trivial
meta-questions ("what's my name", right after being told). Confirmed by
isolating retrieval from history in a live test — not a bug in the new service
layer, a concrete, now-proven thing for Phase 4 to fix.

**Phase 4 — Strengthen the agent graph — ✅ done (session 8).**
Relevance grading (similarity threshold, no extra LLM call) + a bounded
query-rewrite retry + structured-output grounding classification, replacing the
old (deleted) `rag/graph.py`'s heavier per-document LLM grading and separate
hallucination-check call with something cheaper but still genuinely
self-corrective. Full detail in the changelog and the component table above.
**Not ported from the old design**: an independent post-generation hallucination
check (a second LLM call auditing the answer against context) — the self-reported
`grounded` field from the same generation call was judged good enough for this
phase's cost/benefit; a true independent check stays a documented future option.

**Phase 5 — Frontend — ✅ done (session 12).** Real `pytest` suite still not done
— `test_db.py`/`test_rag_pipeline.py`/etc. are still smoke scripts with asserts,
not a pytest/CI setup. `frontend/app.py` built from scratch against the current
API (the old deleted version was never a useful starting point — different
schema, different everything by this point). See §12 and the changelog.

**Phase 6 — Polish / defense-readiness**
Alembic migrations, docker-compose for Postgres (+ Qdrant server if moved off embedded
mode), README.

Waiting for approval before starting any phase.

---

## 8. Schema v2 — implemented (revised session 4: silo Qdrant + feedback loop)

Implemented in `backend/db/models.py` (14 tables) and verified by import (SQLAlchemy
mapper configuration succeeds — see changelog) and by `test_db.py` (round-trips every
table once — session 4 run hit the expected "needs another reset" wall, see below, not
a bug). Qdrant side implemented in `backend/vectordb/` and `backend/rag/` and verified
end-to-end by `test_rag_pipeline.py` against a real Groq call, both as a pooled
collection (session 3) and after reverting to per-twin collections (session 4).

### 8.1 Required before this runs against your local Postgres

**You already ran one reset this project (session 3) — you need to run it again**
after session 4's changes, for a different reason this time: session 4 added a brand
new table (`knowledge_gaps`) AND added a new allowed value
(`escalation_answer`) to `sources.source_type`'s `CHECK` constraint. A plain
`create_all()` adds missing tables but never alters an existing table's `CHECK`
constraint — the live `sources` table still has the OLD constraint without
`escalation_answer` in it, so inserting that source type fails until reset. Confirmed
this directly: `test_db.py` ran successfully through all 12 prior steps and failed
exactly at the `knowledge_gaps` insert with `UndefinedTable`, exactly as expected.

```bash
python -m backend.db.init_db --reset
```

Destructive DB operations are never run automatically here — run it yourself, then
`python test_db.py` to repopulate and confirm all 14 tables round-trip, including the
new knowledge-gap lifecycle.

The Qdrant side needs nothing from you. Session 3 added a pooled `twin_knowledge`
collection; session 4 reverted to per-twin collections and reused the original
`twin_test-twin-001` collection from session 1 (confirmed: searches now only return
points tagged with the new `point_kind` field, so old pre-tagging points from session
1 are silently excluded by the filter — correct behavior, not data loss). Both
`twin_knowledge` (session 3) and the untagged points inside `twin_test-twin-001` are
now orphaned dead data, a few KB — harmless to leave, delete whenever:
`rm -rf qdrant_storage/collection/twin_knowledge`.

Five responsibility groups. Each group's reasoning:

### Identity & tenancy
- `users` — **unified** identity for both twin owners and visitors (not two
  separate account tables). Reasoning: a person can be an owner of one twin and a
  visitor on someone else's; one identity graph avoids an account-linking problem
  later. `password_hash` becomes nullable (null = passwordless/magic-link-only
  account).
- `twins` — add `slug` (unique, human-readable public URL/invite handle).
- `access_grants` **(new)** — `twin_id`, `visitor_id` (nullable until an invited
  email claims an account), `invited_email` (nullable), `tier_name`, `granted_by`,
  `granted_at`, `expires_at` (nullable — time-limited sharing), `revoked_at`
  (nullable — **soft** revoke, keeps audit history). Partial unique index:
  `UNIQUE (twin_id, visitor_id) WHERE revoked_at IS NULL`. This is also a **security
  fix**: the old (deleted) `ChatRequest.access_tier` let the *client* claim any tier
  string with zero server verification. The tier must now be resolved server-side
  from `access_grants` and snapshotted onto `conversations.access_tier` at creation —
  never trusted from request input again.
- `access_tiers` — unchanged (tier name → allowed visibilities), stays orthogonal to
  *who* holds a tier.

### Twin knowledge (profile content)
- `sources` — unchanged role (registry, no text). Extend `SourceType` with
  `VOICE_TRANSCRIPT` / `VIDEO_TRANSCRIPT`; add nullable `media_asset_id` FK so a
  transcript's source row can point back to the recording it came from.
- `twin_attributes` **(new)** — `twin_id`, `key`, `value`, `visibility`. Small stable
  facts ("hometown", "favorite food") injected directly into the persona prompt —
  cheap, always available, no retrieval-miss risk. `UNIQUE(twin_id, key)`.
- `schedule_entries` **(new)** — `twin_id`, `day_of_week`/`specific_date` (exactly
  one set), `start_time`, `end_time`, `label`, `visibility`. Deliberately **not**
  embedded into Qdrant — availability needs exact queries, not semantic similarity.
  Future extension worth flagging: give the agent a tool/node that queries this table
  directly for "are you free Tuesday?" questions, parallel to the vector-retrieval
  node — a nice structured-tool-use addition beyond plain RAG.
- `media_assets` **(new)** — `twin_id`, `asset_type` (voice_sample/video_sample),
  `storage_path`, `duration_seconds`, `format`, `status`, `error_message`,
  **`consent_confirmed_at` (required before status can become `ready`)**. Feeds a
  different downstream consumer than `sources` (a voice-clone/avatar model, not the
  retriever) — that's why it's a separate table. The consent field is a real
  ethical/legal necessity when cloning someone's voice/likeness — worth a paragraph
  in the FYP's ethics section, not just a schema afterthought.

### Interaction
- `conversations` — add `channel` (text/voice). `access_tier` now resolved from
  `access_grants`, never client-supplied.
- `messages` — unchanged (still the audit trail: policy_decision, confidence_score,
  latency_ms, sources_json).
- `call_sessions` **(new)** — `conversation_id` (1:1), `started_at`, `ended_at`,
  `duration_seconds`, `recording_path` (nullable), `recording_consent_at` (nullable),
  `end_reason`. Turn-by-turn content still flows through `messages` (ASR transcript
  as a visitor message, generated reply as a twin message) — call_sessions only
  carries call-specific metadata on top.

### Memory
- `visitor_profile_facts` **(new)** — `twin_id`, `visitor_id`, `key`, `value`,
  `source_message_id` (nullable, provenance). `UNIQUE(twin_id, visitor_id, key)` —
  re-learning a fact just upserts it.
- `memory_chunks` **(new)** — `twin_id`, `visitor_id`, `origin_conversation_id`,
  `created_at`. Mirrors what `sources` is for documents: a lifecycle/deletion
  registry for memory text embedded in Qdrant. Concretely solves "a visitor asks what
  the twin knows about them deleted" — `DELETE FROM memory_chunks WHERE visitor_id=?`
  gives the exact Qdrant point ids to purge, no payload-scanning needed.

### Feedback loop (added session 4)
- `knowledge_gaps` **(new)** — `twin_id`, `conversation_id`, `question_message_id`,
  `question_text` (denormalized off the message — small deliberate duplication so a
  notification/listing query needs no join, and survives even though messages
  cascade-delete with their conversation), `status` (pending/answered/dismissed),
  `answer_text`, `answered_at`, `resulting_source_id` (→ `sources.id`, `ON DELETE
  SET NULL` — deliberately **not** cascade: if the resulting source is later
  deleted, the historical record that this gap existed and was answered should
  stay). This is the concrete mechanism behind "the twin asks the real owner when
  it doesn't know something, and remembers the answer" — not built in this session
  (that's agent/service logic, Phase 3/4), but the data structure for it now exists.
  `sources.source_type` gained `escalation_answer` so a source created this way is
  distinguishable from a manually-added note.

### Qdrant — silo model (one collection per twin, reverted from pool in session 4)
Each twin gets its own collection, named `{QDRANT_COLLECTION_PREFIX}{twin_id}`
(`backend/vectordb/collections.py: twin_collection_name()`). Tenant isolation is
physical — there is no `twin_id` payload field at all anymore, because it would be
constant (and therefore useless to filter or index) within a collection that already
belongs to exactly one twin. Within that collection, points still carry `point_kind`
(`knowledge` | `memory`) so one twin's collection serves both its own documents and
its visitors' memory. Knowledge points carry `source_id` + `visibility`; memory
points carry `visitor_id` + `memory_chunk_id`. Knowledge retrieval and memory
retrieval are still two separate top-k calls, merged at the agent level.
`ensure_twin_collection(twin_id)` is called internally by every upsert (fixing, for
real this time, the "forgot to ensure the collection exists" fragility flagged back
in session 1); `search_twin_knowledge`/`search_visitor_memory` check
`collection_exists()` first and return `[]` for a twin with nothing ingested yet,
rather than raising. `delete_twin_collection(twin_id)` drops a twin's entire
collection in one call when the twin itself is deleted.

---

## 9. Real-time voice/video call architecture (research, session 5 — not implemented)

Researched, not built: the user asked how to make a twin that clones the owner's
voice and face for a live video call, with latency good enough to "feel like a real
person." No code changed this session — this is a technology/architecture decision
record, written up because it determines a lot of what Phase 2/3 eventually need to
plug into.

### Reality check
Sub-second, naturalistic real-time voice+video cloning is the frontier of what
funded companies (Tavus, HeyGen, Synthesia) build with dedicated teams. Realistic for
an FYP: **compose existing specialized real-time APIs** rather than building
ASR/TTS/avatar models — the actual engineering work is pipelining them with
streaming end-to-end and tuning turn-detection, not training models.

### The pipeline (see the rendered diagram this session)
A continuous streaming loop, not a request/response chain: WebRTC transport → STT →
LLM+RAG (Groq) → TTS (cloned voice) → avatar (lip-sync) → back through transport.
Postgres/Qdrant writes (`messages`, `call_sessions`) happen **off the hot path** —
never a synchronous DB round-trip inside the per-utterance loop.

### Per-stage findings (web research this session, Oct 2026 — cite before acting on exact numbers, this space moves fast)
- **Transport/orchestration**: LiveKit Agents or Pipecat, both WebRTC-based. A naive
  sequential pipeline (wait for each stage to fully finish) is 2–4s — unusable.
  Streaming/overlapping every stage boundary (STT partials → LLM → TTS starts on
  partial tokens) is what gets to sub-1s.
- **STT**: **Groq does not appear to offer true streaming ASR** — its Whisper
  endpoints are extremely fast *batch* transcription (throughput, not a WebSocket
  partial-transcript API). Don't reuse Groq here; pick a dedicated streaming STT
  (Deepgram is the most commonly cited for production low-latency streaming).
- **LLM**: Groq is exactly the right tool for *this* stage (fast time-to-first-token)
  — reuse the existing `backend/agent/` retrieve→generate graph, but
  `generate_node`'s `get_llm().invoke(...)` ([backend/agent/nodes.py](t2-rag/backend/agent/nodes.py))
  **must become `.stream()`**, pushing tokens to TTS as they arrive instead of
  waiting for the full response — the single most important code change this
  implies for later.
- **TTS (voice cloning)**: Cartesia (Sonic — fastest, ~40–90ms time-to-first-byte
  depending on source, smaller voice library) vs. ElevenLabs (Flash v2.5 ~75ms
  model-only / Turbo v2.5 ~275ms at higher quality, bigger library, "Instant"/
  "Professional" voice cloning from a short sample). Given the user's stated
  priority is latency, lean Cartesia; vendor TTFB figures exclude network, so
  measure end-to-end yourself.
- **Avatar (lip-synced video)**: all WebRTC-based, latency claims not apples-to-apples
  (measure user-stops-talking → first avatar frame yourself). Tavus (sub-600ms,
  strongest for perceived emotional realism — their stated differentiator), Simli
  (<300ms claimed, cheaper/simpler), Anam (~150ms server-gen, plugs directly into
  LiveKit/Pipecat/ElevenLabs), HeyGen LiveAvatar (most mature SDK + interruption
  handling, but their older Interactive Avatar API sunsets 2026-03-31). For an FYP
  budget, start with Simli or Anam; treat the avatar vendor as swappable (LiveKit
  itself documents multiple avatar integrations behind the same interface).
- **The real risk is NOT the model picks.** A LiveKit community report: ASR
  (~100ms) + LLM (~500ms) + TTS (~200ms) summed to under 1s on paper, but measured
  end-to-end latency was 3–4 seconds — the gap was end-of-turn/VAD detection,
  buffering before the end-of-speech event, and client/outbound audio queuing,
  none of which show up in naive per-component timing. **Instrument capture-to-
  first-audio from the user's side, not individual model call durations.**

### How this connects to the schema already built (§8)
- `media_assets` (voice_sample/video_sample, `consent_confirmed_at`) is exactly the
  raw material these TTS/avatar vendors clone from — and now the consent field
  matters doubly: that recording is about to leave the project and go to a
  third-party API, which is worth a paragraph in the FYP's ethics chapter (whose
  terms govern a cloned biometric voice/face, where it's processed).
- `call_sessions` (`recording_path`, `recording_consent_at`, `duration_seconds`,
  `end_reason`) is written once at call start/end — never inside the live loop.
- The per-twin Qdrant collection (§8) still serves retrieval for the LLM+RAG stage
  exactly as already built; it just needs to stay fast (small `top_k`, already true)
  since it's one of the few synchronous calls still inside the hot path (context is
  needed before generation can start).

### Recommended phasing (unchanged in spirit from the session-2 decision, now concrete)
1. Get the voice-only loop (STT → Groq streaming → TTS) under ~1s real, measured
   end-to-end, before touching video at all — this is hard enough alone.
2. Add the avatar on top once voice latency is solid — it mostly just consumes the
   audio stream that already exists by then.
3. Tune turn-detection/interruption handling last, expecting it to be the dominant
   latency and "does this feel real" factor, not the vendor picks.

Sources (web research, Oct 2026): [HeyGen Streaming Avatars docs](https://docs.heygen.com/docs/streaming-avatars-api), [Fora Soft: real-time avatar lipsync](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/real-time-avatar-lipsync-in-call), [veed.io: best live avatar APIs](https://www.veed.io/learn/best-live-avatar-api), [LiveKit: voice agent architecture (STT/LLM/TTS pipelines explained)](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained), [LiveKit community: high end-to-end latency thread](https://community.livekit.io/t/high-end-to-end-latency-asr-llm-tts-total-1s-but-speech-end-to-reply-takes-3-4s-livekit-agents/1277), [futureagi: optimizing Pipecat latency](https://futureagi.com/blog/how-to-optimize-pipecat-latency-2026/), [Cartesia alternatives roundup](https://smallest.ai/blog/best-cartesia-alternatives-for-real-time-tts-in-2026), [pkgpulse: ElevenLabs vs OpenAI TTS vs Cartesia](https://www.pkgpulse.com/guides/elevenlabs-vs-openai-tts-vs-cartesia-text-to-speech-2026), [Groq ASR Model Guide (PDF)](https://groq.com/GroqDocs/Groq%20ASR%20Model%20Guide.pdf).

### 9.1 Pivot: free/open-source only, not paid vendor APIs (same session)

User decision: build this with free/open-source, self-hostable components instead of
composing paid vendor APIs (Tavus/HeyGen/Cartesia/ElevenLabs/Deepgram) — explicitly
to actually build the system, not just integrate it, which is also the more
defensible FYP position. This makes the problem **harder**, not easier: now the user
is also responsible for model hosting, GPU memory contention across concurrently
running models, and inference optimization that vendors previously handled.

Open-source candidates per stage (web research this session — verify against each
project's repo before committing, this field moves fast):
- **STT**: `faster-whisper` (CTranslate2, GPU) + the `whisper_streaming` wrapper
  (chunking/VAD/local-agreement on top — Whisper itself has no native streaming
  mode) is the most-cited self-hosted real-time path on NVIDIA hardware;
  `whisper.cpp` (+ Vulkan) for AMD/CPU/portable setups. Latency is governed more by
  chunk size and VAD tuning than by model size. Known failure modes to plan for:
  hallucinated text during silence, garbled words at chunk boundaries.
- **TTS (voice cloning)**: **Fish Speech** (Apache 2.0, 10–30s reference clip,
  aimed at real-time voice agents) and **VoxCPM2** (OpenBMB, Apache 2.0, 2B params,
  cloning+design+TTS, released April 2026) are the licensing-safe picks.
  **CosyVoice2-0.5B** claims ~150ms streaming latency (vendor figure, verify).
  **XTTS v2** (Coqui) is the most battle-tested and has a documented Pipecat
  integration (~0.45s TTFB via vLLM serving, voice-conditioning cached once from
  the reference clip) — but its license (CPML) is non-commercial only. For a
  non-commercial FYP that's likely fine; flag it explicitly if this is ever
  productized later.
- **Avatar (talking head)**: **MuseTalk** is the clearest fit — it doesn't
  synthesize a face from scratch, it re-syncs the *mouth region* on an **existing
  reference video** to new audio, hitting 30fps+ on a V100 (datacenter GPU, not a
  confirmed consumer-GPU number). This maps directly onto `media_assets`'
  `video_sample` already in the schema (§8): the owner's uploaded video becomes the
  loop MuseTalk redraws the mouth on, driven by the live TTS audio. Other options
  found and why they're worse fits: LatentSync (ByteDance, best quality, full
  diffusion, too heavy for real-time), LivePortrait (full-face portrait animation,
  no confirmed real-time benchmark), NVIDIA Audio2Face (open-sourced Sept 2025, but
  for 3D character rigs, not 2D photoreal video), Livatar-1 and SoulX FlashHead
  (newer real-time-claimed research/vendor models, worth tracking but less proven).
- **LLM**: left open as a genuine open question — see below.
- **Transport**: no change needed. WebRTC itself is free regardless of vendor
  choice, and LiveKit's media server is separately self-hostable (open-source),
  distinct from LiveKit's paid cloud offering.

**Two gating questions asked back to the user, answers not yet known:**
1. What hardware will actually run these models (GPU and how much VRAM, CPU-only,
   or cloud-free-tier)? This determines almost everything above — MuseTalk and GPU
   Whisper both assume a real GPU; without one, a video avatar is not realistically
   achievable and the honest fallback is voice-only.
2. Does "free of cost" also rule out continuing to use Groq for the LLM stage (it's
   free-tier, not self-hosted)? Self-hosting an LLM with comparable token-generation
   speed on student-grade hardware is a large additional burden that directly
   competes with TTS/avatar for the same GPU memory — recommended default is to
   keep Groq (it's already integrated and working, and is genuinely hard to beat
   for speed at no cost) and spend the self-hosting effort on STT/TTS/avatar only,
   but this is the user's call.

Sources (this sub-section): [Fora Soft: Tavus/HeyGen/Synthesia lip-sync avatars in production](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/tavus-heygen-synthesia-lip-sync-avatars-production), [sync.so: what is MuseTalk](https://sync.so/blog/what-is-musetalk), [sync.so: what is SadTalker](https://sync.so/blog/what-is-sadtalker), [Livatar-1 paper](https://arxiv.org/html/2507.18649v1), [siliconflow: best open source models for voice cloning 2026](https://www.siliconflow.com/articles/best-open-source-models-for-voice-cloning), [betterstack: VoxCPM2 local TTS](https://betterstack.com/community/guides/ai/voxcpm2-local-tts.md), [Pipecat XTTS-vLLM service docs](https://docs.pipecat.ai/api-reference/server/services/tts/xtts-vllm), [dograh: self-hosting Whisper for real-time streaming](https://www.dograh.com/feeds/blog/self-host-whisper-streaming), [whisper_streaming repo](https://github.com/ufal/whisper_streaming).

### 9.2 Answers to the gating questions: CPU-only, keep Groq — this rules video out live

User answered both: **no dedicated GPU (CPU-only)**, and **keep Groq for the LLM,
self-host everything else**. This resolves the architecture, with one hard
consequence worth stating plainly: **every real-time-capable open-source avatar
model found (MuseTalk, LatentSync, LivePortrait, Audio2Face) needs a GPU — none
have a CPU real-time story.** A live neural video avatar is not realistically
achievable on CPU-only hardware with current open-source models. This isn't
pessimism, it's what every source checked this session says.

**The good news is on the voice side.** Found **Pocket TTS** (Kyutai, released
2026-01-13): a 100M-parameter model that does zero-shot voice cloning from ~5
seconds of reference audio, MIT-licensed, and — unusually for a cloning model —
runs on CPU (secondary sources report ~6x realtime on a MacBook Air M4 using 2 CPU
cores, ~200ms to first audio). This is the one to prototype first; benchmark on the
user's actual Windows laptop, not assume Apple-Silicon-class numbers transfer.
(Piper is the other well-known CPU-native TTS, but it ships with fixed preset
voices, not cloning — adding cloning to it means routing through Chatterbox, which
is itself GPU-oriented, defeating the point.)

**Revised, CPU-only, open-source stack:**
- LLM: Groq (unchanged — hosted, free-tier, not a local CPU burden)
- ASR: `faster-whisper`/`whisper.cpp` on CPU, a small model (tiny/base), + the same
  chunking/VAD streaming wrapper discussed in §9.1
- TTS (cloned voice): Pocket TTS — needs real benchmarking on target hardware
  before trusting the vendor-adjacent ~200ms figure
- Avatar: **not live, on current hardware** — see options below

**Checked whether a free cloud GPU closes the avatar gap — mostly no:**
Colab and Kaggle free tiers are both explicitly unsuited to persistent low-latency
serving (Colab's ToS allows terminating a runtime without warning if it's used to
serve a web UI; both have idle timeouts measured in tens of minutes, not hours).
**Hugging Face ZeroGPU** is more interesting: it attaches a real, large GPU for
free inside a Gradio app, callable per-request (~60s cap per call) — theoretically
usable as a serverless backend for one MuseTalk call at a time, while everything
else stays local on CPU. Untested and genuinely uncertain: whether the round-trip to
a shared/queued free GPU service adds enough latency to defeat the entire purpose.
Worth a real benchmark before building around it, not assuming it works.

**Three honest options for video, in order of how much they preserve the original
vision:**
1. Defer video entirely — matches the phasing already decided in §9.1/session 2:
   get the voice-only loop solid first, treat video as a stretch goal.
2. Try HF ZeroGPU as a serverless MuseTalk backend — real option, unvalidated,
   measure round-trip latency before committing any build time to it.
3. Scope "video" down to something CPU-cheap: a simple viseme/cutout animation
   (map audio amplitude/phonemes to a small set of pre-drawn mouth shapes on a
   still image) instead of full neural lip-sync. Much lower fidelity than MuseTalk,
   but genuinely real-time on CPU and still demonstrates "the twin's face responds
   live to its voice" — a legitimate scoped-down deliverable, not a cop-out.

**Decided: option 1, voice-only is the target for now, video revisited later.** The
real-time call build target is Groq (LLM) + faster-whisper/whisper.cpp (ASR) +
Pocket TTS (cloned voice) over WebRTC, with no avatar/video component in scope until
this loop is solid. Video (ZeroGPU-backed MuseTalk, or the cheaper viseme/cutout
fallback) stays a documented future phase, not abandoned — just sequenced after.

### 9.3 Pocket TTS benchmarked for real on this machine — result: not fast enough yet (session 9)

The thing flagged as "check before building more" back in session 5 finally got
checked. Installed `pocket-tts` and `faster-whisper` for real (scratch benchmark
scripts + sample audio kept in `voice_bench/`, not part of the application).

**Result: Pocket TTS on this CPU (Intel Core, no GPU) runs at roughly 0.75–0.98x
realtime — i.e. generating N seconds of speech takes slightly MORE wall-clock time
than N seconds, even with int8 quantization enabled.** This directly contradicts
the secondary-source claim from session 5 ("~6x realtime on a MacBook Air M4,
~200ms to first audio") — that number does not transfer to this hardware at all.
Measured with the model loaded once and three different sentences generated
steady-state (excluding one-time model load, ~3.5–5.5s):

| Sentence | Audio length | Generation time | Realtime factor |
|---|---|---|---|
| "Hi there, I'm Umair's digital twin." | 2.88s | 3.86s (no quant) / 3.05s (int8) | 0.75x / 0.89x |
| "I'm a final year student..." | 2.88s | 3.09s / 2.94s | 0.93x / 0.98x |
| "Let me know if you have..." | 3.92s | 4.67s / 4.02s | 0.84x / 0.93x |

A realtime factor below 1.0x means generation can never catch up to playback —
the opposite of what a live conversation needs (you want generation meaningfully
*faster* than realtime so time-to-first-audio is low and a long reply doesn't
accumulate growing lag). int8 quantization helped (0.75–0.93x → 0.89–0.98x) but
didn't cross the 1.0x line even once.

**Also discovered**: actual voice-*cloning* weights for Pocket TTS are gated
behind accepting terms on `huggingface.co/kyutai/pocket-tts` and a local `hf auth
login` — not just free-and-open as the secondary sources implied. The benchmark
above used a built-in catalog voice instead (architecture-bound generation speed
is the same either way; only the voice *identity* differs) specifically because
cloning requires the user's own HF account action, not something to do on their
behalf.

**faster-whisper (ASR) was not conclusively benchmarked this session** — the
script got stuck downloading `base.en`/`small.en` model weights for over 20
minutes (almost certainly a slow/throttled connection, not inference — `tiny.en`
loaded fine) and was killed rather than left blocking further work. Not reported
as a result either way; re-run `voice_bench/benchmark_asr.py` when bandwidth
allows. (Separately confirmed and fixed: `faster-whisper` 1.2.1's `decode_audio()`
passes `metadata_errors=` to PyAV, which the installed PyAV 19.0.1 doesn't accept
— a real dependency-version-skew bug on this machine, worked around by decoding
the WAV with the stdlib `wave` module instead of letting faster-whisper call PyAV.)

**What this means for the plan**: the voice-only real-time loop, as scoped, is
not viable on this hardware with Pocket TTS as currently measured — a reply would
visibly lag further behind as it got longer, the opposite of "feels like a real
person." Options, not yet decided:
1. A different self-hosted TTS model, if one actually clears >1.5–2x realtime on
   this CPU (CosyVoice2's claimed 150ms latency was never a wall-clock-realtime-
   factor claim and wasn't benchmarked here) — needs the same honest benchmark
   treatment, not another secondary-source number taken on faith.
2. Accept non-live generation (pre-render replies, no live call) — a real scope
   cut from the original "video call" vision.
3. Revisit a paid low-latency vendor (Cartesia/ElevenLabs, §9.1) for just the TTS
   stage specifically, keeping everything else self-hosted — a partial reversal
   of the "free, self-hosted" principle, for this one stage only, if the user
   decides the quality bar matters more than that principle here.
Not decided this session — needs the user's call once they've seen this result.

### 9.4 Decision: proceed anyway, backend capability first (session 10)

User's call after seeing §9.3: no budget for a paid TTS vendor right now, and
explicitly okay with the slow replies for now — "we will look at it later." So:
build the voice round-trip with what's already installed (Pocket TTS + faster-
whisper), accept the latency, revisit speed as a separate future problem. Also
chose, given a live call needs a whole frontend/WebRTC layer that doesn't exist
yet, to build a **backend-only capability first**: send an audio file in, get an
audio file back, no browser UI yet. That's what got built this session.

**New package `backend/voice/`:**
- `audio_utils.py` — WAV decode/resample/encode via stdlib `wave` + `scipy`, not
  via faster-whisper's own (broken on this machine) PyAV call. Also handles a
  real correctness issue, not just a benchmark convenience: Pocket TTS outputs
  24kHz audio, Whisper expects 16kHz — feeding one into the other without
  resampling would silently mis-transcribe. `resample_to_16k()` exists because of
  this specific, checked fact, not as defensive boilerplate.
- `asr.py` — `transcribe_file()`, lazy-loaded `faster-whisper` model (CPU, int8).
  Default model is `tiny.en` (small enough to download reliably; upgrade to
  `base.en`/`small.en` later for accuracy — `ASR_MODEL_SIZE` in `Settings`).
- `tts.py` — `synthesize()`, lazy-loaded Pocket TTS model. Bridges `HF_TOKEN` from
  `Settings` into `os.environ` explicitly, since `huggingface_hub` (which Pocket
  TTS uses for model/voice downloads) reads it from the process environment, not
  from this project's pydantic config — without this bridge, `HF_TOKEN` in `.env`
  would silently do nothing for anyone running the app via `uvicorn` directly
  (as opposed to a script that calls `load_dotenv()` itself). Defaults to the
  catalog voice `alba`; pass a path to a recorded sample as `voice_ref` once real
  cloning is set up.
- `pipeline.py` — `voice_chat()`: audio in → `transcribe_file()` → the **existing**
  `ConversationService.chat()` (unchanged, not duplicated — a voice turn gets the
  exact same grounding/access-tier/audit-trail logic a text turn does) →
  `synthesize()` → audio out. Returns per-stage timing in milliseconds.
- `backend/config.py` — added `ASR_MODEL_SIZE`, `TTS_LANGUAGE`, `TTS_QUANTIZE`,
  `TTS_DEFAULT_VOICE`, `HF_TOKEN`.
- `requirements.txt` — added `pocket-tts`, `faster-whisper`, `scipy`.

**What's needed from the user to go further, stated plainly (not something I can
substitute)**: (1) an actual recording of their voice — cloning needs a real
sample, there's no way around that; (2) accepting Kyutai's terms at
`huggingface.co/kyutai/pocket-tts` plus an `HF_TOKEN` in `.env` for real cloning
specifically (the benchmark and this session's test both used the catalog voice
`alba` instead, since neither of those two things exists yet).

**Verified for real** — `test_voice_pipeline.py`: synthesized a spoken question
with TTS (standing in for a real mic recording, since none exists yet), ran it
through the full round trip, and checked correctness, not just that it ran:
- ASR (tiny.en) transcribed "What technologies does Umair use for his project?"
  as "What technologies does **Umar** use for his project?" — a real, visible
  accuracy limitation of the smallest model (one letter dropped from a name), not
  a pipeline bug. Close enough that downstream retrieval still worked; a reason
  to upgrade `ASR_MODEL_SIZE` once bandwidth allows, not urgent now.
- The agent still answered correctly despite that transcription error:
  "Umair's T2-RAG project leverages PostgreSQL, Qdrant, Groq, and FastAPI" —
  correctly grounded in the one source ingested for this test.
- **Full round-trip timing, measured, one real turn**: ASR 3.9s + chat 6.8s + TTS
  29.7s = **~40.4s total**, producing 7.36s of output audio. The TTS figure here
  is higher than §9.3's steady-state 0.89–0.98x realtime measurement because this
  was the first call in a fresh process — it includes one-time model load, not
  just generation. Both numbers are real and both matter: §9.3's is what a
  long-running server settles to once warm; this 40s figure is what one cold
  script invocation actually felt like, which is closer to today's honest
  experience of calling this once. Either way, the conclusion from §9.3 stands:
  this is not fast, and that's an accepted, deferred tradeoff, not a hidden one.

Not done: wiring this into `backend/main.py` as an actual endpoint (it's only
callable as a Python function / via the test script right now — no
`/twins/{id}/voice-chat` route exists yet, deliberately: wanted the plumbing
proven correct before deciding its API shape), real voice cloning (blocked on
the two user-provided things above), and anything resembling a live call
(WebRTC, browser audio — a separate, larger, explicitly deferred piece of work).

### 9.5 Real voice cloning confirmed working — plus a real bug found and fixed (session 11)

User provided both blocking items from §9.4: a recording
(`fyp_audio testing.ogg`, copied into the project at
`data/voice_samples/umair_voice_sample.ogg`) and `HF_TOKEN` in `.env` (added
under a different key name, `fyp-voice-cloning-token` — renamed to `HF_TOKEN`
via a key-only `sed` rename so the token value itself never passed through this
conversation).

**First real result, with the full 47-second recording**: the cloning-capable
model (confirmed downloading correctly once `HF_TOKEN` was present — a ~260s
one-time fetch, then 2–5s to load from cache after) produced **garbage/truncated
output, every time, reproducibly** — asked for a 10-word sentence, got 0.72s of
audio that transcribed as "that." or similar fragments, regardless of what text
was requested. Isolated with a same-text, different-voice comparison: the
catalog voice `alba` produced a correct, full-length 3.28s result for the exact
same sentence; the cloned voice did not. Tried `frames_after_eos` (the one knob
`pocket-tts` exposes for "stops too early") up to 60 — this didn't fix content,
just padded the output with repeated filler: *"That's that magic. Yeah. That's
it. That's it. That's it."* That filler phrase is the actual diagnosis: the file
is 47 seconds and literally named "testing" — very likely the tail end has
off-topic mic-testing speech ("okay, that's it" or similar), and the model was
partly echoing that regardless of the requested text, rather than cleanly
treating the file as a pure style/voice reference independent of its content.

**Fix, confirmed**: trimmed the reference to its first 12 seconds
(`umair_voice_sample_trimmed.wav`, same directory) — cloning became correct and
reliable immediately. Re-tested the exact same sentence that failed before:
produced 3.12s of audio, transcribed back as "what technology does who may use
for his project" (the ASR mangling "Umair" is a `tiny.en` accuracy limit, not a
TTS problem) — correct content, right length. `backend/config.py`'s
`TTS_VOICE_SAMPLE_PATH` now defaults to the trimmed clip, with the reasoning and
the "keep future recordings to a clean 10-30s, nothing before/after" lesson
written directly into the comment, not just here.

**Full pipeline re-verified end to end with the fix in place**
(`test_voice_pipeline.py`, real run): question synthesized correctly (3.12s,
using the now-default cloned voice) → transcribed → agent answered correctly,
grounded: *"Umair's T2-RAG project leverages PostgreSQL for the database,
Qdrant for vector search, Groq for inference, and FastAPI to expose the
service."* → synthesized back correctly. Timing for this run: ASR 4.5s + chat
4.5s + TTS 19.4s (model and voice state already warm from the question-audio
step earlier in the same process — the one-time clone-setup cost, now much
smaller for a 12s clip than it was for the original 47s one, only has to be
paid once per process per voice, exactly as `backend/voice/tts.py`'s
`_voice_state_for` caching was designed to do).

**Confirmed, not assumed**: the cloning-capable model really is slower than
the preset-voice one — real cost of cloning specifically, separate from Pocket
TTS's general sub-realtime finding in §9.3. Both audio clips (the broken 47s
version transcribing as "that." and the corrected 12s version) were sent to the
user directly to judge sound quality themselves — that's not something
measurable from this end.

Sources (this sub-section): [dev.to: Pocket TTS review (Kyutai)](https://dev.to/andrew-ooo/pocket-tts-review-kyutais-100m-cpu-voice-cloner-2026-40lb), [resemble.ai: best open source AI voice cloning tools](https://www.resemble.ai/best-open-source-ai-voice-cloning-tools/), [promptquorum: Piper vs Chatterbox TTS](https://www.promptquorum.com/power-local-llm/piper-vs-chatterbox-tts), [hivenet: Google Colab GPU limitations guide](https://www.hivenet.com/post/google-colaboratory-gpu-complete-guide-to-free-cloud-gpu-access-and-limitations), [Google Colab official FAQ](https://research.google.com/colaboratory/faq.html).

---

## 12. Frontend (Streamlit) — session 12

`frontend/app.py` is a pure HTTP client against `backend/main.py` — every action
goes through the real API (`requests`), nothing talks to the DB or service layer
directly. That was a deliberate choice: it's the thing that actually proves the
whole stack works together end to end, not just each piece in isolation, and it's
exactly how the bug below got found.

### Backend additions needed first
- `GET /twins/by-slug/{slug}` (`backend/api/twins.py`) — slugs existed since §8
  specifically as a shareable handle, but had no lookup route until the frontend
  actually needed one. Registered *before* `/twins/{twin_id}` in the router so
  "by-slug" isn't swallowed as a twin_id path parameter.
- `POST /twins/{twin_id}/voice-chat` (`backend/api/voice.py`, new) — the first API
  route for the voice capability built in sessions 10–11, which until now was only
  callable as a Python function/test script. Audio in as a multipart upload, JSON
  out (answer text, transcription, sources, timing, and the reply audio as
  base64) — simpler for Streamlit to consume in one response than a separate
  audio-serving endpoint, at a ~33% size cost on an already-small file.
- `backend/voice/audio_utils.py` upgraded from stdlib-`wave`-only decoding to
  `soundfile` — needed so the UI's upload widget (and a browser mic recording)
  can hand over whatever format they produce (ogg/mp3/wav/...), not just 16-bit
  PCM WAV. Still bypasses faster-whisper's own (broken on this machine, §9.3)
  PyAV-based decode path — just with a more capable decoder underneath.
- `backend/api/grants.py`'s `GrantResponse` gained `visitor_email` (resolved from
  `AccessGrant.visitor.email`, built manually in the route rather than via
  `response_model` auto-conversion, since it's not a plain column on the ORM
  object) — showing a raw visitor UUID in a grants list is much less useful than
  their email.

### A real bug found while building this, not invented for the demo
`ConversationService.resolve_access_tier()` had no special case for the twin's
*own owner* — testing the owner's own twin from the UI, a private fact was
invisible until an explicit `AccessGrant` existed, even though
`Conversation.is_owner_session` has existed in the schema since the beginning
specifically for this and was never once set `True` anywhere. Fixed: the owner
now always resolves to the twin's highest-privilege tier (`'private'`, by the
seeding convention in `TwinService`), and `is_owner_session` is actually set.
`get_or_create_conversation`/`resolve_access_tier` now take the loaded `Twin`
object instead of just `twin_id`, both to make this check possible and to avoid
a redundant query.

### Verified live, in a real browser (not just "the code runs")
Started both servers for real (`.claude/launch.json`, backend on :8000, frontend
on :8501) and drove the actual UI:
- Registered an owner, created a twin, ingested a public note through the UI —
  retrieval and chat both worked, correctly grounded.
- Ingested a *private* note, asked about it as the owner with **no grant at
  all** — correctly answered, confirming the owner-access fix above for real,
  not just by reading the diff.
- Granted a second identity `friends`-tier access, logged in as that visitor,
  asked about the same private fact — correctly **denied**, and gracefully
  escalated into a pending `KnowledgeGap`, visible back on the owner's
  Knowledge Gaps tab.
- Answered that gap through the UI — it left the pending list, became a new
  `Source`.
- The Voice tab's record/upload widget needs a native OS file-picker dialog,
  which this session's browser automation can't drive — so instead verified
  `POST /twins/{id}/voice-chat` directly against the same live server: correctly
  used the owner's private knowledge in a spoken answer (same access-control fix
  holding through the voice path too), returned valid, playable audio. Steady
  -state timing on a warm server: ASR ~0.9s, chat ~1s, TTS ~15s — consistent
  with §9.5's finding that cloned-voice generation itself (not setup) is the
  real, ongoing cost, not a one-time tax. Also directly verified
  `POST /twins/{id}/sources/upload` (the file-ingestion path used by the
  Knowledge tab), which had never been exercised through the real API before —
  only through the service layer directly (`test_ingestion_pipeline.py`).

### Not done
Twin profile editing (no `PATCH /twins/{id}` exists — the Overview tab is
read-only), any visual design polish beyond Streamlit's defaults, and the voice
tab's record/upload path specifically couldn't be driven by this session's
browser automation (verified via direct API call instead, see above) — a human
clicking through it is still worth doing once.

---

## 7. Changelog

> Append-only. Newest entry at the bottom. One entry per change, dated, with a short
> **why**.

### 2026-10-15 — Initial architecture audit
- Read entire project tree, git history (`git show HEAD:*` for all deleted files),
  current working-tree code, `.venv` installed packages, and `.env` variable names
  (values not read into this file).
- Created this `CLAUDE.md`. **No code, config, or dependencies were changed.**
- Findings summarized in §1–§5 above; phased plan proposed in §6, awaiting approval.

### 2026-10-15 (session 2) — Scope expansion + schema v2 design
- User revealed the real project scope: multi-modal profile ingestion (schedule,
  preferences, voice samples, video of the owner speaking), privacy grants to named
  specific people (not just a public/friends/private tier label), voice/video calling
  with the twin, and long-term memory scoped per visitor.
- Walked through 4 architecture decisions with the user (Qdrant tenancy model,
  visitor identity model, call-feature scope for this phase, memory storage split);
  user picked the recommended option on all four — see §1 scope note and §8.
- Produced a full v2 schema proposal (5 responsibility groups: identity & tenancy,
  twin knowledge, interaction, memory, pooled Qdrant) — written up in §8.
- Rendered two inline diagrams for the user (current ERD; v2 group architecture) to
  fix a complaint that the Mermaid ERD in this file doesn't render in their local
  markdown viewer (Mermaid needs a renderer — GitHub.com or a VS Code Mermaid
  extension; plain preview shows it as code).
- **No code changed.** Schema v2 is a design only, awaiting the user's go-ahead to
  implement against `backend/db/models.py`, `backend/vectordb/`, and the (not yet
  rebuilt) ingestion/service/API layers.

### 2026-10-15 (session 3) — Schema v2 implemented

Files changed:
- `backend/config.py` — rewritten: `Settings` now declares every env var the
  codebase reads (added `GROQ_API_KEY`, `GROQ_MODEL`, `QDRANT_PATH`,
  `QDRANT_COLLECTION_NAME`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `CHUNK_SIZE`,
  `CHUNK_OVERLAP`).
- `backend/db/models.py` — rewritten to the 13-table v2 schema from §8: unified
  `users` (nullable `password_hash`), `twins.slug`, new `access_grants` (soft-revoke,
  partial unique index on the active grant), new `twin_attributes`,
  `schedule_entries` (exactly-one-of-day_of_week/specific_date CHECK), new
  `media_assets` (consent-before-completed CHECK), `sources.media_asset_id` +
  `SourceType` extended with `VOICE_TRANSCRIPT`/`VIDEO_TRANSCRIPT`,
  `conversations.visitor_id`/`channel`, new `call_sessions` (1:1 with a
  conversation), new `visitor_profile_facts`, new `memory_chunks`.
- `backend/vectordb/client.py` — `client` module-level singleton → lazy
  `get_client()` (`functools.lru_cache`).
- `backend/vectordb/collections.py` — `ensure_twin_collection(twin_id)` (silo model)
  → `ensure_knowledge_collection()` (pool model): one collection, payload indexes on
  `twin_id`/`point_kind`/`visitor_id`.
- `backend/vectordb/operations.py` — `upsert_chunks` → `upsert_knowledge_chunks`
  (tags `point_kind=knowledge`) + new `upsert_memory_chunks` (tags
  `point_kind=memory`); added `delete_visitor_memory`, `delete_twin_points`.
- `backend/rag/retriever.py` — `search_twin_knowledge` updated for the pooled
  collection's filter shape; added `search_visitor_memory`.
- `backend/rag/embeddings.py` — module-level `embedding_model`/`text_splitter`
  singletons → lazy `get_embedder()`/`get_splitter()`; `process_document()` no
  longer takes `source_id`/`visibility` (that metadata now attached at upsert time,
  not chunk time — keeps this module reusable for memory text too).
- `backend/agent/state.py` — added `visitor_id`, `memory_documents`.
- `backend/agent/nodes.py` — module-level `ChatGroq`/`llm` singleton (crashed on
  import without `GROQ_API_KEY`) → lazy `get_llm()`; `retrieve_node` now also calls
  `search_visitor_memory` when a `visitor_id` is present; `generate_node` injects
  the visitor-memory text into the system prompt alongside persona + knowledge.
- `test_db.py` — rewritten to round-trip all 13 v2 tables once.
- `test_rag_pipeline.py` — rewritten for the pooled collection + memory path; added
  a UTF-8 stdout fix (Windows console defaulted to cp1252, couldn't print a
  typographic space character Groq returned).
- `requirements.txt` — removed `chromadb`/`langchain-chroma`/`sentence-transformers`/
  `langchain-huggingface`/`alembic` (unused); added `qdrant-client`, `fastembed`,
  `pydantic-settings`, `langchain-text-splitters` (all actually imported).

Verification performed this session:
- `backend.db.models` imports cleanly — SQLAlchemy accepted every relationship/FK
  across all 13 tables (would fail loudly at import time if misconfigured).
- All of `vectordb`, `rag`, `agent` import cleanly, including `agent.nodes` without a
  `GROQ_API_KEY` crash (confirms the lazy-init fix).
- `ensure_knowledge_collection()` run for real: created `twin_knowledge` in the
  existing local `qdrant_storage/`, alongside the now-orphaned `twin_test-twin-001`.
  Surfaced the local-Qdrant payload-index limitation — documented in §4 and §8.1.
- `test_rag_pipeline.py` run for real end-to-end (real Groq call): 1 knowledge chunk
  and 1 memory chunk upserted, then LangGraph's `retrieve_node` correctly pulled
  both back (2 knowledge + 2 memory hits across two runs) and `generate_node`
  produced a grounded answer. Confirms the pool-model filter shape
  (`twin_id`+`point_kind`+`visibility`/`visitor_id`) actually retrieves correctly,
  not just that the code runs.
- Did **not** run `backend.db.init_db --reset` against the local Postgres (it has
  the old schema loaded — confirmed by inspection) — that's destructive, left for
  the user to run deliberately (§8.1).
- Did **not** run `test_db.py` for the same reason (needs the reset first).

Still not done (unchanged from session 1's roadmap): FastAPI app/routers, service
layer, ingestion pipeline (file parsing + orchestration), self-corrective grounding
in the agent graph, Streamlit frontend, real pytest tests, Alembic migrations.

### 2026-10-15 (session 4) — Qdrant tenancy reverted to silo + knowledge-gap feedback loop

User decision: collection-per-twin instead of the pooled model from session 3 —
isolation should be physical, not a filter every query has to remember. Also
introduced a new requirement in the same breath: when a visitor asks something the
twin can't answer, the question should queue for the real owner to answer once
they're next active, and that answer should become new knowledge in that twin's own
collection — not something a random visitor's conversation should ever create or
poison.

Files changed:
- `backend/db/models.py` — added `KnowledgeGapStatus` enum and `KnowledgeGap` table
  (14th table); added `Twin.knowledge_gaps` relationship; added
  `SourceType.ESCALATION_ANSWER`; updated the module docstring's Qdrant section to
  describe per-twin collections instead of a shared pool.
- `backend/config.py` — `QDRANT_COLLECTION_NAME` (one shared name) →
  `QDRANT_COLLECTION_PREFIX` (default `twin_`, combined with a twin_id per
  collection).
- `backend/vectordb/collections.py` — rewritten: `ensure_knowledge_collection()`
  (pool) → `ensure_twin_collection(twin_id)` + `twin_collection_name(twin_id)`
  helper (silo) + `delete_twin_collection(twin_id)`. Payload indexes now on
  `point_kind`/`visitor_id` only (no `twin_id` index — constant within one twin's
  collection, so indexing it would buy nothing).
- `backend/vectordb/operations.py` — every upsert function now calls
  `ensure_twin_collection(twin_id)` internally and writes to that twin's own
  collection; dropped the `twin_id` payload field (redundant once the collection
  itself is the tenant boundary) and the pool-era `delete_twin_points()` (superseded
  by `delete_twin_collection()` — dropping a whole collection is simpler than a
  filtered bulk-delete once isolation is physical).
- `backend/rag/retriever.py` — rewritten: both search functions resolve
  `twin_collection_name(twin_id)` and check `collection_exists()` first, returning
  `[]` for a twin with nothing ingested rather than letting the client raise — the
  original session-1 "fragile" bug, properly fixed now that silo brought back the
  failure mode session 3's pool model had accidentally made moot.
- `test_rag_pipeline.py` — one line changed (`ensure_knowledge_collection()` →
  `ensure_twin_collection(twin_id)`); upsert/search call sites didn't need to change,
  since those functions kept the same external signature across the revert.
- `test_db.py` — added a `KnowledgeGap` smoke-test block: create a gap from an
  existing message, then answer it by creating a `Source`
  (`source_type=escalation_answer`) and linking `resulting_source_id`.

Verification performed this session:
- `backend.db.models` imports cleanly with 14 tables; all of `vectordb`/`rag`/`agent`
  import cleanly.
- `test_rag_pipeline.py` run for real end-to-end against the per-twin collection:
  reused the original `twin_test-twin-001` collection from session 1, correctly
  retrieved only the newly-tagged knowledge/memory points (old pre-`point_kind`
  points from session 1 correctly excluded by the filter — confirms tagging, not a
  data-loss bug), and produced a grounded Groq answer.
- `test_db.py` run for real: succeeded through all 12 prior steps (reusing the
  Postgres state from session 3's reset) and failed exactly at the new
  `knowledge_gaps` insert with `UndefinedTable` — expected, confirms a second reset
  is needed and pinpoints exactly why (see §8.1). Not re-run after that — the reset
  is the user's call, not run automatically.

Still not done: same list as session 3 (FastAPI, services, ingestion pipeline,
self-corrective grounding, frontend, pytest, Alembic) — this session stayed
deliberately scoped to the database layer per the user's request, not the services
layer.

### 2026-10-15 (session 5) — Real-time voice/video call architecture research

User asked how to actually clone the owner's voice and face for a live video call
with "feels like a real person" latency, explicitly pausing before more coding to
think the architecture through. No code changed — this was research + a design
writeup, captured in full in new §9 above.

Did: 4 targeted web searches (real-time avatar APIs, streaming TTS/voice-cloning
latency, LiveKit/Pipecat pipeline architecture, Groq ASR streaming support) and
synthesized them into a 5-stage streaming pipeline (transport → STT → LLM+RAG → TTS
→ avatar), a vendor shortlist per stage, and a phased build order. Key finding worth
repeating here because it changes the plan: Groq has no evident true streaming ASR
endpoint (batch-only, if very fast batch) — it stays as the LLM stage (its actual
strength) but a different vendor (e.g. Deepgram) is needed for the STT stage. Also
flagged a concrete, specific future code change: `backend/agent/nodes.py`'s
`generate_node` currently calls `get_llm().invoke(...)` (blocks for the full
response) and will need `.stream()` once this is built, to start TTS before the LLM
finishes generating.

Rendered two diagrams for the user (not reproduced here — see chat): the pipeline
architecture, and (implicitly reused) this session's running mental model of where
Postgres/Qdrant sit relative to the hot path.

Nothing implemented. Next step is the user's call: continue the architecture
conversation, or move to coding one of the still-open phases.

**Update, same session:** pivoted away from paid vendor APIs entirely — user wants
this actually built, free/open-source and self-hosted, not just integrated (§9.1).
Answered the two gating questions (CPU-only hardware, keep Groq for the LLM), which
ruled out live video on current hardware (§9.2) and landed on a concrete CPU-only
voice stack: Groq + faster-whisper/whisper.cpp + Pocket TTS. **Confirmed: voice-only
is the build target now, video explicitly deferred, not abandoned.** Still nothing
implemented — the next message should say whether we're moving into code (and
where: the ASR/TTS prototype, or back to the FastAPI/service layer) or continuing to
plan.

### 2026-10-16 (session 6) — Ingestion pipeline (Phase 2) implemented

User picked Phase 2 next, with two explicit asks beyond just "build it": make it
solid and scalable, and explain the embedding-model/chunking-strategy reasoning
through a dedicated flow doc + diagram rather than folding it into CLAUDE.md.

Files added/changed:
- `backend/config.py` — added `MAX_INGEST_CHARS` (500,000, a CPU-only-hardware guard
  against a pathological upload stalling embedding) and `INGEST_BATCH_SIZE` (64).
- `backend/rag/embeddings.py` — `get_splitter()` now passes `add_start_index=True`;
  new `chunk_text()` returns exact `(chunk, char_start, char_end)` triples (verified:
  `text[start:end] == chunk`, not a best-effort re-search); `embed_texts()` now
  batches instead of one unbounded call; `process_document()` gained an `"offsets"`
  key, kept `"chunks"`/`"embeddings"` unchanged for backward compatibility.
- `backend/ingestion/parser.py` **(new)** — ported byte-for-byte in spirit from the
  pre-migration deleted version (PDF/DOCX/TXT/MD → text + whitespace cleanup);
  confirmed Chroma-agnostic as predicted back in session 1's audit.
- `backend/ingestion/pipeline.py` **(new)** — `IngestionPipeline`: `ingest_file()`
  and `ingest_text()`, both routing through a shared `_process()` that chunks,
  embeds, idempotently clears any existing points for that `source_id` before
  upserting new ones, and only marks the `Source` `completed` after the Qdrant
  write succeeds. Failure path best-effort cleans up partial Qdrant writes before
  marking `Source` `failed` and raising `IngestionError`.
- `test_ingestion_pipeline.py` **(new)** — exercises text ingestion, file ingestion
  (.txt and .md, through the real format dispatcher), retrieval of what was just
  ingested, idempotent reprocessing (asserts point count doesn't double), a parse
  failure (missing file), and an oversized-document rejection — with real `assert`s,
  not just prints.
- `backend/ingestion/FLOW.md` **(new)** — the flow (steps, mermaid diagram, why no
  two-phase commit), and the full embedding-model/chunking reasoning the user asked
  for (why FastEmbed over sentence-transformers, why `bge-small` over
  base/large, why 500 chars / 10% overlap).

Verification performed this session: ran `test_ingestion_pipeline.py` for real
against live Postgres + Qdrant — every check passed, including the idempotency
assertion (point count unchanged after reprocessing the same source) and both
failure-path assertions.

Rendered the ingestion flow as a diagram for the user (not reproduced here — the
same content lives as a mermaid block in `FLOW.md`).

Still not done: FastAPI/routers, service layer, self-corrective grounding, frontend,
real pytest suite, Alembic, GitHub/LinkedIn fetchers, markdown-heading-aware
chunking (noted as a deliberately deferred nice-to-have in `FLOW.md`).

### 2026-10-16 (session 7) — FastAPI + service layer (Phase 3) implemented

User picked Phase 3 next from an explicit menu of options (self-corrective grounding,
validating the voice stack on real hardware, or the frontend were the alternatives).

Files added:
- `backend/services/twin_service.py` — `TwinService`: create (auto-slugifies the
  name if no slug given, seeds the three default `AccessTier` rows), get, list by
  owner, delete (drops the twin's Qdrant collection first via
  `delete_twin_collection`, then the Postgres row cascades).
- `backend/services/source_service.py` — `SourceService`: thin wrapper saving an
  uploaded file to `UPLOAD_DIR` before handing it to `IngestionPipeline`; list;
  delete (clears Qdrant chunks via `delete_source_chunks` then the row).
- `backend/services/conversation_service.py` — `ConversationService`, the one with
  real design weight: `resolve_access_tier()` is the SERVER-SIDE-ONLY resolution
  from `AccessGrant` (never trusts a client-supplied tier — the security fix flagged
  repeatedly since session 2); `get_or_create_conversation()` snapshots the
  resolved tier onto the conversation at creation; `_load_history()` reconstructs
  prior turns as LangChain messages (the graph has no checkpointer, so without this
  every call would only ever see the latest message); `chat()` ties it together and
  persists the audit trail.
- `backend/api/{health,twins,sources,chat}.py` + `backend/main.py` — routers and the
  FastAPI app. `TwinCreateRequest`/`ChatRequest` both carry explicit comments that
  `owner_id`/`visitor_id` are trusted with zero verification because there is no
  auth layer yet — not silently assumed, called out in the code itself.
- `backend/config.py` — added `UPLOAD_DIR`.

Verification performed this session — against a REAL running server, not just
imports: started `uvicorn backend.main:app` in the background, then through actual
HTTP calls: created an owner + a twin (slug auto-generated correctly), ingested a
text source (`status=completed`, `chunk_count=1`), ran a two-turn chat that got a
correctly grounded, cited answer on turn 1, then specifically investigated an
unexpected result on turn 2.

**Finding, not a bug in this session's code**: a follow-up question ("what did I
just ask you?", later isolated further with "my name is Sarah" / "what is my
name?") got "I don't know" instead of using visible conversation history. Isolated
the cause with a second live test (a name with zero overlap with the twin's
knowledge, to separate retrieval from history): confirmed the message history IS
being passed to the LLM correctly — the failure is `backend/agent/nodes.py`'s
`generate_node` system prompt being strict enough ("answer the user's question
using ONLY the following retrieved context... state that you do not know") that
the model disregards available history even for trivial meta-questions. Deliberately
**not fixed this session** — it's exactly the kind of thing Phase 4
(self-corrective grounding) should address properly, and now there's a concrete,
reproduced test case to verify against when that happens, instead of a vague
"the agent is too simple" note.

Still not done: self-corrective grounding (Phase 4, now with a concrete bug to fix),
frontend, real pytest suite, Alembic, auth (flagged as a real gap in the API code
itself, not hidden).

### 2026-10-16 (session 8) — Self-corrective grounding (Phase 4) implemented

User picked Phase 4 over starting a multi-agent router or validating the voice
stack, after a short discussion distinguishing "multi-step grounding graph" from
"true multi-agent routing between different kinds of queries" — Phase 4 is the
former; a router is real but premature until there's a second kind of query
(e.g. structured schedule lookups) to route to.

Files changed:
- `backend/config.py` — added `RETRIEVAL_MIN_SCORE` (0.25) and
  `RETRIEVAL_REWRITE_SCORE` (0.15).
- `backend/agent/state.py` — added `raw_top_score`, `rewrite_count`,
  `search_query_override`, `policy_decision`, `confidence_score`, all read via
  `.get(key, default)` in the nodes so existing callers didn't need to change
  their initial-state dicts.
- `backend/agent/nodes.py` — rewritten: `grade_documents_node` (new, drops
  knowledge chunks below `RETRIEVAL_MIN_SCORE`, no LLM call); `should_rewrite`
  (new, the conditional-edge function — only triggers `transform_query_node` if
  the top score was close-but-not-quite, to avoid wasting a retrieval round-trip
  rewriting a plain greeting); `transform_query_node` (new, one bounded query
  rewrite); `generate_node` rewritten around a new `TwinReply(answer, grounded)`
  Pydantic model via `get_llm().with_structured_output(...)` — `grounded=False`
  becomes `policy_decision="escalate"`. **This is also where the session-7 bug
  got fixed**: the prompt now explicitly separates "conversational continuity —
  use history freely" from "factual claims about the twin — must be grounded,"
  instead of the old blanket "answer using ONLY the retrieved context."
- `backend/agent/graph.py` — rewritten for the new 4-node conditional graph
  (retrieve → grade_documents → [transform_query → retrieve, looped once] →
  generate).
- `backend/services/conversation_service.py` — `chat()` now reads
  `policy_decision`/`confidence_score` from the graph's result instead of a
  hardcoded `"answer"`/`None`; when `policy_decision == "escalate"`, it now
  creates a `KnowledgeGap` row (twin_id, conversation_id, question_message_id,
  question_text) — the live trigger logic the table was built for in session 4
  but had no caller for until now.

Verification performed this session, all against live Postgres + Qdrant + a real
Groq model:
- Direct graph test (greeting, no visitor): `policy_decision=answer`,
  `confidence_score` populated, correct conversational reply.
- Re-ran `test_rag_pipeline.py`: same question as session 3
  ("...why are you talking to me?") that previously got "I don't have
  information about why I'm talking to you" now correctly answers using the
  retrieved memory fact (the visitor is a recruiter evaluating a backend role) —
  direct proof the conversational-vs-grounded prompt split works, not just a
  unit-level claim.
- **The exact session-7 bug, reproduced live through the full HTTP API**: "my
  name is Sarah" → "what is my name?" now correctly answers "Sarah" (previously:
  "I don't know," every time).
- **A genuine escalation, same live session**: asked an unanswerable personal
  question ("what is Umair's mother's maiden name?") — got a warm deferral
  instead of a blunt refusal, `policy_decision=escalate` persisted on the
  `Message` row, and confirmed by direct DB query that a `KnowledgeGap` row was
  created with the exact question text and `status=pending`.
- One operational hiccup during testing, not a code bug: a stale background
  uvicorn process from an earlier session was still holding the embedded
  Qdrant file lock (`RuntimeError: Storage folder ... already accessed by
  another instance`) — killed it and retried. Worth remembering: the embedded/
  file-mode Qdrant client (§4) is strictly single-process, so a leftover
  `uvicorn` from a prior session will block any new one every time until this
  moves to a real Qdrant server.

Known, accepted limitation: `confidence_score` reflects retrieval *relevance*,
not whether the retrieved chunk actually answered the question — in the
escalation test it was actually higher (0.68) than in the two successful answers
(0.44, 0.49), because something phrased similarly to a personal question scored
well on similarity without containing that fact. The escalate/answer decision
itself is correct (it comes from the model's own `grounded` self-report, not from
thresholding this score) — just don't read `confidence_score` as "how likely this
answer is correct."

Still not done: an independent post-generation hallucination check (documented as
a deliberate scope cut above), the full multi-agent router, frontend, real pytest
suite, Alembic, auth.

### 2026-10-16 (session 9) — Voice stack benchmarked for real; backend auth/grants/knowledge-gap API completed

User asked for two large things at once: "complete the voice part" and "complete
the backend fully." Pushed back on scope first (each is realistically multi-session
work, not one-shot), then made real progress on the highest-value piece of each
rather than a shallow pass over both: actually benchmarking the voice stack (the
thing flagged as "check before building more" since session 5 and never done), and
closing the loudest, most-repeated flagged gap in the backend — no auth — plus the
two features whose schema has existed since session 4 with zero API surface until
now.

**Voice**: see §9.3 above for the full result. Short version: Pocket TTS measured
at 0.75–0.98x realtime on this CPU, not the researched ~6x — the voice-only
real-time loop is not viable as currently scoped, and three options are laid out,
undecided, for the user's next call. ASR (faster-whisper) inconclusive this
session — stuck on a slow model download, killed rather than left blocking. A
real, separate bug found and worked around: faster-whisper 1.2.1 + PyAV 19.0.1 are
version-incompatible (`decode_audio()` passes a kwarg PyAV 19 doesn't accept) —
bypassed by decoding WAV with the stdlib `wave` module instead.

**Backend — auth**: `pyjwt` + `bcrypt` (added to `requirements.txt`). New
`backend/services/auth_service.py` (hash/verify password, create/decode JWT,
register/login owner, passwordless find-or-create visitor login) and
`backend/api/{auth,deps}.py` (`get_current_user`, `get_current_user_optional`,
`require_owner`). Rewrote `twins.py` (owner_id from token, ownership check on
delete), `sources.py` (every route now owner-only), `chat.py` (visitor_id removed
from the request body entirely, now derived only from an optional Bearer token).

**Backend — access grants**: new `backend/services/access_service.py` +
`backend/api/grants.py` (`POST`/`GET`/`DELETE` on `/twins/{id}/grants`).

**Backend — knowledge gaps**: new `backend/services/knowledge_gap_service.py` +
`backend/api/knowledge_gaps.py` (`GET` list, `POST .../answer`, `POST .../dismiss`).

**New test**: `test_api_auth_flow.py` (requires a running server, uses `requests`)
— the project's first test that exercises a complete, multi-step real-world
scenario through the actual HTTP API rather than a single capability.

Verification performed this session, all against a real running server + live
Postgres + Qdrant + Groq:
- Registering an owner, then creating a twin *without* a token → `401`; *with* a
  token → succeeds, `owner_id` on the resulting twin matches the token's user,
  confirming the client can no longer supply it.
- Ingested one `public` and one `private` source. A visitor with no grant asked
  about the private content → correctly denied, escalated gracefully, and a
  `KnowledgeGap` was created.
- Owner granted that visitor `private` tier by email → a **new** conversation
  (tier is resolved at conversation creation, by design) correctly answered from
  the private source.
- Owner revoked access. Listed the pending knowledge gap, answered it with
  `visibility=public` — and a later chat in a **new** conversation (now with no
  active grant) still got the answer, correctly: the owner's answer was
  deliberately made public, which is a different fact from the original private
  note, not a bug in the revoke logic. Repeated the whole grant/chat/revoke/chat
  sequence with the answer set `visibility=private` instead in the permanent test
  script, confirming revocation does take effect for content that stays private.
- Re-ran `test_db.py` and `test_ingestion_pipeline.py` for regression — both still
  pass. (One operational snag, not a bug: the test script and the running server
  can't hold the embedded Qdrant file lock at the same time — same single-process
  limitation noted in session 8 — server was stopped before re-running them.)

Still not done: the three voice options from §9.3 (undecided), the full
multi-agent router, frontend, real pytest suite, Alembic, the
`AccessGrant.invited_email` pending-claim flow (simplified away, stated in the
code), email-verified visitor login (passwordless ≠ verified, stated in the code).

### 2026-10-16 (session 10) — Voice backend capability built (accepting the latency)

User's decision on §9.3: no budget for a paid TTS vendor, explicitly okay with
the slow replies for now, revisit speed later. Also chose backend-capability-
first over a full live call (that needs a frontend/WebRTC layer that doesn't
exist at all yet) when asked directly. Full detail in §9.4 above — this entry is
the pointer, not a duplicate.

Built `backend/voice/` (audio_utils, asr, tts, pipeline) wiring faster-whisper →
the existing `ConversationService` → Pocket TTS into one `voice_chat()` call.
Fixed a correctness issue found while building this, not just a convenience: TTS
output is 24kHz, Whisper expects 16kHz — `resample_to_16k()` exists because that
was checked and confirmed, not assumed. Bridged `HF_TOKEN` from this project's
`Settings` into `os.environ` since `huggingface_hub` doesn't read it from
anywhere else.

Verified with a real round trip (`test_voice_pipeline.py`): synthesized question
→ transcribed (one small ASR error, "Umair" → "Umar", didn't break the answer) →
correctly grounded chat response → synthesized reply audio. Total measured
latency for the one real turn: ~40.4s (3.9s ASR + 6.8s chat + 29.7s TTS,
including a one-time cold model load folded into that TTS figure).

Explicitly not built: an actual API route for this (it's a Python
function/script right now, by choice — wanted the plumbing proven before
deciding the endpoint shape), real cloning (blocked on the user providing a
voice recording + setting up `HF_TOKEN`), anything live/WebRTC.

### 2026-10-16 (session 11) — Real voice cloning confirmed, one real bug found and fixed

User provided both things blocked in session 10: a recording
(`fyp_audio testing.ogg`) and an HF token — added to `.env` as
`fyp-voice-cloning-token` rather than `HF_TOKEN`, renamed with a key-only `sed`
substitution so the token value never passed through this conversation.

Full story in §9.5 above. Short version: the first attempt, with the full
47-second recording, produced garbage/truncated output every time —
diagnosed (via a same-text/different-voice comparison and a
`frames_after_eos` experiment that just produced filler like "that's it, that's
it, that's it") as the model likely echoing off-topic mic-testing speech from
the recording's tail end rather than treating the recording purely as a voice/
style reference. Trimming to the first 12 seconds fixed it immediately and
reproducibly — confirmed with the exact sentence that failed before, now
correct. `backend/config.py`'s `TTS_VOICE_SAMPLE_PATH` now points at the
trimmed clip by default, with the diagnosis and a "keep future recordings
clean, 10-30s, nothing extraneous" note written into the comment.

Re-ran `test_voice_pipeline.py` end to end with the fix in place: correct
question synthesis, correct transcription (modulo a `tiny.en` ASR accuracy
limit on the name "Umair"), a correctly grounded answer, correct reply
synthesis. Also installed `soundfile` (a real missing dependency — pocket-tts
needs it for any non-WAV format, including the user's `.ogg` file) and added
it to `requirements.txt`.

Sent the user both the broken clip and the corrected clip directly so they can
judge whether it actually sounds like them — that's not something verifiable
from this end.

Still not done: an API route for this capability, anything live/WebRTC, and
revisiting the TTS speed problem from §9.3 (the user's explicit call: deferred,
not forgotten — now additionally confirmed that cloning specifically is even
slower than the already-too-slow preset-voice baseline).

### 2026-10-17 (session 12) — Streamlit frontend built and verified live

User confirmed the cloned voice sounded fine, asked for a recommendation on what's
next; given a complete, tested backend with nothing visible to show for it, the
call was to build the frontend before anything else. Confirmed, then built.

Full detail in new §12 above. Short version: `frontend/app.py` (Streamlit, pure
HTTP client against the real API) covering owner auth, twin management, source
ingestion (text + file), access grants, knowledge gaps, text chat, and voice chat.
Three backend additions needed first: `GET /twins/by-slug/{slug}`, the first real
`POST /twins/{id}/voice-chat` API route (wiring sessions 10–11's voice capability
into the API for the first time), and an `audio_utils.py` upgrade to `soundfile`
so uploads/recordings in arbitrary formats work, not just WAV.

Found and fixed a real bug while building this, not a frontend cosmetic issue: the
twin's own owner got the same `public` tier as a stranger when chatting with their
own twin — `is_owner_session` existed in the schema from the start and was never
once set `True`. Fixed in `ConversationService`.

Set up `.claude/launch.json` (at the FYP root, not t2-rag — the tool expects it
there) running both servers via `cmd.exe /c cd t2-rag && ...`, since `--app-dir`
alone doesn't change the process's actual working directory and this project's
`.env`/`QDRANT_PATH` resolution depends on it being t2-rag.

Verified live in a real browser (not just "it loads"): full owner flow; a private
note invisible to a `friends`-tier visitor but visible to the owner with zero
grant (confirms the bug fix); that same denial correctly escalating into a
`KnowledgeGap`, answered through the UI, becoming a new `Source`. The voice tab's
file-picker needed a native OS dialog this session's browser automation couldn't
drive, so `POST /twins/{id}/voice-chat` was verified directly against the same
live server instead — correctly used the owner's private knowledge in a spoken
reply (the access fix holding through voice too), valid playable audio, steady
-state timing ASR ~0.9s / chat ~1s / TTS ~15s. Also directly verified
`POST /twins/{id}/sources/upload`, never exercised through the real API before.

Also fixed, while reviewing the file for this entry: a documentation bug in this
very file — an "Update, same session" paragraph that belonged at the end of
session 5's entry had been physically misplaced to the end of the whole file
(after session 11), making it look like nothing happened after session 11. Moved
it back to where it actually belongs.

Still not done: `PATCH /twins/{id}` (twin profile editing — Overview tab is
read-only), a human actually clicking the voice tab's record/upload widgets,
real pytest/CI, Alembic, the multi-agent router (still premature — no second
query-type to route to yet).

### 2026-10-19 (session 13) — Streamlit dropped, React + MUI frontend built; VAD-based Call Mode; avatar support; a real MUI v9 bug found and fixed

User asked for four things in one message: (1) replace the record→submit→wait
voice flow with something closer to a live call — press a button, just talk,
hear the reply, keep talking; (2) drop Streamlit entirely for a proper React +
MUI frontend; (3) make profile pictures and voice-as-input first-class, not
afterthoughts; (4) make the whole thing look professional. Flagged one hard
constraint before building anything: a true duplex "feels like a phone call"
experience isn't achievable on this hardware — §9.3's benchmark already showed
Pocket TTS running at 0.75–0.98x realtime, i.e. slower than the speech it's
generating, so a live-overlapping call would just fall further behind the
longer it ran. Built the honest achievable ceiling instead: push-to-talk with
automatic silence detection (no manual stop), an explicit "Thinking…" state
during the real processing pause, auto-play of the reply, then automatic
re-arming of the mic — a continuous loop, just not a continuous *stream*.

**Backend additions (profile pictures):**
- `backend/db/models.py` — `Twin.avatar_path` (nullable, relative path under
  `AVATAR_DIR`). A new column on an existing table — required the destructive
  reset described below.
- `backend/config.py` — `AVATAR_DIR` (default `./data/avatars`).
- `backend/services/twin_service.py` — `update_twin()` (name/bio/persona) and
  `set_avatar()` (saves to `{AVATAR_DIR}/{twin_id}{ext}`).
- `backend/api/twins.py` — `PATCH /twins/{id}` (owner-only — finally closes the
  "Overview tab is read-only" gap flagged at the end of session 12) and
  `POST /twins/{id}/avatar` (owner-only, content-type validated). Added a
  `_to_response()` helper so every twin-returning route consistently computes
  `avatar_url`.
- `backend/main.py` — mounts `/media/avatars` as a `StaticFiles` directory.

**Backend addition (broader audio format support):** `backend/voice/audio_utils.py`
gained a PyAV-based fallback decoder (`_load_with_av`) behind the existing
`soundfile` attempt. Found, not assumed: generated a real webm/opus file
(`ffmpeg -c:a libopus`, mimicking what a browser's `MediaRecorder` actually
produces) and confirmed `soundfile` fails on it outright
(`LibsndfileError: Format not recognised`) while the PyAV fallback decodes it
correctly — verified by running the file through full ASR transcription, not
just a decode-without-crashing check.

**Frontend: complete rewrite.** `frontend/app.py` (Streamlit) and everything
under the old `frontend/` deleted — safe, nothing from it was ever committed
(one commit exists in the whole repo, from session 1). New stack: React 19 +
TypeScript + Vite 8 + MUI v9 + React Router v7 + TanStack Query v5 + axios +
notistack. Structure: a typed `api/` layer (`types.ts`, `client.ts` with an
`apiErrorMessage()` helper that unwraps FastAPI's `detail` field,
`endpoints.ts` grouped by domain), an `AuthContext` persisting
`{role, token, userId, email, displayName}` to `localStorage`, a themed shell
(`theme.ts` — indigo/teal, Inter font, 12px radius), and page/component split
mirroring the four-tab twin-management surface (Overview/Knowledge/Grants/Gaps)
plus a dedicated `ChatPage`.

**Voice UX, the actual ask:**
- `usePushToTalk.ts` — simple click-to-record/click-to-stop for the chat
  composer's mic button (no VAD) — the existing one-shot voice-message path,
  now with a proper UI instead of a file-picker.
- `useVoiceCall.ts` — the new "Call Mode" hook. `AudioContext` +
  `AnalyserNode` computes RMS volume in a `requestAnimationFrame` loop;
  `MediaRecorder` records each utterance; `SILENCE_MS_TO_STOP=1200` triggers
  auto-stop-and-send on sustained quiet after speech; the returned reply audio
  auto-plays via `audio.onended` auto-rearms listening — the full loop runs
  with zero button presses after the initial "Start call." Exposes
  `status: "idle"|"listening"|"thinking"|"speaking"|"error"` and a live
  `volume` number, which `CallOverlay.tsx` renders as a pulsing ring around the
  twin's avatar sized to `status`/`volume` — a visible heartbeat during the
  real multi-second "Thinking…" pause rather than a dead screen.
- Both hooks funnel into the same `ChatPage` message list as text chat, so a
  call-mode exchange stays visible afterward as an ordinary transcript, not a
  disappearing overlay.

**A real, breaking bug found while verifying this live, not a cosmetic issue:**
on first load the layout was broken — the header's right-hand content
(role chip, log-out button) was missing entirely from view, and elements like
"New twin" visually overlapped their heading instead of sitting to its right.
Browser console showed the actual cause: `React does not recognize the
alignItems/justifyContent/textAlign prop on a DOM element` — this installed
version, `@mui/material@9.5.0`, **no longer forwards `alignItems`/
`justifyContent` as direct `Stack` props** (confirmed by reading
`node_modules/@mui/material/Stack/Stack.js`'s own `propTypes`: only
`direction`/`spacing`/`divider`/`useFlexGap`/`sx`/`component`/`children`
remain) — a breaking API change from the MUI version this code was written
against, not a typo. Every place these were passed as top-level JSX props
leaked straight through to the DOM as invalid HTML attributes instead of
becoming CSS, which is exactly why things visually overlapped (no flexbox
alignment was ever applied). Fixed by moving `alignItems`/`justifyContent`
into each element's `sx` object (`Typography`'s `textAlign` similarly moved to
its still-supported `align` prop instead) — **22 occurrences across 14 files**
(`Layout`, `ChatPage`, `VisitPage`, `TwinCard`, `TwinDetailPage`,
`DashboardPage`, `LoginPage`, `ChatBubble`, `CallOverlay`, and all four tab
components). Verified by reading the console again after the fix (errors
gone) and visually confirming the header/dashboard layout was correct in a
screenshot.

**The other known-upfront blocker, communicated and resolved before testing
could proceed**: `Twin.avatar_path` is a new column on an existing table, and
this project has no Alembic — per the standing policy repeated every session
this has come up, the destructive reset was never run automatically. Confirmed
the breakage was real first (a live `POST /twins` against the running server
threw `psycopg2.errors.UndefinedColumn: column "avatar_path" of relation
"twins" does not exist`), then asked the user to run
`python -m backend.db.init_db --reset` themselves, which they did.

**Verified live, in the real browser, against the real backend, after the
reset** — every step through the actual UI except where noted:
- Registered an owner through the Register tab, redirected correctly to an
  empty dashboard.
- Created a twin through the "New twin" dialog; redirected to its detail page.
- **Avatar upload**: the browser pane can't drive a native OS file-picker
  dialog (same limitation noted for the old Streamlit voice tab in session
  12), so verified `POST /twins/{id}/avatar` directly via `curl` with a
  generated test PNG — `avatar_url` came back correctly set, and reloading the
  Overview page in the browser showed the uploaded image rendering in place of
  the placeholder icon.
- **Knowledge ingestion**: typing into the multiline "Content" `TextField` via
  simulated keystrokes silently did nothing (text never appeared, despite the
  tool reporting characters "typed") — worked around with the browser tool's
  direct `form_input` (sets the value and dispatches the right events) instead
  of simulated typing; not chased further since it's a browser-automation
  interaction quirk with this specific multiline-textarea MUI component, not
  an application bug — single-line fields typed normally throughout the rest
  of this session. Ingestion itself worked correctly: submitted, showed
  "Ingesting…", then the new source appeared with a green check, 1 chunk,
  public.
- **Text chat**: asked "What technology does Umair use for his project?" —
  got a correctly grounded answer citing FastAPI/PostgreSQL/Qdrant/Groq, with
  "6038ms · 1 source(s)" metadata shown, rendered in proper chat bubbles with
  role-specific avatars.
- **Voice**: clicking the push-to-talk mic button correctly triggered a
  `getUserMedia` request, which this sandboxed browser denies — confirmed the
  app handles that gracefully (a clean "Couldn't access the microphone:
  Permission denied" snackbar, no crash) rather than silently failing. Real
  mic capture can't be driven by this session's tooling (same limitation as
  every prior voice-UI verification in this project), so verified the
  underlying endpoint directly instead: `POST /twins/{id}/voice-chat` with a
  real webm/opus file (`voice_bench/question_test.webm`, left over from the
  audio_utils fix above) — correctly transcribed, correctly grounded
  (reusing the knowledge note just ingested through the UI), correctly
  synthesized a reply (timing: ASR 4.6s + chat 2.9s + TTS 59.5s ≈ 67s total,
  consistent with every prior measurement of this TTS model being
  sub-realtime). This is the exact endpoint both `usePushToTalk` and
  `useVoiceCall` call, so this confirms the voice path the new UI depends on
  actually works end to end against the new schema.
- Access Grants and Knowledge Gaps tabs both render correctly (empty states,
  no layout bugs) — not exercised further this session (the grant/escalate/
  revoke loop was already verified against this same backend logic in session
  9 and 12; no service-layer code changed there this session).
- Confirmed via the browser console, after all of the above, that no
  stray errors remain beyond one harmless one-time 401 (a `/twins` query
  firing once before the auth token attaches to the axios client on first
  mount, immediately retried successfully by React Query — not acted on,
  cosmetic only).

**Not done / honestly out of scope this session**: driving the mic-based
flows (push-to-talk, Call Mode) through an actual browser click — both are
verified at the API level only, a human click-through is still worth doing
once; the private-vs-friends-tier access boundary and escalate→grant→answer
loop weren't re-driven through the new UI (no reason to expect regression,
service layer untouched, but not literally re-clicked); real pytest/CI;
Alembic (this session's reset-on-schema-change friction is exactly the pain
migrations exist to remove — worth reconsidering once the schema stabilizes).

### 2026-10-20 (session 14) — Discovery gallery, mandatory avatar+voice at creation, voice-note knowledge capture

User sent four screenshots of beyondpresence.ai (a commercial real-time-avatar
vendor) as a concrete UX reference and three explicit asks: (1) a visitor
shouldn't have to type a twin's handle/ID to talk to it — browse and click,
like BeyondPresence's "Talk to Michael" cards; (2) a profile picture AND the
owner's real voice should be **compulsory** when creating a twin, not optional
extras added later; (3) adding knowledge should support "select, open the mic,
speak, save" as a first-class alternative to typing. No schema change was
needed for any of this — `media_assets` (voice_sample, `consent_confirmed_at`)
and `SourceType.VOICE_TRANSCRIPT` have existed since session 3/4 specifically
anticipating this, just with no API ever built on top of them until now.

**Backend:**
- `backend/config.py` — added `VOICE_SAMPLES_DIR` (`./data/twin_voice_samples`),
  distinct from the existing global `TTS_VOICE_SAMPLE_PATH` fallback.
- `backend/services/twin_service.py` — `list_public_twins()` (every active
  twin, for the gallery — no separate "discoverable" flag exists or was
  added; a twin's actual knowledge stays gated by its sources' own visibility
  tiers regardless of gallery listing, so this is safe to keep simple);
  `set_voice_sample()` (saves to `{VOICE_SAMPLES_DIR}/{twin_id}{ext}`,
  replaces any prior `MediaAsset` row for that twin rather than accumulating
  one per re-recording, enforces `consent=True` before the row can be
  `'completed'` — the schema's own consent-before-ready `CheckConstraint`,
  session 3, now actually enforced by a caller instead of just existing);
  `get_voice_sample_path()` (resolves a twin's own cloned-voice reference, or
  `None` to fall back to the global default).
- `backend/api/twins.py` — `GET /twins/public` (registered before
  `/{twin_id}`, same pattern as `/by-slug`); `POST /twins/{id}/voice-sample`
  (owner-only, content-type + explicit-consent validated);
  `TwinResponse.has_voice_sample` added so the frontend can show a "Voice"
  badge and gate the wizard without a second round-trip.
- `backend/api/voice.py` — `voice_chat_endpoint` now resolves
  `TwinService(db).get_voice_sample_path(twin_id)` and passes it as
  `voice_ref` into `voice_chat()`. This closes a real, previously-silent gap:
  every twin's spoken replies used the exact same global catalog/cloned voice
  (whichever `TTS_VOICE_SAMPLE_PATH` pointed at) regardless of which twin was
  talking — `backend/voice/tts.py`'s `synthesize(voice_ref=...)` parameter
  already existed for exactly this, it was just never wired to a caller.
- `backend/services/source_service.py` / `backend/api/sources.py` —
  `ingest_voice_note()` / `POST /twins/{id}/sources/voice-note`: saves the
  upload to a temp file, transcribes it with the existing `transcribe_file()`
  (webm/opus and friends already handled by session 13's PyAV fallback), and
  routes the transcript through the same `IngestionPipeline.ingest_text()`
  every other note uses (`source_type="voice_transcript"`) — the raw audio
  itself is discarded once transcribed, never kept as a `MediaAsset` (that
  table is for cloning-reference clips, a different downstream consumer, per
  its own docstring). Returns the transcript alongside the created `Source` so
  the UI can show the user what was actually captured.

**Frontend:**
- `components/TwinGalleryCard.tsx` **(new)** — full-bleed avatar photo,
  name/bio over a bottom gradient, a "Voice" chip when
  `has_voice_sample`, and a hover-revealed "Talk to {first name}" pill —
  modeled directly on the BeyondPresence screenshots, not a generic card with
  a button bolted on.
- `pages/DashboardPage.tsx` — rewritten for non-owners: instead of a "Find a
  twin" prompt linking to a search page, it now directly renders the gallery
  (`listPublicTwins()` → a `Grid` of `TwinGalleryCard`s), clicking straight
  into `/twins/{id}/chat`. `/visit` (handle search) kept as a one-line
  secondary link ("Enter its handle instead") for someone who already has a
  handle, not removed — just no longer the primary path, matching what was
  actually asked ("it should not be like that like i need to put an id").
- `components/VoiceSampleRecorder.tsx` **(new)**, shared between the creation
  wizard and the Overview tab — record live (reuses `usePushToTalk`) or
  upload a clip, a playback preview, and a required (unchecked by default)
  consent checkbox before the submit button enables. Consent is explicit
  because this clip becomes a biometric voice clone, not a knowledge note —
  deliberately not defaulted to checked.
- `components/CreateTwinWizard.tsx` **(new)**, replacing the old single-form
  create dialog — a 3-step `Stepper` (Profile → Photo → Voice). The twin row
  is actually created at the end of step 1 (so steps 2/3 are plain, retryable
  uploads against a real `twin_id` instead of staging files client-side and
  hoping three separate requests all succeed together); step 2 (photo) and
  step 3 (voice, via `VoiceSampleRecorder`) both block "Next" until something
  is actually provided — no skip button. One deliberate escape hatch: once
  the twin exists, "Finish later" is still offered (closes the wizard,
  navigates to the twin's detail page) — a stuck mic or a bad photo
  shouldn't hard-trap someone mid-flow; the twin just stays visibly
  incomplete (no voice chip, generic-voice fallback) until they come back
  through the Overview tab, which has the same avatar/voice controls.
- `components/tabs/OverviewTab.tsx` — added a "Voice" card
  (`VoiceSampleRecorder` again) so a twin created before this session, or one
  someone "finished later," isn't stuck without a path to add one — shows a
  "Cloned" chip when `has_voice_sample` is true, "Replace voice" vs "Save
  voice" as the button label.
- `components/tabs/KnowledgeTab.tsx` — third card, "Add a voice note",
  alongside the existing text-note and file-upload cards: a plain
  record/stop button (reuses `usePushToTalk`, no VAD — matches the ask "you
  just select and open the mic and start speaking"), a visibility selector,
  and on stop it calls the new `/sources/voice-note` endpoint and shows the
  transcript (truncated) in the success toast so the user can sanity-check
  what got captured without having to open the source separately.
- `api/types.ts` / `api/endpoints.ts` — `Twin.has_voice_sample`,
  `VoiceNoteResponse`, `listPublicTwins()`, `uploadVoiceSample()`,
  `ingestVoiceNote()`.

**A real, pre-existing bug fixed while testing this, not part of the ask**:
`ChatPage.tsx`'s "You have full access to your own twin" / "Chatting as a
visitor" label used `role === "owner"` alone — but `AuthContext.logout()`
deliberately keeps the last-used `role` around (so the login page remembers
which tab you were on) while clearing `token`/`isAuthenticated`. Net effect:
a logged-out former owner visiting a twin as an anonymous visitor still saw
"You have full access to your own twin". Caught by actually logging out and
checking the new gallery flow as a real anonymous visitor would, not by
reading the code. Fixed to `isAuthenticated && role === "owner"`, matching
the `canManage` check a few lines below it that already did this correctly.

Verification performed this session, all against the real running backend +
Postgres + Qdrant + Groq, after restarting both servers (confirmed via
`/health` and a real `/twins` call — exit code 7 / "No logs yet" for the
first ~15s is the usual torch/pocket-tts import cost, not a failure, see
every prior session):
- `GET /twins/public` returns both twins in the DB with `has_voice_sample`
  correctly `false`/`true`.
- `POST /twins/{id}/voice-sample` with a real audio file (the session 11
  trimmed clip) → `has_voice_sample` flips to `true`, file lands at the new
  per-twin path (`data/twin_voice_samples/{twin_id}.wav`, confirmed on disk,
  distinct from the global `TTS_VOICE_SAMPLE_PATH`).
- **Proved the voice_ref wiring is real, not just present in the diff**: the
  first `voice-chat` call after uploading the per-twin sample measured TTS at
  43.4s (a fresh `_voice_state_for()` cache miss — the one-time clone-setup
  cost documented in §9.5) where a warm call on the already-cached global
  default would have been ~15-19s; a second call against the same twin
  immediately dropped to 19.4s (now warm). If the explicit `voice_ref` were
  silently being ignored and falling through to the pre-warmed global path,
  neither call would have paid that cold-start cost — this is a real,
  measured proof the per-twin path is actually being used, not an assumption.
- `POST /twins/{id}/sources/voice-note` with the same webm/opus test file
  from session 13 → correct transcript, `source_type=voice_transcript`,
  `status=completed`, 1 chunk — confirmed in the Knowledge tab's source list
  afterward too.
- Live browser pass: logged out and confirmed the visitor landing page is now
  the gallery (two real cards, correct avatar/bio/Voice-chip rendering,
  "Enter its handle instead" still present as a secondary link) — one click
  on a card went straight to `/twins/{id}/chat`, zero typing, which is the
  literal thing that was asked for. Logged back in as owner, ran the full
  create-twin wizard through step 1→2 (profile → photo), confirmed the twin
  is actually created server-side at that point (`GET /twins` showed it) and
  the Photo step correctly blocks "Next" with no file chosen; used "Finish
  later" and confirmed it lands on that twin's (intentionally incomplete)
  Overview page, which now has a working Voice card in the same disabled-
  until-complete state. Deleted the test twin afterward via the API. Checked
  the Knowledge tab's new three-card layout and confirmed the voice-note
  record button correctly surfaces the same clean "permission denied"
  snackbar as push-to-talk when mic access is refused, no crash.
- Could not drive: any step requiring a native OS file-picker (avatar/voice
  file selection) or real microphone capture (recording) through this
  session's browser automation — the same standing limitation noted in every
  prior frontend session. Everything reachable that way was instead verified
  directly against the real API with real audio/image files, as above, and
  the UI-only logic (button disabled states, step transitions, consent
  gating) was verified by driving the parts of the UI that don't need those
  two things, which is as far as this tooling goes. **A human click-through
  of the record buttons specifically is worth doing once, on your own
  machine.**

Still not done: actual face/voice moderation or review before a twin is
listed in the public gallery (anyone who creates a twin is immediately
listed — fine for an FYP demo, a real concern if this ever had real
strangers' names/faces on it); a "finished later" twin has no visible nudge
anywhere outside its own Overview tab (no banner on the dashboard saying "2
twins need a voice sample," say); real pytest/CI; Alembic.

### 2026-10-20 (session 14, bugfix) — Uploaded voice samples silently produced garbage audio

User reported, right after trying the new mandatory-voice feature for real:
text replies in Call Mode were fine, but the **spoken audio was "complete
distortion."**

**Root cause, confirmed by reproducing it directly, not guessed**: the
`set_voice_sample()` written earlier this session (`backend/services/
twin_service.py`) saved whatever the browser/upload sent straight to disk
with `shutil.copyfileobj` — no decoding, no length limit, no format
normalization. The user's real upload was a genuine, untrimmed **44-second**
Opus-in-Ogg recording. Calling `backend/voice/tts.py`'s `synthesize()`
directly against that exact file for a sentence that should produce ~3-4s of
audio returned **0.72 seconds** — this is the *exact* failure signature
already diagnosed and fixed once before, in session 11 (CLAUDE.md §9.5): a
long, unedited reference recording reproducibly makes the Pocket TTS cloning
model emit near-silent garbage instead of real speech, not because of
anything content-specific, just length/noise in the reference itself. That
fix was applied by hand to one file back then (`umair_voice_sample_trimmed.wav`,
trimmed to 12s) — this session's new upload endpoint reintroduced the exact
same unprotected path for every twin, because it never reused that lesson or
this project's own existing robust audio decoder.

**Fix** (`backend/services/twin_service.py`):
- Added `MAX_VOICE_SAMPLE_SECONDS = 25` (within the documented-safe 10–30s
  range from session 11's finding).
- `set_voice_sample()` now: writes the upload to a temp file, decodes it with
  `backend/voice/audio_utils.load_audio_as_float32()` (the same soundfile→PyAV
  fallback decoder the ASR and voice-note paths already use — handles
  webm/ogg/opus/whatever a browser or phone actually produces, not just
  clean WAV), truncates to the first `MAX_VOICE_SAMPLE_SECONDS` of samples if
  longer, then writes it back out as a clean 16-bit PCM WAV via the existing
  `save_wav()` helper — `storage_path` is now always `{twin_id}.wav`
  regardless of what format was uploaded, instead of inheriting the upload's
  own (untrustworthy — a browser recording's claimed `.webm` extension
  doesn't guarantee its actual container) extension. Also now populates
  `MediaAsset.duration_seconds`/`format`, left blank before.
- Kept the first N seconds specifically, not a random/middle slice — matches
  session 11's finding that the problem was specifically messy content *at
  the end* of a long recording (mic-testing chatter), so dropping the tail is
  the correct trim direction, not an arbitrary choice.

**Fixed the user's actual broken twin without asking them to re-record**:
ran the corrected `set_voice_sample()` directly (a one-off script, not an
endpoint) against their already-uploaded 44s file — came out as a clean,
trimmed 25.0s WAV. Re-ran the exact synthesize() call that previously
returned 0.72s against the corrected file to confirm the fix holds before
reporting it fixed.

Not done: no client-side recording time cap to match the new 25s server-side
limit — `VoiceSampleRecorder.tsx`'s `usePushToTalk`-based recorder can still
record indefinitely, so a long live recording still gets silently trimmed
(safe now, just not obvious to the user why their later speech "didn't
count") rather than auto-stopping near the limit the way `useVoiceCall`'s
silence-detection does for Call Mode. Worth adding if this bites someone
again, not urgent since the underlying garbage-output failure is what
actually mattered and is now fixed regardless of whether a long recording is
silently truncated or capped up front.

### 2026-10-20 (session 15) — GitHub profile import; LinkedIn deliberately not built

User asked for "attach your GitHub or LinkedIn and scrape all of his info into
Qdrant" as a context-collection method alongside typing/uploading/speaking.
Checked `SourceType` before writing any code: `GITHUB`/`LINKEDIN` values have
existed in the enum since session 3, anticipating exactly this — so this
needed **no schema change and no destructive reset**, unlike several earlier
features this project has added.

**LinkedIn: flagged, not built, by explicit user decision.** Before touching
code, raised the real difference between the two platforms: GitHub has a
public, documented, scraping-friendly REST API; LinkedIn's Terms of Service
explicitly prohibit scraping, it actively blocks automated access (login
walls, bot detection), and its official API doesn't expose public-profile
data to third-party apps without a business partnership. Offered four
options (manual-paste only / paid third-party scraper like Proxycurl / direct
scraping attempt / skip LinkedIn entirely) — **user picked "skip LinkedIn
entirely for now."** `backend/ingestion/fetchers.py`'s module docstring
records this reasoning directly in the code, not just here, so a future
session doesn't quietly "fix" the missing LinkedIn button without re-deriving
why it's missing. A LinkedIn profile can still be added today with zero new
code: copy/paste its text into the existing "Add a text note" box — the
Knowledge tab's new GitHub card says this directly in its own helper text.

**Backend:**
- `backend/ingestion/fetchers.py` **(new)** — `fetch_github_profile(username)`:
  two GitHub REST API calls (profile + repo list, no per-repo README fetch —
  deliberately kept to a fixed 2 calls so this doesn't burn through GitHub's
  60-requests/hour unauthenticated rate limit on one import), formatted into
  plain text (bio, company, location, website, follower/repo counts, each
  non-fork repo with its language/description/star count) and handed back as
  a single string — downstream of this function it's just text, routed
  through the exact same `IngestionPipeline.ingest_text()` every other note
  uses, no special-casing in the pipeline itself. `FetchError` carries a
  message that's safe to show the user directly (e.g. `No GitHub user found
  for "..."`), not a raw exception dump.
- `backend/config.py` — added `GITHUB_TOKEN` (optional; raises the rate limit
  from 60 to 5000 requests/hour, bridged into the request headers when set,
  never required to use the feature at all).
- `backend/services/source_service.py` — `ingest_github()`, same shape as
  `ingest_text()`/`ingest_voice_note()`: fetch, then
  `pipeline.ingest_text(..., source_type="github", ...)`.
- `backend/api/sources.py` — `POST /twins/{id}/sources/github` (owner-only,
  body `{username, visibility}`), returns the same `SourceResponse` every
  other ingestion route does.
- `requirements.txt` — added `requests` (was already an installed transitive
  dependency via other packages, but this is the first place the codebase
  calls it directly, so it's now declared like everything else is). Also
  fixed two unrelated, pre-existing gaps noticed while in this file: `av`
  (PyAV) has been directly imported by `backend/voice/audio_utils.py` since
  session 13 but was never added here; `streamlit` was still listed under a
  "# Frontend" heading despite being fully removed in session 13 — both
  corrected (added `av`, removed the dead `streamlit` line and its now-empty
  heading).

**Frontend:**
- `api/endpoints.ts` — `ingestGithub(twinId, username, visibility)`.
- `components/tabs/KnowledgeTab.tsx` — fourth card, "Import from GitHub"
  (username field + visibility + Import button), alongside the existing
  text/file/voice cards. Switched the grid from 3-across (`md=4`) to a 2×2
  (`md=6`) now that there are four methods, not three — reads better than
  three-plus-an-orphan on a second row. The card's own helper text states
  the GitHub scope (bio/repos/languages/stars) and the LinkedIn workaround
  directly, so the reasoning above is visible in the product, not just this
  file.

Verified this session, all against the real running backend + a real GitHub
account, not a mock:
- `fetch_github_profile('octocat')` run directly — correct profile text,
  correct repo list with star counts, confirmed by writing to a UTF-8 file
  (printing it directly in this Windows terminal hit the same cp1252-can't-
  print-a-★-character issue session 3's `test_rag_pipeline.py` hit and fixed
  for its own output — a terminal-display-only issue, not a bug, not fixed
  generally since nothing in the app itself prints to this console).
- `POST /twins/{id}/sources/github` with a real username (`octocat`) →
  `source_type=github`, `status=completed`, correctly chunked. With a
  nonexistent username → clean `422` with `No GitHub user found for "..."`,
  not a raw stack trace.
- Live browser pass: imported `torvalds` through the actual Knowledge tab UI
  (not just the API) — button showed "Importing…", then the new source
  appeared in the list with 3 chunks. Asked the chat "How many GitHub
  followers does this person have, and what repositories do they have?" —
  got back his real, correct follower count and his real public repos
  (`linux` among them), proving the full
  import→chunk→embed→retrieve→ground→generate path works end to end, not
  just that the source row got created.

Still not done: per-repo README fetching for richer content (deliberately
cut for rate-limit reasons, noted in the fetcher's own comment as a future
option); any LinkedIn path beyond "paste it as a text note" (user's explicit
call, not forgotten); de-duplication if the same GitHub username is imported
twice (each import creates a new `Source` row rather than updating the
existing one — matches how re-ingesting a text note under a different click
already behaves, not a new inconsistency, but worth a "replace existing
import" option later if this becomes annoying in practice).

### 2026-10-20 (session 16) — Vector DB explorer (Docker approach was a dead end; built one in-app instead)

User asked to visually explore their Qdrant data. The obvious answer —
Qdrant's own official web dashboard — turned out to be a genuine dead end for
this project's specific setup, discovered by actually trying it, not assumed:

**What was tried and why it failed, in order:**
1. Started Docker Desktop (installed but not running), pulled `qdrant/qdrant`,
   mounted the project's `qdrant_storage/` directory into a container on
   ports 6333/6334 (stopping the backend first — the embedded client holds an
   exclusive file lock on that directory the whole time it runs, same
   constraint noted since session 8). The dashboard came up, but
   `/collections` was empty and the container logs showed `Initializing new
   raft state` — it wasn't reading the mounted data at all.
2. First suspicion: a Windows/Git-Bash path problem (MSYS auto-converts
   argument strings that look like POSIX paths before handing them to
   `docker.exe`). Confirmed this WAS real and separately worth knowing —
   `docker run -v "...:/qdrant/storage"` silently mounted the wrong thing
   because `/qdrant/storage` got rewritten to a Windows path by Git Bash's
   MSYS layer; `MSYS_NO_PATHCONV=1` fixes it, proven with a throwaway
   `alpine` container (`ls /check` failed with `No such file or directory:
   C:/Program Files/Git/check` before the fix, listed the real mounted files
   after it).
3. Even with the mount genuinely fixed, the real `qdrant/qdrant` container
   still wrote a *second*, empty `collections/` directory (plural) alongside
   the project's real `collection/` directory (singular) instead of reading
   it. **Root cause, confirmed by reading `qdrant_client`'s own source**:
   `QdrantClient(path=...)` — what `backend/vectordb/client.py` has used
   since session 1 — runs `qdrant_client.local.qdrant_local.QdrantLocal`, a
   separate **pure-Python** local/testing implementation, not the real
   Qdrant Rust engine compiled into the package. It is not a version skew
   (client 1.19.1 vs the pulled server image's 1.19.2 — functionally
   identical) and not a path bug (already fixed by that point) — it is a
   genuinely different on-disk format that the real server has never been
   able to read. **No Docker image, at any version, will ever open this
   data.** This is new, concrete knowledge about this project's existing
   architecture choice (embedded/local Qdrant, decided session 3, revisited
   §4/§6) worth recording here since it forecloses an entire category of
   "just run the real dashboard" answers for good — a real Qdrant server was
   never an option for inspection without actually migrating off embedded
   mode, which is a bigger decision than this session's ask.

Cleaned up after: removed the container, deleted the stray `collections/`/
`aliases/`/`raft_state.json` the misdirected real-server run had written
directly into the project's actual `qdrant_storage/` (verified they were
freshly-created and empty before deleting — didn't touch `collection/`,
`.lock`, or `meta.json`, the real data), restarted the backend.

**What was built instead — reuses the exact same connection the backend
already has, so none of the above problems apply:**
- `backend/api/debug.py` **(new)** — `GET /debug/qdrant/twins` (every twin
  the caller owns, with `exists`/`vector_size`/knowledge+memory point counts
  — scoped to the caller's own twins, never every twin on the server, since
  full chunk content including private-visibility material is exactly what
  this exposes) and `GET /debug/qdrant/twins/{id}/points` (paginated raw
  points — payload only, no vectors returned; 384 raw floats aren't visually
  useful, the payload text/metadata is the actually inspectable part — owner-
  only via the existing `require_owner`). The module's own docstring carries
  the full "why not Docker" reasoning above, so a future session doesn't
  re-attempt the same dead end without first reading why it failed.
- `frontend/src/pages/QdrantExplorerPage.tsx` **(new)** — a twin sidebar
  (point counts at a glance) and a point browser (kind filter, client-side
  text search over the loaded page, Qdrant-cursor-based prev/next — not a
  page-number pager, since Qdrant's `scroll()` API itself is cursor-based).
  Each point renders its `point_kind`/`visibility`/`chunk_index` as chips,
  full document text, and `source_id` — reusing the same chip-and-card visual
  language already established in `KnowledgeTab.tsx`'s source list rather
  than inventing a new pattern.
- Route `/debug/qdrant` (owner-only, same `RequireOwner` wrapper every other
  owner-only page uses) plus a visible "Explore vector DB" button next to
  "New twin" on the dashboard — reachable from the UI, not just a URL someone
  has to be told.

**A second, independent bug found and fixed while verifying this, not part
of the original ask**: navigating to the new page first threw `useAuth must
be used within AuthProvider` despite `App.tsx`'s provider nesting being
completely correct — cost real time to diagnose precisely because the error
message points at the wrong layer. Root cause: `AuthContext.tsx` exported
both a component (`AuthProvider`) and a plain hook function (`useAuth`) from
the same file, which Vite's Fast Refresh explicitly cannot hot-reload
(console showed repeated `Could not Fast Refresh ("useAuth" export is
incompatible)` warnings going back through this whole session's edits) —
repeated failed invalidations left the browser with a stale/duplicated
Context object. A full dev-server restart didn't fix it (the Vite client's
own WebSocket reconnect logic carried the broken state across); only a
genuinely fresh tab did, which was the tell. **Fixed properly, not papered
over**: moved `useAuth` out into its own `frontend/src/context/useAuth.ts`,
leaving `AuthContext.tsx` exporting only the component + the `AuthContext`
object + types — updated all 5 importers (`App.tsx`, `ChatPage.tsx`,
`DashboardPage.tsx`, `LoginPage.tsx`, `Layout.tsx`). Verified the fix by
restarting the dev server and navigating directly (not via a fresh tab) —
clean console, no Fast Refresh warning, no provider error. This was a latent
fragility in the app's auth setup since session 13, not something this
session's own changes introduced — worth knowing it's gone now rather than
hitting it again mid some future session and re-diagnosing from scratch.

Verified this session, against the real running backend + real data:
- `GET /debug/qdrant/twins` → correct `knowledge_points: 5, memory_points: 0,
  vector_size: 384` for the one twin with data.
- `GET /debug/qdrant/twins/{id}/points` → all 5 real chunks back with correct
  payloads, including the GitHub-import chunks from this same session's
  earlier feature and the original text note.
- Live browser pass (after the useAuth fix, both via a fresh tab and via
  direct URL navigation on an already-open session): twin sidebar shows
  "Umair AI Twin — 5 point(s)"; clicking it renders all 5 point cards with
  correct chips/text/source_id; console clean except the one standing
  harmless first-request-before-token-attaches 401 noted in every prior
  session's frontend verification.

Still not done: no vector-similarity search UI (browsing payloads only, not
"find similar points to X" — Qdrant's own dashboard has this, this explorer
doesn't, not asked for); no way to delete/edit a point from this page
(read-only by design — mutation already exists via the Knowledge tab's
delete-source flow, scoped at the source level which is the right
granularity, not per-chunk).

### 2026-10-21 (session 17) — Multi-agent context collection (Gap Analyst + Curator); Qdrant explorer became a real dashboard

Two separate requests in one message. Both scoped down from an initially
broad ask through direct back-and-forth before any code was written — worth
recording why, since both scope cuts are load-bearing for what got built.

**1. "Add the multiagent part... collecting and managing... specific
person's twin context."** Too open-ended to build blind — "multi-agent
context collection" could reasonably mean a fresh onboarding interview, a
GitHub/file auto-summarizer, or several other things, and guessing wrong on
an architecture-level feature is expensive to redo. Proposed a concrete
2-agent "Interviewer + Curator" design (adaptive interview questions, scoped
by what's already known); user redirected to a narrower, already-proven-
valuable surface instead: **multi-agent clustering and curation of the
existing Knowledge Gaps backlog** (questions real visitors already asked
that the twin couldn't answer — the escalation loop built in session 8,
session 4's schema). This is a better fit than the original proposal would
have been — it's grounded in data that already exists (real unanswered
questions) rather than an agent inventing interview questions from nothing,
and it directly extends a feature the user has already used and whose value
was already proven live (session 9's escalate→grant→answer test).

**Two agents, each doing one job, neither trusted to publish on the owner's
behalf:**
- `backend/agent/gap_analyst.py` — `analyze_gaps(gaps) -> List[GapCluster]`.
  Groups a twin's PENDING knowledge gaps by topic (three phrasings of "what
  do you do for work" collapse into one cluster) via
  `get_llm().with_structured_output(GapAnalysis)` — same pattern
  `generate_node` already uses (`backend/agent/nodes.py`), reused rather than
  reinvented. Short-circuits for 0-1 gaps (nothing to cluster, saves an LLM
  call on the common case). Includes a safety net most structured-output
  code skips: the prompt instructs the model to cover every gap id exactly
  once, but that's never guaranteed from an LLM, so any id missing from the
  model's clusters after the call gets its own singleton cluster rather than
  silently vanishing from the owner's queue — read-only analysis, never
  writes to the database.
- `backend/agent/curator.py` — `curate_answer(question_context, raw_answer)
  -> CuratedDraft {text, suggested_visibility, reasoning}`. Takes the
  owner's raw (often informal/fragmented) typed answer, rewrites it as clean
  knowledge-base prose without adding anything that wasn't said, and
  suggests public/friends/private based on whether the content reads as
  personal or sensitive — flagged with one sentence of reasoning, not a bare
  label. **Drafts only.** The owner sees the draft, can edit the text and
  override the visibility, and nothing is saved until they explicitly
  confirm — the same consent principle already enforced elsewhere in this
  project (voice-sample cloning's required checkbox, session 14) applied
  here to "an agent writing something in my own voice into my own knowledge
  base."
- `backend/services/knowledge_gap_service.py` — `analyze_pending()` (wraps
  the Analyst), `curate_draft()` (wraps the Curator, no DB write),
  `confirm_cluster_answer(gap_ids, text, visibility)` (the actual save: one
  `IngestionPipeline.ingest_text()` call covers every gap in the cluster —
  they were grouped because one answer resolves all of them — and every
  listed gap gets marked `answered` pointing at the same `resulting_source_id`;
  existing single-gap `answer_gap()`/`dismiss_gap()` untouched, still used
  for the non-pending filter views).
- `backend/api/knowledge_gaps.py` — `GET /analyze`, `POST /curate`,
  `POST /confirm`, all owner-only, all one segment under the existing router
  prefix so there's no path-shape overlap with `/{gap_id}/answer` (different
  segment count, confirmed before adding — same check already applied to
  every other router in this project when adding a new literal path
  alongside a `{param}` one, e.g. `/twins/public` vs `/twins/{twin_id}`,
  session 14).
- `frontend/src/components/tabs/KnowledgeGapsTab.tsx` — rewritten: the
  "Pending" filter now renders `ClusterCard`s (theme chip, the Analyst's
  rephrased question, an editable answer box, a "Clean up with AI" button
  that calls the Curator and fills the box + shows its reasoning as an
  `Alert`, "Save answer", "Dismiss all") instead of one flat card per gap.
  "Clean up with AI" is optional, not required — "Save answer" works
  directly off whatever's typed, with or without curating first, so a
  Groq hiccup never blocks the owner from just answering plainly. The other
  three filters (answered/dismissed/all) keep the old flat `GapCard` list —
  clustering only makes sense for the still-open backlog.

**Verified live, real Groq calls throughout, not mocked:**
- Generated real pending gaps by actually asking the live twin unanswerable
  questions through the chat API (not hand-inserted rows — `KnowledgeGap`'s
  `conversation_id`/`question_message_id` are non-nullable FKs, so a real
  escalation was the correct way to get valid rows anyway, not a workaround).
- **Proved clustering genuinely merges, not just passes through 1:1**: four
  genuinely distinct questions (education, hometown, hobby, first job) came
  back as four separate clusters — then three *actual* near-duplicate
  phrasings of "what's your favorite food" were added and re-running
  `/analyze` correctly merged exactly those three into one "Food
  preferences" cluster while leaving the other four untouched. Confirms the
  Analyst is doing real semantic grouping, not an identity function dressed
  up as one.
- Curated a deliberately messy raw answer ("i rly like pakistani food esp
  biryani and nihari, also i love pizza lol. not a big fan of seafood tho")
  → got back clean prose preserving every fact, `suggested_visibility:
  "public"`, with sensible reasoning.
- Confirmed the cluster → all 3 gap rows flipped to `answered`, all three
  pointing at the same `resulting_source_id` → asked the twin the identical
  question again through the chat API → **got the curated answer back,
  correctly grounded**, proving the full loop (escalate → cluster → curate →
  confirm → re-askable) works end to end, not just that each endpoint
  returns 200.
- Live browser pass: typed a real raw answer into a `ClusterCard`, clicked
  "Clean up with AI", watched the Curator's draft and reasoning appear
  in-place, clicked "Save answer", watched that cluster disappear from the
  pending list while the other three correctly remained. Console clean
  besides stale leftovers from the backend-restart window earlier in the
  session (not new).

**Noticed, not touched**: the twin's knowledge base has leftover GitHub
import test data (`@torvalds`) from session 15's own verification, which
caused two of the test escalation questions above to come back wrongly
grounded in Linus Torvalds' bio instead of escalating. Left in place
deliberately — it's the user's own data in their own twin, not scratch
output from this session, and they now have a delete button for it in the
Knowledge tab if they want it gone.

**2. "The current UI for the db explorer is not visually understandable...
make a dashboard type of thing."** Concrete enough to build directly — no
clarifying question needed, unlike part 1. Loaded the `dataviz` skill before
touching any chart code (per its own instructions). Rebuilt
`QdrantExplorerPage.tsx`:
- A 4-tile KPI row (twins with data, total points, knowledge chunks, memory
  chunks) — "a handful of headline numbers" calls for a stat-tile row per
  the skill's own form-selection table, not a chart.
- "Points by twin" as a horizontal stacked bar per twin (knowledge + memory
  segments) replacing the old plain clickable-name sidebar — "part-to-whole,
  many/long-named categories" maps to exactly this form per the same table.
  Colors are the skill's validated default palette slots 1 (blue) + 3 (aqua)
  — picked over slots 1+2 specifically because aqua echoes this app's
  existing teal secondary brand color, and both slots are inside the
  palette's documented "first three slots validate all-pairs in both light
  and dark" guarantee, so no separate validator run was needed for just two
  of them. Legend always shown (2 series), 24px bar cap, 4px rounded data-
  ends, 2px surface gap between the two segments, text in text-ink tokens
  never the series color — all straight from `marks-and-anatomy.md`.
- The existing point browser (search/filter/pagination) kept as-is but moved
  below, now a drill-down panel that appears once a twin's bar is clicked,
  rather than the page's main focus.
- Verified live: stat tiles show correct real counts (1 twin with data, 5
  points, 5 knowledge, 0 memory), the bar renders with the legend, clicking
  the bar correctly drills into the same 5 real points verified in session
  16.

**A second, independent bug found while re-verifying this session, already
fixed before this entry — not new work, just confirming it stayed fixed**:
none of the session-16 `useAuth`/Fast-Refresh symptoms reappeared despite
heavy HMR activity across this session's edits (dozens of file saves across
backend and frontend) — the session-16 fix (splitting `useAuth` into its own
file) holds.

Still not done: no way for the Analyst to check whether a pending gap is
actually already answerable from existing knowledge (a retrieval miss rather
than a true gap) — flagged as a future enhancement in session 16's original
multi-agent proposal, not built here since the user's chosen scope was
clustering + curation, not gap-validity checking; no client-side nudge
pointing the owner at new pending gaps (they still have to visit the tab);
Qdrant dashboard has no dark-mode pass (app-wide, not scoped to this page —
`theme.ts` is light-only, session 13).

### 2026-10-22 (session 18) — Housekeeper agent: duplicate/contradiction scan for existing knowledge

Direct follow-up to session 17's own "still not done" list: user asked
whether the existing agents keep the *whole* vector DB from getting messy,
and the honest answer was no — the Analyst/Curator pair only touches content
flowing through the knowledge-gap-answering path. Text notes, file uploads,
voice notes, and GitHub imports all go in with zero cross-checking against
what's already indexed. User asked for the reasoning before any code, same
pattern as session 17's scoping conversation — explained the two-stage
design and its real limitation up front, then built it.

**The two-stage design, as explained to the user before writing code:**
Stage 1 is vector search, not an LLM: every knowledge chunk's own embedding
finds its nearest neighbors within the same twin's collection (reusing the
embeddings and the Qdrant collection that already exist — no new
infrastructure). Chunks scoring above a similarity threshold get grouped.
Stage 2 is one LLM judgment per GROUP, not per PAIR — the real reason this
is two stages instead of "ask an LLM to compare everything": embedding
similarity alone can't tell "duplicate" from "contradiction" (two sentences
differing only in one conflicting entity, e.g. "I live in Lahore" vs "I live
in Karachi", are close in embedding space precisely because they're
near-identical otherwise) from "complementary" (different, non-conflicting
facts that happen to be topically close) — only an LLM reading the actual
text can make that call, and grouping transitively-related chunks first
means a cluster of 4 near-duplicates costs one LLM call, not six pairwise
ones. **Stated limitation, not silently accepted**: a contradiction between
two chunks that aren't embedding-close at all (e.g. "I'm vegetarian" vs "I
had steak last week" — low vocabulary overlap) never reaches stage 2. This
catches "said it twice" and "restated it and changed a fact," not every
possible contradiction.

**Backend:**
- `backend/agent/housekeeper.py` — `judge_group(chunks) -> HousekeepingVerdict
  {relationship: duplicate|contradiction|complementary, keep_id, reasoning}`
  via `get_llm().with_structured_output()`, same pattern as every other agent
  in this codebase. `complementary` verdicts are filtered out by the caller
  before anything reaches the owner — a correctly-identified non-problem
  shouldn't cost the owner a review decision.
- `backend/vectordb/operations.py` — `list_knowledge_points()` (scrolls every
  knowledge point with its vector for the scan), `delete_points()` (point-id-
  level delete — a duplicate is usually one chunk out of several in a larger
  Source, so the existing `delete_source_chunks` would be too coarse),
  `get_point_source_ids()` / `count_source_points()` (added during this
  session's own verification — see bugfix below).
- `backend/services/housekeeping_service.py` — `_group_by_similarity()`:
  pairwise cosine similarity via numpy (vectors already in hand from the
  scroll, no extra Qdrant round-trips) + union-find so transitively-related
  chunks land in one group, not overlapping pairs. `scan()` orchestrates
  group → judge → filter. `resolve(point_ids)` is the owner-approved delete.
- `backend/config.py` — `HOUSEKEEPING_SIMILARITY_THRESHOLD = 0.80`, explicitly
  flagged as a starting point, not analytically derived or tuned against a
  large real corpus — same honest treatment `RETRIEVAL_MIN_SCORE` got in
  session 8.
- `backend/api/housekeeping.py` — `GET /twins/{id}/housekeeping/scan`,
  `POST /twins/{id}/housekeeping/resolve`, owner-only.
- `frontend/src/components/tabs/HousekeepingTab.tsx` **(new)** + a 5th tab on
  `TwinDetailPage.tsx`. "Scan for issues" is a manual button (an on-demand
  mutation, not an auto-running query) since this does real LLM work and
  shouldn't fire just because the owner opened the tab. Each flagged group
  renders as a card with a Duplicate/Contradiction chip, the agent's
  reasoning, and every chunk individually toggleable Keep/Delete — pre-set to
  the agent's `suggested_keep_id` for a duplicate, left for the owner to pick
  for a contradiction (only they know which fact is actually current — the
  agent never guesses). Nothing is deleted until "Apply."

**A real bug found and fixed during this session's own verification, not
part of the original ask**: point-level deletion removes the chunk from
Qdrant but does nothing to the matching `Source.chunk_count` in Postgres —
caught by actually running the full scan→resolve loop and then checking the
Knowledge tab's source list afterward, where a source whose only chunk had
just been deleted still claimed `chunk_count: 1`. A **phantom source**:
listed as if it has content, nothing actually retrievable from it. Fixed by
having `resolve()` look up which source(s) the deleted points belonged to
(`get_point_source_ids`, a Qdrant `retrieve` call before the delete) and
recompute each one's `chunk_count` by actually counting what's left in
Qdrant afterward (`count_source_points`) rather than decrementing a number
that could drift — `HousekeepingService` gained a `db: Session` dependency
it didn't need before this fix.

**Verified live, real Groq calls, real deletions, not mocked:**
- First scan against the twin's real (by-then-clean) 7-point knowledge base
  correctly returned `[]` in 1.5s — zero LLM calls made, because nothing
  cleared the similarity threshold, confirming stage 1 actually gates stage
  2 rather than always calling the LLM.
- Deliberately ingested a real near-duplicate of the twin's own project-
  description chunk → re-scan correctly grouped exactly those two chunks as
  `duplicate` with sensible reasoning and a `suggested_keep_id` → called
  `/resolve` → confirmed via `/debug/qdrant/twins/{id}/points` that the
  twin's total point count actually dropped (8 → 7), not just that the API
  returned 200.
- **Caught the chunk_count bug this way**, then re-verified the fix the same
  way: fresh deliberate duplicate → scan → resolve → checked
  `GET /sources` directly and confirmed the affected source now correctly
  shows `chunk_count: 0`, not a stale 1.
- Live browser pass: "Scan for issues" on real data → issue card rendered
  with the Duplicate chip, reasoning, one chunk pre-marked for deletion
  (strikethrough, red border) and the other pre-marked Keep, clicked "Apply
  (delete 1)" → card correctly disappeared from the list, confirming the
  resolve mutation succeeded end-to-end through the actual UI, not just the
  API. Re-scanned afterward on the clean knowledge base → "No duplicates or
  contradictions found."
- All test sources created for this verification (`duplicate_test.txt`,
  `duplicate_test2.txt`, `resync_test.txt`, `resync_test2.txt`) deleted
  afterward — the twin's knowledge base was left exactly as it was before
  this session's testing, not littered with scratch content.

Still not done: no scheduled/automatic scanning (on-demand only, matching
every other agent-assisted action in this app — no background jobs anywhere
in this project); the stated embedding-distance blind spot for contradictions
with low vocabulary overlap; no equivalent scan for `memory` points (scoped
to `knowledge` points only — memory is per-visitor and framed as a different
concern throughout this schema, same boundary `delete_visitor_memory` already
respects).

### 2026-10-23 (session 19) — Whole-app visual redesign + a real missing feature (Conversations)

User's ask was blunt and unscoped: "very bad and uneasy for normal use and
not even attractive." Asked three clarifying questions before touching
anything, since "redesign the whole app" and "add important features" could
each mean almost anything and a wrong guess here is expensive — user picked
whole-app scope, named the two actual pain points (clutter, generic/
unpolished look), and delegated the feature shortlist back to me rather than
naming specific ones.

**Theme (`frontend/src/theme.ts`), rewritten, not tweaked.** Exports a new
`BRAND` constant (`gradient`, raw hex) for the handful of places outside the
theme object that need the brand identity directly (the AppBar's logo mark).
Darker, higher-contrast ink (`#171A23` vs the old `#1E293B`) and a cooler
neutral background (`#F7F8FB`) read less like an unstyled MUI default.
Typography gained negative letter-spacing on headings (the single cheapest
"this isn't a template" signal) and `body2` got a taller line-height for the
dense agent-generated text blocks this app is full of. New component
overrides: `MuiCardActionArea` now has a real hover lift
(`translateY(-2px)` + shadow) — previously only the gallery cards had their
own one-off hover treatment; `MuiButton` containedPrimary gets a soft brand-
tinted shadow instead of none; `MuiAppBar` gained a translucent, blurred
background (`backdropFilter: blur(10px)`) instead of flat white; scrollbar
styling added globally via `MuiCssBaseline` (thin, tinted, not OS-default
gray). `shape.borderRadius` 12→14, `MuiCard` 12→16 specifically (cards read
softer/friendlier at a size step above buttons/inputs, a deliberate
hierarchy, not a uniform bump).

**Sidebar navigation replaces the flat tab bar — the single biggest UX
change.** `TwinDetailPage.tsx` went from a horizontal `Tabs` bar (6 items
would have badly crowded it, see below) to a persistent 232px left sidebar:
twin avatar+name header, then nav rows (icon, label, optional badge), the
active row highlighted with a tinted background rather than an underline.
**Knowledge Gaps carries a live badge showing the pending-cluster count** —
fetched once at the page level (`listKnowledgeGaps(twinId, "pending").length`)
specifically so a twin with open questions is visible without clicking in,
which is exactly the "add important features" ask in miniature: surfacing
state that already existed but was previously invisible until you went
looking for it. Housekeeping deliberately has no badge — unlike pending gaps,
"how many issues exist" isn't known without actually running the (LLM-
calling) scan, and a badge that lies by always reading 0 would be worse than
no badge.

**Decluttered the two densest pages** (Knowledge Gaps, Housekeeping — the
pages this session's user feedback was almost certainly reacting to most
directly, both built in sessions 17-18 with explanatory paragraphs 2-3
sentences long sitting permanently on screen): each lead paragraph cut to one
short clause, with the full explanation moved behind a small `(i)` icon +
`Tooltip` instead of deleted — the reasoning stays available on demand
without being forced reading every time the tab opens. Plain "No pending
questions"/"Nothing here" text replaced with the new shared `EmptyState`
component (icon in a tinted circle, title, optional description/action) —
also rolled out to `DashboardPage.tsx`'s empty states and loading states
(bare "Loading…" text replaced with `Skeleton` card placeholders matching
the real card dimensions, so the page doesn't visibly jump when data
arrives).

**Overview tab gained a status strip, not a rebuild** — deliberately a small,
contained change rather than restructuring a page that wasn't actually the
worst offender: three chips under the name/handle header
(Photo added/missing, Voice cloned/missing, "N knowledge sources" — a new
`listSources` query added to this tab specifically for the count) give an
at-a-glance completeness read without scrolling into the Voice card or
switching to the Knowledge tab to check.

**New feature — Conversations (the one genuine functional gap found while
surveying what exists):** before this session, an owner could see escalated
questions (Knowledge Gaps) but had **no way to browse ordinary, successfully-
answered conversations at all** — ordinary chat history was being persisted
(it always has been, since session 7) but nothing ever read it back out for
the owner. `backend/api/conversations.py` **(new)**: `GET
/twins/{id}/conversations` (list, newest first, every conversation including
the owner's own test sessions — labelled via `is_owner_session` rather than
hidden, since hiding them server-side would be a surprising omission on the
owner's own twin, not a real privacy boundary) and `GET .../conversations/
{id}` (full transcript). `ConversationService` gained `list_conversations()`/
`get_conversation()` — thin queries, no new logic, the data was already
there. `frontend/src/components/tabs/ConversationsTab.tsx` **(new)**: a list
view (visitor name or "You (testing)", access-tier chip, channel icon,
last-message preview, relative timestamp, message count) that drills into a
full transcript **reusing the existing `ChatBubble` component** from the
live chat page — same visual language for "a twin's reply" everywhere in the
app, not a second bubble style invented for this view.

Verified live, real data, real browser session (opened in a fresh tab
specifically to sidestep the known AuthContext/Fast-Refresh fragility from
session 16 — didn't recur, but the precaution is now routine):
- Dashboard (owner and logged-out visitor views) — skeleton loaders and
  `EmptyState` render correctly, gallery cards show the new hover-lift.
- Twin detail page sidebar — all 6 items click through correctly; Knowledge
  Gaps badge showed the real "3" pending count, matching what the tab itself
  then displayed.
- **Conversations, the new feature, against real historical data**: list
  showed every real conversation from this session's own earlier testing
  (the food-preference questions, the Torvalds-polluted ones, etc.) with
  correct previews/timestamps/message counts; clicked into one and got the
  full real transcript, correctly rendered through `ChatBubble`, including
  the `policy_decision`/confidence meta line.
- Overview tab's new status strip showed accurate live state: "Photo added",
  "Voice cloned", "5 knowledge sources" — matching the twin's actual data,
  not placeholder values.
- Housekeeping and Knowledge Gaps' decluttered intros confirmed showing the
  short version with a working tooltip, not the old wall of text.
- Console checked after the full click-through (sidebar nav, conversation
  drill-in, logout, visitor gallery): **zero errors**, not even the usual
  harmless first-request 401 this pass.

Still not done: no dark mode (flagged repeatedly since session 13, still
app-wide and still not built — a real redesign candidate for a future
session, not attempted here since the ask was about clutter/polish, not
theming modes); Conversations has no search/filter (fine at the current
twin's scale — a twin with hundreds of conversations would want one);
Overview's Profile form (name/bio/persona fields) is still always-visible
rather than progressively disclosed — judged not to be the worst offender
compared to Housekeeping/Knowledge Gaps, so left alone rather than
restructured for its own sake; no sidebar/mobile-responsive collapse for the
new `TwinDetailPage` layout at narrow viewports (this project hasn't
prioritized mobile layouts elsewhere either, consistent, not a new gap).

### 2026-10-23 (session 20) — Knowledge Gaps crash fixed (blank-message root cause); Housekeeping removed entirely

Two real crash reports arrived together, both from the actual running app, not
synthetic: a 400 from Groq ("Tool choice is required, but model did not call a
tool") breaking the Knowledge Gaps "Analyze" button, and a 413 ("Request too
large... Requested 120869... Limit 8000") breaking the Housekeeping "Scan"
button. Each turned out to trace back to the same underlying class of problem —
this app's structured-output LLM calls (`with_structured_output()`, the pattern
every agent in this codebase uses) had no defense against a prompt that's
pathological in some way, whether empty or oversized — but the two fixes
diverged sharply once their root causes were actually found.

**Knowledge Gaps 400 — root-caused and fixed, kept.** Queried the real
`KnowledgeGap` table directly for the affected twin rather than guessing:
3 pending gaps had `question_text == ''` (confirmed via `repr()`, not just a
falsy check), traced further through the `Message` table to real blank
visitor chat messages that had been escalated. An empty-string prompt gives
Groq nothing to call a tool against, which is exactly the 400's message.
Two-layer fix:
1. **Prevention** — blank messages are now rejected before they can ever
   become a gap: `backend/api/chat.py`'s `ChatRequest` gained a
   `field_validator` rejecting a message that's empty after `.strip()`;
   `backend/services/conversation_service.py`'s `ConversationService.chat()`
   got the same guard directly in the service, since
   `backend/voice/pipeline.py`'s `voice_chat()` calls the service method
   directly and bypasses the Pydantic layer entirely — one validator alone
   would have left the voice path exposed.
2. **Handling for the 3 gaps that already existed** — `backend/agent/
   gap_analyst.py`'s `analyze_gaps()` now partitions its input up front:
   blank-question gaps are grouped into one "Blank messages" cluster with a
   fixed, LLM-free suggested action ("there's nothing to answer, dismiss
   them"), never sent to Groq at all; only genuinely non-empty gaps go
   through the clustering LLM call.
3. **General hardening, same session** — both `gap_analyst.py` and
   `backend/agent/curator.py` gained a 2-attempt retry around their
   `structured_llm.invoke()` call, with a one-cluster-per-gap /
   type-your-answer-as-is fallback if both attempts fail — Groq's structured-
   output mode has shown occasional flakiness independent of input size, so
   this is defense-in-depth, not specific to the blank-message bug.

Verified live against the real broken twin: `/knowledge-gaps/analyze` went
from crashing to returning one clean "Blank messages" cluster; dismissed all
3 via the existing `/dismiss` endpoint; re-ran `/analyze` and got `[]`,
confirming the twin's gap backlog is genuinely clean now, not just
non-crashing.

**Housekeeping 413/timeout — NOT fixed, removed entirely by explicit user
decision.** Root cause: the twin had 311 real knowledge points, and
`_group_by_similarity()`'s union-find clustering (session 18) has a
"chaining" failure mode — if A is similar to B and B is similar to C, all
three merge into one group even if A and C aren't themselves close — which on
a real-sized knowledge base produced a single group large enough that its
prompt alone exceeded Groq's 8,000 tokens-per-minute limit for this org's
`openai/gpt-oss-120b` on-demand tier (requested 120,869 tokens — 15x the
limit). Tried three successive mitigations, escalating in aggressiveness:
`MAX_GROUP_SIZE = 6` per LLM call + truncating each chunk to 500 chars in the
prompt (worked on a synthetic 10-point test, but didn't address wall-clock
time against 311 real points); `MAX_GROUPS_PER_SCAN = 20` (total scan still
timed out past 120s against the real twin); dropping that cap to `5` (still
appeared to hang past a 60s test — never confirmed working). Mid-debugging,
user's call: stop tuning this and remove the feature outright rather than
keep narrowing the batch size or redesigning the scan as async/background
work. **This was a real, unresolved scaling limitation against this
project's actual Groq rate-limit tier on a realistic-sized knowledge base —
not a sign the two-stage vector-similarity-then-LLM-judgment design itself
was wrong (session 18's small-scale verification was genuine and correct),
just that making it perform acceptably synchronously, inside one HTTP
request, over hundreds of real points needed more engineering investment
than the user judged worthwhile right now.**

**Removed completely** (not deprecated, not feature-flagged off — deleted):
`backend/agent/housekeeper.py`, `backend/services/housekeeping_service.py`,
`backend/api/housekeeping.py`, `frontend/src/components/tabs/
HousekeepingTab.tsx`; the router registration in `backend/main.py`; the
`HOUSEKEEPING_SIMILARITY_THRESHOLD` setting in `backend/config.py`; the
sidebar nav entry, tab-key, and conditional render in `frontend/src/pages/
TwinDetailPage.tsx`; the `scanHousekeeping`/`resolveHousekeeping` API
functions in `frontend/src/api/endpoints.ts`; the `HousekeepingIssue`/
`HousekeepingScanResult` types in `frontend/src/api/types.ts`; and four
vectordb helper functions in `backend/vectordb/operations.py`
(`get_point_source_ids`, `count_source_points`, `delete_points`,
`list_knowledge_points`) confirmed via grep to have had no other callers
anywhere in the codebase once the service using them was gone.

Verified clean after removal: `grep -rni "housekeep"` across `backend/` and
`frontend/src` returns zero matches (only this file's historical record
mentions it, which is correct — append-only log, not retroactively erased);
`from backend.main import app` imports successfully with exactly 0 routes
containing "housekeeping" (down from 2); `npx tsc --noEmit` on the frontend
passes with zero errors.

Still outstanding, not addressed this session: the user's separate feedback
that the app has "no good colour combination or any good landing page,"
raised in the same message as both crash reports — not yet investigated,
including a reference screenshot the user attached that hasn't been looked
at yet.

### 2026-10-24 (session 21) — Pivot: a twin is now scoped to ONE declared domain, not a whole person

User's conclusion, stated plainly: building a "general" twin that tries to
hold a whole person's context (schedule, arbitrary personal facts, every
topic they know anything about) is the wrong shape — a person should instead
be able to make a **domain-specific** twin, whose context is scoped to one
topic. Asked to update the database, backend, and UI accordingly.

This is a real architecture change (not additive-only), so before touching
code, four fork points were checked with the user rather than guessed —
getting any of these wrong would have meant redoing schema/backend/UI work:
1. **Identity vs. depersonalization** — does a domain twin still carry the
   owner's own name/photo/cloned voice, with only the *knowledge* scoped to
   one topic, or does it become a fully separate branded persona unconnected
   to who made it? **Decided: keeps personal identity** — e.g. "Umair, React
   Mentor," not a faceless bot.
2. **The whole-life schema features** — `twin_attributes` (arbitrary
   key/value facts like "hometown") and `schedule_entries` (a weekly
   calendar) were built in session 4 for a whole-person twin and never got a
   service/API/UI built on top of them (confirmed by grep before removing —
   zero other callers anywhere in the codebase). **Decided: remove both
   outright**, not deprecate.
3. **How domain is declared** — free-text field vs. a fixed category
   taxonomy vs. free-text plus an AI relevance guard on ingestion.
   **Decided: plain free-text field** (e.g. "React & TypeScript
   development"), simplest and most flexible, no extra LLM call per upload.
4. **One twin per owner vs. many** — unchanged; `TwinService.list_my_twins`
   already supports multiple twins per owner, each now just also carries its
   own domain (e.g. a "cooking" twin and a separate "career coaching" twin).

**Schema** (`backend/db/models.py`):
- `Twin.domain: str` (required, `NOT NULL`) — the one topic/expertise this
  twin's knowledge is scoped to.
- `TwinAttribute` and `ScheduleEntry` models removed entirely, along with
  their `Twin` relationships and their mentions in the module's own
  docstring table.
- **Applied as a targeted in-place migration, not a destructive full
  reset** — unlike every prior schema change in this project (which always
  needed `python -m backend.db.init_db --reset`, wiping all data), this one
  didn't need to: `twin_attributes`/`schedule_entries` were confirmed empty
  (0 rows each, consistent with them never having a caller), so dropping
  them was lossless, and the new `domain` column was added nullable first,
  backfilled with a placeholder (`'Please set your domain'`) on the twin's 2
  existing real rows, then set `NOT NULL` — straight SQL via
  `backend.db.session.engine`, run directly rather than through Alembic
  (still not in this project). This preserved the user's real "umair" twin,
  its avatar, cloned voice, and ingested knowledge intact — worth noting
  since every earlier session's schema change defaulted to the destructive
  path without considering whether a lighter in-place migration was
  possible.

**Backend wiring, so domain is an enforced boundary, not just a label:**
- `backend/services/twin_service.py` — `create_twin()` takes a required
  `domain` param; `update_twin()` takes an optional one.
- `backend/api/twins.py` — `TwinCreateRequest.domain: str` (required),
  `TwinUpdateRequest.domain: Optional[str]`, `TwinResponse.domain: str`.
- `backend/agent/state.py` — `AgentState` gained a `domain: str` field.
- `backend/services/conversation_service.py` — `chat()`'s `initial_state`
  now passes `twin.domain` through to the graph.
- `backend/agent/nodes.py` — `generate_node`'s system prompt now states the
  twin's declared domain explicitly and adds a new rule: if a question is
  clearly outside that domain and isn't covered by retrieved knowledge or
  memory either, the twin says so plainly (e.g. "That's outside what I can
  help with here — I focus on {domain}") and reports `grounded=False`,
  instead of answering generally from the base model's own world knowledge
  — which is exactly the failure mode a domain-scoped twin needs to avoid.

**Frontend, so the domain is visible everywhere a twin is picked or
managed:**
- `CreateTwinWizard.tsx` — new required "Domain / expertise" field on step 1
  (Profile), blocking "Next" alongside the name.
- `OverviewTab.tsx` — the same field, editable, plus a domain chip in the
  header next to the `@slug` chip.
- `TwinGalleryCard.tsx` / `TwinCard.tsx` — a domain chip on every twin card,
  both the visitor-facing discovery gallery and the owner's own twin list —
  a visitor now sees what a twin is actually an expert in before clicking
  into it, not just its name/photo.
- `ChatPage.tsx` — the domain shown as a chip next to the twin's name in the
  chat header.
- `TwinDetailPage.tsx` — the domain shown under the twin's name in the
  management sidebar header.
- `api/types.ts` / `api/endpoints.ts` — `Twin.domain: string`;
  `createTwin`/`updateTwin` payload types updated to match.

**Verified live, real data, real Groq calls:**
- Migration applied against the real Postgres DB — confirmed both existing
  twins kept their id/name/sources/conversations and picked up the
  placeholder domain; `twin_attributes`/`schedule_entries` confirmed
  gone from the schema.
- `npx tsc --noEmit` on the frontend: zero errors after all of the above.
- Full backend import chain (`backend.main`, `backend.agent.*`,
  `backend.services.*`, `backend.api.twins`, `backend.api.chat`): clean.
- Live browser pass: set a real domain ("T2-RAG FYP project & backend/AI
  development") on the existing "umair" test twin through the Overview tab,
  confirmed it immediately appeared in the sidebar header, the status chip,
  the chat page header, and the public gallery card.
- **The actual behavior change, not just the label** — sent two real chat
  messages to the same twin through the live API: an off-domain question
  ("What is the best recipe for chicken biryani?") got back *"I'm sorry, but
  that's outside what I can help with here — I focus on the T2-RAG FYP
  project and backend/AI development"* instead of the base model answering
  generally from its own world knowledge (what would have happened before
  this session, since nothing previously told the agent it had a scope at
  all); a clearly on-domain follow-up ("What technologies does this project
  use?") was correctly treated as answerable-in-scope rather than also being
  deflected, confirming the new rule doesn't over-trigger on-domain
  questions, it only blocks genuinely out-of-scope ones.

Still not done: the second existing twin ("Umair AI Twin") still carries the
placeholder `'Please set your domain'` — intentionally left for the user to
fill in themselves rather than guessed, since only they know what domain
that twin is actually meant to represent; no backend enforcement rejecting
an ingested source that's off-topic for the declared domain (the user chose
the free-text-only option over an AI relevance guard — informational
scoping via the prompt, not a hard ingestion-time gate); the still-earlier,
still-unaddressed "no good colour combination or any good landing page"
feedback from session 20.

### 2026-10-24 (session 22) — Streaming replies, short-by-default answers, compressed chat input

User's ask, three related pieces in one message: (1) replies sometimes run
long and shouldn't by default — short (one-two lines) unless the question
genuinely needs more, not a hard rule; (2) the chat UI shouldn't have to
wait for the full LLM response before showing anything — it should stream;
(3) both the model's output and the conversation input fed back into the
model should stay compact rather than growing unbounded.

**Why streaming + structured output don't mix, and the design chosen
instead:** `generate_node` has used `with_structured_output()` since session
8 specifically so `policy_decision` (answer vs. escalate) comes from an
explicit self-reported `grounded` field instead of regex-matching phrases
in prose. Structured tool-call output doesn't stream in a UI-usable way —
you'd be watching a JSON object's fields fill in, not readable text. Rather
than adding a second LLM call after the stream to classify groundedness
(directly fighting this project's own documented 8,000 TPM Groq ceiling —
CLAUDE.md session 20 — by roughly doubling calls per turn), the streaming
path asks the model to self-report through the TEXT itself: an ungrounded
reply must begin with the literal marker `NEEDS_FOLLOWUP` as its very first
output. Only the first ~14 characters of the stream are buffered to check
for this — once confirmed present or absent, every following token is
forwarded immediately with zero added latency. A second buffering flag
(`suppress_leading_newlines`) catches the case where the blank line the
prompt asks the model to put after the marker lands as its own separate
stream chunk, so it doesn't leak through as a visible leading blank line in
the UI — caught and fixed during this session's own live curl testing, not
assumed correct from reading the code.

**Backend** (`backend/agent/nodes.py`):
- Both generation paths now share one prompt-building function,
  `_build_system_instruction(persona, domain, formatted_memory,
  formatted_context, marker_mode)` — `marker_mode=False` keeps the original
  structured-output instructions (`generate_node`, used by the voice path,
  which needs the complete answer before TTS can run regardless of
  streaming), `marker_mode=True` swaps in the NEEDS_FOLLOWUP instruction
  (`generate_stream`, new). The brevity rule ("keep replies short by
  default... summarize down to the essential point instead of including
  everything") is in the shared prompt, so it applies to text chat, voice
  chat, and any other caller of either path equally — not a UI-only
  constraint.
- New `prepare_retrieval(state)` — the retrieve → grade → (maybe one
  rewrite + re-retrieve) sequence as plain function calls instead of
  through the compiled LangGraph, since `graph.invoke()` blocks until
  `generate_node` finishes and the streaming path needs to intercept before
  that final step. The individual node functions it calls are unchanged and
  still used by `graph.py`'s `StateGraph` as before — this just gives the
  streaming path a way to reuse the same retrieval logic without going
  through the graph machinery for the one step that can't stream through it.
- New `generate_stream(state)` — a generator yielding plain `str` chunks as
  they arrive from `get_llm().stream(messages)`, then exactly one final
  `dict` (distinguishable by `isinstance`) with the full answer,
  `policy_decision`, and `confidence_score` once the stream ends.

**Backend** (`backend/services/conversation_service.py`):
- New `chat_stream(...)` — same contract and persistence as `chat()`
  (resolves access tier, loads history, saves the visitor message, runs
  retrieval, generates, saves the twin message, creates a `KnowledgeGap` on
  escalate) but calls `prepare_retrieval` + `generate_stream` instead of
  `self.graph.invoke()`, yielding chunks through to its caller as they're
  produced instead of returning once at the end.
- New module-level `_cap(text)` — truncates a single message to
  `settings.MAX_CHAT_MESSAGE_CHARS` (4,000, new) before it's used as LLM
  input. Applied to the current message in both `chat()` and
  `chat_stream()`, and to every historical message `_load_history()`
  reconstructs — never applied to what's stored in Postgres, only to what
  the model actually sees, so the audit trail keeps the visitor's real,
  untruncated text even when the model only saw a capped version.
- `_load_history()` now also windows to the most recent
  `settings.MAX_HISTORY_MESSAGES` (12, new) messages instead of replaying a
  conversation's entire history on every turn. **Deliberately truncation,
  not LLM-summarized compaction**: a rolling-summary approach would
  preserve more of a long conversation's context, but regenerating that
  summary on every window overflow costs an extra Groq call each time —
  exactly the kind of added load that caused real, documented crashes in
  this project before (session 20's Housekeeping 413). Window-dropping
  costs nothing extra and was judged the safer default; a twin forgetting
  something from far earlier in a very long conversation is an accepted,
  stated tradeoff of that choice, not an oversight.

**Backend** (`backend/api/chat.py`): new `POST /twins/{id}/chat/stream`,
same `ChatRequest` body as the existing blocking endpoint, but the response
is newline-delimited JSON (`application/x-ndjson`): repeated
`{"type":"chunk","text":"..."}` lines as the answer streams, then one
`{"type":"done","conversation_id":...,"sources":[...],"latency_ms":...}` —
or `{"type":"error","detail":...}` in its place on failure. A plain
`HTTPException` can't report a failure here the way the blocking endpoint's
`except ValueError` does: by the time an error surfaces inside the
generator (e.g. "twin not found"), the 200 response has already started
streaming, so the error has to be one more line in the stream instead of an
HTTP status change.

**Frontend:**
- `api/endpoints.ts` — new `sendChatStream()` using `fetch()` +
  `response.body.getReader()` (not `EventSource`, which can't send a POST
  body) to read the NDJSON stream, calling an `onChunk` callback per line
  and resolving with the trailing `done` metadata. `api/client.ts`'s
  `apiErrorMessage()` gained an `err instanceof Error` branch, since this
  path throws plain `Error`s on a stream-level failure, not axios errors.
- `pages/ChatPage.tsx` — `handleSendText` now appends an empty assistant
  bubble immediately and grows its text as chunks arrive via
  `sendChatStream`, instead of appending one complete bubble after
  `sendChat` resolves. `sendChat` (the old blocking call) is left in place
  in `endpoints.ts`, unused by the UI now but still a thin wrapper the
  still-live blocking `/chat` endpoint needs (used directly by
  `test_api_auth_flow.py` and available for any non-streaming caller) — not
  dead code, just no longer the UI's path.
- Voice chat (`sendVoiceChat`, push-to-talk, Call Mode) is untouched —
  it needs the complete text before TTS can synthesize audio regardless of
  whether generation itself streams, so there's no UI-visible streaming
  benefit there and it still calls the same backend path `generate_node`
  (not `generate_stream`) always used.

**Verified live, real Groq calls, real browser:**
- `curl -N` against `/chat/stream` directly: confirmed real token-by-token
  NDJSON chunks (e.g. "Could" / " you" / " let" / " me" / " know" ...), not
  one chunk per full response.
- On-domain question ("What technologies does this project use?") streamed
  correctly and the answer came back notably shorter than this same twin's
  pre-change replies, confirming the brevity instruction is doing real work,
  not just present in the prompt text.
- Off-domain question, twice (biryani recipe, quantum physics): both
  streamed the NEEDS_FOLLOWUP-triggered decline cleanly, with **no literal
  "NEEDS_FOLLOWUP" text and no leaked leading blank line** reaching the
  client on the second test, after the `suppress_leading_newlines` fix was
  added and the backend restarted — the first test (before that fix)
  visibly showed the leak, confirming the fix actually mattered rather than
  "probably not needed."
- Live browser pass on the real chat UI: asked a question that genuinely
  warranted a structured answer ("what technologies does this project
  use?") and got back an appropriately longer, bulleted-list reply —
  confirming the brevity rule's stated exception ("unless the question
  genuinely needs more... a list") actually holds and the instruction isn't
  over-triggering into cutting off answers that should be longer. Confirmed
  via `read_network_requests` that the page now calls `POST
  /twins/{id}/chat/stream` (with its CORS preflight `OPTIONS` succeeding)
  instead of the old blocking `/chat` route. Console clean apart from the
  same pre-existing, harmless first-request-before-token-attaches 401
  noted in every prior session.
- `npx tsc --noEmit`: zero errors. Full backend import chain
  (`backend.main`, `backend.agent.nodes`'s new `prepare_retrieval`/
  `generate_stream`, `backend.services.conversation_service`'s new
  `chat_stream`, `backend.api.chat`): clean.

Still not done: no client-side cap/warning when a visitor types a message
near `MAX_CHAT_MESSAGE_CHARS` — it's silently truncated server-side with an
"… [truncated]" marker rather than rejected or flagged in the UI before
sending; voice chat still has no streaming equivalent (would need
streaming TTS, a materially bigger piece of work, not attempted here); the
still-unaddressed "no good colour combination or any good landing page"
feedback from session 20, now two sessions old.

### 2026-10-24 (session 23) — Two bugfixes: domain-scoping was over-blocking general chat; voice calls now support barge-in

User reported two real problems with session 22's work, both fixed this
session: (1) the domain-scoping instruction added in session 21 was too
strict — ordinary conversational questions (greetings, "how are you",
"what can you help with") were getting the NEEDS_FOLLOWUP/off-domain
treatment instead of being answered directly, and the brevity instruction
from session 22 read as a hard cap rather than a preference; (2) during a
voice call, the twin's own reply audio played to completion even if the
visitor started talking over it — no barge-in/interrupt support existed.

**Fix 1 — prompt scoping, `backend/agent/nodes.py`'s
`_build_system_instruction()`:**
- Added an explicit carve-out paragraph right after the domain declaration:
  domain scoping applies to substantive, topical FACTUAL questions only —
  greetings, small talk, questions about the twin itself ("who are you",
  "what can you help with"), and conversational follow-ups are always fine
  regardless of domain, with "zero regard for the domain."
- Both the marker-mode (`generate_stream`) and structured-output-mode
  (`generate_node`) grounding instructions were rewritten with an explicit
  negative list ("NEVER use this marker for: a greeting, small talk,
  thanks, a question about yourself as a twin...") and an explicit
  tie-breaker: "When genuinely unsure whether something counts as
  off-domain or just ordinary conversation, treat it as ordinary
  conversation and answer normally — the marker is for real gaps, not a
  default." The old wording ("Use this marker for ANY ungrounded answer...
  not just off-domain ones") was almost certainly what pushed the model
  toward treating "didn't need retrieval" as "ungrounded" — removed.
- The brevity rule now reads "a preference, not a hard limit: never cut out
  information the visitor actually asked for just to stay brief, and never
  refuse or deflect a question only to keep the reply short" — directly
  responding to the user's "generate a small response if possible, not
  restricted."

**Fix 2 — barge-in, `frontend/src/hooks/useVoiceCall.ts`:**
- `getUserMedia` now explicitly requests `echoCancellation`,
  `noiseSuppression`, and `autoGainControl` (previously just `audio: true`)
  — without this, the twin's own reply playing through the speakers would
  leak into the mic and the barge-in monitor would see that as "the visitor
  is talking," interrupting the twin with its own voice.
- While `status === "speaking"`, a new RAF loop (`watchForBargeIn`, mirrors
  the existing listening-phase monitor, factored through a new shared
  `computeRms()` helper to avoid duplicating the RMS math a third time)
  watches the same mic analyser. If RMS clears `BARGE_IN_RMS_THRESHOLD`
  (0.035, deliberately higher than the normal 0.02 listening threshold) for
  a sustained `BARGE_IN_SUSTAIN_MS` (220ms, not a single loud frame) after
  an initial `BARGE_IN_GRACE_MS` (400ms) grace period at the start of
  playback, `interruptAndListen()` fires: cancels the monitor loop, detaches
  `audio.onended`/`onerror` (so the natural-end handlers don't also fire),
  pauses the audio, and calls `startListening()` immediately — the visitor's
  interrupting speech is captured as a fresh utterance from that point, not
  lost or merged with anything.
- `await audio.play()` is now wrapped in its own try/catch: `play()` can
  reject with an AbortError if `interruptAndListen()`'s `pause()` races it
  (the visitor talks right as playback starts) — expected, not a real
  failure, so it's swallowed instead of surfacing as an error toast.
- `CallOverlay.tsx` needed no changes — barge-in transitions `status`
  straight from `"speaking"` to `"listening"` via the same `startListening()`
  path manual silence-detection already uses, which the overlay already
  renders correctly (pulsing ring keyed to live mic volume).

**Verified live, real Groq calls:**
- Five conversational messages ("hi", "how are you", "what can you help me
  with", "thanks", "who are you") sent directly to the real `/chat`
  endpoint against the twin whose domain is "T2-RAG FYP project &
  backend/AI development" — all five answered directly and warmly, zero
  NEEDS_FOLLOWUP/decline behavior, confirming the over-blocking is fixed.
- Re-tested both previously-passing cases to confirm the fix didn't
  over-correct into answering everything: "What is the best recipe for
  chicken biryani?" still correctly declined ("That's outside what I can
  help with here..."), "What technologies does this project use?" still
  correctly answered in full, on-domain detail — the scoping still works,
  just no longer catches ordinary conversation in its net.
- Re-ran the streaming endpoint (`/chat/stream`) against a general greeting
  after this fix — confirmed real token-by-token chunks still arrive and
  the marker-detection/buffering logic from session 22 is unaffected by the
  prompt wording change.
- `npx tsc --noEmit` on the frontend: zero errors after the `useVoiceCall.ts`
  changes. Full backend import chain: clean.
- Barge-in itself could not be exercised through this session's browser
  automation — it needs a live microphone and live TTS audio actually
  playing through speakers, neither of which this tooling can drive (the
  same standing limitation noted for every voice feature in this project
  since session 12). The RMS/timing logic was verified by code review
  against the same pattern the existing, already-verified-working
  listening-phase monitor uses, not by an end-to-end recorded test — **a
  human trying an actual interruption mid-call is still worth doing once.**

Still not done: barge-in has no user-facing settings (threshold/sustain
time are fixed constants, not configurable); the still-unaddressed "no good
colour combination or any good landing page" feedback, now three sessions
old.

### 2026-10-24 (session 24) — Real landing page, richer theme, animations across the app

Direct follow-up to the "no good colour combination or any good landing
page" feedback that had been outstanding since session 20 — finally
addressed head-on this session, plus the broader "animations in whole
webapp" ask.

**What "landing page" meant here, concretely**: before this session, `/`
for a logged-out/visitor-role user rendered straight into the twin gallery
("Who do you want to talk to?") with zero marketing/intro content — there
was no actual landing page anywhere in the app. Rather than add a separate
route that would duplicate the gallery's logic, a hero section
(`components/LandingHero.tsx`) was added above the existing gallery on that
same view — the gallery itself is unchanged, now framed as the section the
hero's "Browse twins" button scrolls down to.

**New dependency**: `framer-motion@11` — chosen as the standard React
animation library (declarative `motion.*` components + `AnimatePresence`
for enter/exit, `layoutId` for shared-element transitions), not previously
in this project.

**Theme** (`frontend/src/theme.ts`):
- `BRAND.heroMesh` — a 3-radial-gradient dark mesh background (indigo,
  teal, amber highlights over a near-black `#0B0F1A` base) used by both the
  new hero and the login page, not a flat gradient — reads as deliberately
  designed rather than a CSS-default gradient.
- `BRAND.accent` (`#F59E0B`, amber) — a third color alongside the existing
  indigo/teal pair, used sparingly (the hero's third feature icon) rather
  than registered as a full MUI palette color (would need TS module
  augmentation for a 4th palette key — not worth it for one accent use).
- A `@keyframes drift` registered once on `MuiCssBaseline` (not
  per-component) — a slow (18s), subtle scale+translate loop reused by
  every dark hero-mesh background in the app, so the "mesh" background
  pattern itself only needs defining once.

**New landing hero** (`components/LandingHero.tsx`): headline ("Talk to
someone's knowledge, not a chatbot."), subheadline explaining the
grounded/cited/cloned-voice/access-controlled pitch, two CTAs ("Browse
twins" scrolls to the gallery via a ref, "Create your own" goes to
`/login`), and three feature chips (Grounded answers / Cloned voice /
Tiered access) — all entering with a framer-motion staggered fade-up
(`staggerChildren: 0.12`), not appearing all at once.

**Page-level and component-level animation** (the "whole webapp" part):
- `components/PageTransition.tsx` (new) — wraps the routed page in a brief
  fade+rise keyed by `location.pathname`, wired into `Layout.tsx` in place
  of a bare `<Outlet />`. Deliberately subtle (200ms, 8px) since it fires on
  every single navigation in the app.
- `pages/DashboardPage.tsx` — both card grids (the visitor gallery and the
  owner's own twin list) now stagger their cards in via shared
  `gridContainer`/`gridItem` variants instead of appearing instantly.
- `components/ChatBubble.tsx` — each message pops in (opacity+y+scale) on
  mount. Because the streaming assistant bubble is one persistent component
  instance whose `text` prop grows in place across re-renders (same React
  key throughout a stream, per session 22's design), the entrance animation
  fires exactly once per message, not once per streamed chunk.
- `pages/LoginPage.tsx` — given the same dark hero-mesh background as the
  landing hero (consistency between the two "arrival" surfaces of the app)
  plus a fade+scale entrance for the card and a "Back" button (the login
  route sits outside `Layout`'s `AppBar`, so it had no way back to `/`
  before this).
- `components/CreateTwinWizard.tsx` — each of the 3 steps now slides in/out
  (`AnimatePresence mode="wait"`, keyed by step) instead of swapping
  instantly.
- `pages/TwinDetailPage.tsx` — two changes: the sidebar's active-tab
  highlight is now a `motion.div` with `layoutId="nav-active-pill"` that
  smoothly slides between nav items (a shared-layout animation, not a
  background-color swap) instead of an instant highlight jump; the tab
  content area itself fades between tabs via `AnimatePresence` keyed by
  `tab`.

**A real, transient issue caught and resolved during this session's own
testing, not a lingering bug**: a stale-HMR render of the login page's
background (captured via `navigate` without a hard reload) showed the
gradient mesh clipped to roughly half the viewport. Diagnosed via direct
`getBoundingClientRect()`/`getComputedStyle()` queries in the live page
before concluding it was a CSS bug — the computed styles showed the
background box and its `background-color`/`background-image` were
correctly covering the full viewport the whole time; a hard reload (`force:
true`) rendered it perfectly. Confirmed as a one-off stale client-side-nav
artifact, not a real defect — not something that needed a code change.
Similarly, a `[vite] Failed to reload CreateTwinWizard.tsx` console error
seen later was confirmed (via `preview_logs`' timestamped history) to be
from a transient mid-edit state between this session's own sequential file
edits, with a clean successful HMR update logged immediately after — not a
persisting problem, confirmed by opening a fresh browser tab (console
history persists across client-side navigations in the same tab, so a
fresh tab was needed for a trustworthy clean-console read).

**Verified live, fresh tab, real browser:**
- `npx tsc --noEmit`: zero errors through all of this session's changes.
- Landing hero renders correctly with the full dark mesh background, all
  three feature chips, both CTAs; "Browse twins" correctly smooth-scrolls
  down to the gallery section, whose cards are visible below.
- Login page renders correctly with the matching mesh background and a
  working "Back" button (previously impossible to reach "/" from here
  without the browser's own back button).
- Owner dashboard, twin detail sidebar (pill slides between Overview and
  Knowledge, tab content fades), and chat (bubbles pop in, including the
  streaming assistant bubble) all exercised live with a clean console in a
  fresh tab (only the standing, harmless pre-token-attach 401 noted in
  every session since 13).
- Create-twin wizard dialog opens and renders step 1 correctly with no
  console errors in the fresh-tab check.

Still not done: no dark mode (flagged in nearly every session since 13 —
the new hero-mesh dark treatment is a deliberate ACCENT used on specific
surfaces, not a site-wide dark theme); no animation on `KnowledgeGapsTab`'s
cluster cards or `QdrantExplorerPage`'s bars/tiles (lower-traffic pages,
left for a future pass if it matters); mobile/narrow-viewport layout still
not a priority anywhere in this app (consistent with every prior session,
not a new gap introduced here).
