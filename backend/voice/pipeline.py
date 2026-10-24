"""
The voice round-trip: audio in -> transcribe -> ConversationService.chat() ->
synthesize -> audio out.

Backend-only capability, deliberately — no WebRTC/live call yet (that's a
separate, larger frontend+transport build; this is the thing to get correct
and measure before wrapping it in anything real-time). Reuses
ConversationService as-is, so a voice turn gets the exact same grounding,
access-tier resolution, and audit trail as a text turn — this module only
adds the audio<->text boundary around it, not a parallel chat path.
"""
import time
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.services.conversation_service import ConversationService
from backend.voice.asr import transcribe_file
from backend.voice.audio_utils import save_wav
from backend.voice.tts import synthesize


def voice_chat(
    db: Session,
    twin_id: str,
    input_audio_path: str,
    output_audio_path: str,
    conversation_id: Optional[str] = None,
    visitor_id: Optional[str] = None,
    visitor_name: str = "Anonymous",
    voice_ref: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.time()
    question_text = transcribe_file(input_audio_path)
    asr_ms = int((time.time() - t0) * 1000)

    t0 = time.time()
    result = ConversationService(db).chat(
        twin_id=twin_id,
        message=question_text,
        conversation_id=conversation_id,
        visitor_id=visitor_id,
        visitor_name=visitor_name,
    )
    chat_ms = int((time.time() - t0) * 1000)

    t0 = time.time()
    samples, sample_rate = synthesize(result["answer"], voice_ref=voice_ref)
    save_wav(output_audio_path, samples, sample_rate)
    tts_ms = int((time.time() - t0) * 1000)

    return {
        **result,
        "question_text": question_text,
        "output_audio_path": output_audio_path,
        "timing_ms": {"asr": asr_ms, "chat": chat_ms, "tts": tts_ms, "total": asr_ms + chat_ms + tts_ms},
    }
