"""Tests for the Nitter-based social collector."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from overpass.collectors.social import NitterSocialCollector
from overpass.config import AppConfig, SocialConfig, SocialHandle

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _build_rss(*, recent: datetime, old: datetime) -> str:
    template = (FIXTURE_DIR / "nitter_s1mpleO.xml").read_text(encoding="utf-8")
    return template.replace("{recent_pub}", format_datetime(recent)).replace(
        "{old_pub}", format_datetime(old)
    )


def _make_config(
    tmp_path: Path,
    *,
    instances: list[str] | None = None,
    handles: list[SocialHandle] | None = None,
    enabled: bool = True,
    max_per_handle: int = 5,
    max_total: int = 12,
    skip_retweets: bool = True,
    skip_replies: bool = True,
) -> SocialConfig:
    return SocialConfig(
        enabled=enabled,
        handles=handles
        if handles is not None
        else [SocialHandle(handle="s1mpleO", display_name="s1mple")],
        instances=instances if instances is not None else ["primary.example"],
        lookback_hours=24,
        max_per_handle=max_per_handle,
        max_total_posts=max_total,
        request_timeout_seconds=5,
        skip_retweets=skip_retweets,
        skip_replies=skip_replies,
        cache_dir=str(tmp_path / "nitter-cache"),
    )


def _patch_load_config(monkeypatch, social_cfg: SocialConfig) -> None:
    base = AppConfig()
    base = base.model_copy(update={"social": social_cfg})
    monkeypatch.setattr("overpass.collectors.social.load_config", lambda: base)


def _patch_async_client(monkeypatch, transport: httpx.MockTransport) -> None:
    real_init = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)


@pytest.mark.asyncio
async def test_collect_parses_recent_posts_and_filters_rt_replies_and_old(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(hours=2), old=now - timedelta(days=3))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "primary.example"
        assert request.url.path == "/s1mpleO/rss"
        return httpx.Response(200, text=rss, headers={"content-type": "application/rss+xml"})

    _patch_load_config(monkeypatch, _make_config(tmp_path))
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    collector = NitterSocialCollector()
    items = await collector.collect()

    assert len(items) == 2
    bodies = [it.metadata["body"] for it in items]
    assert "Cologne is going to be insane this year." in bodies[0] or "Cologne" in bodies[0]
    assert any("Stream tomorrow" in b for b in bodies)
    assert all("RT by" not in b for b in bodies)
    assert all(not b.startswith("@") for b in bodies)
    assert all(it.type == "social" for it in items)
    assert all(it.source == "nitter" for it in items)
    # Display name override flows through.
    assert items[0].metadata["display_name"] == "s1mple"
    assert items[0].metadata["handle"] == "s1mpleO"
    # Sorted newest-first.
    assert items[0].timestamp >= items[-1].timestamp


@pytest.mark.asyncio
async def test_collect_falls_through_to_secondary_instance(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(hours=1), old=now - timedelta(days=3))
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "primary.example":
            return httpx.Response(503, text="busy")
        if request.url.host == "secondary.example":
            return httpx.Response(200, text=rss)
        return httpx.Response(404, text="nope")

    cfg = _make_config(tmp_path, instances=["primary.example", "secondary.example"])
    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()

    assert len(items) >= 1
    assert seen == ["primary.example", "secondary.example"]


@pytest.mark.asyncio
async def test_collect_uses_cache_when_all_instances_fail(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(hours=2), old=now - timedelta(days=3))

    cfg = _make_config(tmp_path, instances=["a.example", "b.example"])
    cache_dir = Path(cfg.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "s1mpleO.xml").write_text(rss, encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()

    assert len(items) >= 1
    assert all(it.source == "nitter" for it in items)


@pytest.mark.asyncio
async def test_collect_returns_empty_when_disabled(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path, enabled=False)
    _patch_load_config(monkeypatch, cfg)

    # No transport patch — if collector tried HTTP it would fail.
    items = await NitterSocialCollector().collect()
    assert items == []


@pytest.mark.asyncio
async def test_collect_returns_empty_with_no_handles(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path, handles=[])
    _patch_load_config(monkeypatch, cfg)
    items = await NitterSocialCollector().collect()
    assert items == []


@pytest.mark.asyncio
async def test_collect_returns_empty_when_all_instances_fail_and_no_cache(monkeypatch, tmp_path):
    cfg = _make_config(tmp_path, instances=["only.example"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()
    assert items == []


@pytest.mark.asyncio
async def test_collect_respects_max_per_handle(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(minutes=30), old=now - timedelta(days=3))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss)

    cfg = _make_config(tmp_path, max_per_handle=1)
    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()
    assert len(items) == 1


@pytest.mark.asyncio
async def test_collect_respects_max_total_posts(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(minutes=30), old=now - timedelta(days=3))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss)

    cfg = _make_config(
        tmp_path,
        handles=[SocialHandle(handle="s1mpleO"), SocialHandle(handle="ZywOo")],
        max_per_handle=5,
        max_total=2,
    )
    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_collect_writes_cache_on_success(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    rss = _build_rss(recent=now - timedelta(hours=2), old=now - timedelta(days=3))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=rss)

    cfg = _make_config(tmp_path)
    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    await NitterSocialCollector().collect()
    cached = Path(cfg.cache_dir) / "s1mpleO.xml"
    assert cached.exists()
    assert "<rss" in cached.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_collect_skips_non_rss_response(monkeypatch, tmp_path):
    """An HTTP 200 with HTML body (e.g. instance error page) should be ignored."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.example":
            return httpx.Response(200, text="<html><body>blocked</body></html>")
        if request.url.host == "good.example":
            now = datetime.now(timezone.utc)
            return httpx.Response(
                200,
                text=_build_rss(recent=now - timedelta(hours=1), old=now - timedelta(days=3)),
            )
        return httpx.Response(404)

    cfg = _make_config(tmp_path, instances=["html.example", "good.example"])
    _patch_load_config(monkeypatch, cfg)
    _patch_async_client(monkeypatch, httpx.MockTransport(handler))

    items = await NitterSocialCollector().collect()
    assert len(items) >= 1
