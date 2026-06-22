from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

PKT = timezone(timedelta(hours=5))

FRESHNESS_CLASSES = frozenset({"BREAKING", "LIVE", "DEVELOPING", "ANALYSIS", "EVERGREEN"})

# Generic event themes — not tied to specific countries
EVENT_THEMES = frozenset(
    {
        "diplomacy",
        "ceasefire",
        "cease-fire",
        "negotiation",
        "mediation",
        "war termination",
        "escalation",
        "military",
        "maritime",
        "chokepoint",
        "strait",
        "shipping",
        "sanctions",
        "energy",
        "oil",
        "lng",
        "nuclear",
        "state visit",
        "treaty",
        "defense pact",
        "trade corridor",
        "coup",
        "regime",
        "instability",
        "espionage",
        "intelligence",
        "cyber",
        "logistics",
        "port",
        "cable",
        "airspace",
        "market",
        "procurement",
        "deployment",
        "strike",
        "missile",
        "hostage",
        "prisoner",
        "summit",
        "bilateral",
        "trilateral",
        "emergency meeting",
    }
)

SLOW_BURN_SOURCES = frozenset(
    {
        "war on the rocks",
        "carnegie",
        "csis",
        "rand.org",
        "brookings",
        "foreign affairs",
        "foreign policy",
        "think tank",
        "analysis",
        "essay",
        "commentary",
        "retrospective",
    }
)

ANALYSIS_MARKERS = frozenset(
    {
        "two years later",
        "revisit",
        "turns one",
        "why ",
        "how ",
        "lessons from",
        "in 2024",
        "policy analysis",
        "think tank",
        "commentary",
        "essay",
    }
)

# Generic state-actor detection patterns (capitalized proper nouns + known role words)
STATE_ROLE_WORDS = frozenset(
    {
        "minister",
        "president",
        "government",
        "military",
        "navy",
        "army",
        "defence",
        "defense",
        "foreign ministry",
        "embassy",
        "state department",
        "mfa",
        "parliament",
        "regime",
        "authority",
    }
)

HIGH_CONFIDENCE_SOURCES = frozenset(
    {"reuters", "ap ", "afp", "associated press", "un news", "official", "statement", "ministry", "wire"}
)

COOLDOWN_HOURS = 12
LIVE_EVENT_PERSIST_HOURS_CRISIS = 24
LIVE_EVENT_PERSIST_HOURS_HIGH = 12
IMMEDIATE_POST_COOLDOWN_HOURS = 12


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


def _infer_niche_tier(region: str, domain: str = "", title: str = "") -> int:
    from xintelops.delivery.ranking import infer_niche_tier

    return infer_niche_tier(region, domain, title)


def normalize_event_key(title: str, url: str = "") -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    words = [w for w in text.split() if len(w) > 2][:8]
    base = " ".join(words) if words else text[:80]
    if url:
        base = f"{base}|{url.split('?')[0].lower()}"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def make_event_id(normalized_key: str) -> str:
    return f"evt_{normalized_key[:16]}"


def count_event_themes(signal: dict[str, Any]) -> int:
    blob = _blob(signal)
    return sum(1 for t in EVENT_THEMES if t in blob)


def count_state_actors(signal: dict[str, Any]) -> int:
    """Estimate distinct state actors from text structure, not hardcoded country list."""
    blob = _blob(signal)
    actors = set()

    # Multi-state phrasing
    for pattern in (
        r"(\w+(?:\s+\w+)?)\s*[-–—/]\s*(\w+(?:\s+\w+)?)\s*(?:talks|mediation|summit|deal|pact|escalation|crisis)",
        r"(\w+(?:\s+\w+)?)\s+and\s+(\w+(?:\s+\w+)?)\s+(?:talks|negotiation|mediation|summit|deal)",
    ):
        for match in re.finditer(pattern, blob):
            actors.update(g.strip() for g in match.groups() if g and len(g.strip()) > 2)

    # Role-based actor mentions
    for role in STATE_ROLE_WORDS:
        if role in blob:
            actors.add(role)

    # Region field often lists actors
    region = str(signal.get("region") or "")
    for part in re.split(r"[,/;|&]+", region):
        part = part.strip().lower()
        if len(part) > 2:
            actors.add(part)

    explicit = signal.get("actors")
    if isinstance(explicit, list):
        actors.update(str(a).lower() for a in explicit if a)

    return max(len(actors), 1 if count_event_themes(signal) >= 2 else 0)


def infer_recency_score(signal: dict[str, Any]) -> int:
    scores = signal.get("scores") or {}
    if scores.get("recency") is not None:
        return max(1, min(10, int(scores.get("recency"))))

    freshness = str(signal.get("freshness_class") or "").upper()
    if freshness == "BREAKING":
        return 10
    if freshness == "LIVE":
        return 9
    if freshness == "DEVELOPING":
        return 7

    blob = _blob(signal)
    if any(w in blob for w in ("today", "hours ago", "breaking", "just announced", "live:")):
        return 9
    if any(w in blob for w in ("yesterday", "last night", "this morning")):
        return 7
    if any(w in blob for w in ("two years", "revisit", "retrospective", "turns one")):
        return 2
    return 5


def infer_consequence_score(signal: dict[str, Any]) -> int:
    scores = signal.get("scores") or {}
    if scores.get("consequence") is not None:
        return max(1, min(10, int(scores.get("consequence"))))

    blob = _blob(signal)
    high = (
        "energy",
        "oil",
        "lng",
        "hormuz",
        "chokepoint",
        "maritime",
        "sanctions",
        "nuclear",
        "market",
        "escalation",
        "strike",
        "war",
        "ceasefire",
        "airspace",
        "shipping",
        "cable",
        "port",
        "cyber",
    )
    matches = sum(1 for w in high if w in blob)
    if matches >= 3:
        return 9
    if matches >= 2:
        return 7
    if matches >= 1:
        return 5
    return 3


def infer_source_convergence(signal: dict[str, Any]) -> int:
    urls = signal.get("source_urls") or []
    citations = signal.get("source_citations") or []
    package = signal.get("source_package") or []
    count = len(urls) + len(citations) + len(package)
    if signal.get("url"):
        count += 1
    source = str(signal.get("source") or "").lower()
    if "/" in source or " and " in source or "," in source:
        count += 1
    if count >= 3:
        return 9
    if count >= 2:
        return 7
    if count >= 1:
        return 5
    return 3


def infer_update_velocity(signal: dict[str, Any]) -> int:
    scores = signal.get("scores") or {}
    if scores.get("update_velocity") is not None:
        return max(1, min(10, int(scores.get("update_velocity"))))
    freshness = str(signal.get("freshness_class") or "").upper()
    if freshness in {"BREAKING", "LIVE"}:
        return 9
    if signal.get("crisis_flag"):
        return 8
    return 5


def classify_freshness(signal: dict[str, Any]) -> str:
    explicit = str(signal.get("freshness_class") or "").upper()
    if explicit in FRESHNESS_CLASSES:
        return explicit

    blob = _blob(signal)
    source = str(signal.get("source") or "").lower()

    if signal.get("crisis_flag") or any(w in blob for w in ("breaking", "just announced", "live:", "developing now")):
        return "BREAKING" if "breaking" in blob or signal.get("crisis_flag") else "LIVE"

    if any(w in blob for w in ("negotiation", "talks", "summit", "mediation", "escalation", "strike today")):
        return "LIVE" if infer_recency_score(signal) >= 7 else "DEVELOPING"

    if any(s in source for s in SLOW_BURN_SOURCES) or any(m in blob for m in ANALYSIS_MARKERS):
        return "ANALYSIS"

    if any(w in blob for w in ("two years", "revisit", "retrospective", "policy essay", "commentary")):
        return "ANALYSIS"

    if infer_recency_score(signal) >= 7:
        return "DEVELOPING"

    if count_event_themes(signal) >= 2 and infer_recency_score(signal) <= 4:
        return "EVERGREEN"

    return "DEVELOPING"


def is_slow_burn_analysis(signal: dict[str, Any]) -> bool:
    freshness = classify_freshness(signal)
    if freshness in {"ANALYSIS", "EVERGREEN"}:
        return True
    source = str(signal.get("source") or "").lower()
    return any(s in source for s in SLOW_BURN_SOURCES)


def live_event_trigger_count(signal: dict[str, Any]) -> int:
    """Count how many of the LIVE_EVENT_PRIORITY trigger conditions are met."""
    from xintelops.delivery.strategic_lane import compute_strategic_lane_score

    conditions = 0
    blob = _blob(signal)

    if count_state_actors(signal) >= 2:
        conditions += 1

    recency = infer_recency_score(signal)
    if recency >= 7 or str(signal.get("freshness_class", "")).upper() in {"BREAKING", "LIVE"}:
        conditions += 1

    confidence = str(signal.get("confidence") or "MEDIUM").upper()
    source = str(signal.get("source") or "").lower()
    if confidence == "HIGH" or any(s in source for s in HIGH_CONFIDENCE_SOURCES):
        conditions += 1

    if infer_consequence_score(signal) >= 6:
        conditions += 1

    lane = compute_strategic_lane_score(signal)
    if lane >= 6:
        conditions += 1

    if recency >= 6 and infer_consequence_score(signal) >= 5:
        conditions += 1

    momentum = int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0)
    live_score = int(signal.get("live_event_score") or 0)
    if momentum >= 7 or live_score >= 8 or "dominate" in blob or "analyst" in blob:
        conditions += 1

    if infer_update_velocity(signal) >= 6 or signal.get("crisis_flag"):
        conditions += 1

    if infer_source_convergence(signal) >= 6:
        conditions += 1

    return conditions


def triggers_live_event_priority(signal: dict[str, Any]) -> bool:
    return live_event_trigger_count(signal) >= 3


def compute_live_event_score(signal: dict[str, Any]) -> dict[str, Any]:
    from xintelops.delivery.strategic_lane import compute_strategic_lane_score

    scores = signal.get("scores") or {}

    actor_score = min(10, count_state_actors(signal) * 2 + 2)
    lane_score = compute_strategic_lane_score(signal)
    recency = infer_recency_score(signal)
    confidence = {"HIGH": 9, "MEDIUM": 6, "LOW": 3}.get(str(signal.get("confidence") or "MEDIUM").upper(), 6)
    consequence = infer_consequence_score(signal)
    velocity = infer_update_velocity(signal)
    post = int(scores.get("post_worthiness") or 5)
    forecast = int(scores.get("forecast_value") or 5)
    niche = int(scores.get("niche_relevance") or 5)
    convergence = infer_source_convergence(signal)

    momentum = int(scores.get("live_momentum") or signal.get("live_momentum") or 5)
    if signal.get("crisis_flag"):
        momentum = max(momentum, 8)

    weighted = (
        actor_score * 0.12
        + lane_score * 0.10
        + recency * 0.15
        + confidence * 0.10
        + consequence * 0.15
        + velocity * 0.10
        + post * 0.08
        + forecast * 0.08
        + niche * 0.07
        + convergence * 0.05
    )

    live_event_score = max(1, min(10, round(weighted)))
    if triggers_live_event_priority(signal) and live_event_score < 8:
        live_event_score = min(10, live_event_score + 1)
    if signal.get("crisis_flag"):
        live_event_score = max(live_event_score, 9)

    return {
        "live_event_score": live_event_score,
        "actor_count": count_state_actors(signal),
        "consequence_score": consequence,
        "recency_score": recency,
        "source_convergence": convergence,
        "update_velocity": velocity,
        "live_event_priority": triggers_live_event_priority(signal),
        "trigger_conditions_met": live_event_trigger_count(signal),
    }


def should_persist_active_event(signal: dict[str, Any], live_event_score: int) -> bool:
    momentum = int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0)
    if signal.get("crisis_flag") or live_event_score >= 10:
        return True
    return live_event_score >= 8 or momentum >= 8


def active_until_for_signal(signal: dict[str, Any], live_event_score: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if signal.get("crisis_flag") or live_event_score >= 10:
        return now + timedelta(hours=LIVE_EVENT_PERSIST_HOURS_CRISIS)
    return now + timedelta(hours=LIVE_EVENT_PERSIST_HOURS_HIGH)


def signal_to_active_event(
    signal: dict[str, Any],
    scan_session: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    title = str(signal.get("title") or "")
    url = str(signal.get("url") or "")
    key = normalize_event_key(title, url)
    meta = compute_live_event_score(signal)
    score = meta["live_event_score"]

    urls: list[str] = []
    if url:
        urls.append(url)
    for item in signal.get("source_package") or signal.get("source_citations") or []:
        u = item.get("url") if isinstance(item, dict) else None
        if u:
            urls.append(str(u))

    return {
        "event_id": make_event_id(key),
        "normalized_event_key": key,
        "title": title,
        "actors": list({str(signal.get("region") or ""), *([str(a) for a in (signal.get("actors") or [])])}),
        "regions": [str(signal.get("region") or "Global")],
        "themes": [t for t in EVENT_THEMES if t in _blob(signal)][:8],
        "first_detected_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "active_until": active_until_for_signal(signal, score, now).isoformat(),
        "live_event_score": score,
        "momentum_score": int((signal.get("scores") or {}).get("live_momentum") or signal.get("live_momentum") or 0),
        "crisis_flag": bool(signal.get("crisis_flag")),
        "source_urls": urls[:10],
        "current_status": "active",
        "latest_update_summary": signal.get("why_hamza_should_care") or signal.get("summary") or "",
        "previous_action": signal.get("recommended_action") or signal.get("canonical_action"),
        "last_recommended_at": None,
        "times_recommended": 0,
        "resolved": False,
        "scan_session": scan_session,
        "freshness_class": classify_freshness(signal),
    }


def active_event_to_signal(event: dict[str, Any]) -> dict[str, Any]:
    """Convert persisted active event into a ranking candidate."""
    return {
        "title": event.get("title", ""),
        "source": "Active live event (carried forward)",
        "url": (event.get("source_urls") or [""])[0] if event.get("source_urls") else "",
        "region": (event.get("regions") or ["Global"])[0],
        "domain": "live_event",
        "event_date": "",
        "why_hamza_should_care": event.get("latest_update_summary") or "",
        "scores": {
            "edge": 6,
            "post_worthiness": 8,
            "forecast_value": 8,
            "niche_relevance": 8,
            "live_momentum": event.get("momentum_score") or 8,
        },
        "recommended_action": event.get("previous_action") or "X POST",
        "action_rationale": "Carried forward from active live event memory.",
        "confidence": "HIGH",
        "crisis_flag": bool(event.get("crisis_flag")),
        "freshness_class": event.get("freshness_class") or "LIVE",
        "live_event_score": event.get("live_event_score") or 8,
        "carried_forward": True,
        "event_id": event.get("event_id"),
        "normalized_event_key": event.get("normalized_event_key"),
        "active_event_status": event.get("carry_status") or "carried_forward",
    }


def merge_active_events(
    current_signals: list[dict[str, Any]],
    active_events: list[dict[str, Any]],
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Inject unresolved active events; mark statuses for operator block."""
    now = now or datetime.now(timezone.utc)
    current_keys = {normalize_event_key(str(s.get("title") or ""), str(s.get("url") or "")) for s in current_signals}
    merged = list(current_signals)
    carry_log: list[dict[str, Any]] = []

    for event in active_events:
        if event.get("resolved"):
            continue
        active_until_raw = event.get("active_until")
        if active_until_raw:
            try:
                active_until = datetime.fromisoformat(str(active_until_raw).replace("Z", "+00:00"))
                if active_until.tzinfo is None:
                    active_until = active_until.replace(tzinfo=timezone.utc)
                if active_until < now:
                    carry_log.append({**event, "carry_status": "expired", "carry_reason": "Active window elapsed."})
                    continue
            except ValueError:
                pass

        key = event.get("normalized_event_key") or normalize_event_key(str(event.get("title") or ""))
        if key in current_keys:
            carry_log.append({**event, "carry_status": "updated", "carry_reason": "Re-detected in current scan."})
            continue

        event_copy = dict(event)
        event_copy["carry_status"] = "carried_forward"
        event_copy["carry_reason"] = "High-momentum event persisted from prior scan."
        merged.append(active_event_to_signal(event_copy))
        carry_log.append(event_copy)

    return merged, carry_log


def cooldown_penalty(
    signal: dict[str, Any],
    rec_history: list[dict[str, Any]],
    now: datetime | None = None,
) -> tuple[int, str]:
    """Return rank penalty and reason for recently recommended slow-burn items."""
    now = now or datetime.now(timezone.utc)
    key = normalize_event_key(str(signal.get("title") or ""), str(signal.get("url") or ""))
    freshness = classify_freshness(signal)

    for rec in rec_history:
        rec_key = rec.get("normalized_event_key") or normalize_event_key(str(rec.get("title") or ""))
        if rec_key != key:
            continue
        rec_at_raw = rec.get("recommended_at") or rec.get("last_recommended_at")
        if not rec_at_raw:
            continue
        try:
            rec_at = datetime.fromisoformat(str(rec_at_raw).replace("Z", "+00:00"))
            if rec_at.tzinfo is None:
                rec_at = rec_at.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        hours_ago = (now - rec_at).total_seconds() / 3600
        if hours_ago > IMMEDIATE_POST_COOLDOWN_HOURS:
            continue

        if freshness in {"ANALYSIS", "EVERGREEN"} or is_slow_burn_analysis(signal):
            return 50, f"Already recommended {hours_ago:.0f}h ago — slow-burn cooldown."
        if not signal.get("new_information_detected") and hours_ago < COOLDOWN_HOURS:
            return 25, f"Already recommended {hours_ago:.0f}h ago without new information."

    return 0, ""


def freshness_immediate_eligible(signal: dict[str, Any], has_stronger_live: bool) -> bool:
    freshness = classify_freshness(signal)
    if freshness in {"BREAKING", "LIVE"}:
        return True
    if freshness == "DEVELOPING":
        return True
    if freshness == "ANALYSIS":
        return not has_stronger_live and not is_slow_burn_analysis(signal)
    return False


def build_active_live_event_block(carry_log: list[dict[str, Any]], selected_title: str = "") -> dict[str, Any]:
    if not carry_log:
        return {"events": [], "summary": "No active live events carried from prior scans."}

    events = []
    for ev in carry_log:
        status = ev.get("carry_status") or ev.get("current_status") or "active"
        if selected_title and ev.get("title") == selected_title and status == "carried_forward":
            status = "carried_forward"
        events.append(
            {
                "title": ev.get("title", ""),
                "status": status,
                "active_until": ev.get("active_until", ""),
                "last_update": ev.get("latest_update_summary") or ev.get("carry_reason") or "",
                "current_action": ev.get("previous_action") or "MONITOR",
                "reason": ev.get("carry_reason") or ev.get("latest_update_summary") or "",
                "live_event_score": ev.get("live_event_score"),
            }
        )
    return {"events": events, "summary": f"{len(events)} active live event(s) tracked."}


def parse_pkt_scan_time(result: dict[str, Any]) -> datetime:
    date_pkt = str(result.get("date_pkt") or datetime.now(PKT).strftime("%Y-%m-%d"))
    time_pkt = str(result.get("time_pkt") or "00:00 PKT").replace(" PKT", "").strip()
    try:
        return datetime.strptime(f"{date_pkt} {time_pkt}", "%Y-%m-%d %H:%M").replace(tzinfo=PKT)
    except ValueError:
        return datetime.now(PKT)
