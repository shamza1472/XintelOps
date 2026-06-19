from __future__ import annotations

import html
from typing import Any


def build_email_html(result: dict[str, Any]) -> str:
    signal = result.get("top_signal", {}) or {}
    journalist = result.get("journalist", {}) or {}
    crisis_flag = bool(signal.get("crisis_flag", False))
    confidence_tag = str(signal.get("confidence", "MEDIUM")).upper()
    tag_class = "tag-crisis" if crisis_flag else "tag-high" if confidence_tag == "HIGH" else "tag-medium"

    if result.get("post_format") == "THREAD":
        x_content = result.get("x_thread") or result.get("x_post") or ""
    else:
        x_content = result.get("x_post") or ""

    if result.get("linkedin_today"):
        linkedin_section = (
            f'<div class="linkedin-box">{html.escape(str(result.get("linkedin_post", ""))).replace(chr(10), "<br>")}</div>'
        )
    else:
        linkedin_section = (
            f'<div class="linkedin-box" style="color:#8a9ab0;font-style:italic">'
            f'{html.escape(str(result.get("linkedin_post", "")))}</div>'
        )

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

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
  .stats-bar {{ background: #13181f; padding: 10px 24px; display: flex; gap: 24px; border-bottom: 1px solid #1e2733; }}
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
  .post-box {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-left: 3px solid #2a6fdb; border-radius: 4px; padding: 14px 16px; font-size: 13px; color: #1a2332; line-height: 1.6; white-space: pre-wrap; }}
  .post-box.crisis {{ border-left-color: #e05252; background: #fff8f8; }}
  .post-box.green {{ border-left-color: #22c97a; background: #f5fdf9; }}
  .post-box.purple {{ border-left-color: #7c5cbf; background: #f8f5fd; }}
  .journalist-name {{ font-size: 13px; font-weight: 600; color: #1a2332; margin-bottom: 2px; }}
  .journalist-handle {{ font-size: 11px; color: #2a6fdb; font-family: monospace; margin-bottom: 10px; }}
  .journalist-hint {{ background: #f8f9fb; border: 1px solid #e0e5ed; border-radius: 4px; padding: 10px 12px; font-size: 12px; color: #4a5a6e; margin-bottom: 10px; }}
  .post-url {{ font-size: 11px; color: #2a6fdb; font-family: monospace; }}
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
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <span class="logo-mark">XI</span>
    <span class="logo-text">XINTELOPS</span>
    <span class="scan-date">{esc(result.get("date_pkt"))} · {esc(result.get("time_pkt"))} · Automated Scan</span>
  </div>
  <div class="stats-bar">
    <div class="stat">SCANNED <span>{esc(result.get("signals_scanned", 0))}</span></div>
    <div class="stat">VERIFIED <span>{esc(result.get("signals_verified", 0))}</span></div>
    <div class="stat">BLOCKED <span>{esc(result.get("signals_blocked", 0))}</span></div>
    <div class="stat crisis">CRISIS <span>{'YES ⚠️' if result.get('crisis_detected') else 'NO'}</span></div>
    <div class="stat">SESSION <span>{esc(str(result.get('scan_session', ''))[-8:])}</span></div>
  </div>
  <div class="body">
    <div class="section">
      <div class="section-label">📡 Post This Now — X</div>
      <div class="signal-title">{esc(signal.get("title"))}</div>
      <div class="signal-meta">
        <span class="tag {tag_class}">{confidence_tag}</span>
        <span class="tag tag-domain">{esc(str(signal.get("domain", "")).replace("_", " ").upper())}</span>
        <span class="tag tag-domain">{esc(str(signal.get("region", "")).upper())}</span>
        <span class="tag tag-domain">{esc(result.get("post_format", "POST"))}</span>
      </div>
      <div class="post-box {'crisis' if crisis_flag else ''}">{esc(x_content).replace(chr(10), '<br>')}</div>
    </div>
    <div class="section">
      <div class="section-label">🔍 What Most People Missed</div>
      <div class="post-box green">{esc(result.get("what_most_missed", "")).replace(chr(10), "<br>")}</div>
    </div>
    <div class="section">
      <div class="section-label">💬 Journalist Comment</div>
      <div class="journalist-name">{esc(journalist.get("name"))}</div>
      <div class="journalist-handle">@{esc(journalist.get("handle"))} · {esc(journalist.get("outlet"))} · Category {esc(journalist.get("category"))} · {esc(result.get("day_of_week"))}</div>
      <div class="journalist-hint">⚡ Find their latest post here: <a href="{esc(journalist.get('profile_url'))}" class="post-url">{esc(journalist.get("profile_url"))}</a></div>
      <h4>Your comment:</h4>
      <div class="post-box purple">{esc(journalist.get("comment_draft", "")).replace(chr(10), "<br>")}</div>
    </div>
    <div class="section">
      <div class="section-label">💼 LinkedIn</div>
      {linkedin_section}
    </div>
    <div class="section">
      <div class="section-label">📋 Internal Brief</div>
      <div class="brief-text">{esc(result.get("internal_brief", "")).replace(chr(10), "<br>")}</div>
      <div class="implications">
        <div class="imp-label">⏱ 48-Hour Implications</div>
        <div class="imp-text">{esc(result.get("implications_48h", "")).replace(chr(10), "<br>")}</div>
      </div>
      <div class="implications" style="margin-top: 8px;">
        <div class="imp-label">📅 7-Day Indicators</div>
        <div class="imp-text">{esc(result.get("implications_7d", "")).replace(chr(10), "<br>")}</div>
      </div>
    </div>
  </div>
  <div class="footer">
    <div class="footer-left">✅ Saved to Supabase · {esc(result.get("scan_session"))}</div>
    <div class="footer-right">XINTELOPS INTELLIGENCE ENGINE</div>
  </div>
</div>
</body>
</html>"""
