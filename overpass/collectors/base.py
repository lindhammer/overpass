"""Abstract base collector and shared data model."""

from __future__ import annotations

import abc
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CollectorItem(BaseModel):
    """Standardised output item produced by every collector."""

    source: str
    type: str  # clip | episode | patch | video | article
    title: str
    url: str
    timestamp: datetime
    metadata: dict[str, Any] = {}
    thumbnail_url: str | None = None


class BaseCollector(abc.ABC):
    """Abstract base class for all data collectors."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable collector name used for logging."""
        ...

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"overpass.collectors.{self.name}")

    @abc.abstractmethod
    async def collect(self) -> list[CollectorItem]:
        """Fetch data from the source and return normalised items."""
        ...
