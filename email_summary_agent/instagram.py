from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EmailSummary
from .ig_constants import POSTING_SLOTS, IMAGE_LIBRARY_DIR, IMAGE_INDEX_PATH
from .ig_utils import _email_datetime, _cleanup_existing_outputs, _slugify, _scrape_article_text
from .ig_slide_builder import _split_summary_for_carousels, _build_slide_specs
from .ig_renderer_pil import _write_slide_png, _qa_slide_png
from .ig_caption import _build_caption
from .ig_image import (
    _find_library_image,
    _find_reference_image_for_article_unique,
    _fetch_og_image_from_url,
)


def write_instagram_carousels(
    summaries: list[EmailSummary],
    output_dir: Path,
    generated_at: datetime | None = None,
    clear_existing: bool = False,
    db_path: Path | None = None,
) -> list[Path]:
    """Create Instagram carousel batches."""
    if not summaries:
        return []
    if clear_existing:
        _cleanup_existing_outputs(output_dir)

    now = generated_at or datetime.now(timezone.utc).astimezone()
    batch_dir = output_dir / now.strftime("%Y%m%d-%H%M%S")
    batch_dir.mkdir(parents=True, exist_ok=True)

    global_used_image_paths: set[str] = _load_used_images_from_db(db_path)

    carousel_dirs: list[Path] = []
    index_rows: list[str] = []
    carousel_index = 0
    for summary in summaries:
        email_dt = _email_datetime(summary.source_date) or now
        for part_summary in _split_summary_for_carousels(summary):
            carousel_index += 1
            index = carousel_index
            slug = _slugify(part_summary.headline or part_summary.subject or f"ai-news-{index}")
            folder_name = f"{index:02d}_{email_dt.strftime('%Y%m%d-%H%M')}_{slug}"
            carousel_dir = batch_dir / folder_name
            carousel_dir.mkdir(parents=True, exist_ok=True)

            slides = _build_slide_specs(part_summary, email_dt, global_used_image_paths)
            for slide in slides:
                img = str(slide.get("image_path", "")).strip()
                if img:
                    global_used_image_paths.add(img)

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
                (carousel_dir / "qa_issues.txt").write_text(
                    "\n".join(qa_issues_any), encoding="utf-8"
                )

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
    return carousel_dirs


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
