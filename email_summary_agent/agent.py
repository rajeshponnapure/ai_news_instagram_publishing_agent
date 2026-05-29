from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Settings
from .article_assembler import assemble as assemble_articles
from .article_enricher import ArticleData, enrich_email_with_articles
from .db import AgentStore
from .digest import parse_news_items
from .email_client import ImapEmailClient
from .instagram import write_instagram_carousels
from .memory_store import MemoryStore
from .models import EmailItem, EmailSummary
from .publisher import publish_ready_carousels, write_publish_manifest
from .report import write_report
from .summarizer import SummaryProvider

@dataclass(frozen=True)
class AgentResult:
    fetched_count: int
    skipped_count: int
    deferred_count: int
    summarized_count: int
    report_path: Path | None
    instagram_count: int
    published_count: int

def run_once(
    settings: Settings,
    all_matching: bool = False,
    reprocess: bool = False,
    recent_limit: int | None = 100,
) -> AgentResult:
    settings.validate_email_access()
    _ensure_output_dirs(settings)
    store = AgentStore(settings.db_path)
    store.initialize()
    store.mark_stale_runs()
    run_id = store.start_run()

    try:
        with ImapEmailClient(settings) as client:
            should_fetch_all = all_matching or settings.process_all_matching
            emails = client.fetch_all_from_sender() if should_fetch_all else client.fetch_recent(limit=recent_limit)
        result = process_items(
            emails=emails,
            settings=settings,
            store=store,
            source_label=settings.email_sender_filter or settings.imap_username,
            process_all=should_fetch_all or recent_limit is None,
            reprocess=reprocess,
        )
        store.finish_run(
            run_id,
            "ok",
            f"Summarized {result.summarized_count} of {result.fetched_count} fetched emails.",
        )
        return result
    except ConnectionError as exc:
        _safe_print("Internet disconnected or offline. Sleeping until next cycle...")
        store.finish_run(run_id, "offline", str(exc))
        return AgentResult(fetched_count=0, skipped_count=0, deferred_count=0, summarized_count=0, report_path=None, instagram_count=0, published_count=0)
    except Exception as exc:
        store.finish_run(run_id, "error", str(exc))
        raise
    finally:
        store.close()


def run_recent_backfill(settings: Settings) -> AgentResult:
    """Process every matching sender email from the configured lookback window in one run."""
    return run_once(settings, recent_limit=None)


def poll_new_once(settings: Settings) -> AgentResult:
    """Check only for brand-new sender mail once and do nothing if nothing new arrived."""
    settings.validate_email_access()
    _ensure_output_dirs(settings)
    store = AgentStore(settings.db_path)
    store.initialize()
    store.mark_stale_runs()
    run_id = store.start_run()
    mailbox_key = f"{settings.email_folder}|{settings.email_sender_filter or settings.imap_username}"
    scan_state_key = f"last_email_scan_at|{mailbox_key}"

    try:
        if not _email_scan_due(store, scan_state_key, settings.email_check_interval_minutes):
            result = AgentResult(
                fetched_count=0,
                skipped_count=0,
                deferred_count=0,
                summarized_count=0,
                report_path=None,
                instagram_count=0,
                published_count=0,
            )
            last_scan = store.get_state(scan_state_key)
            _safe_print(
                f"Email scan skipped for {mailbox_key}. Last scan: {last_scan or 'never'}; "
                f"interval: {settings.email_check_interval_minutes} minutes."
            )
            store.finish_run(
                run_id,
                "ok",
                f"Email scan skipped for {mailbox_key}. Last scan: {last_scan or 'never'}; interval: {settings.email_check_interval_minutes} minutes.",
            )
            return result

        emails = []
        baseline = store.get_mailbox_watermark(mailbox_key)
        with ImapEmailClient(settings) as client:
            if baseline <= 0:
                baseline = client.fetch_latest_uid()
                if baseline > 0:
                    store.set_mailbox_watermark(mailbox_key, baseline)
                result = AgentResult(
                    fetched_count=0,
                    skipped_count=0,
                    deferred_count=0,
                    summarized_count=0,
                    report_path=None,
                    instagram_count=0,
                    published_count=0,
                )
                store.finish_run(
                    run_id,
                    "ok",
                    f"Seeded mailbox watermark for {mailbox_key} at UID {baseline}. No new sender mail processed.",
                )
                _safe_print(f"Seeded mailbox watermark for {mailbox_key} at UID {baseline}.")
                store.set_state(scan_state_key, _now_iso())
                return result

            emails = client.fetch_matching(all_matching=False, since_uid=baseline)

        if not emails:
            result = AgentResult(
                fetched_count=0,
                skipped_count=0,
                deferred_count=0,
                summarized_count=0,
                report_path=None,
                instagram_count=0,
                published_count=0,
            )
            store.finish_run(
                run_id,
                "ok",
                f"No new mail found for {mailbox_key}. Nothing to publish.",
            )
            _safe_print(f"No new mail found for {mailbox_key}. Nothing to publish.")
            store.set_state(scan_state_key, _now_iso())
            return result

        result = process_items(
            emails=emails,
            settings=settings,
            store=store,
            source_label=settings.email_sender_filter or settings.imap_username,
            process_all=False,
            reprocess=False,
        )
        latest_uid = max(int(email.uid) for email in emails if str(email.uid).isdigit())
        if latest_uid > baseline:
            store.set_mailbox_watermark(mailbox_key, latest_uid)
        store.finish_run(
            run_id,
            "ok",
            f"Processed {result.summarized_count} new email(s) for {mailbox_key}.",
        )
        _safe_print(f"Processed {result.summarized_count} new email(s) for {mailbox_key}.")
        store.set_state(scan_state_key, _now_iso())
        return result
    except ConnectionError as exc:
        _safe_print("Internet disconnected or offline. Sleeping until next cycle...")
        store.finish_run(run_id, "offline", str(exc))
        return AgentResult(fetched_count=0, skipped_count=0, deferred_count=0, summarized_count=0, report_path=None, instagram_count=0, published_count=0)
    except Exception as exc:
        store.finish_run(run_id, "error", str(exc))
        raise
    finally:
        store.close()


def _email_scan_due(store: AgentStore, key: str, interval_minutes: int) -> bool:
    if interval_minutes <= 0:
        return True
    raw = store.get_state(key)
    if not raw:
        return True
    try:
        last_scan = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if last_scan.tzinfo is None:
        last_scan = last_scan.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc).astimezone() - last_scan >= timedelta(minutes=interval_minutes)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def process_items(
    emails: list[EmailItem],
    settings: Settings,
    store: AgentStore | None = None,
    source_label: str = "sample data",
    process_all: bool = False,
    reprocess: bool = False,
    clear_existing_posts: bool = False,
) -> AgentResult:
    owns_store = store is None
    if store is None:
        store = AgentStore(settings.db_path)
        store.initialize()

    memory: MemoryStore | None = None
    if settings.enable_memory:
        try:
            memory = MemoryStore(settings.db_path)
        except Exception as exc:
            _safe_print(f"  [memory] init failed: {exc}")

    try:
        # Always use configured summary provider (no local-only toggle)
        provider = SummaryProvider(
            provider=settings.summary_provider,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
        )
        # Filter out everything we have already processed.
        if reprocess:
            fresh_emails = emails
        else:
            fresh_emails = []
            for email in emails:
                if store.is_processed(email.message_key):
                    _safe_print(f"Skipping already-processed email: {email.subject!r} (key={email.message_key})")
                else:
                    fresh_emails.append(email)

        deferred_count = 0
        chunk_size = 0 if process_all else settings.max_emails_per_run
        if len(fresh_emails) > chunk_size:
            if chunk_size > 0:
                deferred_count = len(fresh_emails) - chunk_size
                _safe_print(
                    f"Chunk limit hit: {len(fresh_emails)} new emails found but MAX_EMAILS_PER_RUN={chunk_size}. "
                    f"Processing oldest {chunk_size}; deferring {deferred_count} to next run."
                )
                for deferred in fresh_emails[chunk_size:]:
                    _safe_print(f"  DEFERRED (will process next run): {deferred.subject!r}")
                fresh_emails = fresh_emails[:chunk_size]

        # Stepwise processing: fully summarise every email before generating slides.
        # Carousel generation happens once as a batch AFTER the loop so we create
        # a single clean batch directory instead of one per email.
        summaries: list[tuple[EmailItem, EmailSummary]] = []
        for email_idx, email in enumerate(fresh_emails, 1):
            _safe_print(
                f"[{email_idx}/{len(fresh_emails)}] Summarising: {email.subject!r}"
            )
            enriched_email = email
            story_limit = _story_limit(settings, email)
            seed_items = parse_news_items(email, max_links=story_limit)
            _safe_print(f"  Found {len(seed_items)} article link(s) in email body (limit={story_limit})")
            if settings.enrich_articles:
                enriched_email, articles = enrich_email_with_articles(
                    email,
                    settings.article_assets_dir,
                    max_links=story_limit,
                )
                _safe_print(f"  Enriched to {len(articles)} article(s) after URL filtering")
            else:
                articles = []
            articles = _merge_article_fallbacks(articles, seed_items)
            _safe_print(f"  Total articles after fallback merge: {len(articles)}")

            # Step 2 — multi-page article reconstruction
            if settings.enrich_articles and articles:
                articles = assemble_articles(list(articles))
                _safe_print(f"  After page assembly: {len(articles)} article(s)")

            # Step 3 — deduplicate + plan posts (in-batch + cross-cycle memory)
            if settings.enable_dedup and articles:
                from .post_planner import plan_posts
                article_dicts = []
                for a in articles:
                    d = {"url": a.url, "title": a.title, "description": a.description,
                         "text": a.text, "excerpt": a.excerpt,
                         "image_url": a.image_url, "image_path": a.image_path}
                    if hasattr(a, "extra_image_urls"):
                        d["extra_image_urls"] = list(a.extra_image_urls)
                    if hasattr(a, "extra_image_paths"):
                        d["extra_image_paths"] = list(a.extra_image_paths)
                    article_dicts.append(d)
                posts, demoted = plan_posts(article_dicts, memory, post_size=settings.post_size)
                _safe_print(f"  Planned {len(posts)} post(s) from {len(article_dicts)} raw articles (demoted {len(demoted)})")
                selected = posts[0] if posts else []
                selected_articles = [
                    ArticleData(
                        url=a.get("url", ""),
                        title=a.get("title", ""),
                        description=a.get("description", ""),
                        text=a.get("text", ""),
                        image_url=a.get("image_url", ""),
                        image_path=a.get("image_path", ""),
                    )
                    for a in selected
                ]
                articles = selected_articles if selected_articles else articles[:settings.post_size]
                _safe_print(f"  Selected {len(articles)} articles for summarization")

            # Summarize with full-extract (no truncation)
            summary = provider.summarize(enriched_email, articles=articles, full_extract=True)
            summaries.append((email, summary))

        report_path = None
        instagram_count = 0
        published_count = 0
        if summaries:
            summary_items = [summary for _email, summary in summaries]

            # Write the combined markdown report for all emails in this run.
            report_path = write_report(
                summary_items,
                settings.reports_dir,
                source_label=source_label,
            )

            # Generate all carousel slides in a single batch directory.
            # This runs AFTER all summaries are ready so we produce one clean
            # batch (not N per-email batches) and the manifest gets accurate
            # public URLs from the start.
            if settings.create_instagram_posts:
                settings.validate_instagram_publish()
                carousel_dirs = write_instagram_carousels(
                    summary_items,
                    settings.instagram_dir,
                    clear_existing=clear_existing_posts,
                    db_path=settings.db_path,
                    memory=memory,
                    enable_verification=settings.enable_verification,
                    max_verify_rounds=settings.max_verification_rounds,
                    ollama_url=settings.ollama_url,
                    ollama_model=settings.ollama_model,
                )
                instagram_count = len(carousel_dirs)
                _safe_print(
                    f"Generated {instagram_count} carousel(s) for "
                    f"{len(summaries)} email(s)."
                )
                manifest_path = write_publish_manifest(
                    carousel_dirs, settings.public_media_base_url,
                )
                if manifest_path:
                    # publish_ready_carousels() is a no-op when
                    # AUTO_PUBLISH_INSTAGRAM=false (generate job).
                    # It is active in publish_latest_instagram.py.
                    published_count = publish_ready_carousels(settings, manifest_path)

            for email, summary in summaries:
                store.mark_processed(email, summary, report_path)

        return AgentResult(
            fetched_count=len(emails),
            skipped_count=len(emails) - len(fresh_emails) - deferred_count,
            deferred_count=deferred_count,
            summarized_count=len(summaries),
            report_path=report_path,
            instagram_count=instagram_count,
            published_count=published_count,
        )
    finally:
        if owns_store:
            store.close()
        if memory is not None:
            try:
                memory.prune()
                memory.close()
            except Exception:
                pass


def _story_limit(settings: Settings, email: EmailItem) -> int:
    return settings.max_article_links_per_email


def _merge_article_fallbacks(articles: list[ArticleData], seed_items) -> list[ArticleData]:
    if not seed_items:
        return articles
    by_url = {article.url: article for article in articles}
    merged = list(articles)
    for item in seed_items:
        if item.url in by_url:
            continue
        merged.append(
            ArticleData(
                url=item.url,
                title=item.title,
                description=item.context,
                text=item.context,
            )
        )
    return merged


def run_sample(settings: Settings) -> AgentResult:
    sample_emails = [
        EmailItem(
            uid="sample-1",
            message_id="<sample-1@local>",
            sender="ai-news-agent@example.com",
            subject="OpenAI releases new reasoning tools for developers",
            date="Wed, 22 Apr 2026 10:00:00 +0530",
            body="OpenAI just released groundbreaking new reasoning tools that enable developers to build smarter AI applications.\n\nKey highlights:\n- The new o1 model includes advanced reasoning capabilities that improve problem-solving on complex tasks\n- Developers can now leverage chain-of-thought reasoning for better accuracy\n- The tools are optimized for research, coding, and mathematical problem-solving\n- OpenAI is democratizing access to powerful reasoning models through their API\n\nThis represents a major step forward in making AI reasoning capabilities available to the broader developer community. The tools can handle nuanced reasoning tasks that previously required human expertise.\n\nFor more details, visit: https://openai.com/research/reasoning",
        ),
    ]
    sample_settings = Settings(**{**settings.__dict__, "db_path": ":memory:"})
    return process_items(sample_emails, sample_settings, source_label="built-in sample emails", process_all=True)


def run_latest(settings: Settings) -> AgentResult:
    """Process the latest matching sender email once for end-to-end testing."""
    settings.validate_email_access()
    _ensure_output_dirs(settings)
    store = AgentStore(settings.db_path)
    store.initialize()
    store.mark_stale_runs()
    run_id = store.start_run()

    try:
        with ImapEmailClient(settings) as client:
            emails = client.fetch_latest_from_sender()
        if not emails:
            result = AgentResult(
                fetched_count=0,
                skipped_count=0,
                deferred_count=0,
                summarized_count=0,
                report_path=None,
                instagram_count=0,
                published_count=0,
            )
        else:
            result = process_items(
                emails=emails,
                settings=settings,
                store=store,
                source_label=settings.email_sender_filter or settings.imap_username,
                process_all=True,
                reprocess=True,
                clear_existing_posts=True,
            )
        store.finish_run(
            run_id,
            "ok",
            f"Tested latest email. Summarized {result.summarized_count} of {result.fetched_count} fetched emails.",
        )
        return result
    except ConnectionError as exc:
        _safe_print("Internet disconnected or offline. Sleeping until next cycle...")
        store.finish_run(run_id, "offline", str(exc))
        return AgentResult(fetched_count=0, skipped_count=0, deferred_count=0, summarized_count=0, report_path=None, instagram_count=0, published_count=0)
    finally:
        store.close()

def _format_result(result: AgentResult) -> str:
    report = str(result.report_path) if result.report_path else "no new report"
    return (
        f"Fetched: {result.fetched_count}, skipped: {result.skipped_count}, "
        f"deferred: {result.deferred_count}, summarized: {result.summarized_count}, "
        f"instagram carousels: {result.instagram_count}, published: {result.published_count}, "
        f"report: {report}"
    )


def _safe_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe, flush=True)


def _ensure_output_dirs(settings: Settings) -> None:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.instagram_dir.mkdir(parents=True, exist_ok=True)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI news email summary agent (CI-only)")
    parser.add_argument("--once", action="store_true", help="Run one email summary pass")
    parser.add_argument("--recent-all", action="store_true", help="Run one pass over all matching sender mail from the lookback window")
    parser.add_argument("--poll-once", action="store_true", help="Check once for brand-new sender mail and exit if none arrived")
    parser.add_argument("--test-latest", action="store_true", help="Process the latest matching sender email once")
    parser.add_argument("--sample", action="store_true", help="Generate a report from sample emails")
    parser.add_argument("--all", action="store_true", help="Fetch every matching email from the configured sender")
    parser.add_argument("--reprocess", action="store_true", help="Summarize matching emails again even if they were already processed")
    # Legacy/no-op flags kept for backwards-compatibility with older CI scripts
    parser.add_argument("--stepwise", action="store_true", help="(no-op, kept for compatibility)")
    parser.add_argument("--zero-budget", action="store_true", help="(no-op, kept for compatibility)")
    # NOTE: CLI runs are restricted to GitHub Actions. This binary will early-exit locally.
    args = parser.parse_args(argv)

    # Prevent running locally from the command line — allow only inside GitHub Actions CI.
    # Tests import functions directly and are unaffected.
    if not (os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"):
        print("This agent is configured to run only on GitHub Actions. To run locally for development, set GITHUB_ACTIONS=true (not recommended).", file=sys.stderr)
        return 1

    settings = Settings.from_env()
    try:
        if args.sample:
            result = run_sample(settings)
        elif args.recent_all:
            result = run_recent_backfill(settings)
        elif args.poll_once:
            result = poll_new_once(settings)
        elif args.test_latest:
            result = run_latest(settings)
        else:
            result = run_once(settings, all_matching=args.all, reprocess=args.reprocess)
        _safe_print(_format_result(result))
        return 0
    except ConnectionError:
        # Handled silently in run_once
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
