from __future__ import annotations

from dataclasses import dataclass

from xintelops.config import Settings, get_settings
from xintelops.db.supabase_client import SupabaseClient
from xintelops.ingest.base import IngestedItem
from xintelops.vector.embeddings import EmbeddingService


@dataclass
class DedupResult:
    is_duplicate: bool
    similarity_score: float | None
    matched_id: int | None


class Deduplicator:
    def __init__(
        self,
        settings: Settings | None = None,
        db: SupabaseClient | None = None,
        embedder: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db or SupabaseClient(self.settings)
        self.embedder = embedder or EmbeddingService(self.settings)

    def process(self, item: IngestedItem) -> tuple[DedupResult, list[float]]:
        embedding = self.embedder.embed(item.raw_text)
        matches = self.db.find_similar_feeds(embedding, days=7, limit=5)
        best_score = 0.0
        best_id = None
        for match in matches:
            score = float(match.get("similarity") or 0)
            if score > best_score:
                best_score = score
                best_id = match.get("id")

        is_duplicate = best_score >= self.settings.similarity_threshold
        return (
            DedupResult(
                is_duplicate=is_duplicate,
                similarity_score=best_score if best_id else None,
                matched_id=best_id,
            ),
            embedding,
        )
