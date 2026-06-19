from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    anthropic_api_key: str
    resend_api_key: str
    recipient_email: str
    similarity_threshold: float
    rate_delay_ms: int
    fetch_timeout_sec: int
    max_chars_per_source: int
    journalist_batch_size: int
    sources_csv_path: Path
    journalists_csv_path: Path
    twitter_rss_base: str
    dual_write_legacy: bool
    artifacts_dir: Path
    scan_bundle_path: Path
    scan_result_path: Path
    scan_context_path: Path

    @property
    def uses_cursor_llm(self) -> bool:
        return self.llm_provider == "cursor"

    @property
    def uses_external_llm(self) -> bool:
        return self.llm_provider == "anthropic"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).lower()
    return value in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    artifacts = Path(os.getenv("ARTIFACTS_DIR", str(ARTIFACTS_DIR)))
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "cursor").lower(),
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        recipient_email=os.getenv("RECIPIENT_EMAIL", "hmz1472@gmail.com"),
        similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.85")),
        rate_delay_ms=int(os.getenv("RATE_DELAY_MS", "3000")),
        fetch_timeout_sec=int(os.getenv("FETCH_TIMEOUT_SEC", "12")),
        max_chars_per_source=int(os.getenv("MAX_CHARS_PER_SOURCE", "2000")),
        journalist_batch_size=int(os.getenv("JOURNALIST_BATCH_SIZE", "10")),
        sources_csv_path=REPO_ROOT / os.getenv("SOURCES_CSV_PATH", "data/xintel_sources.csv"),
        journalists_csv_path=REPO_ROOT / os.getenv("JOURNALISTS_CSV_PATH", "data/journalists.csv"),
        twitter_rss_base=os.getenv("TWITTER_RSS_BASE", "https://rsshub.app/twitter/user"),
        dual_write_legacy=_env_bool("DUAL_WRITE_LEGACY", True),
        artifacts_dir=artifacts,
        scan_bundle_path=artifacts / "scan_bundle.txt",
        scan_result_path=artifacts / "scan_result.json",
        scan_context_path=artifacts / "scan_context.json",
    )
