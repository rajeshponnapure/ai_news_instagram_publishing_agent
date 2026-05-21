from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "data" / "knowledge_base" / "instagram_ai_content.json"

STOP_TERMS = {
    "about",
    "after",
    "article",
    "because",
    "before",
    "content",
    "email",
    "from",
    "have",
    "more",
    "news",
    "that",
    "their",
    "there",
    "this",
    "update",
    "with",
}


@dataclass(frozen=True)
class RagContext:
    entries: list[dict[str, Any]]

    @property
    def rules(self) -> list[str]:
        return _dedupe(rule for entry in self.entries for rule in entry.get("rules", []))

    @property
    def angles(self) -> list[str]:
        return _dedupe(angle for entry in self.entries for angle in entry.get("angles", []))

    @property
    def patterns(self) -> list[str]:
        return _dedupe(pattern for entry in self.entries for pattern in entry.get("patterns", []))

    def format_for_prompt(self) -> str:
        if not self.entries:
            return ""
        lines = ["Retrieved content-creator knowledge:"]
        if self.rules:
            lines.append("Rules:")
            lines.extend(f"- {rule}" for rule in self.rules[:8])
        if self.angles:
            lines.append("Angles:")
            lines.extend(f"- {angle}" for angle in self.angles[:6])
        if self.patterns:
            lines.append("Patterns to adapt, not copy:")
            lines.extend(f"- {pattern}" for pattern in self.patterns[:5])
        return "\n".join(lines)


def retrieve_context(query: str, limit: int = 3) -> RagContext:
    entries = _load_entries()
    query_tokens = _tokens(query)
    if not query_tokens:
        return RagContext(entries[:limit])

    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        entry_text = " ".join(
            [
                str(entry.get("title", "")),
                " ".join(entry.get("tags", [])),
                " ".join(entry.get("rules", [])),
                " ".join(entry.get("angles", [])),
            ]
        )
        entry_tokens = _tokens(entry_text)
        overlap = query_tokens & entry_tokens
        score = len(overlap) / max(4, len(query_tokens))
        if overlap:
            scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [entry for _score, entry in scored[:limit]]
    if not selected:
        selected = [entry for entry in entries if entry.get("id") == "instagram_editorial_quality"][:1]
    return RagContext(selected)


def format_context(query: str, limit: int = 3) -> str:
    return retrieve_context(query, limit=limit).format_for_prompt()


def _load_entries() -> list[dict[str, Any]]:
    try:
        data = json.loads(KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = data.get("entries", [])
    return [entry for entry in entries if isinstance(entry, dict)]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in STOP_TERMS
    }


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = re.sub(r"\s+", " ", value).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result
