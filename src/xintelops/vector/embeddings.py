from __future__ import annotations

from openai import OpenAI

from xintelops.config import Settings, get_settings


class EmbeddingService:
    MODEL = "text-embedding-3-small"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.MODEL,
            input=text[:8000],
        )
        return response.data[0].embedding
