"""Pure HTML parsers for HLTV news pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from overpass.hltv.models import HLTVNewsArticle, HLTVNewsListingItem

_ARTICLE_ID_PATTERN = re.compile(r"/news/(\d+)/")


def parse_news_listing(html: str, base_url: str = "https://www.hltv.org") -> list[HLTVNewsListingItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[HLTVNewsListingItem] = []

    for link in soup.select("a.article[href*='/news/']"):
        href = link.get("href")
        title_node = link.select_one(".newstext")
        time_node = link.select_one("time[datetime]")
        if not href or title_node is None or time_node is None:
            continue

        external_id = _extract_article_id(href)
        if external_id is None:
            continue

        teaser_node = link.select_one(".newstc")
        items.append(
            HLTVNewsListingItem(
                external_id=external_id,
                title=_clean_text(title_node.get_text(" ", strip=True)),
                url=urljoin(base_url, href),
                published_at=_parse_datetime(time_node["datetime"]),
                teaser=_clean_text(teaser_node.get_text(" ", strip=True)) if teaser_node is not None else None,
                thumbnail_url=_extract_thumbnail_url(link, base_url),
            )
        )

    return items


def parse_news_article(
    html: str,
    article_url: str | None = None,
    listing_item: HLTVNewsListingItem | None = None,
    base_url: str = "https://www.hltv.org",
) -> HLTVNewsArticle:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("h1.headline")
    author_node = soup.select_one(".article-info .author")
    time_node = soup.select_one(".article-info time[datetime]")
    if title_node is None or time_node is None:
        raise ValueError("Missing required HLTV article metadata")

    canonical_node = soup.select_one("link[rel='canonical'][href]")
    resolved_article_url = article_url
    if resolved_article_url is None and canonical_node is not None:
        resolved_article_url = canonical_node["href"]
    if resolved_article_url is None and listing_item is not None:
        resolved_article_url = listing_item.url
    if resolved_article_url is None:
        resolved_article_url = base_url

    resolved_article_url = urljoin(base_url, resolved_article_url)
    external_id = _extract_article_id(resolved_article_url)
    if external_id is None:
        raise ValueError("Could not determine HLTV article id")
    if listing_item is not None and listing_item.external_id != external_id:
        raise ValueError("Listing item does not match parsed HLTV article")

    body_text = _extract_body_text(soup)
    if not body_text:
        raise ValueError("Missing HLTV article body")

    tags = [_clean_text(node.get_text(" ", strip=True)) for node in soup.select(".article-topics a")]
    article_thumbnail_url = _extract_thumbnail_url(soup, base_url)

    return HLTVNewsArticle(
        external_id=external_id,
        title=_clean_text(title_node.get_text(" ", strip=True)),
        url=resolved_article_url,
        published_at=_parse_datetime(time_node["datetime"]),
        teaser=listing_item.teaser if listing_item is not None else None,
        author=_clean_text(author_node.get_text(" ", strip=True)) if author_node is not None else None,
        body_text=body_text,
        tags=[tag for tag in tags if tag],
        thumbnail_url=(
            listing_item.thumbnail_url
            if listing_item is not None and listing_item.thumbnail_url is not None
            else article_thumbnail_url
        ),
    )


def _extract_article_id(path_or_url: str) -> str | None:
    match = _ARTICLE_ID_PATTERN.search(path_or_url)
    if match is None:
        return None
    return match.group(1)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _extract_body_text(soup: BeautifulSoup) -> str:
    article_body = soup.select_one(".article-body")
    if article_body is None:
        return ""

    body_parts = []
    for node in article_body.select("p, blockquote"):
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            body_parts.append(text)

    return "\n\n".join(body_parts)


def _extract_thumbnail_url(node: BeautifulSoup, base_url: str) -> str | None:
    thumbnail_node = node.select_one(
        "meta[property='og:image'][content], "
        "meta[name='og:image'][content], "
        "link[rel='image_src'][href], "
        "img[src], "
        "img[data-src]"
    )
    if thumbnail_node is None:
        return None

    thumbnail_value = (
        thumbnail_node.get("content")
        or thumbnail_node.get("href")
        or thumbnail_node.get("data-src")
        or thumbnail_node.get("src")
    )
    if not thumbnail_value:
        return None

    return urljoin(base_url, thumbnail_value)
