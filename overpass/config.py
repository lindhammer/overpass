"""Configuration loader – reads config.yaml and resolves env vars."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from pydantic import AnyHttpUrl, BaseModel, Field, TypeAdapter, ValidationError, field_validator

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


# ── Pydantic models ──────────────────────────────────────────────


class YoutubeChannel(BaseModel):
    id: str
    name: str


class YouTubeConfig(BaseModel):
    api_key_env: str = "YOUTUBE_API_KEY"
    channels: list[YoutubeChannel] = []


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


class LiquipediaUpcomingConfig(BaseModel):
    enabled: bool = False
    lookahead_hours: int = Field(default=36, gt=0)


class LiquipediaTransfersConfig(BaseModel):
    enabled: bool = False
    lookback_hours: int = Field(default=48, gt=0)


class LiquipediaConfig(BaseModel):
    base_url: str = "https://liquipedia.net/counterstrike"
    api_url: str = "https://liquipedia.net/counterstrike/api.php"
    contact: str = "63104033+lindhammer@users.noreply.github.com"
    user_agent: str = (
        "overpass/0.1.0 (+https://github.com/lindhammer/overpass; {contact})"
    )
    min_request_interval_seconds: float = Field(default=2.0, ge=0)
    request_timeout_seconds: int = Field(default=30, gt=0)
    cache_dir: str = ".cache/liquipedia"
    cache_ttl_minutes: int = Field(default=30, ge=0)
    hltv_fallback: bool = True
    upcoming_matches: LiquipediaUpcomingConfig = LiquipediaUpcomingConfig()
    transfers: LiquipediaTransfersConfig = LiquipediaTransfersConfig()

    def model_post_init(self, __context: Any) -> None:
        if "{contact}" in self.user_agent:
            object.__setattr__(self, "user_agent", self.user_agent.format(contact=self.contact))


class SocialHandle(BaseModel):
    handle: str
    display_name: str | None = None
    team_color: str | None = None


class SocialConfig(BaseModel):
    enabled: bool = False
    handles: list[SocialHandle] = []
    instances: list[str] = [
        "xcancel.com",
        "nitter.poast.org",
        "nitter.privacyredirect.com",
        "lightbrd.com",
        "nitter.space",
        "nitter.tiekoetter.com",
    ]
    lookback_hours: int = Field(default=24, gt=0)
    max_per_handle: int = Field(default=5, ge=1)
    max_total_posts: int = Field(default=12, ge=1)
    request_timeout_seconds: int = Field(default=8, gt=0)
    skip_retweets: bool = True
    skip_replies: bool = True
    cache_dir: str = ".cache/nitter"
    user_agent: str = (
        "overpass/0.1.0 (+https://github.com/lindhammer/overpass)"
    )


class TelegramConfig(BaseModel):
    bot_token_env: str
    chat_id_env: str


class ScheduleConfig(BaseModel):
    daily_digest: str = "07:00"
    live_poll_interval_minutes: int = 5


class HLTVConfig(BaseModel):
    base_url: str = "https://www.hltv.org"
    headless: bool = True
    news_limit: int = Field(default=20, ge=0)
    results_pages: int = Field(default=1, ge=1)
    request_timeout_seconds: int = Field(default=30, gt=0)
    min_request_interval_seconds: float = Field(default=2.0, ge=0)
    watchlist_only_matches: bool = False
    upcoming_enabled: bool = True
    upcoming_lookahead_hours: int = Field(default=36, gt=0)
    upcoming_max_matches: int = Field(default=8, ge=1)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        try:
            HTTP_URL_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise ValueError("base_url must be a valid http or https URL")
        return value


class AppConfig(BaseModel):
    watchlist_teams: list[str] = []
    hltv_top_n: int = 30
    hltv: HLTVConfig = HLTVConfig()
    youtube: YouTubeConfig = YouTubeConfig()
    podcasts: list[Podcast] = []
    reddit: RedditConfig = RedditConfig(subreddit="GlobalOffensive")
    web_base_url: str = "http://localhost:8000"
    live_alerts: LiveAlertsConfig = LiveAlertsConfig()
    llm: LLMConfig = LLMConfig()
    liquipedia: LiquipediaConfig = LiquipediaConfig()
    social: SocialConfig = SocialConfig()
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
