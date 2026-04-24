"""LiquipediaClient tests — UA header, cache use, rate-limit consultation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from overpass.config import LiquipediaConfig
from overpass.liquipedia.client import LiquipediaClient


def _make_client(tmp_path: Path, transport: httpx.MockTransport) -> LiquipediaClient:
    cfg = LiquipediaConfig(
        cache_dir=str(tmp_path),
        cache_ttl_minutes=60,
        min_request_interval_seconds=0.0,  # speed up tests
    )
    return LiquipediaClient.from_config(cfg, transport=transport)


def test_parse_page_sends_user_agent_header(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ua"] = request.headers["user-agent"]
        return httpx.Response(
            200,
            json={"parse": {"text": {"*": "<div>hello</div>"}}},
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        body = asyncio.run(client.parse_page("Some_Page"))
    finally:
        asyncio.run(client.close())
    assert body == "<div>hello</div>"
    assert "overpass/" in captured["ua"]
    assert "63104033+lindhammer@users.noreply.github.com" in captured["ua"]


def test_parse_page_caches_response(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={"parse": {"text": {"*": "<div>cached</div>"}}},
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        a = asyncio.run(client.parse_page("Page"))
        b = asyncio.run(client.parse_page("Page"))
    finally:
        asyncio.run(client.close())
    assert a == b == "<div>cached</div>"
    assert calls["n"] == 1


def test_search_page_titles_returns_titles_array(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=["BetBoom RUSH B Summit Season 3", ["Title A", "Title B"], ["", ""], ["", ""]],
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        titles = asyncio.run(client.search_page_titles("BetBoom"))
    finally:
        asyncio.run(client.close())
    assert titles == ["Title A", "Title B"]


def test_search_page_titles_falls_back_to_full_text_search(tmp_path: Path) -> None:
    actions: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        actions.append(action)
        if action == "opensearch":
            return httpx.Response(
                200,
                json=["CCT Global Finals 2026", [], [], []],
            )
        return httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {"title": "A-Tier Tournaments"},
                        {"title": "CCT/Season 3/Global Finals"},
                    ]
                }
            },
        )

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        titles = asyncio.run(client.search_page_titles("CCT Global Finals 2026"))
    finally:
        asyncio.run(client.close())

    assert actions == ["opensearch", "query"]
    assert titles == ["A-Tier Tournaments", "CCT/Season 3/Global Finals"]


def test_parse_page_returns_empty_string_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        body = asyncio.run(client.parse_page("Page"))
    finally:
        asyncio.run(client.close())
    assert body == ""


def test_search_returns_empty_list_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _make_client(tmp_path, httpx.MockTransport(handler))
    try:
        titles = asyncio.run(client.search_page_titles("anything"))
    finally:
        asyncio.run(client.close())
    assert titles == []
