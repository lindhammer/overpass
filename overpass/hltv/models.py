"""Structured models for HLTV news parsing."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HLTVNewsItem(BaseModel):
    """Shared news metadata used across listing and article parsing."""

    external_id: str
    title: str
    url: str
    published_at: datetime


class HLTVNewsListingItem(HLTVNewsItem):
    """Metadata extracted from a news listing page."""

    teaser: str | None = None
    thumbnail_url: str | None = None


class HLTVNewsArticle(HLTVNewsListingItem):
    """Fully parsed HLTV news article metadata."""

    author: str | None = None
    body_text: str | None = None
    tags: list[str] = Field(default_factory=list)


class HLTVMatchResult(BaseModel):
    """Shared match metadata extracted from HLTV results and match pages."""

    external_id: str
    url: str
    team1_name: str
    team2_name: str
    team1_rank: int | None = None
    team2_rank: int | None = None
    team1_score: int
    team2_score: int
    winner_name: str | None = None
    event_name: str | None = None
    format: str | None = None
    played_at: datetime | None = None


class HLTVMatchMapResult(BaseModel):
    """Per-map result metadata for a parsed HLTV match."""

    name: str
    team1_score: int
    team2_score: int
    winner_name: str | None = None


class HLTVMatchVetoEntry(BaseModel):
    """A single veto or leftover entry extracted from a match detail page."""

    team_name: str | None = None
    action: str
    map_name: str


class HLTVMatchPlayerStat(BaseModel):
    """A flattened player stat line grouped by team name."""

    team_name: str
    player_name: str
    kills: int
    deaths: int
    adr: float
    kast: float
    rating: float


class HLTVMatchDetail(HLTVMatchResult):
    """Detailed match metadata including maps, veto, and player stats."""

    maps: list[HLTVMatchMapResult] = Field(default_factory=list)
    veto: list[HLTVMatchVetoEntry] = Field(default_factory=list)
    player_stats: list[HLTVMatchPlayerStat] = Field(default_factory=list)
