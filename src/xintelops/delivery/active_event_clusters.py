from __future__ import annotations

import re
from typing import Any

MAX_ACTIVE_CLUSTERS = 5
SIMILARITY_THRESHOLD = 0.45

EVENT_FAMILIES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"hormuz", "strait", "tanker", "iran", "irgc", "ceasefire", "kuwait", "bahrain"}), "hormuz_us_iran"),
    (frozenset({"ras laffan", "lng", "qatar", "explosion", "processing"}), "ras_laffan"),
    (frozenset({"imo", "seafarer", "evacuation", "persian gulf", "gulf"}), "gulf_seafarer_evac"),
    (frozenset({"fujian", "taiwan", "pla", "carrier", "strait"}), "fujian_taiwan"),
    (frozenset({"brahmos", "india", "uae", "missile"}), "brahmos_india_uae"),
    (frozenset({"venezuela", "earthquake", "magnitude"}), "venezuela_earthquake"),
    (frozenset({"hezbollah", "lebanon", "israel"}), "lebanon_hezbollah"),
    (frozenset({"sudan", "el obeid"}), "sudan_el_obeid"),
)


def _title_tokens(title: str) -> set[str]:
    stop = {"the", "a", "an", "as", "in", "on", "at", "to", "for", "of", "and", "with", "says", "after", "from"}
    return {w for w in re.sub(r"[^a-z0-9 ]+", " ", title.lower()).split() if len(w) > 2 and w not in stop}


def title_similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


def event_family(title: str, regions: Any = None) -> str:
    blob = str(title or "").lower()
    if isinstance(regions, list):
        blob += " " + " ".join(str(r).lower() for r in regions)
    elif regions:
        blob += " " + str(regions).lower()
    best = ""
    best_hits = 0
    for keywords, family in EVENT_FAMILIES:
        hits = sum(1 for k in keywords if k in blob)
        if hits >= 2 and hits > best_hits:
            best_hits = hits
            best = family
    return best


def _source_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    urls_a = {str(u).split("?")[0] for u in (a.get("source_urls") or []) if u}
    urls_b = {str(u).split("?")[0] for u in (b.get("source_urls") or []) if u}
    return bool(urls_a and urls_b and urls_a & urls_b)


def same_event_cluster(a: dict[str, Any], b: dict[str, Any]) -> bool:
    title_a = str(a.get("title") or "")
    title_b = str(b.get("title") or "")
    if a.get("normalized_event_key") and a.get("normalized_event_key") == b.get("normalized_event_key"):
        return True
    fam_a = event_family(title_a, a.get("regions"))
    fam_b = event_family(title_b, b.get("regions"))
    if fam_a and fam_a == fam_b:
        return True
    if title_similarity(title_a, title_b) >= SIMILARITY_THRESHOLD:
        return True
    if _source_overlap(a, b):
        return True
    return False


def cluster_active_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group near-duplicate active events; keep highest live_event_score per cluster."""
    if not events:
        return []

    sorted_events = sorted(
        events,
        key=lambda e: (int(e.get("live_event_score") or 0), str(e.get("last_seen_at") or "")),
        reverse=True,
    )
    clusters: list[list[dict[str, Any]]] = []

    for event in sorted_events:
        placed = False
        for cluster in clusters:
            if same_event_cluster(event, cluster[0]):
                cluster.append(event)
                placed = True
                break
        if not placed:
            clusters.append([event])

    display: list[dict[str, Any]] = []
    for cluster in clusters:
        lead = dict(cluster[0])
        lead["cluster_count"] = len(cluster)
        lead["cluster_members"] = cluster
        if len(cluster) > 1:
            lead["cluster_note"] = f"Clustered with: {len(cluster) - 1} related signals"
        display.append(lead)
    return display


def assess_carry_status(
    event: dict[str, Any],
    *,
    carry_status: str,
    selected_title: str = "",
    new_information_detected: bool = False,
) -> tuple[str, bool, str]:
    """
    Return display status, material_change flag, operator_decision.
    material_change is True only with proven delta or re-detection with new info.
    """
    title = str(event.get("title") or "")
    is_selected = bool(selected_title and title == selected_title)

    if carry_status == "expired":
        return "archived", False, "Ignore"
    if carry_status == "updated" or new_information_detected:
        return "updated", True, event.get("previous_action") or "MONITOR"
    if carry_status == "carried_forward" or carry_status == "cooling":
        if is_selected and new_information_detected:
            return "updated", True, event.get("previous_action") or "MONITOR"
        return "cooling", False, "Monitor Only"
    if carry_status in {"active", "new"}:
        return "new", True, event.get("previous_action") or "MONITOR"
    if is_selected and new_information_detected:
        return "updated", True, event.get("previous_action") or "MONITOR"
    return "cooling", False, "Monitor Only"
