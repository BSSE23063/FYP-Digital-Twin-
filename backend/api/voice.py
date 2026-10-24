"""
Voice chat API: audio in, audio reply out. Runs the exact same
backend/voice/pipeline.voice_chat() round trip the test script exercises —
one request/response turn, no live call/WebRTC (CLAUDE.md §9).

Audio is exchanged as base64 inside JSON rather than a raw audio response
body — simpler for the Streamlit frontend to consume alongside the answer
text, transcription, and timing in one response, at the cost of ~33% size
overhead on a file that's already small (a few hundred KB per turn).
"""
import base64
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user_optional
from backend.db.models import User
from backend.db.session import get_db
from backend.services.twin_service import TwinService
from backend.voice.pipeline import voice_chat

router = APIRouter(prefix="/twins/{twin_id}/voice-chat", tags=["voice"])


class SourceRef(BaseModel):
    source_id: Optional[str] = None
    score: Optional[float] = None


class VoiceChatResponse(BaseModel):
    conversation_id: str
    question_text: str
    answer: str
    sources: List[SourceRef]
    audio_base64: str
    timing_ms: Dict[str, int]


@router.post("", response_model=VoiceChatResponse)
def voice_chat_endpoint(
    twin_id: str,
    audio: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    current_visitor: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    # Plain (non-async) def: ASR + TTS are CPU-bound (no GPU anywhere in this
    # project — CLAUDE.md §9.2), so FastAPI runs this in its threadpool
    # instead of blocking the single event loop.
    suffix = Path(audio.filename or "input.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as in_file:
        in_file.write(audio.file.read())
        input_path = in_file.name
    output_path = input_path + ".reply.wav"

    try:
        # Each twin speaks in its own cloned voice when the owner has uploaded
        # one (session 14); falls back to the global catalog/default voice
        # inside synthesize() otherwise (backend/voice/tts.py).
        voice_ref = TwinService(db).get_voice_sample_path(twin_id)
        result = voice_chat(
            db=db,
            twin_id=twin_id,
            input_audio_path=input_path,
            output_audio_path=output_path,
            conversation_id=conversation_id,
            visitor_id=current_visitor.id if current_visitor else None,
            visitor_name=current_visitor.display_name if current_visitor else "Anonymous",
            voice_ref=voice_ref,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        Path(input_path).unlink(missing_ok=True)

    audio_bytes = Path(output_path).read_bytes()
    Path(output_path).unlink(missing_ok=True)

    return VoiceChatResponse(
        conversation_id=result["conversation_id"],
        question_text=result["question_text"],
        answer=result["answer"],
        sources=result["sources"],
        audio_base64=base64.b64encode(audio_bytes).decode("ascii"),
        timing_ms=result["timing_ms"],
    )
