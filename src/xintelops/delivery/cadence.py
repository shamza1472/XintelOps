from __future__ import annotations

from typing import Any

from xintelops.delivery.crisis_tier import classify_scan_tier
from xintelops.delivery.linkedin_synthesis import build_linkedin_block
from xintelops.delivery.operator import enrich_operator_result
from xintelops.delivery.queue import resolve_queue
from xintelops.delivery.signal_display import format_top_signals_block


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
    block = result.get("operator_block") or {}
    x_block = block.get("x") or {}
    li_block = block.get("linkedin") or {}
    queue = block.get("queue") or {}
    journalist = result.get("journalist") or {}
    post_url = journalist.get("target_post_url") or journalist.get("post_url") or "see email"

    return {
        "x_primary": (
            f"{x_block.get('action', 'X POST')}: {x_block.get('post_now', 'top signal')} "
            f"— deadline {x_block.get('deadline', '30 min')}"
        ),
        "x_secondary": queue.get("reason") or "No tracked later-post.",
        "x_engagement": (
            f"Reply on journalist post: {post_url}"
            if not journalist.get("engagement_skipped")
            else "Skip journalist engagement — no relevant original post."
        ),
        "linkedin": (
            f"{li_block.get('status', 'Not scheduled today')}. "
            f"Next window: {li_block.get('next_window', '')}. "
            f"Action: {li_block.get('todays_action', '')}"
        ),
        "linkedin_today": str(li_block.get("status") == "Scheduled today").lower(),
        "next_linkedin_day": li_block.get("next_window", next_linkedin_day(str(result.get("day_of_week") or ""))),
    }


def enrich_result(
    result: dict[str, Any],
    *,
    active_events: list[dict[str, Any]] | None = None,
    rec_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fill operator, LinkedIn, and cadence fields so emails are never empty."""
    result = enrich_operator_result(result, active_events=active_events, rec_history=rec_history)
    day = str(result.get("day_of_week") or "")

    if "linkedin_today" not in result or result.get("linkedin_today") is None:
        linkedin_signals = [
            s for s in result.get("ranked_signals", []) if s.get("recommended_action") == "LINKEDIN"
        ]
        result["linkedin_today"] = bool(linkedin_signals) or is_linkedin_day(day)

    if not result.get("linkedin_post"):
        if result.get("linkedin_today"):
            lead = (result.get("ranked_signals") or [{}])[0]
            result["linkedin_post"] = (
                f"[DRAFT NEEDED]\n\n"
                f"Signal: {lead.get('title', '')}\n\n"
                f"{lead.get('why_hamza_should_care', '')[:600]}"
            ).strip()
        else:
            nxt = next_linkedin_day(day)
            result["linkedin_post"] = f"No LinkedIn post today ({day}). Next window: {nxt}."

    if not result.get("source_citations"):
        citations = []
        for sig in result.get("ranked_signals") or []:
            if sig.get("url"):
                citations.append(
                    {
                        "name": sig.get("source") or "Source",
                        "url": sig.get("url"),
                        "published_date": sig.get("event_date") or "Unknown",
                        "tier": f"T{sig.get('niche_tier', 2)}",
                        "why_supports": sig.get("why_hamza_should_care") or "",
                    }
                )
        if not citations:
            signal = result.get("top_signal") or {}
            if signal.get("url"):
                citations.append(
                    {
                        "name": signal.get("source") or "Primary source",
                        "url": signal.get("url"),
                        "published_date": signal.get("event_date") or "Unknown",
                        "tier": signal.get("tier") or "L1",
                        "why_supports": signal.get("summary") or "",
                    }
                )
        result["source_citations"] = citations[:5]

    if not result.get("internal_brief"):
        lines = ["Operator summary:"]
        for sig in result.get("ranked_signals") or []:
            scores = sig.get("scores") or {}
            lines.append(
                f"#{sig.get('rank')} {sig.get('title')} — "
                f"E{scores.get('edge')} P{scores.get('post_worthiness')} "
                f"F{scores.get('forecast_value')} → {sig.get('recommended_action')}"
            )
        result["internal_brief"] = "\n".join(lines)

    tier_meta = classify_scan_tier(result)
    result["crisis_tier_meta"] = tier_meta
    result["crisis_detected"] = tier_meta.get("crisis_detected", False)
    result["scan_tier"] = tier_meta.get("immediate_tier") or tier_meta.get("scan_tier", "ROUTINE")
    result["top_signals_display"] = format_top_signals_block(result)

    if not result.get("linkedin_block"):
        result["linkedin_block"] = build_linkedin_block(result, [])

    result = resolve_queue(result, None)

    if not result.get("posting_cadence"):
        result["posting_cadence"] = build_posting_cadence(result)

    result["_enriched"] = True
    return result
