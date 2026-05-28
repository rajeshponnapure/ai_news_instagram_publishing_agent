# Strict Multi-Layer AI Content Pipeline — Design Lock

> Status: **LOCKED** (implementation contract). Pure-stdlib + Pillow only — no new heavy
> dependencies, no API keys required, CI stays green on Ubuntu/py3.11. Premium backends
> (Claude, CLIP, Voyage, OCR) are optional plug-ins behind interfaces; the offline
> implementations are the default and the thing that ships.

## 1. Goals (hard requirements)

1. Process 80–100 articles from one email.
2. Build posts of **exactly 8 unique articles** + one CTA slide (9 children; IG allows 10).
3. Eliminate duplicate news / keypoints / images / summaries / topics within a post.
4. Prevent repeated content across pages, posts, emails, and publishing cycles.
5. **No keypoint heading / filler text** ("The real shift is here", "Keep an eye on this",
   "What this means", "Why it matters", etc.) ever appears. Keypoints read like a human
   content creator wrote them — summarised, punchy, fact-led — not raw scraped sentences.
6. No cut-off titles, no missing images, no missing keypoints, no malformed output.
7. Mandatory two-phase verification before publishing.
8. Durable, typed memory of seen stories / keypoints / images / topics / published posts.

## 2. Why pure-stdlib

The deploy target is GitHub Actions with `requirements.txt = Pillow, playwright, pytest`.
There are no model API keys. So the shipping implementation uses:

- **SimHash (64-bit)** + content SHA-256 + token-set Jaccard + token-frequency cosine —
  pure Python, deterministic, no numpy. (`text_similarity.py`)
- **Perceptual image hashing** (average-hash + difference-hash, 64-bit) computed directly
  with Pillow (resize → grayscale → bit extraction). No `imagehash` package.
  (`perceptual_image.py`)
- **SQLite** for all memory (extends existing `db.py`). (`memory_store.py`)

Premium backends are optional: an `EmbeddingProvider` seam can route to Voyage/Claude/CLIP
when keys + packages are present, but the **default and tested path is offline**.

## 3. Layered architecture

```
[L0] Ingestion          agent.py + email_client.py            EmailItem[]
[L1] Extraction         article_enricher.py                   RawArticle[]   (URL canon, fetch, parse, paginate)
[L2] Page reconstruct   article_assembler.py (NEW)            CanonicalArticle[]  (merge pages, drop repeated paragraphs)
[L3] Fingerprint+dedup  dedup_engine.py (NEW)                 UniqueArticle[]    (URL→SHA→SimHash→cosine→entity/topic)
[L4] Semantic memory    memory_store.py (NEW)                 reject seen-before across emails/cycles
[L5] Selection          post_planner.py (NEW)                 Post(exactly 8) + carryover queue
[L6] Generation         summarizer.py + ig_keypoints.py       summary, headline, professional keypoints (Phase-1 constrained)
[L7] Image              ig_image.py (extended)                8 unique relevant HD images (pHash/dHash dedup)
[L8] Slide render       ig_slide_builder.py + ig_renderer_pil 8 content slides + mandatory CTA, fit-to-box titles
[L9] VERIFY (gate)      verifier.py (NEW)                     PASS / FAIL + confidence + audit report
[L10] Publish           publisher.py (gated)                  Meta Graph API — PASS only
[L11] Commit to memory  memory_store.py                       record published posts/images/keypoints/topics
```

Failure handling and audit/monitoring wrap L1–L10.

## 4. Deduplication (Instruction 2)

### 4.1 Five-stage cascade (`dedup_engine.py`)
- **Stage 0 — URL canonicalize:** strip `utm_*`, `fbclid`, `gclid`, `ref`, pagination params;
  normalize trailing slash / AMP. Exact canonical match ⇒ drop.
- **Stage 1 — Content SHA:** sha256 of normalized text[:4000]. Match in memory ⇒ duplicate.
- **Stage 2 — SimHash:** 64-bit; Hamming ≤ 3 ⇒ near-duplicate (reworded/syndicated/multi-page).
- **Stage 3 — Token cosine:** cosine ≥ 0.92 ⇒ duplicate; 0.82–0.92 ⇒ same-topic cluster (keep best);
  < 0.82 ⇒ distinct.
- **Stage 4 — Entity+topic:** signature = sorted(top entities)+topic bucket; identical sig and
  cosine ≥ 0.78 ⇒ collapse.

`duplicate_score = max(exact, url, 0.95·simhash≤3, cosine, 0.90·entity+topic)`
- `≥ 0.92` REJECT · `≥ 0.78` CLUSTER(keep best, demote rest to carryover) · else ACCEPT (new `story_id`).

### 4.2 Multi-page reconstruction (`article_assembler.py`)
Group URLs by canonical base; follow pagination; concatenate; **drop paragraphs whose SimHash
Hamming ≤ 3 vs an earlier paragraph** (removes repeated teasers/headers). Emit one
`CanonicalArticle`. Dedup cascade then runs on the assembled article.

### 4.3 Memory + retention (`memory_store.py`, SQLite)
- `story_memory` (sha, simhash, entities, topic, times_seen, published) — **90-day window**.
- `keypoint_memory` (text, simhash) — **45 days**.
- `image_memory` (path, ahash, dhash, used_in_post) — **indefinite** (never reuse an image).
- `topic_memory` (topic_sig, last_covered_at) — **30-day decay**.
- `published_posts` (story_ids, headline, summary_sha) — cross-cycle summary dedup.
- `carryover_articles` (payload_json, attempts) — TTL 72h or attempts ≥ 3.

### 4.4 Enforcement thresholds
| Type | Detector | Threshold | Action |
|---|---|---|---|
| dup article (same email) | SHA / SimHash | exact / ≤3 | drop |
| dup article (cross email/cycle) | cosine vs story_memory | ≥0.92 | reject |
| dup summary | summary_sha + cosine vs published_posts | ≥0.93 | regen / replace |
| dup headline | normalized + cosine | ≥0.90 | re-headline |
| dup keypoint | simhash/jaccard vs keypoint_memory + in-post | ≥0.85 jaccard | drop+replace |
| dup image (perceptual) | aHash/dHash Hamming | ≤6 | next candidate |
| dup topic across posts | topic_sig in run + topic_memory | exact sig | demote to carryover |

### 4.5 Exactly-8 guarantee (`post_planner.py`)
Over-supply candidates → rank (authority, completeness, image, recency) → fill groups of 8,
holding any remainder in persistent `carryover_articles`. **A post is emitted only at exactly 8**;
short tails are never published, they wait for the next cycle. If an article fails during
generation/imaging, the planner pops a replacement so the post stays at 8. CTA appended after.

## 5. Keypoints: no headings, human quality (Instruction 1 — top priority)

`ig_keypoints.py` + `ig_copy.py`:
- **Hard heading removal:** a single normalizer strips every meta-label/heading prefix
  anywhere in the string (not just the start), including all `KEYPOINT_LABELS`, `ROBOTIC_PHRASES`,
  and bold/`##`/`**label:**` markup. A point that still *looks* like a heading after stripping
  is rejected, not shipped.
- **Reshape, don't copy-paste:** each candidate sentence is condensed into a single
  fact-led statement — lead with entity/number/action verb, drop connective filler
  ("Furthermore", "In addition", "As a result"), strip trailing clauses, ≤ ~18 words,
  no ellipsis, ends clean.
- **Quality scoring + rejection:** score on {concrete number/name/date, action verb lead,
  length band, standalone, not generic/heading}. Below threshold ⇒ rejected; require ≥4
  passing points per slide (backfill from title/description if needed, still reshaped).
- **Semantic dedup** across articles via SimHash/Jaccard, not the old `lower()[:60]` prefix.

## 6. Titles: no cut-offs
Replace the 4–7-word clamp in `layout_safe_headline` with a **PIL fit-to-box** measure: keep
the whole real title and wrap it; only shorten on word boundaries, never mid-word, never drop
the leading entity. Reject/repair titles starting lowercase/mid-word or ending on a stopword.

## 7. CTA: always present
`_make_cta_slide` is appended as the final slide of every carousel in `ig_slide_builder`.

## 8. Two-phase verification (Instruction 3)

### Phase 1 — pre-generation (input gate)
Banned-pattern reject (hard, semantic), completeness (title≥20, body≥120, ≥1 image candidate,
≥4 valid keypoints), title preservation, keypoint quality scoring, page-merge check,
uniqueness pre-check vs memory, image-relevance scoring, topic-diversity (≥4 distinct topics/post).

### Phase 2 — pre-publish gate (`verifier.py`, blocking)
12 checks, each pass/fail + confidence:
1 no dup keypoints · 2 no dup images · 3 no repeated semantic news · 4 titles complete ·
5 exactly 8 articles · 6 all images exist (HD) · 7 CTA present · 8 keypoints professional /
no headings · 9 no generic filler · 10 no repeated info across slides · 11 all summaries unique ·
12 valid image↔article mapping.

```
hard_fail = any blocking check failed   # {2,3,4,5,6,7,11,12}
confidence = weighted_mean(check confidences)
verdict = PASS if (not hard_fail and confidence >= 0.85) else FAIL
```
On FAIL → targeted recovery (regen keypoints/summary/headline, pick next image, backfill slot,
append CTA) up to 2 rounds → re-verify → else QUARANTINE (status `verify_failed`, never publish).
Every round writes `verification_report.json` in the batch dir + a `verification_audit` row.

### Publishing enforcement (`publisher.py`)
Refuse any post whose verification status ≠ `PASS` (status `blocked_verification`). Keep the
existing `published_at` idempotency guard.

## 9. Failure handling
Fetch fail → article absent (never a blank slide), planner backfills. LLM/keypoint fail →
offline reshape path; if still below quality, carryover the article. Image fail → ordered
fallback chain, each dedup-checked; if all fail, backfill the slot. Publish fail → existing
retryable/non-retryable handling + `blocked_verification` dead-letter.

## 10. Monitoring / audit
Per-stage structured log line (`run_id, stage, story_id, decision, score`); per-run rollup
(`fetched, unique, rejected_dup, posts_built, verify_pass_rate, avg_confidence`) into `runs` +
markdown report; `verification_audit` table for the gate.

## 11. Implementation steps (0–12) — see TaskList
0 design lock + plan · 1 `text_similarity.py` · 2 keypoints rewrite (headings/quality) ·
3 `perceptual_image.py` · 4 `memory_store.py` · 5 `dedup_engine.py` · 6 `article_assembler.py` ·
7 `post_planner.py` · 8 CTA + fit-to-box titles · 9 image-memory fix + perceptual dedup ·
10 `verifier.py` · 11 publisher gating · 12 test scripts (generate images + verify) & run.

## 12. New modules ↔ files map
| New | Touches |
|---|---|
| `text_similarity.py` | used by dedup_engine, verifier, ig_keypoints, memory_store |
| `perceptual_image.py` | used by ig_image, verifier, memory_store |
| `memory_store.py` | db.py (shared sqlite), instagram.py, dedup_engine, post_planner, verifier |
| `dedup_engine.py` | agent.py / instagram.py flow |
| `article_assembler.py` | article_enricher.py, agent.py |
| `post_planner.py` | instagram.py (`write_instagram_carousels`) |
| `verifier.py` | instagram.py (after render), publisher.py (gate) |
| keypoints rewrite | ig_keypoints.py, ig_copy.py |
| CTA + titles | ig_slide_builder.py, ig_copy.py, ig_renderer_pil.py |
| image-memory fix | agent.py → instagram.py (`db_path`), ig_image.py |
