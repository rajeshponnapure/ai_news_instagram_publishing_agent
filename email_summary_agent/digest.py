from __future__ import annotations

import re
from dataclasses import dataclass

from .article_enricher import extract_article_urls
from .models import EmailItem


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str = ""
    context: str = ""

    def to_article_seed(self) -> dict[str, str]:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.context,
            "excerpt": self.context,
            "source": self.source,
            "image_path": "",
            "image_url": "",
        }


def parse_news_items(email: EmailItem, max_links: int = 20) -> list[NewsItem]:
    """Extract per-story items from an AI alert/digest email.

    The upstream emails vary between compact alerts and large daily digests. This
    parser keeps the contract intentionally simple: one unique article URL is one
    story, with nearby text used as the story title/context until enrichment
    replaces it with the real article metadata.
    """
    urls = extract_article_urls(email.body)
    if max_links > 0:
        urls = urls[:max_links]
    if not urls:
        return []

    text = _normalize_lines(email.body)
    items: list[NewsItem] = []
    for index, url in enumerate(urls, start=1):
        window = _context_window(text, url)
        raw_context = _strip_url(window, url)
        context = _tighten(raw_context, 900)
        if len(urls) == 1 and _is_weak_link_context(context):
            raw_context = _strip_url(text, url)
            context = _tighten(raw_context, 1200)
        title = _title_from_context(window) or _title_from_context(raw_context)
        if _is_weak_link_context(title) and len(urls) == 1:
            title = email.subject.strip()
        title = title or _title_from_url(url) or f"AI news {index}"
        source = _source_from_subject(email.subject) or _source_from_url(url)
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                context=context,
            )
        )
    return items


def _normalize_lines(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _context_window(text: str, url: str) -> str:
    position = text.find(url)
    if position < 0:
        return ""
    start = max(0, text.rfind("\n\n", 0, position))
    end = text.find("\n\n", position)
    if end < 0:
        end = min(len(text), position + 900)
    if start == 0:
        start = max(0, position - 450)
    return text[start:end].strip()


def _title_from_context(context: str) -> str:
    lines = [line.strip(" -#*\t") for line in context.splitlines() if line.strip()]
    for line in lines:
        if line.startswith(("http://", "https://")):
            continue
        if re.search(r"\bunsubscribe|privacy|read more|view in browser|for more details\b", line, re.I):
            continue
        line = re.sub(r"^\d+[\).:-]\s*", "", line)
        line = re.sub(r"\s*https?://\S+.*$", "", line).strip()
        if 12 <= len(line) <= 140:
            return line
    return ""


def _is_weak_link_context(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" :-")
    if not cleaned:
        return True
    return bool(re.fullmatch(r"(?i)(for more details,?\s*)?(visit|read more|learn more|source)?", cleaned))


def _source_from_subject(subject: str) -> str:
    if "—" in subject:
        return subject.rsplit("—", 1)[1].strip()
    if " - " in subject:
        return subject.rsplit(" - ", 1)[1].strip()
    return ""


def _source_from_url(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else ""


def _title_from_url(url: str) -> str:
    path = re.sub(r"^https?://[^/]+/?", "", url)
    path = path.split("?", 1)[0].strip("/")
    if not path:
        return ""
    slug = path.rsplit("/", 1)[-1]
    words = re.sub(r"[-_]+", " ", slug).strip()
    return words[:1].upper() + words[1:] if words else ""


def _strip_url(text: str, url: str) -> str:
    return re.sub(re.escape(url), "", text).strip(" -\n\t")


def _tighten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."
