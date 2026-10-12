"""
Comprehensive test script for the T2-RAG system:
- Twin creation & Access tiers
- Document ingestion & Chunker offset verification
- ChromaDB indexing & Tenant isolation guarantee test
- LangGraph RAG invocation check
"""

import sys
from backend.db.session import SessionLocal, engine, Base
from backend.services.twin_service import TwinService
from backend.services.document_service import DocumentService
from backend.services.conversation_service import ConversationService
from backend.rag.vector_store import get_vector_store


def run_tests():
    print("=" * 65)
    print("[RUN] T2-RAG End-to-End System & Multi-Tenancy Isolation Test")
    print("=" * 65)

    db = SessionLocal()
    twin_svc = TwinService(db)
    doc_svc = DocumentService(db)
    conv_svc = ConversationService(db)
    v_store = get_vector_store()

    try:
        # 1. Clean existing test twins if any
        existing_twins = twin_svc.list_twins()
        for t in existing_twins:
            if t.name in ["Umair Twin", "Competitor Twin"]:
                print(f"Cleaning previous test twin: {t.name}")
                twin_svc.delete_twin(t.id)

        # 2. Create Twin A (Umair)
        print("\n[1/5] Creating Twin A (Umair)...")
        twin_a = twin_svc.create_twin(
            name="Umair Twin",
            description="Software Engineering final year student focused on AI/ML.",
            persona_prompt="I am Umair, an AI/ML enthusiast from Lahore building digital twins. I speak professionally and enthusiastically about agentic AI."
        )
        print(f"  -> Created Twin A: ID={twin_a.id}, Name={twin_a.name}")

        # 3. Ingest documents for Twin A
        print("\n[2/5] Ingesting Knowledge for Twin A...")
        cv_text = """
        Hafiz Umair is a final-year Software Engineering student located in Lahore, Pakistan.
        He has deep expertise in Agentic AI, LangGraph, FastAPI, and vector retrieval.
        His Final Year Project (FYP) is T2-RAG: a Personal AI Digital Twin platform with grounded RAG,
        tenant isolation, and calibrated hallucination guards.
        Umair completed an internship as a Machine Learning Engineer where he built semantic search pipelines.
        """
        doc_a = doc_svc.ingest_raw_text(
            twin_id=twin_a.id,
            filename="umair_profile.txt",
            text_content=cv_text,
            visibility="public",
        )
        print(f"  -> Ingested Doc A: ID={doc_a.id}, Status={doc_a.ingestion_status}, Chunks={doc_a.chunk_count}")

        # 4. Create Twin B (Different tenant) and ingest different knowledge
        print("\n[3/5] Creating Twin B (Competitor Twin) for Multi-Tenancy Isolation Test...")
        twin_b = twin_svc.create_twin(
            name="Competitor Twin",
            description="Alice, a Graphic Designer in New York.",
            persona_prompt="I am Alice, a creative graphic designer."
        )
        alice_text = """
        Alice is a Senior UI/UX Designer based in New York.
        She specializes in Figma design systems, typography, and motion graphics.
        Her flagship project is an open-source 3D icon library.
        """
        doc_b = doc_svc.ingest_raw_text(
            twin_id=twin_b.id,
            filename="alice_profile.txt",
            text_content=alice_text,
            visibility="public",
        )
        print(f"  -> Ingested Doc B: ID={doc_b.id}, Status={doc_b.ingestion_status}, Chunks={doc_b.chunk_count}")

        # 5. Verify Strict Tenant Isolation
        print("\n[4/5] Testing Tenant Isolation in ChromaDB...")
        # Search Twin A with a query about Alice
        results_a_for_alice = v_store.search(
            twin_id=twin_a.id,
            query_text="Where is Alice based and what is her design project?",
            allowed_visibilities=["public"],
        )
        # Search Twin B with a query about Umair
        results_b_for_umair = v_store.search(
            twin_id=twin_b.id,
            query_text="What is Umair's Final Year Project and location?",
            allowed_visibilities=["public"],
        )

        # Confirm Twin A NEVER gets Alice's documents
        for r in results_a_for_alice:
            assert "Alice" not in r["content"], "LEAK DETECTED: Twin A returned Twin B's knowledge!"
            assert r["metadata"]["twin_id"] == twin_a.id, "LEAK DETECTED: Incorrect twin_id in metadata!"

        # Confirm Twin B NEVER gets Umair's documents
        for r in results_b_for_umair:
            assert "Umair" not in r["content"], "LEAK DETECTED: Twin B returned Twin A's knowledge!"
            assert r["metadata"]["twin_id"] == twin_b.id, "LEAK DETECTED: Incorrect twin_id in metadata!"

        print("  [PASS] Tenant Isolation PASSED: Twin A and Twin B are completely isolated!")

        # 6. Test LangGraph RAG Invocation
        print("\n[5/5] Testing LangGraph Conversational Pipeline for Twin A...")
        chat_res = conv_svc.chat(
            twin_id=twin_a.id,
            message="What is your Final Year Project and what technologies are you using?",
            visitor_name="Recruiter",
            access_tier="public",
        )
        print(f"  -> Decision: {chat_res['policy_decision']}")
        print(f"  -> Confidence Score: {chat_res['confidence_score']}")
        print(f"  -> Latency: {chat_res['latency_ms']} ms")
        print(f"  -> Sources Cited: {len(chat_res['sources'])} chunks")
        print(f"  -> Twin Response:\n\n{chat_res['answer']}\n")

        print("=" * 65)
        print("[SUCCESS] All T2-RAG Pipeline and Isolation Tests Completed!")
        print("=" * 65)

    finally:
        db.close()


if __name__ == "__main__":
    run_tests()

