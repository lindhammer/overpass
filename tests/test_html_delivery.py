"""Tests for the HTML briefing renderer."""

from __future__ import annotations

import html as html_lib
from datetime import date, datetime, timezone

import pytest

from overpass.collectors.base import CollectorItem
from overpass.delivery.html import _first_paragraph, render_briefing
from overpass.editorial.digest import DigestOutput, SectionOutput

# ── Fixtures ─────────────────────────────────────────────────────

_NOW = datetime(2026, 4, 10, 7, 0, tzinfo=timezone.utc)
_DATE = date(2026, 4, 10)


def _clip() -> CollectorItem:
    return CollectorItem(
        source="reddit",
        type="clip",
        title="Amazing AWP ace on Mirage",
        url="https://www.reddit.com/r/GlobalOffensive/comments/abc123/",
        timestamp=_NOW,
        thumbnail_url="https://example.com/thumb.jpg",
        metadata={"score": 4200, "num_comments": 87, "author": "clipper123", "flair": "Highlight"},
    )


def _episode() -> CollectorItem:
    return CollectorItem(
        source="podcast",
        type="episode",
        title="Episode 300: Major Recap",
        url="https://example.com/ep300",
        timestamp=_NOW,
        thumbnail_url=None,
        metadata={"podcast_name": "HLTV Confirmed", "duration": "1:42:10", "description": "Full recap."},
    )


def _video() -> CollectorItem:
    return CollectorItem(
        source="youtube",
        type="video",
        title="Top 10 Plays This Week",
        url="https://www.youtube.com/watch?v=xyz",
        timestamp=_NOW,
        thumbnail_url="https://img.youtube.com/vi/xyz/maxresdefault.jpg",
        metadata={"channel_name": "HLTV", "channel_id": "UC_SgBkrOEFVnJkBMKcpp5lg", "video_id": "xyz"},
    )


def _article() -> CollectorItem:
    return CollectorItem(
        source="hltv",
        type="article",
        title="FaZe win Cologne opener",
        url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        timestamp=_NOW,
        thumbnail_url="https://www.hltv.org/gallery/12345/cover.jpg",
        metadata={
            "teaser": "Finn \"karrigan\" Andersen's side opened the event with a comfortable series win.",
            "body_text": (
                "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n\n"
                "Finn \"karrigan\" Andersen said the team kept its early-game protocols simple and trusted the calling in late rounds.\n\n"
                "\"We knew the veto gave us room to play our own game,\" karrigan said."
            ),
            "author": "Striker",
            "tags": ["CS2", "IEM Cologne"],
        },
    )


def _match() -> CollectorItem:
    return CollectorItem(
        source="hltv",
        type="match",
        title="Spirit vs FaZe",
        url="https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        timestamp=_NOW,
        metadata={
            "team1_name": "Spirit",
            "team2_name": "FaZe",
            "team1_score": 2,
            "team2_score": 1,
            "winner_name": "Spirit",
            "event_name": "BLAST Open Lisbon 2026",
            "format": "bo3",
            "maps": [
                {"name": "Mirage", "team1_score": 13, "team2_score": 9, "winner_name": "Spirit"},
                {"name": "Ancient", "team1_score": 11, "team2_score": 13, "winner_name": "FaZe"},
                {"name": "Anubis", "team1_score": 13, "team2_score": 8, "winner_name": "Spirit"},
            ],
            "veto": [
                {"team_name": "Spirit", "action": "removed", "map_name": "Inferno"},
                {"team_name": "FaZe", "action": "removed", "map_name": "Nuke"},
                {"team_name": "Spirit", "action": "picked", "map_name": "Mirage"},
                {"team_name": "FaZe", "action": "picked", "map_name": "Ancient"},
                {"team_name": None, "action": "left_over", "map_name": "Anubis"},
            ],
        },
    )


def _patch() -> CollectorItem:
    return CollectorItem(
        source="steam",
        type="patch",
        title="CS2 Update – April 10",
        url="https://store.steampowered.com/news/app/730/view/1234",
        timestamp=_NOW,
        metadata={
            "contents": "Fixed a bug with the AWP scope.\n\n[b]Gameplay[/b]\nImproved server performance.",
            "feedname": "steam_community_announcements",
        },
    )


def _full_digest() -> DigestOutput:
    return DigestOutput(
        summary_line="Amazing AWP ace, ropz tops the charts, CS2 patch drops today.",
        sections={
            "Clips": SectionOutput(intro="Best clips from the last 24 hours.", items=[_clip()]),
            "Podcasts": SectionOutput(intro="Fresh episodes from your tracked shows.", items=[_episode()]),
            "Videos": SectionOutput(intro="Latest uploads from tracked channels.", items=[_video()]),
            "Patches": SectionOutput(intro="Valve shipped an update overnight.", items=[_patch()]),
        },
    )


def _digest_with_hltv_sections() -> DigestOutput:
    return DigestOutput(
        summary_line="Spirit edge FaZe in Lisbon while HLTV leads with match and news coverage.",
        sections={
            "Matches": SectionOutput(intro="Key results from tracked HLTV matches.", items=[_match()]),
            "News": SectionOutput(intro="Top HLTV reporting and analysis.", items=[_article()]),
            "Clips": SectionOutput(intro="Best clips from the last 24 hours.", items=[_clip()]),
            "Videos": SectionOutput(intro="Latest uploads from tracked channels.", items=[_video()]),
            "Podcasts": SectionOutput(intro="Fresh episodes from your tracked shows.", items=[_episode()]),
            "Patches": SectionOutput(intro="Valve shipped an update overnight.", items=[_patch()]),
        },
    )


# ── Tests ─────────────────────────────────────────────────────────


def test_summary_line_appears_in_html():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert digest.summary_line in html


def test_all_section_headings_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    for section in ["Clips", "Podcasts", "Videos", "Patches"]:
        assert section in html, f"Section '{section}' missing from HTML"


def test_all_item_titles_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    for title in [
        "Amazing AWP ace on Mirage",
        "Episode 300: Major Recap",
        "Top 10 Plays This Week",
        "CS2 Update – April 10",
    ]:
        assert title in html, f"Item title '{title}' missing from HTML"


def test_clip_score_and_comments_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "4200" in html
    assert "87" in html


def test_podcast_name_and_duration_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "HLTV Confirmed" in html
    assert "1:42:10" in html


def test_video_channel_name_appears():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "HLTV" in html


def test_patch_excerpt_strips_bbcode():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    # BBCode tags must be stripped in the rendered output
    assert "[b]" not in html
    assert "[/b]" not in html
    # First paragraph text should be present
    assert "Fixed a bug with the AWP scope" in html


def test_section_intros_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "Best clips from the last 24 hours." in html
    assert "Valve shipped an update overnight." in html


def test_empty_sections_not_rendered():
    digest = DigestOutput(
        summary_line="Quiet day in CS2.",
        sections={},
    )
    html = render_briefing(digest, _DATE)
    assert "Quiet day in CS2." in html
    # None of the section headings should appear
    for section in ["Clips", "Podcasts", "Videos", "Patches"]:
        assert f">{section}<" not in html


def test_missing_sections_not_rendered():
    """Sections absent from the digest don't produce empty headings."""
    digest = DigestOutput(
        summary_line="Only patches today.",
        sections={
            "Patches": SectionOutput(intro="", items=[_patch()]),
        },
    )
    html = render_briefing(digest, _DATE)
    assert "CS2 Update" in html
    # No Clips / Podcasts / Videos sections
    assert "class=\"section-heading\">Clips<" not in html
    assert "class=\"section-heading\">Podcasts<" not in html


def test_date_appears_in_html():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "2026" in html
    assert "April" in html


def test_thumbnail_url_used_in_clip_card():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "https://example.com/thumb.jpg" in html


def test_item_urls_are_linked():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "https://www.reddit.com/r/GlobalOffensive/comments/abc123/" in html
    assert "https://example.com/ep300" in html
    assert "https://www.youtube.com/watch?v=xyz" in html


def test_matches_and_news_sections_render_ahead_of_older_media_sections():
    digest = _digest_with_hltv_sections()
    html = render_briefing(digest, _DATE)

    matches_heading = html.index('class="section-heading">Matches<')
    news_heading = html.index('class="section-heading">News<')
    clips_heading = html.index('class="section-heading">Clips<')
    videos_heading = html.index('class="section-heading">Videos<')

    assert matches_heading < clips_heading
    assert news_heading < clips_heading
    assert news_heading < videos_heading


def test_news_and_match_cards_render_digest_details():
    digest = _digest_with_hltv_sections()
    html = html_lib.unescape(render_briefing(digest, _DATE))

    assert "FaZe win Cologne opener" in html
    assert "Finn \"karrigan\" Andersen's side opened the event with a comfortable series win." in html
    assert "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion." in html
    assert "Spirit vs FaZe" in html
    assert "BLAST Open Lisbon 2026" in html
    assert "2-1" in html
    assert "Mirage 13-9" in html
    assert "Ancient 11-13" in html
    assert "Anubis 13-8" in html
    assert "Spirit removed Inferno" in html
    assert "FaZe picked Ancient" in html
    assert "Anubis left over" in html


# ── Unit tests for _first_paragraph ──────────────────────────────


def test_first_paragraph_strips_bbcode():
    result = _first_paragraph("[b]Hello[/b] world")
    assert result == "Hello world"


def test_first_paragraph_returns_first_block():
    result = _first_paragraph("First paragraph.\n\nSecond paragraph.")
    assert result == "First paragraph."


def test_first_paragraph_truncates():
    long_text = "A" * 400
    result = _first_paragraph(long_text, max_chars=300)
    assert len(result) <= 304  # 300 chars + possible "…"
    assert result.endswith("…")


def test_first_paragraph_empty_input():
    result = _first_paragraph("")
    assert result == ""
