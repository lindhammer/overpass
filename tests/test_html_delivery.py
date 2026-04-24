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
from overpass.editorial.digest import DigestOutput, MatchBlurb, SectionOutput

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
            "subreddit": "GlobalOffensive",
            "author": "clipper123",
            "upvotes": 4200,
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
        metadata={
            "description": "Full recap of the major final.",
            "duration": "1:42:10",
        },
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
            "channel": "HLTV",
            "duration": "12:34",
            "description": "Best plays from the past week.",
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
            "category_label": "Match Recap",
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
            "event": "BLAST Open Lisbon 2026",
            "format": "Best of 3",
            "flags": ["watch", "final"],
            "maps": [
                {"name": "Mirage", "team1_score": 13, "team2_score": 9, "winner_name": "Spirit"},
                {"name": "Ancient", "team1_score": 11, "team2_score": 13, "winner_name": "FaZe"},
                {"name": "Anubis", "team1_score": 13, "team2_score": 8, "winner_name": "Spirit"},
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
            "changes": [
                "Fixed a pixel walk on Inferno banana.",
                "XM1014 rate of fire reduced by 6%.",
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


def test_section_titles_appear_uppercased():
    """Section blocks render with their title uppercased in the section header."""
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    # Both Videos + Podcasts present → merged into "Content Drops"
    for label in ("TOP CLIPS", "PATCH NOTES", "CONTENT DROPS"):
        assert label in html, f"Section title {label!r} missing from HTML"


def test_match_and_news_section_titles_render():
    digest = _digest_with_hltv_sections()
    html = render_briefing(digest, _DATE)
    assert "MATCH RESULTS" in html
    # "Roster Moves & News" — ampersand gets HTML-escaped.
    assert "ROSTER MOVES" in html


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


def test_clip_upvotes_appear():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "4200" in html
    assert "r/GlobalOffensive" in html
    assert "u/clipper123" in html


def test_podcast_duration_appears_in_drop():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "1:42:10" in html
    assert "PODCAST" in html  # drop-kind ribbon


def test_video_drop_renders_channel_and_duration():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "Top 10 Plays This Week" in html
    assert "12:34" in html
    assert "HLTV" in html


def test_patch_entries_render_version_and_changes():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "1.40.1.9" in html
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
    assert "OVERPASS" in html
    for label in ("TOP CLIPS", "MATCH RESULTS", "PATCH NOTES"):
        assert label not in html


def test_only_patches_section_renders():
    digest = DigestOutput(
        summary_line="Only patches today.",
        sections={"Patches": SectionOutput(intro="", items=[_patch()])},
    )
    html = render_briefing(digest, _DATE)
    assert "CS2 Update – April 10" in html
    assert "TOP CLIPS" not in html
    assert "MATCH RESULTS" not in html


def test_date_appears_in_html():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    assert "2026" in html
    # Topbar uses upper-case abbreviated date e.g. "FRI 10 APR 2026"
    assert "APR" in html


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

    assert "MATCH RESULTS" in html
    assert "Spirit" in html
    assert "FaZe" in html
    assert "BLAST Open Lisbon 2026" in html
    # Map breakdown is rendered inline as "<MapName> <s1>-<s2>".
    assert "Mirage 13-9" in html
    assert "Anubis 13-8" in html


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

    # Logos render inside the .crest.has-logo wrapper.
    assert 'class="crest has-logo"' in collapsed
    assert 'src="https://img.example/spirit.png"' in collapsed
    assert 'alt="Spirit logo"' in collapsed
    assert 'src="https://img.example/faze.png"' in collapsed
    assert 'alt="FaZe logo"' in collapsed


def test_match_section_falls_back_to_initial_crest_without_team_logos():
    digest = _digest_with_hltv_sections()

    html = html_lib.unescape(render_briefing(digest, _DATE))
    collapsed = " ".join(html.split())

    # Without logo URL → bare crest with the short team code as text.
    assert 'class="crest" data-team="SP"' in collapsed
    assert ">SP<" in collapsed


def test_news_section_renders_article():
    digest = _digest_with_hltv_sections()
    html = html_lib.unescape(render_briefing(digest, _DATE))

    assert "ROSTER MOVES" in html
    assert "FaZe win Cologne opener" in html
    assert "Match Recap" in html  # category_label ribbon
    assert (
        "Finn \"karrigan\" Andersen's side opened the event with a comfortable series win."
        in html
    )


def test_match_section_renders_before_clips():
    digest = _digest_with_hltv_sections()
    html = render_briefing(digest, _DATE)
    assert html.index("MATCH RESULTS") < html.index("TOP CLIPS")


def test_per_match_blurbs_are_rendered():
    match = _match()
    digest = DigestOutput(
        summary_line="x",
        sections={"Matches": SectionOutput(intro="", items=[match])},
        per_match_blurbs={
            match.url: MatchBlurb(
                tagline="THREE-MAP DECIDER",
                highlight="ZywOo carried the late Ancient comeback.",
            ),
        },
    )

    html = render_briefing(digest, _DATE)

    assert "THREE-MAP DECIDER" in html
    assert "ZywOo carried the late Ancient comeback." in html


def test_match_renders_fallback_tagline_when_blurb_missing():
    """No per-match blurb → falls back to deterministic tagline based on score diff."""
    digest = DigestOutput(
        summary_line="x",
        sections={"Matches": SectionOutput(intro="", items=[_match()])},
    )
    html = render_briefing(digest, _DATE)
    # Score diff = 1 (2-1) with non-"1"-format → "DECIDER".
    assert "DECIDER" in html


def test_issue_number_appears_in_topbar():
    digest = _full_digest()
    html = render_briefing(digest, _DATE)
    expected = _compute_issue_number(_DATE)
    assert f"Issue {expected}" in html


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


# ── This Day in CS ──────────────────────────────

from overpass.history.models import HistoryEntry


def _digest_with_one_section() -> DigestOutput:
    """Minimal digest the renderer accepts (reuses existing fixtures upstream)."""
    return DigestOutput(
        summary_line="Test summary.",
        sections={"Reddit Clips": SectionOutput(intro="", items=[_clip()])},
    )


def test_render_briefing_includes_this_day_section_when_entry_passed():
    digest = _digest_with_one_section()
    entry = HistoryEntry(
        year=2018,
        headline="Cloud9 win the ELEAGUE Boston Major",
        narrative="C9 beat FaZe 2-1 in Boston after triple OT on Inferno.",
        visual_label="BOS '18",
        source_url="https://liquipedia.net/counterstrike/ELEAGUE/Major/2018",
    )
    html = render_briefing(digest, _DATE, this_day=entry)
    assert "This Day in CS" in html
    assert "Cloud9 win the ELEAGUE Boston Major" in html
    assert "C9 beat FaZe 2-1 in Boston" in html
    assert "BOS &#39;18" in html or "BOS '18" in html
    # date_label is computed from the entry year + briefing month/day:
    assert "April 10, 2018" in html
    assert "https://liquipedia.net/counterstrike/ELEAGUE/Major/2018" in html


def test_render_briefing_omits_this_day_section_when_none():
    digest = _digest_with_one_section()
    html = render_briefing(digest, _DATE)
    assert "This Day in CS" not in html


def test_render_briefing_falls_back_to_year_when_no_visual_label():
    digest = _digest_with_one_section()
    entry = HistoryEntry(
        year=2018,
        headline="x",
        narrative="y",
    )
    html = render_briefing(digest, _DATE, this_day=entry)
    # The template renders `visual_label or year`; with no label, "2018" appears.
    assert "2018" in html

