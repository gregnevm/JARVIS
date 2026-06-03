"""JARVIS TTS service — текст → голосове (OGG/Opus) через piper."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from .config import settings
from .synth import synthesize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jarvis.tts.main")


class TtsRequest(BaseModel):
    text: str


app = FastAPI(title="JARVIS TTS")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tts")
async def tts(req: TtsRequest) -> Response:
    try:
        audio = await synthesize(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — piper/ffmpeg збій → 502, gateway фолбекне на текст
        logger.exception("tts failed")
        raise HTTPException(status_code=502, detail=f"tts failed: {exc}") from exc
    return Response(content=audio, media_type="audio/ogg")


logger.info("TTS up. voice=%s max_chars=%s", settings.voice_path, settings.max_chars)
