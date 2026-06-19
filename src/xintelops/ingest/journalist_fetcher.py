from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

import feedparser
import requests

from xintelops.config import Settings, get_settings
from xintelops.ingest.base import IngestedItem

USER_AGENT = "XIntelOps/2.0"


@dataclass
class Journalist:
    name: str
    handle: str
    outlet: str
    category: str
    focus: str
    region: str
    profile_url: str
    roster_tier: str
    engagement_day: str
    trust_level: str
    notes: str = ""


def load_journalists(csv_path: Path) -> list[Journalist]:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    journalists: list[Journalist] = []
    for row in rows:
        journalists.append(
            Journalist(
                name=row["name"],
                handle=row["handle"],
                outlet=row["outlet"],
                category=row["category"],
                focus=row["focus"],
                region=row["region"],
                profile_url=row["profile_url"],
                roster_tier=row["roster_tier"],
                engagement_day=row["engagement_day"],
                trust_level=row["trust_level"],
                notes=row.get("notes", ""),
            )
        )
    return journalists


class JournalistFetcher:
    """Fetch recent public posts for journalist handles via RSS syndication."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.journalists = load_journalists(self.settings.journalists_csv_path)

    def fetch(self, category: str | None = None, limit: int | None = None) -> list[IngestedItem]:
        targets = self.journalists
        if category:
            targets = [j for j in targets if j.category == category]
        if limit:
            targets = targets[:limit]

        items: list[IngestedItem] = []
        batch_size = self.settings.journalist_batch_size
        for idx, journalist in enumerate(targets):
            item = self._fetch_journalist(journalist)
            if item:
                items.append(item)
            if (idx + 1) % batch_size == 0:
                time.sleep(self.settings.rate_delay_ms / 1000)
        return items

    def _fetch_journalist(self, journalist: Journalist) -> IngestedItem | None:
        rss_url = f"{self.settings.twitter_rss_base}/{journalist.handle}"
        try:
            response = requests.get(
                rss_url,
                timeout=self.settings.fetch_timeout_sec,
                headers={"User-Agent": USER_AGENT},
            )
            if response.status_code != 200:
                return None
            parsed = feedparser.parse(response.content)
        except Exception:
            return None

        posts: list[str] = []
        for entry in parsed.entries[:5]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            posts.append(f"• {title} {summary}".strip())
        if not posts:
            return None

        body = "\n".join(posts)[: self.settings.max_chars_per_source]
        return IngestedItem(
            source=f"{journalist.name} (@{journalist.handle})",
            raw_text=f"[JOURNALIST: {journalist.name} | Category {journalist.category}]\n{body}",
            title=journalist.name,
            url=journalist.profile_url,
            source_type="journalist",
            region=journalist.region,
            domain=journalist.focus,
        )


def get_journalist_for_today(journalists: list[Journalist], utc_now) -> Journalist:
    """Rotate primary engagement journalist within today's category roster."""
    pkt_offset = 5 * 60 * 60
    pkt = utc_now.timestamp() + pkt_offset
    from datetime import datetime, timezone

    pkt_dt = datetime.fromtimestamp(pkt, tz=timezone.utc)
    day_of_week = pkt_dt.weekday()
    # Python weekday: Mon=0 ... Sun=6; map to TS roster (Sun=0)
    ts_day = (day_of_week + 1) % 7
    category_map = {0: "A", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F"}
    category = category_map[ts_day]

    core = [
        j
        for j in journalists
        if j.roster_tier == "core"
        and j.category == category
        and str(ts_day) in [d.strip() for d in j.engagement_day.split(",")]
    ]
    if not core:
        core = [j for j in journalists if j.roster_tier == "core" and j.category == category]
    if not core:
        core = journalists

    week_num = pkt_dt.isocalendar().week
    return core[week_num % len(core)]
