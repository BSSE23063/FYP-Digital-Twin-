"""
Speech-to-text via faster-whisper, CPU-only.

Latency here was never conclusively benchmarked this session (the download
got stuck — see CLAUDE.md §9.3) — treat it as unmeasured, not fast, until
actually timed end to end.
"""
from functools import lru_cache
from pathlib import Path
from typing import Union

from faster_whisper import WhisperModel

from backend.config import settings
from backend.voice.audio_utils import load_wav_as_float32, resample_to_16k


@lru_cache(maxsize=1)
def get_asr_model() -> WhisperModel:
    return WhisperModel(settings.ASR_MODEL_SIZE, device="cpu", compute_type="int8")


def transcribe_file(path: Union[str, Path]) -> str:
    """Decodes and resamples the WAV itself before handing raw samples to
    faster-whisper, bypassing its own (broken on this machine) decode_audio()
    path entirely."""
    samples, source_rate = load_wav_as_float32(path)
    samples = resample_to_16k(samples, source_rate)
    segments, _ = get_asr_model().transcribe(samples, beam_size=1)
    return " ".join(segment.text for segment in segments).strip()
