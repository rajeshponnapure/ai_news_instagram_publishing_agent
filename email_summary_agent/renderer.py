"""
Graitech Design System â€” HTML-to-PNG slide renderer.

Renders Instagram carousel slides (1080Ã—1350 px) by injecting article content
into the official Graitech HTML templates and screenshotting them with
Playwright Chromium. Guarantees pixel-perfect fidelity to the design system â€”
fonts, concrete texture, neon accents, corner ticks â€” with no PIL pixel-pushing.
"""
from __future__ import annotations

import base64
import html as _html
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .ig_copy import layout_safe_headline, layout_safe_points

# â”€â”€ asset paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ASSETS = Path(__file__).parent / "assets" / "graitech"
_FONTS = _ASSETS / "fonts"
_LOCAL_FONTS = Path(__file__).parent / "fonts"
_IMG = _ASSETS / "assets"

CANVAS_W = 1080
CANVAS_H = 1350


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Public API
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def render_slide_to_png(
    path: Path,
    slide: dict[str, Any],
    slide_number: int,
    total_slides: int,
    email_dt: datetime,
) -> None:
    """Render *slide* to a 1080Ã—1350 PNG at *path* using Playwright."""
    html_src = _build_slide_html(slide, slide_number, total_slides, email_dt)
    _screenshot_html(html_src, path)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HTML builder
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _build_slide_html(slide, slide_number, total_slides, email_dt):
    kind = slide.get("kind", "")
    if kind == "title":
        body = _title_body(slide, email_dt)
    elif kind == "list":
        body = _list_body(slide)
    elif kind == "cta":
        body = _cta_body(slide)
    elif kind == "digest":
        body = _digest_body(slide)
    else:
        body = _list_body(slide)   # safe fallback
    return _wrap_in_shell(body, slide_number, total_slides, kind)


def _wrap_in_shell(body, slide_number, total_slides, slide_kind=""):
    css = _inline_css()
    logo = _data_uri(_IMG / "graitech-logo.png", "image/png")
    # For digest slides the article image occupies y 110â€“470px.  Placing the logo
    # at top:56px (the default) puts it right on top of that image.  Move it to
    # Logo always anchored to top-right corner on every slide kind.
    logo_style = "top:56px; right:56px;"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>{css}</style></head><body>
<article class="ig">
  <div class="ticks"><i></i></div>
  <div class="ig__logo" style="{logo_style}"><img src="{logo}" alt="graitech"></div>
{body}
  <div class="ig__handle"><span class="dot"></span>@graitech</div>
  <div class="ig__page">
    <span class="bar"></span>
    <span><span class="num">{slide_number:02d}</span> / {total_slides:02d}</span>
    <span class="bar"></span>
  </div>
</article>
</body></html>"""


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Slide kinds
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _title_body(slide, email_dt):
    eyebrow = _e(slide.get("eyebrow") or email_dt.strftime("AI News â€” %b %Y"))
    headline = _e(slide.get("title") or "AI Update")
    subtitle = _e(slide.get("body") or slide.get("subtitle") or "")
    source = _e(slide.get("source_label") or "")
    src_html = f'<div class="source-label">{source}</div>' if source else ""
    lines = _wrap_headline(headline, 13)

    # Article image: render in the lower third of the slide so the headline
    # occupies the visually dominant upper area.  Use a fade-to-black gradient
    # overlay so the image blends into the dark background without clashing
    # with the bottom chrome (handle / page indicator).
    img_css = _image_css(slide.get("image_path") or "")
    img_html = f"""  <div class="title-image" style="background-image:{img_css};"></div>""" if img_css != _FALLBACK_GRADIENT else ""

    return f"""{img_html}
  <div class="ig__content" style="justify-content: space-between;">
    <div class="kicker-row"><span class="stamp">AI Dispatch</span></div>
    <div class="heading-stack">
      <div class="eyebrow">{eyebrow}</div>
      <div class="rule"></div>
      <h1 class="display-block">{lines}</h1>
      <p class="body">{subtitle}</p>
      {src_html}
    </div>
    <div class="swipe-row">Swipe <span class="arrow"></span></div>
  </div>"""


def _list_body(slide):
    eyebrow = _e(slide.get("eyebrow") or "Key Points")
    section = _e(layout_safe_headline(slide.get("title") or slide.get("section") or "AI Update"))
    # Accept either a list or newline-joined string of points
    raw = slide.get("points") or slide.get("key_points") or []
    if not raw and slide.get("body"):
        raw = [ln.lstrip("â€¢â€“â€”- ").strip()
               for ln in str(slide["body"]).splitlines() if ln.strip()]
    safe_points = layout_safe_points([str(pt) for pt in raw], limit=3)
    if not safe_points and section:
        safe_points = layout_safe_points([section], limit=1)
    pts_html = "".join(
        f'      <div class="row"><div><p>{_e(str(pt))}</p></div></div>\n'
        for pt in safe_points
    )
    return f"""  <div class="ig__content" style="gap: 32px;">
    <div class="heading-stack" style="gap: 14px;">
      <div class="eyebrow">{eyebrow}</div>
      <div class="rule"></div>
      <h2 class="display-tall" style="font-size:72px;">{section}</h2>
    </div>
    <div class="ol">
{pts_html}    </div>
  </div>"""


def _digest_body(slide):
    eyebrow = _e(slide.get("eyebrow") or "AI Update")
    headline = _e(slide.get("title") or layout_safe_headline("AI Update", fallback="AI Update"))
    source = _e(slide.get("source_label") or "")
    src_html = f'<div class="source-label" style="margin-top:14px;">{source}</div>' if source else ""
    raw = slide.get("key_points") or []
    body = slide.get("body") or ""
    if not raw and isinstance(body, list):
        raw = body
    elif not raw and body:
        raw = [ln.lstrip("â€¢â€“â€”- ").strip() for ln in str(body).splitlines() if ln.strip()]
    safe_points = layout_safe_points([str(pt) for pt in raw], limit=5)
    if not safe_points and headline:
        safe_points = layout_safe_points([headline], limit=1)

    image_path = str(slide.get("image_path") or "")
    has_image = bool(image_path and Path(image_path).exists())

    # â”€â”€ Dynamic keypoint sizing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Estimate available height for the KP list based on slide type.
    # Non-KP elements on every digest slide:
    #   Eyebrow: 26px font + ~10px line-height overhead â‰ˆ 36px
    #   Rule: 3px + 10+18 margins = 31px
    #   Headline: 56px font + 24px margin â‰ˆ 80px (single line estimate)
    #   Source label: 22px font + 14px margin â‰ˆ 36px
    #   Total non-KP â‰ˆ 183px; round to 190 for safety margin
    NON_KP_HEIGHT = 190

    if has_image:
        # .digest-body top=500px, bottom=140px â†’ 710px total
        total_kp_area = CANVAS_H - 500 - 140 - NON_KP_HEIGHT
    else:
        # .digest-body.no-image top=220px, bottom=140px â†’ 990px total
        total_kp_area = CANVAS_H - 220 - 140 - NON_KP_HEIGHT
    total_kp_area = max(200, total_kp_area)

    n = len(safe_points)
    # Reduce vertical row gap when there are more keypoints to fit
    row_gap = 18 if n <= 4 else (14 if n <= 5 else 10)
    gaps_h = max(0, n - 1) * row_gap
    avail_per_row = (total_kp_area - gaps_h) / max(n, 1)

    # Target font size so text at 3 lines fits within avail_per_row
    text_height_budget = avail_per_row
    target_font = min(30, max(20, int(text_height_budget / (1.34 * 3))))

    # Number font scales proportionally
    target_num = min(31, max(20, target_font + 2))

    pts_html = "".join(
        f'<div class="kp-row">'
        f'<span class="kp-num" style="font-size:{target_num}px;min-width:54px;">{i:02d}</span>'
        f'<span class="kp-text" style="font-size:{target_font}px;">{_highlight_keywords_html(str(pt))}</span></div>\n'
        for i, pt in enumerate(safe_points, 1)
    )

    # Apply dynamic row gap to the kp-list container
    row_gap_css = f"gap:{row_gap}px;"

    img_html = ""
    body_class = "digest-body"
    if has_image:
        img_val = _image_css(image_path)
        img_html = f"""  <div class="digest-image" style="background-image:{img_val}; background-size:cover; background-position:center;"></div>
"""
    else:
        body_class += " no-image"
    return f"""{img_html}  <div class="{body_class}">
    <div class="eyebrow">{eyebrow}</div>
    <div class="rule" style="margin:10px 0 18px;"></div>
    <div class="digest-headline">{headline}</div>
    <div class="kp-list" style="{row_gap_css}">{pts_html}</div>
    {src_html}
  </div>"""


def _cta_body(slide):
    eyebrow = _e(slide.get("eyebrow") or "GRAITECH")
    title = _e(slide.get("title") or "Follow for the next AI briefing")
    body = _e(slide.get("body") or "Like Â· Comment Â· Follow Â· Save")
    return f"""  <div class="ig__content" style="justify-content: space-between;">
    <div class="kicker-row"><span class="stamp">AI Dispatch</span></div>
    <div class="heading-stack">
      <div class="eyebrow">{eyebrow}</div>
      <div class="rule"></div>
      <h2 class="display-tall" style="font-size:150px; line-height:0.92;">{title}</h2>
      <p class="body" style="color:var(--gt-neon); letter-spacing:0.08em; font-size:30px; line-height:1.35;">{body}</p>
    </div>
    <div style="display:flex; gap:32px; align-items:center;">
      <span class="stamp">graitech.io</span>
      <span class="meta">Follow for more</span>
    </div>
  </div>"""


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CSS â€” fully self-contained, no external network calls
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _inline_css():
    anton_r = _font_b64("AntonSC-Regular.ttf")
    space_r = _font_b64("SpaceMono-Regular.ttf")
    space_b = _font_b64("SpaceMono-Bold.ttf")
    tex = _svg_b64(_IMG / "concrete-texture.svg")

    return f"""
@font-face {{font-family:'Anton SC'; src:url('data:font/truetype;base64,{anton_r}') format('truetype'); font-weight:400; font-style:normal;}}
@font-face {{font-family:'Space Mono'; src:url('data:font/truetype;base64,{space_r}') format('truetype'); font-weight:400; font-style:normal;}}
@font-face {{font-family:'Space Mono'; src:url('data:font/truetype;base64,{space_b}') format('truetype'); font-weight:700; font-style:normal;}}

:root {{
  --gt-neon: #39FF14; --gt-neon-glow: rgba(57,255,20,0.45);
  --gt-black: #000; --gt-white: #fff; --gt-chalk: #E8E8E8;
  --gt-ash: #A8A8A8; --gt-cement-2: #3A3A3A;
  --gt-fg-2: #E8E8E8; --gt-fg-3: #A8A8A8;
  --gt-font-display: 'Anton SC', Impact, Arial Black, sans-serif;
  --gt-font-body: 'Space Mono', monospace;
  --gt-font-mono: 'Space Mono', monospace;
}}
html,body{{margin:0;padding:0;background:#000;}}
.ig{{position:relative;width:{CANVAS_W}px;height:{CANVAS_H}px;background:#000;overflow:hidden;isolation:isolate;font-family:var(--gt-font-mono);color:var(--gt-white);}}
.ig::before{{content:"";position:absolute;inset:0;background-image:url('data:image/svg+xml;base64,{tex}');background-size:cover;z-index:0;opacity:0.9;}}
.ig::after{{content:"";position:absolute;inset:0;background-image:linear-gradient(to right,rgba(255,255,255,0.018) 1px,transparent 1px),linear-gradient(to bottom,rgba(255,255,255,0.018) 1px,transparent 1px);background-size:90px 90px;pointer-events:none;z-index:1;mask-image:radial-gradient(ellipse 60% 60% at 50% 50%,transparent 20%,#000 95%);}}
.ig__logo{{position:absolute;top:34px;right:44px;width:84px;height:84px;z-index:10;filter:drop-shadow(0 0 14px rgba(57,255,20,0.25));}}
.ig__logo img{{width:100%;height:100%;display:block;}}
.ig__handle{{position:absolute;bottom:56px;left:56px;z-index:10;display:flex;align-items:center;gap:12px;font-family:var(--gt-font-mono);font-size:26px;font-weight:700;color:var(--gt-white);letter-spacing:0.04em;}}
.ig__handle .dot{{width:10px;height:10px;border-radius:50%;background:var(--gt-neon);box-shadow:0 0 14px var(--gt-neon);}}
.ig__page{{position:absolute;bottom:56px;left:50%;transform:translateX(-50%);z-index:10;font-family:var(--gt-font-mono);font-size:20px;letter-spacing:0.32em;color:var(--gt-fg-3);display:flex;align-items:center;gap:14px;}}
.ig__page .num{{color:var(--gt-neon);font-weight:700;}}
.ig__page .bar{{width:28px;height:1px;background:var(--gt-cement-2);}}
.ig__content{{position:absolute;top:220px;left:80px;right:80px;bottom:160px;z-index:5;display:flex;flex-direction:column;overflow:hidden;}}
.eyebrow{{font-family:var(--gt-font-mono);font-size:26px;font-weight:700;letter-spacing:0.32em;text-transform:uppercase;color:var(--gt-neon);}}
.display-block{{font-family:var(--gt-font-display);font-size:min(136px, 12vw);line-height:1.02;letter-spacing:0;text-transform:none;color:var(--gt-neon);text-shadow:0 0 28px rgba(57,255,20,0.35);margin:0;overflow-wrap:break-word;word-break:break-word;}}
.display-tall{{font-family:var(--gt-font-display);font-size:min(108px, 10vw);line-height:1.02;letter-spacing:0;text-transform:none;color:var(--gt-neon);text-shadow:0 0 22px rgba(57,255,20,0.30);margin:0;overflow-wrap:break-word;word-break:break-word;}}
.body{{font-family:var(--gt-font-body);font-size:34px;line-height:1.48;color:var(--gt-white);max-width:860px;overflow:hidden;}}
.meta{{font-family:var(--gt-font-mono);font-size:20px;letter-spacing:0.18em;text-transform:uppercase;color:var(--gt-fg-3);}}
.rule{{width:96px;height:3px;background:var(--gt-neon);box-shadow:0 0 12px var(--gt-neon-glow);}}
.kicker-row{{display:flex;align-items:center;gap:18px;}}
.stamp{{display:inline-flex;align-items:center;gap:10px;padding:10px 22px;border:1.5px solid var(--gt-neon);color:var(--gt-neon);font-family:var(--gt-font-mono);font-size:20px;font-weight:700;letter-spacing:0.24em;text-transform:uppercase;border-radius:999px;}}
.stamp::before{{content:"";width:8px;height:8px;border-radius:50%;background:var(--gt-neon);box-shadow:0 0 10px var(--gt-neon);}}
.ol{{display:flex;flex-direction:column;gap:24px;counter-reset:g;flex:1;overflow:hidden;}}
.ol .row{{display:grid;grid-template-columns:70px 1fr;gap:16px;align-items:start;counter-increment:g;}}
.ol .row::before{{content:counter(g,decimal-leading-zero);font-family:var(--gt-font-mono);color:var(--gt-neon);font-size:46px;line-height:1;text-shadow:0 0 18px rgba(57,255,20,0.35);}}
.ol .row p{{font-family:var(--gt-font-body);font-size:34px;line-height:1.35;color:var(--gt-fg-2);margin:0;overflow:hidden;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;}}
.heading-stack{{display:flex;flex-direction:column;gap:28px;}}
.swipe-row{{display:flex;align-items:center;gap:20px;font-family:var(--gt-font-mono);font-size:26px;font-weight:700;color:var(--gt-neon);letter-spacing:0.24em;text-transform:uppercase;}}
.swipe-row .arrow{{width:64px;height:2px;background:var(--gt-neon);position:relative;box-shadow:0 0 10px var(--gt-neon-glow);}}
.swipe-row .arrow::after{{content:"";position:absolute;right:-1px;top:50%;width:14px;height:14px;border-top:2px solid var(--gt-neon);border-right:2px solid var(--gt-neon);transform:translateY(-50%) rotate(45deg);}}
.ticks{{position:absolute;inset:190px 56px 140px 56px;pointer-events:none;z-index:2;}}
.ticks::before,.ticks::after,.ticks>i::before,.ticks>i::after{{content:"";position:absolute;width:20px;height:20px;border-color:var(--gt-cement-2);}}
.ticks::before{{top:0;left:0;border-top:1.5px solid;border-left:1.5px solid;}}
.ticks::after{{top:0;right:0;border-top:1.5px solid;border-right:1.5px solid;}}
.ticks>i{{position:absolute;inset:0;}}
.ticks>i::before{{bottom:0;left:0;border-bottom:1.5px solid;border-left:1.5px solid;top:auto;}}
.ticks>i::after{{bottom:0;right:0;border-bottom:1.5px solid;border-right:1.5px solid;top:auto;}}
.source-label{{font-family:var(--gt-font-mono);font-size:22px;letter-spacing:0.18em;text-transform:uppercase;color:var(--gt-ash);margin-top:8px;}}
.digest-image{{position:absolute;top:110px;left:54px;right:54px;height:360px;z-index:3;border-radius:14px;overflow:hidden;}}
.digest-image::after{{content:"";position:absolute;bottom:0;left:0;right:0;height:150px;background:linear-gradient(transparent,#000);}}
.digest-body{{position:absolute;top:500px;left:72px;right:72px;bottom:140px;z-index:5;display:flex;flex-direction:column;overflow:hidden;}}
.digest-body.no-image{{top:220px;}}
.digest-body.no-image .digest-headline{{font-size:68px;line-height:1.04;margin-bottom:24px;}}
.digest-body.no-image .kp-list{{gap:22px;}}
.digest-body.no-image .kp-text{{font-size:33px;line-height:1.34;}}
.digest-headline{{font-family:var(--gt-font-display);font-size:56px;line-height:1.05;color:var(--gt-neon);text-shadow:0 0 22px rgba(57,255,20,0.30);text-transform:none;margin-bottom:24px;letter-spacing:0;overflow-wrap:break-word;word-break:normal;}}
.kp-list{{display:flex;flex-direction:column;gap:18px;flex:1;overflow:hidden;}}
.kp-row{{display:flex;gap:18px;align-items:flex-start;}}
.kp-num{{font-family:var(--gt-font-mono);font-size:31px;line-height:1.2;color:var(--gt-neon);text-shadow:0 0 14px rgba(57,255,20,0.40);min-width:54px;flex-shrink:0;font-weight:700;}}
.kp-text{{font-family:var(--gt-font-body);font-size:30px;line-height:1.34;color:var(--gt-chalk);flex:1;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow-wrap:break-word;word-break:normal;}}
.kp-text strong{{color:var(--gt-neon);font-weight:700;}}
.title-image{{position:absolute;bottom:140px;left:0;right:0;height:380px;z-index:2;background-size:cover;background-position:center top;}}
.title-image::before{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,0.55) 0%,rgba(0,0,0,0) 40%,rgba(0,0,0,0) 60%,rgba(0,0,0,0.85) 100%);z-index:1;}}
"""


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Utility helpers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _e(text):
    return _html.escape(_html.unescape(str(text or "").strip()))


_CAPS_STOPWORDS = frozenset({
    "IS", "OF", "TO", "IN", "AT", "BY", "NO", "SO", "AS", "AN", "OR",
    "BE", "DO", "WE", "IT", "ON", "IF", "UP", "US", "VS", "VIA", "THE",
    "AND", "BUT", "FOR", "HAS", "HAD", "NOT", "ARE", "WAS", "ITS", "ALL",
    "NEW", "ITS", "HOW", "CAN", "ONE", "TWO", "NOW", "OUT", "USE", "GET",
})


def _highlight_keywords_html(text: str) -> str:
    """Return HTML-escaped text with key terms bolded via <strong>.

    Bolds:
    - Numbers with units (50%, $1.2B, 2x, 3bn, etc.)
    - ALL-CAPS acronyms 2-6 chars (AI, ML, LLM, API, GPT, etc.) excluding stopwords
    """
    escaped = _html.escape(str(text or "").strip())
    # Bold numbers with optional units/symbols (e.g. 50%, $1.2B, 2x, 100bn)
    escaped = re.sub(
        r'(\$?\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|x)?)',
        r'<strong>\1</strong>',
        escaped,
        flags=re.IGNORECASE,
    )
    # Bold ALL-CAPS acronyms, skipping common English stop-words

    def _bold_acronym(m: re.Match) -> str:
        word = m.group(0)
        return word if word in _CAPS_STOPWORDS else f"<strong>{word}</strong>"
    escaped = re.sub(r'\b[A-Z]{2,6}\b', _bold_acronym, escaped)
    keyword_re = re.compile(
        r"\b(hidden|shocking|critical|dangerous|proven|massive|unexpected|"
        r"powerful|released|launches|ships|raises|hits|breaks|reveals|"
        r"changes|unlocks|watch|signal|developers|agents|models|workflow|workflows)\b",
        re.I,
    )
    escaped = keyword_re.sub(r"<strong>\1</strong>", escaped)
    return escaped



def _wrap_headline(text, chars=13):
    words = text.split()
    lines, cur, length = [], [], 0
    for w in words:
        if length + len(w) > chars and cur:
            lines.append(" ".join(cur))
            cur, length = [w], len(w)
        else:
            cur.append(w)
            length += len(w) + 1
    if cur:
        lines.append(" ".join(cur))
    return "<br>".join(lines)


def _font_b64(filename):
    p = _LOCAL_FONTS / filename
    if not p.exists():
        p = _FONTS / filename
    return base64.b64encode(p.read_bytes()).decode("ascii") if p.exists() else ""


def _data_uri(path, mime):
    if not path.exists():
        return ""
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _svg_b64(path):
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("ascii")


_FALLBACK_GRADIENT = "linear-gradient(135deg,#0a0a0a 0%,#1a1a1a 50%,#0d0d0d 100%)"


def _image_css(img_path):
    if not img_path:
        return _FALLBACK_GRADIENT
    p = Path(img_path)
    if not p.exists():
        return _FALLBACK_GRADIENT
    file_url = p.absolute().as_uri()
    return f"url('{file_url}')"


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Playwright screenshot
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _screenshot_html(html_src, out_path):
    from playwright.sync_api import sync_playwright
    tmp = out_path.with_suffix(".tmp.html")
    tmp.write_text(html_src, encoding="utf-8")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ])
            page = browser.new_page(viewport={"width": CANVAS_W, "height": CANVAS_H})
            page.goto(tmp.absolute().as_uri(), wait_until="load", timeout=15000)
            page.wait_for_timeout(200)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out_path), full_page=False, type="png")
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)
