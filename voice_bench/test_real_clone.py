"""
One-off test: does voice cloning from the user's real recording actually work
now that HF_TOKEN is set? Not part of the application -- scratch script.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

import os
from backend.config import settings
if settings.HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)
    print(f"HF_TOKEN loaded from .env, length={len(settings.HF_TOKEN)}")
else:
    print("WARNING: HF_TOKEN is empty in settings!")

from pocket_tts import TTSModel

VOICE_FILE = r"C:\Users\umairs\Downloads\fyp_audio testing.ogg"

print("\nLoading TTS model (voice-cloning-capable weights this time)...")
t0 = time.time()
model = TTSModel.load_model(language="english", quantize=False)
print(f"Model loaded in {time.time() - t0:.2f}s")

print(f"\nBuilding voice state by cloning: {VOICE_FILE}")
t0 = time.time()
state = model.get_state_for_audio_prompt(VOICE_FILE)
print(f"Clone setup took {time.time() - t0:.2f}s")

print("\nGenerating a test sentence in the cloned voice...")
t0 = time.time()
audio = model.generate_audio(state, text_to_generate="Hi, this is a test of my cloned voice.")
gen_s = time.time() - t0
audio_s = audio.shape[-1] / model.sample_rate
print(f"Generated {audio_s:.2f}s of audio in {gen_s:.2f}s (realtime_factor={audio_s/gen_s:.2f}x)")

import numpy as np
from backend.voice.audio_utils import save_wav
samples = audio.detach().cpu().numpy().squeeze().astype(np.float32)
save_wav("./voice_bench/cloned_voice_test.wav", samples, model.sample_rate)
print("\nSaved: voice_bench/cloned_voice_test.wav")
