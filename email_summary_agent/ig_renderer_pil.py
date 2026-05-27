"""ig_renderer_pil.py — PIL-based slide renderer for the Instagram pipeline.

This module contains the full graitech Design System PIL renderer used as the
fallback when the primary Playwright renderer (renderer.py) is unavailable.
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .ig_constants import (
    ACCENT_GREEN,
    ASH_GRAY,
    CANVAS_H,
    CANVAS_W,
    FINAL_LOGO_CANDIDATES,
    FONT_MIN_READABLE,
    FONTS_DIR,
    GRAITECH_LOGO_PATH,
    GT_CEMENT_2,
    GT_IRON,
    NEON_RGB,
    PAGE_BLACK,
    REFERENCE_BRANDS,
    SOFT_WHITE,
    TEXT_WHITE,
    WATERMARK_CANDIDATES,
    IMAGE_MIN_HD_W,
    IMAGE_MIN_HD_H,
    _BG_THEMES,
)
from .ig_utils import _clean_headline, _clean_public_text
from .ig_image import _resolve_image_source
from .ig_copy import layout_safe_headline, layout_safe_points


# ─────────────────────────────────────────────────────────────────────────────
# Font loader
# ─────────────────────────────────────────────────────────────────────────────

def _font(image_font, size: int, bold: bool = False, mono: bool = False,
          preferred: list[str] | None = None, display: bool = False):
    """Load a font from the graitech Design System.

    Font roles (matching graitech brand spec):
    - display=True  → Anton SC  (tall condensed all-caps headlines)
    - mono/body     → Space Mono (body, eyebrows, meta, labels)
    Falls back to system/bundled fonts when the graitech assets aren't present.
    """
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

    if preferred:
        for p in preferred:
            try:
                return image_font.truetype(p, size=size)
            except OSError:
                pass

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


# ─────────────────────────────────────────────────────────────────────────────
# Text wrapping
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_to_width(draw, text: str, font, width: int, max_lines: int) -> list[str]:
    """Word-wrap text to fit within `width` pixels, returning at most `max_lines`."""
    lines, _ = _wrap_to_width_overflow(draw, text, font, width, max_lines)
    return lines


def _wrap_to_width_overflow(draw, text: str, font, width: int, max_lines: int) -> tuple[list[str], str]:
    """Like _wrap_to_width but also returns leftover text that didn't fit."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive typography helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    """Return the largest font that fits `text` inside box_width × box_height."""
    from PIL import Image as _PIL_Image, ImageDraw as _PIL_Draw
    effective_min = max(size_min, FONT_MIN_READABLE)
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

    Returns (last_y, overflow_text).
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


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers
# ─────────────────────────────────────────────────────────────────────────────

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
    """Draw body text centered horizontally, top-aligned vertically within the box."""
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


def _paste_contained(base_image, artwork, box: tuple[int, int, int, int], radius: int, pad: int = 24, cover: bool = False) -> None:
    from PIL import Image, ImageDraw, ImageOps

    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    inner_width = max(1, width - pad * 2)
    inner_height = max(1, height - pad * 2)
    if cover:
        fitted = ImageOps.fit(artwork, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
    else:
        fitted = ImageOps.contain(artwork, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    layer = Image.new("RGBA", (width, height), PAGE_BLACK)
    offset_x = pad + (inner_width - fitted.width) // 2
    offset_y = pad + (inner_height - fitted.height) // 2
    layer.paste(fitted, (offset_x, offset_y))
    base_image.paste(layer, (x1, y1), mask)


# ─────────────────────────────────────────────────────────────────────────────
# Artwork loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_artwork(image_path: str, topic: str, box: tuple[int, int, int, int], image_cls, draw_cls, enhance_cls, filter_cls, ops_cls, fallback_text=""):
    path = _resolve_image_source(image_path)
    if path and path.exists():
        try:
            art = image_cls.open(path).convert("RGB")
            art = enhance_cls.Contrast(art).enhance(1.02)
            return art.filter(filter_cls.UnsharpMask(radius=1, percent=80))
        except Exception:
            pass
    if not path:
        x1, y1, x2, y2 = box
        w, h = max(1, x2 - x1), max(1, y2 - y1)
        img = image_cls.new("RGB", (w, h), (4, 8, 14))
        d = draw_cls.Draw(img, "RGBA")
        for y in range(h):
            alpha = y / max(1, h - 1)
            r = int(4 + 8 * alpha)
            g = int(8 + 18 * alpha)
            b = int(14 + 28 * alpha)
            d.line((0, y, w, y), fill=(r, g, b, 255))
        for gx in range(0, w, 90):
            d.line((gx, 0, gx, h), fill=(57, 255, 20, 18))
        for gy in range(0, h, 90):
            d.line((0, gy, w, gy), fill=(255, 255, 255, 12))
        return img
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
    """Generate a self-contained abstract illustration with heading text overlay."""
    from PIL import ImageFont

    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return None
    if w > 2000 or h > 2000:
        w, h = min(w, 2000), min(h, 2000)

    heading = (text or topic or "AI").strip()[:200]

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

    try:
        fs = max(24, min(w, h) // 14)
        font = _font(ImageFont, fs, bold=True)
        mw = w - 80
        words_list = heading.split()
        lines, cur = [], ""
        for word in words_list:
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


# ─────────────────────────────────────────────────────────────────────────────
# Background renderers
# ─────────────────────────────────────────────────────────────────────────────

def _gt_draw_background(image, draw) -> None:
    """Render the graitech concrete-textured black background."""
    import random as _rng
    from PIL import Image as _Img, ImageFilter as _IF
    draw.rectangle((0, 0, CANVAS_W, CANVAS_H), fill=(0, 0, 0, 255))
    rng = _rng.Random(7331)
    for y in range(0, CANVAS_H, 2):
        for x in range(0, CANVAS_W, 2):
            if rng.random() < 0.055:
                a = rng.randint(3, 7)
                draw.point((x, y), fill=(255, 255, 255, a))
    for y in range(0, CANVAS_H, 5):
        for x in range(0, CANVAS_W, 5):
            if rng.random() < 0.07:
                a = rng.randint(4, 10)
                draw.point((x, y), fill=(200, 200, 200, a))
    for y in range(0, CANVAS_H, 11):
        for x in range(0, CANVAS_W, 11):
            if rng.random() < 0.04:
                a = rng.randint(2, 6)
                draw.point((x, y), fill=(255, 255, 255, a))
    for y in range(0, CANVAS_H, 4):
        draw.line((0, y, CANVAS_W, y), fill=(0, 0, 0, 18))
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


def _draw_background_grid(draw) -> None:
    """Legacy function kept for backward compatibility."""
    _draw_dynamic_background(draw, {})


def _draw_dynamic_background(draw, slide: dict[str, Any]) -> None:
    """Fill the slide canvas with a solid black background."""
    draw.rectangle((0, 0, CANVAS_W, CANVAS_H), fill=(5, 5, 5, 255))


# ─────────────────────────────────────────────────────────────────────────────
# graitech chrome (logo + handle + page indicator)
# ─────────────────────────────────────────────────────────────────────────────

def _gt_draw_chrome(image, draw, ImageFont, slide_number: int, total_slides: int, slide_kind: str = "") -> None:
    """Draw fixed chrome elements on every slide."""
    TICK = 20
    TICK_C = (58, 58, 58, 200)
    draw.line((75, 215, 75 + TICK, 215), fill=TICK_C, width=2)
    draw.line((75, 215, 75, 215 + TICK), fill=TICK_C, width=2)
    draw.line((1005 - TICK, 215, 1005, 215), fill=TICK_C, width=2)
    draw.line((1005, 215, 1005, 215 + TICK), fill=TICK_C, width=2)
    draw.line((75, 1195 - TICK, 75, 1195), fill=TICK_C, width=2)
    draw.line((75, 1195, 75 + TICK, 1195), fill=TICK_C, width=2)
    draw.line((1005, 1195 - TICK, 1005, 1195), fill=TICK_C, width=2)
    draw.line((1005 - TICK, 1195, 1005, 1195), fill=TICK_C, width=2)

    logo_size = 78
    logo_right = 44
    logo_top = 34
    pill_pad = 10
    lx = CANVAS_W - logo_right - logo_size
    ly = logo_top
    draw.rounded_rectangle(
        (lx - pill_pad, ly - pill_pad, lx + logo_size + pill_pad, ly + logo_size + pill_pad),
        radius=12, fill=(0, 0, 0, 190),
    )
    _gt_draw_logo(image, right=logo_right, top=logo_top, size=logo_size)

    font_handle = _font(ImageFont, 24, bold=True, mono=True)
    dot_x, dot_y = 56, CANVAS_H - 56 - 24
    draw.ellipse((dot_x, dot_y + 6, dot_x + 10, dot_y + 16), fill=NEON_RGB + (255,))
    draw.text((dot_x + 18, dot_y), "@graitech", fill=TEXT_WHITE, font=font_handle)

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


def _gt_draw_rule(draw, x: int, y: int) -> int:
    """Draw a 96×3px neon rule with soft glow. Returns y after rule."""
    RULE_W = 96
    RULE_H = 3
    for offset in range(6, 0, -1):
        a = max(0, 50 - offset * 8)
        draw.rectangle(
            (x - offset, y - 1, x + RULE_W + offset, y + RULE_H + 1),
            fill=(57, 255, 20, a)
        )
    draw.rectangle((x, y, x + RULE_W, y + RULE_H), fill=(57, 255, 20, 255))
    return y + RULE_H


def _gt_draw_eyebrow(draw, ImageFont, text: str, x: int, y: int) -> int:
    """Draw eyebrow text in neon green Space Mono Bold. Returns y after eyebrow."""
    font = _font(ImageFont, 26, bold=True, mono=True)
    draw.text((x, y), text.upper(), fill=ACCENT_GREEN, font=font)
    try:
        bh = draw.textbbox((0, 0), text, font=font)[3]
    except Exception:
        bh = 22
    return y + bh


# ─────────────────────────────────────────────────────────────────────────────
# Slide renderers
# ─────────────────────────────────────────────────────────────────────────────

def _gt_render_list_slide_bullets_only(
    draw, image_font, body_text: str,
    x1: int, y1: int, x2: int, y2: int,
) -> None:
    """Render bullet-point list text into a bounding box."""
    bullets = [b.strip() for b in body_text.split("\n") if b.strip()]
    bullets = layout_safe_points(bullets, limit=5)
    if not bullets:
        return
    content_w = x2 - x1 - 24
    avail_h = y2 - y1
    chosen_size = 25
    for fsz in (31, 29, 27, 25):
        font_bp = _font(image_font, fsz, mono=True)
        bold_bp = _font(image_font, fsz, bold=True, mono=True)
        total = 0
        for bp in bullets:
            text = bp.lstrip("• ").strip()
            lines = _wrap_highlighted_lines(draw, text, font_bp, bold_bp, content_w, max_lines=4)
            try:
                lh = draw.textbbox((0, 0), "Ag", font=font_bp)[3]
            except Exception:
                lh = fsz
            total += len(lines) * (lh + 5) + 14
        if total <= avail_h:
            chosen_size = fsz
            break
    font_bp = _font(image_font, chosen_size, mono=True)
    bold_bp = _font(image_font, chosen_size, bold=True, mono=True)
    y = y1
    for bullet in bullets:
        text = bullet.lstrip("• ").strip()
        if not text or y >= y2 - 30:
            break
        bp_lines = _wrap_highlighted_lines(draw, text, font_bp, bold_bp, content_w, max_lines=4)
        try:
            lh = draw.textbbox((0, 0), "Ag", font_bp)[3]
        except Exception:
            lh = chosen_size
        dot_cy = y + lh // 2
        draw.ellipse((x1, dot_cy - 4, x1 + 8, dot_cy + 4), fill=(57, 255, 20, 255))
        tx = x1 + 18
        for line_tokens in bp_lines:
            if y >= y2 - 10:
                break
            _draw_highlighted_line(draw, line_tokens, tx, y, font_bp, bold_bp)
            y += lh + 6
        y += 14


def _keyword_is_neon(token: str) -> bool:
    word = token.strip().strip(".,;:!?\"'()[]{}")
    if not word or len(word) <= 1:
        return False
    if re.match(r"^[\$]?\d[\d,.]*(?:B|M|K|bn|mn|%|x)?$", word, re.I):
        return True
    if word in {"AI", "API", "LLM", "ML", "GPU", "CPU", "SDK", "RAG", "GPT"}:
        return True
    if word in REFERENCE_BRANDS or word.lower() in {brand.lower() for brand in REFERENCE_BRANDS}:
        return True
    return word.lower() in {
        "hidden", "shocking", "critical", "dangerous", "proven", "massive",
        "unexpected", "powerful", "released", "launches", "ships", "raises",
        "hits", "breaks", "reveals", "changes", "unlocks", "watch", "signal",
        "developers", "agents", "models", "workflow", "workflows",
    }


def _wrap_highlighted_lines(draw, text: str, font, bold_font, width: int, max_lines: int) -> list[list[str]]:
    tokens = re.findall(r"\S+\s*", re.sub(r"\s+", " ", text or "").strip())
    lines: list[list[str]] = []
    current: list[str] = []
    current_w = 0.0
    for token in tokens:
        token_font = bold_font if _keyword_is_neon(token) else font
        token_w = draw.textlength(token, font=token_font)
        if current and current_w + token_w > width:
            lines.append(current)
            current = [token]
            current_w = token_w
            if len(lines) >= max_lines:
                return lines
        else:
            current.append(token)
            current_w += token_w
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def _draw_highlighted_line(draw, tokens: list[str], x: int, y: int, font, bold_font) -> None:
    cursor = x
    for token in tokens:
        is_neon = _keyword_is_neon(token)
        token_font = bold_font if is_neon else font
        draw.text((cursor, y), token, fill=ACCENT_GREEN if is_neon else SOFT_WHITE, font=token_font)
        cursor += draw.textlength(token, font=token_font)


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
    """Render a digest carousel slide (1080 × 1350 px)."""
    margin = 54
    image_box = (margin, 112, CANVAS_W - margin, 560)

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

    font_eyebrow = _font(image_font, 30, bold=True, mono=True)
    eyebrow = str(slide.get("eyebrow", "AI NEWS")).upper()
    eyebrow_clean = re.sub(r"[^\x00-\x7F]+", "", eyebrow).strip()
    if not eyebrow_clean:
        eyebrow_clean = "AI NEWS"
    draw.text((margin, 586), eyebrow_clean, fill=ACCENT_GREEN, font=font_eyebrow)

    _gt_draw_rule(draw, margin, 614)

    headline = layout_safe_headline(
        _clean_headline(str(slide.get("title", "AI Update"))) or "AI Update",
        fallback="AI Update",
    ).upper()
    headline_box = (margin, 640, CANVAS_W - margin, 808)
    _draw_autofit_text(
        draw, headline, headline_box, image_font,
        fill=TEXT_WHITE, bold=False, size_max=72, size_min=32, max_lines=3, align="left",
        display=True,
    )

    body_text = str(slide.get("body", "")).strip()
    if body_text:
        body_box = (margin, 820, CANVAS_W - margin, 1238)
        is_bullets = "\n" in body_text or body_text.startswith("•") or "\n•" in body_text
        if is_bullets:
            _gt_render_list_slide_bullets_only(draw, image_font, body_text, margin, 820, CANVAS_W - margin, 1238)
        else:
            _draw_autofit_text(
                draw, body_text, body_box, image_font,
                fill=SOFT_WHITE, bold=False, size_max=36, size_min=FONT_MIN_READABLE, max_lines=7, align="left",
            )

    source = str(slide.get("source_label", "")).strip()
    if source:
        font_source = _font(image_font, 18, mono=True)
        draw.text(
            (margin, 1246),
            f"SOURCE: {source.upper()}",
            fill=(200, 200, 200, 255),
            font=font_source,
        )


def _gt_render_title_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide: dict) -> None:
    """Render a graitech title slide (kind="title")."""
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80

    y = SAFE_T
    y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "FIELD NOTES"), SAFE_L, y)
    y += 16
    y = _gt_draw_rule(draw, SAFE_L, y) + 24

    headline = (slide.get("title") or "AI UPDATE").upper()
    content_w = SAFE_R - SAFE_L
    font_display = _font(ImageFont, 120, display=True)
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

    subtitle = (slide.get("body") or "").strip()
    if subtitle and y < 920:
        font_body = _font(ImageFont, 36, bold=False, mono=True)
        sub_lines = _wrap_to_width(draw, subtitle, font_body, content_w, max_lines=4)
        for sline in sub_lines:
            if y + 36 > 950:
                break
            draw.text((SAFE_L, y), sline, fill=SOFT_WHITE, font=font_body)
            y += 36

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
            draw.rounded_rectangle(img_box, radius=16, outline=(57, 255, 20, 100), width=1)

    source = (slide.get("source_label") or "").strip()
    if source:
        font_src = _font(ImageFont, 26, mono=True)
        draw.text((SAFE_L, 1155), f"SOURCE: {source.upper()}", fill=(200, 200, 200, 255), font=font_src)


def _gt_render_list_slide(draw, ImageFont, slide: dict) -> None:
    """Render a graitech list slide (kind="list")."""
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80

    y = SAFE_T
    y = _gt_draw_eyebrow(draw, ImageFont, slide.get("eyebrow", "INSIGHTS"), SAFE_L, y)
    y += 16
    y = _gt_draw_rule(draw, SAFE_L, y) + 24

    headline = (slide.get("title") or "").upper()
    if headline:
        font_sec = _font(ImageFont, 52, display=True)
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

    body_raw = (slide.get("body") or "").strip()
    bullets = [b.strip() for b in body_raw.split("\n") if b.strip()]
    if not bullets:
        return

    avail_h = 1185 - y
    font_sizes_to_try = [46, 42, 38, 34]
    BULLET_GAP = 36
    LINE_GAP = 12
    content_w = SAFE_R - SAFE_L - 30

    chosen_size = 28
    for fsz in font_sizes_to_try:
        font_bp = _font(ImageFont, fsz, mono=True)
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
        dot_cy = y + lh // 2
        draw.ellipse((SAFE_L, dot_cy - 5, SAFE_L + 10, dot_cy + 5), fill=(57, 255, 20, 255))
        text_x = SAFE_L + 22
        for line in bp_lines:
            if y >= 1170:
                break
            draw.text((text_x, y), line, fill=SOFT_WHITE, font=font_bp)
            y += lh + LINE_GAP
        y += BULLET_GAP


def _gt_render_cta_slide(image, draw, ImageFont, slide: dict) -> None:
    """Render a graitech CTA slide (kind="cta")."""
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80

    font_stamp = _font(ImageFont, 18, bold=True, mono=True)
    stamp_text = "END / DISPATCH"
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
    draw.ellipse((SAFE_L + 14, SAFE_T + sh // 2 - 5, SAFE_L + 24, SAFE_T + sh // 2 + 5),
                 fill=(57, 255, 20, 255))
    draw.text((SAFE_L + 30, SAFE_T + (sh - 18) // 2), stamp_text,
              fill=ACCENT_GREEN, font=font_stamp)

    y = SAFE_T + sh + 32
    y = _gt_draw_eyebrow(draw, ImageFont, "TAKE IT WITH YOU", SAFE_L, y)
    y += 16
    y = _gt_draw_rule(draw, SAFE_L, y) + 28

    cta_lines = ["SAVE THIS.", "STEAL THIS.", "SHARE IT."]
    font_cta_big = _font(ImageFont, 160, display=True)
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


def _gt_render_legacy_slide(image, draw, ImageFont, Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, slide: dict) -> None:
    """Render old-format slides using the graitech visual language as a base."""
    SAFE_L, SAFE_T = 80, 235
    SAFE_R = CANVAS_W - 80
    content_w = SAFE_R - SAFE_L

    y = SAFE_T
    kind = slide.get("kind", "")

    if kind == "image":
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
        kp_text = str(slide.get("body", ""))
        bullet_slide = dict(slide, kind="list",
                            body="\n".join(f"•  {kp_text}".split("\n")))
        _gt_render_list_slide(draw, ImageFont, bullet_slide)

    else:
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
            body_lines = body.split("\n")
            font_b = _font(ImageFont, 30, mono=True)
            for bline in body_lines:
                if y > 1170:
                    break
                draw.text((SAFE_L, y), bline, fill=SOFT_WHITE, font=font_b)
                try:
                    y += draw.textbbox((0, 0), bline, font=font_b)[3] + 10
                except Exception:
                    y += 38


# ─────────────────────────────────────────────────────────────────────────────
# Image quality and QA helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate_image_hd(path: str) -> bool:
    """Return True when the image at `path` meets the minimum HD resolution."""
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
    """Programmatically inspect a rendered PNG slide for common quality issues."""
    issues: list[str] = []
    try:
        from PIL import Image as _PIL
        img = _PIL.open(path).convert("RGB")
        w, h = img.size

        if w != CANVAS_W or h != CANVAS_H:
            issues.append(f"Wrong dimensions {w}×{h} (expected {CANVAS_W}×{CANVAS_H})")

        pixels = list(img.getdata())
        sample = pixels[::max(1, len(pixels) // 400)]
        unique_colours = len(set(sample))
        if unique_colours < 8:
            issues.append("Slide appears blank — too few unique colours")

        bright = sum(1 for r, g, b in sample if max(r, g, b) > 160)
        if bright < 5:
            issues.append("Slide too dark — no bright text or accent pixels detected")

    except Exception as exc:
        issues.append(f"QA could not read slide: {exc}")

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Legacy / misc helpers
# ─────────────────────────────────────────────────────────────────────────────

def _draw_accent_frame(draw) -> None:
    """Legacy accent frame — no-op in new design."""
    pass


def _draw_slide_chip(draw, text: str, box: tuple[int, int, int, int], font, fill: str, outline) -> None:
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
    draw.line((cx - 34, cy + 28, cx + 38, cy - 30, cx + 12, cy + 38, cx + 2, cy + 8, cx - 34, cy + 28), fill=ACCENT_GREEN, width=5)


def _draw_save_icon(draw, cx: int, cy: int) -> None:
    draw.line((cx - 28, cy - 34, cx + 28, cy - 34, cx + 28, cy + 36, cx, cy + 14, cx - 28, cy + 36, cx - 28, cy - 34), fill=ACCENT_GREEN, width=5)


def _draw_watermark_overlay(base_image) -> None:
    """Legacy watermark — no-op in the graitech design."""
    pass


def _draw_handle_overlay(draw, image_font) -> None:
    """Draw the @graitech handle at bottom-left."""
    font = _font(image_font, 24, bold=True, mono=True)
    handle = "@graitech"
    try:
        bbox = draw.textbbox((0, 0), handle, font=font)
        th = bbox[3] - bbox[1]
    except Exception:
        th = 24
    x, y = 56, CANVAS_H - 56 - th
    draw.ellipse((x, y + th // 2 - 5, x + 10, y + th // 2 + 5), fill=(57, 255, 20, 255))
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


# ─────────────────────────────────────────────────────────────────────────────
# Main slide writer (entry point)
# ─────────────────────────────────────────────────────────────────────────────

def _write_slide_png(path: Path, slide_number: int, total_slides: int, slide: dict[str, Any], email_dt: datetime) -> None:
    """Render a single carousel slide using the graitech Design System.

    Delegates to the Playwright-based HTML renderer in renderer.py, which
    injects article content into the official Graitech HTML templates and
    screenshots the result at 1080×1350 px.  Falls back to the legacy PIL
    renderer only if Playwright is unavailable.
    """
    try:
        from .renderer import render_slide_to_png
        render_slide_to_png(path, slide, slide_number, total_slides, email_dt)
        return
    except Exception as _pw_err:
        print(f"[renderer] Playwright render failed for {path.name}: {_pw_err}  — falling back to PIL", flush=True)

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
