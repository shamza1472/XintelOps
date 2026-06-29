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


class GateResult(TypedDict):
    text: str
    passed: bool
    blocked: bool
    block_reason: str
    violations: list[str]
    platform: str
    format_type: str


def _contains_global_banned(text: str) -> str | None:
    lower = text.lower()
    for phrase in sorted(GLOBAL_BANNED_PHRASES, key=len, reverse=True):
        if phrase in lower:
            return phrase
    return None


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
    if format_type == "single_tweet":
        if is_malformed_tweet(check_body):
            violations.append("malformed tweet")
        if is_truncated_tweet(check_body):
            violations.append("truncated tweet")
        if max_len and len(check_body) > max_len:
            check_body = fit_tweet_length(check_body, max_len)
    elif max_len and len(check_body) > max_len:
        check_body = check_body[:max_len].rsplit(" ", 1)[0].rstrip(",;") + "."

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
    region = str(signal.get("region") or "").strip()
    confidence = str(signal.get("confidence") or "").upper()

    verified: list[str] = []
    for item in signal.get("verified_facts") or []:
        if isinstance(item, dict):
            verified.append(str(item.get("fact") or item.get("claim") or ""))
        else:
            verified.append(str(item))
    verified = [v.strip().rstrip(".") for v in verified if v.strip()]

    implication = str(
        signal.get("summary") or signal.get("why_hamza_should_care") or ""
    ).strip()
    if implication and re.search(
        r"why_this|xintelops|operator|score|the signal|watch next|bottom line|if you",
        implication,
        re.I,
    ):
        implication = ""

    parts: list[str] = []
    if title:
        parts.append(f"{title}.")
    elif verified:
        parts.append(f"{verified[0]}.")

    if verified and verified[0].lower() not in (title or "").lower():
        parts.append(f"{verified[0]}.")

    if implication and implication.lower() not in " ".join(parts).lower():
        imp = implication if implication.endswith(".") else f"{implication}."
        parts.append(imp)

    if confidence in {"", "LOW", "MEDIUM"}:
        parts.append("Treat secondary details as provisional until follow-on confirmation.")
    elif region:
        parts.append(f"Worth tracking follow-on reporting from {region}.")

    text = " ".join(parts).strip()
    if not text and source_package:
        src = source_package[0]
        name = src.get("name") or src.get("source") or "Reporting"
        parts = [f"{name} reports an update on {title or 'the selected signal'}."]
        text = " ".join(parts)

    return fit_tweet_length(text, 260) if text else ""


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
