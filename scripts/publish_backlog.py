"""publish_backlog.py — find and publish every unposted Instagram carousel across all batches.

Searches all batch directories in reports/instagram_posts/, identifies carousels
that were never successfully published (no ``published_at`` in manifest, not in
``published_posts`` DB table), rebuilds fresh publish manifests, and publishes
them.

Can also optionally re-render carousels from the original DB summaries with the
latest image-extraction pipeline (enabling fresh OG images from article URLs).

The ``--recover-rejected`` mode re-evaluates articles that were previously
rejected by quality filters (persisted in the ``rejected_articles`` table). It
re-scrapes each URL with the latest OG-extraction pipeline and, if valid content
and images are found, injects them into the publishing pipeline as fresh carousels.

Usage:
    python scripts/publish_backlog.py                          # scan & report only
    python scripts/publish_backlog.py --publish                 # scan & publish
    python scripts/publish_backlog.py --all                     # publish all pending batches
    python scripts/publish_backlog.py --rebuild                 # rebuild carousels from DB before publishing
    python scripts/publish_backlog.py --publish --rebuild       # fresh images + publish
    python scripts/publish_backlog.py --recover-rejected        # re-check rejected articles only
    python scripts/publish_backlog.py --recover-rejected --publish   # re-check + publish rescued articles
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings
from email_summary_agent.models import EmailSummary
from email_summary_agent.publisher import publish_ready_carousels, write_publish_manifest


# ── helpers ──────────────────────────────────────────────────────────────────


def _iter_carousels(instagram_dir: Path) -> Iterator[tuple[Path, Path]]:
    """Yield (batch_dir, carousel_dir) for every carousel in the filesystem."""
    if not instagram_dir.exists():
        return
    for batch_dir in sorted(instagram_dir.iterdir()):
        if not batch_dir.is_dir() or batch_dir.name.startswith("."):
            continue
        for carousel_dir in sorted(batch_dir.iterdir()):
            if not carousel_dir.is_dir() or carousel_dir.name.startswith("."):
                continue
            yield (batch_dir, carousel_dir)


def _has_published_at(manifest_path: Path, carousel_dir: Path) -> bool:
    """Check if a specific carousel is marked published in the batch manifest."""
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    folder_str = str(carousel_dir)
    for post in manifest.get("posts", []):
        if str(post.get("folder", "")) == folder_str:
            published_at = post.get("published_at")
            if published_at:
                return True
            status = post.get("status", "")
            if status == "published":
                return True
    return False


def _is_published_in_db(db_path: Path, carousel_name: str) -> bool:
    """Check if the carousel name appears as a post_id in published_posts."""
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT 1 FROM published_posts WHERE post_id = ? LIMIT 1",
            (carousel_name,),
        ).fetchone()
        conn.close()
        return row is not None
    except sqlite3.OperationalError:
        pass
    return False


def _has_failed_marker(carousel_dir: Path) -> bool:
    return (carousel_dir / "VERIFY_FAILED").exists()


def _count_slides(carousel_dir: Path) -> int:
    return len(list(carousel_dir.glob("slide_*.png")))


def _batch_name(batch_dir: Path) -> str:
    """Return a human-readable batch name from dir name or mtime."""
    try:
        dt = datetime.strptime(batch_dir.name[:15], "%Y%m%d-%H%M%S")
        return dt.strftime("%b %d %Y %H:%M")
    except ValueError:
        pass
    try:
        mtime = datetime.fromtimestamp(batch_dir.stat().st_mtime)
        return mtime.strftime("%b %d %Y %H:%M")
    except OSError:
        return batch_dir.name[:20]


# ── rebuild from DB summaries (fresh OG image extraction) ────────────────────


def _load_summaries_from_db(db_path: Path) -> list[dict]:
    """Load all processed email summaries from the database."""
    if not db_path.exists():
        print(f"  DB not found: {db_path}")
        return []
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT processed_at, summary_json FROM processed_emails ORDER BY processed_at ASC"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"  Cannot query DB: {exc}")
        return []
    finally:
        conn.close()

    summaries = []
    for row in rows:
        try:
            data = json.loads(row["summary_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        summaries.append(data)
    return summaries


def _rebuild_carousels_from_db(settings: Settings) -> list[Path]:
    """Rebuild carousels from DB summaries using the latest pipeline (fresh OG extraction)."""
    from email_summary_agent.instagram import write_instagram_carousels
    from email_summary_agent.memory_store import MemoryStore

    summaries_data = _load_summaries_from_db(settings.db_path)
    if not summaries_data:
        print("  No summaries found in DB to rebuild.")
        return []

    from dataclasses import fields
    allowed_field_names = {field.name for field in fields(EmailSummary)}

    email_summaries = []
    for data in summaries_data:
        try:
            payload = {k: v for k, v in data.items() if k in allowed_field_names}
            # Sanitize fields (mirrors rebuild_instagram_backlog.py)
            for key in ("key_points", "companies", "models", "topics"):
                if not isinstance(payload.get(key), list):
                    payload[key] = []
            for key in ("message_key", "subject", "source_date", "headline", "summary"):
                payload[key] = str(payload.get(key) or "")
            for key in ("article_url", "article_title", "article_image_path", "article_image_url", "article_excerpt"):
                if key in payload:
                    payload[key] = str(payload.get(key) or "")
            payload["confidence"] = float(payload.get("confidence") or 0.7)
            if not isinstance(payload.get("article_items"), list):
                payload["article_items"] = []
            email_summaries.append(EmailSummary(**payload))
        except (TypeError, ValueError) as exc:
            print(f"  Skipping malformed summary: {exc}")
            continue

    if not email_summaries:
        print("  No valid summaries could be reconstructed from DB.")
        return []

    memory = None
    if settings.enable_memory:
        try:
            memory = MemoryStore(settings.db_path)
        except Exception:
            pass

    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    carousel_dirs = write_instagram_carousels(
        email_summaries,
        settings.instagram_dir,
        clear_existing=False,
        db_path=None,
        flush_partial=True,
        memory=None,
        enable_verification=settings.enable_verification,
        max_verify_rounds=settings.max_verification_rounds,
    )

    if memory:
        try:
            memory.close()
        except Exception:
            pass

    return carousel_dirs


# ── scan & report ────────────────────────────────────────────────────────────


def scan_backlog(settings: Settings) -> list[tuple[Path, Path, str]]:
    """Scan all batches and return list of (batch_dir, carousel_dir, reason)."""
    pending: list[tuple[Path, Path, str]] = []
    batches_seen: set[str] = set()

    for batch_dir, carousel_dir in _iter_carousels(settings.instagram_dir):
        batchname = _batch_name(batch_dir)
        batches_seen.add(batch_dir.name)

        carousel_name = carousel_dir.name

        if _has_failed_marker(carousel_dir):
            pending.append((batch_dir, carousel_dir, "VERIFY_FAILED — rebuild needed"))
            continue

        manifest = batch_dir / "publish_manifest.json"
        if _has_published_at(manifest, carousel_dir):
            continue  # already published
        if _is_published_in_db(settings.db_path, carousel_name):
            continue  # already recorded in DB

        slides = _count_slides(carousel_dir)
        if slides == 0:
            pending.append((batch_dir, carousel_dir, "no slides — corrupted"))
            continue

        pending.append((batch_dir, carousel_dir, f"{slides} slides — pending"))

    return pending


def print_report(pending: list[tuple[Path, Path, str]]) -> None:
    """Print a human-readable report of pending carousels."""
    if not pending:
        print("✅ All carousels are published. No backlog found.")
        return

    batches: dict[str, list[tuple[Path, str]]] = {}
    for batch_dir, carousel_dir, reason in pending:
        name = _batch_name(batch_dir)
        batches.setdefault(name, []).append((carousel_dir, reason))

    total = len(pending)
    print(f"\n[BACKLOG] {total} unposted carousel(s) found\n")
    for batchname in sorted(batches, reverse=True):
        items = batches[batchname]
        print(f"  Batch: {batchname}  ({len(items)} pending)")
        for carousel_dir, reason in items:
            print(f"    PENDING: {carousel_dir.name[:80]}")
            print(f"        {reason}")


# ── recover rejected articles (re-check with fresh OG extraction) ───────────


def _recover_rejected_articles(
    settings: Settings,
    *,
    do_publish: bool = False,
) -> int:
    """Re-check articles in the rejected_articles table.

    Re-scrapes each URL with the latest OG-extraction pipeline. If valid content
    and images are found, injects them into the publishing pipeline as carousels.

    Returns the number of articles successfully rescued.
    """
    from email_summary_agent.memory_store import MemoryStore
    from email_summary_agent.ig_image import _fetch_og_image_from_url
    from email_summary_agent.ig_utils import _scrape_article_text

    try:
        memory = MemoryStore(settings.db_path)
    except Exception as exc:
        print(f"  Cannot open memory store: {exc}")
        return 0

    rejected = memory.pop_rejected_for_retry(
        min_retry_interval_hours=0,  # allow immediate retry (manual invocation)
        max_attempts=3,
        limit=50,
    )
    if not rejected:
        # Check if table exists but is empty
        try:
            count = memory.get_rejected_count()
            if count == 0:
                print("  No rejected articles in the database.")
            else:
                print(f"  All {count} rejected article(s) have exhausted retries (max 3).")
                print(f"  Use --clear-rejected to reset them.")
        except Exception:
            print("  Table 'rejected_articles' does not exist yet (no articles have been rejected going forward).")
            print("  Newly rejected articles from future pipeline runs will be captured automatically.")
        memory.close()
        return 0

    print(f"\n  Re-checking {len(rejected)} previously rejected article(s) with fresh OG extraction...\n")

    rescued: list[dict] = []
    for idx, article in enumerate(rejected, 1):
        url = article.get("url") or article.get("_rejected_url", "")
        title = article.get("title", "")[:60]
        reason = article.get("_rejected_reason", "unknown")
        url_preview = url[:70] if url else "(no url)"
        print(f"  [{idx}/{len(rejected)}] {title!r}  ({reason})")
        print(f"      {url_preview}")

        # Step 1: Re-scrape the article text from the live URL
        if url:
            scraped = _scrape_article_text(url)
            if scraped and len(scraped.strip()) > 100:
                article["scraped_content"] = scraped
                article["text"] = scraped
                print(f"      -> scraped {len(scraped)} chars of content")
            else:
                print(f"      -> scraped content too short or empty ({len(scraped) if scraped else 0} chars)")
                continue  # skip — can't verify content
        else:
            continue  # skip — no URL to check

        # Step 2: Attempt OG image extraction
        img_url = _fetch_og_image_from_url(url)
        if img_url:
            article["image_url"] = img_url
            article["image_path"] = ""
            print(f"      -> OG image found: {img_url[:60]}...")
        else:
            # Try scraping images from the page
            from email_summary_agent.ig_utils import _scrape_article_images
            scraped_img = _scrape_article_images(url)
            if scraped_img:
                article["image_url"] = scraped_img
                article["image_path"] = ""
                print(f"      -> scraped image found: {scraped_img[:60]}...")
            else:
                print(f"      -> no image found, skipping")
                continue

        rescued.append(article)
        # Mark as recovered so it's excluded from future retry polls
        memory.resolve_rejected_article(url, "recovered")

    memory.close()

    if not rescued:
        print("\n  No articles could be rescued from the rejected pool.")
        return 0

    print(f"\n  Rescued {len(rescued)} article(s) with fresh content + images.")

    # Build a synthetic EmailSummary so we can feed rescued articles to the
    # Instagram pipeline.
    from datetime import datetime
    from email_summary_agent.models import EmailSummary

    now_str = datetime.now().isoformat()
    sanitized_items = []
    for a in rescued:
        sanitized_items.append({
            "url": str(a.get("url", "")),
            "title": str(a.get("title", "")),
            "description": a.get("scraped_content", "") or a.get("description", "") or "",
            "text": a.get("scraped_content", "") or a.get("text", "") or "",
            "image_url": str(a.get("image_url", "") or ""),
            "image_path": str(a.get("image_path", "") or ""),
        })

    rescued_summary = EmailSummary(
        message_key=f"rejected-recovery:{len(rescued)}-{datetime.now().timestamp():.0f}",
        subject="Recovered Articles",
        source_date=now_str,
        headline=f"Recovered {len(rescued)} articles from rejected pool",
        summary="Articles previously rejected by quality filters, re-scraped with fresh OG images.",
        key_points=[],
        companies=[],
        models=[],
        topics=["ai", "recovery"],
        confidence=0.7,
        article_items=sanitized_items,
        article_url=str(sanitized_items[0].get("url", "")) if sanitized_items else "",
        article_title=str(sanitized_items[0].get("title", "")) if sanitized_items else "",
        article_image_path="",
        article_image_url="",
    )

    # Generate carousels from rescued articles
    from email_summary_agent.instagram import write_instagram_carousels

    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    carousel_dirs = write_instagram_carousels(
        [rescued_summary],
        settings.instagram_dir,
        clear_existing=False,
        db_path=None,
        flush_partial=True,
        memory=None,
        enable_verification=settings.enable_verification,
        max_verify_rounds=settings.max_verification_rounds,
    )

    print(f"  Generated {len(carousel_dirs)} carousel(s) from rescued articles.")

    if do_publish and carousel_dirs:
        if not settings.public_media_base_url:
            print("  PUBLIC_MEDIA_BASE_URL not set; skipping publish.")
            return len(rescued)
        settings.validate_instagram_publish()
        manifest_path = write_publish_manifest(carousel_dirs, settings.public_media_base_url)
        if manifest_path:
            published = publish_ready_carousels(settings, manifest_path)
            print(f"  Published {published} carousel(s) from rescued articles.")

    return len(rescued)


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find & publish every unposted Instagram carousel across all batches."
    )
    parser.add_argument("--publish", action="store_true", help="Actually publish pending carousels")
    parser.add_argument(
        "--all", action="store_true",
        help="Publish from all batches, not just the latest one"
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Rebuild carousels from DB summaries (fresh OG images) before publishing"
    )
    parser.add_argument(
        "--recover-rejected", action="store_true",
        help="Re-check previously rejected articles with fresh OG extraction and rescue those with valid content+images"
    )
    parser.add_argument(
        "--report-rejected", action="store_true",
        help="Show a breakdown of rejected articles by reason and retry status"
    )
    parser.add_argument(
        "--retry-summary", action="store_true",
        help="Show which retry attempts succeeded by reason category"
    )
    parser.add_argument(
        "--clear-rejected", action="store_true",
        help="Clear all entries from the rejected_articles table"
    )
    parser.add_argument(
        "--cleanup-verify-failed", action="store_true",
        help="Remove VERIFY_FAILED zombie carousel directories"
    )
    args = parser.parse_args()

    settings = Settings.from_env()

    # ── Cleanup zombies ──────────────────────────────────────────────────────
    if args.cleanup_verify_failed:
        from scripts.publish_latest_instagram import _cleanup_verify_failed_carousels
        _cleanup_verify_failed_carousels(settings.instagram_dir)
        return 0

    # ── Report rejected articles breakdown ───────────────────────────────────
    if args.report_rejected:
        from email_summary_agent.memory_store import MemoryStore
        try:
            memory = MemoryStore(settings.db_path)
        except Exception as exc:
            print(f"Cannot open memory store: {exc}")
            return 1

        total = memory.get_rejected_count()
        by_reason = memory.count_rejected_by_reason()
        memory.close()

        if total == 0:
            print("\n  [REJECTED ARTICLES] No rejected articles in the database.\n")
            return 0

        print(f"\n  [REJECTED ARTICLES] {total} article(s) pending retry\n")
        for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
        print()
        return 0

    # ── Retry summary ────────────────────────────────────────────────────────
    if args.retry_summary:
        from email_summary_agent.memory_store import MemoryStore
        try:
            memory = MemoryStore(settings.db_path)
        except Exception as exc:
            print(f"Cannot open memory store: {exc}")
            return 1

        summary = memory.get_retry_summary()
        memory.close()

        if not summary:
            print("\n  [RETRY SUMMARY] No rejected articles in the database.\n")
            return 0

        tot_pending = 0
        tot_recovered = 0
        tot_exhausted = 0
        print("\n  [RETRY SUMMARY — outcomes by reason category]")
        for reason in sorted(summary):
            s = summary[reason]
            p, r, e = s.get("pending", 0), s.get("recovered", 0), s.get("exhausted", 0)
            tot_pending += p
            tot_recovered += r
            tot_exhausted += e
            print(f"  \n  {reason}:")
            print(f"    pending:     {p}")
            print(f"    recovered:   {r}")
            print(f"    exhausted:   {e}")
        print(f"  \n  Totals:")
        print(f"    pending:     {tot_pending}")
        print(f"    recovered:   {tot_recovered}")
        print(f"    exhausted:   {tot_exhausted}")
        total = tot_pending + tot_recovered + tot_exhausted
        print(f"    grand total: {total}")
        print()
        return 0

    # ── Recover rejected articles ────────────────────────────────────────────
    if args.recover_rejected or args.clear_rejected:
        from email_summary_agent.memory_store import MemoryStore
        try:
            memory = MemoryStore(settings.db_path)
        except Exception as exc:
            print(f"Cannot open memory store: {exc}")
            return 1

        if args.clear_rejected:
            n = memory.clear_rejected()
            print(f"Cleared {n} entry(ies) from rejected_articles table.")
            memory.close()
            return 0

        rescued = _recover_rejected_articles(settings, do_publish=args.publish)
        count = memory.get_rejected_count()
        if count:
            print(f"\n  {count} rejected article(s) still remaining (will retry on next run).")
        memory.close()
        if rescued:
            print(f"\n  Successfully rescued {rescued} article(s) that now have valid content + images.\n")
            # After recovery, scan and print the backlog so user sees the new carousels
            pending = scan_backlog(settings)
            print_report(pending)
        return 0

    # ── Rebuild from DB with fresh OG extraction ─────────────────────────────
    if args.rebuild:
        print("Rebuilding carousels from DB summaries (fresh OG extraction)...")
        new_dirs = _rebuild_carousels_from_db(settings)
        print(f"  Rebuilt {len(new_dirs)} carousel(s) from DB summaries.")
        print("  These will appear in the batch listing below.\n")

    # ── Scan for backlog ─────────────────────────────────────────────────────
    pending = scan_backlog(settings)
    print_report(pending)

    if not pending:
        return 0

    # ── Publish ──────────────────────────────────────────────────────────────
    if not args.publish:
        print("\n  Run with --publish to publish pending carousels.")
        print("  Run with --rebuild --publish to rebuild from DB (fresh OG images) then publish.")
        return 0

    if not settings.public_media_base_url:
        print("\n  PUBLIC_MEDIA_BASE_URL is not set. Publishing requires deployed public URLs.")
        print("  Set it in .env or GitHub Actions secrets.")
        return 1

    settings.validate_instagram_publish()

    # Group pending carousels by batch
    batch_map: dict[Path, list[Path]] = {}
    for batch_dir, carousel_dir, _reason in pending:
        batch_map.setdefault(batch_dir, []).append(carousel_dir)

    total_published = 0
    total_failed = 0
    total_retryable = 0

    for batch_dir in sorted(batch_map, key=lambda p: p.name):
        print(f"\n  Publishing batch: {_batch_name(batch_dir)}")

        # Write manifest for pending carousels in this batch
        manifest_path = write_publish_manifest(
            batch_map[batch_dir], settings.public_media_base_url
        )
        if not manifest_path:
            print("    No manifest created (all carousels filtered out).")
            continue

        if args.all or len(batch_map) == 1:
            # Publish all pending
            try:
                published = publish_ready_carousels(settings, manifest_path)
            except Exception as exc:
                print(f"    ERROR during publish: {exc}")
                published = 0

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for post in manifest.get("posts", []):
                status = post.get("status", "unknown")
                if status == "published":
                    total_published += 1
                elif status == "publish_failed_retryable":
                    total_retryable += 1
                elif status in ("publish_failed",):
                    total_failed += 1

            print(f"    Published {published} carousel(s) from this batch.")
        else:
            # --publish without --all: only publish the latest batch
            print("    Run with --all to publish from ALL batches (not just latest).")
            break

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  Published: {total_published}")
    if total_retryable:
        print(f"  Retryable failures: {total_retryable} (will retry next run)")
    if total_failed:
        print(f"  Permanent failures: {total_failed}")
    print("=" * 60)

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
