"""Agent toolkit — backward-compatible re-exports."""
from __future__ import annotations

from .dispatch import coerce_args, dispatch
from .image import (
    _generate_image_ollama,
    describe_image,
    generate_image,
    image_gen_enabled,
    ocr_image,
)
from .notes import recall_notes, take_note
from .schemas import TOOL_SCHEMAS, agent_tool_schemas
from .web import _html_to_text, _parse_ddg, calc, code_exec, parse_file, web_fetch, web_search

__all__ = [
    "TOOL_SCHEMAS",
    "_generate_image_ollama",
    "_html_to_text",
    "_parse_ddg",
    "agent_tool_schemas",
    "calc",
    "coerce_args",
    "code_exec",
    "describe_image",
    "dispatch",
    "generate_image",
    "image_gen_enabled",
    "ocr_image",
    "parse_file",
    "recall_notes",
    "take_note",
    "web_fetch",
    "web_search",
]
