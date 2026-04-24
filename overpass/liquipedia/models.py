"""Structured result models for Liquipedia parsers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiquipediaMap(BaseModel):
    """Per-map result parsed from a Liquipedia match."""

    name: str
    team1_score: int
    team2_score: int


class LiquipediaMatch(BaseModel):
    """Match result parsed from a Liquipedia tournament page."""

    team1_name: str
    team2_name: str
    team1_logo_url: str | None = None
    team2_logo_url: str | None = None
    team1_score: int
    team2_score: int
    winner_name: str | None = None
    maps: list[LiquipediaMap] = Field(default_factory=list)
