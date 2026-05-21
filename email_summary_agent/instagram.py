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
MAX_CAROUSEL_SLIDES = 10
STORIES_PER_CAROUSEL = 2
POSTING_SLOTS = ("08:00", "14:00", "18:00", "22:00")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATERMARK_CANDIDATES = [PROJECT_ROOT / "GR watermark.png", PROJECT_ROOT / "GR Watermark.png", PROJECT_ROOT / "GR watermark.svg"]
FINAL_LOGO_CANDIDATES = [PROJECT_ROOT / "GR INSTA LOGO.png", PROJECT_ROOT / "GRInstaLogo.png", PROJECT_ROOT / "GR INSTA LOGO.svg"]
ARTICLE_ASSET_DIR = PROJECT_ROOT / "data" / "article_assets"
REFERENCE_IMAGE_DIR = ARTICLE_ASSET_DIR / "reference_images"
# Shared image library — all downloaded images land here for reuse across posts
IMAGE_LIBRARY_DIR = PROJECT_ROOT / "data" / "images"
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


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
) -> list[Path]:
    """Create Instagram carousel batches.

    A single-story summary produces one image slide, three content slides, and
    one CTA slide. Digest summaries are split into parts of up to two stories
    each because Instagram caps carousel children at 10 media items:
    2 stories * 4 slides + one CTA slide.
    """
    if not summaries:
        return []
    if clear_existing:
        _cleanup_existing_outputs(output_dir)

    now = generated_at or datetime.now(timezone.utc).astimezone()
    batch_dir = output_dir / now.strftime("%Y%m%d-%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

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
            for slide_number, slide in enumerate(slides, start=1):
                _write_slide_png(
                    carousel_dir / f"slide_{slide_number:02d}.png",
                    slide_number=slide_number,
                    total_slides=len(slides),
                    slide=slide,
                    email_dt=email_dt,
                )

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


def _split_summary_for_carousels(summary: EmailSummary) -> list[EmailSummary]:
    articles = _article_items(summary)
    if len(articles) <= STORIES_PER_CAROUSEL:
        return [summary]
    chunks = [articles[index : index + STORIES_PER_CAROUSEL] for index in range(0, len(articles), STORIES_PER_CAROUSEL)]
    parts: list[EmailSummary] = []
    for part_number, chunk in enumerate(chunks, start=1):
        headline = f"{_tighten(summary.headline or summary.subject or 'Daily AI Digest', 88)} - Part {part_number}"
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
        object.__setattr__(part, "_carousel_total_parts", len(chunks))
        parts.append(part)
    return parts


def _build_slide_specs(summary: EmailSummary, email_dt: datetime) -> list[dict[str, Any]]:
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
    for article_index, article in enumerate(articles[:STORIES_PER_CAROUSEL], start=1):
        headline = _tighten(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update"))
            or _tighten(summary.headline or summary.subject or "AI update", 88),
            88,
        )
        topic = ", ".join(summary.topics[:2]) or headline
        image_path = _select_article_image(article, topic)
        slides.append(
            {
                "kind": "image",
                "eyebrow": f"STORY {article_index:02d}",
                "title": headline,
                "body": "",
                "image_path": image_path,
                "topic": topic,
                "url": article.get("url", ""),
            }
        )

        narrative = _compose_article_narrative(summary, article)
        content_pages = _split_narrative_for_content_pages(narrative)
        while len(content_pages) < 2:
            content_pages.append(_fallback_story_page(summary, article, len(content_pages) + 1))

        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - WHAT HAPPENED",
                "title": headline,
                "body": _tighten(content_pages[0], 620),
                "supporting": _supporting_note(summary, article, article_index, "Why this matters", variant="why"),
                "image_path": "",
                "topic": topic,
                "url": article.get("url", ""),
            }
        )
        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - WHY IT MATTERS",
                "title": "Why it matters",
                "body": _tighten(content_pages[1], 620),
                "supporting": _supporting_note(summary, article, article_index, "The bigger signal", variant="signal"),
                "image_path": "",
                "topic": topic,
                "url": article.get("url", ""),
            }
        )
        if len(content_pages) >= 3:
            slides.append(
                {
                    "kind": "text",
                    "eyebrow": f"STORY {article_index:02d} - WATCH NEXT",
                    "title": "What to watch next",
                    "body": _tighten(content_pages[2], 620),
                    "supporting": _supporting_note(summary, article, article_index, "Watch this next", variant="watch"),
                    "image_path": "",
                    "topic": topic,
                    "url": article.get("url", ""),
                }
            )

    slides.append(
        {
            "kind": "cta",
            "eyebrow": "GRAITECH",
            "title": "Follow for the next AI briefing",
            "body": "LIKE | COMMENT | FOLLOW | SAVE",
            "image_path": "",
        }
    )

    return slides[:MAX_CAROUSEL_SLIDES]


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

    _draw_background_grid(draw)

    margin = 72
    if slide["kind"] == "image":
        image_box = (margin, 150, CANVAS_W - margin, 1070)
        artwork = _load_artwork(
            slide.get("image_path", ""),
            slide.get("topic", "AI"),
            image_box,
            Image,
            ImageDraw,
            ImageEnhance,
            ImageFilter,
            ImageOps,
        )
        if artwork is not None:
            artwork = ImageEnhance.Color(artwork).enhance(0.90)
            artwork = ImageEnhance.Contrast(artwork).enhance(1.05)
            # Paste artwork with minimal padding to display the full image without cropping.
            _paste_contained(image, artwork, image_box, radius=36, pad=6, cover=False)
            draw.rounded_rectangle(image_box, radius=36, outline=ACCENT_GREEN, width=2)
        else:
            _draw_no_image_story_card(
                draw,
                slide.get("eyebrow", "STORY"),
                slide.get("title", "AI update"),
                slide.get("url", ""),
                image_box,
                font_eyebrow,
                font_title,
                font_body,
                font_meta,
            )
    elif slide["kind"] == "cta":
        draw.rounded_rectangle((margin, 92, CANVAS_W - margin, 1258), radius=46, fill="#0B0B0B", outline="#1F1F1F", width=2)
        _draw_centered_text(draw, "GRAITECH", (140, 150, 940, 240), font_brand, ACCENT_GREEN, 1)
        _draw_centered_text(draw, "Instagram-ready AI news", (140, 278, 940, 365), font_title, TEXT_WHITE, 1)
        _draw_social_icons(draw, (140, 410, 940, 540), font_meta)
        _draw_centered_logo_panel(image, (240, 575, 840, 945))
        _draw_centered_text(draw, "Save this post for your next AI briefing.", (130, 1000, 950, 1080), font_body, TEXT_WHITE, 1)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1120, 630, 1170), font_meta, ACCENT_GREEN, 1)
    else:
        _draw_centered_text(draw, slide["eyebrow"], (110, 74, 970, 130), font_eyebrow, ACCENT_GREEN, 1)
        title_box = (110, 148, 970, 330)
        _draw_top_centered_text_block(draw, slide.get("title", ""), title_box, font_title, TEXT_WHITE, max_lines=2)

        # Dark container behind body text — readable over the background grid
        body_container = (64, 336, CANVAS_W - 64, 900)
        draw.rounded_rectangle(body_container, radius=24, fill=(8, 8, 8, 230))

        body_box = (100, 358, 980, 886)
        _draw_left_text_block(
            draw,
            slide["body"],
            box=body_box,
            font=font_body,
            fill=SOFT_WHITE,
            line_gap=12,
            max_lines=11,
        )
        supporting = str(slide.get("supporting", "")).strip()
        if supporting:
            support_box = (100, 908, 980, 1200)
            draw.rounded_rectangle(support_box, radius=28, outline=ACCENT_GREEN, width=2, fill="#0A0A0A")
            font_support = _font(ImageFont, 34, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
            _draw_centered_text_block(
                draw,
                supporting,
                box=(130, 936, 950, 1172),
                font=font_support,
                fill=TEXT_WHITE,
                line_gap=14,
                max_lines=5,
            )
        draw.rounded_rectangle((160, 1248, 920, 1262), radius=3, fill=ACCENT_GREEN)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1270, 630, 1310), font_meta, SOFT_WHITE, 1)

    path.parent.mkdir(parents=True, exist_ok=True)
    _draw_watermark_overlay(image)
    image.save(path, "PNG", optimize=True)


def _draw_background_grid(draw) -> None:
    draw.rectangle((0, 0, CANVAS_W, CANVAS_H), fill=PAGE_BLACK)
    for x in range(0, CANVAS_W, 110):
        draw.line((x, 0, x, CANVAS_H), fill=(200, 255, 0, 12), width=1)
    for y in range(0, CANVAS_H, 110):
        draw.line((0, y, CANVAS_W, y), fill=(200, 255, 0, 12), width=1)
    draw.rounded_rectangle((28, 28, 1052, 1322), radius=42, outline=(255, 255, 255, 20), width=2)


def _draw_header(draw, font_meta, font_page, slide_number: int, total_slides: int, email_dt: datetime) -> None:
    draw.text((72, 78), "AI SIGNAL DAILY", fill=TEXT_WHITE, font=font_meta)
    draw.text((72, 120), email_dt.strftime("%d %b %Y - %H:%M"), fill=SOFT_WHITE, font=font_meta)
    page = f"{slide_number:02d}/{total_slides:02d}"
    bbox = draw.textbbox((0, 0), page, font=font_page)
    draw.text((1008 - (bbox[2] - bbox[0]), 86), page, fill=ACCENT_GREEN, font=font_page)


def _draw_text_box(draw, text: str, box: tuple[int, int, int, int], font, fill: str, line_gap: int, max_lines: int) -> int:
    x1, y1, x2, y2 = box
    lines = _wrap_to_width(draw, text, font, x2 - x1, max_lines)
    y = y1
    for line in lines:
        if y > y2:
            break
        draw.text((x1, y), line, fill=fill, font=font)
        bbox = draw.textbbox((x1, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


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


def _draw_single_line(draw, text: str, xy: tuple[int, int], font, fill: str, max_chars: int) -> None:
    draw.text(xy, _tighten(text, max_chars), fill=fill, font=font)


def _wrap_to_width(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    words = re.sub(r"\s+", " ", text or "").strip().split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = _tighten(lines[-1], max(10, len(lines[-1]) - 3))
    return lines or [""]


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


def _draw_left_text_block(draw, text: str, box: tuple[int, int, int, int], font, fill: str, line_gap: int, max_lines: int) -> int:
    """Draw left-aligned text block starting at the top-left of the box."""
    x1, y1, x2, y2 = box
    width = x2 - x1
    lines = _wrap_to_width(draw, text, font, width, max_lines)
    y = y1
    for line in lines:
        if y > y2:
            break
        draw.text((x1, y), line, fill=fill, font=font)
        bbox = draw.textbbox((x1, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _select_article_image(article: dict[str, Any], topic: str) -> str:
    """Smart image selection pipeline:
    1. Use the image extracted directly from the blog/article (best relevance)
    2. Check the shared data/images library for a previously downloaded relevant image
    3. Search Wikimedia Commons for a relevant image and save it to the library
    4. Fall back to a reference image from the brand/topic cache
    """
    title = str(article.get("title") or "")
    url = str(article.get("url") or "")

    # 1. Blog/article image — most relevant, already downloaded by enricher
    for key in ("image_path", "image_url"):
        value = str(article.get(key, "") or "").strip()
        if value:
            # If it's a URL, download it to the library and return the local path
            if value.startswith(("http://", "https://")):
                local = _download_to_library(value, title or topic)
                if local:
                    return local
            else:
                path = Path(value)
                if path.exists():
                    return value

    # 2. Check the shared image library for a relevant cached image
    library_match = _find_library_image(title or topic)
    if library_match:
        return library_match

    # 3. Search the web for a relevant image and save to library
    web_image = _find_reference_image_for_article(article, topic)
    if web_image:
        return web_image

    return ""


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
    meta.write_text(json.dumps({"url": url, "seed": seed_text}, ensure_ascii=True), encoding="utf-8")
    return str(dest)


def _find_library_image(query: str) -> str | None:
    """Search the data/images library for an image relevant to the query."""
    if not IMAGE_LIBRARY_DIR.exists():
        return None
    query_tokens = set(re.findall(r"[A-Za-z]{4,}", query.lower()))
    if not query_tokens:
        return None
    best_path: str | None = None
    best_score = 0
    for meta_file in IMAGE_LIBRARY_DIR.glob("*.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        seed = str(meta.get("seed", "")).lower()
        seed_tokens = set(re.findall(r"[A-Za-z]{4,}", seed))
        score = len(query_tokens & seed_tokens)
        if score > best_score:
            # Find the matching image file
            stem = meta_file.stem
            for suffix in (".jpg", ".jpeg", ".png", ".webp"):
                candidate = IMAGE_LIBRARY_DIR / f"{stem}{suffix}"
                if candidate.exists():
                    best_score = score
                    best_path = str(candidate)
                    break
    # Only return if there's a meaningful match (at least 2 tokens in common)
    return best_path if best_score >= 2 else None


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


def _split_narrative_for_two_pages(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ("", "")
    sentences = re.split(r"(?<=[\.\!\?])\s+", text)
    first_parts: list[str] = []
    second_parts: list[str] = []
    for sentence in sentences:
        candidate = " ".join(first_parts + [sentence]).strip()
        if len(candidate) <= 620 or not first_parts:
            first_parts.append(sentence)
        else:
            second_parts.append(sentence)
    first = " ".join(first_parts).strip()
    second = " ".join(second_parts).strip()
    if not second and len(first) > 420:
        midpoint = max(1, len(first) // 2)
        split_at = first.rfind(" ", 0, midpoint)
        if split_at == -1:
            split_at = midpoint
        second = first[split_at:].strip()
        first = first[:split_at].strip()
    return _tighten(first, 680), _tighten(second, 650)


def _split_narrative_for_content_pages(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    if len(text) <= 1040:
        return _split_narrative_for_page_count(text, page_count=2, target_chars=520)
    return _split_narrative_for_page_count(text, page_count=3, target_chars=520)


def _split_narrative_for_three_pages(text: str) -> list[str]:
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


def _fetch_unsplash_for_topic(topic: str, width: int, height: int) -> str | None:
    try:
        # Use high-quality parameter and add orientation for better images
        clean_topic = re.sub(r"[^a-zA-Z0-9 ]+", " ", topic or "technology").strip() or "technology"
        query = urllib.parse.quote_plus(clean_topic)
        # Use Unsplash's featured endpoint for high-quality curated images
        url = f"https://source.unsplash.com/1200x1200/?{query},professional,high-quality"
        tmp_dir = Path(tempfile.gettempdir()) / "ai_news_instagram"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_dir / f"{_slugify(topic)}_{width}x{height}_{int(datetime.now().timestamp())}.jpg"
        _download_url(url, dest)
        return str(dest)
    except Exception:
        return None


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
            downloaded = _download_reference_image(image_url, cache_key)
            if downloaded:
                return downloaded
    return None


def _reference_image_queries(article: dict[str, Any], topic: str) -> list[str]:
    title = _strip_decorative_symbols(str(article.get("title") or "")).strip()
    source = _source_label_from_url(str(article.get("url") or ""))
    raw_candidates = [
        title,
        *_brand_queries(title),
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


def _download_reference_image(image_url: str, cache_key: str) -> str | None:
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
    return str(dest)


def _query_looks_like_company(query: str) -> bool:
    lowered = query.lower()
    return any(company.lower() in lowered for company in ("openai", "google", "microsoft", "meta", "amazon", "aws", "nvidia", "anthropic"))


def _pick_local_article_asset(seed_text: str) -> Path | None:
    if not ARTICLE_ASSET_DIR.exists():
        return None
    candidates = [path for path in ARTICLE_ASSET_DIR.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".img"}]
    if not candidates:
        return None
    index = abs(hash(seed_text or "ai-news")) % len(candidates)
    return candidates[index]


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


def _split_text_into_sections(text: str, approx_chars: int = 380) -> list[str]:
    # Split by paragraphs first, then fall back to sentence boundaries.
    if not text:
        return [""]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text.strip()]
    sections: list[str] = []
    for para in paras:
        if len(para) <= approx_chars:
            sections.append(para)
        else:
            # split long paragraph into sentence-like chunks
            parts = re.split(r"(?<=[\.\!\?])\s+", para)
            current = ""
            for part in parts:
                if not current:
                    current = part
                elif len(current) + 1 + len(part) <= approx_chars:
                    current = current + " " + part
                else:
                    sections.append(current.strip())
                    current = part
            if current:
                sections.append(current.strip())
    # Ensure we don't exceed reasonable slide count
    if len(sections) > (MAX_CAROUSEL_SLIDES - 2):
        # merge trailing sections
        combined = " ".join(sections[(MAX_CAROUSEL_SLIDES - 3):])
        sections = sections[: (MAX_CAROUSEL_SLIDES - 3)] + [combined]
    return sections or [text.strip()]


def _build_caption(summary: EmailSummary) -> str:
    """Build a fully unique caption for each carousel post.

    Every field — lead text, takeaways, hashtags, and the closing line —
    is derived from *this* summary's article content so no two posts share
    the same body even when they come from the same email digest.
    """
    article = (_article_items(summary) or [{}])[0]

    # ── Lead paragraph ────────────────────────────────────────────────────────
    lead = _clean_public_text(
        str(article.get("description") or article.get("excerpt") or summary.summary or "")
    )
    lead = _dedupe_lead_text(lead, summary.headline or summary.subject or "")
    if not lead or re.sub(r"\s+", " ", lead).strip().lower() == re.sub(r"\s+", " ", (summary.headline or summary.subject or "")).strip().lower():
        lead = _fallback_summary_text(summary, summary.headline or summary.subject or "")
    lead = _tighten(lead, 420)

    # ── Takeaway bullets — pulled from this article's key_points only ─────────
    cleaned_points = _clean_public_points(summary.key_points, summary.headline or "", lead)
    if not cleaned_points:
        cleaned_points = _fallback_public_points(summary)
    # Use article-specific points, not shared digest points
    article_points = [_clean_public_text(str(p)) for p in article.get("key_points", []) if str(p).strip()]
    article_points = [p for p in article_points if p and len(p) > 20]
    if article_points:
        # Merge article-specific points first, then fall back to summary points
        merged: list[str] = []
        seen_keys: set[str] = set()
        for p in [*article_points, *cleaned_points]:
            key = re.sub(r"\s+", " ", p).strip().lower()[:80]
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(p)
        cleaned_points = merged
    bullets = [f"- {_tighten(point, 150)}" for point in cleaned_points[:4]]

    # ── Hashtags — unique per post based on this article's entities ───────────
    keywords = _keywords(summary)
    # Add article-specific title words as extra tags
    article_title = str(article.get("title") or summary.headline or "")
    title_words = [w for w in re.findall(r"[A-Za-z]{4,}", article_title) if w.lower() not in {"with", "that", "this", "from", "into", "over", "your", "their", "have", "been", "will", "also", "more", "than", "when", "what", "about"}]
    extra_tags = [w for w in title_words[:4] if w not in keywords]
    all_keywords = keywords + extra_tags
    hashtags = " ".join(f"#{_hashtag(word)}" for word in all_keywords[:14])

    # ── Closing line — unique per article ─────────────────────────────────────
    source_domain = _source_label_from_url(str(article.get("url") or summary.article_url or ""))
    if source_domain:
        closing = f"Source: {source_domain} | Curated by Graitech AI."
    elif summary.companies:
        closing = f"Covering {summary.companies[0]} and the latest in AI. Curated by Graitech."
    else:
        closing = "AI news curated and summarised by Graitech."

    lines = [
        _tighten(summary.headline or summary.subject or "AI news", 120),
        "",
        lead,
        "",
        "Key takeaways:",
        *bullets,
        "",
        closing,
        "",
        hashtags,
    ]
    return "\n".join(line for line in lines if line is not None).strip() + "\n"


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


def _fallback_story_second_page(summary: EmailSummary, article: dict[str, Any]) -> str:
    return _fallback_story_page(summary, article, 3)


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


def _signal_line(summary: EmailSummary) -> str:
    parts = []
    if summary.companies:
        parts.append(f"Companies: {', '.join(summary.companies[:2])}")
    if summary.models:
        parts.append(f"Models: {', '.join(summary.models[:2])}")
    if summary.topics:
        parts.append(f"Topics: {', '.join(summary.topics[:2])}")
    return " | ".join(parts)


def _takeaway_title(index: int, summary: EmailSummary, point: str) -> str:
    if index == 1 and summary.companies:
        return summary.companies[0]
    if index == 2 and summary.models:
        return summary.models[0]
    return f"Takeaway {index}"


def _takeaway_support(summary: EmailSummary, index: int) -> str:
    if summary.topics:
        return f"Focus: {', '.join(summary.topics[:2])}."
    return f"Key point {index} pulled from the email summary."


def _watch_title(summary: EmailSummary) -> str:
    if summary.topics:
        return _tighten(f"Watch: {summary.topics[0]}", 72)
    if summary.companies:
        return _tighten(f"Watch: {summary.companies[0]}", 72)
    return "What to watch next"


def _first_image(articles: list[dict[str, Any]]) -> str:
    for article in articles:
        image_path = article.get("image_path", "")
        if image_path:
            return image_path
    return ""


def _recap_text(summary: EmailSummary, articles: list[dict[str, Any]]) -> str:
    if articles:
        titles = [article.get("title", "") for article in articles[:3] if article.get("title")]
        return "This email points to " + "; ".join(titles) + ". The common thread: " + (", ".join(summary.topics[:3]) or "AI industry movement") + "."
    return " ".join(summary.key_points[:3]) or summary.summary


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


def _derive_story_points(text: str, summary: EmailSummary) -> list[str]:
    text = _clean_public_text(text)
    if not text:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[\.!?])\s+", text) if part.strip()]
    points: list[str] = []
    for sentence in sentences:
        if len(sentence) < 40:
            continue
        points.append(_tighten(sentence, 160))
        if len(points) >= 3:
            break
    if points:
        return points
    return _fallback_public_points(summary)
