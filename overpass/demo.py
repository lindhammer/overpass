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
_DEMO_DATE = date(2026, 4, 25)

# ── Output path ──────────────────────────────────────────────────
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "briefings"
_OUTPUT_PATH = _OUTPUT_DIR / "demo.html"


# ── Mock match results ────────────────────────────────────────────

_MATCHES: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="match",
        title="9z vs Legacy",
        url="https://www.hltv.org/matches/2393452/9z-vs-legacy-betboom-rush-b-summit-season-3",
        timestamp=datetime(2026, 4, 24, 22, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "9z",
            "team2_name": "Legacy",
            "team1_score": 0,
            "team2_score": 2,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/COZDFWOIm41AT0srqOHFhM.png?invert=true&ixlib=java-2.1.0&sat=-100&w=100&s=002bc4bec253f97296484dc3986a233a",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/RWbHH6RA8uGwJurGeLFvSr.png?ixlib=java-2.1.0&w=100&s=10ff29ff632e0bd82922f4fcd83f930f",
            "format": "BO3",
            "event": "BetBoom RUSH B Summit Season 3",
            "winner_name": "Legacy",
            "flags": [],
            "maps": [
                {"name": "Inferno", "team1_score": 9, "team2_score": 13, "winner_name": "Legacy"},
                {"name": "Nuke", "team1_score": 3, "team2_score": 13, "winner_name": "Legacy"},
            ],
            "veto": [
                {"team_name": "Legacy", "action": "removed", "map_name": "Overpass"},
                {"team_name": "9z", "action": "removed", "map_name": "Ancient"},
                {"team_name": "Legacy", "action": "picked", "map_name": "Inferno"},
                {"team_name": "9z", "action": "picked", "map_name": "Nuke"},
                {"team_name": "9z", "action": "removed", "map_name": "Mirage"},
                {"team_name": "Legacy", "action": "removed", "map_name": "Anubis"},
                {"team_name": None, "action": "left_over", "map_name": "Dust2"},
            ],
            "player_stats": [
                {"team_name": "Legacy", "player_name": "dumau", "kills": 46, "deaths": 27, "adr": 88.4, "kast": 76.0, "rating": 1.38},
                {"team_name": "Legacy", "player_name": "yuurih", "kills": 40, "deaths": 29, "adr": 80.1, "kast": 74.5, "rating": 1.22},
                {"team_name": "Legacy", "player_name": "drop", "kills": 36, "deaths": 28, "adr": 72.6, "kast": 72.0, "rating": 1.14},
                {"team_name": "Legacy", "player_name": "saadzin", "kills": 30, "deaths": 29, "adr": 63.4, "kast": 70.0, "rating": 1.00},
                {"team_name": "Legacy", "player_name": "nqz", "kills": 28, "deaths": 30, "adr": 60.2, "kast": 68.5, "rating": 0.94},
                {"team_name": "9z", "player_name": "max", "kills": 28, "deaths": 36, "adr": 67.2, "kast": 62.0, "rating": 0.92},
                {"team_name": "9z", "player_name": "dgt", "kills": 24, "deaths": 36, "adr": 57.8, "kast": 60.0, "rating": 0.80},
                {"team_name": "9z", "player_name": "lux1z", "kills": 22, "deaths": 37, "adr": 55.4, "kast": 58.0, "rating": 0.76},
                {"team_name": "9z", "player_name": "Luken", "kills": 20, "deaths": 38, "adr": 52.1, "kast": 56.0, "rating": 0.72},
                {"team_name": "9z", "player_name": "order", "kills": 18, "deaths": 36, "adr": 49.6, "kast": 55.0, "rating": 0.68},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="Monte vs Ninjas in Pyjamas",
        url="https://www.hltv.org/matches/2393416/monte-vs-ninjas-in-pyjamas-cct-global-finals-2026",
        timestamp=datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Monte",
            "team2_name": "Ninjas in Pyjamas",
            "team1_score": 2,
            "team2_score": 1,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/2tc9n4fHkiRIX2FiJSkhgt.png?ixlib=java-2.1.0&w=100&s=35b0f1f1725e21bc55bb9a3f6edb344e",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/-ttGATBV_P_HcZazxNNtIb.png?ixlib=java-2.1.0&w=100&s=8553ef1ff134f4171868cbfaf234836d",
            "format": "BO3",
            "event": "CCT Global Finals 2026",
            "winner_name": "Monte",
            "flags": [],
            "maps": [
                {"name": "Nuke", "team1_score": 10, "team2_score": 13, "winner_name": "Ninjas in Pyjamas"},
                {"name": "Dust2", "team1_score": 13, "team2_score": 7, "winner_name": "Monte"},
                {"name": "Anubis", "team1_score": 16, "team2_score": 14, "winner_name": "Monte"},
            ],
            "veto": [
                {"team_name": "Ninjas in Pyjamas", "action": "removed", "map_name": "Inferno"},
                {"team_name": "Monte", "action": "removed", "map_name": "Ancient"},
                {"team_name": "Ninjas in Pyjamas", "action": "picked", "map_name": "Nuke"},
                {"team_name": "Monte", "action": "picked", "map_name": "Dust2"},
                {"team_name": "Ninjas in Pyjamas", "action": "removed", "map_name": "Mirage"},
                {"team_name": "Monte", "action": "removed", "map_name": "Overpass"},
                {"team_name": None, "action": "left_over", "map_name": "Anubis"},
            ],
            "player_stats": [
                {"team_name": "Monte", "player_name": "DemQQ", "kills": 58, "deaths": 46, "adr": 82.4, "kast": 73.5, "rating": 1.24},
                {"team_name": "Monte", "player_name": "w1dow", "kills": 52, "deaths": 48, "adr": 76.1, "kast": 71.0, "rating": 1.12},
                {"team_name": "Monte", "player_name": "Bugged", "kills": 47, "deaths": 50, "adr": 70.4, "kast": 69.5, "rating": 1.02},
                {"team_name": "Monte", "player_name": "facecrack", "kills": 38, "deaths": 51, "adr": 61.8, "kast": 65.0, "rating": 0.90},
                {"team_name": "Monte", "player_name": "Woro2k", "kills": 35, "deaths": 50, "adr": 57.4, "kast": 63.0, "rating": 0.84},
                {"team_name": "Ninjas in Pyjamas", "player_name": "Plopski", "kills": 55, "deaths": 49, "adr": 79.8, "kast": 70.0, "rating": 1.16},
                {"team_name": "Ninjas in Pyjamas", "player_name": "headtr1ck", "kills": 50, "deaths": 50, "adr": 73.6, "kast": 68.5, "rating": 1.06},
                {"team_name": "Ninjas in Pyjamas", "player_name": "hampus", "kills": 42, "deaths": 52, "adr": 65.2, "kast": 65.0, "rating": 0.90},
                {"team_name": "Ninjas in Pyjamas", "player_name": "REZ", "kills": 38, "deaths": 54, "adr": 60.4, "kast": 62.5, "rating": 0.82},
                {"team_name": "Ninjas in Pyjamas", "player_name": "maxster", "kills": 32, "deaths": 55, "adr": 52.6, "kast": 58.0, "rating": 0.72},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="BetBoom vs Ursa",
        url="https://www.hltv.org/matches/2393193/betboom-vs-ursa-nodwin-clutch-series-7",
        timestamp=datetime(2026, 4, 24, 16, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "BetBoom",
            "team2_name": "Ursa",
            "team1_score": 1,
            "team2_score": 2,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/G4ZrdB0-q41USPd_z27IQA.png?ixlib=java-2.1.0&w=100&s=cb2c8c3b65e034368ff60f1c6a8d04ef",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/y8cjHnlpqAPHEVRTd_tnzz.png?ixlib=java-2.1.0&w=100&s=f8b71ba88f7792254c48a11f5990bd0d",
            "format": "BO3",
            "event": "NODWIN Clutch Series 7",
            "winner_name": "Ursa",
            "flags": ["upset"],
            "maps": [
                {"name": "Dust2", "team1_score": 9, "team2_score": 13, "winner_name": "Ursa"},
                {"name": "Nuke", "team1_score": 13, "team2_score": 9, "winner_name": "BetBoom"},
                {"name": "Anubis", "team1_score": 9, "team2_score": 13, "winner_name": "Ursa"},
            ],
            "veto": [
                {"team_name": "Ursa", "action": "removed", "map_name": "Ancient"},
                {"team_name": "BetBoom", "action": "removed", "map_name": "Inferno"},
                {"team_name": "Ursa", "action": "picked", "map_name": "Dust2"},
                {"team_name": "BetBoom", "action": "picked", "map_name": "Nuke"},
                {"team_name": "Ursa", "action": "removed", "map_name": "Mirage"},
                {"team_name": "BetBoom", "action": "removed", "map_name": "Overpass"},
                {"team_name": None, "action": "left_over", "map_name": "Anubis"},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="BIG vs HEROIC",
        url="https://www.hltv.org/matches/2393415/big-vs-heroic-cct-global-finals-2026",
        timestamp=datetime(2026, 4, 24, 14, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "BIG",
            "team2_name": "HEROIC",
            "team1_score": 0,
            "team2_score": 2,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/OgMRQA35hopXA8kDwMFHIY.svg?ixlib=java-2.1.0&s=ec7bc44165c7acf4224a22a1338ab7d7",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/4S22uk_gnZTiQiI-hhH4yp.png?ixlib=java-2.1.0&w=100&s=a5d9fdc008d14ed3b126835304871d49",
            "format": "BO3",
            "event": "CCT Global Finals 2026",
            "winner_name": "HEROIC",
            "flags": [],
            "maps": [
                {"name": "Dust2", "team1_score": 9, "team2_score": 13, "winner_name": "HEROIC"},
                {"name": "Overpass", "team1_score": 7, "team2_score": 13, "winner_name": "HEROIC"},
            ],
            "veto": [
                {"team_name": "HEROIC", "action": "removed", "map_name": "Anubis"},
                {"team_name": "BIG", "action": "removed", "map_name": "Nuke"},
                {"team_name": "HEROIC", "action": "picked", "map_name": "Dust2"},
                {"team_name": "BIG", "action": "picked", "map_name": "Overpass"},
                {"team_name": "HEROIC", "action": "removed", "map_name": "Ancient"},
                {"team_name": "BIG", "action": "removed", "map_name": "Inferno"},
                {"team_name": None, "action": "left_over", "map_name": "Mirage"},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="Alliance vs Oxuji",
        url="https://www.hltv.org/matches/2393192/alliance-vs-oxuji-nodwin-clutch-series-7",
        timestamp=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Alliance",
            "team2_name": "Oxuji",
            "team1_score": 2,
            "team2_score": 0,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/xsWK0BtR26rN776qdnWFC1.png?ixlib=java-2.1.0&w=100&s=8a8620433b87679e532367e2c90a3248",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/FHuQgIDeH66FZalxl9lKLh.png?ixlib=java-2.1.0&w=100&s=f27a572e6a139e2780d95348193aa598",
            "format": "BO3",
            "event": "NODWIN Clutch Series 7",
            "winner_name": "Alliance",
            "flags": [],
            "maps": [
                {"name": "Nuke", "team1_score": 13, "team2_score": 11, "winner_name": "Alliance"},
                {"name": "Anubis", "team1_score": 13, "team2_score": 7, "winner_name": "Alliance"},
            ],
            "veto": [
                {"team_name": "Oxuji", "action": "removed", "map_name": "Overpass"},
                {"team_name": "Alliance", "action": "removed", "map_name": "Mirage"},
                {"team_name": "Oxuji", "action": "picked", "map_name": "Nuke"},
                {"team_name": "Alliance", "action": "picked", "map_name": "Anubis"},
                {"team_name": "Oxuji", "action": "removed", "map_name": "Inferno"},
                {"team_name": "Alliance", "action": "removed", "map_name": "Dust2"},
                {"team_name": None, "action": "left_over", "map_name": "Ancient"},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="BIG vs Acend",
        url="https://www.hltv.org/matches/2393191/big-vs-acend-nodwin-clutch-series-7",
        timestamp=datetime(2026, 4, 24, 10, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "BIG",
            "team2_name": "Acend",
            "team1_score": 2,
            "team2_score": 0,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/OgMRQA35hopXA8kDwMFHIY.svg?ixlib=java-2.1.0&s=ec7bc44165c7acf4224a22a1338ab7d7",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/TslndPhDvsn1bLMdm1j2i6.png?ixlib=java-2.1.0&w=100&s=59913cb4781074edfb7628a074afea79",
            "format": "BO3",
            "event": "NODWIN Clutch Series 7",
            "winner_name": "BIG",
            "flags": [],
            "maps": [
                {"name": "Ancient", "team1_score": 13, "team2_score": 9, "winner_name": "BIG"},
                {"name": "Overpass", "team1_score": 13, "team2_score": 8, "winner_name": "BIG"},
            ],
            "veto": [
                {"team_name": "Acend", "action": "removed", "map_name": "Nuke"},
                {"team_name": "BIG", "action": "removed", "map_name": "Inferno"},
                {"team_name": "Acend", "action": "picked", "map_name": "Ancient"},
                {"team_name": "BIG", "action": "picked", "map_name": "Overpass"},
                {"team_name": "Acend", "action": "removed", "map_name": "Dust2"},
                {"team_name": "BIG", "action": "removed", "map_name": "Anubis"},
                {"team_name": None, "action": "left_over", "map_name": "Mirage"},
            ],
        },
    ),
    CollectorItem(
        source="hltv",
        type="match",
        title="Legacy vs Keyd Stars",
        url="https://www.hltv.org/matches/2393449/legacy-vs-keyd-stars-betboom-rush-b-summit-season-3",
        timestamp=datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc),
        metadata={
            "team1_name": "Legacy",
            "team2_name": "Keyd Stars",
            "team1_score": 2,
            "team2_score": 0,
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/RWbHH6RA8uGwJurGeLFvSr.png?ixlib=java-2.1.0&w=100&s=10ff29ff632e0bd82922f4fcd83f930f",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/m-SA9fWSyBqRgsrDCDXCId.png?ixlib=java-2.1.0&w=100&s=28e6b04f5c05dd98e0e3d1a038235811",
            "format": "BO3",
            "event": "BetBoom RUSH B Summit Season 3",
            "winner_name": "Legacy",
            "flags": [],
            "maps": [
                {"name": "Ancient", "team1_score": 13, "team2_score": 1, "winner_name": "Legacy"},
                {"name": "Mirage", "team1_score": 13, "team2_score": 7, "winner_name": "Legacy"},
            ],
            "veto": [
                {"team_name": "Keyd Stars", "action": "removed", "map_name": "Inferno"},
                {"team_name": "Legacy", "action": "removed", "map_name": "Anubis"},
                {"team_name": "Keyd Stars", "action": "picked", "map_name": "Ancient"},
                {"team_name": "Legacy", "action": "picked", "map_name": "Mirage"},
                {"team_name": "Legacy", "action": "removed", "map_name": "Nuke"},
                {"team_name": "Keyd Stars", "action": "removed", "map_name": "Overpass"},
                {"team_name": None, "action": "left_over", "map_name": "Dust2"},
            ],
        },
    ),
]

_MATCH_BLURBS: dict[str, MatchBlurb] = {
    "https://www.hltv.org/matches/2393452/9z-vs-legacy-betboom-rush-b-summit-season-3": MatchBlurb(
        tagline="MAP DOMINANCE",
        highlight="Legacy secured Nuke with a dominant 13-3 scoreline against 9z to close out the series 2-0.",
    ),
    "https://www.hltv.org/matches/2393416/monte-vs-ninjas-in-pyjamas-cct-global-finals-2026": MatchBlurb(
        tagline="OVERTIME DECIDER",
        highlight="Monte won a tight Anubis 16-14 in overtime to clinch the series 2-1 over Ninjas in Pyjamas.",
    ),
    "https://www.hltv.org/matches/2393193/betboom-vs-ursa-nodwin-clutch-series-7": MatchBlurb(
        tagline="THREE-MAP BATTLE",
        highlight="Ursa took the decider map Anubis 13-9, securing a 2-1 series victory against BetBoom.",
    ),
    "https://www.hltv.org/matches/2393415/big-vs-heroic-cct-global-finals-2026": MatchBlurb(
        tagline="CONFIDENT PROGRESSION",
        highlight="HEROIC advanced after taking Dust2 13-9 and Overpass 13-7 against BIG in a 2-0 series.",
    ),
    "https://www.hltv.org/matches/2393192/alliance-vs-oxuji-nodwin-clutch-series-7": MatchBlurb(
        tagline="SERIES ADVANCEMENT",
        highlight="Alliance secured their series victory over Oxuji by taking Nuke 13-11 and Anubis 13-7.",
    ),
    "https://www.hltv.org/matches/2393191/big-vs-acend-nodwin-clutch-series-7": MatchBlurb(
        tagline="SMOOTH SAILING",
        highlight="BIG secured Ancient 13-9 and Overpass 13-8 to defeat Acend 2-0 in the series.",
    ),
    "https://www.hltv.org/matches/2393449/legacy-vs-keyd-stars-betboom-rush-b-summit-season-3": MatchBlurb(
        tagline="ANCIENT STATEMENT",
        highlight="Legacy opened the series with a commanding 13-1 victory on Ancient before closing it out on Mirage.",
    ),
}

# ── Mock clips ────────────────────────────────────────────────────

_CLIPS: list[CollectorItem] = [
    CollectorItem(
        source="reddit",
        type="clip",
        title="After 30 hours I finally beat this INSANE surf bonus",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1sulx8v/after_30_hours_i_finally_beat_this_insane_surf/",
        timestamp=datetime(2026, 4, 24, 17, 13, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/OWdwZmh4ZWI3NnhnMeAbR758GcZNReYZyZYkSbRisUfngLjEezi0G4reA0sP.png?format=pjpg&auto=webp&s=7e3befe7545ccde8e37b308166c9574444031447",
        metadata={"subreddit": "GlobalOffensive", "author": "ima_noob10", "upvotes": 587},
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="Must've been the wind",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1sum18j/mustve_been_the_wind/",
        timestamp=datetime(2026, 4, 24, 17, 17, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/ejIzY3libDU5NnhnMag5X162Hia6vCtlX780OJQTHJNn5uVJZjXI_iuJffnu.png?format=pjpg&auto=webp&s=7c041f67af9c9c019d0917a3ffd4bad3287d70a8",
        metadata={"subreddit": "GlobalOffensive", "author": "yogurt2125", "upvotes": 88},
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="You can still hold your breath by holding inspect (+another small bug that might help decreasing network usage by 1 bits a second :P)",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1sugw0k/you_can_still_hold_your_breath_by_holding_inspect/",
        timestamp=datetime(2026, 4, 24, 14, 11, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/OGtkaTc0ODliNXhnMVpALXX-DcURu76OJJ4UU-qhXDtY9BThEwf7PAHyrLtF.png?format=pjpg&auto=webp&s=d45045ef02554aaee87c04707a50b5e1146b66b6",
        metadata={"subreddit": "GlobalOffensive", "author": "g-mancs", "upvotes": 75},
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="Cache is coming!",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1surhgm/cache_is_coming/",
        timestamp=datetime(2026, 4, 24, 20, 37, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/UAEpzLyvmuzVKxGhoA3mEpoJEdrhph5MSXGpHHlHMpg.jpeg?auto=webp&s=c69cfb9688dd5ee989ad7b87fb7ddd1b2ea7537e",
        metadata={"subreddit": "GlobalOffensive", "author": "ShrikeCS", "upvotes": 69},
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="Cleanest Ace I've Gotten (Second Game on Animgraph 2)",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1suuj74/cleanest_ace_ive_gotten_second_game_on_animgraph_2/",
        timestamp=datetime(2026, 4, 24, 22, 37, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/MHRpa2ViMzV1N3hnMZHYpTbINtoF5lVDZb5r53neqOauI0WeemBomfIVxVqk.png?format=pjpg&auto=webp&s=e0e0ac963b28c708764e1f1fdc219d74720b5c4b",
        metadata={"subreddit": "GlobalOffensive", "author": "Deastruacsion", "upvotes": 61},
    ),
    CollectorItem(
        source="reddit",
        type="clip",
        title="Overthrow (Pre-release) - New CS2 Wingman Map",
        url="https://www.reddit.com/r/GlobalOffensive/comments/1surc4b/overthrow_prerelease_new_cs2_wingman_map/",
        timestamp=datetime(2026, 4, 24, 20, 31, tzinfo=timezone.utc),
        thumbnail_url="https://external-preview.redd.it/c3FnaXRtYmk3N3hnMf6qwtVOI7eYGxVzdHvuJhaQIaPdzjwFbKW4kn-xdkxV.png?format=pjpg&auto=webp&s=76d6e8cbbc8a9072c636ddea2308f6558181f7e2",
        metadata={"subreddit": "GlobalOffensive", "author": "kyaroscuro", "upvotes": 57},
    ),
]

# ── Mock news / roster moves ──────────────────────────────────────

_NEWS: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="article",
        title='Valve tease Cache addition: "What are you doing next week?"',
        url="https://www.hltv.org/news/44449/valve-tease-cache-addition-what-are-you-doing-next-week",
        timestamp=datetime(2026, 4, 24, 19, 28, tzinfo=timezone.utc),
        metadata={
            "category": "default",
            "category_label": "News",
        },
    ),
    CollectorItem(
        source="hltv",
        type="article",
        title="ash parts ways with GamerLegion",
        url="https://www.hltv.org/news/44447/ash-parts-ways-with-gamerlegion",
        timestamp=datetime(2026, 4, 24, 14, 19, tzinfo=timezone.utc),
        metadata={
            "category": "trade",
            "category_label": "Roster",
        },
    ),
    CollectorItem(
        source="hltv",
        type="article",
        title="The EVPs and All-Stars of IEM Rio 2026",
        url="https://www.hltv.org/news/44442/the-evps-and-all-stars-of-iem-rio-2026",
        timestamp=datetime(2026, 4, 24, 12, 20, tzinfo=timezone.utc),
        metadata={
            "category": "default",
            "category_label": "News",
        },
    ),
    CollectorItem(
        source="hltv",
        type="article",
        title="Short news: Week 16",
        url="https://www.hltv.org/news/44424/short-news-week-16",
        timestamp=datetime(2026, 4, 24, 11, 14, tzinfo=timezone.utc),
        metadata={
            "category": "default",
            "category_label": "News",
        },
    ),
]

# ── Mock upcoming matches ─────────────────────────────────────────

_UPCOMING: list[CollectorItem] = [
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="Sharks vs BIG",
        url="https://www.hltv.org/matches/2393417/sharks-vs-big-cct-global-finals-2026",
        timestamp=datetime(2026, 4, 25, 8, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "Sharks",
            "team2": "BIG",
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/xduTwTuydAWc0Dbt-eEjeH.png?ixlib=java-2.1.0&w=50&s=16cdced9e9b1a2b2e771157638f39391",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/OgMRQA35hopXA8kDwMFHIY.svg?ixlib=java-2.1.0&s=ec7bc44165c7acf4224a22a1338ab7d7",
            "event": "CCT Global Finals 2026",
            "format": "BO3",
            "hltv_url": "https://www.hltv.org/matches/2393417/sharks-vs-big-cct-global-finals-2026",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="HEROIC vs Monte",
        url="https://www.hltv.org/matches/2393419/heroic-vs-monte-cct-global-finals-2026",
        timestamp=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "HEROIC",
            "team2": "Monte",
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/4S22uk_gnZTiQiI-hhH4yp.png?ixlib=java-2.1.0&w=50&s=3619ddf1d490573ab3dc261b8c2f3f6f",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/2tc9n4fHkiRIX2FiJSkhgt.png?ixlib=java-2.1.0&w=50&s=7334ef0dd24ba5349b404dfd0e8c6148",
            "event": "CCT Global Finals 2026",
            "format": "BO3",
            "hltv_url": "https://www.hltv.org/matches/2393419/heroic-vs-monte-cct-global-finals-2026",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="EYEBALLERS vs CYBERSHOKE",
        url="https://www.hltv.org/matches/2393198/eyeballers-vs-cybershoke-nodwin-clutch-series-7",
        timestamp=datetime(2026, 4, 25, 17, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "EYEBALLERS",
            "team2": "CYBERSHOKE",
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/3-Mfc-yWBTls8MPSEFhma5.png?invert=true&ixlib=java-2.1.0&sat=-100&w=50&s=2ffde3e377d01663937bf08b74d2057b",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/gzn14uIQ6ENslja9hMqnkj.png?ixlib=java-2.1.0&w=50&s=0bea5f061e9130561d93b89834624603",
            "event": "NODWIN Clutch Series 7",
            "format": "BO3",
            "hltv_url": "https://www.hltv.org/matches/2393198/eyeballers-vs-cybershoke-nodwin-clutch-series-7",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="FOKUS vs KOLESIE",
        url="https://www.hltv.org/matches/2393429/fokus-vs-kolesie-lorgar-rankings-season-1",
        timestamp=datetime(2026, 4, 25, 18, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "FOKUS",
            "team2": "KOLESIE",
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/VFmCLfAOw0WUmb_2fDDX3o.png?ixlib=java-2.1.0&w=50&s=e10aa35f917c5b05e6ed2a011da8d36a",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/-7-6akNJ0_2bI2GrRGd6EW.png?ixlib=java-2.1.0&w=50&s=b8aee4a558dffb251918588deba6cf6f",
            "event": "LORGAR RANKINGS Season 1",
            "format": "BO3",
            "hltv_url": "https://www.hltv.org/matches/2393429/fokus-vs-kolesie-lorgar-rankings-season-1",
        },
    ),
    CollectorItem(
        source="hltv",
        type="upcoming",
        title="TYLOO vs Sensation",
        url="https://www.hltv.org/matches/2393568/tyloo-vs-sensation-esl-challenger-league-season-51-asia-pacific-cup-4",
        timestamp=datetime(2026, 4, 26, 13, 0, tzinfo=timezone.utc),
        metadata={
            "team1": "TYLOO",
            "team2": "Sensation",
            "team1_logo_url": "https://img-cdn.hltv.org/teamlogo/hMPKtNMDxp07n3lrBEHCuq.svg?ixlib=java-2.1.0&s=6d22fc4af07d0cd9d31fcd7f3023af9a",
            "team2_logo_url": "https://img-cdn.hltv.org/teamlogo/e8wRB8g5B9kr77JcfAlmLu.png?ixlib=java-2.1.0&w=50&s=2d25f229460acaeb4d7ef58b07d8069d",
            "event": "ESL Challenger League Season 51 Asia-Pacific Cup 4",
            "format": "BO3",
            "hltv_url": "https://www.hltv.org/matches/2393568/tyloo-vs-sensation-esl-challenger-league-season-51-asia-pacific-cup-4",
        },
    ),
]

# ── Mock podcast episodes ─────────────────────────────────────────

_PODCASTS: list[CollectorItem] = [
    CollectorItem(
        source="HLTV Confirmed",
        type="episode",
        title="Ep. 491 — CCT Global Finals preview, IEM Rio EVPs reviewed, Cache return hype",
        url="https://feeds.simplecast.com/hltvconfirmed/ep491",
        timestamp=datetime(2026, 4, 24, 20, 0, tzinfo=timezone.utc),
        metadata={
            "description": (
                "The panel breaks down the CCT Global Finals bracket, reacts to HLTV's IEM Rio EVP"
                " and All-Star selections, and discusses the implications of Valve's Cache teaser."
            ),
            "duration": "1:22:08",
        },
    ),
    CollectorItem(
        source="Talking Counter",
        type="episode",
        title="The Cache Is Coming — What Does It Mean for the Map Pool?",
        url="https://feeds.simplecast.com/talkingcounter/ep88",
        timestamp=datetime(2026, 4, 24, 17, 30, tzinfo=timezone.utc),
        metadata={
            "description": (
                "Deep dive into Valve's Cache teaser, the history of the map in competitive play,"
                " and which map it might replace in the active duty pool."
            ),
            "duration": "58:44",
        },
    ),
]

# ── Mock YouTube videos ───────────────────────────────────────────

_VIDEOS: list[CollectorItem] = [
    CollectorItem(
        source="youtube",
        type="video",
        title="TRASH TALK + CS2 = Iconic Combination 🗣️🔥",
        url="https://www.youtube.com/watch?v=6cDoKP0DfOY",
        timestamp=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
        metadata={
            "description": (
                "apEX is the obvious pick here... but which other Counter-Strike pros are the BIGGEST"
                " TRASH TALKERS? Check out this compilation from BLAST Premier."
            ),
            "channel": "BLAST Premier",
        },
    ),
    CollectorItem(
        source="youtube",
        type="video",
        title="UFC fighter vs CS players ⚡️",
        url="https://www.youtube.com/watch?v=HWyHn7IuaSw",
        timestamp=datetime(2026, 4, 24, 14, 0, tzinfo=timezone.utc),
        metadata={
            "description": None,
            "channel": "Team Vitality CS",
        },
    ),
    CollectorItem(
        source="youtube",
        type="video",
        title="How Do You Actually Beat Vitality?",
        url="https://www.youtube.com/watch?v=h44fLejRGzo",
        timestamp=datetime(2026, 4, 24, 16, 0, tzinfo=timezone.utc),
        metadata={
            "description": (
                "Vitality are beatable — a tactical breakdown of what teams need to do to"
                " dismantle the world's best roster."
            ),
            "channel": "More Hawka",
        },
    ),
]

# ── Mock Steam patch ──────────────────────────────────────────────

_PATCHES: list[CollectorItem] = [
    CollectorItem(
        source="steam",
        type="patch",
        title="Counter-Strike 2 Update",
        url="https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1830797770237569",
        timestamp=datetime(2026, 4, 24, 18, 0, tzinfo=timezone.utc),
        metadata={
            "version": "v1.41.2.0",
            "changes": [
                "Fixed multiple animation transition issues in the AnimGraph 2 system causing visual glitches on weapon inspect.",
                "Fixed a startup crash occurring on certain hardware configurations after the AnimGraph 2 rollout.",
                "Fixed held-breath state persisting incorrectly when holding the inspect key.",
                "Addressed minor network bandwidth regression introduced in the previous update.",
                "Miscellaneous stability and rendering fixes.",
            ],
        },
    ),
]

# ── Mock social posts ─────────────────────────────────────────────

_SOCIAL: list[CollectorItem] = [
    CollectorItem(
        source="social",
        type="social",
        title="Cache is back next week. I've been waiting 3 years for this.",
        url="https://x.com/s1mple/status/1915300000000000001",
        timestamp=datetime(2026, 4, 24, 20, 5, tzinfo=timezone.utc),
        metadata={
            "handle": "s1mple",
            "display_name": "s1mple",
            "verified": True,
            "body": "Cache is back next week. I've been waiting 3 years for this.",
            "context": "Reacting to Valve's Cache teaser tweet.",
        },
    ),
    CollectorItem(
        source="social",
        type="social",
        title="Really proud of the boys today. Legacy is building something real.",
        url="https://x.com/dumau/status/1915300000000000002",
        timestamp=datetime(2026, 4, 24, 23, 12, tzinfo=timezone.utc),
        metadata={
            "handle": "dumau",
            "display_name": "dumau",
            "verified": True,
            "body": "Really proud of the boys today. Legacy is building something real. 🔥",
            "context": "After Legacy's dominant 2-0 win over 9z.",
        },
    ),
    CollectorItem(
        source="social",
        type="social",
        title="AnimGraph 2 is actually smoother now. Happy Valve is listening.",
        url="https://x.com/NiKo/status/1915300000000000003",
        timestamp=datetime(2026, 4, 24, 21, 44, tzinfo=timezone.utc),
        metadata={
            "handle": "NiKo",
            "display_name": "NiKo",
            "verified": True,
            "body": "AnimGraph 2 is actually smoother now. Happy Valve is listening.",
            "context": "Reacting to today's CS2 patch notes.",
        },
    ),
]

# ── Mock This Day in CS history entry ────────────────────────────

_THIS_DAY = HistoryEntry(
    year=2024,
    headline="Valve implements left-handed viewmodel support in Counter-Strike 2",
    narrative=(
        "A quality-of-life update brings ambidextrous viewmodel functionality to CS2, allowing "
        "players to dynamically switch the weapon to their left hand via a simple console command. "
        "The patch also networks the viewmodel orientation to first-person spectators for accurate "
        "broadcasting, a feature long requested by the community since the game's 2023 launch."
    ),
    visual_label="CS2 '24",
    source_url="https://www.gamespot.com/articles/counter-strike-2-update-adds-ambidextrous-support-adjusts-buy-menu/1100-6523024/",
)

# ── Assemble DigestOutput ─────────────────────────────────────────

_SUMMARY_LINE = (
    "Valve strongly hints at Cache's return; HLTV reveals IEM Rio EVPs and All-Stars; "
    "CS2 receives animation and crash fixes."
)


def _build_digest() -> DigestOutput:
    sections: dict = {
        "Matches": SectionOutput(
            intro="Several best-of-three series concluded across the CCT Global Finals, BetBoom RUSH B Summit, and NODWIN Clutch Series today, including a notable upset.",
            items=_MATCHES,
        ),
        "Clips": SectionOutput(
            intro="Community-submitted clips showcase skilled gameplay and community reactions to the latest map news, including a preview of a new Wingman map.",
            items=_CLIPS,
        ),
        "News": SectionOutput(
            intro="Today's news highlights a strong Valve teaser for the return of Cache, alongside a roster departure and a detailed breakdown of IEM Rio's top performers.",
            items=_NEWS,
        ),
        "Videos": SectionOutput(
            intro="New video content covers team dynamics, player crossovers, and strategic analyses of the world's best roster.",
            items=_VIDEOS,
        ),
        "Podcasts": SectionOutput(
            intro="Long-form audio dropped overnight covering the Cache return hype, IEM Rio EVPs, and a full CCT Global Finals preview.",
            items=_PODCASTS,
        ),
        "Patches": SectionOutput(
            intro="A new CS2 update addresses multiple animation issues within the AnimGraph 2 system and resolves a critical startup crash, among other miscellaneous fixes.",
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
        social_items=_SOCIAL,
        upcoming_items=_UPCOMING,
        this_day=_THIS_DAY,
    )

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(f"Demo briefing generated: {_OUTPUT_PATH}")
    print("Open it in your browser to see what Overpass looks like.")
