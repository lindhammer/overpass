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
