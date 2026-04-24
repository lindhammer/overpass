"""Parse a Liquipedia tournament page for a specific matchup."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from overpass.liquipedia.models import LiquipediaMap, LiquipediaMatch

logger = logging.getLogger("overpass.liquipedia.matches")

_MATCH_NODE_SELECTORS = (
    ".brkts-match, .brkts-matchlist-match, .bracket-game, .matchlist .match-row"
)
_OPPONENT_ENTRY_SELECTORS = (
    ".brkts-opponent-entry, .bracket-popup-body-element, .matchlist-opponent"
)
_TEAM_NAME_SELECTORS_PER_ENTRY = (
    ".name.hidden-xs, .name, .team-template-text,"
    " .team-template-team-short, .team-template-team2-short"
)
_SCORE_SELECTORS_PER_ENTRY = (
    ".brkts-opponent-score-inner, .brkts-opponent-score, .score"
)
_MAP_ROW_SELECTORS = (
    ".brkts-popup-body-game, .brkts-popup-body-grid-row, .bracket-popup-body-element"
)
_MAP_NAME_LINK_SELECTORS = (
    ".brkts-popup-body-game-mapname, .bracket-popup-game-map,"
    " .brkts-popup-spaced a[title]"
)
_MAP_MAIN_SCORE_SELECTORS = ".brkts-popup-body-detailed-scores-main-score"
_MAP_SCORE_PATTERN = re.compile(r"(\d+)\s*[-:\u2013]\s*(\d+)")
_SUFFIXES_TO_STRIP = ("esports", "gaming", "team", "club")
_TEAM_ALIASES = {
    "betclic": "apogee",
    "eyeballers": "eye",
}


def parse_match_from_tournament_page(
    html: str, team1_name: str, team2_name: str
) -> LiquipediaMatch | None:
    """Return the unique matchup of (team1, team2) on this page, or None."""
    if not html or not team1_name or not team2_name:
        return None

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[LiquipediaMatch] = []

    for node in soup.select(_MATCH_NODE_SELECTORS):
        match = _parse_match_node(node)
        if match is None:
            continue
        if not _matches_pair(match, team1_name, team2_name):
            continue
        # Orient the match so team1 in the result corresponds to the requested team1.
        oriented = _orient_to(match, team1_name)
        candidates.append(oriented)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            "Ambiguous Liquipedia match for %s vs %s (%d candidates)",
            team1_name, team2_name, len(candidates),
        )
    return None


def _parse_match_node(node: Tag) -> LiquipediaMatch | None:
    if "brkts-matchlist-match" in (node.get("class") or []):
        return _parse_matchlist_node(node)

    entries = node.select(_OPPONENT_ENTRY_SELECTORS)
    if len(entries) < 2:
        return None

    team_names: list[str] = []
    scores: list[int] = []
    for entry in entries[:2]:
        name_node = entry.select_one(_TEAM_NAME_SELECTORS_PER_ENTRY)
        score_node = entry.select_one(_SCORE_SELECTORS_PER_ENTRY)
        if name_node is None or score_node is None:
            return None
        name = _clean(name_node.get_text(" ", strip=True))
        score_text = _clean(score_node.get_text(" ", strip=True))
        if not name:
            return None
        try:
            score = int(score_text)
        except ValueError:
            return None
        team_names.append(name)
        scores.append(score)

    raw_t1, raw_t2 = team_names[0], team_names[1]
    s1, s2 = scores[0], scores[1]

    maps = _parse_maps(node)
    winner = raw_t1 if s1 > s2 else raw_t2 if s2 > s1 else None

    return LiquipediaMatch(
        team1_name=raw_t1,
        team2_name=raw_t2,
        team1_score=s1,
        team2_score=s2,
        winner_name=winner,
        maps=maps,
    )


def _parse_matchlist_node(node: Tag) -> LiquipediaMatch | None:
    opponent_cells = node.find_all(
        class_="brkts-matchlist-opponent",
        recursive=False,
    )
    score_cells = node.find_all(
        class_="brkts-matchlist-score",
        recursive=False,
    )
    if len(opponent_cells) < 2 or len(score_cells) < 2:
        return None

    team_names: list[str] = []
    for cell in (opponent_cells[0], opponent_cells[-1]):
        name_node = cell.select_one(_TEAM_NAME_SELECTORS_PER_ENTRY)
        if name_node is None:
            return None
        name = _clean(name_node.get_text(" ", strip=True))
        if not name:
            return None
        team_names.append(name)

    scores: list[int] = []
    for cell in (score_cells[0], score_cells[-1]):
        text = _clean(cell.get_text(" ", strip=True))
        try:
            scores.append(int(text))
        except ValueError:
            return None

    raw_t1, raw_t2 = team_names[0], team_names[1]
    s1, s2 = scores[0], scores[1]
    winner = raw_t1 if s1 > s2 else raw_t2 if s2 > s1 else None

    return LiquipediaMatch(
        team1_name=raw_t1,
        team2_name=raw_t2,
        team1_score=s1,
        team2_score=s2,
        winner_name=winner,
        maps=_parse_maps(node),
    )


def _parse_maps(node: Tag) -> list[LiquipediaMap]:
    maps: list[LiquipediaMap] = []
    for map_node in node.select(_MAP_ROW_SELECTORS):
        name_node = map_node.select_one(_MAP_NAME_LINK_SELECTORS)
        if name_node is None:
            continue
        # Skip vetoed/cancelled maps (rendered with <s>strikethrough</s>).
        if name_node.find_parent("s") is not None:
            continue
        name = _clean(name_node.get_text(" ", strip=True))
        if not name:
            continue

        main_scores = map_node.select(_MAP_MAIN_SCORE_SELECTORS)
        t1: int | None = None
        t2: int | None = None
        if len(main_scores) >= 2:
            t1_text = _clean(main_scores[0].get_text(" ", strip=True))
            t2_text = _clean(main_scores[1].get_text(" ", strip=True))
            if not t1_text or not t2_text:
                continue
            try:
                t1 = int(t1_text)
                t2 = int(t2_text)
            except ValueError:
                t1 = t2 = None

        if t1 is None or t2 is None:
            text = _clean(map_node.get_text(" ", strip=True))
            m = _MAP_SCORE_PATTERN.search(text)
            if m is None:
                continue
            t1 = int(m.group(1))
            t2 = int(m.group(2))

        maps.append(LiquipediaMap(name=name, team1_score=t1, team2_score=t2))
    return maps


def _matches_pair(match: LiquipediaMatch, want_t1: str, want_t2: str) -> bool:
    a = _normalize(match.team1_name)
    b = _normalize(match.team2_name)
    x = _normalize(want_t1)
    y = _normalize(want_t2)
    return {a, b} == {x, y}


def _orient_to(match: LiquipediaMatch, want_t1: str) -> LiquipediaMatch:
    if _normalize(match.team1_name) == _normalize(want_t1):
        return match
    return LiquipediaMatch(
        team1_name=match.team2_name,
        team2_name=match.team1_name,
        team1_score=match.team2_score,
        team2_score=match.team1_score,
        winner_name=match.winner_name,
        maps=[
            LiquipediaMap(name=m.name, team1_score=m.team2_score, team2_score=m.team1_score)
            for m in match.maps
        ],
    )


def _normalize(name: str) -> str:
    n = name.casefold().strip()
    if n.startswith("team "):
        n = n[5:]
    for suffix in _SUFFIXES_TO_STRIP:
        if n.endswith(f" {suffix}"):
            n = n[: -(len(suffix) + 1)]
    n = _TEAM_ALIASES.get(n, n)
    return n.strip()


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
