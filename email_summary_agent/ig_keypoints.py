"""ig_keypoints.py — key point extraction and narrative composition for the Instagram pipeline."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .ig_constants import REFERENCE_BRANDS
from .ig_utils import _clean_public_text, _tighten, _trim_no_dots, _fallback_summary_text
from .ig_copy import clean_creator_text, is_public_safe_text, layout_safe_points

if TYPE_CHECKING:
    from .models import EmailSummary


# ─────────────────────────────────────────────────────────────────────────────
# Highlight keyword system
# ─────────────────────────────────────────────────────────────────────────────

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
    if re.match(r"^[\$€£]?\d+[\d,.]*(?:[BMTKbmtk]|bn|mn|%|x|×|th)?$", word):
        return True
    if word in _HIGHLIGHT_ACRONYMS:
        return True
    if word in REFERENCE_BRANDS or word.lower() in {b.lower() for b in REFERENCE_BRANDS}:
        return True
    if word in _HIGHLIGHT_MODELS or word.lower() in {m.lower() for m in _HIGHLIGHT_MODELS}:
        return True
    if word.lower() in _HIGHLIGHT_VERBS:
        return True
    return False


def _draw_keypoint_body_with_highlights(
    draw, text, box, image_font,
    size_max=68, size_min=26, max_lines=8, align="center",
):
    """Draw keypoint body with highlight-worthy words in bold neon green."""
    from .ig_constants import ACCENT_GREEN, TEXT_WHITE
    from .ig_renderer_pil import _auto_fit_font, _font

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


# ─────────────────────────────────────────────────────────────────────────────
# Key point extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_instagram_key_points(
    article: dict[str, Any],
    summary: "EmailSummary",
    max_points: int = 10,
    used_fingerprints: set[str] | None = None,
) -> list[str]:
    """Extract punchy, attention-grabbing key points for Instagram slides.

    Phase 1: Collect candidates from THIS article's own fields (no cross-article dedup).
    Phase 2: Apply cross-article dedup to find novel points.
    Phase 3: Relax dedup when too aggressive (fewer than 3 novel points).
    Phase 4: Score and sort.
    Phase 5: Guarantee minimum 4 points by synthesising from article title/desc.
    Phase 6: Register selected fingerprints for cross-article dedup.
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
        r"[^.!?]*\bLink\s*:\s*\d+[^.!?]*[.!?]?\s*",
        r"\bLink\s*:\s*",
        r"\bLink\s*[.,]?\s*$",
        r"\b(?:\d+|I)\s+event\(s\)\s+detected\b[^\n]*",
        r"#{1,6}\s+(?:Bug Fixes|Features?|Performance|Breaking Changes?|Refactoring?|Chores?|Docs?).*",
        r"\*\*([^*]+):\*\*\s*",
        r"\bv(?:ia)?\s+[A-Z][^\n.!?]{5,80}",
        r"\bMore from\s+\S+[^\n.!?]*",
        r"\s*\|\s*[A-Z][A-Za-z0-9 &]{1,30}$",
    ]
    POWER_VERBS = (
        "launches", "releases", "achieves", "beats", "surpasses", "reveals",
        "breaks", "builds", "cuts", "doubles", "enables", "expands",
        "introduces", "joins", "reaches", "replaces", "sets", "ships",
        "shows", "trains", "upgrades",
    )
    def _strip_noise(text: str) -> str:
        text = clean_creator_text(text)
        for pattern in NOISE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.I)
        return re.sub(r"\s+", " ", text).strip()

    def _is_valid_bullet(text: str) -> bool:
        if not text or len(text) < 15:
            return False
        if not is_public_safe_text(text):
            return False
        if not (text[0].isupper() or text[0].isdigit()):
            return False
        if any(text.lower().startswith(pfx) for pfx in STOP_PREFIXES):
            return False
        return True

    # ---- Phase 1: Collect candidates from THIS article ----
    article_candidates = []

    for p in article.get("key_points", []):
        cleaned = _strip_noise(_clean_public_text(str(p))).strip()
        if _is_valid_bullet(cleaned):
            article_candidates.append(cleaned)

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

    # Deduplicate among themselves only
    seen_local: set[str] = set()
    deduped_local = []
    for p in article_candidates:
        key = re.sub(r"\s+", " ", p).lower()[:60]
        if key not in seen_local:
            seen_local.add(key)
            deduped_local.append(p)

    # ---- Phase 2: Apply cross-article dedup ----
    novel = []
    novel_fingerprints = []
    for p in deduped_local:
        key = re.sub(r"\s+", " ", p).lower()[:60]
        if used_fingerprints is None or key not in used_fingerprints:
            novel.append(p)
            novel_fingerprints.append(key)

    # ---- Phase 3: Relax dedup when too aggressive ----
    if len(novel) < 3:
        for p in deduped_local:
            if p not in novel:
                novel.append(p)
                novel_fingerprints.append(re.sub(r"\s+", " ", p).lower()[:60])
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

    # ---- Phase 5: Guarantee minimum 4 points ----
    if len(novel) < 4:
        title_str = _clean_public_text(str(article.get("title") or summary.headline or summary.subject or ""))
        desc_str = _clean_public_text(str(article.get("description") or article.get("excerpt") or ""))
        if title_str and len(title_str) > 15 and not any(title_str[:40].lower() in p.lower() for p in novel):
            novel.append(title_str)
        if desc_str and len(novel) < 4:
            for chunk in re.split(r"[;,]\s+|(?<=[.!?])\s+", desc_str):
                chunk = chunk.strip()
                if len(chunk) > 35 and _is_valid_bullet(chunk) and chunk not in novel:
                    novel.append(chunk)
                if len(novel) >= 4:
                    break

    # Format and trim for visual-safe carousel layout.
    final = layout_safe_points([_trim_no_dots(pt, 150) for pt in novel], limit=max_points)

    if not final:
        title_fb = _trim_no_dots(
            _clean_public_text(str(article.get("title") or article.get("url") or summary.subject or "AI update")), 95
        )
        return layout_safe_points([title_fb], limit=1)

    if len(final) == 1:
        title_pt = _trim_no_dots(
            _clean_public_text(str(article.get("title") or summary.headline or summary.subject or "")), 120
        )
        if title_pt and title_pt not in final[0]:
            final.extend(layout_safe_points([title_pt], limit=1))

    # ---- Phase 6: Register fingerprints ----
    if used_fingerprints is not None:
        for fp in novel_fingerprints[:max_points]:
            used_fingerprints.add(fp)

    return final


# ─────────────────────────────────────────────────────────────────────────────
# Narrative composition
# ─────────────────────────────────────────────────────────────────────────────

def _compose_article_narrative(summary: "EmailSummary", article: dict[str, Any]) -> str:
    """Build a clean narrative from the structured article fields."""
    what_happened = _clean_public_text(str(article.get("what_happened") or ""))
    why_matters = _clean_public_text(str(article.get("why_matters") or ""))
    what_watch = _clean_public_text(str(article.get("what_to_watch") or ""))

    if what_happened:
        parts = [p for p in [what_happened, why_matters, what_watch] if p]
        return _tighten(re.sub(r"\s+", " ", " ".join(parts)).strip(), 2400)

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
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
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
