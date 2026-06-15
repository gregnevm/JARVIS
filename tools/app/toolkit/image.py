"""Image OCR, vision describe, and image generation."""
from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings


def ocr_image(path: str, lang: str = "ukr+eng") -> str:
    p = Path(path)
    if not p.is_file():
        return f"Файл не знайдено: {path}"
    try:
        import pytesseract
        from PIL import Image
    except Exception:  # noqa: BLE001
        return "OCR недоступний (немає pytesseract/Pillow або системного tesseract)."
    try:
        with Image.open(str(p)) as img:
            text = pytesseract.image_to_string(img, lang=lang)
    except Exception as exc:  # noqa: BLE001
        try:
            with Image.open(str(p)) as img:
                text = pytesseract.image_to_string(img)
        except Exception:  # noqa: BLE001
            return f"Помилка OCR: {exc}"
    text = (text or "").strip()
    return text[: settings.fetch_max_chars] or "На зображенні не знайдено тексту."


async def describe_image(path: str, question: str = "") -> str:
    if not settings.ollama_model_vision:
        return "Опис зображень вимкнено (не задано OLLAMA_MODEL_VISION)."
    p = Path(path)
    if not p.is_file():
        return f"Файл не знайдено: {path}"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    except OSError as exc:
        return f"Не вдалося прочитати зображення: {exc}"
    from ..ollama_vram import vision_chat_payload, vision_vram_scope

    prompt = question.strip() or "Опиши детально, що зображено. Якщо є текст — наведи його."
    payload = vision_chat_payload(prompt, b64)
    try:
        async with vision_vram_scope():
            async with httpx.AsyncClient(timeout=settings.ollama_timeout) as cli:
                resp = await cli.post(
                    f"{settings.ollama_host.rstrip('/')}/api/chat", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return f"Vision-модель недоступна: {exc}"
    msg = data.get("message") or {}
    text = str(msg.get("content") or "").strip()
    return text[: settings.fetch_max_chars] or "Vision-модель не дала опису."


def image_gen_enabled() -> bool:
    """Чи доступний інструмент generate_image (схема + dispatch)."""
    url = (settings.image_gen_url or "").strip().lower()
    if url in ("ollama", "ollama://"):
        return bool((settings.image_gen_model or "").strip())
    if url in ("pollinations", "pollinations.ai"):
        return True
    if url in ("horde", "aihorde", "stablehorde"):
        return True
    return bool(url)


def _image_gen_backend() -> str:
    url = (settings.image_gen_url or "").strip().lower()
    if url in ("ollama", "ollama://"):
        return "ollama"
    if url in ("pollinations", "pollinations.ai"):
        return "pollinations"
    if url in ("horde", "aihorde", "stablehorde"):
        return "horde"
    if "/v1" in url:
        return "openai"
    return "a1111"


def _save_generated_png(img_bytes: bytes) -> Path | str:
    out_dir = Path(settings.data_dir) / "uploads"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"gen_{int(time.time())}.png"
    out.write_bytes(img_bytes)
    return out


_HORDE_API = "https://aihorde.net/api/v2"
_HORDE_AGENT = "JARVIS:1.0:jarvis-telegram"


def _horde_headers() -> dict[str, str]:
    return {
        "apikey": (settings.horde_api_key or "0000000000").strip(),
        "Client-Agent": _HORDE_AGENT,
    }


async def _generate_image_horde(prompt: str) -> bytes | None:
    models = ["AlbedoBase XL (SDXL)", "Deliberate", "DreamShaper"]
    if (settings.image_gen_model or "").strip():
        models = [settings.image_gen_model.strip()]
    body = {
        "prompt": prompt,
        "params": {"width": 512, "height": 512, "steps": 22, "n": 1},
        "models": models,
        "r2": True,
        "nsfw": False,
        "censor_nsfw": True,
    }
    deadline = time.monotonic() + settings.image_gen_timeout
    async with httpx.AsyncClient(timeout=60.0) as cli:
        resp = await cli.post(
            f"{_HORDE_API}/generate/async",
            json=body,
            headers=_horde_headers(),
        )
        resp.raise_for_status()
        job_id = resp.json().get("id")
        if not job_id:
            return None
        while time.monotonic() < deadline:
            chk = await cli.get(
                f"{_HORDE_API}/generate/check/{job_id}",
                headers=_horde_headers(),
            )
            chk.raise_for_status()
            if chk.json().get("done"):
                break
            await asyncio.sleep(2.0)
        st = await cli.get(
            f"{_HORDE_API}/generate/status/{job_id}",
            headers=_horde_headers(),
        )
        st.raise_for_status()
        gens = st.json().get("generations") or []
        if not gens:
            return None
        gen = gens[0]
        img_url = gen.get("img")
        if img_url:
            img_resp = await cli.get(str(img_url))
            img_resp.raise_for_status()
            return img_resp.content
        raw_b64 = gen.get("base64") or gen.get("imgdata")
        if raw_b64:
            return base64.b64decode(raw_b64)
    return None


async def _generate_image_pollinations(prompt: str) -> bytes | None:
    from urllib.parse import quote

    url = (
        "https://image.pollinations.ai/prompt/"
        f"{quote(prompt)}?width=768&height=768&nologo=true"
    )
    async with httpx.AsyncClient(timeout=settings.image_gen_timeout, follow_redirects=True) as cli:
        resp = await cli.get(url)
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        if "image" not in ctype:
            return None
        return resp.content


async def _generate_image_ollama(prompt: str) -> bytes | None:
    model = (settings.image_gen_model or "x/z-image-turbo").strip()
    url = f"{settings.ollama_host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    async with httpx.AsyncClient(timeout=settings.image_gen_timeout) as cli:
        resp = await cli.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("image")
    if isinstance(raw, str) and raw:
        return base64.b64decode(raw)
    text = resp.text.strip()
    if text:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw = chunk.get("image")
            if isinstance(raw, str) and raw:
                return base64.b64decode(raw)
    return None


async def generate_image(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not image_gen_enabled():
        return (
            "Генерація зображень вимкнена. Локально: IMAGE_GEN_URL=http://host.docker.internal:7860 "
            "і .\\scripts\\start_sd_forge.ps1"
        )
    if not prompt:
        return "Порожній опис для генерації."
    from ..image_gen_lock import release, try_acquire

    if not await try_acquire():
        return (
            "Генерація зображень зараз зайнята (інший запит). "
            "Спробуй через хвилину — так Ollama не втрачає VRAM."
        )
    backend = _image_gen_backend()
    try:
        img_bytes: bytes | None = None
        try:
            async with httpx.AsyncClient(timeout=settings.image_gen_timeout) as cli:
                if backend == "ollama":
                    img_bytes = await _generate_image_ollama(prompt)
                elif backend == "pollinations":
                    img_bytes = await _generate_image_pollinations(prompt)
                elif backend == "horde":
                    img_bytes = await _generate_image_horde(prompt)
                elif backend == "openai":
                    base = settings.image_gen_url.rstrip("/")
                    body: dict[str, Any] = {"prompt": prompt, "n": 1, "response_format": "b64_json"}
                    if settings.image_gen_model:
                        body["model"] = settings.image_gen_model
                    resp = await cli.post(f"{base}/images/generations", json=body)
                    resp.raise_for_status()
                    item = (resp.json().get("data") or [{}])[0]
                    raw = item.get("b64_json")
                    img_bytes = base64.b64decode(raw) if raw else None
                else:
                    base = settings.image_gen_url.rstrip("/")
                    body = {
                        "prompt": prompt,
                        "negative_prompt": "blurry, low quality, watermark, text",
                        "steps": 22,
                        "width": 512,
                        "height": 512,
                        "cfg_scale": 7.0,
                        "sampler_name": "Euler a",
                    }
                    ckpt = (settings.image_gen_model or "").strip()
                    if ckpt:
                        body["override_settings"] = {"sd_model_checkpoint": ckpt}
                    resp = await cli.post(f"{base}/sdapi/v1/txt2img", json=body)
                    resp.raise_for_status()
                    images = resp.json().get("images") or []
                    img_bytes = base64.b64decode(images[0]) if images else None
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300]
            except Exception:  # noqa: BLE001
                pass
            if backend == "ollama" and exc.response.status_code == 404:
                return (
                    f"Модель Ollama для зображень не знайдена ({settings.image_gen_model}). "
                    f"На хості: ollama pull {settings.image_gen_model or 'x/flux2-klein:4b'}"
                )
            if backend == "ollama":
                err = detail or str(exc)
                if (
                    exc.response.status_code == 500
                    or "only work on macOS" in err
                    or "mlx" in err.lower()
                    or "image generation not available" in err.lower()
                    or "GiB" in err
                ):
                    return (
                        "Ollama image gen на Windows ще не працює (потрібен Forge). "
                        "На хості: .\\scripts\\setup_sd_forge.ps1 → .\\scripts\\start_sd_forge.ps1. "
                        "У .env: IMAGE_GEN_URL=http://host.docker.internal:7860"
                    )
            return f"Не вдалося згенерувати зображення: {exc} {detail}".strip()
        except httpx.ConnectError:
            if backend == "a1111":
                return (
                    "Локальний Forge/SD не запущений. На хості: .\\scripts\\start_sd_forge.ps1 "
                    "(перший раз: .\\scripts\\setup_sd_forge.ps1). IMAGE_GEN_URL=http://host.docker.internal:7860"
                )
            return f"Не вдалося згенерувати зображення: сервіс недоступний ({settings.image_gen_url})"
        except (httpx.HTTPError, ValueError) as exc:
            return f"Не вдалося згенерувати зображення: {exc}"
        if not img_bytes:
            return "Бекенд генерації не повернув зображення."
        try:
            out = _save_generated_png(img_bytes)
        except OSError as exc:
            return f"Не вдалося зберегти зображення: {exc}"
        return f"Зображення згенеровано. Поверни його користувачу: [[photo:{out}]]"
    finally:
        await release()
