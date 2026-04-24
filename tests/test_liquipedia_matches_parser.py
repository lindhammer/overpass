"""parse_match_from_tournament_page tests against a real captured fixture.

Fixture: tests/fixtures/liquipedia_tournament.html
Recorded match-up (from Task 0 Step 4):
  team1_name (HLTV spelling): 9z
  team2_name (Liquipedia spelling): ALKA GAMING
  expected score: 2 - 0
  expected maps: [("Dust II", 13, 6), ("Nuke", 13, 7)]
"""

from __future__ import annotations

from pathlib import Path

from overpass.liquipedia.matches import parse_match_from_tournament_page

EXPECTED_TEAM1 = "9z"
EXPECTED_TEAM2 = "ALKA GAMING"
EXPECTED_T1_SCORE = 2
EXPECTED_T2_SCORE = 0
EXPECTED_MAPS = [("Dust II", 13, 6), ("Nuke", 13, 7)]

_FIXTURE = Path(__file__).parent / "fixtures" / "liquipedia_tournament.html"


def _html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_parser_finds_known_matchup() -> None:
    match = parse_match_from_tournament_page(_html(), EXPECTED_TEAM1, EXPECTED_TEAM2)
    assert match is not None
    assert match.team1_score == EXPECTED_T1_SCORE
    assert match.team2_score == EXPECTED_T2_SCORE
    assert [(m.name, m.team1_score, m.team2_score) for m in match.maps] == EXPECTED_MAPS


def test_parser_normalises_team_name_suffixes() -> None:
    # Same matchup, but with a "Team " prefix that should normalise away.
    match = parse_match_from_tournament_page(
        _html(), f"Team {EXPECTED_TEAM1}", EXPECTED_TEAM2
    )
    assert match is not None
    assert match.team1_score == EXPECTED_T1_SCORE


def test_parser_matches_known_liquipedia_abbreviations() -> None:
    html = """\
    <div class="brkts-match">
      <div class="brkts-opponent-entry">
        <span class="name">Walczaki</span>
        <span class="brkts-opponent-score-inner">2</span>
      </div>
      <div class="brkts-opponent-entry">
        <span class="name">EYE</span>
        <span class="brkts-opponent-score-inner">1</span>
      </div>
    </div>
    """

    match = parse_match_from_tournament_page(html, "Walczaki", "EYEBALLERS")

    assert match is not None
    assert match.team1_name == "Walczaki"
    assert match.team2_name == "EYE"


def test_parser_matches_sponsor_short_name_to_liquipedia_team_name() -> None:
    html = """\
    <div class="brkts-match">
      <div class="brkts-opponent-entry">
        <span class="name">Monte</span>
        <span class="brkts-opponent-score-inner">2</span>
      </div>
      <div class="brkts-opponent-entry">
        <span class="name">Apogee Esports</span>
        <span class="brkts-opponent-score-inner">0</span>
      </div>
    </div>
    """

    match = parse_match_from_tournament_page(html, "Monte", "Betclic")

    assert match is not None
    assert match.team1_name == "Monte"
    assert match.team2_name == "Apogee Esports"


def test_parser_reads_matchlist_layout_with_separate_score_cells() -> None:
    html = """\
    <div class="brkts-matchlist-match">
      <div class="brkts-matchlist-opponent">
        <span class="name">Walczaki</span>
      </div>
      <div class="brkts-matchlist-score">
        <div class="brkts-matchlist-cell-content">0</div>
      </div>
      <div class="brkts-matchlist-score">
        <div class="brkts-matchlist-cell-content">2</div>
      </div>
      <div class="brkts-matchlist-opponent">
        <span class="name">EYE</span>
      </div>
    </div>
    """

    match = parse_match_from_tournament_page(html, "Walczaki", "EYEBALLERS")

    assert match is not None
    assert match.team1_score == 0
    assert match.team2_score == 2


def test_parser_returns_none_when_no_match_found() -> None:
    match = parse_match_from_tournament_page(_html(), "Nonexistent A", "Nonexistent B")
    assert match is None


def test_parser_returns_none_when_html_has_no_match_nodes() -> None:
    match = parse_match_from_tournament_page("<html><body>nothing</body></html>", "A", "B")
    assert match is None
