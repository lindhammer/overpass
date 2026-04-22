from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from overpass.hltv.models import HLTVNewsArticle, HLTVNewsListingItem
from overpass.hltv.news import parse_news_article, parse_news_listing


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_parse_news_listing_extracts_listing_items() -> None:
    items = parse_news_listing(
        _read_fixture("hltv_news_listing.html"),
        base_url="https://www.hltv.org",
    )

    assert all(type(item) is HLTVNewsListingItem for item in items)
    assert all(not isinstance(item, HLTVNewsArticle) for item in items)
    assert items == [
        HLTVNewsListingItem(
            external_id="12345",
            title="FaZe win Cologne opener",
            url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
            published_at=datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc),
            teaser="Finn \"karrigan\" Andersen's side opened the event with a comfortable series win.",
            thumbnail_url="https://www.hltv.org/gallery/12345/cover.jpg",
        ),
        HLTVNewsListingItem(
            external_id="12346",
            title="Vitality lock playoff spot",
            url="https://www.hltv.org/news/12346/vitality-lock-playoff-spot",
            published_at=datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc),
            teaser="apEX's team secured a playoff berth after a clean sweep in group B.",
            thumbnail_url="https://www.hltv.org/gallery/12346/cover.jpg",
        ),
    ]


def test_parse_news_article_hydrates_listing_item_without_manual_merge() -> None:
    listing_item = parse_news_listing(
        _read_fixture("hltv_news_listing.html"),
        base_url="https://www.hltv.org",
    )[0]

    article = parse_news_article(
        _read_fixture("hltv_news_article.html"),
        listing_item=listing_item,
        base_url="https://www.hltv.org",
    )

    assert article == HLTVNewsArticle(
        external_id="12345",
        title="FaZe win Cologne opener",
        url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        published_at=datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc),
        teaser="Finn \"karrigan\" Andersen's side opened the event with a comfortable series win.",
        author="Striker",
        tags=["CS2", "IEM Cologne"],
        body_text=(
            "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n\n"
            "Finn \"karrigan\" Andersen said the team kept its early-game protocols simple "
            "and trusted the calling in late rounds.\n\n"
            "\"We knew the veto gave us room to play our own game,\" karrigan said."
        ),
        thumbnail_url="https://www.hltv.org/gallery/12345/cover.jpg",
    )


def test_parse_news_article_rejects_mismatched_listing_item_identity() -> None:
    listing_item = parse_news_listing(
        _read_fixture("hltv_news_listing.html"),
        base_url="https://www.hltv.org",
    )[1]

    try:
        parse_news_article(
            _read_fixture("hltv_news_article.html"),
            listing_item=listing_item,
            base_url="https://www.hltv.org",
        )
    except ValueError as exc:
        assert str(exc) == "Listing item does not match parsed HLTV article"
    else:
        raise AssertionError("Expected parse_news_article to reject mismatched listing metadata")


def test_parse_news_article_uses_caller_provided_article_url() -> None:
    html = _read_fixture("hltv_news_article.html").replace(
        "https://www.hltv.org/news/12345/faze-win-cologne-opener",
        "https://www.hltv.org/news/99999/wrong-canonical-url",
    )

    article = parse_news_article(
        html,
        article_url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        base_url="https://www.hltv.org",
    )

    assert article.external_id == "12345"
    assert article.url == "https://www.hltv.org/news/12345/faze-win-cologne-opener"


def test_parse_news_article_extracts_metadata_and_body() -> None:
    article = parse_news_article(
        _read_fixture("hltv_news_article.html"),
        article_url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        base_url="https://www.hltv.org",
    )

    assert article == HLTVNewsArticle(
        external_id="12345",
        title="FaZe win Cologne opener",
        url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        published_at=datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc),
        author="Striker",
        tags=["CS2", "IEM Cologne"],
        body_text=(
            "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n\n"
            "Finn \"karrigan\" Andersen said the team kept its early-game protocols simple "
            "and trusted the calling in late rounds.\n\n"
            "\"We knew the veto gave us room to play our own game,\" karrigan said."
        ),
        thumbnail_url="https://www.hltv.org/gallery/12345/article.jpg",
    )


def test_parse_news_article_extracts_body_text_from_mildly_nested_markup() -> None:
    html = _read_fixture("hltv_news_article.html").replace(
        """      <div class=\"article-body\">\n        <p>\n          FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n        </p>\n        <p>\n          Finn \"karrigan\" Andersen said the team kept its early-game protocols simple\n          and trusted the calling in late rounds.\n        </p>\n        <blockquote>\n          \"We knew the veto gave us room to play our own game,\" karrigan said.\n        </blockquote>\n      </div>""",
        """      <div class=\"article-body\">\n        <div class=\"copy-block\">\n          <p>\n            FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n          </p>\n        </div>\n        <section>\n          <p>\n            Finn \"karrigan\" Andersen said the team kept its early-game protocols simple\n            and trusted the calling in late rounds.\n          </p>\n        </section>\n        <div class=\"quote-wrapper\">\n          <blockquote>\n            \"We knew the veto gave us room to play our own game,\" karrigan said.\n          </blockquote>\n        </div>\n      </div>""",
    )

    article = parse_news_article(
        html,
        article_url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        base_url="https://www.hltv.org",
    )

    assert article.body_text == (
        "FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n\n"
        "Finn \"karrigan\" Andersen said the team kept its early-game protocols simple "
        "and trusted the calling in late rounds.\n\n"
        "\"We knew the veto gave us room to play our own game,\" karrigan said."
    )


def test_parse_news_article_rejects_empty_article_body() -> None:
    html = _read_fixture("hltv_news_article.html").replace(
        """      <div class=\"article-body\">\n        <p>\n          FaZe opened their Cologne run with a composed 2-0 win over GamerLegion.\n        </p>\n        <p>\n          Finn \"karrigan\" Andersen said the team kept its early-game protocols simple\n          and trusted the calling in late rounds.\n        </p>\n        <blockquote>\n          \"We knew the veto gave us room to play our own game,\" karrigan said.\n        </blockquote>\n      </div>""",
        """      <div class=\"article-body\">\n        <p>   </p>\n        <blockquote>   </blockquote>\n      </div>""",
    )

    try:
        parse_news_article(
            html,
            article_url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
            base_url="https://www.hltv.org",
        )
    except ValueError as exc:
        assert str(exc) == "Missing HLTV article body"
    else:
        raise AssertionError("Expected parse_news_article to reject an empty article body")


def test_parse_news_article_allows_missing_author_markup() -> None:
    html = _read_fixture("hltv_news_article.html").replace(
        '<a class="author" href="/profile/1/striker">Striker</a>\n',
        "",
    )

    article = parse_news_article(
        html,
        article_url="https://www.hltv.org/news/12345/faze-win-cologne-opener",
        base_url="https://www.hltv.org",
    )

    assert article.author is None
    assert article.title == "FaZe win Cologne opener"
    assert article.published_at == datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc)
