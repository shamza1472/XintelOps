#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xintelops.config import get_settings
from xintelops.delivery.cadence import enrich_result
from xintelops.pipeline.runner import PipelineRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize scan: save to Supabase and send email")
    parser.add_argument(
        "--result-file",
        type=Path,
        help="Path to scan_result.json (default: artifacts/scan_result.json)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    result_path = args.result_file or settings.scan_result_path
    if not result_path.exists():
        logging.error("Missing result file: %s", result_path)
        return 1

    result = enrich_result(json.loads(result_path.read_text(encoding="utf-8")))
    runner = PipelineRunner(settings)
    outcome = runner.finalize(result)
    logging.info("Finalize complete: %s", outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
