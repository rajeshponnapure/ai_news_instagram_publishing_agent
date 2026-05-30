"""ig_keypoints.py — key point extraction and narrative composition for the Instagram pipeline."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .ig_constants import REFERENCE_BRANDS
from .ig_utils import _clean_public_text, _tighten, _trim_no_dots, _fallback_summary_text
from .ig_copy import (
    clean_creator_text,
    is_public_safe_text,
    layout_safe_points,
    looks_like_heading,
    strip_leading_filler,
)
from .text_similarity import jaccard, normalize_text, simhash, simhash_similar

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
# Human-written keypoint style constants
# ─────────────────────────────────────────────────────────────────────────────

# Patterns that produce weak, generic-sounding keypoints — avoid these
_AI_SOUNDING_PATTERNS = [
    r"\bthis\s+(means|shows|highlights|demonstrates|suggests|underscores)\b",
    r"\bthe\s+(real|key|important|main|biggest)\s+(shift|takeaway|point|insight|detail|thing)\b",
    r"\b(here'?s?|here is)\s+(the|what|why|how)\b",
    r"\bwhat this means\b",
    r"\bkeep an eye on\b",
    r"\bin conclusion\b",
    r"\boverall\b",
    r"\bfurthermore\b",
    r"\badditionally\b",
    r"\bin addition\b",
    r"\bit is important to note\b",
    r"\bwhat you need to know\b",
    r"\blooking ahead\b",
    r"\bwhere things stand\b",
    r"\bsetting the stage\b",
    r"\b(in )?today'?s (digital|fast.paced|rapidly evolving)\b",
    r"\bthe landscape\s+(is shifting|is changing|evolves)\b",
    r"\bit remains to be seen\b",
    r"\bthis comes (amid|as|at a time)\b",
]

_STRONG_OPENERS = (
    "openai", "google", "meta", "apple", "microsoft", "amazon", "anthropic",
    "claude", "gpt", "gemini", "llama", "mistral", "groq", "perplexity",
    "github", "salesforce", "nvidia", "intel", "amd", "ibm",
    "tesla", "spacex", "zoom", "slack", "notion", "figma", "canva",
    "adobe", "oracle", "sap", "uber", "airbnb", "spotify", "netflix",
    "instagram", "whatsapp", "facebook", "linkedin", "tiktok", "twitter", "x",
)

_SENTENCE_START_NOISE = (
    "in the", "as a", "as the", "with the", "for the", "at the", "by the",
    "this is", "there is", "there are", "it is", "it has", "that is",
    "the company", "the article", "the post", "the report", "the study",
    "according to", "in addition", "in this", "in recent",
)

_CREATOR_LABEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BY THE NUMBERS", ("%", "$", "billion", "million", "revenue", "valuation", "users", "x ", "times")),
    ("DEV ANGLE", ("api", "sdk", "developer", "github", "code", "workflow", "agent", "tool")),
    ("MODEL MOVE", ("gpt", "claude", "gemini", "llama", "mistral", "model", "reasoning", "inference")),
    ("MARKET SIGNAL", ("funding", "raise", "acquisition", "partnership", "enterprise", "startup", "customer")),
    ("ROLL OUT", ("launch", "release", "ship", "preview", "available", "beta", "access", "region")),
    ("RISK CHECK", ("safety", "security", "privacy", "policy", "regulation", "lawsuit", "risk")),
)

_CREATOR_LABEL_FALLBACKS = (
    "QUICK SHIFT",
    "WHY IT MATTERS",
    "WHAT CHANGED",
    "WATCH NEXT",
    "CREATOR NOTE",
    "FIELD SIGNAL",
)


def _creator_label_for_point(point: str, used_labels: set[str]) -> str:
    low = f" {point.lower()} "
    for label, keywords in _CREATOR_LABEL_RULES:
        if label in used_labels:
            continue
        if any(keyword in low for keyword in keywords):
            return label
    for label in _CREATOR_LABEL_FALLBACKS:
        if label not in used_labels:
            return label
    return "FIELD SIGNAL"


def _make_creator_style_point(point: str, used_labels: set[str] | None = None) -> str:
    """Add one concise creator label without changing the factual point."""
    used_labels = used_labels if used_labels is not None else set()
    cleaned = re.sub(r"\s+", " ", clean_creator_text(point or "")).strip()
    if not cleaned:
        return ""
    if re.match(r"^[A-Z][A-Z ]{2,24}:\s+", cleaned):
        label = cleaned.split(":", 1)[0]
        used_labels.add(label)
        return cleaned
    label = _creator_label_for_point(cleaned, used_labels)
    used_labels.add(label)
    return f"{label}: {cleaned}"


# ─────────────────────────────────────────────────────────────────────────────
# Key point extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_instagram_key_points(
    article: dict[str, Any],
    summary: "EmailSummary",
    max_points: int = 10,
    used_fingerprints: set[str] | None = None,
) -> list[str]:
    """Build punchy, human-style key points for Instagram slides.

    The goal is a line a human content creator would write: a single fact-led
    statement, no heading/meta label, no essay connectives, no copy-pasted
    article prose. Pipeline:

    Phase 1: Collect raw candidates from THIS article's own fields.
    Phase 2: Reshape each into a human-style line and reject headings/low quality.
    Phase 3: Drop near-duplicates of points already used on earlier slides
             (semantic, via Jaccard/SimHash), relaxing only to avoid starving a slide.
    Phase 4: Score and sort by concreteness.
    Phase 5: Guarantee >=4 points by reshaping the title/description.
    Phase 6: Register the selected points for cross-slide dedup.
    """
    STOP_PREFIXES = (
        "this article", "in this post", "the article", "we discuss",
        "this piece", "this blog", "you will learn", "click here",
        "read more", "find out", "learn how", "sign up",
        "grdevelopers", "graitech",
    )
    # Weak openers that produce vague, AI-sounding points instead of facts.
    WEAK_OPENERS = (
        "this ", "it ", "these ", "those ", "there ", "that ", "here ",
        "they ", "we ", "such ", "as a ", "in the ", "the company ",
        "the article ", "according to ", "in addition ",
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
    # Additional AI-sounding phrases to strip from extracted sentences
    _AI_FILLER_PATTERNS = [
        r"(?i)\b(in )?this (article|post|piece|blog|report)\s+(we|I|the author)\s+(will\s+)?(discuss|explore|examine|cover|look at|dive into)\b.*",
        r"(?i)\bin today['']?s (digital|fast.paced|rapidly. evolving|competitive|modern)\s+\w+\b.*",
        r"(?i)\b(as we (move|head|transition|look) (into|toward|ahead))\b.*",
        r"(?i)\bits (important|essential|crucial|worth noting|no surprise)\s+(to|that)\b.*",
        r"(?i)\bthe (real|key|important|main|biggest)\s+(question|challenge|issue|concern|takeaway)\s+(is|remains)\b.*",
    ]
    POWER_VERBS = (
        "launches", "launched", "releases", "released", "achieves", "beats",
        "surpasses", "reveals", "breaks", "builds", "cuts", "doubles",
        "enables", "expands", "introduces", "introduced", "joins", "reaches",
        "replaces", "sets", "ships", "shipped", "shows", "trains", "upgrades",
        "announces", "announced", "unveils", "raises", "raised", "acquires",
        "partners", "hits", "tops", "adds", "brings", "opens",
    )

    def _strip_noise(text: str) -> str:
        text = clean_creator_text(text)
        for pattern in NOISE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.I)
        return re.sub(r"\s+", " ", text).strip()

    def _humanize(text: str) -> str:
        """Reshape a raw sentence into a single fact-led creator line."""
        t = strip_leading_filler(_strip_noise(text))
        # Strip AI-sounding filler phrases
        for fp in _AI_FILLER_PATTERNS:
            t = re.sub(fp, "", t).strip()
        # Keep only the first complete sentence — points are one idea each.
        parts = re.split(r"(?<=[.!?])\s+", t)
        if parts and parts[0].strip():
            t = parts[0].strip()
        # Drop trailing attribution clauses (", the company said", "— OpenAI says").
        t = re.sub(
            r"[,;:\-–—]\s*(?:the\s+\w+\s+)?(?:said|says|added|noted|wrote|"
            r"according to|reported|explained)\b.*$",
            "",
            t,
            flags=re.I,
        ).strip()
        # Remove trailing AI-sounding patterns
        t = re.sub(r"\s*[-–—]?\s*(?:and\s+)?(?:this (?:means|shows|highlights|demonstrates|suggests)\b.*)$", "", t, flags=re.I).strip()
        words = t.split()
        if len(words) > 16:
            t = " ".join(words[:16])
        t = t.strip(" -–—,;:·•")
        if not t:
            return ""
        t = t[0].upper() + t[1:]
        t = re.sub(r"[\s.,;:\-–—]+$", "", t)
        if t and t[-1] not in "!?":
            t += "."
        return t

    def _is_quality(text: str) -> bool:
        if not text or len(text) < 15:
            return False
        if not is_public_safe_text(text):
            return False
        if looks_like_heading(text):
            return False
        low = text.lower()
        if any(low.startswith(pfx) for pfx in STOP_PREFIXES):
            return False
        if any(low.startswith(w) for w in WEAK_OPENERS):
            return False
        if not (text[0].isupper() or text[0].isdigit()):
            return False
        if any(re.search(p, low) for p in _AI_SOUNDING_PATTERNS):
            return False
        if any(low.startswith(n) for n in _SENTENCE_START_NOISE):
            return False
        return True

    def _semantic_dupe(text: str, used_texts) -> bool:
        if not used_texts:
            return False
        sh = simhash(text)
        for prior in used_texts:
            if jaccard(text, prior) >= 0.82:
                return True
            if simhash_similar(sh, simhash(prior), max_hamming=3):
                return True
        return False

    # ---- Phase 1+2: Collect, reshape, and quality-gate candidates ----
    candidates: list[str] = []
    seen_local_norm: set[str] = set()

    def _consider(raw: str) -> None:
        point = _humanize(raw)
        if not _is_quality(point):
            return
        norm = normalize_text(point)
        if not norm or norm in seen_local_norm:
            return
        if _semantic_dupe(point, [_recover(n) for n in seen_local_norm]):
            return
        seen_local_norm.add(norm)
        _norm_to_text[norm] = point
        candidates.append(point)

    _norm_to_text: dict[str, str] = {}

    def _recover(norm: str) -> str:
        return _norm_to_text.get(norm, norm)

    for p in article.get("key_points", []):
        _consider(_clean_public_text(str(p)))

    for field in ("what_happened", "why_matters", "what_to_watch", "description", "excerpt", "scraped_content"):
        text = _strip_noise(_clean_public_text(str(article.get(field) or "")))
        if not text:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", text):
            if len(sent.strip()) > 25:
                _consider(sent)
        if len(candidates) >= max_points * 3:
            break

    # ---- Phase 3: Cross-slide dedup (relaxed so a slide is never starved) ----
    used_texts = list(used_fingerprints) if used_fingerprints else []
    novel = [c for c in candidates if not _semantic_dupe(c, used_texts)]
    if len(novel) < 4:
        for c in candidates:
            if c not in novel:
                novel.append(c)

    # ---- Phase 4: Score and sort by concreteness ----
    def _point_score(pt: str) -> float:
        score = 0.0
        low = pt.lower()
        words = pt.split()
        # Power verbs indicate action-oriented content
        if any(low.startswith(v) for v in POWER_VERBS) or any(f" {v} " in f" {low} " for v in POWER_VERBS):
            score += 0.4
        # Specific numbers — concrete, not generic
        if re.search(r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|x|B|M|K|bn|mn|billion|million|percent|times)\b", pt, re.I):
            score += 0.35
        # Proper nouns / brands / models — specific entities beat generic prose
        if re.search(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)?\b", pt[1:]) or any(
            b.lower() in low for b in REFERENCE_BRANDS
        ):
            score += 0.2
        # Company/org name at start — direct and grounded
        if any(pt.lower().startswith(opener) for opener in _STRONG_OPENERS):
            score += 0.25
        # Good length: specific enough to be useful, short enough for Instagram
        if 6 <= len(words) <= 14:
            score += 0.2
        # Starts with a number — very specific
        if words and re.match(r"^\d", words[0]):
            score += 0.15
        # Penalize AI-sounding sentence starts
        if any(low.startswith(n) for n in _SENTENCE_START_NOISE):
            score -= 0.3
        return max(0.0, score)

    novel.sort(key=_point_score, reverse=True)

    # ---- Phase 5: Guarantee >=4 points from title/description ----
    if len(novel) < 4:
        for raw in (
            str(article.get("title") or ""),
            str(article.get("description") or article.get("excerpt") or ""),
        ):
            if len(novel) >= 4:
                break
            for chunk in re.split(r"(?<=[.!?])\s+|[;]\s+", _clean_public_text(raw)):
                point = _humanize(chunk)
                if not _is_quality(point):
                    continue
                norm = normalize_text(point)
                if norm in seen_local_norm:
                    continue
                seen_local_norm.add(norm)
                novel.append(point)
                if len(novel) >= 4:
                    break

    final = layout_safe_points([_trim_no_dots(pt, 150) for pt in novel], limit=max_points)
    labels_used: set[str] = set()
    final = [
        styled for styled in (_make_creator_style_point(pt, labels_used) for pt in final)
        if styled
    ]

    if not final:
        title_fb = _humanize(_clean_public_text(str(article.get("title") or "")))
        return layout_safe_points([_make_creator_style_point(title_fb)], limit=1) if _is_quality(title_fb) else []

    # ---- Phase 6: Register selected points for cross-slide dedup ----
    if used_fingerprints is not None:
        for pt in final:
            used_fingerprints.add(pt)

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
