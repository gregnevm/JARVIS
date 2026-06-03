from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LLMInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 512) -> str: ...

    @abstractmethod
    def stream(self, prompt: str, max_tokens: int = 512) -> Iterator[str]: ...
