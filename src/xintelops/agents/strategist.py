from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from xintelops.agents.base import AnthropicAgent
from xintelops.ingest.journalist_fetcher import Journalist, get_journalist_for_today, load_journalists
from xintelops.config import get_settings


CATEGORY_FOCUS = {
    "A": "Global / Foreign Policy",
    "B": "Middle East & Gulf",
    "C": "Defense & Military Affairs",
    "D": "Indo-Pacific & East Asia",
    "E": "Eastern Europe / Ukraine-Russia",
    "F": "Geo-Economics & Sanctions",
}


def get_pkt_date_info(utc_date: datetime) -> dict[str, Any]:
    pkt = utc_date.timestamp() + 5 * 3600
    pkt_dt = datetime.fromtimestamp(pkt, tz=timezone.utc)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_name = days[pkt_dt.weekday()]
    date_str = pkt_dt.date().isoformat()
    time_str = f"{pkt_dt.hour:02d}:{pkt_dt.minute:02d} PKT"
    is_linkedin_day = pkt_dt.weekday() in {0, 2, 4}
    return {
        "date_str": date_str,
        "time_str": time_str,
        "day_name": day_name,
        "is_linkedin_day": is_linkedin_day,
    }


class StrategistAgent:
    def __init__(self, agent: AnthropicAgent | None = None) -> None:
        self.agent = agent or AnthropicAgent()
        self.journalists = load_journalists(get_settings().journalists_csv_path)

    def run(
        self,
        analyst_output: dict[str, Any],
        redteam_output: dict[str, Any],
        utc_now: datetime | None = None,
    ) -> dict[str, Any]:
        utc_now = utc_now or datetime.now(timezone.utc)
        pkt = get_pkt_date_info(utc_now)
        journalist = get_journalist_for_today(self.journalists, utc_now)
        category = journalist.category
        focus = CATEGORY_FOCUS.get(category, journalist.focus)

        system_prompt = f"""You are the XIntelOps Strategist.
Produce the content package and journalist engagement draft.
Today: {pkt['date_str']} ({pkt['day_name']}), {pkt['time_str']}.
LinkedIn posting day: {pkt['is_linkedin_day']}.
Journalist: {journalist.name} (@{journalist.handle}) — {journalist.outlet}
Category {category}: {focus}

Return ONLY JSON:
{{
  "scan_session": "SCAN-{pkt['date_str']}-{pkt['time_str'].replace(':', '').replace(' PKT', '')}",
  "date_pkt": "{pkt['date_str']}",
  "time_pkt": "{pkt['time_str']}",
  "day_of_week": "{pkt['day_name']}",
  "post_format": "SHORT POST",
  "x_post": "",
  "x_thread": null,
  "what_most_missed": "",
  "linkedin_today": {str(pkt['is_linkedin_day']).lower()},
  "linkedin_post": "",
  "internal_brief": "",
  "implications_48h": "",
  "implications_7d": "",
  "journalist": {{
    "name": "{journalist.name}",
    "handle": "{journalist.handle}",
    "outlet": "{journalist.outlet}",
    "category": "{category}",
    "focus": "{focus}",
    "profile_url": "{journalist.profile_url}",
    "comment_draft": "",
    "engagement_rationale": ""
  }},
  "redteam_summary": ""
}}"""

        user_message = (
            f"Analyst output:\n{analyst_output}\n\n"
            f"Red team output:\n{redteam_output}\n\n"
            "Return ONLY valid JSON."
        )
        result = self.agent.run(system_prompt, user_message)
        result.setdefault("top_signal", analyst_output.get("top_signal", {}))
        result.setdefault("signals_scanned", 0)
        result.setdefault("signals_verified", 1)
        result.setdefault("signals_blocked", 0)
        result.setdefault("crisis_detected", analyst_output.get("top_signal", {}).get("crisis_flag", False))
        result["redteam_summary"] = redteam_output.get("redteam_summary", "")
        result["implications_48h"] = result.get("implications_48h") or analyst_output.get("implications_48h", "")
        result["implications_7d"] = result.get("implications_7d") or analyst_output.get("implications_7d", "")
        return result
