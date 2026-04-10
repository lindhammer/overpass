"""Configuration loader – reads config.yaml and resolves env vars."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, model_validator

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


# ── Pydantic models ──────────────────────────────────────────────


class YoutubeChannel(BaseModel):
    id: str
    name: str


class Podcast(BaseModel):
    name: str
    feed_url: str


class RedditConfig(BaseModel):
    subreddit: str
    sort: str = "top"
    time_filter: str = "day"
    limit: int = 10
    flair_filter: list[str] = []
    client_id_env: str = "REDDIT_CLIENT_ID"
    client_secret_env: str = "REDDIT_CLIENT_SECRET"
    user_agent: str = "overpass:v0.1.0 (by /u/overpass-bot)"


class LiveAlertsConfig(BaseModel):
    watchlist_match_live: bool = True
    valve_patch: bool = True
    roster_moves: bool = True
    tournament_stage_change: bool = True


class LLMProviderConfig(BaseModel):
    model: str
    api_key_env: str


class LLMConfig(BaseModel):
    default_provider: str = "gemini"
    providers: dict[str, LLMProviderConfig] = {}


class TelegramConfig(BaseModel):
    bot_token_env: str
    chat_id_env: str


class ScheduleConfig(BaseModel):
    daily_digest: str = "07:00"
    live_poll_interval_minutes: int = 5


class AppConfig(BaseModel):
    watchlist_teams: list[str] = []
    hltv_top_n: int = 30
    youtube_channels: list[YoutubeChannel] = []
    podcasts: list[Podcast] = []
    reddit: RedditConfig = RedditConfig(subreddit="GlobalOffensive")
    live_alerts: LiveAlertsConfig = LiveAlertsConfig()
    llm: LLMConfig = LLMConfig()
    telegram: TelegramConfig = TelegramConfig(bot_token_env="TELEGRAM_BOT_TOKEN", chat_id_env="TELEGRAM_CHAT_ID")
    schedule: ScheduleConfig = ScheduleConfig()
    timezone: str = "Europe/Berlin"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


# ── Env-var resolution ───────────────────────────────────────────


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively walk a parsed YAML structure and replace every value
    whose **key** ends with ``_env`` with the content of the corresponding
    environment variable.  The key is kept as-is so Pydantic can still
    validate it.
    """
    if isinstance(obj, dict):
        resolved: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and key.endswith("_env") and isinstance(value, str):
                resolved[key] = os.environ.get(value, "")
            else:
                resolved[key] = _resolve_env_vars(value)
        return resolved
    if isinstance(obj, list):
        return [_resolve_env_vars(item) for item in obj]
    return obj


# ── Public API ───────────────────────────────────────────────────


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate the application configuration."""
    config_path = path or CONFIG_PATH
    with open(config_path, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}
    resolved = _resolve_env_vars(raw)
    return AppConfig(**resolved)
