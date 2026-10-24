"""
Database smoke test — touches every table in the v3 (domain-scoped twin)
schema once, end to end: owner + visitor identity, an access grant, a
knowledge source, a media asset, a conversation + message + call session, and
per-visitor memory (visitor_profile_facts + memory_chunks).

Not a pytest suite (no assertions) — just proves the model graph round-trips
through Postgres without constraint errors. See Phase 5 in CLAUDE.md for
converting this into real pytest tests.
"""
from datetime import datetime, timezone

from backend.db.session import SessionLocal
from backend.db.models import (
    AccessGrant, CallSession, Conversation, KnowledgeGap, MediaAsset, MemoryChunk,
    Message, Source, Twin, User, VisitorProfileFact,
)
from sqlalchemy.exc import IntegrityError


def run_test():
    db = SessionLocal()
    try:
        # 1. Owner + Twin
        owner = User(
            email="owner@t2rag.local",
            password_hash="fakehash123",
            display_name="Owner User",
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
        print(f"[OK] owner created: {owner.email}")

        twin = Twin(
            owner_id=owner.id,
            slug="umair-demo-twin",
            name="Expert Assistant",
            domain="Backend API development",
            bio="A highly knowledgeable AI twin.",
            persona_prompt="You are a helpful assistant.",
        )
        db.add(twin)
        db.commit()
        db.refresh(twin)
        print(f"[OK] twin created: {twin.name} (slug={twin.slug})")

        # 2. Visitor identity (passwordless) + access grant
        visitor = User(
            email="visitor@example.com",
            password_hash=None,
            display_name="Visiting Recruiter",
        )
        db.add(visitor)
        db.commit()
        db.refresh(visitor)

        grant = AccessGrant(
            twin_id=twin.id,
            visitor_id=visitor.id,
            tier_name="friends",
            granted_by=owner.id,
        )
        db.add(grant)
        db.commit()
        print(f"[OK] access grant created: visitor={visitor.email} tier={grant.tier_name}")

        # 3. Knowledge source
        source = Source(
            twin_id=twin.id,
            source_type="upload",
            name="knowledge_base_v1.pdf",
            visibility="public",
            status="completed",
        )
        db.add(source)
        db.commit()
        print(f"[OK] source registered: {source.name}")

        # 4. Media asset (voice sample, consent confirmed)
        media = MediaAsset(
            twin_id=twin.id,
            asset_type="voice_sample",
            storage_path="/data/media/umair_voice_01.wav",
            duration_seconds=42.0,
            format="wav",
            status="completed",
            consent_confirmed_at=datetime.now(timezone.utc),
        )
        db.add(media)
        db.commit()
        print(f"[OK] media asset: {media.asset_type} ({media.duration_seconds}s)")

        # 5. Conversation + message + call session
        conv = Conversation(
            twin_id=twin.id,
            visitor_id=visitor.id,
            visitor_name=visitor.display_name,
            channel="voice",
            access_tier=grant.tier_name,
            is_owner_session=False,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg = Message(
            conversation_id=conv.id,
            role="visitor",
            content="Hello! What can you do?",
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)

        call = CallSession(conversation_id=conv.id, end_reason="completed")
        db.add(call)
        db.commit()
        print(f"[OK] conversation logged: channel={conv.channel}, 1 message, 1 call session")

        # 6. Per-visitor memory: a structured fact + a Qdrant-bound memory chunk
        fact = VisitorProfileFact(
            twin_id=twin.id,
            visitor_id=visitor.id,
            key="stated_role",
            value="recruiter",
            source_message_id=msg.id,
        )
        db.add(fact)
        db.commit()

        memory_chunk = MemoryChunk(
            twin_id=twin.id,
            visitor_id=visitor.id,
            origin_conversation_id=conv.id,
        )
        db.add(memory_chunk)
        db.commit()
        print(f"[OK] visitor memory: fact={fact.key}={fact.value}, memory_chunk registered")

        # 7. Knowledge gap: the twin couldn't answer -> queued -> owner answers it
        gap = KnowledgeGap(
            twin_id=twin.id,
            conversation_id=conv.id,
            question_message_id=msg.id,
            question_text="What's your availability next month?",
        )
        db.add(gap)
        db.commit()
        db.refresh(gap)

        # The owner answers later: becomes a new Source (not embedded here --
        # that's the ingestion pipeline's job, not this smoke test's).
        answer_source = Source(
            twin_id=twin.id,
            source_type="escalation_answer",
            name=f"answer to: {gap.question_text[:40]}",
            visibility="public",
            status="completed",
        )
        db.add(answer_source)
        db.commit()
        db.refresh(answer_source)

        gap.status = "answered"
        gap.answer_text = "I'm generally free weekday afternoons next month."
        gap.answered_at = datetime.now(timezone.utc)
        gap.resulting_source_id = answer_source.id
        db.commit()
        print(f"[OK] knowledge gap: '{gap.question_text}' -> answered, linked to source {answer_source.id}")

        print("\nAll v2 tables round-tripped successfully.")

    except IntegrityError as e:
        db.rollback()
        print(f"[FAIL] database integrity error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    run_test()
