from __future__ import annotations

import csv
import html
import re
import time
from pathlib import Path

import feedparser
import requests

from xintelops.config import Settings, get_settings
from xintelops.delivery.ranking import source_priority_score
from xintelops.ingest.base import IngestedItem

USER_AGENT = "XIntelOps Intelligence Engine/2.0"


def _clean_text(text: str, max_chars: int) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _load_sources(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class RSSFetcher:
    """Fetch RSS/Atom feeds from sources with Alt Feed / RSS entries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sources = _load_sources(self.settings.sources_csv_path)

    def fetch(self) -> list[IngestedItem]:
        items: list[IngestedItem] = []
        ordered = sorted(
            self.sources,
            key=lambda row: source_priority_score(
                row.get("Source Name", ""),
                row.get("Region", ""),
                row.get("Domain", ""),
            ),
            reverse=True,
        )
        for row in ordered:
            feed_url = (row.get("Alt Feed / RSS (if any)") or "").strip()
            if not feed_url:
                continue
            items.extend(self._fetch_feed(row, feed_url))
            time.sleep(self.settings.rate_delay_ms / 1000)
        return items

    def _fetch_feed(self, row: dict[str, str], feed_url: str) -> list[IngestedItem]:
        try:
            response = requests.get(
                feed_url,
                timeout=self.settings.fetch_timeout_sec,
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
        except Exception:
            return []

        source_name = row.get("Source Name", "Unknown")
        results: list[IngestedItem] = []
        for entry in parsed.entries[:5]:
            title = _clean_text(getattr(entry, "title", ""), 300)
            summary = _clean_text(
                getattr(entry, "summary", "") or getattr(entry, "description", ""),
                self.settings.max_chars_per_source,
            )
            link = getattr(entry, "link", "")
            body = f"{title}\n{summary}".strip()
            if not body:
                continue
            results.append(
                IngestedItem(
                    source=source_name,
                    raw_text=body,
                    title=title,
                    url=link,
                    source_type="rss",
                    layer=row.get("Layer", ""),
                    region=row.get("Region", ""),
                    domain=row.get("Domain", ""),
                )
            )
        return results
