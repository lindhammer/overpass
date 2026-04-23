"""Pure HTML parsers for HLTV results and match detail pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from overpass.hltv.models import (
    HLTVMatchDetail,
    HLTVMatchMapResult,
    HLTVMatchPlayerStat,
    HLTVMatchResult,
    HLTVMatchVetoEntry,
)

_MATCH_ID_PATTERN = re.compile(r"/matches/(\d+)/")
_PLAYER_KD_PATTERN = re.compile(r"(?P<kills>\d+)-(?P<deaths>\d+)")
_MATCH_FORMAT_PATTERN = re.compile(r"bo[135]", re.IGNORECASE)
_VETO_PREFIX_PATTERN = re.compile(r"^\d+\.\s*")
_TEAM_VETO_PATTERN = re.compile(r"(?P<team>.+?) (?P<action>removed|picked) (?P<map>.+)")
_LEFTOVER_VETO_PATTERN = re.compile(r"(?P<map>.+?) was left over")


def parse_results_listing(html: str, base_url: str = "https://www.hltv.org") -> list[HLTVMatchResult]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[HLTVMatchResult] = []

    for link in soup.select("a.a-reset[href*='/matches/']"):
        result_node = link.select_one(".result-con, .result")
        time_node = _select_result_time_node(link)
        team_nodes = _select_team_nodes(link)
        score_nodes = link.select(".result-score span")
        event_node = link.select_one(".event-name")
        format_node = link.select_one(".map-text")
        href = link.get("href")

        if (
            result_node is None
            or time_node is None
            or len(team_nodes) < 2
            or len(score_nodes) < 2
            or event_node is None
            or not href
        ):
            continue

        external_id = _extract_match_id(href)
        if external_id is None:
            continue

        team1_score = _parse_int(score_nodes[0].get_text(" ", strip=True))
        team2_score = _parse_int(score_nodes[1].get_text(" ", strip=True))
        team1_name, team1_rank = _parse_team_name_and_rank(team_nodes[0])
        team2_name, team2_rank = _parse_team_name_and_rank(team_nodes[1])

        items.append(
            HLTVMatchResult(
                external_id=external_id,
                url=urljoin(base_url, href),
                team1_name=team1_name,
                team2_name=team2_name,
                team1_rank=team1_rank,
                team2_rank=team2_rank,
                team1_score=team1_score,
                team2_score=team2_score,
                winner_name=_determine_winner(team1_name, team2_name, team1_score, team2_score),
                event_name=_clean_text(event_node.get_text(" ", strip=True)),
                format=(
                    _normalize_match_format(format_node.get_text(" ", strip=True))
                    if format_node is not None
                    else None
                ),
                played_at=_parse_datetime_node(time_node),
            )
        )

    return items


def parse_ranked_team_names(html: str, limit: int) -> list[str]:
    if limit <= 0:
        return []

    soup = BeautifulSoup(html, "html.parser")
    team_names: list[str] = []
    seen_names: set[str] = set()

    for node in soup.select(".ranked-team .teamLine .name, .teamLine .name"):
        team_name = _clean_text(node.get_text(" ", strip=True))
        normalized_name = team_name.casefold()
        if not team_name or normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        team_names.append(team_name)
        if len(team_names) >= limit:
            break

    return team_names


def _parse_team_name_and_rank(node: Tag) -> tuple[str, int | None]:
    rank_node = node.select_one(".team-rank")
    team_rank = _parse_rank(rank_node.get_text(" ", strip=True)) if rank_node is not None else None
    if rank_node is not None:
        rank_node.extract()
    return _clean_text(node.get_text(" ", strip=True)), team_rank


def parse_match_detail(
    html: str,
    match_url: str | None = None,
    listing_item: HLTVMatchResult | None = None,
    base_url: str = "https://www.hltv.org",
) -> HLTVMatchDetail:
    soup = BeautifulSoup(html, "html.parser")

    canonical_node = soup.select_one("link[rel='canonical'][href]")
    resolved_match_url = match_url
    if resolved_match_url is None and canonical_node is not None:
        resolved_match_url = canonical_node.get("href")
    if resolved_match_url is None and listing_item is not None:
        resolved_match_url = listing_item.url
    if resolved_match_url is None:
        raise ValueError("Could not determine HLTV match url")

    resolved_match_url = urljoin(base_url, resolved_match_url)
    external_id = _extract_match_id(resolved_match_url)
    if external_id is None:
        raise ValueError("Could not determine HLTV match id")
    if listing_item is not None and listing_item.external_id != external_id:
        raise ValueError("Listing item does not match parsed HLTV match")

    team1_name = _select_required_text(soup, ".team1-gradient .teamName")
    team2_name = _select_required_text(soup, ".team2-gradient .teamName")
    team1_score = _select_required_int(soup, ".team1-gradient .won, .team1-gradient .lost")
    team2_score = _select_required_int(soup, ".team2-gradient .won, .team2-gradient .lost")
    event_name = _select_optional_text(soup, ".timeAndEvent .event, .timeAndEvent .text")
    format_name = _select_optional_text(soup, ".timeAndEvent .format")
    time_node = soup.select_one(".timeAndEvent .time[data-datetime], .timeAndEvent .time[data-unix]")

    if event_name is None and listing_item is not None:
        event_name = listing_item.event_name
    if format_name is None and listing_item is not None:
        format_name = listing_item.format

    return HLTVMatchDetail(
        external_id=external_id,
        url=resolved_match_url,
        team1_name=team1_name,
        team2_name=team2_name,
        team1_score=team1_score,
        team2_score=team2_score,
        winner_name=_determine_winner(team1_name, team2_name, team1_score, team2_score),
        event_name=event_name,
        format=format_name,
        played_at=_parse_datetime_node(time_node) if time_node is not None else listing_item.played_at if listing_item else None,
        maps=_parse_maps(soup, team1_name, team2_name),
        veto=_parse_veto(soup),
        player_stats=_parse_player_stats(soup),
    )


def _parse_maps(soup: BeautifulSoup, team1_name: str, team2_name: str) -> list[HLTVMatchMapResult]:
    maps: list[HLTVMatchMapResult] = []

    for map_node in soup.select(".mapholder"):
        map_name = _select_optional_text(map_node, ".mapname")
        score_nodes = map_node.select(".results-team-score")
        if map_name is None or len(score_nodes) < 2:
            continue

        team1_score_text = _clean_text(score_nodes[0].get_text(" ", strip=True))
        team2_score_text = _clean_text(score_nodes[1].get_text(" ", strip=True))
        # Unplayed maps in a BO3/BO5 series render as "-"; skip them.
        if not team1_score_text.isdigit() or not team2_score_text.isdigit():
            continue

        team1_score = int(team1_score_text)
        team2_score = int(team2_score_text)
        maps.append(
            HLTVMatchMapResult(
                name=map_name,
                team1_score=team1_score,
                team2_score=team2_score,
                winner_name=_determine_winner(team1_name, team2_name, team1_score, team2_score),
            )
        )

    return maps


def _parse_veto(soup: BeautifulSoup) -> list[HLTVMatchVetoEntry]:
    veto_entries: list[HLTVMatchVetoEntry] = []

    for veto_node in soup.select(".veto-box .padding > div"):
        text = _strip_veto_prefix(_clean_text(veto_node.get_text(" ", strip=True)))
        if not text:
            continue

        leftover_match = _LEFTOVER_VETO_PATTERN.fullmatch(text)
        if leftover_match is not None:
            veto_entries.append(
                HLTVMatchVetoEntry(
                    team_name=None,
                    action="left_over",
                    map_name=leftover_match.group("map"),
                )
            )
            continue

        team_match = _TEAM_VETO_PATTERN.fullmatch(text)
        if team_match is None:
            continue

        veto_entries.append(
            HLTVMatchVetoEntry(
                team_name=team_match.group("team"),
                action=team_match.group("action"),
                map_name=team_match.group("map"),
            )
        )

    return veto_entries


def _parse_player_stats(soup: BeautifulSoup) -> list[HLTVMatchPlayerStat]:
    player_stats: list[HLTVMatchPlayerStat] = []
    current_team_name: str | None = None

    for row in soup.select("table.totalstats tr"):
        if "team-row" in (row.get("class") or []):
            current_team_name = _clean_text(row.get_text(" ", strip=True))
            continue

        player_node = row.select_one(".player a")
        kd_node = row.select_one(".kd")
        adr_node = row.select_one(".adr")
        kast_node = row.select_one(".kast")
        rating_node = row.select_one(".rating")
        if (
            current_team_name is None
            or player_node is None
            or kd_node is None
            or adr_node is None
            or kast_node is None
            or rating_node is None
        ):
            continue

        kd_match = _PLAYER_KD_PATTERN.fullmatch(_clean_text(kd_node.get_text(" ", strip=True)))
        if kd_match is None:
            continue

        player_stats.append(
            HLTVMatchPlayerStat(
                team_name=current_team_name,
                player_name=_clean_text(player_node.get_text(" ", strip=True)),
                kills=int(kd_match.group("kills")),
                deaths=int(kd_match.group("deaths")),
                adr=float(_clean_text(adr_node.get_text(" ", strip=True))),
                kast=float(_clean_text(kast_node.get_text(" ", strip=True)).rstrip("%")),
                rating=float(_clean_text(rating_node.get_text(" ", strip=True))),
            )
        )

    return player_stats


def _extract_match_id(path_or_url: str) -> str | None:
    match = _MATCH_ID_PATTERN.search(path_or_url)
    if match is None:
        return None
    return match.group(1)


def _parse_datetime_node(node: BeautifulSoup) -> datetime:
    raw_value = node.get("data-datetime") or node.get("data-unix") or node.get("data-zonedgrouping-entry-unix")
    if raw_value is None:
        raise ValueError("Missing HLTV match datetime")
    if node.get("data-datetime") is not None:
        return _parse_iso_datetime(raw_value)
    return datetime.fromtimestamp(int(raw_value) / 1000, tz=timezone.utc)


def _select_result_time_node(link: Tag) -> Tag | None:
    time_node = link.select_one(".time[data-datetime], .time[data-unix]")
    if time_node is not None:
        return time_node

    return link.find_parent("div", attrs={"data-zonedgrouping-entry-unix": True})


def _select_team_nodes(link: Tag) -> list[Tag]:
    team1_node = link.select_one(".team1 .team, .team.team1")
    team2_node = link.select_one(".team2 .team, .team.team2")
    if team1_node is not None and team2_node is not None:
        return [team1_node, team2_node]

    team_nodes = link.select(".team")
    return team_nodes[:2]


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_match_format(value: str) -> str | None:
    normalized = _clean_text(value).lower()
    if _MATCH_FORMAT_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _strip_veto_prefix(value: str) -> str:
    return _VETO_PREFIX_PATTERN.sub("", value)


def _select_required_text(node: BeautifulSoup, selector: str) -> str:
    value = _select_optional_text(node, selector)
    if value is None:
        raise ValueError(f"Missing required HLTV match field: {selector}")
    return value


def _select_optional_text(node: BeautifulSoup, selector: str) -> str | None:
    selected = node.select_one(selector)
    if selected is None:
        return None
    text = _clean_text(selected.get_text(" ", strip=True))
    return text or None


def _select_required_int(node: BeautifulSoup, selector: str) -> int:
    selected = node.select_one(selector)
    if selected is None:
        raise ValueError(f"Missing required HLTV match field: {selector}")
    return _parse_int(selected.get_text(" ", strip=True))


def _parse_int(value: str) -> int:
    return int(_clean_text(value))


def _parse_rank(value: str) -> int | None:
    normalized = _clean_text(value).lstrip("#")
    if not normalized.isdigit():
        return None
    return int(normalized)


def _determine_winner(team1_name: str, team2_name: str, team1_score: int, team2_score: int) -> str | None:
    if team1_score > team2_score:
        return team1_name
    if team2_score > team1_score:
        return team2_name
    return None


def _clean_text(value: str) -> str:
    return " ".join(value.split())
