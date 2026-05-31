"""Unified article-to-carousel slide specification builder."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .ig_constants import MAX_ARTICLES_PER_POST, MAX_CAROUSEL_SLIDES, MAX_KP_PER_SLIDE
from .editorial_page import build_editorial_page_copy
from .ig_copy import is_public_safe_text, layout_safe_headline, layout_safe_points
from .ig_image import _fetch_og_image_from_url, _select_unique_article_image
from .ig_keypoints import _extract_instagram_key_points
from .ig_utils import (
    _article_items,
    _clean_headline,
    _clean_public_text,
    _scrape_article_images,
    _scrape_article_text,
    _source_label_from_url,
)

if TYPE_CHECKING:
    from .models import EmailSummary


def _pick_bg_theme_from_text(text: str) -> str:
    text = (text or "").lower()
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
    combined = " ".join([
        " ".join(summary.topics or []),
        " ".join(summary.companies or []),
        " ".join(summary.models or []),
        str(summary.headline or ""),
        str(summary.subject or ""),
    ])
    return _pick_bg_theme_from_text(combined)


def _pick_bg_theme(slide: dict[str, Any]) -> str:
    if slide.get("bg_theme"):
        return str(slide["bg_theme"])
    return _pick_bg_theme_from_text(" ".join([
        str(slide.get("eyebrow", "")),
        str(slide.get("title", "")),
        str(slide.get("body", "")),
        str(slide.get("topic", "")),
    ]))


def build_part_summary(
    template: "EmailSummary",
    chunk: list[dict[str, Any]],
    part_number: int,
    total_parts: int,
) -> "EmailSummary":
    """Build one carousel-part EmailSummary from a group of article dicts.

    Shared by ``_split_summary_for_carousels`` (legacy single-email split) and
    ``post_planner`` (exactly-8 cross-email planning).
    """
    from .models import EmailSummary as _EmailSummary

    first = chunk[0]
    base_headline = _clean_headline(template.headline or template.subject or "AI Update")
    headline = (
        f"{base_headline} - Part {part_number} of {total_parts}"
        if total_parts > 1 else base_headline
    )
    part = _EmailSummary(
        message_key=f"{template.message_key}:batch:{part_number}",
        subject=template.subject,
        source_date=template.source_date,
        headline=headline,
        summary=template.summary,
        key_points=template.key_points,
        companies=template.companies,
        models=template.models,
        topics=template.topics,
        confidence=template.confidence,
        article_url=str(first.get("url", "")),
        article_title=str(first.get("title", "")),
        article_image_path=str(first.get("image_path", "")),
        article_image_url=str(first.get("image_url", "")),
        article_excerpt=str(first.get("excerpt") or first.get("description") or ""),
        article_items=chunk,
    )
    object.__setattr__(part, "_carousel_part", part_number)
    object.__setattr__(part, "_carousel_total_parts", total_parts)
    return part


def _split_summary_for_carousels(summary: "EmailSummary") -> list["EmailSummary"]:
    """Split a single email into sequential article batches of up to 8.

    Legacy/standalone splitter. The production path uses ``post_planner`` which
    enforces *exactly* 8 and carries remainders across runs. Kept for the
    single-summary fallback and unit tests.
    """
    articles = _article_items(summary)
    if not articles:
        return [summary]

    chunks = [
        articles[index: index + MAX_ARTICLES_PER_POST]
        for index in range(0, len(articles), MAX_ARTICLES_PER_POST)
    ]
    total_parts = len(chunks)
    return [
        build_part_summary(summary, chunk, part_number, total_parts)
        for part_number, chunk in enumerate(chunks, start=1)
    ]


def _build_slide_specs(
    summary: "EmailSummary",
    email_dt: datetime,
    initial_used_paths: set[str] | None = None,
    initial_used_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one image/key-point slide per article plus a final CTA slide."""
    articles = _article_items(summary)
    if not articles:
        slides = _build_fallback_single_slide(summary, initial_used_paths)
    else:
        slides = _build_article_slides(summary, articles[:MAX_CAROUSEL_SLIDES], initial_used_paths, initial_used_urls)
        if not slides:
            slides = _build_fallback_single_slide(summary, initial_used_paths)
    slides.append(_make_cta_slide(len(slides) + 1))
    return slides


def _build_fallback_single_slide(
    summary: "EmailSummary",
    initial_used_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    headline_raw = _clean_headline(
        _clean_public_text(str(summary.headline or summary.subject or "AI Update"))
    ) or "AI Update"
    headline = layout_safe_headline(headline_raw, fallback="AI Update")
    synthetic_article = {
        "title": headline,
        "url": str(summary.article_url or ""),
        "description": summary.article_excerpt or summary.summary or "",
        "image_path": getattr(summary, "article_image_path", None) or "",
        "image_url": getattr(summary, "article_image_url", None) or "",
    }
    points = _extract_instagram_key_points(synthetic_article, summary, max_points=MAX_KP_PER_SLIDE)
    if not points:
        points = layout_safe_points([_clean_public_text(summary.summary or headline)], limit=MAX_KP_PER_SLIDE)
    return [_article_to_slide(summary, synthetic_article, 1, points, set(), set(initial_used_paths or ()))]


def _build_article_slides(
    summary: "EmailSummary",
    articles: list[dict[str, Any]],
    initial_used_paths: set[str] | None = None,
    initial_used_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    used_image_urls: set[str] = set(initial_used_urls or ())
    used_image_paths: set[str] = set(initial_used_paths or ())
    used_image_hashes: list = []
    used_key_fingerprints: set[str] = set()
    slides: list[dict[str, Any]] = []
    skipped_no_img = 0

    for article_index, raw_article in enumerate(articles, start=1):
        article = dict(raw_article)
        url = str(article.get("url") or "")
        if url and not article.get("scraped_content"):
            scraped = _scrape_article_text(url)
            if scraped:
                article["scraped_content"] = scraped
        if url:
            # Always attempt OG image extraction from the article URL,
            # regardless of cached image_url/image_path from prior runs.
            img_url = _fetch_og_image_from_url(url)
            if not img_url:
                img_url = _scrape_article_images(url)
            if img_url:
                article["image_url"] = img_url
                article["image_path"] = ""  # invalidate cached fallback path
            # Prevent _select_unique_article_image from making a redundant HTTP request.
            article["_og_scraped"] = True

        points = _extract_instagram_key_points(
            article,
            summary,
            max_points=MAX_KP_PER_SLIDE,
            used_fingerprints=used_key_fingerprints,
        )
        if not points and not _article_has_publishable_seed(article):
            continue

        # Attempt to get the article image. If no image can be resolved,
        # skip this slide rather than killing the entire carousel.
        image_path = _select_unique_article_image(article, ", ".join(summary.topics[:2]) or "", used_image_urls, used_image_paths, used_image_hashes)
        if not image_path:
            skipped_no_img += 1
            print(f"  [slides] SKIPPED article {article_index} ({article.get('title', '')[:50]}): no article image could be resolved")
            continue

        slide = _article_to_slide_with_image(
            summary, article, article_index, points,
            image_path, used_image_urls, used_image_paths, used_image_hashes,
        )
        slides.append(slide)

    if skipped_no_img > 0:
        print(f"  [slides] Skipped {skipped_no_img} article(s) with unresolvable images; {len(slides)} slide(s) built")
    return slides


def _article_to_slide_with_image(
    summary: "EmailSummary",
    article: dict[str, Any],
    article_index: int,
    points: list[str],
    image_path: str,
    used_image_urls: set[str],
    used_image_paths: set[str],
    used_image_hashes: list | None = None,
) -> dict[str, Any]:
    """Build a slide dict from an article that already has a resolved image."""
    headline_raw = _clean_headline(
        _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
    ) or "AI Update"
    headline = layout_safe_headline(headline_raw, fallback=str(summary.headline or "AI Update"))
    topic = ", ".join(summary.topics[:2]) or headline
    url = str(article.get("url") or "")
    editorial = build_editorial_page_copy(article, summary, points)
    key_points = [str(point) for point in editorial["key_points"]]

    return {
        "kind": "digest",
        "slide_index": article_index,
        "eyebrow": _pick_article_eyebrow(article, summary),
        "title": str(editorial["heading"] or headline),
        "summary_lines": list(editorial["summary_lines"]),
        "key_points": key_points,
        "body": "\n".join(key_points[:MAX_KP_PER_SLIDE]),
        "image_path": image_path,
        "image_source": str(article.get("image_source", "")) if image_path else "",
        "article_image_url": str(article.get("image_url") or ""),
        "topic": topic,
        "url": url,
        "source_label": _source_label_from_url(url),
        "bg_theme": _pick_bg_theme_from_summary(summary),
    }


def _article_to_slide(
    summary: "EmailSummary",
    article: dict[str, Any],
    article_index: int,
    points: list[str],
    used_image_urls: set[str],
    used_image_paths: set[str],
    used_image_hashes: list | None = None,
) -> dict[str, Any]:
    headline_raw = _clean_headline(
        _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
    ) or "AI Update"
    headline = layout_safe_headline(headline_raw, fallback=str(summary.headline or "AI Update"))
    topic = ", ".join(summary.topics[:2]) or headline
    url = str(article.get("url") or "")
    image_path = _select_unique_article_image(article, topic, used_image_urls, used_image_paths, used_image_hashes)
    editorial = build_editorial_page_copy(article, summary, points)
    key_points = [str(point) for point in editorial["key_points"]]

    return {
        "kind": "digest",
        "slide_index": article_index,
        "eyebrow": _pick_article_eyebrow(article, summary),
        "title": str(editorial["heading"] or headline),
        "summary_lines": list(editorial["summary_lines"]),
        "key_points": key_points,
        "body": "\n".join(key_points[:MAX_KP_PER_SLIDE]),
        "image_path": image_path,
        "image_source": str(article.get("image_source", "")) if image_path else "",
        "article_image_url": str(article.get("image_url") or ""),
        "topic": topic,
        "url": url,
        "source_label": _source_label_from_url(url),
        "bg_theme": _pick_bg_theme_from_summary(summary),
    }


def _pick_article_eyebrow(article: dict[str, Any], summary: "EmailSummary") -> str:
    rules = {
        "RESEARCH": ("paper", "research", "arxiv", "study", "benchmark", "dataset"),
        "BREAKING": ("breaking", "just announced", "just released", "today"),
        "INDUSTRY": ("funding", "acquisition", "valuation", "ipo", "revenue", "partnership"),
        "POLICY": ("regulation", "policy", "law", "ban", "government", "eu", "senate"),
        "TOOLS": ("api", "sdk", "tool", "plugin", "open-source", "github", "developer"),
        "DATA": ("benchmark", "performance", "statistic", "report", "survey"),
        "DEEP DIVE": ("how it works", "architecture", "technical", "explained"),
    }
    combined = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        " ".join(summary.topics),
    ]).lower()
    for label, keywords in rules.items():
        if any(keyword in combined for keyword in keywords):
            return label
    return "AI NEWS"


def _article_has_publishable_seed(article: dict[str, Any]) -> bool:
    fields = (
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        str(article.get("excerpt") or ""),
        str(article.get("summary") or ""),
        str(article.get("what_happened") or ""),
    )
    return any(is_public_safe_text(_clean_public_text(field)) for field in fields)


def _make_cta_slide(slide_index: int) -> dict[str, Any]:
    """Create the final call-to-action slide appended to every carousel."""
    return {
        "kind": "cta",
        "slide_index": slide_index,
        "eyebrow": "NEXT BRIEFING",
        "title": "FOLLOW @graitech",
        "body": "Save this carousel. Share it with your team. Get the next AI briefing delivered to your feed.",
        "image_path": "",
        "url": "",
        "source_label": "graitech.io",
        "bg_theme": "default",
    }
