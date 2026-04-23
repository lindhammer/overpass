import asyncio
from bs4 import BeautifulSoup

from overpass.config import load_config
from overpass.hltv.browser import HLTVBrowserClient

URL = "https://www.hltv.org/matches/2393442/9z-vs-alka-betboom-rush-b-summit-season-3"


async def inspect(headless: bool) -> None:
    config = load_config().hltv
    client = HLTVBrowserClient(
        base_url=config.base_url,
        headless=headless,
        request_timeout_seconds=config.request_timeout_seconds,
        min_request_interval_seconds=0.0,
    )
    try:
        html = await client.fetch_page_content(URL, wait_until="load")
    finally:
        await client.close()

    soup = BeautifulSoup(html, "html.parser")
    print("HEADLESS", headless)
    print("TITLE", soup.title.get_text(" ", strip=True) if soup.title else None)
    print("TEAM1", soup.select_one(".team1-gradient .teamName").get_text(" ", strip=True) if soup.select_one(".team1-gradient .teamName") else None)
    print("TEAM2", soup.select_one(".team2-gradient .teamName").get_text(" ", strip=True) if soup.select_one(".team2-gradient .teamName") else None)
    print("CHALLENGE", "just a moment" in html.lower() or "checking your browser before accessing" in html.lower())
    print("FIRST_180", html[:180].replace("\n", " "))
    print("---")


async def main() -> None:
    await inspect(True)
    await inspect(False)


if __name__ == "__main__":
    asyncio.run(main())
