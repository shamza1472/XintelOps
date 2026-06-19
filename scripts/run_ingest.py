#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xintelops.config import get_settings
from xintelops.delivery.cadence import is_linkedin_day, next_linkedin_day
from xintelops.ingest.journalist_fetcher import fetch_journalist_candidates, load_journalists
from xintelops.agents.strategist import get_pkt_date_info
from xintelops.pipeline.runner import PipelineRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest sources and write scan bundle for Cursor agent")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    runner = PipelineRunner(settings)
    items, bundle = runner.ingest_and_store()

    journalists = load_journalists(settings.journalists_csv_path)
    utc_now = datetime.now(timezone.utc)
    candidates = fetch_journalist_candidates(journalists, settings, utc_now)
    pkt = get_pkt_date_info(utc_now)
    context = {
        "items_ingested": len(items),
        "bundle_path": str(settings.scan_bundle_path),
        "date_pkt": pkt["date_str"],
        "time_pkt": pkt["time_str"],
        "day_of_week": pkt["day_name"],
        "linkedin_today": is_linkedin_day(pkt["day_name"]),
        "next_linkedin_day": next_linkedin_day(pkt["day_name"]),
        "journalist_candidates": candidates,
        "journalist_selection_note": (
            "Pick ONE journalist from journalist_candidates who posted an original tweet "
            "relevant to today's top signal. Use their specific post URL — never profile-only links. "
            "Skip engagement if no candidate fits."
        ),
        "llm_provider": settings.llm_provider,
        "next_step": "Read artifacts/scan_bundle.txt and prompts/cursor_scan.md, produce JSON at artifacts/scan_result.json",
    }
    settings.scan_context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")

    logging.info("Ingested %s items → %s", len(items), settings.scan_bundle_path)
    logging.info("Context → %s", settings.scan_context_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
