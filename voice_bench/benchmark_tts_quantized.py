import time

from pocket_tts import TTSModel

print("Loading model WITH int8 quantization...")
t0 = time.time()
tts_model = TTSModel.load_model(language="english", quantize=True)
print(f"Model loaded in {time.time() - t0:.2f}s\n")

state = tts_model.get_state_for_audio_prompt("alba")

sentences = [
    "Hi there, I'm Umair's digital twin.",
    "I'm a final year student building a RAG platform.",
    "Let me know if you have any other questions about my background or my projects.",
]

print("--- Steady-state per-utterance generation (quantized) ---")
for s in sentences:
    t0 = time.time()
    audio = tts_model.generate_audio(state, text_to_generate=s, copy_state=True)
    gen_s = time.time() - t0
    audio_s = audio.shape[-1] / tts_model.sample_rate
    print(f"audio={audio_s:.2f}s, generated in {gen_s:.2f}s, realtime_factor={audio_s/gen_s:.2f}x")
