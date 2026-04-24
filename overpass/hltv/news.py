"""Pure HTML parsers for HLTV news pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from overpass.hltv.models import HLTVNewsArticle, HLTVNewsListingItem

_ARTICLE_ID_PATTERN = re.compile(r"/news/(\d+)/")


def parse_news_listing(html: str, base_url: str = "https://www.hltv.org") -> list[HLTVNewsListingItem]:
    """Parse an HLTV news listing page into article summaries.

    Args:
        html: HTML containing `a.article` links with news titles, dates,
            optional teasers, and thumbnails.
        base_url: Base URL used to resolve relative article and image links.

    Returns:
        Parsed news listing items; incomplete article rows are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[HLTVNewsListingItem] = []

    for link in soup.select("a.article[href*='/news/']"):
        href = link.get("href")
        title_node = link.select_one(".newstext")
        published_at = _parse_listing_datetime(link)
        if not href or title_node is None or published_at is None:
            continue

        external_id = _extract_article_id(href)
        if external_id is None:
            continue

        items.append(
            HLTVNewsListingItem(
                external_id=external_id,
                title=_clean_text(title_node.get_text(" ", strip=True)),
                url=urljoin(base_url, href),
                published_at=published_at,
                teaser=_extract_listing_teaser(link),
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
    """Parse an HLTV news article page into article metadata and body text.

    Args:
        html: HTML for a news page with article metadata, a headline, and body
            paragraphs or blockquotes.
        article_url: Optional known article URL to use instead of page metadata.
        listing_item: Optional listing item used to fill teaser/thumbnail data
            and verify the parsed article id.
        base_url: Base URL used to resolve relative article and image links.

    Returns:
        Parsed article metadata, tags, thumbnail URL, and body text.

    Raises:
        ValueError: If required article metadata, id, or body content is missing.
    """
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one("article.newsitem h1, h1.headline")
    author_node = soup.select_one(".article-info .author, .article-info .authorName")
    time_node = soup.select_one(
        ".article-info time[datetime], "
        ".article-info .date[data-unix], "
        ".news-with-frag-date[data-unix], "
        ".news-with-frag-date"
    )
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
        published_at=_parse_datetime_node(time_node),
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


def _parse_datetime_node(node: Tag) -> datetime:
    datetime_value = node.get("datetime")
    if datetime_value:
        return _parse_datetime(datetime_value)

    unix_value = node.get("data-unix")
    if unix_value:
        return datetime.fromtimestamp(int(unix_value) / 1000, tz=timezone.utc)

    return _parse_datetime_text(node.get_text(" ", strip=True))


def _parse_datetime_text(value: str) -> datetime:
    cleaned_value = _clean_text(value)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(cleaned_value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _parse_datetime(cleaned_value)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _extract_body_text(soup: BeautifulSoup) -> str:
    article_body = soup.select_one(".article-body")
    if article_body is not None:
        selectors = "p, blockquote"
        body_root: BeautifulSoup | Tag = article_body
    else:
        body_root = soup.select_one("article.newsitem") or soup
        selectors = "p.news-block, blockquote"

    body_parts = []
    for node in body_root.select(selectors):
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            body_parts.append(text)

    return "\n\n".join(body_parts)


def _parse_listing_datetime(link: Tag) -> datetime | None:
    time_node = link.select_one("time[datetime]")
    if time_node is not None:
        return _parse_datetime_node(time_node)

    date_node = link.select_one(".newsrecent")
    if date_node is None:
        return None

    return _parse_datetime_text(date_node.get_text(" ", strip=True))


def _extract_listing_teaser(link: Tag) -> str | None:
    teaser_node = link.select_one(".newstc")
    if teaser_node is None:
        return None

    if teaser_node.select_one(".newsrecent") is not None:
        return None

    teaser = _clean_text(teaser_node.get_text(" ", strip=True))
    return teaser or None


def _extract_thumbnail_url(node: BeautifulSoup, base_url: str) -> str | None:
    # Prefer high-quality previews (og:image, image_src) before falling back
    # to <img> tags. Skip the small country flag sprites that HLTV embeds in
    # listing rows – they're 30x20 px GIFs and look terrible as press photos.
    candidates = node.select(
        "meta[property='og:image'][content], "
        "meta[name='og:image'][content], "
        "link[rel='image_src'][href], "
        "img[src], "
        "img[data-src]"
    )
    for candidate in candidates:
        thumbnail_value = (
            candidate.get("content")
            or candidate.get("href")
            or candidate.get("data-src")
            or candidate.get("src")
        )
        if not thumbnail_value:
            continue
        if "/flags/" in thumbnail_value:
            continue
        return urljoin(base_url, thumbnail_value)

    return None
