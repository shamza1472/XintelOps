from __future__ import annotations

from typing import Any

from xintelops.agents.base import AnthropicAgent


class VerifierAgent:
    SYSTEM = """You are the XIntelOps Verifier.
Scan source content and identify up to 3 significant geopolitical signals from the past 24 hours.
Only use named high-trust sources. Block low confidence or high misinfo risk signals.
Return ONLY JSON:
{
  "signals_scanned": 0,
  "signals_verified": 0,
  "signals_blocked": 0,
  "crisis_detected": false,
  "verified_signals": [
    {
      "title": "",
      "source": "",
      "tier": "L0",
      "url": "",
      "summary": "",
      "region": "",
      "domain": "",
      "confidence": "HIGH",
      "crisis_flag": false,
      "verified_facts": []
    }
  ]
}"""

    def __init__(self, agent: AnthropicAgent | None = None) -> None:
        self.agent = agent or AnthropicAgent()

    def run(self, source_content: str) -> dict[str, Any]:
        return self.agent.run(
            self.SYSTEM,
            f"Source bundle:\n\n{source_content}\n\nReturn ONLY valid JSON.",
        )
