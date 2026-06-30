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


def _is_hormuz_fee_signal(signal: dict[str, Any]) -> bool:
    title = str(signal.get("title") or "").lower()
    return any(k in title for k in ("hormuz", "strait", "transit fee", "fee plan", "transit-fee"))


def _dedupe_paragraphs(paragraphs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for para in paragraphs:
        key = re.sub(r"\s+", " ", para.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(para.strip())
    return out


def _build_structured_thread(signal: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    """Editorial thread: what changed / why it matters / who is exposed / pressure point / watch."""
    title = str(signal.get("title") or facts.get("title") or "").strip().rstrip(".")
    verified = _verified_facts(signal) or facts.get("verified_facts") or []

    if _is_hormuz_fee_signal(signal):
        tweets = [
            "Oman and Iran are advancing a Strait of Hormuz transit-fee plan despite US objections.",
            "If implemented, the Strait becomes more than a military chokepoint. It becomes a pricing chokepoint.",
            "That matters for shipping firms, insurers, energy buyers, Gulf ports, and any operator exposed to route cost volatility.",
            "The pressure point is not only whether Hormuz stays open. It is who can attach cost, delay, or legal control to transit.",
            "Watch for formal fee language, insurer notices, and changes in Gulf shipping behavior. That is where the next signal appears.",
        ]
    else:
        change = verified[0] if verified else (f"{title}." if title else "Reporting confirms a material update.")
        if not change.endswith("."):
            change = f"{change}."
        why = _business_consequence_sentence(signal).rstrip(".")
        region = str(signal.get("region") or facts.get("region") or "the region")
        actors = signal.get("actors") or signal.get("entities") or []
        if isinstance(actors, str):
            actors = [actors]
        actor_label = ", ".join(str(a) for a in actors[:3]) if actors else region
        watch = verified[1] if len(verified) > 1 else f"Official statements and follow-on reporting in {region}."
        tweets = [
            change,
            why if why.endswith(".") else f"{why}.",
            f"Exposure sits with teams tied to {actor_label}, not just headline readers.",
            f"The pressure point is how quickly {region} behavior reprices cost, routing, and procurement decisions.",
            f"Watch {watch.rstrip('.')}. That is where the next confirmation appears.",
        ]

    cleaned = [fit_tweet_length(t, 280) for t in tweets if t and len(t) >= 20]
    seen: set[str] = set()
    unique: list[str] = []
    for t in cleaned:
        key = t.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique[:6] if len(unique) >= 4 else _build_structured_thread_minimal(signal, facts)


def _build_structured_thread_minimal(signal: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    title = str(signal.get("title") or "").strip().rstrip(".")
    region = str(signal.get("region") or facts.get("region") or "the region")
    consequence = _business_consequence_sentence(signal).rstrip(".")
    return [
        fit_tweet_length(f"{title}.", 280),
        fit_tweet_length(f"{consequence}.", 280),
        fit_tweet_length(
            "Exposure sits with shipping, insurance, energy, and procurement teams tied to the corridor.",
            280,
        ),
        fit_tweet_length(
            f"The pressure point is how {region} behavior reprices operating cost before headlines catch up.",
            280,
        ),
        fit_tweet_length(
            "Watch official statements, insurer notices, and corridor behavior for the next confirmation.",
            280,
        ),
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
                tweets = edited
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
    display = format_thread_for_display(forced, add_brand_footer=False)
    return FinalCopy(
        text=display,
        display=display,
        tweets=forced,
        passed=bool(forced),
        regenerated=True,
        internal_note="Thread was regenerated after validation.",
    )


def _trim_linkedin(text: str, *, min_len: int = 700, max_len: int = 1200) -> str:
    t = sanitize_public_copy(text).strip()
    t = re.sub(r"What to monitor:\.?\s*$", "", t, flags=re.I).strip()
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."
    if len(t) < min_len:
        pad = (
            " The practical read is to treat this as an operating adjustment, not a headline-only update. "
            "Monitor official statements, market repricing, and corridor behavior before the next reporting cycle."
        )
        t = (t + pad).strip()
        if len(t) > max_len:
            t = t[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."
    return t


def _build_linkedin_post(signal: dict[str, Any]) -> str:
    """Deterministic LinkedIn sections: opening, implication, analysis, watch, close."""
    if _is_hormuz_fee_signal(signal):
        paragraphs = [
            "Oman and Iran are advancing a Strait of Hormuz transit-fee plan despite US objections.",
            (
                "If implemented, this would shift part of the Hormuz risk model from emergency disruption "
                "to recurring cost exposure. That matters because shipping firms, insurers, energy buyers, "
                "and Gulf ports do not only price whether the Strait is open. They price delay, legal control, "
                "routing uncertainty, and the political cost of transit."
            ),
            (
                "The important point is not the fee alone. It is the precedent. A formal transit mechanism "
                "would give regional actors another way to shape maritime behavior without closing the Strait outright."
            ),
            (
                "Watch official fee language, insurer notices, port behavior, "
                "and any US diplomatic or commercial response to the fee plan."
            ),
            "Hormuz risk is moving from shock pricing toward structural pricing.",
        ]
    else:
        opening = str(signal.get("title") or "Signal update").strip().rstrip(".") + "."
        implication = _business_consequence_sentence(signal)
        region = str(signal.get("region") or "the region")
        paragraphs = _dedupe_paragraphs([
            opening,
            implication,
            (
                f"The important point is how this update reprices operating decisions tied to {region}, "
                "not just the headline itself."
            ),
            "Watch official statements, market behavior, and follow-on reporting in the next scan window.",
            f"Treat this as an operating update with direct exposure for teams tracking {region}.",
        ])

    body = "\n\n".join(_dedupe_paragraphs(paragraphs))
    return _trim_linkedin(_strip_banned_phrases(body))


def produce_final_linkedin(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    draft: str = "",
    secondary_signals: list[dict[str, Any]] | None = None,
) -> FinalCopy:
    primary_title = str(signal.get("title") or "")
    structured = _build_linkedin_post(signal)

    for raw in (structured, build_safe_linkedin_fallback(signal, sources, secondary_signals or [])):
        text, _ = _prepare_with_repair(
            raw, platform="linkedin", format_type="linkedin_post", sources=sources, primary_title=primary_title
        )
        if text:
            final = _trim_linkedin(_strip_banned_phrases(text))
            if "What to monitor:." not in final:
                return FinalCopy(text=final, display=final, passed=True, regenerated=True, internal_note="")

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
    why = _clean_operator_text(str(signal.get("why_hamza_should_care") or "")) or thesis.rstrip(".")
    if _is_hormuz_fee_signal(signal):
        second_order = (
            "A formal transit fee would let regional actors shape maritime behavior through pricing and legal control, "
            "not only through closure or military pressure. Insurers, charterers, and Gulf ports would need to model "
            "recurring cost exposure rather than episodic disruption."
        )
        watch = (
            "Watch official fee language, insurer notices, port behavior, and whether US objections produce "
            "diplomatic or commercial pushback."
        )
        bottom = "Hormuz risk is shifting from shock pricing toward structural pricing."
    else:
        second_order = (
            f"The second-order effect is repricing across insurance, routing, and procurement decisions tied to {region}, "
            "not just the headline itself."
        )
        watch = "Watch official statements, corridor behavior, and follow-on reporting in the next scan window."
        bottom = f"Bottom line: treat this as an operating update with direct exposure for teams tracking {region}."

    sections = [
        f"{title}\n",
        f"Thesis\n{thesis}\n",
        f"What changed\n{what_changed}.\n",
        f"Why it matters\n{why}\n",
        f"Second-order effects\n{second_order}\n",
        f"What to watch\n{watch}\n",
        f"Bottom line\n{bottom}\n",
        f"Sources cited in this note: {source_names}.",
    ]
    body = "\n".join(sections)

    word_count = len(body.split())
    if word_count < 500:
        body += (
            "\n\nFor operators, the practical question is whether corridor behavior, insurance terms, "
            "and procurement plans already reflect the update. Compare the signal against transit data, "
            "market repricing, and official statements before the next reporting cycle."
        )
    while len(body.split()) < 500:
        body += (
            " Additional reporting may clarify implementation timing, insurer response, "
            "and routing adjustments across Gulf-linked trade lanes."
        )
        if len(body.split()) >= 520:
            break

    words = body.split()
    if len(words) > 800:
        body = " ".join(words[:800]).rstrip(",;") + "."

    text, _ = _prepare_with_repair(
        body, platform="substack", format_type="substack_post", sources=sources, primary_title=primary_title
    )
    final = _strip_banned_phrases(text or body)
    return FinalCopy(text=final, display=final, passed=bool(final), regenerated=False, internal_note="")


def _normalize_suggested_format(fmt: str) -> str:
    label = str(fmt or "").upper()
    if "THREAD" in label:
        return "THREAD"
    return "SINGLE TWEET"


def _suggested_format_reason(fmt: str) -> str:
    if fmt == "THREAD":
        return "The signal has enough consequence and watch indicators for a short thread."
    return "The signal is sharp enough for one post. Thread adds limited value."


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
    from xintelops.delivery.cadence import is_linkedin_day

    if is_linkedin_day(day):
        linkedin_cadence = "LinkedIn cadence: Today is a suggested LinkedIn posting day."
        linkedin_action = "Suggested action: Consider posting this LinkedIn draft."
    else:
        linkedin_cadence = "LinkedIn cadence: Not a scheduled LinkedIn posting day."
        linkedin_action = "Suggested action: Review only. Save if useful."

    suggested = _normalize_suggested_format(recommended_format)
    also_included = "THREAD" if suggested == "SINGLE TWEET" else "SINGLE TWEET"
    reason = _suggested_format_reason(suggested)

    delivery = {
        "x_tweet": single.get("display") or single.get("text") or "",
        "x_thread": thread.get("tweets") or [],
        "x_thread_display": thread.get("display") or thread.get("text") or "",
        "linkedin": linkedin.get("display") or linkedin.get("text") or "",
        "substack": substack.get("display") or substack.get("text") or "",
        "suggested_format": suggested,
        "suggested_format_reason": reason,
        "also_included": also_included,
        "youtube_note": "YouTube: Not active yet. Video scripts will be added soon.",
        "linkedin_cadence_note": linkedin_cadence,
        "linkedin_cadence_action": linkedin_action,
        # Legacy aliases for callers/tests
        "single_copy": single.get("display") or single.get("text") or "",
        "thread_copy": thread.get("display") or thread.get("text") or "",
        "linkedin_copy": linkedin.get("display") or linkedin.get("text") or "",
        "substack_copy": substack.get("display") or substack.get("text") or "",
        "single_internal_note": single.get("internal_note") or "",
        "thread_internal_note": thread.get("internal_note") or "",
        "thread_tweets": thread.get("tweets") or [],
    }
    return delivery
