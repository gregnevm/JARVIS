"""JARVIS TTS service — текст → голосове (OGG/Opus) через Coqui XTTS v2."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .config import settings
from .synth import preload_model, resolved_device, synthesize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("jarvis.tts.main")


class TtsRequest(BaseModel):
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.model_ready = False
    try:
        await asyncio.to_thread(preload_model)
        app.state.model_ready = True
        logger.info(
            "TTS up. engine=xtts_v2 device=%s language=%s max_chars=%s",
            resolved_device(),
            settings.language,
            settings.max_chars,
        )
    except Exception:
        logger.exception("XTTS preload failed — /tts will retry on first request")
    yield


app = FastAPI(title="JARVIS TTS", lifespan=lifespan)


@app.get("/health")
async def health(request: Request) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "engine": "xtts_v2",
        "device": resolved_device(),
        "model_ready": bool(getattr(request.app.state, "model_ready", False)),
    }


@app.post("/tts")
async def tts(req: TtsRequest) -> Response:
    try:
        audio = await synthesize(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        logger.error("tts timed out after %.0fs", settings.synth_timeout)
        raise HTTPException(status_code=504, detail="tts timed out") from exc
    except Exception as exc:  # noqa: BLE001 — synth/ffmpeg збій → 502, gateway фолбекне на текст
        logger.exception("tts failed")
        raise HTTPException(status_code=502, detail=f"tts failed: {exc}") from exc
    return Response(content=audio, media_type="audio/ogg")
