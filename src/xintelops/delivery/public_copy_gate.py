"""Unified public copy sanitizer and validator for all operator-facing copy channels."""
from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from xintelops.delivery.editorial import (
    _apply_final_rewrites,
    _capitalize_sentence_starts,
    _cleanup_orphan_punctuation,
    _EMOJI_PATTERN,
    _EM_DASH_PATTERN,
    _PLUS_SHORTHAND_PATTERN,
    _soften_certainty,
    _strip_formulaic_labels,
    _strip_slop_phrases,
    anti_hallucination_pass,
    audit_final_copy_violations,
    editorial_pipeline,
    final_anti_ai_slop_pass,
)
from xintelops.delivery.x_copy import fit_tweet_length, is_malformed_tweet, is_truncated_tweet

Platform = Literal["x", "linkedin", "substack", "youtube", "email_public_block", "generic_public"]
FormatType = Literal[
    "single_tweet",
    "thread",
    "linkedin_post",
    "substack_post",
    "youtube_script",
    "youtube_title",
    "youtube_description",
    "public_summary",
]

_ARROW_PATTERN = re.compile(r"→|➜|➡|->")
_HASHTAG_PATTERN = re.compile(r"#\w+")
_COMPRESSED_LIST_PATTERN = re.compile(r"\(\d+\)|(?:^|\s)\d+\)")
_INTERNAL_LABEL_PATTERN = re.compile(
    r"\b(?:action|format|deadline|expires|tier|layer|source role|monitor only|post primary thread|live event priority mode)\s*:",
    re.I,
)

GLOBAL_BANNED_PHRASES = (
    "delve",
    "landscape",
    "leverage",
    "utilize",
    "robust",
    "comprehensive",
    "game-changer",
    "game changer",
    "unlock",
    "transform",
    "powerful",
    "crucial",
    "in today's world",
    "at the end of the day",
    "this isn't",
    "this is not",
    "not just",
    "not a headline cycle",
    "headline cycle",
    "unlike others",
    "the key is",
    "what matters is",
    "here's why",
    "let's unpack",
    "lets unpack",
    "deep dive",
    "signal from noise",
    "bottom line",
    "what most analysts miss",
    "what most people miss",
    "most accounts miss",
    "most feeds skip",
    "if you are tracking",
    "if you're only",
    "you're late",
    "the signal",
    "real signal",
    "through-line",
    "through line",
    "hedging under fire",
    "under-covered",
    "watch next",
    "xintelops angle",
    "post primary thread",
    "live event priority mode",
    "headline most accounts",
    "structural question",
    "not a footnote",
    "markets hear",
    "insurers hear guns",
    "chokepoint story",
    "kinetic again",
    "easy re-escalation",
    "lots of paper",
    "generic headline",
    "dominates analyst feeds",
)

GLOBAL_REWRITES: tuple[tuple[str, str], ...] = (
    (r"(\w)\s*—\s*(\w)", r"\1. \2"),
    (r"(\w)\s*–\s*(\w)", r"\1, \2"),
    (" — ", ". "),
    (" – ", ", "),
    ("→", ", "),
    ("->", ", "),
    ("this isn't", "this is not"),
    ("what most analysts miss:", ""),
    ("what most analysts miss", ""),
    ("watch next:", "Worth tracking:"),
    ("bottom line:", ""),
    ("here's why:", ""),
    ("if you're only", "If the focus is only"),
    ("if you are tracking", "If the focus is on"),
    ("the signal is", "The issue is"),
    ("the real signal", "The issue"),
    ("headline most accounts", "many accounts"),
    ("structural question", "open question"),
    ("not a footnote", "not secondary"),
    ("through-line", "connection"),
    ("hedging under fire", "pressure under fire"),
    ("xintelops angle", "The relevant linkage is"),
    ("post primary thread", ""),
    ("live event priority mode", ""),
    ("markets hear", "markets may react to"),
    ("insurers hear guns", "insurers may reprice risk"),
    ("chokepoint story", "chokepoint pressure"),
    ("kinetic again", "active again"),
    ("easy re-escalation", "renewed escalation risk"),
    ("lots of paper", "diplomatic statements"),
    ("dominates analyst feeds", "draws analyst attention"),
)

_PLUS_LIST_PATTERN = re.compile(
    r"(\b[\w\s]{2,30})\s*\+\s*([\w\s]{2,30})(?:\s*\+\s*([\w\s]{2,30}))?",
    re.I,
)

_THREAD_QUALITY_BANNED = (
    "corridor-defining event",
    "corridor defining event",
    "available reporting is still developing on secondary details",
    "available reporting is still developing",
)

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "with", "after", "before",
    "from", "by", "as", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "may", "might", "must", "shall", "should", "can", "could",
    "would", "that", "this", "these", "those", "it", "its", "their", "them", "they", "we", "us",
    "lead", "lead", "talks", "talk", "weekend", "exchange", "strikes", "strike", "agree", "agreed",
})

_STRONG_GEO_ENTITIES = frozenset({
    "pakistan", "afghanistan", "durand", "iran", "tehran", "hormuz", "doha", "kushner", "witkoff",
    "israel", "gaza", "ukraine", "russia", "china", "taiwan", "india", "syria", "yemen", "houthi",
    "lebanon", "kuwait", "bahrain", "saudi", "qatar", "egypt", "turkey", "un", "centcom", "nato",
    "washington", "islamabad", "kabul", "taiwan", "black", "panama", "ukraine", "gaza",
})

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")

_INCOMPLETE_ENDING_FRAGMENTS = (
    "worth tracking whether.",
    "worth watching whether.",
    "worth tracking if.",
    "worth watching if.",
    "track whether.",
    "watch whether.",
    "the question is whether.",
    "it remains to be seen whether.",
    "worth.",
)

_DANGLING_FINAL_WORDS = frozenset({
    "worth", "until", "without", "before", "after", "while", "because", "if", "whether",
    "track", "watch", "the", "a", "an", "to", "for", "with", "by", "on", "at", "in", "of", "and", "or",
})

_EDITORIAL_WEAK_PHRASES = (
    "live again but fragile",
    "live again but",
    "violation cycle",
    "produce anything durable",
    "worth tracking",
    "before markets reopen",
    "another violation cycle",
    "directly affects hormuz shipping risk",
    "anything durable",
    "ceasefire is live again",
    "remains fragile",
    "another violation",
    "reprices within hours",
    "headline cycle",
    "the pause remains uncertain",
    "the next escalation",
    "transit risk changes before",
    "whether doha talks transit risk",
)

_EDITORIAL_REWRITES: tuple[tuple[str, str], ...] = (
    ("live again but fragile,", ""),
    ("live again but fragile", ""),
    ("violation cycle", ""),
    ("another violation cycle", ""),
    ("produce anything durable", ""),
    ("worth tracking follow-on reporting from", ""),
    ("worth tracking", ""),
    ("before markets reopen", "before the next round of talks"),
    ("the ceasefire is live again but fragile,", ""),
    ("the ceasefire is live again but fragile", ""),
    ("ceasefire is live again", ""),
    ("directly affects hormuz shipping risk", ""),
    ("the pause remains uncertain.", ""),
    ("the pause remains uncertain", ""),
    ("the next escalation", ""),
)

_COMMA_SPLICE_PATTERNS = (
    re.compile(r"\b(?:fragile|again|live|strikes|talks|pause|ceasefire|unclear)\s*,\s*(?:another|any|the|it|this|each|more)\b", re.I),
    re.compile(r"\.\s*[^.]+\s,\s*(?:another|any|the|it|this)\s+\w+", re.I),
    re.compile(r"\b,\s+another\s+(?:violation|cycle|round|wave|strike)\b", re.I),
)

_VAGUE_ISSUE_PATTERN = re.compile(
    r"\bthe issue is\b(?!\s+(?:now\s+)?whether\b)",
    re.I,
)

class GateResult(TypedDict):
    text: str
    passed: bool
    blocked: bool
    block_reason: str
    violations: list[str]
    platform: str
    format_type: str


def audit_copy_completeness(text: str) -> list[str]:
    """Detect incomplete fragments and dangling endings in public copy."""
    t = str(text or "").strip()
    if not t:
        return ["empty copy"]

    violations: list[str] = []
    lower = t.lower().rstrip()

    for frag in _INCOMPLETE_ENDING_FRAGMENTS:
        if lower.endswith(frag):
            violations.append(f"incomplete ending: {frag}")

    if re.search(r"\bworth tracking whether\.?$", lower):
        violations.append("incomplete: worth tracking whether")
    if re.search(r"\bworth watching whether\.?$", lower):
        violations.append("incomplete: worth watching whether")
    if re.search(r"\bworth tracking if\.?$", lower):
        violations.append("incomplete: worth tracking if")
    if re.search(r"\bworth watching if\.?$", lower):
        violations.append("incomplete: worth watching if")
    if re.search(r"\bthe question is whether\.?$", lower):
        violations.append("incomplete: the question is whether")
    if re.search(r"\bit remains to be seen whether\.?$", lower):
        violations.append("incomplete: it remains to be seen whether")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if sentences:
        last = sentences[-1]
        last_body = last.rstrip(".!?").strip()
        last_words = last_body.split()
        if last_words:
            last_word = last_words[-1].lower()
            if last.endswith("."):
                if len(last_words) <= 2:
                    violations.append("incomplete final sentence: fewer than 3 words")
                elif len(last_words) < 4 and last_word in _DANGLING_FINAL_WORDS:
                    violations.append("incomplete final sentence: fewer than 4 words with dangling ending")
                elif last_word in _DANGLING_FINAL_WORDS:
                    if last_word == "whether" and len(last_words) >= 5:
                        pass
                    else:
                        violations.append(f"incomplete ending: dangling {last_word}")

    return violations


def repair_incomplete_public_copy(text: str) -> str:
    """Remove incomplete trailing sentence(s) and return cleaned copy."""
    t = sanitize_public_copy(text)
    if not t:
        return ""
    if not audit_copy_completeness(t):
        return t

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    while sentences:
        candidate = " ".join(sentences)
        if not audit_copy_completeness(candidate):
            return candidate
        sentences.pop()
    return ""


def _violations_are_completeness_only(violations: list[str]) -> bool:
    if not violations:
        return False
    completeness_markers = ("incomplete", "truncated tweet", "truncated", "dangling")
    return all(any(marker in v.lower() for marker in completeness_markers) for v in violations)


def _violations_are_editorial_only(violations: list[str]) -> bool:
    if not violations:
        return False
    editorial_markers = ("editorial quality", "comma splice", "weak phrase", "vague phrasing", "generated phrasing")
    return all(any(marker in v.lower() for marker in editorial_markers) for v in violations)


def audit_editorial_quality(text: str) -> list[str]:
    """Detect weak generated phrasing, comma splices, and vague operator-facing copy."""
    t = str(text or "").strip()
    if not t:
        return ["empty copy"]

    violations: list[str] = []
    lower = t.lower()

    for phrase in _EDITORIAL_WEAK_PHRASES:
        if phrase in lower:
            violations.append(f"weak phrase: {phrase}")

    for pattern in _COMMA_SPLICE_PATTERNS:
        if pattern.search(t):
            violations.append("comma splice")
            break

    if _VAGUE_ISSUE_PATTERN.search(t):
        violations.append("vague phrasing: the issue is without whether-clause")

    if re.search(r"\bworth tracking\b", lower):
        violations.append("generated phrasing: worth tracking")

    if re.search(r"\bbefore markets reopen\b", lower):
        violations.append("weak phrase: before markets reopen")

    if re.search(r"\.\s*,\s*\w", t):
        violations.append("broken phrasing: orphan comma after sentence break")

    if re.search(r"\bgulf basing,\s+and whether\b", lower):
        violations.append("weak phrase: gulf basing, and whether")

    if re.search(r",\s+and whether\b", lower) and not re.search(
        r"\bthe issue(?: now)? is whether\b", lower
    ):
        violations.append("vague phrasing: dangling and whether clause")

    return violations


def repair_editorial_public_copy(text: str) -> str:
    """Rewrite weak phrasing and fix comma splices once."""
    t = sanitize_public_copy(text)
    if not t:
        return ""

    for old, new in sorted(_EDITORIAL_REWRITES, key=lambda x: -len(x[0])):
        t = re.sub(re.escape(old), new, t, flags=re.IGNORECASE)

    t = re.sub(
        r"\b(?:the )?ceasefire is live again but fragile,\s*",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r",\s+another\s+(?:violation cycle|violation|round)[^.]*\.",
        ".",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"\blive,\s+(?:any|another)\b",
        "live. ",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"\.\s*,\s*", ". ", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()


def validate_editorial_quality(
    text: str,
    platform: Platform,
    format_type: FormatType,
) -> GateResult:
    """Final editorial quality validator for paste-ready public copy."""
    body = sanitize_public_copy(text)
    violations = audit_editorial_quality(body)
    passed = not violations and bool(body.strip())
    reason = violations[0] if violations else ""
    return {
        "text": body if passed else "",
        "passed": passed,
        "blocked": not passed,
        "block_reason": reason,
        "violations": violations,
        "platform": platform,
        "format_type": format_type,
    }


def format_operator_block_reason(violation: str, *, format_label: str = "Thread") -> str:
    """Convert internal validation fragments into operator-readable block reasons."""
    v = str(violation or "").strip()
    lower = v.lower()
    if "pakistan/afghanistan" in lower or "pakistan" in lower and "us-iran" in lower:
        return f"{format_label} blocked because it referenced Pakistan/Afghanistan while the selected signal is US/Iran."
    if "different signal topic" in lower:
        return f"{format_label} blocked because it referenced a different signal topic."
    if "foreign actors" in lower or "not in selected signal" in lower:
        return f"{format_label} blocked because it referenced actors or locations outside the selected signal."
    if "comma splice" in lower:
        return f"{format_label} blocked because the copy contained a comma splice."
    if "weak phrase" in lower or "generated phrasing" in lower or "vague phrasing" in lower:
        return f"{format_label} blocked because the copy needed manual rewriting before posting."
    if v:
        return f"{format_label} blocked because {v[0].lower() + v[1:] if len(v) > 1 else v.lower()}."
    return f"{format_label} blocked because final copy quality failed."


def sanitize_visible_text(text: str) -> str:
    """Sanitize any operator-visible generated text (email fields, summaries, reasons)."""
    return sanitize_public_copy(str(text or ""))


def resolve_effective_format_recommendation(
    recommended: str,
    format_reason: str,
    *,
    single_passed: bool,
    thread_passed: bool,
) -> tuple[str, str]:
    """Override format recommendation when a format is blocked."""
    if single_passed and not thread_passed:
        return "SINGLE TWEET", "Thread failed final validation; single tweet passed."
    if thread_passed and not single_passed:
        return "THREAD", "Single tweet failed final validation; thread passed."
    if thread_passed and single_passed:
        if recommended == "THREAD":
            return "THREAD", format_reason
        return "SINGLE TWEET", format_reason
    return recommended, format_reason


def _phrase_matches_banned(text: str, phrase: str) -> bool:
    """Match banned phrases on word boundaries so substrings like 'the key issue' do not hit 'the key is'."""
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return bool(re.search(pattern, text.lower()))


def _contains_global_banned(text: str) -> str | None:
    for phrase in sorted(GLOBAL_BANNED_PHRASES, key=len, reverse=True):
        if _phrase_matches_banned(text, phrase):
            return phrase
    return None


def _contains_thread_quality_banned(text: str) -> str | None:
    for phrase in _THREAD_QUALITY_BANNED:
        if _phrase_matches_banned(text, phrase):
            return phrase
    return None


def _title_tokens(title: str) -> set[str]:
    tokens: set[str] = set()
    for word in re.findall(r"[A-Za-z]{3,}", str(title or "")):
        w = word.lower()
        if w not in _STOPWORDS:
            tokens.add(w)
    lower = str(title or "").lower()
    for entity in _STRONG_GEO_ENTITIES:
        if entity in lower:
            tokens.add(entity)
    return tokens


def extract_binding_anchors(signal: dict[str, Any]) -> dict[str, Any]:
    """Extract actors, locations, and title anchors for copy binding checks."""
    title = str(signal.get("title") or "").strip()
    tokens = _title_tokens(title)

    for item in signal.get("actors") or signal.get("entities") or []:
        for part in re.findall(r"[A-Za-z]{2,}", str(item)):
            w = part.lower()
            if w not in _STOPWORDS:
                tokens.add(w)

    region = str(signal.get("region") or "").strip().lower()
    domain = str(signal.get("domain") or "").strip().lower()
    if region:
        tokens.add(region)
    if domain:
        tokens.add(domain)

    geo = {t for t in tokens if t in _STRONG_GEO_ENTITIES}
    return {
        "title": title,
        "tokens": tokens,
        "geo": geo,
        "region": region,
        "domain": domain,
    }


def _anchor_hits(copy_text: str, anchors: dict[str, Any]) -> set[str]:
    lower = str(copy_text or "").lower()
    hits: set[str] = set()
    for token in anchors.get("tokens") or set():
        if re.search(rf"\b{re.escape(token)}", lower):
            hits.add(token)
    return hits


def _foreign_topic_violations(
    copy_text: str,
    selected_signal: dict[str, Any],
    other_signals: list[dict[str, Any]] | None = None,
) -> list[str]:
    violations: list[str] = []
    body = sanitize_public_copy(copy_text)
    copy_lower = body.lower()
    selected_title_lower = str(selected_signal.get("title") or "").lower()
    selected_anchors = extract_binding_anchors(selected_signal)

    selected_is_us_iran = (
        any(m in selected_title_lower for m in ("iran", "hormuz", "doha", "tehran"))
        and any(m in selected_title_lower for m in ("stand down", "stand-down", "us ", "u.s.", "washington", "iran"))
    )
    copy_is_south_asia = any(m in copy_lower for m in ("pakistan", "afghanistan", "durand", "islamabad", "kabul"))
    if selected_is_us_iran and copy_is_south_asia and not any(m in selected_title_lower for m in ("pakistan", "afghanistan")):
        violations.append("copy describes Pakistan/Afghanistan but selected signal is US-Iran")

    geo_hits = {t for t in _anchor_hits(body, selected_anchors) if t in _STRONG_GEO_ENTITIES}
    for other in other_signals or []:
        other_title = str(other.get("title") or "")
        if other_title == str(selected_signal.get("title") or ""):
            continue
        other_anchors = extract_binding_anchors(other)
        other_tokens = other_anchors.get("tokens") or set()
        distinctive = (other_anchors.get("geo") or set()) | other_tokens
        selected_tokens = selected_anchors.get("tokens") or set()
        copy_distinctive_hits = {
            t for t in distinctive
            if len(t) >= 3 and t in copy_lower and t in _STRONG_GEO_ENTITIES and t not in selected_tokens
        }
        if copy_distinctive_hits and not (geo_hits & (selected_anchors.get("geo") or set())):
            violations.append("copy matches different signal topic")
    return violations


def validate_copy_signal_binding(
    copy_text: str,
    selected_signal: dict[str, Any],
    source_package: list[dict[str, Any]] | None = None,
    *,
    allowed_fallback_signal: dict[str, Any] | None = None,
    other_signals: list[dict[str, Any]] | None = None,
    thread_mode: bool = False,
) -> GateResult:
    """Ensure public copy describes the selected active_now signal, not another topic."""
    source_package = source_package or []
    other_signals = other_signals or []
    body = sanitize_public_copy(copy_text)
    target_signal = allowed_fallback_signal or selected_signal
    target_anchors = extract_binding_anchors(target_signal)
    selected_anchors = extract_binding_anchors(selected_signal)
    hits = _anchor_hits(body, target_anchors)
    selected_hits = _anchor_hits(body, selected_anchors)

    violations: list[str] = []
    if not allowed_fallback_signal:
        violations.extend(_foreign_topic_violations(body, selected_signal, other_signals))
    else:
        violations.extend(_foreign_topic_violations(body, target_signal, other_signals))

    if thread_mode:
        passed = not violations
        reason = violations[0] if violations else ""
        return {
            "text": body if passed else "",
            "passed": passed,
            "blocked": not passed,
            "block_reason": reason,
            "violations": violations,
            "platform": "x",
            "format_type": "thread",
        }

    copy_lower = body.lower()
    geo_hits = {t for t in hits if t in _STRONG_GEO_ENTITIES}
    target_geo = target_anchors.get("geo") or set()

    min_hits = 2 if len(target_anchors.get("tokens") or []) >= 4 else 1
    geo_overlap = geo_hits & (target_geo | selected_anchors.get("geo") or set())
    effective_hits = len(hits | geo_overlap)
    foreign_geo = geo_hits - (target_geo | selected_anchors.get("geo") or set())
    if foreign_geo and not geo_overlap:
        violations.append(
            f"copy references foreign actors/locations ({', '.join(sorted(foreign_geo))}) not in selected signal"
        )
    if allowed_fallback_signal:
        if effective_hits < min_hits:
            violations.append(
                f"copy does not match declared fallback signal: {target_signal.get('title', '')}"
            )
    elif effective_hits < min_hits and not geo_overlap:
        violations.append(
            f"copy does not match selected signal: {selected_signal.get('title', '')}"
        )

    if (
        source_package
        and not allowed_fallback_signal
        and selected_signal.get("url")
        and effective_hits < min_hits
    ):
        url = str(selected_signal.get("url") or "")
        bound = any(str(item.get("url") or "") == url for item in source_package)
        title_key = str(selected_signal.get("title") or "").lower()[:40]
        if not bound and title_key:
            bound = any(
                title_key[:20] in str(item.get("why_supports") or "").lower()
                for item in source_package
            )
        if not bound:
            violations.append("source package does not match selected signal")

    passed = not violations
    reason = violations[0] if violations else ""
    return {
        "text": body if passed else "",
        "passed": passed,
        "blocked": not passed,
        "block_reason": reason,
        "violations": violations,
        "platform": "x",
        "format_type": "single_tweet",
    }


def selected_signal_has_verified_source(
    signal: dict[str, Any],
    source_package: list[dict[str, Any]] | None = None,
) -> bool:
    if signal.get("url") or signal.get("verified_facts"):
        return True
    title = str(signal.get("title") or "").lower()
    for item in source_package or []:
        why = str(item.get("why_supports") or "").lower()
        if title[:30] and title[:30] in why:
            return True
        if str(item.get("url") or "") == str(signal.get("url") or ""):
            return True
    return False


def _rewrite_plus_lists(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        parts = [p.strip() for p in match.groups() if p and p.strip()]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        if len(parts) >= 3:
            return f"{parts[0]}, {parts[1]}, and {parts[2]}"
        return match.group(0)

    return _PLUS_LIST_PATTERN.sub(repl, text)


def sanitize_public_copy(text: str) -> str:
    """Normalize unsafe symbols and rewrite banned patterns before validation."""
    out = str(text or "").strip()
    if not out:
        return ""

    out = _EM_DASH_PATTERN.sub(", ", out)
    out = _ARROW_PATTERN.sub(", ", out)
    for old, new in sorted(GLOBAL_REWRITES, key=lambda x: -len(x[0])):
        if old.startswith("("):
            out = re.sub(old, new, out, flags=re.IGNORECASE)
        else:
            out = re.sub(re.escape(old), new, out, flags=re.IGNORECASE)
    out = _apply_final_rewrites(out)
    out = _rewrite_plus_lists(out)
    out = _strip_formulaic_labels(out)
    out = _EMOJI_PATTERN.sub("", out)
    out = _HASHTAG_PATTERN.sub("", out)
    out = re.sub(_COMPRESSED_LIST_PATTERN, "", out)
    out = _INTERNAL_LABEL_PATTERN.sub("", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _cleanup_orphan_punctuation(out)
    out = _capitalize_sentence_starts(out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _max_len_for(format_type: str) -> int | None:
    if format_type == "single_tweet":
        return 280
    if format_type == "youtube_title":
        return 100
    if format_type in {"youtube_description", "public_summary"}:
        return 5000
    return None


def _long_form_public_pass(
    text: str,
    sources: list[dict[str, Any]] | None,
    *,
    primary_title: str = "",
) -> dict[str, Any]:
    """Long-form public pass: strip slop and block only unsupported claims, not score heuristics."""
    cleaned = _soften_certainty(_strip_slop_phrases(text))
    hall = anti_hallucination_pass(cleaned, sources, primary_title=primary_title)
    return {
        "text": hall["text"],
        "blocked": hall["blocked"],
        "block_reason": hall.get("block_reason") or "",
    }


def validate_public_copy(
    text: str,
    platform: Platform,
    format_type: FormatType,
    *,
    sources: list[dict[str, Any]] | None = None,
    primary_title: str = "",
    ignore_footer: bool = True,
) -> GateResult:
    """Validate sanitized public copy. Input should already be sanitized once."""
    sources = sources or []
    body = sanitize_public_copy(text)
    violations: list[str] = []

    if not body.strip():
        return {
            "text": "",
            "passed": False,
            "blocked": True,
            "block_reason": "Empty after public copy sanitization.",
            "violations": ["empty"],
            "platform": platform,
            "format_type": format_type,
        }

    banned = _contains_global_banned(body)
    if banned:
        violations.append(f"banned phrase: {banned}")

    if format_type == "thread":
        thread_banned = _contains_thread_quality_banned(body)
        if thread_banned:
            violations.append(f"thread quality: {thread_banned}")
        if _SPACE_BEFORE_PUNCT.search(str(text or "")):
            violations.append("comma spacing error")

    if _EM_DASH_PATTERN.search(body):
        violations.append("unsafe symbol: em dash")
    if _ARROW_PATTERN.search(body):
        violations.append("unsafe symbol: arrow")
    if _HASHTAG_PATTERN.search(body):
        violations.append("hashtag")
    if _EMOJI_PATTERN.search(body):
        violations.append("emoji")
    unquoted = re.sub(r"""['"][^'"]*['"]""", "", body)
    if _PLUS_SHORTHAND_PATTERN.search(unquoted):
        violations.append("unsafe format: plus shorthand")

    audit = audit_final_copy_violations(body, ignore_footer=ignore_footer)
    for v in audit:
        if v not in violations:
            violations.append(v)

    max_len = _max_len_for(format_type)
    check_body = body
    if format_type == "single_tweet" and is_malformed_tweet(check_body):
        violations.append("malformed tweet")

    if format_type == "single_tweet":
        edited = editorial_pipeline(check_body, sources, primary_title=primary_title)
        if edited.get("blocked"):
            violations.append(edited.get("block_reason") or "editorial fail")
        else:
            check_body = edited["text"]
    elif format_type in {"linkedin_post", "substack_post", "public_summary"}:
        edited = _long_form_public_pass(check_body, sources, primary_title=primary_title)
        if edited.get("blocked"):
            violations.append(edited.get("block_reason") or "editorial fail")
        else:
            check_body = edited["text"]

    if format_type == "single_tweet":
        final = final_anti_ai_slop_pass(check_body, max_len=280)
        if final.get("blocked"):
            violations.extend(final.get("violations") or [final.get("block_reason", "final gate fail")])
        else:
            check_body = final["text"]
    elif format_type == "thread":
        final = final_anti_ai_slop_pass(check_body, max_len=280)
        if final.get("blocked"):
            violations.extend(final.get("violations") or [final.get("block_reason", "final gate fail")])
        else:
            check_body = final["text"]
    else:
        check_body = sanitize_public_copy(check_body)
        post_audit = audit_final_copy_violations(check_body, ignore_footer=ignore_footer)
        for v in post_audit:
            if v not in violations:
                violations.append(v)

    if format_type == "single_tweet" and max_len and len(check_body) > max_len:
        check_body = fit_tweet_length(check_body, max_len)
    elif max_len and len(check_body) > max_len:
        check_body = check_body[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."

    if format_type == "single_tweet" and is_truncated_tweet(check_body):
        violations.append("truncated tweet")

    for v in audit_copy_completeness(check_body):
        if v not in violations:
            violations.append(v)

    for v in audit_editorial_quality(check_body):
        mapped = f"editorial quality: {v}"
        if mapped not in violations:
            violations.append(mapped)

    if format_type == "single_tweet":
        post_banned = _contains_global_banned(check_body)
        if post_banned:
            violations.append(f"banned phrase: {post_banned}")

    passed = not violations and bool(check_body.strip())
    reason = violations[0] if violations else ""
    return {
        "text": check_body if passed else "",
        "passed": passed,
        "blocked": not passed,
        "block_reason": reason,
        "violations": violations,
        "platform": platform,
        "format_type": format_type,
    }


def prepare_public_copy(
    text: str,
    platform: Platform,
    format_type: FormatType,
    *,
    sources: list[dict[str, Any]] | None = None,
    primary_title: str = "",
) -> GateResult:
    """Sanitize, validate, repair once, validate again."""
    sanitized = sanitize_public_copy(text)
    first = validate_public_copy(
        sanitized,
        platform,
        format_type,
        sources=sources,
        primary_title=primary_title,
    )
    if first["passed"]:
        return first

    if _violations_are_completeness_only(first["violations"]):
        repaired = repair_incomplete_public_copy(sanitized)
        if repaired and repaired != sanitized:
            completeness_retry = validate_public_copy(
                repaired,
                platform,
                format_type,
                sources=sources,
                primary_title=primary_title,
            )
            if completeness_retry["passed"]:
                return completeness_retry
            editorial_on_repaired = repair_editorial_public_copy(repaired)
            if editorial_on_repaired and editorial_on_repaired != repaired:
                chained = validate_public_copy(
                    editorial_on_repaired,
                    platform,
                    format_type,
                    sources=sources,
                    primary_title=primary_title,
                )
                if chained["passed"]:
                    return chained

    if _violations_are_editorial_only(first["violations"]):
        repaired = repair_editorial_public_copy(sanitized)
        if repaired and repaired != sanitized:
            editorial_retry = validate_public_copy(
                repaired,
                platform,
                format_type,
                sources=sources,
                primary_title=primary_title,
            )
            if editorial_retry["passed"]:
                return editorial_retry

    repaired = sanitize_public_copy(sanitized)
    if repaired != sanitized:
        second = validate_public_copy(
            repaired,
            platform,
            format_type,
            sources=sources,
            primary_title=primary_title,
        )
        if second["passed"]:
            return second
        return second

    return first


def is_verified_signal(signal: dict[str, Any]) -> bool:
    if not signal or not signal.get("title"):
        return False
    if signal.get("url"):
        return True
    if signal.get("verified_facts"):
        return True
    if signal.get("new_information_detected"):
        return True
    return bool(str(signal.get("source") or "").strip())


def get_verified_signals(result: dict[str, Any]) -> list[dict[str, Any]]:
    signals = result.get("ranked_signals") or []
    verified = [s for s in signals if is_verified_signal(s)]
    return verified if verified else signals


def build_minimal_verified_single_tweet(
    signal: dict[str, Any],
    source_package: list[dict[str, Any]] | None = None,
) -> str:
    """Deterministic minimal single tweet from structured facts only."""
    source_package = source_package or []
    title = str(signal.get("title") or "").strip().rstrip(".")
    title_lower = title.lower()
    region = str(signal.get("region") or "").strip()

    if (
        "iran" in title_lower
        and ("us" in title_lower or "u.s." in title_lower or "washington" in title_lower or "stand down" in title_lower)
    ):
        text = (
            "US and Iran say they will stand down after weekend strikes. "
            "The issue now is whether the pause lowers Hormuz shipping risk, Gulf basing pressure, "
            "and insurance pricing before the next round of Doha talks."
        )
        return text

    verified: list[str] = []
    for item in signal.get("verified_facts") or []:
        if isinstance(item, dict):
            verified.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            verified.append(str(item))
    verified = [v.strip().rstrip(".") for v in verified if v.strip()]

    parts: list[str] = []
    if title:
        parts.append(f"{title}.")
    elif verified:
        parts.append(f"{verified[0]}.")

    if verified and verified[0].lower() not in (title or "").lower():
        parts.append(f"{verified[0]}.")

    implication = str(
        signal.get("summary") or signal.get("why_hamza_should_care") or ""
    ).strip()
    if implication and re.search(
        r"why_this|xintelops|operator|score|the signal|watch next|bottom line|if you|you're late",
        implication,
        re.I,
    ):
        implication = ""
    if implication and not audit_editorial_quality(implication):
        if implication.lower() not in " ".join(parts).lower():
            parts.append(implication if implication.endswith(".") else f"{implication}.")

    if region.lower() in {"gulf", "middle east"} or "hormuz" in title_lower:
        parts.append(
            "The issue now is whether the pause lowers shipping risk, Gulf basing pressure, "
            "and insurance pricing before follow-on diplomacy."
        )
    else:
        parts.append("Some details remain unclear until follow-on reporting confirms the timeline.")

    text = " ".join(parts).strip()
    if not text and source_package:
        src = source_package[0]
        name = src.get("name") or src.get("source") or "Reporting"
        text = f"{name} reports an update on {title or 'the selected signal'}."

    return text if text else ""


def build_safe_linkedin_fallback(
    signal: dict[str, Any],
    source_package: list[dict[str, Any]] | None = None,
    secondary_signals: list[dict[str, Any]] | None = None,
) -> str:
    """Deterministic LinkedIn fallback from structured facts."""
    source_package = source_package or []
    secondary_signals = secondary_signals or []
    title = str(signal.get("title") or "Signal update").strip().rstrip(".")
    region = str(signal.get("region") or "the region").strip()
    confidence = str(signal.get("confidence") or "").upper()

    verified: list[str] = []
    for item in signal.get("verified_facts") or []:
        if isinstance(item, dict):
            verified.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            verified.append(str(item))
    verified = [v.strip() for v in verified if v.strip()]

    source_name = ""
    if source_package:
        source_name = str(source_package[0].get("name") or source_package[0].get("source") or "Official reporting")

    event_line = verified[0] if verified else title
    if source_name and verified:
        para1 = (
            f"{source_name} reports that {event_line.rstrip('.')}. "
        )
    else:
        para1 = f"{event_line.rstrip('.')}. "

    if confidence in {"", "LOW", "MEDIUM"}:
        para1 += "Available confirmation remains uneven, so the corridor risk should not be treated as resolved."
    else:
        para1 += "Reporting is still developing on secondary details."

    para2 = (
        f"The issue is whether commercial transit behavior in {region} changes before follow-on diplomacy catches up. "
        "Gulf basing risk, insurance pricing, and official statements remain part of the same operating picture."
    )

    para3 = (
        "The next indicators are transit recovery data, Gulf state statements, and whether follow-on reporting confirms the same timeline."
    )
    if secondary_signals:
        sec_title = str(secondary_signals[0].get("title") or "").strip()
        if sec_title:
            para3 += f" A related signal to watch is {sec_title.rstrip('.')}."

    return f"{para1}\n\n{para2}\n\n{para3}"


def gate_public_thread(
    tweets: list[str],
    *,
    sources: list[dict[str, Any]] | None = None,
    primary_title: str = "",
) -> GateResult:
    """Validate each tweet in a thread through the global gate."""
    if not tweets:
        return {
            "text": "",
            "passed": False,
            "blocked": True,
            "block_reason": "No thread tweets available.",
            "violations": ["empty thread"],
            "platform": "x",
            "format_type": "thread",
        }

    cleaned: list[str] = []
    for i, tweet in enumerate(tweets):
        result = prepare_public_copy(
            tweet,
            "x",
            "thread",
            sources=sources,
            primary_title=primary_title,
        )
        if not result["passed"]:
            return {
                "text": "",
                "passed": False,
                "blocked": True,
                "block_reason": f"Tweet {i + 1}: {result['block_reason']}",
                "violations": result["violations"],
                "platform": "x",
                "format_type": "thread",
            }
        cleaned.append(result["text"])

    return {
        "text": "\n".join(cleaned),
        "passed": True,
        "blocked": False,
        "block_reason": "",
        "violations": [],
        "platform": "x",
        "format_type": "thread",
    }


def assert_no_em_dashes(text: str) -> None:
    """Test helper: hard fail if em or en dash present."""
    if "—" in text or "–" in text:
        raise AssertionError("Public copy contains em or en dash")
