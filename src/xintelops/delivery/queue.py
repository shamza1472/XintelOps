from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from xintelops.delivery.ranking import compute_rank_score

PKT = timezone(timedelta(hours=5))
LATER_WINDOW_HOURS = 4
LATER_EXPIRY_HOURS = 6
ACTIVE_DEADLINE_MINUTES = 30
ACTIVE_EXPIRES_HOURS = 3


def parse_scan_time_pkt(result: dict[str, Any]) -> datetime:
    date_pkt = str(result.get("date_pkt") or datetime.now(PKT).strftime("%Y-%m-%d"))
    time_pkt = str(result.get("time_pkt") or "00:00 PKT").replace(" PKT", "").strip()
    try:
        return datetime.strptime(f"{date_pkt} {time_pkt}", "%Y-%m-%d %H:%M").replace(tzinfo=PKT)
    except ValueError:
        return datetime.now(PKT)


def format_pkt(dt: datetime) -> str:
    return dt.astimezone(PKT).strftime("%Y-%m-%d %H:%M PKT")


def _ensure_datetime(value: datetime | str | None, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return fallback


def _to_iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _format_draft(result: dict[str, Any], action: str) -> str:
    if action == "X THREAD":
        thread = result.get("x_thread")
        if isinstance(thread, list):
            return "\n\n".join(f"{i}/ {t}" for i, t in enumerate(thread, 1))
        return str(thread or result.get("x_post") or "")
    return str(result.get("x_post") or "")


def _format_label(action: str) -> str:
    if action == "X THREAD":
        return "THREAD"
    if action == "X POST":
        return "SINGLE TWEET"
    return action


def build_source_package(result: dict[str, Any], signal_title: str = "") -> list[dict[str, Any]]:
    explicit = result.get("source_package")
    if isinstance(explicit, list) and explicit:
        return explicit

    package: list[dict[str, Any]] = []
    for item in result.get("source_citations") or []:
        package.append(
            {
                "name": item.get("name") or item.get("source") or "Source",
                "url": item.get("url") or "",
                "published_date": item.get("published_date") or item.get("event_date") or "Unknown",
                "tier": item.get("tier") or "L1",
                "why_supports": item.get("why_supports")
                or f"Supports claims in: {signal_title or 'top signal'}",
            }
        )

    if not package:
        for sig in result.get("ranked_signals") or []:
            if sig.get("url"):
                package.append(
                    {
                        "name": sig.get("source") or "Source",
                        "url": sig.get("url"),
                        "published_date": sig.get("event_date") or "Unknown",
                        "tier": f"T{sig.get('niche_tier', 2)}",
                        "why_supports": sig.get("why_hamza_should_care") or sig.get("action_rationale") or "",
                    }
                )
    return package[:5]


def _pick_later_candidate(result: dict[str, Any]) -> dict[str, Any]:
    missing = (result.get("operator_decisions") or {}).get("one_signal_everyone_missing") or {}
    if missing.get("title"):
        return {
            "title": missing.get("title"),
            "draft": result.get("what_most_missed") or missing.get("why", ""),
            "format": "X POST",
        }
    for sig in result.get("ranked_signals") or []:
        if sig.get("recommended_action") in {"X POST", "MONITOR", "HIGH PRIORITY TRACKING"}:
            return {
                "title": sig.get("title"),
                "draft": sig.get("why_hamza_should_care") or "",
                "format": "X POST",
            }
    return {"title": "", "draft": "", "format": "X POST"}


def _priority_score(result: dict[str, Any]) -> float:
    post = (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    title = post.get("title")
    for sig in result.get("ranked_signals") or []:
        if sig.get("title") == title:
            return float(sig.get("rank_score") or compute_rank_score(sig).get("rank_score", 0))
    return 0.0


def resolve_queue(
    result: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve post-now vs post-later queue against the previous content_schedule row."""
    scan_time = parse_scan_time_pkt(result)
    post_decision = (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    post_action = str(post_decision.get("action") or "X POST")
    post_title = post_decision.get("title") or (result.get("top_signal") or {}).get("title") or "No post"
    post_why = post_decision.get("why") or ""

    later_candidate = _pick_later_candidate(result)
    later_active_from = scan_time + timedelta(hours=LATER_WINDOW_HOURS)
    later_expires_at = scan_time + timedelta(hours=LATER_EXPIRY_HOURS)

    queue: dict[str, Any] = {
        "previous_later_post": "",
        "status": "none",
        "reason": "No previous later-post in queue.",
    }

    prev_later_signal = ""
    prev_later_expires = None
    if previous:
        prev_later_signal = previous.get("later_signal") or previous.get("midday_signal") or ""
        prev_later_expires_raw = previous.get("later_expires_at")
        if prev_later_expires_raw:
            try:
                prev_later_expires = datetime.fromisoformat(
                    str(prev_later_expires_raw).replace("Z", "+00:00")
                )
            except ValueError:
                prev_later_expires = None

    current_priority = _priority_score(result)

    if prev_later_signal:
        queue["previous_later_post"] = prev_later_signal
        if prev_later_expires and prev_later_expires < scan_time:
            queue["status"] = "expired"
            queue["reason"] = "Previous later-post expired and archived."
        elif post_title and post_title != prev_later_signal:
            rank1 = (result.get("ranked_signals") or [{}])[0]
            tier = rank1.get("niche_tier", 3)
            if current_priority >= 70 or tier == 1:
                queue["status"] = "replaced"
                queue["reason"] = f"Previous later-post replaced by higher-priority signal: {post_title}."
            else:
                queue["status"] = "carried_forward"
                expiry_label = format_pkt(prev_later_expires) if prev_later_expires else "next scan"
                queue["reason"] = f"Previous later-post still valid until {expiry_label}."
                later_candidate = {
                    "title": prev_later_signal,
                    "draft": previous.get("later_draft") or previous.get("midday_draft") or "",
                    "format": previous.get("later_format") or "X POST",
                }
                if prev_later_expires:
                    later_expires_at = prev_later_expires
                later_active_from = _ensure_datetime(
                    previous.get("later_active_from"), later_active_from
                )
        else:
            queue["status"] = "carried_forward"
            expiry_label = format_pkt(prev_later_expires) if prev_later_expires else "next scan"
            queue["reason"] = f"Previous later-post still valid until {expiry_label}."
            later_candidate = {
                "title": prev_later_signal,
                "draft": previous.get("later_draft") or previous.get("midday_draft") or "",
                "format": previous.get("later_format") or "X POST",
            }
            if prev_later_expires:
                later_expires_at = prev_later_expires
            later_active_from = _ensure_datetime(
                previous.get("later_active_from"), later_active_from
            )

    source_package = build_source_package(result, post_title)
    active_deadline = scan_time + timedelta(minutes=ACTIVE_DEADLINE_MINUTES)
    active_expires = scan_time + timedelta(hours=ACTIVE_EXPIRES_HOURS)

    operator_block = {
        "x": {
            "action": post_action,
            "format": _format_label(post_action),
            "post_now": post_title,
            "deadline": format_pkt(active_deadline),
            "expires": format_pkt(active_expires),
            "why_this_won": post_why,
            "source_package": source_package,
            "draft": _format_draft(result, post_action),
        },
        "linkedin": result.get("linkedin_block") or {},
        "queue": queue,
        "regional_priority": result.get("regional_priority_check") or {},
    }

    queue_status = queue["status"]
    if post_action in {"X POST", "X THREAD"}:
        queue_status = f"active_{queue['status']}"

    result["operator_block"] = operator_block
    result["content_queue"] = {
        "active_now_signal": post_title,
        "active_now_format": _format_label(post_action),
        "active_now_draft": _format_draft(result, post_action),
        "active_now_deadline": active_deadline.isoformat(),
        "active_now_expires_at": active_expires.isoformat(),
        "active_now_reason": post_why,
        "active_now_source_package": source_package,
        "later_signal": later_candidate.get("title") or "",
        "later_format": later_candidate.get("format") or "X POST",
        "later_draft": later_candidate.get("draft") or "",
        "later_active_from": _to_iso(later_active_from) if later_candidate.get("title") else None,
        "later_expires_at": _to_iso(later_expires_at) if later_candidate.get("title") else None,
        "later_status": queue["status"] if later_candidate.get("title") else "none",
        "later_replaced_by": post_title if queue["status"] == "replaced" else None,
        "later_reason": queue["reason"],
        "queue_status": queue_status,
        "operator_action_summary": (
            f"Post now: {post_title} ({_format_label(post_action)}). "
            f"Queue: {queue['reason']}"
        ),
    }
    return result
