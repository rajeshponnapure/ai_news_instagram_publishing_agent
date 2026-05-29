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
    "are you a robot",
    "prove you are human",
    "detected unusual activity",
    "unusual activity from your computer network",
    "to continue, please click the box",
    "please click the box below",
    "global markets news at your fingertips",
    "bloomberg.com subscription",
    "for inquiries related to this message",
    "contact our support team",
    "support team and provide",
    "please contact our support",
    "enable javascript",
    "access to this page has been denied",
    "checking your browser",
    "verify you are a human",
)

ROBOTIC_PHRASES = (
    "in conclusion",
    "overall",
    "it is important to note",
    "it is worth noting",
    "it bears mentioning",
    "this highlights the significance",
    "furthermore",
    "additionally",
    "this comes amid",
    "this comes as",
    "the landscape is shifting",
    "this is a developing story",
    "in related news",
    "speaking of which",
    "on that note",
    "the practical impact:",
    "watch next:",
    "this article discusses",
    "the email indicates",
    "primary entities",
    "likely content themes",
    "best posting angle",
    "here is the key detail:",
    "the real shift here:",
    "keep an eye on this:",
    "what this means:",
)

# Leading connective / filler tokens that make a key point read like an essay
# instead of a punchy human-written line. Stripped from the START of a point.
LEADING_FILLER = (
    "furthermore", "additionally", "in addition", "moreover", "however",
    "meanwhile", "notably", "importantly", "interestingly", "as a result",
    "consequently", "therefore", "thus", "in fact", "indeed", "that said",
    "on the other hand", "for instance", "for example", "in other words",
    "ultimately", "in short", "in summary", "to sum up", "all in all",
    "essentially", "basically", "simply put", "of course", "clearly",
    "according to the company", "according to the report", "according to the post",
    "the company said", "the company says", "in a blog post", "in a statement",
    "in a press release", "reportedly", "apparently",
)


ACTION_VERBS = (
    "launches", "launched",
    "releases", "released",
    "ships", "shipped",
    "raises", "raised",
    "hits", "hit",
    "breaks", "broke",
    "reveals", "revealed",
    "exposes", "exposed",
    "changes", "changed",
    "unlocks", "unlocked",
    "warns", "warned",
    "cuts", "cut",
    "doubles", "doubled",
    "deploys", "deployed",
    "announces", "announced",
    "introduces", "introduced",
    "partners", "partnered",
    "acquires", "acquired",
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "in", "into", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "with", "your", "you",
}

KEYPOINT_LABELS = (
    "here is the key detail",
    "here's the key detail",
    "the key detail",
    "the real shift here",
    "the real shift is here",
    "the real shift",
    "the real story",
    "keep an eye on this",
    "keep an eye out",
    "what this means",
    "what it means",
    "here's what this means",
    "what this really means",
    "watch next",
    "what's next",
    "what comes next",
    "the practical impact",
    "the real impact",
    "why it matters",
    "why this matters",
    "here's why it matters",
    "what happened",
    "here's what happened",
    "what to watch",
    "what to watch next",
    "the bottom line",
    "bottom line",
    "the big picture",
    "the takeaway",
    "key takeaway",
    "key takeaways",
    "the key takeaway",
    "the upshot",
    "the catch",
    "the kicker",
    "the gist",
    "the context",
    "make no mistake",
    "let that sink in",
    "zoom out",
    "zoom in",
    "tl;dr",
    "in summary",
    "to sum up",
    "the key point",
    "the main point",
    "here's the thing",
    "the thing is",
    "the details",
    "here are the details",
    "here's the details",
    "more details",
    "for more details",
    "the latest",
    "here's the latest",
    "the news",
    "here's the news",
    "what you need to know",
    "here's what you need to know",
    "everything you need to know",
    "fast facts",
    "key insights",
    "the key insight",
    "quick take",
    "the quick take",
    "for context",
    "here's some context",
    "some context",
    "the backstory",
    "the background",
    "what's happening",
    "here's what's happening",
    "where things stand",
    "the situation",
    "the headline",
    "why now",
    "why this now",
    "what changed",
    "what's changed",
    "the development",
    "the announcement",
    "what you should know",
    "by the numbers",
    "the full picture",
    "the full story",
    "the bigger story",
    "a closer look",
    "taking a closer look",
    "looking ahead",
    "the outlook",
    "the verdict",
    "the punchline",
    "the breakdown",
    "the update",
    "here's the update",
    "quick update",
    "status update",
    "setting the stage",
    "the scene",
    "the backstory",
)

# A point that, after cleaning, is *only* one of these (or matches the heading
# regex) is rejected outright — it carries no fact, just a label.
_HEADING_RE = re.compile(
    r"^(?:the\s+|a\s+|an\s+)?"
    r"(?:real\s+shift|key\s+(?:detail|point|takeaway|insight)|big\s+picture|bottom\s+line|"
    r"practical\s+impact|takeaway|upshot|catch|kicker|gist|context|"
    r"what\s+(?:this|it)\s+(?:means|really\s+means)|what\s+happened|"
    r"what(?:'s|\s+to|\s+comes)\s+(?:next|watch|changed)|why\s+(?:it|this)\s+matters|"
    r"why\s+now|keep\s+an\s+eye(?:\s+out|\s+on\s+this)?|watch\s+next|make\s+no\s+mistake|"
    r"zoom\s+(?:in|out)|in\s+summary|to\s+sum\s+up|here'?s\s+(?:the\s+thing|what|why|"
    r"the\s+(?:latest|news|details|update|verdict|punchline|breakdown|"
    r"backstory|background|headline|scene|situation|outlook)|"
    r"what\s+(?:you\s+need\s+to\s+know|you\s+should\s+know|we're\s+watching|"
    r"we\s+know|changed|'s\s+happening)|"
    r"(?:fast\s+facts|key\s+insights?|quick\s+take|(?:quick\s+)?(?:context|update)|"
    r"more\s+details|for\s+(?:more\s+)?details|by\s+the\s+numbers|"
    r"full\s+(?:picture|story)|bigger\s+story|a\s+closer\s+look|"
    r"taking\s+a\s+closer\s+look|looking\s+ahead|setting\s+the\s+stage|"
    r"where\s+things\s+stand|the\s+development|the\s+announcement)))"
    r"\b[\s:.\-–—]*$",
    re.I,
)


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
    return _strip_keypoint_heading(text)


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


# Headlines wrap onto multiple lines in the renderer, so we preserve the real
# title up to this many words rather than truncating it. Only past this do we
# trim — always on a word boundary, never mid-word, and never dropping the
# leading entity (which caused "title cut off at the beginning").
MAX_HEADLINE_WORDS = 12


def layout_safe_headline(text: str, fallback: str = "AI Update") -> str:
    """Return the article's real title, cleaned and never cut mid-word.

    The previous implementation rebuilt the headline from an extracted entity +
    verb, which dropped the start/end of real titles. We now keep the cleaned
    title as-is, only trimming overly long ones on a word boundary, and synthesize
    a headline solely when the title is empty or unsafe.
    """
    cleaned = clean_creator_text(text)
    cleaned = re.sub(r"\([^)]{8,}\)", "", cleaned)          # drop long parentheticals
    cleaned = re.sub(r"#\d{3,}", "", cleaned)               # drop PR/issue numbers
    cleaned = re.sub(r"\s*[\-|–—]\s*[A-Z][A-Za-z0-9 .]{1,24}$", "", cleaned)  # trailing " - SiteName"
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.")
    if not cleaned or not is_public_safe_text(cleaned):
        cleaned = clean_creator_text(fallback)

    words = _meaningful_words(cleaned)
    if not words:
        words = _meaningful_words(fallback) or ["AI", "Update"]

    if len(words) > MAX_HEADLINE_WORDS:
        words = words[:MAX_HEADLINE_WORDS]
        # Never end a headline on a dangling stopword/preposition.
        while len(words) > 4 and words[-1].lower() in STOPWORDS:
            words.pop()

    headline = " ".join(words).strip()
    if not headline:
        return fallback
    return headline[0].upper() + headline[1:]


def layout_safe_point(text: str, index: int = 0) -> str:
    """Return a direct, layout-safe key point without meta-label prefixes."""
    cleaned = clean_creator_text(text)
    cleaned = cleaned.lstrip("-*\u2022 ").strip()
    if not is_public_safe_text(cleaned):
        return ""

    sentence = _first_complete_sentence(cleaned)
    words = sentence.split()
    if len(words) > 16:
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


def _strip_keypoint_heading(text: str) -> str:
    """Remove heading/meta labels from the START of a point, with any separator.

    Handles ``Label:``, ``Label -``, ``Label —``, ``Label.`` and bare ``Label``
    when followed by sentence content. Also handles labels followed by whitespace
    + capital letter (no separator — LLM sometimes omits it). Loops so stacked
    labels are all removed.
    """
    cleaned = str(text or "").strip()
    changed = True
    while changed:
        changed = False
        cleaned = re.sub(r"^[\s\-:|/>#*•·]+", "", cleaned).strip()
        for label in KEYPOINT_LABELS:
            updated = re.sub(
                rf"^(?i:{re.escape(label)})\s*(?:[:\-–—.]+\s*(?=\S)|\s+(?=[A-Z]))",
                "", cleaned,
            ).strip()
            if updated != cleaned and updated:
                cleaned = updated
                changed = True
                break
    return cleaned


def strip_leading_filler(text: str) -> str:
    """Drop essay-style connectives/attribution from the START of a point."""
    cleaned = str(text or "").strip()
    changed = True
    while changed:
        changed = False
        cleaned = re.sub(r"^[\s\-:,;]+", "", cleaned).strip()
        for phrase in LEADING_FILLER:
            updated = re.sub(
                rf"^{re.escape(phrase)}\b[\s,:;.\-–—]*", "", cleaned, flags=re.I
            ).strip()
            if updated != cleaned and updated:
                cleaned = updated
                changed = True
                break
    return cleaned


def _label_norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(text or "").lower()).strip()


_KEYPOINT_LABEL_NORMS = frozenset(_label_norm(label) for label in KEYPOINT_LABELS)


def looks_like_heading(text: str) -> bool:
    """True when ``text`` is essentially a label/heading carrying no real fact."""
    cleaned = clean_creator_text(text)
    # Exact match against the known heading bank (handles "The real shift is here").
    if _label_norm(cleaned) in _KEYPOINT_LABEL_NORMS:
        return True
    stripped = _strip_keypoint_heading(cleaned).strip()
    if not stripped:
        return True
    if _label_norm(stripped) in _KEYPOINT_LABEL_NORMS:
        return True
    if _HEADING_RE.match(stripped):
        return True
    # A 1–4 word fragment that is only stopwords/labels is a heading, not a fact.
    words = re.findall(r"[A-Za-z0-9']+", stripped)
    if len(words) <= 4 and all(w.lower() in STOPWORDS for w in words):
        return True
    return False


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
    return [w.strip(".,;:!?") for w in raw if w.strip(".,;:!?")]


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
