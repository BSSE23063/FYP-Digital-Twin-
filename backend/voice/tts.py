"""
Text-to-speech via Pocket TTS, CPU-only.

The preset-voice model measured 0.75-0.98x realtime on this hardware
(CLAUDE.md §9.3) — slower than live speech, accepted for now per the user's
call. Real voice cloning is confirmed working as of session 11 (the user
provided a recording + set up HF_TOKEN per Kyutai's terms at
huggingface.co/kyutai/pocket-tts) — but the cloning-capable model itself is a
heavier checkpoint and measured notably slower again: ~0.3x realtime, roughly
3x slower than the preset-voice model. That's a real cost of cloning
specifically, not just Pocket TTS in general — factor it in before assuming
speed work later will land this anywhere close to live-call territory.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from pocket_tts import TTSModel

from backend.config import settings

# huggingface_hub reads HF_TOKEN from the process environment, not from this
# project's pydantic Settings — bridge it here so a .env value actually
# reaches it when the app is started directly (e.g. via uvicorn), not just
# when a script calls load_dotenv() itself first.
if settings.HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)


@lru_cache(maxsize=1)
def get_tts_model() -> TTSModel:
    return TTSModel.load_model(language=settings.TTS_LANGUAGE, quantize=settings.TTS_QUANTIZE)


@lru_cache(maxsize=8)
def _voice_state_for(voice_ref: str):
    """Cached per voice reference — building this state is a one-time cost
    per voice (measured ~66s for a real cloned voice from a fresh recording),
    not something to redo on every utterance."""
    return get_tts_model().get_state_for_audio_prompt(voice_ref)


def _default_voice_ref() -> str:
    if settings.TTS_VOICE_SAMPLE_PATH and Path(settings.TTS_VOICE_SAMPLE_PATH).exists():
        return settings.TTS_VOICE_SAMPLE_PATH
    return settings.TTS_DEFAULT_VOICE


def synthesize(text: str, voice_ref: Optional[str] = None) -> Tuple[np.ndarray, int]:
    """Returns (samples: float32 mono array, sample_rate). If voice_ref isn't
    given, uses the real cloned voice at settings.TTS_VOICE_SAMPLE_PATH when
    that file exists, else falls back to the catalog voice
    settings.TTS_DEFAULT_VOICE."""
    model = get_tts_model()
    state = _voice_state_for(voice_ref or _default_voice_ref())
    audio = model.generate_audio(state, text_to_generate=text, copy_state=True)
    samples = audio.detach().cpu().numpy().squeeze().astype(np.float32)
    return samples, model.sample_rate
