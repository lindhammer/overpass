"""HLTV upcoming-matches collector backed by the shared browser client."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.config import load_config
from overpass.hltv.browser import HLTVBrowserClient, can_launch_headful_browser
from overpass.hltv.matches import parse_ranked_team_names
from overpass.hltv.models import HLTVUpcomingMatch
from overpass.hltv.upcoming import parse_upcoming_listing


class HLTVUpcomingCollector(BaseCollector):
    """Collect scheduled HLTV matches in the next ``upcoming_lookahead_hours``.

    Filters down to matches involving either a watchlist team or a top-N
    ranked team — the same logic the results collector uses, applied to the
    upcoming side of the schedule.
    """

    name = "hltv_upcoming"
    _RANKINGS_PATH = "/ranking/teams/"
    _UPCOMING_PATH = "/matches"
    _CHALLENGE_MARKERS = (
        "<title>just a moment",
        "checking your browser before accessing",
        "cf-browser-verification",
        "cf-challenge",
    )

    def __init__(
        self,
        browser_client: HLTVBrowserClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        config = load_config()
        self._hltv_config = config.hltv
        self._owns_browser_client = browser_client is None
        self._browser_client = browser_client or HLTVBrowserClient.from_config(self._hltv_config)
        self._base_url = getattr(
            self._browser_client,
            "base_url",
            self._hltv_config.base_url,
        ).rstrip("/")
        self._watchlist_teams = {team.casefold() for team in config.watchlist_teams}
        self._top_n = max(config.hltv_top_n, 0)
        self._lookahead_hours = self._hltv_config.upcoming_lookahead_hours
        self._max_matches = self._hltv_config.upcoming_max_matches
        self._enabled = self._hltv_config.upcoming_enabled
        self._now = now or (lambda: datetime.now(tz=timezone.utc))
        super().__init__()

    async def collect(self) -> list[CollectorItem]:
        if not self._enabled:
            self.logger.info("HLTV upcoming collector disabled – skipping")
            return []

        try:
            now = self._now()
            cutoff = now + timedelta(hours=self._lookahead_hours)

            try:
                html = await self._fetch_upcoming_html()
            except Exception:
                self.logger.exception("Failed to fetch HLTV /matches")
                return []

            all_matches = parse_upcoming_listing(html, base_url=self._base_url)
            in_window = [m for m in all_matches if now <= m.starts_at <= cutoff]

            relevant_teams = await self._relevant_team_names(in_window)
            if not relevant_teams:
                self.logger.info("No relevant upcoming HLTV matches in window")
                return []

            filtered = [
                m for m in in_window if self._has_relevant_team(m, relevant_teams)
            ]
            filtered.sort(key=lambda m: m.starts_at)
            limited = filtered[: self._max_matches]

            items = [self._to_collector_item(m) for m in limited]
            self.logger.info("Collected %d upcoming HLTV matches", len(items))
            return items
        finally:
            if self._owns_browser_client:
                await self._browser_client.close()

    async def _relevant_team_names(self, matches: list[HLTVUpcomingMatch]) -> set[str]:
        relevant: set[str] = set(self._watchlist_teams)
        if self._top_n > 0:
            try:
                rankings_html = await self._fetch_rankings_html()
                ranked = parse_ranked_team_names(rankings_html, self._top_n)
                relevant.update(name.casefold() for name in ranked)
            except Exception:
                self.logger.exception("Failed to fetch HLTV rankings for upcoming filter")
        return relevant

    async def _fetch_rankings_html(self) -> str:
        rankings_client = self._browser_client
        temporary_client: HLTVBrowserClient | None = None
        try:
            if getattr(self._browser_client, "headless", False) and can_launch_headful_browser():
                temporary_client = HLTVBrowserClient(
                    base_url=self._base_url,
                    headless=False,
                    request_timeout_seconds=self._hltv_config.request_timeout_seconds,
                    min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
                )
                rankings_client = temporary_client
            return await self._fetch_with_load_fallback(rankings_client, self._RANKINGS_PATH)
        finally:
            if temporary_client is not None:
                await temporary_client.close()

    async def _fetch_upcoming_html(self) -> str:
        html = await self._browser_client.fetch_page_content(self._UPCOMING_PATH)
        if not self._looks_like_challenge_page(html):
            return html

        # `wait_until="load"` and even `networkidle` rarely beat Cloudflare's
        # JS challenge in headless mode for HLTV's /matches – go straight to
        # a headful browser when we're allowed to.
        rendered = await self._fetch_with_load_fallback(self._browser_client, self._UPCOMING_PATH)
        if not self._looks_like_challenge_page(rendered):
            return rendered

        if not getattr(self._browser_client, "headless", False) or not can_launch_headful_browser():
            return rendered

        headful = HLTVBrowserClient(
            base_url=self._base_url,
            headless=False,
            request_timeout_seconds=self._hltv_config.request_timeout_seconds,
            min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
        )
        try:
            # `networkidle` gives Cloudflare's JS challenge a moment to auto-solve.
            try:
                return await headful.fetch_page_content(self._UPCOMING_PATH, wait_until="networkidle")
            except Exception:
                return await self._fetch_with_load_fallback(headful, self._UPCOMING_PATH)
        finally:
            await headful.close()

    @staticmethod
    async def _fetch_with_load_fallback(client: HLTVBrowserClient, path_or_url: str) -> str:
        try:
            return await client.fetch_page_content(path_or_url, wait_until="load")
        except Exception:
            return await client.fetch_page_content(path_or_url)

    @classmethod
    def _looks_like_challenge_page(cls, html: str) -> bool:
        lowered = html.lower()
        return any(marker in lowered for marker in cls._CHALLENGE_MARKERS)

    @staticmethod
    def _has_relevant_team(match: HLTVUpcomingMatch, relevant_teams: set[str]) -> bool:
        return (
            match.team1_name.casefold() in relevant_teams
            or match.team2_name.casefold() in relevant_teams
        )

    @staticmethod
    def _to_collector_item(m: HLTVUpcomingMatch) -> CollectorItem:
        return CollectorItem(
            source="hltv",
            type="upcoming",
            title=f"{m.team1_name} vs {m.team2_name}",
            url=m.url,
            timestamp=m.starts_at,
            metadata={
                "external_id": m.external_id,
                "starts_at": m.starts_at.isoformat(),
                "team1": m.team1_name,
                "team2": m.team2_name,
                "team1_logo_url": m.team1_logo_url,
                "team2_logo_url": m.team2_logo_url,
                "event": m.event_name,
                "format": (m.format or "").upper() or None,
                "stage": m.stage,
                "hltv_url": m.url,
            },
        )
