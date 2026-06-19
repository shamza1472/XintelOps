from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from xintelops.agents.analyst import AnalystAgent
from xintelops.agents.red_team import RedTeamAgent
from xintelops.agents.strategist import StrategistAgent
from xintelops.agents.verifier import VerifierAgent
from xintelops.config import get_settings
from xintelops.db.supabase_client import SupabaseClient
from xintelops.delivery.resend_client import ResendClient
from xintelops.ingest.orchestrator import IngestOrchestrator
from xintelops.vector.deduplicator import Deduplicator

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ingest = IngestOrchestrator()
        self.dedup = Deduplicator()
        self.db = SupabaseClient(self.settings)
        self.verifier = VerifierAgent()
        self.analyst = AnalystAgent()
        self.red_team = RedTeamAgent()
        self.strategist = StrategistAgent()
        self.email = ResendClient(self.settings)

    def run(self, skip_ingest: bool = False, source_bundle: str | None = None) -> dict[str, Any]:
        if source_bundle is None:
            if skip_ingest:
                raise ValueError("source_bundle is required when skip_ingest=True")
            items = self.ingest.fetch_all()
            source_bundle = self.ingest.bundle_text(items)
            self._store_ingested_items(items)

        verifier_output = self.verifier.run(source_bundle)
        verified_signals = verifier_output.get("verified_signals") or []
        if not verified_signals:
            raise RuntimeError("No verified signals produced by verifier agent")

        top_signal = verified_signals[0]
        analyst_output = self.analyst.run(top_signal)
        analyst_output["top_signal"] = analyst_output.get("top_signal") or top_signal
        redteam_output = self.red_team.run(analyst_output)
        result = self.strategist.run(analyst_output, redteam_output, datetime.now(timezone.utc))

        result["signals_scanned"] = verifier_output.get("signals_scanned", len(verified_signals))
        result["signals_verified"] = verifier_output.get("signals_verified", len(verified_signals))
        result["signals_blocked"] = verifier_output.get("signals_blocked", 0)
        result["crisis_detected"] = verifier_output.get("crisis_detected", False)
        result["top_signal"] = analyst_output.get("top_signal", top_signal)

        synth_id = None
        legacy_ids = {"raw_signal_id": None, "output_id": None, "pipeline_log_id": None}
        if self.db.client:
            synth_id = self.db.insert_synthesized_intelligence(
                {
                    "feed_ids": [],
                    "core_anomaly": analyst_output.get("analysis_summary", ""),
                    "red_team_analysis": redteam_output.get("redteam_summary", ""),
                    "strategist_implication": result.get("internal_brief", ""),
                    "status": "pending_review",
                    "x_post": result.get("x_post", ""),
                    "internal_brief": result.get("internal_brief", ""),
                    "crisis_flag": result.get("crisis_detected", False),
                }
            )
            legacy_ids = self.db.dual_write_legacy(result)

        email_sent = self.email.send_scan_email(result)
        if self.db.client:
            self.db.mark_email_sent(legacy_ids.get("pipeline_log_id"), email_sent)

        return {
            "success": True,
            "session": result.get("scan_session"),
            "synthesized_id": synth_id,
            "output_id": legacy_ids.get("output_id"),
            "crisis": result.get("crisis_detected"),
            "signal": result.get("top_signal", {}).get("title"),
            "email_sent": email_sent,
        }

    def _store_ingested_items(self, items) -> None:
        if not self.db.client:
            logger.warning("Supabase not configured; skipping vector storage")
            return
        novel_count = 0
        for item in items:
            dedup_result, embedding = self.dedup.process(item)
            self.db.insert_raw_feed(
                source=item.source,
                raw_text=item.raw_text,
                title=item.title,
                url=item.url,
                source_type=item.source_type,
                embedding=embedding,
                is_duplicate=dedup_result.is_duplicate,
                similarity_score=dedup_result.similarity_score,
            )
            if not dedup_result.is_duplicate:
                novel_count += 1
        logger.info("Stored %s ingested items (%s novel)", len(items), novel_count)
