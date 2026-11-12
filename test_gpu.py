import os
import site
import time

# CUDA-DLLs aus den nvidia-pip-Paketen auffindbar machen (Windows)
for base in site.getsitepackages() + [site.getusersitepackages()]:
    for sub in ("nvidia\\cublas\\bin", "nvidia\\cudnn\\bin", "nvidia\\cuda_nvrtc\\bin"):
        p = os.path.join(base, sub)
        if os.path.isdir(p):
            os.add_dll_directory(p)
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel

print("Lade large-v3 auf CUDA (float16)...")
t0 = time.time()
model = WhisperModel("large-v3", device="cuda", compute_type="float16")
print(f"Modell geladen in {time.time()-t0:.1f}s")

import numpy as np
sr = 16000
audio = np.zeros(sr * 2, dtype=np.float32)  # 2s Stille
t0 = time.time()
segments, info = model.transcribe(audio, language="de")
segs = list(segments)
print(f"Transkription (Stille) lief durch in {time.time()-t0:.2f}s")
print(f"Erkannte Sprache: {info.language}, Segmente: {len(segs)}")
print("GPU-PIPELINE OK")
