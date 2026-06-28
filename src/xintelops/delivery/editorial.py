from __future__ import annotations

import re
from typing import Any

SLOP_REWRITES: tuple[tuple[str, str], ...] = (
    ("second-order angle most feeds skip", "Secondary risk"),
    ("xintelops angle:", "The relevant linkage is"),
    ("xintelops angle", "The relevant linkage is"),
    ("most feeds skip", "Secondary risk"),
    ("not a headline cycle", "not a standalone event"),
    ("not a standalone event . it's", "The issue is"),
    ("not a standalone event. it's", "The issue is"),
    ("chokepoint crisis", "chokepoint pressure"),
    ("watch next 12h", "Watch next scan window"),
    ("operators should watch", "Worth monitoring"),
    ("world's most critical", "high-consequence"),
    ("world's most watched", "widely tracked"),
    ("before headlines catch up", "before broader coverage"),
    ("post now while sources are converging", "Sources are still converging"),
    ("this is no longer bilateral", "This now involves multiple actors"),
    ("generic headline cycle", "routine headline cycle"),
)

SLOP_PHRASES = (
    "this changes everything",
    "the world is watching",
    "game changer",
    "wake-up call",
    "new era",
    "critical moment",
    "major implications",
    "rising tensions",
    "could reshape the region",
    "signal over noise",
    "before the headline",
    "the stakes could not be higher",
    "only time will tell",
    "it remains to be seen",
    "in today's complex geopolitical landscape",
    "watch closely",
    "operators should watch",
    "chokepoint math is changing fast",
    "generic headline noise",
    "xintelops lane",
    "xintelops tracks",
    "dominate analyst conversation",
    "analysts splitting attention",
    "xintelops angle",
    "most feeds skip",
    "not a headline cycle",
    "chokepoint crisis",
    "watch next 12h",
    "world's most critical",
    "world's most watched",
    "before headlines catch up",
    "post now while sources are converging",
    "this is no longer bilateral",
    "generic headline cycle",
)

CERTAINTY_REPLACEMENTS = (
    (r"\bproves\b", "suggests"),
    (r"\bwill reprice\b", "could reprice"),
    (r"\bwill\b", "may"),
    (r"\bguarantees\b", "may support"),
    (r"\bconfirms\b(?!\s+(?:source|report|statement))", "is consistent with"),
    (r"\bis preparing to escalate\b", "adds pressure, but available sources do not prove escalation"),
    (r"\bis preparing for war\b", "points to hedging, not proof of imminent conflict"),
)

HALLUCINATION_PATTERNS = (
    r"\b\d+\s*(?:ships|tanks|troops|casualties|dead|killed)\b",
    r"\banalysts believe\b",
    r"\bmarkets will\b",
    r"\bcoordinated (?:china|iran|russia|strategy)\b",
)


def _apply_slop_rewrites(text: str) -> str:
    out = text
    for old, new in sorted(SLOP_REWRITES, key=lambda x: -len(x[0])):
        out = re.sub(re.escape(old), new, out, flags=re.IGNORECASE)
    return out


def _strip_slop_phrases(text: str) -> str:
    out = _apply_slop_rewrites(text)
    for phrase in SLOP_PHRASES:
        out = re.sub(re.escape(phrase), "", out, flags=re.IGNORECASE)
    out = re.sub(r"🧵", "", out)
    out = re.sub(r"#\w+", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _soften_certainty(text: str) -> str:
    out = text
    for pattern, repl in CERTAINTY_REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def score_editorial_quality(text: str) -> dict[str, Any]:
    if not text.strip():
        return {
            "clarity": 1,
            "specificity": 1,
            "evidence_discipline": 1,
            "hype_risk": 10,
            "ai_slop_risk": 10,
            "hallucination_risk": 10,
            "passes_editorial_filter": False,
        }

    lower = text.lower()
    slop_hits = sum(1 for p in SLOP_PHRASES if p in lower)
    hype_hits = sum(1 for w in ("!", "critical", "massive", "unprecedented", "dramatic") if w in lower)
    hall_hits = sum(1 for p in HALLUCINATION_PATTERNS if re.search(p, lower))
    has_source_ref = any(w in lower for w in ("reuters", "bbc", "irna", "defense news", "according to", "said"))
    word_count = len(text.split())
    is_short_form = len(text) <= 280 and word_count <= 50

    clarity = max(1, min(10, 6 + (1 if word_count < 120 else 0) + (1 if "\n" in text else 0)))
    specificity = max(1, min(10, 5 + (2 if has_source_ref else 0) + (1 if re.search(r"\d", text) else 0)))
    evidence = max(1, min(10, 6 + (2 if has_source_ref else -1) - hall_hits))
    if is_short_form:
        specificity = max(specificity, 7)
        evidence = max(evidence, 7)
    hype = max(1, min(10, 3 + slop_hits + hype_hits))
    slop = max(1, min(10, 2 + slop_hits * 2))
    hall = max(1, min(10, 2 + hall_hits * 3))

    passes = (
        clarity >= 7
        and specificity >= 7
        and evidence >= 7
        and hype <= 5
        and slop <= 4
        and hall <= 3
    )
    return {
        "clarity": clarity,
        "specificity": specificity,
        "evidence_discipline": evidence,
        "hype_risk": hype,
        "ai_slop_risk": slop,
        "hallucination_risk": hall,
        "passes_editorial_filter": passes,
    }


def build_claim_map(text: str, sources: list[dict[str, Any]], primary_title: str = "") -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    source_urls = [str(s.get("url") or "") for s in sources if s.get("url")]
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.strip()
        if len(s) < 20:
            continue
        matched_url = next((u for u in source_urls if u and u.split("/")[2] in s.lower()), source_urls[0] if source_urls else "")
        support = "direct" if matched_url else "unsupported"
        if any(w in s.lower() for w in ("may", "could", "suggests", "points to", "consistent with")):
            support = "analytical inference"
        claims.append(
            {
                "claim": s[:240],
                "source_role": "primary" if primary_title.lower()[:20] in s.lower() else "contextual",
                "source_url": matched_url,
                "support_level": support,
            }
        )
    return claims[:12]


def anti_hallucination_pass(
    text: str,
    sources: list[dict[str, Any]] | None = None,
    *,
    primary_title: str = "",
) -> dict[str, Any]:
    sources = sources or []
    claims = build_claim_map(text, sources, primary_title)
    unsupported = [c for c in claims if c["support_level"] == "unsupported"]
    rewritten = _soften_certainty(text)
    scores = score_editorial_quality(rewritten)

    blocked = False
    reason = ""
    if unsupported and len(unsupported) >= max(2, len(claims) // 2):
        blocked = True
        reason = f"Unsupported claim: {unsupported[0]['claim'][:120]}"
        rewritten = _soften_certainty(rewritten)
    if scores["hallucination_risk"] > 3:
        rewritten = _soften_certainty(rewritten)
        scores = score_editorial_quality(rewritten)

    return {
        "text": rewritten,
        "claims": claims,
        "unsupported_claims": unsupported,
        "blocked": blocked,
        "block_reason": reason,
        "scores": scores,
    }


def anti_slop_editorial_pass(text: str) -> dict[str, Any]:
    if not str(text or "").strip():
        return {
            "text": "",
            "blocked": True,
            "block_reason": "COPY BLOCKED — LOW SIGNAL",
            "scores": score_editorial_quality(""),
        }

    cleaned = _strip_slop_phrases(text)
    cleaned = _soften_certainty(cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    scores = score_editorial_quality(cleaned)

    if not cleaned.strip():
        return {
            "text": "",
            "blocked": True,
            "block_reason": "COPY BLOCKED — LOW SIGNAL",
            "scores": scores,
        }

    if not scores["passes_editorial_filter"]:
        cleaned = _soften_certainty(_strip_slop_phrases(cleaned))
        scores = score_editorial_quality(cleaned)

    blocked = False
    reason = ""
    if not scores["passes_editorial_filter"]:
        blocked = True
        reason = (
            f"COPY BLOCKED — EDITORIAL QUALITY FAIL "
            f"(clarity={scores['clarity']}, slop={scores['ai_slop_risk']}, hall={scores['hallucination_risk']})"
        )

    return {
        "text": cleaned,
        "blocked": blocked,
        "block_reason": reason,
        "scores": scores,
    }


def editorial_pipeline(
    text: str,
    sources: list[dict[str, Any]] | None = None,
    *,
    primary_title: str = "",
) -> dict[str, Any]:
    slop = anti_slop_editorial_pass(text)
    if slop["blocked"]:
        return {**slop, "claims": []}
    hall = anti_hallucination_pass(slop["text"], sources, primary_title=primary_title)
    combined_blocked = slop["blocked"] or hall["blocked"]
    reason = hall["block_reason"] or slop["block_reason"]
    scores = hall["scores"]
    return {
        "text": hall["text"],
        "blocked": combined_blocked,
        "block_reason": reason,
        "scores": scores,
        "claims": hall["claims"],
    }


# --- Final copy-paste safety pass (public X copy only) ---

FINAL_COPY_REWRITES: tuple[tuple[str, str], ...] = (
    ("this isn't a headline cycle — it's", "The issue is"),
    ("this isn't a headline cycle — it is", "The issue is"),
    ("this isn't a headline cycle", "not a standalone event"),
    ("this is not a headline cycle", "not a standalone event"),
    ("what most analysts miss:", ""),
    ("what most analysts miss", ""),
    ("what most feeds miss", ""),
    ("most feeds skip", "Secondary risk"),
    ("second-order watch", "Secondary risk"),
    ("bottom line:", ""),
    ("live event priority mode", ""),
    ("post primary thread", ""),
    ("post now", ""),
    ("translation —", ""),
    ("translation:", ""),
    ("for operators:", ""),
    ("for operators", ""),
    ("for tracking", ""),
    ("operators should watch", "Worth monitoring"),
    ("chokepoint crisis", "chokepoint pressure"),
    ("chokepoint math", "transit cost"),
    ("insurance math", "insurance cost"),
    ("before headlines catch up", "before broader coverage"),
    ("dominates analyst feeds", "is drawing analyst attention"),
    ("generic headline noise", "routine headline coverage"),
    ("xintelops angle", "The relevant linkage is"),
    ("xintelops tracks", ""),
    ("your audience", "readers"),
)

FINAL_BANNED_PHRASES = (
    "this isn't a headline cycle",
    "this is not a headline cycle",
    "headline cycle",
    "what most analysts miss",
    "what most feeds miss",
    "most feeds skip",
    "operators should watch",
    "for operators",
    "for tracking",
    "second-order watch",
    "bottom line:",
    "live event priority mode",
    "post primary thread",
    "post now",
    "translation —",
    "translation:",
    "chokepoint crisis",
    "chokepoint math",
    "insurance math",
    "before headlines catch up",
    "dominates analyst feeds",
    "generic headline noise",
    "xintelops angle",
    "xintelops tracks",
    "your audience",
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
    "it's not ",
    "it is not ",
    "this isn't just",
    "this is not just",
    "unlike others",
    "the key is",
    "what matters is",
    "here's why",
    "lets unpack",
    "let's unpack",
    "deep dive",
    "signal from noise",
    "signal over noise",
)

FINAL_INTERNAL_LABELS = (
    "action:",
    "format:",
    "deadline:",
    "expires:",
    "tier:",
    "layer:",
    "monitor only",
    "post primary thread",
    "source role:",
    "live event priority mode",
)

_FORMULAIC_LABEL_PREFIX = re.compile(
    r"^\s*(?:why it matters|bottom line|what most analysts miss|for operators|translation|what to watch)\s*:\s*",
    re.IGNORECASE,
)

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def _replace_em_dashes(text: str) -> str:
    out = text.replace("\u2014", ". ").replace(" — ", ". ").replace("—", ". ")
    out = re.sub(r"\.\s+\.", ".", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def _apply_final_rewrites(text: str) -> str:
    out = text
    for old, new in sorted(FINAL_COPY_REWRITES, key=lambda x: -len(x[0])):
        out = re.sub(re.escape(old), new, out, flags=re.IGNORECASE)
    return out


def _contains_banned_phrase(text: str) -> str | None:
    lower = text.lower()
    for phrase in FINAL_BANNED_PHRASES:
        if phrase in lower:
            return phrase
    return None


def _contains_internal_label(text: str) -> str | None:
    lower = text.lower()
    for label in FINAL_INTERNAL_LABELS:
        if label in lower:
            return label
    return None


def _strip_formulaic_labels(text: str) -> str:
    out = _FORMULAIC_LABEL_PREFIX.sub("", text)
    out = re.sub(r"^\s*\d+\)\s*", "", out)
    return out.strip()


def _cleanup_orphan_punctuation(text: str) -> str:
    out = re.sub(r"\s*\.\s*,\s*", ". ", text)
    out = re.sub(r"^\s*[.,:;]+\s*", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def _is_broken_after_cleaning(text: str) -> bool:
    t = text.strip()
    words = re.findall(r"\b[a-z]{2,}\b", t.lower())
    if len(words) < 4:
        return True
    if len(t) < 20:
        return True
    if re.match(r"^[\s.,:;!?]+", t):
        return True
    return False


def final_anti_ai_slop_pass(text: str, *, max_len: int = 280) -> dict[str, Any]:
    """
    Final copy-paste safety pass on rendered public X tweet text.
    Runs after slop, hallucination, parsing, numbering, and brand footer insertion.
    """
    from xintelops.delivery.x_copy import THREAD_BRAND_FOOTER, fit_tweet_length, is_truncated_tweet

    raw = str(text or "").strip()
    if not raw:
        return {
            "text": "",
            "blocked": True,
            "block_reason": "Tweet is empty after final copy pass.",
            "issues": ["empty"],
        }

    issues: list[str] = []
    cleaned = _replace_em_dashes(raw)
    cleaned = _apply_final_rewrites(cleaned)
    cleaned = _strip_formulaic_labels(cleaned)
    cleaned = re.sub(r"^\s*translation\s*\.?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = _EMOJI_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"#\w+", "", cleaned)
    cleaned = _cleanup_orphan_punctuation(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    banned = _contains_banned_phrase(cleaned)
    if banned:
        cleaned = re.sub(re.escape(banned), "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        banned = _contains_banned_phrase(cleaned)

    internal = _contains_internal_label(cleaned)
    if internal:
        cleaned = re.sub(re.escape(internal), "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        internal = _contains_internal_label(cleaned)

    if "\u2014" in cleaned or "—" in cleaned:
        cleaned = _replace_em_dashes(cleaned)
        issues.append("em_dash")

    body_for_truncation = cleaned.replace(THREAD_BRAND_FOOTER, "").strip()

    if is_truncated_tweet(body_for_truncation) and len(cleaned) <= max_len:
        return {
            "text": cleaned,
            "blocked": True,
            "block_reason": "Tweet ends with truncated or incomplete text.",
            "issues": issues + ["truncated"],
        }

    if len(cleaned) > max_len:
        cleaned = fit_tweet_length(cleaned, max_len=max_len)
        body_for_truncation = cleaned.replace(THREAD_BRAND_FOOTER, "").strip()

    if is_truncated_tweet(body_for_truncation):
        return {
            "text": cleaned,
            "blocked": True,
            "block_reason": "Tweet ends with truncated or incomplete text.",
            "issues": issues + ["truncated"],
        }

    banned = _contains_banned_phrase(cleaned)
    internal = _contains_internal_label(cleaned)
    blocked = bool(banned or internal)
    reason = ""
    if banned:
        reason = f"Banned phrase remains: {banned}"
    elif internal:
        reason = f"Internal operator label remains: {internal}"
    elif re.search(r"#\w+", cleaned):
        blocked = True
        reason = "Hashtag in public copy."
    elif _EMOJI_PATTERN.search(cleaned):
        blocked = True
        reason = "Emoji in public copy."

    if not cleaned.strip():
        blocked = True
        reason = reason or "Tweet is empty after final copy pass."
    elif _is_broken_after_cleaning(cleaned):
        blocked = True
        reason = reason or "Tweet is a broken fragment after final copy pass."

    return {
        "text": cleaned,
        "blocked": blocked,
        "block_reason": reason,
        "issues": issues,
    }
