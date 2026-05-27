"""ig_caption.py — Instagram caption builders for the AI news pipeline."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .ig_utils import (
    _article_items,
    _clean_headline,
    _clean_public_text,
    _dedupe_lead_text,
    _fallback_summary_text,
    _source_label_from_url,
    _trim_no_dots,
)
from .ig_copy import clean_creator_text, layout_safe_headline, layout_safe_points, trim_without_ellipsis

if TYPE_CHECKING:
    from .models import EmailSummary


# ─────────────────────────────────────────────────────────────────────────────
# Main caption builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_caption(summary: "EmailSummary") -> str:
    """Build a high-quality Instagram caption following editorial rules.

    Structure:
        1. Hook line (<125 chars, no hashtag start)
        2. Lead paragraph (2–3 sentences)
        3. 3–5 emoji-prefixed bullet points
        4. Closing question (drives comments)
        5. Source credit with URL
        6. Hashtags (15–20 optimised tags)
        7. Disclaimer if content warrants one
    """
    try:
        from .knowledge import get_rag as _get_rag
        _get_rag()  # warm the cache; errors are silently ignored
    except Exception:
        pass

    articles = _article_items(summary)
    article = articles[0] if articles else {}

    headline = _clean_headline(summary.headline or summary.subject or "AI update")
    article_url = str(article.get("url") or summary.article_url or "")

    # ── Hook line ─────────────────────────────────────────────────────────────
    hook = _build_caption_hook(summary, article, headline)

    # ── Lead paragraph ────────────────────────────────────────────────────────
    lead_raw = _clean_public_text(
        str(article.get("what_happened") or article.get("description") or
            article.get("excerpt") or summary.summary or "")
    )
    lead_raw = _dedupe_lead_text(lead_raw, headline)
    if not lead_raw or len(lead_raw) < 60:
        lead_raw = _fallback_summary_text(summary, headline)
    lead = trim_without_ellipsis(lead_raw, 360)

    # ── Takeaway bullets ──────────────────────────────────────────────────────
    bullets = _build_caption_bullets(summary, article, lead)

    # ── Closing question ──────────────────────────────────────────────────────
    closing_q = _build_closing_question(summary, article)

    # ── Source credit — include ALL article URLs from this summary ────────────
    _seen_urls: set[str] = set()
    _all_url_pairs: list[tuple[str, str]] = []
    for _art in articles:
        _u = str(_art.get("url") or "").strip()
        if _u and _u.startswith("http") and _u not in _seen_urls:
            _all_url_pairs.append((_u, _source_label_from_url(_u) or "Source"))
            _seen_urls.add(_u)
    if not _all_url_pairs and summary.article_url:
        _u = summary.article_url.strip()
        if _u.startswith("http"):
            _all_url_pairs.append((_u, _source_label_from_url(_u) or "Source"))

    if len(_all_url_pairs) == 1:
        _url, _domain = _all_url_pairs[0]
        source_credit = f"Source: {_domain}\n{_url}" if _domain else _url
    elif len(_all_url_pairs) > 1:
        _link_lines = [f"- {_u}" for _u, _ in _all_url_pairs[:5]]
        source_credit = "Sources:\n" + "\n".join(_link_lines)
    else:
        source_credit = "Curated by Graitech AI News"

    # ── Hashtags ──────────────────────────────────────────────────────────────
    hashtags_line = _build_editorial_hashtags(summary, article)

    # ── Disclaimer ────────────────────────────────────────────────────────────
    disclaimer = _build_disclaimer_if_needed(summary, article)

    save_bait = "Save this before it disappears from your feed."
    swipe_prompt = "Swipe for the full breakdown."

    parts: list[str] = [hook, "", swipe_prompt, "", lead, ""]
    if bullets:
        parts.extend(bullets)
        parts.append("")
    parts.append(closing_q)
    parts.append("")
    parts.append(save_bait)
    parts.append("")
    parts.append(source_credit)
    parts.append("")
    parts.append(hashtags_line)
    if disclaimer:
        parts.append("")
        parts.append(disclaimer)

    return "\n".join(parts).strip() + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Caption sub-builders
# ─────────────────────────────────────────────────────────────────────────────

def _build_caption_hook(summary: "EmailSummary", article: dict[str, Any], headline: str) -> str:
    """Hook line: < 125 chars, never starts with hashtag or 'I/We'."""
    companies = summary.companies[:1]
    entity = companies[0] if companies else (summary.models[:1] or ["AI"])[0]

    text_pool = " ".join([
        str(article.get("what_happened") or ""),
        str(article.get("description") or ""),
        " ".join(summary.key_points[:3]),
    ])
    stat = _extract_stat_from_text(text_pool)

    if stat:
        hook = f"{stat} changes the whole {entity} story."
    elif len(headline) <= 110 and not headline.lower().startswith(("i ", "we ")):
        hook = layout_safe_headline(headline, fallback=f"{entity} just changed everything")
        hook = hook if hook.endswith(".") else hook + "."
    else:
        hook = f"{entity} just made a move most people missed."

    if len(hook) > 125:
        hook = trim_without_ellipsis(hook, 125)
    hook = clean_creator_text(re.sub(r"^#+\s*", "", hook)).strip()
    return hook


def _build_caption_bullets(summary: "EmailSummary", article: dict[str, Any], lead: str) -> list[str]:
    """3–5 emoji-prefixed bullet points, each adding new info not in the lead."""
    seen_bullet: set[str] = set()
    deduped: list[str] = []

    lead_fp = re.sub(r"\s+", " ", lead.lower())[:120]

    for p in article.get("key_points", []):
        cleaned = _clean_public_text(str(p))
        fp = re.sub(r"\s+", " ", cleaned.lower())[:70]
        if len(cleaned) > 25 and fp not in seen_bullet and fp not in lead_fp:
            seen_bullet.add(fp)
            deduped.append(cleaned)

    for p in summary.key_points:
        cleaned = _clean_public_text(str(p))
        fp = re.sub(r"\s+", " ", cleaned.lower())[:70]
        if len(cleaned) > 25 and fp not in seen_bullet and fp not in lead_fp:
            seen_bullet.add(fp)
            deduped.append(cleaned)

    for field in ("what_happened", "why_matters", "what_to_watch"):
        text = _clean_public_text(str(article.get(field) or ""))
        if not text:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", text):
            sent = sent.strip()
            fp = re.sub(r"\s+", " ", sent.lower())[:70]
            if len(sent) > 30 and fp not in seen_bullet and fp not in lead_fp:
                seen_bullet.add(fp)
                deduped.append(sent)

    bullets = [f"- {pt}" for pt in layout_safe_points(deduped, limit=5)]

    if not bullets:
        for field in ("what_happened", "why_matters", "what_to_watch"):
            text = _clean_public_text(str(article.get(field) or ""))
            if text and len(text) > 30:
                safe = layout_safe_points([text], limit=1)
                if safe:
                    bullets.append(f"- {safe[0]}")
            if len(bullets) >= 3:
                break

    return bullets[:5]


def _build_closing_question(summary: "EmailSummary", article: dict[str, Any]) -> str:
    """Closing question that a non-technical reader can answer."""
    companies = summary.companies[:1]
    entity = companies[0] if companies else "this technology"

    questions = [
        f"Do you think {entity}'s move here is exciting or a risk? Drop your take below.",
        "Which industry do you think will feel the impact of this first?",
        "Would you use something like this in your daily work? Yes or no in the comments.",
        f"Is {entity} moving too fast, or not fast enough? Let's hear it.",
        "What's the one thing about this that surprised you most?",
    ]
    url_hash = abs(hash(str(article.get("url") or summary.message_key or "")))
    return questions[url_hash % len(questions)]


def _build_editorial_hashtags(summary: "EmailSummary", article: dict[str, Any]) -> str:
    """Build 15–20 Instagram hashtags optimised for the algorithm."""
    _NICHE_MAP = {
        "llm": ["#LargeLanguageModels", "#LLMNews", "#LanguageModels"],
        "language": ["#LanguageAI", "#NLP"],
        "generative": ["#GenerativeAI", "#GenAI"],
        "video": ["#AIVideo", "#AIVideoGeneration"],
        "image": ["#AIArt", "#AIImageGeneration", "#TextToImage"],
        "agent": ["#AIAgents", "#AutonomousAgents", "#AIWorkflow"],
        "autonomous": ["#AutonomousAI", "#AIAgents"],
        "policy": ["#AIPolicy", "#AIGovernance", "#TechPolicy"],
        "regulation": ["#AIRegulation", "#TechLaw"],
        "ethics": ["#AIEthics", "#ResponsibleAI"],
        "research": ["#AIResearch", "#MLResearch", "#DeepLearning"],
        "machine learning": ["#MachineLearning", "#MLOps"],
        "tool": ["#AITools", "#ProductivityAI", "#AIProductivity"],
        "productivity": ["#AIProductivity", "#AITools", "#WorkSmarter"],
        "chip": ["#AIChips", "#AIHardware", "#MLInfrastructure"],
        "hardware": ["#AIInfrastructure", "#AIChips"],
        "robot": ["#AIRobotics", "#Robotics", "#HumanoidRobots"],
        "health": ["#AIHealth", "#HealthTech", "#MedicalAI"],
        "medical": ["#MedicalAI", "#HealthcareAI", "#ClinicalAI"],
        "enterprise": ["#EnterpriseAI", "#BusinessAI", "#AIAdoption"],
        "startup": ["#AIStartup", "#TechStartup", "#VentureAI"],
        "coding": ["#AICoding", "#GithubCopilot", "#DeveloperAI"],
        "open source": ["#OpenSourceAI", "#OpenSource"],
        "multimodal": ["#MultimodalAI", "#VisionAI"],
        "reasoning": ["#AIReasoning", "#AIBenchmarks"],
        "voice": ["#AIVoice", "#SpeechAI"],
        "automation": ["#Automation", "#AIAutomation", "#NoCode"],
        "cloud": ["#CloudAI", "#AICloud"],
    }
    _COMPANY_MAP = {
        "openai": ["#OpenAI", "#ChatGPT"],
        "chatgpt": ["#ChatGPT", "#OpenAI"],
        "gpt": ["#GPT4", "#GPT5", "#OpenAI"],
        "google": ["#GoogleAI", "#Gemini"],
        "gemini": ["#Gemini", "#GoogleAI"],
        "deepmind": ["#GoogleDeepMind", "#DeepMind"],
        "anthropic": ["#Anthropic", "#Claude"],
        "claude": ["#Claude", "#Anthropic"],
        "meta": ["#MetaAI", "#LlamaAI"],
        "llama": ["#LlamaAI", "#MetaAI"],
        "microsoft": ["#MicrosoftAI", "#Copilot"],
        "copilot": ["#Copilot", "#MicrosoftAI"],
        "apple": ["#AppleIntelligence", "#AppleAI"],
        "nvidia": ["#NVIDIA", "#NVIDIAGPU"],
        "mistral": ["#MistralAI"],
        "hugging face": ["#HuggingFace", "#Transformers"],
        "groq": ["#Groq", "#FastAI"],
        "cohere": ["#Cohere", "#EnterpriseAI"],
        "perplexity": ["#PerplexityAI", "#AISearch"],
        "stability": ["#StabilityAI", "#StableDiffusion"],
        "midjourney": ["#Midjourney", "#AIArt"],
        "xai": ["#xAI", "#Grok"],
        "grok": ["#Grok", "#xAI"],
        "amazon": ["#AmazonBedrock", "#AWSCloud"],
    }
    _MID = [
        "#AINews", "#TechNews", "#AIUpdates", "#ArtificialIntelligence",
        "#FutureOfAI", "#TechTrends", "#Innovation", "#EmergingTech",
    ]
    _BROAD = [
        "#Technology", "#Tech", "#AI", "#MachineLearning",
        "#DataScience", "#FutureTech", "#DigitalTransformation",
    ]
    _FORMAT = [
        "#AICarousel", "#LearnAI", "#AIExplained", "#AIForEveryone",
        "#TechCarousel", "#AIBreakdown",
    ]

    combined = " ".join([
        str(article.get("title") or ""),
        " ".join(summary.topics),
        " ".join(summary.companies),
        " ".join(summary.models),
        str(summary.headline or ""),
    ]).lower()

    niche_tags: list[str] = []
    for kw, tags in _NICHE_MAP.items():
        if kw in combined:
            niche_tags.extend(tags)
        if len(niche_tags) >= 8:
            break

    company_tags: list[str] = []
    for kw, tags in _COMPANY_MAP.items():
        if kw in combined:
            company_tags.extend(tags)
        if len(company_tags) >= 6:
            break

    key_hash = abs(hash(summary.message_key or ""))
    mid_picks = [_MID[(key_hash + i) % len(_MID)] for i in range(4)]
    broad_picks = [_BROAD[(key_hash + i) % len(_BROAD)] for i in range(3)]
    fmt_pick = _FORMAT[key_hash % len(_FORMAT)]

    if not niche_tags:
        niche_tags = ["#AINews", "#AITools", "#GenerativeAI"]

    seen_tags: set[str] = set()
    unique_tags: list[str] = []
    for tag in [*niche_tags, *company_tags, *mid_picks, *broad_picks, fmt_pick]:
        if tag not in seen_tags and len(unique_tags) < 20:
            seen_tags.add(tag)
            unique_tags.append(tag)

    fallbacks = [
        "#DeepLearning", "#NeuralNetworks", "#ComputerVision",
        "#NaturalLanguageProcessing", "#MLNews", "#AIWeekly",
        "#TechInnovation", "#AIStartups", "#FutureOfWork",
    ]
    for fb in fallbacks:
        if len(unique_tags) >= 20:
            break
        if fb not in seen_tags:
            unique_tags.append(fb)
            seen_tags.add(fb)

    return " ".join(unique_tags)


def _extract_stat_from_text(text: str) -> str:
    """Extract a concrete statistic from text for use in a hook line."""
    match = re.search(
        r"\b(\d[\d,]*(?:\.\d+)?(?:B|M|K|bn|mn|%|\s+(?:billion|million|thousand|percent|times|x)))\b",
        text, re.I,
    )
    if not match:
        return ""

    search_region = text[:match.start()]
    sent_start = 0
    for m in re.finditer(r"[.!?]\s+", search_region):
        sent_start = m.end()

    if sent_start == 0:
        first_word = text[:match.start()].strip().split()
        if first_word and not (first_word[0][0].isupper() or first_word[0][0].isdigit()):
            return ""

    end = min(len(text), match.end() + 80)
    snippet = re.sub(r"\s+", " ", text[sent_start:end]).strip()

    offset_in_snippet = match.end() - sent_start
    period_pos = snippet.find(".", max(0, offset_in_snippet))
    if period_pos > 0:
        snippet = snippet[:period_pos + 1]

    if not snippet or not (snippet[0].isupper() or snippet[0].isdigit()):
        return ""

    return snippet[:110] if len(snippet) > 10 else ""


def _build_disclaimer_if_needed(summary: "EmailSummary", article: dict[str, Any]) -> str:
    """Return a short disclaimer when article content warrants one."""
    text = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        " ".join(summary.key_points[:4]),
        " ".join(summary.topics),
    ]).lower()

    warning = ""
    if any(kw in text for kw in ("benchmark", "performance score", "eval")):
        warning = "Benchmarks reflect results at publication time and may change as models are updated."
    elif any(kw in text for kw in ("price", "pricing", "$", "cost per")):
        warning = "Pricing information can change. Verify directly with the provider."
    elif any(kw in text for kw in ("medical", "health", "diagnosis", "clinical")):
        warning = "This is not medical advice. AI health tools do not replace professional care."
    elif any(kw in text for kw in ("invest", "financial", "stock", "trading")):
        warning = "This is not financial advice. AI investment tools carry significant risks."
    elif any(kw in text for kw in ("regulation", "law", "legal", "compliance", "gdpr")):
        warning = "This is not legal advice. Consult a qualified professional for guidance."

    attribution = "AI-assisted summary by Graitech from the sources listed above. Original rights remain with the publishers."

    if warning:
        return f"-\n{warning}\n{attribution}\n-"
    return f"-\n{attribution}\n-"
