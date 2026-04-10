"""Gemini LLM provider – uses the REST API directly via httpx."""

from __future__ import annotations

import logging

import httpx

from overpass.editorial.base import BaseLLMProvider

logger = logging.getLogger("overpass.editorial.gemini")

_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider (REST, no SDK)."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    async def generate(self, prompt: str, system: str | None = None) -> str:
        url = _API_URL.format(model=self.model)

        contents: list[dict] = [{"role": "user", "parts": [{"text": prompt}]}]

        body: dict = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                params={"key": self._api_key},
                json=body,
            )
            resp.raise_for_status()

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            logger.error("Unexpected Gemini response structure: %s", data)
            raise RuntimeError("Failed to parse Gemini response") from exc
