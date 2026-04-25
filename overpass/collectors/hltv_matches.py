"""HLTV match collector backed by the shared browser client and HTML parsers."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from overpass.config import load_config
from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.hltv.browser import HLTVBrowserClient, _looks_like_challenge
from overpass.hltv.matches import parse_match_detail, parse_ranked_team_names, parse_results_listing
from overpass.hltv.models import HLTVMatchDetail, HLTVMatchMapResult, HLTVMatchResult
from overpass.liquipedia.client import LiquipediaClient
from overpass.liquipedia.matches import parse_match_from_tournament_page
from overpass.liquipedia.models import LiquipediaMatch
from overpass.liquipedia.pages import find_match_page

_NUMBER_WORDS = {
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "10": "Ten",
}


class HLTVMatchesCollector(BaseCollector):
    name = "hltv_matches"
    _RANKINGS_PATH = "/ranking/teams/"
    _CHALLENGE_MARKERS = (
        "<title>just a moment",
        "checking your browser before accessing",
        "cf-browser-verification",
        "cf-challenge",
        "challenges.cloudflare.com",
    )

    def __init__(
        self,
        browser_client: HLTVBrowserClient | None = None,
        now: Callable[[], datetime] | None = None,
        base_url: str = "https://www.hltv.org",
        liquipedia_client: LiquipediaClient | None = None,
    ) -> None:
        config = load_config()
        self._hltv_config = config.hltv
        self._owns_browser_client = browser_client is None
        self._browser_client = browser_client or HLTVBrowserClient.from_config(self._hltv_config)
        self._base_url = getattr(
            self._browser_client,
            "base_url",
            self._hltv_config.base_url if self._owns_browser_client else base_url,
        ).rstrip("/")
        self._watchlist_only_matches = self._hltv_config.watchlist_only_matches
        self._watchlist_teams = {team.casefold() for team in config.watchlist_teams}
        self._results_pages = self._hltv_config.results_pages
        self._top_n = max(config.hltv_top_n, 0)
        self._now = now or (lambda: datetime.now(tz=timezone.utc))
        self._liquipedia_client = liquipedia_client
        super().__init__()

    async def collect(self) -> list[CollectorItem]:
        cutoff = self._now() - timedelta(hours=24)

        try:
            listing_items: list[HLTVMatchResult] = []
            for results_path in self._results_paths():
                listing_items.extend(await self._collect_results_page(results_path))

            recent_listing_items = [
                listing_item for listing_item in listing_items if listing_item.played_at is not None and listing_item.played_at >= cutoff
            ]
            relevant_teams = await self._relevant_team_names(recent_listing_items)
            if not relevant_teams:
                self.logger.info("No relevant HLTV matches found from watchlist or top-ranked teams")
                return []

            relevant_listing_items = [
                listing_item
                for listing_item in recent_listing_items
                if self._has_relevant_team(listing_item, relevant_teams)
            ]

            items: list[CollectorItem] = []
            for listing_item in relevant_listing_items:
                try:
                    match = await self._collect_match_detail(listing_item)
                except Exception:
                    self.logger.exception(
                        "Failed to collect HLTV match %s",
                        listing_item.url,
                    )
                    continue

                items.append(self._to_collector_item(match))

            self.logger.info("Collected %d HLTV matches", len(items))
            return items
        except Exception:
            self.logger.exception("Failed to collect HLTV matches")
            return []
        finally:
            if self._owns_browser_client:
                await self._browser_client.close()

    def _results_paths(self) -> list[str]:
        return ["/results", *[f"/results?offset={page_index * 100}" for page_index in range(1, self._results_pages)]]

    async def _collect_results_page(self, results_path: str) -> list[HLTVMatchResult]:
        results_html = await self._browser_client.fetch_page_content(results_path)
        listing_items = parse_results_listing(results_html, base_url=self._base_url)
        if listing_items or not self._looks_like_challenge_page(results_html):
            return listing_items

        rendered_results_html = await self._fetch_with_load_fallback(self._browser_client, results_path)
        rendered_listing_items = parse_results_listing(rendered_results_html, base_url=self._base_url)
        if rendered_listing_items or not self._looks_like_challenge_page(rendered_results_html):
            return rendered_listing_items

        if not getattr(self._browser_client, "headless", False):
            return rendered_listing_items

        headful_client = HLTVBrowserClient(
            base_url=self._base_url,
            headless=False,
            request_timeout_seconds=self._hltv_config.request_timeout_seconds,
            min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
        )
        try:
            headful_results_html = await self._fetch_with_load_fallback(headful_client, results_path)
            return parse_results_listing(headful_results_html, base_url=self._base_url)
        finally:
            await headful_client.close()

    async def _collect_match_detail(self, listing_item: HLTVMatchResult) -> HLTVMatchDetail:
        # Try headless first; escalate to headful if Cloudflare blocks us, then
        # to Liquipedia only as a last resort (Liquipedia can resolve to the
        # wrong tournament page, so prefer the real HLTV detail when possible).
        detail_html = await self._browser_client.fetch_page_content(listing_item.url)
        cf_blocked = _looks_like_challenge(detail_html)
        first_error: BaseException | None = None

        if not cf_blocked:
            try:
                return parse_match_detail(
                    detail_html,
                    listing_item=listing_item,
                    base_url=self._base_url,
                )
            except ValueError as error:
                first_error = error
                try:
                    detail_html = await self._fetch_with_load_fallback(
                        self._browser_client, listing_item.url
                    )
                    if _looks_like_challenge(detail_html):
                        cf_blocked = True
                    else:
                        return parse_match_detail(
                            detail_html,
                            listing_item=listing_item,
                            base_url=self._base_url,
                        )
                except ValueError as rendered_error:
                    first_error = rendered_error

        if cf_blocked:
            self.logger.warning(
                "HLTV match page %s blocked by Cloudflare in headless mode; escalating to headful",
                listing_item.url,
            )

        if getattr(self._browser_client, "headless", False):
            headful_client = HLTVBrowserClient(
                base_url=self._base_url,
                headless=False,
                request_timeout_seconds=self._hltv_config.request_timeout_seconds,
                min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
            )
            try:
                try:
                    headful_detail_html = await self._fetch_with_load_fallback(
                        headful_client, listing_item.url
                    )
                    return parse_match_detail(
                        headful_detail_html,
                        listing_item=listing_item,
                        base_url=self._base_url,
                    )
                except ValueError as headful_error:
                    first_error = headful_error
            finally:
                await headful_client.close()

        if first_error is None:
            first_error = ValueError("HLTV match page could not be retrieved")
        return await self._maybe_fallback_or_raise(listing_item, first_error)

    async def _maybe_fallback_or_raise(
        self,
        listing_item: HLTVMatchResult,
        original_error: BaseException,
    ) -> HLTVMatchDetail:
        if self._liquipedia_client is None:
            raise original_error

        try:
            found_title = await find_match_page(self._liquipedia_client, listing_item.event_name or "")
            page_titles = _liquipedia_page_title_candidates(listing_item, found_title)
            if not page_titles:
                raise original_error

            for page_title in page_titles:
                html = await self._liquipedia_client.parse_page(page_title)
                if not html:
                    continue

                liq_match = parse_match_from_tournament_page(
                    html, listing_item.team1_name, listing_item.team2_name
                )
                if liq_match is None:
                    continue

                return self._liquipedia_match_to_hltv_detail(listing_item, liq_match)
            raise original_error
        except Exception:
            self.logger.exception(
                "Liquipedia fallback failed for %s; dropping match",
                listing_item.url,
            )
            raise original_error from None

    @staticmethod
    def _liquipedia_match_to_hltv_detail(
        listing_item: HLTVMatchResult,
        liq_match: LiquipediaMatch,
    ) -> HLTVMatchDetail:
        return HLTVMatchDetail(
            external_id=listing_item.external_id,
            url=listing_item.url,
            team1_name=listing_item.team1_name,
            team2_name=listing_item.team2_name,
            team1_logo_url=liq_match.team1_logo_url,
            team2_logo_url=liq_match.team2_logo_url,
            team1_rank=listing_item.team1_rank,
            team2_rank=listing_item.team2_rank,
            team1_score=liq_match.team1_score,
            team2_score=liq_match.team2_score,
            winner_name=liq_match.winner_name,
            event_name=listing_item.event_name,
            format=listing_item.format,
            played_at=listing_item.played_at,
            maps=[
                HLTVMatchMapResult(
                    name=m.name,
                    team1_score=m.team1_score,
                    team2_score=m.team2_score,
                    winner_name=(
                        listing_item.team1_name if m.team1_score > m.team2_score
                        else listing_item.team2_name if m.team2_score > m.team1_score
                        else None
                    ),
                )
                for m in liq_match.maps
            ],
            source_fallback="liquipedia",
        )

    async def _relevant_team_names(self, listing_items: list[HLTVMatchResult]) -> set[str]:
        if self._watchlist_only_matches:
            return set(self._watchlist_teams)

        relevant_teams = set(self._watchlist_teams)
        relevant_teams.update(await self._top_ranked_team_names(listing_items))
        return relevant_teams

    async def _top_ranked_team_names(self, listing_items: list[HLTVMatchResult]) -> set[str]:
        if self._top_n <= 0:
            return set()

        ranked_teams: set[str] = set()
        for listing_item in listing_items:
            if listing_item.team1_rank is not None and listing_item.team1_rank <= self._top_n:
                ranked_teams.add(listing_item.team1_name.casefold())
            if listing_item.team2_rank is not None and listing_item.team2_rank <= self._top_n:
                ranked_teams.add(listing_item.team2_name.casefold())
        if ranked_teams:
            return ranked_teams

        return await self._fetch_top_ranked_team_names_from_rankings()

    async def _fetch_top_ranked_team_names_from_rankings(self) -> set[str]:
        try:
            rankings_client = self._browser_client
            temporary_client: HLTVBrowserClient | None = None
            if getattr(self._browser_client, "headless", False):
                temporary_client = HLTVBrowserClient(
                    base_url=self._base_url,
                    headless=False,
                    request_timeout_seconds=self._hltv_config.request_timeout_seconds,
                    min_request_interval_seconds=self._hltv_config.min_request_interval_seconds,
                )
                rankings_client = temporary_client

            rankings_html = await self._fetch_with_load_fallback(rankings_client, self._RANKINGS_PATH)
            ranked_team_names = parse_ranked_team_names(rankings_html, limit=self._top_n)
            return {team_name.casefold() for team_name in ranked_team_names}
        except Exception:
            self.logger.exception("Failed to fetch HLTV rankings for top-team relevance")
            return set()
        finally:
            if 'temporary_client' in locals() and temporary_client is not None:
                await temporary_client.close()
        return ranked_teams

    def _has_relevant_team(self, listing_item: HLTVMatchResult, relevant_teams: set[str]) -> bool:
        return (
            listing_item.team1_name.casefold() in relevant_teams
            or listing_item.team2_name.casefold() in relevant_teams
        )

    async def _fetch_with_load_fallback(self, browser_client: HLTVBrowserClient, path_or_url: str) -> str:
        try:
            return await browser_client.fetch_page_content(path_or_url, wait_until="load")
        except Exception:
            return await browser_client.fetch_page_content(path_or_url)

    @classmethod
    def _looks_like_challenge_page(cls, html: str) -> bool:
        lowered_html = html.lower()
        return any(marker in lowered_html for marker in cls._CHALLENGE_MARKERS)

    def _to_collector_item(self, match: HLTVMatchDetail) -> CollectorItem:
        flags: list[str] = []
        winner = (match.winner_name or "").casefold()
        if winner and winner in self._watchlist_teams:
            flags.append("watch")
        t1r, t2r = match.team1_rank, match.team2_rank
        if (
            winner
            and t1r is not None
            and t2r is not None
            and t1r != t2r
        ):
            winner_rank = t1r if winner == match.team1_name.casefold() else t2r
            loser_rank = t2r if winner == match.team1_name.casefold() else t1r
            if winner_rank > loser_rank:
                flags.append("upset")

        metadata = {
            "external_id": match.external_id,
            "team1_name": match.team1_name,
            "team2_name": match.team2_name,
            "team1_score": match.team1_score,
            "team2_score": match.team2_score,
            "winner_name": match.winner_name,
            "event_name": match.event_name,
            "format": match.format,
            "maps": [map_result.model_dump() for map_result in match.maps],
            "veto": [veto_entry.model_dump() for veto_entry in match.veto],
            "player_stats": [player_stat.model_dump() for player_stat in match.player_stats],
            "flags": flags,
        }
        if match.source_fallback is not None:
            metadata["source_fallback"] = match.source_fallback
        if match.team1_logo_url is not None:
            metadata["team1_logo_url"] = match.team1_logo_url
        if match.team2_logo_url is not None:
            metadata["team2_logo_url"] = match.team2_logo_url

        return CollectorItem(
            source="hltv",
            type="match",
            title=f"{match.team1_name} vs {match.team2_name}",
            url=match.url,
            timestamp=match.played_at or datetime.now(tz=timezone.utc),
            metadata=metadata,
        )


def _liquipedia_page_title_candidates(
    listing_item: HLTVMatchResult,
    found_title: str | None,
) -> list[str]:
    candidates: list[str] = []

    def add(title: str | None) -> None:
        if title and title not in candidates:
            candidates.append(title)

    add(found_title)

    season_word = _season_word(listing_item.event_name or "")
    if found_title and season_word is not None:
        add(re.sub(r"/Part [^/]+$", f"/Part {season_word}", found_title))

    if found_title and re.search(r"/\d{4}$", found_title):
        add(f"{found_title}/Online Stage")

    if listing_item.played_at is not None and season_word is not None:
        event_base = re.sub(
            r"\s+Season\s+\d+\b",
            "",
            listing_item.event_name or "",
            flags=re.IGNORECASE,
        ).strip()
        parts = event_base.split(maxsplit=1)
        if len(parts) == 2:
            series, rest = parts
            rest = rest.replace("RUSH B Summit", "RUSH B! Summit")
            add(f"{series}/{rest}/{listing_item.played_at.year}/Part {season_word}")

    return candidates


def _season_word(event_name: str) -> str | None:
    match = re.search(r"\bSeason\s+(\d{1,2})\b", event_name, flags=re.IGNORECASE)
    if match is None:
        return None
    return _NUMBER_WORDS.get(match.group(1))
