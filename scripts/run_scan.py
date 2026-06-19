#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xintelops.config import get_settings
from xintelops.db.supabase_client import SupabaseClient
from xintelops.pipeline.runner import PipelineRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the XIntelOps intelligence scan pipeline")
    parser.add_argument("--seed", action="store_true", help="Seed trusted_sources and journalists tables")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip live ingestion (requires --bundle-file)")
    parser.add_argument("--bundle-file", type=Path, help="Use a pre-fetched source bundle text file")
    parser.add_argument("--ingest-only", action="store_true", help="Run ingestion + vector storage only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    db = SupabaseClient(settings)

    if args.seed:
        if not db.client:
            logging.error("Supabase credentials required for seeding")
            return 1
        sources_count = db.seed_trusted_sources(settings.sources_csv_path)
        journalists_count = db.seed_journalists(settings.journalists_csv_path)
        logging.info("Seeded %s trusted sources and %s journalists", sources_count, journalists_count)
        return 0

    runner = PipelineRunner()
    bundle = args.bundle_file.read_text(encoding="utf-8") if args.bundle_file else None

    if args.ingest_only:
        items = runner.ingest.fetch_all()
        runner._store_ingested_items(items)
        logging.info("Ingestion complete: %s items", len(items))
        return 0

    result = runner.run(skip_ingest=args.skip_ingest, source_bundle=bundle)
    logging.info("Scan complete: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
