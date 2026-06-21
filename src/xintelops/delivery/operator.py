from __future__ import annotations

from typing import Any

from xintelops.delivery.ranking import (
    apply_ranking_bias,
    infer_niche_tier,
    select_post_with_quota,
)

VALID_ACTIONS = frozenset(
    {
        "IGNORE",
        "ARCHIVE",
        "MONITOR",
        "X POST",
        "X THREAD",
        "LINKEDIN",
        "NEWSLETTER CANDIDATE",
        "HIGH PRIORITY TRACKING",
    }
)


def _clamp_score(value: Any, default: int = 5) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, score))


def _normalize_action(action: Any) -> str:
    text = str(action or "MONITOR").upper().strip()
    if text in VALID_ACTIONS:
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
        },
        "recommended_action": action,
        "action_rationale": "Legacy scan format — regenerate for full operator scoring.",
        "confidence": str(top.get("confidence") or "MEDIUM").upper(),
        "crisis_flag": bool(top.get("crisis_flag", False)),
    }


def enrich_operator_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize operator fields, apply niche ranking bias, enforce regional post quota."""
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
                "niche_tier": item.get("niche_tier")
                or infer_niche_tier(region, domain, title),
                "event_date": item.get("event_date") or "",
                "why_hamza_should_care": item.get("why_hamza_should_care") or item.get("summary") or "",
                "scores": {
                    "edge": _clamp_score(scores.get("edge")),
                    "post_worthiness": _clamp_score(scores.get("post_worthiness")),
                    "forecast_value": _clamp_score(scores.get("forecast_value")),
                    "niche_relevance": _clamp_score(scores.get("niche_relevance")),
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
    selected, priority_check = select_post_with_quota(normalized, decisions.get("one_signal_to_post"))

    post_action = selected.get("recommended_action", "X POST")
    if post_action not in {"X POST", "X THREAD"}:
        post_action = "X POST" if post_action not in {"LINKEDIN"} else post_action

    decisions["one_signal_to_post"] = {
        "title": selected.get("title", ""),
        "action": post_action if post_action in {"X POST", "X THREAD"} else "X POST",
        "why": selected.get("why_hamza_should_care") or selected.get("action_rationale", ""),
        "regional_override_reason": priority_check.get("reason") if priority_check.get("status") == "Overridden" else "",
    }

    watch_candidates = sorted(normalized, key=lambda s: s.get("scores", {}).get("forecast_value", 0), reverse=True)
    edge_candidates = sorted(
        [s for s in normalized if s.get("niche_tier", 3) <= 2] or normalized,
        key=lambda s: s.get("scores", {}).get("edge", 0),
        reverse=True,
    )

    if not decisions.get("one_signal_to_watch"):
        pick = watch_candidates[0] if watch_candidates else {}
        decisions["one_signal_to_watch"] = {
            "title": pick.get("title", ""),
            "horizon_days": "7-30",
            "why": pick.get("action_rationale") or pick.get("why_hamza_should_care", ""),
        }

    if not decisions.get("one_signal_everyone_missing"):
        pick = edge_candidates[0] if edge_candidates else {}
        decisions["one_signal_everyone_missing"] = {
            "title": pick.get("title", ""),
            "edge_score": pick.get("scores", {}).get("edge", 0),
            "why": pick.get("why_hamza_should_care", ""),
        }

    result["operator_decisions"] = decisions
    result["regional_priority_check"] = priority_check
    result["operator_mode"] = result.get("operator_mode") or "vNext"

    if decisions.get("one_signal_to_post", {}).get("action") == "X THREAD":
        result["post_format"] = "THREAD"
    elif decisions.get("one_signal_to_post", {}).get("action") == "X POST":
        result["post_format"] = result.get("post_format") or "SHORT POST"

    if normalized:
        lead = normalized[0]
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
