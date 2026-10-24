"""
Chat API: converse with a digital twin.

visitor_id is no longer a client-supplied field (that was the hole flagged
since session 7 — a client could claim any visitor_id and inherit that
visitor's access grants). It now comes ONLY from an optional Bearer token: no
token -> anonymous/public visitor (visitor_id=None), a valid token -> that
token's user id. A client can no longer claim to be anyone but who they
actually logged in as.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_optional
from backend.db.models import User
from backend.db.session import get_db
from backend.services.conversation_service import ConversationService

router = APIRouter(prefix="/twins/{twin_id}/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        # Bugfix (session 20): a blank message reached this endpoint for real
        # (not hypothetically — found live, three times in one real
        # conversation) and was processed anyway: the agent generated a
        # reply to nothing, then escalated with an empty question_text,
        # producing a Knowledge Gap with no actual question in it. The
        # current ChatPage.tsx already guards against sending an empty
        # string, so this was reached some other way (a direct API call,
        # or an earlier version of the frontend) — enforced here too, since
        # frontend-only validation can always be bypassed by whoever calls
        # the API directly.
        if not v.strip():
            raise ValueError("message cannot be empty")
        return v


class SourceRef(BaseModel):
    source_id: Optional[str] = None
    score: Optional[float] = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: List[SourceRef]
    latency_ms: int


@router.post("", response_model=ChatResponse)
def chat_with_twin(
    twin_id: str,
    payload: ChatRequest,
    current_visitor: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    try:
        return service.chat(
            twin_id=twin_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            visitor_id=current_visitor.id if current_visitor else None,
            visitor_name=current_visitor.display_name if current_visitor else "Anonymous",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/stream")
def chat_with_twin_stream(
    twin_id: str,
    payload: ChatRequest,
    current_visitor: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Same request shape as the blocking endpoint above, but the response
    body is newline-delimited JSON (application/x-ndjson), one object per
    line, so the client can render the answer as it's generated instead of
    waiting for the full text:
      {"type": "chunk", "text": "..."}   — repeated, the answer as it streams
      {"type": "done", "conversation_id": ..., "sources": [...], "latency_ms": ...}
      {"type": "error", "detail": "..."} — in place of "done", on failure

    A plain HTTPException can't be used for the failure case the way the
    blocking endpoint does: by the time an error inside the generator (e.g.
    "twin not found") is reached, the 200 response has already started
    streaming, so the only way left to report it is as a line in the stream
    itself — the frontend's reader treats a "error" line the same way it
    would an HTTP error from the blocking endpoint.
    """
    service = ConversationService(db)

    def event_stream():
        try:
            for piece in service.chat_stream(
                twin_id=twin_id,
                message=payload.message,
                conversation_id=payload.conversation_id,
                visitor_id=current_visitor.id if current_visitor else None,
                visitor_name=current_visitor.display_name if current_visitor else "Anonymous",
            ):
                if isinstance(piece, dict):
                    yield json.dumps({"type": "done", **piece}) + "\n"
                else:
                    yield json.dumps({"type": "chunk", "text": piece}) + "\n"
        except ValueError as e:
            yield json.dumps({"type": "error", "detail": str(e)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")
