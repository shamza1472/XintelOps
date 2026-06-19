from __future__ import annotations

import html
from typing import Any

from xintelops.delivery.cadence import enrich_result


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _render_citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return '<p class="muted">No source URLs captured — check top_signal.url in scan output.</p>'
    rows = []
    for item in citations:
        url = item.get("url") or ""
        name = item.get("name") or item.get("source") or "Source"
        pub = item.get("published_date") or item.get("event_date") or "date unknown"
        tier = item.get("tier") or ""
        link = f'<a href="{_esc(url)}" class="post-url">{_esc(url)}</a>' if url else "—"
        rows.append(
            f"<li><strong>{_esc(name)}</strong> · tier {_esc(tier)} · event {_esc(pub)}<br>{link}</li>"
        )
    return f"<ul class='citation-list'>{''.join(rows)}</ul>"


def _format_x_content(result: dict[str, Any]) -> tuple[str, str]:
    post_format = str(result.get("post_format") or "SHORT POST").upper()
    if post_format == "THREAD":
        thread = result.get("x_thread")
        if isinstance(thread, list) and thread:
            numbered = [f"{idx}/ {tweet}" for idx, tweet in enumerate(thread, 1)]
            return "🧵 THREAD", "\n\n".join(numbered)
        raw = str(thread or result.get("x_post") or "")
        return "🧵 THREAD", raw
    return "📱 SINGLE TWEET", str(result.get("x_post") or "")


def _render_journalist_section(journalist: dict[str, Any], day_of_week: str) -> str:
    if journalist.get("engagement_skipped"):
        return (
            '<p class="muted">No suitable original journalist post found this scan — '
            "skip engagement today.</p>"
        )

    post_url = journalist.get("target_post_url") or journalist.get("post_url") or ""
    post_summary = journalist.get("target_post_summary") or journalist.get("post_summary") or ""
    why_comment = journalist.get("why_we_comment") or journalist.get("engagement_rationale") or ""
    post_link = (
        f'<a href="{_esc(post_url)}" class="post-url">{_esc(post_url)}</a>'
        if post_url
        else '<span class="muted">No post URL captured — regenerate scan</span>'
    )

    return f"""
      <div class="journalist-name">{_esc(journalist.get("name"))}</div>
      <div class="journalist-handle">@{_esc(journalist.get("handle"))} · {_esc(journalist.get("outlet"))} · Category {_esc(journalist.get("category"))} · {_esc(day_of_week)}</div>
      <h4>Their post (comment here):</h4>
      <div class="journalist-hint">{post_link}</div>
      <h4>What they said:</h4>
      <div class="journalist-hint">{_esc(post_summary).replace(chr(10), "<br>")}</div>
      <h4>Why we're commenting:</h4>
      <div class="journalist-hint">{_esc(why_comment).replace(chr(10), "<br>")}</div>
      <h4>Your comment:</h4>
      <div class="post-box purple">{_esc(journalist.get("comment_draft", "")).replace(chr(10), "<br>")}</div>
    """


def build_email_html(result: dict[str, Any]) -> str:
    result = enrich_result(dict(result))
    signal = result.get("top_signal", {}) or {}
    journalist = result.get("journalist", {}) or {}
    cadence = result.get("posting_cadence") or {}
    citations = result.get("source_citations") or []

    crisis_flag = bool(signal.get("crisis_flag", False))
    confidence_tag = str(signal.get("confidence", "MEDIUM")).upper()
    tag_class = "tag-crisis" if crisis_flag else "tag-high" if confidence_tag == "HIGH" else "tag-medium"
    event_date = signal.get("event_date") or signal.get("published_date") or "See sources"

    x_format_label, x_content = _format_x_content(result)
    journalist_html = _render_journalist_section(journalist, str(result.get("day_of_week") or ""))

    if result.get("linkedin_today"):
        linkedin_section = (
            f'<div class="linkedin-box">{_esc(result.get("linkedin_post", "")).replace(chr(10), "<br>")}</div>'
        )
    else:
        linkedin_section = (
            f'<div class="linkedin-box" style="color:#8a9ab0;font-style:italic">'
            f'{_esc(result.get("linkedin_post", ""))}</div>'
        )

    verified_facts = signal.get("verified_facts") or []
    facts_html = ""
    if verified_facts:
        facts_html = "<ul class='facts-list'>" + "".join(
            f"<li>{_esc(f if isinstance(f, str) else f.get('fact', f))}</li>" for f in verified_facts
        ) + "</ul>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ background: #f4f6f9; font-family: -apple-system, 'Helvetica Neue', sans-serif; margin: 0; padding: 24px; }}
  .wrapper {{ max-width: 680px; margin: 0 auto; }}
  .header {{ background: #0a0c0f; padding: 20px 24px; border-radius: 6px 6px 0 0; display: flex; align-items: center; gap: 12px; }}
  .logo-mark {{ background: #2a6fdb; color: white; font-weight: 900; font-size: 13px; padding: 4px 8px; border-radius: 3px; display: inline-block; letter-spacing: 0.05em; }}
  .logo-text {{ color: #e8edf2; font-size: 13px; font-weight: 700; letter-spacing: 0.15em; }}
  .scan-date {{ color: #4a5a6e; font-size: 11px; font-family: monospace; margin-left: auto; }}
  .stats-bar {{ background: #13181f; padding: 10px 24px; display: flex; gap: 24px; border-bottom: 1px solid #1e2733; flex-wrap: wrap; }}
  .stat {{ font-family: monospace; font-size: 11px; color: #4a5a6e; }}
  .stat span {{ color: #4da6ff; font-weight: 700; }}
  .stat.crisis span {{ color: #e05252; }}
  .body {{ background: #ffffff; padding: 0; border-radius: 0 0 6px 6px; overflow: hidden; }}
  .section {{ padding: 20px 24px; border-bottom: 1px solid #f0f2f5; }}
  .section:last-child {{ border-bottom: none; }}
  .section-label {{ font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #8a9ab0; margin-bottom: 12px; }}
  .signal-meta {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
  .tag {{ font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 3px; font-family: monospace; }}
  .tag-high {{ background: #e8f0fe; color: #2a6fdb; }}
  .tag-crisis {{ background: #fde8e8; color: #e05252; }}
  .tag-medium {{ background: #fef6e8; color: #b87a00; }}
  .tag-domain {{ background: #f4f6f9; color: #4a5a6e; border: 1px solid #e0e5ed; }}
  .tag-fresh {{ background: #e8fdf3; color: #12805a; border: 1px solid #b8efd4; }}
  .post-box {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-left: 3px solid #2a6fdb; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #1a2332; line-height: 1.6; white-space: pre-wrap; }}
  .post-box.crisis {{ border-left-color: #e05252; background: #fff8f8; }}
  .post-box.green {{ border-left-color: #22c97a; background: #f5fdf9; }}
  .post-box.purple {{ border-left-color: #7c5cbf; background: #f8f5fd; }}
  .post-box.amber {{ border-left-color: #d4a017; background: #fffbf0; }}
  .journalist-name {{ font-size: 13px; font-weight: 600; color: #1a2332; margin-bottom: 2px; }}
  .journalist-handle {{ font-size: 11px; color: #2a6fdb; font-family: monospace; margin-bottom: 10px; }}
  .journalist-hint {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-radius: 4px; padding: 10px 12px; font-size: 12px; color: #4a5a6e; margin-bottom: 10px; }}
  .post-url {{ font-size: 11px; color: #2a6fdb; font-family: monospace; word-break: break-all; }}
  .brief-text {{ font-size: 13px; color: #2a3a4a; line-height: 1.7; }}
  .implications {{ background: #f8f9fb; border-radius: 4px; padding: 12px 16px; margin-top: 12px; }}
  .imp-label {{ font-size: 10px; font-weight: 700; color: #8a9ab0; letter-spacing: 0.08em; margin-bottom: 4px; }}
  .imp-text {{ font-size: 12px; color: #2a3a4a; line-height: 1.6; }}
  .footer {{ background: #f8f9fb; border-top: 1px solid #e0e5ed; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; }}
  .footer-left {{ font-size: 10px; color: #8a9ab0; font-family: monospace; }}
  .footer-right {{ font-size: 10px; color: #2a6fdb; font-family: monospace; font-weight: 700; }}
  .linkedin-box {{ background: #f0f7ff; border: 1px solid #c8ddf7; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #1a2332; line-height: 1.6; white-space: pre-wrap; }}
  h4 {{ margin: 8px 0 4px 0; font-size: 11px; color: #8a9ab0; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }}
  .signal-title {{ font-size: 14px; font-weight: 600; color: #1a2332; margin-bottom: 8px; }}
  .citation-list, .facts-list {{ margin: 8px 0 0 18px; padding: 0; font-size: 12px; line-height: 1.6; }}
  .muted {{ color: #8a9ab0; font-size: 12px; }}
  .cadence-row {{ margin-bottom: 8px; font-size: 12px; }}
  .cadence-label {{ font-weight: 700; color: #4a5a6e; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <span class="logo-mark">XI</span>
    <span class="logo-text">XINTELOPS</span>
    <span class="scan-date">{_esc(result.get("date_pkt"))} · {_esc(result.get("time_pkt"))} · Automated Scan</span>
  </div>
  <div class="stats-bar">
    <div class="stat">SCANNED <span>{_esc(result.get("signals_scanned", 0))}</span></div>
    <div class="stat">VERIFIED <span>{_esc(result.get("signals_verified", 0))}</span></div>
    <div class="stat">BLOCKED <span>{_esc(result.get("signals_blocked", 0))}</span></div>
    <div class="stat crisis">CRISIS <span>{'YES ⚠️' if result.get('crisis_detected') else 'NO'}</span></div>
    <div class="stat">EVENT <span>{_esc(event_date)}</span></div>
    <div class="stat">SESSION <span>{_esc(str(result.get('scan_session', ''))[-8:])}</span></div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">🔗 Source Verification — cite these if challenged</div>
      <div class="signal-title">{_esc(signal.get("title"))}</div>
      <div class="signal-meta">
        <span class="tag tag-fresh">EVENT {_esc(event_date)}</span>
        <span class="tag {tag_class}">{confidence_tag}</span>
        <span class="tag tag-domain">{_esc(str(signal.get("source", "")))}</span>
        <span class="tag tag-domain">{_esc(str(signal.get("region", "")).upper())}</span>
      </div>
      {_render_citations(citations)}
      {f"<h4>Verified facts</h4>{facts_html}" if facts_html else ""}
      <p class="muted" style="margin-top:10px">Scan run: {_esc(result.get("date_pkt"))} {_esc(result.get("time_pkt"))} · Event date is when the underlying development occurred (must be within 24h).</p>
    </div>
    <div class="section">
      <div class="section-label">📅 Posting Cadence — when to publish</div>
      <div class="post-box amber">
        <div class="cadence-row"><span class="cadence-label">X (now):</span> {_esc(cadence.get("x_primary"))}</div>
        <div class="cadence-row"><span class="cadence-label">X (later):</span> {_esc(cadence.get("x_secondary"))}</div>
        <div class="cadence-row"><span class="cadence-label">X (engagement):</span> {_esc(cadence.get("x_engagement"))}</div>
        <div class="cadence-row"><span class="cadence-label">LinkedIn:</span> {_esc(cadence.get("linkedin"))}</div>
      </div>
    </div>
    <div class="section">
      <div class="section-label">📡 Post This Now — X</div>
      <div class="signal-meta">
        <span class="tag tag-domain">{_esc(x_format_label)}</span>
        <span class="tag tag-domain">{_esc(result.get("post_format", "POST"))}</span>
      </div>
      <div class="post-box {'crisis' if crisis_flag else ''}">{_esc(x_content).replace(chr(10), '<br>')}</div>
    </div>
    <div class="section">
      <div class="section-label">🔍 What Most People Missed</div>
      <div class="post-box green">{_esc(result.get("what_most_missed", "")).replace(chr(10), "<br>")}</div>
    </div>
    <div class="section">
      <div class="section-label">💬 Journalist Comment — reply on their post</div>
      {journalist_html}
    </div>
    <div class="section">
      <div class="section-label">💼 LinkedIn {'— POST TODAY' if result.get('linkedin_today') else '— NOT TODAY'}</div>
      {linkedin_section}
    </div>
    <div class="section">
      <div class="section-label">📋 Internal Brief</div>
      <div class="brief-text">{_esc(result.get("internal_brief", "")).replace(chr(10), "<br>")}</div>
      <div class="implications">
        <div class="imp-label">⏱ 48-Hour Implications</div>
        <div class="imp-text">{_esc(result.get("implications_48h", "")).replace(chr(10), "<br>")}</div>
      </div>
      <div class="implications" style="margin-top: 8px;">
        <div class="imp-label">📅 7-Day Indicators</div>
        <div class="imp-text">{_esc(result.get("implications_7d", "")).replace(chr(10), "<br>")}</div>
      </div>
    </div>
  </div>
  <div class="footer">
    <div class="footer-left">✅ Saved to Supabase · {_esc(result.get("scan_session"))}</div>
    <div class="footer-right">XINTELOPS INTELLIGENCE ENGINE</div>
  </div>
</div>
</body>
</html>"""
