"""Layout-safe creator copy helpers for Instagram carousel text."""
from __future__ import annotations

import html
import re


FORBIDDEN_PHRASES = (
    "dismiss alert",
    "public notifications",
    "you must be signed in",
    "you signed out",
    "you switched accounts",
    "search code",
    "repositories users issues pull requests",
    "filter loading",
    "sorry something went wrong",
    "hamburger navigation",
    "navigation drawer",
    "verified learn about vigilant",
    "techcrunch desktop logo",
    "techcrunch mobile logo",
    "latest startups venture",
    "notifications notifications",
    "read more",
    "click here",
    "learn more",
    "cookie preferences",
    "privacy policy",
    "terms of service",
)

ROBOTIC_PHRASES = (
    "in conclusion",
    "overall",
    "it is important to note",
    "this highlights the significance",
    "furthermore",
    "additionally",
    "the practical impact:",
    "watch next:",
    "this article discusses",
    "the email indicates",
    "primary entities",
    "likely content themes",
    "best posting angle",
)

POWER_WORDS = (
    "hidden",
    "surprising",
    "critical",
    "powerful",
    "unexpected",
    "massive",
    "dangerous",
    "proven",
    "exposed",
)

ACTION_VERBS = (
    "launches",
    "released",
    "ships",
    "raises",
    "hits",
    "breaks",
    "reveals",
    "exposes",
    "changes",
    "unlocks",
    "warns",
    "cuts",
    "doubles",
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "in", "into", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "with", "your", "you",
}


def clean_creator_text(text: str) -> str:
    """Decode, clean, and normalize public-facing carousel copy."""
    text = html.unescape(str(text or ""))
    text = text.replace("\u2026", ".").replace("...", ".")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^\S\r\n]+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"^[\s\-:|/>#*]+", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    for phrase in ROBOTIC_PHRASES:
        text = re.sub(re.escape(phrase), "", text, flags=re.I).strip(" -:;")
    return text


def is_public_safe_text(text: str) -> bool:
    cleaned = clean_creator_text(text).lower()
    if len(cleaned) < 15:
        return False
    if any(phrase in cleaned for phrase in FORBIDDEN_PHRASES):
        return False
    if re.search(r"\{\{.*?\}\}", cleaned):
        return False
    if re.search(r"\b(?:logo|drawer|notification|signed out|signed in)\b", cleaned):
        return False
    return True


def layout_safe_headline(text: str, fallback: str = "AI Update") -> str:
    """Return a 4-7 word creator-style headline that fits the slide."""
    cleaned = clean_creator_text(text)
    cleaned = re.sub(r"\([^)]{8,}\)", "", cleaned)
    cleaned = re.sub(r"#\d{3,}", "", cleaned)
    cleaned = re.sub(r"\b(?:new release|latest|update|changes since)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.")
    if not cleaned or not is_public_safe_text(cleaned):
        cleaned = clean_creator_text(fallback)

    words = _meaningful_words(cleaned)
    if not words:
        words = _meaningful_words(fallback) or ["AI", "Update"]

    if 4 <= len(words) <= 7:
        return _title_case(words)

    entity = _entity_from_text(cleaned) or words[0]
    verb = _verb_from_text(cleaned)
    topic_words = [w for w in words if w.lower() not in STOPWORDS and w.lower() != entity.lower()]

    if verb:
        picked = [entity, verb, *topic_words[:4]]
    else:
        picked = [entity, "Just", "Changed", *topic_words[:3]]

    picked = _dedupe_words(picked)[:7]
    if len(picked) < 4:
        picked = (picked + ["Changes", "Everything"])[:4]
    return _title_case(picked)


def layout_safe_point(text: str, index: int = 0) -> str:
    """Return a 12-16 word max point with creator-style tension."""
    cleaned = clean_creator_text(text)
    cleaned = cleaned.lstrip("-*\u2022 ").strip()
    if not is_public_safe_text(cleaned):
        return ""

    sentence = _first_complete_sentence(cleaned)
    words = sentence.split()
    if len(words) > 16:
        sentence = " ".join(words[:16]).rstrip(".,;:-")

    lower = sentence.lower()
    if not any(word in lower for word in (*POWER_WORDS, *ACTION_VERBS, "why", "watch", "secret", "truth")):
        prefix = (
            "Here is the hidden part:"
            if index == 0 else
            "This is the real shift:"
            if index == 1 else
            "Watch the critical signal:"
            if index == 2 else
            "Most people miss this:"
        )
        combined = f"{prefix} {sentence}"
        words = combined.split()
        sentence = " ".join(words[:16]).rstrip(".,;:-")

    if sentence and sentence[-1] not in ".!?":
        sentence += "."
    return sentence


def layout_safe_points(points: list[str], limit: int = 5) -> list[str]:
    shaped: list[str] = []
    seen: set[str] = set()
    for raw in points:
        point = layout_safe_point(raw, len(shaped))
        key = re.sub(r"\W+", " ", point.lower()).strip()[:70]
        if point and key not in seen:
            shaped.append(point)
            seen.add(key)
        if len(shaped) >= limit:
            break
    return shaped


def trim_without_ellipsis(text: str, limit: int) -> str:
    cleaned = clean_creator_text(text).rstrip(". ")
    if len(cleaned) <= limit:
        return _ensure_sentence(cleaned)
    truncated = cleaned[:limit].rsplit(" ", 1)[0].rstrip(".,;:- ")
    return _ensure_sentence(truncated)


def _first_complete_sentence(text: str) -> str:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts[0] if parts else text


def _ensure_sentence(text: str) -> str:
    text = text.strip()
    if text and text[-1] not in ".!?":
        return text + "."
    return text


def _meaningful_words(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9$][A-Za-z0-9$.'+-]*", text)
    words = [w.strip(".,;:!?") for w in raw if w.strip(".,;:!?")]
    return words


def _entity_from_text(text: str) -> str:
    match = re.search(r"\b[A-Z][A-Za-z0-9.+-]*(?:\s+[A-Z][A-Za-z0-9.+-]*){0,1}\b", text)
    return match.group(0) if match else ""


def _verb_from_text(text: str) -> str:
    lower = text.lower()
    for verb in ACTION_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", lower):
            return verb.capitalize()
    if re.search(r"\b(?:will|could|may)\b", lower):
        return "Could"
    return ""


def _dedupe_words(words: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for word in words:
        key = word.lower()
        if key not in seen:
            out.append(word)
            seen.add(key)
    return out


def _title_case(words: list[str]) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in words).strip()
