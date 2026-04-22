from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from overpass.hltv.matches import parse_match_detail, parse_results_listing
from overpass.hltv.models import (
    HLTVMatchDetail,
    HLTVMatchMapResult,
    HLTVMatchPlayerStat,
    HLTVMatchResult,
    HLTVMatchVetoEntry,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_parse_results_listing_extracts_recent_match_metadata() -> None:
    items = parse_results_listing(
        _read_fixture("hltv_results.html"),
        base_url="https://www.hltv.org",
    )

    assert all(type(item) is HLTVMatchResult for item in items)
    assert all(not isinstance(item, HLTVMatchDetail) for item in items)
    assert items == [
        HLTVMatchResult(
            external_id="2412345",
            url="https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
            team1_name="Spirit",
            team2_name="FaZe",
            team1_score=2,
            team2_score=1,
            winner_name="Spirit",
            event_name="BLAST Open Lisbon 2026",
            format="bo3",
            played_at=datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc),
        ),
        HLTVMatchResult(
            external_id="2412346",
            url="https://www.hltv.org/matches/2412346/vitality-vs-mouz-blast-open-lisbon-2026",
            team1_name="Vitality",
            team2_name="MOUZ",
            team1_score=2,
            team2_score=0,
            winner_name="Vitality",
            event_name="BLAST Open Lisbon 2026",
            format="bo3",
            played_at=datetime(2026, 4, 21, 20, 30, tzinfo=timezone.utc),
        ),
    ]


def test_parse_results_listing_ignores_non_format_map_text_values() -> None:
    html = """
    <a class="a-reset" href="/matches/2412347/spirit-vs-faze-blast-open-lisbon-2026">
      <div class="result-con">
        <div class="time" data-datetime="2026-04-21T21:00:00+00:00"></div>
        <div class="team team1">Spirit</div>
        <div class="result-score"><span>2</span><span>0</span></div>
        <div class="team team2">FaZe</div>
        <div class="map-text">d2</div>
        <div class="event-name">BLAST Open Lisbon 2026</div>
      </div>
    </a>
    """

    items = parse_results_listing(html, base_url="https://www.hltv.org")

    assert items == [
        HLTVMatchResult(
            external_id="2412347",
            url="https://www.hltv.org/matches/2412347/spirit-vs-faze-blast-open-lisbon-2026",
            team1_name="Spirit",
            team2_name="FaZe",
            team1_score=2,
            team2_score=0,
            winner_name="Spirit",
            event_name="BLAST Open Lisbon 2026",
            format=None,
            played_at=datetime(2026, 4, 21, 21, 0, tzinfo=timezone.utc),
        )
    ]


def test_parse_results_listing_extracts_team_ranks_when_present() -> None:
    html = """
    <a class="a-reset" href="/matches/2412348/falcons-vs-furia-iem-rio-2026">
      <div class="result-con">
        <div class="time" data-datetime="2026-04-21T22:00:00+00:00"></div>
        <div class="team team1">Falcons <span class="team-rank">#4</span></div>
        <div class="result-score"><span>2</span><span>1</span></div>
        <div class="team team2">FURIA <span class="team-rank">#16</span></div>
        <div class="map-text">bo3</div>
        <div class="event-name">IEM Rio 2026</div>
      </div>
    </a>
    """

    items = parse_results_listing(html, base_url="https://www.hltv.org")

    assert items == [
        HLTVMatchResult(
            external_id="2412348",
            url="https://www.hltv.org/matches/2412348/falcons-vs-furia-iem-rio-2026",
            team1_name="Falcons",
            team2_name="FURIA",
            team1_score=2,
            team2_score=1,
            winner_name="Falcons",
            event_name="IEM Rio 2026",
            format="bo3",
            played_at=datetime(2026, 4, 21, 22, 0, tzinfo=timezone.utc),
            team1_rank=4,
            team2_rank=16,
        )
    ]


def test_parse_match_detail_hydrates_listing_item_with_maps_veto_and_player_stats() -> None:
    listing_item = parse_results_listing(
        _read_fixture("hltv_results.html"),
        base_url="https://www.hltv.org",
    )[0]

    match = parse_match_detail(
        _read_fixture("hltv_match_detail.html"),
        listing_item=listing_item,
        base_url="https://www.hltv.org",
    )

    assert match == HLTVMatchDetail(
        external_id="2412345",
        url="https://www.hltv.org/matches/2412345/spirit-vs-faze-blast-open-lisbon-2026",
        team1_name="Spirit",
        team2_name="FaZe",
        team1_score=2,
        team2_score=1,
        winner_name="Spirit",
        event_name="BLAST Open Lisbon 2026",
        format="bo3",
        played_at=datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc),
        maps=[
            HLTVMatchMapResult(
                name="Mirage",
                team1_score=13,
                team2_score=9,
                winner_name="Spirit",
            ),
            HLTVMatchMapResult(
                name="Ancient",
                team1_score=11,
                team2_score=13,
                winner_name="FaZe",
            ),
            HLTVMatchMapResult(
                name="Anubis",
                team1_score=13,
                team2_score=8,
                winner_name="Spirit",
            ),
        ],
        veto=[
            HLTVMatchVetoEntry(team_name="Spirit", action="removed", map_name="Inferno"),
            HLTVMatchVetoEntry(team_name="FaZe", action="removed", map_name="Nuke"),
            HLTVMatchVetoEntry(team_name="Spirit", action="picked", map_name="Mirage"),
            HLTVMatchVetoEntry(team_name="FaZe", action="picked", map_name="Ancient"),
            HLTVMatchVetoEntry(team_name=None, action="left_over", map_name="Anubis"),
        ],
        player_stats=[
            HLTVMatchPlayerStat(
                team_name="Spirit",
                player_name="donk",
                kills=47,
                deaths=30,
                adr=101.2,
                kast=78.4,
                rating=1.39,
            ),
            HLTVMatchPlayerStat(
                team_name="Spirit",
                player_name="sh1ro",
                kills=41,
                deaths=28,
                adr=84.3,
                kast=74.5,
                rating=1.22,
            ),
            HLTVMatchPlayerStat(
                team_name="FaZe",
                player_name="broky",
                kills=38,
                deaths=39,
                adr=77.1,
                kast=68.6,
                rating=1.03,
            ),
            HLTVMatchPlayerStat(
                team_name="FaZe",
                player_name="frozen",
                kills=31,
                deaths=42,
                adr=69.8,
                kast=62.7,
                rating=0.91,
            ),
        ],
    )


def test_parse_match_detail_accepts_numbered_veto_rows() -> None:
    listing_item = parse_results_listing(
        _read_fixture("hltv_results.html"),
        base_url="https://www.hltv.org",
    )[0]
    html = _read_fixture("hltv_match_detail.html").replace(
        """          <div>Spirit removed Inferno</div>
          <div>FaZe removed Nuke</div>
          <div>Spirit picked Mirage</div>
          <div>FaZe picked Ancient</div>
          <div>Anubis was left over</div>""",
        """          <div>1. Spirit removed Inferno</div>
          <div>2. FaZe removed Nuke</div>
          <div>3. Spirit picked Mirage</div>
          <div>4. FaZe picked Ancient</div>
          <div>5. Anubis was left over</div>""",
    )

    match = parse_match_detail(
        html,
        listing_item=listing_item,
        base_url="https://www.hltv.org",
    )

    assert match.veto == [
        HLTVMatchVetoEntry(team_name="Spirit", action="removed", map_name="Inferno"),
        HLTVMatchVetoEntry(team_name="FaZe", action="removed", map_name="Nuke"),
        HLTVMatchVetoEntry(team_name="Spirit", action="picked", map_name="Mirage"),
        HLTVMatchVetoEntry(team_name="FaZe", action="picked", map_name="Ancient"),
        HLTVMatchVetoEntry(team_name=None, action="left_over", map_name="Anubis"),
    ]
