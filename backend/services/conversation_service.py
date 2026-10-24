"""
Conversation service: resolves access tier SERVER-SIDE (never from client
input — see the SECURITY note on ChatRequest in backend/api/chat.py and the
Conversation docstring in backend/db/models.py), loads prior turns so the
agent gets real multi-turn context, invokes the LangGraph agent, and persists
the audit trail (policy_decision, confidence_score, latency_ms, sources_json).

Two generation paths (session 22): chat() blocks for the full answer (used by
voice, which needs complete text before TTS can run); chat_stream() yields
the answer token-by-token for the text chat endpoint. Both apply the same
input-compression settings (_cap, MAX_HISTORY_MESSAGES) before anything
reaches the LLM — see backend/config.py's comment for why windowing was
chosen over LLM-summarized history (an extra Groq call per overflow would
fight the exact TPM limit this is meant to relieve).
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.agent.graph import rag_app
from backend.agent.nodes import generate_stream, prepare_retrieval
from backend.config import settings
from backend.db.models import AccessGrant, AccessTier, Conversation, KnowledgeGap, Message, Twin


def _cap(text: str) -> str:
    """Caps a single message to MAX_CHAT_MESSAGE_CHARS before it's used as
    LLM input. Never applied to what's stored in Postgres — only to what's
    sent to the model, so the audit trail (Message.content) always keeps the
    visitor's full original text even when the model only saw a capped
    version of it."""
    limit = settings.MAX_CHAT_MESSAGE_CHARS
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "… [truncated]"


class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.graph = rag_app

    def resolve_access_tier(self, twin: Twin, visitor_id: Optional[str]) -> str:
        """The only place a conversation's tier is decided. A visitor with no
        active grant — including every anonymous/public visitor — gets
        'public'. Never accept a tier name from the request body.

        Bug found while building the frontend (session 12): the twin's own
        owner, chatting with their own twin, was getting the same 'public'
        tier as a stranger — resolve_access_tier only ever checked
        AccessGrant, with no special case for the owner at all, despite
        `Conversation.is_owner_session` existing in the schema specifically
        for this and never once being set True anywhere. Fixed here: the
        owner always resolves to the twin's highest-privilege tier, which by
        the seeding convention in TwinService is 'private'."""
        if visitor_id and visitor_id == twin.owner_id:
            return "private"
        if visitor_id:
            now = datetime.now(timezone.utc)
            twin_id = twin.id
            grant = (
                self.db.query(AccessGrant)
                .filter(
                    AccessGrant.twin_id == twin_id,
                    AccessGrant.visitor_id == visitor_id,
                    AccessGrant.revoked_at.is_(None),
                )
                .filter(or_(AccessGrant.expires_at.is_(None), AccessGrant.expires_at > now))
                .order_by(AccessGrant.granted_at.desc())
                .first()
            )
            if grant:
                return grant.tier_name
        return "public"

    def allowed_visibilities_for_tier(self, twin_id: str, tier_name: str) -> List[str]:
        tier = (
            self.db.query(AccessTier)
            .filter(AccessTier.twin_id == twin_id, AccessTier.tier_name == tier_name)
            .first()
        )
        return tier.visibility_list if tier else ["public"]

    def get_or_create_conversation(
        self,
        twin: Twin,
        conversation_id: Optional[str],
        visitor_id: Optional[str],
        visitor_name: str,
        channel: str = "text",
    ) -> Conversation:
        if conversation_id:
            existing = (
                self.db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.twin_id == twin.id)
                .first()
            )
            if existing:
                return existing

        # Tier is resolved and snapshotted once, here, at conversation creation
        # — later revoking a grant doesn't retroactively change what an
        # already-open conversation can see, by design (see models.py).
        tier_name = self.resolve_access_tier(twin, visitor_id)
        conv = Conversation(
            twin_id=twin.id,
            visitor_id=visitor_id,
            visitor_name=visitor_name,
            channel=channel,
            access_tier=tier_name,
            is_owner_session=bool(visitor_id and visitor_id == twin.owner_id),
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def list_conversations(self, twin_id: str) -> List[Conversation]:
        """Every conversation this twin has had, newest first — the owner's
        view into what visitors actually asked, not just the escalated
        subset that reaches Knowledge Gaps. No backend-only filtering of the
        owner's own test sessions: `is_owner_session` is returned so the
        frontend can label/filter them, but hiding them server-side would
        just be a surprising omission, not a real privacy boundary (it's the
        owner's own twin)."""
        return (
            self.db.query(Conversation)
            .filter(Conversation.twin_id == twin_id)
            .order_by(Conversation.created_at.desc())
            .all()
        )

    def get_conversation(self, twin_id: str, conversation_id: str) -> Optional[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.twin_id == twin_id)
            .first()
        )

    def _load_history(self, conversation: Conversation) -> List[Any]:
        """Reconstructs prior turns as LangChain messages so the agent has
        real multi-turn context — each call to the graph is stateless on its
        own (no checkpointer configured), so without this every chat() call
        would only ever see the single latest message.

        Windowed to the most recent MAX_HISTORY_MESSAGES turns and each
        turn's content capped (session 22) — a long-running conversation
        would otherwise replay its ENTIRE history into the prompt on every
        single turn, growing without bound. Older turns are dropped, not
        summarized; see backend/config.py for why."""
        recent = conversation.messages[-settings.MAX_HISTORY_MESSAGES:]
        history: List[Any] = []
        for msg in recent:
            if msg.role == "visitor":
                history.append(HumanMessage(content=_cap(msg.content)))
            elif msg.role == "twin":
                history.append(AIMessage(content=_cap(msg.content)))
        return history

    def chat(
        self,
        twin_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        visitor_id: Optional[str] = None,
        visitor_name: str = "Anonymous",
    ) -> Dict[str, Any]:
        # Bugfix (session 20): found live on a real twin — three blank
        # messages in one conversation, each one processed anyway (the agent
        # answered nothing, then escalated with an empty question_text,
        # producing an unanswerable Knowledge Gap). chat.py's ChatRequest
        # validates this for the text endpoint, but voice_chat() calls this
        # method directly with whatever ASR returns (silence/unclear audio
        # can transcribe to ""), bypassing that check entirely — enforced
        # here instead, at the one place both paths funnel through.
        if not message.strip():
            raise ValueError("message cannot be empty")

        twin = self.db.query(Twin).filter(Twin.id == twin_id, Twin.is_active.is_(True)).first()
        if not twin:
            raise ValueError(f"Twin {twin_id} not found or inactive")

        conv = self.get_or_create_conversation(twin, conversation_id, visitor_id, visitor_name)
        history = self._load_history(conv)

        visitor_msg = Message(conversation_id=conv.id, role="visitor", content=message)
        self.db.add(visitor_msg)
        self.db.commit()

        allowed_visibilities = self.allowed_visibilities_for_tier(twin_id, conv.access_tier)

        initial_state = {
            "messages": history + [HumanMessage(content=_cap(message))],
            "twin_id": twin.id,
            "visitor_id": visitor_id,
            "allowed_visibilities": allowed_visibilities,
            "persona_prompt": twin.persona_prompt or "",
            "domain": twin.domain,
            "context_documents": [],
            "memory_documents": [],
        }

        start = time.time()
        result = self.graph.invoke(initial_state)
        latency_ms = int((time.time() - start) * 1000)

        answer = result["messages"][-1].content
        sources = [
            {"source_id": doc.get("source_id"), "score": doc.get("score")}
            for doc in result.get("context_documents", [])
        ]

        # Phase 4: these now come from the agent's own grading (generate_node's
        # structured `grounded` output), not a hardcoded placeholder.
        policy_decision = result.get("policy_decision", "answer")
        confidence_score = result.get("confidence_score")

        twin_msg = Message(
            conversation_id=conv.id,
            role="twin",
            content=answer,
            policy_decision=policy_decision,
            confidence_score=confidence_score,
            latency_ms=latency_ms,
            sources_json=sources,
        )
        self.db.add(twin_msg)
        self.db.commit()

        # The twin couldn't ground an answer -- queue it for the owner instead
        # of just letting the visitor hit a dead end. This is the trigger logic
        # the knowledge_gaps table (§8) was built for back in session 4 but had
        # no live caller for until now.
        if policy_decision == "escalate":
            gap = KnowledgeGap(
                twin_id=twin_id,
                conversation_id=conv.id,
                question_message_id=visitor_msg.id,
                question_text=message,
            )
            self.db.add(gap)
            self.db.commit()

        return {
            "conversation_id": conv.id,
            "answer": answer,
            "sources": sources,
            "latency_ms": latency_ms,
        }

    def chat_stream(
        self,
        twin_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        visitor_id: Optional[str] = None,
        visitor_name: str = "Anonymous",
    ) -> Iterator[Any]:
        """Same contract and persistence as chat(), but yields the answer
        token-by-token instead of blocking for the full text — see
        generate_stream's docstring (backend/agent/nodes.py) for why
        grounding detection works differently on this path. Yields plain str
        chunks as they arrive, then exactly one final dict (distinguishable
        by isinstance) with conversation_id/sources/latency_ms once the full
        answer is known and persisted — mirroring chat()'s return shape
        minus `answer`, since the caller already has it from the streamed
        chunks."""
        if not message.strip():
            raise ValueError("message cannot be empty")

        twin = self.db.query(Twin).filter(Twin.id == twin_id, Twin.is_active.is_(True)).first()
        if not twin:
            raise ValueError(f"Twin {twin_id} not found or inactive")

        conv = self.get_or_create_conversation(twin, conversation_id, visitor_id, visitor_name)
        history = self._load_history(conv)

        visitor_msg = Message(conversation_id=conv.id, role="visitor", content=message)
        self.db.add(visitor_msg)
        self.db.commit()

        allowed_visibilities = self.allowed_visibilities_for_tier(twin_id, conv.access_tier)

        initial_state = {
            "messages": history + [HumanMessage(content=_cap(message))],
            "twin_id": twin.id,
            "visitor_id": visitor_id,
            "allowed_visibilities": allowed_visibilities,
            "persona_prompt": twin.persona_prompt or "",
            "domain": twin.domain,
            "context_documents": [],
            "memory_documents": [],
        }

        start = time.time()
        # Retrieval/grading/rewrite run as plain function calls (not through
        # the compiled graph) so the final generation step can stream —
        # graph.invoke() would block until generate_node finishes.
        state = prepare_retrieval(initial_state)

        final_meta: Dict[str, Any] = {}
        for piece in generate_stream(state):
            if isinstance(piece, dict):
                final_meta = piece
            else:
                yield piece

        latency_ms = int((time.time() - start) * 1000)
        answer = final_meta.get("answer", "")
        policy_decision = final_meta.get("policy_decision", "answer")
        confidence_score = final_meta.get("confidence_score")

        sources = [
            {"source_id": doc.get("source_id"), "score": doc.get("score")}
            for doc in state.get("context_documents", [])
        ]

        twin_msg = Message(
            conversation_id=conv.id,
            role="twin",
            content=answer,
            policy_decision=policy_decision,
            confidence_score=confidence_score,
            latency_ms=latency_ms,
            sources_json=sources,
        )
        self.db.add(twin_msg)
        self.db.commit()

        if policy_decision == "escalate":
            gap = KnowledgeGap(
                twin_id=twin_id,
                conversation_id=conv.id,
                question_message_id=visitor_msg.id,
                question_text=message,
            )
            self.db.add(gap)
            self.db.commit()

        yield {
            "conversation_id": conv.id,
            "sources": sources,
            "latency_ms": latency_ms,
        }
