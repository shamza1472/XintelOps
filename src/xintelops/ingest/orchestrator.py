from __future__ import annotations

from datetime import datetime, timezone

from xintelops.ingest.base import IngestedItem
from xintelops.ingest.html_scraper import HTMLScraper, SelectorScraper
from xintelops.ingest.journalist_fetcher import JournalistFetcher
from xintelops.ingest.rss_fetcher import RSSFetcher
from xintelops.ingest.telemetry import TelemetryFetcher


class IngestOrchestrator:
    """Run all ingestion modules and merge results."""

    def __init__(self) -> None:
        self.rss = RSSFetcher()
        self.html = HTMLScraper()
        self.selector = SelectorScraper()
        self.telemetry = TelemetryFetcher()
        self.journalists = JournalistFetcher()

    def fetch_all(self, include_journalists: bool = True) -> list[IngestedItem]:
        items: list[IngestedItem] = []
        items.extend(self.html.fetch())
        items.extend(self.rss.fetch())
        items.extend(self.selector.fetch())
        items.extend(self.telemetry.fetch())
        if include_journalists:
            category = self._today_category()
            items.extend(self.journalists.fetch(category=category, limit=12))
            items.extend(self.journalists.fetch(limit=20))
        return items

    def bundle_text(self, items: list[IngestedItem]) -> str:
        sections = {
            "news": [],
            "rss": [],
            "telemetry": [],
            "journalist": [],
        }
        for item in items:
            sections.setdefault(item.source_type, []).append(item)

        parts = ["═══ XINTELOPS SOURCE BUNDLE ═══"]
        for label, key in [
            ("DIRECT + HTML FEEDS", "news"),
            ("RSS CATALOG", "rss"),
            ("TELEMETRY", "telemetry"),
            ("JOURNALIST POSTS", "journalist"),
        ]:
            block = sections.get(key, [])
            if not block:
                continue
            parts.append(f"\n═══ {label} ═══")
            for item in block:
                parts.append(f"\n[{item.source}]\n{item.raw_text}")
        return "\n".join(parts)[:50000]

    def _today_category(self) -> str:
        utc_now = datetime.now(timezone.utc)
        pkt = utc_now.timestamp() + 5 * 3600
        pkt_dt = datetime.fromtimestamp(pkt, tz=timezone.utc)
        ts_day = (pkt_dt.weekday() + 1) % 7
        return {0: "A", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F"}[ts_day]
