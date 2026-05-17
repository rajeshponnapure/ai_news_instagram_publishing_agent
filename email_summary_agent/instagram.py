from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
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
ACCENT_GREEN = "#C8FF00"
PAGE_BLACK = "#050505"
TEXT_WHITE = "#FFFFFF"
SOFT_WHITE = "#D7D7D7"


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
) -> list[Path]:
    """Create one clean, image-led Instagram carousel per email summary."""
    if not summaries:
        return []
    if clear_existing:
        _cleanup_existing_outputs(output_dir)

    now = generated_at or datetime.now(timezone.utc).astimezone()
    batch_dir = output_dir / now.strftime("%Y%m%d-%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

    carousel_dirs: list[Path] = []
    index_rows: list[str] = []
    for index, summary in enumerate(summaries, start=1):
        email_dt = _email_datetime(summary.source_date) or now
        slug = _slugify(summary.headline or summary.subject or f"ai-news-{index}")
        folder_name = f"{index:02d}_{email_dt.strftime('%Y%m%d-%H%M')}_{slug}"
        carousel_dir = batch_dir / folder_name
        carousel_dir.mkdir(parents=True, exist_ok=True)

        slides = _build_slide_specs(summary, email_dt)
        for slide_number, slide in enumerate(slides, start=1):
            _write_slide_png(
                carousel_dir / f"slide_{slide_number:02d}.png",
                slide_number=slide_number,
                total_slides=len(slides),
                slide=slide,
                email_dt=email_dt,
            )

        caption = _build_caption(summary)
        (carousel_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (carousel_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "email_received_at": email_dt.isoformat(timespec="minutes"),
                    "recommended_post_time": POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)],
                    "headline": summary.headline,
                    "subject": summary.subject,
                    "source_date": summary.source_date,
                    "companies": summary.companies,
                    "models": summary.models,
                    "topics": summary.topics,
                    "article_url": summary.article_url,
                    "article_title": summary.article_title,
                    "article_image_path": summary.article_image_path,
                    "article_image_url": summary.article_image_url,
                    "article_items": summary.article_items or [],
                    "slides": [slide["title"] for slide in slides],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        index_rows.append(
            f'<li><a href="{carousel_dir.name}/slide_01.png">{html.escape(summary.headline)}</a> '
            f'<span>{len(slides)} slides - {POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)]}</span></li>'
        )
        carousel_dirs.append(carousel_dir)

    (batch_dir / "index.html").write_text(_render_index(index_rows), encoding="utf-8")
    return carousel_dirs


def _build_slide_specs(summary: EmailSummary, email_dt: datetime) -> list[dict[str, Any]]:
    articles = _article_items(summary)
    if not articles:
        articles = [
            {
                "title": summary.headline or summary.subject or "AI news",
                "description": summary.summary,
                "excerpt": summary.article_excerpt,
                "image_path": summary.article_image_path,
                "image_url": summary.article_image_url,
                "url": summary.article_url,
            }
        ]

    slides: list[dict[str, Any]] = []
    total_articles = min(len(articles), 3)
    for article_index, article in enumerate(articles[:3], start=1):
        title = _tighten(article.get("title") or summary.headline or summary.subject or "AI news", 88)
        topic = ", ".join([part for part in [title, *summary.topics[:2]] if part]) or "AI news"
        image_path = _select_article_image(article, topic)
        slides.append(
            {
                "kind": "image",
                "eyebrow": f"STORY {article_index:02d}",
                "title": title,
                "body": "",
                "image_path": image_path,
                "topic": topic,
                "url": article.get("url", ""),
            }
        )

        narrative = _compose_article_narrative(summary, article)
        first_half, second_half = _split_narrative_for_two_pages(narrative)
        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - PART 1",
                "title": title,
                "body": first_half,
                "supporting": _supporting_note(summary, article, article_index, "Why it matters", variant="why"),
                "image_path": "",
                "topic": topic,
                "url": article.get("url", ""),
            }
        )
        slides.append(
            {
                "kind": "text",
                "eyebrow": f"STORY {article_index:02d} - PART 2",
                "title": "What happens next",
                "body": second_half,
                "supporting": _supporting_note(summary, article, article_index, "What to watch next", variant="watch"),
                "image_path": "",
                "topic": topic,
                "url": article.get("url", ""),
            }
        )

    slides.append(
        {
            "kind": "cta",
            "eyebrow": "GRAITECH",
            "title": "Follow for the next AI drop",
            "body": "Share • comment • follow",
            "image_path": "",
            "topic": "graitech",
        }
    )

    return slides[:MAX_CAROUSEL_SLIDES]


def _write_slide_png(path: Path, slide_number: int, total_slides: int, slide: dict[str, Any], email_dt: datetime) -> None:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

    image = Image.new("RGBA", (CANVAS_W, CANVAS_H), PAGE_BLACK)
    draw = ImageDraw.Draw(image, "RGBA")
    font_eyebrow = _font(ImageFont, 26, bold=True, mono=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/consolab.ttf"])
    font_title = _font(ImageFont, 58, bold=True, preferred=["C:/Windows/Fonts/bahnschrift.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"])
    font_body = _font(ImageFont, 42, bold=False, preferred=["C:/Windows/Fonts/seguisb.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
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
        artwork = ImageEnhance.Color(artwork).enhance(0.90)
        artwork = ImageEnhance.Contrast(artwork).enhance(1.05)
        _paste_contained(image, artwork, image_box, radius=36, pad=24)
        draw.rounded_rectangle(image_box, radius=36, outline=ACCENT_GREEN, width=2)
    elif slide["kind"] == "cta":
        draw.rounded_rectangle((margin, 92, CANVAS_W - margin, 1258), radius=46, fill="#0B0B0B", outline="#1F1F1F", width=2)
        _draw_centered_text(draw, "GRAITECH", (140, 150, 940, 240), font_brand, ACCENT_GREEN, 1)
        _draw_centered_text(draw, "Instagram-ready AI news", (140, 280, 940, 380), font_title, TEXT_WHITE, 1)
        _draw_centered_text(draw, "Share • comment • follow", (160, 400, 920, 470), font_cta, SOFT_WHITE, 1)
        _draw_centered_logo_panel(image, (240, 545, 840, 955))
        _draw_centered_text(draw, "Save this post for your next AI briefing.", (130, 1000, 950, 1080), font_body, TEXT_WHITE, 1)
        _draw_centered_text(draw, f"{slide_number:02d}/{total_slides:02d}", (450, 1120, 630, 1170), font_meta, ACCENT_GREEN, 1)
    else:
        _draw_centered_text(draw, slide["eyebrow"], (170, 86, 910, 132), font_eyebrow, ACCENT_GREEN, 1)
        title_box = (120, 152, 960, 336)
        _draw_centered_text(draw, slide.get("title", ""), title_box, font_title, TEXT_WHITE, 2)
        body_box = (120, 340, 960, 860)
        _draw_centered_text_block(
            draw,
            slide["body"],
            box=body_box,
            font=font_body,
            fill=SOFT_WHITE,
            line_gap=18,
            max_lines=8,
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
    width = box[2] - box[0]
    height = box[3] - box[1]
    path = _resolve_image_source(image_path)
    if path and path.exists():
        try:
            art = image_cls.open(path).convert("RGB")
            art = ops_cls.fit(art, (width, height), method=image_cls.Resampling.LANCZOS)
            art = enhance_cls.Color(art).enhance(0.88)
            art = enhance_cls.Contrast(art).enhance(1.08)
            return art.filter(filter_cls.UnsharpMask(radius=2, percent=110))
        except Exception:
            pass

    # If we don't have a source image, try fetching a royalty-free representative image
    if not path or not path.exists():
        try:
            tmp = _fetch_unsplash_for_topic(topic, width, height)
            if tmp:
                art = image_cls.open(tmp).convert("RGB")
                art = ops_cls.fit(art, (width, height), method=image_cls.Resampling.LANCZOS)
                art = enhance_cls.Color(art).enhance(0.92)
                art = enhance_cls.Contrast(art).enhance(1.04)
                return art.filter(filter_cls.UnsharpMask(radius=1, percent=100))
        except Exception:
            pass

    art = image_cls.new("RGB", (width, height), PAGE_BLACK)
    draw = draw_cls.Draw(art, "RGBA")
    seed = sum(ord(ch) for ch in topic)
    colors = [ACCENT_GREEN, "#FFFFFF", "#4D7CFF", "#17D1B8"]
    for i in range(10):
        x = (seed * (i + 4) * 37) % width
        y = (seed * (i + 6) * 53) % height
        size = 80 + ((seed + i * 29) % 260)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=colors[(seed + i) % len(colors)] + "22")
    for i in range(-height, width, 86):
        draw.line((i, height, i + height, 0), fill=(255, 255, 255, 28), width=3)
    return art.filter(filter_cls.GaussianBlur(radius=0.4))


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
    candidates = []
    if preferred:
        candidates.extend(preferred)
    if mono:
        candidates.extend(["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf"])
    if bold:
        candidates.extend(["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"])
    candidates.extend(["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"])
    for candidate in candidates:
        try:
            return image_font.truetype(candidate, size=size)
        except OSError:
            continue
    return image_font.load_default()


def _paste_contained(base_image, artwork, box: tuple[int, int, int, int], radius: int, pad: int = 24) -> None:
    from PIL import Image, ImageDraw, ImageOps

    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    inner_width = max(1, width - pad * 2)
    inner_height = max(1, height - pad * 2)
    fitted = ImageOps.contain(artwork, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    layer = Image.new("RGBA", (width, height), PAGE_BLACK)
    offset_x = (width - fitted.width) // 2
    offset_y = (height - fitted.height) // 2
    layer.paste(fitted, (offset_x, offset_y))
    base_image.paste(layer, (x1, y1), mask)


def _select_article_image(article: dict[str, Any], topic: str) -> str:
    for key in ("image_path", "image_url", "thumbnail", "thumbnail_url"):
        value = str(article.get(key, "") or "").strip()
        if value:
            return value
    local_asset = _pick_local_article_asset(topic or str(article.get("title", "")))
    if local_asset:
        return str(local_asset)
    return _fetch_unsplash_for_topic(topic, 1080, 1080) or ""


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
    title = str(article.get("title") or summary.headline or summary.subject or "AI update").strip()
    description = str(article.get("description") or article.get("excerpt") or summary.summary or "").strip()
    points = [point.strip() for point in summary.key_points if point.strip()]
    lead = description or summary.summary or ""
    if points:
        lead = lead + "\n\nKey takeaways:\n- " + "\n- ".join(points[:4])
    return f"{title}\n\n{lead}".strip()


def _split_narrative_for_two_pages(text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ("", "")
    sentences = re.split(r"(?<=[\.\!\?])\s+", text)
    if len(sentences) <= 2:
        midpoint = max(1, len(text) // 2)
        split_at = text.rfind(" ", 0, midpoint)
        if split_at == -1:
            split_at = midpoint
        first = text[:split_at].strip()
        second = text[split_at:].strip()
    else:
        half = max(1, len(sentences) // 2)
        first = " ".join(sentences[:half]).strip()
        second = " ".join(sentences[half:]).strip()
    if not first:
        first = text[: max(1, len(text) // 2)].strip()
    if not second:
        second = text[max(1, len(text) // 2):].strip()
    return first, second


def _fetch_unsplash_for_topic(topic: str, width: int, height: int) -> str | None:
    try:
        query = urllib.parse.quote_plus(re.sub(r"[^a-zA-Z0-9 ]+", " ", topic or "technology").strip() or "technology")
        url = f"https://source.unsplash.com/featured/{width}x{height}/?{query}"
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
    hashtags = " ".join(f"#{_hashtag(word)}" for word in keywords[:16])
    article_count = len(_article_items(summary))
    source_line = f"Covered from {article_count} linked story/stories in this email." if article_count else "Covered from this email briefing."
    lines = [
        _tighten(summary.headline, 120),
        "",
        _tighten(summary.summary, 420),
        "",
        source_line,
        "",
        "Quick takeaways:",
        *[f"- {_tighten(point, 150)}" for point in summary.key_points[:4]],
        "",
        "Disclaimer: This post is an AI-assisted news summary. Check the linked source before making business, legal, or investment decisions.",
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
    companies = ", ".join(summary.companies[:3]) or "the named source"
    topics = ", ".join(summary.topics[:3]) or "AI product updates"
    article_title = _tighten(str(article.get("title") or summary.headline or summary.subject or "AI update"), 78)
    lead = _tighten(str(article.get("excerpt") or article.get("description") or summary.summary or ""), 180)
    if variant == "why":
        return f"{heading}\n\n{companies} are the names to watch here.\n{topics} is the theme.\n{lead}"
    # variant == 'watch' or others
    return f"{heading}\n\nNext steps for {article_title}: monitor {topics}.\n{lead}"


def _email_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _keywords(summary: EmailSummary) -> list[str]:
    raw = [*summary.companies, *summary.models, *summary.topics]
    raw.extend(["AI news", "AI tools", "automation", "tech update", "artificial intelligence"])
    seen: set[str] = set()
    keywords: list[str] = []
    for item in raw:
        cleaned = re.sub(r"\s+", " ", item).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
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
