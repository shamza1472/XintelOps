from __future__ import annotations

from typing import Any

ROLE_PRIMARY = "Primary Event"
ROLE_SECONDARY = "Secondary Signal"
ROLE_BACKGROUND = "Background"
ROLE_WATCHLIST = "Watchlist"

ROLE_SECTIONS = (
    ("PRIMARY EVENT SOURCES", ROLE_PRIMARY),
    ("SECONDARY SIGNAL SOURCES", ROLE_SECONDARY),
    ("BACKGROUND SOURCES", ROLE_BACKGROUND),
    ("WATCHLIST SOURCES", ROLE_WATCHLIST),
)


def _title_key(title: str) -> str:
    return str(title or "").lower()[:50]


def classify_source_role(
    source: dict[str, Any],
    *,
    primary_title: str,
    cross_roles: list[dict[str, Any]] | None = None,
    secondary_titles: set[str] | None = None,
) -> str:
    cross_roles = cross_roles or []
    secondary_titles = secondary_titles or set()
    url = str(source.get("url") or "").lower()
    why = str(source.get("why_supports") or "").lower()
    name = str(source.get("name") or "").lower()

    for role_entry in cross_roles:
        role_title = str(role_entry.get("title") or "")
        role = role_entry.get("role") or ROLE_BACKGROUND
        pkg = role_entry.get("source_package") or []
        pkg_urls = {str(p.get("url") or "").lower() for p in pkg if isinstance(p, dict)}
        if url and url in pkg_urls:
            return role
        if role_title and _title_key(role_title) in why:
            return role

    if primary_title and _title_key(primary_title) in why:
        return ROLE_PRIMARY
    if any(_title_key(t) in why or _title_key(t) in name for t in secondary_titles):
        return ROLE_SECONDARY
    if source.get("source_role"):
        return str(source["source_role"])
    return ROLE_BACKGROUND


def partition_sources_by_role(
    sources: list[dict[str, Any]],
    *,
    primary_title: str,
    cross_roles: list[dict[str, Any]] | None = None,
    secondary_titles: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {
        ROLE_PRIMARY: [],
        ROLE_SECONDARY: [],
        ROLE_BACKGROUND: [],
        ROLE_WATCHLIST: [],
    }
    seen_urls: set[str] = set()
    for src in sources:
        url = str(src.get("url") or "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        role = classify_source_role(
            src,
            primary_title=primary_title,
            cross_roles=cross_roles,
            secondary_titles=secondary_titles,
        )
        entry = {**src, "source_role": role, "used_for": src.get("used_for") or src.get("why_supports") or ""}
        buckets.setdefault(role, []).append(entry)

    # Secondary must not appear in primary
    primary_urls = {str(s.get("url") or "") for s in buckets[ROLE_PRIMARY]}
    cleaned_secondary = []
    for s in buckets[ROLE_SECONDARY]:
        if s.get("url") not in primary_urls:
            cleaned_secondary.append(s)
    buckets[ROLE_SECONDARY] = cleaned_secondary

    return buckets


def build_role_separated_package(
    result: dict[str, Any],
    signal_title: str = "",
) -> dict[str, list[dict[str, Any]]]:

    primary_title = signal_title or (
        (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    ).get("title", "")
    later_title = (result.get("content_queue") or {}).get("later_signal") or ""
    secondary_titles = {later_title} if later_title else set()
    for role in result.get("cross_event_roles") or []:
        if role.get("role") == ROLE_SECONDARY:
            secondary_titles.add(str(role.get("title") or ""))

    from xintelops.delivery.queue import build_source_package

    raw = build_source_package(result, primary_title)
    return partition_sources_by_role(
        raw,
        primary_title=primary_title,
        cross_roles=result.get("cross_event_roles") or [],
        secondary_titles=secondary_titles,
    )


def render_source_package_html(buckets: dict[str, list[dict[str, Any]]], esc_fn) -> str:
    parts = ['<div class="op-line"><span class="op-key">SOURCE PACKAGE</span></div>']
    any_source = False
    for section_label, role in ROLE_SECTIONS:
        items = buckets.get(role) or []
        if not items:
            continue
        any_source = True
        parts.append(f'<div class="op-line"><strong>{esc_fn(section_label)}</strong></div>')
        parts.append("<ul class='source-list'>")
        for src in items:
            url = src.get("url") or ""
            link = f'<a href="{esc_fn(url)}" class="post-url">{esc_fn(url)}</a>' if url else "—"
            parts.append(
                f"<li><strong>{esc_fn(src.get('name'))}</strong><br>{link}<br>"
                f"<span class='muted'>Used for: {esc_fn(src.get('used_for') or src.get('why_supports'))}</span></li>"
            )
        parts.append("</ul>")
    if not any_source:
        parts.append('<p class="muted">No source package attached.</p>')
    return "".join(parts)
