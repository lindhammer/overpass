"""HLTV match collector backed by the shared browser client and HTML parsers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from overpass.config import load_config
from overpass.collectors.base import BaseCollector, CollectorItem
from overpass.hltv.browser import HLTVBrowserClient
from overpass.hltv.matches import parse_match_detail, parse_results_listing
from overpass.hltv.models import HLTVMatchDetail, HLTVMatchResult


class HLTVMatchesCollector(BaseCollector):
    name = "hltv_matches"

    def __init__(
        self,
        browser_client: HLTVBrowserClient | None = None,
        now: Callable[[], datetime] | None = None,
        base_url: str = "https://www.hltv.org",
    ) -> None:
        config = load_config()
        self._owns_browser_client = browser_client is None
        self._browser_client = browser_client or HLTVBrowserClient.from_config(config.hltv)
        self._base_url = getattr(
            self._browser_client,
            "base_url",
            config.hltv.base_url if self._owns_browser_client else base_url,
        ).rstrip("/")
        self._watchlist_only_matches = config.hltv.watchlist_only_matches
        self._watchlist_teams = {team.casefold() for team in config.watchlist_teams}
        self._results_pages = config.hltv.results_pages
        self._top_n = max(config.hltv_top_n, 0)
        self._now = now or (lambda: datetime.now(tz=timezone.utc))
        super().__init__()

    async def collect(self) -> list[CollectorItem]:
        cutoff = self._now() - timedelta(hours=24)

        try:
            listing_items: list[HLTVMatchResult] = []
            for results_path in self._results_paths():
                results_html = await self._browser_client.fetch_page_content(results_path)
                listing_items.extend(parse_results_listing(results_html, base_url=self._base_url))

            recent_listing_items = [
                listing_item for listing_item in listing_items if listing_item.played_at is not None and listing_item.played_at >= cutoff
            ]
            relevant_teams = self._relevant_team_names(recent_listing_items)
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
                    detail_html = await self._browser_client.fetch_page_content(listing_item.url)
                    match = parse_match_detail(
                        detail_html,
                        listing_item=listing_item,
                        base_url=self._base_url,
                    )
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

    def _relevant_team_names(self, listing_items: list[HLTVMatchResult]) -> set[str]:
        if self._watchlist_only_matches:
            return set(self._watchlist_teams)

        relevant_teams = set(self._watchlist_teams)
        relevant_teams.update(self._top_ranked_team_names(listing_items))
        return relevant_teams

    def _top_ranked_team_names(self, listing_items: list[HLTVMatchResult]) -> set[str]:
        if self._top_n <= 0:
            return set()

        ranked_teams: set[str] = set()
        for listing_item in listing_items:
            if listing_item.team1_rank is not None and listing_item.team1_rank <= self._top_n:
                ranked_teams.add(listing_item.team1_name.casefold())
            if listing_item.team2_rank is not None and listing_item.team2_rank <= self._top_n:
                ranked_teams.add(listing_item.team2_name.casefold())
        return ranked_teams

    def _has_relevant_team(self, listing_item: HLTVMatchResult, relevant_teams: set[str]) -> bool:
        return (
            listing_item.team1_name.casefold() in relevant_teams
            or listing_item.team2_name.casefold() in relevant_teams
        )

    @staticmethod
    def _to_collector_item(match: HLTVMatchDetail) -> CollectorItem:
        return CollectorItem(
            source="hltv",
            type="match",
            title=f"{match.team1_name} vs {match.team2_name}",
            url=match.url,
            timestamp=match.played_at or datetime.now(tz=timezone.utc),
            metadata={
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
            },
        )
