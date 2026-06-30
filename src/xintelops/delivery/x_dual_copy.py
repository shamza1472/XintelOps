from __future__ import annotations

import re
from typing import Any

from xintelops.delivery.public_copy_gate import (
    build_minimal_verified_single_tweet,
    format_operator_block_reason,
    get_verified_signals,
    prepare_public_copy,
    repair_editorial_public_copy,
    repair_incomplete_public_copy,
    resolve_effective_format_recommendation,
    selected_signal_has_verified_source,
    validate_copy_signal_binding,
    _foreign_topic_violations,
    _violations_are_completeness_only,
    _violations_are_editorial_only,
)
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    format_single_post,
    format_thread_for_display,
    is_malformed_tweet,
    parse_x_thread,
    validate_thread_tweets,
)

_INTERNAL_SKIP = re.compile(
    r"why_this_fits|xintelops|operator|score|lane|headline cycle|most analysts|the signal|watch next|bottom line|"
    r"dominant headline|prior scans|monitor only|repost|already covered",
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
    use_top = bool(top) and str(top.get("title") or "") == str(signal.get("title") or primary_title)

    verified: list[str] = []
    verified_source = (top.get("verified_facts") if use_top else None) or signal.get("verified_facts") or []
    for item in verified_source:
        if isinstance(item, dict):
            verified.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            verified.append(str(item))
    verified = [v.strip() for v in verified if v.strip()]

    title = _clean_fact_text(primary_title or signal.get("title") or (top.get("title") if use_top else "") or "")
    implication = _clean_fact_text(
        signal.get("summary")
        or signal.get("why_hamza_should_care")
        or (top.get("summary") if use_top else "")
        or ""
    )
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
        "region": str(signal.get("region") or (top.get("region") if use_top else "") or (regions[0] if regions else "")),
        "domain": str(signal.get("domain") or (top.get("domain") if use_top else "") or ""),
        "source": str(signal.get("source") or (top.get("source") if use_top else "") or ""),
        "confidence": str(signal.get("confidence") or (top.get("confidence") if use_top else "") or ""),
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

    pseudo_signal = {
        "title": facts.get("title") or "",
        "region": facts.get("region") or "",
        "domain": facts.get("domain") or "",
    }
    if implication and _foreign_topic_violations(implication, pseudo_signal, []):
        implication = ""

    parts: list[str] = []
    if event:
        parts.append(event)

    title_lower = str(facts.get("title") or "").lower()
    region = str(facts.get("region") or "").lower()
    if (
        "iran" in title_lower
        and ("us" in title_lower or "stand down" in title_lower or "stand-down" in title_lower)
    ):
        parts.append(
            "The issue now is whether the pause lowers Hormuz shipping risk, Gulf basing pressure, "
            "and insurance pricing before the next round of Doha talks."
        )
    elif implication and implication.lower() not in (event or "").lower():
        parts.append(implication if implication.endswith(".") else f"{implication}.")
    elif region in {"gulf", "middle east"} or "hormuz" in title_lower:
        parts.append(
            "The issue now is whether the pause lowers shipping risk, Gulf basing pressure, "
            "and insurance pricing before follow-on diplomacy."
        )

    text = " ".join(parts).strip()
    return text


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

    title_lower = str(facts.get("title") or "").lower()
    region = str(facts.get("region") or "").lower()
    if "iran" in title_lower and ("stand down" in title_lower or "stand-down" in title_lower):
        tweets.append(
            "The issue now is whether the pause lowers Hormuz shipping risk, Gulf basing pressure, "
            "and insurance pricing before the next round of Doha talks."
        )
    elif region in {"gulf", "middle east"} or "hormuz" in title_lower:
        tweets.append("The issue is whether shipping and basing risk ease before the talks.")
    elif facts.get("implication"):
        imp = facts["implication"]
        tweets.append(imp if imp.endswith(".") else f"{imp}.")

    if "iran" in title_lower or "hormuz" in title_lower:
        tweets.append(
            "Some details remain unclear, including how Tehran frames the stand-down and whether Gulf states adjust basing alerts."
        )
    else:
        tweets.append("Some details remain unclear until follow-on reporting confirms the timeline.")

    region_label = facts.get("region") or "the region"
    tweets.append(
        f"The next indicators are official statements, transit behavior in {region_label}, and follow-on reporting."
    )

    cleaned = [t for t in tweets if t and len(t) >= 20]
    return cleaned[:6]


def _format_block_reason(format_label: str, reason: str) -> str:
    clean = format_operator_block_reason(reason, format_label=format_label)
    return f"{format_label.upper()} BLOCKED - FINAL COPY QUALITY FAIL\nReason: {clean}"


def _empty_single_result(reason: str) -> dict[str, Any]:
    return {
        "passed": False,
        "text": "",
        "display": "",
        "block_reason": reason,
        "fallback_used": False,
        "fallback_signal": "",
        "fallback_reason": "",
    }


def _finalize_single(
    text: str,
    sources: list[dict[str, Any]],
    primary_title: str,
    *,
    selected_signal: dict[str, Any],
    other_signals: list[dict[str, Any]] | None = None,
    allowed_fallback_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    single = format_single_post(text)
    if not single or is_malformed_tweet(single):
        return _empty_single_result(
            "SINGLE TWEET BLOCKED - FINAL COPY QUALITY FAIL\nReason: Malformed or empty single tweet."
        )

    gate = prepare_public_copy(
        single,
        "x",
        "single_tweet",
        sources=sources,
        primary_title=primary_title,
    )
    if not gate["passed"] and _violations_are_completeness_only(gate.get("violations") or []):
        repaired = repair_incomplete_public_copy(single)
        if repaired:
            gate = prepare_public_copy(
                repaired,
                "x",
                "single_tweet",
                sources=sources,
                primary_title=primary_title,
            )
    if not gate["passed"] and _violations_are_editorial_only(gate.get("violations") or []):
        repaired = repair_editorial_public_copy(single)
        if repaired:
            gate = prepare_public_copy(
                repaired,
                "x",
                "single_tweet",
                sources=sources,
                primary_title=primary_title,
            )
    if not gate["passed"]:
        reason = gate.get("block_reason") or "Final copy quality fail."
        return _empty_single_result(_format_block_reason("Single tweet", reason))

    binding = validate_copy_signal_binding(
        gate["text"],
        selected_signal,
        sources,
        allowed_fallback_signal=allowed_fallback_signal,
        other_signals=other_signals,
    )
    if not binding["passed"]:
        return _empty_single_result(
            _format_block_reason("Single tweet", binding.get("block_reason", "Signal binding fail"))
        )

    final = gate["text"]
    result = {"passed": True, "text": final, "display": final, "block_reason": ""}
    if allowed_fallback_signal:
        result["fallback_used"] = True
        result["fallback_signal"] = allowed_fallback_signal.get("title") or ""
        result["fallback_reason"] = "Selected signal failed copy validation."
    else:
        result["fallback_used"] = False
        result["fallback_signal"] = ""
        result["fallback_reason"] = ""
    return result


def _finalize_thread(
    tweets: list[str],
    sources: list[dict[str, Any]],
    primary_title: str,
    *,
    selected_signal: dict[str, Any],
    other_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not tweets:
        return {
            "passed": False,
            "text": "",
            "tweets": [],
            "display": "",
            "block_reason": _format_block_reason("Thread", "No thread tweets available."),
        }

    validation = validate_thread_tweets(tweets)
    if validation.get("blocked"):
        return {
            "passed": False,
            "text": "",
            "tweets": [],
            "display": "",
            "block_reason": _format_block_reason("Thread", validation.get("block_reason") or "Malformed thread."),
        }

    edited_tweets: list[str] = []
    for tweet in validation["tweets"]:
        gate = prepare_public_copy(
            tweet,
            "x",
            "thread",
            sources=sources,
            primary_title=primary_title,
        )
        if not gate["passed"]:
            return {
                "passed": False,
                "text": "",
                "tweets": [],
                "display": "",
                "block_reason": _format_block_reason("Thread", gate.get("block_reason", "Editorial fail")),
            }
        binding = validate_copy_signal_binding(
            gate["text"],
            selected_signal,
            sources,
            other_signals=other_signals,
            thread_mode=True,
        )
        if not binding["passed"]:
            return {
                "passed": False,
                "text": "",
                "tweets": [],
                "display": "",
                "block_reason": _format_block_reason("Thread", binding.get("block_reason", "Signal binding fail")),
            }
        edited_tweets.append(gate["text"])

    combined_binding = validate_copy_signal_binding(
        " ".join(edited_tweets),
        selected_signal,
        sources,
        other_signals=other_signals,
    )
    if not combined_binding["passed"]:
        return {
            "passed": False,
            "text": "",
            "tweets": [],
            "display": "",
            "block_reason": _format_block_reason("Thread", combined_binding.get("block_reason", "Signal binding fail")),
        }

    tweets_with_footer = apply_brand_footer_to_tweets(edited_tweets)
    display = format_thread_for_display(tweets_with_footer, add_brand_footer=False)
    return {
        "passed": True,
        "text": display,
        "tweets": tweets_with_footer,
        "display": display,
        "block_reason": "",
    }


def _mandatory_single_fallback(
    result: dict[str, Any],
    sources: list[dict[str, Any]],
    primary_title: str,
    signal: dict[str, Any],
    other_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build minimal tweet from selected signal only; cross-signal fallback only without verified source."""
    minimal = build_minimal_verified_single_tweet(signal, sources)
    if minimal:
        attempt = _finalize_single(
            minimal,
            sources,
            primary_title,
            selected_signal=signal,
            other_signals=other_signals,
        )
        if attempt["passed"]:
            return attempt

    if selected_signal_has_verified_source(signal, sources):
        return _empty_single_result(
            "SINGLE TWEET BLOCKED - FINAL COPY QUALITY FAIL\nReason: No clean single tweet from selected signal."
        )

    for alt in get_verified_signals(result):
        alt_title = alt.get("title") or ""
        if alt_title == primary_title:
            continue
        minimal = build_minimal_verified_single_tweet(alt, sources)
        if not minimal:
            continue
        attempt = _finalize_single(
            minimal,
            sources,
            alt_title,
            selected_signal=signal,
            other_signals=other_signals,
            allowed_fallback_signal=alt,
        )
        if attempt["passed"]:
            return attempt

    return _empty_single_result(
        "SINGLE TWEET BLOCKED - FINAL COPY QUALITY FAIL\nReason: No clean single tweet from verified signals."
    )


def build_dual_x_copy(
    result: dict[str, Any],
    sources: list[dict[str, Any]],
    primary_title: str,
    requested_action: str = "",
) -> dict[str, Any]:
    """Build, validate, and gate single tweet and thread independently for the selected signal."""
    verified_signals = get_verified_signals(result)
    has_verified = bool(verified_signals)
    other_signals = [s for s in (result.get("ranked_signals") or []) if s.get("title") != primary_title]

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
    minimal = build_minimal_verified_single_tweet(signal, sources)
    if minimal and minimal not in single_candidates:
        single_candidates.append(minimal)
    if not single_candidates and parse_x_thread(result.get("x_thread")):
        single_candidates.append(parse_x_thread(result.get("x_thread"))[0])

    single_result = _empty_single_result(
        "SINGLE TWEET BLOCKED - FINAL COPY QUALITY FAIL\nReason: No single tweet candidate."
    )
    for candidate in single_candidates:
        attempt = _finalize_single(
            candidate,
            sources,
            primary_title,
            selected_signal=signal,
            other_signals=other_signals,
        )
        if attempt["passed"]:
            single_result = attempt
            break
        single_result = attempt

    if not single_result["passed"] and has_verified:
        single_result = _mandatory_single_fallback(
            result, sources, primary_title, signal, other_signals
        )

    thread_candidates: list[list[str]] = []
    built_thread = build_thread_from_facts(facts)
    if built_thread and len(built_thread) >= 3:
        thread_candidates.append(built_thread)
    agent_thread = parse_x_thread(result.get("x_thread"))
    if agent_thread:
        thread_candidates.append(agent_thread)

    thread_result: dict[str, Any] = {
        "passed": False,
        "text": "",
        "tweets": [],
        "display": "",
        "block_reason": "THREAD BLOCKED - FINAL COPY QUALITY FAIL\nReason: No thread candidate.",
    }
    for candidate in thread_candidates:
        attempt = _finalize_thread(
            candidate,
            sources,
            primary_title,
            selected_signal=signal,
            other_signals=other_signals,
        )
        if attempt["passed"]:
            thread_result = attempt
            break
        thread_result = attempt

    any_pass = single_result["passed"] or thread_result["passed"]
    effective_format, effective_format_reason = resolve_effective_format_recommendation(
        recommended,
        format_reason,
        single_passed=single_result["passed"],
        thread_passed=thread_result["passed"],
    )

    if effective_format == "SINGLE TWEET" and single_result["passed"]:
        primary_draft = single_result["display"]
    elif effective_format == "THREAD" and thread_result["passed"]:
        primary_draft = thread_result["display"]
    elif single_result["passed"]:
        primary_draft = single_result["display"]
    elif thread_result["passed"]:
        primary_draft = thread_result["display"]
    else:
        primary_draft = ""

    return {
        "recommended_format": effective_format,
        "format_reason": effective_format_reason,
        "original_recommended_format": recommended,
        "original_format_reason": format_reason,
        "single": single_result,
        "thread": thread_result,
        "any_passed": any_pass,
        "both_failed": not any_pass,
        "primary_draft": primary_draft,
        "has_verified_signals": has_verified,
        "mandatory_single_met": single_result["passed"],
        "bound_signal_title": primary_title,
        "fallback_used": single_result.get("fallback_used", False),
        "fallback_signal": single_result.get("fallback_signal", ""),
        "fallback_reason": single_result.get("fallback_reason", ""),
    }
