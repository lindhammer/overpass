"""Gemini LLM provider – uses the REST API directly via httpx."""

from __future__ import annotations

import asyncio
import logging

import httpx

from overpass.editorial.base import BaseLLMProvider

logger = logging.getLogger("overpass.editorial.gemini")

_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Gemini's free-tier flash models are frequently hit with 503 UNAVAILABLE
# during demand spikes; a couple of retries with backoff almost always
# recovers the request without falling back to an unannotated digest.
_TRANSIENT_STATUSES = (429, 500, 502, 503, 504)
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = (2.0, 5.0, 12.0)


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
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                resp = await client.post(
                    url,
                    headers={"x-goog-api-key": self._api_key},
                    json=body,
                )
                if resp.status_code in _TRANSIENT_STATUSES and attempt < _MAX_ATTEMPTS:
                    delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Gemini returned %d (attempt %d/%d); retrying in %.1fs",
                        resp.status_code, attempt, _MAX_ATTEMPTS, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                break

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            logger.error("Unexpected Gemini response structure: %s", data)
            raise RuntimeError("Failed to parse Gemini response") from exc
