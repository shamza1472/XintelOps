from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def is_linkedin_day(day_name: str) -> bool:
    return day_name in {"Monday", "Wednesday", "Friday"}


def next_linkedin_day(day_name: str) -> str:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    linkedin_days = {"Monday", "Wednesday", "Friday"}
    if day_name not in order:
        return "Monday"
    idx = order.index(day_name)
    for offset in range(1, 8):
        candidate = order[(idx + offset) % 7]
        if candidate in linkedin_days:
            return candidate
    return "Monday"


def build_posting_cadence(result: dict[str, Any]) -> dict[str, str]:
    day = str(result.get("day_of_week") or "")
    linkedin_today = bool(result.get("linkedin_today")) or is_linkedin_day(day)
    next_li = next_linkedin_day(day)

    x_format = str(result.get("post_format") or "SHORT POST")
    return {
        "x_primary": f"Post within 30 minutes of this email — {x_format} (top verified signal).",
        "x_secondary": "Post 4–6 hours later (or at the next scan): use the 'What Most People Missed' block.",
        "x_engagement": "Once daily: paste the journalist comment under their latest relevant post (do not spam).",
        "linkedin": (
            "Post today 09:00–11:00 PKT — flagship analysis (200–350 words)."
            if linkedin_today
            else f"No LinkedIn post today. Next window: {next_li} 09:00–11:00 PKT."
        ),
        "linkedin_today": str(linkedin_today).lower(),
        "next_linkedin_day": next_li,
    }


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    """Fill missing LinkedIn/cadence fields so emails are never empty."""
    day = str(result.get("day_of_week") or "")
    if "linkedin_today" not in result or result.get("linkedin_today") is None:
        result["linkedin_today"] = is_linkedin_day(day)
    if not result.get("linkedin_post"):
        if result.get("linkedin_today"):
            brief = str(result.get("internal_brief") or result.get("top_signal", {}).get("summary") or "")
            result["linkedin_post"] = (
                f"[DRAFT NEEDED — regenerate on next scan]\n\n"
                f"Signal: {result.get('top_signal', {}).get('title', '')}\n\n"
                f"{brief[:600]}"
            ).strip()
        else:
            nxt = next_linkedin_day(day)
            result["linkedin_post"] = (
                f"Not a LinkedIn posting day ({day}). "
                f"Next LinkedIn window: {nxt} — prepare flagship analysis from this scan's internal brief."
            )
    if not result.get("posting_cadence"):
        result["posting_cadence"] = build_posting_cadence(result)
    if not result.get("source_citations"):
        signal = result.get("top_signal") or {}
        citations = []
        if signal.get("url"):
            citations.append(
                {
                    "name": signal.get("source") or "Primary source",
                    "url": signal.get("url"),
                    "published_date": signal.get("event_date") or "Unknown",
                    "tier": signal.get("tier") or "L1",
                }
            )
        for fact in signal.get("verified_facts") or []:
            if isinstance(fact, dict) and fact.get("url"):
                citations.append(fact)
        result["source_citations"] = citations
    return result
