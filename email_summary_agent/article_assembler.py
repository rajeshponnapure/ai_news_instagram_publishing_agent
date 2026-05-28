"""article_assembler.py — multi-page article reconstruction + repeat removal.

Newsletter emails frequently link several pages of the same article, and the
same story shows up under more than one URL. This module:

1. Groups paginated URL variants (``/page/2``, ``?page=2``, ``-page-2``) onto a
   single base so they reconstruct into one article.
2. Concatenates the pages and removes near-duplicate sentences (repeated
   teasers/headers that recur on every page) using SimHash + normalized match.

Operates on :class:`article_enricher.ArticleData`. Imported lazily by
``article_enricher`` to avoid an import cycle.
"""
from __future__ import annotations

import re

from . import text_similarity as ts
from .dedup_engine import canonicalize_url

_PAGE_SUFFIX_RE = re.compile(
    r"(?:[/-]page[/-]?\d+|/\d+|[?&](?:page|p|pg|start|offset)=\d+)/?$", re.I
)


def paginated_base(url: str) -> str:
    """Collapse a paginated URL onto its base so page 1..N share a key."""
    canon = canonicalize_url(url)
    prev = None
    while canon != prev:
        prev = canon
        canon = _PAGE_SUFFIX_RE.sub("", canon)
    return canon.rstrip("/") or canon


def dedup_text_segments(text: str, *, max_hamming: int = 3, jaccard_thr: float = 0.9) -> str:
    """Drop near-duplicate sentences while preserving order.

    Catches both exact repeats (normalized match) and lightly-edited repeats
    (SimHash within ``max_hamming`` or Jaccard above ``jaccard_thr``).
    """
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    kept: list[str] = []
    kept_norms: set[str] = set()
    kept_hashes: list[int] = []
    for sentence in sentences:
        norm = ts.normalize_text(sentence)
        if not norm or norm in kept_norms:
            continue
        sh = ts.simhash(sentence)
        is_dup = False
        for prior_hash, prior in zip(kept_hashes, kept):
            if ts.simhash_similar(sh, prior_hash, max_hamming=max_hamming):
                is_dup = True
                break
            if len(norm) > 40 and ts.jaccard(sentence, prior) >= jaccard_thr:
                is_dup = True
                break
        if is_dup:
            continue
        kept.append(sentence)
        kept_norms.add(norm)
        kept_hashes.append(sh)
    return " ".join(kept)


def assemble(articles: list) -> list:
    """Merge paginated variants of the same article and de-repeat their text.

    Preserves first-seen order. Returns new ``ArticleData`` objects.
    """
    from .article_enricher import ArticleData

    if not articles:
        return []

    order: list[str] = []
    groups: dict[str, list] = {}
    for article in articles:
        base = paginated_base(getattr(article, "url", "") or "")
        key = base or f"_solo_{len(order)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(article)

    merged: list = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            single = group[0]
            merged.append(
                ArticleData(
                    url=single.url,
                    title=single.title,
                    description=single.description,
                    text=dedup_text_segments(single.text),
                    image_url=single.image_url,
                    image_path=single.image_path,
                    extra_image_urls=single.extra_image_urls,
                    extra_image_paths=single.extra_image_paths,
                )
            )
            continue

        combined_text = dedup_text_segments(" ".join(a.text for a in group if a.text))
        title = next((a.title for a in group if a.title), "")
        description = next((a.description for a in group if a.description), "")
        image_url = next((a.image_url for a in group if a.image_url), "")
        image_path = next((a.image_path for a in group if a.image_path), "")
        extra_urls: list[str] = []
        extra_paths: list[str] = []
        for a in group:
            for u in (a.image_url, *a.extra_image_urls):
                if u and u != image_url and u not in extra_urls:
                    extra_urls.append(u)
            for p in (a.image_path, *a.extra_image_paths):
                if p and p != image_path and p not in extra_paths:
                    extra_paths.append(p)
        merged.append(
            ArticleData(
                url=group[0].url,
                title=title,
                description=description,
                text=combined_text,
                image_url=image_url,
                image_path=image_path,
                extra_image_urls=tuple(extra_urls[:3]),
                extra_image_paths=tuple(extra_paths[:3]),
            )
        )
    return merged
