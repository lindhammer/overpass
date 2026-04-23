"""Structured result models for Liquipedia parsers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LiquipediaMap(BaseModel):
    name: str
    team1_score: int
    team2_score: int


class LiquipediaMatch(BaseModel):
    team1_name: str
    team2_name: str
    team1_score: int
    team2_score: int
    winner_name: str | None = None
    maps: list[LiquipediaMap] = Field(default_factory=list)
