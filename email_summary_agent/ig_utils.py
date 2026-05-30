"""ig_utils.py — shared text and date utility functions for the Instagram pipeline."""
from __future__ import annotations

import re
import shutil
import unicodedata
import urllib.request
import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .ig_constants import CHROME_USER_AGENT, PUBLIC_BLOCKED_PHRASES, VIDEO_BLOCKED_TERMS
from .http_utils import urlopen_with_cert_fallback

if TYPE_CHECKING:
    from .models import EmailSummary


# ─────────────────────────────────────────────────────────────────────────────
# Text cleaning
# ─────────────────────────────────────────────────────────────────────────────

def _strip_decorative_symbols(text: str) -> str:
    cleaned: list[str] = []
    for char in text or "":
        category = unicodedata.category(char)
        if category == "So":
            continue
        cleaned.append(char)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def _clean_public_text(text: str) -> str:
    """Remove digest noise, cookie consent boilerplate, and navigation cruft."""
    text = html.unescape(text or "")
    text = re.sub(r"BREAKING AI UPDATE\s*[-–—]\s*", "", text or "", flags=re.I)
    text = re.sub(r"\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]\s*", "", text, flags=re.I)
    text = re.sub(r"\bImpact\s*:\s*(?:Low|Medium|High|Critical)\b", "", text, flags=re.I)
    text = re.sub(r"\bRead\s*time\s*:\s*\d+\s*(?:min|mins|minutes?)\b", "", text, flags=re.I)
    text = re.sub(r"={3,}", "", text)
    text = re.sub(r"Company\s*:\s*[^\n]*(\n|$)", "", text, flags=re.I)
    text = re.sub(r"AI Summary\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"Link\s*:\s*https?://\S+", "", text, flags=re.I)
    text = re.sub(r"[^.!?]*\bLink\s*:\s*\d+[^.!?]*[.!?]?\s*", "", text, flags=re.I)
    text = re.sub(r"\bLink\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\b(?:\d+|I)\s+event\(s\)\s+detected\b[^\n]*", "", text, flags=re.I)
    text = re.sub(
        r"#{1,6}\s+(?:Bug Fixes|Features?|Performance|Breaking Changes?|Refactoring?|Chores?|Docs?).*",
        "", text, flags=re.I,
    )
    text = re.sub(r"\*\*([^*]+):\*\*\s*", r"\1: ", text)
    text = re.sub(r"\bMore from\s+\S+[^\n.!?]*", "", text, flags=re.I)
    text = re.sub(r"\s*\|[^|.\n]{1,40}(?=\s|$)", "", text)
    text = re.sub(r"\b(?:Dismiss alert|Public Notifications|You must be signed in|You signed out|You switched accounts)\b[^.!?]*[.!?]?", "", text, flags=re.I)
    text = re.sub(r"\b(?:Search code, repositories, users, issues, pull requests|Filter Loading|Sorry, something went wrong|Hamburger Navigation Button|Navigation Drawer)\b[^.!?]*[.!?]?", "", text, flags=re.I)
    text = re.sub(r"\b(?:Desktop Logo|Mobile Logo|Latest Startups Venture|Events Podcasts)\b[^.!?]*[.!?]?", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    text = _strip_decorative_symbols(text)
    text = re.sub(
        r"\[…\]\s*Select your cookie.*?(?=\s{2,}|\Z)", "", text, flags=re.I | re.S,
    )
    text = re.sub(
        r"(?:Select your cookie preferences|Customize cookie preferences"
        r"|Essential cookies are necessary|You may review and change your choices"
        r"|Cookie Notice|Cookie preferences|Accept all cookies|Reject all cookies"
        r"|We use essential cookies|We and our advertising partners"
        r"|Cookie settings).*?(?=(?:\s+[A-Z][a-z]|\s*$))",
        " ", text, flags=re.I | re.S,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[\.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term in lowered for term in VIDEO_BLOCKED_TERMS):
            continue
        if re.match(r"\s*Article\s+\d+\s+(?:URL|title|summary source)\s*:", sentence, re.I):
            continue
        if re.match(r"\s*Article\s+title\s*:", sentence, re.I):
            continue
        if any(phrase in lowered for phrase in PUBLIC_BLOCKED_PHRASES):
            continue
        if re.search(r"\bcookies?\b|\bGDPR\b|\bCCPA\b|\bopt.out\b|\bunsubscribe\b", sentence, re.I):
            continue
        if re.fullmatch(r"\s*(impact|source|link|read time)\s*:\s*(low|medium|high|\d+.*)?\s*", sentence, re.I):
            continue
        kept.append(sentence.strip())
    return " ".join(part for part in kept if part)


def _clean_headline(text: str) -> str:
    """Sanitise a headline string for use as a slide title."""
    MAX_TITLE_CHARS = 90

    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"[.…]+$", "", text).strip()
    text = re.sub(r"^[\s:–—|]+", "", text).strip()
    text = re.sub(r"\s*\|[^|]{1,40}$", "", text).strip()

    if re.match(r"^/[\w/-]{10,}$", text):
        return ""
    if re.match(r"^[\w][\w-]{10,}$", text) and text.count("-") > text.count(" ") * 2 + 2:
        return ""
    if re.match(r"^[A-Z][A-Z0-9-]{10,}$", text) and "-" in text:
        return ""

    words = text.split()
    if words and len(words[0]) == 1 and not words[0].isdigit() and words[0] not in ("A", "I"):
        return ""

    if len(text) < 10:
        return ""

    name_match = re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+)[:\s]\s*(.+)$", text)
    if name_match and len(name_match.group(2)) > 20:
        text = name_match.group(2).strip()

    if len(text) <= MAX_TITLE_CHARS:
        return text

    region = text[:MAX_TITLE_CHARS]
    for terminator in (".", "!", "?"):
        pos = region.rfind(terminator)
        if pos > MAX_TITLE_CHARS // 2:
            return text[:pos + 1].strip()

    return region.rsplit(" ", 1)[0].rstrip(".,;:—-").strip()


def _tighten(text: str, limit: int) -> str:
    """Trim text to a word boundary without adding ellipsis."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:â€”- ")
    if shortened and shortened[-1] not in ".!?":
        shortened += "."
    return shortened


def _trim_no_dots(text: str, limit: int) -> str:
    """Trim text to a word boundary without adding trailing dots."""
    text = re.sub(r"\s+", " ", text or "").strip().rstrip(".…")
    if len(text) <= limit:
        if text and text[-1] not in ".!?":
            text = text + "."
        return text
    truncated = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:—-")
    if truncated and truncated[-1] not in ".!?":
        truncated = truncated + "."
    return truncated


def _source_label_from_url(url: str) -> str:
    """Extract a readable domain label from a URL (e.g. 'techcrunch.com')."""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return match.group(1) if match else ""


def _slugify(text: str) -> str:
    """Convert text into a filesystem-safe ASCII slug."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:60] or "post"


def _dedupe_lead_text(lead: str, headline: str) -> str:
    """Remove the headline sentence from the lead text to avoid redundancy."""
    if not lead or not headline:
        return lead
    hl_lower = headline.lower().rstrip(".")
    sentences = re.split(r"(?<=[.!?])\s+", lead)
    kept = [s for s in sentences if s.lower().rstrip(".") != hl_lower]
    return " ".join(kept).strip() or lead


# ─────────────────────────────────────────────────────────────────────────────
# Article content helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scrape_article_text(url: str) -> str:
    """Best-effort fetch of article body text from a URL."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        headers = {
            "User-Agent": CHROME_USER_AGENT,
            "Accept": "text/html",
        }
        req = urllib.request.Request(url, headers=headers)
        with urlopen_with_cert_fallback(req, timeout=10) as resp:
            raw = resp.read(500_000).decode("utf-8", errors="replace")
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", raw, re.I | re.S)
        text = " ".join(
            re.sub(r"<[^>]+>", " ", p).strip()
            for p in paragraphs
            if len(re.sub(r"<[^>]+>", "", p).strip()) > 40
        )
        return re.sub(r"\s+", " ", text).strip()[:5000]
    except Exception:
        return ""


def _scrape_article_images(url: str) -> str:
    """Find the best real image URL from the article page HTML.

    Scans ALL <img> tags (not just og:image/twitter:image), skips
    low-value images (logo, icon, avatar, pixel, tracking, badge),
    and prefers images inside <article>/<main> blocks.
    Returns the best image URL or empty string.
    """
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        headers = {
            "User-Agent": CHROME_USER_AGENT,
            "Accept": "text/html,image/webp,image/jpeg,image/png,*/*;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers)
        with urlopen_with_cert_fallback(req, timeout=15) as resp:
            raw = resp.read(500_000).decode("utf-8", errors="replace")
    except Exception:
        return ""

    _skip = {"logo", "icon", "avatar", "pixel", "tracking", "badge", "1x1", "spacer", "sprite", "placeholder", "transparent"}
    _img_exts = (".jpg", ".jpeg", ".png", ".webp")

    # First pass — images inside <article> or <main>
    content_block = re.search(r"<(?:article|main)[^>]*>(.*?)</(?:article|main)>", raw, re.I | re.S)
    search_zone = content_block.group(1) if content_block else raw

    candidates = []
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', search_zone, re.I):
        src = m.group(1).strip()
        if not src.startswith(("http://", "https://")):
            continue
        src_lower = src.lower()
        if not any(ext in src_lower for ext in _img_exts):
            continue
        if any(skip in src_lower for skip in _skip):
            continue
        candidates.append(src)

    if candidates:
        return candidates[0]

    # Second pass — entire page if nothing found in article/main
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', raw, re.I):
        src = m.group(1).strip()
        if not src.startswith(("http://", "https://")):
            continue
        src_lower = src.lower()
        if not any(ext in src_lower for ext in _img_exts):
            continue
        if any(skip in src_lower for skip in _skip):
            continue
        candidates.append(src)

    return candidates[0] if candidates else ""


def _fallback_summary_text(summary: "EmailSummary", headline: str) -> str:
    """Build a fallback summary string when article-level data is too short."""
    parts = [
        summary.summary,
        " ".join(summary.key_points[:3]),
        headline,
    ]
    combined = " ".join(p for p in parts if p and len(p) > 10)
    return re.sub(r"\s+", " ", combined).strip() or headline


# ─────────────────────────────────────────────────────────────────────────────
# Article item accessors
# ─────────────────────────────────────────────────────────────────────────────

def _article_items(summary: "EmailSummary") -> list[dict[str, Any]]:
    items = summary.article_items or []
    if items:
        return items
    if summary.article_url or summary.article_title or summary.article_excerpt:
        return [
            {
                "url": summary.article_url,
                "title": summary.article_title or summary.headline,
                "description": summary.article_excerpt or summary.summary,
                "excerpt": summary.article_excerpt,
                "image_path": summary.article_image_path,
                "image_url": summary.article_image_url,
            }
        ]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Date / time helpers
# ─────────────────────────────────────────────────────────────────────────────

def _email_datetime(source_date: str) -> datetime | None:
    """Parse an email date string (RFC 2822 or ISO) into a timezone-aware datetime."""
    if not source_date:
        return None
    try:
        return parsedate_to_datetime(source_date)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(source_date, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Output cleanup
# ─────────────────────────────────────────────────────────────────────────────

def _cleanup_existing_outputs(output_dir: Path) -> None:
    try:
        if not output_dir.exists():
            return
        for child in output_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    except Exception:
        return
