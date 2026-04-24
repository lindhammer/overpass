"""Parse HLTV's /matches page for upcoming-match listings."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from overpass.hltv.models import HLTVUpcomingMatch

_MATCH_ID_PATTERN = re.compile(r"/matches/(\d+)/")
_PLACEHOLDER_LOGO_FRAGMENTS = (
    "/dynamic-svg/teamplaceholder",
    "teamplaceholder?letter",
)


def parse_upcoming_listing(
    html: str,
    base_url: str = "https://www.hltv.org",
) -> list[HLTVUpcomingMatch]:
    """Parse `/matches` and return upcoming (non-live) scheduled matches."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[HLTVUpcomingMatch] = []
    seen_ids: set[str] = set()

    for node in soup.select(".matches-list-section .match"):
        try:
            match = _parse_match(node, base_url)
        except Exception:
            continue
        if match is None or match.external_id in seen_ids:
            continue
        seen_ids.add(match.external_id)
        out.append(match)

    return out


def _parse_match(node: Tag, base_url: str) -> HLTVUpcomingMatch | None:
    href = None
    for link in node.select("a[href*='/matches/']"):
        candidate = link.get("href")
        if isinstance(candidate, str) and "/matches/" in candidate:
            href = candidate
            break
    if not href:
        return None
    external_id = _extract_match_id(href)
    if external_id is None:
        return None

    time_node = node.select_one(".match-time[data-unix]")
    if time_node is None:
        return None
    raw_unix = time_node.get("data-unix")
    if not raw_unix:
        return None
    try:
        starts_at = datetime.fromtimestamp(int(raw_unix) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None

    team1_node = node.select_one(".match-team.team1 .match-teamname") or node.select_one(".match-team.team1")
    team2_node = node.select_one(".match-team.team2 .match-teamname") or node.select_one(".match-team.team2")
    if team1_node is None or team2_node is None:
        return None
    team1_name = _clean(team1_node.get_text(" ", strip=True))
    team2_name = _clean(team2_node.get_text(" ", strip=True))
    if not team1_name or not team2_name:
        return None
    # Skip matches that aren't yet drawn ("TBD" placeholders aren't useful).
    if team1_name.upper() == "TBD" or team2_name.upper() == "TBD":
        return None

    event_node = node.select_one(".match-event[data-event-headline], .match-event")
    event_name: str | None = None
    if event_node is not None:
        event_name = (event_node.get("data-event-headline") or "").strip() or None
        if event_name is None:
            event_name = _clean(event_node.get_text(" ", strip=True)) or None

    fmt_node = node.select_one(".match-meta")
    fmt = _clean(fmt_node.get_text(" ", strip=True)).lower() if fmt_node is not None else None
    if fmt and not re.fullmatch(r"bo[1-9]", fmt):
        fmt = None

    stage_node = node.select_one(".match-stage")
    stage = _clean(stage_node.get_text(" ", strip=True)) if stage_node is not None else None
    stage = stage or None

    team1_logo_url = _team_logo_url(node, ".match-team.team1", base_url)
    team2_logo_url = _team_logo_url(node, ".match-team.team2", base_url)

    return HLTVUpcomingMatch(
        external_id=external_id,
        url=urljoin(base_url, href),
        starts_at=starts_at,
        team1_name=team1_name,
        team2_name=team2_name,
        team1_logo_url=team1_logo_url,
        team2_logo_url=team2_logo_url,
        event_name=event_name,
        format=fmt,
        stage=stage,
    )


def _team_logo_url(node: Tag, scope_selector: str, base_url: str) -> str | None:
    container = node.select_one(scope_selector)
    if container is None:
        return None
    for img in container.select("img"):
        raw = img.get("data-src") or img.get("src")
        if not isinstance(raw, str):
            continue
        url = raw.strip()
        if not url:
            continue
        if any(frag in url for frag in _PLACEHOLDER_LOGO_FRAGMENTS):
            continue
        return urljoin(base_url, url)
    return None


def _extract_match_id(path: str) -> str | None:
    m = _MATCH_ID_PATTERN.search(path)
    return m.group(1) if m else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
