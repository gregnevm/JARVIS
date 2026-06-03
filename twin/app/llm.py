"""Re-export LLM layer from jarvis_core (DESIGN §5.2)."""
from jarvis_core.llm import (
    CacheLLM,
    KoboldAdapter,
    LLMInterface,
    LoggingLLM,
    OllamaAdapter,
    RetryLLM,
    StyleLLM,
    build_llm_stack,
)
from jarvis_core.llm.parsers import kobold_token as _kobold_token
from jarvis_core.llm.parsers import ollama_chunk as _ollama_chunk

__all__ = [
    "LLMInterface",
    "KoboldAdapter",
    "OllamaAdapter",
    "LoggingLLM",
    "CacheLLM",
    "RetryLLM",
    "StyleLLM",
    "build_llm_stack",
    "_kobold_token",
    "_ollama_chunk",
]
