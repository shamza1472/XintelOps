from __future__ import annotations

from typing import Any

from xintelops.delivery.live_events import (
    infer_consequence_score,
    infer_recency_score,
    infer_update_velocity,
)

LANE_RELEVANCE_TYPES = frozenset(
    {
        "Direct lane relevance",
        "Indirect lane relevance",
        "Global strategic relevance",
        "Live momentum override",
        "Low relevance",
    }
)

# Structural themes — not tied to any single crisis or actor set
STRATEGIC_LANE_THEMES: dict[str, frozenset[str]] = {
    "chokepoints": frozenset({"chokepoint", "strait", "hormuz", "bab el-mandeb", "canal", "suez", "panama"}),
    "shipping_lanes": frozenset({"shipping lane", "shipping route", "maritime route", "sea lane", "red sea shipping"}),
    "ports": frozenset({"port access", "port closure", "port deal", "harbor", "terminal", "port authority"}),
    "energy_flows": frozenset(
        {"energy flow", "oil", "lng", "gas pipeline", "energy infrastructure", "energy routing", "oil price", "lng supply"}
    ),
    "sanctions": frozenset({"sanctions", "sanctions relief", "sanctions enforcement", "sanctions evasion", "waiver", "frozen asset"}),
    "defense_procurement": frozenset({"defense procurement", "arms deal", "weapons sale", "missile sale", "procurement agreement"}),
    "defense_industrial": frozenset({"defense-industrial", "defense industrial", "arms production", "munitions", "shipyard"}),
    "dual_use": frozenset({"dual-use", "dual use", "export control", "technology transfer"}),
    "isr_drones_ew_cyber": frozenset(
        {"isr", "drone", "uav", "ew", "electronic warfare", "cyber", "cyberattack", "satellite", "reconnaissance"}
    ),
    "logistics_corridors": frozenset({"logistics corridor", "trade corridor", "supply corridor", "transit route", "land bridge"}),
    "maritime_security": frozenset({"maritime security", "naval deployment", "convoy", "piracy", "maritime insurance", "houthi", "shipping disruption"}),
    "nuclear_negotiations": frozenset({"nuclear", "enrichment", "iaea", "nuclear inspection", "nuclear talks"}),
    "ceasefire_war_termination": frozenset({"ceasefire", "cease-fire", "war termination", "peace talks", "truce", "armistice"}),
    "state_mediation": frozenset({"mediation", "mediator", "facilitator", "backchannel", "diplomatic meeting"}),
    "influence_operations": frozenset({"influence operation", "disinformation", "propaganda", "information warfare"}),
    "espionage_diaspora": frozenset({"espionage", "intelligence conviction", "spy", "diaspora targeting", "covert operation"}),
    "undersea_cables": frozenset({"undersea cable", "subsea cable", "submarine cable", "cable cut", "cable attack"}),
    "supply_chain_vulnerability": frozenset(
        {"food security", "water security", "grain", "fertilizer", "critical mineral", "supply chain", "supply-chain chokepoint"}
    ),
    "sovereign_wealth": frozenset({"sovereign wealth", "strategic investment", "state fund", "swf"}),
    "basing_access": frozenset({"military base", "basing", "airspace", "access agreement", "force posture", "deployment"}),
    "corridor_realignment": frozenset({"corridor realignment", "route shift", "reroute", "alternative route", "bypass"}),
}

STRUCTURAL_EVENT_TRIGGERS = frozenset(
    {
        "ceasefire talks",
        "sanctions relief",
        "energy waiver",
        "nuclear inspection",
        "military escalation",
        "maritime disruption",
        "chokepoint closure",
        "defense-industrial agreement",
        "state visit",
        "port access",
        "intelligence conviction",
        "cyber disruption",
        "supply-chain chokepoint",
        "sovereign wealth",
    }
)

CORE_REGION_ACTORS = frozenset(
    {
        "china",
        "chinese",
        "taiwan",
        "gulf",
        "saudi",
        "uae",
        "qatar",
        "kuwait",
        "bahrain",
        "oman",
        "iran",
        "pakistan",
        "india",
        "red sea",
        "horn of africa",
        "east africa",
        "arabian sea",
        "indian ocean",
        "central asia",
        "levant",
        "israel",
        "palestine",
        "syria",
        "lebanon",
        "turkey",
        "caucasus",
        "georgia",
        "armenia",
        "azerbaijan",
        "southeast asia",
        "asean",
        "myanmar",
        "indo-pacific",
        "south asia",
        "djibouti",
        "somalia",
        "ethiopia",
        "yemen",
    }
)

SECONDARY_REGIONS = frozenset(
    {
        "europe",
        "european",
        "russia",
        "russian",
        "united states",
        "u.s.",
        "us ",
        "washington",
        "nato",
        "japan",
        "australia",
        "africa",
        "latin america",
        "south america",
        "brazil",
        "mexico",
    }
)

SECONDARY_LINK_TOKENS = frozenset(
    {
        "energy",
        "sanctions",
        "maritime",
        "shipping",
        "defense supply",
        "supply chain",
        "china",
        "russia",
        "iran",
        "alignment",
        "military basing",
        "logistics",
        "technology transfer",
        "food security",
        "chokepoint",
        "strategic capital",
        "sovereign wealth",
        "grain",
        "insurance",
    }
)

GLOBAL_OVERRIDE_MARKERS = frozenset(
    {
        "panama canal",
        "suez",
        "black sea grain",
        "black sea energy",
        "strait closure",
        "ethiopia port",
        "sudan red sea",
        "singapore sanctions",
        "undersea cable",
        "critical mineral",
        "global oil",
        "lng shock",
        "shipping cyberattack",
    }
)

CORE_REGION_BOOST = 1.5
SECONDARY_REGION_BOOST = 0.8
GLOBAL_OVERRIDE_BOOST = 2.0

# Penalty caps (on 0–100 rank scale)
REPETITION_PENALTY_MAX = 50
EVERGREEN_PENALTY = 30
ANALYSIS_PENALTY = 15
LOW_FRESHNESS_PENALTY = 20


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


def _confidence_score(confidence: str) -> int:
    return {"HIGH": 10, "MEDIUM": 7, "LOW": 4}.get(str(confidence or "MEDIUM").upper(), 7)


def _theme_present(blob: str, token: str) -> bool:
    if token not in blob:
        return False
    idx = blob.find(token)
    window = blob[max(0, idx - 24):idx]
    if any(neg in window for neg in ("without ", "no ", "not ", "lack of ", "absence of ", "without")):
        return False
    return True


def matched_lane_themes(signal: dict[str, Any]) -> list[str]:
    blob = _blob(signal)
    matched = []
    for theme, tokens in STRATEGIC_LANE_THEMES.items():
        if any(_theme_present(blob, token) for token in tokens):
            matched.append(theme)
    for trigger in STRUCTURAL_EVENT_TRIGGERS:
        if _theme_present(blob, trigger):
            matched.append(trigger.replace(" ", "_"))
    return list(dict.fromkeys(matched))


def compute_strategic_lane_score(signal: dict[str, Any]) -> int:
    """0–10 score from structural themes, not region membership."""
    themes = matched_lane_themes(signal)
    if not themes:
        domain = str(signal.get("domain") or "").lower()
        if domain in {"maritime", "energy", "defense", "diplomacy", "sanctions", "logistics", "cyber"}:
            return 4
        return 2

    score = min(10, 3 + len(themes) * 1.5)
    if any(t in themes for t in ("chokepoints", "energy_flows", "maritime_security", "undersea_cables")):
        score = min(10, score + 1)
    if any(t in themes for t in ("ceasefire_war_termination", "state_mediation", "nuclear_negotiations")):
        score = min(10, score + 0.5)
    return max(1, min(10, round(score)))


def has_core_region_involvement(signal: dict[str, Any]) -> bool:
    blob = _blob(signal)
    return any(token in blob for token in CORE_REGION_ACTORS)


def has_secondary_region_with_link(signal: dict[str, Any]) -> bool:
    blob = _blob(signal)
    has_secondary = any(token in blob for token in SECONDARY_REGIONS)
    has_link = any(token in blob for token in SECONDARY_LINK_TOKENS) or bool(matched_lane_themes(signal))
    return has_secondary and has_link


def is_global_strategic_override(signal: dict[str, Any]) -> bool:
    blob = _blob(signal)
    if any(marker in blob for marker in GLOBAL_OVERRIDE_MARKERS):
        return True
    consequence = infer_consequence_score(signal)
    lane = compute_strategic_lane_score(signal)
    return consequence >= 8 and lane >= 7


def compute_region_actor_boost(signal: dict[str, Any], *, live_event_score: int, consequence: int) -> float:
    """Weighted prior boost — capped so static region cannot dominate event structure."""
    boost = 0.0
    if has_core_region_involvement(signal):
        boost += CORE_REGION_BOOST
    elif has_secondary_region_with_link(signal):
        boost += SECONDARY_REGION_BOOST
    if is_global_strategic_override(signal):
        boost += GLOBAL_OVERRIDE_BOOST

    # Multi-actor diplomacy adds modest structural weight, not a hard gate
    actors = signal.get("actors")
    if isinstance(actors, list) and len(actors) >= 3:
        boost += 0.5

    max_boost = (live_event_score * 0.25 + consequence * 0.20) * 10
    return min(boost * 10, max_boost)


def classify_lane_relevance_type(signal: dict[str, Any], *, live_event_score: int = 0) -> str:
    consequence = infer_consequence_score(signal)
    lane = compute_strategic_lane_score(signal)
    momentum = int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0)

    if live_event_score >= 8 and momentum >= 8 and not has_core_region_involvement(signal):
        return "Live momentum override"
    if is_global_strategic_override(signal) or (consequence >= 8 and lane >= 7):
        return "Global strategic relevance"
    if has_core_region_involvement(signal) and lane >= 5:
        return "Direct lane relevance"
    if has_secondary_region_with_link(signal) and lane >= 4:
        return "Indirect lane relevance"
    if lane >= 6 or consequence >= 7:
        return "Global strategic relevance"
    if lane >= 4:
        return "Indirect lane relevance"
    return "Low relevance"


def build_why_xintelops_fits(signal: dict[str, Any], lane_type: str | None = None) -> str:
    lane_type = lane_type or classify_lane_relevance_type(
        signal, live_event_score=int(signal.get("live_event_score") or 0)
    )
    themes = matched_lane_themes(signal)
    theme_hint = themes[0].replace("_", " ") if themes else "strategic corridor dynamics"

    templates = {
        "Direct lane relevance": (
            f"This directly affects the core XIntelOps lane ({theme_hint}) with immediate operational consequences."
        ),
        "Indirect lane relevance": (
            "This is outside the core geography, but affects sanctions enforcement, maritime patterns, "
            "or defense supply chains relevant to Gulf and Indian Ocean flows."
        ),
        "Global strategic relevance": (
            f"This is a global chokepoint or structural shift ({theme_hint}) with immediate energy, logistics, "
            "or alignment consequences."
        ),
        "Live momentum override": (
            "This story is outside the usual lane, but its consequence and update velocity make it the "
            "dominant analyst conversation for the next 3–12 hours."
        ),
        "Low relevance": (
            "Limited strategic-lane impact at current momentum — monitor unless consequence escalates."
        ),
    }
    return templates.get(lane_type, templates["Indirect lane relevance"])


def infer_audience_relevance(signal: dict[str, Any]) -> int:
    scores = signal.get("scores") or {}
    niche = int(scores.get("niche_relevance") or 5)
    post = int(scores.get("post_worthiness") or 5)
    edge = int(scores.get("edge") or 5)
    return max(1, min(10, round((niche + post + edge) / 3)))


def should_discard_signal(signal: dict[str, Any]) -> bool:
    """Only discard when BOTH consequence and strategic-lane relevance are low."""
    consequence = infer_consequence_score(signal)
    lane = compute_strategic_lane_score(signal)
    return consequence <= 3 and lane <= 3


def is_routine_peripheral_update(signal: dict[str, Any]) -> bool:
    """Routine NATO/Ukraine-style updates without structural link — archive candidate, not hard block."""
    blob = _blob(signal)
    routine_markers = (
        "nato aid",
        "aid package",
        "military aid",
        "battlefield update",
        "front line",
        "casualty",
        "patriot delivery",
        "himars",
        "defense spending pledge",
    )
    if not any(m in blob for m in routine_markers):
        return False
    consequence = infer_consequence_score(signal)
    lane = compute_strategic_lane_score(signal)
    momentum = int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0)
    return consequence <= 5 and lane <= 4 and momentum < 7


def build_why_it_ranked_here(signal: dict[str, Any], ranking: dict[str, Any]) -> str:
    parts = [
        f"final={ranking.get('final_score', ranking.get('rank_score', 0)):.1f}",
        f"live={ranking.get('live_event_score', 0)}",
        f"consequence={ranking.get('consequence_score', 0)}",
        f"lane={ranking.get('strategic_lane_score', 0)}",
        f"region_boost={ranking.get('region_actor_boost', 0):.1f}",
    ]
    if ranking.get("repetition_penalty"):
        parts.append(f"rep_penalty=-{ranking['repetition_penalty']}")
    if ranking.get("evergreen_penalty"):
        parts.append(f"evergreen=-{ranking['evergreen_penalty']}")
    lane_type = ranking.get("lane_relevance_type", "")
    if lane_type:
        parts.append(lane_type)
    return "; ".join(parts)


def apply_region_overfitting_guardrail(
    selected: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None]:
    """
    If a low-momentum preferred-region story beats a high-consequence non-core story
    without explainable reason, the high-consequence story wins.
    """
    if not candidates:
        return selected, None

    sel_live = int(selected.get("live_event_score") or 0)
    sel_consequence = int(selected.get("consequence_score") or infer_consequence_score(selected))
    sel_lane = int(selected.get("strategic_lane_score") or compute_strategic_lane_score(selected))
    sel_core = has_core_region_involvement(selected)
    sel_momentum = int(selected.get("live_momentum") or 0)

    challengers = []
    for cand in candidates:
        if cand.get("title") == selected.get("title"):
            continue
        c_live = int(cand.get("live_event_score") or 0)
        c_consequence = int(cand.get("consequence_score") or infer_consequence_score(cand))
        c_lane = int(cand.get("strategic_lane_score") or compute_strategic_lane_score(cand))
        c_core = has_core_region_involvement(cand)

        if c_core:
            continue
        if c_consequence < 7 or c_live < 7:
            continue
        if sel_core and sel_momentum < 7 and sel_consequence < c_consequence - 1:
            challengers.append(cand)
        elif sel_core and sel_lane < c_lane and c_live >= sel_live + 2:
            challengers.append(cand)

    if not challengers:
        return selected, None

    best = max(
        challengers,
        key=lambda s: (
            s.get("final_score", s.get("rank_score", 0)),
            s.get("live_event_score", 0),
            s.get("consequence_score", 0),
        ),
    )
    reason = (
        f"Guardrail: {best.get('title', 'challenger')[:60]} wins — "
        f"consequence {best.get('consequence_score')} + live momentum outweigh static core-region preference."
    )
    return best, reason


def assign_cross_event_roles(signals: list[dict[str, Any]], immediate_title: str = "") -> list[dict[str, Any]]:
    """Label Primary / Secondary / Background / Watchlist for synthesis."""
    if not signals:
        return []

    ranked = sorted(signals, key=lambda s: s.get("rank_score", 0), reverse=True)
    roles: list[dict[str, Any]] = []

    primary_idx = 0
    if immediate_title:
        for i, sig in enumerate(ranked):
            if sig.get("title") == immediate_title:
                primary_idx = i
                break

    for i, sig in enumerate(ranked):
        if i == primary_idx:
            role = "Primary Event"
        elif i == 1 and sig.get("strategic_lane_score", compute_strategic_lane_score(sig)) >= 5:
            role = "Secondary Signal"
        elif sig.get("recommended_action") in {"MONITOR", "HIGH PRIORITY TRACKING"}:
            role = "Watchlist"
        else:
            role = "Background"
        roles.append(
            {
                "title": sig.get("title", ""),
                "role": role,
                "region": sig.get("region", ""),
                "lane_relevance_type": sig.get("lane_relevance_type")
                or classify_lane_relevance_type(sig, live_event_score=int(sig.get("live_event_score") or 0)),
                "source_package": sig.get("source_package") or [],
            }
        )
    return roles
