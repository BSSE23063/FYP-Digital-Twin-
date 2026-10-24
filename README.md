# T2-RAG — Context-Aware Digital Twin Platform

A full-stack AI-powered Digital Twin platform that creates personalized conversational twins grounded in an owner's knowledge, documents, and profile. Built around Retrieval-Augmented Generation (RAG), semantic search, access-controlled knowledge sharing, and a feedback loop that allows twins to learn from unanswered questions.

## Overview

T2-RAG is a Final Year Project exploring how AI can represent a person's knowledge and make it accessible through a persistent, context-aware digital twin.

Each twin has its own knowledge base. Owners can upload documents, add text notes, and import public GitHub profile information. Visitors can interact with twins through a conversational interface, while access permissions control which knowledge can be retrieved.

When a twin cannot answer a question reliably, it can escalate the question to its owner. The owner can provide an answer, which is ingested into the twin's knowledge base so that it can be retrieved in future conversations.

The platform is designed around a core principle:

**PostgreSQL stores structured application data; Qdrant stores semantically searchable knowledge and memory.**

## Key Features

- **Personalized Digital Twins:** Create and manage individual twins with a profile, domain, and personality instructions.
- **Retrieval-Augmented Generation:** Retrieve relevant knowledge chunks and use them to generate context-grounded answers through Groq.
- **Document Ingestion:** Process supported PDF, DOCX, TXT, and Markdown files, as well as manually supplied text.
- **Semantic Search:** Generate vector embeddings with FastEmbed and search using Qdrant.
- **Multi-Tenant Isolation:** Maintain a separate Qdrant collection for each twin.
- **Authentication:** Owner registration and login with password hashing and JWT-based authentication.
- **Granular Access Control:** Manage visitor access grants and control access to public, friends-only, and private knowledge.
- **Knowledge-Gap Resolution:** Escalate unanswered questions to the owner, then ingest approved answers into the knowledge base.
- **Conversation History:** Persist conversations and messages, including retrieval sources, policy decisions, and latency metadata.
- **GitHub Profile Import:** Import public GitHub profile and repository information into a twin's knowledge base.
- **Voice Interaction:** Support audio input, speech transcription, RAG-based response generation, and synthesized spoken replies.
- **Voice Cloning Experiments:** Prototype personalized voice synthesis using Pocket TTS.
- **Modern Web Interface:** React-based owner dashboard, twin discovery gallery, text chat, voice messages, and hands-free call mode.

## Architecture

```mermaid
flowchart TD
    U[Owner or Visitor] --> FE[React Frontend]
    FE --> API[FastAPI Backend]

    API --> AUTH[Authentication and Access Control]
    API --> SVC[Service Layer]

    SVC --> PG[(PostgreSQL)]
    SVC --> ING[Ingestion Pipeline]
    SVC --> AGENT[LangGraph RAG Agent]
    SVC --> VOICE[Voice Pipeline]

    ING --> PARSE[Document Parsing]
    PARSE --> CHUNK[Text Chunking]
    CHUNK --> EMB[FastEmbed]
    EMB --> QD[(Qdrant)]

    AGENT --> RET[Knowledge Retrieval]
    RET --> QD
    RET --> GRADE[Relevance Grading]
    GRADE --> GEN[Groq LLM]
    GEN --> RESP[Grounded Response]

    VOICE --> ASR[Speech Recognition]
    ASR --> AGENT
    RESP --> TTS[Pocket TTS]
    TTS --> AUDIO[Generated Audio]

    RESP --> GAP[Knowledge Gap Escalation]
    GAP --> OWNER[Owner Answers Question]
    OWNER --> ING
```

The diagram represents the main application flow. The voice pipeline is currently an audio-in/audio-out capability; a fully real-time WebRTC calling system and live talking avatar are not yet implemented.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Material UI |
| Backend | Python, FastAPI |
| Relational database | PostgreSQL |
| ORM | SQLAlchemy |
| Vector database | Qdrant |
| Embeddings | FastEmbed, BAAI/bge-small-en-v1.5 |
| LLM inference | Groq API |
| Agent orchestration | LangGraph, LangChain |
| Document processing | LangChain text splitters and document parsers |
| Authentication | JWT, bcrypt |
| Speech recognition | faster-whisper |
| Text-to-speech | Pocket TTS |
| Testing | Python smoke and integration scripts |

## How the RAG Pipeline Works

1. **Ingestion:** The owner uploads a supported document, imports public GitHub information, or submits text.
2. **Parsing:** The ingestion pipeline extracts usable text from the supplied source.
3. **Chunking:** Text is split into smaller, overlapping chunks. The default configuration uses a chunk size of 500 characters with an overlap of 50 characters.
4. **Embedding:** FastEmbed converts chunks into 384-dimensional vectors.
5. **Storage:** Vectors and associated metadata are stored in the Qdrant collection belonging to that twin.
6. **Retrieval:** A visitor's question is embedded and used to search the appropriate twin's knowledge collection, applying the relevant visibility restrictions.
7. **Grading:** The agent evaluates retrieval relevance and can perform one bounded query-rewriting retry.
8. **Generation:** Groq generates a response using the retrieved knowledge and conversational history.
9. **Escalation:** If the agent determines that it cannot provide a grounded answer, the question can be recorded as a knowledge gap.
10. **Learning:** The owner answers the question, and the resulting source passes through the ingestion pipeline to become searchable knowledge.

## Data Storage Strategy

### PostgreSQL

PostgreSQL stores structured application information, including:

- Users and authentication-related records
- Digital twins and their profiles
- Source metadata and ingestion status
- Access tiers and visitor access grants
- Conversations and messages
- Knowledge gaps and their resolution history
- Media asset metadata and visitor memory records

### Qdrant

Qdrant stores vectorized knowledge and semantically searchable memory.

Each twin has its own collection, named using the configured collection prefix followed by its twin ID. This provides collection-level isolation between twins.

Knowledge points include metadata such as source identifiers and visibility. Visitor memory points are associated with their visitor identity and memory records.

### Embedding Configuration

The default embedding model is `BAAI/bge-small-en-v1.5`, producing 384-dimensional vectors. The configured embedding dimension must match the vector size of the Qdrant collection.

## Project Structure

```text
t2-rag/
├── backend/
│   ├── agent/
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   ├── api/
│   ├── db/
│   ├── ingestion/
│   │   ├── parser.py
│   │   ├── pipeline.py
│   │   └── fetchers.py
│   ├── rag/
│   │   ├── embeddings.py
│   │   └── retriever.py
│   ├── services/
│   ├── vectordb/
│   ├── voice/
│   ├── config.py
│   └── main.py
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── qdrant_storage/
├── tests and verification scripts
├── requirements.txt
├── .env.example
└── README.md
```

This is a representative structure; individual files and directories may evolve during development.

## Getting Started

### Prerequisites

Install the following before running the project:

- Python 3.10 or a compatible Python version supported by the dependencies
- Node.js and npm
- PostgreSQL
- A Groq API key

Qdrant currently uses local embedded storage, so a separate Qdrant server is not required for the default development configuration.

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/t2-rag.git
cd t2-rag
```

Replace `YOUR_USERNAME` with your GitHub username and adjust the repository name if necessary.

### 2. Create a Python Virtual Environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks virtual environment activation, use the Python executable directly from `.venv\Scripts\python.exe` or follow Microsoft's PowerShell execution-policy guidance.

### 3. Configure Environment Variables

Create a local `.env` file in the backend project's root directory. Do not commit this file.

Example configuration:

```dotenv
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/t2rag
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
SECRET_KEY=replace_with_a_long_random_secret
DEBUG=false
QDRANT_PATH=./qdrant_storage
QDRANT_COLLECTION_PREFIX=twin_
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384
CHUNK_SIZE=500
CHUNK_OVERLAP=50
```

These are example values. Check `backend/config.py` for the exact settings supported by your checkout, including any voice-specific configuration.

Create the `t2rag` PostgreSQL database before starting the application. Update the connection string with your actual local database credentials.

### 4. Initialize the Database

From the repository root:

```powershell
python -m backend.db.init_db
```

**Important:** The development database may require a schema reset when the models change. A reset drops existing database tables and their data, so back up any data you need before using the destructive reset option.

```powershell
python -m backend.db.init_db --reset
```

Use the reset command only when necessary in a disposable development database.

### 5. Start the Backend

From the repository root:

```powershell
python -m uvicorn backend.main:app --reload
```

The backend should be available at:

- API base URL: `http://127.0.0.1:8000`
- Interactive API documentation: `http://127.0.0.1:8000/docs`

### 6. Start the Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, typically `http://localhost:5173`.

If the frontend cannot reach the API, verify its API base URL and the backend's CORS configuration.

## Main Application Capabilities

| Capability | Description |
|---|---|
| Authentication | Register and log in as an owner; support passwordless visitor identity |
| Twin management | Create, view, and manage digital twins |
| Knowledge ingestion | Upload documents, submit text, and import public GitHub information |
| Text conversations | Ask questions and receive context-aware responses |
| Access grants | Grant and revoke visitor permissions |
| Knowledge gaps | Review unanswered questions and submit owner-provided answers |
| Voice chat | Submit audio and receive a synthesized spoken response |
| Conversation history | Persist and browse previous conversations |
| Audit metadata | Record policy decisions, retrieval sources, and latency information |

For the authoritative endpoint schemas and request formats, use the interactive Swagger documentation at `/docs` after starting the backend.

## Verification and Testing

The repository includes scripts for verifying core application flows, including:

- Database model round-trips
- RAG retrieval and response generation
- Document ingestion and idempotent reprocessing
- Authentication, access grants, chat, and knowledge-gap resolution
- Voice pipeline processing

Some scripts require a running PostgreSQL database, local Qdrant storage, a valid Groq API key, or downloaded speech-model weights.

Run the relevant scripts from the repository root using the Python environment configured for the project. These are currently smoke and integration scripts; a comprehensive `pytest` suite and continuous integration pipeline remain future work.

## Current Limitations

- Voice synthesis on CPU can be slow, so voice responses are not yet suitable for consistently low-latency live conversation.
- Full real-time WebRTC calling and neural talking-avatar video are future development goals.
- Visitor passwordless login does not yet verify email ownership through a magic-link flow.
- Database schema migrations using Alembic are not yet implemented.
- Automated CI and a comprehensive pytest suite are still pending.
- Local embedded Qdrant storage is intended for development and can cause conflicts if multiple processes access the same storage path concurrently.
- Model performance, retrieval quality, and response grounding require further systematic evaluation.

## Roadmap

- [x] Implement the core RAG pipeline with Qdrant and Groq.
- [x] Build document ingestion and embedding generation.
- [x] Add FastAPI endpoints and the service layer.
- [x] Implement authentication and visitor access grants.
- [x] Add relevance grading and bounded query rewriting.
- [x] Build the React frontend and conversation interface.
- [x] Implement knowledge-gap escalation and owner-answer ingestion.
- [x] Prototype audio transcription and synthesized voice responses.
- [ ] Add Alembic database migrations and a stronger automated test suite.
- [ ] Benchmark retrieval quality, grounding, and end-to-end latency.
- [ ] Improve CPU voice-generation performance.
- [ ] Explore real-time voice communication.
- [ ] Revisit live avatar and video-call support.

## Security and Privacy

- Keep API keys, database credentials, JWT signing secrets, and private environment files out of version control.
- Use server-side authentication and authorization for protected operations.
- Apply access restrictions during retrieval, not merely in the user interface.
- Treat voice samples and other biometric-like media as sensitive data, and obtain appropriate consent before processing or cloning them.
- Do not use real private documents or personal recordings in public test fixtures.

## Academic Context

This project is being developed as a Software Engineering Final Year Project focused on Retrieval-Augmented Generation, personalized AI systems, vector search, access control, and persistent conversational memory.

The objective is to investigate how a digital twin can answer questions using an individual's own knowledge while maintaining access boundaries and a mechanism for resolving unanswered questions.

## Contributing

Contributions, suggestions, and technical discussions are welcome. For substantial changes, consider opening an issue first to discuss the proposed implementation.

## License

No license has been specified yet. Unless a license is added to this repository, all rights remain with the copyright holder and reuse is not automatically permitted.

---

**Built with Python, FastAPI, PostgreSQL, Qdrant, LangGraph, Groq, and React.**
