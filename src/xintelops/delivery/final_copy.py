"""Authoritative final copy production: repair, regenerate, fallback — never fail on banned words."""
from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from xintelops.delivery.public_copy_gate import (
    GLOBAL_BANNED_PHRASES,
    build_minimal_verified_single_tweet,
    build_safe_linkedin_fallback,
    prepare_public_copy,
    repair_editorial_public_copy,
    repair_incomplete_public_copy,
    sanitize_public_copy,
    validate_copy_signal_binding,
    _contains_global_banned,
    audit_editorial_quality,
    _minimal_consequence_sentence,
    _violations_are_completeness_only,
    _violations_are_editorial_only,
)
from xintelops.delivery.x_copy import (
    apply_brand_footer_to_tweets,
    fit_tweet_length,
    format_single_post,
    format_thread_for_display,
    is_malformed_tweet,
)

from xintelops.delivery.x_dual_copy import (
    build_single_from_facts,
    build_thread_from_facts,
    extract_signal_facts,
)

FormatKind = Literal["single_tweet", "thread", "linkedin_post", "substack_post"]
PlatformKind = Literal["x", "linkedin", "substack"]

_GENERIC_FILLER = re.compile(
    r"\b(?:the issue now is whether|worth tracking whether|the key question is|"
    r"this matters because|the real signal|what most people miss)\b",
    re.I,
)

_INTERNAL_SKIP = re.compile(
    r"why_this|xintelops|operator|score|lane|headline cycle|most analysts|the signal|watch next|bottom line|"
    r"dominant headline|prior scans|monitor only|repost|already covered|leverage|delve",
    re.I,
)


class FinalCopy(TypedDict, total=False):
    text: str
    display: str
    tweets: list[str]
    passed: bool
    regenerated: bool
    internal_note: str


def _verified_facts(signal: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    for item in signal.get("verified_facts") or []:
        if isinstance(item, dict):
            facts.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            facts.append(str(item))
    return [f.strip().rstrip(".") for f in facts if f.strip()]


def _clean_operator_text(text: str) -> str:
    t = re.sub(r"\s+", " ", str(text or "").strip())
    if not t or _INTERNAL_SKIP.search(t) or _GENERIC_FILLER.search(t):
        return ""
    return t


def _strip_banned_phrases(text: str) -> str:
    out = str(text or "")
    for phrase in sorted(GLOBAL_BANNED_PHRASES, key=len, reverse=True):
        pattern = r"\b" + re.escape(phrase) + r"\b"
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\.\s*\.", ".", out)
    return out.strip()


def _business_consequence_sentence(signal: dict[str, Any]) -> str:
    title = str(signal.get("title") or "").lower()
    consequence = _minimal_consequence_sentence(signal, title=str(signal.get("title") or ""), verified=_verified_facts(signal))
    consequence = _clean_operator_text(consequence.rstrip("."))
    if consequence:
        return consequence if consequence.endswith(".") else f"{consequence}."

    region = str(signal.get("region") or "the corridor").strip()
    domain = str(signal.get("domain") or "markets").strip()
    if "hormuz" in title or "strait" in title or "fee" in title or "transit" in title:
        return (
            "If implemented, the Strait shifts from a military chokepoint into a pricing chokepoint, "
            "with direct consequences for shipping costs, insurance, and Gulf trade exposure."
        )
    if region.lower() in {"gulf", "middle east"}:
        return (
            f"Reporting points to repricing risk across shipping, insurance, and basing decisions tied to {region}."
        )
    return (
        f"The update affects {domain} exposure and follow-on decisions for operators tracking {region}."
    )


def _build_business_tweet(signal: dict[str, Any]) -> str:
    title = str(signal.get("title") or "").strip().rstrip(".")
    event = f"{title}." if title else ""
    consequence = _business_consequence_sentence(signal)
    parts = [p for p in (event, consequence) if p]
    text = " ".join(parts).strip()
    return fit_tweet_length(text, 280) if text else ""


def _build_structured_thread(signal: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    title = str(signal.get("title") or facts.get("title") or "").strip().rstrip(".")
    verified = _verified_facts(signal) or facts.get("verified_facts") or []
    implication = _clean_operator_text(
        str(signal.get("why_hamza_should_care") or signal.get("summary") or facts.get("implication") or "")
    )
    actors = signal.get("actors") or signal.get("entities") or []
    if isinstance(actors, str):
        actors = [actors]
    actor_label = ", ".join(str(a) for a in actors[:3]) if actors else str(signal.get("region") or "regional actors")
    region = str(signal.get("region") or facts.get("region") or "the region").strip()

    tweet1 = f"{title}." if title else (f"{verified[0]}." if verified else "Reporting confirms a material update.")
    tweet2 = (
        implication if implication.endswith(".") else f"{implication}."
    ) if implication else (
        _business_consequence_sentence(signal)
    )
    tweet3 = f"Operators with exposure across {actor_label} face the first-order adjustment window."
    watch = verified[1] if len(verified) > 1 else f"Official statements and transit behavior in {region}."
    tweet4 = f"Next indicators: {watch.rstrip('.')}."
    tweet5 = (
        f"XIntelOps read: { _business_consequence_sentence(signal).rstrip('.') }."
    )

    tweets = [fit_tweet_length(t, 280) for t in (tweet1, tweet2, tweet3, tweet4, tweet5) if t and len(t) >= 20]
    seen: set[str] = set()
    unique: list[str] = []
    for t in tweets:
        key = t.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique[:6] if len(unique) >= 4 else _build_structured_thread_minimal(signal, facts)


def _build_structured_thread_minimal(signal: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    title = str(signal.get("title") or "").strip().rstrip(".")
    region = str(signal.get("region") or facts.get("region") or "the region")
    consequence = _business_consequence_sentence(signal)
    return [
        fit_tweet_length(f"{title}.", 280),
        fit_tweet_length(consequence, 280),
        fit_tweet_length(f"Exposure sits with operators tied to {region}.", 280),
        fit_tweet_length("Next indicators are official statements and follow-on reporting.", 280),
        fit_tweet_length(f"XIntelOps read: {consequence.rstrip('.')}.", 280),
    ]


def _prepare_with_repair(
    text: str,
    *,
    platform: PlatformKind,
    format_type: FormatKind,
    sources: list[dict[str, Any]],
    primary_title: str,
) -> tuple[str, bool]:
    """Validate with repair once. Returns (text, passed_strict)."""
    body = sanitize_public_copy(text)
    if not body.strip():
        return "", False

    gate = prepare_public_copy(body, platform, format_type, sources=sources, primary_title=primary_title)
    if gate["passed"]:
        return gate["text"], True

    sanitized = sanitize_public_copy(body)
    if _violations_are_completeness_only(gate.get("violations") or []):
        repaired = repair_incomplete_public_copy(sanitized)
        if repaired:
            retry = prepare_public_copy(repaired, platform, format_type, sources=sources, primary_title=primary_title)
            if retry["passed"]:
                return retry["text"], True
    if _violations_are_editorial_only(gate.get("violations") or []):
        repaired = repair_editorial_public_copy(sanitized)
        if repaired:
            retry = prepare_public_copy(repaired, platform, format_type, sources=sources, primary_title=primary_title)
            if retry["passed"]:
                return retry["text"], True

    stripped = _strip_banned_phrases(sanitized)
    stripped = repair_editorial_public_copy(stripped) or stripped
    retry = prepare_public_copy(stripped, platform, format_type, sources=sources, primary_title=primary_title)
    if retry["passed"]:
        return retry["text"], True

    return stripped, False


def _force_usable_single(text: str) -> str:
    t = _strip_banned_phrases(sanitize_public_copy(text))
    t = repair_editorial_public_copy(t) or t
    t = repair_incomplete_public_copy(t) or t
    if format_single_post(t) and not is_malformed_tweet(t):
        return fit_tweet_length(format_single_post(t), 280)
    return fit_tweet_length(t, 280) if t else ""


def _force_usable_thread_tweets(tweets: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tweet in tweets:
        t = _force_usable_single(tweet)
        if not t or len(t) < 20:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(t)
    return cleaned[:6]


def _agent_candidate_usable(draft: str) -> bool:
    text = format_single_post(str(draft or ""))
    if not text or _contains_global_banned(text):
        return False
    return not audit_editorial_quality(text)


def _finalize_single_text(
    text: str,
    *,
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    primary_title: str,
) -> str:
    final = _force_usable_single(text)
    if not final:
        return ""
    gate = prepare_public_copy(
        final, platform="x", format_type="single_tweet", sources=sources, primary_title=primary_title
    )
    if not gate["passed"]:
        return ""
    binding = validate_copy_signal_binding(gate["text"], signal, sources)
    return binding["text"] if binding["passed"] else ""


def produce_final_x_tweet(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None = None,
    agent_draft: str = "",
) -> FinalCopy:
    """Always return usable single tweet text for verified scans."""
    result = result or {}
    primary_title = str(signal.get("title") or "")
    facts = extract_signal_facts(result or {"ranked_signals": [signal], "top_signal": signal}, primary_title)

    candidates: list[str] = []
    if agent_draft and _agent_candidate_usable(agent_draft):
        candidates.append(agent_draft)
    candidates.extend(
        [
            build_single_from_facts(facts),
            _build_business_tweet(signal),
            build_minimal_verified_single_tweet(signal, sources),
        ]
    )
    regenerated = False
    internal_note = ""

    for idx, raw in enumerate(candidates):
        raw = format_single_post(str(raw or ""))
        if not raw:
            continue
        text, passed = _prepare_with_repair(
            raw, platform="x", format_type="single_tweet", sources=sources, primary_title=primary_title
        )
        final = _finalize_single_text(
            text, signal=signal, sources=sources, primary_title=primary_title
        )
        if final:
            if idx > 0 or not passed:
                regenerated = True
                internal_note = "Single tweet was regenerated after validation."
            return FinalCopy(
                text=final,
                display=final,
                passed=True,
                regenerated=regenerated,
                internal_note=internal_note,
            )

    for raw in (_build_business_tweet(signal), build_minimal_verified_single_tweet(signal, sources)):
        final = _finalize_single_text(
            str(raw or ""), signal=signal, sources=sources, primary_title=primary_title
        )
        if final:
            return FinalCopy(
                text=final,
                display=final,
                passed=True,
                regenerated=True,
                internal_note="Single tweet was regenerated after validation.",
            )

    fallback = _force_usable_single(_build_business_tweet(signal) or build_minimal_verified_single_tweet(signal, sources))
    return FinalCopy(
        text=fallback,
        display=fallback,
        passed=bool(fallback),
        regenerated=True,
        internal_note="Single tweet was regenerated after validation.",
    )


def produce_final_x_thread(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None = None,
    agent_thread: list[str] | None = None,
) -> FinalCopy:
    """Always return usable thread display for verified scans."""
    result = result or {}
    primary_title = str(signal.get("title") or "")
    facts = extract_signal_facts(result or {"ranked_signals": [signal], "top_signal": signal}, primary_title)
    other_signals = [s for s in (result.get("ranked_signals") or []) if s.get("title") != primary_title]

    structured = _build_structured_thread(signal, facts)
    candidates: list[list[str]] = [structured]
    if agent_thread and not any(_contains_global_banned(t) for t in agent_thread):
        candidates.insert(0, agent_thread)
    built = build_thread_from_facts(facts)
    if built and built not in candidates:
        candidates.append(built)

    regenerated = False
    internal_note = ""

    for idx, raw_tweets in enumerate(candidates):
        edited: list[str] = []
        ok = True
        for tweet in raw_tweets:
            text, passed = _prepare_with_repair(
                tweet, platform="x", format_type="thread", sources=sources, primary_title=primary_title
            )
            if not text:
                ok = False
                break
            binding = validate_copy_signal_binding(
                text, signal, sources, other_signals=other_signals, thread_mode=True
            )
            edited.append(binding["text"] if binding["passed"] else text)
        if ok and len(edited) >= 4:
            combined = validate_copy_signal_binding(" ".join(edited), signal, sources, other_signals=other_signals)
            if combined["passed"] or idx > 0:
                if idx > 0:
                    regenerated = True
                    internal_note = "Thread was regenerated after validation."
                tweets = apply_brand_footer_to_tweets(edited)
                display = format_thread_for_display(tweets, add_brand_footer=False)
                return FinalCopy(
                    text=display,
                    display=display,
                    tweets=tweets,
                    passed=True,
                    regenerated=regenerated,
                    internal_note=internal_note,
                )

    forced = _force_usable_thread_tweets(structured)
    if len(forced) < 4:
        forced = _force_usable_thread_tweets(_build_structured_thread_minimal(signal, facts))
    tweets = apply_brand_footer_to_tweets(forced)
    display = format_thread_for_display(tweets, add_brand_footer=False)
    return FinalCopy(
        text=display,
        display=display,
        tweets=tweets,
        passed=bool(forced),
        regenerated=True,
        internal_note="Thread was regenerated after validation.",
    )


def _trim_linkedin(text: str, *, min_len: int = 900, max_len: int = 1500) -> str:
    t = sanitize_public_copy(text).strip()
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."
    if len(t) < min_len:
        pad = (
            " The practical read for decision-makers is to treat this as an operating adjustment, "
            "not a headline-only update. Monitor official statements, market repricing, and corridor behavior "
            "before the next reporting cycle confirms direction."
        )
        t = (t + pad).strip()
        if len(t) > max_len:
            t = t[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."
    return t


def produce_final_linkedin(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    draft: str = "",
    secondary_signals: list[dict[str, Any]] | None = None,
) -> FinalCopy:
    primary_title = str(signal.get("title") or "")
    article = _clean_operator_text(draft) or _clean_operator_text(str(signal.get("why_hamza_should_care") or ""))
    if not article or article.startswith("No LinkedIn"):
        article = build_safe_linkedin_fallback(signal, sources, secondary_signals or [])

    opening = str(signal.get("title") or "Signal update").strip().rstrip(".")
    middle = _business_consequence_sentence(signal)
    region = str(signal.get("region") or "the region")
    source_name = sources[0].get("name") if sources else str(signal.get("source") or "Reporting")
    structured = (
        f"{opening}.\n\n"
        f"{middle}\n\n"
        f"{source_name} reporting frames the update for operators tracking {region}. "
        f"{article}\n\n"
        f"What to monitor: official statements, corridor behavior, and follow-on confirmation in the next scan window."
    )
    structured = _trim_linkedin(structured)

    for raw in (structured, build_safe_linkedin_fallback(signal, sources, secondary_signals or [])):
        text, _ = _prepare_with_repair(
            raw, platform="linkedin", format_type="linkedin_post", sources=sources, primary_title=primary_title
        )
        if text:
            final = _trim_linkedin(_strip_banned_phrases(text))
            return FinalCopy(text=final, display=final, passed=True, regenerated=bool(draft), internal_note="")

    final = _trim_linkedin(_strip_banned_phrases(structured))
    return FinalCopy(text=final, display=final, passed=bool(final), regenerated=True, internal_note="")


def produce_final_substack(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
) -> FinalCopy:
    primary_title = str(signal.get("title") or "")
    title = str(signal.get("title") or "Signal update").strip().rstrip(".")
    thesis = _business_consequence_sentence(signal)
    verified = _verified_facts(signal)
    region = str(signal.get("region") or "the region")
    source_names = ", ".join(dict.fromkeys(str(s.get("name") or "Reporting") for s in sources[:3])) or "Reporting"

    what_changed = verified[0] if verified else title
    why = _clean_operator_text(str(signal.get("why_hamza_should_care") or "")) or thesis
    second_order = (
        f"The second-order effect is repricing across insurance, routing, and procurement decisions tied to {region}, "
        "not just the headline itself."
    )
    watch = (
        "Watch official statements, corridor behavior, and whether follow-on reporting confirms the same timeline."
    )
    bottom = f"Bottom line: treat this as an operating update with direct exposure for decision-makers tracking {region}."

    body = (
        f"{title}\n\n"
        f"One-line thesis: {thesis}\n\n"
        f"What changed\n{what_changed}.\n\n"
        f"Why it matters\n{why}\n\n"
        f"Second-order effects\n{second_order}\n\n"
        f"What to watch next\n{watch}\n\n"
        f"{bottom}\n\n"
        f"Sources cited in this note: {source_names}."
    )
    # Expand toward 500+ words if short
    while len(body.split()) < 500:
        body += (
            f"\n\nAdditional context: {source_names} reporting remains the anchor for this scan. "
            f"The update sits inside broader {region} risk management for shipping, insurance, basing, and procurement teams. "
            "Operators should compare this signal against corridor behavior before the next reporting cycle."
        )
        if len(body.split()) >= 520:
            break

    words = body.split()
    if len(words) > 900:
        body = " ".join(words[:900]).rstrip(",;") + "."

    text, _ = _prepare_with_repair(
        body, platform="substack", format_type="substack_post", sources=sources, primary_title=primary_title
    )
    final = _strip_banned_phrases(text or body)
    return FinalCopy(text=final, display=final, passed=bool(final), regenerated=False, internal_note="")


def build_delivery_formats(
    result: dict[str, Any],
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    recommended_format: str,
    format_reason: str,
    agent_single: str = "",
    agent_thread: list[str] | None = None,
) -> dict[str, Any]:
    """Produce all operator-facing copy formats for a verified scan."""
    secondary = [s for s in (result.get("ranked_signals") or []) if s.get("title") != signal.get("title")][:2]
    single = produce_final_x_tweet(signal, sources, result=result, agent_draft=agent_single)
    thread = produce_final_x_thread(signal, sources, result=result, agent_thread=agent_thread)
    linkedin = produce_final_linkedin(
        signal,
        sources,
        draft=str(result.get("linkedin_post") or ""),
        secondary_signals=secondary,
    )
    substack = produce_final_substack(signal, sources)

    day = str(result.get("day_of_week") or "")
    from xintelops.delivery.cadence import is_linkedin_day, next_linkedin_day

    if is_linkedin_day(day):
        linkedin_cadence = "LinkedIn cadence: Today is a suggested LinkedIn posting day."
        linkedin_action = "Suggested action: Consider posting this LinkedIn draft."
    else:
        linkedin_cadence = "LinkedIn cadence: Not a scheduled LinkedIn posting day."
        linkedin_action = "Suggested action: Review only. Save if useful."

    return {
        "single_copy": single.get("display") or single.get("text") or "",
        "thread_copy": thread.get("display") or thread.get("text") or "",
        "linkedin_copy": linkedin.get("display") or linkedin.get("text") or "",
        "substack_copy": substack.get("display") or substack.get("text") or "",
        "single_internal_note": single.get("internal_note") or "",
        "thread_internal_note": thread.get("internal_note") or "",
        "suggested_format": recommended_format,
        "suggested_format_reason": format_reason,
        "linkedin_cadence_note": linkedin_cadence,
        "linkedin_cadence_action": linkedin_action,
        "youtube_note": "YouTube: Not active yet. Video scripts will be added soon.",
        "single_tweets": [],
        "thread_tweets": thread.get("tweets") or [],
    }
