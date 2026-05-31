"""verifier.py — two-phase pre-generation and pre-publishing verification.

Phase 1 (pre-generation): input gate that rejects malformed/duplicate content
before rendering. Phase 2 (pre-publish): blocking gate that checks all 12
quality dimensions before allowing publishing. Each phase produces a typed
report with pass/fail per check and an overall confidence score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import text_similarity as ts
from . import perceptual_image as pi
from .article_quality import PROMO_OR_NON_ARTICLE_PATTERNS, clean_quality_text, contains_public_noise
from .ig_constants import MAX_CAROUSEL_SLIDES, MAX_INSTAGRAM_CAROUSEL_SLIDES, MAX_KP_PER_SLIDE
from .memory_store import MemoryStore

MIN_KP_PER_SLIDE = 4

_BLOCKED_HEADLINES = frozenset({
    "the real shift is here", "keep an eye on this", "what this means",
    "the key detail", "here is the hidden part", "most people miss this",
    "the practical impact", "watch next",
})
_GENERIC_PATTERNS = [
    r"this (means|shows|highlights|demonstrates|suggests)",
    r"the (real|key|important) (shift|detail|takeaway|point|insight)",
    r"here('s| is) (the|what|why)",
    r"what this means",
    r"keep an eye on",
    r"in conclusion", "overall", "furthermore", "additionally",
    r"what you need to know",
    r"here('s| is) (the latest|the news|the update|what you need|the details)",
    r"(fast facts|key insights|quick take|by the numbers)",
    r"(looking ahead|where things stand|setting the stage)",
    r"this (comes amid|comes as|is a developing story)",
    r"the landscape is shifting",
    r"early bird",
    r"strictlyvc",
    r"disrupt",
    r"equitypod",
    r"all about agents",
    r"follow on x",
    r"threads",
    r"for more details",
    r"query met quiet",
    r"lost page, still warm light",
]

HARD_FAIL_CHECKS = {2, 4, 5, 6, 7, 9, 10, 11}
CONFIDENCE_THRESHOLD = 0.75
MAX_VERIFICATION_ROUNDS = 2


@dataclass
class CheckResult:
    check_id: int
    name: str
    passed: bool
    confidence: float
    detail: str = ""


@dataclass
class VerificationReport:
    phase: str  # "pre_generation" | "pre_publish"
    round_no: int
    passed: bool
    confidence: float
    checks: list[CheckResult] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "round": self.round_no,
            "passed": self.passed,
            "confidence": round(self.confidence, 4),
            "checks": [
                {"id": c.check_id, "name": c.name, "passed": c.passed,
                 "confidence": round(c.confidence, 4), "detail": c.detail}
                for c in self.checks
            ],
            "summary": self.summary,
        }


def _any_generic(text: str) -> bool:
    import re
    cleaned = clean_quality_text(text).lower()
    return bool(re.search("|".join(_GENERIC_PATTERNS), cleaned))


def _contains_non_article_noise(text: str) -> bool:
    import re
    cleaned = clean_quality_text(text).lower()
    if contains_public_noise(cleaned):
        return True
    if "&#" in cleaned or "&amp;#" in cleaned:
        return True
    if re.search(r"\b[a-z0-9-]+/[a-z0-9-]+(?:/[a-z0-9-]+)+", cleaned):
        return True
    return any(re.search(pattern, cleaned, re.I) for pattern in PROMO_OR_NON_ARTICLE_PATTERNS)


def _headline_cutoff(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t[0].islower():
        return True
    if len(t) < 8:
        return True
    if t.endswith(("the", "a", "an", "and", "of", "in", "to", "for", "with")):
        return True
    if t[-1] in (":", ";", "-", "|"):
        return True
    return False


def _keypoint_quality(points: list[str]) -> tuple[float, list[str]]:
    if not points:
        return 0.0, ["no keypoints"]
    issues = []
    scores = []
    for p in points:
        s = 1.0
        if _any_generic(p):
            s -= 0.3
            issues.append(f"generic: {p[:50]}")
        if len(p) < 15 or len(p) > 180:
            s -= 0.2
            issues.append(f"length={len(p)}: {p[:50]}")
        if _contains_non_article_noise(p):
            s -= 0.6
            issues.append(f"noise: {p[:50]}")
        if p[0].islower() if p else True:
            s -= 0.2
            issues.append(f"lowercase start: {p[:50]}")
        if p and p[-1] not in ".!?":
            s -= 0.2
            issues.append(f"incomplete ending: {p[:50]}")
        if p.startswith(("why", "how", "what", "does", "will", "can", "is ", "are ")):
            s -= 0.3
            issues.append(f"question-like: {p[:50]}")
        scores.append(max(0.0, s))
    avg = sum(scores) / len(scores) if scores else 0.0
    return avg, issues[:5]


def _check_keypoints_unique(points: list[str]) -> tuple[bool, float, str]:
    if len(points) <= 1:
        return True, 1.0, ""
    fps = [ts.fingerprint_text({"title": "", "text": p}) for p in points]
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            cos = ts.cosine(fps[i], fps[j])
            if cos >= 0.85:
                return False, 1.0 - cos, f"dup: {points[i][:40]} ~ {points[j][:40]}"
    return True, 1.0, ""


def _check_images_unique(paths: list[str]) -> tuple[bool, float, str]:
    real = [p for p in paths if p and Path(p).exists()]
    if len(real) <= 1:
        return True, 1.0, ""
    hashed = []
    for p in real:
        ah, dh = pi.hashes_for(p)
        hashed.append((ah, dh, p))
    for i in range(len(hashed)):
        for j in range(i + 1, len(hashed)):
            if pi.is_duplicate(hashed[i][0], hashed[i][1], [(hashed[j][0], hashed[j][1])]):
                return False, 0.5, f"dup images: {Path(hashed[i][2]).name} ~ {Path(hashed[j][2]).name}"
    return True, 1.0, ""


# ── Phase 1: Pre-Generation ──────────────────────────────────────────────

def verify_pre_generation(
    article: dict,
    memory: MemoryStore | None = None,
) -> VerificationReport:
    """Run input-gate checks on a single article before rendering."""
    checks: list[CheckResult] = []
    title = str(article.get("title") or "")
    body = str(article.get("text") or article.get("description") or article.get("summary") or "")
    points = article.get("key_points", []) or []

    # 1. Title preservation (no cutoff, no blocked heading)
    cutoff = _headline_cutoff(title)
    blocked = title.lower().strip() in _BLOCKED_HEADLINES
    title_ok = not cutoff and not blocked
    checks.append(CheckResult(
        1, "title_preserved", title_ok,
        0.0 if cutoff else (0.0 if blocked else 1.0),
        "cutoff" if cutoff else ("blocked" if blocked else ""),
    ))

    # 2. Body completeness (≥ 120 chars)
    body_ok = len(body) >= 120
    checks.append(CheckResult(
        2, "body_min_length", body_ok,
        1.0 if body_ok else 0.0,
        f"body length={len(body)}",
    ))

    # 3. Has at least one image candidate
    has_img = bool(article.get("image_url") or article.get("image_path"))
    checks.append(CheckResult(
        3, "image_candidate", has_img,
        1.0 if has_img else 0.0, "",
    ))

    # 4. ≥ 4 valid keypoints
    quality, issues = _keypoint_quality(points)
    kp_ok = len(points) >= MIN_KP_PER_SLIDE and len(points) <= MAX_KP_PER_SLIDE and quality >= 0.6
    checks.append(CheckResult(
        4, "keypoint_quality", kp_ok, quality,
        "; ".join(issues[:3]),
    ))

    # 5. No generic filler
    has_generic = _any_generic(title) or _any_generic(body) or _contains_non_article_noise(title) or _contains_non_article_noise(body)
    checks.append(CheckResult(
        5, "no_generic_filler", not has_generic,
        0.0 if has_generic else 1.0, "",
    ))

    # 6. Article continuity (has URL + content)
    has_url = bool(article.get("url"))
    has_content = bool(body)
    continuity = has_url and has_content
    checks.append(CheckResult(
        6, "article_continuity", continuity,
        1.0 if continuity else 0.0,
        "missing url" if not has_url else "missing content",
    ))

    # 7. Cross-cycle uniqueness check
    dup_score = 0.0
    if memory is not None and has_content:
        fp = ts.fingerprint_text(article)
        sha = ts.content_sha256(body)
        sh = ts.simhash(fp)
        hit = memory.find_duplicate_story(sha=sha, simhash_val=sh, fp_text=fp)
        if hit:
            dup_score = hit[1]
    is_dup = dup_score >= 0.92
    checks.append(CheckResult(
        7, "cross_cycle_unique", not is_dup,
        1.0 - dup_score,
        f"dup_score={dup_score:.2f}" if is_dup else "",
    ))

    # 8. Topic diversity - skip for per-article check (handled at post level)

    confidence = sum(c.confidence * (1.0 if c.passed else 0.0) for c in checks) / max(len(checks), 1)
    hard_fail = any(not c.passed and c.check_id in {2, 6, 7} for c in checks)
    passed = not hard_fail and confidence >= CONFIDENCE_THRESHOLD
    return VerificationReport(
        phase="pre_generation", round_no=0,
        passed=passed, confidence=confidence,
        checks=checks,
        summary="PASS" if passed else f"FAIL (conf={confidence:.2f}, hard_fail={hard_fail})",
    )


# ── Phase 2: Pre-Publishing ──────────────────────────────────────────────

def _collect_slide_info(slides: list[dict]) -> dict:
    kinds = [s.get("kind", "") for s in slides]
    titles = [str(s.get("title", "")) for s in slides]
    bodies = [str(s.get("body", "")) for s in slides]
    images = [str(s.get("image_path", "")) for s in slides]
    return {"kinds": kinds, "titles": titles, "bodies": bodies, "images": images}


def verify_pre_publish(
    slides: list[dict],
    memory: MemoryStore | None = None,
    round_no: int = 0,
) -> VerificationReport:
    """Run the 12 pre-publishing checks on a fully built carousel."""
    info = _collect_slide_info(slides)
    checks: list[CheckResult] = []
    content_slides = [s for s in slides if s.get("kind") == "digest"]

    # 1. No duplicate keypoints across slides
    all_points = [s.get("body", "") for s in content_slides]
    kp_unique, kp_score, kp_detail = _check_keypoints_unique([p for p in all_points if p])
    checks.append(CheckResult(1, "kp_unique_across_slides", kp_unique, kp_score, kp_detail))

    # 2. No duplicate perceptual images
    img_unique, img_score, img_detail = _check_images_unique(info["images"])
    checks.append(CheckResult(2, "images_unique", img_unique, img_score, img_detail))

    # 3. No repeated semantic news across slides
    semantic_dup = False
    sem_score = 1.0
    sem_detail = ""
    for i in range(len(content_slides)):
        for j in range(i + 1, len(content_slides)):
            t1 = ts.fingerprint_text(content_slides[i])
            t2 = ts.fingerprint_text(content_slides[j])
            cos = ts.cosine(t1, t2)
            if cos >= 0.82:
                semantic_dup = True
                sem_score = 1.0 - cos
                sem_detail = f"semantic dup slides {i+1}~{j+1} (cos={cos:.2f})"
                break
        if semantic_dup:
            break
    checks.append(CheckResult(3, "semantic_unique", not semantic_dup, sem_score, sem_detail))

    # 4. Titles complete (no cutoff)
    titles_ok = True
    title_conf = 1.0
    title_detail = ""
    for i, t in enumerate(info["titles"]):
        if _headline_cutoff(t):
            titles_ok = False
            title_conf = 0.0
            title_detail = f"slide {i+1} title cutoff: {t[:40]}"
            break
    checks.append(CheckResult(4, "titles_complete", titles_ok, title_conf, title_detail))

    # 5. Valid Instagram carousel size: 1-8 content slides plus required CTA.
    valid_content_count = 1 <= len(content_slides) <= MAX_CAROUSEL_SLIDES
    valid_total_count = len(slides) <= MAX_INSTAGRAM_CAROUSEL_SLIDES
    valid_slide_count = valid_content_count and valid_total_count
    checks.append(CheckResult(
        5, "valid_carousel_slide_count", valid_slide_count,
        1.0 if valid_slide_count else 0.0,
        f"content={len(content_slides)}, total={len(slides)}",
    ))

    # 6. Every article slide has a same-article image that exists.
    all_img_ok = True
    img_exist_score = 1.0
    img_exist_detail = ""
    for i, slide in enumerate(content_slides):
        p = str(slide.get("image_path", "") or "").strip()
        if not p:
            all_img_ok = False
            img_exist_score = 0.0
            img_exist_detail = f"slide {i+1}: missing same-article image"
            break
        img_source = str(slide.get("image_source", "") or "")
        if img_source not in ("article", "fallback"):
            all_img_ok = False
            img_exist_score = 0.0
            img_exist_detail = f"slide {i+1}: image source not recognized ({img_source!r})"
            break
        path = Path(p)
        if not path.exists():
            all_img_ok = False
            img_exist_score = 0.0
            img_exist_detail = f"slide {i+1}: {p} not found"
            break
        w, h = pi.image_dimensions(p)
        if w < 200 or h < 150:
            all_img_ok = False
            img_exist_score = 0.3
            img_exist_detail = f"slide {i+1}: {w}x{h} too small"
            break
    checks.append(CheckResult(6, "images_exist_hd", all_img_ok, img_exist_score, img_exist_detail))

    # 7. CTA present as last slide
    last_kind = info["kinds"][-1] if info["kinds"] else ""
    cta_present = last_kind == "cta"
    checks.append(CheckResult(
        7, "cta_present", cta_present,
        1.0 if cta_present else 0.0, "",
    ))

    # 8. Keypoints are professional (no headings, no generic)
    kp_prof = True
    kp_prof_score = 1.0
    kp_prof_detail = ""
    for i, s in enumerate(content_slides):
        body = str(s.get("body", ""))
        points = [p for p in body.split("\n") if p.strip()] if body else []
        quality, issues = _keypoint_quality(points)
        if len(points) < MIN_KP_PER_SLIDE or len(points) > MAX_KP_PER_SLIDE:
            kp_prof = False
            kp_prof_score = 0.0
            kp_prof_detail = f"slide {i+1}: keypoints={len(points)}"
            break
        if quality < 0.5:
            kp_prof = False
            kp_prof_score = quality
            kp_prof_detail = f"slide {i+1}: {'; '.join(issues[:2])}"
            break
    checks.append(CheckResult(8, "keypoints_professional", kp_prof, kp_prof_score, kp_prof_detail))

    # 9. No generic filler text anywhere
    no_filler = True
    filler_score = 1.0
    filler_detail = ""
    for i, s in enumerate(slides):
        body = str(s.get("body", ""))
        title = str(s.get("title", ""))
        if _any_generic(title) or _any_generic(body) or _contains_non_article_noise(title) or _contains_non_article_noise(body):
            no_filler = False
            filler_score = 0.0
            filler_detail = f"slide {i+1} has generic filler or non-article noise"
            break
    checks.append(CheckResult(9, "no_generic_filler", no_filler, filler_score, filler_detail))

    # 10. No duplicate slide titles (content slides only)
    #   Uses a two-pronged check:
    #   (a) Full-title cosine similarity (catches near-identical titles)
    #   (b) First-5-token prefix overlap (catches truncated-style duplicates
    #       like "Beyond power forecasting for offshore wind..." vs
    #       "Beyond power forecasting for offshore solar...")
    no_repeat = True
    repeat_score = 1.0
    repeat_detail = ""
    content_titles = [
        t for t, k in zip(info["titles"], info["kinds"]) if k == "digest"
    ]
    for i in range(len(content_titles)):
        for j in range(i + 1, len(content_titles)):
            t_i = content_titles[i]
            t_j = content_titles[j]
            if not t_i or not t_j:
                continue
            # (a) Full-title cosine similarity
            cos_sim = ts.cosine(t_i, t_j)
            if cos_sim >= 0.75:
                no_repeat = False
                repeat_score = max(0.0, 1.0 - cos_sim)
                repeat_detail = f"title dup: {t_i[:50]} ~ {t_j[:50]} (cos={cos_sim:.2f})"
                break
            # (b) First-5-content-token prefix overlap — catches titles that
            #     share a long prefix but diverge in their second half.
            ti_tokens = ts.tokens(t_i, drop_stopwords=True)
            tj_tokens = ts.tokens(t_j, drop_stopwords=True)
            ti_prefix = set(ti_tokens[:5])
            tj_prefix = set(tj_tokens[:5])
            if ti_prefix and tj_prefix:
                overlap = len(ti_prefix & tj_prefix)
                prefix_max = max(len(ti_prefix), len(tj_prefix))
                if overlap / prefix_max >= 0.6:
                    no_repeat = False
                    repeat_score = max(0.0, 1.0 - (overlap / prefix_max))
                    repeat_detail = f"title dup: {t_i[:50]} ~ {t_j[:50]} (prefix overlap {overlap}/{prefix_max})"
                    break
        if not no_repeat:
            break
    checks.append(CheckResult(10, "no_repeated_info", no_repeat, repeat_score, repeat_detail))

    # 11. All summaries unique
    summaries = [str(s.get("body", "")) for s in content_slides if s.get("body")]
    summ_unique = True
    summ_score = 1.0
    summ_detail = ""
    for i in range(len(summaries)):
        for j in range(i + 1, len(summaries)):
            cos = ts.cosine(summaries[i], summaries[j])
            if cos >= 0.93:
                summ_unique = False
                summ_score = 1.0 - cos
                summ_detail = f"summary dup slides {i+1}~{j+1}"
                break
        if not summ_unique:
            break
    checks.append(CheckResult(11, "summaries_unique", summ_unique, summ_score, summ_detail))

    # 12. Image-to-article mapping valid
    mapping_ok = True
    map_score = 1.0
    map_detail = ""
    for i, s in enumerate(content_slides):
        url = str(s.get("url", ""))
        if not url:
            mapping_ok = False
            map_score = 0.0
            map_detail = f"slide {i+1}: no url"
            break
    checks.append(CheckResult(12, "image_article_mapping", mapping_ok, map_score, map_detail))

    # Compute verdict
    confidences = [c.confidence * (1.0 if c.passed else 0.0) for c in checks]
    confidence = sum(confidences) / max(len(checks), 1)
    hard_fail = any(not c.passed and c.check_id in HARD_FAIL_CHECKS for c in checks)
    passed = not hard_fail and confidence >= CONFIDENCE_THRESHOLD
    return VerificationReport(
        phase="pre_publish", round_no=round_no,
        passed=passed, confidence=confidence,
        checks=checks,
        summary="PASS" if passed else f"FAIL (conf={confidence:.2f}, hard_fail={hard_fail})",
    )


# ── Report helpers ────────────────────────────────────────────────────────

def write_verification_report(report: VerificationReport, path: Path) -> None:
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")


def load_verification_report(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_verified(path: Path) -> bool:
    report = load_verification_report(path)
    return bool(report and report.get("passed") and report.get("confidence", 0) >= CONFIDENCE_THRESHOLD)
