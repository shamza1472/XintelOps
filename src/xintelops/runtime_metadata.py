from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from typing import Any


def _git(args: str) -> str:
    try:
        result = subprocess.run(
            ["git"] + args.split(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def get_runtime_metadata() -> dict[str, Any]:
    """Capture branch/commit for pipeline_log and email footer."""
    started_at = datetime.now(timezone.utc).isoformat()

    branch = (
        os.getenv("GITHUB_REF_NAME")
        or os.getenv("CURSOR_GIT_BRANCH")
        or _git("branch --show-current")
        or "unknown"
    )
    if branch.startswith("refs/heads/"):
        branch = branch.removeprefix("refs/heads/")

    sha = (
        os.getenv("GITHUB_SHA")
        or os.getenv("CURSOR_GIT_COMMIT")
        or _git("rev-parse HEAD")
        or "unknown"
    )
    short_sha = sha[:7] if len(sha) > 7 else sha

    return {
        "runtime_branch": branch,
        "runtime_commit_sha": sha,
        "runtime_commit_short": short_sha,
        "scan_runtime_started_at": started_at,
        "runtime_label": f"{branch} @ {short_sha}",
    }


def attach_runtime_metadata(result: dict[str, Any]) -> dict[str, Any]:
    meta = get_runtime_metadata()
    result["runtime"] = meta
    return result
