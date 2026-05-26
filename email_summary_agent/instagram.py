from __future__ import annotations

import html
import hashlib
import json
import random
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from .models import EmailSummary


CANVAS_W = 1080
CANVAS_H = 1350
# Instagram API allows 2–10 children per carousel post.
MAX_CAROUSEL_SLIDES = 10
# Articles per carousel post for both digest and normal emails.
# 8 articles + 1 CTA = 9 slides minimum; overflow slides (same image, extra
# key points) may push the total to the 10-slide Instagram cap.
DIGEST_NEWS_PER_POST = 8
# For regular single-article posts: one article tells its full story across slides.
STORIES_PER_CAROUSEL = 1
# Normal emails now use the same 8-articles-per-post layout as digest emails.
NORMAL_NEWS_PER_POST = 8
# Maximum key points shown on a single article slide before overflow.
# 4 points fit cleanly in the body zone below the article image.
MAX_KP_PER_SLIDE = 4
# Hard minimum readable font size — never go below this on any slide.
FONT_MIN_READABLE = 32
POSTING_SLOTS = ("08:00", "14:00", "18:00", "22:00")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# graitech Design System assets bundled with the package
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
GRAITECH_LOGO_PATH = ASSETS_DIR / "graitech-logo.png"
WATERMARK_CANDIDATES = [PROJECT_ROOT / "GR watermark.png", PROJECT_ROOT / "GR Watermark.png", PROJECT_ROOT / "GR watermark.svg"]
FINAL_LOGO_CANDIDATES = [PROJECT_ROOT / "GR INSTA LOGO.png", PROJECT_ROOT / "GRInstaLogo.png", PROJECT_ROOT / "GR INSTA LOGO.svg"]
ARTICLE_ASSET_DIR = PROJECT_ROOT / "data" / "article_assets"
REFERENCE_IMAGE_DIR = ARTICLE_ASSET_DIR / "reference_images"
# Shared image library — all downloaded images land here for reuse across posts
IMAGE_LIBRARY_DIR = PROJECT_ROOT / "data" / "images"
IMAGE_INDEX_PATH = IMAGE_LIBRARY_DIR / "index.json"
REFERENCE_BRANDS = (
    "OpenAI",
    "Google",
    "DeepMind",
    "Anthropic",
    "Microsoft",
    "Meta",
    "Amazon",
    "AWS",
    "NVIDIA",
    "Apple",
    "LangChain",
    "Mistral",
    "Perplexity",
    "Hugging Face",
    "Cohere",
    "Salesforce",
)
# ── graitech Design System color tokens ────────────────────────────────────
ACCENT_GREEN = "#39FF14"    # neon green primary accent
NEON_RGB = (57, 255, 20)    # ACCENT_GREEN as RGB tuple
PAGE_BLACK = "#000000"      # true black canvas
TEXT_WHITE = "#FFFFFF"      # body text
SOFT_WHITE = "#E8E8E8"      # chalk — secondary text
ASH_GRAY = "#A8A8A8"        # ash — meta/tertiary text
GT_IRON = "#1E1E1E"         # hairline / divider
GT_CEMENT_2 = "#3A3A3A"     # concrete highlight (corner ticks)

# ── Dynamic background theme palette ─────────────────────────────────────────
# Each theme is keyed by content category and defines a dark gradient pair,
# a subtle glow accent colour, a decorative pattern name, and its opacity.
# All base values are kept dark (< 50 per channel) to ensure WCAG AA contrast
# with white text rendered inside the dark overlay cards on every slide.
_BG_THEMES: dict[str, dict] = {
    # Deep cosmic purple — AI research, papers, benchmarks
    "research": {
        "base": (6, 3, 22), "top": (18, 9, 52),
        "glow": (90, 50, 200), "pattern": "hex", "alpha": 14,
    },
    # Deep ocean teal — developer tools, APIs, SDKs
    "tools": {
        "base": (3, 12, 26), "top": (8, 28, 52),
        "glow": (0, 145, 210), "pattern": "circuit", "alpha": 12,
    },
    # Midnight navy-gold — industry news, funding, partnerships
    "industry": {
        "base": (5, 6, 18), "top": (14, 20, 44),
        "glow": (165, 125, 10), "pattern": "lines", "alpha": 16,
    },
    # Dark teal-slate — policy, regulation, law, government
    "policy": {
        "base": (3, 20, 22), "top": (8, 40, 46),
        "glow": (20, 165, 150), "pattern": "cross", "alpha": 10,
    },
    # Deep crimson — breaking news, urgent alerts
    "breaking": {
        "base": (22, 3, 3), "top": (46, 9, 9),
        "glow": (225, 55, 15), "pattern": "burst", "alpha": 12,
    },
    # Deep forest green — health, medicine, biotech
    "health": {
        "base": (3, 20, 10), "top": (8, 44, 22),
        "glow": (18, 185, 75), "pattern": "cross", "alpha": 10,
    },
    # Dark olive — finance, markets, crypto, economy
    "finance": {
        "base": (8, 12, 4), "top": (20, 26, 10),
        "glow": (148, 205, 72), "pattern": "grid", "alpha": 14,
    },
    # Space ink — astronomy, future tech, deep science
    "space": {
        "base": (2, 2, 20), "top": (6, 6, 44),
        "glow": (62, 62, 225), "pattern": "dots", "alpha": 18,
    },
    # Charcoal slate — general AI, miscellaneous (much better than plain black)
    "default": {
        "base": (5, 6, 12), "top": (12, 15, 26),
        "glow": (85, 165, 42), "pattern": "grid", "alpha": 10,
    },
}

# Minimum resolution for "HD quality" images (width × height in pixels)
IMAGE_MIN_HD_W = 1920
IMAGE_MIN_HD_H = 1080
VIDEO_BLOCKED_TERMS = ("video", "videos", "reel", "reels", "clip", "clips", "short", "shorts")
NOISY_ENTITY_TERMS = ("releases", "introduces", "designed", "tracks", "posting", "angle", "primary", "entities")
NOISY_POINT_PREFIXES = (
    "tracks new ai launch activity",
    "best posting angle",
    "primary entities to watch",
    "likely content themes",
)
PUBLIC_BLOCKED_PHRASES = (
    "article 1 title:",
    "article title:",
    "use essential cookies",
    "essential cookies are necessary",
    "advertising partners",
    "show you ads",
    "cookie settings",
    "cookie preferences",
    "customize cookie",
    "accept all cookies",
    "reject all cookies",
    "you may review and change your choices",
    "cookie notice",
    "privacy policy",
    "terms of service",
    "build software better",
    "read every piece of feedback",
    "gitHub is where people build software".lower(),
    "more than 150 million people",
    "contribute to over 420 million projects",
    "get tips, technical guides, and best practices",
    "sign up for",
    "subscribe to",
    "select your cookie",
    "deactivated",
    "footer of this site",
    "read our cookie",
    "how we use them",
    "manage your preferences",
    "opt out",
    "gdpr",
    "ccpa",
    "data protection",
    "third-party cookies",
    "tracking cookies",
    "functional cookies",
    "performance cookies",
    "analytics cookies",
    "marketing cookies",
    "view in browser",
    "unsubscribe",
    "manage subscriptions",
    "email preferences",
    "you are receiving this",
    "sent to you because",
    "no longer wish to receive",
)
STOP_IMAGE_TOKENS = frozenset(
    {
        "about",
        "after",
        "article",
        "blog",
        "content",
        "cookie",
        "from",
        "image",
        "launch",
        "latest",
        "more",
        "news",
        "privacy",
        "release",
        "story",
        "summary",
        "technology",
        "this",
        "update",
        "with",
    }
)


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
    db_path: Path | None = None,
) -> list[Path]:
    """Create Instagram carousel batches.

    A single-story summary produces one image slide, three content slides, and
    one CTA slide. Digest summaries are split into parts of up to two stories
    each because Instagram caps carousel children at 10 media items:
    2 stories * 4 slides + one CTA slide.

    db_path: optional path to the agent SQLite database.  When provided,
             previously used image paths are loaded for cross-batch dedup and
             newly used paths are persisted after each carousel is rendered.
    """
    if not summaries:
        return []
    if clear_existing:
        _cleanup_existing_outputs(output_dir)

    now = generated_at or datetime.now(timezone.utc).astimezone()
    batch_dir = output_dir / now.strftime("%Y%m%d-%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Load previously used images from SQLite for cross-batch deduplication.
    global_used_image_paths: set[str] = _load_used_images_from_db(db_path)

    carousel_dirs: list[Path] = []
    index_rows: list[str] = []
    carousel_index = 0
    for summary in summaries:
        email_dt = _email_datetime(summary.source_date) or now
        for part_summary in _split_summary_for_carousels(summary):
            carousel_index += 1
            index = carousel_index
            slug = _slugify(part_summary.headline or part_summary.subject or f"ai-news-{index}")
            folder_name = f"{index:02d}_{email_dt.strftime('%Y%m%d-%H%M')}_{slug}"
            carousel_dir = batch_dir / folder_name
            carousel_dir.mkdir(parents=True, exist_ok=True)

            # Build slides, seeding the dedup set from ALL previously used
            # paths (DB history + any carousels already built this batch).
            slides = _build_slide_specs(part_summary, email_dt, global_used_image_paths)
            # Immediately extend global set so the next carousel in this batch
            # cannot reuse any image selected for this one.
            for slide in slides:
                img = str(slide.get("image_path", "")).strip()
                if img:
                    global_used_image_paths.add(img)

            qa_issues_any: list[str] = []
            for slide_number, slide in enumerate(slides, start=1):
                slide_path = carousel_dir / f"slide_{slide_number:02d}.png"
                _write_slide_png(
                    slide_path,
                    slide_number=slide_number,
                    total_slides=len(slides),
                    slide=slide,
                    email_dt=email_dt,
                )
                # Visual QA — log any issues but do not abort rendering.
                qa_issues = _qa_slide_png(slide_path)
                if qa_issues:
                    qa_issues_any.extend([f"slide_{slide_number:02d}: {issue}" for issue in qa_issues])

            if qa_issues_any:
                (carousel_dir / "qa_issues.txt").write_text(
                    "\n".join(qa_issues_any), encoding="utf-8"
                )

            # Persist newly used images back to SQLite.
            _save_used_images_to_db(db_path, global_used_image_paths)

            caption = _build_caption(part_summary)
            (carousel_dir / "caption.txt").write_text(caption, encoding="utf-8")
            (carousel_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "email_received_at": email_dt.isoformat(timespec="minutes"),
                        "recommended_post_time": POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)],
                        "headline": part_summary.headline,
                        "subject": part_summary.subject,
                        "source_date": part_summary.source_date,
                        "companies": part_summary.companies,
                        "models": part_summary.models,
                        "topics": part_summary.topics,
                        "article_url": part_summary.article_url,
                        "article_title": part_summary.article_title,
                        "article_image_path": part_summary.article_image_path,
                        "article_image_url": part_summary.article_image_url,
                        "article_items": part_summary.article_items or [],
                        "carousel_part": getattr(part_summary, "_carousel_part", None),
                        "carousel_total_parts": getattr(part_summary, "_carousel_total_parts", None),
                        "slides": [slide["title"] for slide in slides],
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            index_rows.append(
                f'<li><a href="{carousel_dir.name}/slide_01.png">{html.escape(part_summary.headline)}</a> '
                f'<span>{len(slides)} slides - {POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)]}</span></li>'
            )
            carousel_dirs.append(carousel_dir)

    (batch_dir / "index.html").write_text(_render_index(index_rows), encoding="utf-8")
    return carousel_dirs


def _is_digest_summary(summary: EmailSummary) -> bool:
    """Return True when this summary represents a daily digest email.

    Digest emails are the once-per-day bulk emails containing 15–50 news items.
    Normal emails arrive throughout the day with 1–N articles (N is typically small).

    Detection rules:
    1. subject/headline matches a known digest pattern (strongest signal)
    2. article_items >= 8 (genuine digest — normal emails rarely exceed 4-5 articles)
    """
    import re as _re
    subject = summary.subject or summary.headline or ""
    if _re.search(
        r"\b(AI\s+Alert|AI\s+Digest|AI\s+Updates|daily\s+digest|news\s+digest|"
        r"morning\s+brief|evening\s+brief|weekly\s+digest|ai\s+roundup|tech\s+digest)\b",
        subject, _re.I,
    ):
        return True
    articles = _article_items(summary)
    # Only treat as digest when article count is large enough to be a bulk email.
    # Normal emails with 2-7 articles are still treated as normal posts.
    return len(articles) >= 8


def _split_summary_for_carousels(summary: EmailSummary) -> list[EmailSummary]:
    """Split a summary into one or more carousel-sized EmailSummary objects.

    DIGEST emails (8+ article_items OR subject matches digest pattern):
        Each article_item becomes one digest slide.
        Posts are capped at DIGEST_NEWS_PER_POST news slides + 1 CTA = MAX_CAROUSEL_SLIDES.
        If the digest has more items than fit in one post, extra posts are created.

    NORMAL emails (< 8 article_items, no digest subject):
        Articles are grouped in batches of NORMAL_NEWS_PER_POST (8) per carousel.
        Each batch becomes one post using the same unified layout as digest posts.
    """
    articles = _article_items(summary)

    # ── Normal email — group articles in batches of NORMAL_NEWS_PER_POST per post ─
    if not _is_digest_summary(summary):
        articles = _article_items(summary)
        if len(articles) <= NORMAL_NEWS_PER_POST:
            return [summary]
        # Split into groups of NORMAL_NEWS_PER_POST articles
        normal_parts: list[EmailSummary] = []
        for chunk_start in range(0, len(articles), NORMAL_NEWS_PER_POST):
            chunk = articles[chunk_start:chunk_start + NORMAL_NEWS_PER_POST]
            first = chunk[0]
            part = EmailSummary(
                message_key=f"{summary.message_key}:n{chunk_start // NORMAL_NEWS_PER_POST + 1}",
                subject=summary.subject,
                source_date=summary.source_date,
                headline=summary.headline,
                summary=summary.summary,
                key_points=summary.key_points,
                companies=summary.companies,
                models=summary.models,
                topics=summary.topics,
                confidence=summary.confidence,
                article_url=str(first.get("url", "")),
                article_title=str(first.get("title", "")),
                article_image_path=str(first.get("image_path", "")),
                article_image_url=str(first.get("image_url", "")),
                article_excerpt=str(first.get("excerpt") or first.get("description") or ""),
                article_items=chunk,
            )
            normal_parts.append(part)
        return normal_parts

    # ── Digest email — split into posts of DIGEST_NEWS_PER_POST items ─────────
    if not articles:
        return [summary]

    chunks = [
        articles[i : i + DIGEST_NEWS_PER_POST]
        for i in range(0, len(articles), DIGEST_NEWS_PER_POST)
    ]
    total_parts = len(chunks)
    parts: list[EmailSummary] = []

    base_headline = _clean_headline(summary.headline or summary.subject or "Daily AI Digest")

    for part_number, chunk in enumerate(chunks, start=1):
        if total_parts > 1:
            headline = f"{base_headline} — Part {part_number} of {total_parts}"
        else:
            headline = base_headline

        first = chunk[0]
        part = EmailSummary(
            message_key=f"{summary.message_key}:part:{part_number}",
            subject=summary.subject,
            source_date=summary.source_date,
            headline=headline,
            summary=summary.summary,
            key_points=summary.key_points,
            companies=summary.companies,
            models=summary.models,
            topics=summary.topics,
            confidence=summary.confidence,
            article_url=str(first.get("url", "")),
            article_title=str(first.get("title", "")),
            article_image_path=str(first.get("image_path", "")),
            article_image_url=str(first.get("image_url", "")),
            article_excerpt=str(first.get("excerpt") or first.get("description") or ""),
            article_items=chunk,
        )
        object.__setattr__(part, "_carousel_part", part_number)
        object.__setattr__(part, "_carousel_total_parts", total_parts)
        object.__setattr__(part, "_is_digest", True)
        parts.append(part)

    return parts


def _clean_headline(text: str) -> str:
    """Sanitise a headline string for use as a slide title.

    Steps applied (in order):
    1. Collapse whitespace.
    2. Strip trailing dots / ellipsis.
    3. Strip leading punctuation garbage  (': ', '– ', '— ', etc.)
    4. Remove publication pipe suffix  (' | Publication Name').
    5. Reject URL-path slugs (strings that look like /word-word-word paths).
    6. Trim at the last *sentence boundary* that fits within MAX_TITLE_CHARS
       so we never cut mid-word or mid-sentence.
    """
    MAX_TITLE_CHARS = 90          # hard cap before sentence-boundary trimming

    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"[.…]+$", "", text).strip()

    # Strip leading punctuation garbage: ': ', '– ', '— ', '| ', etc.
    text = re.sub(r"^[\s:–—|]+", "", text).strip()

    # Strip publication pipe suffix: "Headline | TechCrunch" → "Headline"
    text = re.sub(r"\s*\|[^|]{1,40}$", "", text).strip()

    # Reject URL slugs — a title that's mostly lowercase-hyphenated words
    # starting with '/' or looking like a URL path fragment.
    if re.match(r"^/[\w/-]{10,}$", text):
        return ""
    # Also reject titles that are purely a URL slug pattern (no spaces, mostly hyphens)
    if re.match(r"^[\w][\w-]{10,}$", text) and text.count("-") > text.count(" ") * 2 + 2:
        return ""
    # Reject all-uppercase hyphenated slugs (e.g. "ERA-IS-CREATING-A-BUG-HUNTING-ARMS-RAC")
    if re.match(r"^[A-Z][A-Z0-9-]{10,}$", text) and "-" in text:
        return ""

    # Reject single-character first-word fragments (e.g. "S PRICES - I FOUND...")
    # These occur when email rendering truncates a word at the boundary.
    words = text.split()
    if words and len(words[0]) == 1 and not words[0].isdigit() and words[0] not in ("A", "I"):
        return ""

    # Reject very short titles that look like section headers / UI labels
    # (e.g. "Client Challenge", "Hat Templates") rather than real article titles.
    if len(text) < 10:
        return ""

    # Strip author-name prefix: "Firstname Lastname: Article Title" or
    # "Firstname Lastname Article Title" where the first two words look like a name.
    name_match = re.match(r"^([A-Z][a-z]+ [A-Z][a-z]+)[:\s]\s*(.+)$", text)
    if name_match and len(name_match.group(2)) > 20:
        text = name_match.group(2).strip()

    # Trim at sentence boundary within limit
    if len(text) <= MAX_TITLE_CHARS:
        return text

    # Walk back to the nearest sentence end within limit
    region = text[:MAX_TITLE_CHARS]
    for terminator in (".", "!", "?"):
        pos = region.rfind(terminator)
        if pos > MAX_TITLE_CHARS // 2:       # must be at least halfway in
            return text[:pos + 1].strip()

    # No sentence boundary — trim at last word boundary, don't add dots
    return region.rsplit(" ", 1)[0].rstrip(".,;:—-").strip()


def _build_slide_specs(
    summary: EmailSummary,
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Route to the correct slide builder based on whether this is a digest or a normal post."""
    if getattr(summary, "_is_digest", False) or _is_digest_summary(summary):
        return _build_digest_slide_specs(summary, email_dt, initial_used_paths)
    return _build_normal_slide_specs(summary, email_dt, initial_used_paths)


def _build_fallback_single_slide(
    summary: EmailSummary,
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return a minimal 2-slide carousel (1 digest + 1 CTA) when no article_items exist.

    Used as the safety net inside _build_digest_slide_specs when the summary
    has no structured article list but still carries a headline / summary text.
    """
    used_image_urls: set[str] = set()
    used_image_paths: set[str] = set(initial_used_paths or ())
    carousel_theme = _pick_bg_theme_from_summary(summary)

    # Treat the whole summary as one anonymous article.
    headline = _clean_headline(
        _clean_public_text(str(summary.headline or summary.subject or "AI Update"))
    ) or "AI Update"
    url = str(summary.article_url or "")
    topic = ", ".join(summary.topics[:2]) or headline
    source_label = _source_label_from_url(url) if url else ""

    synthetic_article: dict[str, Any] = {
        "title": headline,
        "url": url,
        "description": summary.article_excerpt or summary.summary or "",
        "image_path": getattr(summary, "article_image_path", None) or "",
        "image_url": getattr(summary, "article_image_url", None) or "",
    }

    # Attempt og:image fetch if we have a URL.
    if url and not synthetic_article["image_url"]:
        og = _fetch_og_image_from_url(url)
        if og:
            synthetic_article["image_url"] = og

    image_path = _select_unique_article_image(
        synthetic_article, topic, used_image_urls, used_image_paths
    )
    key_points = _extract_instagram_key_points(synthetic_article, summary, max_points=4)
    body_text = "\n".join(key_points) if key_points else _clean_public_text(summary.summary or "")[:300]

    slides: list[dict[str, Any]] = [
        {
            "kind": "digest",
            "slide_index": 1,
            "eyebrow": _pick_digest_eyebrow(synthetic_article, summary),
            "title": headline,
            "body": body_text,
            "image_path": image_path,
            "topic": topic,
            "url": url,
            "source_label": source_label,
            "bg_theme": carousel_theme,
        },
        {
            "kind": "cta",
            "eyebrow": "GRAITECH",
            "title": "Follow for the next AI briefing",
            "body": "LIKE | COMMENT | FOLLOW | SAVE",
            "image_path": "",
            "source_label": "",
            "bg_theme": carousel_theme,
        },
    ]
    return slides


def _build_digest_slide_specs(
    summary: EmailSummary,
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build slides for a digest (or unified normal) email carousel.

    Layout per article slide:
        • Top ~38%  : article's own image (fetched from og:image / scraped)
        • Bottom ~62%: eyebrow | headline | 3–4 key points | source credit
        • Overflow slide: if an article has more than MAX_KP_PER_SLIDE points,
          a second slide is created with the SAME image and remaining points.
        • Final slide: CTA

    Processing per article (mandatory):
        1. Follow the article URL and read the full text.
        2. Fetch the og:image (or twitter:image / first <img>) for that article.
        3. Summarise the full text and generate 3–5 key points.

    Total slides: up to 8 article slides (+ possible overflow slides)
                  + 1 CTA ≤ 10 (Instagram carousel cap).

    Images are deduplicated across all slides in this carousel AND across all
    previously published batches (via initial_used_paths seeded from the DB).
    """
    articles = _article_items(summary)
    if not articles:
        # No articles at all — build a minimal single-slide summary post.
        return _build_fallback_single_slide(summary, email_dt, initial_used_paths)

    slides: list[dict[str, Any]] = []
    # Seed from cross-batch history so previously-used images are never reused.
    used_image_urls: set[str] = set()
    used_image_paths: set[str] = set(initial_used_paths or ())

    # Pick ONE background theme for the whole carousel (consistent visual identity).
    carousel_theme = _pick_bg_theme_from_summary(summary)

    # Reserve 1 slot for the CTA slide so it never gets cut off.
    max_content_slides = MAX_CAROUSEL_SLIDES - 1

    # Cross-article dedup set so the same key point never appears on two slides.
    used_key_fingerprints: set[str] = set()

    for article_index, article in enumerate(articles[:DIGEST_NEWS_PER_POST], start=1):
        if len(slides) >= max_content_slides:
            break

        # ── Step 1: Mandatory full-article scrape ────────────────────────────
        url = str(article.get("url") or "")
        article = dict(article)   # work on a copy so we don't mutate the source
        if url and not article.get("scraped_content"):
            scraped = _scrape_article_text(url)
            if scraped:
                article["scraped_content"] = scraped

        # ── Step 2: Mandatory og:image fetch (overrides pre-populated values) ─
        if url and not article.get("image_url") and not article.get("image_path"):
            og_url = _fetch_og_image_from_url(url)
            if og_url:
                article["image_url"] = og_url

        headline = _clean_headline(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
        ) or "AI Update"

        topic = ", ".join(summary.topics[:2]) or headline
        source_label = _source_label_from_url(url)

        # ── Step 3: Fetch the article image for this slide ───────────────────
        image_path = _select_unique_article_image(
            article, topic, used_image_urls, used_image_paths
        )

        # ── Step 4: Generate 3–5 key points from the full article content ────
        all_key_points = _extract_instagram_key_points(
            article, summary, max_points=5, used_fingerprints=used_key_fingerprints
        )

        # ── Step 5: Build primary slide (up to MAX_KP_PER_SLIDE points) ──────
        primary_points = all_key_points[:MAX_KP_PER_SLIDE]
        overflow_points = all_key_points[MAX_KP_PER_SLIDE:]

        slides.append({
            "kind": "digest",
            "slide_index": article_index,
            "eyebrow": _pick_digest_eyebrow(article, summary),
            "title": headline,
            "body": "\n".join(primary_points),
            "image_path": image_path,
            "topic": topic,
            "url": url,
            "source_label": source_label,
            "bg_theme": carousel_theme,
        })

        # ── Step 6: Overflow slide — same image, remaining key points ─────────
        # Only created if there are leftover points AND a free slot exists.
        if overflow_points and len(slides) < max_content_slides:
            slides.append({
                "kind": "digest",
                "slide_index": article_index,        # same article index
                "eyebrow": _pick_digest_eyebrow(article, summary),
                "title": headline,                   # same headline
                "body": "\n".join(overflow_points),
                "image_path": image_path,            # same image — spec requirement
                "topic": topic,
                "url": url,
                "source_label": source_label,
                "bg_theme": carousel_theme,
            })

    # CTA slide — always appended, slot was reserved above.
    slides.append({
        "kind": "cta",
        "eyebrow": "GRAITECH",
        "title": "Follow for the next AI briefing",
        "body": "LIKE | COMMENT | FOLLOW | SAVE",
        "image_path": "",
        "source_label": "",
        "bg_theme": carousel_theme,
    })

    return slides


def _build_normal_slide_specs(
    summary: EmailSummary,
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build the carousel for a regular (non-digest) email.

    Normal emails now use the same unified 1-slide-per-article layout as digest
    emails: image + key points per article, 8 articles per post, CTA at end.
    This function delegates directly to _build_digest_slide_specs which
    implements the full shared pipeline (mandatory scraping, og:image fetch,
    overflow slides, cross-article dedup).
    """
    # Ensure the summary has article_items so the digest builder can process it.
    if not (summary.article_items) and (
        summary.article_url or summary.article_title
    ):
        object.__setattr__(
            summary,
            "article_items",
            [
                {
                    "url": summary.article_url,
                    "title": summary.article_title or summary.headline or summary.subject or "AI update",
                    "description": summary.article_excerpt or summary.summary,
                    "excerpt": summary.article_excerpt,
                    "image_path": summary.article_image_path,
                    "image_url": summary.article_image_url,
                }
            ],
        )
    return _build_digest_slide_specs(summary, email_dt, initial_used_paths)


def _build_digest_slide_brief(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Build a brief, complete 2–3 sentence summary for a single digest slide.

    Uses the pre-structured narrative sections when available.  Falls back
    gracefully through description → excerpt → key_points → generic summary.
    Never adds truncation dots — returns complete sentences only.
    """
    what_happened = _clean_public_text(str(article.get("what_happened") or ""))
    why_matters = _clean_public_text(str(article.get("why_matters") or ""))

    if what_happened and why_matters:
        combined = f"{what_happened} {why_matters}"
        return _trim_no_dots(combined, 480)

    if what_happened:
        # Pad with description if we only have what_happened
        desc = _clean_public_text(str(article.get("description") or article.get("excerpt") or ""))
        combined = f"{what_happened} {desc}".strip()
        return _trim_no_dots(combined, 480)

    # Fallback hierarchy
    for key in ("summary", "description", "excerpt"):
        text = _clean_public_text(str(article.get(key) or ""))
        if len(text) >= 80:
            return _trim_no_dots(text, 480)

    # Last resort: stitch key points into prose
    points = [_clean_public_text(str(p)) for p in article.get("key_points", []) if str(p).strip()]
    if points:
        return _trim_no_dots(" ".join(points[:3]), 480)

    return _trim_no_dots(summary.summary or summary.headline or "AI update.", 480)


def _pick_digest_eyebrow(article: dict[str, Any], summary: EmailSummary) -> str:
    """Pick an appropriate eyebrow category label for a digest slide."""
    _EYEBROW_RULES = {
        "🔬 RESEARCH":  ("paper", "research", "arxiv", "study", "benchmark", "dataset"),
        "⚡ BREAKING":  ("breaking", "just announced", "just released", "today"),
        "💼 INDUSTRY":  ("funding", "acquisition", "valuation", "ipo", "revenue", "partnership"),
        "🌍 POLICY":    ("regulation", "policy", "law", "ban", "government", "eu", "senate"),
        "🛠️ TOOLS":     ("api", "sdk", "tool", "plugin", "open-source", "github", "developer"),
        "📊 DATA":      ("benchmark", "performance", "statistic", "report", "survey"),
        "🧠 DEEP DIVE": ("how it works", "architecture", "technical", "explained"),
    }
    combined = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        " ".join(summary.topics),
    ]).lower()

    for label, keywords in _EYEBROW_RULES.items():
        if any(kw in combined for kw in keywords):
            return label
    return "🤖 AI NEWS"


def _tighten(text: str, limit: int) -> str:
    """Trim text to a word boundary, appending '...' if truncated."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _trim_no_dots(text: str, limit: int) -> str:
    """Trim text to a word boundary without adding trailing dots.

    Unlike _tighten(), this never appends '...' — the sentence is simply cut
    cleanly at the last complete word that fits within `limit` characters.
    """
    text = re.sub(r"\s+", " ", text or "").strip().rstrip(".…")
    if len(text) <= limit:
        # Still ensure the text ends with a proper sentence terminator.
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


def _scrape_article_text(url: str) -> str:
    """Best-effort fetch of article body text from a URL for slide content enrichment."""
    if not url or not url.startswith(("http://", "https://")):
        return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0)",
            "Accept": "text/html",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def _fallback_summary_text(summary: "EmailSummary", headline: str) -> str:
    """Build a fallback summary string when article-level data is too short."""
    parts = [
        summary.summary,
        " ".join(summary.key_points[:3]),
        headline,
    ]
    combined = " ".join(p for p in parts if p and len(p) > 10)
    return re.sub(r"\s+", " ", combined).strip() or headline


def _dedupe_lead_text(lead: str, headline: str) -> str:
    """Remove the headline sentence from the lead text to avoid redundancy in captions."""
    if not lead or not headline:
        return lead
    hl_lower = headline.lower().rstrip(".")
    sentences = re.split(r"(?<=[.!?])\s+", lead)
    kept = [s for s in sentences if s.lower().rstrip(".") != hl_lower]
    return " ".join(kept).strip() or lead


def _slugify(text: str) -> str:
    """Convert text into a filesystem-safe ASCII slug."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:60] or "post"


# ── Adaptive typography helpers ───────────────────────────────────────────────

def _auto_fit_font(
    image_font,
    text: str,
    box_width: int,
    box_height: int,
    bold: bool = False,
    size_max: int = 72,
    size_min: int = 28,
    step: int = 2,
    max_lines: int = 10,
    display: bool = False,
) -> Any:
    """Return the largest font that fits `text` inside box_width × box_height.

    Starts at size_max and steps down by `step` until the rendered text block
    fits.  Never goes below max(size_min, FONT_MIN_READABLE) so text always
    stays legible.  Returns the font object.
    """
    # Enforce the global readable minimum — callers may pass a lower size_min
    # but we never render below FONT_MIN_READABLE.
    effective_min = max(size_min, FONT_MIN_READABLE)
    # We need a temporary draw surface for measuring — use a tiny proxy image.
    from PIL import Image as _PIL_Image, ImageDraw as _PIL_Draw
    _probe = _PIL_Image.new("L", (box_width + 4, max(box_height + 4, 10)))
    _draw = _PIL_Draw.Draw(_probe)

    for size in range(size_max, effective_min - 1, -step):
        font = _font(image_font, size, bold=bold, display=display)
        lines = _wrap_to_width(_draw, text, font, box_width, max_lines)
        total_h = 0
        for line in lines:
            bbox = _draw.textbbox((0, 0), line, font=font)
            total_h += (bbox[3] - bbox[1]) + 8
        if total_h <= box_height:
            return font
    return _font(image_font, effective_min, bold=bold)


def _draw_autofit_text(
    draw,
    text: str,
    box: tuple[int, int, int, int],
    image_font,
    fill: str,
    bold: bool = False,
    size_max: int = 72,
    size_min: int = 28,
    max_lines: int = 10,
    align: str = "center",
    display: bool = False,
) -> tuple[int, str]:
    """Draw text auto-sized to fit inside `box`.

    Returns (last_y, overflow_text) where:
    - last_y is the y-pixel position after the last drawn line
    - overflow_text is any text that did not fit (empty string when all fits)

    Text is never truncated or ended with dots.  If the content does not fit
    at the minimum readable font size the overflow is returned so the caller
    can push it onto the next slide.
    """
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    font = _auto_fit_font(
        image_font, text, width, height,
        bold=bold, size_max=size_max, size_min=size_min, max_lines=max_lines,
        display=display,
    )
    lines, overflow_text = _wrap_to_width_overflow(draw, text, font, width, max_lines)

    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    gap = 10
    block_h = sum(line_heights) + max(0, len(lines) - 1) * gap
    y = y1 + max(0, (height - block_h) // 2)

    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        if align == "center":
            x = x1 + max(0, (width - line_w) // 2)
        elif align == "left":
            x = x1
        else:
            x = x1 + max(0, width - line_w)
        draw.text((x, y), line, fill=fill, font=font)
        y += line_heights[idx] + gap

    return y, overflow_text


# ── Digest slide renderer ─────────────────────────────────────────────────────

def _write_digest_slide(
    image,
    draw,
    slide_number: int,
    total_slides: int,
    slide: dict[str, Any],
    image_font,
    image_cls,
    draw_cls,
    enhance_cls,
    filter_cls,
    ops_cls,
) -> None:
    """Render a digest carousel slide.

    Layout (1080 × 1350 px):
      • y   0 – 700  : Article image (full width, rounded corners)
      • y 700 – 760  : Eyebrow chip + slide counter
      • y 760 – 920  : Headline (auto-sized, never truncated)
      • y 920 – 1230 : Brief summary body (auto-sized, no dots)
      • y1230 – 1310 : Source credit + progress bar

    NOTE: background is already drawn by the caller (_write_slide_png) before
    dispatching here — do NOT call _draw_background_grid or _draw_accent_frame.
    """

    margin = 54
    image_box = (margin, 40, CANVAS_W - margin, 700)

    # ── Article image (top half) — AI-generated if no source found ────────────
    artwork = _load_artwork(
        slide.get("image_path", ""),
        slide.get("topic", "AI"),
        image_box,
        image_cls, draw_cls, enhance_cls, filter_cls, ops_cls,
        fallback_text=slide.get("title", "") + " " + slide.get("body", ""),
    )
    if artwork is not None:
        _paste_contained(image, artwork, image_box, radius=16, pad=0, cover=True)
        draw.rounded_rectangle(image_box, radius=16, outline=(57, 255, 20, 80), width=1)

    # ── Eyebrow (neon green mono) — no slide counter in content area ─────────
    font_eyebrow = _font(image_font, 30, bold=True, mono=True)
    eyebrow = str(slide.get("eyebrow", "AI NEWS")).upper()
    # Remove emoji from eyebrow for brand consistency
    eyebrow_clean = re.sub(r"[^\x00-\x7F]+", "", eyebrow).strip()
    if not eyebrow_clean:
        eyebrow_clean = "AI NEWS"
    draw.text((margin, 718), eyebrow_clean, fill=ACCENT_GREEN, font=font_eyebrow)

    # Neon rule below eyebrow
    _gt_draw_rule(draw, margin, 746)

    # ── Headline — Anton SC, auto-sized, white, no truncation ────────────────
    headline = _clean_headline(str(slide.get("title", "AI Update"))).upper()
    headline_box = (margin, 770, CANVAS_W - margin, 950)
    _draw_autofit_text(
        draw, headline, headline_box, image_font,
        fill=TEXT_WHITE, bold=False, size_max=72, size_min=32, max_lines=3, align="left",
        display=True,
    )

    # ── Key points / body — bullet points left-aligned ───────────────────────
    body_text = str(slide.get("body", "")).strip()
    if body_text:
        body_box = (margin, 958, CANVAS_W - margin, 1195)
        # Check if body contains bullet points (• prefix)
        is_bullets = body_text.startswith("•") or "\n•" in body_text
        body_align = "left"
        if is_bullets:
            # Render bullet list directly
            _gt_render_list_slide_bullets_only(draw, image_font, body_text, margin, 958, CANVAS_W - margin, 1195)
        else:
            _draw_autofit_text(
                draw, body_text, body_box, image_font,
                fill=SOFT_WHITE, bold=False, size_max=36, size_min=FONT_MIN_READABLE, max_lines=7, align="left",
            )

    # ── Source credit — bottom, mono, muted ──────────────────────────────────
    source = str(slide.get("source_label", "")).strip()
    if source:
        font_source = _font(image_font, 18, mono=True)
        draw.text(
            (margin, 1210),
            f"SOURCE: {source.upper()}",
            fill=(200, 200, 200, 255),
            font=font_source,
        )



def _write_slide_png(path: Path, slide_number: int, total_slides: int, slide: dict[str, Any], email_dt: datetime) -> None:
    """Render a single carousel slide using the graitech Design System.

    Delegates to the Playwright-based HTML renderer in renderer.py, which
    injects article content into the official Graitech HTML templates and
    screenshots the result at 1080×1350 px.  This guarantees pixel-perfect
    fidelity to the design system — the correct fonts, concrete texture,
    neon accents, and corner ticks — with no manual PIL pixel-pushing.

    Falls back to the legacy PIL renderer only if Playwright is unavailable.
    """
    try:
        from .renderer import render_slide_to_png
        render_slide_to_png(path, slide, slide_number, total_slides, email_dt)
        return
    except Exception as _pw_err:
        print(f"[renderer] Playwright render failed for {path.name}: {_pw_err}  — falling back to PIL", flush=True)

    # ── Legacy PIL fallback ────────────────────────────────────────────────
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    _gt_draw_background(image, draw)

    kind = slide.get("kind", "")
    if kind == "digest":
        _write_digest_slide(
            image, draw, slide_number, total_slides, slide,
            ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps,
        )
    elif kind == "title":
        _gt_render_title_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide)
    elif kind == "list":
        _gt_render_list_slide(draw, ImageFont, slide)
    elif kind == "cta":
        _gt_render_cta_slide(image, draw, ImageFont, slide)
    else:
        _gt_render_legacy_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide)

    _gt_draw_chrome(image, draw, ImageFont, slide_number, total_slides, slide_kind=kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    if image.mode == "RGBA":
        image = image.convert("RGB")
    image.save(path, "PNG", optimize=True)


# ── graitech background renderer ─────────────────────────────────────────────

def _gt_draw_background(image, draw) -> None:
    """Render the graitech concrete-textured black background with multi-scale grain and neon glow."""
    import random as _rng
    from PIL import Image as _Img, ImageFilter as _IF
    # Solid black canvas
    draw.rectangle((0, 0, CANVAS_W, CANVAS_H), fill=(0, 0, 0, 255))
    # Multi-scale concrete grain — three passes at different densities and scales
    rng = _rng.Random(7331)
    # Fine grain (every 2px)
    for y in range(0, CANVAS_H, 2):
        for x in range(0, CANVAS_W, 2):
            if rng.random() < 0.055:
                a = rng.randint(3, 7)
                draw.point((x, y), fill=(255, 255, 255, a))
    # Medium grain (every 5px)
    for y in range(0, CANVAS_H, 5):
        for x in range(0, CANVAS_W, 5):
            if rng.random() < 0.07:
                a = rng.randint(4, 10)
                draw.point((x, y), fill=(200, 200, 200, a))
    # Coarse grain (every 11px)
    for y in range(0, CANVAS_H, 11):
        for x in range(0, CANVAS_W, 11):
            if rng.random() < 0.04:
                a = rng.randint(2, 6)
                draw.point((x, y), fill=(255, 255, 255, a))
    # Subtle scan-lines (every 4px, very faint)
    for y in range(0, CANVAS_H, 4):
        draw.line((0, y, CANVAS_W, y), fill=(0, 0, 0, 18))
    # Faint neon-green corner glow (bottom-left, brand accent)
    try:
        glow_layer = _Img.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        from PIL import ImageDraw as _ID
        gd = _ID.Draw(glow_layer)
        for radius in range(300, 0, -30):
            alpha = max(0, int(6 * (1 - radius / 300)))
            gd.ellipse((-radius, CANVAS_H - radius, radius, CANVAS_H + radius),
                       fill=(57, 255, 20, alpha))
        glow_layer = glow_layer.filter(_IF.GaussianBlur(radius=40))
        image.alpha_composite(glow_layer)
    except Exception:
        pass


# ── graitech chrome (logo + handle + page indicator) ─────────────────────────

def _gt_draw_chrome(image, draw, ImageFont, slide_number: int, total_slides: int, slide_kind: str = "") -> None:
    """Draw fixed chrome elements on every slide."""
    # Corner L-bracket ticks (content safe-area boundary markers)
    TICK = 20
    TICK_C = (58, 58, 58, 200)  # --gt-cement-2 with alpha
    # Top-left tick
    draw.line((75, 215, 75 + TICK, 215), fill=TICK_C, width=2)
    draw.line((75, 215, 75, 215 + TICK), fill=TICK_C, width=2)
    # Top-right tick
    draw.line((1005 - TICK, 215, 1005, 215), fill=TICK_C, width=2)
    draw.line((1005, 215, 1005, 215 + TICK), fill=TICK_C, width=2)
    # Bottom-left tick
    draw.line((75, 1195 - TICK, 75, 1195), fill=TICK_C, width=2)
    draw.line((75, 1195, 75 + TICK, 1195), fill=TICK_C, width=2)
    # Bottom-right tick
    draw.line((1005, 1195 - TICK, 1005, 1195), fill=TICK_C, width=2)
    draw.line((1005 - TICK, 1195, 1005, 1195), fill=TICK_C, width=2)

    # Logo — positioned to never overlap article image content.
    # Digest slides have a full-width image at y=40-700; place logo
    # at the bottom-right corner of that zone.  All other slides have
    # images only at y≥880, so the default top-right position is safe.
    logo_size = 100
    if slide_kind == "digest":
        logo_right = 64
        logo_top = 700 - logo_size - 16
    else:
        logo_right = 56
        logo_top = 56
    # Dark pill behind logo so it's readable on any background
    pill_pad = 10
    lx = CANVAS_W - logo_right - logo_size
    ly = logo_top
    draw.rounded_rectangle(
        (lx - pill_pad, ly - pill_pad, lx + logo_size + pill_pad, ly + logo_size + pill_pad),
        radius=14, fill=(0, 0, 0, 200),
    )
    _gt_draw_logo(image, right=logo_right, top=logo_top, size=logo_size)

    # @graitech handle bottom-left (56px from each edge)
    font_handle = _font(ImageFont, 24, bold=True, mono=True)
    dot_x, dot_y = 56, CANVAS_H - 56 - 24
    # Neon dot
    draw.ellipse((dot_x, dot_y + 6, dot_x + 10, dot_y + 16), fill=NEON_RGB + (255,))
    # Handle text
    draw.text((dot_x + 18, dot_y), "@graitech", fill=TEXT_WHITE, font=font_handle)

    # Page indicator bottom-center — 01 / 05 — with hairline bars
    page_text = f"{slide_number:02d} / {total_slides:02d}"
    font_page = _font(ImageFont, 18, bold=False, mono=True)
    try:
        bbox = draw.textbbox((0, 0), page_text, font=font_page)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = 80, 18
    px = (CANVAS_W - tw) // 2
    py = CANVAS_H - 56 - th
    BAR_W = 28
    BAR_Y = py + th // 2
    BAR_C = (58, 58, 58, 200)
    draw.line((px - BAR_W - 8, BAR_Y, px - 8, BAR_Y), fill=BAR_C, width=1)
    draw.line((px + tw + 8, BAR_Y, px + tw + BAR_W + 8, BAR_Y), fill=BAR_C, width=1)
    # Page number with neon-green current page
    num_parts = page_text.split(" / ")
    if len(num_parts) == 2:
        font_num = _font(ImageFont, 18, bold=True, mono=True)
        try:
            n1_bbox = draw.textbbox((0, 0), num_parts[0], font=font_num)
            n1_w = n1_bbox[2] - n1_bbox[0]
        except Exception:
            n1_w = tw // 2
        draw.text((px, py), num_parts[0], fill=ACCENT_GREEN, font=font_num)
        draw.text((px + n1_w, py), " / " + num_parts[1], fill=(200, 200, 200, 255), font=font_page)
    else:
        draw.text((px, py), page_text, fill=(200, 200, 200, 255), font=font_page)


def _gt_draw_logo(image, right: int, top: int, size: int) -> None:
    """Paste the graitech logo at a fixed position with a neon glow."""
    from PIL import Image as _Img, ImageOps
    _GRAITECH_SUBFOLDER = Path(__file__).resolve().parent / "assets" / "graitech" / "assets"
    _LOGO_CANDIDATES = [
        GRAITECH_LOGO_PATH,
        _GRAITECH_SUBFOLDER / "graitech-logo.png",
        _GRAITECH_SUBFOLDER / "GR logo without bng.png",
        *WATERMARK_CANDIDATES,
        *FINAL_LOGO_CANDIDATES,
    ]
    path = next((c for c in _LOGO_CANDIDATES if c.exists()), None)
    if not path:
        return
    try:
        logo = _Img.open(path).convert("RGBA")
        logo = logo.resize((size, size), _Img.Resampling.LANCZOS)
        x = CANVAS_W - right - size
        y = top
        image.paste(logo, (x, y), logo)
    except Exception:
        pass


# ── graitech neon rule helper ─────────────────────────────────────────────────

def _gt_draw_rule(draw, x: int, y: int) -> int:
    """Draw a 96×3px neon rule with soft glow. Returns y after rule."""
    RULE_W = 96
    RULE_H = 3
    # Soft glow halos (widening outward with decreasing alpha)
    for offset in range(6, 0, -1):
        a = max(0, 50 - offset * 8)
        draw.rectangle(
            (x - offset, y - 1, x + RULE_W + offset, y + RULE_H + 1),
            fill=(57, 255, 20, a)
        )
    # Solid rule
    draw.rectangle((x, y, x + RULE_W, y + RULE_H), fill=(57, 255, 20, 255))
    return y + RULE_H


# ── graitech eyebrow helper ───────────────────────────────────────────────────

def _gt_draw_eyebrow(draw, ImageFont, text: str, x: int, y: int) -> int:
    """Draw eyebrow text in neon green Space Mono Bold. Returns y after eyebrow."""
    font = _font(ImageFont, 26, bold=True, mono=True)
    draw.text((x, y), text.upper(), fill=ACCENT_GREEN, font=font)
    try:
        bh = draw.textbbox((0, 0), text, font=font)[3]
    except Exception:
        bh = 22
    return y + bh


# ── Title slide renderer ──────────────────────────────────────────────────────

def _gt_render_list_slide_bullets_only(
    draw, image_font, body_text: str,
    x1: int, y1: int, x2: int, y2: int,
) -> None:
    """Render bullet-point list text into a bounding box.
    Used by digest slide renderer to draw bullet lists.
    """
    bullets = [b.strip() for b in body_text.split("\n") if b.strip()]
    if not bullets:
        return
    content_w = x2 - x1 - 22  # 22px for bullet prefix
    avail_h = y2 - y1
    chosen_size = 26
    for fsz in (34, 32, 30, 28, 26):
        font_bp = _font(image_font, fsz, mono=True)
        total = 0
        for bp in bullets:
            text = bp.lstrip("• ").strip()
            lines = _wrap_to_width(draw, text, font_bp, content_w, max_lines=4)
            try:
                lh = draw.textbbox((0, 0), "Ag", font=font_bp)[3]
            except Exception:
                lh = fsz
            total += len(lines) * (lh + 6) + 22
        if total <= avail_h:
            chosen_size = fsz
            break
    font_bp = _font(image_font, chosen_size, mono=True)
    y = y1
    for bullet in bullets:
        text = bullet.lstrip("• ").strip()
        if not text or y >= y2 - 30:
            break
        bp_lines = _wrap_to_width(draw, text, font_bp, content_w, max_lines=4)
        try:
            lh = draw.textbbox((0, 0), "Ag", font=font_bp)[3]
        except Exception:
            lh = chosen_size
        dot_cy = y + lh // 2
        draw.ellipse((x1, dot_cy - 4, x1 + 8, dot_cy + 4), fill=(57, 255, 20, 255))
        tx = x1 + 18
        for line in bp_lines:
            if y >= y2 - 10:
                break
            draw.text((tx, y), line, fill=SOFT_WHITE, font=font_bp)
            y += lh + 6
        y += 18


def _gt_render_title_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide: dict) -> None:
    """Render a graitech title slide (kind="title").

    Layout inside safe area (80, 220) → (1000, 1190):
      Row 1: eyebrow (neon mono)
      Row 2: neon rule
      Row 3: big Anton SC headline (neon green)
      Row 4: subtitle/body (Space Mono white)
      Row 5: article image (if available) below text block
    """
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80  # 1000

    y = SAFE_T

    # Eyebrow
    y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "FIELD NOTES"), SAFE_L, y)
    y += 16

    # Rule
    y = _gt_draw_rule(draw, SAFE_L, y) + 24

    # Headline in Anton SC (display font) — auto-sized, neon green, UPPERCASE
    headline = (slide.get("title") or "AI UPDATE").upper()
    content_w = SAFE_R - SAFE_L
    font_display = _font(ImageFont, 120, display=True)
    # Auto-size headline to fit within ~500px height
    for font_size in range(140, 40, -4):
        font_display = _font(ImageFont, font_size, display=True)
        lines = _wrap_to_width(draw, headline, font_display, content_w, max_lines=5)
        try:
            sample_h = draw.textbbox((0, 0), "Ag", font=font_display)[3]
        except Exception:
            sample_h = font_size
        total_h = len(lines) * (sample_h + 8)
        if total_h <= 480:
            break
    lines = _wrap_to_width(draw, headline, font_display, content_w, max_lines=5)
    for line in lines:
        try:
            lh = draw.textbbox((0, 0), line, font=font_display)[3]
        except Exception:
            lh = font_size
        draw.text((SAFE_L, y), line, fill=ACCENT_GREEN, font=font_display)
        y += lh + 6
    y += 24

    # Subtitle body text (Space Mono, white)
    subtitle = (slide.get("body") or "").strip()
    if subtitle and y < 920:
        remaining_h = min(920, 1190) - y
        font_body = _font(ImageFont, 36, bold=False, mono=True)
        sub_lines = _wrap_to_width(draw, subtitle, font_body, content_w, max_lines=4)
        for sline in sub_lines:
            if y + 36 > 950:
                break
            draw.text((SAFE_L, y), sline, fill=SOFT_WHITE, font=font_body)
            y += 36

    # Article image (lower portion of safe area, if available)
    image_path = slide.get("image_path", "")
    img_y_start = max(y + 24, 880)
    if img_y_start + 200 < 1190:
        img_box = (SAFE_L, img_y_start, SAFE_R, 1185)
        artwork = _load_artwork(
            image_path,
            slide.get("topic", "AI"),
            img_box,
            Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps,
            fallback_text=slide.get("title", ""),
        )
        if artwork is not None:
            _paste_contained(image, artwork, img_box, radius=16, pad=0, cover=True)
            # Hairline neon border
            draw.rounded_rectangle(img_box, radius=16, outline=(57, 255, 20, 100), width=1)

    # Source label
    source = (slide.get("source_label") or "").strip()
    if source:
        font_src = _font(ImageFont, 26, mono=True)
        draw.text((SAFE_L, 1155), f"SOURCE: {source.upper()}", fill=(200, 200, 200, 255), font=font_src)


# ── List slide renderer ───────────────────────────────────────────────────────

def _gt_render_list_slide(draw, ImageFont, slide: dict) -> None:
    """Render a graitech list slide (kind="list").

    Layout inside safe area:
      Row 1: eyebrow (neon)
      Row 2: neon rule
      Row 3: section title (smaller Anton SC, white)
      Row 4+: bullet-point list (Space Mono, 4 bullets max)

    Each bullet point line: "•  Point text here" on its own line.
    Bullet dot is drawn in neon green; text in white.
    """
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80

    y = SAFE_T

    # Eyebrow
    y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "INSIGHTS"), SAFE_L, y)
    y += 16

    # Rule
    y = _gt_draw_rule(draw, SAFE_L, y) + 24

    # Section title (smaller Anton SC)
    headline = (slide.get("title") or "").upper()
    if headline:
        font_sec = _font(ImageFont, 52, display=True)
        # Auto-size to fit on 2 lines max
        for fsz in range(60, 28, -4):
            font_sec = _font(ImageFont, fsz, display=True)
            lines = _wrap_to_width(draw, headline, font_sec, SAFE_R - SAFE_L, max_lines=2)
            try:
                lh = draw.textbbox((0, 0), "A", font=font_sec)[3]
            except Exception:
                lh = fsz
            if len(lines) * (lh + 4) <= 140:
                break
        sec_lines = _wrap_to_width(draw, headline, font_sec, SAFE_R - SAFE_L, max_lines=2)
        for sline in sec_lines:
            try:
                lh = draw.textbbox((0, 0), sline, font=font_sec)[3]
            except Exception:
                lh = 52
            draw.text((SAFE_L, y), sline, fill=TEXT_WHITE, font=font_sec)
            y += lh + 4
        y += 28

    # Bullet points
    body_raw = (slide.get("body") or "").strip()
    bullets = [b.strip() for b in body_raw.split("\n") if b.strip()]

    if not bullets:
        return

    # Choose font size based on number of bullets and available height
    avail_h = 1185 - y
    font_sizes_to_try = [46, 42, 38, 34]
    BULLET_GAP = 36  # pixels between bullet items
    LINE_GAP = 12    # pixels between wrapped lines within one bullet
    content_w = SAFE_R - SAFE_L - 30  # 30px for bullet prefix

    chosen_size = 28
    for fsz in font_sizes_to_try:
        font_bp = _font(ImageFont, fsz, mono=True)
        font_bp_bold = _font(ImageFont, fsz, bold=True, mono=True)
        total_estimated = 0
        for bp in bullets:
            text = bp.lstrip("• ").strip()
            lines = _wrap_to_width(draw, text, font_bp, content_w, max_lines=4)
            try:
                lh = draw.textbbox((0, 0), "Ag", font=font_bp)[3]
            except Exception:
                lh = fsz
            total_estimated += len(lines) * (lh + LINE_GAP) + BULLET_GAP
        if total_estimated <= avail_h:
            chosen_size = fsz
            break

    font_bp = _font(ImageFont, chosen_size, mono=True)
    font_bullet = _font(ImageFont, chosen_size, bold=True, mono=True)

    for bullet in bullets:
        text = bullet.lstrip("• ").strip()
        if not text:
            continue
        if y >= 1170:
            break

        bp_lines = _wrap_to_width(draw, text, font_bp, content_w, max_lines=4)
        try:
            lh = draw.textbbox((0, 0), "Ag", font=font_bp)[3]
        except Exception:
            lh = chosen_size

        # Neon bullet dot
        dot_cy = y + lh // 2
        draw.ellipse((SAFE_L, dot_cy - 5, SAFE_L + 10, dot_cy + 5),
                     fill=(57, 255, 20, 255))

        text_x = SAFE_L + 22
        for line in bp_lines:
            if y >= 1170:
                break
            draw.text((text_x, y), line, fill=SOFT_WHITE, font=font_bp)
            y += lh + LINE_GAP
        y += BULLET_GAP


# ── CTA slide renderer ────────────────────────────────────────────────────────

def _gt_render_cta_slide(image, draw, ImageFont, slide: dict) -> None:
    """Render a graitech CTA slide (kind="cta").

    Matches the slide-05-cta.html template:
      Stamp / eyebrow at top
      Big Anton SC "Save this. Steal this. Share it." in neon
      Follow text + graitech.io stamp
    """
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80

    # Stamp (top)
    font_stamp = _font(ImageFont, 18, bold=True, mono=True)
    stamp_text = "END / DISPATCH"
    # Pill stamp
    try:
        stamp_bbox = draw.textbbox((0, 0), stamp_text, font=font_stamp)
        sw = stamp_bbox[2] - stamp_bbox[0] + 32
        sh = stamp_bbox[3] - stamp_bbox[1] + 20
    except Exception:
        sw, sh = 200, 36
    draw.rounded_rectangle(
        (SAFE_L, SAFE_T, SAFE_L + sw, SAFE_T + sh),
        radius=999, outline=(57, 255, 20, 255), width=2, fill=(0, 0, 0, 0)
    )
    # Neon dot inside stamp
    draw.ellipse((SAFE_L + 14, SAFE_T + sh // 2 - 5, SAFE_L + 24, SAFE_T + sh // 2 + 5),
                 fill=(57, 255, 20, 255))
    draw.text((SAFE_L + 30, SAFE_T + (sh - 18) // 2), stamp_text,
              fill=ACCENT_GREEN, font=font_stamp)

    y = SAFE_T + sh + 32

    # Eyebrow
    y = _gt_draw_eyebrow(draw, ImageFont, "TAKE IT WITH YOU", SAFE_L, y)
    y += 16

    # Rule
    y = _gt_draw_rule(draw, SAFE_L, y) + 28

    # Big headline in Anton SC
    cta_lines = ["SAVE THIS.", "STEAL THIS.", "SHARE IT."]
    font_cta_big = _font(ImageFont, 160, display=True)
    # Auto-size to fit
    for fsz in range(180, 60, -6):
        font_cta_big = _font(ImageFont, fsz, display=True)
        try:
            lh = draw.textbbox((0, 0), "A", font=font_cta_big)[3]
        except Exception:
            lh = fsz
        if len(cta_lines) * (lh + 6) <= 640:
            break
    try:
        lh_cta = draw.textbbox((0, 0), "A", font=font_cta_big)[3]
    except Exception:
        lh_cta = 140
    for cline in cta_lines:
        if y + lh_cta > 1100:
            break
        draw.text((SAFE_L, y), cline, fill=ACCENT_GREEN, font=font_cta_big)
        y += lh_cta + 6

    y += 24

    # Body follow text
    body = (slide.get("body") or "Follow @graitech for the next AI briefing.").strip()
    font_body = _font(ImageFont, 28, mono=True)
    body_lines = _wrap_to_width(draw, body, font_body, SAFE_R - SAFE_L, max_lines=2)
    for bline in body_lines:
        if y > 1150:
            break
        draw.text((SAFE_L, y), bline, fill=SOFT_WHITE, font=font_body)
        try:
            y += draw.textbbox((0, 0), bline, font=font_body)[3] + 8
        except Exception:
            y += 36

    y += 16

    # graitech.io stamp + "Follow for more" meta
    if y < 1165:
        font_meta_sm = _font(ImageFont, 18, mono=True)
        font_meta_bold = _font(ImageFont, 18, bold=True, mono=True)
        draw.text((SAFE_L, y), "graitech.io", fill=ACCENT_GREEN, font=font_meta_bold)
        try:
            gw = draw.textbbox((0, 0), "graitech.io", font=font_meta_bold)[2]
        except Exception:
            gw = 120
        draw.text((SAFE_L + gw + 28, y), "FOLLOW FOR MORE",
                  fill=(200, 200, 200, 255), font=font_meta_sm)


# ── Legacy slide renderer (for "image" / "keypoint" kinds) ───────────────────

def _gt_render_legacy_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide: dict) -> None:
    """Render old-format slides using the graitech visual language as a base."""
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80
    content_w = SAFE_R - SAFE_L

    y = SAFE_T
    kind = slide.get("kind", "")

    if kind == "image":
        # eyebrow + rule + title + image
        y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "AI NEWS"), SAFE_L, y) + 16
        y = _gt_draw_rule(draw, SAFE_L, y) + 24
        headline = (slide.get("title") or "AI UPDATE").upper()
        font_h = _font(ImageFont, 80, display=True)
        for fsz in range(90, 32, -4):
            font_h = _font(ImageFont, fsz, display=True)
            hl = _wrap_to_width(draw, headline, font_h, content_w, max_lines=3)
            try:
                lh = draw.textbbox((0, 0), "A", font=font_h)[3]
            except Exception:
                lh = fsz
            if len(hl) * (lh + 8) <= 300:
                break
        hl = _wrap_to_width(draw, headline, font_h, content_w, max_lines=3)
        for hline in hl:
            try:
                lh = draw.textbbox((0, 0), hline, font=font_h)[3]
            except Exception:
                lh = 80
            draw.text((SAFE_L, y), hline, fill=ACCENT_GREEN, font=font_h)
            y += lh + 6
        y += 20
        img_box = (SAFE_L, y, SAFE_R, 1185)
        art = _load_artwork(slide.get("image_path", ""), slide.get("topic", "AI"), img_box,
                            Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps,
                            fallback_text=slide.get("title", ""))
        if art is not None:
            _paste_contained(image, art, img_box, radius=16, pad=0, cover=True)
            draw.rounded_rectangle(img_box, radius=16, outline=(57, 255, 20, 80), width=1)

    elif kind == "keypoint":
        # Treat as list slide
        kp_text = str(slide.get("body", ""))
        bullet_slide = dict(slide, kind="list",
                            body="\n".join(f"•  {kp_text}".split("\n")))
        _gt_render_list_slide(draw, ImageFont, bullet_slide)

    else:
        # Generic fallback
        y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "AI NEWS"), SAFE_L, y) + 16
        y = _gt_draw_rule(draw, SAFE_L, y) + 24
        title = (slide.get("title") or "").upper()
        if title:
            font_t = _font(ImageFont, 60, display=True)
            tl = _wrap_to_width(draw, title, font_t, content_w, max_lines=3)
            for tline in tl:
                try:
                    lh = draw.textbbox((0, 0), tline, font=font_t)[3]
                except Exception:
                    lh = 60
                draw.text((SAFE_L, y), tline, fill=ACCENT_GREEN, font=font_t)
                y += lh + 6
            y += 20
        body = (slide.get("body") or "").strip()
        if body:
            body_lines = (slide.get("body") or "").split("\n")
            font_b = _font(ImageFont, 30, mono=True)
            for bline in body_lines:
                if y > 1170:
                    break
                draw.text((SAFE_L, y), bline, fill=SOFT_WHITE, font=font_b)
                try:
                    y += draw.textbbox((0, 0), bline, font=font_b)[3] + 10
                except Exception:
                    y += 38


def _draw_background_grid(draw) -> None:
    """Legacy function kept for backward compatibility — delegates to the default dynamic background."""
    _draw_dynamic_background(draw, {})


# ── Dynamic background system ─────────────────────────────────────────────────

def _pick_bg_theme_from_summary(summary: "EmailSummary") -> str:
    """Select a background theme name based on the summary's topics, companies, and content."""
    combined = " ".join([
        " ".join(summary.topics or []),
        " ".join(summary.companies or []),
        " ".join(summary.models or []),
        str(summary.headline or ""),
        str(summary.subject or ""),
    ]).lower()
    return _pick_bg_theme_from_text(combined)


def _pick_bg_theme(slide: dict[str, Any]) -> str:
    """Select a background theme name from the slide dict.
    Uses the pre-computed 'bg_theme' key when available (set during spec building).
    Falls back to content-based classification.
    """
    if slide.get("bg_theme"):
        return str(slide["bg_theme"])
    combined = " ".join([
        str(slide.get("eyebrow", "")),
        str(slide.get("title", "")),
        str(slide.get("body", "")),
        str(slide.get("topic", "")),
    ]).lower()
    return _pick_bg_theme_from_text(combined)


def _pick_bg_theme_from_text(text: str) -> str:
    """Classify text into one of the 9 background themes."""
    if any(k in text for k in ("research", "paper", "arxiv", "study", "benchmark", "dataset", "academic", "survey")):
        return "research"
    if any(k in text for k in ("api", "sdk", "tool", "developer", "open-source", "github", "plugin", "code", "library")):
        return "tools"
    if any(k in text for k in ("funding", "acquisition", "revenue", "partnership", "valuation", "ipo", "investment", "startup", "enterprise")):
        return "industry"
    if any(k in text for k in ("regulation", "policy", "law", "ban", "government", "senate", "eu ", "compliance", "congress")):
        return "policy"
    if any(k in text for k in ("breaking", "urgent", "alert", "just announced", "just released", "exclusive")):
        return "breaking"
    if any(k in text for k in ("health", "medical", "clinical", "patient", "therapy", "drug", "hospital", "pharma", "biotech")):
        return "health"
    if any(k in text for k in ("finance", "trading", "market", "stock", "crypto", "blockchain", "economy", "gdp", "inflation")):
        return "finance"
    if any(k in text for k in ("space", "nasa", "satellite", "rocket", "astronomy", "cosmos", "orbit")):
        return "space"
    return "default"


def _draw_dynamic_background(draw, slide: dict[str, Any]) -> None:
    """Fill the slide canvas with a solid black background."""
    draw.rectangle((0, 0, CANVAS_W, CANVAS_H), fill=(5, 5, 5, 255))


def _draw_dynamic_background_UNUSED(draw, slide: dict[str, Any]) -> None:
    """ARCHIVED — kept for reference only. Background is now always solid black."""
    import math as _math

    theme_name = _pick_bg_theme(slide)
    theme = _BG_THEMES.get(theme_name, _BG_THEMES["default"])
    base: tuple = theme["base"]
    top_col: tuple = theme["top"]
    glow: tuple = theme["glow"]
    pattern: str = theme["pattern"]
    pat_a: int = theme["alpha"]

    band = 10
    for y0 in range(0, CANVAS_H, band):
        t = y0 / CANVAS_H
        r = int(top_col[0] + (base[0] - top_col[0]) * t)
        g = int(top_col[1] + (base[1] - top_col[1]) * t)
        b = int(top_col[2] + (base[2] - top_col[2]) * t)
        draw.rectangle((0, y0, CANVAS_W, min(y0 + band, CANVAS_H)), fill=(r, g, b, 255))

    cx, cy = CANVAS_W // 2, 320
    for radius in range(580, 0, -30):
        alpha = int(pat_a * 1.8 * (1 - radius / 580))
        if alpha < 1:
            continue
        draw.ellipse(
            (cx - radius, int(cy - radius * 0.65),
             cx + radius, int(cy + radius * 0.65)),
            fill=(*glow, alpha),
        )

    if pattern == "grid":
        for x in range(0, CANVAS_W + 1, 108):
            draw.line((x, 0, x, CANVAS_H), fill=(*glow, pat_a), width=1)
        for y in range(0, CANVAS_H + 1, 108):
            draw.line((0, y, CANVAS_W, y), fill=(*glow, pat_a), width=1)

    elif pattern == "hex":
        hex_w, hex_h = 90, 78
        for row in range(-1, CANVAS_H // hex_h + 2):
            for col in range(-1, CANVAS_W // hex_w + 2):
                ox = col * hex_w + (hex_w // 2 if row % 2 else 0)
                oy = row * hex_h
                pts = []
                for a in range(6):
                    angle = _math.radians(60 * a + 30)
                    pts.append((ox + 36 * _math.cos(angle), oy + 36 * _math.sin(angle)))
                draw.polygon(pts, outline=(*glow, pat_a))

    elif pattern == "circuit":
        for y in range(60, CANVAS_H, 120):
            draw.line((0, y, CANVAS_W, y), fill=(*glow, pat_a), width=1)
        for x in range(60, CANVAS_W, 120):
            draw.line((x, 0, x, CANVAS_H), fill=(*glow, pat_a), width=1)
        for y in range(60, CANVAS_H, 120):
            for x in range(60, CANVAS_W, 120):
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(*glow, pat_a * 2))

    elif pattern == "lines":
        for offset in range(-CANVAS_H, CANVAS_W + CANVAS_H, 72):
            draw.line((offset, 0, offset + CANVAS_H, CANVAS_H), fill=(*glow, pat_a), width=1)

    elif pattern == "cross":
        for x in range(0, CANVAS_W + 1, 72):
            draw.line((x, 0, x, CANVAS_H), fill=(*glow, pat_a // 2 + 2), width=1)
        for y in range(0, CANVAS_H + 1, 72):
            draw.line((0, y, CANVAS_W, y), fill=(*glow, pat_a // 2 + 2), width=1)

    elif pattern == "dots":
        for px in range(54, CANVAS_W, 86):
            for py in range(54, CANVAS_H, 86):
                draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=(*glow, pat_a * 2 + 4))

    elif pattern == "burst":
        for angle_deg in range(0, 360, 14):
            angle_rad = _math.radians(angle_deg)
            ex = CANVAS_W // 2 + int(900 * _math.cos(angle_rad))
            ey = CANVAS_H // 2 + int(900 * _math.sin(angle_rad))
            draw.line((CANVAS_W // 2, CANVAS_H // 2, ex, ey), fill=(*glow, pat_a // 2 + 2), width=1)

    draw.rounded_rectangle((28, 28, CANVAS_W - 28, CANVAS_H - 28),
                            radius=42, outline=(*glow, 18), width=2)


# ── Image quality helpers ─────────────────────────────────────────────────────

def _validate_image_hd(path: str) -> bool:
    """Return True when the image at `path` meets the minimum HD resolution.

    Minimum: IMAGE_MIN_HD_W × IMAGE_MIN_HD_H (1280 × 720 px).
    Returns False for missing, unreadable, or sub-HD images.
    """
    if not path:
        return False
    try:
        from PIL import Image as _PIL
        img = _PIL.open(path)
        w, h = img.size
        return w >= IMAGE_MIN_HD_W and h >= IMAGE_MIN_HD_H
    except Exception:
        return False


def _qa_slide_png(path: Path) -> list[str]:
    """Programmatically inspect a rendered PNG slide for common quality issues.

    Checks performed:
    1. Correct canvas dimensions (1080 × 1350 px)
    2. Slide is not blank / entirely one colour
    3. At least one bright pixel exists (text / accent colours present)

    Returns a list of issue strings (empty = slide passes QA).
    """
    issues: list[str] = []
    try:
        from PIL import Image as _PIL
        img = _PIL.open(path).convert("RGB")
        w, h = img.size

        if w != CANVAS_W or h != CANVAS_H:
            issues.append(f"Wrong dimensions {w}×{h} (expected {CANVAS_W}×{CANVAS_H})")

        # Check slide is not blank (all pixels near-identical colour)
        pixels = list(img.getdata())
        sample = pixels[::max(1, len(pixels) // 400)]
        unique_colours = len(set(sample))
        if unique_colours < 8:
            issues.append("Slide appears blank — too few unique colours")

        # Check that at least some bright pixels exist (text/accents visible)
        bright = sum(1 for r, g, b in sample if max(r, g, b) > 160)
        if bright < 5:
            issues.append("Slide too dark — no bright text or accent pixels detected")

    except Exception as exc:
        issues.append(f"QA could not read slide: {exc}")

    return issues


def _draw_accent_frame(draw) -> None:
    """Legacy accent frame — retained for backward compatibility (no-op in new design)."""
    pass  # graitech design uses corner ticks via _gt_draw_chrome instead


def _draw_slide_chip(draw, text: str, box: tuple[int, int, int, int], font, fill: str, outline: tuple[int, int, int] | str) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=2)
    _draw_centered_text(draw, text, box, font, TEXT_WHITE, 1)


def _draw_cta_pills(draw, font_meta) -> None:
    pills = [
        ((138, 1160, 304, 1212), "SAVE"),
        ((324, 1160, 540, 1212), "FOLLOW"),
        ((560, 1160, 790, 1212), "SHARE"),
        ((810, 1160, 942, 1212), "READ"),
    ]
    for box, label in pills:
        draw.rounded_rectangle(box, radius=20, fill="#0A0A0A", outline=(200, 255, 0, 120), width=2)
        _draw_centered_text(draw, label, box, font_meta, ACCENT_GREEN, 1)


def _draw_centered_text(draw, text: str, box: tuple[int, int, int, int], font, fill: str, max_lines: int) -> int:
    return _draw_centered_text_block(draw, text, box, font, fill, line_gap=10, max_lines=max_lines)


def _draw_centered_text_block(draw, text: str, box: tuple[int, int, int, int], font, fill: str, line_gap: int, max_lines: int) -> int:
    x1, y1, x2, y2 = box
    width = x2 - x1
    lines = _wrap_to_width(draw, text, font, width, max_lines)
    text_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_heights.append(bbox[3] - bbox[1])
    block_height = sum(text_heights) + max(0, len(lines) - 1) * line_gap
    y = max(y1, y1 + (y2 - y1 - block_height) // 2)
    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = x1 + max(0, (width - text_width) // 2)
        draw.text((x, y), line, fill=fill, font=font)
        y += text_height + line_gap
    return y


def _wrap_to_width(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    """Word-wrap text to fit within `width` pixels, returning at most `max_lines`.

    IMPORTANT: This function NEVER appends '...' or truncates mid-word.
    When used with _auto_fit_font(), the font will already be sized so that
    all words fit cleanly.  For fixed-font contexts (chip labels, slide counter)
    max_lines naturally limits output but we still never add dots.
    """
    lines, _ = _wrap_to_width_overflow(draw, text, font, width, max_lines)
    return lines


def _wrap_to_width_overflow(draw, text: str, font, width: int, max_lines: int) -> tuple[list[str], str]:
    """Like _wrap_to_width but also returns leftover text that didn't fit.

    Returns (lines, overflow_text) where overflow_text is the portion of `text`
    that could not fit within max_lines at the given font size.  overflow_text
    is empty when everything fits.  This enables callers to push the overflow
    onto the next slide instead of silently dropping it.
    """
    words = re.sub(r"\s+", " ", text or "").strip().split()
    lines: list[str] = []
    current: list[str] = []
    overflow_start_idx = len(words)
    for idx, word in enumerate(words):
        candidate = " ".join([*current, word])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > width and current:
            lines.append(" ".join(current))
            current = [word]
            if len(lines) >= max_lines:
                # Hit the line limit — record where overflow begins.
                overflow_start_idx = idx
                current = []
                break
        else:
            current.append(word)
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
        overflow_start_idx = len(words)
    overflow_text = " ".join(words[overflow_start_idx:]).strip()
    return (lines or [""]), overflow_text


def _load_artwork(image_path: str, topic: str, box: tuple[int, int, int, int], image_cls, draw_cls, enhance_cls, filter_cls, ops_cls, fallback_text=""):
    path = _resolve_image_source(image_path)
    if path and path.exists():
        try:
            art = image_cls.open(path).convert("RGB")
            art = enhance_cls.Contrast(art).enhance(1.02)
            return art.filter(filter_cls.UnsharpMask(radius=1, percent=80))
        except Exception:
            pass
    try:
        heading = _clean_public_text(fallback_text or topic)
        return _generate_ai_image(heading, topic, box, image_cls, draw_cls)
    except Exception:
        pass
    x1, y1, x2, y2 = box
    img = image_cls.new("RGB", (max(1, x2 - x1), max(1, y2 - y1)), (5, 5, 15))
    return img


def _generate_ai_image(
    text: str,
    topic: str,
    box: tuple[int, int, int, int],
    image_cls,
    draw_cls,
):
    """Generate a self-contained abstract illustration with heading text overlay.

    Uses the heading text to select a colour palette via keyword matching,
    renders a modern abstract composition, and overlays the heading in neon
    accent colour.  Zero external dependencies — pure Pillow, works in
    GitHub Actions without any local model or API.
    """
    from PIL import ImageFont

    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return None
    if w > 2000 or h > 2000:
        w, h = min(w, 2000), min(h, 2000)

    heading = (text or topic or "AI").strip()[:200]

    # ── Colour palette from heading keywords ─────────────────────────────
    hl = heading.lower()
    if any(w in hl for w in ("launch", "release", "introduc", "debut", "unveil", "new")):
        base, a1, a2, glow = (4, 12, 28), (0, 140, 230), (0, 220, 255), (0, 80, 180)
    elif any(w in hl for w in ("record", "beat", "surpass", "achieve", "milestone", "break", "crush")):
        base, a1, a2, glow = (22, 8, 4), (210, 80, 20), (255, 200, 50), (180, 60, 10)
    elif any(w in hl for w in ("security", "risk", "threat", "attack", "breach", "vulnerability", "safety")):
        base, a1, a2, glow = (22, 4, 4), (200, 40, 20), (255, 100, 50), (160, 30, 10)
    elif any(w in hl for w in ("ai", "model", "neural", "gpt", "claude", "gemini", "llama", "deep", "learn", "intelligence")):
        base, a1, a2, glow = (10, 5, 28), (100, 40, 210), (200, 255, 0), (70, 25, 160)
    elif any(w in hl for w in ("fund", "billion", "million", "raise", "invest", "acquire", "deal", "valuation")):
        base, a1, a2, glow = (4, 18, 10), (0, 180, 90), (200, 255, 0), (0, 120, 70)
    elif any(w in hl for w in ("robot", "automation", "agent", "autonomous", "self-driving")):
        base, a1, a2, glow = (4, 8, 28), (40, 80, 220), (100, 200, 255), (20, 50, 180)
    elif any(w in hl for w in ("open", "source", "code", "developer", "api", "sdk")):
        base, a1, a2, glow = (5, 18, 22), (0, 160, 180), (100, 220, 255), (0, 100, 150)
    else:
        palettes = {
            "research": ((10, 5, 25), (90, 50, 200), (200, 255, 0), (60, 30, 160)),
            "tools": ((4, 12, 28), (0, 130, 210), (0, 200, 255), (0, 80, 180)),
            "product": ((4, 18, 12), (0, 160, 90), (200, 255, 0), (0, 120, 70)),
            "funding": ((22, 8, 4), (200, 100, 20), (255, 200, 50), (160, 60, 10)),
            "policy": ((10, 4, 20), (130, 40, 200), (200, 180, 255), (90, 20, 160)),
        }
        t = topic.lower() if topic else ""
        if t in palettes:
            base, a1, a2, glow = palettes[t]
        else:
            base, a1, a2, glow = (5, 5, 18), (60, 80, 130), (200, 255, 0), (40, 50, 110)

    # ── Render abstract background ───────────────────────────────────────
    img = image_cls.new("RGBA", (w, h), base + (255,))
    draw = draw_cls.Draw(img, "RGBA")
    rng = random.Random(heading)

    for y in range(h):
        t = y / h
        r = int(base[0] * (1 - t) + glow[0] * t * 0.35)
        g = int(base[1] * (1 - t) + glow[1] * t * 0.35)
        b = int(base[2] * (1 - t) + glow[2] * t * 0.35)
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

    cx, cy = w // 2, int(h * 0.45)
    mr = max(w, h) // 3
    for r in range(mr, 0, -6):
        a = max(0, min(50, (mr - r) // 3))
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=glow + (a,))

    for _ in range(rng.randint(4, 9)):
        rx, ry, rr = rng.randint(0, w), rng.randint(0, h), rng.randint(18, min(w, h) // 5)
        c = a1 if rng.random() < 0.5 else a2
        draw.ellipse([(rx - rr, ry - rr), (rx + rr, ry + rr)], outline=c + (rng.randint(8, 35),), width=rng.randint(1, 3))

    pts = [(rng.randint(0, w), rng.randint(0, h)) for _ in range(rng.randint(10, 18))]
    for i, (px, py) in enumerate(pts):
        for j, (qx, qy) in enumerate(pts[i + 1:], i + 1):
            d = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
            if d < max(w, h) * 0.45:
                a = max(8, int(55 * (1 - d / (max(w, h) * 0.45))))
                draw.line([(px, py), (qx, qy)], fill=a1 + (a,), width=1)

    for px, py in pts:
        draw.ellipse([(px - 3, py - 3), (px + 3, py + 3)], fill=a2 + (180,))

    sp = rng.choice((40, 50, 60, 80))
    for gx in range(0, w, sp):
        draw.line([(gx, 0), (gx, h)], fill=(255, 255, 255, 5), width=1)
    for gy in range(0, h, sp):
        draw.line([(0, gy), (w, gy)], fill=(255, 255, 255, 5), width=1)

    s = min(w, h) // 7
    for gx, gy, dx, dy in ((0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)):
        draw.line([(gx + 8, gy + 8), (gx + dx * s + 8, gy + 8)], fill=a2 + (120,), width=3)
        draw.line([(gx + 8, gy + 8), (gx + 8, gy + dy * s + 8)], fill=a2 + (120,), width=3)

    # ── Overlay heading text on a dark pill at the bottom ────────────────
    try:
        fs = max(24, min(w, h) // 14)
        font = _font(ImageFont, fs, bold=True)
        mw = w - 80
        words = heading.split()
        lines, cur = [], ""
        for word in words:
            t = (cur + " " + word).strip()
            if draw.textlength(t, font=font) > mw and cur:
                lines.append(cur)
                cur = word
            else:
                cur = t
        if cur:
            lines.append(cur)
        lines = lines[:3]
        lh_list = []
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=font)
            lh_list.append(bb[3] - bb[1])
        th = sum(lh_list) + max(0, len(lines) - 1) * 6
        ty = h - th - 40
        if ty < 10:
            ty = max(10, (h - th) // 2)
        pad = 24
        draw.rounded_rectangle(
            (24, ty - pad, w - 24, ty + th + pad),
            radius=14, fill=(0, 0, 0, 200),
        )
        for line, lh in zip(lines, lh_list):
            lw = int(draw.textlength(line, font=font))
            draw.text(((w - lw) // 2, ty), line, fill=a2, font=font)
            ty += lh + 6
    except Exception:
        pass

    return img.convert("RGB")


def _draw_social_icons(draw, box: tuple[int, int, int, int], font_meta) -> None:
    x1, y1, x2, y2 = box
    centers = [
        (x1 + 120, y1 + 58, "LIKE"),
        (x1 + 340, y1 + 58, "COMMENT"),
        (x1 + 560, y1 + 58, "SHARE"),
        (x1 + 780, y1 + 58, "SAVE"),
    ]
    for cx, cy, label in centers:
        draw.rounded_rectangle((cx - 60, cy - 62, cx + 60, cy + 34), radius=22, outline=ACCENT_GREEN, width=2, fill="#050505")
        if label == "LIKE":
            _draw_heart_icon(draw, cx, cy - 18)
        elif label == "COMMENT":
            _draw_comment_icon(draw, cx, cy - 18)
        elif label == "SHARE":
            _draw_share_icon(draw, cx, cy - 18)
        else:
            _draw_save_icon(draw, cx, cy - 18)
        _draw_centered_text(draw, label, (cx - 74, cy + 48, cx + 74, cy + 82), font_meta, TEXT_WHITE, 1)


def _draw_heart_icon(draw, cx: int, cy: int) -> None:
    points = [(cx, cy + 28), (cx - 36, cy - 2), (cx - 24, cy - 32), (cx, cy - 18), (cx + 24, cy - 32), (cx + 36, cy - 2)]
    draw.line(points + [points[0]], fill=ACCENT_GREEN, width=5, joint="curve")


def _draw_comment_icon(draw, cx: int, cy: int) -> None:
    draw.rounded_rectangle((cx - 34, cy - 28, cx + 34, cy + 20), radius=16, outline=ACCENT_GREEN, width=5)
    draw.line((cx - 8, cy + 20, cx - 26, cy + 36), fill=ACCENT_GREEN, width=5)


def _draw_share_icon(draw, cx: int, cy: int) -> None:
    draw.polygon([(cx - 34, cy + 28), (cx + 38, cy - 30), (cx + 12, cy + 38), (cx + 2, cy + 8)], outline=ACCENT_GREEN, fill=None)
    draw.line((cx - 34, cy + 28, cx + 38, cy - 30, cx + 12, cy + 38, cx + 2, cy + 8, cx - 34, cy + 28), fill=ACCENT_GREEN, width=5)


def _draw_save_icon(draw, cx: int, cy: int) -> None:
    draw.line((cx - 28, cy - 34, cx + 28, cy - 34, cx + 28, cy + 36, cx, cy + 14, cx - 28, cy + 36, cx - 28, cy - 34), fill=ACCENT_GREEN, width=5)


def _draw_watermark_overlay(base_image) -> None:
    """Legacy watermark — no-op in the graitech design (logo is in fixed chrome)."""
    pass  # New design draws the graitech logo via _gt_draw_chrome


def _draw_handle_overlay(draw, image_font) -> None:
    """Draw the @graitech handle at bottom-left — graitech Design System style.
    (Used by legacy digest slide renderer — new slides use _gt_draw_chrome.)
    """
    font = _font(image_font, 24, bold=True, mono=True)
    handle = "@graitech"
    try:
        bbox = draw.textbbox((0, 0), handle, font=font)
        th = bbox[3] - bbox[1]
    except Exception:
        th = 24
    x, y = 56, CANVAS_H - 56 - th
    # Neon dot
    draw.ellipse((x, y + th // 2 - 5, x + 10, y + th // 2 + 5),
                 fill=(57, 255, 20, 255))
    draw.text((x + 18, y), handle, fill=TEXT_WHITE, font=font)


def _draw_centered_logo_panel(base_image, box: tuple[int, int, int, int]) -> None:
    from PIL import Image, ImageOps

    logo_path = next((candidate for candidate in FINAL_LOGO_CANDIDATES if candidate.exists()), None)
    if not logo_path:
        return
    try:
        logo = Image.open(logo_path).convert("RGBA")
        x1, y1, x2, y2 = box
        panel = Image.new("RGBA", (x2 - x1, y2 - y1), (0, 0, 0, 0))
        panel_draw = Image.new("RGBA", panel.size, (0, 0, 0, 0))
        panel = Image.alpha_composite(panel, panel_draw)
        logo = _remove_logo_background(logo)
        logo = ImageOps.contain(logo, (int((x2 - x1) * 0.62), int((y2 - y1) * 0.62)), method=Image.Resampling.LANCZOS)
        alpha = logo.getchannel("A")
        alpha = alpha.point(lambda value: int(value * 0.95))
        logo.putalpha(alpha)
        panel.paste(logo, ((panel.width - logo.width) // 2, (panel.height - logo.height) // 2), logo)
        base_image.paste(panel, (x1, y1), panel)
    except Exception:
        return


def _remove_logo_background(logo) -> Any:
    cleaned = logo.convert("RGBA")
    pixels = cleaned.load()
    for y in range(cleaned.height):
        for x in range(cleaned.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if max(r, g, b) < 45:
                pixels[x, y] = (r, g, b, 0)
    return cleaned


def _font(image_font, size: int, bold: bool = False, mono: bool = False,
          preferred: list[str] | None = None, display: bool = False):
    """Load a font from the graitech Design System.

    Font roles (matching graitech brand spec):
    - display=True  → Anton SC  (tall condensed all-caps headlines)
    - mono/body     → Space Mono (body, eyebrows, meta, labels)
    Falls back to system/bundled fonts when the graitech assets aren't present.
    """
    # ── 1. graitech Design System fonts (bundled in assets/fonts/) ────────────
    gt_candidates: list[Path] = []
    if display:
        gt_candidates.append(FONTS_DIR / "AntonSC-Regular.ttf")
    if bold and mono:
        gt_candidates.append(FONTS_DIR / "SpaceMono-Bold.ttf")
    elif mono:
        gt_candidates.append(FONTS_DIR / "SpaceMono-Regular.ttf")
    elif bold:
        gt_candidates += [FONTS_DIR / "SpaceMono-Bold.ttf", FONTS_DIR / "AntonSC-Regular.ttf"]
    else:
        gt_candidates.append(FONTS_DIR / "SpaceMono-Regular.ttf")
    # Always include both Space Mono variants as fallbacks
    gt_candidates += [
        FONTS_DIR / "SpaceMono-Bold.ttf",
        FONTS_DIR / "SpaceMono-Regular.ttf",
        FONTS_DIR / "AntonSC-Regular.ttf",
    ]
    for cand in gt_candidates:
        if cand.exists():
            try:
                return image_font.truetype(str(cand), size=size)
            except OSError:
                pass

    # ── 2. Caller-preferred paths ─────────────────────────────────────────────
    if preferred:
        for p in preferred:
            try:
                return image_font.truetype(p, size=size)
            except OSError:
                pass

    # ── 3. System + Linux fallbacks ───────────────────────────────────────────
    candidates: list[str] = []
    if mono:
        candidates.extend([
            "C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf",
        ])
    if bold:
        candidates.extend([
            "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
        ])
    candidates.extend([
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ])
    for candidate in candidates:
        try:
            return image_font.truetype(candidate, size=size)
        except OSError:
            continue
    return image_font.load_default()


def _paste_contained(base_image, artwork, box: tuple[int, int, int, int], radius: int, pad: int = 24, cover: bool = False) -> None:
    from PIL import Image, ImageDraw, ImageOps

    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    inner_width = max(1, width - pad * 2)
    inner_height = max(1, height - pad * 2)
    if cover:
        # Fill the area, cropping if necessary so there are no empty bands
        fitted = ImageOps.fit(artwork, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
    else:
        # Contain within the inner box (preserve whole image, add letterbox if needed)
        fitted = ImageOps.contain(artwork, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    layer = Image.new("RGBA", (width, height), PAGE_BLACK)
    # center the fitted artwork within the padded area
    offset_x = pad + (inner_width - fitted.width) // 2
    offset_y = pad + (inner_height - fitted.height) // 2
    layer.paste(fitted, (offset_x, offset_y))
    base_image.paste(layer, (x1, y1), mask)


def _draw_top_centered_text_block(draw, text: str, box: tuple[int, int, int, int], font, fill: str, max_lines: int) -> int:
    """Draw centered text but top-aligned in the given box."""
    x1, y1, x2, y2 = box
    width = x2 - x1
    lines = _wrap_to_width(draw, text, font, width, max_lines)
    y = y1
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = x1 + max(0, (width - text_width) // 2)
        draw.text((x, y), line, fill=fill, font=font)
        y += text_height + 6
    return y


def _draw_centered_body_block(draw, text: str, box: tuple[int, int, int, int], font, fill: str, line_gap: int, max_lines: int) -> int:
    """Draw body text centered horizontally, top-aligned vertically within the box.
    Each line is individually centered so the text looks balanced on the slide.
    """
    x1, y1, x2, y2 = box
    width = x2 - x1
    lines = _wrap_to_width(draw, text, font, width, max_lines)
    y = y1
    for line in lines:
        if y > y2:
            break
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x = x1 + max(0, (width - line_w) // 2)
        draw.text((x, y), line, fill=fill, font=font)
        y += line_h + line_gap
    return y


def _select_article_image(article: dict[str, Any], topic: str) -> str:
    """Smart image selection pipeline (no deduplication guard).
    Use _select_unique_article_image() when building carousel batches."""
    return _select_unique_article_image(article, topic, set(), set())


def _select_unique_article_image(
    article: dict[str, Any],
    topic: str,
    used_image_urls: set[str],
    used_image_paths: set[str],
) -> str:
    """Deduplicated image selection pipeline.

    Priority order:
    1. Article's own featured/hero image (from blog — highest relevance)
    2. Shared image library — best semantic match that has NOT been used yet
    3. Wikimedia Commons web search — unique image downloaded fresh
    4. Return empty string (slide layer will generate an AI illustration)

    Deduplication uses both the remote URL and the local file path so that
    the same physical file is never shown on two different slides in one batch.
    """
    title = str(article.get("title") or "")
    query_text = _tighten(_image_query_text(article, topic), 1200)

    # ── 0. Scrape og:image directly from the article URL ─────────────────────
    # This is the highest-priority source — pull the editor-chosen hero image
    # straight from the blog before touching the library or web search.
    article_url = str(article.get("url") or "")
    if article_url and not article.get("image_url") and not article.get("image_path"):
        scraped_url = _fetch_og_image_from_url(article_url)
        if scraped_url and scraped_url not in used_image_urls:
            local = _download_to_library(scraped_url, query_text or title or topic)
            if local and local not in used_image_paths:
                # Accept even non-HD blog images — editorial choice trumps resolution.
                used_image_urls.add(scraped_url)
                used_image_paths.add(local)
                article["image_url"] = scraped_url
                article["image_path"] = local
                return local

    # ── 1. Blog/article image (pre-populated by summariser) ──────────────────
    for key in ("image_path", "image_url"):
        value = str(article.get(key, "") or "").strip()
        if not value:
            continue
        if value.startswith(("http://", "https://")):
            if value in used_image_urls:
                continue
            local = _download_to_library(value, query_text or title or topic)
            if local and local not in used_image_paths:
                used_image_urls.add(value)
                used_image_paths.add(local)
                return local
        else:
            path = Path(value)
            if path.exists() and value not in used_image_paths:
                if _validate_image_hd(value):
                    used_image_paths.add(value)
                    return value
                pass

    # ── 1b. Non-HD local fallback from article keys ───────────────────────────
    for key in ("image_path",):
        value = str(article.get(key, "") or "").strip()
        if not value:
            continue
        path = Path(value)
        if path.exists() and value not in used_image_paths:
            used_image_paths.add(value)
            return value

    # ── 2. Shared image library — deduplicated semantic match ─────────────────
    library_match = _find_library_image_unique(
        query_text or title or topic, used_image_paths
    )
    if library_match:
        used_image_paths.add(library_match)
        return library_match

    # ── 3. Web image search — fresh download ──────────────────────────────────
    web_image = _find_reference_image_for_article_unique(
        article, topic, used_image_paths
    )
    if web_image:
        used_image_paths.add(web_image)
        return web_image

    return ""


def _find_library_image_unique(query: str, exclude_paths: set[str]) -> str | None:
    """Like _find_library_image but skips any path already in exclude_paths."""
    if not IMAGE_LIBRARY_DIR.exists():
        return None
    query_tokens = _important_image_tokens(query)
    if not query_tokens:
        return None
    query_brand = _brand_tokens(query)
    query_signature = _image_topic_signature(query)
    best_path: str | None = None
    best_score = 0.0
    for image_id, meta in _iter_image_metadata():
        candidate = _image_path_from_metadata(image_id, meta)
        if not candidate:
            continue
        candidate_str = str(candidate)
        # Skip images already used in this carousel
        if candidate_str in exclude_paths:
            continue
        seed = str(meta.get("seed", ""))
        meta_tokens = set(meta.get("tokens") or []) or _important_image_tokens(seed)
        overlap = query_tokens & meta_tokens
        score = len(overlap) / max(4, len(query_tokens)) if overlap else 0.0
        if query_brand:
            score += 0.25 * len(query_brand & meta_tokens)
        if query_signature and query_signature == _image_topic_signature(seed):
            score += 0.18
        if any(token in seed.lower() for token in query_tokens):
            score += 0.10
        if any(token in overlap for token in query_brand):
            score += 0.20
        if score > best_score:
            best_score = score
            best_path = candidate_str
    return best_path if best_score >= 0.45 else None


def _find_reference_image_for_article_unique(
    article: dict[str, Any], topic: str, exclude_paths: set[str]
) -> str | None:
    """Like _find_reference_image_for_article but skips already-used images."""
    for query in _reference_image_queries(article, topic):
        cache_key = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            cached = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
            if cached.exists() and str(cached) not in exclude_paths:
                return str(cached)
        image_url = _search_wikimedia_image(query)
        if image_url:
            downloaded = _download_reference_image(image_url, cache_key, query)
            if downloaded and downloaded not in exclude_paths:
                return downloaded
    return None


def _image_query_text(article: dict[str, Any], topic: str) -> str:
    return " ".join(
        str(part or "")
        for part in (
            article.get("title"),
            article.get("description"),
            article.get("summary"),
            article.get("excerpt"),
            " ".join(article.get("key_points", [])[:6]) if isinstance(article.get("key_points"), list) else "",
            topic,
            _source_label_from_url(str(article.get("url") or "")),
        )
    )


def _resolve_image_source(image_path: str) -> Path | None:
    value = str(image_path or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return _download_remote_image(value)
    path = Path(value)
    if path.exists():
        return path
    return None


def _fetch_og_image_from_url(article_url: str) -> str:
    """Scrape the article page and return the best image URL found.

    Priority:
    1. og:image meta tag  (most reliable — editors set this deliberately)
    2. twitter:image meta tag
    3. First <img> inside <article> / <main> / <div class*=content>
    4. Returns "" if nothing found or the page can't be fetched.

    This is called before any library / web-search fallback so that the slide
    image always comes from the actual article first.
    """
    if not article_url or not article_url.startswith(("http://", "https://")):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0; +https://graitech.ai)",
        "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    raw_html = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(article_url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw_html = resp.read(500_000).decode("utf-8", errors="replace")
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
                continue
            print(f"  [img] _fetch_og_image_from_url failed for {article_url[:80]}: {exc}")

    if not raw_html:
        return ""

    # 1. og:image
    og = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not og:
        og = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*>',
            raw_html, re.I,
        )
    if og:
        img_url = og.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            print(f"  [img] Found og:image for {article_url[:60]}: ...{img_url[-50:]}")
            return img_url

    # 2. twitter:image
    tw = re.search(
        r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not tw:
        tw = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']twitter:image["\'][^>]*>',
            raw_html, re.I,
        )
    if tw:
        img_url = tw.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            print(f"  [img] Found twitter:image for {article_url[:60]}: ...{img_url[-50:]}")
            return img_url

    # 3. First substantive <img> in article/main content area
    content_block = re.search(
        r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>',
        raw_html, re.I | re.S,
    )
    search_zone = content_block.group(1) if content_block else raw_html
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', search_zone, re.I):
        src = img_match.group(1).strip()
        if (src.startswith(("http://", "https://"))
                and any(ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp"))
                and not any(skip in src.lower() for skip in ("logo", "icon", "avatar", "pixel", "tracking", "badge", "1x1", "spacer"))):
            print(f"  [img] Found <img> tag in article body for {article_url[:60]}: ...{src[-50:]}")
            return src

    print(f"  [img] No image found in {article_url[:60]}")
    return ""


def _download_to_library(url: str, seed_text: str) -> str | None:
    """Download an image URL to the shared data/images library and return the local path."""
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    # Check if already downloaded
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        cached = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
        if cached.exists():
            return str(cached)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0)",
            "Referer": url,
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower().strip()
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, ".jpg")
            data = resp.read(8_000_000)
    except Exception:
        return None
    if len(data) < 8_000:
        return None
    dest = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
    dest.write_bytes(data)
    # Save a sidecar metadata file so we can match images to topics later
    meta = IMAGE_LIBRARY_DIR / f"{cache_key}.json"
    meta_data = {"url": url, "seed": seed_text, "path": str(dest), "tokens": sorted(_important_image_tokens(seed_text)), "topic": _image_topic_signature(seed_text)}
    meta.write_text(json.dumps(meta_data, ensure_ascii=True), encoding="utf-8")
    _upsert_image_index(cache_key, meta_data)
    return str(dest)


def _find_library_image(query: str) -> str | None:
    """Search the data/images library for an image relevant to the query."""
    if not IMAGE_LIBRARY_DIR.exists():
        return None
    query_tokens = _important_image_tokens(query)
    if not query_tokens:
        return None
    query_brand = _brand_tokens(query)
    query_signature = _image_topic_signature(query)
    best_path: str | None = None
    best_score = 0.0
    for image_id, meta in _iter_image_metadata():
        seed = str(meta.get("seed", ""))
        meta_tokens = set(meta.get("tokens") or []) or _important_image_tokens(seed)
        overlap = query_tokens & meta_tokens
        score = len(overlap) / max(4, len(query_tokens)) if overlap else 0.0
        if query_brand:
            score += 0.25 * len(query_brand & meta_tokens)
        if query_signature and query_signature == _image_topic_signature(seed):
            score += 0.18
        if any(token in seed.lower() for token in query_tokens):
            score += 0.10
        if any(token in overlap for token in query_brand):
            score += 0.20
        if score <= best_score:
            continue
        candidate = _image_path_from_metadata(image_id, meta)
        if candidate:
            best_score = score
            best_path = str(candidate)
    return best_path if best_score >= 0.45 else None


def _iter_image_metadata() -> list[tuple[str, dict[str, Any]]]:
    items: dict[str, dict[str, Any]] = {}
    try:
        data = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
        for item in data.get("images", []):
            image_id = str(item.get("id") or "")
            if image_id:
                items[image_id] = item
    except Exception:
        pass

    for meta_file in IMAGE_LIBRARY_DIR.glob("*.json"):
        if meta_file.name == IMAGE_INDEX_PATH.name:
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta.setdefault("id", meta_file.stem)
        items[meta_file.stem] = meta
    return sorted(items.items())


def _upsert_image_index(image_id: str, meta: dict[str, Any]) -> None:
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    data = {"images": []}
    try:
        data = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    images = [item for item in data.get("images", []) if item.get("id") != image_id]
    images.append({"id": image_id, **meta})
    IMAGE_INDEX_PATH.write_text(json.dumps({"images": images}, ensure_ascii=True, indent=2), encoding="utf-8")


def _image_path_from_metadata(image_id: str, meta: dict[str, Any]) -> Path | None:
    raw_path = str(meta.get("path") or "")
    if raw_path:
        path = Path(raw_path)
        if path.exists():
            return path
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = IMAGE_LIBRARY_DIR / f"{image_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _important_image_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in STOP_IMAGE_TOKENS
    }
    return tokens


def _brand_tokens(text: str) -> set[str]:
    lowered = (text or "").lower()
    return {
        token
        for brand in REFERENCE_BRANDS
        if brand.lower() in lowered
        for token in _important_image_tokens(brand)
    }


# ── Highlight keyword system for keypoint slides ──────────────────────────────
# Words matching these patterns are rendered in bold neon green to draw the eye.

_HIGHLIGHT_MODELS = frozenset({
    "GPT", "GPT-4", "GPT-5", "GPT4", "GPT5", "GPT-4o", "GPT-4.5",
    "Claude", "Claude 3", "Claude 3.5", "Claude 4",
    "Gemini", "Gemini 2", "Gemini 2.0", "Gemini 1.5",
    "Llama", "Llama 2", "Llama 3", "Llama 4",
    "Mistral", "Mistral Large", "Mistral Medium",
    "Grok", "Grok 2", "Grok 3",
    "Sora", "Veo", "Veo 2", "DALL-E", "DALL-E 3",
    "Copilot", "ChatGPT", "Gemini", "Midjourney",
    "Stable Diffusion", "SD3", "Flux",
    "o1", "o3", "o4", "R1", "Sonnet", "Haiku", "Opus",
})

_HIGHLIGHT_VERBS = frozenset({
    "launches", "releases", "achieves", "beats", "surpasses", "reveals",
    "breaks", "builds", "cuts", "doubles", "enables", "expands",
    "introduces", "joins", "reaches", "replaces", "sets", "ships",
    "shows", "trains", "upgrades", "unveils", "announces", "partners",
    "acquires", "raises", "deploys", "integrates",
    "launched", "released", "achieved", "surpassed", "introduced",
    "announced", "unveiled", "partnered", "acquired", "raised",
    "crushes", "shatters", "hits", "tops", "explodes",
})

_HIGHLIGHT_ACRONYMS = frozenset({
    "AI", "API", "GPU", "CPU", "LLM", "ML", "NLP", "SDK", "RAG",
    "RLHF", "AGI", "HPC", "TPU", "ASIC", "FPGA", "SaaS", "MCP",
})


def _token_is_highlight_worthy(token: str) -> bool:
    word = token.strip().strip(".,;:!?\"'()[]{}")
    if not word or len(word) <= 1:
        return False
    # Numbers (digits, percentages, monetary values, etc.)
    if re.match(r"^[\$€£]?\d+[\d,.]*(?:[BMTKbmtk]|bn|mn|%|x|×|th)?$", word):
        return True
    # Acronyms
    if word in _HIGHLIGHT_ACRONYMS:
        return True
    # Company names (case-insensitive against REFERENCE_BRANDS)
    if word in REFERENCE_BRANDS or word.lower() in {b.lower() for b in REFERENCE_BRANDS}:
        return True
    # Model names
    if word in _HIGHLIGHT_MODELS or word.lower() in {m.lower() for m in _HIGHLIGHT_MODELS}:
        return True
    # Power verbs
    if word.lower() in _HIGHLIGHT_VERBS:
        return True
    return False


def _draw_keypoint_body_with_highlights(
    draw, text, box, image_font,
    size_max=68, size_min=26, max_lines=8, align="center",
):
    """Draw keypoint body with highlight-worthy words in bold neon green.

    Instead of one uniform colour block, this function renders each word
    individually. Words that match _token_is_highlight_worthy() are drawn in
    bold ACCENT_GREEN; everything else stays white.  The font is still auto-
    sized to fit the entire box so no layout overflows.
    """
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    if not text:
        return y1

    font = _auto_fit_font(
        image_font, text, width, height,
        bold=True, size_max=size_max, size_min=size_min, max_lines=max_lines,
    )
    bold_font = _font(image_font, font.size, bold=True)

    tokens = re.findall(r"\S+\s*", text)
    lines: list[list[str]] = []
    current_line: list[str] = []
    current_w = 0.0
    for tok in tokens:
        tw = draw.textlength(tok, font=font)
        if current_line and current_w + tw > width:
            lines.append(current_line)
            current_line = [tok]
            current_w = tw
            if len(lines) >= max_lines:
                current_line = []
                break
        else:
            current_line.append(tok)
            current_w += tw
    if current_line and len(lines) < max_lines:
        lines.append(current_line)

    line_heights = []
    for line_tokens in lines:
        mh = 0
        for tok in line_tokens:
            bb = draw.textbbox((0, 0), tok, font=font)
            mh = max(mh, bb[3] - bb[1])
        line_heights.append(mh)

    gap = 10
    block_h = sum(line_heights) + max(0, len(lines) - 1) * gap
    y = y1 + max(0, (height - block_h) // 2)

    for li, line_tokens in enumerate(lines):
        lw = sum(draw.textlength(t, font=font) for t in line_tokens)
        if align == "center":
            x = x1 + max(0, (width - lw) // 2)
        elif align == "left":
            x = x1
        else:
            x = x1 + max(0, width - lw)

        for tok in line_tokens:
            is_hl = _token_is_highlight_worthy(tok)
            cf = bold_font if is_hl else font
            draw.text((x, y), tok, fill=ACCENT_GREEN if is_hl else TEXT_WHITE, font=cf)
            x += draw.textlength(tok, font=cf)

        y += line_heights[li] + gap
    return y


def _extract_instagram_key_points(
    article: dict[str, Any],
    summary: "EmailSummary",
    max_points: int = 10,
    used_fingerprints: set[str] | None = None,
) -> list[str]:
    """Extract punchy, attention-grabbing key points for Instagram slides.

    Storytelling rules (inspired by viral AI news accounts):
    - Each point starts with a numbered emoji (1️⃣ 2️⃣ 3️⃣ …)
    - Strong hook: verb, stat, or striking claim first
    - Plain language — "This means..." framing where relevant
    - ≤ 110 chars per point, no trailing dots
    - 3–5 points ordered by impact (most striking first)

    When *used_fingerprints* is provided, points whose lowercase-60-char
    fingerprint already appears in the set are skipped *and* the fingerprints
    of selected points are added back so callers can avoid duplicates across
    multiple calls (e.g. across articles in one carousel).
    """
    STOP_PREFIXES = (
        "this article", "in this post", "the article", "we discuss",
        "this piece", "this blog", "you will learn", "click here",
        "read more", "find out", "learn how", "sign up",
        "grdevelopers", "graitech",
    )
    NOISE_PATTERNS = [
        r"BREAKING AI UPDATE\s*[-–—]\s*",
        r"\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]\s*",
        r"\bImpact\s*:\s*(?:Low|Medium|High|Critical)\b",
        r"\bRead\s*time\s*:\s*\d+\s*(?:min|mins|minutes?)\b",
        r"={3,}",
        r"Company\s*:\s*",
        r"AI Summary\s*:\s*",
        r"Link\s*:\s*https?://\S+",
        # Remove the entire sentence containing "Link : <number>" — a common
        # digest-email boilerplate like "The model connects via Link : 1."
        # The greedy [^.!?]* on both sides ensures the whole clause is gone.
        r"[^.!?]*\bLink\s*:\s*\d+[^.!?]*[.!?]?\s*",
        # Remove orphaned "Link:" / "Link :" fragments (no URL or digit follows).
        r"\bLink\s*:\s*",
        # Remove "Link ." / "Link." trailing punctuation fragments left after
        # the number was stripped by the pattern above.
        r"\bLink\s*[.,]?\s*$",
        # Remove "\d+ event(s) detected" digest header lines (sometimes rendered
        # as "I event(s) detected" when "1" and "I" are confused in encoding).
        r"\b(?:\d+|I)\s+event\(s\)\s+detected\b[^\n]*",
        r"#{1,6}\s+(?:Bug Fixes|Features?|Performance|Breaking Changes?|Refactoring?|Chores?|Docs?).*",
        r"\*\*([^*]+):\*\*\s*",
        # Remove "v <Article Title>" link-reference fragments that appear when a
        # digest email embeds article titles as inline citations.
        # Pattern matches a lone "v " or "via " followed by a capitalised phrase.
        r"\bv(?:ia)?\s+[A-Z][^\n.!?]{5,80}",
        # Remove "More from <Publication>" navigation bleed.
        r"\bMore from\s+\S+[^\n.!?]*",
        # Strip publication pipe suffix inside bullets (e.g. "… | TechCrunch")
        r"\s*\|\s*[A-Z][A-Za-z0-9 &]{1,30}$",
    ]
    POWER_VERBS = (
        "launches", "releases", "achieves", "beats", "surpasses", "reveals",
        "breaks", "builds", "cuts", "doubles", "enables", "expands",
        "introduces", "joins", "reaches", "replaces", "sets", "ships",
        "shows", "trains", "upgrades",
    )
    # No emojis — graitech brand uses no emoji in brand surfaces.
    # Use a clean bullet point so each point stands on its own line.
    BULLET = "•"

    def _strip_noise(text: str) -> str:
        for pattern in NOISE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.I)
        return re.sub(r"\s+", " ", text).strip()

    raw: list[str] = []

    def _is_valid_bullet(text: str) -> bool:
        """Return True only if this text is a usable, well-formed bullet point."""
        if not text or len(text) < 15:
            return False
        # Must start with uppercase letter or a digit — never a mid-sentence fragment
        if not (text[0].isupper() or text[0].isdigit()):
            return False
        # Must not start with a blocked prefix
        if any(text.lower().startswith(pfx) for pfx in STOP_PREFIXES):
            return False
        return True

    # ---- Phase 1: Collect candidates from THIS article's own fields (no cross-article dedup) ----
    article_candidates = []

    # 1a. Pre-structured key_points from article (highest quality)
    for p in article.get("key_points", []):
        cleaned = _strip_noise(_clean_public_text(str(p))).strip()
        if _is_valid_bullet(cleaned):
            article_candidates.append(cleaned)

    # 1b. Mine article text fields for sentence-level insights
    for field in ("what_happened", "why_matters", "what_to_watch", "description", "excerpt", "scraped_content"):
        text = _strip_noise(_clean_public_text(str(article.get(field) or "")))
        if not text:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", text):
            sent = sent.strip()
            if _is_valid_bullet(sent) and len(sent) > 35:
                article_candidates.append(sent)
        if len(article_candidates) >= max_points * 3:
            break

    # Deduplicate article_candidates among themselves only
    seen_local = set()
    deduped_local = []
    for p in article_candidates:
        key = re.sub(r"\s+", " ", p).lower()[:60]
        if key not in seen_local:
            seen_local.add(key)
            deduped_local.append(p)

    # ---- Phase 2: Apply cross-article dedup to find novel points ----
    novel = []
    novel_fingerprints = []
    for p in deduped_local:
        key = re.sub(r"\s+", " ", p).lower()[:60]
        if used_fingerprints is None or key not in used_fingerprints:
            novel.append(p)
            novel_fingerprints.append(key)

    # ---- Phase 3: Relax dedup when too aggressive (fewer than 3 novel points) ----
    # Rather than showing a near-empty slide, allow some content repetition.
    if len(novel) < 3:
        for p in deduped_local:
            if p not in novel:
                novel.append(p)
                novel_fingerprints.append(re.sub(r"\s+", " ", p).lower()[:60])
        # Still short? Pull from shared summary key_points as last resort.
        if len(novel) < 3:
            for p in (summary.key_points or []):
                cleaned = _strip_noise(_clean_public_text(str(p))).strip()
                if cleaned and _is_valid_bullet(cleaned) and cleaned not in novel:
                    novel.append(cleaned)
                    novel_fingerprints.append(re.sub(r"\s+", " ", cleaned).lower()[:60])

    # ---- Phase 4: Score and sort ----
    def _point_score(pt):
        score = 0.0
        pt_l = pt.lower()
        if any(pt_l.startswith(v) for v in POWER_VERBS):
            score += 0.4
        if re.search(r"\b\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|x|\s+(?:billion|million|percent|times))", pt, re.I):
            score += 0.35
        if len(pt) <= 80:
            score += 0.25
        return score

    novel.sort(key=_point_score, reverse=True)

    # ---- Phase 5: Guarantee minimum 4 points by synthesising from article title/desc ----
    if len(novel) < 4:
        title_str = _clean_public_text(str(article.get("title") or summary.headline or summary.subject or ""))
        desc_str = _clean_public_text(str(article.get("description") or article.get("excerpt") or ""))
        # Use article title if not already represented
        if title_str and len(title_str) > 15 and not any(title_str[:40].lower() in p.lower() for p in novel):
            novel.append(title_str)
        # Split description on natural boundaries for extra points
        if desc_str and len(novel) < 4:
            for chunk in re.split(r"[;,]\s+|(?<=[.!?])\s+", desc_str):
                chunk = chunk.strip()
                if len(chunk) > 35 and _is_valid_bullet(chunk) and chunk not in novel:
                    novel.append(chunk)
                if len(novel) >= 4:
                    break

    # Format and trim
    trimmed = [_trim_no_dots(pt, 140) for pt in novel[:max_points]]
    final = [f"{BULLET}  {pt}" for pt in trimmed if pt and len(pt) > 10]

    if not final:
        # Absolute last resort: use THIS article's title, not the shared summary
        # headline (which would create identical fallback text on every slide).
        title_fb = _trim_no_dots(
            _clean_public_text(str(article.get("title") or article.get("url") or summary.subject or "AI update")), 95
        )
        return [f"{BULLET}  {title_fb}"]

    # Pad to at least 2 bullets if only 1 survived
    if len(final) == 1:
        title_pt = _trim_no_dots(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "")), 120
        )
        if title_pt and title_pt not in final[0]:
            final.append(f"{BULLET}  {title_pt}")

    # ---- Phase 6: Register selected fingerprints for cross-article dedup ----
    if used_fingerprints is not None:
        for fp in novel_fingerprints[:max_points]:
            used_fingerprints.add(fp)
    return final


def _compose_article_narrative(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Build a clean narrative from the structured article fields produced by the new summariser."""
    # Prefer the pre-structured narrative sections if available
    what_happened = _clean_public_text(str(article.get("what_happened") or ""))
    why_matters = _clean_public_text(str(article.get("why_matters") or ""))
    what_watch = _clean_public_text(str(article.get("what_to_watch") or ""))

    if what_happened:
        parts = [p for p in [what_happened, why_matters, what_watch] if p]
        return _tighten(re.sub(r"\s+", " ", " ".join(parts)).strip(), 2400)

    # Fallback: build from description/summary/key_points
    title = _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
    article_summary = _clean_public_text(str(article.get("summary") or ""))
    description = _clean_public_text(str(article.get("description") or ""))
    excerpt = _clean_public_text(str(article.get("excerpt") or ""))
    summary_text = _clean_public_text(summary.summary)

    primary = article_summary if len(article_summary) >= 120 else description
    if len(primary) < 120:
        primary = excerpt
    if len(primary) < 120:
        primary = summary_text
    if not primary:
        primary = _fallback_summary_text(summary, title or (summary.headline or "AI update"))

    points = [
        _clean_public_text(str(point).strip())
        for point in article.get("key_points", [])
        if str(point).strip()
    ]
    points = [p for p in points if p and p.lower() not in primary.lower()]
    narrative = primary
    if points:
        narrative = f"{primary} {' '.join(points[:4])}"
    if title and title.lower() not in narrative.lower():
        narrative = f"{title}. {narrative}"
    return _tighten(re.sub(r"\s+", " ", narrative).strip(), 2400)


def _split_narrative_for_content_pages(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= 1040:
        return _split_narrative_for_page_count(text, page_count=2, target_chars=520)
    return _split_narrative_for_page_count(text, page_count=3, target_chars=520)


def _split_narrative_for_page_count(text: str, page_count: int, target_chars: int) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    if len(sentences) < page_count and len(text) > target_chars:
        return [_tighten(part, 620) for part in _split_by_length(text, page_count)]

    pages = [""] * page_count
    page_index = 0
    for sentence in sentences:
        candidate = " ".join(part for part in [pages[page_index], sentence] if part).strip()
        if len(candidate) <= target_chars or not pages[page_index]:
            pages[page_index] = candidate
        elif page_index < page_count - 1:
            page_index += 1
            pages[page_index] = sentence
        else:
            pages[page_index] = " ".join([pages[page_index], sentence]).strip()

    pages = [_tighten(page, 620) for page in pages if page.strip()]
    if len(pages) == 1 and len(pages[0]) > target_chars and page_count > 1:
        pages = [_tighten(part, 620) for part in _split_by_length(pages[0], page_count)]
    elif page_count == 3 and len(pages) == 2 and len(pages[0]) > 500:
        first_split = _split_by_length(pages[0], 2)
        pages = [_tighten(first_split[0], 620), _tighten(first_split[1], 620), pages[1]]
    return pages[:page_count]


def _split_by_length(text: str, parts: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    target = max(1, len(words) // parts)
    chunks: list[str] = []
    for index in range(parts):
        start = index * target
        end = None if index == parts - 1 else (index + 1) * target
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _download_remote_image(url: str) -> Path | None:
    try:
        tmp_dir = Path(tempfile.gettempdir()) / "ai_news_instagram"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg"
        dest = tmp_dir / f"img_{abs(hash(url))}{suffix}"
        _download_url(url, dest)
        return dest
    except Exception:
        return None


def _download_url(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        dest.write_bytes(response.read())


def _find_reference_image_for_article(article: dict[str, Any], topic: str) -> str | None:
    for query in _reference_image_queries(article, topic):
        cache_key = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            cached = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
            if cached.exists():
                return str(cached)
        image_url = _search_wikimedia_image(query)
        if image_url:
            downloaded = _download_reference_image(image_url, cache_key, query)
            if downloaded:
                return downloaded
    return None


def _reference_image_queries(article: dict[str, Any], topic: str) -> list[str]:
    title = _strip_decorative_symbols(str(article.get("title") or "")).strip()
    description = _strip_decorative_symbols(str(article.get("description") or article.get("summary") or article.get("excerpt") or "")).strip()
    source = _source_label_from_url(str(article.get("url") or ""))
    raw_candidates = [
        title,
        description,
        *_brand_queries(title),
        *_brand_queries(description),
        source,
        topic,
        "artificial intelligence" if "ai" in f"{title} {topic}".lower() else "",
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        query = re.sub(r"\b(update|launch|announces|announced|new|latest|story|research|hub|plans)\b", " ", raw, flags=re.I)
        query = re.sub(r"[^A-Za-z0-9 .&+-]+", " ", query)
        query = re.sub(r"\s+", " ", query).strip()
        query = _tighten(query, 120)
        key = query.lower()
        if len(query) >= 3 and key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def _brand_queries(text: str) -> list[str]:
    lowered = text.lower()
    return [brand for brand in REFERENCE_BRANDS if brand.lower() in lowered]


def _search_wikimedia_image(query: str) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "gsrsearch": query,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AIInstagramNewsAgent/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        title = str(page.get("title") or "").lower()
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "").lower()
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        image_url = str(info.get("url") or "")
        if not image_url:
            continue
        if not _image_result_matches_query(query, title, image_url):
            continue
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if width < 1280 or height < 720:
            continue
        if any(term in title for term in ("logo", "icon", "symbol", "seal", "flag")) and not _query_looks_like_company(query):
            continue
        return image_url
    return None


def _image_result_matches_query(query: str, title: str, image_url: str) -> bool:
    haystack = f"{title} {urllib.parse.unquote(image_url).lower()}"
    tokens = _important_query_tokens(query)
    if not tokens:
        return False
    if any(token in haystack for token in tokens):
        return True
    return False


def _important_query_tokens(query: str) -> list[str]:
    blocked = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "news",
        "model",
        "models",
        "release",
        "support",
        "endpoint",
        "endpoints",
        "technology",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", query.lower())
    return [token for token in tokens if token not in blocked and len(token) >= 4]


def _image_topic_signature(text: str) -> tuple[str, ...]:
    tokens = [token for token in _important_image_tokens(text) if token not in {"latest", "update", "article", "story", "image"}]
    return tuple(sorted(tokens)[:5])


def _download_reference_image(image_url: str, cache_key: str, seed_text: str = "") -> str | None:
    try:
        request = urllib.request.Request(image_url, headers={"User-Agent": "AIInstagramNewsAgent/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            suffix = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }.get(content_type)
            if not suffix:
                return None
            data = response.read(5_000_000)
    except Exception:
        return None
    if len(data) < 20_000:
        return None
    # Save to both the reference cache and the shared library
    REFERENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
    dest.write_bytes(data)
    lib_dest = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
    if not lib_dest.exists():
        lib_dest.write_bytes(data)
    meta_data = {
        "url": image_url,
        "seed": seed_text or image_url,
        "path": str(lib_dest),
        "tokens": sorted(_important_image_tokens(seed_text or image_url)),
    }
    (IMAGE_LIBRARY_DIR / f"{cache_key}.json").write_text(json.dumps(meta_data, ensure_ascii=True), encoding="utf-8")
    _upsert_image_index(cache_key, meta_data)
    return str(dest)


def _query_looks_like_company(query: str) -> bool:
    lowered = query.lower()
    return any(company.lower() in lowered for company in ("openai", "google", "microsoft", "meta", "amazon", "aws", "nvidia", "anthropic"))


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


def _cleanup_existing_outputs(output_dir: Path) -> None:
    try:
        if not output_dir.exists():
            return
        for child in output_dir.iterdir():
            # remove files and directories inside the instagram output folder
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    except Exception:
        # don't fail the whole pipeline if cleanup encounters an issue
        return



def _build_caption(summary: EmailSummary) -> str:
    """Build a high-quality Instagram caption following editorial rules.

    Structure:
        1. Hook line (<125 chars, no hashtag start)
        2. Lead paragraph (2–3 sentences)
        3. 3–5 emoji-prefixed bullet points
        4. Closing question (drives comments)
        5. Source credit with URL
        6. Exactly 5 CamelCase hashtags
        7. Disclaimer if content warrants one
    """
    try:
        from .knowledge import get_rag as _get_rag
        _get_rag()  # warm the cache; errors are silently ignored
    except Exception:
        pass

    articles = _article_items(summary)
    article = articles[0] if articles else {}

    headline = _clean_headline(summary.headline or summary.subject or "AI update")
    article_url = str(article.get("url") or summary.article_url or "")

    # ── Hook line ─────────────────────────────────────────────────────────────
    hook = _build_caption_hook(summary, article, headline)

    # ── Lead paragraph ────────────────────────────────────────────────────────
    lead_raw = _clean_public_text(
        str(article.get("what_happened") or article.get("description") or
            article.get("excerpt") or summary.summary or "")
    )
    lead_raw = _dedupe_lead_text(lead_raw, headline)
    if not lead_raw or len(lead_raw) < 60:
        lead_raw = _fallback_summary_text(summary, headline)
    lead = _trim_no_dots(lead_raw, 420)

    # ── Takeaway bullets ──────────────────────────────────────────────────────
    bullets = _build_caption_bullets(summary, article, lead)

    # ── Closing question ──────────────────────────────────────────────────────
    closing_q = _build_closing_question(summary, article)

    # ── Source credit — include ALL article URLs from this summary ────────────
    # Collect every unique article URL in order (max 5 to fit within Instagram's
    # 2,200-character caption limit while leaving room for hashtags/disclaimer).
    _seen_urls: set[str] = set()
    _all_url_pairs: list[tuple[str, str]] = []  # (url, domain)
    for _art in articles:
        _u = str(_art.get("url") or "").strip()
        if _u and _u.startswith("http") and _u not in _seen_urls:
            _all_url_pairs.append((_u, _source_label_from_url(_u) or "Source"))
            _seen_urls.add(_u)
    # Fall back to the summary-level URL if no article URLs were found
    if not _all_url_pairs and summary.article_url:
        _u = summary.article_url.strip()
        if _u.startswith("http"):
            _all_url_pairs.append((_u, _source_label_from_url(_u) or "Source"))

    if len(_all_url_pairs) == 1:
        _url, _domain = _all_url_pairs[0]
        source_credit = (
            f"📰 Source: {_domain}\n🔗 {_url}"
            if _domain else
            f"🔗 {_url}"
        )
    elif len(_all_url_pairs) > 1:
        _link_lines = [f"🔗 {_u}" for _u, _ in _all_url_pairs[:5]]
        source_credit = "📰 Read the full stories:\n" + "\n".join(_link_lines)
    else:
        source_credit = "📰 Curated by Graitech AI News"

    # ── Hashtags — exactly 5 CamelCase ───────────────────────────────────────
    hashtags_line = _build_editorial_hashtags(summary, article)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    disclaimer = _build_disclaimer_if_needed(summary, article)

    # ── Engagement hooks (Instagram algorithm signals) ────────────────────────
    # Carousel save-bait: asking users to save drives the algorithm to push
    # the post to more people (saves are the highest-weight engagement signal).
    save_bait = "💾 Save this post — you'll want to come back to this one."

    # Swipe prompt on first line of body: keeps users swiping = longer dwell time.
    swipe_prompt = "👉 Swipe to see the full breakdown →"

    parts: list[str] = [hook, "", swipe_prompt, "", lead, ""]
    if bullets:
        parts.extend(bullets)
        parts.append("")
    parts.append(closing_q)
    parts.append("")
    parts.append(save_bait)
    parts.append("")
    parts.append(source_credit)
    parts.append("")
    parts.append(hashtags_line)
    if disclaimer:
        parts.append("")
        parts.append(disclaimer)

    return "\n".join(parts).strip() + "\n"


def _build_caption_hook(summary: EmailSummary, article: dict[str, Any], headline: str) -> str:
    """Hook line: < 125 chars, never starts with hashtag or 'I/We'."""
    companies = summary.companies[:1]
    entity = companies[0] if companies else (summary.models[:1] or ["AI"])[0]

    text_pool = " ".join([
        str(article.get("what_happened") or ""),
        str(article.get("description") or ""),
        " ".join(summary.key_points[:3]),
    ])
    stat = _extract_stat_from_text(text_pool)

    if stat:
        hook = f"{stat} — and that changes everything you knew about {entity}."
    elif len(headline) <= 110 and not headline.lower().startswith(("i ", "we ")):
        hook = headline if headline.endswith(".") else headline + "."
    else:
        hook = f"{entity} just did something no one expected. Here's what it actually means."

    if len(hook) > 125:
        hook = _trim_no_dots(hook, 125)
    hook = re.sub(r"^#+\s*", "", hook).strip()
    return hook


def _build_caption_bullets(summary: EmailSummary, article: dict[str, Any], lead: str) -> list[str]:
    """3–5 emoji-prefixed bullet points, each adding new info not in the lead."""
    EMOJIS = ["🔹", "⚡", "🧠", "📊", "🔬", "💡", "🛠️", "🌍", "🤖", "📈"]
    raw_points: list[str] = []

    for p in article.get("key_points", []):
        cleaned = _clean_public_text(str(p))
        if len(cleaned) > 25 and cleaned.lower() not in lead.lower():
            raw_points.append(cleaned)
    for p in summary.key_points:
        cleaned = _clean_public_text(str(p))
        if len(cleaned) > 25 and cleaned.lower() not in lead.lower() and cleaned not in raw_points:
            raw_points.append(cleaned)

    seen: set[str] = set()
    deduped: list[str] = []
    for p in raw_points:
        key = re.sub(r"\s+", " ", p).lower()[:70]
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    bullets = [
        f"{EMOJIS[i % len(EMOJIS)]} {_trim_no_dots(pt, 140)}"
        for i, pt in enumerate(deduped[:5])
    ]

    if not bullets:
        for field in ("what_happened", "why_matters", "what_to_watch"):
            text = _clean_public_text(str(article.get(field) or ""))
            if text and len(text) > 30:
                bullets.append(f"🔹 {_trim_no_dots(text, 140)}")
            if len(bullets) >= 3:
                break

    return bullets[:5]


def _build_closing_question(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Closing question that a non-technical reader can answer."""
    companies = summary.companies[:1]
    entity = companies[0] if companies else "this technology"

    questions = [
        f"Do you think {entity}'s move here is exciting or a risk? Drop your take below.",
        "Which industry do you think will feel the impact of this first?",
        "Would you use something like this in your daily work? Yes or no in the comments.",
        f"Is {entity} moving too fast, or not fast enough? Let's hear it.",
        "What's the one thing about this that surprised you most?",
    ]
    url_hash = abs(hash(str(article.get("url") or summary.message_key or "")))
    return questions[url_hash % len(questions)]


def _build_editorial_hashtags(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Build 15–20 Instagram hashtags optimised for the algorithm.

    Instagram's Reels and Feed algorithm rewards a mix of:
      • 3-5 highly specific niche tags (small community, high relevance)
      • 5-8 mid-tier tags (moderate audience, strong signal)
      • 3-5 broad discovery tags (large reach, lower relevance per user)
      • 1-2 content-format tags (carousel, explainer, etc.)

    Tags are deduped and returned as a single space-joined string.
    Using ~15-20 tags outperforms the old 5-tag strategy by 2–3× in
    initial reach according to Instagram algorithm analyses.
    """
    _NICHE_MAP = {
        "llm": ["#LargeLanguageModels", "#LLMNews", "#LanguageModels"],
        "language": ["#LanguageAI", "#NLP"],
        "generative": ["#GenerativeAI", "#GenAI"],
        "video": ["#AIVideo", "#AIVideoGeneration"],
        "image": ["#AIArt", "#AIImageGeneration", "#TextToImage"],
        "agent": ["#AIAgents", "#AutonomousAgents", "#AIWorkflow"],
        "autonomous": ["#AutonomousAI", "#AIAgents"],
        "policy": ["#AIPolicy", "#AIGovernance", "#TechPolicy"],
        "regulation": ["#AIRegulation", "#TechLaw"],
        "ethics": ["#AIEthics", "#ResponsibleAI"],
        "research": ["#AIResearch", "#MLResearch", "#DeepLearning"],
        "machine learning": ["#MachineLearning", "#MLOps"],
        "tool": ["#AITools", "#ProductivityAI", "#AIProductivity"],
        "productivity": ["#AIProductivity", "#AITools", "#WorkSmarter"],
        "chip": ["#AIChips", "#AIHardware", "#MLInfrastructure"],
        "hardware": ["#AIInfrastructure", "#AIChips"],
        "robot": ["#AIRobotics", "#Robotics", "#HumanoidRobots"],
        "health": ["#AIHealth", "#HealthTech", "#MedicalAI"],
        "medical": ["#MedicalAI", "#HealthcareAI", "#ClinicalAI"],
        "enterprise": ["#EnterpriseAI", "#BusinessAI", "#AIAdoption"],
        "startup": ["#AIStartup", "#TechStartup", "#VentureAI"],
        "coding": ["#AICoding", "#GithubCopilot", "#DeveloperAI"],
        "open source": ["#OpenSourceAI", "#OpenSource"],
        "multimodal": ["#MultimodalAI", "#VisionAI"],
        "reasoning": ["#AIReasoning", "#AIBenchmarks"],
        "voice": ["#AIVoice", "#SpeechAI"],
        "automation": ["#Automation", "#AIAutomation", "#NoCode"],
        "cloud": ["#CloudAI", "#AICloud"],
    }
    _COMPANY_MAP = {
        "openai": ["#OpenAI", "#ChatGPT"],
        "chatgpt": ["#ChatGPT", "#OpenAI"],
        "gpt": ["#GPT4", "#GPT5", "#OpenAI"],
        "google": ["#GoogleAI", "#Gemini"],
        "gemini": ["#Gemini", "#GoogleAI"],
        "deepmind": ["#GoogleDeepMind", "#DeepMind"],
        "anthropic": ["#Anthropic", "#Claude"],
        "claude": ["#Claude", "#Anthropic"],
        "meta": ["#MetaAI", "#LlamaAI"],
        "llama": ["#LlamaAI", "#MetaAI"],
        "microsoft": ["#MicrosoftAI", "#Copilot"],
        "copilot": ["#Copilot", "#MicrosoftAI"],
        "apple": ["#AppleIntelligence", "#AppleAI"],
        "nvidia": ["#NVIDIA", "#NVIDIAGPU"],
        "mistral": ["#MistralAI"],
        "hugging face": ["#HuggingFace", "#Transformers"],
        "groq": ["#Groq", "#FastAI"],
        "cohere": ["#Cohere", "#EnterpriseAI"],
        "perplexity": ["#PerplexityAI", "#AISearch"],
        "stability": ["#StabilityAI", "#StableDiffusion"],
        "midjourney": ["#Midjourney", "#AIArt"],
        "xai": ["#xAI", "#Grok"],
        "grok": ["#Grok", "#xAI"],
        "amazon": ["#AmazonBedrock", "#AWSCloud"],
    }
    _MID = [
        "#AINews", "#TechNews", "#AIUpdates", "#ArtificialIntelligence",
        "#FutureOfAI", "#TechTrends", "#Innovation", "#EmergingTech",
    ]
    _BROAD = [
        "#Technology", "#Tech", "#AI", "#MachineLearning",
        "#DataScience", "#FutureTech", "#DigitalTransformation",
    ]
    _FORMAT = [
        "#AICarousel", "#LearnAI", "#AIExplained", "#AIForEveryone",
        "#TechCarousel", "#AIBreakdown",
    ]

    combined = " ".join([
        str(article.get("title") or ""),
        " ".join(summary.topics),
        " ".join(summary.companies),
        " ".join(summary.models),
        str(summary.headline or ""),
    ]).lower()

    # Collect niche tags (up to 6 unique)
    niche_tags: list[str] = []
    for kw, tags in _NICHE_MAP.items():
        if kw in combined:
            niche_tags.extend(tags)
        if len(niche_tags) >= 8:
            break

    # Collect company tags (up to 4 unique)
    company_tags: list[str] = []
    for kw, tags in _COMPANY_MAP.items():
        if kw in combined:
            company_tags.extend(tags)
        if len(company_tags) >= 6:
            break

    key_hash = abs(hash(summary.message_key or ""))
    # Pick variety from mid, broad, format pools based on message hash
    mid_picks = [_MID[(key_hash + i) % len(_MID)] for i in range(4)]
    broad_picks = [_BROAD[(key_hash + i) % len(_BROAD)] for i in range(3)]
    fmt_pick = _FORMAT[key_hash % len(_FORMAT)]

    # If no niche match, seed with safe defaults
    if not niche_tags:
        niche_tags = ["#AINews", "#AITools", "#GenerativeAI"]

    # Deduplicate and cap at 20
    seen_tags: set[str] = set()
    unique_tags: list[str] = []
    for tag in [*niche_tags, *company_tags, *mid_picks, *broad_picks, fmt_pick]:
        if tag not in seen_tags and len(unique_tags) < 20:
            seen_tags.add(tag)
            unique_tags.append(tag)

    # Guarantee minimum 15 tags with fallbacks
    fallbacks = [
        "#DeepLearning", "#NeuralNetworks", "#ComputerVision",
        "#NaturalLanguageProcessing", "#MLNews", "#AIWeekly",
        "#TechInnovation", "#AIStartups", "#FutureOfWork",
    ]
    for fb in fallbacks:
        if len(unique_tags) >= 20:
            break
        if fb not in seen_tags:
            unique_tags.append(fb)
            seen_tags.add(fb)

    return " ".join(unique_tags)


def _extract_stat_from_text(text: str) -> str:
    """Extract a concrete statistic from text for use in a hook line.

    Always starts at a sentence boundary so the hook never begins mid-word.
    Returns "" if no clean sentence boundary can be found before the number.
    """
    match = re.search(
        r"\b(\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|\s+(?:billion|million|thousand|percent|times|x)))\b",
        text, re.I,
    )
    if not match:
        return ""

    # Walk backwards to find the nearest sentence boundary before the number.
    search_region = text[:match.start()]
    sent_start = 0
    for m in re.finditer(r"[.!?]\s+", search_region):
        sent_start = m.end()

    # If there's no sentence boundary and the text doesn't start with a capital
    # or digit, the snippet would begin mid-sentence — skip it entirely.
    if sent_start == 0:
        first_word = text[:match.start()].strip().split()
        if first_word and not (first_word[0][0].isupper() or first_word[0][0].isdigit()):
            return ""

    end = min(len(text), match.end() + 80)
    snippet = re.sub(r"\s+", " ", text[sent_start:end]).strip()

    # Trim at the first sentence-ending period after the number.
    offset_in_snippet = match.end() - sent_start
    period_pos = snippet.find(".", max(0, offset_in_snippet))
    if period_pos > 0:
        snippet = snippet[:period_pos + 1]

    # Final safety: reject snippets that don't start with a capital letter or digit.
    if not snippet or not (snippet[0].isupper() or snippet[0].isdigit()):
        return ""

    return snippet[:110] if len(snippet) > 10 else ""


def _build_disclaimer_if_needed(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Return a short disclaimer when article content warrants one.

    Always appended with an attribution line so readers know this content
    comes from the original news sources, not from Graitech.
    """
    text = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        " ".join(summary.key_points[:4]),
        " ".join(summary.topics),
    ]).lower()

    warning = ""
    if any(kw in text for kw in ("benchmark", "performance score", "eval")):
        warning = "⚠️ Benchmarks reflect results at publication time and may change as models are updated."
    elif any(kw in text for kw in ("price", "pricing", "$", "cost per")):
        warning = "⚠️ Pricing information is subject to change — verify directly with the provider."
    elif any(kw in text for kw in ("medical", "health", "diagnosis", "clinical")):
        warning = "⚠️ This is not medical advice. AI health tools do not replace professional care."
    elif any(kw in text for kw in ("invest", "financial", "stock", "trading")):
        warning = "⚠️ This is not financial advice. AI investment tools carry significant risks."
    elif any(kw in text for kw in ("regulation", "law", "legal", "compliance", "gdpr")):
        warning = "⚠️ This is not legal advice. Consult a qualified professional for guidance."

    attribution = "ℹ️ Content curated & summarised by Graitech from the sources listed above. All rights remain with the original publishers."

    if warning:
        return f"─\n{warning}\n{attribution}\n─"
    return f"─\n{attribution}\n─"

def _render_index(rows: list[str]) -> str:
    items = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Instagram Carousel Batch</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin:0; background:#050505; color:#fff; font:16px/1.5 Arial, sans-serif; }}
    main {{ max-width:960px; margin:0 auto; padding:48px 24px; }}
    h1 {{ font-size:clamp(2rem, 8vw, 5rem); line-height:1; margin:0 0 24px; }}
    p {{ color:#cfcfcf; max-width:62ch; }}
    ol {{ list-style:none; padding:0; display:grid; gap:12px; }}
    li {{ display:flex; justify-content:space-between; gap:16px; border:1px solid #2b2b2b; padding:16px; background:#101010; }}
    a {{ color:#e8ff47; font-weight:800; text-decoration:none; }}
    span {{ color:#aaa; white-space:nowrap; }}
  </style>
</head>
<body>
  <main>
    <h1>Instagram carousel batch</h1>
    <p>Each folder is one email-based post. Upload the PNG slides in order as a carousel.</p>
    <ol>{items}</ol>
  </main>
</body>
</html>
"""


def _article_items(summary: EmailSummary) -> list[dict[str, Any]]:
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


def _load_used_images_from_db(db_path: Path | None) -> set[str]:
    """Load all previously-used image paths from the agent SQLite database.

    Returns an empty set if the database is missing, inaccessible, or the
    used_images table does not yet exist (first run).
    """
    if not db_path:
        return set()
    try:
        import sqlite3 as _sqlite3
        with _sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS used_images (
                    path TEXT PRIMARY KEY,
                    url  TEXT,
                    used_at TEXT NOT NULL
                )
                """
            )
            rows = conn.execute("SELECT path FROM used_images").fetchall()
            return {row[0] for row in rows}
    except Exception:
        return set()


def _save_used_images_to_db(db_path: Path | None, paths: set[str]) -> None:
    """Persist the set of used image paths into the agent SQLite database."""
    if not db_path or not paths:
        return
    try:
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc).isoformat(timespec="seconds")
        with _sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS used_images (
                    path TEXT PRIMARY KEY,
                    url  TEXT,
                    used_at TEXT NOT NULL
                )
                """
            )
            conn.executemany(
                "INSERT OR IGNORE INTO used_images (path, used_at) VALUES (?, ?)",
                [(p, now) for p in paths if p],
            )
            conn.commit()
    except Exception:
        pass  # Never crash the main pipeline over a DB write failure


def _clean_public_text(text: str) -> str:
    # ── Strip grdevelopers.co email digest noise ──────────────────────────────
    text = re.sub(r"BREAKING AI UPDATE\s*[-–—]\s*", "", text or "", flags=re.I)
    text = re.sub(r"\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]\s*", "", text, flags=re.I)
    text = re.sub(r"\bImpact\s*:\s*(?:Low|Medium|High|Critical)\b", "", text, flags=re.I)
    text = re.sub(r"\bRead\s*time\s*:\s*\d+\s*(?:min|mins|minutes?)\b", "", text, flags=re.I)
    text = re.sub(r"={3,}", "", text)
    text = re.sub(r"Company\s*:\s*[^\n]*(\n|$)", "", text, flags=re.I)
    text = re.sub(r"AI Summary\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"Link\s*:\s*https?://\S+", "", text, flags=re.I)
    # Remove the entire sentence containing "Link : <number>" boilerplate.
    text = re.sub(r"[^.!?]*\bLink\s*:\s*\d+[^.!?]*[.!?]?\s*", "", text, flags=re.I)
    text = re.sub(r"\bLink\s*:\s*", "", text, flags=re.I)
    # Remove "N event(s) detected" digest header lines.
    text = re.sub(r"\b(?:\d+|I)\s+event\(s\)\s+detected\b[^\n]*", "", text, flags=re.I)
    # Strip GitHub markdown changelog headings
    text = re.sub(
        r"#{1,6}\s+(?:Bug Fixes|Features?|Performance|Breaking Changes?|Refactoring?|Chores?|Docs?).*",
        "", text, flags=re.I,
    )
    text = re.sub(r"\*\*([^*]+):\*\*\s*", r"\1: ", text)
    # Strip "More from <Publication>" navigation scrape text (e.g. "More from TechCrunch")
    text = re.sub(r"\bMore from\s+\S+[^\n.!?]*", "", text, flags=re.I)
    # Strip publication pipe suffix from any inline headline references
    text = re.sub(r"\s*\|[^|.\n]{1,40}(?=\s|$)", "", text)
    # ─────────────────────────────────────────────────────────────────────────
    text = re.sub(r"\s+", " ", text).strip()
    text = _strip_decorative_symbols(text)
    # Strip cookie consent blocks that appear mid-text (e.g. from AWS/blog scrapers)
    text = re.sub(
        r"\[…\]\s*Select your cookie.*?(?=\s{2,}|\Z)",
        "",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"(?:Select your cookie preferences|Customize cookie preferences|Essential cookies are necessary"
        r"|You may review and change your choices|Cookie Notice|Cookie preferences"
        r"|Accept all cookies|Reject all cookies|We use essential cookies"
        r"|We and our advertising partners|Cookie settings).*?(?=(?:\s+[A-Z][a-z]|\s*$))",
        " ",
        text,
        flags=re.I | re.S,
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
        if sentence.startswith(("Article ", "Article 1 Title:", "Article title:")):
            continue
        if any(phrase in lowered for phrase in PUBLIC_BLOCKED_PHRASES):
            continue
        # Drop sentences that are mostly cookie/legal noise even if not exact match
        if re.search(r"\bcookies?\b|\bGDPR\b|\bCCPA\b|\bopt.out\b|\bunsubscribe\b", sentence, re.I):
            continue
        # Drop newsletter metadata lines like "Impact: HIGH", "Source: X", "Link: 3"
        if re.fullmatch(r"\s*(impact|source|link|read time)\s*:\s*(low|medium|high|\d+.*)?\s*", sentence, re.I):
            continue
        kept.append(sentence.strip())
    result = " ".join(part for part in kept if part)
    return result


def _strip_decorative_symbols(text: str) -> str:
    cleaned: list[str] = []
    for char in text or "":
        category = unicodedata.category(char)
        if category == "So":
            continue
        cleaned.append(char)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()
