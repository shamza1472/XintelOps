from __future__ import annotations

import json
import re
from typing import Any

import anthropic

from xintelops.config import Settings, get_settings

MODEL = "claude-haiku-4-5-20251001"


class AnthropicAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    def run(self, system_prompt: str, user_message: str, max_tokens: int = 4096) -> dict[str, Any]:
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text if response.content else "{}"
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
