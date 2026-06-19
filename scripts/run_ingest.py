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
from xintelops.ingest.journalist_fetcher import get_journalist_for_today, load_journalists
from xintelops.pipeline.runner import PipelineRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest sources and write scan bundle for Cursor agent")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    runner = PipelineRunner(settings)
    items, bundle = runner.ingest_and_store()

    journalists = load_journalists(settings.journalists_csv_path)
    journalist = get_journalist_for_today(journalists, datetime.now(timezone.utc))
    context = {
        "items_ingested": len(items),
        "bundle_path": str(settings.scan_bundle_path),
        "journalist": {
            "name": journalist.name,
            "handle": journalist.handle,
            "outlet": journalist.outlet,
            "category": journalist.category,
            "focus": journalist.focus,
            "profile_url": journalist.profile_url,
        },
        "llm_provider": settings.llm_provider,
        "next_step": "Read artifacts/scan_bundle.txt and prompts/cursor_scan.md, produce JSON at artifacts/scan_result.json",
    }
    settings.scan_context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")

    logging.info("Ingested %s items → %s", len(items), settings.scan_bundle_path)
    logging.info("Context → %s", settings.scan_context_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
