from __future__ import annotations

import html
from typing import Any

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.operator import _action_tag_class


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _render_source_package(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return '<p class="muted">No source package attached.</p>'
    rows = []
    for src in sources:
        url = src.get("url") or ""
        link = f'<a href="{_esc(url)}" class="post-url">{_esc(url)}</a>' if url else "—"
        rows.append(
            f"<li><strong>{_esc(src.get('name'))}</strong> · tier {_esc(src.get('tier'))} · "
            f"{_esc(src.get('published_date'))}<br>{link}<br>"
            f"<span class='muted'>{_esc(src.get('why_supports'))}</span></li>"
        )
    return f"<ul class='source-list'>{''.join(rows)}</ul>"


def _render_active_live_events(active: dict[str, Any]) -> str:
    events = active.get("events") or []
    if not events:
        return f'<div class="op-line muted">{_esc(active.get("summary", "No active live events."))}</div>'
    rows = []
    for ev in events:
        rows.append(
            f"""
            <div class="op-line"><strong>{_esc(ev.get('title'))}</strong></div>
            <div class="op-line"><span class="op-key">Status:</span> {_esc(ev.get('status'))}</div>
            <div class="op-line"><span class="op-key">Active until:</span> {_esc(ev.get('active_until'))}</div>
            <div class="op-line"><span class="op-key">Last update:</span> {_esc(ev.get('last_update'))}</div>
            <div class="op-line"><span class="op-key">Action:</span> {_esc(ev.get('current_action'))}</div>
            <div class="op-line"><span class="op-key">Reason:</span> {_esc(ev.get('reason'))}</div>
            """
        )
    return "".join(rows)


def _render_linkedin_decision(li: dict[str, Any]) -> str:
    copy_block = ""
    if li.get("copy_this") and li.get("status") in {"Post now", "Crisis exception", "Scheduled today"}:
        copy_block = f"""
        <div class="op-line"><span class="op-key">COPY THIS:</span></div>
        <div class="post-box linkedin" style="margin-top:6px;">{_esc(li.get('copy_this', '')).replace(chr(10), '<br>')}</div>
        """
    why_no = ""
    if not li.get("topic") and li.get("status") == "Not scheduled today":
        why_no = f'<div class="op-line">{_esc(li.get("todays_action"))}</div>'

    return f"""
      <div class="op-section">
        <div class="op-heading">LinkedIn Decision</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc(li.get('status'))}</div>
        <div class="op-line"><span class="op-key">Window:</span> {_esc(li.get('window'))}</div>
        <div class="op-line"><span class="op-key">Current time:</span> {_esc(li.get('current_time'))}</div>
        <div class="op-line"><span class="op-key">Action:</span> {_esc(li.get('action'))}</div>
        <div class="op-line"><span class="op-key">Topic:</span> <strong>{_esc(li.get('topic'))}</strong></div>
        <div class="op-line"><span class="op-key">Format:</span> {_esc(li.get('format'))}</div>
        <div class="op-line"><span class="op-key">Why this topic:</span> {_esc(li.get('why_this_topic'))}</div>
        {copy_block}
        <div class="op-line"><span class="op-key">Source package:</span></div>
        {_render_source_package(li.get('source_package') or [])}
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
        <div class="op-line"><span class="op-key">Action:</span> {_esc(immediate.get('action'))} · Live event {_esc(immediate.get('live_event_score'))}/10 · Momentum {_esc(immediate.get('live_momentum'))}/10 · {_esc(immediate.get('freshness_class'))}</div>
        <div class="op-line">{_esc(immediate.get('why'))}</div>
      </div>
      <div class="op-section">
        <div class="op-heading">Best Strategic Lead</div>
        <div class="op-line"><strong>{_esc((block.get('immediate_vs_strategic') or {}).get('strategic', {}).get('title'))}</strong></div>
        <div class="op-line">{_esc((block.get('immediate_vs_strategic') or {}).get('strategic', {}).get('why'))}</div>
      </div>
      <div class="op-section">
        <div class="op-heading">Best Archive Signal</div>
        <div class="op-line"><strong>{_esc((block.get('immediate_vs_strategic') or {}).get('archive', {}).get('title'))}</strong></div>
        <div class="op-line">{_esc((block.get('immediate_vs_strategic') or {}).get('archive', {}).get('why'))}</div>
      </div>
      <div class="op-section">
        <div class="op-heading">X — post now</div>
        <div class="op-line"><span class="op-key">Action:</span> {_esc(x.get('action'))}</div>
        <div class="op-line"><span class="op-key">Format:</span> {_esc(x.get('format'))}</div>
        <div class="op-line"><span class="op-key">Post now:</span> <strong>{_esc(x.get('post_now'))}</strong></div>
        <div class="op-line"><span class="op-key">Deadline:</span> {_esc(x.get('deadline'))}</div>
        <div class="op-line"><span class="op-key">Expires:</span> {_esc(x.get('expires'))}</div>
        <div class="op-line"><span class="op-key">Why this won:</span> {_esc(x.get('why_this_won'))}</div>
        <div class="op-line"><span class="op-key">Source package:</span></div>
        {_render_source_package(x.get('source_package') or [])}
      </div>
      {_render_linkedin_decision(li)}
      <div class="op-section">
        <div class="op-heading">Live Momentum Check</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc((block.get('live_momentum') or {}).get('status'))}</div>
        <div class="op-line"><span class="op-key">Reason:</span> {_esc((block.get('live_momentum') or {}).get('reason'))}</div>
      </div>
      <div class="op-section">
        <div class="op-heading">Regional Priority Check</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc((block.get('regional_priority') or {}).get('status'))}</div>
        <div class="op-line"><span class="op-key">Reason:</span> {_esc((block.get('regional_priority') or {}).get('reason'))}</div>
      </div>
      <div class="op-section">
        <div class="op-heading">Queue</div>
        <div class="op-line"><span class="op-key">Previous later-post:</span> {_esc(queue.get('previous_later_post') or 'None')}</div>
        <div class="op-line"><span class="op-key">Status:</span> {_esc(queue.get('status'))}</div>
        <div class="op-line"><span class="op-key">Reason:</span> {_esc(queue.get('reason'))}</div>
      </div>
    </div>
    """


def _render_ranked_signals(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return '<p class="muted">No ranked signals.</p>'
    rows = []
    for sig in signals:
        scores = sig.get("scores") or {}
        action = sig.get("canonical_action") or sig.get("recommended_action") or "MONITOR"
        rows.append(
            f"""
            <div class="rank-row">
              <div class="rank-num">{_esc(sig.get('rank'))}</div>
              <div class="rank-body">
                <div class="rank-title">{_esc(sig.get('title'))}</div>
                <div class="rank-why">{_esc(sig.get('why_hamza_should_care'))}</div>
                <div class="score-line">
                  Rank {_esc(sig.get('rank_score'))} · Live event {_esc(sig.get('live_event_score'))} · {_esc(sig.get('freshness_class'))} ·
                  Momentum {_esc(scores.get('live_momentum'))} · Edge {_esc(scores.get('edge'))} ·
                  Post {_esc(scores.get('post_worthiness'))} · Forecast {_esc(scores.get('forecast_value'))} ·
                  Niche {_esc(scores.get('niche_relevance'))} · T{_esc(sig.get('niche_tier'))}
                  {' · 🚨 LIVE' if sig.get('live_momentum_override') else ''}
                  {' · ↩ carried' if sig.get('carried_forward') else ''}
                </div>
                <span class="tag {_action_tag_class(action)}">{_esc(action)}</span>
              </div>
            </div>
            """
        )
    return "".join(rows)


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
    x_block = block.get("x") or {}
    li_block = block.get("linkedin") or {}
    ranked = result.get("ranked_signals") or []
    journalist = result.get("journalist") or {}

    draft = x_block.get("draft") or result.get("x_post") or ""
    show_linkedin = li_block.get("copy_this") and li_block.get("status") in {
        "Post now", "Crisis exception", "Scheduled today"
    }

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
  .rank-row {{ display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f2f5; }}
  .rank-num {{ font-size: 16px; font-weight: 800; color: #2a6fdb; min-width: 20px; font-family: monospace; }}
  .rank-title {{ font-size: 13px; font-weight: 600; }}
  .rank-why {{ font-size: 12px; color: #5a6a7e; margin: 3px 0 5px; }}
  .score-line {{ font-size: 10px; color: #8a9ab0; font-family: monospace; margin-bottom: 5px; }}
  .tag {{ font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
  .tag-action-post {{ background: #e8f0fe; color: #2a6fdb; }}
  .tag-action-linkedin {{ background: #f0f7ff; color: #1a5fbf; }}
  .tag-action-track {{ background: #fde8e8; color: #b03030; }}
  .tag-action-monitor {{ background: #fef6e8; color: #b87a00; }}
  .tag-action-ignore {{ background: #f4f6f9; color: #8a9ab0; }}
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
    <span class="logo-mark">XI</span><span class="logo-text">OPERATOR BRIEF</span>
    <div class="header-sub">{_esc(result.get('date_pkt'))} · {_esc(result.get('time_pkt'))} · {_esc(result.get('scan_session'))}</div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">Operator decision block — read first</div>
      {_render_operator_block(block)}
    </div>
    <div class="section">
      <div class="section-label">Top signals today</div>
      {_render_ranked_signals(ranked)}
    </div>
    {'<div class="section"><div class="section-label">Draft — ' + _esc(x_block.get("format", "POST")) + '</div><div class="post-box">' + _esc(draft).replace(chr(10), "<br>") + '</div>' + _render_source_package(x_block.get("source_package") or []) + '</div>' if draft else ''}
    {'<div class="section"><div class="section-label">LinkedIn — ' + _esc(li_block.get("status", "POST")) + '</div><div class="post-box linkedin">' + _esc(li_block.get("copy_this") or li_block.get("article_post", "")).replace(chr(10), "<br>") + '</div>' + _render_source_package(li_block.get("source_package") or []) + '</div>' if show_linkedin else ''}
    <div class="section">
      <div class="section-label">Journalist engagement</div>
      {_render_journalist(journalist)}
    </div>
  </div>
  <div class="footer">Operator layer · content_schedule queue · {_esc(result.get('scan_session'))}</div>
</div>
</body>
</html>"""
