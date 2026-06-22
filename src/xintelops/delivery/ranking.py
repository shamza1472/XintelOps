from __future__ import annotations

from typing import Any

from xintelops.delivery.live_events import (
    classify_freshness,
    compute_live_event_score,
    cooldown_penalty,
    freshness_immediate_eligible,
    is_slow_burn_analysis,
)

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
        "qatar",
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
        "lng",
        "oil",
    }
)

PRIORITY_ACTOR_TOKENS = frozenset(
    {
        "iran",
        "qatar",
        "pakistan",
        "gulf",
        "saudi",
        "uae",
        "u.s.",
        "us ",
        "united states",
        "washington",
        "china",
        "india",
        "israel",
        "lebanon",
        "hezbollah",
        "hormuz",
        "red sea",
        "oil",
        "lng",
        "sanctions",
        "ceasefire",
        "mediation",
        "nuclear",
        "switzerland",
        "geneva",
    }
)

LIVE_MOMENTUM_HIGH = frozenset(
    {
        "ceasefire",
        "cease-fire",
        "war termination",
        "escalation talk",
        "mediation",
        "negotiation",
        "talks in switzerland",
        "geneva talks",
        "diplomatic meeting",
        "emergency meeting",
        "hostage",
        "prisoner swap",
        "frozen asset",
        "sanctions relief",
        "sanctions enforcement",
        "missile strike",
        "airspace closure",
        "naval deployment",
        "strait of hormuz",
        "oil price",
        "lng",
        "multi-state",
        "crisis management",
    }
)

LIVE_MOMENTUM_MEDIUM = frozenset(
    {
        "summit",
        "bilateral",
        "trilateral",
        "delegation",
        "foreign minister",
        "defense minister",
        "procurement",
        "deployment",
        "exercise",
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
        "qatar",
        "ceasefire",
        "lng",
        "oil",
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
        "qatar",
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

TIER1_BOOST = 15
TIER2_BOOST = 8
THEME_BOOST = 5
GENERIC_WESTERN_PENALTY = 20
MULTI_ACTOR_MOMENTUM_BOOST = 12
LIVE_MOMENTUM_THRESHOLD = 8

# Normal mode weights
N_NORMAL = {"niche": 0.30, "edge": 0.25, "forecast": 0.20, "post": 0.15, "confidence": 0.10}
# Live momentum override mode weights
N_OVERRIDE = {"momentum": 0.35, "post": 0.20, "niche": 0.20, "forecast": 0.15, "confidence": 0.10}


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


def count_priority_actors(signal: dict[str, Any]) -> int:
    blob = _blob(signal)
    return sum(1 for token in PRIORITY_ACTOR_TOKENS if token in blob)


def infer_live_momentum(signal: dict[str, Any]) -> int:
    scores = signal.get("scores") or {}
    if scores.get("live_momentum") is not None:
        return max(1, min(10, int(scores.get("live_momentum"))))

    blob = _blob(signal)
    if signal.get("crisis_flag"):
        base = 8
    elif any(t in blob for t in LIVE_MOMENTUM_HIGH):
        base = 9
    elif any(t in blob for t in LIVE_MOMENTUM_MEDIUM):
        base = 7
    else:
        base = 4

    actors = count_priority_actors(signal)
    if actors >= 3:
        base = min(10, base + 2)
    if actors >= 4:
        base = min(10, max(base, 9))

    return max(1, min(10, base))


def is_western_defense_signal(signal: dict[str, Any]) -> bool:
    return any(token in _blob(signal) for token in WESTERN_DEFENSE_REGIONS)


def has_strategic_theme(signal: dict[str, Any]) -> bool:
    return any(token in _blob(signal) for token in STRATEGIC_THEME_TOKENS)


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


def is_generic_western_content(signal: dict[str, Any]) -> bool:
    momentum = infer_live_momentum(signal)
    if momentum >= LIVE_MOMENTUM_THRESHOLD and count_priority_actors(signal) >= 2:
        return False
    if not is_western_defense_signal(signal):
        return False
    blob = _blob(signal)
    if any(token in blob for token in GENERIC_WESTERN_TOKENS):
        return not has_second_order_relevance(signal) and momentum < LIVE_MOMENTUM_THRESHOLD
    if has_strategic_theme(signal) or has_second_order_relevance(signal):
        return False
    return is_western_defense_signal(signal) and momentum < LIVE_MOMENTUM_THRESHOLD


def _confidence_score(confidence: str) -> int:
    mapping = {"HIGH": 10, "MEDIUM": 7, "LOW": 4}
    return mapping.get(str(confidence or "MEDIUM").upper(), 7)


def compute_rank_score(
    signal: dict[str, Any],
    *,
    rec_history: list[dict[str, Any]] | None = None,
    has_stronger_live: bool = False,
) -> dict[str, Any]:
    scores = signal.get("scores") or {}
    niche = int(scores.get("niche_relevance", 5))
    edge = int(scores.get("edge", 5))
    forecast = int(scores.get("forecast_value", 5))
    post = int(scores.get("post_worthiness", 5))
    conf = _confidence_score(signal.get("confidence", "MEDIUM"))
    momentum = infer_live_momentum(signal)
    scores["live_momentum"] = momentum

    live_meta = compute_live_event_score(signal)
    live_event_score = live_meta["live_event_score"]
    signal["live_event_score"] = live_event_score
    freshness = classify_freshness(signal)
    signal["freshness_class"] = freshness

    tier = signal.get("niche_tier") or infer_niche_tier(
        str(signal.get("region") or ""),
        str(signal.get("domain") or ""),
        str(signal.get("title") or ""),
    )
    actors = count_priority_actors(signal)
    use_override = (
        live_event_score >= LIVE_MOMENTUM_THRESHOLD
        or momentum >= LIVE_MOMENTUM_THRESHOLD
        or live_meta.get("live_event_priority")
        or actors >= 3
    )

    if use_override:
        base = (
            max(live_event_score, momentum) * N_OVERRIDE["momentum"] * 10
            + post * N_OVERRIDE["post"] * 10
            + niche * N_OVERRIDE["niche"] * 10
            + forecast * N_OVERRIDE["forecast"] * 10
            + conf * N_OVERRIDE["confidence"] * 10
        )
        ranking_mode = "live_event_priority" if live_event_score >= LIVE_MOMENTUM_THRESHOLD else "live_momentum_override"
    else:
        base = (
            niche * N_NORMAL["niche"] * 10
            + edge * N_NORMAL["edge"] * 10
            + forecast * N_NORMAL["forecast"] * 10
            + post * N_NORMAL["post"] * 10
            + conf * N_NORMAL["confidence"] * 10
        )
        ranking_mode = "normal"

    tier_boost = TIER1_BOOST if tier == 1 else TIER2_BOOST if tier == 2 else 0
    theme_boost = THEME_BOOST if has_strategic_theme(signal) else 0
    actor_boost = MULTI_ACTOR_MOMENTUM_BOOST if actors >= 3 else 0

    penalty = 0
    penalty_reason = ""
    if is_generic_western_content(signal):
        penalty = GENERIC_WESTERN_PENALTY
        penalty_reason = "Generic NATO/Ukraine/Europe content without live momentum or niche link"
    elif is_western_defense_signal(signal) and not has_second_order_relevance(signal) and momentum < LIVE_MOMENTUM_THRESHOLD:
        penalty = GENERIC_WESTERN_PENALTY
        penalty_reason = "Western defense signal lacks priority-theater linkage and live momentum"
    elif freshness == "EVERGREEN":
        penalty += 30
        penalty_reason = (penalty_reason + " Evergreen content — not immediate post material.").strip()
    elif freshness == "ANALYSIS" and is_slow_burn_analysis(signal):
        penalty += 15
        penalty_reason = (penalty_reason + " Slow-burn analysis — LinkedIn/archive candidate.").strip()
    elif not freshness_immediate_eligible(signal, has_stronger_live):
        penalty += 20
        penalty_reason = (penalty_reason + f" Freshness {freshness} blocked for immediate post.").strip()

    if rec_history:
        cd_penalty, cd_reason = cooldown_penalty(signal, rec_history)
        if cd_penalty:
            penalty += cd_penalty
            penalty_reason = (penalty_reason + " " + cd_reason).strip()

    final = base + tier_boost + theme_boost + actor_boost - penalty
    return {
        "base_score": round(base, 1),
        "tier_boost": tier_boost,
        "theme_boost": theme_boost,
        "actor_boost": actor_boost,
        "penalty": penalty,
        "penalty_reason": penalty_reason,
        "rank_score": round(final, 1),
        "niche_tier": tier,
        "live_momentum": momentum,
        "live_event_score": live_event_score,
        "freshness_class": freshness,
        "priority_actor_count": actors,
        "ranking_mode": ranking_mode,
        "live_momentum_override": use_override,
        "live_event_priority": live_meta.get("live_event_priority", False),
    }


def apply_ranking_bias(
    signals: list[dict[str, Any]],
    *,
    rec_history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prepped: list[dict[str, Any]] = []
    for sig in signals:
        item = dict(sig)
        item["niche_tier"] = item.get("niche_tier") or infer_niche_tier(
            str(item.get("region") or ""),
            str(item.get("domain") or ""),
            str(item.get("title") or ""),
        )
        if "scores" not in item:
            item["scores"] = {}
        item["scores"]["live_momentum"] = infer_live_momentum(item)
        prepped.append(item)

    has_stronger_live = any(
        compute_live_event_score(s)["live_event_score"] >= LIVE_MOMENTUM_THRESHOLD for s in prepped
    )

    enriched: list[dict[str, Any]] = []
    for item in prepped:
        ranking = compute_rank_score(
            item,
            rec_history=rec_history,
            has_stronger_live=has_stronger_live,
        )
        item.update(ranking)
        item["scores"] = {
            **(item.get("scores") or {}),
            "live_momentum": ranking["live_momentum"],
            "live_event_score": ranking["live_event_score"],
        }

        action = str(item.get("recommended_action") or "MONITOR").upper()
        if is_generic_western_content(item) and action in {"X POST", "X THREAD", "LINKEDIN"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "")
                + " [Auto-demoted: generic Western defense without live momentum.]"
            ).strip()
        elif item.get("freshness_class") == "EVERGREEN" and action in {"X POST", "X THREAD"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "") + " [Auto-demoted: evergreen — use LinkedIn/archive.]"
            ).strip()
        elif (
            is_slow_burn_analysis(item)
            and ranking.get("penalty", 0) >= 40
            and action in {"X POST", "X THREAD"}
        ):
            item["recommended_action"] = "MONITOR"
            item["action_rationale"] = (
                (item.get("action_rationale") or "") + " [Cooldown: slow-burn already recommended recently.]"
            ).strip()

        item["canonical_action"] = item.get("recommended_action")
        enriched.append(item)

    enriched.sort(key=lambda s: s.get("rank_score", 0), reverse=True)
    for idx, sig in enumerate(enriched, 1):
        sig["rank"] = idx
    return enriched


def _post_eligible(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    has_live = any(s.get("live_event_score", 0) >= LIVE_MOMENTUM_THRESHOLD for s in signals)
    eligible = []
    for s in signals:
        if not freshness_immediate_eligible(s, has_live):
            continue
        if s.get("recommended_action") in {"X POST", "X THREAD", "LINKEDIN"}:
            eligible.append(s)
        elif s.get("rank_score", 0) >= 60 and not is_generic_western_content(s):
            eligible.append(s)
        elif s.get("live_event_score", 0) >= LIVE_MOMENTUM_THRESHOLD:
            eligible.append(s)
    return eligible


def select_immediate_post(signals: list[dict[str, Any]], agent_pick: dict[str, Any] | None) -> dict[str, Any]:
    """Highest-value post right now: live_event_score + rank_score, not static region alone."""
    eligible = _post_eligible(signals) or [s for s in signals if not is_generic_western_content(s)]
    if not eligible:
        return signals[0] if signals else {}

    by_rank = sorted(
        eligible,
        key=lambda s: (s.get("live_event_score", 0), s.get("rank_score", 0)),
        reverse=True,
    )
    top = by_rank[0]

    # live_event_score >= 9 wins unless source confidence is weak
    high_live = [s for s in by_rank if s.get("live_event_score", 0) >= 9]
    if high_live:
        confident = [s for s in high_live if str(s.get("confidence", "")).upper() != "LOW"]
        if confident:
            return confident[0]

    agent_title = (agent_pick or {}).get("title")
    if agent_title:
        agent_sig = next((s for s in signals if s.get("title") == agent_title), None)
        if agent_sig and not is_generic_western_content(agent_sig):
            agent_live = agent_sig.get("live_event_score", 0)
            top_live = top.get("live_event_score", 0)
            if top.get("rank_score", 0) > agent_sig.get("rank_score", 0) + 5 and top_live >= LIVE_MOMENTUM_THRESHOLD:
                return top
            if agent_live >= LIVE_MOMENTUM_THRESHOLD and count_priority_actors(agent_sig) >= 2:
                return agent_sig
            if agent_sig.get("rank_score", 0) >= top.get("rank_score", 0) - 3:
                return agent_sig

    return top


def select_strategic_lead(signals: list[dict[str, Any]], immediate: dict[str, Any]) -> dict[str, Any]:
    """Best long-term tracking lead — high forecast + edge, lower live momentum ok."""
    candidates = [s for s in signals if s.get("title") != immediate.get("title")]
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda s: (
            s.get("scores", {}).get("forecast_value", 0) * 2
            + s.get("scores", {}).get("edge", 0)
            + (5 if s.get("niche_tier", 3) <= 2 else 0)
        ),
    )


def select_archive_signal(signals: list[dict[str, Any]], immediate: dict[str, Any], strategic: dict[str, Any]) -> dict[str, Any]:
    skip = {immediate.get("title"), strategic.get("title")}
    archived = [s for s in signals if s.get("recommended_action") in {"ARCHIVE", "IGNORE"} and s.get("title") not in skip]
    if archived:
        return archived[0]
    remaining = [s for s in signals if s.get("title") not in skip]
    if not remaining:
        return {}
    return min(remaining, key=lambda s: s.get("scores", {}).get("post_worthiness", 10))


def build_live_momentum_check(selected: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
    momentum = selected.get("live_momentum", 0)
    actors = selected.get("priority_actor_count", 0)
    override = selected.get("live_momentum_override") or momentum >= LIVE_MOMENTUM_THRESHOLD

    if override and momentum >= LIVE_MOMENTUM_THRESHOLD:
        actor_list = []
        blob = _blob(selected)
        for token in PRIORITY_ACTOR_TOKENS:
            if token in blob and token not in actor_list:
                actor_list.append(token.strip())
        actors_str = ", ".join(actor_list[:6]) or f"{actors} priority actors/themes"
        return {
            "status": "Override Triggered",
            "reason": (
                f"Live Momentum Override triggered because this story involves {actors_str}, "
                f"momentum {momentum}/10, and time-sensitive consequences likely to dominate "
                f"analyst conversation in the next 3–12 hours."
            ),
        }

    if momentum >= 6:
        return {
            "status": "Passed",
            "reason": f"Moderate live momentum ({momentum}/10) — timely but not crisis-cycle dominant.",
        }

    static_niche_only = (
        selected.get("niche_tier", 3) <= 2
        and momentum < 6
        and all(s.get("live_momentum", 0) < LIVE_MOMENTUM_THRESHOLD for s in signals[:3])
    )
    if static_niche_only:
        return {
            "status": "Passed",
            "reason": "No higher live-momentum signal in this scan; niche strategic lead selected.",
        }

    return {
        "status": "Failed",
        "reason": "Low live momentum — consider whether a more urgent signal was missed.",
    }


def build_regional_priority_check(selected: dict[str, Any]) -> dict[str, Any]:
    tier = selected.get("niche_tier", 3)
    momentum = selected.get("live_momentum", 0)
    actors = selected.get("priority_actor_count", 0)

    if momentum >= LIVE_MOMENTUM_THRESHOLD and actors >= 2:
        return {
            "status": "Passed",
            "reason": (
                f"Live momentum ({momentum}/10) with {actors} priority actors — "
                "timing overrides static region preference."
            ),
        }
    if tier <= 2:
        return {
            "status": "Passed",
            "reason": f"Tier-{tier} priority theater ({selected.get('region', 'niche region')}).",
        }
    if has_second_order_relevance(selected):
        return {
            "status": "Overridden",
            "reason": "Western/peripheral signal retained due to second-order niche relevance.",
        }
    return {
        "status": "Overridden",
        "reason": "Peripheral region selected — verify live momentum justified this over Tier 1/2 options.",
    }


def select_post_with_quota(
    signals: list[dict[str, Any]],
    agent_pick: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (immediate_post, regional_check, momentum_check)."""
    if not signals:
        return {}, {"status": "Failed", "reason": "No verified signals."}, {"status": "Failed", "reason": "No signals."}

    immediate = select_immediate_post(signals, agent_pick)
    regional = build_regional_priority_check(immediate)
    momentum = build_live_momentum_check(immediate, signals)
    return immediate, regional, momentum


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
