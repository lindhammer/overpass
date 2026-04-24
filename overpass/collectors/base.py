"""Base collector interface implemented by all Overpass data collectors."""

from __future__ import annotations

import abc
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CollectorItem(BaseModel):
    """Standardized item returned by collectors for downstream processing."""

    source: str
    type: str  # clip | episode | patch | video | article
    title: str
    url: str
    timestamp: datetime
    metadata: dict[str, Any] = {}
    thumbnail_url: str | None = None


class BaseCollector(abc.ABC):
    """Base interface for collectors that return standardized collected items.

    Subclasses provide a human-readable name and implement collect() to fetch
    source data, normalize it, and return a list of CollectorItem instances.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable collector name used for logging."""
        ...

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"overpass.collectors.{self.name}")

    @abc.abstractmethod
    async def collect(self) -> list[CollectorItem]:
        """Fetch source data and return standardized items.

        Implementations should handle recoverable source failures internally and
        return an empty list when no items can be collected.
        """
        ...
