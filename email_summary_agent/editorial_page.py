"""Editorial page copy shaping for Instagram carousel slides."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .article_quality import contains_public_noise
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
KEY_POINT_MIN = 4
KEY_POINT_TARGET = 5
KEY_POINT_MAX_WORDS = 22
KEY_POINT_MIN_WORDS = 8


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
    if _is_complete_heading(title) and not _bad_heading_source(title):
        return _trim_words(title, 12)

    source = " ".join(summary_lines) or title
    source_line = _summary_line(source)
    if source_line and _is_complete_heading(source_line) and not _bad_heading_source(source_line):
        return _trim_words(source_line, 12)
    entity = _primary_entity(source) or _primary_entity(title) or "The update"
    verb = _primary_action(source) or "updates"
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
    source_sentences.extend(_sentences(article.get("excerpt") or article.get("scraped_content") or article.get("text") or ""))
    source_sentences.extend(_story_arc_seeds(summary_lines, article, heading))

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

    if len(points) < KEY_POINT_MIN:
        for seed in _story_arc_seeds(summary_lines, article, heading):
            point = _key_point(seed, heading, len(points))
            key = _norm(point)[:72]
            if point and key not in seen and not _near_duplicate(point, points):
                points.append(point)
                seen.add(key)
            if len(points) >= KEY_POINT_MIN:
                break

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
    cleaned = re.sub(r"^(?:This|It|They|The update)\s+(?:means|shows|highlights|suggests|demonstrates)\s+that\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^(?:This|It|They)\s+", "", cleaned, flags=re.I)
    cleaned = _trim_sentence_words(cleaned, KEY_POINT_MAX_WORDS)
    if len(cleaned.split()) < KEY_POINT_MIN_WORDS:
        return ""
    if not _complete_public_sentence(cleaned):
        return ""
    return _sentence(cleaned)


def _story_arc_seeds(summary_lines: list[str], article: dict[str, Any], heading: str) -> list[str]:
    source = " ".join(summary_lines + _sentences(article.get("description") or article.get("summary") or ""))
    entity = _primary_entity(source) or _primary_entity(heading) or "The update"
    audience = _audience_phrase(source)
    return [
        f"{entity} turns the announcement into a practical decision point for teams planning rollout.",
        f"{audience} should read the move through adoption, cost, reliability, and rollout pressure.",
        "The practical value depends on cleaner execution, fewer manual decisions, and less policy drift over time.",
        f"The risk is that unclear rollout details could limit near-term impact despite the bigger ambition.",
        f"Next, watch pricing, customer uptake, technical reliability, and competitor response.",
    ]


def _audience_phrase(text: str) -> str:
    low = (text or "").lower()
    if any(term in low for term in ("developer", "sdk", "api", "workflow", "agent")):
        return "Developers and product teams"
    if any(term in low for term in ("security", "policy", "firewall", "compliance", "governance")):
        return "Security and platform teams"
    if any(term in low for term in ("valuation", "stock", "funding", "bank", "investor")):
        return "Investors and operators"
    if any(term in low for term in ("school", "lawsuit", "regulator", "policy", "government")):
        return "Policy teams and leaders"
    return "Teams tracking the story"


def _trim_sentence_words(text: str, max_words: int) -> str:
    words = text.rstrip(".!?").split()
    if len(words) <= max_words:
        return " ".join(words)
    cut = words[:max_words]
    while len(cut) > KEY_POINT_MIN_WORDS and cut[-1].lower().strip(".,;:") in WEAK_HEADLINE_ENDINGS:
        cut.pop()
    return " ".join(cut).rstrip(".,;:")


def _complete_public_sentence(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned or contains_public_noise(cleaned):
        return False
    words = cleaned.split()
    if len(words) < KEY_POINT_MIN_WORDS:
        return False
    if words[-1].lower().strip(".,;:!?") in WEAK_HEADLINE_ENDINGS:
        return False
    if re.search(r"(?:\(|\[|\{)[^)\]\}]*$", cleaned):
        return False
    return bool(re.search(r"\b(?:is|are|was|were|will|could|should|can|adds|backs|builds|changes|cuts|expands|funds|launches|opens|raises|releases|ships|strengthens|tightens|turns|unveils|upgrades|matters|depends|watch)\b", cleaned, re.I))


def _insight_from_summary_line(line: str, heading: str, index: int) -> str:
    low = line.lower()
    entity = _primary_entity(line) or _primary_entity(heading) or "The update"
    if re.search(r"\$\d|\b\d[\d,.]*(?:%|x|b|m|bn|mn|billion|million)\b", line, re.I):
        return _sentence(f"{entity} adds a concrete number readers can use to judge the size of the move")
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
        return ""
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
    if not text or contains_public_noise(text) or not is_public_safe_text(text):
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
        f"{entity} matters most where it changes adoption, costs, rollout quality, or competitive pressure.",
        "The strongest angle is practical workflow impact, not broad hype around the announcement.",
        "Teams should compare pricing, rollout quality, customer uptake, and competitor response before reacting.",
        "The business impact depends on infrastructure choices, governance decisions, and market positioning.",
        "Readers should watch whether the next update confirms real usage or only extends the announcement cycle.",
    ]


def _is_complete_heading(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9$][A-Za-z0-9$.'+-]*", text)
    if len(words) < 5:
        return False
    if words[-1].lower().strip(".,") in WEAK_HEADLINE_ENDINGS:
        return False
    low = text.lower()
    return any(re.search(rf"\b{re.escape(verb)}\b", low) for verb in ACTION_VERBS) or bool(re.search(r"\b(?:is|are|will|could|plans|moves|faces|gets|makes|lets)\b", low))


def _bad_heading_source(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return True
    if low.startswith(("which ", "what ", "how ", "why ", "and ", "or ", "but ", "speaking ", "according ")):
        return True
    first = low.split()[0].strip(".,;:'\"") if low.split() else ""
    if first in {"nd", "th", "ustry", "omberg", "creates"}:
        return True
    return False


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
        return "raises"
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
