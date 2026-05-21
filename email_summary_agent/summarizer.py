from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from .models import EmailItem, EmailSummary
from .article_enricher import ArticleData


STOP_WORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "among",
    "because",
    "before",
    "being",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
    "more",
    "most",
    "news",
    "over",
    "said",
    "such",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "update",
    "updates",
    "were",
    "which",
    "while",
    "with",
    "would",
}

AI_TERMS = {
    "agent",
    "agents",
    "ai",
    "artificial",
    "automation",
    "benchmark",
    "chatbot",
    "chip",
    "coding",
    "compute",
    "data",
    "deep",
    "generation",
    "gpu",
    "inference",
    "intelligence",
    "language",
    "launch",
    "learning",
    "llm",
    "model",
    "models",
    "multimodal",
    "open-source",
    "reasoning",
    "release",
    "research",
    "robotics",
    "safety",
    "training",
    "video",
    "voice",
}

KNOWN_COMPANIES = [
    "OpenAI",
    "Google",
    "DeepMind",
    "Anthropic",
    "Microsoft",
    "Meta",
    "Apple",
    "Amazon",
    "AWS",
    "NVIDIA",
    "Intel",
    "AMD",
    "Tesla",
    "xAI",
    "Mistral",
    "Perplexity",
    "Hugging Face",
    "Cohere",
    "Stability AI",
    "Runway",
    "ElevenLabs",
    "Adobe",
    "Oracle",
    "IBM",
    "Salesforce",
]

COMPANY_SUFFIXES = {
    "AI",
    "Cloud",
    "Labs",
    "Lab",
    "Research",
    "Robotics",
    "Systems",
    "Technologies",
    "Technology",
    "Studio",
    "Studios",
    "Inc",
    "Corp",
    "Corporation",
    "LLC",
    "Ltd",
}

CAPITALIZED_BLOCKLIST = {
    "AI",
    "API",
    "GPU",
    "CPU",
    "LLM",
    "Early",
    "Analysts",
    "Developers",
    "Researchers",
    "Users",
    "Customers",
    "The",
    "This",
    "That",
    "New",
}

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

        # If we have full article content from linked pages, prioritize summarizing that
        if article_list:
            # Create a synthetic 'email' that contains the full article text for better summary
            combined_parts = []
            for idx, art in enumerate(article_list, start=1):
                combined_parts.append(
                    "\n\n".join(
                        part
                        for part in [
                            f"Article {idx} Title: {art.title}",
                            f"Article {idx} Description: {art.description}",
                            f"Article {idx} Excerpt: {art.excerpt}",
                            art.text,
                        ]
                        if part and part.strip()
                    )
                )
            combined_body = "\n\n".join(combined_parts)
            pseudo_email = EmailItem(
                uid=email.uid,
                message_id=email.message_id,
                sender=email.sender,
                subject=email.subject,
                date=email.date,
                body=combined_body,
            )
            # Use Ollama when available, otherwise local summarizer on the full article text
            if self.provider in {"auto", "ollama"} and self._can_use_ollama():
                try:
                    return _with_article_fields(self._summarize_with_ollama(pseudo_email), article_list)
                except Exception:
                    if self.provider == "ollama":
                        raise
            return _with_article_fields(summarize_locally(pseudo_email), article_list)

        # Fallback: no linked article content — summarize email as before
        if _is_digest_subject(email.subject):
            return _with_article_fields(summarize_locally(email), article_list)
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
            request = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=1.5) as response:
                self._ollama_available = response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            self._ollama_available = False
        return self._ollama_available

    def _summarize_with_ollama(self, email: EmailItem) -> EmailSummary:
        prompt = f"""
Return only JSON with these exact keys:
headline, summary, key_points, companies, models, topics, confidence.

Rules:
- Summarize the AI news in plain English for a faceless Instagram news workflow.
- key_points must be 3 to 5 short bullets.
- companies, models, and topics must be arrays of strings.
- confidence must be a number from 0 to 1.
- Do not invent facts that are not in the email.

Subject: {email.subject}
Date: {email.date}
Body:
{email.body[:6000]}
""".strip()
        payload = {
            "model": self.ollama_model,
            "stream": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": "You summarize AI news emails into compact structured JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))

        content = data.get("message", {}).get("content", "")
        parsed = _parse_json_object(content)
        return EmailSummary(
            message_key=email.message_key,
            subject=email.subject,
            source_date=email.date,
            headline=_string(parsed.get("headline")) or _fallback_headline(email),
            summary=_string(parsed.get("summary")) or summarize_locally(email).summary,
            key_points=_string_list(parsed.get("key_points"))[:5]
            or summarize_locally(email).key_points,
            companies=_string_list(parsed.get("companies"))[:8],
            models=_string_list(parsed.get("models"))[:8],
            topics=_string_list(parsed.get("topics"))[:8],
            confidence=_float(parsed.get("confidence"), 0.7),
        )


def summarize_locally(email: EmailItem) -> EmailSummary:
    text = _normalize_text(f"{email.subject}. {_clean_newsletter_noise(email.body)}")
    if _is_digest_subject(email.subject):
        return _summarize_digest_email(email, text)
    sentences = _split_sentences(text)
    if not sentences:
        sentences = [email.subject or "No readable email body was found."]

    ranked = _rank_sentences(sentences)
    chosen_indexes = sorted(index for index, _score in ranked[:5])
    chosen = [sentences[index] for index in chosen_indexes]
    key_points = [_trim_sentence(sentence, 220) for sentence in chosen[:5]]
    if len(key_points) < 3:
        key_points = _expand_key_points(key_points, sentences)

    companies = _find_companies(text)
    models = _find_models(text)
    topics = _find_topics(text)
    headline = _build_headline(email.subject, companies, models, key_points)
    summary = " ".join(key_points[:2])

    return EmailSummary(
        message_key=email.message_key,
        subject=email.subject,
        source_date=email.date,
        headline=headline,
        summary=_trim_sentence(summary, 480),
        key_points=key_points,
        companies=companies,
        models=models,
        topics=topics,
        confidence=0.62 if email.body else 0.35,
    )


def _summarize_digest_email(email: EmailItem, text: str) -> EmailSummary:
    companies = _find_companies(text)
    models = _find_models(text)
    topics = _find_topics(text)
    sources = _extract_subject_sources(email.subject)
    count_text = _extract_count_text(email.subject)
    subject = _trim_sentence(email.subject, 110)
    source_line = ", ".join(sources[:4]) if sources else "the tracked AI sources"
    entity_line = ", ".join([*companies[:2], *models[:2]]) or source_line

    if "digest" in email.subject.lower():
        headline = subject
        summary = f"A daily AI digest covering {count_text or 'multiple'} updates across launches, model releases, developer tools, and market signals."
        key_points = [
            f"Covers {count_text or 'multiple AI'} updates from {source_line}.",
            f"Best posting angle: turn the biggest launch or model update into a quick creator briefing.",
            f"Primary entities to watch: {entity_line}.",
        ]
    else:
        headline = subject
        summary = f"A launch alert from {source_line}, useful for spotting fresh AI products, model upgrades, and developer tools before they become mainstream."
        key_points = [
            f"Tracks {count_text or 'new'} AI launch activity from {source_line}.",
            f"Best posting angle: explain what changed, who it helps, and why creators should care.",
            f"Primary entities to watch: {entity_line}.",
        ]

    if topics:
        key_points.append(f"Likely content themes: {', '.join(topics[:3])}.")

    return EmailSummary(
        message_key=email.message_key,
        subject=email.subject,
        source_date=email.date,
        headline=headline,
        summary=_trim_sentence(summary, 480),
        key_points=key_points[:5],
        companies=companies,
        models=models,
        topics=topics,
        confidence=0.72,
    )


def _rank_sentences(sentences: list[str]) -> list[tuple[int, float]]:
    tokens = _tokens(" ".join(sentences))
    frequencies = Counter(tokens)
    if not frequencies:
        return [(index, 0.0) for index, _sentence in enumerate(sentences)]
    max_frequency = max(frequencies.values())
    normalized = {token: count / max_frequency for token, count in frequencies.items()}

    scored: list[tuple[int, float]] = []
    for index, sentence in enumerate(sentences):
        sentence_tokens = _tokens(sentence)
        if not sentence_tokens:
            scored.append((index, 0.0))
            continue
        base = sum(normalized.get(token, 0.0) for token in sentence_tokens) / len(sentence_tokens)
        ai_boost = sum(1 for token in sentence_tokens if token in AI_TERMS) * 0.08
        number_boost = 0.1 if re.search(r"\b\d+(?:\.\d+)?%?\b", sentence) else 0.0
        action_boost = 0.12 if re.search(r"\b(launch|release|announce|raise|partner|ban|open-source|ship)\w*\b", sentence, re.I) else 0.0
        length_penalty = 0.12 if len(sentence) > 360 else 0.0
        scored.append((index, base + ai_boost + number_boost + action_boost - length_penalty))

    return sorted(scored, key=lambda item: item[1], reverse=True)


def _split_sentences(text: str) -> list[str]:
    candidates = re.split(r"(?<=[.!?])\s+|\n+|(?=\b[A-Z][A-Za-z0-9&.-]{2,}\s+(?:launches|released|announced|adds|raises|partners|opens)\b)", text)
    sentences = [
        _trim_sentence(candidate, 420)
        for candidate in candidates
        if 40 <= len(candidate.strip()) <= 900 and not _is_low_value_sentence(candidate)
    ]
    return sentences


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text.lower())
    return [word for word in words if word not in STOP_WORDS]


def _normalize_text(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("\u2014", " - ").replace("\u00b7", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_newsletter_noise(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\bLink:\s*\d+\.?", " ", text, flags=re.I)
    text = re.sub(r"\bImpact:\s*(LOW|MEDIUM|HIGH)\b", " ", text, flags=re.I)
    text = re.sub(r"\bSource:\s*([A-Z][A-Za-z0-9&.\- ]{1,40})", " ", text)
    text = re.sub(r"\bRead more\b|\bSubscribe\b|\bUnsubscribe\b|\bView in browser\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_low_value_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    if len(sentence.strip()) < 40:
        return True
    noisy_terms = {
        "unsubscribe",
        "view in browser",
        "privacy policy",
        "copyright",
        "use essential cookies",
        "advertising partners",
        "show you ads",
        "cookie settings",
        "accept all cookies",
        "reject all cookies",
        "terms of service",
    }
    if any(term in lowered for term in noisy_terms):
        return True
    return bool(re.fullmatch(r"(source|impact|link|low|medium|high|\d+|[\W_])+", lowered.strip()))


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
        if any(word.lower() in {"model", "models", "api", "agent", "agents"} for word in words):
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
            if model and model.lower() not in {item.lower() for item in found}:
                found.append(model)
    return found[:8]


def _find_topics(text: str) -> list[str]:
    tokens = set(_tokens(text))
    topics = [
        topic
        for topic, words in TOPIC_RULES.items()
        if tokens.intersection(words)
    ]
    return topics[:8] or ["general AI update"]


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
        launches = re.search(r"\|\s*(\d+)\s+updates?\s*[\u00b7-]\s*(\d+)\s+launches?", subject, flags=re.I)
        if launches:
            return f"{launches.group(1)} updates and {launches.group(2)} launches"
        return ""
    return " and ".join(counts[:2]).lower()


def _build_headline(
    subject: str,
    companies: list[str],
    models: list[str],
    key_points: list[str],
) -> str:
    if subject and subject != "(no subject)":
        subject = _trim_sentence(subject, 110)
        if len(subject) >= 20:
            return subject
    entity = companies[0] if companies else models[0] if models else "AI"
    if key_points:
        return _trim_sentence(f"{entity}: {key_points[0]}", 120)
    return f"{entity} update"


def _fallback_headline(email: EmailItem) -> str:
    return _trim_sentence(email.subject or "AI update", 120)


def _expand_key_points(points: list[str], sentences: list[str]) -> list[str]:
    expanded = list(points)
    for sentence in sentences:
        point = _trim_sentence(sentence, 220)
        if point not in expanded:
            expanded.append(point)
        if len(expanded) >= 3:
            break
    while len(expanded) < 3:
        expanded.append("The email did not include enough readable detail for a stronger summary.")
    return expanded[:5]


def _trim_sentence(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -\t\r\n")
    if len(value) <= limit:
        return value
    trimmed = value[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:")
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


def _with_article_fields(summary: EmailSummary, articles: list[ArticleData] | None) -> EmailSummary:
    if not articles:
        return summary
    article = articles[0]
    article_items = [_article_item_for_instagram(item) for item in articles]
    headline = summary.headline
    if article.title and (not headline or _is_digest_subject(headline)):
        headline = _trim_sentence(article.title, 110)
    summary_text = article_items[0].get("summary", summary.summary)
    if article.description and len(article.description) > len(summary_text):
        summary_text = _trim_sentence(article.description, 700)

    # Build rich key points from the articles themselves instead of generic placeholders
    merged_points = []
    for item in article_items:
        points = item.get("key_points", [])
        for pt in points:
            cleaned = _normalize_text(pt)
            if cleaned and cleaned not in merged_points and not _is_low_value_sentence(cleaned):
                lowered = cleaned.lower()
                # Exclude noisy placeholders
                if not any(prefix in lowered for prefix in ("tracks new", "best posting angle", "primary entities", "likely content themes")):
                    merged_points.append(cleaned)
                    
    final_points = merged_points[:5] if merged_points else summary.key_points

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
    summary, points = _human_article_summary(article)
    return {
        "url": article.url,
        "title": article.title,
        "description": article.description,
        "excerpt": article.excerpt,
        "summary": summary,
        "key_points": points,
        "image_path": article.image_path,
        "image_url": article.image_url,
    }


def _human_article_summary(article: ArticleData) -> tuple[str, list[str]]:
    source = _normalize_text(" ".join(part for part in [article.description, article.text] if part))
    sentences = [sentence for sentence in _split_sentences(source) if not _is_low_value_sentence(sentence)]
    if not sentences:
        fallback = article.description or article.excerpt or article.title or "This update is worth watching."
        return _trim_sentence(fallback, 760), [_trim_sentence(fallback, 180)]

    ranked = _rank_sentences(sentences)
    chosen = [sentences[index] for index, _score in sorted(ranked[:6])]
    if not chosen:
        chosen = sentences[:4]

    title = article.title.strip()
    opener = chosen[0]
    detail = " ".join(chosen[1:5])
    if title and title.lower() not in opener.lower():
        summary = f"{title}. {opener} {detail}".strip()
    else:
        summary = f"{opener} {detail}".strip()

    points = []
    for sentence in chosen[:5]:
        point = _trim_sentence(sentence, 190)
        if point and point not in points and not _is_low_value_sentence(point):
            points.append(point)
    return _trim_sentence(summary, 950), points[:5]
