from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from overpass.collectors.base import CollectorItem
from overpass.editorial.base import BaseLLMProvider
from overpass.editorial.digest import (
    DigestOutput,
    MatchBlurb,
    generate_digest,
    generate_match_blurbs,
)


class _ScriptedProvider(BaseLLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str | None]] = []

    async def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return self._responses.pop(0)


def _match_item(url: str = "https://www.hltv.org/matches/1/x") -> CollectorItem:
    return CollectorItem(
        source="hltv",
        type="match",
        title="Vitality vs G2",
        url=url,
        timestamp=datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Vitality",
            "team2_name": "G2",
            "team1_score": 2,
            "team2_score": 1,
            "winner_name": "Vitality",
            "event_name": "PGL Bucharest",
            "format": "Best of 3",
            "maps": [
                {"name": "Mirage", "team1_score": 13, "team2_score": 7, "winner_name": "Vitality"},
                {"name": "Inferno", "team1_score": 10, "team2_score": 13, "winner_name": "G2"},
                {"name": "Ancient", "team1_score": 13, "team2_score": 11, "winner_name": "Vitality"},
            ],
            "veto": [],
            "player_stats": [
                {"team_name": "Vitality", "player_name": "ZywOo", "kills": 78, "deaths": 55, "adr": 95.2, "kast": 78.0, "rating": 1.42},
                {"team_name": "G2", "player_name": "huNter-", "kills": 62, "deaths": 60, "adr": 80.1, "kast": 70.0, "rating": 1.05},
            ],
        },
    )


def test_generate_match_blurbs_parses_keyed_response() -> None:
    item = _match_item()
    response = (
        '{"https://www.hltv.org/matches/1/x": '
        '{"tagline": "OT THRILLER", "highlight": "ZywOo dropped 78 kills as Vitality edged G2 on Ancient."}}'
    )
    provider = _ScriptedProvider([response])

    blurbs = asyncio.run(generate_match_blurbs([item], provider))

    assert blurbs == {
        item.url: MatchBlurb(
            tagline="OT THRILLER",
            highlight="ZywOo dropped 78 kills as Vitality edged G2 on Ancient.",
        )
    }
    # System prompt was passed.
    assert provider.calls[0][1] is not None
    # Prompt includes structured match payload.
    assert "Vitality" in provider.calls[0][0]
    assert "Mirage" in provider.calls[0][0]


def test_generate_match_blurbs_strips_markdown_fences() -> None:
    item = _match_item()
    response = (
        "```json\n"
        '{"' + item.url + '": {"tagline": "CLEAN CLOSE", "highlight": "Three-map decider."}}'
        "\n```"
    )
    provider = _ScriptedProvider([response])

    blurbs = asyncio.run(generate_match_blurbs([item], provider))

    assert blurbs[item.url].tagline == "CLEAN CLOSE"


def test_generate_match_blurbs_drops_unknown_urls() -> None:
    item = _match_item()
    response = (
        '{"https://example.com/other": {"tagline": "X", "highlight": "Y"},'
        ' "' + item.url + '": {"tagline": "DECIDER", "highlight": "Three maps."}}'
    )
    provider = _ScriptedProvider([response])

    blurbs = asyncio.run(generate_match_blurbs([item], provider))

    assert set(blurbs) == {item.url}


def test_generate_match_blurbs_returns_empty_on_invalid_json() -> None:
    item = _match_item()
    provider = _ScriptedProvider(["not json at all"])

    blurbs = asyncio.run(generate_match_blurbs([item], provider))

    assert blurbs == {}


def test_generate_match_blurbs_skips_when_no_matches() -> None:
    provider = _ScriptedProvider([])
    blurbs = asyncio.run(generate_match_blurbs([], provider))
    assert blurbs == {}
    assert provider.calls == []


def test_generate_digest_runs_second_pass_for_matches() -> None:
    item = _match_item()
    digest_response = (
        '{"summary_line": "Vitality survive G2 in three maps.",'
        ' "sections": {"Matches": {"intro": "One match yesterday."}}}'
    )
    blurbs_response = (
        '{"' + item.url + '": {"tagline": "OT THRILLER", "highlight": "ZywOo carried."}}'
    )
    provider = _ScriptedProvider([digest_response, blurbs_response])

    digest = asyncio.run(generate_digest([item], provider))

    assert isinstance(digest, DigestOutput)
    assert digest.summary_line == "Vitality survive G2 in three maps."
    assert "Matches" in digest.sections
    assert digest.per_match_blurbs[item.url].tagline == "OT THRILLER"
    # Two LLM calls: digest + match-blurbs
    assert len(provider.calls) == 2


def test_generate_digest_skips_blurbs_when_no_matches() -> None:
    item = CollectorItem(
        source="reddit",
        type="clip",
        title="A clip",
        url="https://reddit.com/x",
        timestamp=datetime(2026, 4, 24, tzinfo=timezone.utc),
        metadata={"upvotes": 100},
    )
    provider = _ScriptedProvider(['{"summary_line": "x", "sections": {"Clips": {"intro": "y"}}}'])

    digest = asyncio.run(generate_digest([item], provider))

    assert digest.per_match_blurbs == {}
    assert len(provider.calls) == 1
