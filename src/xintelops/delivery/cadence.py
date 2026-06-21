from __future__ import annotations

from typing import Any

from xintelops.delivery.operator import enrich_operator_result


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

    post_decision = (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    post_action = str(post_decision.get("action") or result.get("post_format") or "X POST").upper()
    x_label = "🧵 THREAD" if post_action in {"X THREAD", "THREAD"} else "📱 SINGLE TWEET"

    journalist = result.get("journalist") or {}
    post_url = journalist.get("target_post_url") or journalist.get("post_url") or "see email"

    watch = (result.get("operator_decisions") or {}).get("one_signal_to_watch") or {}
    watch_title = watch.get("title") or "top forecast signal"

    return {
        "x_primary": f"{post_action}: {post_decision.get('title', 'top signal')} — post within 30 min ({x_label}).",
        "x_secondary": "4–6 hrs later: post the 'Everyone Is Missing' angle or secondary ranked signal.",
        "x_engagement": (
            f"Reply on journalist post: {post_url}"
            if not journalist.get("engagement_skipped")
            else "Skip journalist engagement — no relevant original post."
        ),
        "linkedin": (
            f"Post today 09:00–11:00 PKT — check ranked signals with LINKEDIN action."
            if linkedin_today
            else f"No LinkedIn window today. Next: {next_li}. Monitor: {watch_title}."
        ),
        "linkedin_today": str(linkedin_today).lower(),
        "next_linkedin_day": next_li,
    }


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    """Fill operator, LinkedIn, and cadence fields so emails are never empty."""
    result = enrich_operator_result(result)
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

    if not result.get("posting_cadence"):
        result["posting_cadence"] = build_posting_cadence(result)

    if not result.get("source_citations"):
        citations = []
        for sig in result.get("ranked_signals") or []:
            if sig.get("url"):
                citations.append(
                    {
                        "name": sig.get("source") or "Source",
                        "url": sig.get("url"),
                        "published_date": sig.get("event_date") or "Unknown",
                        "tier": "L1",
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

    return result
