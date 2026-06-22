from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from xintelops.delivery.live_events import parse_pkt_scan_time
from xintelops.delivery.ranking import infer_niche_tier

PKT = timezone(timedelta(hours=5))

LINKEDIN_DAYS = {"Monday", "Wednesday", "Friday"}
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LINKEDIN_WINDOW_START = time(9, 0)
LINKEDIN_WINDOW_END = time(11, 0)


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


def linkedin_window_state(result: dict[str, Any]) -> str:
    """Return: before_window | in_window | after_window | not_scheduled."""
    day = str(result.get("day_of_week") or "")
    if not is_linkedin_day(day):
        return "not_scheduled"
    scan_time = parse_pkt_scan_time(result)
    t = scan_time.time()
    if t < LINKEDIN_WINDOW_START:
        return "before_window"
    if LINKEDIN_WINDOW_START <= t <= LINKEDIN_WINDOW_END:
        return "in_window"
    return "after_window"


def format_pkt_now(result: dict[str, Any]) -> str:
    return parse_pkt_scan_time(result).strftime("%Y-%m-%d %H:%M PKT")


SYNTHESIS_TOPICS = [
    "Maritime chokepoints and insurance premiums as the real escalation signal.",
    "Defense-industrial procurement patterns across priority theaters.",
    "Dual-use technology and supply-chain risk beyond consumer headlines.",
    "Energy routing, sanctions enforcement, and market repricing windows.",
    "Port, cable, and airspace disruptions as leading indicators.",
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


def _top_live_signal(result: dict[str, Any]) -> dict[str, Any] | None:
    for sig in result.get("ranked_signals") or []:
        if sig.get("live_event_score", 0) >= 8 and sig.get("freshness_class") in {"BREAKING", "LIVE", "DEVELOPING"}:
            return sig
    for sig in result.get("ranked_signals") or []:
        if sig.get("live_event_score", 0) >= 9:
            return sig
    return None


def pick_linkedin_topic(result: dict[str, Any], db_outputs: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, str]:
    """Hierarchy: active crisis/live > synthesis > strategic lead > archive."""
    live = _top_live_signal(result)
    if live:
        return live, "Active high-momentum live event"

    for sig in result.get("ranked_signals") or []:
        if sig.get("recommended_action") == "LINKEDIN":
            return sig, "Fresh verified LinkedIn candidate"

    strategic = (result.get("operator_decisions") or {}).get("best_strategic_lead") or {}
    if strategic.get("title"):
        for sig in result.get("ranked_signals") or []:
            if sig.get("title") == strategic.get("title"):
                return sig, "Best strategic lead from active queue"

    outputs = db_outputs or []
    if outputs:
        ranked = sorted(outputs, key=_score_output, reverse=True)
        row = ranked[0]
        pseudo = {
            "title": str(row.get("internal_brief") or row.get("source_name") or "Synthesis")[:120],
            "why_hamza_should_care": str(row.get("internal_brief") or row.get("what_most_people_missed") or "")[:600],
            "region": row.get("region"),
            "source": row.get("source_name"),
            "niche_tier": _region_tier(str(row.get("region") or "")),
        }
        return pseudo, "Database synthesis (24–72h)"

    archive = (result.get("operator_decisions") or {}).get("best_archive_signal") or {}
    if archive.get("title"):
        for sig in result.get("ranked_signals") or []:
            if sig.get("title") == archive.get("title"):
                return sig, "Evergreen archive — no live material"

    return None, "none"


def synthesize_linkedin_from_db(outputs: list[dict[str, Any]], horizon: str) -> tuple[str, str]:
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
    return "\n".join(lines), f"Database synthesis ({horizon})"


def _build_source_package_for_signal(result: dict[str, Any], sig: dict[str, Any]) -> list[dict[str, Any]]:
    package = []
    if sig.get("url"):
        package.append(
            {
                "name": sig.get("source") or "Source",
                "url": sig.get("url"),
                "published_date": sig.get("event_date") or "Unknown",
                "tier": f"T{sig.get('niche_tier', 2)}",
                "why_supports": sig.get("why_hamza_should_care") or "",
            }
        )
    for item in result.get("source_citations") or []:
        if item.get("url"):
            package.append(item)
    return package[:5]


def build_linkedin_block(
    result: dict[str, Any],
    db_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    day = str(result.get("day_of_week") or "")
    next_li = next_linkedin_day(day)
    next_window = f"{next_li} 09:00–11:00 PKT"
    current_time = format_pkt_now(result)
    window = linkedin_window_state(result)
    crisis = bool(result.get("crisis_detected"))
    top_live = _top_live_signal(result)
    live_score = int(top_live.get("live_event_score", 0)) if top_live else 0
    crisis_exception = crisis or live_score >= 9

    base = {
        "window": "09:00–11:00 PKT",
        "current_time": current_time,
        "next_window": next_window,
        "format": "LinkedIn analysis",
        "source_package": [],
        "why_this_topic": "",
        "topic": "",
        "copy_this": "",
        "draft_ready": False,
    }

    if window == "not_scheduled" and not crisis_exception:
        return {
            **base,
            "status": "Not scheduled today",
            "action": "No LinkedIn post required.",
            "content_source": "N/A",
            "article_post": "",
            "todays_action": f"No LinkedIn post today ({day}). Next window: {next_window}.",
        }

    topic_sig, topic_reason = pick_linkedin_topic(result, db_outputs)
    article = str(result.get("linkedin_post") or "").strip()
    if topic_sig and not article.startswith("[DRAFT"):
        article = article or _draft_from_signal(topic_sig)
    elif topic_sig and (not article or article.startswith("[DRAFT")):
        article = _draft_from_signal(topic_sig)
    elif not article or article.startswith("[DRAFT"):
        article, source = synthesize_linkedin_from_db(db_outputs or [], "24–72 hours")
        if not article and db_outputs:
            article, source = synthesize_linkedin_from_db(db_outputs, "30 days")
        topic_reason = source if article else topic_reason

    if topic_sig:
        base["topic"] = topic_sig.get("title", "")
        base["why_this_topic"] = topic_reason
        base["source_package"] = _build_source_package_for_signal(result, topic_sig)

    if article:
        result["linkedin_post"] = article
        base["copy_this"] = article
        base["draft_ready"] = True

    if window == "before_window":
        return {
            **base,
            "status": "Scheduled today",
            "action": "Hold until window",
            "content_source": topic_reason,
            "article_post": article,
            "todays_action": "Draft ready — hold until 09:00 PKT.",
        }

    if window == "in_window":
        return {
            **base,
            "status": "Post now",
            "action": "Post now",
            "content_source": topic_reason,
            "article_post": article,
            "todays_action": "COPY THIS — post during 09:00–11:00 PKT window.",
        }

    # after_window
    if crisis_exception:
        return {
            **base,
            "status": "Crisis exception",
            "action": "Post now despite missed window",
            "content_source": topic_reason,
            "article_post": article,
            "todays_action": f"Crisis/live_event_score {live_score} — post now even though window passed.",
            "exception_reason": "Active crisis or live_event_score >= 9.",
        }

    return {
        **base,
        "status": "Window passed",
        "action": "Roll to next LinkedIn window",
        "content_source": topic_reason,
        "article_post": "",
        "copy_this": "",
        "draft_ready": bool(article),
        "suggested_next_topic": base.get("topic") or "Use next scan's strategic lead.",
        "todays_action": f"Missed window. Next normal window: {next_window}.",
    }


def _draft_from_signal(sig: dict[str, Any]) -> str:
    title = sig.get("title") or "Signal"
    why = sig.get("why_hamza_should_care") or sig.get("action_rationale") or ""
    region = sig.get("region") or "Global"
    return (
        f"{title}\n\n"
        f"{why}\n\n"
        f"Why this matters for operators tracking {region}: "
        f"the second-order effects on logistics, energy, and defense-industrial posture "
        f"often move before the headline cycle catches up."
    ).strip()
