from __future__ import annotations

from typing import Any

from xintelops.delivery.live_events import (
    build_active_live_event_block,
    classify_freshness,
    merge_active_events,
    should_persist_active_event,
    signal_to_active_event,
)
from xintelops.delivery.ranking import (
    apply_ranking_bias,
    infer_niche_tier,
    select_archive_signal,
    select_post_with_quota,
    select_strategic_lead,
)
from xintelops.delivery.strategic_lane import assign_cross_event_roles, build_why_xintelops_fits


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


def _normalize_signal(item: dict[str, Any], top: dict[str, Any], idx: int) -> dict[str, Any]:
    scores = item.get("scores") or {}
    region = str(item.get("region") or top.get("region") or "Global")
    domain = str(item.get("domain") or top.get("domain") or "")
    title = str(item.get("title") or f"Signal {idx}")
    signal = {
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
        "freshness_class": item.get("freshness_class") or "",
        "actors": item.get("actors"),
        "carried_forward": item.get("carried_forward", False),
        "event_id": item.get("event_id"),
        "normalized_event_key": item.get("normalized_event_key"),
        "new_information_detected": item.get("new_information_detected", False),
    }
    signal["freshness_class"] = classify_freshness(signal)
    return signal


def enrich_operator_result(
    result: dict[str, Any],
    *,
    active_events: list[dict[str, Any]] | None = None,
    rec_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize operator fields, merge active events, apply ranking, select immediate vs strategic."""
    top = dict(result.get("top_signal") or {})
    ranked = list(result.get("ranked_signals") or [])

    if not ranked and top.get("title"):
        ranked = [_signal_from_legacy(top, 1)]

    normalized = [_normalize_signal(item, top, idx) for idx, item in enumerate(ranked, 1)]

    carry_log: list[dict[str, Any]] = []
    if active_events:
        normalized, carry_log = merge_active_events(normalized, active_events)

    normalized = apply_ranking_bias(normalized, rec_history=rec_history)
    result["ranked_signals"] = normalized
    result["active_live_events"] = build_active_live_event_block(carry_log)

    decisions = dict(result.get("operator_decisions") or {})
    immediate, regional_check, momentum_check = select_post_with_quota(
        normalized, decisions.get("one_signal_to_post") or decisions.get("best_immediate_post")
    )
    strategic = select_strategic_lead(normalized, immediate)
    archive = select_archive_signal(normalized, immediate, strategic)

    post_action = _normalize_action(immediate.get("canonical_action") or immediate.get("recommended_action"))
    if post_action not in {"X POST", "X THREAD"}:
        if immediate.get("live_event_score", 0) >= 8 or immediate.get("crisis_flag"):
            post_action = "X THREAD" if immediate.get("live_event_score", 0) >= 9 else "X POST"
        else:
            post_action = "MONITOR"

    immediate["canonical_action"] = post_action

    lane_type = immediate.get("lane_relevance_type", "")
    why_lane = immediate.get("why_xintelops_fits") or build_why_xintelops_fits(immediate, lane_type)

    decisions["best_immediate_post"] = {
        "title": immediate.get("title", ""),
        "action": post_action,
        "why": immediate.get("why_hamza_should_care") or immediate.get("action_rationale", ""),
        "live_momentum": immediate.get("live_momentum", 0),
        "live_event_score": immediate.get("live_event_score", 0),
        "freshness_class": immediate.get("freshness_class", ""),
        "ranking_mode": immediate.get("ranking_mode", "normal"),
        "lane_relevance_type": lane_type,
        "why_xintelops_fits": why_lane,
        "strategic_lane_score": immediate.get("strategic_lane_score", 0),
        "final_score": immediate.get("final_score", immediate.get("rank_score", 0)),
        "why_it_ranked_here": immediate.get("why_it_ranked_here", ""),
        "guardrail_applied": immediate.get("guardrail_applied", ""),
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
    result["strategic_lane_check"] = regional_check
    result["live_momentum_check"] = momentum_check
    result["cross_event_roles"] = assign_cross_event_roles(normalized, immediate.get("title", ""))
    result["operator_mode"] = result.get("operator_mode") or "vNext-strategic-lane"

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

    # Queue events for persistence after finalize
    pending_events = []
    scan_session = str(result.get("scan_session") or "")
    for sig in normalized:
        score = int(sig.get("live_event_score") or 0)
        if should_persist_active_event(sig, score):
            pending_events.append(signal_to_active_event(sig, scan_session))
    result["_pending_active_events"] = pending_events
    result["_immediate_recommendation"] = {
        "title": immediate.get("title", ""),
        "action": post_action,
        "freshness_class": immediate.get("freshness_class", ""),
        "live_event_score": immediate.get("live_event_score", 0),
        "normalized_event_key": immediate.get("normalized_event_key"),
    }

    result["active_live_events"] = build_active_live_event_block(
        carry_log, selected_title=immediate.get("title", "")
    )
    return result
