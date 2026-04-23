"""On-disk TTL cache for Liquipedia API responses."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("overpass.liquipedia.cache")

_CACHE_SCHEMA = "v1"


class FileCache:
    """SHA-1-keyed file cache with a single TTL applied to every entry.

    Entries live at ``{root}/{key[:2]}/{key}.json`` and store
    ``{"fetched_at": float_unix, "body": str}``. Expired entries are
    ignored on read (not deleted) so the cache is deterministic and
    cheap. Write failures are logged and swallowed — the cache is a
    performance aid, never a correctness boundary.
    """

    def __init__(self, root: Path, ttl_seconds: float) -> None:
        self._root = Path(root)
        self._ttl = float(ttl_seconds)

    def _key_for(self, raw_key: str) -> str:
        digest = hashlib.sha1(f"{_CACHE_SCHEMA}:{raw_key}".encode("utf-8")).hexdigest()
        return digest

    def _path_for(self, raw_key: str) -> Path:
        key = self._key_for(raw_key)
        return self._root / key[:2] / f"{key}.json"

    def get(self, raw_key: str) -> str | None:
        path = self._path_for(raw_key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(payload["fetched_at"])
            body = payload["body"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if time.time() - fetched_at > self._ttl:
            return None
        return body

    def set(self, raw_key: str, body: str) -> None:
        path = self._path_for(raw_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"fetched_at": time.time(), "body": body}),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write cache entry %s: %s", path, exc)
