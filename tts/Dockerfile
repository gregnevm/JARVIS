# --- Stage 1: український reference clip для XTTS voice cloning (piper, CPU) ---
FROM python:3.11-slim AS ref

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "piper-tts>=1.2"

RUN mkdir -p /voices && \
    curl -fL -o /voices/uk.onnx \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium.onnx" && \
    curl -fL -o /voices/uk.onnx.json \
      "https://huggingface.co/rhasspy/piper-voices/resolve/main/uk/uk_UA/ukrainian_tts/medium/uk_UA-ukrainian_tts-medium.onnx.json"

RUN printf '%s\n' \
    "Привіт! Я Jarvis, твій голосовий асистент. Радий тебе чути." | \
    piper -m /voices/uk.onnx -f /voices/reference.wav

# --- Stage 2: XTTS v2 runtime (GPU, PyTorch CUDA) ---
FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    COQUI_TOS_AGREED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/voices
COPY --from=ref /voices/reference.wav /app/voices/reference.wav

COPY app ./app

EXPOSE 8300
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300"]
