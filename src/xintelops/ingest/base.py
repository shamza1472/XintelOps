from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class IngestedItem:
    source: str
    raw_text: str
    title: str = ""
    url: str = ""
    source_type: str = "news"
    layer: str = ""
    region: str = ""
    domain: str = ""


class Fetcher(Protocol):
    def fetch(self) -> list[IngestedItem]: ...
