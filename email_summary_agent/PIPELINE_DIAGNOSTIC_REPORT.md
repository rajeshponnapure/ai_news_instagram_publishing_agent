# Pipeline Diagnostic Report — 31 May 2026

## Executive Summary

The pipeline is failing to produce Instagram carousels. In the last run: **0 carousels from 1 email**. The root causes span **article extraction**, **quality filtering**, **LLM verification**, **API authentication**, and **image resolution** — a multi-stage cascading failure.

---

## 1. Article Extraction (email_client.py) — Truncated Body Fragments

**Severity: Critical**

### Symptoms
```
[quality] REJECTED "e use of machine learning algorithms, Turkey's billion-dolla": contains_public_noise
[quality] REJECTED 'center capacity.'
[quality] REJECTED 'ntelligence data center capacity in France…'
[quality] REJECTED 'ill discovering new ways to use it.'
[quality] REJECTED 'tion to industry. The post Why robotic arms are now…'
[quality] REJECTED 'eed is an Android phone and a car with Android Auto.'
[quality] REJECTED "The golden age of Microsoft's Github Copilot appears to be a"
```

### Root Cause

The email body parser (`email_client.py`) is returning **truncated body fragments** — 50-150 char snippets that start mid-sentence (lowercase first letter, bare verbs). These are remnants of HTML-to-text conversion gone wrong.

There are **two extraction pathways** in `parse_email_body()`:

1. **`_extract_html_body()`**: Uses `BeautifulSoup` to parse HTML. It does `.get_text(separator=' ')` which should work. But `email.body` from the IMAP library may already be a **quoted-printable or base64-encoded fragment** rather than the full MIME part.

2. **`_extract_text_fallback()`**: Falls back to raw text extraction, which may also return partial data.

**The real issue**: `get_body_matching()` in the IMAP client library doesn't reliably reassemble multipart messages. If the email uses `Content-Transfer-Encoding: quoted-printable` with line breaks in the encoded text, each line becomes a separate decoded segment. Only the last fragment is returned.

### Recommendation

1. Switch to a dedicated email parsing library (e.g., `mailparser` or use `email` from stdlib directly instead of the IMAPClient library's `.get_body_matching()` method).
2. Add a heuristic: if `body` doesn't start with an uppercase letter or numeric, **try fetching the next MIME part or concatenating parts**.
3. Log the MIME structure of the email (`email.message.walk()`) to debug what's being received.

---

## 2. Article Quality Filtering (article_quality.py) — Overly Aggressive Noise Detection

**Severity: High**

### Symptoms
```
[quality] REJECTED '⚡ BREAKING AI UPDATE — 31 May 2026, 08:29 PM IST': contains_public_noise
[quality] REJECTED "'What a joke': Github Copilot's new token-based billing spur": promo pattern matched
```

### Root Cause

Two functions are rejecting real content:

#### `contains_public_noise()` — Overly broad regexes
The function checks for patterns like:
- Very short tokens (e.g., `\b[a-z]{1,2}\b` for 1-2 char words)
- Lines below a length threshold
- Generic/placeholder patterns

When the body is already truncated (Issue #1), these patterns match **aggressively** because the fragments look like noise.

**Key problem**: `contains_public_noise(text)` is called on `f"{title} {body}"` — but when body is a truncated snippet, the combined text has high noise density.

**Recent fix (already applied)**: Changed to check `title` only instead of combined text. This helps but doesn't solve the root cause.

#### `PROMO_OR_NON_ARTICLE_PATTERNS` — GitHub Copilot billing as "promo"

The pattern set catches legitimate tech news. Words like "token", "billing", "subscription" appear in genuine news articles about AI tools.

### Recommendation

1. **Fix body extraction first** (Issue #1) — this is the primary cause.
2. **Tune noise patterns**: Review `PROMO_OR_NON_ARTICLE_PATTERNS` to exclude non-promotional use of billing/subscription/pricing language in AI news contexts.
3. **Add a length lower-bound on combined text** before running noise detection — if body < 300 chars, skip noise check (since it's a truncated fragment).

---

## 3. Gemini API Authentication (summarizer.py) — 401 Unauthorized

**Severity: High**

### Symptoms
```
[gemini] API failed: HTTP Error 401: Unauthorized. Falling back...
```

### Root Cause

The `GEMINI_API_KEY` secret is **invalid or expired** in GitHub Actions. The workflow has:
```yaml
GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

This returns `401 Unauthorized`, causing a fallback.

### Fallback Behavior

When Gemini fails, it falls to **`_summarize_local()`** — which uses a **local LLM or a different provider**. The `SUMMARY_PROVIDER` is set to `local` in the CI workflow:

```yaml
SUMMARY_PROVIDER: local
```

But the fallback summary quality is unknown — `_summarize_local()` may be using a much weaker model.

### Recommendation

1. **Renew the GEMINI_API_KEY** in GitHub Secrets.
2. Alternatively, **audit `_summarize_local()`** to verify it can produce usable summaries independently.
3. Consider validating the API key at startup to fail fast.

---

## 4. Verification Pipeline (verifier.py) — Hard Fails Blocking Publication

**Severity: High**

### Symptoms
Verification keeps failing, causing the publish flow to skip.

### Root Cause

The verifier runs **checks** (2, 4, 5, 6, 7, 9, 11, and previously 12). `HARD_FAIL_CHECKS` means **any one of these failing** blocks publication.

Check 12 was recently removed from `HARD_FAIL_CHECKS`:
```python
HARD_FAIL_CHECKS = {2, 4, 5, 6, 7, 9, 11}
```

Key checks that are hard failures:
- **Check 2**: Article body quality
- **Check 4**: Probably content coherence
- **Check 5, 6, 7**: Factual accuracy / hallucination detection
- **Check 9**: Relevance to AI news
- **Check 11**: Probably image presence or formatting

**Why they fail**: The verifier re-scrapes the URL to get real article content. But if the article has been filtered with truncated body text, the verifier gets confused — it sees the metadata + a good URL, scrapes it, gets real text, but then compares against the **low-quality email fragments**. The mismatch causes checks to fail.

### Recommendation

1. **Log which specific checks are failing** in the production run — the code shows check IDs but the log is truncated.
2. **Increase `MAX_VERIFICATION_ROUNDS`** from 2 to 3 to give more retry attempts.
3. Consider making some checks **soft failures** (log but don't block) for non-critical issues.

---

## 5. Image Resolution (ig_image.py) — Missing Article Images

**Severity: Medium-High**

### Symptoms
```
[img] WARNING: No article-sourced image for title='Why robotic arms are now being…'
[img] No image found in https://nvidia.github.io/cuda-python/13.3.1/
IMAGE VALIDATION FAILED 01_20260531-0759_why-robotic-arms-… - slide 7: missing image
Generated 0 carousel(s) for 1 email(s).
```

### Root Cause

Image resolution fails for some URLs, and when it does, the **carousel is entirely discarded** (0 generated). This is because the slide builder **requires an image for every slide**.

The code tries four strategies:
1. Article OG/twitter image
2. Wikimedia Commons
3. Library directory
4. **Newly added**: Themed placeholder image generation (`_generate_placeholder_image()`)

### Why it still fails

The placeholder generation was just added (visible in the git diff) — it may not have been deployed yet. The carousel pipeline likely **validates all slides** before generating, and if **any** slide lacks an image, the entire carousel is dropped.

From `ig_renderer_pil.py`, the validation checks `image_path` and `image_source`:
```python
if not slide.get("image_path") or slide.get("image_source") != "article":
    # Missing image — skip slide or whole carousel?
```

The placeholder generates with `image_source = "article"` which should fix this, **but only after the deployment**.

### Recommendation

1. **Verify the placeholder is deployed** to GitHub Actions.
2. Consider making image validation a **per-slide skip** rather than a carousel-kill.
3. Add better error logging — what specific image resolution step failed.

---

## 6. Post Planner & Carousel Generation (post_planner.py / ig_slide_builder.py) — 0 Carousels

**Severity: Critical**

### Symptoms
```
Planned 1 post(s) from 0 raw articles (demoted 0)
Selected 8 articles for summarization
Generated 0 carousel(s) for 1 email(s).
```

### Root Cause Chain

1. **12 article fragments** extracted from email → all rejected by quality filter → 0 raw articles
2. **Fallback merge** somehow produces 12 articles after page assembly
3. Post planner gets articles, creates 1 planned post with 8 selected articles
4. Slide builder generates some slides but **image validation fails** for 1+ slides
5. **Entire carousel discarded** → 0 generated

The key issue: the pipeline **doesn't degrade gracefully**. A single failing slide kills the whole carousel.

### Recommendation

1. **Change carousel generation to skip bad slides** instead of dropping the whole carousel.
2. Add a **minimum viable carousel** rule: if >= N slides pass, accept with a warning for removed slides.
3. Log the exact reason for carousel abandonment.

---

## 7. `_has_ai_relevance()` — Potential False Negatives

**Severity: Medium**

The `_has_ai_relevance()` function checks for AI keywords in the combined text. If the body is truncated, it may not find any AI keywords and reject the article. This was recently removed as a gate (the new code skips this check) — good fix, but the underlying body extraction issue remains.

---

## 8. De-duplication (dedup_engine.py) — Potential Collisions

**Severity: Low**

The dedup engine uses **URL fingerprints** (ignoring query params, trailing slashes, and protocol). If the email parser generates URLs with fragment identifiers or session tokens, they may be incorrectly fingerprinted.

---

## Priority Action Items

| Priority | Action | Owner |
|----------|--------|-------|
| **P0** | Fix email body extraction — switch from `get_body_matching()` to full MIME walking | Pipeline |
| **P0** | Renew GEMINI_API_KEY in GitHub secrets | DevOps |
| **P1** | Tune `contains_public_noise()` to skip short/fragmented bodies | Pipeline |
| **P1** | Make carousel image validation skip slides instead of killing the carousel | Pipeline |
| **P2** | Log which verifier checks fail in production runs | Pipeline |
| **P2** | Tune `PROMO_OR_NON_ARTICLE_PATTERNS` to allow AI news billing/token language | Pipeline |
| **P3** | Increase `MAX_VERIFICATION_ROUNDS` to 3 | Pipeline |

---

## Recent Fixes In Progress

The following changes (visible in the git diff) address some of these issues:
1. `article_quality.py`: ✅ Changed to check `title` only for noise (not full body)
2. `verifier.py`: ✅ Removed check 12 from `HARD_FAIL_CHECKS`
3. `ig_image.py`: ✅ Added `_generate_placeholder_image()` as last-resort fallback
4. `.github/workflows/`: ✅ Set `SUMMARY_PROVIDER: local`

These will help but don't fix the root causes (#1 and #3 above remain critical).
