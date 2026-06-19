from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from xintelops.config import Settings, get_settings
from xintelops.db.supabase_client import SupabaseClient
from xintelops.ingest.base import IngestedItem


@dataclass
class DedupResult:
    is_duplicate: bool
    similarity_score: float | None
    matched_id: int | None
    content_hash: str


def normalize_for_hash(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]


def content_hash(text: str) -> str:
    normalized = normalize_for_hash(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class HashDeduplicator:
    """Zero-cost dedup using normalized content hashes (Cursor-native mode)."""

    def __init__(
        self,
        settings: Settings | None = None,
        db: SupabaseClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or SupabaseClient(self.settings)

    def process(self, item: IngestedItem) -> DedupResult:
        digest = content_hash(item.raw_text)
        matched = self.db.find_by_content_hash(digest, days=7)
        if matched:
            return DedupResult(
                is_duplicate=True,
                similarity_score=1.0,
                matched_id=matched.get("id"),
                content_hash=digest,
            )
        return DedupResult(
            is_duplicate=False,
            similarity_score=None,
            matched_id=None,
            content_hash=digest,
        )
