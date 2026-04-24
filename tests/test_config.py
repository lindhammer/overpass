"""Tests for application config validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from overpass.config import load_config


@pytest.mark.parametrize(
    ("field_name", "yaml_value"),
    [
        ("news_limit", "-1"),
        ("results_pages", "0"),
        ("request_timeout_seconds", "0"),
        ("min_request_interval_seconds", "-2"),
        ("base_url", '"not-a-url"'),
    ],
)
def test_load_config_rejects_invalid_hltv_settings(tmp_path, field_name: str, yaml_value: str):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"hltv:\n  {field_name}: {yaml_value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match=field_name):
        load_config(config_path)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://:443",
        "https://user@:443",
    ],
)
def test_load_config_rejects_malformed_hltv_base_url(tmp_path, base_url: str):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f'hltv:\n  base_url: "{base_url}"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="base_url"):
        load_config(config_path)


def test_reddit_config_has_no_credential_fields():
    from overpass.config import RedditConfig

    cfg = RedditConfig(subreddit="GlobalOffensive")

    assert not hasattr(cfg, "client_id_env")
    assert not hasattr(cfg, "client_secret_env")


def test_load_config_reads_reddit_block_without_credentials(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            'reddit:\n'
            '  subreddit: "GlobalOffensive"\n'
            '  sort: "hot"\n'
            '  time_filter: "day"\n'
            '  limit: 25\n'
        ),
        encoding="utf-8",
    )

    cfg = load_config(config_path)

    assert cfg.reddit.subreddit == "GlobalOffensive"
    assert cfg.reddit.sort == "hot"
    assert cfg.reddit.time_filter == "day"
    assert cfg.reddit.limit == 25


def test_liquipedia_config_defaults():
    from overpass.config import LiquipediaConfig

    cfg = LiquipediaConfig()
    assert cfg.base_url == "https://liquipedia.net/counterstrike"
    assert cfg.api_url == "https://liquipedia.net/counterstrike/api.php"
    assert cfg.min_request_interval_seconds == 2.0
    assert cfg.cache_ttl_minutes == 30
    assert cfg.hltv_fallback is True
    assert cfg.upcoming_matches.enabled is False
    assert cfg.upcoming_matches.lookahead_hours == 36
    assert cfg.transfers.enabled is False
    assert cfg.transfers.lookback_hours == 48


def test_liquipedia_user_agent_interpolates_contact():
    from overpass.config import LiquipediaConfig

    cfg = LiquipediaConfig(
        contact="me@example.com",
        user_agent="overpass/0.1.0 (+url; {contact})",
    )
    assert cfg.user_agent == "overpass/0.1.0 (+url; me@example.com)"


def test_app_config_includes_liquipedia_block():
    from overpass.config import AppConfig

    cfg = AppConfig()
    assert cfg.liquipedia.hltv_fallback is True
