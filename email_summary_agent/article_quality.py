from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

from .ig_constants import REFERENCE_BRANDS


AI_RELEVANCE_TERMS = (
    "ai", "artificial intelligence", "agent", "agents", "llm", "model",
    "models", "machine learning", "deep learning", "neural", "inference",
    "training", "gpu", "chip", "chatbot", "automation", "robot", "robotics",
    "claude", "gemini", "gpt", "openai", "anthropic", "mistral", "llama",
    "groq", "nvidia", "sagemaker", "codex", "copilot", "rag",
)

PROMO_OR_NON_ARTICLE_PATTERNS = (
    r"\bearly bird\b",
    r"\bdiscount\b",
    r"\bsavings?\b",
    r"\bbuy tickets?\b",
    r"\bregister now\b",
    r"\bcovered live\b",
    r"\bcoverage deliver",
    r"\bstrictlyvc\b",
    r"\bdisrupt\b",
    r"\bequitypod\b",
    r"\ball about agents\b",
    r"\bfollow (?:us )?(?:on )?x\b",
    r"\bfollow .*threads\b",
    r"\bsubscribe\b",
    r"\bnewsletter\b",
    r"\bpodcast\b",
)

NOISE_PHRASES = (
    "for more details, visit",
    "query met quiet",
    "lost page, still warm light",
    "soft signs lean toward the next path",
    "step in, make it yours",
    "only blank but well lit space",
    "bring your best question",
    "are you a robot",
    "access to this page has been denied",
    "json.stringify",
    "__uspapi",
    "cmpcall",
    "escape will cancel and close the window",
    "beginning of dialog window",
    "connect with us",
    "advertising partners",
    "personalize your",
    "breaking ai update",
)

CODE_OR_MARKUP_PATTERNS = (
    r"\bJSON\.(?:stringify|parse)\b",
    r"\b__uspapi\b",
    r"\b(?:cmpCall|gdprApplies|consentData|privacyManager)\b",
    r"\btypeof\s+[_A-Za-z$][\w$]*\s*(?:==|===|!==|!=)",
    r"\bcatch\s*\([^)]*\)\s*\{",
    r"\bfunction\s*\(",
    r"\b(?:push|splice|slice|map|forEach)\s*\(",
    r"[{}]{2,}",
    r"&#x?[0-9a-f]+;",
    r"&amp;#x?[0-9a-f]+;",
    r"\bLink\s*:\s*\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]",
    r"\bCompany\s*:\s*[A-Za-z0-9 .&-]+\s+Summary\s*:",
    r"^\s*\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]\s+",
    r"^\s*(?:HIGH|MEDIUM|LOW|CRITICAL)\s*:\s+",
    r"^\s*[a-z]{1,3}\s*:\s*[A-Z][A-Za-z0-9 .&-]+",
)


def clean_quality_text(text: str) -> str:
    cleaned = html.unescape(str(text or ""))
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\u2019", "'").replace("\u2018", "'")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def contains_public_noise(text: str) -> bool:
    cleaned = clean_quality_text(text)
    lowered = cleaned.lower()
    if any(phrase in lowered for phrase in NOISE_PHRASES):
        return True
    if any(re.search(pattern, cleaned, re.I) for pattern in CODE_OR_MARKUP_PATTERNS):
        return True
    if len(re.findall(r"\bLink\s*:", cleaned, re.I)) >= 2:
        return True
    if len(re.findall(r"\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]", cleaned, re.I)) >= 2:
        return True
    if len(re.findall(r"\b(?:Company|Summary)\s*:", cleaned, re.I)) >= 3:
        return True
    return False


def is_publishable_article(article: dict, *, _debug_tag: str = "") -> bool:
    title = clean_quality_text(str(article.get("title") or ""))
    body = clean_quality_text(" ".join(
        str(article.get(key) or "")
        for key in ("description", "excerpt", "summary", "text", "scraped_content")
    ))
    url = str(article.get("url") or "")
    tag = f"  [quality:{_debug_tag}]" if _debug_tag else "  [quality]"

    # --- Hard rejects (no valid URL) ---
    if not url.startswith(("http://", "https://")):
        print(f"{tag} REJECTED {title[:60]!r}: url={url[:40]!r} no http prefix")
        return False

    # --- Title noise check (unsalvageable) ---
    if contains_public_noise(title):
        print(f"{tag} REJECTED {title[:60]!r}: title contains noise patterns")
        return False
    if _title_is_truncated_fragment(title):
        print(f"{tag} REJECTED {title[:60]!r}: title is a truncated fragment")
        return False

    # --- Promo patterns: check title only (body is email context noise) ---
    if any(re.search(pattern, title, re.I) for pattern in PROMO_OR_NON_ARTICLE_PATTERNS):
        print(f"{tag} REJECTED {title[:60]!r}: title has promo pattern")
        return False
    if _body_has_digest_fragment_noise(body):
        print(f"{tag} REJECTED {title[:60]!r}: body contains newsletter fragment noise")
        return False

    # --- All checks below are for email-fallback articles ---
    # The slide builder re-scrapes the URL and gets real content.
    # Email placeholder text quality is irrelevant.
    # Accept unconditionally if URL is valid and title is clean.
    return True


def _body_has_digest_fragment_noise(body: str) -> bool:
    """Reject newsletter rows that were parsed as articles.

    A real article body can mention companies, summaries, pricing, or links.
    The malformed rows from alert emails have dense ``Link : [HIGH]``,
    ``Company :`` and ``Summary :`` markers in one short fragment; those are
    not article text and consistently generate duplicate/noisy slides.
    """
    if not body:
        return False
    if contains_public_noise(body):
        return True
    markers = (
        len(re.findall(r"\bLink\s*:", body, re.I))
        + len(re.findall(r"\[(?:HIGH|MEDIUM|LOW|CRITICAL)\]", body, re.I))
        + len(re.findall(r"\b(?:Company|Summary)\s*:", body, re.I))
    )
    return markers >= 2


def _title_is_url_slug(title: str) -> bool:
    if not title:
        return True
    lowered = title.lower()
    if "/" in title or "\\" in title:
        return True
    if re.search(r"\b[a-z0-9-]+/[a-z0-9-]+", lowered):
        return True
    words = title.split()
    hyphenated = sum(1 for word in words if "-" in word)
    if len(words) <= 5 and hyphenated >= 2:
        return True
    if len(title) > 12 and title.count("-") >= max(3, title.count(" ") + 2):
        return True
    return False


def _title_is_truncated_fragment(title: str) -> bool:
    """Return True only when the title is genuinely a truncated fragment.

    This is intentionally permissive — most lowercase-starting titles from
    digest emails are legitimate ("how to…", "the new…", "what happens when…").
    We only reject titles with clear truncation signals.
    """
    if not title:
        return True
    text = title.strip()
    words = text.split()
    if not words:
        return True
    # Ends with trailing ellipsis or punctuation that suggests mid-sentence cut-off
    if re.search(r"[a-z][)]?\.\.\.$", text):
        return True
    # Ends mid-word with a dash (e.g. "launching new product fea-")
    if re.search(r"[a-zA-Z]-$", text):
        return True
    # Too short and doesn't look like a real title (1-2 words, all lowercase, no proper nouns)
    if len(words) <= 2:
        lowered = text.lower()
        # Accept if it contains any uppercase letter (likely a proper noun in digest titles)
        if any(c.isupper() for c in text):
            return False
        # Accept common 2-word lowercase starters that are legitimate titles
        common_starters = {
            "how to", "what is", "what are", "why is", "why are", "when is",
            "the new", "the next", "the rise", "the end", "the future",
            "inside the", "inside a",
            "this is", "this new",
            "meet the", "meet your",
            "is your", "is the",
            "can ai", "will ai",
        }
        if len(words) == 2 and " ".join(words).lower() in common_starters:
            return False
        # If 1-2 words, all lowercase, it's likely just a fragment — reject
        if not lowered.startswith(("ai", "gpt", "llm")):
            return True
        return False
    if re.match(r"^[a-z]{1,4}\s*:", text):
        return True
    if re.match(r"^(?:e|eed|ill|ny|tion|ntelligence)\b", text, re.I):
        return True
    if re.search(r"\btop\s+[A-Z]\s*$", text):
        return True
    if re.search(r"\b(?:\w+ing|\w+ed|\w+ion|capacity)\.$", text) and text[:1].islower() and len(words) <= 8:
        return True
    return False


def _has_ai_relevance(combined: str) -> bool:
    if any(term in combined for term in AI_RELEVANCE_TERMS):
        return True
    return any(brand.lower() in combined for brand in REFERENCE_BRANDS)


def source_domain(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""
