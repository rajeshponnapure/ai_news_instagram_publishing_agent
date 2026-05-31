"""post_planner.py — exactly-8-article selection with carryover queue.

Oversupplies candidates → rank (authority, completeness, image, recency) →
fills groups of exactly 8, surplus goes to the persistent carryover queue.
A post is emitted only at exactly 8; short tails are never published.
"""
from __future__ import annotations

from .article_quality import is_publishable_article
from .dedup_engine import deduplicate, DedupResult
from .memory_store import MemoryStore


_BLOCKED_HEADLINES = frozenset({
    "the real shift is here", "keep an eye on this", "what this means",
    "the key detail", "here is the hidden part", "most people miss this",
    "the practical impact", "watch next", "why it matters",
    "what happened", "what to watch", "what this means for",
})


def _is_blocked_headline(text: str) -> bool:
    t = (text or "").strip().lower().rstrip(".:!?")
    return t in _BLOCKED_HEADLINES


def _rank_article(article: dict) -> float:
    if not is_publishable_article(article):
        return -999.0
    text = str(article.get("text") or article.get("description") or "")
    score = min(len(text), 4000) / 4000 * 2.0
    if article.get("image_url") or article.get("image_path"):
        score += 0.5
    from .dedup_engine import _AUTHORITY_DOMAINS
    url = str(article.get("url") or "").lower()
    if any(d in url for d in _AUTHORITY_DOMAINS):
        score += 1.0
    title = str(article.get("title") or "")
    if _is_blocked_headline(title):
        score -= 2.0
    return score


def plan_posts(
    articles: list[dict],
    memory: MemoryStore | None = None,
    *,
    post_size: int = 8,
    min_post_size: int = 8,
) -> tuple[list[list[dict]], list[dict]]:
    """Return (posts, carryover) from an oversupplied article list.

    Each post has exactly ``post_size`` unique articles. Surplus articles
    that don't fill a complete post are returned as ``carryover``.
    """
    # Stage 1: deduplicate the candidate pool.
    dedup: DedupResult = deduplicate(articles, memory, consult_memory=True, record=True)
    pool: list[dict] = []
    demoted = dedup.demoted[:]
    for article in dedup.unique:
        if is_publishable_article(article):
            pool.append(article)
        else:
            demoted.append(article)
            if memory is not None:
                memory.save_rejected_article(
                    url=str(article.get("url", "")),
                    title=str(article.get("title", "")),
                    article=article,
                    reason="quality_filter_post_planner",
                )

    # Stage 2: pull in carryover from memory.
    if memory is not None:
        carry = memory.pop_carryover(limit=post_size)
        for c in carry:
            existing = {a.get("_story_id") for a in pool if a.get("_story_id")}
            if c.get("_carryover_story_id") not in existing and is_publishable_article(c):
                pool.append(c)

    # Stage 3: rank and select.
    pool.sort(key=_rank_article, reverse=True)
    posts: list[list[dict]] = []
    leftover: list[dict] = []

    while len(pool) >= post_size:
        chunk = pool[:post_size]
        posts.append(chunk)
        pool = pool[post_size:]

    leftover = list(pool)

    # Stage 4: push excess (fewer than post_size) to carryover.
    if leftover and memory is not None:
        for article in leftover:
            story_id = article.get("_story_id") or ""
            if story_id:
                memory.push_carryover(story_id, article)

    return posts, demoted


def plan_summary_parts(
    summaries: list,
    memory: MemoryStore | None = None,
    *,
    flush: bool = False,
    post_size: int = 8,
) -> list:
    """Plan carousel batches from EmailSummary list.

    Pools all article_items across summaries, deduplicates, plans posts
    of exactly ``post_size``, and returns the planned summary parts in order.
    When ``flush`` is False and the surplus is fewer than ``post_size`` the
    leftover is pushed to carryover instead of emitting an incomplete post.
    """
    from .models import EmailSummary as _ES
    from .ig_slide_builder import _split_summary_for_carousels

    # Pool all article items
    all_items: list[dict] = []
    for summary in summaries:
        parts = _split_summary_for_carousels(summary)
        for part in parts:
            items = part.article_items or []
            all_items.extend(items)

    if not all_items:
        return summaries

    # Deduplicate across all summaries
    dedup: DedupResult = deduplicate(all_items, memory, consult_memory=True, record=True)
    pool: list[dict] = []
    for article in dedup.unique:
        if is_publishable_article(article):
            pool.append(article)
        elif memory is not None:
            memory.save_rejected_article(
                url=str(article.get("url", "")),
                title=str(article.get("title", "")),
                article=article,
                reason="quality_filter_plan_summary",
            )

    # Sort by rank
    pool.sort(key=_rank_article, reverse=True)

    # Build posts
    result_parts: list = []
    while len(pool) >= post_size:
        chunk = pool[:post_size]
        pool = pool[post_size:]
        from datetime import datetime
        headline = chunk[0].get("title", "AI News Update") if chunk else "AI News Update"
        story_ids = ",".join(a.get("_story_id", "") for a in chunk)
        part = _ES(
            message_key=f"planned:{story_ids[:32]}",
            subject="",
            source_date=datetime.now().isoformat(),
            headline=headline,
            summary="",
            key_points=[],
            companies=[],
            models=[],
            topics=[],
            confidence=0.8,
            article_items=chunk,
            article_url=str(chunk[0].get("url", "")),
            article_title=str(chunk[0].get("title", "")),
            article_image_path=str(chunk[0].get("image_path", "")),
            article_image_url=str(chunk[0].get("image_url", "")),
        )
        result_parts.append(part)

    # Push leftovers to carryover
    if pool and memory is not None and not flush:
        for article in pool:
            story_id = article.get("_story_id") or ""
            if story_id:
                memory.push_carryover(story_id, article)
    elif pool and flush:
        for article in pool:
            result_parts.append(
                _ES(
                    message_key=f"carryover:{article.get('_story_id', '')[:16]}",
                    subject="",
                    source_date=datetime.now().isoformat(),
                    headline=article.get("title", "AI Update"),
                    summary="",
                    key_points=[],
                    companies=[],
                    models=[],
                    topics=[],
                    confidence=0.6,
                    article_items=[article],
                )
            )

    return result_parts if result_parts else summaries


def fill_missing_article(
    article: dict | None,
    backup_pool: list[dict],
    memory: MemoryStore | None = None,
) -> dict | None:
    """Replace a failed/generation-failed article with the next best from pool."""
    if backup_pool:
        backup_pool[:] = [a for a in backup_pool if is_publishable_article(a)]
    if backup_pool:
        best = max(backup_pool, key=_rank_article)
        backup_pool.remove(best)
        return best
    if memory is not None:
        carry = memory.pop_carryover(limit=1)
        for article in carry:
            if is_publishable_article(article):
                return article
    return None
