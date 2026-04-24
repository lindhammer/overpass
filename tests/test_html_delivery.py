"""Tests for the HTML briefing renderer."""

from __future__ import annotations

import html as html_lib
from datetime import date, datetime, timezone

from overpass.collectors.base import CollectorItem
from overpass.delivery.html import (
    _build_ticker_chips,
    _compute_issue_number,
    _first_paragraph,
    _team_code,
    render_briefing,
)
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
        metadata={
            "score": 4200,
            "num_comments": 87,
            "duration": "0:38",
            "rank": 1,
            "author": "clipper123",
            "flair": "Highlight",
        },
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
        metadata={
            "channel_name": "HLTV",
            "channel_id": "UC_SgBkrOEFVnJkBMKcpp5lg",
            "video_id": "xyz",
            "duration": "12:34",
            "is_new": True,
        },
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
            "author": "Striker",
            "tags": ["CS2", "IEM Cologne"],
            "flag": "confirmed",
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
            "flags": ["watch", "final"],
            "maps": [
                {"name": "Mirage", "team1_score": 13, "team2_score": 9},
                {"name": "Ancient", "team1_score": 11, "team2_score": 13},
                {"name": "Anubis", "team1_score": 13, "team2_score": 8},
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
            "version": "1.40.1.9",
            "entries": [
                {"tag": "Maps", "body": "Fixed a pixel walk on Inferno banana."},
                {"tag": "Weapons", "body": "XM1014 rate of fire reduced by 6%."},
            ],
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


# ── Smoke tests ──────────────────────────────────────────────────


def test_summary_line_appears_in_html():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert digest.summary_line in html


def test_section_labels_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    for label in ["Top Clips", "Patch Notes", "Podcasts &amp; Content"]:
        assert label in html, f"Section label {label!r} missing from HTML"


def test_all_item_titles_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    for title in [
        "Amazing AWP ace on Mirage",
        "Episode 300: Major Recap",
        "Top 10 Plays This Week",
        "CS2 Update – April 10",
    ]:
        assert title in html, f"Item title {title!r} missing from HTML"


def test_clip_score_and_comments_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "4.2k" in html
    assert "87 comments" in html


def test_podcast_name_and_duration_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "HLTV Confirmed" in html
    assert "1:42:10" in html


def test_video_hero_renders():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "Top 10 Plays This Week" in html


def test_patch_entries_render():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "Build 1.40.1.9 · Valve" in html
    assert "Fixed a pixel walk on Inferno banana." in html
    assert "XM1014 rate of fire reduced by 6%." in html


def test_section_intros_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "Best clips from the last 24 hours." in html
    assert "Valve shipped an update overnight." in html


def test_empty_digest_renders_only_lede_and_chrome():
    digest = DigestOutput(summary_line="Quiet day in CS2.", sections={})
    html = render_briefing(digest, _DATE)
    assert "Quiet day in CS2." in html
    assert "Overpass" in html
    for label in ["Top Clips", "Match Results", "Patch Notes"]:
        assert label not in html


def test_only_patches_section_renders():
    digest = DigestOutput(
        summary_line="Only patches today.",
        sections={"Patches": SectionOutput(intro="", items=[_patch()])},
    )
    html = render_briefing(digest, _DATE)
    assert "CS2 Update – April 10" in html
    assert "Top Clips" not in html
    assert "Match Results" not in html


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


def test_match_section_renders_teams_score_and_event():
    digest = _digest_with_hltv_sections()
    html = html_lib.unescape(render_briefing(digest, _DATE))

    assert "Match Results" in html
    assert "Spirit" in html
    assert "FaZe" in html
    assert "BLAST Open Lisbon 2026" in html
    assert "Mirage" in html


def test_match_section_renders_team_logos_when_available():
    match = _match()
    match.metadata["team1_logo_url"] = "https://img.example/spirit.png"
    match.metadata["team2_logo_url"] = "https://img.example/faze.png"
    digest = DigestOutput(
        summary_line="Spirit edge FaZe in Lisbon.",
        sections={"Matches": SectionOutput(intro="", items=[match])},
    )

    html = html_lib.unescape(render_briefing(digest, _DATE))
    collapsed = " ".join(html.split())

    assert 'class="team-logo"' in collapsed
    assert 'src="https://img.example/spirit.png"' in collapsed
    assert 'alt="Spirit logo"' in collapsed
    assert 'src="https://img.example/faze.png"' in collapsed
    assert 'alt="FaZe logo"' in collapsed
    assert ">SP</span>" not in html
    assert ">FAZE</span>" not in html


def test_match_section_falls_back_to_initial_crest_without_team_logos():
    digest = _digest_with_hltv_sections()

    html = html_lib.unescape(render_briefing(digest, _DATE))
    collapsed = " ".join(html.split())

    assert 'class="crest" data-team="SP"' in collapsed
    assert ">SP</span>" in html


def test_news_section_renders_article():
    digest = _digest_with_hltv_sections()
    html = html_lib.unescape(render_briefing(digest, _DATE))

    assert "Roster & News" in html
    assert "FaZe win Cologne opener" in html
    assert "Striker" in html
    assert (
        "Finn \"karrigan\" Andersen's side opened the event with a comfortable series win."
        in html
    )


def test_match_section_renders_before_clips():
    digest = _digest_with_hltv_sections()
    html = render_briefing(digest, _DATE)
    assert html.index("Match Results") < html.index("Top Clips")


def test_lede_bold_markdown_wraps_in_highlight_span():
    digest = DigestOutput(
        summary_line="ropz **MVP run** continues at PGL Bucharest.",
        sections={},
    )
    html = render_briefing(digest, _DATE)
    collapsed = " ".join(html.split())
    assert 'class="hl"' in collapsed
    assert "MVP run</span" in collapsed
    assert "**" not in html


def test_issue_number_appears_in_masthead_and_colophon():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    expected = _compute_issue_number(_DATE)
    assert f"No. {expected}" in html
    assert f"Issue No. {expected}" in html


# ── Unit tests ────────────────────────────────────────────────────


def test_first_paragraph_strips_bbcode():
    assert _first_paragraph("[b]Hello[/b] world") == "Hello world"


def test_first_paragraph_returns_first_block():
    assert _first_paragraph("First paragraph.\n\nSecond paragraph.") == "First paragraph."


def test_first_paragraph_truncates():
    long_text = "A" * 400
    result = _first_paragraph(long_text, max_chars=300)
    assert len(result) <= 304
    assert result.endswith("…")


def test_first_paragraph_empty_input():
    assert _first_paragraph("") == ""


def test_team_code_known_aliases():
    assert _team_code("Vitality") == "VIT"
    assert _team_code("Natus Vincere") == "NAVI"
    assert _team_code("The MongolZ") == "MZ"
    assert _team_code("FaZe Clan") == "FAZE"


def test_team_code_unknown_team_uses_first_letters():
    assert _team_code("Random Esports") == "RAN"


def test_team_code_handles_empty():
    assert _team_code(None) == "??"
    assert _team_code("") == "??"
    assert _team_code("123") == "??"


def test_compute_issue_number_starts_at_one_for_empty_output(tmp_path, monkeypatch):
    from datetime import date as _date

    from overpass.delivery import html as html_module

    monkeypatch.setattr(html_module, "_OUTPUT_DIR", tmp_path)
    assert html_module._compute_issue_number(_date(2026, 4, 23)) == 1


def test_compute_issue_number_counts_distinct_briefing_files(tmp_path, monkeypatch):
    from datetime import date as _date

    from overpass.delivery import html as html_module

    monkeypatch.setattr(html_module, "_OUTPUT_DIR", tmp_path)
    for name in ("2026-04-20.html", "2026-04-21.html", "2026-04-22.html"):
        (tmp_path / name).write_text("<html></html>", encoding="utf-8")
    # Today doesn't yet have a file; it still counts as the next issue.
    assert html_module._compute_issue_number(_date(2026, 4, 23)) == 4
    # Re-rendering an existing date doesn't double-count.
    assert html_module._compute_issue_number(_date(2026, 4, 22)) == 3


def test_ticker_chips_empty_without_matches():
    digest = DigestOutput(summary_line="x", sections={})
    assert _build_ticker_chips(digest) == []


def test_ticker_chips_count_live_upset_and_watch():
    live_match = _match()
    live_match.metadata["flags"] = ["live", "watch"]
    upset_match = _match()
    upset_match.metadata["flags"] = ["upset", "final"]

    digest = DigestOutput(
        summary_line="x",
        sections={"Matches": SectionOutput(intro="", items=[live_match, upset_match])},
    )
    chips = _build_ticker_chips(digest)
    kinds = [c["kind"] for c in chips]
    assert "live" in kinds
    assert "amber" in kinds
    assert "up" in kinds
