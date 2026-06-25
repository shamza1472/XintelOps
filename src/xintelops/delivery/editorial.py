from __future__ import annotations

import re
from typing import Any

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


def _strip_slop_phrases(text: str) -> str:
    out = text
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
