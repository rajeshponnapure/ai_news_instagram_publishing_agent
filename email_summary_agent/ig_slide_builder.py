"""ig_slide_builder.py — slide specification construction for the Instagram pipeline."""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .ig_constants import (
    DIGEST_NEWS_PER_POST,
    MAX_CAROUSEL_SLIDES,
    MAX_KP_PER_SLIDE,
    NORMAL_NEWS_PER_POST,
)
from .ig_utils import (
    _article_items,
    _clean_headline,
    _clean_public_text,
    _scrape_article_text,
    _source_label_from_url,
    _trim_no_dots,
)
from .ig_image import _fetch_og_image_from_url, _select_unique_article_image
from .ig_keypoints import _extract_instagram_key_points
from .ig_copy import layout_safe_headline, layout_safe_points

if TYPE_CHECKING:
    from .models import EmailSummary


# ─────────────────────────────────────────────────────────────────────────────
# Background theme classification
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Digest / normal classification
# ─────────────────────────────────────────────────────────────────────────────

def _is_digest_summary(summary: "EmailSummary") -> bool:
    """Return True when this summary represents a daily digest email.

    Digest emails are the once-per-day bulk emails containing 15–50 news items.
    Normal emails arrive throughout the day with 1–N articles (N is typically small).

    Detection rules:
    1. subject/headline matches a known digest pattern (strongest signal)
    2. article_items >= 8 (genuine digest — normal emails rarely exceed 4-5 articles)
    """
    subject = summary.subject or summary.headline or ""
    if re.search(
        r"\b(AI\s+Alert|AI\s+Digest|AI\s+Updates|daily\s+digest|news\s+digest|"
        r"morning\s+brief|evening\s+brief|weekly\s+digest|ai\s+roundup|tech\s+digest)\b",
        subject, re.I,
    ):
        return True
    articles = _article_items(summary)
    return len(articles) >= 8


def _split_summary_for_carousels(summary: "EmailSummary") -> "list[EmailSummary]":
    """Split a summary into one or more carousel-sized EmailSummary objects.

    DIGEST emails (8+ article_items OR subject matches digest pattern):
        Each article_item becomes one digest slide.
        Posts are capped at DIGEST_NEWS_PER_POST news slides + 1 CTA = MAX_CAROUSEL_SLIDES.
        If the digest has more items than fit in one post, extra posts are created.

    NORMAL emails (< 8 article_items, no digest subject):
        Articles are grouped in batches of NORMAL_NEWS_PER_POST (8) per carousel.
        Each batch becomes one post using the same unified layout as digest posts.
    """
    from .models import EmailSummary as _ES

    articles = _article_items(summary)

    # ── Normal email — group articles in batches of NORMAL_NEWS_PER_POST per post ─
    if not _is_digest_summary(summary):
        articles = _article_items(summary)
        if len(articles) <= NORMAL_NEWS_PER_POST:
            return [summary]
        normal_parts: list[_ES] = []
        for chunk_start in range(0, len(articles), NORMAL_NEWS_PER_POST):
            chunk = articles[chunk_start:chunk_start + NORMAL_NEWS_PER_POST]
            first = chunk[0]
            part = _ES(
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
    parts: list[_ES] = []

    base_headline = _clean_headline(summary.headline or summary.subject or "Daily AI Digest")

    for part_number, chunk in enumerate(chunks, start=1):
        if total_parts > 1:
            headline = f"{base_headline} — Part {part_number} of {total_parts}"
        else:
            headline = base_headline

        first = chunk[0]
        part = _ES(
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


# ─────────────────────────────────────────────────────────────────────────────
# Slide spec construction
# ─────────────────────────────────────────────────────────────────────────────

def _build_slide_specs(
    summary: "EmailSummary",
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Route to the correct slide builder based on whether this is a digest or a normal post."""
    if getattr(summary, "_is_digest", False) or _is_digest_summary(summary):
        return _build_digest_slide_specs(summary, email_dt, initial_used_paths)
    return _build_normal_slide_specs(summary, email_dt, initial_used_paths)


def _build_fallback_single_slide(
    summary: "EmailSummary",
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

    headline_raw = _clean_headline(
        _clean_public_text(str(summary.headline or summary.subject or "AI Update"))
    ) or "AI Update"
    headline = layout_safe_headline(headline_raw, fallback="AI Update")
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

    if url and not synthetic_article["image_url"]:
        og = _fetch_og_image_from_url(url)
        if og:
            synthetic_article["image_url"] = og

    image_path = _select_unique_article_image(
        synthetic_article, topic, used_image_urls, used_image_paths
    )
    key_points = _extract_instagram_key_points(synthetic_article, summary, max_points=4)
    body_text = "\n".join(key_points) if key_points else "\n".join(
        layout_safe_points([_clean_public_text(summary.summary or "")], limit=2)
    )

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
    summary: "EmailSummary",
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
        return _build_fallback_single_slide(summary, email_dt, initial_used_paths)

    slides: list[dict[str, Any]] = []
    used_image_urls: set[str] = set()
    used_image_paths: set[str] = set(initial_used_paths or ())

    carousel_theme = _pick_bg_theme_from_summary(summary)
    max_content_slides = MAX_CAROUSEL_SLIDES - 1
    used_key_fingerprints: set[str] = set()

    for article_index, article in enumerate(articles[:DIGEST_NEWS_PER_POST], start=1):
        if len(slides) >= max_content_slides:
            break

        url = str(article.get("url") or "")
        article = dict(article)   # work on a copy
        if url and not article.get("scraped_content"):
            scraped = _scrape_article_text(url)
            if scraped:
                article["scraped_content"] = scraped

        if url and not article.get("image_url") and not article.get("image_path"):
            og_url = _fetch_og_image_from_url(url)
            if og_url:
                article["image_url"] = og_url

        headline_raw = _clean_headline(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
        ) or "AI Update"
        headline = layout_safe_headline(headline_raw, fallback=str(summary.headline or "AI Update"))

        topic = ", ".join(summary.topics[:2]) or headline
        source_label = _source_label_from_url(url)

        image_path = _select_unique_article_image(
            article, topic, used_image_urls, used_image_paths
        )

        all_key_points = _extract_instagram_key_points(
            article, summary, max_points=5, used_fingerprints=used_key_fingerprints
        )

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

        if overflow_points and len(slides) < max_content_slides:
            slides.append({
                "kind": "digest",
                "slide_index": article_index,
                "eyebrow": _pick_digest_eyebrow(article, summary),
                "title": headline,
                "body": "\n".join(overflow_points),
                "image_path": image_path,
                "topic": topic,
                "url": url,
                "source_label": source_label,
                "bg_theme": carousel_theme,
            })

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
    summary: "EmailSummary",
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


# ─────────────────────────────────────────────────────────────────────────────
# Slide content helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_digest_slide_brief(summary: "EmailSummary", article: dict[str, Any]) -> str:
    """Build a brief, complete 2–3 sentence summary for a single digest slide."""
    what_happened = _clean_public_text(str(article.get("what_happened") or ""))
    why_matters = _clean_public_text(str(article.get("why_matters") or ""))

    if what_happened and why_matters:
        combined = f"{what_happened} {why_matters}"
        return _trim_no_dots(combined, 480)

    if what_happened:
        desc = _clean_public_text(str(article.get("description") or article.get("excerpt") or ""))
        combined = f"{what_happened} {desc}".strip()
        return _trim_no_dots(combined, 480)

    for key in ("summary", "description", "excerpt"):
        text = _clean_public_text(str(article.get(key) or ""))
        if len(text) >= 80:
            return _trim_no_dots(text, 480)

    points = [_clean_public_text(str(p)) for p in article.get("key_points", []) if str(p).strip()]
    if points:
        return _trim_no_dots(" ".join(points[:3]), 480)

    return _trim_no_dots(summary.summary or summary.headline or "AI update.", 480)


def _pick_digest_eyebrow(article: dict[str, Any], summary: "EmailSummary") -> str:
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
