from __future__ import annotations

from typing import Any

from xintelops.delivery.live_events import (
    classify_freshness,
    compute_live_event_score,
    cooldown_penalty,
    freshness_immediate_eligible,
    infer_consequence_score,
    infer_update_velocity,
    is_slow_burn_analysis,
)
from xintelops.delivery.strategic_lane import (
    apply_region_overfitting_guardrail,
    build_why_it_ranked_here,
    build_why_xintelops_fits,
    classify_lane_relevance_type,
    compute_region_actor_boost,
    compute_strategic_lane_score,
    infer_audience_relevance,
    is_routine_peripheral_update,
    should_discard_signal,
)

# Legacy region tiers — used only as weak priors via strategic_lane, not hard gates
TIER1_REGIONS = frozenset(
    {
        "china", "chinese", "taiwan", "pakistan", "india", "gulf", "iran", "levant",
        "red sea", "horn of africa", "middle east", "saudi", "uae", "yemen", "israel",
        "palestine", "syria", "iraq", "qatar", "south asia", "south china sea", "indo-pacific",
    }
)

TIER2_REGIONS = frozenset(
    {
        "central asia", "caucasus", "east africa", "asean", "southeast asia", "myanmar",
        "kazakhstan", "uzbekistan", "indian ocean", "arabian sea", "somalia", "ethiopia", "djibouti",
    }
)

STRATEGIC_THEME_TOKENS = frozenset(
    {
        "port", "shipping", "maritime", "chokepoint", "undersea cable", "subsea cable", "isr", "ew",
        "electronic warfare", "drone", "uav", "rare earth", "energy infrastructure", "pipeline",
        "telecom", "sanctions evasion", "sanctions enforcement", "defense procurement",
        "sovereign wealth", "dual-use", "espionage", "influence operation", "logistics corridor",
        "supply chain", "insurance premium", "hormuz", "bab el-mandeb", "strait", "lng", "oil",
    }
)

LIVE_MOMENTUM_HIGH = frozenset(
    {
        "ceasefire", "cease-fire", "war termination", "escalation talk", "mediation", "negotiation",
        "diplomatic meeting", "emergency meeting", "sanctions relief", "sanctions enforcement",
        "missile strike", "airspace closure", "naval deployment", "strait of hormuz", "oil price",
        "lng", "multi-state", "crisis management",
    }
)

LIVE_MOMENTUM_MEDIUM = frozenset(
    {"summit", "bilateral", "trilateral", "delegation", "foreign minister", "defense minister", "procurement", "deployment", "exercise"}
)

NICHE_SOURCE_KEYWORDS = frozenset(
    {
        "china", "chinese", "taiwan", "pakistan", "india", "iran", "gulf", "qatar", "saudi", "uae",
        "yemen", "red sea", "horn", "somalia", "ethiopia", "djibouti", "central asia", "asean",
        "maritime", "shipping", "rare earth", "sanctions", "irna", "al jazeera", "sipri",
    }
)

LIVE_MOMENTUM_THRESHOLD = 8

# Scoring weights (components on 1–10 scale, multiplied by 10 for 0–100 rank scale)
W_LIVE = 0.25
W_CONSEQUENCE = 0.20
W_SOURCE = 0.15
W_VELOCITY = 0.10
W_FORECAST = 0.10
W_AUDIENCE = 0.10
W_LANE = 0.10


def _blob(signal: dict[str, Any]) -> str:
    parts = [
        signal.get("title"), signal.get("why_hamza_should_care"), signal.get("action_rationale"),
        signal.get("region"), signal.get("domain"), signal.get("source"), signal.get("summary"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def infer_niche_tier(region: str, domain: str = "", title: str = "") -> int:
    """Legacy tier hint — not used as a hard ranking gate."""
    blob = f"{region} {domain} {title}".lower()
    if any(token in blob for token in TIER1_REGIONS):
        return 1
    if any(token in blob for token in TIER2_REGIONS):
        return 2
    return 3


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

    actors = signal.get("actors")
    if isinstance(actors, list) and len(actors) >= 3:
        base = min(10, base + 2)
    return max(1, min(10, base))


def has_strategic_theme(signal: dict[str, Any]) -> bool:
    return compute_strategic_lane_score(signal) >= 5


def _confidence_score(confidence: str) -> int:
    return {"HIGH": 10, "MEDIUM": 7, "LOW": 4}.get(str(confidence or "MEDIUM").upper(), 7)


def compute_rank_score(
    signal: dict[str, Any],
    *,
    rec_history: list[dict[str, Any]] | None = None,
    has_stronger_live: bool = False,
) -> dict[str, Any]:
    scores = signal.get("scores") or {}
    forecast = int(scores.get("forecast_value") or 5)
    conf = _confidence_score(signal.get("confidence", "MEDIUM"))
    momentum = infer_live_momentum(signal)
    scores["live_momentum"] = momentum

    live_meta = compute_live_event_score(signal)
    live_event_score = live_meta["live_event_score"]
    signal["live_event_score"] = live_event_score
    freshness = classify_freshness(signal)
    signal["freshness_class"] = freshness

    consequence = infer_consequence_score(signal)
    velocity = infer_update_velocity(signal)
    audience = infer_audience_relevance(signal)
    lane_score = compute_strategic_lane_score(signal)
    region_boost = compute_region_actor_boost(
        signal, live_event_score=live_event_score, consequence=consequence
    )
    lane_type = classify_lane_relevance_type(signal, live_event_score=live_event_score)

    base = (
        live_event_score * W_LIVE * 10
        + consequence * W_CONSEQUENCE * 10
        + conf * W_SOURCE * 10
        + velocity * W_VELOCITY * 10
        + forecast * W_FORECAST * 10
        + audience * W_AUDIENCE * 10
        + lane_score * W_LANE * 10
    )

    repetition_penalty = 0
    evergreen_penalty = 0
    penalty_reason = ""

    if rec_history:
        cd_penalty, cd_reason = cooldown_penalty(signal, rec_history)
        if cd_penalty:
            repetition_penalty = cd_penalty
            penalty_reason = cd_reason

    if freshness == "EVERGREEN":
        evergreen_penalty += 30
        penalty_reason = (penalty_reason + " Evergreen content — not immediate post material.").strip()
    elif freshness == "ANALYSIS" and is_slow_burn_analysis(signal):
        evergreen_penalty += 15
        penalty_reason = (penalty_reason + " Slow-burn analysis — LinkedIn/archive candidate.").strip()
    elif not freshness_immediate_eligible(signal, has_stronger_live):
        evergreen_penalty += 20
        penalty_reason = (penalty_reason + f" Freshness {freshness} blocked for immediate post.").strip()

    if is_routine_peripheral_update(signal):
        evergreen_penalty += 15
        penalty_reason = (penalty_reason + " Routine peripheral update without structural lane link.").strip()

    total_penalty = repetition_penalty + evergreen_penalty
    final = base + region_boost - total_penalty

    use_override = live_event_score >= LIVE_MOMENTUM_THRESHOLD or momentum >= LIVE_MOMENTUM_THRESHOLD
    ranking_mode = "strategic_lane_live" if use_override else "strategic_lane_normal"

    result = {
        "base_score": round(base, 1),
        "final_score": round(final, 1),
        "rank_score": round(final, 1),
        "region_actor_boost": round(region_boost, 1),
        "strategic_lane_score": lane_score,
        "lane_relevance_type": lane_type,
        "consequence_score": consequence,
        "source_confidence": conf,
        "live_event_score": live_event_score,
        "update_velocity": velocity,
        "forecast_value": forecast,
        "audience_relevance": audience,
        "freshness_class": freshness,
        "repetition_penalty": repetition_penalty,
        "evergreen_penalty": evergreen_penalty,
        "penalty": total_penalty,
        "penalty_reason": penalty_reason,
        "live_momentum": momentum,
        "niche_tier": signal.get("niche_tier") or infer_niche_tier(
            str(signal.get("region") or ""), str(signal.get("domain") or ""), str(signal.get("title") or "")
        ),
        "ranking_mode": ranking_mode,
        "live_momentum_override": use_override,
        "live_event_priority": live_meta.get("live_event_priority", False),
        # Legacy aliases for downstream compatibility
        "tier_boost": 0,
        "theme_boost": 0,
        "actor_boost": round(region_boost, 1),
    }
    result["why_it_ranked_here"] = build_why_it_ranked_here(signal, result)
    result["why_xintelops_fits"] = build_why_xintelops_fits(signal, lane_type)
    return result


def apply_ranking_bias(
    signals: list[dict[str, Any]],
    *,
    rec_history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    prepped: list[dict[str, Any]] = []
    for sig in signals:
        item = dict(sig)
        item["niche_tier"] = item.get("niche_tier") or infer_niche_tier(
            str(item.get("region") or ""), str(item.get("domain") or ""), str(item.get("title") or "")
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
            "consequence": ranking["consequence_score"],
            "strategic_lane": ranking["strategic_lane_score"],
        }

        action = str(item.get("recommended_action") or "MONITOR").upper()
        if should_discard_signal(item) and action in {"X POST", "X THREAD"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "") + " [Auto-demoted: low consequence and low strategic-lane relevance.]"
            ).strip()
        elif is_routine_peripheral_update(item) and action in {"X POST", "X THREAD"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "") + " [Auto-demoted: routine update without lane structural link.]"
            ).strip()
        elif item.get("freshness_class") == "EVERGREEN" and action in {"X POST", "X THREAD"}:
            item["recommended_action"] = "ARCHIVE"
            item["action_rationale"] = (
                (item.get("action_rationale") or "") + " [Auto-demoted: evergreen — use LinkedIn/archive.]"
            ).strip()
        elif (
            is_slow_burn_analysis(item)
            and ranking.get("repetition_penalty", 0) >= 40
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
        if should_discard_signal(s):
            continue
        if not freshness_immediate_eligible(s, has_live):
            continue
        if s.get("recommended_action") in {"X POST", "X THREAD", "LINKEDIN"}:
            eligible.append(s)
        elif s.get("rank_score", 0) >= 55:
            eligible.append(s)
        elif s.get("live_event_score", 0) >= LIVE_MOMENTUM_THRESHOLD:
            eligible.append(s)
    return eligible


def select_immediate_post(signals: list[dict[str, Any]], agent_pick: dict[str, Any] | None) -> dict[str, Any]:
    """Highest-value post: event structure + consequence + live momentum, not static region alone."""
    eligible = _post_eligible(signals) or [s for s in signals if not should_discard_signal(s)]
    if not eligible:
        return signals[0] if signals else {}

    by_rank = sorted(
        eligible,
        key=lambda s: (s.get("final_score", s.get("rank_score", 0)), s.get("live_event_score", 0)),
        reverse=True,
    )
    top = by_rank[0]

    high_live = [s for s in by_rank if s.get("live_event_score", 0) >= 9]
    if high_live:
        confident = [s for s in high_live if str(s.get("confidence", "")).upper() != "LOW"]
        if confident:
            top = confident[0]

    agent_title = (agent_pick or {}).get("title")
    if agent_title:
        agent_sig = next((s for s in signals if s.get("title") == agent_title), None)
        if agent_sig and not should_discard_signal(agent_sig):
            if top.get("rank_score", 0) > agent_sig.get("rank_score", 0) + 5 and top.get("live_event_score", 0) >= LIVE_MOMENTUM_THRESHOLD:
                pass  # keep top
            elif agent_sig.get("live_event_score", 0) >= LIVE_MOMENTUM_THRESHOLD:
                top = agent_sig
            elif agent_sig.get("rank_score", 0) >= top.get("rank_score", 0) - 3:
                top = agent_sig

    guarded, guard_reason = apply_region_overfitting_guardrail(top, by_rank)
    if guard_reason:
        guarded["guardrail_applied"] = guard_reason
    return guarded


def select_strategic_lead(signals: list[dict[str, Any]], immediate: dict[str, Any]) -> dict[str, Any]:
    candidates = [s for s in signals if s.get("title") != immediate.get("title")]
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda s: (
            s.get("scores", {}).get("forecast_value", 0) * 2
            + s.get("scores", {}).get("edge", 0)
            + s.get("strategic_lane_score", 0)
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
    live = selected.get("live_event_score", 0)
    override = selected.get("live_momentum_override") or momentum >= LIVE_MOMENTUM_THRESHOLD

    if override and (momentum >= LIVE_MOMENTUM_THRESHOLD or live >= LIVE_MOMENTUM_THRESHOLD):
        return {
            "status": "Override Triggered",
            "reason": (
                f"Live momentum {momentum}/10, live_event_score {live}/10 — "
                f"time-sensitive consequences likely to dominate analyst conversation in the next 3–12 hours."
            ),
        }
    if momentum >= 6 or live >= 7:
        return {
            "status": "Passed",
            "reason": f"Moderate live momentum ({momentum}/10) / live_event ({live}/10) — timely signal.",
        }
    if selected.get("strategic_lane_score", 0) >= 7:
        return {
            "status": "Passed",
            "reason": "High strategic-lane score compensates for lower live momentum.",
        }
    return {
        "status": "Failed",
        "reason": "Low live momentum — verify a higher-consequence signal was not missed.",
    }


def build_strategic_lane_check(selected: dict[str, Any]) -> dict[str, Any]:
    lane_type = selected.get("lane_relevance_type") or classify_lane_relevance_type(
        selected, live_event_score=int(selected.get("live_event_score") or 0)
    )
    lane = selected.get("strategic_lane_score", 0)
    consequence = selected.get("consequence_score", 0)
    boost = selected.get("region_actor_boost", 0)

    if selected.get("guardrail_applied"):
        return {
            "status": "Guardrail Applied",
            "reason": selected["guardrail_applied"],
            "lane_relevance_type": lane_type,
        }
    if lane_type == "Live momentum override":
        return {
            "status": "Passed",
            "reason": "Live momentum override — event structure beats static region preference.",
            "lane_relevance_type": lane_type,
        }
    if lane_type in {"Direct lane relevance", "Global strategic relevance"}:
        return {
            "status": "Passed",
            "reason": f"{lane_type}: lane={lane}/10, consequence={consequence}/10, region_boost={boost}.",
            "lane_relevance_type": lane_type,
        }
    if lane_type == "Indirect lane relevance":
        return {
            "status": "Passed",
            "reason": f"Indirect lane relevance via structural themes — lane={lane}/10, region_boost={boost}.",
            "lane_relevance_type": lane_type,
        }
    return {
        "status": "Monitor",
        "reason": f"Low strategic-lane relevance (lane={lane}/10) — acceptable only if no stronger live signal exists.",
        "lane_relevance_type": lane_type,
    }


# Backward-compatible alias
def build_regional_priority_check(selected: dict[str, Any]) -> dict[str, Any]:
    return build_strategic_lane_check(selected)


def select_post_with_quota(
    signals: list[dict[str, Any]],
    agent_pick: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not signals:
        return {}, {"status": "Failed", "reason": "No verified signals."}, {"status": "Failed", "reason": "No signals."}

    immediate = select_immediate_post(signals, agent_pick)
    lane_check = build_strategic_lane_check(immediate)
    momentum = build_live_momentum_check(immediate, signals)
    return immediate, lane_check, momentum


def source_priority_score(source_name: str, region: str = "", domain: str = "") -> int:
    blob = f"{source_name} {region} {domain}".lower()
    score = 50
    if any(k in blob for k in NICHE_SOURCE_KEYWORDS):
        score += 40
    if any(k in blob for k in STRATEGIC_THEME_TOKENS):
        score += 10
    return score
