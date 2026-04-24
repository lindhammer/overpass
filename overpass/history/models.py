"""Pydantic models for the 'This Day in CS' dataset."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryEntry(BaseModel):
    """A single curated historical moment."""

    year: int = Field(ge=1999)
    headline: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    visual_label: str | None = None
    source_url: str | None = None


class HistoryDay(BaseModel):
    """All entries bucketed under a single MM-DD key."""

    primary: HistoryEntry
    alternatives: list[HistoryEntry] = []
