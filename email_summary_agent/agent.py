from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .article_enricher import ArticleData, enrich_email_with_articles
from .db import AgentStore
from .digest import parse_news_items
from .email_client import ImapEmailClient
from .instagram import write_instagram_carousels
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


def watch_new(settings: Settings) -> None:
    """Continuously watch for new sender mail and process only arrivals after startup."""
    settings.validate_email_access()
    store = AgentStore(settings.db_path)
    store.initialize()
    store.mark_stale_runs()
    mailbox_key = f"{settings.email_folder}|{settings.email_sender_filter or settings.imap_username}"

    try:
        with ImapEmailClient(settings) as client:
            baseline = client.fetch_latest_uid()
        current = store.get_mailbox_watermark(mailbox_key)
        if baseline > current:
            store.set_mailbox_watermark(mailbox_key, baseline)
        _safe_print(
            f"Watching for new mail from {settings.email_sender_filter or settings.imap_username!r}. "
            f"Starting after UID {store.get_mailbox_watermark(mailbox_key)}."
        )
        while True:
            try:
                _process_new_mail_cycle(settings, store, mailbox_key)
            except ConnectionError:
                _safe_print("Mailbox temporarily unreachable. Retrying on the next cycle...")
            time.sleep(max(60, settings.poll_interval_minutes * 60))
    finally:
        store.close()


def poll_new_once(settings: Settings) -> AgentResult:
    """Check only for brand-new sender mail once and do nothing if nothing new arrived."""
    settings.validate_email_access()
    store = AgentStore(settings.db_path)
    store.initialize()
    store.mark_stale_runs()
    run_id = store.start_run()
    mailbox_key = f"{settings.email_folder}|{settings.email_sender_filter or settings.imap_username}"

    try:
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

    try:
        provider = SummaryProvider(
            provider=settings.summary_provider,
            ollama_url=settings.ollama_url,
            ollama_model=settings.ollama_model,
        )
        
        # Filter out everything we have already processed.
        fresh_emails = emails if reprocess else [email for email in emails if not store.is_processed(email.message_key)]

        deferred_count = 0
        chunk_size = 0 if process_all else settings.max_emails_per_run
        if len(fresh_emails) > chunk_size:
            if chunk_size > 0:
                deferred_count = len(fresh_emails) - chunk_size
                _safe_print(f"Found {len(fresh_emails)} new emails. Processing the oldest {chunk_size} this round; {deferred_count} left for later.")
                fresh_emails = fresh_emails[:chunk_size]

        summaries: list[tuple[EmailItem, EmailSummary]] = []
        for email in fresh_emails:
            _safe_print(f"Summarizing: {email.subject}")
            articles = []
            enriched_email = email
            story_limit = _story_limit(settings, email)
            seed_items = parse_news_items(email, max_links=story_limit)
            if settings.enrich_articles:
                enriched_email, articles = enrich_email_with_articles(
                    email,
                    settings.article_assets_dir,
                    max_links=story_limit,
                )
            articles = _merge_article_fallbacks(articles, seed_items)
            summaries.append((email, provider.summarize(enriched_email, articles=articles)))

        report_path = None
        instagram_count = 0
        published_count = 0
        if summaries:
            summary_items = [summary for _email, summary in summaries]
            report_path = write_report(
                summary_items,
                settings.reports_dir,
                source_label=source_label,
            )
            if settings.create_instagram_posts:
                settings.validate_instagram_publish()
                carousel_dirs = write_instagram_carousels(
                    summary_items,
                    settings.instagram_dir,
                    clear_existing=clear_existing_posts,
                )
                instagram_count = len(carousel_dirs)
                manifest_path = write_publish_manifest(carousel_dirs, settings.public_media_base_url)
                if manifest_path:
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


def _story_limit(settings: Settings, email: EmailItem) -> int:
    subject = email.subject.lower()
    if "digest" in subject or "updates" in subject:
        return max(settings.max_article_links_per_email, 20)
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


def _process_new_mail_cycle(settings: Settings, store: AgentStore, mailbox_key: str) -> None:
    baseline = store.get_mailbox_watermark(mailbox_key)
    with ImapEmailClient(settings) as client:
        emails = client.fetch_matching(all_matching=False, since_uid=baseline)
    if not emails:
        return
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
    _safe_print(_format_result(result))

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

def watch(settings: Settings) -> None:
    _safe_print(f"Email summary agent started. Polling every {settings.poll_interval_minutes} minutes.")
    while True:
        try:
            result = run_once(settings)
            _safe_print(_format_result(result))
        except Exception as exc:
            print(f"Run failed: {exc}", file=sys.stderr, flush=True)
        time.sleep(settings.poll_interval_minutes * 60)

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

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local AI news email summary agent")
    parser.add_argument("--once", action="store_true", help="Run one email summary pass")
    parser.add_argument("--recent-all", action="store_true", help="Run one pass over all matching sender mail from the lookback window")
    parser.add_argument("--watch", action="store_true", help="Run forever on the configured interval")
    parser.add_argument("--watch-new", action="store_true", help="Run forever and only process new mail after startup")
    parser.add_argument("--poll-once", action="store_true", help="Check once for brand-new sender mail and exit if none arrived")
    parser.add_argument("--test-latest", action="store_true", help="Process the latest matching sender email once")
    parser.add_argument("--sample", action="store_true", help="Generate a report from sample emails")
    parser.add_argument("--all", action="store_true", help="Fetch every matching email from the configured sender")
    parser.add_argument("--reprocess", action="store_true", help="Summarize matching emails again even if they were already processed")
    args = parser.parse_args(argv)

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
        elif args.watch:
            watch(settings)
            return 0
        elif args.watch_new:
            watch_new(settings)
            return 0
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
