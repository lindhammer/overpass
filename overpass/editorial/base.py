"""Abstract base class for LLM providers."""

from __future__ import annotations

import abc


class BaseLLMProvider(abc.ABC):
    """Provider-agnostic interface for text generation."""

    @abc.abstractmethod
    async def generate(self, prompt: str, system: str | None = None) -> str:
        """Send *prompt* to the LLM and return the generated text."""
        ...
