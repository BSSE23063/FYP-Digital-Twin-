"""
Audio decoding, resampling, and encoding helpers.

Two-layer decode: `soundfile` first (fast, handles WAV/OGG/FLAC cleanly), then
a PyAV fallback for anything soundfile can't open — concretely needed for the
React frontend's browser-recorded audio (session 13), which Chrome's
MediaRecorder produces as webm/opus by default and soundfile cannot read at
all (confirmed: `LibsndfileError: Format not recognised`). The PyAV fallback
is a direct, careful decode (resampled to mono float with `av.AudioResampler`)
— NOT the same call path as faster-whisper's own broken `decode_audio()`
(session 10's bug: it passes `metadata_errors=` to PyAV, which the installed
PyAV 19.0.1 doesn't accept). This module never calls that path; it decodes
itself and always hands faster-whisper a raw array, bypassing the bug
entirely regardless of input format.
"""
import wave
from pathlib import Path
from typing import Tuple, Union

import av
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

WHISPER_SAMPLE_RATE = 16000


def _load_with_av(path: Union[str, Path]) -> Tuple[np.ndarray, int]:
    """Broad-format fallback (webm/opus, mp4/aac, mp3, ...) via PyAV/ffmpeg."""
    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout="mono")
        chunks = []
        sample_rate = stream.rate
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                chunks.append(resampled.to_ndarray().reshape(-1))
                sample_rate = resampled.sample_rate
    finally:
        container.close()
    if not chunks:
        return np.zeros(0, dtype=np.float32), sample_rate
    return np.concatenate(chunks).astype(np.float32), sample_rate


def load_audio_as_float32(path: Union[str, Path]) -> Tuple[np.ndarray, int]:
    """Reads an audio file (WAV/OGG/FLAC/webm/mp3/mp4/...) into a float32
    mono array in [-1, 1] and its native sample rate."""
    try:
        samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        return samples.astype(np.float32), sample_rate
    except Exception:
        return _load_with_av(path)


# Old name kept as an alias — several modules already import this.
load_wav_as_float32 = load_audio_as_float32


def resample_to_16k(samples: np.ndarray, source_rate: int) -> np.ndarray:
    """Whisper models are trained on 16kHz mono audio. Passing a raw array
    (instead of a file path) to faster-whisper skips whatever resampling it
    would otherwise do internally, so this has to happen explicitly — matters
    concretely here because Pocket TTS outputs 24kHz, not 16kHz, so a
    synthesized reply fed back in for a round-trip test would otherwise be
    silently mis-pitched going into Whisper."""
    if source_rate == WHISPER_SAMPLE_RATE:
        return samples
    gcd = np.gcd(source_rate, WHISPER_SAMPLE_RATE)
    up, down = WHISPER_SAMPLE_RATE // gcd, source_rate // gcd
    return resample_poly(samples, up, down).astype(np.float32)


def save_wav(path: Union[str, Path], samples: np.ndarray, sample_rate: int) -> None:
    """Writes a float32 [-1, 1] array out as 16-bit PCM WAV. Kept on the
    stdlib `wave` module (not soundfile) deliberately — this is the one
    format we always produce ourselves, so there's nothing to decode, and it
    avoids depending on soundfile's write-side codecs for a plain WAV."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm.tobytes())
