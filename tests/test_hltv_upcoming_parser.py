"""Tests for `parse_upcoming_listing` against the captured HLTV /matches fixture."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

from overpass.hltv.upcoming import parse_upcoming_listing

_FIXTURE = Path(__file__).parent / "fixtures" / "hltv_matches_upcoming.html"


def _load() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_parses_at_least_one_match():
    matches = parse_upcoming_listing(_load())
    assert len(matches) >= 10


def test_each_match_has_required_fields():
    matches = parse_upcoming_listing(_load())
    for m in matches:
        assert m.external_id.isdigit()
        assert m.url.startswith("https://www.hltv.org/matches/")
        assert m.starts_at.tzinfo == timezone.utc
        assert m.team1_name and m.team2_name
        assert m.team1_name.upper() != "TBD"
        assert m.team2_name.upper() != "TBD"


def test_external_ids_are_unique():
    matches = parse_upcoming_listing(_load())
    ids = [m.external_id for m in matches]
    assert len(ids) == len(set(ids))


def test_format_is_bo_or_none():
    matches = parse_upcoming_listing(_load())
    formats = {m.format for m in matches}
    for fmt in formats:
        if fmt is not None:
            assert fmt.startswith("bo") and fmt[2:].isdigit()


def test_event_names_populated():
    matches = parse_upcoming_listing(_load())
    with_event = [m for m in matches if m.event_name]
    assert len(with_event) == len(matches)


def test_team_logos_resolve_to_absolute_urls_when_present():
    matches = parse_upcoming_listing(_load())
    has_any_logo = False
    for m in matches:
        for url in (m.team1_logo_url, m.team2_logo_url):
            if url is None:
                continue
            has_any_logo = True
            assert url.startswith("http")
            assert "teamplaceholder" not in url
    assert has_any_logo, "expected at least one resolved team logo in fixture"


def test_recognized_top_team_present():
    """At least one well-known team should be in the trimmed fixture."""
    matches = parse_upcoming_listing(_load())
    teams = {m.team1_name for m in matches} | {m.team2_name for m in matches}
    big_teams = {"Vitality", "FaZe", "G2", "NAVI", "MOUZ", "Astralis", "Spirit", "The MongolZ"}
    assert teams & big_teams, f"expected one of {big_teams} in fixture, got {sorted(teams)[:20]}"


def test_starts_at_chronological_per_section():
    """Matches within a single time block share the same data-unix start."""
    matches = parse_upcoming_listing(_load())
    by_time: dict[str, int] = {}
    for m in matches:
        key = m.starts_at.isoformat()
        by_time[key] = by_time.get(key, 0) + 1
    # We expect multiple matches to share a start time (group-stage simul casts).
    grouped = [count for count in by_time.values() if count > 1]
    assert grouped, "expected at least one shared start-time bucket"


def test_handles_empty_html():
    assert parse_upcoming_listing("") == []
    assert parse_upcoming_listing("<html><body></body></html>") == []
