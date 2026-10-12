"""
Chat API endpoint for conversing with a Digital Twin.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.conversation_service import ConversationService

router = APIRouter(prefix="/twins/{twin_id}/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    visitor_name: Optional[str] = "Anonymous"
    access_tier: Optional[str] = "public"


class SourceSnippet(BaseModel):
    chunk_id: str
    similarity: float
    snippet: str


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    policy_decision: str
    confidence_score: float
    sources: List[Dict[str, Any]]
    latency_ms: int


@router.post("", response_model=ChatResponse)
def chat_with_twin(
    twin_id: str,
    payload: ChatRequest,
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    try:
        response = service.chat(
            twin_id=twin_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            visitor_name=payload.visitor_name or "Anonymous",
            access_tier=payload.access_tier or "public",
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

