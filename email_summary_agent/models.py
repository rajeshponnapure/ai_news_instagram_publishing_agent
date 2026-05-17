from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EmailItem:
    uid: str
    message_id: str
    sender: str
    subject: str
    date: str
    body: str

    @property
    def message_key(self) -> str:
        return self.message_id or f"uid:{self.uid}"


@dataclass(frozen=True)
class EmailSummary:
    message_key: str
    subject: str
    source_date: str
    headline: str
    summary: str
    key_points: list[str]
    companies: list[str]
    models: list[str]
    topics: list[str]
    confidence: float
    article_url: str = ""
    article_title: str = ""
    article_image_path: str = ""
    article_image_url: str = ""
    article_excerpt: str = ""
    article_items: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
