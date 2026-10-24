"""
One-off benchmark: load Pocket TTS once, then measure steady-state per-utterance
latency (the metric that matters for a live server, not CLI cold-start cost).
Not part of the application -- scratch script for this session's hardware check.
"""
import time

from pocket_tts import TTSModel

print("Loading model (one-time cost for a real server)...")
t0 = time.time()
tts_model = TTSModel.load_model(language="english", quantize=False)
load_s = time.time() - t0
print(f"Model loaded in {load_s:.2f}s\n")

print("NOTE: actual voice-cloning weights are gated behind HF terms acceptance + login")
print("(discovered this run) -- using a built-in catalog voice instead to still measure")
print("raw generation speed, which is architecture-bound, not cloning-specific.\n")
t0 = time.time()
clone_state = tts_model.get_state_for_audio_prompt("alba")
clone_setup_s = time.time() - t0
print(f"Voice state setup: {clone_setup_s:.2f}s (one-time per voice, not per utterance)\n")

sentences = [
    "Hi there, I'm Umair's digital twin.",
    "I'm a final year student building a RAG platform.",
    "Let me know if you have any other questions about my background or my projects.",
]

print("--- Steady-state per-utterance generation (cloned voice) ---")
for s in sentences:
    t0 = time.time()
    audio = tts_model.generate_audio(clone_state, text_to_generate=s, copy_state=True)
    gen_s = time.time() - t0
    audio_s = audio.shape[-1] / tts_model.sample_rate
    print(f"text={s!r}\n  audio={audio_s:.2f}s, generated in {gen_s:.2f}s, "
          f"realtime_factor={audio_s/gen_s:.2f}x (>1.0x = faster than real-time)\n")
