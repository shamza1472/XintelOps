from __future__ import annotations

import re
from typing import Any

# --- Regional tiers ---

TIER1_REGIONS = frozenset(
    {
        "china",
        "chinese",
        "taiwan",
        "pakistan",
        "india",
        "gulf",
        "iran",
        "levant",
        "red sea",
        "horn of africa",
        "middle east",
        "saudi",
        "uae",
        "yemen",
        "israel",
        "palestine",
        "syria",
        "iraq",
        "south asia",
        "south china sea",
        "indo-pacific",
    }
)

TIER2_REGIONS = frozenset(
    {
        "central asia",
        "caucasus",
        "east africa",
        "asean",
        "southeast asia",
        "myanmar",
        "kazakhstan",
        "uzbekistan",
        "indian ocean",
        "arabian sea",
        "somalia",
        "ethiopia",
        "djibouti",
    }
)

WESTERN_DEFENSE_REGIONS = frozenset(
    {
        "ukraine",
        "europe",
        "european",
        "nato",
        "crimea",
        "russia",
        "brussels",
        "kyiv",
        "kiev",
        "donbas",
        "baltic",
        "poland",
        "germany",
        "france",
        "uk",
        "britain",
    }
)

STRATEGIC_THEME_TOKENS = frozenset(
    {
        "port",
        "shipping",
        "maritime",
        "chokepoint",
        "undersea cable",
        "subsea cable",
        "isr",
        "ew",
        "electronic warfare",
        "drone",
        "uav",
        "rare earth",
        "energy infrastructure",
        "pipeline",
        "telecom",
        "sanctions evasion",
        "sanctions enforcement",
        "defense procurement",
        "sovereign wealth",
        "dual-use",
        "espionage",
        "influence operation",
        "logistics corridor",
        "supply chain",
        "insurance premium",
        "hormuz",
        "bab el-mandeb",
        "strait",
    }
)

GENERIC_WESTERN_TOKENS = frozenset(
    {
        "nato statement",
        "nato summit",
        "nato briefing",
        "ukraine battlefield",
        "casualty",
        "casualties",
        "aid package",
        "military aid",
        "press conference",
        "air defense request",
        "patriot",
        "himars delivery",
        "european defense industry",
        "defense spending pledge",
        "battlefield update",
        "front line",
        "territory recaptured",
    }
)

SECOND_ORDER_TOKENS = frozenset(
    {
        "china",
        "chinese",
        "taiwan",
        "indo-pacific",
        "gulf",
        "iran",
        "red sea",
        "hormuz",
        "black sea",
        "sanctions",
        "maritime insurance",
        "shipping route",
        "supply chain",
        "defense-industrial",
        "defense industrial",
        "drone doctrine",
        "ew lesson",
        "north korea",
        "rare earth",
        "energy routing",
        "food security",
        "logistics",
        "chokepoint",
        "pakistan",
        "india",
        "horn of africa",
        "south asia",
        "espionage",
        "dual-use",
    }
)

NICHE_SOURCE_KEYWORDS = frozenset(
    {
        "china",
        "chinese",
        "taiwan",
        "pakistan",
        "india",
        "iran",
        "gulf",
        "saudi",
        "uae",
        "yemen",
        "red sea",
        "horn",
        "somalia",
        "ethiopia",
        "djibouti",
        "central asia",
        "asean",
        "maritime",
        "shipping",
        "rare earth",
        "sanctions",
        "irna",
        "al jazeera",
        "sipri",
    }
)

WESTERN_HEAVY_SOURCE_KEYWORDS = frozenset(
    {"nato", "ukraine", "crimea", "bbc", "reuters world", "tass", "defense.gov"}
)

TIER1_BOOST = 25
TIER2_BOOST = 15
THEME_BOOST = 10
GENERIC_WESTERN_PENALTY = 20

WEIGHT_NICHE = 0.35
WEIGHT_EDGE = 0.25
WEIGHT_FORECAST = 0.20
WEIGHT_POST = 0.15
WEIGHT_CONFIDENCE = 0.05


def _blob(signal: dict[str, Any]) -> str:
    parts = [
        signal.get("title"),
        signal.get("why_hamza_should_care"),
        signal.get("action_rationale"),
        signal.get("region"),
        signal.get("domain"),
        signal.get("source"),
        signal.get("summary"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def infer_niche_tier(region: str, domain: str = "", title: str = "") -> int:
    blob = f"{region} {domain} {title}".lower()
    if any(token in blob for token in TIER1_REGIONS):
        return 1
    if any(token in blob for token in TIER2_REGIONS):
        return 2
    if any(token in blob for token in WESTERN_DEFENSE_REGIONS):
        return 3
    return 3


def is_western_defense_signal(signal: dict[str, Any]) -> bool:
    blob = _blob(signal)
    return any(token in blob for token in WESTERN_DEFENSE_REGIONS)


def has_strategic_theme(signal: dict[str, Any]) -> bool:
    return any(token in _blob(signal) for token in STRATEGIC_THEME_TOKENS)


def is_generic_western_content(signal: dict[str, Any]) -> bool:
    if not is_western_defense_signal(signal):
        return False
    blob = _blob(signal)
    if any(token in blob for token in GENERIC_WESTERN_TOKENS):
        return True
    if has_strategic_theme(signal) or has_second_order_relevance(signal):
        return False
    scores = signal.get("scores") or {}
    if int(scores.get("edge", 5)) >= 8 and has_second_order_relevance(signal):
        return False
    return is_western_defense_signal(signal) and not has_second_order_relevance(signal)


def has_second_order_relevance(signal: dict[str, Any]) -> bool:
    if signal.get("second_order_relevance") is True:
        return True
    if str(signal.get("second_order_relevance", "")).lower() in {"true", "yes"}:
        return True
    blob = _blob(signal)
    matches = sum(1 for token in SECOND_ORDER_TOKENS if token in blob)
    if matches >= 2:
        return True
    return matches >= 1 and has_strategic_theme(signal)


def _confidence_score(confidence: str) -> int:
    mapping = {"HIGH": 10, "MEDIUM": 7, "LOW": 4}
    return mapping.get(str(confidence or "MEDIUM").upper(), 7)


def compute_rank_score(signal: dict[str, Any]) -> dict[str, Any]:
    scores = signal.get("scores") or {}
    niche = int(scores.get("niche_relevance", 5))
    edge = int(scores.get("edge", 5))
    forecast = int(scores.get("forecast_value", 5))
    post = int(scores.get("post_worthiness", 5))
    conf = _confidence_score(signal.get("confidence", "MEDIUM"))

    base = (
        niche * WEIGHT_NICHE * 10
        + edge * WEIGHT_EDGE * 10
        + forecast * WEIGHT_FORECAST * 10
        + post * WEIGHT_POST * 10
        + conf * WEIGHT_CONFIDENCE * 10
    )

    tier = signal.get("niche_tier") or infer_niche_tier(
        str(signal.get("region") or ""),
        str(signal.get("domain") or ""),
        str(signal.get("title") or ""),
    )
    tier_boost = TIER1_BOOST if tier == 1 else TIER2_BOOST if tier == 2 else 0
    theme_boost = THEME_BOOST if has_strategic_theme(signal) else 0

    penalty = 0
    penalty_reason = ""
    if is_generic_western_content(signal):
        penalty = GENERIC_WESTERN_PENALTY
        penalty_reason = "Generic NATO/Ukraine/Europe content without second-order niche relevance"
    elif is_western_defense_signal(signal) and not has_second_order_relevance(signal):
        penalty = GENERIC_WESTERN_PENALTY
        penalty_reason = "Western defense signal lacks China/Gulf/Red Sea/supply-chain linkage"

    final = base + tier_boost + theme_boost - penalty
    return {
        "base_score": round(base, 1),
        "tier_boost": tier_boost,
        "theme_boost": theme_boost,
        "penalty": penalty,
        "penalty_reason": penalty_reason,
        "rank_score": round(final, 1),
        "niche_tier": tier,
    }


def apply_ranking_bias(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for sig in signals:
        item = dict(sig)
        item["niche_tier"] = item.get("niche_tier") or infer_niche_tier(
            str(item.get("region") or ""),
            str(item.get("domain") or ""),
            str(item.get("title") or ""),
        )
        ranking = compute_rank_score(item)
        item.update(ranking)

        action = str(item.get("recommended_action") or "MONITOR").upper()
        if is_generic_western_content(item) and action in {"X POST", "X THREAD", "LINKEDIN"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "")
                + " [Auto-demoted: generic Western defense — archive/monitor only.]"
            ).strip()

        enriched.append(item)

    enriched.sort(key=lambda s: s.get("rank_score", 0), reverse=True)
    for idx, sig in enumerate(enriched, 1):
        sig["rank"] = idx
    return enriched


def _best_niche_post_candidate(signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    for sig in signals:
        if sig.get("niche_tier", 3) <= 2 and sig.get("recommended_action") in {"X POST", "X THREAD"}:
            return sig
    for sig in signals:
        if sig.get("niche_tier", 3) <= 2:
            return sig
    return None


def select_post_with_quota(
    signals: list[dict[str, Any]],
    agent_pick: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (selected_signal, regional_priority_check)."""
    if not signals:
        return {}, {"status": "Failed", "reason": "No verified signals in scan."}

    niche_best = _best_niche_post_candidate(signals)
    agent_title = (agent_pick or {}).get("title")
    selected = next((s for s in signals if s.get("title") == agent_title), signals[0])
    if not agent_title:
        selected = niche_best or signals[0]

    tier = selected.get("niche_tier", 3)
    western = is_western_defense_signal(selected)
    second_order = has_second_order_relevance(selected)
    agent_override_reason = (agent_pick or {}).get("regional_override_reason") or selected.get(
        "regional_override_reason"
    )

    if tier <= 2:
        return selected, {
            "status": "Passed",
            "reason": f"Top post from Tier-{tier} priority theater ({selected.get('region', 'niche region')}).",
        }

    if niche_best and niche_best.get("title") != selected.get("title"):
        if not second_order and not agent_override_reason:
            return niche_best, {
                "status": "Overridden",
                "reason": (
                    f"Agent selected Western/generic signal '{selected.get('title')}'. "
                    f"Replaced with Tier-{niche_best.get('niche_tier')} priority: "
                    f"{niche_best.get('title')}."
                ),
            }

    if western and second_order:
        reason = agent_override_reason or (
            "Western signal retained due to explicit second-order relevance to "
            "China/Gulf/Red Sea/supply chains/maritime/sanctions theaters."
        )
        return selected, {"status": "Overridden", "reason": reason}

    if western and not niche_best:
        reason = agent_override_reason or (
            "No Tier-1/Tier-2 signal available this scan. Western signal selected with caution."
        )
        return selected, {"status": "Overridden", "reason": reason}

    if western:
        return niche_best or selected, {
            "status": "Overridden",
            "reason": (
                agent_override_reason
                or f"Generic Western signal blocked. Using Tier-{niche_best.get('niche_tier')} priority pick."
            ),
        }

    return selected, {
        "status": "Passed",
        "reason": f"Signal aligns with XIntelOps niche positioning ({selected.get('region', 'priority theater')}).",
    }


def source_priority_score(source_name: str, region: str = "", domain: str = "") -> int:
    blob = f"{source_name} {region} {domain}".lower()
    score = 50
    if any(k in blob for k in NICHE_SOURCE_KEYWORDS):
        score += 40
    if any(k in blob for k in WESTERN_HEAVY_SOURCE_KEYWORDS):
        score -= 25
    if any(k in blob for k in STRATEGIC_THEME_TOKENS):
        score += 10
    return score
