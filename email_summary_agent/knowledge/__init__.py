"""
email_summary_agent/knowledge/__init__.py
─────────────────────────────────────────────────────────────────────────────
Knowledge base package for the Instagram AI News Agent.

Exports the EditorialRAG class and the get_rag() singleton helper.

Quick start:
    from email_summary_agent.knowledge import get_rag

    rag = get_rag()
    slide_context   = rag.get_context("slide_structure")
    caption_context = rag.get_context("caption")
    checklist       = rag.get_checklist("slides")
    slide_prompt    = rag.build_slide_prompt(title, body, 1, 8)
    caption_prompt  = rag.build_caption_prompt(title, body, url, source)
    summary_prompt  = rag.build_summary_prompt(title, body)
─────────────────────────────────────────────────────────────────────────────
"""

from .rag_skill import EditorialRAG, get_rag

__all__ = ["EditorialRAG", "get_rag"]
