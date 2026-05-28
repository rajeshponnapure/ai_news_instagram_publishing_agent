"""text_similarity.py — pure-Python text fingerprinting and similarity.

No third-party dependencies. Deterministic across processes (uses hashlib, never
Python's salted ``hash()``). Provides the building blocks the dedup engine, the
verifier, the keypoint generator and the memory store all rely on:

- ``content_sha256``  exact-duplicate detection
- ``simhash`` / ``hamming`` / ``simhash_similar``  near-duplicate detection
- ``jaccard``  token-set overlap (good for short strings like keypoints)
- ``cosine``  token-frequency cosine (good for paragraph-length text)
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

# Compact stopword set shared by all similarity measures.
_STOPWORDS = frozenset(
    """a an and are as at be been by for from has have in into is it its of on or
    that the their there these they this to was were what when where which who will
    with would your you about after also more most new news over said such than then
    them we our us""".split()
)

_WORD_RE = re.compile(r"[a-z0-9]+")
_HEX64 = (1 << 64) - 1


# ── normalization & tokenization ──────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    lowered = (text or "").lower()
    return " ".join(_WORD_RE.findall(lowered))


def tokens(text: str, *, drop_stopwords: bool = True, min_len: int = 2) -> list[str]:
    """Return content tokens from ``text``."""
    out = []
    for token in _WORD_RE.findall((text or "").lower()):
        if len(token) < min_len:
            continue
        if drop_stopwords and token in _STOPWORDS:
            continue
        out.append(token)
    return out


def token_set(text: str, **kwargs) -> set[str]:
    return set(tokens(text, **kwargs))


# ── exact hashing ─────────────────────────────────────────────────────────────

def content_sha256(text: str, *, limit: int = 4000) -> str:
    """SHA-256 of normalized text, truncated to ``limit`` chars before hashing."""
    norm = normalize_text(text)[:limit]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ── SimHash (64-bit) ──────────────────────────────────────────────────────────

def _token_hash(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big")


def simhash(text: str, *, ngram: int = 2) -> int:
    """Return a 64-bit SimHash of ``text``.

    Uses weighted token n-grams (default bigrams) so paraphrases with shared
    phrasing collide. Returns 0 for empty input.
    """
    toks = tokens(text)
    if not toks:
        return 0
    features: Counter[str] = Counter()
    # unigrams + n-grams give robustness to small edits
    features.update(toks)
    if ngram > 1 and len(toks) >= ngram:
        for i in range(len(toks) - ngram + 1):
            features[" ".join(toks[i: i + ngram])] += 1
    bit_acc = [0] * 64
    for feature, weight in features.items():
        h = _token_hash(feature)
        for bit in range(64):
            if (h >> bit) & 1:
                bit_acc[bit] += weight
            else:
                bit_acc[bit] -= weight
    result = 0
    for bit in range(64):
        if bit_acc[bit] > 0:
            result |= 1 << bit
    return result & _HEX64


def hamming(a: int, b: int) -> int:
    """Hamming distance between two 64-bit ints."""
    return bin((a ^ b) & _HEX64).count("1")


def simhash_similar(a: int, b: int, *, max_hamming: int = 3) -> bool:
    """True when two SimHashes are within ``max_hamming`` bits (both non-zero)."""
    if not a or not b:
        return False
    return hamming(a, b) <= max_hamming


# ── set / vector similarity ─────────────────────────────────────────────────────

def jaccard(a: str, b: str) -> float:
    """Token-set Jaccard overlap in [0, 1]."""
    sa, sb = token_set(a), token_set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def cosine(a: str, b: str) -> float:
    """Token-frequency cosine similarity in [0, 1]."""
    ca, cb = Counter(tokens(a)), Counter(tokens(b))
    if not ca or not cb:
        return 0.0
    common = set(ca) & set(cb)
    dot = sum(ca[t] * cb[t] for t in common)
    if not dot:
        return 0.0
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


# ── high-level duplicate scoring ────────────────────────────────────────────────

def duplicate_score(
    text_a: str,
    text_b: str,
    *,
    sha_a: str | None = None,
    sha_b: str | None = None,
    simhash_a: int | None = None,
    simhash_b: int | None = None,
) -> float:
    """Combined duplicate confidence in [0, 1].

    Pre-computed sha/simhash may be supplied to avoid recomputation.
    """
    if sha_a is None:
        sha_a = content_sha256(text_a)
    if sha_b is None:
        sha_b = content_sha256(text_b)
    if sha_a and sha_a == sha_b:
        return 1.0
    if simhash_a is None:
        simhash_a = simhash(text_a)
    if simhash_b is None:
        simhash_b = simhash(text_b)
    score = cosine(text_a, text_b)
    if simhash_similar(simhash_a, simhash_b, max_hamming=3):
        score = max(score, 0.95)
    return score
