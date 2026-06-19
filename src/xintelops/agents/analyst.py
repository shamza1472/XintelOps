from __future__ import annotations

from typing import Any

from xintelops.agents.base import AnthropicAgent


class AnalystAgent:
    SYSTEM = """You are the XIntelOps Analyst.
Analyze the top verified signal with institution-grade depth.
If crisis_flag=true use Crisis Mode (operational implications, escalation ladder, proxy indicators).
Otherwise use Standard Analysis (strategic context, 48h and 7d implications).
Return ONLY JSON:
{
  "top_signal": {},
  "analysis_summary": "",
  "implications_48h": "",
  "implications_7d": "",
  "crisis_mode": false
}"""

    def __init__(self, agent: AnthropicAgent | None = None) -> None:
        self.agent = agent or AnthropicAgent()

    def run(self, verified_signal: dict[str, Any]) -> dict[str, Any]:
        return self.agent.run(
            self.SYSTEM,
            f"Verified signal:\n{verified_signal}\n\nReturn ONLY valid JSON.",
        )
