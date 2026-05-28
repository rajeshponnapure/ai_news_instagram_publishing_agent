"""dedup_engine.py — five-stage article deduplication cascade.

Stage 0  canonical URL          exact URL  -> reject
Stage 1  content SHA-256        exact text -> reject
Stage 2  SimHash (Hamming<=3)   near-dup   -> reject/cluster
Stage 3  token cosine           >=0.92 reject · 0.82-0.92 same-topic cluster
Stage 4  entity+topic signature collapse same-topic

Works against both the in-batch set and persistent :class:`memory_store.MemoryStore`
(cross-email / cross-cycle). Returns the best article of each cluster tagged with a
stable ``_story_id``; cluster losers are returned separately as carryover candidates.
"""
from __future__ import annotations

import re
import urllib.parse
import uuid
from dataclasses import dataclass, field

from . import text_similarity as ts
from .ig_constants import REFERENCE_BRANDS

# Domains we trust more when picking the best article of a duplicate cluster.
_AUTHORITY_DOMAINS = (
    "openai.com", "anthropic.com", "deepmind.google", "blog.google", "ai.google",
    "microsoft.com", "meta.com", "nvidia.com", "huggingface.co", "arxiv.org",
    "techcrunch.com", "theverge.com", "wired.com", "reuters.com", "bloomberg.com",
    "venturebeat.com", "arstechnica.com", "mit.edu",
)

_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_|source$|cmpid$|spm$|igshid$|_hsenc|_hsmi)"
)
_PAGINATION_PARAMS = {"page", "p", "pg", "pagenum", "start", "offset"}

STORY_DUP_COSINE = 0.92
STORY_CLUSTER_COSINE = 0.82
ENTITY_TOPIC_COSINE = 0.78


@dataclass
class _Accepted:
    article: dict
    story_id: str
    canonical_url: str
    sha: str
    simhash: int
    fp_text: str
    entities: frozenset[str]
    topic_sig: str
    rank: float


@dataclass
class DedupResult:
    unique: list[dict] = field(default_factory=list)        # best-of-cluster, tagged _story_id
    rejected: list[dict] = field(default_factory=list)      # exact/near duplicates dropped
    demoted: list[dict] = field(default_factory=list)       # cluster losers -> carryover candidates


# ── helpers ──────────────────────────────────────────────────────────────────

def canonicalize_url(url: str) -> str:
    """Strip tracking/pagination params and normalize for exact-dup detection."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
        if not _TRACKING_PARAMS.match(k) and k.lower() not in _PAGINATION_PARAMS
    ]
    path = re.sub(r"/(?:amp|index\.html?)?/?$", "/", parts.path) or "/"
    path = path.rstrip("/") or "/"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return urllib.parse.urlunsplit(("https", netloc, path, urllib.parse.urlencode(sorted(query)), ""))


def article_text(article: dict) -> str:
    return " ".join(
        str(article.get(k) or "")
        for k in ("title", "description", "summary", "excerpt", "text", "scraped_content")
    ).strip()


def _entities(article: dict) -> frozenset[str]:
    text = article_text(article).lower()
    found = {b.lower() for b in REFERENCE_BRANDS if b.lower() in text}
    found.update(m.lower() for m in re.findall(r"\bGPT[- ]?\d[\w.]*|\bClaude\s?\d?[\w.]*|\bGemini\s?\d?[\w.]*", text))
    return frozenset(found)


def _topic_signature(article: dict) -> str:
    toks = ts.tokens(ts.fingerprint_text(article))
    from collections import Counter

    common = [t for t, _ in Counter(toks).most_common(6)]
    return "|".join(sorted(common))


def _rank(article: dict) -> float:
    text = str(article.get("text") or article.get("description") or "")
    score = min(len(text), 4000) / 4000 * 2.0
    if article.get("image_url") or article.get("image_path"):
        score += 0.5
    url = str(article.get("url") or "").lower()
    if any(domain in url for domain in _AUTHORITY_DOMAINS):
        score += 1.0
    return score


# ── main entry ──────────────────────────────────────────────────────────────

def deduplicate(articles: list[dict], memory=None, *, consult_memory: bool = True, record: bool = True) -> DedupResult:
    """Run the cascade over ``articles``; return :class:`DedupResult`."""
    result = DedupResult()
    accepted: list[_Accepted] = []
    seen_urls: set[str] = set()

    for raw in articles:
        article = dict(raw)
        canon = canonicalize_url(str(article.get("url") or ""))
        fp = ts.fingerprint_text(article)
        if not fp:
            continue
        sha = ts.content_sha256(fp)
        sh = ts.simhash(fp)
        ents = _entities(article)
        topic = _topic_signature(article)
        rank = _rank(article)

        # Stage 0: exact canonical URL within this batch.
        if canon and canon in seen_urls:
            result.rejected.append(article)
            continue

        # Stages 1-4 against in-batch accepted set.
        cluster_idx, decision = _match_in_batch(sha, sh, fp, ents, topic, accepted)
        if decision == "reject":
            result.rejected.append(article)
            continue
        if decision == "cluster":
            incumbent = accepted[cluster_idx]
            if rank > incumbent.rank:
                # New article wins the cluster; demote the incumbent.
                result.demoted.append(incumbent.article)
                result.unique.remove(incumbent.article)
                accepted[cluster_idx] = _Accepted(
                    article, incumbent.story_id, canon or incumbent.canonical_url, sha, sh, fp, ents, topic, rank
                )
                article["_story_id"] = incumbent.story_id
                result.unique.append(article)
                if canon:
                    seen_urls.add(canon)
            else:
                result.demoted.append(article)
            continue

        # Stage 4b: cross-cycle memory.
        story_id = None
        if consult_memory and memory is not None:
            hit = memory.find_duplicate_story(sha=sha, simhash_val=sh, fp_text=fp)
            if hit and hit[1] >= STORY_DUP_COSINE:
                result.rejected.append(article)
                continue
            if hit and hit[1] >= STORY_CLUSTER_COSINE:
                story_id = hit[0]  # same story resurfacing; reuse id, still allow if not published

        story_id = story_id or uuid.uuid4().hex
        article["_story_id"] = story_id
        accepted.append(_Accepted(article, story_id, canon, sha, sh, fp, ents, topic, rank))
        result.unique.append(article)
        if canon:
            seen_urls.add(canon)
        if record and memory is not None:
            memory.record_story(
                canonical_url=canon,
                sha=sha,
                simhash_val=sh,
                title=str(article.get("title") or ""),
                fp_text=fp,
                entities=sorted(ents),
                topic=topic,
                story_id=story_id,
            )
            memory.record_topic(topic)

    return result


def _match_in_batch(sha, sh, fp, ents, topic, accepted: list[_Accepted]) -> tuple[int, str]:
    """Return (index, decision) where decision in {'new','reject','cluster'}."""
    best_cluster = -1
    for idx, acc in enumerate(accepted):
        if sha == acc.sha:
            return idx, "reject"
        if ts.simhash_similar(sh, acc.simhash, max_hamming=3):
            return idx, "reject"
        cos = ts.cosine(fp, acc.fp_text)
        if cos >= STORY_DUP_COSINE:
            return idx, "reject"
        if cos >= STORY_CLUSTER_COSINE:
            best_cluster = idx
            continue
        if ents and acc.entities and (ents & acc.entities) and topic == acc.topic_sig and cos >= ENTITY_TOPIC_COSINE:
            best_cluster = idx
    if best_cluster >= 0:
        return best_cluster, "cluster"
    return -1, "new"
