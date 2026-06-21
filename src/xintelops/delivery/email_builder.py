from __future__ import annotations

import html
from typing import Any

from xintelops.delivery.cadence import enrich_result
from xintelops.delivery.operator import _action_tag_class


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _format_x_content(result: dict[str, Any]) -> tuple[str, str]:
    post_action = (
        (result.get("operator_decisions") or {}).get("one_signal_to_post") or {}
    ).get("action", "")
    post_format = str(result.get("post_format") or "SHORT POST").upper()
    is_thread = post_action == "X THREAD" or post_format == "THREAD"

    if is_thread:
        thread = result.get("x_thread")
        if isinstance(thread, list) and thread:
            numbered = [f"{idx}/ {tweet}" for idx, tweet in enumerate(thread, 1)]
            return "🧵 THREAD", "\n\n".join(numbered)
        return "🧵 THREAD", str(thread or result.get("x_post") or "")
    return "📱 SINGLE TWEET", str(result.get("x_post") or "")


def _render_ranked_signals(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return '<p class="muted">No ranked signals — regenerate scan.</p>'

    rows = []
    for sig in signals:
        scores = sig.get("scores") or {}
        action = sig.get("recommended_action") or "MONITOR"
        tag_class = _action_tag_class(action)
        rows.append(
            f"""
            <div class="rank-row">
              <div class="rank-num">{_esc(sig.get('rank'))}</div>
              <div class="rank-body">
                <div class="rank-title">{_esc(sig.get('title'))}</div>
                <div class="rank-why">{_esc(sig.get('why_hamza_should_care'))}</div>
                <div class="score-line">
                  Edge <strong>{_esc(scores.get('edge'))}</strong> ·
                  Post <strong>{_esc(scores.get('post_worthiness'))}</strong> ·
                  Forecast <strong>{_esc(scores.get('forecast_value'))}</strong> ·
                  Niche <strong>{_esc(scores.get('niche_relevance'))}</strong>
                  · T{_esc(sig.get('niche_tier'))}
                </div>
                <span class="tag {tag_class}">{_esc(action)}</span>
              </div>
            </div>
            """
        )
    return "".join(rows)


def _render_operator_decisions(decisions: dict[str, Any]) -> str:
    post = decisions.get("one_signal_to_post") or {}
    watch = decisions.get("one_signal_to_watch") or {}
    missing = decisions.get("one_signal_everyone_missing") or {}

    return f"""
    <div class="decision-grid">
      <div class="decision-card post">
        <div class="decision-label">Post now</div>
        <div class="decision-title">{_esc(post.get('title'))}</div>
        <div class="decision-action">{_esc(post.get('action'))}</div>
        <div class="decision-why">{_esc(post.get('why'))}</div>
      </div>
      <div class="decision-card watch">
        <div class="decision-label">Watch 7–30 days</div>
        <div class="decision-title">{_esc(watch.get('title'))}</div>
        <div class="decision-why">{_esc(watch.get('why'))}</div>
      </div>
      <div class="decision-card edge">
        <div class="decision-label">Everyone is missing</div>
        <div class="decision-title">{_esc(missing.get('title'))}</div>
        <div class="decision-action">Edge {_esc(missing.get('edge_score'))}/10</div>
        <div class="decision-why">{_esc(missing.get('why'))}</div>
      </div>
    </div>
    """


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
      <div class="compact-line"><strong>@{_esc(journalist.get('handle'))}</strong> · {_esc(journalist.get('outlet'))}</div>
      <div class="compact-line">Post: {link}</div>
      <div class="compact-line">They said: {_esc(journalist.get('target_post_summary'))}</div>
      <div class="compact-line">Why comment: {_esc(journalist.get('why_we_comment'))}</div>
      <div class="post-box purple">{_esc(journalist.get('comment_draft', '')).replace(chr(10), '<br>')}</div>
    """


def build_email_html(result: dict[str, Any]) -> str:
    result = enrich_result(dict(result))
    ranked = result.get("ranked_signals") or []
    decisions = result.get("operator_decisions") or {}
    journalist = result.get("journalist") or {}
    cadence = result.get("posting_cadence") or {}
    post_action = str((decisions.get("one_signal_to_post") or {}).get("action") or "")

    x_label, x_content = _format_x_content(result)
    show_x = post_action in {"X POST", "X THREAD"} and (result.get("x_post") or result.get("x_thread"))
    show_linkedin = result.get("linkedin_today") and result.get("linkedin_post")
    post_count = sum(
        1 for s in ranked if s.get("recommended_action") in {"X POST", "X THREAD", "LINKEDIN"}
    )
    ignore_count = sum(1 for s in ranked if s.get("recommended_action") in {"IGNORE", "ARCHIVE"})

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
  .stats {{ background: #13181f; padding: 8px 20px; display: flex; gap: 16px; flex-wrap: wrap; font-family: monospace; font-size: 10px; color: #6a7a8e; }}
  .stats span {{ color: #4da6ff; }}
  .body {{ background: #fff; border-radius: 0 0 6px 6px; overflow: hidden; }}
  .section {{ padding: 16px 20px; border-bottom: 1px solid #eef1f5; }}
  .section-label {{ font-size: 9px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #8a9ab0; margin-bottom: 10px; }}
  .decision-grid {{ display: grid; gap: 10px; }}
  .decision-card {{ border-radius: 5px; padding: 12px 14px; border: 1px solid #e0e5ed; }}
  .decision-card.post {{ border-left: 3px solid #2a6fdb; background: #f5f9ff; }}
  .decision-card.watch {{ border-left: 3px solid #d4a017; background: #fffbf0; }}
  .decision-card.edge {{ border-left: 3px solid #22c97a; background: #f5fdf9; }}
  .decision-label {{ font-size: 9px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #8a9ab0; }}
  .decision-title {{ font-size: 14px; font-weight: 600; color: #1a2332; margin: 4px 0; }}
  .decision-action {{ font-size: 11px; font-weight: 700; color: #2a6fdb; font-family: monospace; margin-bottom: 4px; }}
  .decision-why {{ font-size: 12px; color: #4a5a6e; line-height: 1.5; }}
  .rank-row {{ display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f2f5; }}
  .rank-row:last-child {{ border-bottom: none; }}
  .rank-num {{ font-size: 18px; font-weight: 800; color: #2a6fdb; min-width: 24px; font-family: monospace; }}
  .rank-title {{ font-size: 13px; font-weight: 600; color: #1a2332; }}
  .rank-why {{ font-size: 12px; color: #5a6a7e; margin: 3px 0 6px; line-height: 1.45; }}
  .score-line {{ font-size: 11px; color: #8a9ab0; font-family: monospace; margin-bottom: 6px; }}
  .tag {{ font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
  .tag-action-post {{ background: #e8f0fe; color: #2a6fdb; }}
  .tag-action-linkedin {{ background: #f0f7ff; color: #1a5fbf; }}
  .tag-action-track {{ background: #fde8e8; color: #b03030; }}
  .tag-action-monitor {{ background: #fef6e8; color: #b87a00; }}
  .tag-action-ignore {{ background: #f4f6f9; color: #8a9ab0; }}
  .post-box {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-left: 3px solid #2a6fdb; border-radius: 4px; padding: 12px 14px; font-size: 13px; line-height: 1.55; white-space: pre-wrap; }}
  .post-box.green {{ border-left-color: #22c97a; }}
  .post-box.purple {{ border-left-color: #7c5cbf; }}
  .post-box.linkedin {{ border-left-color: #0a66c2; background: #f0f7ff; }}
  .compact-line {{ font-size: 12px; color: #4a5a6e; margin-bottom: 6px; line-height: 1.5; }}
  .cadence-line {{ font-size: 12px; color: #4a5a6e; margin-bottom: 6px; }}
  .cadence-line strong {{ color: #2a3a4a; }}
  .post-url {{ color: #2a6fdb; word-break: break-all; }}
  .muted {{ color: #8a9ab0; font-size: 12px; }}
  .footer {{ background: #f8f9fb; padding: 12px 20px; font-size: 10px; color: #8a9ab0; font-family: monospace; display: flex; justify-content: space-between; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <span class="logo-mark">XI</span><span class="logo-text">XINTELOPS OPERATOR BRIEF</span>
    <div class="header-sub">{_esc(result.get('date_pkt'))} · {_esc(result.get('time_pkt'))} · {_esc(result.get('scan_session'))}</div>
  </div>
  <div class="stats">
    <div>VERIFIED <span>{_esc(result.get('signals_verified', len(ranked)))}</span></div>
    <div>POST <span>{post_count}</span></div>
    <div>IGNORE <span>{ignore_count}</span></div>
    <div>CRISIS <span>{'YES' if result.get('crisis_detected') else 'NO'}</span></div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">Operator decisions — read this first</div>
      {_render_operator_decisions(decisions)}
    </div>
    <div class="section">
      <div class="section-label">Top signals today</div>
      {_render_ranked_signals(ranked)}
    </div>
    {'<div class="section"><div class="section-label">📡 Post now — ' + _esc(x_label) + '</div><div class="post-box">' + _esc(x_content).replace(chr(10), '<br>') + '</div></div>' if show_x else ''}
    {'<div class="section"><div class="section-label">🔍 Secondary angle</div><div class="post-box green">' + _esc(result.get('what_most_missed', '')).replace(chr(10), '<br>') + '</div></div>' if result.get('what_most_missed') else ''}
    {'<div class="section"><div class="section-label">💼 LinkedIn — post today</div><div class="post-box linkedin">' + _esc(result.get('linkedin_post', '')).replace(chr(10), '<br>') + '</div></div>' if show_linkedin else ''}
    <div class="section">
      <div class="section-label">💬 Journalist engagement</div>
      {_render_journalist(journalist)}
    </div>
    <div class="section">
      <div class="section-label">⏱ When to act</div>
      <div class="cadence-line"><strong>Now:</strong> {_esc(cadence.get('x_primary'))}</div>
      <div class="cadence-line"><strong>Later:</strong> {_esc(cadence.get('x_secondary'))}</div>
      <div class="cadence-line"><strong>Engage:</strong> {_esc(cadence.get('x_engagement'))}</div>
      <div class="cadence-line"><strong>LinkedIn:</strong> {_esc(cadence.get('linkedin'))}</div>
    </div>
  </div>
  <div class="footer">
    <span>Operator mode vNext · Supabase saved</span>
    <span>{_esc(str(result.get('scan_session', ''))[-8:])}</span>
  </div>
</div>
</body>
</html>"""
