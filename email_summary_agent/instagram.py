from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EmailSummary
from .ig_constants import POSTING_SLOTS
from .ig_utils import _email_datetime, _cleanup_existing_outputs, _slugify
from .ig_slide_builder import _build_slide_specs
from .post_planner import plan_summary_parts
from .ig_renderer_pil import _write_slide_png, _qa_slide_png
from .ig_caption import _build_caption


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
    db_path: Path | None = None,
    flush_partial: bool = False,
    memory: Any | None = None,
    enable_verification: bool = True,
    max_verify_rounds: int = 2,
) -> list[Path]:
    """Create Instagram carousel batches.

    Articles from all summaries (plus any carryover) are pooled, deduplicated and
    split into posts of exactly 8 unique articles via ``post_planner``. Each
    carousel ends with a mandatory CTA slide. Used images are recorded to the
    persistent memory store so they are never reused across runs.

    When ``enable_verification`` is True the carousel runs the Phase-2
    pre-publish verifier and blocks failed posts.
    """
    if not summaries:
        return []
    if clear_existing:
        _cleanup_existing_outputs(output_dir)

    now = generated_at or datetime.now(timezone.utc).astimezone()
    batch_dir = output_dir / now.strftime("%Y%m%d-%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Use passed memory or open one from db_path.
    if memory is None and db_path is not None:
        memory = _open_memory(db_path)
    effective_flush = flush_partial or memory is None

    global_used_image_paths: set[str] = _load_used_images_from_db(db_path)
    global_used_image_urls: set[str] = set()
    used_image_hashes = memory.load_used_image_hashes() if memory is not None else []

    parts = plan_summary_parts(summaries, memory, flush=effective_flush)

    carousel_dirs: list[Path] = []
    index_rows: list[str] = []
    for carousel_index, part_summary in enumerate(parts, start=1):
        index = carousel_index
        email_dt = _email_datetime(part_summary.source_date) or now
        slug = _slugify(part_summary.headline or part_summary.subject or f"ai-news-{index}")
        folder_name = f"{index:02d}_{email_dt.strftime('%Y%m%d-%H%M')}_{slug}"
        carousel_dir = batch_dir / folder_name
        carousel_dir.mkdir(parents=True, exist_ok=True)

        content_slides = _build_slide_specs(
            part_summary, email_dt, global_used_image_paths, global_used_image_urls
        )

        # ── Phase 2: Pre-publish verification ──────────────────────────────
        verification_ok = True
        if enable_verification:
            from .verifier import verify_pre_publish, write_verification_report
            for round_no in range(1, max_verify_rounds + 1):
                report = verify_pre_publish(content_slides, memory, round_no=round_no)
                ver_path = carousel_dir / "verification_report.json"
                write_verification_report(report, ver_path)
                if memory is not None:
                    memory.record_verification(
                        post_id=carousel_dir.name,
                        round_no=round_no,
                        status="PASS" if report.passed else "FAIL",
                        confidence=report.confidence,
                        report=report.to_dict(),
                    )
                if report.passed:
                    break
                # Failed: try targeted recovery
                if round_no < max_verify_rounds:
                    _repair_failed_slides(content_slides, report, memory)
                else:
                    verification_ok = False

        if not verification_ok:
            (carousel_dir / "VERIFY_FAILED").touch()
            _safe_print(f"  VERIFY FAILED {carousel_dir.name} — skipping")
            continue

        # Record image usage (path + perceptual hash) so it is never reused.
        for slide in content_slides:
            img = str(slide.get("image_path", "")).strip()
            if img:
                global_used_image_paths.add(img)
                _remember_image(memory, used_image_hashes, img, str(slide.get("url", "")))

        slides = content_slides

        qa_issues_any: list[str] = []
        for slide_number, slide in enumerate(slides, start=1):
            slide_path = carousel_dir / f"slide_{slide_number:02d}.png"
            _write_slide_png(
                slide_path,
                slide_number=slide_number,
                total_slides=len(slides),
                slide=slide,
                email_dt=email_dt,
            )
            qa_issues = _qa_slide_png(slide_path)
            if qa_issues:
                qa_issues_any.extend([f"slide_{slide_number:02d}: {issue}" for issue in qa_issues])

        if qa_issues_any:
            (carousel_dir / "qa_issues.txt").write_text("\n".join(qa_issues_any), encoding="utf-8")

        _save_used_images_to_db(db_path, global_used_image_paths)

        caption = _build_caption(part_summary)
        (carousel_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (carousel_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "email_received_at": email_dt.isoformat(timespec="minutes"),
                    "recommended_post_time": POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)],
                    "headline": part_summary.headline,
                    "subject": part_summary.subject,
                    "source_date": part_summary.source_date,
                    "companies": part_summary.companies,
                    "models": part_summary.models,
                    "topics": part_summary.topics,
                    "article_url": part_summary.article_url,
                    "article_title": part_summary.article_title,
                    "article_image_path": part_summary.article_image_path,
                    "article_image_url": part_summary.article_image_url,
                    "article_items": part_summary.article_items or [],
                    "carousel_part": getattr(part_summary, "_carousel_part", None),
                    "carousel_total_parts": getattr(part_summary, "_carousel_total_parts", None),
                    "content_slide_count": len(content_slides),
                    "has_cta": True,
                    "slides": [slide["title"] for slide in slides],
                },
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        index_rows.append(
            f'<li><a href="{carousel_dir.name}/slide_01.png">{html.escape(part_summary.headline)}</a> '
            f'<span>{len(slides)} slides - {POSTING_SLOTS[(index - 1) % len(POSTING_SLOTS)]}</span></li>'
        )
        carousel_dirs.append(carousel_dir)

    (batch_dir / "index.html").write_text(_render_index(index_rows), encoding="utf-8")
    if memory is not None:
        memory.prune()
        memory.close()
    return carousel_dirs


def _repair_failed_slides(slides: list[dict], report, memory) -> None:
    """Attempt targeted recovery for verification failures."""
    from .ig_copy import layout_safe_headline
    failed_ids = {c.check_id for c in report.checks if not c.passed}
    for slide in slides:
        if 4 in failed_ids:
            t = str(slide.get("title", ""))
            slide["title"] = layout_safe_headline(t, fallback="AI Update")
        if 1 in failed_ids or 8 in failed_ids:
            body = str(slide.get("body", ""))
            if body:
                lines = [line for line in body.split("\n") if line.strip()]
                from .ig_keypoints import _strip_noise
                body = "\n".join(_strip_noise(line) for line in lines)
                slide["body"] = body


def _safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe, flush=True)


def _open_memory(db_path: Path | None):
    if not db_path:
        return None
    try:
        from .memory_store import MemoryStore

        return MemoryStore(db_path)
    except Exception:
        return None


def _remember_image(memory, used_hashes: list, path: str, src_url: str) -> None:
    if memory is None:
        return
    try:
        from . import perceptual_image as pi

        ahash, dhash = pi.hashes_for(path)
        used_hashes.append((ahash, dhash))
        memory.record_image(path=path, src_url=src_url, ahash=ahash, dhash=dhash)
    except Exception:
        pass


def _render_index(rows: list[str]) -> str:
    items = "\n".join(rows)
    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "  <title>Instagram Carousel Batch</title>\n"
        "  <style>\n"
        "    *, *::before, *::after { box-sizing: border-box; }\n"
        "    body { margin:0; background:#050505; color:#fff; font:16px/1.5 Arial, sans-serif; }\n"
        "    main { max-width:960px; margin:0 auto; padding:48px 24px; }\n"
        "    h1 { font-size:clamp(2rem, 8vw, 5rem); line-height:1; margin:0 0 24px; }\n"
        "    p { color:#cfcfcf; max-width:62ch; }\n"
        "    ol { list-style:none; padding:0; display:grid; gap:12px; }\n"
        "    li { display:flex; justify-content:space-between; gap:16px; border:1px solid #2b2b2b; padding:16px; background:#101010; }\n"
        "    a { color:#e8ff47; font-weight:800; text-decoration:none; }\n"
        "    span { color:#aaa; white-space:nowrap; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        "    <h1>Instagram carousel batch</h1>\n"
        "    <p>Each folder is one email-based post. Upload the PNG slides in order as a carousel.</p>\n"
        f"    <ol>{items}</ol>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _load_used_images_from_db(db_path: Path | None) -> set[str]:
    """Load previously-used image paths from the agent SQLite database."""
    if not db_path:
        return set()
    try:
        import sqlite3 as _sqlite3
        with _sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS used_images "
                "(path TEXT PRIMARY KEY, url TEXT, used_at TEXT NOT NULL)"
            )
            rows = conn.execute("SELECT path FROM used_images").fetchall()
            return {row[0] for row in rows}
    except Exception:
        return set()


def _save_used_images_to_db(db_path: Path | None, paths: set[str]) -> None:
    """Persist the set of used image paths into the agent SQLite database."""
    if not db_path or not paths:
        return
    try:
        import sqlite3 as _sqlite3
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc).isoformat(timespec="seconds")
        with _sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS used_images "
                "(path TEXT PRIMARY KEY, url TEXT, used_at TEXT NOT NULL)"
            )
            conn.executemany(
                "INSERT OR IGNORE INTO used_images (path, used_at) VALUES (?, ?)",
                [(p, now) for p in paths if p],
            )
            conn.commit()
    except Exception:
        pass
