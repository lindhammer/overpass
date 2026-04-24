"""Demo mode — generate a complete briefing from hardcoded mock data.

No config, API keys, or network access required.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from overpass.collectors.base import CollectorItem
from overpass.delivery.html import render_briefing
from overpass.editorial.digest import DigestOutput, MatchBlurb, SectionOutput
from overpass.history.models import HistoryEntry

# ── Fixed demo date ──────────────────────────────────────────────
_DEMO_DATE = date(2025, 1, 15)

# ── Output path ──────────────────────────────────────────────────
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "briefings"
_OUTPUT_PATH = _OUTPUT_DIR / "demo.html"


# ── Mock match results ────────────────────────────────────────────

_MATCHES: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="match",
        title="Team Vitality vs Natus Vincere",
        url="https://www.hltv.org/matches/2370295/vitality-vs-natus-vincere-pgl-bucharest-2025",
        timestamp=datetime(2025, 1, 15, 14, 30, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Team Vitality",
            "team2_name": "Natus Vincere",
            "team1_score": 2,
            "team2_score": 0,
            "team1_rank": 1,
            "team2_rank": 4,
            "format": "BO3",
            "event": "PGL Bucharest 2025 — Quarterfinals",
            "winner_name": "Team Vitality",
            "flags": ["watch"],
            "maps": [
                {
                    "name": "Inferno",
                    "team1_score": 16,
                    "team2_score": 11,
                    "winner_name": "Team Vitality",
                },
                {
                    "name": "Mirage",
                    "team1_score": 16,
                    "team2_score": 9,
                    "winner_name": "Team Vitality",
                },
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="FaZe Clan vs G2 Esports",
        url="https://www.hltv.org/matches/2370296/faze-vs-g2-pgl-bucharest-2025",
        timestamp=datetime(2025, 1, 15, 17, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "FaZe Clan",
            "team2_name": "G2 Esports",
            "team1_score": 2,
            "team2_score": 1,
            "team1_rank": 3,
            "team2_rank": 5,
            "format": "BO3",
            "event": "PGL Bucharest 2025 — Quarterfinals",
            "winner_name": "FaZe Clan",
            "flags": [],
            "maps": [
                {
                    "name": "Ancient",
                    "team1_score": 16,
                    "team2_score": 12,
                    "winner_name": "FaZe Clan",
                },
                {
                    "name": "Nuke",
                    "team1_score": 10,
                    "team2_score": 16,
                    "winner_name": "G2 Esports",
                },
                {
                    "name": "Dust2",
                    "team1_score": 16,
                    "team2_score": 13,
                    "winner_name": "FaZe Clan",
                },
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="Team Spirit vs MOUZ",
        url="https://www.hltv.org/matches/2370297/spirit-vs-mouz-pgl-bucharest-2025",
        timestamp=datetime(2025, 1, 15, 11, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Team Spirit",
            "team2_name": "MOUZ",
            "team1_score": 0,
            "team2_score": 2,
            "team1_rank": 2,
            "team2_rank": 7,
            "format": "BO3",
            "event": "PGL Bucharest 2025 — Quarterfinals",
            "winner_name": "MOUZ",
            "flags": ["upset"],
            "maps": [
                {
                    "name": "Vertigo",
                    "team1_score": 11,
                    "team2_score": 16,
                    "winner_name": "MOUZ",
                },
                {
                    "name": "Overpass",
                    "team1_score": 12,
                    "team2_score": 16,
                    "winner_name": "MOUZ",
                },
            ],
        },
    ),
]

_MATCH_BLURBS: dict[str, MatchBlurb] = {
    "https://www.hltv.org/matches/2370295/vitality-vs-natus-vincere-pgl-bucharest-2025": MatchBlurb(
        tagline="CLEAN SWEEP",
        highlight="ZywOo posts 1.42 rating on Inferno as Vitality eliminate NaVi in straight maps.",
    ),
    "https://www.hltv.org/matches/2370296/faze-vs-g2-pgl-bucharest-2025": MatchBlurb(
        tagline="CLOSE CALL",
        highlight="karrigan's read-heavy T-side on Dust2 seals the series for FaZe in a tense decider.",
    ),
    "https://www.hltv.org/matches/2370297/spirit-vs-mouz-pgl-bucharest-2025": MatchBlurb(
        tagline="UPSET ALERT",
        highlight="MOUZ knock out #2-ranked Spirit in back-to-back dominant halves, xertioN top-frags both maps.",
    ),
}

# ── Mock clips ────────────────────────────────────────────────────

_CLIPS: list[CollectorItem] = [
    CollectorItem(
        source="reddit",
        type="clip",
        title="ZywOo 4k through smoke on CT-side Inferno — absolutely insane",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1azmq9p/zywoo_4k_through_smoke_on_ct_side_inferno/",
        timestamp=datetime(2025, 1, 15, 15, 20, tzinfo=timezone.utc),
        metadata={
            "subreddit": "GlobalOffensive",
            "author": "cs2highlights",
            "upvotes": 5812,
        },
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="xertioN deagle ace on Vertigo to break Spirit's economy",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1azmp4r/xertion_deagle_ace_on_vertigo_to_break_spirits/",
        timestamp=datetime(2025, 1, 15, 12, 44, tzinfo=timezone.utc),
        metadata={
            "subreddit": "GlobalOffensive",
            "author": "MOUZfanclub",
            "upvotes": 3291,
        },
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="karrigan clutch 1v3 on Dust2 to force OT — the read was absurd",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1azmr3x/karrigan_clutch_1v3_on_dust2_to_force_ot/",
        timestamp=datetime(2025, 1, 15, 19, 5, tzinfo=timezone.utc),
        metadata={
            "subreddit": "GlobalOffensive",
            "author": "FaZe_content",
            "upvotes": 2147,
        },
    ),
]

# ── Mock news / roster moves ──────────────────────────────────────

_NEWS: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="article",
        title="s1mple removed from NaVi's active roster following Bucharest exit",
        url="https://www.hltv.org/news/39001/s1mple-removed-from-navis-active-roster",
        timestamp=datetime(2025, 1, 15, 18, 0, tzinfo=timezone.utc),
        metadata={
            "category": "trade",
            "category_label": "Roster Move",
            "teaser": (
                "Oleksandr 's1mple' Kostyliev has been moved to the bench following Natus Vincere's"
                " early exit at PGL Bucharest 2025. The organization cited a need for structural change."
            ),
        },
    ),
    CollectorItem(
        source="hltv",
        type="article",
        title="ENCE sign Finland prodigy sLowi as entry fragger",
        url="https://www.hltv.org/news/39002/ence-sign-slowi-as-entry-fragger",
        timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
        metadata={
            "category": "trade",
            "category_label": "Signing",
            "teaser": (
                "ENCE have announced the signing of 19-year-old Finnish talent Joona 'sLowi' Laine"
                " on a two-year deal, replacing the departing SunPayus."
            ),
        },
    ),
]

# ── Mock upcoming matches ─────────────────────────────────────────

_UPCOMING: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="Team Vitality vs FaZe Clan",
        url="https://www.hltv.org/matches/2370300/vitality-vs-faze-pgl-bucharest-2025",
        timestamp=datetime(2025, 1, 16, 14, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "Team Vitality",
            "team2": "FaZe Clan",
            "event": "PGL Bucharest 2025",
            "format": "BO3",
            "stage": "Semifinals",
            "hltv_url": "https://www.hltv.org/matches/2370300/vitality-vs-faze-pgl-bucharest-2025",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="MOUZ vs Heroic",
        url="https://www.hltv.org/matches/2370301/mouz-vs-heroic-pgl-bucharest-2025",
        timestamp=datetime(2025, 1, 16, 17, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "MOUZ",
            "team2": "Heroic",
            "event": "PGL Bucharest 2025",
            "format": "BO3",
            "stage": "Semifinals",
            "hltv_url": "https://www.hltv.org/matches/2370301/mouz-vs-heroic-pgl-bucharest-2025",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="Astralis vs FURIA",
        url="https://www.hltv.org/matches/2370302/astralis-vs-furia-iem-cologne-quals",
        timestamp=datetime(2025, 1, 17, 19, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "Astralis",
            "team2": "FURIA",
            "event": "IEM Cologne 2025 Qualifiers",
            "format": "BO1",
            "stage": "Group Stage",
            "hltv_url": "https://www.hltv.org/matches/2370302/astralis-vs-furia-iem-cologne-quals",
        },
    ),
]

# ── Mock podcast episodes ─────────────────────────────────────────

_PODCASTS: list[CollectorItem] = [
    CollectorItem(
        source="HLTV Confirmed",
        type="episode",
        title="Ep. 483 — Vitality sweep NaVi, MOUZ upset Spirit, Bucharest semis preview",
        url="https://feeds.simplecast.com/hltvconfirmed/ep483",
        timestamp=datetime(2025, 1, 15, 20, 0, tzinfo=timezone.utc),
        metadata={
            "description": (
                "The panel breaks down Vitality's dominant run through Bucharest, discusses s1mple's"
                " benching, and previews the Vitality vs FaZe semifinal."
            ),
            "duration": "1:18:22",
        },
    ),
    CollectorItem(
        source="CSGO Podcast",
        type="episode",
        title="The MOUZ Upset Special — How did Spirit lose to a tier-2 roster?",
        url="https://feeds.simplecast.com/csgopodcast/ep201",
        timestamp=datetime(2025, 1, 15, 17, 45, tzinfo=timezone.utc),
        metadata={
            "description": (
                "Deep dive into Spirit's surprising early exit, xertioN's individual performance,"
                " and whether MOUZ can challenge the top three in 2025."
            ),
            "duration": "54:11",
        },
    ),
]

# ── Mock YouTube videos ───────────────────────────────────────────

_VIDEOS: list[CollectorItem] = [
    CollectorItem(
        source="youtube",
        type="video",
        title="BEST OF PGL BUCHAREST 2025 QUARTERFINALS — Highlights Montage",
        url="https://www.youtube.com/watch?v=bucharest2025qf",
        timestamp=datetime(2025, 1, 15, 21, 0, tzinfo=timezone.utc),
        metadata={
            "description": "Every highlight from today's quarterfinals: Vitality sweep, FaZe clutch, and the MOUZ upset.",
            "channel": "HLTV",
            "duration": "22:14",
        },
    ),
    CollectorItem(
        source="youtube",
        type="video",
        title="ZywOo Career Highlights — The Bucharest Edition",
        url="https://www.youtube.com/watch?v=zywoo_bucharest",
        timestamp=datetime(2025, 1, 15, 16, 30, tzinfo=timezone.utc),
        metadata={
            "description": "A curated look at ZywOo's best plays from PGL Bucharest 2025 as Vitality march toward the title.",
            "channel": "Team Vitality",
            "duration": "9:47",
        },
    ),
]

# ── Mock Steam patch ──────────────────────────────────────────────

_PATCHES: list[CollectorItem] = [
    CollectorItem(
        source="steam",
        type="patch",
        title="CS2 Update — January 14, 2025",
        url="https://store.steampowered.com/news/app/730/view/502985623012345678",
        timestamp=datetime(2025, 1, 14, 18, 0, tzinfo=timezone.utc),
        metadata={
            "version": "v1.39.6.4",
            "changes": [
                "Fixed a rare server crash when players connect during overtime.",
                "Adjusted smoke grenade throw trajectory on Dust2 B-site.",
                "Improved rendering performance for low-end GPUs during large smoke stack scenarios.",
                "Fixed sub-tick interpolation artifact causing visible hitbox desync at high ping.",
            ],
        },
    ),
]

# ── Mock This Day in CS history entry ────────────────────────────

_THIS_DAY = HistoryEntry(
    year=2014,
    headline="NiP's legendary 87-0 streak finally ends at DreamHack Winter",
    narrative=(
        "On January 15, 2014, Ninjas in Pyjamas suffered their first-ever LAN defeat in CS:GO "
        "when LDLC France ended their extraordinary 87-0 unbeaten run in the DreamHack Winter "
        "group stage. The result shocked the scene and marked the moment CS:GO's competitive "
        "era truly opened up beyond a single dominant dynasty."
    ),
    visual_label="2014",
    source_url="https://www.youtube.com/watch?v=GqOtNxmyVKk",
)

# ── Assemble DigestOutput ─────────────────────────────────────────

_SUMMARY_LINE = (
    "Vitality sweep NaVi 2-0, MOUZ upset #2 Spirit in Bucharest quarters, "
    "s1mple dropped from active roster"
)


def _build_digest() -> DigestOutput:
    sections: dict = {
        "Matches": SectionOutput(
            intro="Three quarterfinal series closed out the Bucharest bracket today — one sweep, one decider, one major upset.",
            items=_MATCHES,
        ),
        "Clips": SectionOutput(
            intro="Reddit's top plays from today's sessions, sorted by community upvotes.",
            items=_CLIPS,
        ),
        "News": SectionOutput(
            intro="Roster moves and announcements breaking in the 24 hours around today's event day.",
            items=_NEWS,
        ),
        "Podcasts": SectionOutput(
            intro="Long-form audio dropped overnight covering today's results and the broader Bucharest story.",
            items=_PODCASTS,
        ),
        "Videos": SectionOutput(
            intro="Official and community video content from the Bucharest quarterfinals.",
            items=_VIDEOS,
        ),
        "Patches": SectionOutput(
            intro="A minor update shipped yesterday addressing server stability and smoke behavior.",
            items=_PATCHES,
        ),
    }
    return DigestOutput(
        summary_line=_SUMMARY_LINE,
        sections=sections,
        per_match_blurbs=_MATCH_BLURBS,
    )


# ── Public entry point ────────────────────────────────────────────

def run_demo() -> None:
    """Generate a demo briefing from hardcoded mock data and save to output/briefings/demo.html."""
    digest = _build_digest()

    html = render_briefing(
        digest,
        _DEMO_DATE,
        social_items=[],
        upcoming_items=_UPCOMING,
        this_day=_THIS_DAY,
    )

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(f"Demo briefing generated: {_OUTPUT_PATH}")
    print("Open it in your browser to see what Overpass looks like.")
