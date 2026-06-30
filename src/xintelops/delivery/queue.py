from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from xintelops.delivery.editorial import editorial_pipeline
from xintelops.delivery.public_copy_gate import (
    resolve_effective_format_recommendation,
)
from xintelops.delivery.ranking import compute_rank_score
from xintelops.delivery.source_roles import build_role_separated_package
from xintelops.delivery.x_dual_copy import build_dual_x_copy
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    apply_final_copy_safety_gate,
    apply_x_copy_to_result,
    format_thread_for_display,
    prepare_x_copy,
)

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


def _format_draft(result: dict[str, Any], action: str) -> str:
    """Build publishable X copy with normalization and editorial pass."""
    result = apply_x_copy_to_result(result, action)
    meta = result.get("_x_copy_meta") or prepare_x_copy(result, action)
    if meta.get("blocked"):
        return ""

    copy_text = meta.get("copy_text") or ""
    primary_title = (
        (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    ).get("title", "")
    buckets = build_role_separated_package(result, primary_title)
    flat_sources = []
    for items in buckets.values():
        flat_sources.extend(items)

    if meta.get("copy_type") == "thread":
        edited_tweets = []
        for tweet in meta.get("tweets") or []:
            edited = editorial_pipeline(tweet, flat_sources, primary_title=primary_title)
            if edited.get("blocked"):
                result["_x_copy_meta"] = {**meta, "blocked": True, "block_reason": edited.get("block_reason")}
                return ""
            edited_tweets.append(edited["text"])
        tweets_with_footer = apply_brand_footer_to_tweets(edited_tweets)
        final_gate = apply_final_copy_safety_gate(tweets_with_footer)
        if final_gate["blocked"]:
            result["_x_copy_meta"] = {
                **meta,
                "blocked": True,
                "block_reason": final_gate["block_reason"],
            }
            return ""
        final_tweets = final_gate["tweets"]
        result["x_thread"] = final_tweets
        result["_editorial_scores"] = edited.get("scores") if edited_tweets else {}
        result["_claim_map"] = edited.get("claims") if edited_tweets else []
        return format_thread_for_display(final_tweets, add_brand_footer=False)

    edited = editorial_pipeline(copy_text, flat_sources, primary_title=primary_title)
    if edited.get("blocked"):
        result["_x_copy_meta"] = {**meta, "blocked": True, "block_reason": edited.get("block_reason")}
        return ""
    final_gate = apply_final_copy_safety_gate([edited["text"]])
    if final_gate["blocked"]:
        result["_x_copy_meta"] = {**meta, "blocked": True, "block_reason": final_gate["block_reason"]}
        return ""
    result["x_post"] = final_gate["tweets"][0]
    result["_editorial_scores"] = edited.get("scores")
    result["_claim_map"] = edited.get("claims")
    return final_gate["tweets"][0]


def _active_now_format_label(
    *,
    x_blocked: bool,
    single_ok: bool,
    thread_ok: bool,
    recommended_format: str,
) -> str:
    if x_blocked or (not single_ok and not thread_ok):
        return "MONITOR_ONLY"
    if recommended_format == "THREAD" and thread_ok:
        return "THREAD"
    if single_ok:
        return "SINGLE_TWEET"
    if thread_ok:
        return "THREAD"
    return "MONITOR_ONLY"


def _active_now_draft(
    *,
    x_blocked: bool,
    single_ok: bool,
    thread_ok: bool,
    recommended_format: str,
    single: dict[str, Any],
    thread: dict[str, Any],
) -> str:
    if x_blocked:
        return ""
    if recommended_format == "THREAD" and thread_ok:
        return thread.get("display") or ""
    if single_ok:
        return single.get("display") or single.get("text") or ""
    if thread_ok:
        return thread.get("display") or ""
    return ""


def _format_label(action: str) -> str:
    if action == "X THREAD":
        return "THREAD"
    if action == "X POST":
        return "SINGLE POST"
    return action


def build_source_package(result: dict[str, Any], signal_title: str = "") -> list[dict[str, Any]]:
    title = signal_title or (result.get("operator_decisions") or {}).get("one_signal_to_post", {}).get("title", "")

    explicit = result.get("source_package")
    if isinstance(explicit, list) and explicit:
        bound = [p for p in explicit if title and title.lower()[:40] in str(p.get("why_supports", "")).lower()]
        if bound:
            return bound[:5]
        if any(title.lower()[:30] in str(p.get("why_supports", "")).lower() for p in explicit):
            return explicit[:5]

    selected = next((s for s in result.get("ranked_signals") or [] if s.get("title") == title), None)
    if selected and selected.get("url"):
        package = [
            {
                "name": selected.get("source") or "Source",
                "url": selected.get("url"),
                "published_date": selected.get("event_date") or "Unknown",
                "tier": f"T{selected.get('niche_tier', 2)}",
                "why_supports": selected.get("why_hamza_should_care") or f"Primary source for: {title}",
            }
        ]
        for item in result.get("source_citations") or []:
            if item.get("url") and item.get("url") != selected.get("url"):
                package.append(
                    {
                        "name": item.get("name") or item.get("source") or "Source",
                        "url": item.get("url") or "",
                        "published_date": item.get("published_date") or item.get("event_date") or "Unknown",
                        "tier": item.get("tier") or "L1",
                        "why_supports": item.get("why_supports") or f"Corroborates: {title}",
                    }
                )
        return package[:5]

    package: list[dict[str, Any]] = []
    for item in result.get("source_citations") or []:
        package.append(
            {
                "name": item.get("name") or item.get("source") or "Source",
                "url": item.get("url") or "",
                "published_date": item.get("published_date") or item.get("event_date") or "Unknown",
                "tier": item.get("tier") or "L1",
                "why_supports": item.get("why_supports") or f"Supports claims in: {title or 'top signal'}",
            }
        )

    if not package and selected and selected.get("url"):
        package.append(
            {
                "name": selected.get("source") or "Source",
                "url": selected.get("url"),
                "published_date": selected.get("event_date") or "Unknown",
                "tier": f"T{selected.get('niche_tier', 2)}",
                "why_supports": selected.get("why_hamza_should_care") or "",
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
                prev_later_expires = datetime.fromisoformat(str(prev_later_expires_raw).replace("Z", "+00:00"))
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
                later_active_from = previous.get("later_active_from") or later_active_from
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
            later_active_from = previous.get("later_active_from") or later_active_from

    source_buckets = build_role_separated_package(result, post_title)
    flat_sources = []
    for items in source_buckets.values():
        flat_sources.extend(items)

    draft = ""
    x_blocked = False
    x_block_reason = ""
    effective_action = post_action
    dual_copy: dict[str, Any] = {}

    if post_action in {"X POST", "X THREAD"}:
        dual_copy = build_dual_x_copy(result, flat_sources, post_title, post_action)
        result["_x_dual_copy"] = dual_copy

        single = dual_copy.get("single") or {}
        thread = dual_copy.get("thread") or {}
        delivery = dual_copy.get("delivery") or {}
        single_ok = bool(single.get("passed") or delivery.get("single_copy"))
        thread_ok = bool(thread.get("passed") or delivery.get("thread_copy"))
        has_verified = bool(dual_copy.get("has_verified_signals"))

        effective_format, effective_format_reason = resolve_effective_format_recommendation(
            dual_copy.get("original_recommended_format") or dual_copy.get("recommended_format") or "",
            dual_copy.get("original_format_reason") or dual_copy.get("format_reason") or "",
            single_passed=single_ok,
            thread_passed=thread_ok,
        )
        dual_copy["recommended_format"] = effective_format
        dual_copy["format_reason"] = effective_format_reason

        if single_ok:
            result["x_post"] = single.get("text") or delivery.get("single_copy") or ""
        else:
            result["x_post"] = ""

        if thread_ok:
            result["x_thread"] = thread.get("tweets") or delivery.get("thread_tweets") or []
        else:
            result["x_thread"] = []

        if not has_verified:
            x_blocked = True
            x_block_reason = "No verified signal exists in this scan."
            effective_action = "MONITOR"
            draft = ""
        else:
            x_blocked = False
            draft = _active_now_draft(
                x_blocked=False,
                single_ok=single_ok,
                thread_ok=thread_ok,
                recommended_format=effective_format,
                single=single,
                thread=thread,
            )
            effective_action = post_action

    active_deadline = scan_time + timedelta(minutes=ACTIVE_DEADLINE_MINUTES)
    active_expires = scan_time + timedelta(hours=ACTIVE_EXPIRES_HOURS)

    single_meta = dual_copy.get("single") or {}
    thread_meta = dual_copy.get("thread") or {}
    delivery = dual_copy.get("delivery") or {}

    x_section = {
        "action": effective_action,
        "requested_action": post_action,
        "format": _format_label(post_action) if not x_blocked else "BLOCKED",
        "recommended_format": dual_copy.get("recommended_format", ""),
        "format_reason": dual_copy.get("format_reason", ""),
        "post_now": post_title,
        "deadline": format_pkt(active_deadline),
        "expires": format_pkt(active_expires),
        "why_this_won": post_why,
        "source_package": flat_sources,
        "source_buckets": source_buckets,
        "draft": draft,
        "single_copy": delivery.get("single_copy") or single_meta.get("display") or "",
        "single_blocked": False if delivery.get("single_copy") else not single_meta.get("passed"),
        "single_block_reason": "",
        "thread_copy": delivery.get("thread_copy") or thread_meta.get("display") or "",
        "thread_blocked": False if delivery.get("thread_copy") else not thread_meta.get("passed"),
        "thread_block_reason": "",
        "copy_blocked": x_blocked,
        "no_verified_signal": not dual_copy.get("has_verified_signals", False) if dual_copy else False,
        "block_reason": x_block_reason,
        "fallback_used": dual_copy.get("fallback_used", False),
        "fallback_signal": dual_copy.get("fallback_signal", ""),
        "fallback_reason": dual_copy.get("fallback_reason", ""),
        "bound_signal_title": dual_copy.get("bound_signal_title", post_title),
        "editorial_scores": result.get("_editorial_scores") or {},
        "claim_map": result.get("_claim_map") or [],
        "single_internal_note": delivery.get("single_internal_note") or single_meta.get("internal_note") or "",
        "thread_internal_note": delivery.get("thread_internal_note") or thread_meta.get("internal_note") or "",
    }

    delivery_section = {
        "linkedin_copy": delivery.get("linkedin_copy") or (result.get("linkedin_block") or {}).get("copy_this") or "",
        "substack_copy": delivery.get("substack_copy") or "",
        "suggested_format": delivery.get("suggested_format") or dual_copy.get("recommended_format") or "",
        "suggested_format_reason": delivery.get("suggested_format_reason") or dual_copy.get("format_reason") or "",
        "linkedin_cadence_note": delivery.get("linkedin_cadence_note") or "",
        "linkedin_cadence_action": delivery.get("linkedin_cadence_action") or "",
        "youtube_note": delivery.get("youtube_note") or "YouTube: Not active yet. Video scripts will be added soon.",
    }

    if delivery_section.get("linkedin_copy"):
        li_block = dict(result.get("linkedin_block") or {})
        li_block["copy_this"] = li_block.get("copy_this") or delivery_section["linkedin_copy"]
        li_block["article_post"] = li_block.get("article_post") or delivery_section["linkedin_copy"]
        li_block.setdefault("copy_blocked", False)
        result["linkedin_block"] = li_block
    elif not result.get("linkedin_block"):
        from xintelops.delivery.linkedin_synthesis import build_linkedin_block

        result["linkedin_block"] = build_linkedin_block(result, [])
        delivery_section["linkedin_copy"] = result["linkedin_block"].get("copy_this") or ""

    operator_block = {
        "x": x_section,
        "linkedin": result.get("linkedin_block") or {},
        "delivery": delivery_section,
        "queue": queue,
        "regional_priority": result.get("strategic_lane_check") or result.get("regional_priority_check") or {},
        "strategic_lane": result.get("strategic_lane_check") or result.get("regional_priority_check") or {},
        "live_momentum": result.get("live_momentum_check") or {},
        "active_live_events": result.get("active_live_events") or {},
        "immediate_vs_strategic": {
            "immediate": (result.get("operator_decisions") or {}).get("best_immediate_post") or {},
            "strategic": (result.get("operator_decisions") or {}).get("best_strategic_lead") or {},
            "archive": (result.get("operator_decisions") or {}).get("best_archive_signal") or {},
        },
        "top_signals": result.get("top_signals_display") or {},
    }

    queue_status = queue["status"]
    if effective_action in {"X POST", "X THREAD"} and not x_blocked:
        queue_status = f"active_{queue['status']}"

    result["operator_block"] = operator_block
    result["content_queue"] = {
        "active_now_signal": post_title,
        "active_now_format": _active_now_format_label(
            x_blocked=x_blocked,
            single_ok=bool(single_meta.get("passed")),
            thread_ok=bool(thread_meta.get("passed")),
            recommended_format=dual_copy.get("recommended_format", "") if dual_copy else "",
        ),
        "active_now_draft": draft,
        "active_now_deadline": active_deadline.isoformat(),
        "active_now_expires_at": active_expires.isoformat(),
        "active_now_reason": post_why,
        "active_now_source_package": flat_sources,
        "later_signal": later_candidate.get("title") or "",
        "later_format": later_candidate.get("format") or "X POST",
        "later_draft": later_candidate.get("draft") or "",
        "later_active_from": later_active_from.isoformat() if later_candidate.get("title") else None,
        "later_expires_at": later_expires_at.isoformat() if later_candidate.get("title") else None,
        "later_status": queue["status"] if later_candidate.get("title") else "none",
        "later_replaced_by": post_title if queue["status"] == "replaced" else None,
        "later_reason": queue["reason"],
        "queue_status": queue_status,
        "operator_action_summary": (
            f"{'BLOCKED' if x_blocked else 'Post now'}: {post_title} ({_format_label(post_action)}). "
            f"Queue: {queue['reason']}"
        ),
    }
    return result
