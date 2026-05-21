"""summarizer.py — editorial-quality AI news summarizer.

The local summarizer produces structured, human-readable content in three
sections (What happened / Why it matters / What to watch next) rather than
just extracting raw sentences from scraped HTML.  Cookie consent text, legal
boilerplate, and newsletter noise are stripped before any content is used.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from .models import EmailItem, EmailSummary
from .article_enricher import ArticleData


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SKILL_PATH = PROJECT_ROOT / "skills" / "instagram-ai-news-summary-v2.md"

# ── Noise patterns stripped before any summarisation ─────────────────────────
_NOISE_PATTERNS = [
    r"https?://\S+",
    r"\bLink:\s*\d+\.?",
    r"\bImpact:\s*(LOW|MEDIUM|HIGH)\b",
    r"\bSource:\s*[A-Z][A-Za-z0-9&.\- ]{1,40}",
    r"\bRead more\b",
    r"\bSubscribe\b",
    r"\bUnsubscribe\b",
    r"\bView in browser\b",
    r"\bManage subscriptions?\b",
    r"\bEmail preferences\b",
    r"\bYou are receiving this\b.*",
    r"\bSent to you because\b.*",
    r"\bNo longer wish to receive\b.*",
    r"\bSelect your cookie preferences?\b.*",
    r"\bCustomize cookie preferences?\b.*",
    r"\bEssential cookies are necessary\b.*",
    r"\bYou may review and change your choices\b.*",
    r"\bCookie Notice\b.*",
    r"\bCookie preferences?\b.*",
    r"\bAccept all cookies\b.*",
    r"\bReject all cookies\b.*",
    r"\bWe use essential cookies\b.*",
    r"\bWe and our advertising partners\b.*",
    r"\bCookie settings\b.*",
    r"\bPrivacy [Pp]olicy\b.*",
    r"\bTerms of [Ss]ervice\b.*",
    r"\bAll rights reserved\b.*",
    r"\bCopyright ©?\s*\d{4}\b.*",
    r"\[…\].*?(?=\s{2,}|\Z)",
]

_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.I | re.S)

_BOILERPLATE_PHRASES = frozenset([
    "all rights reserved", "sign up for", "subscribe to",
    "use essential cookies", "advertising partners", "show you ads",
    "cookie settings", "manage cookies", "accept all cookies",
    "reject all cookies", "cookie policy", "privacy policy",
    "terms of service", "cookie preferences", "customize cookie",
    "essential cookies are necessary", "you may review and change",
    "cookie notice", "select your cookie", "gdpr", "ccpa",
    "opt out", "data protection", "third-party cookies",
    "tracking cookies", "functional cookies", "performance cookies",
    "analytics cookies", "marketing cookies", "view in browser",
    "unsubscribe", "manage subscriptions", "email preferences",
    "you are receiving this", "sent to you because",
    "no longer wish to receive", "read more", "click here",
    "learn more", "find out more", "see more", "show more",
])

STOP_WORDS = frozenset([
    "about", "after", "again", "against", "also", "among", "because",
    "before", "being", "between", "could", "first", "from", "have",
    "into", "more", "most", "news", "over", "said", "such", "than",
    "that", "their", "there", "these", "they", "this", "through",
    "under", "update", "updates", "were", "which", "while", "with", "would",
])

AI_TERMS = frozenset([
    "agent", "agents", "ai", "artificial", "automation", "benchmark",
    "chatbot", "chip", "coding", "compute", "data", "deep", "generation",
    "gpu", "inference", "intelligence", "language", "launch", "learning",
    "llm", "model", "models", "multimodal", "open-source", "reasoning",
    "release", "research", "robotics", "safety", "training", "video", "voice",
])

KNOWN_COMPANIES = [
    "OpenAI", "Google", "DeepMind", "Anthropic", "Microsoft", "Meta",
    "Apple", "Amazon", "AWS", "NVIDIA", "Intel", "AMD", "Tesla", "xAI",
    "Mistral", "Perplexity", "Hugging Face", "Cohere", "Stability AI",
    "Runway", "ElevenLabs", "Adobe", "Oracle", "IBM", "Salesforce",
]

COMPANY_SUFFIXES = frozenset([
    "AI", "Cloud", "Labs", "Lab", "Research", "Robotics", "Systems",
    "Technologies", "Technology", "Studio", "Studios", "Inc", "Corp",
    "Corporation", "LLC", "Ltd",
])

CAPITALIZED_BLOCKLIST = frozenset([
    "AI", "API", "GPU", "CPU", "LLM", "Early", "Analysts", "Developers",
    "Researchers", "Users", "Customers", "The", "This", "That", "New",
])

MODEL_PATTERNS = [
    r"\bGPT[- ]?\d+(?:\.\d+)?[A-Za-z-]*\b",
    r"\bClaude(?:\s+\d+(?:\.\d+)?)?[A-Za-z-]*\b",
    r"\bGemini(?:\s+\d+(?:\.\d+)?)?[A-Za-z-]*\b",
    r"\bLlama(?:\s+\d+(?:\.\d+)?)?[A-Za-z-]*\b",
    r"\bMistral(?:\s+\d+(?:\.\d+)?)?[A-Za-z-]*\b",
    r"\bGrok(?:\s+\d+(?:\.\d+)?)?[A-Za-z-]*\b",
    r"\bStable Diffusion(?:\s+\d+(?:\.\d+)?)?\b",
    r"\bSora\b",
    r"\bVeo(?:\s+\d+(?:\.\d+)?)?\b",
]

TOPIC_RULES = {
    "model release": {"launch", "launched", "release", "released", "unveil", "announced"},
    "funding or business": {"funding", "valuation", "revenue", "acquisition", "partnership"},
    "regulation or safety": {"regulation", "safety", "policy", "privacy", "lawsuit", "ban"},
    "developer tools": {"api", "sdk", "coding", "developer", "open-source", "github"},
    "hardware and compute": {"gpu", "chip", "compute", "training", "inference", "datacenter"},
    "media generation": {"image", "video", "voice", "audio", "music", "creative"},
}


# ── Action verbs that signal a real news event ────────────────────────────────
_ACTION_RE = re.compile(
    r"\b(launch(?:es|ed)?|release[sd]?|announc(?:es|ed|ing)|introduc(?:es|ed|ing)|"
    r"unveil(?:s|ed|ing)?|ship(?:s|ped|ping)?|open[- ]sourc(?:es|ed|ing)?|"
    r"partner(?:s|ed|ing)?|acqui(?:res|red|ring)?|rais(?:es|ed|ing)?|"
    r"deploy(?:s|ed|ing)?|integrat(?:es|ed|ing)?|updat(?:es|ed|ing)?|"
    r"expan(?:ds|ded|ding)?|enabl(?:es|ed|ing)?|allow(?:s|ed|ing)?)\b",
    re.I,
)

# ── Sentences that are almost certainly boilerplate ───────────────────────────
_BOILERPLATE_RE = re.compile(
    r"\b(cookie|gdpr|ccpa|unsubscribe|privacy policy|terms of service|"
    r"all rights reserved|copyright|read more|click here|learn more|"
    r"find out more|see more|show more|sign up|subscribe|view in browser|"
    r"manage subscriptions?|email preferences|sent to you because|"
    r"no longer wish to receive|advertising partners|show you ads)\b",
    re.I,
)


class SummaryProvider:
    def __init__(self, provider: str, ollama_url: str, ollama_model: str) -> None:
        self.provider = provider
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self._ollama_available: bool | None = None

    def summarize(
        self,
        email: EmailItem,
        article: ArticleData | None = None,
        articles: list[ArticleData] | None = None,
    ) -> EmailSummary:
        article_list = articles or ([article] if article else [])

        if article_list:
            # Build a clean pseudo-email body from the enriched article content
            combined_parts = []
            for idx, art in enumerate(article_list, start=1):
                parts = [
                    f"Article {idx} Title: {art.title}",
                    f"Article {idx} Description: {art.description}",
                    art.text,
                ]
                combined_parts.append("\n\n".join(p for p in parts if p and p.strip()))
            combined_body = "\n\n".join(combined_parts)
            pseudo_email = EmailItem(
                uid=email.uid,
                message_id=email.message_id,
                sender=email.sender,
                subject=email.subject,
                date=email.date,
                body=combined_body,
            )
            if self.provider in {"auto", "ollama"} and self._can_use_ollama():
                try:
                    return _with_article_fields(self._summarize_with_ollama(pseudo_email), article_list)
                except Exception:
                    if self.provider == "ollama":
                        raise
            return _with_article_fields(_summarize_article_list(pseudo_email, article_list), article_list)

        if _is_digest_subject(email.subject):
            return _with_article_fields(_summarize_digest_email(email), article_list)
        if self.provider in {"auto", "ollama"} and self._can_use_ollama():
            try:
                return _with_article_fields(self._summarize_with_ollama(email), article_list)
            except Exception:
                if self.provider == "ollama":
                    raise
        return _with_article_fields(summarize_locally(email), article_list)

    def _can_use_ollama(self) -> bool:
        if self.provider == "local":
            return False
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                self._ollama_available = resp.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            self._ollama_available = False
        return self._ollama_available

    def _summarize_with_ollama(self, email: EmailItem) -> EmailSummary:
        prompt = (
            "Return ONLY valid JSON with these exact keys: "
            "headline, what_happened, why_it_matters, what_to_watch, "
            "key_points, companies, models, topics, confidence.\n\n"
            f"Skill guide:\n{_load_summary_skill()}\n\n"
            "Rules:\n"
            "- headline: one punchy sentence, max 100 chars, names the real event.\n"
            "- what_happened: 2-3 sentences. What was announced/released/changed. "
            "  Name the company, product, model, or person. Include concrete details "
            "  (numbers, dates, API names, pricing, regions).\n"
            "- why_it_matters: 2-3 sentences. Practical impact on developers, "
            "  creators, companies, or AI users. No hype without evidence.\n"
            "- what_to_watch: 1-2 sentences. Next signal: rollout, adoption, "
            "  pricing, competition, limitations, benchmarks, or user reaction.\n"
            "- key_points: array of 4-6 short bullets derived from the article. "
            "  Each bullet must be a complete, specific sentence. No generic labels.\n"
            "- companies, models, topics: arrays of strings.\n"
            "- confidence: float 0-1.\n"
            "- Do NOT invent facts. If the article does not say it, omit it.\n"
            "- Do NOT include cookie consent text, legal boilerplate, or newsletter noise.\n\n"
            f"Subject: {email.subject}\nDate: {email.date}\nBody:\n{email.body[:6000]}"
        )
        payload = {
            "model": self.ollama_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": "You are an expert AI news editor writing for Instagram."},
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data.get("message", {}).get("content", "")
        parsed = _parse_json_object(content)
        # Compose a rich summary from the structured fields
        what_happened = _string(parsed.get("what_happened"))
        why_matters = _string(parsed.get("why_it_matters"))
        what_watch = _string(parsed.get("what_to_watch"))
        summary_text = " ".join(p for p in [what_happened, why_matters] if p)
        key_points = _string_list(parsed.get("key_points"))[:6]
        if not key_points:
            key_points = [p for p in [what_happened, why_matters, what_watch] if p]
        return EmailSummary(
            message_key=email.message_key,
            subject=email.subject,
            source_date=email.date,
            headline=_string(parsed.get("headline")) or _fallback_headline(email),
            summary=_trim(summary_text, 600) or summarize_locally(email).summary,
            key_points=key_points or summarize_locally(email).key_points,
            companies=_string_list(parsed.get("companies"))[:8],
            models=_string_list(parsed.get("models"))[:8],
            topics=_string_list(parsed.get("topics"))[:8],
            confidence=_float(parsed.get("confidence"), 0.8),
        )


def _load_summary_skill() -> str:
    try:
        return SUMMARY_SKILL_PATH.read_text(encoding="utf-8")[:3500]
    except OSError:
        return (
            "Summarize the linked article in a human AI-news editor voice. "
            "Cover what happened, why it matters, and what to watch next. "
            "Use concrete article details. Avoid generic category labels."
        )


# ── Core local summariser ─────────────────────────────────────────────────────

def summarize_locally(email: EmailItem) -> EmailSummary:
    """Produce a structured summary from raw email text without an LLM."""
    text = _clean_text(f"{email.subject}. {email.body}")
    if _is_digest_subject(email.subject):
        return _summarize_digest_email(email)
    sentences = _good_sentences(text)
    if not sentences:
        sentences = [_trim(email.subject or "AI update", 220)]
    companies = _find_companies(text)
    models = _find_models(text)
    topics = _find_topics(text)
    headline = _build_headline(email.subject, companies, models)
    # Rank and pick the best sentences
    ranked = _rank_sentences(sentences)
    top = [sentences[i] for i, _ in ranked[:6]]
    key_points = [_trim(s, 220) for s in top[:5]]
    if len(key_points) < 3:
        key_points += [_trim(s, 220) for s in sentences if _trim(s, 220) not in key_points][:3 - len(key_points)]
    summary = " ".join(top[:2])
    return EmailSummary(
        message_key=email.message_key,
        subject=email.subject,
        source_date=email.date,
        headline=headline,
        summary=_trim(summary, 500),
        key_points=key_points[:5],
        companies=companies,
        models=models,
        topics=topics,
        confidence=0.60 if email.body else 0.30,
    )


def _summarize_article_list(email: EmailItem, articles: list[ArticleData]) -> EmailSummary:
    """Build a structured summary from enriched article data."""
    base = summarize_locally(email)
    if not articles:
        return base
    article = articles[0]
    title = _clean_text(article.title or email.subject or "AI update")
    # Build the three narrative sections from the article text
    what_happened, why_matters, what_watch = _extract_narrative_sections(article, title)
    key_points = _extract_key_points(article, title)
    summary_text = " ".join(p for p in [what_happened, why_matters] if p) or base.summary
    headline = _trim(title, 110) if title else base.headline
    return EmailSummary(
        message_key=email.message_key,
        subject=email.subject,
        source_date=email.date,
        headline=headline,
        summary=_trim(summary_text, 600),
        key_points=key_points or base.key_points,
        companies=base.companies or _find_companies(article.text or ""),
        models=base.models or _find_models(article.text or ""),
        topics=base.topics or _find_topics(article.text or ""),
        confidence=0.82,
    )


def _extract_narrative_sections(article: ArticleData, title: str) -> tuple[str, str, str]:
    """Extract what-happened / why-it-matters / what-to-watch from article text."""
    text = _clean_text(f"{article.description} {article.text}")
    sentences = _good_sentences(text)
    if not sentences:
        desc = _clean_text(article.description or article.excerpt or title)
        return desc, "", ""
    ranked = _rank_sentences(sentences)
    top_sentences = [sentences[i] for i, _ in ranked[:10]]
    # What happened: action sentences with concrete details
    action_sentences = [s for s in top_sentences if _ACTION_RE.search(s)]
    detail_sentences = [s for s in top_sentences if re.search(r"\b\d+\b", s)]
    what_happened_parts = _dedupe_sentences(action_sentences[:2] + detail_sentences[:1])
    if not what_happened_parts:
        what_happened_parts = top_sentences[:2]
    what_happened = " ".join(what_happened_parts[:2])
    # Why it matters: impact/benefit sentences
    impact_sentences = [
        s for s in top_sentences
        if re.search(r"\b(allow|enable|help|mean|impact|benefit|improve|change|"
                     r"developer|user|customer|team|company|creator|platform)\b", s, re.I)
        and s not in what_happened_parts
    ]
    why_matters = " ".join(impact_sentences[:2]) if impact_sentences else ""
    # What to watch: forward-looking sentences
    watch_sentences = [
        s for s in top_sentences
        if re.search(r"\b(next|future|plan|expect|watch|rollout|adopt|pricing|"
                     r"competition|limit|benchmark|reaction|availab)\b", s, re.I)
        and s not in what_happened_parts and s not in impact_sentences
    ]
    what_watch = watch_sentences[0] if watch_sentences else ""
    return (
        _trim(what_happened, 500),
        _trim(why_matters, 400),
        _trim(what_watch, 300),
    )


def _extract_key_points(article: ArticleData, title: str) -> list[str]:
    """Extract 4-6 specific, clean bullet points from article content."""
    text = _clean_text(f"{article.description} {article.text}")
    sentences = _good_sentences(text)
    if not sentences:
        return [_trim(article.description or title, 220)] if (article.description or title) else []
    ranked = _rank_sentences(sentences)
    candidates = [sentences[i] for i, _ in ranked[:12]]
    points: list[str] = []
    seen: set[str] = set()
    for s in candidates:
        key = re.sub(r"\s+", " ", s).lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        points.append(_trim(s, 220))
        if len(points) >= 6:
            break
    return points


def _summarize_digest_email(email: EmailItem) -> EmailSummary:
    text = _clean_text(f"{email.subject}. {email.body}")
    companies = _find_companies(text)
    models = _find_models(text)
    topics = _find_topics(text)
    sources = _extract_subject_sources(email.subject)
    count_text = _extract_count_text(email.subject)
    subject = _trim(email.subject, 110)
    source_line = ", ".join(sources[:4]) if sources else "tracked AI sources"
    entity_line = ", ".join([*companies[:2], *models[:2]]) or source_line
    # Build real sentences from the email body instead of generic placeholders
    sentences = _good_sentences(text)
    ranked = _rank_sentences(sentences) if sentences else []
    top = [sentences[i] for i, _ in ranked[:4]] if ranked else []
    if top:
        key_points = [_trim(s, 220) for s in top[:4]]
    else:
        key_points = [
            f"Covers {count_text or 'multiple AI'} updates from {source_line}.",
            f"Key entities: {entity_line}.",
        ]
        if topics:
            key_points.append(f"Topics covered: {', '.join(topics[:3])}.")
    summary = (
        f"AI digest from {source_line} covering {count_text or 'multiple'} updates "
        f"across launches, model releases, developer tools, and market signals."
    )
    return EmailSummary(
        message_key=email.message_key,
        subject=email.subject,
        source_date=email.date,
        headline=subject,
        summary=_trim(summary, 480),
        key_points=key_points[:5],
        companies=companies,
        models=models,
        topics=topics,
        confidence=0.70,
    )


# ── Text cleaning ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Strip all noise, boilerplate, and cookie consent from raw text."""
    text = re.sub(r"\r\n?", "\n", text or "")
    text = _NOISE_RE.sub(" ", text)
    text = text.replace("\u2014", " - ").replace("\u00b7", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _good_sentences(text: str) -> list[str]:
    """Split text into clean, content-bearing sentences, filtering all noise."""
    raw = re.split(r"(?<=[.!?])\s+|\n+", text)
    result: list[str] = []
    for s in raw:
        s = s.strip()
        if len(s) < 40 or len(s) > 800:
            continue
        if _BOILERPLATE_RE.search(s):
            continue
        lowered = s.lower()
        if any(phrase in lowered for phrase in _BOILERPLATE_PHRASES):
            continue
        # Skip sentences that are mostly punctuation/numbers
        if re.fullmatch(r"[\W\d\s]+", s):
            continue
        result.append(s)
    return result


def _dedupe_sentences(sentences: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in sentences:
        key = re.sub(r"\s+", " ", s).lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


# ── Sentence ranking ──────────────────────────────────────────────────────────

def _rank_sentences(sentences: list[str]) -> list[tuple[int, float]]:
    if not sentences:
        return []
    tokens_all = _tokens(" ".join(sentences))
    freq = Counter(tokens_all)
    max_f = max(freq.values()) if freq else 1
    norm = {t: c / max_f for t, c in freq.items()}
    scored: list[tuple[int, float]] = []
    for i, s in enumerate(sentences):
        toks = _tokens(s)
        if not toks:
            scored.append((i, 0.0))
            continue
        base = sum(norm.get(t, 0.0) for t in toks) / len(toks)
        ai_boost = sum(0.08 for t in toks if t in AI_TERMS)
        num_boost = 0.12 if re.search(r"\b\d+(?:\.\d+)?%?\b", s) else 0.0
        action_boost = 0.15 if _ACTION_RE.search(s) else 0.0
        len_penalty = 0.10 if len(s) > 350 else 0.0
        scored.append((i, base + ai_boost + num_boost + action_boost - len_penalty))
    return sorted(scored, key=lambda x: x[1], reverse=True)


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text.lower())
    return [w for w in words if w not in STOP_WORDS]


# ── Entity extraction ─────────────────────────────────────────────────────────

def _find_companies(text: str) -> list[str]:
    found: list[str] = []
    for company in KNOWN_COMPANIES:
        if re.search(rf"\b{re.escape(company)}\b", text, re.I):
            found.append(company)
    for phrase in re.findall(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,2}\b", text):
        phrase = phrase.strip()
        words = phrase.split()
        if phrase in found or phrase in CAPITALIZED_BLOCKLIST:
            continue
        if len(words) == 1:
            continue
        if words[-1].strip(".,") not in COMPANY_SUFFIXES:
            continue
        if any(w.lower() in {"model", "models", "api", "agent", "agents"} for w in words):
            continue
        if len(phrase) >= 3:
            found.append(phrase)
        if len(found) >= 8:
            break
    return found[:8]


def _find_models(text: str) -> list[str]:
    found: list[str] = []
    for pattern in MODEL_PATTERNS:
        for match in re.findall(pattern, text, flags=re.I):
            model = match.strip()
            if model and model.lower() not in {m.lower() for m in found}:
                found.append(model)
    return found[:8]


def _find_topics(text: str) -> list[str]:
    toks = set(_tokens(text))
    topics = [topic for topic, words in TOPIC_RULES.items() if toks.intersection(words)]
    return topics[:8] or ["general AI update"]


# ── Headline / subject helpers ────────────────────────────────────────────────

def _build_headline(subject: str, companies: list[str], models: list[str]) -> str:
    if subject and subject != "(no subject)" and len(subject.strip()) >= 20:
        return _trim(subject, 110)
    entity = companies[0] if companies else models[0] if models else "AI"
    return f"{entity} update"


def _fallback_headline(email: EmailItem) -> str:
    return _trim(email.subject or "AI update", 120)


def _is_digest_subject(subject: str) -> bool:
    return bool(re.search(r"\bAI\s+(Alert|Digest|Updates)\b", subject, flags=re.I))


def _extract_subject_sources(subject: str) -> list[str]:
    if "\u2014" in subject:
        tail = subject.split("\u2014", 1)[1]
    elif "-" in subject:
        tail = subject.rsplit("-", 1)[1]
    else:
        return []
    tail = re.sub(r"\([^)]*\)", "", tail)
    return [
        item.strip()
        for item in re.split(r",|/|\|", tail)
        if item.strip() and not re.search(r"\b\d+\s+updates?\b", item, flags=re.I)
    ][:6]


def _extract_count_text(subject: str) -> str:
    counts = re.findall(r"\b\d+\s+(?:new\s+)?(?:launches?|updates?)\b", subject, flags=re.I)
    if not counts:
        m = re.search(r"\|\s*(\d+)\s+updates?\s*[\u00b7-]\s*(\d+)\s+launches?", subject, flags=re.I)
        if m:
            return f"{m.group(1)} updates and {m.group(2)} launches"
        return ""
    return " and ".join(counts[:2]).lower()


# ── Article field merging ─────────────────────────────────────────────────────

def _with_article_fields(summary: EmailSummary, articles: list[ArticleData] | None) -> EmailSummary:
    if not articles:
        return summary
    article = articles[0]
    article_items = [_article_item_for_instagram(art) for art in articles]
    headline = summary.headline
    if article.title and (not headline or _is_digest_subject(headline)):
        headline = _trim(article.title, 110)
    # Use the best available summary text
    summary_text = summary.summary
    if article.description and len(article.description) > len(summary_text):
        summary_text = _trim(_clean_text(article.description), 600)
    # Merge key points — prefer article-derived points over generic placeholders
    merged: list[str] = []
    seen: set[str] = set()
    for item in article_items:
        for pt in item.get("key_points", []):
            cleaned = _clean_text(pt)
            key = re.sub(r"\s+", " ", cleaned).lower()[:60]
            if cleaned and key not in seen and len(cleaned) > 20:
                if not any(p in cleaned.lower() for p in ("tracks new", "best posting angle", "primary entities", "likely content themes")):
                    seen.add(key)
                    merged.append(cleaned)
    final_points = merged[:6] if merged else summary.key_points
    return EmailSummary(
        message_key=summary.message_key,
        subject=summary.subject,
        source_date=summary.source_date,
        headline=headline,
        summary=summary_text,
        key_points=final_points,
        companies=summary.companies,
        models=summary.models,
        topics=summary.topics,
        confidence=max(summary.confidence, 0.78),
        article_url=article.url,
        article_title=article.title,
        article_image_path=article.image_path,
        article_image_url=article.image_url,
        article_excerpt=article.excerpt,
        article_items=article_items,
    )


def _article_item_for_instagram(article: ArticleData) -> dict[str, Any]:
    what_happened, why_matters, what_watch = _extract_narrative_sections(
        article, article.title or ""
    )
    key_points = _extract_key_points(article, article.title or "")
    # Build a clean summary from the narrative sections
    summary_parts = [p for p in [what_happened, why_matters] if p]
    summary_text = " ".join(summary_parts) or _clean_text(article.description or article.excerpt or article.title or "")
    return {
        "url": article.url,
        "title": article.title,
        "description": _clean_text(article.description),
        "excerpt": _clean_text(article.excerpt),
        "summary": _trim(summary_text, 1200),
        "what_happened": what_happened,
        "why_matters": why_matters,
        "what_to_watch": what_watch,
        "key_points": key_points,
        "image_path": article.image_path,
        "image_url": article.image_url,
    }


# ── Utility ───────────────────────────────────────────────────────────────────

def _trim(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" -\t\r\n")
    if len(value) <= limit:
        return value
    trimmed = value[:limit - 3].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{trimmed}..."


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


# Keep backward-compat alias used by agent.py
_trim_sentence = _trim
