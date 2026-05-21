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
POSTING_SLOTS = ("08:00", "14:00", "18:00", "22:00")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATERMARK_CANDIDATES = [PROJECT_ROOT / "GR watermark.png", PROJECT_ROOT / "GR Watermark.png", PROJECT_ROOT / "GR watermark.svg"]
FINAL_LOGO_CANDIDATES = [PROJECT_ROOT / "GR INSTA LOGO.png", PROJECT_ROOT / "GRInstaLogo.png", PROJECT_ROOT / "GR INSTA LOGO.svg"]
ARTICLE_ASSET_DIR = PROJECT_ROOT / "data" / "article_assets"
REFERENCE_IMAGE_DIR = ARTICLE_ASSET_DIR / "reference_images"
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
    "advertising partners",
    "show you ads",
    "cookie settings",
    "accept all cookies",
    "reject all cookies",
    "build software better",
    "read every piece of feedback",
    "gitHub is where people build software".lower(),
    "more than 150 million people",
    "contribute to over 420 million projects",
    "get tips, technical guides, and best practices",
    "sign up for",
    "subscribe to",
)


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
) -> list[Path]:
    """Create Instagram carousel batches.

    A single-story summary produces one 4-slide post. A digest summary with
    multiple article_items is split into carousel parts of up to three stories
    each because the Instagram publishing API commonly caps carousel children at
    10 media items: 3 stories * 3 slides + one CTA slide.
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
    if len(articles) <= 3:
        return [summary]
    chunks = [articles[index : index + 3] for index in range(0, len(articles), 3)]
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
    for article_index, article in enumerate(articles[:3], start=1):
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
        first_half, second_half = _split_narrative_for_two_pages(narrative)
        if not second_half:
            second_half = _fallback_story_second_page(summary, article)

        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - WHAT HAPPENED",
                "title": headline,
                "body": _tighten(first_half, 820),
                "supporting": _supporting_note(summary, article, article_index, "Why this matters", variant="why"),
                "image_path": "",
                "topic": topic,
                "url": article.get("url", ""),
            }
        )
        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - NEXT",
                "title": "What to watch next",
                "body": _tighten(second_half, 780),
                "supporting": _supporting_note(summary, article, article_index, "Watch this angle", variant="watch"),
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
    # Large fonts for full-page text coverage with minimal whitespace
    font_eyebrow = _font(ImageFont, 22, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])
    font_title = _font(ImageFont, 50, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"])
    font_body = _font(ImageFont, 34, bold=False, preferred=["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    font_meta = _font(ImageFont, 22, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])
    font_cta = _font(ImageFont, 42, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
    font_brand = _font(ImageFont, 108, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])

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
        _draw_centered_text(draw, slide["eyebrow"], (170, 86, 910, 132), font_eyebrow, ACCENT_GREEN, 1)
        title_box = (120, 152, 960, 336)
        # Draw the title top-aligned to avoid large vertical centering gaps
        _draw_top_centered_text_block(draw, slide.get("title", ""), title_box, font_title, TEXT_WHITE, max_lines=2)
        body_box = (120, 340, 960, 880)
        _draw_left_text_block(
            draw,
            slide["body"],
            box=body_box,
            font=font_body,
            fill=SOFT_WHITE,
            line_gap=6,
            max_lines=11,
        )
        supporting = str(slide.get("supporting", "")).strip()
        if supporting:
            support_box = (160, 900, 920, 1168)
            draw.rounded_rectangle(support_box, radius=28, outline=ACCENT_GREEN, width=2, fill="#0B0B0B")
            _draw_centered_text_block(
                draw,
                supporting,
                box=(190, 930, 890, 1136),
                font=_font(ImageFont, 30, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf"]),
                fill=TEXT_WHITE,
                line_gap=12,
                max_lines=6,
            )
        draw.rounded_rectangle((180, 1240, 900, 1254), radius=3, fill=ACCENT_GREEN)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1262, 630, 1300), font_meta, SOFT_WHITE, 1)

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
    for key in ("image_path", "image_url", "thumbnail", "thumbnail_url"):
        value = str(article.get(key, "") or "").strip()
        if value:
            return value
    return _find_reference_image_for_article(article, topic) or ""


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


def _compose_article_narrative(summary: EmailSummary, article: dict[str, Any]) -> str:
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
    points = [point for point in points if point and point.lower() not in primary.lower()]
    narrative = primary
    if points:
        narrative = f"{primary} Key details: {' '.join(points[:5])}"
    if title and title.lower() not in narrative.lower():
        narrative = f"{title}. {narrative}"
    return _tighten(re.sub(r"\s+", " ", narrative).strip(), 1500)


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
    query = _reference_image_query(article, topic)
    if not query:
        return None
    cache_key = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        cached = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
        if cached.exists():
            return str(cached)
    image_url = _search_wikimedia_image(query)
    if not image_url:
        return None
    return _download_reference_image(image_url, cache_key)


def _reference_image_query(article: dict[str, Any], topic: str) -> str:
    title = _strip_decorative_symbols(str(article.get("title") or "")).strip()
    source = _source_label_from_url(str(article.get("url") or ""))
    parts = [title, topic, source]
    query = " ".join(part for part in parts if part)
    query = re.sub(r"\b(update|launch|announces|announced|new|latest|story)\b", " ", query, flags=re.I)
    query = re.sub(r"[^A-Za-z0-9 .&+-]+", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return _tighten(query, 120)


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
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if width < 500 or height < 350:
            continue
        if any(term in title for term in ("logo", "icon", "symbol", "seal", "flag")) and not _query_looks_like_company(query):
            continue
        return image_url
    return None


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
    REFERENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    dest = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
    dest.write_bytes(data)
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
    keywords = _keywords(summary)
    hashtags = " ".join(f"#{_hashtag(word)}" for word in keywords[:12])
    article = (_article_items(summary) or [{}])[0]
    lead = _clean_public_text(
        str(article.get("description") or article.get("excerpt") or summary.summary)
    )
    cleaned_points = _clean_public_points(summary.key_points, summary.headline, lead)
    if not cleaned_points:
        cleaned_points = _fallback_public_points(summary)
    lead = lead or _fallback_summary_text(summary, summary.headline or summary.subject or "")
    lead = _dedupe_lead_text(lead, summary.headline or summary.subject or "")
    if not lead or re.sub(r"\s+", " ", lead).strip().lower() == re.sub(r"\s+", " ", (summary.headline or summary.subject or "")).strip().lower():
        lead = _fallback_summary_text(summary, summary.headline or summary.subject or "")
    lines = [
        _tighten(summary.headline or summary.subject or "AI news", 120),
        "",
        _tighten(lead, 420),
        "",
        "Built from the linked article shared in today's AI news email.",
        "",
        "Quick takeaways:",
        *[f"- {_tighten(point, 150)}" for point in cleaned_points[:4]],
        "",
        "Disclaimer: This is an AI-assisted summary of the email brief.",
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
    text = re.sub(
        r"\b(?:We use essential cookies|We and our advertising partners|Cookie settings|Accept all cookies|Reject all cookies)\b.*?(?=(?:\s+[A-Z][a-z]|\s*$))",
        " ",
        text,
        flags=re.I,
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
    companies = ", ".join(_clean_entity_list(summary.companies)[:3])
    topics = ", ".join(summary.topics[:3])
    title = _tighten(_clean_public_text(str(article.get("title") or summary.headline or "AI update")), 72)
    parts = [
        f"Story focus: {title}." if title else "",
        f"Teams to watch: {companies}." if companies else "",
        f"Theme: {topics}." if topics else "",
    ]
    return " ".join(part for part in parts if part) or "Watch adoption signals, developer feedback, and the next release milestone."


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
    points = [_clean_public_text(str(point)) for point in article.get("key_points", []) if str(point).strip()]
    points = [point for point in points if point]
    topics = ", ".join(summary.topics[:3]) or "AI product updates"
    article_title = _tighten(_clean_public_text(str(article.get("title") or summary.headline or summary.subject or "AI update")), 72)
    if variant == "why":
        detail = points[1] if len(points) > 1 else points[0] if points else f"This matters because it changes the practical AI tooling story around {topics}."
        return f"{heading}\n\n{_tighten(detail, 180)}"
    detail = points[2] if len(points) > 2 else f"Watch adoption, developer feedback, and follow-up releases around {article_title}."
    return f"{heading}\n\n{_tighten(detail, 180)}"


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
