from __future__ import annotations

from typing import Any

from xintelops.agents.base import AnthropicAgent


class RedTeamAgent:
    SYSTEM = """You are the XIntelOps Red Team.
Stress-test the analyst output with counter-arguments and alternative explanations.
Harden the analysis against the top 2 challenges.
Return ONLY JSON:
{
  "redteam_summary": "",
  "counter_arguments": [],
  "revised_analysis": "",
  "residual_risks": []
}"""

    def __init__(self, agent: AnthropicAgent | None = None) -> None:
        self.agent = agent or AnthropicAgent()

    def run(self, analyst_output: dict[str, Any]) -> dict[str, Any]:
        return self.agent.run(
            self.SYSTEM,
            f"Analyst output:\n{analyst_output}\n\nReturn ONLY valid JSON.",
        )
