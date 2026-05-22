from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
import tempfile
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
# Instagram allows up to 20 slides per carousel post — use the full limit.
MAX_CAROUSEL_SLIDES = 20
# For digest posts: pack up to 19 news-story slides + 1 CTA = 20 slides per post.
DIGEST_NEWS_PER_POST = 19
# For regular single-article posts: one article tells its full story across slides.
STORIES_PER_CAROUSEL = 1
# For normal (non-digest) emails: pack up to 2 news stories per carousel post.
# Each story gets an image+headline slide + N key-point slides.
NORMAL_NEWS_PER_POST = 2
# Hard minimum readable font size — never go below this on any slide.
FONT_MIN_READABLE = 26
POSTING_SLOTS = ("08:00", "14:00", "18:00", "22:00")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
ACCENT_GREEN = "#C8FF00"
PAGE_BLACK = "#050505"
TEXT_WHITE = "#FFFFFF"
SOFT_WHITE = "#D7D7D7"

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
IMAGE_MIN_HD_W = 1280
IMAGE_MIN_HD_H = 720
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

            slides = _build_slide_specs(part_summary, email_dt)
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
                # Track image paths for cross-batch dedup.
                img = str(slide.get("image_path", "")).strip()
                if img:
                    global_used_image_paths.add(img)

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
        Articles are grouped in pairs (NORMAL_NEWS_PER_POST = 2 per carousel).
        Each pair becomes one post with image+headline + keypoint slides.
    """
    articles = _article_items(summary)

    # ── Normal email — group articles in pairs (NORMAL_NEWS_PER_POST per post) ─
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
    """Remove trailing dots/ellipsis from a headline and tighten whitespace."""
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"[.…]+$", "", text).strip()
    return text


def _build_slide_specs(summary: EmailSummary, email_dt: datetime) -> list[dict[str, Any]]:
    """Route to the correct slide builder based on whether this is a digest or a normal post."""
    if getattr(summary, "_is_digest", False) or _is_digest_summary(summary):
        return _build_digest_slide_specs(summary, email_dt)
    return _build_normal_slide_specs(summary, email_dt)


def _build_digest_slide_specs(summary: EmailSummary, email_dt: datetime) -> list[dict[str, Any]]:
    """Build slides for a digest email carousel.

    Layout per slide:
        • Top 52%: unique article image (from blog; web fallback if missing)
        • Bottom 48%: eyebrow label | headline | brief 2–3 sentence summary | source credit
        • One CTA slide at the end

    Images are deduplicated across all slides in this carousel — no two slides
    ever share the same image URL or local file.
    """
    articles = _article_items(summary)
    if not articles:
        return _build_normal_slide_specs(summary, email_dt)

    slides: list[dict[str, Any]] = []
    # Track URLs and local paths used so far — prevents any image reuse.
    used_image_urls: set[str] = set()
    used_image_paths: set[str] = set()

    # Pick ONE background theme for the whole carousel (consistent visual identity).
    carousel_theme = _pick_bg_theme_from_summary(summary)

    for article_index, article in enumerate(articles[:DIGEST_NEWS_PER_POST], start=1):
        headline = _clean_headline(
            _clean_public_text(str(article.get("title") or summary.headline or "AI update"))
        ) or "AI Update"

        topic = ", ".join(summary.topics[:2]) or headline
        source_label = _source_label_from_url(str(article.get("url") or ""))

        # Build a brief, complete summary for this slide (2–3 sentences, no dots).
        brief = _build_digest_slide_brief(summary, article)

        # Select a unique image for this article.
        image_path = _select_unique_article_image(
            article, topic, used_image_urls, used_image_paths
        )

        slides.append(
            {
                "kind": "digest",
                "slide_index": article_index,
                "eyebrow": _pick_digest_eyebrow(article, summary),
                "title": headline,
                "body": brief,
                "image_path": image_path,
                "topic": topic,
                "url": str(article.get("url", "")),
                "source_label": source_label,
                "bg_theme": carousel_theme,
            }
        )

    # CTA slide
    slides.append(
        {
            "kind": "cta",
            "eyebrow": "GRAITECH",
            "title": "Follow for the next AI briefing",
            "body": "LIKE | COMMENT | FOLLOW | SAVE",
            "image_path": "",
            "source_label": "",
            "bg_theme": carousel_theme,
        }
    )

    return slides[:MAX_CAROUSEL_SLIDES]


def _build_normal_slide_specs(summary: EmailSummary, email_dt: datetime) -> list[dict[str, Any]]:
    """Build the carousel for a regular (non-digest) email.

    Structure per post:
    • Up to NORMAL_NEWS_PER_POST (2) news articles per carousel post.
    • Per article:
        - Slide 1: image + headline  (kind="image")
        - Slides 2-N: one key point per slide  (kind="keypoint")
          N depends on how many key points the extractor produces (3–6).
    • Final slide: CTA  (kind="cta")

    If the email contains more than NORMAL_NEWS_PER_POST articles, this
    function is called once per group of NORMAL_NEWS_PER_POST articles via
    _split_summary_for_carousels().
    """
    articles = _article_items(summary)
    if not articles:
        articles = [
            {
                "url": summary.article_url,
                "title": summary.article_title or summary.headline or summary.subject or "AI update",
                "description": summary.article_excerpt or summary.summary,
                "excerpt": summary.article_excerpt,
                "image_path": summary.article_image_path,
                "image_url": summary.article_image_url,
            }
        ]

    slides: list[dict[str, Any]] = []
    used_image_urls: set[str] = set()
    used_image_paths: set[str] = set()

    # One visual theme per carousel post — all slides share the same background.
    carousel_theme = _pick_bg_theme_from_summary(summary)

    KP_EMOJIS = ["⚡", "🔹", "🧠", "📊", "🔬", "💡", "🛠️", "🌍", "🤖", "📈", "🎯", "🚀"]

    for article_index, article in enumerate(articles[:NORMAL_NEWS_PER_POST], start=1):
        headline = _clean_headline(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
        ) or "AI Update"
        topic = ", ".join(summary.topics[:2]) or headline
        source_label = _source_label_from_url(str(article.get("url") or ""))

        # ── Slide 1: Image + headline ─────────────────────────────────────────
        image_path = _select_unique_article_image(article, topic, used_image_urls, used_image_paths)
        slides.append({
            "kind": "image",
            "eyebrow": f"STORY {article_index:02d}",
            "title": headline,
            "body": "",
            "image_path": image_path,
            "topic": topic,
            "url": str(article.get("url") or ""),
            "source_label": source_label,
            "bg_theme": carousel_theme,
        })

        # ── Slides 2-N: Key-point slides ─────────────────────────────────────
        key_points = _extract_instagram_key_points(article, summary, max_points=6)
        for kp_idx, kp_text in enumerate(key_points):
            emoji = KP_EMOJIS[kp_idx % len(KP_EMOJIS)]
            slides.append({
                "kind": "keypoint",
                "eyebrow": f"STORY {article_index:02d} · POINT {kp_idx + 1}/{len(key_points)}",
                "title": headline,
                "body": kp_text,
                "emoji": emoji,
                "point_num": kp_idx + 1,
                "total_points": len(key_points),
                "image_path": "",
                "topic": topic,
                "url": str(article.get("url") or ""),
                "source_label": source_label,
                "bg_theme": carousel_theme,
            })

    # ── CTA slide ─────────────────────────────────────────────────────────────
    slides.append({
        "kind": "cta",
        "eyebrow": "GRAITECH",
        "title": "Follow for the next AI briefing",
        "body": "LIKE | COMMENT | FOLLOW | SAVE",
        "image_path": "",
        "source_label": "",
        "bg_theme": carousel_theme,
    })

    return slides[:MAX_CAROUSEL_SLIDES]


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
        font = _font(image_font, size, bold=bold)
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

    # ── Article image (top half) ──────────────────────────────────────────────
    artwork = _load_artwork(
        slide.get("image_path", ""),
        slide.get("topic", "AI"),
        image_box,
        image_cls, draw_cls, enhance_cls, filter_cls, ops_cls,
    )
    if artwork is not None:
        artwork = enhance_cls.Color(artwork).enhance(0.88)
        artwork = enhance_cls.Contrast(artwork).enhance(1.08)
        _paste_contained(image, artwork, image_box, radius=32, pad=4, cover=True)
        draw.rounded_rectangle(image_box, radius=32, outline=ACCENT_GREEN, width=2)
        # Subtle gradient overlay on bottom of image for readability
        for gy in range(580, 700):
            alpha = int(180 * (gy - 580) / 120)
            draw.line([(margin, gy), (CANVAS_W - margin, gy)], fill=(5, 5, 5, alpha))
    else:
        # No image — draw a branded placeholder
        draw.rounded_rectangle(image_box, radius=32, fill="#0A0A0A", outline=ACCENT_GREEN, width=2)
        draw.rounded_rectangle((margin + 30, 260, CANVAS_W - margin - 30, 440), radius=20, fill="#111111", outline=(200, 255, 0, 60))
        draw.text(
            (CANVAS_W // 2 - 40, 320),
            "🤖",
            fill=ACCENT_GREEN,
            font=_font(image_font, 72, bold=True),
        )

    # ── Eyebrow + slide counter row ───────────────────────────────────────────
    font_meta = _font(image_font, 26, bold=True, mono=True)
    eyebrow = str(slide.get("eyebrow", "🤖 AI NEWS"))
    _draw_slide_chip(
        draw,
        eyebrow,
        (margin, 714, margin + 280, 756),
        font_meta,
        fill="#0B0B0B",
        outline=ACCENT_GREEN,
    )
    counter_text = f"{slide_number:02d} / {total_slides:02d}"
    _draw_slide_chip(
        draw,
        counter_text,
        (CANVAS_W - margin - 160, 714, CANVAS_W - margin, 756),
        font_meta,
        fill="#0B0B0B",
        outline=(60, 60, 60, 200),
    )

    # ── Headline — auto-sized, full text, no truncation ───────────────────────
    headline = _clean_headline(str(slide.get("title", "AI Update")))
    headline_box = (margin, 768, CANVAS_W - margin, 930)
    _draw_autofit_text(
        draw, headline, headline_box, image_font,
        fill=TEXT_WHITE, bold=True, size_max=68, size_min=32, max_lines=3, align="left",
    )

    # ── Separator line ────────────────────────────────────────────────────────
    draw.line([(margin, 938), (CANVAS_W - margin, 938)], fill=ACCENT_GREEN, width=2)

    # ── Body summary — auto-sized, no dots, complete sentences ───────────────
    body_text = str(slide.get("body", "")).strip()
    if body_text:
        body_box = (margin, 950, CANVAS_W - margin, 1220)
        _draw_autofit_text(
            draw, body_text, body_box, image_font,
            fill=SOFT_WHITE, bold=False, size_max=36, size_min=FONT_MIN_READABLE, max_lines=8, align="left",
        )

    # ── Source credit ─────────────────────────────────────────────────────────
    source = str(slide.get("source_label", "")).strip()
    if source:
        draw.rounded_rectangle(
            (margin, 1232, CANVAS_W - margin, 1270),
            radius=10, fill=(12, 12, 12, 200), outline=(80, 80, 80, 100),
        )
        font_source = _font(image_font, 24, bold=False)
        draw.text(
            (margin + 16, 1242),
            f"Source: {source}",
            fill=SOFT_WHITE,
            font=font_source,
        )

    # ── Progress bar ─────────────────────────────────────────────────────────
    bar_x1, bar_y = margin, 1290
    bar_total = CANVAS_W - margin * 2
    draw.rounded_rectangle((bar_x1, bar_y, bar_x1 + bar_total, bar_y + 6), radius=3, fill=(40, 40, 40))
    filled = int(bar_total * slide_number / total_slides)
    if filled > 0:
        draw.rounded_rectangle((bar_x1, bar_y, bar_x1 + filled, bar_y + 6), radius=3, fill=ACCENT_GREEN)


def _write_slide_png(path: Path, slide_number: int, total_slides: int, slide: dict[str, Any], email_dt: datetime) -> None:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), PAGE_BLACK)
    draw = ImageDraw.Draw(image, "RGBA")
    # Font sizes tuned for a 1080×1350 canvas — body text is large enough to
    # fill the slide and be readable on a phone screen without zooming.
    font_eyebrow = _font(ImageFont, 36, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])
    font_title   = _font(ImageFont, 62, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"])
    font_body    = _font(ImageFont, 38, bold=False, preferred=["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    font_meta    = _font(ImageFont, 26, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])
    font_cta     = _font(ImageFont, 46, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
    font_brand   = _font(ImageFont, 112, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])

    _draw_dynamic_background(draw, slide)
    _draw_accent_frame(draw)

    margin = 72

    # ── Digest slide — each news item gets its own visual card ────────────────
    if slide["kind"] == "digest":
        _write_digest_slide(
            image, draw, slide_number, total_slides, slide,
            ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _draw_handle_overlay(draw, ImageFont)
        _draw_watermark_overlay(image)
        image.save(path, "PNG", optimize=True)
        return

    if slide["kind"] == "image":
        # ── Full title at the TOP — neon green, auto-sized, never truncated ──
        title_text = _clean_headline(str(slide.get("title", "AI Update")))
        draw.rounded_rectangle((54, 44, CANVAS_W - 54, 314), radius=24,
                                fill=(0, 0, 0, 220), outline=(200, 255, 0, 70), width=2)
        _draw_autofit_text(
            draw, title_text,
            (76, 58, CANVAS_W - 76, 298),
            ImageFont,
            fill=ACCENT_GREEN, bold=True, size_max=76, size_min=30,
            max_lines=4, align="center",
        )

        # ── Image below the title ─────────────────────────────────────────────
        image_box = (54, 322, CANVAS_W - 54, 1180)
        artwork = _load_artwork(
            slide.get("image_path", ""),
            slide.get("topic", "AI"),
            image_box,
            Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps,
        )
        if artwork is not None:
            artwork = ImageEnhance.Color(artwork).enhance(0.90)
            artwork = ImageEnhance.Contrast(artwork).enhance(1.05)
            _paste_contained(image, artwork, image_box, radius=30, pad=4, cover=False)
            draw.rounded_rectangle(image_box, radius=30, outline=ACCENT_GREEN, width=2)
            # Source label at bottom of image
            source_text = (slide.get("source_label") or
                           _source_label_from_url(str(slide.get("url") or "")))
            if source_text:
                draw.rounded_rectangle(
                    (54, 1146, CANVAS_W - 54, 1180), radius=12,
                    fill=(0, 0, 0, 200),
                )
                font_src = _font(ImageFont, 26, bold=False)
                _draw_centered_text(
                    draw, f"SOURCE: {source_text}",
                    (76, 1150, CANVAS_W - 76, 1178),
                    font_src, SOFT_WHITE, 1,
                )
        else:
            _draw_no_image_story_card(
                draw,
                slide.get("eyebrow", "STORY"),
                slide.get("title", "AI update"),
                slide.get("url", ""),
                image_box,
                font_eyebrow, font_title, font_body, font_meta,
            )

        # ── Progress bar ──────────────────────────────────────────────────────
        draw.rounded_rectangle((160, 1200, 920, 1212), radius=3, fill=ACCENT_GREEN)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}",
                            (450, 1222, 630, 1266), font_meta, SOFT_WHITE, 1)
    elif slide["kind"] == "keypoint":
        # ── Article headline at TOP — neon green, full text, auto-sized ───────
        headline = _clean_headline(str(slide.get("title", "AI Update")))
        draw.rounded_rectangle(
            (54, 36, CANVAS_W - 54, 224), radius=22,
            fill=(0, 0, 0, 220), outline=(200, 255, 0, 70), width=2,
        )
        _draw_autofit_text(
            draw, headline,
            (76, 50, CANVAS_W - 76, 210),
            ImageFont,
            fill=ACCENT_GREEN, bold=True, size_max=56, size_min=26,
            max_lines=3, align="center",
        )

        # ── Point counter pill ────────────────────────────────────────────────
        pt_num = slide.get("point_num", 1)
        pt_tot = slide.get("total_points", 1)
        pt_label = f"KEY INSIGHT  {pt_num} / {pt_tot}"
        draw.rounded_rectangle(
            (CANVAS_W // 2 - 210, 236, CANVAS_W // 2 + 210, 288),
            radius=20, fill=(200, 255, 0, 18), outline=(200, 255, 0, 110), width=2,
        )
        _draw_centered_text(
            draw, pt_label,
            (CANVAS_W // 2 - 210, 236, CANVAS_W // 2 + 210, 288),
            font_meta, ACCENT_GREEN, 1,
        )

        # ── Key-point container — white text, dark rounded card ───────────────
        kp_text = str(slide.get("body", ""))
        kp_card = (54, 302, CANVAS_W - 54, 1172)
        draw.rounded_rectangle(kp_card, radius=36, fill=(8, 8, 8, 240),
                                outline=(200, 255, 0, 80), width=2)
        kp_box = (88, 334, CANVAS_W - 88, 1142)
        _draw_autofit_text(
            draw, kp_text, kp_box, ImageFont,
            fill=TEXT_WHITE, bold=True, size_max=68, size_min=FONT_MIN_READABLE,
            max_lines=8, align="center",
        )

        # ── Progress bar + counter ────────────────────────────────────────────
        draw.rounded_rectangle((160, 1192, 920, 1204), radius=3, fill=ACCENT_GREEN)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}",
                            (450, 1216, 630, 1260), font_meta, SOFT_WHITE, 1)

    elif slide["kind"] == "cta":
        draw.rounded_rectangle((margin, 92, CANVAS_W - margin, 1258), radius=46, fill="#0B0B0B", outline="#1F1F1F", width=2)
        draw.rounded_rectangle((92, 126, 988, 184), radius=18, fill=(200, 255, 0, 20), outline=(200, 255, 0, 130), width=2)
        _draw_centered_text(draw, "GRAITECH", (140, 150, 940, 240), font_brand, ACCENT_GREEN, 1)
        _draw_centered_text(draw, "Instagram-ready AI news", (140, 278, 940, 365), font_title, TEXT_WHITE, 1)
        _draw_social_icons(draw, (140, 410, 940, 540), font_meta)
        _draw_centered_logo_panel(image, (240, 575, 840, 945))
        _draw_centered_text(draw, "Save this post for your next AI briefing.", (130, 1000, 950, 1080), font_body, TEXT_WHITE, 1)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1120, 630, 1170), font_meta, ACCENT_GREEN, 1)
        _draw_cta_pills(draw, font_meta)
    else:
        # ── Eyebrow label ─────────────────────────────────────────────────────
        _draw_slide_chip(
            draw,
            slide["eyebrow"],
            (64, 60, 420, 116),
            font_meta,
            fill="#0B0B0B",
            outline=ACCENT_GREEN,
        )
        source_label = slide.get("source_label") or _source_label_from_url(str(slide.get("url") or ""))
        if source_label:
            _draw_slide_chip(
                draw,
                f"SOURCE: {source_label}",
                (648, 60, 1016, 116),
                font_meta,
                fill="#0B0B0B",
                outline=(80, 80, 80, 180),
            )

        # ── Title — auto-sized, complete text, never truncated ───────────────
        title_box = (84, 150, CANVAS_W - 84, 340)
        draw.rounded_rectangle((72, 142, CANVAS_W - 72, 360), radius=30, fill=(8, 8, 8, 228), outline=(200, 255, 0, 120), width=2)
        _draw_autofit_text(
            draw, _clean_headline(slide.get("title", "")), title_box, ImageFont,
            fill=TEXT_WHITE, bold=True, size_max=62, size_min=FONT_MIN_READABLE, max_lines=3, align="center",
        )
        draw.line((104, 352, CANVAS_W - 104, 352), fill=ACCENT_GREEN, width=3)

        # ── Body container — same dark rounded style as supporting box ─────────
        body_container = (64, 364, CANVAS_W - 64, 902)
        draw.rounded_rectangle(body_container, radius=30, fill=(8, 8, 8, 235), outline=(40, 40, 40, 180), width=1)
        draw.rounded_rectangle((84, 384, 316, 436), radius=18, fill=(200, 255, 0, 18), outline=(200, 255, 0, 110), width=2)
        _draw_centered_text(draw, "WHAT HAPPENED", (92, 392, 308, 430), font_meta, ACCENT_GREEN, 1)

        # Body text — auto-sized so the full summary always fits, no dots
        body_box = (96, 432, CANVAS_W - 96, 890)
        _draw_autofit_text(
            draw, str(slide["body"]), body_box, ImageFont,
            fill=SOFT_WHITE, bold=False, size_max=38, size_min=FONT_MIN_READABLE, max_lines=12, align="center",
        )

        # ── Supporting note box ───────────────────────────────────────────────
        supporting = str(slide.get("supporting", "")).strip()
        if supporting:
            support_box = (64, 912, CANVAS_W - 64, 1210)
            draw.rounded_rectangle(support_box, radius=28, outline=ACCENT_GREEN, width=2, fill=(10, 10, 10, 245))
            draw.line((108, 956, 972, 956), fill=(200, 255, 0, 60), width=2)
            font_support = _font(ImageFont, 34, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
            _draw_centered_text_block(
                draw,
                supporting,
                box=(96, 940, CANVAS_W - 96, 1182),
                font=font_support,
                fill=TEXT_WHITE,
                line_gap=14,
                max_lines=5,
            )

        # ── Slide counter ─────────────────────────────────────────────────────
        draw.rounded_rectangle((160, 1252, 920, 1266), radius=3, fill=ACCENT_GREEN)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1274, 630, 1314), font_meta, SOFT_WHITE, 1)

    path.parent.mkdir(parents=True, exist_ok=True)
    _draw_handle_overlay(draw, ImageFont)
    _draw_watermark_overlay(image)
    image.save(path, "PNG", optimize=True)


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
    draw.line((86, 94, 318, 94), fill=ACCENT_GREEN, width=4)
    draw.line((762, 94, 994, 94), fill=ACCENT_GREEN, width=4)
    draw.line((86, 1256, 318, 1256), fill=ACCENT_GREEN, width=4)
    draw.line((762, 1256, 994, 1256), fill=ACCENT_GREEN, width=4)
    draw.line((92, 124, 92, 214), fill=(200, 255, 0, 70), width=3)
    draw.line((988, 124, 988, 214), fill=(200, 255, 0, 70), width=3)


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


def _load_artwork(image_path: str, topic: str, box: tuple[int, int, int, int], image_cls, draw_cls, enhance_cls, filter_cls, ops_cls):
    path = _resolve_image_source(image_path)
    if path and path.exists():
        try:
            art = image_cls.open(path).convert("RGB")
            art = enhance_cls.Color(art).enhance(0.88)
            art = enhance_cls.Contrast(art).enhance(1.08)
            return art.filter(filter_cls.UnsharpMask(radius=2, percent=110))
        except Exception:
            pass
    return None


def _draw_no_image_story_card(
    draw,
    eyebrow: str,
    title: str,
    url: str,
    box: tuple[int, int, int, int],
    font_eyebrow,
    font_title,
    font_body,
    font_meta,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=36, fill="#080808", outline=ACCENT_GREEN, width=2)
    draw.rectangle((x1 + 36, y1 + 36, x2 - 36, y1 + 44), fill=ACCENT_GREEN)
    _draw_centered_text(draw, _strip_decorative_symbols(eyebrow).upper(), (x1 + 70, y1 + 96, x2 - 70, y1 + 142), font_eyebrow, ACCENT_GREEN, 1)
    _draw_centered_text_block(
        draw,
        _strip_decorative_symbols(title),
        (x1 + 86, y1 + 220, x2 - 86, y1 + 520),
        font_title,
        TEXT_WHITE,
        line_gap=14,
        max_lines=4,
    )
    source = _source_label_from_url(url)
    footer = f"Source: {source}" if source else "Source: email brief"
    _draw_centered_text_block(
        draw,
        footer,
        (x1 + 110, y2 - 210, x2 - 110, y2 - 120),
        font_body,
        SOFT_WHITE,
        line_gap=10,
        max_lines=2,
    )
    _draw_centered_text(draw, "SOURCE BRIEF", (x1 + 160, y2 - 96, x2 - 160, y2 - 52), font_meta, ACCENT_GREEN, 1)


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
    from PIL import Image, ImageOps

    watermark_path = next((candidate for candidate in WATERMARK_CANDIDATES if candidate.exists()), None)
    if not watermark_path:
        return
    try:
        watermark = Image.open(watermark_path).convert("RGBA")
        watermark = ImageOps.contain(watermark, (92, 92), method=Image.Resampling.LANCZOS)
        watermark = _remove_logo_background(watermark)
        alpha = watermark.getchannel("A")
        alpha = alpha.point(lambda value: int(value * 0.88))
        watermark.putalpha(alpha)
        base_image.paste(watermark, (CANVAS_W - watermark.width - 28, 24), watermark)
    except Exception:
        return


def _draw_handle_overlay(draw, image_font) -> None:
    """Draw the @graitech Instagram handle at the bottom-left of every slide."""
    font = _font(image_font, 28, bold=True, mono=True)
    handle = "@graitech"
    try:
        bbox = draw.textbbox((0, 0), handle, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = 160, 28
    x = 36
    y = CANVAS_H - text_h - 38
    draw.rounded_rectangle(
        (x - 10, y - 8, x + text_w + 12, y + text_h + 8),
        radius=12, fill=(0, 0, 0, 190),
    )
    draw.text((x, y), handle, fill=ACCENT_GREEN, font=font)


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


def _font(image_font, size: int, bold: bool = False, mono: bool = False, preferred: list[str] | None = None):
    # Try bundled fonts first
    bundled_dir = Path(__file__).resolve().parent / "fonts"
    bundled_candidates = []
    if mono:
        bundled_candidates.append(bundled_dir / "RobotoMono-Regular.ttf")
    elif bold:
        bundled_candidates.append(bundled_dir / "Roboto-Bold.ttf")
    else:
        bundled_candidates.append(bundled_dir / "Roboto-Regular.ttf")
    
    # Fallback to other styles just in case
    bundled_candidates.extend([
        bundled_dir / "Roboto-Bold.ttf",
        bundled_dir / "Roboto-Regular.ttf",
        bundled_dir / "RobotoMono-Regular.ttf"
    ])
    
    for cand in bundled_candidates:
        if cand.exists():
            try:
                return image_font.truetype(str(cand), size=size)
            except OSError:
                pass

    # Fallback to system fonts
    candidates = []
    if preferred:
        candidates.extend(preferred)
    if mono:
        candidates.extend(["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf"])
    if bold:
        candidates.extend(["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
    candidates.extend(["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"])
    
    # Add Linux standard font paths for extra safety
    linux_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"
    ]
    candidates.extend(linux_paths)
    
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
    4. Return empty string (slide will render text-only fallback)

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
                # Prefer HD images from library; fall through if sub-HD but still use as last resort.
                if _validate_image_hd(value):
                    used_image_paths.add(value)
                    return value
                # Keep as fallback — will be used below if no HD source found.
                # (We still mark it so the loop below won't pick it redundantly.)
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
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0; +https://graitech.ai)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(article_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_html = resp.read(300_000).decode("utf-8", errors="replace")
    except Exception:
        return ""

    # 1. og:image
    og = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*/?\\s*>',
        raw_html, re.I,
    )
    if not og:
        og = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*/?\\s*>',
            raw_html, re.I,
        )
    if og:
        img_url = og.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            return img_url

    # 2. twitter:image
    tw = re.search(
        r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*/?\\s*>',
        raw_html, re.I,
    )
    if not tw:
        tw = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']twitter:image["\'][^>]*/?\\s*>',
            raw_html, re.I,
        )
    if tw:
        img_url = tw.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            return img_url

    # 3. First substantive <img> in article/main content area
    content_block = re.search(
        r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>',
        raw_html, re.I | re.S,
    )
    search_zone = content_block.group(1) if content_block else raw_html
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*/?\\s*>', search_zone, re.I):
        src = img_match.group(1).strip()
        if (src.startswith(("http://", "https://"))
                and any(ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp"))
                and not any(skip in src.lower() for skip in ("logo", "icon", "avatar", "pixel", "tracking", "badge", "1x1", "spacer"))):
            return src

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
    if len(data) < 10_000:
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


def _extract_instagram_key_points(
    article: dict[str, Any],
    summary: "EmailSummary",
    max_points: int = 6,
) -> list[str]:
    """Extract punchy, attention-grabbing key points for Instagram slides.

    Writes like a professional content creator:
    - Short and impactful (≤ 90 chars each)
    - Starts with a verb, stat, or striking claim when possible
    - Avoids fluff words and filler phrases
    - Each point must add new information (no repeats)
    - Returns 3–6 points ordered by impact (most striking first)
    """
    STOP_PREFIXES = (
        "this article", "in this post", "the article", "we discuss",
        "this piece", "this blog", "you will learn", "click here",
        "read more", "find out", "learn how", "sign up",
    )
    POWER_VERBS = (
        "launches", "releases", "achieves", "beats", "surpasses", "reveals",
        "breaks", "builds", "cuts", "doubles", "enables", "expands",
        "introduces", "joins", "reaches", "replaces", "sets", "ships",
        "shows", "trains", "upgrades",
    )

    raw: list[str] = []

    # 1. Use pre-structured key_points from article (highest quality)
    for p in article.get("key_points", []):
        cleaned = _clean_public_text(str(p)).strip()
        if len(cleaned) > 12 and not any(cleaned.lower().startswith(pfx) for pfx in STOP_PREFIXES):
            raw.append(cleaned)

    # 2. Also pull from summary-level key_points
    for p in (summary.key_points or []):
        cleaned = _clean_public_text(str(p)).strip()
        if cleaned and cleaned not in raw and len(cleaned) > 12:
            if not any(cleaned.lower().startswith(pfx) for pfx in STOP_PREFIXES):
                raw.append(cleaned)

    # 3. Fallback — mine structured fields for insight sentences
    if len(raw) < 3:
        for field in ("what_happened", "why_matters", "what_to_watch", "description", "excerpt"):
            text = _clean_public_text(str(article.get(field) or ""))
            if not text:
                continue
            for sent in re.split(r"(?<=[.!?])\s+", text):
                sent = sent.strip()
                if len(sent) > 30 and sent not in raw:
                    raw.append(sent)
                if len(raw) >= max_points * 2:
                    break
            if len(raw) >= max_points * 2:
                break

    # Deduplicate by first-60-chars fingerprint
    seen: set[str] = set()
    deduped: list[str] = []
    for p in raw:
        key = re.sub(r"\s+", " ", p).lower()[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    # Score: prefer shorter + starts with power verb / stat
    def _point_score(pt: str) -> float:
        score = 0.0
        pt_l = pt.lower()
        if any(pt_l.startswith(v) for v in POWER_VERBS):
            score += 0.4
        if re.search(r"\b\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|x|\s+(?:billion|million|percent|times))", pt, re.I):
            score += 0.35
        if len(pt) <= 80:
            score += 0.25
        return score

    deduped.sort(key=_point_score, reverse=True)

    # Trim each point to a readable length without dots
    final = [_trim_no_dots(pt, 110) for pt in deduped[:max_points]]
    return final if final else [_trim_no_dots(summary.headline or summary.subject or "AI update", 110)]


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
        if width < 500 or height < 350:
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
    source_domain = _source_label_from_url(article_url)

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

    # ── Source credit ─────────────────────────────────────────────────────────
    if source_domain and article_url:
        source_credit = f"📰 Source: {source_domain}\n🔗 {article_url}"
    elif article_url:
        source_credit = f"🔗 {article_url}"
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
    """Extract a concrete statistic from text for use in a hook line."""
    match = re.search(
        r"\b(\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|\s+(?:billion|million|thousand|percent|times|x)))\b",
        text, re.I,
    )
    if not match:
        return ""
    start = max(0, match.start() - 40)
    end = min(len(text), match.end() + 60)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    period_pos = snippet.find(".", match.end() - start)
    if period_pos > 0:
        snippet = snippet[:period_pos + 1]
    return _trim_no_dots(snippet, 100) if len(snippet) > 10 else ""


def _build_disclaimer_if_needed(summary: EmailSummary, article: dict[str, Any]) -> str:
    """Return a short disclaimer when article content warrants one."""
    text = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        " ".join(summary.key_points[:4]),
        " ".join(summary.topics),
    ]).lower()

    if any(kw in text for kw in ("benchmark", "performance score", "eval")):
        return "─\n⚠️ Benchmarks reflect results at publication time and may change as models are updated.\n─"
    if any(kw in text for kw in ("price", "pricing", "$", "cost per")):
        return "─\n⚠️ Pricing information is subject to change — verify directly with the provider.\n─"
    if any(kw in text for kw in ("medical", "health", "diagnosis", "clinical")):
        return "─\n⚠️ This is not medical advice. AI health tools do not replace professional care.\n─"
    if any(kw in text for kw in ("invest", "financial", "stock", "trading")):
        return "─\n⚠️ This is not financial advice. AI investment tools carry significant risks.\n─"
    if any(kw in text for kw in ("regulation", "law", "legal", "compliance", "gdpr")):
        return "─\n⚠️ This is not legal advice. Consult a qualified professional for guidance.\n─"
    return ""

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
    text = re.sub(r"\s+", " ", text or "").strip()
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
        if re.fullmatch(r"\s*(impact|source|link|read time)\s*:\s*(low|medium|high|\d+.*)?", sentence, re.I):
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


def _source_label_from_url(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/?#]+)", url or "")
    if not match:
        return ""
    return match.group(1).replace("www.", "")


def _clean_public_points(points: list[str], headline: str, summary_text: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    headline_key = re.sub(r"\s+", " ", headline or "").strip().lower()
    summary_key = re.sub(r"\s+", " ", summary_text or "").strip().lower()
    for point in points:
        cleaned_point = _clean_public_text(point)
        normalized = re.sub(r"\s+", " ", cleaned_point).strip().lower()
        if not cleaned_point:
            continue
        if normalized in seen:
            continue
        if normalized == headline_key or normalized == summary_key:
            continue
        if any(normalized.startswith(prefix) for prefix in NOISY_POINT_PREFIXES):
            continue
        if headline_key and (normalized.startswith(headline_key) or headline_key in normalized):
            continue
        if len(cleaned_point) < 12:
            continue
        seen.add(normalized)
        cleaned.append(cleaned_point)
    return cleaned


def _fallback_summary_text(summary: EmailSummary, headline: str) -> str:
    parts = [headline.strip()]
    if summary.companies:
        parts.append(f"Company: {summary.companies[0]}")
    if summary.models:
        parts.append(f"Model: {summary.models[0]}")
    if summary.topics:
        parts.append(f"Topic: {summary.topics[0]}")
    return " | ".join(part for part in parts if part)


def _fallback_public_points(summary: EmailSummary) -> list[str]:
    points: list[str] = []
    if summary.companies:
        points.append(f"Primary company in this update: {summary.companies[0]}")
    if summary.models:
        points.append(f"Model highlighted: {summary.models[0]}")
    if summary.topics:
        points.append(f"Main topic: {summary.topics[0]}")
    if summary.article_title:
        points.append(_tighten(summary.article_title, 120))
    return points


def _fallback_story_page(summary: EmailSummary, article: dict[str, Any], page_number: int) -> str:
    companies = ", ".join(_clean_entity_list(summary.companies)[:3])
    topics = ", ".join(summary.topics[:3])
    title = _tighten(_clean_public_text(str(article.get("title") or summary.headline or "AI update")), 72)
    if page_number == 1:
        return f"The main update is {title}. The article points to a concrete AI development rather than a broad category label."
    if page_number == 2:
        entity = companies or "the companies and users affected by this update"
        theme = topics or "AI product adoption"
        return f"The bigger signal is how this could affect {entity}. The practical angle is {theme}, especially for people tracking AI tools, launches, and platform shifts."
    parts = [
        f"Watch how {title} develops next." if title else "",
        f"Teams to watch: {companies}." if companies else "",
        f"Key signal: {topics}." if topics else "",
        "The next useful signal will be adoption, pricing, benchmarks, limitations, or user reaction.",
    ]
    return " ".join(part for part in parts if part)


def _dedupe_lead_text(text: str, headline: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    headline = re.sub(r"\s+", " ", headline or "").strip()
    if not text or not headline:
        return text
    lowered = text.lower()
    headline_lower = headline.lower()
    if lowered == headline_lower:
        return text
    if lowered.startswith(headline_lower):
        remainder = text[len(headline):].strip()
        if remainder.startswith(("-", "|", ":", ".")):
            remainder = remainder[1:].strip()
        return remainder or headline
    return text


def _supporting_note(summary: EmailSummary, article: dict[str, Any], article_index: int, heading: str, variant: str = "why") -> str:
    # Prefer the pre-structured narrative fields from the new summariser
    why_matters = _clean_public_text(str(article.get("why_matters") or ""))
    what_watch = _clean_public_text(str(article.get("what_to_watch") or ""))
    what_happened = _clean_public_text(str(article.get("what_happened") or ""))
    points = [_clean_public_text(str(p)) for p in article.get("key_points", []) if str(p).strip()]
    points = [p for p in points if p]
    topics = ", ".join(summary.topics[:3]) or "AI product updates"
    article_title = _tighten(_clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update")), 72)
    if variant == "why":
        detail = why_matters or (points[1] if len(points) > 1 else points[0] if points else f"This changes the practical AI tooling story around {topics}.")
        return f"{heading}\n\n{_tighten(detail, 200)}"
    if variant == "signal":
        detail = what_watch or (points[2] if len(points) > 2 else f"Watch whether this becomes useful in real workflows, not just another announcement.")
        return f"{heading}\n\n{_tighten(detail, 200)}"
    detail = what_watch or (points[2] if len(points) > 2 else f"Watch adoption, developer feedback, and follow-up releases around {article_title}.")
    return f"{heading}\n\n{_tighten(detail, 200)}"


def _email_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()

def _keywords(summary: EmailSummary) -> list[str]:
    raw = [*_clean_entity_list(summary.companies), *summary.models, *summary.topics]
    raw.extend(["AI news", "AI tools", "automation", "tech update", "artificial intelligence"])
    seen: set[str] = set()
    keywords: list[str] = []
    for item in raw:
        cleaned = re.sub(r"\s+", " ", item).strip()
        key = cleaned.lower()
        if cleaned and key not in seen and not any(term in key for term in VIDEO_BLOCKED_TERMS):
            seen.add(key)
            keywords.append(cleaned)
    return keywords


def _tighten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug[:72] or "ai-news"

def _hashtag(value: str) -> str:
    tag = re.sub(r"[^a-zA-Z0-9]", "", value.title())
    return tag or "AINews"


def _clean_entity_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = re.sub(r"\s+", " ", raw or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if any(term in lowered for term in NOISY_ENTITY_TERMS):
            continue
        if len(value.split()) > 4:
            continue
        key = lowered
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned
