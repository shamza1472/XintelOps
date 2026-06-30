from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from supabase import Client, create_client

from xintelops.config import Settings, get_settings
from xintelops.delivery.linkedin_synthesis import build_linkedin_block
from xintelops.delivery.active_event_clusters import same_event_cluster
from xintelops.delivery.live_events import normalize_event_key
from xintelops.delivery.queue import resolve_queue

PKT = timezone(timedelta(hours=5))


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

    def get_latest_content_schedule(self) -> dict[str, Any] | None:
        try:
            result = (
                self._require_client()
                .table("content_schedule")
                .select("*")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            return rows[0] if rows else None
        except Exception:
            return None

    def get_intelligence_outputs_for_synthesis(self, days: int = 7, limit: int = 30) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            result = (
                self._require_client()
                .table("intelligence_outputs")
                .select(
                    "id, source_name, region, domain, confidence, crisis_flag, "
                    "internal_brief, implications_7d, what_most_people_missed, linkedin_post, created_at"
                )
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def get_active_live_events(self) -> list[dict[str, Any]]:
        try:
            now = datetime.now(timezone.utc).isoformat()
            result = (
                self._require_client()
                .table("active_live_events")
                .select("*")
                .eq("resolved", False)
                .gte("active_until", now)
                .order("live_event_score", desc=True)
                .limit(100)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def get_recent_recommendations(self, hours: int = 12) -> list[dict[str, Any]]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        try:
            result = (
                self._require_client()
                .table("signal_recommendations")
                .select("*")
                .gte("recommended_at", cutoff)
                .order("recommended_at", desc=True)
                .limit(50)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def resolve_expired_active_events(self) -> int:
        """Mark expired active events as resolved."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            expired = (
                self._require_client()
                .table("active_live_events")
                .select("id")
                .eq("resolved", False)
                .lt("active_until", now)
                .execute()
            )
            ids = [row["id"] for row in (expired.data or [])]
            if not ids:
                return 0
            for row_id in ids:
                self._require_client().table("active_live_events").update(
                    {"resolved": True, "current_status": "resolved", "updated_at": now}
                ).eq("id", row_id).execute()
            return len(ids)
        except Exception:
            return 0

    def _find_similar_active_row(self, client, event: dict[str, Any]) -> dict[str, Any] | None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            rows = (
                client.table("active_live_events")
                .select("*")
                .eq("resolved", False)
                .gte("active_until", now)
                .limit(100)
                .execute()
            ).data or []
        except Exception:
            return None
        for row in rows:
            if row.get("normalized_event_key") == event.get("normalized_event_key"):
                return row
            if same_event_cluster(row, event):
                return row
        return None

    def persist_live_events(self, result: dict[str, Any]) -> None:
        self.resolve_expired_active_events()
        pending = result.get("_pending_active_events") or []
        if not pending:
            return
        client = self._require_client()
        now = datetime.now(timezone.utc).isoformat()
        for event in pending:
            key = event.get("normalized_event_key")
            if not key:
                continue
            material = bool(event.get("material_change") or event.get("new_information_detected"))
            status = "updated" if material else "cooling"
            try:
                existing = (
                    client.table("active_live_events")
                    .select("id")
                    .eq("normalized_event_key", key)
                    .eq("resolved", False)
                    .limit(1)
                    .execute()
                )
                rows = existing.data or []
                target = rows[0] if rows else self._find_similar_active_row(client, event)

                if target:
                    client.table("active_live_events").update(
                        {
                            "last_seen_at": now,
                            "active_until": event.get("active_until"),
                            "live_event_score": event.get("live_event_score"),
                            "momentum_score": event.get("momentum_score"),
                            "crisis_flag": event.get("crisis_flag"),
                            "latest_update_summary": event.get("latest_update_summary"),
                            "current_status": status,
                            "scan_session": event.get("scan_session"),
                            "freshness_class": event.get("freshness_class"),
                            "updated_at": now,
                            "title": event.get("title") or target.get("title"),
                            "normalized_event_key": key,
                        }
                    ).eq("id", target["id"]).execute()
                else:
                    event["current_status"] = "active"
                    client.table("active_live_events").insert(event).execute()
            except Exception:
                continue

    def log_immediate_recommendation(self, result: dict[str, Any]) -> None:
        rec = result.get("_immediate_recommendation") or {}
        title = rec.get("title") or (result.get("operator_decisions") or {}).get("one_signal_to_post", {}).get("title")
        if not title:
            return
        action = rec.get("action") or "MONITOR"
        if action not in {"X POST", "X THREAD"}:
            return
        key = rec.get("normalized_event_key") or normalize_event_key(title)
        try:
            self._require_client().table("signal_recommendations").insert(
                {
                    "normalized_event_key": key,
                    "title": title,
                    "freshness_class": rec.get("freshness_class"),
                    "recommended_at": datetime.now(timezone.utc).isoformat(),
                    "scan_session": result.get("scan_session"),
                    "action": action,
                    "live_event_score": rec.get("live_event_score"),
                }
            ).execute()
        except Exception:
            pass

        try:
            existing = (
                self._require_client()
                .table("active_live_events")
                .select("times_recommended")
                .eq("normalized_event_key", key)
                .limit(1)
                .execute()
            )
            rows = existing.data or []
            times = (rows[0].get("times_recommended") or 0) + 1 if rows else 1
            self._require_client().table("active_live_events").update(
                {
                    "last_recommended_at": datetime.now(timezone.utc).isoformat(),
                    "times_recommended": times,
                    "previous_action": action,
                }
            ).eq("normalized_event_key", key).execute()
        except Exception:
            pass

    def resolve_operator_queue(self, result: dict[str, Any]) -> dict[str, Any]:
        """Load prior queue, resolve conflicts, build LinkedIn block, attach content_queue."""
        previous = self.get_latest_content_schedule()
        outputs = self.get_intelligence_outputs_for_synthesis(days=7)
        if not outputs:
            outputs = self.get_intelligence_outputs_for_synthesis(days=30)
        from xintelops.delivery.signal_display import format_top_signals_block

        if not result.get("top_signals_display"):
            result["top_signals_display"] = format_top_signals_block(result)
        result["linkedin_block"] = build_linkedin_block(result, outputs)
        result = resolve_queue(result, previous)
        self.persist_live_events(result)
        self.log_immediate_recommendation(result)
        return result

    def dual_write_legacy(self, result: dict[str, Any]) -> dict[str, int | None]:
        if not self.settings.dual_write_legacy:
            return {"raw_signal_id": None, "output_id": None, "pipeline_log_id": None}

        client = self._require_client()
        signal = result.get("top_signal", {})
        raw_payload = {
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
        raw_signal_id = None
        signal_url = str(signal.get("url") or "").strip()
        if signal_url:
            existing = client.table("raw_signals").select("id").eq("url", signal_url).limit(1).execute()
            if existing.data:
                raw_signal_id = existing.data[0]["id"]
        if raw_signal_id is None:
            raw = client.table("raw_signals").insert(raw_payload).execute()
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
        post_decision = (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
        post_action = post_decision.get("action") or result.get("post_format", "SHORT POST")
        queue = result.get("content_queue") or {}
        linkedin_block = result.get("linkedin_block") or {}

        schedule_payload = {
            "run_date": result.get("date_pkt"),
            "run_date_pkt": result.get("date_pkt"),
            "session_label": result.get("scan_session"),
            "morning_format": post_action,
            "morning_signal": post_decision.get("title") or signal.get("title", ""),
            "morning_draft": result.get("x_post", ""),
            "midday_signal": queue.get("later_signal")
            or (result.get("operator_decisions") or {})
            .get("one_signal_everyone_missing", {})
            .get("title", ""),
            "midday_draft": queue.get("later_draft") or result.get("what_most_missed", ""),
            "evening_format": "journalist_comment",
            "evening_target": journalist.get("target_post_url") or f"@{journalist.get('handle', '')}",
            "evening_draft": journalist.get("comment_draft", ""),
            "linkedin_post_day": result.get("day_of_week", ""),
            "linkedin_type": linkedin_block.get("content_source")
            or ("flagship_analysis" if result.get("linkedin_today") else "not_today"),
            "linkedin_draft": linkedin_block.get("article_post") or result.get("linkedin_post", ""),
            "x_post": result.get("x_post", ""),
            "x_thread": json.dumps(result.get("x_thread")) if isinstance(result.get("x_thread"), list) else result.get("x_thread"),
            "what_most_people_missed": result.get("what_most_missed", ""),
            "journalist_comment": journalist.get("comment_draft", ""),
            "intelligence_output_id": output_id,
            "active_now_signal": queue.get("active_now_signal"),
            "active_now_format": queue.get("active_now_format"),
            "active_now_draft": queue.get("active_now_draft"),
            "active_now_deadline": queue.get("active_now_deadline"),
            "active_now_expires_at": queue.get("active_now_expires_at"),
            "active_now_reason": queue.get("active_now_reason"),
            "active_now_source_package": queue.get("active_now_source_package"),
            "later_signal": queue.get("later_signal"),
            "later_format": queue.get("later_format"),
            "later_draft": queue.get("later_draft"),
            "later_active_from": queue.get("later_active_from"),
            "later_expires_at": queue.get("later_expires_at"),
            "later_status": queue.get("later_status"),
            "later_replaced_by": queue.get("later_replaced_by"),
            "later_reason": queue.get("later_reason"),
            "queue_status": queue.get("queue_status"),
            "operator_action_summary": queue.get("operator_action_summary"),
        }
        client.table("content_schedule").insert(schedule_payload).execute()

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
                    "runtime_branch": (result.get("runtime") or {}).get("runtime_branch"),
                    "runtime_commit_sha": (result.get("runtime") or {}).get("runtime_commit_sha"),
                    "scan_runtime_started_at": (result.get("runtime") or {}).get("scan_runtime_started_at"),
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
