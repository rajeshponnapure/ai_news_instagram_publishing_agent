"""Editorial page copy shaping for Instagram carousel slides."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .ig_copy import clean_creator_text, is_public_safe_text, layout_safe_headline, layout_safe_points
from .ig_utils import _clean_public_text

if TYPE_CHECKING:
    from .models import EmailSummary


ACTION_VERBS = (
    "adds", "backs", "builds", "changes", "cuts", "expands", "funds",
    "launches", "opens", "raises", "releases", "ships", "signals",
    "strengthens", "tightens", "unveils", "upgrades",
)

WEAK_HEADLINE_ENDINGS = {
    "a", "an", "and", "as", "by", "for", "from", "in", "of", "on",
    "or", "the", "to", "with",
}

SUMMARY_LINE_LIMIT = 3
KEY_POINT_TARGET = 4


def build_editorial_page_copy(
    article: dict[str, Any],
    summary: "EmailSummary",
    raw_points: list[str],
) -> dict[str, list[str] | str]:
    """Return publication-ready heading, summary lines, and key points.

    The key points are intentionally generated after the summary lines are
    finalized, so slide bullets stay grounded in the visible page summary.
    """
    summary_lines = _build_summary_lines(article, summary, raw_points)
    heading = _build_heading(article, summary, summary_lines)
    key_points = _build_key_points_from_summary(summary_lines, raw_points, article, heading)
    return {
        "heading": heading,
        "summary_lines": summary_lines,
        "key_points": key_points,
    }


def _build_heading(article: dict[str, Any], summary: "EmailSummary", summary_lines: list[str]) -> str:
    title = clean_creator_text(article.get("title") or summary.headline or summary.subject or "AI update")
    title = re.sub(r"\s*[\-|:]\s*(?:TechCrunch|Bloomberg|Reuters|The Verge|AWS|Amazon Web Services)\s*$", "", title, flags=re.I)
    title = layout_safe_headline(title, fallback="AI update")
    title = _sentence(title)
    if _is_complete_heading(title):
        return _trim_words(title, 12)

    source = " ".join(summary_lines) or title
    entity = _primary_entity(source) or _primary_entity(title) or "The update"
    verb = _primary_action(source) or "signals"
    object_phrase = _compact_object_phrase(source, entity)
    heading = f"{entity} {verb} {object_phrase}"
    return _trim_words(_sentence(heading), 12)


def _build_summary_lines(
    article: dict[str, Any],
    summary: "EmailSummary",
    raw_points: list[str],
) -> list[str]:
    candidates: list[str] = []
    for field in ("what_happened", "why_matters", "what_to_watch", "summary", "description", "excerpt", "scraped_content", "text"):
        candidates.extend(_sentences(article.get(field) or ""))
    candidates.extend(_sentences(summary.summary))
    candidates.extend(_sentences(" ".join(raw_points)))

    selected: list[str] = []
    seen: set[str] = set()
    for sentence in sorted(candidates, key=_summary_score, reverse=True):
        line = _summary_line(sentence)
        key = _norm(line)[:72]
        if not line or key in seen:
            continue
        if _near_duplicate(line, selected):
            continue
        selected.append(line)
        seen.add(key)
        if len(selected) >= SUMMARY_LINE_LIMIT:
            break

    if not selected:
        fallback = _summary_line(article.get("title") or summary.headline or "A major AI update is moving through the market.")
        selected = [fallback]

    return selected[:SUMMARY_LINE_LIMIT]


def _build_key_points_from_summary(
    summary_lines: list[str],
    raw_points: list[str],
    article: dict[str, Any],
    heading: str,
) -> list[str]:
    source_sentences = list(summary_lines)
    source_sentences.extend(_sentences(" ".join(raw_points)))
    source_sentences.extend(_sentences(article.get("description") or article.get("summary") or ""))

    points: list[str] = []
    seen: set[str] = set()
    for index, sentence in enumerate(source_sentences):
        point = _key_point(sentence, heading, index)
        key = _norm(point)[:72]
        if not point or key in seen:
            continue
        if _near_duplicate(point, points):
            continue
        points.append(point)
        seen.add(key)
        if len(points) >= KEY_POINT_TARGET:
            break

    seeds = _fallback_keypoint_seeds(summary_lines, article, heading)
    for seed in seeds:
        if len(points) >= KEY_POINT_TARGET:
            break
        point = _key_point(seed, heading, len(points))
        key = _norm(point)[:72]
        if point and key not in seen and not _near_duplicate(point, points):
            points.append(point)
            seen.add(key)

    return points[:KEY_POINT_TARGET]


def _summary_line(text: str) -> str:
    cleaned = _clean_sentence(text)
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) > 18:
        cleaned = " ".join(words[:18]).rstrip(".,;:")
    return _sentence(cleaned)


def _key_point(text: str, heading: str, index: int = 0) -> str:
    cleaned = _clean_sentence(text)
    if not cleaned:
        return ""
    insight = _insight_from_summary_line(cleaned, heading, index)
    if insight:
        return insight
    cleaned = re.sub(r"^(?:This|It|They|The update)\s+(?:means|shows|highlights|suggests|demonstrates)\s+that\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:This|It|They)\s+", "", cleaned, flags=re.I)
    words = cleaned.split()
    if len(words) > 18:
        cleaned = " ".join(words[:18]).rstrip(".,;:")
    if len(cleaned.split()) < 6:
        entity = _primary_entity(heading) or "The update"
        cleaned = f"{entity} gives teams a clearer signal to track adoption, competition, and execution risk"
    return _sentence(cleaned)


def _insight_from_summary_line(line: str, heading: str, index: int) -> str:
    low = line.lower()
    entity = _primary_entity(line) or _primary_entity(heading) or "The update"
    if re.search(r"\$\d|\b\d[\d,.]*(?:%|x|b|m|bn|mn|billion|million)\b", line, re.I):
        return _sentence(f"{entity} puts a concrete number behind the move, making the market signal easier to judge")
    if "clearer signal to evaluate" in low:
        return _sentence("Readers get a practical decision frame for execution quality, reliability, and adoption")
    if re.search(r"\b(lets|allows|enables|gives)\b", low):
        capability = re.split(r"\b(?:lets|allows|enables|gives)\b", line, maxsplit=1, flags=re.I)[-1]
        capability = _compact_clause(capability)
        return _sentence(f"{entity} creates a clearer path for {capability}")
    if re.search(r"\b(reduces|cuts|lowers|simplifies)\b", low):
        return _sentence("The operational win is less manual upkeep, cleaner execution, and faster response to changing conditions")
    if re.search(r"\b(security|policy|firewall|compliance|governance)\b", low):
        return _sentence("Security teams get stronger control where fast-changing AI and SaaS domains usually create policy drift")
    if re.search(r"\b(model|inference|llm|agent|developer|workflow)\b", low):
        return _sentence("The developer angle matters where better tooling changes deployment choices, reliability, and day-to-day workflow speed")
    if index == 0:
        return _sentence(f"{entity} gives readers the main signal to watch before reacting to the headline")
    return ""


def _compact_clause(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" -:;,.")
    words = [
        word.strip(".,;:!?")
        for word in re.findall(r"[A-Za-z0-9$][A-Za-z0-9$.'+-]*", cleaned)
        if word.lower() not in {"and", "or", "that", "this", "its"}
    ]
    if not words:
        return "teams to act on the update with less friction"
    if len(words) >= 2 and words[0].lower() in {"administrators", "teams", "developers", "operators", "companies", "creators"} and words[1].lower() not in {"to", "a", "an", "the"}:
        words.insert(1, "to")
    return " ".join(words[:14])


def _clean_sentence(text: str) -> str:
    text = clean_creator_text(_clean_public_text(str(text or "")))
    text = re.sub(r"\b(?:quick shift|market signal|model move|roll out|dev angle|risk check|by the numbers)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\b(?:for more details|read more|learn more|click here)\b.*$", "", text, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.")
    if not text or not is_public_safe_text(text):
        return ""
    if re.search(r"\bstory\s+\d+\s+excerpt\b", text, re.I):
        return ""
    if re.search(r"\b[a-z0-9-]+/[a-z0-9-]+(?:/[a-z0-9-]+)+", text.lower()):
        return ""
    return text


def _sentences(text: Any) -> list[str]:
    cleaned = clean_creator_text(str(text or ""))
    parts = re.split(r"(?<=[.!?])\s+|\n+|(?:\s+-\s+)", cleaned)
    return [part.strip() for part in parts if len(part.strip()) >= 24]


def _summary_score(text: str) -> float:
    low = text.lower()
    score = 0.0
    if any(verb in low for verb in ACTION_VERBS):
        score += 0.5
    if re.search(r"\b\d[\d,.]*(?:%|x|b|m|bn|mn|billion|million)?\b", text, re.I):
        score += 0.35
    if re.search(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+)?\b", text):
        score += 0.25
    if any(term in low for term in ("developer", "enterprise", "customer", "policy", "funding", "model", "inference", "security")):
        score += 0.2
    if any(term in low for term in ("early bird", "subscribe", "follow", "newsletter", "podcast")):
        score -= 2.0
    return score


def _fallback_keypoint_seeds(summary_lines: list[str], article: dict[str, Any], heading: str) -> list[str]:
    source = " ".join(summary_lines)
    entity = _primary_entity(source) or _primary_entity(heading) or "The story"
    return [
        f"{entity} gives operators a clearer signal to evaluate execution, reliability, and adoption.",
        "The strongest angle is practical workflow impact, not broad hype around the announcement.",
        "Teams should watch pricing, rollout quality, customer uptake, and competitive response before overreacting.",
        "The story matters most where it changes infrastructure choices, governance decisions, or market positioning.",
    ]


def _is_complete_heading(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9$][A-Za-z0-9$.'+-]*", text)
    if len(words) < 5:
        return False
    if words[-1].lower().strip(".,") in WEAK_HEADLINE_ENDINGS:
        return False
    low = text.lower()
    return any(re.search(rf"\b{re.escape(verb)}\b", low) for verb in ACTION_VERBS) or bool(re.search(r"\b(?:is|are|will|could|plans|moves|faces|gets|makes|lets)\b", low))


def _primary_entity(text: str) -> str:
    matches = re.findall(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,2}\b", text or "")
    blocked = {"The", "This", "That", "AI", "API", "GPU", "LLM", "URL", "Domain", "Category"}
    for match in matches:
        if match not in blocked and len(match) >= 3:
            return match
    return ""


def _primary_action(text: str) -> str:
    low = text.lower()
    for verb in ACTION_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", low):
            return verb
    if "funding" in low or "valuation" in low:
        return "signals"
    if "policy" in low or "security" in low:
        return "tightens"
    if "model" in low or "inference" in low:
        return "upgrades"
    return ""


def _compact_object_phrase(text: str, entity: str) -> str:
    cleaned = re.sub(re.escape(entity), "", text or "", flags=re.I).strip()
    words = [
        word.strip(".,;:!?")
        for word in re.findall(r"[A-Za-z0-9$][A-Za-z0-9$.'+-]*", cleaned)
        if word.lower() not in {"the", "a", "an", "and", "or", "with", "from", "that", "this", "its", "for"}
    ]
    phrase = " ".join(words[:7]).strip()
    return phrase or "a sharper AI market signal"


def _sentence(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" -:;,.")
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _trim_words(text: str, max_words: int) -> str:
    words = text.rstrip(".!?").split()
    if len(words) <= max_words:
        return _sentence(" ".join(words))
    while len(words) > 5 and words[max_words - 1].lower().strip(".,") in WEAK_HEADLINE_ENDINGS:
        max_words -= 1
    return _sentence(" ".join(words[:max_words]))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _near_duplicate(text: str, existing: list[str]) -> bool:
    words = set(_norm(text).split())
    if not words:
        return True
    for item in existing:
        other = set(_norm(item).split())
        if not other:
            continue
        if len(words & other) / max(1, len(words | other)) >= 0.72:
            return True
    return False
