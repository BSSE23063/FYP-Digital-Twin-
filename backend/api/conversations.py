"""
Conversations API (session 19) — the owner's view of what visitors actually
asked their twin. Closes a real gap: before this, the only way to see any
visitor interaction was indirectly, through Knowledge Gaps' escalated
subset — there was no way to browse ordinary, successfully-answered
conversations at all. Owner-only, same as every other twin-management route.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.db.models import User
from backend.db.session import get_db
from backend.services.conversation_service import ConversationService

router = APIRouter(prefix="/twins/{twin_id}/conversations", tags=["conversations"])


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    policy_decision: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: str

    class Config:
        from_attributes = True


class ConversationSummary(BaseModel):
    id: str
    visitor_name: str
    channel: str
    access_tier: str
    is_owner_session: bool
    message_count: int
    last_message_preview: Optional[str] = None
    created_at: str


class ConversationDetail(ConversationSummary):
    messages: List[MessageResponse]


def _summarize(conv) -> ConversationSummary:
    last = conv.messages[-1] if conv.messages else None
    return ConversationSummary(
        id=conv.id,
        visitor_name=conv.visitor_name,
        channel=conv.channel,
        access_tier=conv.access_tier,
        is_owner_session=conv.is_owner_session,
        message_count=len(conv.messages),
        last_message_preview=(last.content[:140] if last else None),
        created_at=conv.created_at.isoformat(),
    )


@router.get("", response_model=List[ConversationSummary])
def list_conversations(
    twin_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    convs = ConversationService(db).list_conversations(twin_id)
    return [_summarize(c) for c in convs]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    twin_id: str,
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    conv = ConversationService(db).get_conversation(twin_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    summary = _summarize(conv)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                policy_decision=m.policy_decision,
                confidence_score=m.confidence_score,
                created_at=m.created_at.isoformat(),
            )
            for m in conv.messages
        ],
    )
