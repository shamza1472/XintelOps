from __future__ import annotations

import re
from typing import Any

from xintelops.delivery.editorial import editorial_pipeline
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    apply_final_copy_safety_gate,
    fit_tweet_length,
    format_single_post,
    format_thread_for_display,
    is_malformed_tweet,
    parse_x_thread,
    validate_thread_tweets,
)

_INTERNAL_SKIP = re.compile(
    r"why_this_fits|xintelops|operator|score|lane|headline cycle|most analysts|the signal|watch next|bottom line",
    re.I,
)


def _clean_fact_text(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if not t or _INTERNAL_SKIP.search(t):
        return ""
    return t.rstrip(".")


def _selected_signal(result: dict[str, Any], primary_title: str) -> dict[str, Any]:
    for sig in result.get("ranked_signals") or []:
        if sig.get("title") == primary_title:
            return sig
    return (result.get("ranked_signals") or [{}])[0] if result.get("ranked_signals") else {}


def extract_signal_facts(result: dict[str, Any], primary_title: str) -> dict[str, Any]:
    signal = _selected_signal(result, primary_title)
    top = result.get("top_signal") or {}
    verified: list[str] = []
    for item in top.get("verified_facts") or signal.get("verified_facts") or []:
        if isinstance(item, dict):
            verified.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            verified.append(str(item))
    verified = [v.strip() for v in verified if v.strip()]

    title = _clean_fact_text(primary_title or signal.get("title") or top.get("title") or "")
    implication = _clean_fact_text(
        signal.get("summary")
        or signal.get("why_hamza_should_care")
        or top.get("summary")
        or ""
    )
    watch = _clean_fact_text(signal.get("action_rationale") or "")

    regions = signal.get("regions") or []
    if isinstance(regions, str):
        regions = [regions]
    actors = signal.get("actors") or signal.get("entities") or []
    if isinstance(actors, str):
        actors = [actors]

    return {
        "title": title,
        "event": f"{title.rstrip('.')}." if title else "",
        "implication": implication,
        "watch": watch,
        "region": str(signal.get("region") or top.get("region") or (regions[0] if regions else "")),
        "domain": str(signal.get("domain") or top.get("domain") or ""),
        "source": str(signal.get("source") or top.get("source") or ""),
        "confidence": str(signal.get("confidence") or top.get("confidence") or ""),
        "verified_facts": verified[:4],
        "live_event_score": int(signal.get("live_event_score") or 0),
        "update_velocity": int(signal.get("update_velocity") or 0),
        "consequence_score": int(signal.get("consequence_score") or 0),
        "region_count": len(regions) if regions else (1 if signal.get("region") else 0),
        "actor_count": len(actors) if actors else 0,
        "has_sequence": int(signal.get("update_velocity") or 0) >= 7 or len(verified) >= 2,
    }


def recommend_x_format(
    signal: dict[str, Any],
    facts: dict[str, Any],
    requested_action: str = "",
) -> tuple[str, str]:
    action = str(requested_action or signal.get("recommended_action") or "").upper()
    live = facts.get("live_event_score", 0)
    actors = facts.get("actor_count", 0)
    sequence = facts.get("has_sequence", False)
    verified = len(facts.get("verified_facts") or [])
    domains = 2 if facts.get("domain") and facts.get("region") else 1

    thread_score = 0
    if live >= 8:
        thread_score += 2
    if sequence:
        thread_score += 2
    if actors >= 2:
        thread_score += 2
    if verified >= 2:
        thread_score += 1
    if domains >= 2:
        thread_score += 1
    if action == "X THREAD":
        thread_score += 1
    if action == "X POST":
        thread_score -= 2

    if thread_score >= 4:
        return (
            "THREAD",
            "The event has a sequence, multiple actors, contested claims, and follow-on indicators.",
        )
    return (
        "SINGLE TWEET",
        "The event has one clear update and does not need multi-part explanation.",
    )


def build_single_from_facts(facts: dict[str, Any]) -> str:
    event = facts.get("event") or ""
    implication = facts.get("implication") or ""
    watch = facts.get("watch") or ""

    parts: list[str] = []
    if event:
        parts.append(event)
    if implication and implication.lower() not in (event or "").lower():
        parts.append(implication if implication.endswith(".") else f"{implication}.")
    if watch:
        watch_line = watch
        if not re.match(r"^(Watch|Treat|Worth)", watch_line, re.I):
            watch_line = f"Worth tracking whether {watch_line.rstrip('.')}."
        elif not watch_line.endswith("."):
            watch_line += "."
        parts.append(watch_line)
    elif facts.get("region"):
        parts.append(f"Worth tracking follow-on reporting from {facts['region']}.")

    text = " ".join(parts).strip()
    if not text:
        return ""
    return fit_tweet_length(text, 260)


def build_thread_from_facts(facts: dict[str, Any]) -> list[str]:
    tweets: list[str] = []
    if facts.get("event"):
        tweets.append(facts["event"])

    verified = facts.get("verified_facts") or []
    if verified:
        fact = verified[0]
        tweets.append(fact if fact.endswith(".") else f"{fact}.")
    elif facts.get("implication"):
        imp = facts["implication"]
        tweets.append(imp if imp.endswith(".") else f"{imp}.")

    if facts.get("implication") and (not verified or facts["implication"] != verified[0]):
        imp = facts["implication"]
        line = imp if imp.endswith(".") else f"{imp}."
        if line not in tweets:
            tweets.append(line)

    if facts.get("confidence", "").upper() == "HIGH":
        tweets.append("Available reporting is still developing on secondary details.")
    else:
        tweets.append("Treat early reporting as provisional until additional confirmation.")

    region = facts.get("region") or "the region"
    tweets.append(
        f"The next indicators are official statements, transit behavior in {region}, and follow-on reporting."
    )

    cleaned = [fit_tweet_length(t) for t in tweets if t and len(t) >= 20]
    return cleaned[:6]


def _finalize_single(text: str, sources: list[dict[str, Any]], primary_title: str) -> dict[str, Any]:
    single = format_single_post(text)
    if not single or is_malformed_tweet(single):
        return {
            "passed": False,
            "text": "",
            "display": "",
            "block_reason": "SINGLE TWEET BLOCKED — FINAL COPY QUALITY FAIL\nReason: Malformed or empty single tweet.",
        }
    edited = editorial_pipeline(single, sources, primary_title=primary_title)
    if edited.get("blocked"):
        return {
            "passed": False,
            "text": "",
            "display": "",
            "block_reason": f"SINGLE TWEET BLOCKED — FINAL COPY QUALITY FAIL\nReason: {edited.get('block_reason', 'Editorial fail')}",
        }
    gate = apply_final_copy_safety_gate([edited["text"]])
    if gate.get("blocked"):
        reason = gate.get("block_reason", "Final copy quality fail.")
        if reason.startswith("COPY BLOCKED"):
            reason = reason.replace("COPY BLOCKED — FINAL COPY QUALITY FAIL", "SINGLE TWEET BLOCKED — FINAL COPY QUALITY FAIL", 1)
        return {"passed": False, "text": "", "display": "", "block_reason": reason}
    final = gate["tweets"][0]
    return {"passed": True, "text": final, "display": final, "block_reason": ""}


def _finalize_thread(tweets: list[str], sources: list[dict[str, Any]], primary_title: str) -> dict[str, Any]:
    if not tweets:
        return {
            "passed": False,
            "text": "",
            "tweets": [],
            "display": "",
            "block_reason": "THREAD BLOCKED — FINAL COPY QUALITY FAIL\nReason: No thread tweets available.",
        }
    validation = validate_thread_tweets(tweets)
    if validation.get("blocked"):
        reason = validation.get("block_reason") or "Malformed thread."
        return {
            "passed": False,
            "text": "",
            "tweets": [],
            "display": "",
            "block_reason": f"THREAD BLOCKED — FINAL COPY QUALITY FAIL\nReason: {reason}",
        }
    edited_tweets: list[str] = []
    for tweet in validation["tweets"]:
        edited = editorial_pipeline(tweet, sources, primary_title=primary_title)
        if edited.get("blocked"):
            return {
                "passed": False,
                "text": "",
                "tweets": [],
                "display": "",
                "block_reason": f"THREAD BLOCKED — FINAL COPY QUALITY FAIL\nReason: {edited.get('block_reason', 'Editorial fail')}",
            }
        edited_tweets.append(edited["text"])
    tweets_with_footer = apply_brand_footer_to_tweets(edited_tweets)
    gate = apply_final_copy_safety_gate(tweets_with_footer)
    if gate.get("blocked"):
        reason = gate.get("block_reason", "Final copy quality fail.")
        if reason.startswith("COPY BLOCKED"):
            reason = reason.replace("COPY BLOCKED — FINAL COPY QUALITY FAIL", "THREAD BLOCKED — FINAL COPY QUALITY FAIL", 1)
        return {"passed": False, "text": "", "tweets": [], "display": "", "block_reason": reason}
    final_tweets = gate["tweets"]
    display = format_thread_for_display(final_tweets, add_brand_footer=False)
    return {
        "passed": True,
        "text": display,
        "tweets": final_tweets,
        "display": display,
        "block_reason": "",
    }


def build_dual_x_copy(
    result: dict[str, Any],
    sources: list[dict[str, Any]],
    primary_title: str,
    requested_action: str = "",
) -> dict[str, Any]:
    """Build, validate, and gate single tweet and thread independently."""
    signal = _selected_signal(result, primary_title)
    facts = extract_signal_facts(result, primary_title)
    recommended, format_reason = recommend_x_format(signal, facts, requested_action)

    single_candidates: list[str] = []
    agent_single = format_single_post(str(result.get("x_post") or ""))
    if agent_single:
        single_candidates.append(agent_single)
    built_single = build_single_from_facts(facts)
    if built_single and built_single not in single_candidates:
        single_candidates.append(built_single)
    if not single_candidates and parse_x_thread(result.get("x_thread")):
        single_candidates.append(parse_x_thread(result.get("x_thread"))[0])

    single_result: dict[str, Any] = {
        "passed": False,
        "text": "",
        "display": "",
        "block_reason": "SINGLE TWEET BLOCKED — FINAL COPY QUALITY FAIL\nReason: No single tweet candidate.",
    }
    for candidate in single_candidates:
        attempt = _finalize_single(candidate, sources, primary_title)
        if attempt["passed"]:
            single_result = attempt
            break
        single_result = attempt

    thread_candidates: list[list[str]] = []
    agent_thread = parse_x_thread(result.get("x_thread"))
    if agent_thread:
        thread_candidates.append(agent_thread)
    built_thread = build_thread_from_facts(facts)
    if built_thread and len(built_thread) >= 3:
        thread_candidates.append(built_thread)

    thread_result: dict[str, Any] = {
        "passed": False,
        "text": "",
        "tweets": [],
        "display": "",
        "block_reason": "THREAD BLOCKED — FINAL COPY QUALITY FAIL\nReason: No thread candidate.",
    }
    for candidate in thread_candidates:
        attempt = _finalize_thread(candidate, sources, primary_title)
        if attempt["passed"]:
            thread_result = attempt
            break
        thread_result = attempt

    any_pass = single_result["passed"] or thread_result["passed"]
    if recommended == "SINGLE TWEET" and single_result["passed"]:
        primary_draft = single_result["display"]
    elif recommended == "THREAD" and thread_result["passed"]:
        primary_draft = thread_result["display"]
    elif single_result["passed"]:
        primary_draft = single_result["display"]
    elif thread_result["passed"]:
        primary_draft = thread_result["display"]
    else:
        primary_draft = ""

    return {
        "recommended_format": recommended,
        "format_reason": format_reason,
        "single": single_result,
        "thread": thread_result,
        "any_passed": any_pass,
        "both_failed": not any_pass,
        "primary_draft": primary_draft,
    }
