from __future__ import annotations

from typing import Any

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

TIER1_REGIONS = frozenset(
    {
        "china",
        "pakistan",
        "india",
        "gulf",
        "iran",
        "levant",
        "red sea",
        "horn of africa",
        "middle east",
        "saudi",
        "uae",
        "yemen",
        "israel",
        "palestine",
        "syria",
        "iraq",
    }
)

TIER2_REGIONS = frozenset(
    {
        "central asia",
        "caucasus",
        "east africa",
        "asean",
        "southeast asia",
        "myanmar",
        "kazakhstan",
        "uzbekistan",
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


def _infer_niche_tier(region: str, domain: str = "") -> int:
    blob = f"{region} {domain}".lower()
    if any(token in blob for token in TIER1_REGIONS):
        return 1
    if any(token in blob for token in TIER2_REGIONS):
        return 2
    return 3


def _signal_from_legacy(top: dict[str, Any], rank: int = 1) -> dict[str, Any]:
    region = str(top.get("region") or "Global")
    action = "X THREAD" if str(top.get("post_format") or "").upper() == "THREAD" else "X POST"
    return {
        "rank": rank,
        "title": top.get("title") or "Untitled signal",
        "source": top.get("source") or "Unknown",
        "url": top.get("url") or "",
        "region": region,
        "niche_tier": _infer_niche_tier(region, str(top.get("domain") or "")),
        "event_date": top.get("event_date") or "",
        "why_hamza_should_care": top.get("summary") or "",
        "scores": {
            "edge": 6,
            "post_worthiness": 7,
            "forecast_value": 6,
            "niche_relevance": 7 if _infer_niche_tier(region) <= 2 else 4,
        },
        "recommended_action": action,
        "action_rationale": "Legacy scan format — regenerate for full operator scoring.",
        "confidence": str(top.get("confidence") or "MEDIUM").upper(),
        "crisis_flag": bool(top.get("crisis_flag", False)),
    }


def enrich_operator_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize vNext operator fields and backfill legacy scans."""
    top = dict(result.get("top_signal") or {})
    ranked = list(result.get("ranked_signals") or [])

    if not ranked and top.get("title"):
        ranked = [_signal_from_legacy(top, 1)]

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(ranked, 1):
        scores = item.get("scores") or {}
        region = str(item.get("region") or top.get("region") or "Global")
        normalized.append(
            {
                "rank": item.get("rank") or idx,
                "title": item.get("title") or f"Signal {idx}",
                "source": item.get("source") or "",
                "url": item.get("url") or "",
                "region": region,
                "niche_tier": item.get("niche_tier") or _infer_niche_tier(region, str(item.get("domain") or "")),
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
            }
        )

    normalized.sort(key=lambda s: s.get("rank") or 99)
    result["ranked_signals"] = normalized

    if not top.get("title") and normalized:
        lead = normalized[0]
        result["top_signal"] = {
            "title": lead["title"],
            "source": lead["source"],
            "tier": "L1",
            "url": lead["url"],
            "summary": lead["why_hamza_should_care"],
            "region": lead["region"],
            "domain": "",
            "confidence": lead["confidence"],
            "crisis_flag": lead["crisis_flag"],
            "event_date": lead["event_date"],
            "verified_facts": top.get("verified_facts") or [],
        }
        top = result["top_signal"]

    decisions = dict(result.get("operator_decisions") or {})
    post_candidates = [s for s in normalized if s["recommended_action"] in {"X POST", "X THREAD"}]
    watch_candidates = sorted(
        normalized,
        key=lambda s: s["scores"]["forecast_value"],
        reverse=True,
    )
    edge_candidates = sorted(
        normalized,
        key=lambda s: s["scores"]["edge"],
        reverse=True,
    )

    if not decisions.get("one_signal_to_post"):
        pick = post_candidates[0] if post_candidates else (normalized[0] if normalized else {})
        decisions["one_signal_to_post"] = {
            "title": pick.get("title", ""),
            "action": pick.get("recommended_action", "X POST"),
            "why": pick.get("why_hamza_should_care") or pick.get("action_rationale", ""),
        }

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
    result["operator_mode"] = result.get("operator_mode") or "vNext"

    post_action = str(decisions.get("one_signal_to_post", {}).get("action") or "")
    if post_action == "X THREAD":
        result["post_format"] = "THREAD"
    elif post_action == "X POST":
        result["post_format"] = result.get("post_format") or "SHORT POST"

    result["crisis_detected"] = result.get("crisis_detected") or any(
        s.get("crisis_flag") for s in normalized
    )
    return result
