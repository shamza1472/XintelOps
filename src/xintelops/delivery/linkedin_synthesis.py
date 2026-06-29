from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from xintelops.delivery.crisis_tier import POSTING_TIERS, classify_scan_tier
from xintelops.delivery.public_copy_gate import (
    build_safe_linkedin_fallback,
    prepare_public_copy,
    sanitize_public_copy,
)
from xintelops.delivery.live_events import parse_pkt_scan_time
from xintelops.delivery.ranking import infer_niche_tier
from xintelops.delivery.strategic_lane import compute_strategic_lane_score, has_core_region_involvement

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
    pseudo = {
        "title": str(row.get("internal_brief") or row.get("source_name") or ""),
        "region": row.get("region"),
        "domain": row.get("domain"),
        "why_hamza_should_care": str(row.get("internal_brief") or row.get("what_most_people_missed") or ""),
    }
    lane = compute_strategic_lane_score(pseudo)
    confidence = str(row.get("confidence") or "").lower()
    conf_bonus = 3 if confidence == "high" else 1 if confidence == "medium" else 0
    crisis_bonus = 2 if row.get("crisis_flag") else 0
    core_bonus = 3 if has_core_region_involvement(pseudo) else 0
    return lane + conf_bonus + crisis_bonus + core_bonus


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
    primary = ranked[0]
    secondary = ranked[1] if len(ranked) > 1 else None

    topic_idx = hash(str(primary.get("region") or "global")) % len(SYNTHESIS_TOPICS)
    topic = SYNTHESIS_TOPICS[topic_idx]

    lines = [
        f"{topic}",
        "",
        f"Cross-event synthesis from the last {horizon} of verified intelligence. Sources separated by claim.",
        "",
        "Primary Event:",
        f"  {primary.get('source_name', 'Source')}: {str(primary.get('internal_brief') or primary.get('what_most_people_missed') or '')[:280]}",
    ]
    if secondary:
        lines.extend(
            [
                "",
                "Secondary Signal:",
                f"  {secondary.get('source_name', 'Source')}: {str(secondary.get('internal_brief') or secondary.get('what_most_people_missed') or '')[:280]}",
                "",
                "Synthesis:",
                "These signals may converge on a structural shift. Verify the explicit linkage before posting.",
            ]
        )
    lines.extend(
        [
            "",
            "Operator takeaway:",
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


def _gate_linkedin_copy(
    article: str,
    sources: list[dict[str, Any]],
    primary_title: str,
    topic_sig: dict[str, Any] | None,
    secondary_signals: list[dict[str, Any]] | None = None,
) -> tuple[str, bool, str]:
    """Sanitize, validate, repair, fallback. Returns (text, passed, block_reason)."""
    if not article.strip():
        return "", False, "Empty LinkedIn draft."

    gate = prepare_public_copy(
        article,
        "linkedin",
        "linkedin_post",
        sources=sources,
        primary_title=primary_title,
    )
    if gate["passed"]:
        return gate["text"], True, ""

    fallback = build_safe_linkedin_fallback(
        topic_sig or {},
        sources,
        secondary_signals or [],
    )
    fallback_gate = prepare_public_copy(
        fallback,
        "linkedin",
        "linkedin_post",
        sources=sources,
        primary_title=primary_title,
    )
    if fallback_gate["passed"]:
        return fallback_gate["text"], True, ""

    reason = gate.get("block_reason") or fallback_gate.get("block_reason") or "Final copy quality fail."
    return "", False, reason


def build_linkedin_block(
    result: dict[str, Any],
    db_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    day = str(result.get("day_of_week") or "")
    next_li = next_linkedin_day(day)
    next_window = f"{next_li} 09:00–11:00 PKT"
    current_time = format_pkt_now(result)
    window = linkedin_window_state(result)
    tier_meta = result.get("crisis_tier_meta") or classify_scan_tier(result)
    immediate_tier = tier_meta.get("immediate_tier") or "ROUTINE"
    crisis_exception = immediate_tier in POSTING_TIERS
    top_live = _top_live_signal(result)
    live_score = int(top_live.get("live_event_score", 0)) if top_live else 0

    base = {
        "window": "09:00-11:00 PKT",
        "current_time": current_time,
        "next_window": next_window,
        "format": "LinkedIn analysis",
        "source_package": [],
        "why_this_topic": "",
        "topic": "",
        "copy_this": "",
        "draft_ready": False,
        "copy_blocked": False,
        "block_reason": "",
    }

    if window == "not_scheduled" and not crisis_exception:
        return {
            **base,
            "status": "Not scheduled today",
            "action": "Hold until next LinkedIn window",
            "content_source": "N/A",
            "article_post": "",
            "copy_this": "",
            "todays_action": f"No LinkedIn post today ({day}). Next window: {next_window}.",
        }

    topic_sig, topic_reason = pick_linkedin_topic(result, db_outputs)
    cross_roles = result.get("cross_event_roles") or []
    article = str(result.get("linkedin_post") or "").strip()
    if topic_sig and not article.startswith("[DRAFT"):
        article = article or _draft_from_signal(topic_sig, cross_roles)
    elif topic_sig and (not article or article.startswith("[DRAFT")):
        article = _draft_from_signal(topic_sig, cross_roles)
    elif not article or article.startswith("[DRAFT"):
        article, source = synthesize_linkedin_from_db(db_outputs or [], "24–72 hours")
        if not article and db_outputs:
            article, source = synthesize_linkedin_from_db(db_outputs, "30 days")
        topic_reason = source if article else topic_reason

    if topic_sig:
        base["topic"] = topic_sig.get("title", "")
        base["why_this_topic"] = topic_reason
        base["source_package"] = _build_source_package_for_signal(result, topic_sig)

    secondary = [s for s in (result.get("ranked_signals") or []) if s.get("title") != base.get("topic")][:2]
    clean_article = ""
    li_blocked = False
    li_block_reason = ""

    if article:
        clean_article, li_passed, li_block_reason = _gate_linkedin_copy(
            article,
            base.get("source_package") or [],
            base.get("topic") or "",
            topic_sig,
            secondary,
        )
        li_blocked = not li_passed
        if li_passed:
            result["linkedin_post"] = clean_article
            base["article_post"] = clean_article
            base["draft_ready"] = True
        else:
            result["linkedin_post"] = ""
            base["article_post"] = ""
            base["draft_ready"] = False
            base["copy_blocked"] = True
            base["block_reason"] = li_block_reason
    else:
        base["article_post"] = ""
        base["draft_ready"] = False

    article = clean_article

    if window == "before_window":
        return {
            **base,
            "status": "Before scheduled window",
            "action": "Hold until window opens",
            "content_source": topic_reason,
            "copy_this": "",
            "draft_ready": bool(article) and not li_blocked,
            "todays_action": "Draft ready. Hold until 09:00 PKT." if article and not li_blocked else (
                f"LINKEDIN BLOCKED - FINAL COPY QUALITY FAIL\nReason: {li_block_reason}\nFallback: Hold until clean copy is generated."
                if li_blocked else "No draft ready."
            ),
        }

    if window == "in_window":
        if li_blocked:
            return {
                **base,
                "status": "In scheduled window",
                "action": "Hold",
                "content_source": topic_reason,
                "copy_this": "",
                "draft_ready": False,
                "copy_blocked": True,
                "block_reason": li_block_reason,
                "todays_action": f"LINKEDIN BLOCKED - FINAL COPY QUALITY FAIL\nReason: {li_block_reason}\nFallback: Hold until clean copy is generated.",
            }
        return {
            **base,
            "status": "In scheduled window",
            "action": "Post now",
            "content_source": topic_reason,
            "copy_this": article if article and not article.startswith("No LinkedIn post today") else "",
            "draft_ready": bool(article),
            "todays_action": "COPY THIS - post during 09:00-11:00 PKT window.",
        }

    if window == "not_scheduled" and crisis_exception:
        if li_blocked:
            return {
                **base,
                "status": "Crisis exception",
                "action": "Hold",
                "content_source": topic_reason,
                "article_post": "",
                "copy_this": "",
                "copy_blocked": True,
                "block_reason": li_block_reason,
                "todays_action": f"LINKEDIN BLOCKED - FINAL COPY QUALITY FAIL\nReason: {li_block_reason}\nFallback: Hold until clean copy is generated.",
                "exception_reason": f"Tier {immediate_tier} triggers LinkedIn exception.",
            }
        return {
            **base,
            "status": "Crisis exception",
            "action": "Post now despite non-scheduled day",
            "content_source": topic_reason,
            "article_post": article,
            "copy_this": article if article and not article.startswith("No LinkedIn post today") else "",
            "todays_action": f"Crisis tier {immediate_tier}. Post now despite non-scheduled day.",
            "exception_reason": f"Tier {immediate_tier} triggers LinkedIn exception.",
        }

    # after_window on scheduled day
    if window == "after_window" and crisis_exception:
        if li_blocked:
            return {
                **base,
                "status": "Crisis exception",
                "action": "Hold",
                "content_source": topic_reason,
                "article_post": "",
                "copy_this": "",
                "copy_blocked": True,
                "block_reason": li_block_reason,
                "todays_action": f"LINKEDIN BLOCKED - FINAL COPY QUALITY FAIL\nReason: {li_block_reason}\nFallback: Hold until clean copy is generated.",
                "exception_reason": f"Tier {immediate_tier} triggers LinkedIn exception.",
            }
        return {
            **base,
            "status": "Crisis exception",
            "action": "Post now despite missed window",
            "content_source": topic_reason,
            "article_post": article,
            "copy_this": article if article and not article.startswith("No LinkedIn post today") else "",
            "todays_action": f"Crisis tier {immediate_tier}. Post now even though window passed.",
            "exception_reason": f"Tier {immediate_tier} triggers LinkedIn exception.",
        }

    if window == "after_window":
        return {
            **base,
            "status": "Window passed",
            "action": "Roll to next LinkedIn window",
            "content_source": topic_reason,
            "article_post": "",
            "copy_this": "",
            "draft_ready": False,
            "suggested_next_topic": base.get("topic") or "Use next scan's strategic lead.",
            "todays_action": f"Missed window. Next normal window: {next_window}.",
        }

    return {
        **base,
        "status": "Not scheduled today",
        "action": "Hold until next LinkedIn window",
        "content_source": topic_reason,
        "article_post": "",
        "copy_this": "",
        "todays_action": f"No LinkedIn post today ({day}). Next window: {next_window}.",
    }


def _draft_from_signal(sig: dict[str, Any], cross_roles: list[dict[str, Any]] | None = None) -> str:
    title = sig.get("title") or "Signal"
    why = sig.get("why_hamza_should_care") or sig.get("action_rationale") or ""
    lane_why = sig.get("why_xintelops_fits") or ""
    lines = [title, "", why]
    if lane_why:
        lines.extend(["", f"Why this fits XIntelOps ({sig.get('lane_relevance_type', 'Strategic')}): {lane_why}"])
    if cross_roles:
        secondary = [r for r in cross_roles if r.get("role") == "Secondary Signal"]
        if secondary:
            lines.extend(["", "Secondary Signal:", f"  {secondary[0].get('title', '')}"])
            lines.extend(["", "Synthesis:", "  Verify explicit linkage between primary and secondary before posting."])
    return "\n".join(lines).strip()
