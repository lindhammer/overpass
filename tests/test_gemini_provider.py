from __future__ import annotations

import asyncio

from overpass.editorial import gemini as gemini_module
from overpass.editorial.gemini import GeminiProvider


class _FakeGeminiResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Daily briefing text"},
                        ],
                    },
                }
            ],
        }


def test_gemini_provider_sends_api_key_header_not_query_param(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            captured["params"] = kwargs.get("params")
            captured["json"] = kwargs.get("json")
            return _FakeGeminiResponse()

    monkeypatch.setattr(gemini_module.httpx, "AsyncClient", FakeAsyncClient)

    text = asyncio.run(GeminiProvider("gemini-test", "secret-key").generate("prompt"))

    assert text == "Daily briefing text"
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-test:generateContent"
    )
    assert captured["headers"] == {"x-goog-api-key": "secret-key"}
    assert captured["params"] in (None, {})
    assert "secret-key" not in str(captured["url"])
