from __future__ import annotations

import hashlib
import html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Tuple
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .models import EmailItem


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class ArticleData:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    image_url: str = ""
    image_path: str = ""
    extra_image_urls: tuple[str, ...] = ()
    extra_image_paths: tuple[str, ...] = ()

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
        self.images: list[str] = []
        self.image_candidates: list[dict[str, str]] = []
        self._capture_title = False
        self._capture_paragraph = False
        self._capture_heading = False
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
        elif tag in {"h1", "h2", "h3"}:
            self._capture_heading = True
            self._paragraph_parts = []
        elif tag in {"p", "li"}:
            self._capture_paragraph = True
            self._paragraph_parts = []
        elif tag == "img":
            src = (
                attrs_map.get("src")
                or attrs_map.get("data-src")
                or attrs_map.get("data-lazy-src")
                or attrs_map.get("data-original")
            )
            if src and not _is_low_value_image(src):
                cleaned_src = html.unescape(src.strip())
                self.images.append(cleaned_src)
                self.image_candidates.append(
                    {
                        "src": cleaned_src,
                        "alt": html.unescape(attrs_map.get("alt", "").strip()),
                        "title": html.unescape(attrs_map.get("title", "").strip()),
                        "width": attrs_map.get("width", ""),
                        "height": attrs_map.get("height", ""),
                        "loading": attrs_map.get("loading", ""),
                    }
                )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._capture_title = False
        elif tag in {"h1", "h2", "h3"} and self._capture_heading:
            text = _clean_text(" ".join(self._paragraph_parts))
            if len(text) >= 20 and not _is_boilerplate(text):
                self.paragraphs.append(text)
            self._capture_heading = False
            self._paragraph_parts = []
        elif tag in {"p", "li"} and self._capture_paragraph:
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
        elif self._capture_paragraph or self._capture_heading:
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


# Domains that are tracking/redirect wrappers — never real article pages
_TRACKING_DOMAINS = (
    "mailchimp.com", "list-manage.com", "mailerlite.com",
    "sendgrid.net", "sendgrid.com", "constantcontact.com",
    "klaviyo.com", "marketo.net", "hubspotemail.net",
    "click.convertkit", "app.convertkit.com",
    "beehiiv.com/subscribe", "substack.com/subscribe",
    "emailoctopus.com", "tinyletter.com",
    "go.pardot.com", "mkt.", "email.mg.",
    "t.co/", "bit.ly/", "ow.ly/", "tinyurl.com/",
    "buff.ly/", "dlvr.it/",
)

# Path fragments that indicate non-article pages in newsletters
_SKIP_PATH_FRAGMENTS = (
    "unsubscribe", "privacy", "terms", "optout", "opt-out",
    "manage-preferences", "email-preferences", "account/settings",
    "help/", "support/", "about/", "contact/",
    "track/click", "/click/",
    "facebook.com/help", "twitter.com/intent",
)

def extract_article_urls(text: str) -> list[str]:
    candidates = re.findall(r"https?://[^\s<>\")']+", html.unescape(text or ""))
    urls: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        url = raw.rstrip(".,;:!?)]}")
        lowered = url.lower()
        # Skip image files
        if any(ext in lowered for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico")):
            continue
        # Skip known tracking/redirect domains
        if any(td in lowered for td in _TRACKING_DOMAINS):
            continue
        # Skip non-article path patterns
        if any(frag in lowered for frag in _SKIP_PATH_FRAGMENTS):
            continue
        # Skip bare domain-only URLs (no path = not an article)
        path_part = url.split("//", 1)[-1].split("/", 1)
        if len(path_part) < 2 or not path_part[1].strip("/"):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def fetch_article(url: str, assets_dir: Path) -> ArticleData | None:
    used_playwright = False
    try:
        html_bytes, final_url = _read_url(url, timeout=12)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Try a headless browser render fallback (better for JS-heavy or blocked pages)
        try:
            html_bytes, final_url = _render_with_playwright(url, timeout=18)
            used_playwright = True
        except Exception:
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
    text = _clean_text(" ".join(parser.paragraphs))  # keep the full article body for downstream chunking
    raw_image_urls = _select_best_images(parser, final_url, title, description, text, n=4)
    raw_image_urls = [urllib.parse.urljoin(final_url, u) for u in raw_image_urls]
    # If the basic fetch didn't yield useful paragraphs, try a rendered fetch using Playwright
    if not parser.paragraphs and not (parser.meta or parser.title) and not used_playwright:
        try:
            html_bytes2, final_url2 = _render_with_playwright(url, timeout=18)
            if html_bytes2:
                charset2 = _detect_charset(html_bytes2) or "utf-8"
                page2 = html_bytes2.decode(charset2, errors="replace")
                parser2 = _ArticleParser()
                parser2.feed(page2)
                title = title or _clean_text(
                    parser2.meta.get("og:title")
                    or parser2.meta.get("twitter:title")
                    or parser2.title
                )
                description = description or _clean_text(
                    parser2.meta.get("og:description")
                    or parser2.meta.get("twitter:description")
                    or parser2.meta.get("description")
                )
                if not raw_image_urls:
                    text2 = _clean_text(" ".join(parser2.paragraphs))
                    raw_image_urls = [
                        urllib.parse.urljoin(final_url2, u)
                        for u in _select_best_images(parser2, final_url2, title, description, text2, n=4)
                    ]
                text = text or _clean_text(" ".join(parser2.paragraphs))
                final_url = final_url2 or final_url
        except Exception:
            pass
    # Download up to 4 images; first is the primary, rest go in extra_*
    image_paths = [_download_image(u, assets_dir, final_url) for u in raw_image_urls]
    image_url = raw_image_urls[0] if raw_image_urls else ""
    image_path = image_paths[0] if image_paths else ""
    extra_image_urls = tuple(u for u in raw_image_urls[1:4])
    extra_image_paths = tuple(p for p in image_paths[1:4] if p)
    return ArticleData(
        url=final_url,
        title=title,
        description=description,
        text=text,
        image_url=image_url,
        image_path=image_path,
        extra_image_urls=extra_image_urls,
        extra_image_paths=extra_image_paths,
    )


def _read_url(url: str, timeout: int) -> tuple[bytes, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise ValueError(f"Not an HTML page: {content_type}")
        return response.read(8_000_000), response.geturl()  # 8MB — captures full long-form articles


def _render_with_playwright(url: str, timeout: int) -> Tuple[bytes, str]:
    """Use Playwright to render the page in a headless Chromium and return the HTML bytes and final URL.
    This is a best-effort fallback for JS-heavy sites or pages that block simple HTTP clients.
    If Playwright is not installed or rendering fails, this function will raise an exception.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 800})
        page = context.new_page()
        try:
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            content = page.content()
            final = page.url
            return content.encode("utf-8"), final
        finally:
            context.close()
            browser.close()


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
            data = response.read(8_000_000)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return ""
    digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:16]
    assets_dir.mkdir(parents=True, exist_ok=True)
    path = assets_dir / f"{digest}{suffix}"
    path.write_bytes(data)
    # Also save to the shared image library for reuse across posts
    library_dir = Path(__file__).resolve().parents[1] / "data" / "images"
    library_dir.mkdir(parents=True, exist_ok=True)
    lib_path = library_dir / f"{digest}{suffix}"
    if not lib_path.exists():
        lib_path.write_bytes(data)
    # Save sidecar metadata for relevance matching
    meta_path = library_dir / f"{digest}.json"
    if not meta_path.exists():
        meta_path.write_text(
            __import__("json").dumps({"url": image_url, "seed": source_url}, ensure_ascii=True),
            encoding="utf-8",
        )
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
    lowered = text.lower().strip()
    # Reject single-word or very short noise tokens
    if re.fullmatch(r"(low|medium|high|impact|source|link|\d+\.?)", lowered):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "all rights reserved", "sign up for", "subscribe to",
            "use essential cookies", "advertising partners", "show you ads",
            "cookie settings", "manage cookies", "accept all cookies",
            "reject all cookies", "cookie policy", "privacy policy",
            "terms of service", "cookie preferences", "customize cookie",
            "essential cookies are necessary", "you may review and change",
            "cookie notice", "select your cookie", "gdpr", "ccpa",
            "opt out", "data protection", "third-party cookies",
            "tracking cookies", "functional cookies", "performance cookies",
            "analytics cookies", "marketing cookies", "view in browser",
            "unsubscribe", "manage subscriptions", "email preferences",
            "you are receiving this", "sent to you because",
            "no longer wish to receive", "read more", "click here",
            "learn more", "find out more",
            "impact: low", "impact: medium", "impact: high",
            "source:", "link:", "read time:",
        )
    )


def _is_low_value_image(src: str) -> bool:
    lowered = src.lower()
    return any(
        marker in lowered
        for marker in (
            "logo",
            "avatar",
            "icon",
            "sprite",
            "tracking",
            "pixel",
            "blank",
            "spacer",
            "1x1",
        )
    )


def _tighten(text: str, limit: int) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _select_best_images(
    parser: _ArticleParser,
    final_url: str,
    title: str,
    description: str,
    text: str,
    n: int = 4,
) -> list[str]:
    """Return up to `n` best image URLs from the parsed article, ranked by relevance."""
    candidates: list[dict[str, str]] = []
    meta_image = parser.meta.get("og:image") or parser.meta.get("twitter:image")
    if meta_image:
        candidates.append({"src": meta_image, "source": "meta"})
    if parser.images:
        candidates.extend(parser.image_candidates or [{"src": src, "source": "img"} for src in parser.images])

    if not candidates:
        return []

    context = " ".join(part for part in [title, description, text] if part)
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        src = str(candidate.get("src") or "").strip()
        if not src or _is_low_value_image(src) or src in seen:
            continue
        seen.add(src)
        score = _score_image_candidate(candidate, context, final_url)
        scored.append((score, src))

    scored.sort(reverse=True)
    return [src for _, src in scored[:n]]


def _select_best_image(parser: _ArticleParser, final_url: str, title: str, description: str, text: str) -> str:
    results = _select_best_images(parser, final_url, title, description, text, n=1)
    return results[0] if results else ""


def _score_image_candidate(candidate: dict[str, str], context: str, final_url: str) -> float:
    src = str(candidate.get("src") or "").lower()
    alt = _clean_text(candidate.get("alt", ""))
    title = _clean_text(candidate.get("title", ""))
    tokens = _important_tokens(" ".join([src, alt, title, context, final_url]))
    context_tokens = _important_tokens(context)
    overlap = tokens & context_tokens
    score = len(overlap) * 0.22
    if overlap:
        score += min(0.20, 0.04 * len(overlap))
    if alt:
        score += 0.12
    if title:
        score += 0.08
    if any(term in alt.lower() for term in ("hero", "feature", "cover", "main", "lead")):
        score += 0.08
    if any(term in src for term in ("hero", "cover", "article", "feature")):
        score += 0.08
    # HTML-declared dimensions (unreliable but useful when present)
    width = _safe_int(candidate.get("width", ""))
    height = _safe_int(candidate.get("height", ""))
    if width >= 3840 or height >= 2160:
        score += 0.30  # 4K / UHD
    elif width >= 1920 or height >= 1080:
        score += 0.22  # Full HD
    elif width >= 1280 and height >= 720:
        score += 0.15  # HD
    elif width and height:
        if width < 400 or height < 300:
            score -= 0.20  # penalise confirmed thumbnails
        else:
            score += 0.04
    # URL-level resolution hints (CDN params, path tokens, quality keywords)
    url_dim = _url_size_hint(src)
    if url_dim >= 3840:
        score += 0.35  # 4K URL hint
    elif url_dim >= 1920:
        score += 0.28  # Full HD URL hint
    elif url_dim >= 1280:
        score += 0.18  # HD URL hint
    elif url_dim >= 800:
        score += 0.06
    elif 0 < url_dim < 400:
        score -= 0.22  # confirmed small image
    if any(term in src for term in ("logo", "avatar", "icon", "sprite", "pixel", "tracking")):
        score -= 0.40
    if candidate.get("loading", "").lower() == "lazy":
        score += 0.02
    if re.search(r"\b(openai|google|microsoft|meta|amazon|aws|nvidia|anthropic|open source|launch|model|api)\b", context, re.I):
        score += 0.06 if any(term in src for term in ("model", "launch", "api", "product", "news", "blog")) else 0.0
    return score


def _url_size_hint(url: str) -> int:
    """Extract the largest pixel dimension hinted in a CDN image URL.

    Returns the inferred width (or largest dimension) in pixels, or 0 if unknown.
    Checks explicit query params first (most reliable), then path segments, then
    quality keywords.
    """
    lowered = url.lower()
    # 1. Explicit query parameters: ?w=1920, ?width=2560, ?size=1920x1080
    for m in re.finditer(r"[?&](?:w|width|size|maxwidth|max_width|imgwidth)=(\d+)", lowered):
        val = int(m.group(1))
        if val >= 100:
            return val
    # 2. Size embedded in path: -1920x1080, _1920w, /1920/, -2048-, @2x
    for m in re.finditer(r"[-_/](\d{3,4})(?:x\d+|w\b|px\b)?", lowered):
        val = int(m.group(1))
        if 200 <= val <= 9999:
            return val
    # 3. Quality/size keywords in URL
    if any(k in lowered for k in ("4k", "2160p", "uhd", "qhd", "2560")):
        return 3840
    if any(k in lowered for k in ("1080p", "1920", "fhd", "fullhd")):
        return 1920
    if any(k in lowered for k in ("720p", "1280", "hd")):
        return 1280
    if any(k in lowered for k in ("original", "full-size", "fullsize", "xlarge", "x-large", "max")):
        return 1600
    if any(k in lowered for k in ("large",)):
        return 1024
    if any(k in lowered for k in ("medium",)):
        return 800
    if any(k in lowered for k in ("small", "thumbnail", "thumb", "tiny")):
        return 200
    return 0


def _important_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in {"about", "after", "article", "blog", "cookie", "image", "news", "privacy", "story", "update", "with"}
    }


def _safe_int(value: str) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        return 0
