from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .models import EmailItem


USER_AGENT = "AIInstagramNewsAgent/1.0 (+local article summarizer)"


@dataclass(frozen=True)
class ArticleData:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    image_url: str = ""
    image_path: str = ""

    @property
    def excerpt(self) -> str:
        body = self.description or self.text
        return _tighten(body, 700)


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self.paragraphs: list[str] = []
        self._capture_title = False
        self._capture_paragraph = False
        self._paragraph_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): value for key, value in attrs if key and value}
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = True
        elif tag == "meta":
            key = attrs_map.get("property") or attrs_map.get("name")
            content = attrs_map.get("content", "")
            if key and content:
                self.meta[key.lower()] = html.unescape(content.strip())
        elif tag == "p":
            self._capture_paragraph = True
            self._paragraph_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = False
        elif tag == "p" and self._capture_paragraph:
            text = _clean_text(" ".join(self._paragraph_parts))
            if len(text) >= 60 and not _is_boilerplate(text):
                self.paragraphs.append(text)
            self._capture_paragraph = False
            self._paragraph_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._capture_title:
            self.title += data
        elif self._capture_paragraph:
            self._paragraph_parts.append(data)


def enrich_email_from_links(
    email: EmailItem,
    assets_dir: Path,
    max_links: int = 1,
) -> tuple[EmailItem, ArticleData | None]:
    enriched, articles = enrich_email_with_articles(email, assets_dir, max_links=max_links)
    return enriched, articles[0] if articles else None


def enrich_email_with_articles(
    email: EmailItem,
    assets_dir: Path,
    max_links: int = 5,
) -> tuple[EmailItem, list[ArticleData]]:
    urls = extract_article_urls(email.body)
    if max_links > 0:
        urls = urls[:max_links]
    articles: list[ArticleData] = []
    for url in urls:
        article = fetch_article(url, assets_dir)
        if article and (article.text or article.description or article.title):
            articles.append(article)
    if not articles:
        return email, []
    article_blocks = []
    for index, article in enumerate(articles, start=1):
        article_blocks.append(
            "\n".join(
                part
                for part in [
                    f"Article {index} URL: {article.url}",
                    f"Article {index} title: {article.title}",
                    f"Article {index} summary source: {article.description}",
                    article.text,
                ]
                if part
            )
        )
    enriched = EmailItem(
        uid=email.uid,
        message_id=email.message_id,
        sender=email.sender,
        subject=email.subject,
        date=email.date,
        body="\n\n".join([email.body, *article_blocks]),
    )
    return enriched, articles


def extract_article_urls(text: str) -> list[str]:
    candidates = re.findall(r"https?://[^\s<>\")']+", text)
    urls: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        url = raw.rstrip(".,;:!?)]}")
        lowered = url.lower()
        if any(blocked in lowered for blocked in ("unsubscribe", "privacy", "mailto:", "facebook.com/help")):
            continue
        if any(ext in lowered for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def fetch_article(url: str, assets_dir: Path) -> ArticleData | None:
    try:
        html_bytes, final_url = _read_url(url, timeout=12)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    charset = _detect_charset(html_bytes) or "utf-8"
    page = html_bytes.decode(charset, errors="replace")
    parser = _ArticleParser()
    try:
        parser.feed(page)
    except Exception:
        return None

    title = _clean_text(
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or parser.title
    )
    description = _clean_text(
        parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or parser.meta.get("description")
    )
    image_url = parser.meta.get("og:image") or parser.meta.get("twitter:image") or ""
    image_url = urllib.parse.urljoin(final_url, image_url) if image_url else ""
    image_path = _download_image(image_url, assets_dir, final_url) if image_url else ""
    text = _clean_text(" ".join(parser.paragraphs[:18]))
    return ArticleData(
        url=final_url,
        title=title,
        description=description,
        text=_tighten(text, 5000),
        image_url=image_url,
        image_path=image_path,
    )


def _read_url(url: str, timeout: int) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise ValueError(f"Not an HTML page: {content_type}")
        return response.read(1_500_000), response.geturl()


def _download_image(image_url: str, assets_dir: Path, source_url: str) -> str:
    try:
        request = urllib.request.Request(image_url, headers={"User-Agent": USER_AGENT, "Referer": source_url})
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if not content_type.startswith("image/"):
                return ""
            suffix = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }.get(content_type.split(";", 1)[0], ".img")
            data = response.read(4_000_000)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ""
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:16]
    assets_dir.mkdir(parents=True, exist_ok=True)
    path = assets_dir / f"{digest}{suffix}"
    path.write_bytes(data)
    return str(path)


def _detect_charset(data: bytes) -> str:
    head = data[:1000].decode("ascii", errors="ignore")
    match = re.search(r"charset=['\"]?([A-Za-z0-9_-]+)", head, flags=re.I)
    return match.group(1) if match else ""


def _clean_text(value: str) -> str:
    value = _repair_mojibake(value)
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _repair_mojibake(text: str) -> str:
    if not text or not re.search(r"[\u00c3\u00c2\u00e2\u00f0]", text):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if len(repaired.strip()) >= max(1, len(text.strip()) // 2) else text


def _is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "all rights reserved",
            "sign up for",
            "subscribe to",
            "cookie policy",
            "privacy policy",
            "terms of service",
        )
    )


def _tighten(text: str, limit: int) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."
