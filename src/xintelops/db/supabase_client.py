from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from supabase import Client, create_client

from xintelops.config import Settings, get_settings


class SupabaseClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
            self.client: Client | None = None
        else:
            self.client = create_client(
                self.settings.supabase_url,
                self.settings.supabase_service_role_key,
            )

    def _require_client(self) -> Client:
        if not self.client:
            raise RuntimeError("Supabase credentials are not configured")
        return self.client

    def insert_raw_feed(
        self,
        *,
        source: str,
        raw_text: str,
        title: str = "",
        url: str = "",
        source_type: str = "news",
        embedding: list[float] | None = None,
        content_hash: str | None = None,
        is_duplicate: bool = False,
        similarity_score: float | None = None,
    ) -> int | None:
        payload = {
            "source": source,
            "raw_text": raw_text,
            "title": title,
            "url": url,
            "source_type": source_type,
            "is_duplicate": is_duplicate,
            "similarity_score": similarity_score,
        }
        if embedding is not None:
            payload["vector_embedding"] = embedding
        if content_hash is not None:
            payload["content_hash"] = content_hash

        result = self._require_client().table("ingested_raw_feeds").insert(payload).execute()
        rows = result.data or []
        return rows[0]["id"] if rows else None

    def find_similar_feeds(self, embedding: list[float], days: int = 7, limit: int = 5) -> list[dict[str, Any]]:
        # RPC helper; fallback to recent-row scan if RPC not deployed yet
        try:
            result = self._require_client().rpc(
                "match_ingested_feeds",
                {
                    "query_embedding": embedding,
                    "match_threshold": self.settings.similarity_threshold,
                    "match_count": limit,
                    "days_back": days,
                },
            ).execute()
            return result.data or []
        except Exception:
            return []

    def find_by_content_hash(self, digest: str, days: int = 7) -> dict[str, Any] | None:
        try:
            result = (
                self._require_client()
                .table("ingested_raw_feeds")
                .select("id, source, timestamp")
                .eq("content_hash", digest)
                .eq("is_duplicate", False)
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def insert_synthesized_intelligence(self, payload: dict[str, Any]) -> int | None:
        result = self._require_client().table("synthesized_intelligence").insert(payload).execute()
        rows = result.data or []
        return rows[0]["id"] if rows else None

    def dual_write_legacy(self, result: dict[str, Any]) -> dict[str, int | None]:
        if not self.settings.dual_write_legacy:
            return {"raw_signal_id": None, "output_id": None, "pipeline_log_id": None}

        client = self._require_client()
        signal = result.get("top_signal", {})
        raw = (
            client.table("raw_signals")
            .insert(
                {
                    "source_name": signal.get("source", "Unknown"),
                    "layer": signal.get("tier", "L0"),
                    "trust": signal.get("confidence", "medium"),
                    "region": signal.get("region", "Global"),
                    "domain": signal.get("domain", "diplomatic_signal"),
                    "title": signal.get("title", ""),
                    "summary": signal.get("summary", ""),
                    "url": signal.get("url", ""),
                    "processed": True,
                }
            )
            .execute()
        )
        raw_signal_id = raw.data[0]["id"] if raw.data else None

        output = (
            client.table("intelligence_outputs")
            .insert(
                {
                    "source_name": signal.get("source", "Unknown"),
                    "region": signal.get("region", "Global"),
                    "domain": signal.get("domain", "diplomatic_signal"),
                    "confidence": signal.get("confidence", "medium"),
                    "crisis_flag": signal.get("crisis_flag", False),
                    "x_post": result.get("x_post", ""),
                    "x_thread": result.get("x_thread"),
                    "linkedin_post": result.get("linkedin_post", ""),
                    "internal_brief": result.get("internal_brief", ""),
                    "implications_48h": result.get("implications_48h", ""),
                    "implications_7d": result.get("implications_7d", ""),
                    "redteam_status": "approved",
                    "verified_facts": "\n".join(signal.get("verified_facts", []) or []),
                    "raw_signal_id": raw_signal_id,
                }
            )
            .execute()
        )
        output_id = output.data[0]["id"] if output.data else None

        journalist = result.get("journalist", {})
        client.table("content_schedule").insert(
            {
                "run_date": result.get("date_pkt"),
                "session_label": result.get("scan_session"),
                "morning_format": result.get("post_format", "SHORT POST"),
                "morning_signal": signal.get("title", ""),
                "morning_draft": result.get("x_post", ""),
                "midday_signal": signal.get("title", ""),
                "midday_draft": result.get("what_most_missed", ""),
                "evening_format": "journalist_comment",
                "evening_target": journalist.get("target_post_url") or f"@{journalist.get('handle', '')}",
                "evening_draft": journalist.get("comment_draft", ""),
                "linkedin_post_day": result.get("day_of_week", ""),
                "linkedin_type": "flagship_analysis" if result.get("linkedin_today") else "not_today",
                "linkedin_draft": result.get("linkedin_post", ""),
                "intelligence_output_id": output_id,
            }
        ).execute()

        client.table("journalist_engagements").insert(
            {
                "run_date": result.get("date_pkt"),
                "session_label": result.get("scan_session"),
                "journalist_category": journalist.get("category", ""),
                "journalist_name": journalist.get("name", ""),
                "journalist_handle": journalist.get("handle", ""),
                "post_url": journalist.get("target_post_url") or journalist.get("profile_url", ""),
                "post_summary": journalist.get("target_post_summary")
                or journalist.get("post_summary", ""),
                "comment_draft": journalist.get("comment_draft", ""),
                "engagement_rationale": journalist.get("why_we_comment")
                or journalist.get("engagement_rationale", ""),
                "intelligence_output_id": output_id,
            }
        ).execute()

        pl = (
            client.table("pipeline_log")
            .insert(
                {
                    "session_label": result.get("scan_session"),
                    "signals_scraped": result.get("signals_scanned", 0),
                    "signals_verified": result.get("signals_verified", 0),
                    "signals_approved": result.get("signals_verified", 0),
                    "signals_blocked": result.get("signals_blocked", 0),
                    "crisis_detected": result.get("crisis_detected", False),
                    "email_sent": False,
                }
            )
            .execute()
        )
        pipeline_log_id = pl.data[0]["id"] if pl.data else None
        return {
            "raw_signal_id": raw_signal_id,
            "output_id": output_id,
            "pipeline_log_id": pipeline_log_id,
        }

    def seed_trusted_sources(self, csv_path: Path) -> int:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        trust_map = {"Very High": 0.95, "High": 0.85, "Medium": 0.70, "Low": 0.50}
        count = 0
        for row in rows:
            trust = row.get("Trust Level", "Medium")
            payload = {
                "source_name": row.get("Source Name", ""),
                "reliability_score": trust_map.get(trust, 0.70),
                "layer": row.get("Layer", ""),
                "domain": row.get("Domain", ""),
            }
            if not payload["source_name"]:
                continue
            self._require_client().table("trusted_sources").upsert(payload).execute()
            count += 1
        return count

    def seed_journalists(self, csv_path: Path) -> int:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        count = 0
        for row in rows:
            payload = {
                "name": row["name"],
                "handle": row["handle"],
                "outlet": row["outlet"],
                "category": row["category"],
                "focus": row["focus"],
                "region": row["region"],
                "profile_url": row["profile_url"],
                "roster_tier": row["roster_tier"],
                "engagement_day": row["engagement_day"],
                "trust_level": row["trust_level"],
                "reliability_score": 0.85,
            }
            self._require_client().table("journalist_engagement_targets").upsert(
                payload, on_conflict="handle"
            ).execute()
            count += 1
        return count

    def mark_email_sent(self, pipeline_log_id: int | None, sent: bool) -> None:
        if not pipeline_log_id:
            return
        self._require_client().table("pipeline_log").update({"email_sent": sent}).eq(
            "id", pipeline_log_id
        ).execute()
