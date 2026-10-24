"""
Voice pipeline smoke test: synthesize a spoken QUESTION (standing in for a
real microphone recording, since none exists yet), run it through the full
audio -> ASR -> ConversationService.chat() -> TTS -> audio round trip, and
check the transcription and the answer are actually correct -- not just that
the code runs without raising.

Backend-only capability (CLAUDE.md §9): no live call, no WebRTC. Real-world
voice cloning needs a recorded sample of an actual person + HF_TOKEN set up
(see backend/voice/tts.py) -- this test uses the built-in catalog voice for
both the fake "question" audio and the twin's reply.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import uuid

from dotenv import load_dotenv
load_dotenv()

from backend.db.session import SessionLocal
from backend.db.models import Twin, User
from backend.ingestion.pipeline import IngestionPipeline
from backend.voice.pipeline import voice_chat
from backend.voice.tts import synthesize
from backend.voice.audio_utils import save_wav


def run_test():
    db = SessionLocal()
    try:
        owner = User(email=f"voice-test-{uuid.uuid4().hex[:6]}@t2rag.local", display_name="Voice Test Owner")
        db.add(owner)
        db.commit()
        db.refresh(owner)

        twin = Twin(owner_id=owner.id, slug=f"voice-test-{uuid.uuid4().hex[:6]}", name="Voice Test Twin",
                    domain="Umair's FYP project", persona_prompt="You are a concise, helpful assistant for Umair.")
        db.add(twin)
        db.commit()
        db.refresh(twin)
        print(f"[OK] test twin created: {twin.slug}")

        IngestionPipeline(db).ingest_text(
            twin_id=twin.id, name="bio.txt", source_type="manual", visibility="public",
            text="Umair is a final-year CS student building T2-RAG. The project uses "
                 "PostgreSQL, Qdrant, Groq, and FastAPI.",
        )
        print("[OK] knowledge ingested")

        question_text = "What technologies does Umair use for his project?"
        print(f"\n--- Synthesizing a spoken question (stand-in for a mic recording): {question_text!r} ---")
        samples, sample_rate = synthesize(question_text)
        save_wav("./voice_bench/question.wav", samples, sample_rate)
        print(f"[OK] question audio written ({len(samples)/sample_rate:.2f}s)")

        print("\n--- Running the full voice round trip ---")
        result = voice_chat(
            db=db,
            twin_id=twin.id,
            input_audio_path="./voice_bench/question.wav",
            output_audio_path="./voice_bench/answer.wav",
        )

        print(f"\nTranscribed question: {result['question_text']!r}")
        assert "technolog" in result["question_text"].lower() or "umair" in result["question_text"].lower(), \
            f"ASR transcription looks wrong: {result['question_text']!r}"
        print("[OK] transcription looks right")

        print(f"Answer: {result['answer']!r}")
        assert any(k in result["answer"].lower() for k in ("postgres", "qdrant", "groq", "fastapi")), \
            f"answer doesn't mention any known fact: {result['answer']!r}"
        print("[OK] answer is grounded in the ingested knowledge")

        print(f"Output audio: {result['output_audio_path']}")
        print(f"Timing (ms): {result['timing_ms']}")

        print("\nVoice pipeline round-trip passed.")
    finally:
        db.close()


if __name__ == "__main__":
    run_test()
