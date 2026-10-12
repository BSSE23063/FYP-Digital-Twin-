"""
Conversation service managing chat sessions, LangGraph invocation, and audit logging.
"""

import json
import time
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.db.models import Conversation, Message, Twin, AccessTier
from backend.rag.graph import get_rag_graph


class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.graph = get_rag_graph()

    def get_or_create_conversation(
        self,
        twin_id: str,
        conversation_id: Optional[str] = None,
        visitor_name: str = "Anonymous",
        access_tier: str = "public",
    ) -> Conversation:
        if conversation_id:
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                return conv

        conv = Conversation(
            twin_id=twin_id,
            visitor_name=visitor_name,
            access_tier=access_tier,
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_allowed_visibilities(self, twin_id: str, tier_name: str) -> List[str]:
        tier = (
            self.db.query(AccessTier)
            .filter(AccessTier.twin_id == twin_id, AccessTier.tier_name == tier_name)
            .first()
        )
        if tier and tier.allowed_visibilities:
            return [v.strip() for v in tier.allowed_visibilities.split(",") if v.strip()]
        return ["public"]

    def chat(
        self,
        twin_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        visitor_name: str = "Anonymous",
        access_tier: str = "public",
    ) -> Dict[str, Any]:
        twin = self.db.query(Twin).filter(Twin.id == twin_id).first()
        if not twin:
            raise ValueError(f"Twin {twin_id} not found.")

        conv = self.get_or_create_conversation(
            twin_id=twin_id,
            conversation_id=conversation_id,
            visitor_name=visitor_name,
            access_tier=access_tier,
        )

        # 1. Log visitor message
        user_msg = Message(
            conversation_id=conv.id,
            role="visitor",
            content=message,
        )
        self.db.add(user_msg)
        self.db.commit()

        # 2. Determine allowed visibilities for this session's tier
        allowed_vis = self.get_allowed_visibilities(twin_id, conv.access_tier)

        # 3. Invoke LangGraph RAG
        t_start = time.time()
        initial_state = {
            "question": message,
            "twin_id": twin.id,
            "twin_name": twin.name,
            "persona_prompt": twin.persona_prompt or "",
            "allowed_visibilities": allowed_vis,
            "documents": [],
            "generation": "",
            "policy_decision": "answer",
            "confidence_score": 0.0,
            "sources": [],
            "retry_count": 0,
            "latency_ms": 0,
            "start_time": t_start,
        }

        result = self.graph.invoke(initial_state)
        latency_ms = int((time.time() - t_start) * 1000)

        # 4. Save twin message audit record
        sources_json = json.dumps(result.get("sources", []))
        twin_msg = Message(
            conversation_id=conv.id,
            role="twin",
            content=result.get("generation", ""),
            sources_json=sources_json,
            policy_decision=result.get("policy_decision", "answer"),
            confidence_score=result.get("confidence_score", 0.0),
            latency_ms=latency_ms,
            is_escalated=(result.get("policy_decision") == "escalate"),
        )
        self.db.add(twin_msg)
        self.db.commit()

        return {
            "conversation_id": conv.id,
            "answer": result.get("generation", ""),
            "policy_decision": result.get("policy_decision", "answer"),
            "confidence_score": result.get("confidence_score", 0.0),
            "sources": result.get("sources", []),
            "latency_ms": latency_ms,
        }

