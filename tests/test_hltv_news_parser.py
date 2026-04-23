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


def test_parse_news_listing_supports_archive_entries_with_date_only() -> None:
        html = """
        <div class="standard-box standard-list">
            <a href="/news/44424/short-news-week-16" class="newsline article">
                <img src="/img/static/flags/30x20/WORLD.gif" alt="Other">
                <div class="newstext">Short news: Week 16</div>
                <div class="newstc">
                    <div class="newsrecent">2026-04-22</div>
                    <div>363 comments</div>
                </div>
            </a>
        </div>
        """

        items = parse_news_listing(html, base_url="https://www.hltv.org")

        # Country flag sprites are explicitly skipped as thumbnails because
        # they're tiny GIFs that look bad as press photos.
        assert items == [
                HLTVNewsListingItem(
                        external_id="44424",
                        title="Short news: Week 16",
                        url="https://www.hltv.org/news/44424/short-news-week-16",
                        published_at=datetime(2026, 4, 22, 0, 0, tzinfo=timezone.utc),
                        teaser=None,
                        thumbnail_url=None,
                )
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
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.hltv.org/news/12345/faze-win-cologne-opener">
      </head>
      <body>
        <h1 class="headline">FaZe win Cologne opener</h1>
        <div class="article-info">
          <time datetime="2026-04-22T10:30:00+00:00">2026-04-22 10:30</time>
        </div>
        <div class="article-body">
          <p>   </p>
          <blockquote>   </blockquote>
        </div>
      </body>
    </html>
    """

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


def test_parse_news_article_supports_current_live_article_markup() -> None:
        html = """
        <html>
            <head>
                <link rel="canonical" href="https://www.hltv.org/news/44440/adrrr-to-step-in-as-legacy-coach-for-rest-of-season">
                <meta property="og:image" content="https://img-cdn.hltv.org/gallery/44440/cover.jpg">
            </head>
            <body>
                <article class="newsitem standard-box">
                    <div class="article-info">
                        <div><span class="author"><a class="authorName" href="/author/920331/sumljiv"><span>Sumljiv</span></a></span></div>
                        <div class="date" data-time-format="d-M-yyyy HH:mm" data-unix="1776878940000">22-4-2026 19:29</div>
                    </div>
                    <h1 class="headline">adrrr to step in as Legacy coach for rest of season</h1>
                    <p class="news-block">Legacy have announced that assistant coach Alan "adrrr" Riveros will stand behind the team in the upcoming tournaments.</p>
                    <p class="news-block">Despite RiVAS' absence, the organization stated that the Brazilian coach remains under contract.</p>
                </article>
            </body>
        </html>
        """

        article = parse_news_article(html, base_url="https://www.hltv.org")

        assert article == HLTVNewsArticle(
                external_id="44440",
                title="adrrr to step in as Legacy coach for rest of season",
                url="https://www.hltv.org/news/44440/adrrr-to-step-in-as-legacy-coach-for-rest-of-season",
                published_at=datetime(2026, 4, 22, 17, 29, tzinfo=timezone.utc),
                author="Sumljiv",
                tags=[],
                body_text=(
                        "Legacy have announced that assistant coach Alan \"adrrr\" Riveros will stand behind the team in the upcoming tournaments.\n\n"
                        "Despite RiVAS' absence, the organization stated that the Brazilian coach remains under contract."
                ),
                thumbnail_url="https://img-cdn.hltv.org/gallery/44440/cover.jpg",
        )


def test_parse_news_article_supports_short_news_pages() -> None:
        html = """
        <html>
            <head>
                <link rel="canonical" href="https://www.hltv.org/news/44424/short-news-week-16">
            </head>
            <body>
                <article class="newsitem standard-box">
                    <div class="news-with-frag-head-container">
                        <div class="news-with-frag-banner-content-container">
                            <div class="news-with-frag-content-no-logo">
                                <div class="news-with-frag-date" data-time-format="d-M-yyyy HH:mm" data-unix="1776880980000">22-4-2026 20:03</div>
                                <h1>Short news: Week 16</h1>
                            </div>
                        </div>
                    </div>
                    <p class="news-block">Phantom is down to four players on its active lineup after the organization announced the benching of Wiktor "mynio" Kruk on Saturday.</p>
                    <p class="news-block">The Polish organization also announced a new strategic direction for the roster.</p>
                </article>
            </body>
        </html>
        """

        article = parse_news_article(html, base_url="https://www.hltv.org")

        assert article.external_id == "44424"
        assert article.title == "Short news: Week 16"
        assert article.url == "https://www.hltv.org/news/44424/short-news-week-16"
        assert article.published_at == datetime(2026, 4, 22, 18, 3, tzinfo=timezone.utc)
        assert article.author is None
        assert article.body_text == (
                "Phantom is down to four players on its active lineup after the organization announced the benching of Wiktor \"mynio\" Kruk on Saturday.\n\n"
                "The Polish organization also announced a new strategic direction for the roster."
        )
