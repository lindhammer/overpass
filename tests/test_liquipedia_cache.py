"""FileCache tests — TTL hit/miss/expiry, corruption tolerance."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from overpass.liquipedia.cache import FileCache


def test_get_returns_none_when_key_missing(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    assert cache.get("nope") is None


def test_set_then_get_returns_value(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("k", "hello")
    assert cache.get("k") == "hello"


def test_get_returns_none_when_entry_expired(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=0)
    cache.set("k", "hello")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_get_returns_none_for_corrupt_file(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    # Force a corrupt entry at the path FileCache would use.
    cache.set("k", "hello")
    cache_file = next(tmp_path.rglob("*.json"))
    cache_file.write_text("not json", encoding="utf-8")
    assert cache.get("k") is None


def test_set_handles_unwritable_directory_silently(tmp_path: Path, monkeypatch) -> None:
    # Simulate a write failure: replace Path.write_text with one that raises.
    cache = FileCache(tmp_path, ttl_seconds=60)
    real_write_text = Path.write_text

    def boom(self, *a, **kw):
        if "liquipedia" in str(self) or self.suffix == ".json":
            raise OSError("disk full")
        return real_write_text(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", boom)
    # Must not raise.
    cache.set("k", "hello")


def test_keys_are_sharded_by_prefix(tmp_path: Path) -> None:
    cache = FileCache(tmp_path, ttl_seconds=60)
    cache.set("alpha", "a")
    cache.set("beta", "b")
    # Each value lives in a 2-char shard subdir named after the SHA-1 prefix.
    files = list(tmp_path.rglob("*.json"))
    assert len(files) == 2
    for f in files:
        assert f.parent.name == f.stem[:2]
