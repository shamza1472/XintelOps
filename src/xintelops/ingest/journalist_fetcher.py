from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests

from xintelops.config import Settings, get_settings
from xintelops.ingest.base import IngestedItem

USER_AGENT = "XIntelOps/2.0"
RETWEET_PATTERN = re.compile(r"^(RT\s+@\w+|Retweeted\b)", re.IGNORECASE)


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


@dataclass
class JournalistPost:
    url: str
    text: str
    published: str = ""


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


def is_retweet(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    if RETWEET_PATTERN.match(stripped):
        return True
    if stripped.lower().startswith("rt @"):
        return True
    return False


def _entry_text(entry: Any) -> str:
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    return title.strip() or summary.strip()


def parse_original_posts(parsed: Any, max_posts: int = 3) -> list[JournalistPost]:
    posts: list[JournalistPost] = []
    for entry in parsed.entries:
        text = _entry_text(entry)
        if not text or is_retweet(text):
            continue
        link = getattr(entry, "link", "") or ""
        if "/status/" not in link:
            continue
        published = getattr(entry, "published", "") or getattr(entry, "updated", "") or ""
        posts.append(JournalistPost(url=link, text=text, published=published))
        if len(posts) >= max_posts:
            break
    return posts


def fetch_posts_for_journalist(
    journalist: Journalist,
    settings: Settings,
    max_posts: int = 3,
) -> list[JournalistPost]:
    rss_url = f"{settings.twitter_rss_base}/{journalist.handle}"
    try:
        response = requests.get(
            rss_url,
            timeout=settings.fetch_timeout_sec,
            headers={"User-Agent": USER_AGENT},
        )
        if response.status_code != 200:
            return []
        parsed = feedparser.parse(response.content)
    except Exception:
        return []
    return parse_original_posts(parsed, max_posts=max_posts)


def _today_category(utc_now: datetime) -> str:
    pkt = utc_now.timestamp() + 5 * 3600
    pkt_dt = datetime.fromtimestamp(pkt, tz=timezone.utc)
    ts_day = (pkt_dt.weekday() + 1) % 7
    return {0: "A", 1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F"}[ts_day]


def _prioritize_journalists(journalists: list[Journalist], category: str) -> list[Journalist]:
    def sort_key(j: Journalist) -> tuple[int, str]:
        if j.roster_tier == "core" and j.category == category:
            return (0, j.name)
        if j.roster_tier == "core":
            return (1, j.name)
        return (2, j.name)

    return sorted(journalists, key=sort_key)


def fetch_journalist_candidates(
    journalists: list[Journalist],
    settings: Settings | None = None,
    utc_now: datetime | None = None,
    max_journalists: int = 25,
    posts_per_journalist: int = 3,
) -> list[dict[str, Any]]:
    """Return journalists who posted original content recently (not retweets)."""
    settings = settings or get_settings()
    utc_now = utc_now or datetime.now(timezone.utc)
    category = _today_category(utc_now)
    ordered = _prioritize_journalists(journalists, category)

    candidates: list[dict[str, Any]] = []
    batch_size = settings.journalist_batch_size
    for idx, journalist in enumerate(ordered[:max_journalists]):
        posts = fetch_posts_for_journalist(journalist, settings, max_posts=posts_per_journalist)
        if not posts:
            continue
        candidates.append(
            {
                "name": journalist.name,
                "handle": journalist.handle,
                "outlet": journalist.outlet,
                "category": journalist.category,
                "focus": journalist.focus,
                "profile_url": journalist.profile_url,
                "region": journalist.region,
                "recent_posts": [
                    {"url": p.url, "text": p.text, "published": p.published} for p in posts
                ],
            }
        )
        if (idx + 1) % batch_size == 0:
            time.sleep(settings.rate_delay_ms / 1000)
    return candidates


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
        posts = fetch_posts_for_journalist(journalist, self.settings, max_posts=5)
        if not posts:
            return None

        lines = []
        for post in posts:
            lines.append(f"• [{post.url}] {post.text}")
        body = "\n".join(lines)[: self.settings.max_chars_per_source]
        return IngestedItem(
            source=f"{journalist.name} (@{journalist.handle})",
            raw_text=f"[JOURNALIST: {journalist.name} | Category {journalist.category}]\n{body}",
            title=journalist.name,
            url=posts[0].url,
            source_type="journalist",
            region=journalist.region,
            domain=journalist.focus,
        )


def get_journalist_for_today(journalists: list[Journalist], utc_now) -> Journalist:
    """Legacy rotation helper — prefer fetch_journalist_candidates for engagement."""
    pkt_offset = 5 * 60 * 60
    pkt = utc_now.timestamp() + pkt_offset
    pkt_dt = datetime.fromtimestamp(pkt, tz=timezone.utc)
    day_of_week = pkt_dt.weekday()
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
