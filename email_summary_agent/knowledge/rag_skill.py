"""
email_summary_agent/knowledge/rag_skill.py
─────────────────────────────────────────────────────────────────────────────
Instagram Editorial RAG Skill
─────────────────────────────────────────────────────────────────────────────
Purpose:
    Lightweight Retrieval-Augmented Generation layer that loads the
    instagram_editorial_rules.md knowledge base and returns the right
    sections as structured context strings for the summarizer, slide
    writer, and caption generator.

Usage:
    from email_summary_agent.knowledge.rag_skill import EditorialRAG

    rag = EditorialRAG()                     # loads knowledge base once
    ctx = rag.get_context("slide_structure") # returns relevant rules
    ctx = rag.get_context("caption")
    ctx = rag.get_context("hashtags")
    ctx = rag.get_context("writing_quality")
    ctx = rag.get_context("images")
    ctx = rag.get_context("anti_patterns")
    ctx = rag.get_context("checklists")
    ctx = rag.get_context("philosophy")
    ctx = rag.get_context("all")            # full knowledge base

    # For slide writing — build a complete content prompt:
    prompt = rag.build_slide_prompt(article_data, slide_number, total_slides)

    # For caption writing:
    prompt = rag.build_caption_prompt(article_data)

    # For validation against checklists:
    checklist = rag.get_checklist("slides")
    checklist = rag.get_checklist("caption")
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── Path to the knowledge base file ─────────────────────────────────────────
_KB_PATH = Path(__file__).parent / "instagram_editorial_rules.md"

# ── Section tag → human label ────────────────────────────────────────────────
_SECTION_TAGS: dict[str, str] = {
    "philosophy":      "PHILOSOPHY",
    "slide_structure": "SLIDE_STRUCTURE",
    "caption":         "CAPTION",
    "hashtags":        "HASHTAGS",
    "writing_quality": "WRITING_QUALITY",
    "images":          "IMAGES",
    "anti_patterns":   "ANTI_PATTERNS",
    "checklists":      "CHECKLISTS",
}


class EditorialRAG:
    """
    Loads instagram_editorial_rules.md once and provides fast, structured
    access to any named section. All public methods return plain strings
    ready to be injected into LLM prompts or rule-based validators.
    """

    def __init__(self, kb_path: Optional[Path] = None) -> None:
        self._kb_path = kb_path or _KB_PATH
        self._raw: str = self._load_kb()
        self._sections: dict[str, str] = self._parse_sections(self._raw)
        logger.info(
            "EditorialRAG loaded %d sections from %s",
            len(self._sections),
            self._kb_path,
        )

    # ── Loading ──────────────────────────────────────────────────────────────

    def _load_kb(self) -> str:
        if not self._kb_path.exists():
            raise FileNotFoundError(
                f"Knowledge base not found at {self._kb_path}. "
                "Make sure instagram_editorial_rules.md is present in "
                "email_summary_agent/knowledge/"
            )
        return self._kb_path.read_text(encoding="utf-8")

    def _parse_sections(self, raw: str) -> dict[str, str]:
        """
        Extract named sections delimited by # [SECTION_NAME] … # [/SECTION_NAME].
        Returns a dict keyed by lowercase section name.
        """
        sections: dict[str, str] = {}
        pattern = re.compile(
            r"#\s*\[([A-Z_]+)\](.*?)#\s*\[/\1\]",
            re.DOTALL,
        )
        for match in pattern.finditer(raw):
            tag = match.group(1).lower()
            content = match.group(2).strip()
            sections[tag] = content

        if not sections:
            logger.warning(
                "No sections found in knowledge base — check [TAG] / [/TAG] formatting."
            )
        return sections

    # ── Public API ───────────────────────────────────────────────────────────

    def get_context(self, section: str) -> str:
        """
        Return raw knowledge base content for the requested section.

        Args:
            section: One of the keys in _SECTION_TAGS, or "all" for the
                     complete knowledge base.

        Returns:
            A plain string of editorial rules ready to inject into a prompt.
        """
        if section == "all":
            return self._raw

        tag = _SECTION_TAGS.get(section.lower())
        if not tag:
            available = ", ".join(_SECTION_TAGS.keys())
            raise ValueError(
                f"Unknown section '{section}'. "
                f"Available sections: {available}"
            )

        content = self._sections.get(tag.lower())
        if not content:
            logger.warning("Section '%s' not found in knowledge base.", tag)
            return ""

        return content

    def list_sections(self) -> list[str]:
        """Return a list of available section names."""
        return list(_SECTION_TAGS.keys())

    # ── Prompt Builders ──────────────────────────────────────────────────────

    def build_slide_prompt(
        self,
        article_title: str,
        article_body: str,
        slide_number: int,
        total_slides: int,
        slide_label: str = "",
        previous_slide_summary: str = "",
    ) -> str:
        """
        Build a complete LLM prompt for writing a single carousel slide.

        Args:
            article_title:          Full article headline.
            article_body:           Full article text (no char limit).
            slide_number:           Current slide index (1-based).
            total_slides:           Total slides in this carousel.
            slide_label:            Section label for this slide (e.g. "Why it matters").
            previous_slide_summary: One-sentence summary of the previous slide
                                    (to avoid repetition).

        Returns:
            A fully assembled prompt string for the content model.
        """
        philosophy = self.get_context("philosophy")
        slide_rules = self.get_context("slide_structure")
        writing_rules = self.get_context("writing_quality")
        anti_patterns = self.get_context("anti_patterns")

        is_first = slide_number == 1
        is_last = slide_number == total_slides
        is_penultimate = slide_number == total_slides - 1

        if is_first:
            slide_role = (
                "This is SLIDE 1 — the COVER SLIDE. "
                "Write a complete, punchy headline (6–12 words, no truncation, no ellipsis). "
                "Also write a one-sentence subheadline that adds essential context. "
                "Choose the correct eyebrow label category from the SLIDE_STRUCTURE rules."
            )
        elif is_last:
            slide_role = (
                "This is the LAST SLIDE — the CTA / BRAND SLIDE. "
                "Write one primary call-to-action from the CTA bank in the SLIDE_STRUCTURE rules. "
                "Do NOT repeat a CTA used in a previous post if you know it. "
                "Keep it short, punchy, and action-oriented."
            )
        elif is_penultimate:
            slide_role = (
                "This is the PENULTIMATE SLIDE — 'What to watch'. "
                "Write 3–4 bullet points of specific things the reader should monitor, "
                "follow, or act on based on this article."
            )
        else:
            depth = "simple and accessible" if slide_number <= 3 else "progressively more detailed"
            slide_role = (
                f"This is SLIDE {slide_number} of {total_slides} — a DEPTH SLIDE. "
                f"Section label: '{slide_label}'. "
                f"Tone for this slide should be {depth} (follow the simple→technical progression rule). "
                "Write 4–8 sentences in 1–2 paragraphs. Each slide is a COMPLETE thought — "
                "never end with an ellipsis or a sentence that continues on the next slide. "
                "Do NOT repeat information from the previous slide."
            )

        prev_context = (
            f"\nPREVIOUS SLIDE SUMMARY (do NOT repeat this content):\n{previous_slide_summary}\n"
            if previous_slide_summary
            else ""
        )

        prompt = f"""You are writing slide {slide_number} of {total_slides} for an Instagram carousel post about an AI news article.

ARTICLE TITLE:
{article_title}

FULL ARTICLE CONTENT:
{article_body}
{prev_context}
YOUR TASK FOR THIS SLIDE:
{slide_role}

EDITORIAL PHILOSOPHY (always follow):
{philosophy}

SLIDE STRUCTURE RULES:
{slide_rules}

WRITING QUALITY RULES:
{writing_rules}

ANTI-PATTERNS (never do these):
{anti_patterns}

OUTPUT FORMAT:
Return ONLY the slide content. No preamble, no "Here is slide X:", no markdown code blocks.
For slide 1: Return FORMAT: EYEBROW_LABEL | HEADLINE | SUBHEADLINE (pipe-separated, one line each)
For all other slides: Return the body text directly, paragraphs separated by a blank line.
"""
        return prompt

    def build_caption_prompt(
        self,
        article_title: str,
        article_body: str,
        article_url: str,
        article_source: str = "",
    ) -> str:
        """
        Build a complete LLM prompt for writing an Instagram caption.

        Args:
            article_title:   Full article headline.
            article_body:    Full article text (no char limit).
            article_url:     Direct URL to the original article.
            article_source:  Publication name (e.g. "TechCrunch").

        Returns:
            A fully assembled prompt string for the caption model.
        """
        philosophy = self.get_context("philosophy")
        caption_rules = self.get_context("caption")
        hashtag_rules = self.get_context("hashtags")
        writing_rules = self.get_context("writing_quality")
        anti_patterns = self.get_context("anti_patterns")

        source_line = f"{article_source} — {article_url}" if article_source else article_url

        prompt = f"""You are writing an Instagram caption for an AI news carousel post.

ARTICLE TITLE:
{article_title}

FULL ARTICLE CONTENT:
{article_body}

ARTICLE SOURCE:
{source_line}

YOUR TASK:
Write a complete Instagram caption following EXACTLY the structure and rules below.
The caption should feel like it was written by a professional tech content creator —
confident, conversational, and genuinely interesting. Not robotic. Not generic.

EDITORIAL PHILOSOPHY:
{philosophy}

CAPTION STRUCTURE RULES (follow this order exactly):
{caption_rules}

HASHTAG RULES (exactly 5 hashtags):
{hashtag_rules}

WRITING QUALITY RULES:
{writing_rules}

ANTI-PATTERNS (never do these):
{anti_patterns}

OUTPUT FORMAT:
Return ONLY the caption text, ready to copy-paste into Instagram.
Include the hook, lead paragraph, bullets, closing question, source credit,
exactly 5 hashtags, and disclaimer if the article warrants one.
No preamble. No "Here is the caption:". No markdown code blocks.
"""
        return prompt

    def build_summary_prompt(
        self,
        article_title: str,
        article_body: str,
        target_slide_count: int = 0,
    ) -> str:
        """
        Build a prompt for the summarizer to analyse a full article and
        produce a structured slide plan before any slide text is written.

        Args:
            article_title:      Full article headline.
            article_body:       Full article text (no char limit).
            target_slide_count: If 0, the model decides based on article length.

        Returns:
            A prompt string that asks the model to return a JSON slide plan.
        """
        philosophy = self.get_context("philosophy")
        slide_rules = self.get_context("slide_structure")

        slide_count_instruction = (
            f"The carousel must have exactly {target_slide_count} slides."
            if target_slide_count > 0
            else (
                "Choose the number of slides (between 4 and 15) based on article complexity. "
                "Use as many slides as needed to cover the story fully — never truncate content."
            )
        )

        prompt = f"""You are a professional Instagram content strategist specialising in AI news.

ARTICLE TITLE:
{article_title}

FULL ARTICLE CONTENT:
{article_body}

YOUR TASK:
Analyse the full article above and produce a structured SLIDE PLAN for an Instagram carousel.
{slide_count_instruction}

The slide plan must:
1. Follow the simple→technical depth progression (slide 2 plain English, later slides more technical)
2. Cover the ENTIRE story — no important detail should be left out
3. Never split content mid-thought between slides
4. Include a "What to watch" slide as the second-to-last slide
5. Include a CTA slide as the final slide

EDITORIAL PHILOSOPHY:
{philosophy}

SLIDE STRUCTURE RULES:
{slide_rules}

OUTPUT FORMAT — return a JSON object ONLY, no preamble, no markdown code blocks:
{{
  "total_slides": <int>,
  "eyebrow_label": "<label>",
  "headline": "<complete headline, no truncation>",
  "subheadline": "<one sentence of context>",
  "slides": [
    {{
      "slide_number": 1,
      "role": "cover",
      "section_label": null,
      "key_content": "<what this slide covers in 1–2 sentences>"
    }},
    {{
      "slide_number": 2,
      "role": "what_happened",
      "section_label": "What happened",
      "key_content": "<what this slide covers>"
    }},
    ... (one object per slide)
    {{
      "slide_number": <N-1>,
      "role": "what_to_watch",
      "section_label": "What to watch 👀",
      "key_content": "<3-4 things to watch>"
    }},
    {{
      "slide_number": <N>,
      "role": "cta",
      "section_label": null,
      "key_content": "CTA slide"
    }}
  ],
  "article_category": "<one of: AI_NEWS | RESEARCH | BREAKING | INDUSTRY | DEEP_DIVE | POLICY | TOOLS | DATA>",
  "needs_disclaimer": <true|false>,
  "disclaimer_type": "<benchmark|pricing|legal|medical|financial|null>",
  "suggested_hashtags": ["<tag1>", "<tag2>", "<tag3>", "<tag4>", "<tag5>"]
}}
"""
        return prompt

    # ── Validation Helpers ───────────────────────────────────────────────────

    def get_checklist(self, checklist_type: str) -> list[str]:
        """
        Return a list of checklist items for pre-publish validation.

        Args:
            checklist_type: "slides" or "caption"

        Returns:
            List of checklist item strings (without the [ ] prefix).
        """
        raw = self.get_context("checklists")
        if not raw:
            return []

        # Find the relevant checklist block
        if checklist_type == "slides":
            pattern = re.compile(
                r"PRE-PUBLISH SLIDE CHECKLIST:(.*?)(?:PRE-PUBLISH|\Z)", re.DOTALL
            )
        elif checklist_type == "caption":
            pattern = re.compile(
                r"PRE-PUBLISH CAPTION CHECKLIST:(.*?)(?:\Z)", re.DOTALL
            )
        else:
            raise ValueError(f"Unknown checklist type '{checklist_type}'. Use 'slides' or 'caption'.")

        match = pattern.search(raw)
        if not match:
            return []

        block = match.group(1)
        items = re.findall(r"\[\s*\]\s+(.+)", block)
        return [item.strip() for item in items]

    def get_forbidden_phrases(self) -> list[str]:
        """Return the list of forbidden phrases from the PHILOSOPHY section."""
        raw = self.get_context("philosophy")
        # Extract the FORBIDDEN PHRASES block
        match = re.search(
            r"FORBIDDEN PHRASES.*?:(.*?)(?:[A-Z_]{4,}:|\Z)", raw, re.DOTALL
        )
        if not match:
            return []
        block = match.group(1)
        phrases = re.findall(r'-\s+"([^"]+)"', block)
        return phrases

    def get_cta_bank(self) -> list[str]:
        """Return all CTA options from the SLIDE_STRUCTURE section."""
        raw = self.get_context("slide_structure")
        match = re.search(r"CTA BANK.*?:(.*?)(?:[A-Z_]{4,}:|\Z)", raw, re.DOTALL)
        if not match:
            return []
        block = match.group(1)
        ctas = re.findall(r'"([^"]+)"', block)
        return ctas

    def get_hook_formulas(self) -> dict[str, str]:
        """Return all hook line formulas from the CAPTION section."""
        raw = self.get_context("caption")
        formulas: dict[str, str] = {}
        # Match "Type X — Label:" blocks
        pattern = re.compile(r"Type ([A-Z]) — ([^\n]+):\n\s+(.+?)(?=\n\s+Type [A-Z]|HOOK RULES)", re.DOTALL)
        for match in pattern.finditer(raw):
            key = f"Type {match.group(1)} — {match.group(2).strip()}"
            template = match.group(3).strip().split("\n")[0].strip()
            formulas[key] = template
        return formulas

    def get_analogies_bank(self) -> dict[str, str]:
        """Return the analogies bank as a dict {concept: analogy}."""
        raw = self.get_context("writing_quality")
        analogies: dict[str, str] = {}
        pattern = re.compile(r"(\w[\w/\s]+):\s+\"([^\"]+)\"")
        # Find the analogies block
        match = re.search(r"ANALOGIES BANK(.*?)(?:[A-Z_]{4,} |ENGAGEMENT)", raw, re.DOTALL)
        if not match:
            return analogies
        block = match.group(1)
        for m in pattern.finditer(block):
            analogies[m.group(1).strip()] = m.group(2).strip()
        return analogies

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def diagnose_caption(self, caption_text: str) -> dict[str, list[str]]:
        """
        Run a basic rule-based check against a generated caption.
        Returns a dict with "errors" and "warnings" lists.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check forbidden phrases
        for phrase in self.get_forbidden_phrases():
            if phrase.lower() in caption_text.lower():
                errors.append(f"Forbidden phrase found: '{phrase}'")

        # Check hashtag count
        hashtags = re.findall(r"#\w+", caption_text)
        if len(hashtags) == 0:
            errors.append("No hashtags found. Exactly 5 are required.")
        elif len(hashtags) < 5:
            errors.append(f"Only {len(hashtags)} hashtags found. Exactly 5 are required.")
        elif len(hashtags) > 5:
            errors.append(f"{len(hashtags)} hashtags found. Instagram's hard limit is 5.")

        # Check CamelCase hashtags
        for tag in hashtags:
            if tag != tag[0] + tag[1:] and tag.lower() == tag:
                warnings.append(f"Hashtag {tag} is all lowercase — use CamelCase.")

        # Check hook length (first non-empty line)
        lines = [l.strip() for l in caption_text.split("\n") if l.strip()]
        if lines:
            hook = lines[0]
            if len(hook) > 125:
                errors.append(
                    f"Hook line is {len(hook)} chars (limit: 125). Shorten it."
                )
            if hook.startswith("#"):
                errors.append("Hook line must not start with a hashtag.")
            if hook.lower().startswith("i ") or hook.lower().startswith("we "):
                warnings.append("Hook line starts with 'I' or 'We' — try a different opening.")

        # Check for forbidden phrases in slides
        for phrase in [
            "in conclusion", "it is worth noting", "as we can see",
            "in today's fast-paced world", "without further ado"
        ]:
            if phrase in caption_text.lower():
                errors.append(f"Forbidden phrase: '{phrase}'")

        # Check for ellipsis truncation
        if "..." in caption_text:
            warnings.append(
                "Ellipsis (...) detected. Make sure no content is truncated mid-sentence."
            )

        # Check for source URL
        if "http" not in caption_text:
            warnings.append("No source URL detected. Source credit is required.")

        return {"errors": errors, "warnings": warnings}

    def diagnose_slide(self, slide_text: str, slide_number: int) -> dict[str, list[str]]:
        """
        Run a basic rule-based check against a generated slide's text.
        Returns a dict with "errors" and "warnings" lists.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check for truncation
        if slide_text.rstrip().endswith("..."):
            errors.append(f"Slide {slide_number} ends with ellipsis — content appears truncated.")

        # Check for forbidden phrases
        for phrase in self.get_forbidden_phrases():
            if phrase.lower() in slide_text.lower():
                errors.append(f"Forbidden phrase on slide {slide_number}: '{phrase}'")

        # Check for excessive length (rough word count)
        word_count = len(slide_text.split())
        if word_count > 120:
            warnings.append(
                f"Slide {slide_number} has ~{word_count} words — may be too long for a phone screen."
            )
        if word_count < 20 and slide_number not in (1,):
            warnings.append(
                f"Slide {slide_number} has only ~{word_count} words — may feel too sparse."
            )

        # Check for continuation markers
        for bad_pattern in ["continued...", "cont'd", "→ next slide", "(continued)"]:
            if bad_pattern.lower() in slide_text.lower():
                errors.append(
                    f"Slide {slide_number} contains continuation marker '{bad_pattern}' — "
                    "each slide must be a complete thought."
                )

        return {"errors": errors, "warnings": warnings}


# ── Module-level convenience functions ───────────────────────────────────────

@lru_cache(maxsize=1)
def get_rag() -> EditorialRAG:
    """
    Return a cached singleton EditorialRAG instance.
    Call this anywhere in the codebase to get the shared RAG object
    without re-reading the file every time.

    Usage:
        from email_summary_agent.knowledge.rag_skill import get_rag
        rag = get_rag()
        context = rag.get_context("slide_structure")
    """
    return EditorialRAG()
