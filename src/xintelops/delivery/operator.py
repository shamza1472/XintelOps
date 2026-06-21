from __future__ import annotations

from typing import Any

from xintelops.delivery.ranking import (
    apply_ranking_bias,
    infer_niche_tier,
    select_archive_signal,
    select_post_with_quota,
    select_strategic_lead,
)


def _clamp_score(value: Any, default: int = 5) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, score))


def _normalize_action(action: Any) -> str:
    text = str(action or "MONITOR").upper().strip()
    valid = {
        "IGNORE", "ARCHIVE", "MONITOR", "X POST", "X THREAD", "LINKEDIN",
        "NEWSLETTER CANDIDATE", "HIGH PRIORITY TRACKING",
    }
    if text in valid:
        return text
    if text in {"XPOST", "X-POST", "SHORT POST", "POST"}:
        return "X POST"
    if text in {"XTHREAD", "X-THREAD", "THREAD"}:
        return "X THREAD"
    return "MONITOR"


def _action_tag_class(action: str) -> str:
    if action in {"X POST", "X THREAD"}:
        return "tag-action-post"
    if action == "LINKEDIN":
        return "tag-action-linkedin"
    if action in {"HIGH PRIORITY TRACKING", "NEWSLETTER CANDIDATE"}:
        return "tag-action-track"
    if action == "MONITOR":
        return "tag-action-monitor"
    return "tag-action-ignore"


def _signal_from_legacy(top: dict[str, Any], rank: int = 1) -> dict[str, Any]:
    region = str(top.get("region") or "Global")
    action = "X THREAD" if str(top.get("post_format") or "").upper() == "THREAD" else "X POST"
    return {
        "rank": rank,
        "title": top.get("title") or "Untitled signal",
        "source": top.get("source") or "Unknown",
        "url": top.get("url") or "",
        "region": region,
        "domain": top.get("domain") or "",
        "niche_tier": infer_niche_tier(region, str(top.get("domain") or ""), str(top.get("title") or "")),
        "event_date": top.get("event_date") or "",
        "why_hamza_should_care": top.get("summary") or "",
        "scores": {
            "edge": 6,
            "post_worthiness": 7,
            "forecast_value": 6,
            "niche_relevance": 7 if infer_niche_tier(region) <= 2 else 4,
            "live_momentum": 5,
        },
        "recommended_action": action,
        "action_rationale": "Legacy scan format — regenerate for full operator scoring.",
        "confidence": str(top.get("confidence") or "MEDIUM").upper(),
        "crisis_flag": bool(top.get("crisis_flag", False)),
    }


def enrich_operator_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize operator fields, apply ranking with live momentum, select immediate vs strategic."""
    top = dict(result.get("top_signal") or {})
    ranked = list(result.get("ranked_signals") or [])

    if not ranked and top.get("title"):
        ranked = [_signal_from_legacy(top, 1)]

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(ranked, 1):
        scores = item.get("scores") or {}
        region = str(item.get("region") or top.get("region") or "Global")
        domain = str(item.get("domain") or top.get("domain") or "")
        title = str(item.get("title") or f"Signal {idx}")
        normalized.append(
            {
                "rank": item.get("rank") or idx,
                "title": title,
                "source": item.get("source") or "",
                "url": item.get("url") or "",
                "region": region,
                "domain": domain,
                "niche_tier": item.get("niche_tier") or infer_niche_tier(region, domain, title),
                "event_date": item.get("event_date") or "",
                "why_hamza_should_care": item.get("why_hamza_should_care") or item.get("summary") or "",
                "scores": {
                    "edge": _clamp_score(scores.get("edge")),
                    "post_worthiness": _clamp_score(scores.get("post_worthiness")),
                    "forecast_value": _clamp_score(scores.get("forecast_value")),
                    "niche_relevance": _clamp_score(scores.get("niche_relevance")),
                    "live_momentum": _clamp_score(scores.get("live_momentum"), 5),
                },
                "recommended_action": _normalize_action(item.get("recommended_action")),
                "action_rationale": item.get("action_rationale") or "",
                "confidence": str(item.get("confidence") or "MEDIUM").upper(),
                "crisis_flag": bool(item.get("crisis_flag", False)),
                "second_order_relevance": item.get("second_order_relevance"),
                "regional_override_reason": item.get("regional_override_reason") or "",
            }
        )

    normalized = apply_ranking_bias(normalized)
    result["ranked_signals"] = normalized

    decisions = dict(result.get("operator_decisions") or {})
    immediate, regional_check, momentum_check = select_post_with_quota(
        normalized, decisions.get("one_signal_to_post") or decisions.get("best_immediate_post")
    )
    strategic = select_strategic_lead(normalized, immediate)
    archive = select_archive_signal(normalized, immediate, strategic)

    post_action = immediate.get("recommended_action", "X POST")
    if post_action not in {"X POST", "X THREAD"}:
        post_action = "X POST"

    decisions["best_immediate_post"] = {
        "title": immediate.get("title", ""),
        "action": post_action,
        "why": immediate.get("why_hamza_should_care") or immediate.get("action_rationale", ""),
        "live_momentum": immediate.get("live_momentum", 0),
        "ranking_mode": immediate.get("ranking_mode", "normal"),
    }
    decisions["best_strategic_lead"] = {
        "title": strategic.get("title", ""),
        "why": strategic.get("why_hamza_should_care") or strategic.get("action_rationale", ""),
        "horizon": "7-30 days",
    }
    decisions["best_archive_signal"] = {
        "title": archive.get("title", ""),
        "why": archive.get("why_hamza_should_care") or archive.get("action_rationale", "") or "Useful context, not post-worthy now.",
    }
    decisions["one_signal_to_post"] = {
        "title": immediate.get("title", ""),
        "action": post_action,
        "why": decisions["best_immediate_post"]["why"],
        "regional_override_reason": regional_check.get("reason") if regional_check.get("status") == "Overridden" else "",
    }
    decisions["one_signal_to_watch"] = decisions.get("one_signal_to_watch") or {
        "title": strategic.get("title", ""),
        "horizon_days": "7-30",
        "why": decisions["best_strategic_lead"]["why"],
    }
    decisions["one_signal_everyone_missing"] = decisions.get("one_signal_everyone_missing") or {
        "title": strategic.get("title", ""),
        "edge_score": strategic.get("scores", {}).get("edge", 0),
        "why": strategic.get("why_hamza_should_care", ""),
    }

    result["operator_decisions"] = decisions
    result["regional_priority_check"] = regional_check
    result["live_momentum_check"] = momentum_check
    result["operator_mode"] = result.get("operator_mode") or "vNext"

    if post_action == "X THREAD":
        result["post_format"] = "THREAD"
    elif post_action == "X POST":
        result["post_format"] = result.get("post_format") or "SHORT POST"

    if normalized:
        lead = immediate or normalized[0]
        result["top_signal"] = {
            "title": lead["title"],
            "source": lead["source"],
            "tier": "L1",
            "url": lead["url"],
            "summary": lead["why_hamza_should_care"],
            "region": lead["region"],
            "domain": lead.get("domain", ""),
            "confidence": lead["confidence"],
            "crisis_flag": lead["crisis_flag"],
            "event_date": lead["event_date"],
            "verified_facts": top.get("verified_facts") or [],
        }

    result["crisis_detected"] = result.get("crisis_detected") or any(
        s.get("crisis_flag") for s in normalized
    )
    return result
