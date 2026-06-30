from __future__ import annotations

from typing import Any

CRISIS_TIERS = frozenset({"ROUTINE", "MONITOR", "PRIORITY", "LIVE_EVENT", "CRISIS", "FLASHPOINT"})
POSTING_TIERS = frozenset({"CRISIS", "FLASHPOINT"})

_STRUCTURAL_CORRIDOR_MARKERS = (
    "fee plan",
    "transit fee",
    "transit-fee",
    "fee mechanism",
    "insurance",
    "pricing chokepoint",
    "transit payment",
)
_KINETIC_MARKERS = (
    "strike",
    "strikes",
    "attack",
    "missile",
    "kinetic",
    "war",
    "ceasefire broken",
    "escalation",
    "hit ",
    "drone",
)


def _is_structural_corridor_signal(signal: dict[str, Any]) -> bool:
    if signal.get("crisis_flag"):
        return False
    title = str(signal.get("title") or "").lower()
    domain = str(signal.get("domain") or "").lower()
    if any(marker in title for marker in _STRUCTURAL_CORRIDOR_MARKERS):
        return True
    return domain in {"maritime", "shipping", "insurance"} and "hormuz" in title


def _has_kinetic_escalation(signal: dict[str, Any]) -> bool:
    title = str(signal.get("title") or "").lower()
    return any(marker in title for marker in _KINETIC_MARKERS)


def classify_signal_tier(signal: dict[str, Any], *, material_change: bool = True) -> str:
    """Delivery-layer tier label — does not alter ranking weights."""
    action = str(signal.get("canonical_action") or signal.get("recommended_action") or "").upper()
    if action in {"ARCHIVE", "IGNORE"}:
        return "ROUTINE"

    live = int(signal.get("live_event_score") or 0)
    consequence = int(signal.get("consequence_score") or 0)
    momentum = int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0)
    velocity = int(signal.get("update_velocity") or 0)
    confidence = str(signal.get("confidence") or "MEDIUM").upper()
    freshness = str(signal.get("freshness_class") or "").upper()

    if not material_change and live >= 7:
        return "MONITOR"

    is_flashpoint = (
        consequence >= 9
        and live >= 9
        and momentum >= 9
        and velocity >= 8
        and confidence == "HIGH"
        and freshness in {"BREAKING", "LIVE"}
        and material_change
    )
    if is_flashpoint:
        if _is_structural_corridor_signal(signal) and not _has_kinetic_escalation(signal):
            return "LIVE_EVENT"
        return "FLASHPOINT"

    is_crisis = (
        material_change
        and consequence >= 8
        and live >= 8
        and momentum >= 8
        and velocity >= 7
        and confidence in {"HIGH", "MEDIUM"}
        and freshness in {"BREAKING", "LIVE", "DEVELOPING"}
    )
    if is_crisis:
        if _is_structural_corridor_signal(signal) and not _has_kinetic_escalation(signal):
            return "LIVE_EVENT"
        return "CRISIS"

    if live >= 8 or momentum >= 8:
        return "LIVE_EVENT"
    if live >= 6 or consequence >= 7:
        return "PRIORITY"
    if action == "MONITOR" or live <= 4:
        return "MONITOR"
    return "ROUTINE"


def classify_scan_tier(result: dict[str, Any]) -> dict[str, Any]:
    """Scan-level tier from selected post signal and ranked signals."""
    post_decision = (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    immediate_title = (
        post_decision.get("title")
        or ((result.get("operator_decisions") or {}).get("best_immediate_post") or {}).get("title")
        or (result.get("top_signal") or {}).get("title")
    )

    tiers: list[str] = []
    tier_by_title: dict[str, str] = {}
    for sig in result.get("ranked_signals") or []:
        material = bool(sig.get("new_information_detected", False))
        if sig.get("carried_forward") and not material:
            material = False
        tier = classify_signal_tier(sig, material_change=bool(material))
        tier_by_title[str(sig.get("title") or "")] = tier
        tiers.append(tier)

    scan_max_tier = "ROUTINE"
    priority_order = ["FLASHPOINT", "CRISIS", "LIVE_EVENT", "PRIORITY", "MONITOR", "ROUTINE"]
    for t in priority_order:
        if t in tiers:
            scan_max_tier = t
            break

    immediate_tier = tier_by_title.get(str(immediate_title or ""), "ROUTINE")
    scan_tier = immediate_tier
    immediate_sig = next(
        (s for s in result.get("ranked_signals") or [] if str(s.get("title") or "") == str(immediate_title or "")),
        {},
    )
    immediate_material = bool(immediate_sig.get("new_information_detected"))
    if immediate_sig.get("carried_forward") and not immediate_material:
        immediate_material = False
    posting_exception = immediate_tier in POSTING_TIERS and immediate_material

    return {
        "scan_tier": scan_tier,
        "scan_max_tier": scan_max_tier,
        "immediate_tier": immediate_tier,
        "posting_exception": posting_exception,
        "crisis_detected": posting_exception,
        "immediate_material_change": immediate_material,
        "tier_by_title": tier_by_title,
    }


def action_for_tier(tier: str, default_action: str) -> str:
    if tier == "MONITOR" and default_action in {"X POST", "X THREAD"}:
        return "Monitor Only"
    return default_action
