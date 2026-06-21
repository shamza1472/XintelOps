from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from xintelops.delivery.ranking import infer_niche_tier

PKT = timezone(timedelta(hours=5))

LINKEDIN_DAYS = {"Monday", "Wednesday", "Friday"}
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def is_linkedin_day(day_name: str) -> bool:
    return day_name in LINKEDIN_DAYS


def next_linkedin_day(day_name: str) -> str:
    if day_name not in DAY_ORDER:
        return "Monday"
    idx = DAY_ORDER.index(day_name)
    for offset in range(1, 8):
        candidate = DAY_ORDER[(idx + offset) % 7]
        if candidate in LINKEDIN_DAYS:
            return candidate
    return "Monday"

SYNTHESIS_TOPICS = [
    "China's ISR and logistics posture across the First Island Chain.",
    "The Gulf–Red Sea–Horn of Africa corridor as the real strategic map.",
    "Pakistan, India, and China: procurement signals that matter more than diplomatic noise.",
    "Crimea logistics pressure as a leading indicator for Russian operational tempo.",
    "Why agricultural drones are a harder supply-chain risk than consumer apps.",
]


def _region_tier(region: str, domain: str = "") -> int:
    return infer_niche_tier(region, domain)


def _score_output(row: dict[str, Any]) -> int:
    tier = _region_tier(str(row.get("region") or ""), str(row.get("domain") or ""))
    confidence = str(row.get("confidence") or "").lower()
    conf_bonus = 3 if confidence == "high" else 1 if confidence == "medium" else 0
    crisis_bonus = 2 if row.get("crisis_flag") else 0
    tier_bonus = {1: 10, 2: 6, 3: 1}.get(tier, 0)
    return tier_bonus + conf_bonus + crisis_bonus


def pick_fresh_linkedin_signal(result: dict[str, Any]) -> dict[str, Any] | None:
    for sig in result.get("ranked_signals") or []:
        if sig.get("recommended_action") == "LINKEDIN":
            return sig
    for sig in result.get("ranked_signals") or []:
        if sig.get("niche_tier") == 1 and sig.get("recommended_action") in {"X POST", "X THREAD", "LINKEDIN"}:
            return sig
    for sig in result.get("ranked_signals") or []:
        if sig.get("niche_tier") == 2:
            return sig
    return None


def synthesize_linkedin_from_db(outputs: list[dict[str, Any]], horizon: str) -> tuple[str, str]:
    """Build LinkedIn article from prior intelligence_outputs when no fresh signal exists."""
    if not outputs:
        return "", "none"

    ranked = sorted(outputs, key=_score_output, reverse=True)
    top_regions: dict[str, list[dict[str, Any]]] = {}
    for row in ranked[:12]:
        region = str(row.get("region") or "Global")
        top_regions.setdefault(region, []).append(row)

    primary_region = max(top_regions, key=lambda r: len(top_regions[r]))
    cluster = top_regions[primary_region][:3]
    topic_idx = hash(primary_region) % len(SYNTHESIS_TOPICS)
    topic = SYNTHESIS_TOPICS[topic_idx]

    lines = [
        f"{topic}",
        "",
        f"Pattern synthesis from the last {horizon} of verified intelligence — not a recycled headline.",
        "",
        f"Regional focus: {primary_region}",
        "",
    ]
    for idx, row in enumerate(cluster, 1):
        brief = str(row.get("internal_brief") or row.get("what_most_people_missed") or "")[:280]
        lines.append(f"{idx}. {row.get('source_name', 'Source')} — {brief}")
        if row.get("implications_7d"):
            lines.append(f"   7d indicator: {str(row.get('implications_7d'))[:200]}")
        lines.append("")

    lines.extend(
        [
            "Operator takeaway:",
            "These signals converge on a structural shift, not a one-day headline.",
            "Watch for follow-on procurement, logistics, or force-posture indicators in the next scan window.",
        ]
    )
    source_label = f"Database synthesis ({horizon})"
    return "\n".join(lines), source_label


def build_linkedin_block(
    result: dict[str, Any],
    db_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    day = str(result.get("day_of_week") or "")
    next_li = next_linkedin_day(day)
    next_window = f"{next_li} 09:00–11:00 PKT"
    crisis = bool(result.get("crisis_detected"))

    if not is_linkedin_day(day) and not crisis:
        return {
            "status": "Not scheduled today",
            "next_window": next_window,
            "todays_action": "No LinkedIn post required.",
            "content_source": "N/A",
            "article_post": "",
        }

    fresh = pick_fresh_linkedin_signal(result)
    if fresh and result.get("linkedin_post") and not str(result.get("linkedin_post", "")).startswith("[DRAFT"):
        tier_label = f"Fresh verified Tier-{fresh.get('niche_tier', 1)} signal"
        return {
            "status": "Scheduled today",
            "next_window": next_window,
            "todays_action": "Post flagship analysis 09:00–11:00 PKT",
            "content_source": tier_label,
            "article_post": result.get("linkedin_post", ""),
        }

    outputs_7d = db_outputs or []
    article, source = synthesize_linkedin_from_db(outputs_7d, "3–7 days")
    if not article and outputs_7d:
        article, source = synthesize_linkedin_from_db(outputs_7d, "30 days")

    if article:
        result["linkedin_post"] = article
        result["linkedin_today"] = True
        return {
            "status": "Scheduled today",
            "next_window": next_window,
            "todays_action": "Post synthesis article 09:00–11:00 PKT",
            "content_source": source,
            "article_post": article,
        }

    return {
        "status": "Scheduled today — draft missing",
        "next_window": next_window,
        "todays_action": "Regenerate scan; no usable intelligence_outputs in database.",
        "content_source": "none",
        "article_post": result.get("linkedin_post") or "",
    }
