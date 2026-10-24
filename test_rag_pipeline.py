"""
End-to-End System Verification Script.
Tests FastEmbed, the pooled Qdrant collection (knowledge AND memory points),
and LangGraph execution via Groq.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252, which
# can't print characters some LLMs output (e.g. typographic spaces/quotes).

from dotenv import load_dotenv
load_dotenv()  # MUST be called before importing backend modules

import uuid
from langchain_core.messages import HumanMessage

from backend.vectordb.collections import ensure_twin_collection
from backend.vectordb.operations import upsert_knowledge_chunks, upsert_memory_chunks
from backend.rag.embeddings import process_document, embed_texts
from backend.agent.graph import rag_app


def run_verification():
    twin_id = "test-twin-001"
    visitor_id = "test-visitor-001"

    print("\n--- 0. Ensure this twin's own Qdrant collection exists ---")
    collection_name = ensure_twin_collection(twin_id)
    print(f"[OK] using collection '{collection_name}'")

    print("\n--- 1. Knowledge ingestion (chunk -> embed -> upsert) ---")
    knowledge_text = (
        "Umair is building a Digital Twin application called T2-RAG. "
        "The system uses PostgreSQL for relational data, Qdrant for vector embeddings, "
        "and LangGraph with Groq for autonomous AI reasoning. "
        "The project structure separates DB, VectorDB, RAG utilities, and the Agent system."
    )
    source_id = f"src-{uuid.uuid4().hex[:6]}"
    processed = process_document(knowledge_text)
    upsert_knowledge_chunks(
        twin_id=twin_id,
        source_id=source_id,
        visibility="public",
        vectors=processed["embeddings"],
        documents=processed["chunks"],
        metadatas=[{"chunk_index": i} for i in range(len(processed["chunks"]))],
    )
    print(f"[OK] chunked into {len(processed['chunks'])} chunk(s), "
          f"embedding dim {len(processed['embeddings'][0])}, upserted as knowledge points")

    print("\n--- 2. Visitor memory ingestion (simulating a learned fact) ---")
    memory_text = "This visitor said they are a recruiter evaluating Umair for a backend role."
    memory_chunk_id = f"mem-{uuid.uuid4().hex[:6]}"
    upsert_memory_chunks(
        twin_id=twin_id,
        visitor_id=visitor_id,
        memory_chunk_id=memory_chunk_id,
        vectors=embed_texts([memory_text]),
        documents=[memory_text],
    )
    print("[OK] upserted 1 memory point for this visitor")

    print("\n--- 3. LangGraph agentic pipeline (knowledge + memory, via Groq) ---")
    initial_state = {
        "messages": [HumanMessage(content="What technologies is Umair using, and why are you talking to me?")],
        "twin_id": twin_id,
        "visitor_id": visitor_id,
        "allowed_visibilities": ["public"],
        "persona_prompt": "You are a helpful and concise AI assistant for Umair.",
        "context_documents": [],
        "memory_documents": [],
    }

    result = rag_app.invoke(initial_state)

    print("\n--- VERIFICATION RESULTS ---")
    print(f"Knowledge chunks retrieved: {len(result['context_documents'])}")
    print(f"Memory chunks retrieved:    {len(result['memory_documents'])}")
    print("\nAI Response (Groq LLM):")
    print(result["messages"][-1].content)


if __name__ == "__main__":
    run_verification()
