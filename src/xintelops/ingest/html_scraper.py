from __future__ import annotations

import csv
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from xintelops.config import Settings, get_settings
from xintelops.ingest.base import IngestedItem

USER_AGENT = "XIntelOps Intelligence Engine/2.0"

# Tier 0/1 direct feeds mirrored from the production edge function
DIRECT_SOURCES = [
    {"url": "https://feeds.reuters.com/reuters/topNews", "name": "Reuters"},
    {"url": "https://feeds.reuters.com/reuters/worldNews", "name": "Reuters World"},
    {"url": "https://apnews.com/index.rss", "name": "AP News"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "name": "BBC World"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "name": "Al Jazeera"},
    {"url": "https://tass.com/rss/v2.xml", "name": "TASS"},
    {"url": "https://en.irna.ir/rss", "name": "IRNA"},
    {"url": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10", "name": "DoD News"},
    {"url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "name": "UN News"},
    {"url": "https://www.sipri.org/rss", "name": "SIPRI"},
]

GOOGLE_NEWS_QUERIES = [
    {"url": "https://news.google.com/rss/search?q=(site:reuters.com+OR+site:apnews.com)+military+OR+strike&hl=en-US&gl=US&ceid=US:en", "name": "GNews: Military/Conflict"},
    {"url": "https://news.google.com/rss/search?q=(site:csis.org+OR+site:carnegieendowment.org+OR+site:rand.org)&hl=en-US&gl=US&ceid=US:en", "name": "GNews: Think Tanks"},
]


class HTMLScraper:
    """Fetch HTML pages and direct RSS endpoints for high-priority sources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fetch(self) -> list[IngestedItem]:
        items: list[IngestedItem] = []
        for source in DIRECT_SOURCES + GOOGLE_NEWS_QUERIES:
            item = self._fetch_source(source["url"], source["name"])
            if item:
                items.append(item)
            time.sleep(self.settings.rate_delay_ms / 1000)
        return items

    def _fetch_source(self, url: str, name: str) -> IngestedItem | None:
        try:
            response = requests.get(
                url,
                timeout=self.settings.fetch_timeout_sec,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/rss+xml, application/xml, text/html, */*",
                },
            )
            response.raise_for_status()
            text = response.text
        except Exception:
            return None

        if "rss" in response.headers.get("Content-Type", "") or url.endswith(".rss") or "rss" in url:
            soup = BeautifulSoup(text, "xml")
            chunks = [tag.get_text(" ", strip=True) for tag in soup.find_all(["title", "description"])[:12]]
        else:
            soup = BeautifulSoup(text, "lxml")
            chunks = [tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2", "p"])[:20]]

        clean = " ".join(chunks)
        clean = " ".join(clean.split())[: self.settings.max_chars_per_source]
        if not clean:
            return None
        return IngestedItem(
            source=name,
            raw_text=f"[SOURCE: {name}]\n{clean}",
            title=name,
            url=url,
            source_type="html",
        )


class SelectorScraper:
    """Scrape curated HTML sources from data/sources.csv using CSS selectors."""

    def __init__(self, settings: Settings | None = None, csv_path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.csv_path = csv_path or (self.settings.sources_csv_path.parent / "sources.csv")

    def fetch(self) -> list[IngestedItem]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        items: list[IngestedItem] = []
        for row in rows:
            item = self._scrape_row(row)
            if item:
                items.append(item)
            time.sleep(self.settings.rate_delay_ms / 1000)
        return items

    def _scrape_row(self, row: dict[str, str]) -> IngestedItem | None:
        url = row.get("url", "")
        if not url:
            return None
        try:
            response = requests.get(
                url,
                timeout=self.settings.fetch_timeout_sec,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
        except Exception:
            return None

        main_sel = row.get("selector_main", "article")
        title_sel = row.get("selector_title", "h1")
        blocks = soup.select(main_sel)[:5]
        titles = [el.get_text(" ", strip=True) for el in soup.select(title_sel)[:5]]
        text = " | ".join(titles + [b.get_text(" ", strip=True) for b in blocks])
        text = text[: self.settings.max_chars_per_source]
        if not text:
            return None
        return IngestedItem(
            source=row.get("source_name", "Unknown"),
            raw_text=text,
            title=titles[0] if titles else row.get("source_name", ""),
            url=url,
            source_type="scraper",
        )
