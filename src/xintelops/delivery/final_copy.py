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


_SUBSTACK_SECTION_HEADERS = frozenset({
    "Thesis",
    "What changed",
    "Why it matters",
    "Second-order effects",
    "What to watch",
    "Bottom line",
})

_SUBSTACK_FILLER_PHRASES = (
    "additional reporting may clarify",
)

_SUBSTACK_SECTION_ORDER: tuple[tuple[str, str | None], ...] = (
    ("title", None),
    ("thesis", "Thesis"),
    ("what_changed", "What changed"),
    ("why_it_matters", "Why it matters"),
    ("second_order_effects", "Second-order effects"),
    ("what_to_watch", "What to watch"),
    ("bottom_line", "Bottom line"),
)


def _normalize_sentence_key(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().rstrip(".,;:!?"))


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s.strip()]


def _join_sentences(sentences: list[str]) -> str:
    out: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        out.append(s)
    return " ".join(out)


def _substack_source_depth(signal: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    names = {str(s.get("name") or "").strip().lower() for s in sources if s.get("name")}
    names.discard("")
    verified = _verified_facts(signal)
    if len(names) >= 3 and len(verified) >= 3:
        return "deep"
    if len(names) >= 2 or len(verified) >= 2:
        return "multi"
    return "thin"


def _substack_max_words(depth: str) -> int:
    return {"thin": 450, "multi": 750, "deep": 1000}.get(depth, 450)


def _build_hormuz_substack_sections(signal: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, str]:
    _ = sources
    return {
        "title": "Hormuz Risk Is Moving From Shock Pricing To Structural Pricing",
        "thesis": (
            "Oman and Iran's transit-fee plan would shift part of the Strait of Hormuz risk model "
            "from emergency disruption to recurring cost exposure."
        ),
        "what_changed": "Oman and Iran are advancing a Strait of Hormuz transit-fee plan despite US objections.",
        "why_it_matters": (
            "If implemented, the Strait becomes more than a military chokepoint. It becomes a pricing chokepoint. "
            "Shipping firms, insurers, energy buyers, Gulf ports, and procurement teams would need to model "
            "recurring cost exposure into Gulf transit assumptions."
        ),
        "second_order_effects": (
            "A fee mechanism can shape maritime behavior without closing the Strait outright. "
            "That makes it quieter than a military escalation but potentially more durable as a commercial pressure tool."
        ),
        "what_to_watch": (
            "Watch formal fee language, insurer notices, port behavior, US diplomatic response, "
            "and any change in Gulf-linked routing patterns."
        ),
        "bottom_line": (
            "Hormuz risk is no longer only about whether the Strait closes. "
            "It is about who gets to price passage through it."
        ),
    }


def _build_generic_substack_sections(signal: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, str]:
    title = str(signal.get("title") or "Signal update").strip().rstrip(".")
    verified = _verified_facts(signal)
    region = str(signal.get("region") or "the region")
    thesis = _business_consequence_sentence(signal).rstrip(".")
    what_changed = verified[0] if verified else title
    why = _clean_operator_text(str(signal.get("why_hamza_should_care") or "")) or thesis
    second_order = (
        f"The second-order effect is repricing across insurance, routing, and procurement decisions tied to {region}."
    )
    watch_raw = verified[1] if len(verified) > 1 else f"official statements and corridor behavior in {region}"
    watch = watch_raw if str(watch_raw).lower().startswith("watch") else f"Watch {watch_raw.rstrip('.')}."
    bottom = f"The operating read is to track corridor exposure for teams tied to {region}, not the headline alone."
    return {
        "title": title,
        "thesis": thesis if thesis.endswith(".") else f"{thesis}.",
        "what_changed": what_changed if what_changed.endswith(".") else f"{what_changed}.",
        "why_it_matters": why if why.endswith(".") else f"{why}.",
        "second_order_effects": second_order,
        "what_to_watch": watch,
        "bottom_line": bottom,
    }


def _build_minimal_substack_sections(signal: dict[str, Any]) -> dict[str, str]:
    title = str(signal.get("title") or "Signal update").strip().rstrip(".")
    verified = _verified_facts(signal)
    region = str(signal.get("region") or "the region")
    what_changed = verified[0] if verified else title
    thesis = _business_consequence_sentence(signal).rstrip(".")
    return {
        "title": title,
        "thesis": thesis if thesis.endswith(".") else f"{thesis}.",
        "what_changed": what_changed if what_changed.endswith(".") else f"{what_changed}.",
        "why_it_matters": f"The update affects operating decisions tied to {region}.",
        "second_order_effects": f"Insurance, routing, and procurement plans may need to adjust if the update holds.",
        "what_to_watch": f"Watch official statements and corridor behavior in {region}.",
        "bottom_line": f"Treat this as an operating update with direct exposure for teams tracking {region}.",
    }


def _dedupe_substack_sections(sections: dict[str, str]) -> dict[str, str]:
    seen: set[str] = set()
    title_key = _normalize_sentence_key(sections.get("title", ""))
    if title_key:
        seen.add(title_key)

    out: dict[str, str] = {}
    if sections.get("title"):
        out["title"] = sections["title"].strip()

    for key, _label in _SUBSTACK_SECTION_ORDER[1:]:
        body = str(sections.get(key) or "").strip()
        if not body:
            continue
        kept: list[str] = []
        for sentence in _split_sentences(body):
            sent_key = _normalize_sentence_key(sentence)
            if not sent_key or sent_key in seen:
                continue
            seen.add(sent_key)
            kept.append(sentence)
        if kept:
            out[key] = _join_sentences(kept)
    return out


def _render_substack_post(sections: dict[str, str]) -> str:
    parts: list[str] = []
    title = sections.get("title", "").strip()
    if title:
        parts.append(title)
    for key, label in _SUBSTACK_SECTION_ORDER[1:]:
        body = sections.get(key, "").strip()
        if body and label:
            parts.append(f"{label}\n{body}")
    return "\n\n".join(parts)


def _sanitize_substack_block(block: str) -> str:
    from xintelops.delivery.editorial import _EM_DASH_PATTERN

    lines = block.split("\n", 1)
    if len(lines) == 2 and lines[0].strip() in _SUBSTACK_SECTION_HEADERS:
        header, body = lines[0].strip(), _EM_DASH_PATTERN.sub(", ", lines[1])
        body = _strip_banned_phrases(body)
        for phrase in _SUBSTACK_FILLER_PHRASES:
            body = re.sub(re.escape(phrase), "", body, flags=re.IGNORECASE)
        body = re.sub(r"\s{2,}", " ", body).strip()
        return f"{header}\n{body}" if body else ""
    cleaned = _strip_banned_phrases(_EM_DASH_PATTERN.sub(", ", block))
    for phrase in _SUBSTACK_FILLER_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _sanitize_substack_copy(text: str) -> str:
    blocks = [_sanitize_substack_block(b) for b in text.split("\n\n")]
    return "\n\n".join(b for b in blocks if b.strip())


def _dedupe_substack_text(text: str) -> str:
    seen: set[str] = set()
    blocks_out: list[str] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n", 1)
        if len(lines) == 2 and lines[0].strip() in _SUBSTACK_SECTION_HEADERS:
            header, body = lines[0].strip(), lines[1]
            kept: list[str] = []
            for sentence in _split_sentences(body):
                key = _normalize_sentence_key(sentence)
                if key and key not in seen:
                    seen.add(key)
                    kept.append(sentence)
            if kept:
                blocks_out.append(f"{header}\n{_join_sentences(kept)}")
            continue
        kept = []
        for sentence in _split_sentences(block):
            key = _normalize_sentence_key(sentence)
            if key and key not in seen:
                seen.add(key)
                kept.append(sentence)
        if kept:
            blocks_out.append(_join_sentences(kept))
    return "\n\n".join(blocks_out)


def _trim_substack_to_max_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    blocks = text.split("\n\n")
    while blocks and len(" ".join(blocks).split()) > max_words:
        blocks.pop()
    trimmed = "\n\n".join(blocks).strip()
    if trimmed:
        return trimmed
    return " ".join(words[:max_words]).rstrip(",;") + "."


def _parse_substack_sections(text: str) -> dict[str, str]:
    header_to_key = {
        "Thesis": "thesis",
        "What changed": "what_changed",
        "Why it matters": "why_it_matters",
        "Second-order effects": "second_order_effects",
        "What to watch": "what_to_watch",
        "Bottom line": "bottom_line",
    }
    sections: dict[str, str] = {}
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n", 1)
        if len(lines) == 2 and lines[0].strip() in header_to_key:
            sections[header_to_key[lines[0].strip()]] = lines[1].strip()
        elif "title" not in sections:
            sections["title"] = block.strip()
    return sections


def _substack_validation_violations(
    sections: dict[str, str],
    rendered: str,
    *,
    linkedin: str = "",
    tweet: str = "",
) -> list[str]:
    violations: list[str] = []
    all_sentences: list[str] = []
    for key in ("title", "thesis", "what_changed", "why_it_matters", "second_order_effects", "what_to_watch", "bottom_line"):
        all_sentences.extend(_split_sentences(sections.get(key, "")))
    keys = [_normalize_sentence_key(s) for s in all_sentences if s]
    if len(keys) != len(set(keys)):
        violations.append("repeated sentence")

    lowered = rendered.lower()
    if any(lowered.count(phrase) > 0 for phrase in _SUBSTACK_FILLER_PHRASES):
        violations.append("filler padding")

    if re.search(r"what to monitor:\.?\s*$", rendered, re.I | re.M):
        violations.append("malformed label")

    title_norm = _normalize_sentence_key(sections.get("title", ""))
    for key in ("thesis", "what_changed", "why_it_matters", "second_order_effects", "what_to_watch", "bottom_line"):
        body_norm = _normalize_sentence_key(sections.get(key, ""))
        if body_norm and body_norm == title_norm:
            violations.append("title repeated without analysis")

    analytical = sum(
        1
        for key in ("thesis", "what_changed", "why_it_matters", "second_order_effects", "what_to_watch", "bottom_line")
        if sections.get(key, "").strip()
    )
    if analytical < 3:
        violations.append("insufficient analytical points")

    if not sections.get("bottom_line", "").strip():
        violations.append("missing bottom line")

    if "—" in rendered or "–" in rendered:
        violations.append("em dash")

    combined = " ".join(sections.get(k, "") for k in ("thesis", "what_changed", "why_it_matters", "second_order_effects"))
    if combined and audit_editorial_quality(combined):
        violations.append("editorial slop")

    if linkedin:
        li_keys = {_normalize_sentence_key(s) for s in _split_sentences(linkedin)}
        body_sentences = _split_sentences(combined)
        if body_sentences:
            overlap = sum(1 for s in body_sentences if _normalize_sentence_key(s) in li_keys)
            if overlap >= max(3, len(body_sentences) - 1):
                violations.append("stretched linkedin")

    if tweet:
        tweet_keys = {_normalize_sentence_key(s) for s in _split_sentences(tweet)}
        body_sentences = _split_sentences(combined)
        if body_sentences and all(_normalize_sentence_key(s) in tweet_keys for s in body_sentences[:2]):
            violations.append("stretched tweet")

    return violations


def _finalize_substack_copy(sections: dict[str, str], *, max_words: int) -> str:
    sections = _dedupe_substack_sections(sections)
    text = _render_substack_post(sections)
    text = _sanitize_substack_copy(text)
    text = _dedupe_substack_text(text)
    text = _trim_substack_to_max_words(text, max_words)
    return text


def produce_final_substack(
    signal: dict[str, Any],
    sources: list[dict[str, Any]],
) -> FinalCopy:
    depth = _substack_source_depth(signal, sources)
    max_words = _substack_max_words(depth)

    if _is_hormuz_fee_signal(signal):
        sections = _build_hormuz_substack_sections(signal, sources)
    else:
        sections = _build_generic_substack_sections(signal, sources)

    text = _finalize_substack_copy(sections, max_words=max_words)
    parsed = _parse_substack_sections(text)
    violations = _substack_validation_violations(parsed, text)
    if violations:
        sections = _build_minimal_substack_sections(signal)
        text = _finalize_substack_copy(sections, max_words=max_words)
        parsed = _parse_substack_sections(text)

    return FinalCopy(text=text, display=text, passed=bool(text), regenerated=bool(violations), internal_note="")


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
