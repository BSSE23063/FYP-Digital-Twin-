"""
Benchmark faster-whisper on CPU. Decodes the WAV manually with the stdlib
`wave` module instead of letting faster-whisper call PyAV -- the installed
PyAV (19.0.1) and faster-whisper (1.2.1) have an incompatible decode_audio()
call (`metadata_errors` kwarg), a real dependency-version-skew bug on this
machine, bypassed here rather than chased further since it's not blocking.
"""
import time
import wave

import numpy as np
from faster_whisper import WhisperModel


def load_wav_as_float32(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as f:
        sample_rate = f.getframerate()
        frames = f.readframes(f.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, sample_rate


audio, sr = load_wav_as_float32("./voice_bench/sample1.wav")
print(f"Loaded {len(audio)/sr:.2f}s of audio at {sr}Hz\n")

for model_size in ("tiny.en", "base.en", "small.en"):
    print(f"=== {model_size} ===")
    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"Model loaded in {time.time() - t0:.2f}s")

    t0 = time.time()
    segments, info = model.transcribe(audio, beam_size=1)
    text = " ".join(seg.text for seg in segments)
    transcribe_s = time.time() - t0
    print(f"Transcribed {info.duration:.2f}s of audio in {transcribe_s:.2f}s "
          f"(realtime_factor={info.duration/transcribe_s:.2f}x)")
    print(f"Text: {text!r}\n")
