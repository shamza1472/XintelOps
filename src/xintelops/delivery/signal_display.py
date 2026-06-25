from __future__ import annotations

import re
from typing import Any

from xintelops.delivery.crisis_tier import action_for_tier, classify_signal_tier
from xintelops.delivery.live_events import normalize_event_key
from xintelops.delivery.queue import format_pkt, parse_scan_time_pkt

MAX_TOP_SIGNALS = 10


def _title_tokens(title: str) -> set[str]:
    stop = {"the", "a", "an", "as", "in", "on", "at", "to", "for", "of", "and", "with", "says", "after"}
    return {w for w in re.sub(r"[^a-z0-9 ]+", " ", title.lower()).split() if len(w) > 2 and w not in stop}


def _similarity(a: str, b: str) -> float:
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


def cluster_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group near-duplicate signals; keep highest rank per cluster."""
    if not signals:
        return []

    sorted_sigs = sorted(signals, key=lambda s: s.get("rank_score", 0), reverse=True)
    clusters: list[list[dict[str, Any]]] = []

    for sig in sorted_sigs:
        key = sig.get("normalized_event_key") or normalize_event_key(str(sig.get("title") or ""), str(sig.get("url") or ""))
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            rep_key = rep.get("normalized_event_key") or normalize_event_key(str(rep.get("title") or ""), str(rep.get("url") or ""))
            if key == rep_key:
                cluster.append(sig)
                placed = True
                break
            if _similarity(str(sig.get("title") or ""), str(rep.get("title") or "")) >= 0.45:
                cluster.append(sig)
                placed = True
                break
        if not placed:
            clusters.append([sig])

    display: list[dict[str, Any]] = []
    for cluster in clusters:
        lead = cluster[0]
        lead = dict(lead)
        lead["cluster_count"] = len(cluster)
        if len(cluster) > 1:
            lead["cluster_note"] = f"Clustered with: {len(cluster) - 1} related signals"
        display.append(lead)
    return display


def prepare_top_signals(result: dict[str, Any], limit: int = MAX_TOP_SIGNALS) -> dict[str, Any]:
    ranked = list(result.get("ranked_signals") or [])
    total = len(ranked)
    clustered = cluster_signals(ranked)
    top = clustered[:limit]
    return {
        "signals": top,
        "total_eligible": total,
        "shown": len(top),
        "truncated": total > limit,
    }


def _role_label(sig: dict[str, Any], cross_roles: list[dict[str, Any]] | None) -> str:
    title = str(sig.get("title") or "")
    for entry in cross_roles or []:
        if entry.get("title") == title:
            role = str(entry.get("role") or "")
            return role.replace(" Event", "").replace(" Signal", "")
    return "Background"


def _one_line_why(sig: dict[str, Any]) -> str:
    why = sig.get("why_it_ranked_here") or sig.get("why_hamza_should_care") or ""
    line = str(why).split(";")[0].split(".")[0].strip()
    return (line[:140] + "…") if len(line) > 140 else line


def format_top_signal_entry(
    sig: dict[str, Any],
    idx: int,
    *,
    cross_roles: list[dict[str, Any]] | None = None,
    tier_by_title: dict[str, str] | None = None,
    scan_time=None,
) -> str:
    tier_by_title = tier_by_title or {}
    title = str(sig.get("title") or "")
    tier = tier_by_title.get(title) or classify_signal_tier(sig)
    action = sig.get("canonical_action") or sig.get("recommended_action") or "MONITOR"
    display_action = action_for_tier(tier, str(action))
    if tier == "MONITOR" and not sig.get("new_information_detected") and sig.get("carried_forward"):
        display_action = "Monitor Only"

    expires = ""
    if scan_time is not None:
        from datetime import timedelta

        expires = format_pkt(scan_time + timedelta(hours=3))

    lines = [
        f"{idx}. {title}",
        f"Tier: {tier}",
        f"Action: {display_action}",
        f"Why it ranks: {_one_line_why(sig)}",
        f"Source role: {_role_label(sig, cross_roles)}",
    ]
    if expires:
        lines.append(f"Expires: {expires}")
    if sig.get("cluster_note"):
        lines.append(str(sig["cluster_note"]))
    return "\n".join(lines)


def format_top_signals_block(result: dict[str, Any]) -> dict[str, Any]:
    prep = prepare_top_signals(result)
    cross_roles = result.get("cross_event_roles") or []
    tier_by_title = (result.get("crisis_tier_meta") or {}).get("tier_by_title") or {}
    scan_time = parse_scan_time_pkt(result)

    entries = []
    for i, sig in enumerate(prep["signals"], 1):
        entries.append(
            format_top_signal_entry(
                sig, i, cross_roles=cross_roles, tier_by_title=tier_by_title, scan_time=scan_time
            )
        )

    if prep["truncated"]:
        header = f"Showing top {prep['shown']} of {prep['total_eligible']} eligible signals."
        footer = "Additional signals archived in DB. Not shown to keep operator queue clean."
    elif prep["shown"] == 0:
        header = "Showing 0 eligible signals."
        footer = ""
    else:
        header = f"Showing {prep['shown']} eligible signals."
        footer = ""

    return {
        "header": header,
        "footer": footer,
        "entries": entries,
        "text": header + "\n\n" + "\n\n".join(entries) + ("\n\n" + footer if footer else ""),
    }
