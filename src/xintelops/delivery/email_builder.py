from __future__ import annotations

import html
from typing import Any

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.source_roles import render_source_package_html


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _render_active_live_events(active: dict[str, Any]) -> str:
    events = active.get("events") or []
    if not events:
        return f'<div class="op-line muted">{_esc(active.get("summary", "No active live events tracked this scan."))}</div>'
    rows = [f'<div class="op-line muted">{_esc(active.get("summary") or active.get("header", ""))}</div>']
    for ev in events:
        idx = ev.get("index") or len(rows)
        cluster = f'<div class="op-line"><span class="op-key">{_esc(ev.get("cluster_note"))}</span></div>' if ev.get("cluster_note") else ""
        rows.append(
            f"""
            <div class="op-line"><strong>{idx}. {_esc(ev.get('title'))}</strong></div>
            <div class="op-line"><span class="op-key">Status:</span> {_esc(ev.get('status'))}</div>
            <div class="op-line"><span class="op-key">Material change:</span> {_esc(ev.get('material_change', 'unknown'))}</div>
            <div class="op-line"><span class="op-key">Operator decision:</span> {_esc(ev.get('operator_decision') or ev.get('current_action'))}</div>
            {cluster}
            <div class="op-line"><span class="op-key">Last seen:</span> {_esc(ev.get('last_seen') or ev.get('last_update'))}</div>
            <div class="op-line"><span class="op-key">Why it matters:</span> {_esc(ev.get('why_it_matters') or ev.get('reason'))}</div>
            """
        )
    if active.get("footer"):
        rows.append(f'<div class="op-line muted">{_esc(active.get("footer"))}</div>')
    return "".join(rows)


def _render_x_post_section(x: dict[str, Any]) -> str:
    if x.get("copy_blocked"):
        return f"""
        <div class="op-section">
          <div class="op-heading">X BLOCKED — NO VALID PUBLIC COPY</div>
          <div class="op-line">Reason: {_esc(x.get('block_reason') or 'Single tweet and thread both failed final validation.')}</div>
          <div class="op-line">Fallback: Monitor only.</div>
        </div>
        """

    copy_blocks: list[str] = []
    recommended = x.get("recommended_format") or ""
    format_reason = x.get("format_reason") or ""

    if not x.get("single_blocked") and x.get("single_copy"):
        copy_blocks.append(
            f"""
        <div class="op-line"><span class="op-key">COPY THIS — SINGLE TWEET</span></div>
        <div class="post-box" style="margin-top:6px;background:#1a2332;color:#e8edf2;border-left:3px solid #4da6ff;">{_esc(x.get('single_copy')).replace(chr(10), '<br>')}</div>
        """
        )
    elif x.get("single_block_reason"):
        copy_blocks.append(
            f"""
        <div class="op-line"><span class="op-key">SINGLE TWEET BLOCKED — FINAL COPY QUALITY FAIL</span></div>
        <div class="op-line muted">Reason: {_esc(x.get('single_block_reason'))}</div>
        """
        )

    if not x.get("thread_blocked") and x.get("thread_copy"):
        copy_blocks.append(
            f"""
        <div class="op-line"><span class="op-key">COPY THIS — THREAD</span></div>
        <div class="post-box" style="margin-top:6px;background:#1a2332;color:#e8edf2;border-left:3px solid #4da6ff;">{_esc(x.get('thread_copy')).replace(chr(10), '<br>')}</div>
        """
        )
    elif x.get("thread_block_reason"):
        copy_blocks.append(
            f"""
        <div class="op-line"><span class="op-key">THREAD BLOCKED — FINAL COPY QUALITY FAIL</span></div>
        <div class="op-line muted">Reason: {_esc(x.get('thread_block_reason'))}</div>
        """
        )

    copy_block = "".join(copy_blocks)
    buckets = x.get("source_buckets") or {}
    source_html = render_source_package_html(buckets, _esc) if buckets else ""

    return f"""
      <div class="op-section">
        <div class="op-heading">X — post now</div>
        <div class="op-line"><span class="op-key">Recommended format:</span> {_esc(recommended or x.get('format'))}</div>
        <div class="op-line"><span class="op-key">Reason:</span> {_esc(format_reason)}</div>
        <div class="op-line"><span class="op-key">Action:</span> {_esc(x.get('action'))}</div>
        <div class="op-line"><span class="op-key">Post now:</span> <strong>{_esc(x.get('post_now'))}</strong></div>
        <div class="op-line"><span class="op-key">Deadline:</span> {_esc(x.get('deadline'))}</div>
        <div class="op-line"><span class="op-key">Expires:</span> {_esc(x.get('expires'))}</div>
        <div class="op-line"><span class="op-key">Why this won:</span> {_esc(x.get('why_this_won'))}</div>
        {copy_block}
        {source_html}
      </div>
    """


def _render_linkedin_decision(li: dict[str, Any]) -> str:
    copy_block = ""
    show_copy_statuses = {"Post now", "Crisis exception", "Scheduled today", "In scheduled window"}
    if li.get("copy_this") and li.get("status") in show_copy_statuses:
        copy_block = f"""
        <div class="op-line"><span class="op-key">COPY THIS:</span></div>
        <div class="post-box linkedin" style="margin-top:6px;">{_esc(li.get('copy_this', '')).replace(chr(10), '<br>')}</div>
        """
    why_no = ""
    if li.get("status") in {"Not scheduled today", "Window passed"} and not li.get("copy_this"):
        why_no = f'<div class="op-line">{_esc(li.get("todays_action"))}</div>'

    return f"""
      <div class="op-section">
        <div class="op-heading">LinkedIn Decision</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc(li.get('status'))}</div>
        <div class="op-line"><span class="op-key">Window:</span> {_esc(li.get('window'))}</div>
        <div class="op-line"><span class="op-key">Current time:</span> {_esc(li.get('current_time'))}</div>
        <div class="op-line"><span class="op-key">Action:</span> {_esc(li.get('action'))}</div>
        <div class="op-line"><span class="op-key">Topic:</span> <strong>{_esc(li.get('topic'))}</strong></div>
        <div class="op-line"><span class="op-key">Why this topic:</span> {_esc(li.get('why_this_topic'))}</div>
        {copy_block}
        {why_no}
      </div>
    """


def _render_operator_block(block: dict[str, Any]) -> str:
    x = block.get("x") or {}
    li = block.get("linkedin") or {}
    queue = block.get("queue") or {}
    immediate = (block.get("immediate_vs_strategic") or {}).get("immediate") or {}

    return f"""
    <div class="op-block">
      <div class="op-section">
        <div class="op-heading">Active Live Events</div>
        {_render_active_live_events(block.get('active_live_events') or {})}
      </div>
      <div class="op-section">
        <div class="op-heading">Best Immediate Post</div>
        <div class="op-line"><strong>{_esc(immediate.get('title'))}</strong></div>
        <div class="op-line"><span class="op-key">Action:</span> {_esc(immediate.get('action'))} · Live event {_esc(immediate.get('live_event_score'))}/10 · {_esc(immediate.get('freshness_class'))}</div>
        <div class="op-line"><span class="op-key">Lane:</span> {_esc(immediate.get('lane_relevance_type'))} · Final {_esc(immediate.get('final_score'))}</div>
        <div class="op-line"><span class="op-key">Why this fits XIntelOps:</span> {_esc(immediate.get('why_xintelops_fits'))}</div>
        <div class="op-line">{_esc(immediate.get('why'))}</div>
      </div>
      {_render_x_post_section(x)}
      {_render_linkedin_decision(li)}
      <div class="op-section">
        <div class="op-heading">Queue</div>
        <div class="op-line"><span class="op-key">Previous later-post:</span> {_esc(queue.get('previous_later_post') or 'None')}</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc(queue.get('status'))}</div>
        <div class="op-line"><span class="op-key">Reason:</span> {_esc(queue.get('reason'))}</div>
      </div>
    </div>
    """


def _render_top_signals(display: dict[str, Any]) -> str:
    if not display:
        return '<p class="muted">No ranked signals.</p>'
    parts = [
        f'<div class="muted">{_esc(display.get("header"))}</div>',
    ]
    for entry in display.get("entries") or []:
        parts.append(f'<div class="post-box" style="margin-top:8px;font-size:12px;">{_esc(entry).replace(chr(10), "<br>")}</div>')
    if display.get("footer"):
        parts.append(f'<div class="muted" style="margin-top:8px;">{_esc(display.get("footer"))}</div>')
    return "".join(parts)


def _render_journalist(journalist: dict[str, Any]) -> str:
    if journalist.get("engagement_skipped"):
        return '<p class="muted">Skip — no relevant journalist post today.</p>'
    post_url = journalist.get("target_post_url") or ""
    link = (
        f'<a href="{_esc(post_url)}" class="post-url">{_esc(post_url)}</a>'
        if post_url
        else '<span class="muted">No post URL</span>'
    )
    return f"""
      <div class="compact-line">@{_esc(journalist.get('handle'))} · {_esc(journalist.get('outlet'))}</div>
      <div class="compact-line">Post: {link}</div>
      <div class="compact-line">They said: {_esc(journalist.get('target_post_summary'))}</div>
      <div class="compact-line">Why comment: {_esc(journalist.get('why_we_comment'))}</div>
      <div class="post-box purple">{_esc(journalist.get('comment_draft', '')).replace(chr(10), '<br>')}</div>
    """


def build_email_html(result: dict[str, Any]) -> str:
    if not result.get("operator_block"):
        result = enrich_result(dict(result))
    else:
        result = dict(result)
    block = result.get("operator_block") or {}
    li_block = block.get("linkedin") or {}
    journalist = result.get("journalist") or {}
    top_display = block.get("top_signals") or result.get("top_signals_display") or {}

    tier_meta = result.get("crisis_tier_meta") or {}
    scan_tier = tier_meta.get("immediate_tier") or tier_meta.get("scan_tier") or result.get("scan_tier") or "ROUTINE"
    crisis_header = bool(tier_meta.get("crisis_detected"))

    show_linkedin = li_block.get("copy_this") and li_block.get("status") in {
        "Post now", "Crisis exception", "Scheduled today", "In scheduled window"
    }

    runtime = (result.get("runtime") or {}).get("runtime_label") or "unknown"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ background: #f4f6f9; font-family: -apple-system, 'Helvetica Neue', sans-serif; margin: 0; padding: 20px; }}
  .wrapper {{ max-width: 640px; margin: 0 auto; }}
  .header {{ background: #0a0c0f; padding: 16px 20px; border-radius: 6px 6px 0 0; }}
  .logo-mark {{ background: #2a6fdb; color: white; font-weight: 900; font-size: 12px; padding: 3px 7px; border-radius: 3px; }}
  .logo-text {{ color: #e8edf2; font-size: 12px; font-weight: 700; letter-spacing: 0.12em; margin-left: 8px; }}
  .header-sub {{ color: #6a7a8e; font-size: 11px; margin-top: 6px; font-family: monospace; }}
  .stats-bar {{ background: #13181f; padding: 10px 20px; display: flex; gap: 16px; flex-wrap: wrap; border-bottom: 1px solid #1e2733; }}
  .stat {{ font-family: monospace; font-size: 11px; color: #4a5a6e; }}
  .stat span {{ color: #4da6ff; font-weight: 700; }}
  .stat.crisis span {{ color: #e05252; }}
  .body {{ background: #fff; border-radius: 0 0 6px 6px; overflow: hidden; }}
  .section {{ padding: 16px 20px; border-bottom: 1px solid #eef1f5; }}
  .section-label {{ font-size: 9px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #8a9ab0; margin-bottom: 10px; }}
  .op-block {{ background: #0a0c0f; color: #e8edf2; border-radius: 5px; padding: 14px 16px; font-size: 12px; line-height: 1.55; }}
  .op-section {{ margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #1e2733; }}
  .op-section:last-child {{ margin-bottom: 0; padding-bottom: 0; border-bottom: none; }}
  .op-heading {{ font-weight: 800; letter-spacing: 0.08em; margin-bottom: 6px; color: #4da6ff; }}
  .op-line {{ margin-bottom: 4px; }}
  .op-key {{ color: #8a9ab0; }}
  .source-list {{ margin: 6px 0 0 16px; padding: 0; color: #c8d4e0; font-size: 11px; }}
  .post-box {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-left: 3px solid #2a6fdb; border-radius: 4px; padding: 12px 14px; font-size: 13px; line-height: 1.55; white-space: pre-wrap; }}
  .post-box.linkedin {{ border-left-color: #0a66c2; background: #f0f7ff; }}
  .post-box.purple {{ border-left-color: #7c5cbf; }}
  .compact-line {{ font-size: 12px; color: #4a5a6e; margin-bottom: 6px; }}
  .post-url {{ color: #2a6fdb; word-break: break-all; }}
  .muted {{ color: #8a9ab0; font-size: 12px; }}
  .footer {{ background: #f8f9fb; padding: 12px 20px; font-size: 10px; color: #8a9ab0; font-family: monospace; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <span class="logo-mark">XI</span><span class="logo-text">XINTELOPS OPERATOR BRIEF</span>
    <div class="header-sub">{_esc(result.get('date_pkt'))} · {_esc(result.get('time_pkt'))} · {_esc(result.get('scan_session'))}</div>
  </div>
  <div class="stats-bar">
    <div class="stat">TIER <span>{_esc(scan_tier)}</span></div>
    <div class="stat crisis">CRISIS <span>{'YES' if crisis_header else 'NO'}</span></div>
    <div class="stat">VERIFIED <span>{_esc(result.get('signals_verified', 0))}</span></div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">Operator decision block</div>
      {_render_operator_block(block)}
    </div>
    <div class="section">
      <div class="section-label">Top Signals Today</div>
      {_render_top_signals(top_display)}
    </div>
    {'<div class="section"><div class="section-label">LinkedIn — ' + _esc(li_block.get("status", "POST")) + '</div><div class="post-box linkedin">' + _esc(li_block.get("copy_this") or li_block.get("article_post", "")).replace(chr(10), "<br>") + '</div></div>' if show_linkedin else ''}
    <div class="section">
      <div class="section-label">Journalist engagement</div>
      {_render_journalist(journalist)}
    </div>
  </div>
  <div class="footer">XIntelOps Operator Brief · content_schedule queue · {_esc(result.get('scan_session'))}<br>Runtime: {_esc(runtime)}</div>
</div>
</body>
</html>"""
