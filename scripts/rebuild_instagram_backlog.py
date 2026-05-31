from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.article_quality import contains_public_noise, is_publishable_article  # noqa: E402
from email_summary_agent.config import Settings  # noqa: E402
from email_summary_agent.ig_copy import clean_creator_text  # noqa: E402
from email_summary_agent.instagram import write_instagram_carousels  # noqa: E402
from email_summary_agent.models import EmailSummary  # noqa: E402
from email_summary_agent.publisher import publish_ready_carousels, write_publish_manifest  # noqa: E402


DEFAULT_TZ = "Asia/Kolkata"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild safe Instagram carousel assets from processed email summaries."
    )
    parser.add_argument(
        "--since",
        help="Inclusive start time, ISO-8601 or email date. Default: yesterday 23:00 Asia/Kolkata.",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        help="Use the last N hours instead of --since/default.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TZ,
        help="Timezone used by the default yesterday-23:00 window.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish the rebuilt batch after manifest creation. Requires deployed public URLs.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Render without pre-publish verification. Do not use for production recovery.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    since = _resolve_since(args.since, args.since_hours, args.timezone)
    print(f"Rebuilding Instagram backlog from {since.isoformat(timespec='seconds')}")

    rows = _load_processed_summaries(settings.db_path, since)
    summaries = [_summary_from_row(row) for row in rows]
    summaries = [summary for summary in summaries if summary is not None]
    summaries = [_sanitize_summary(summary) for summary in summaries]
    summaries = [summary for summary in summaries if summary and summary.article_items]

    if not summaries:
        print("No publishable processed summaries found in the requested window.")
        return 0

    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    carousels = write_instagram_carousels(
        summaries,
        settings.instagram_dir,
        clear_existing=False,
        db_path=None,
        flush_partial=True,
        memory=None,
        enable_verification=not args.no_verify,
        max_verify_rounds=settings.max_verification_rounds,
    )

    if not carousels:
        print("No carousel folders were created after filtering unsafe articles.")
        return 1

    manifest_path = write_publish_manifest(carousels, settings.public_media_base_url)
    print(f"Created {len(carousels)} rebuilt carousel folder(s).")
    print(f"Manifest: {manifest_path}")

    if args.publish:
        settings.validate_instagram_publish()
        if not manifest_path:
            print("No manifest was created; publish skipped.")
            return 1
        published = publish_ready_carousels(settings, manifest_path)
        print(f"Published {published} rebuilt carousel(s).")

    return 0


def _resolve_since(raw: str | None, since_hours: int | None, tz_name: str) -> datetime:
    if since_hours:
        return datetime.now(timezone.utc) - timedelta(hours=since_hours)
    if raw:
        return _parse_datetime(raw)

    tz = _timezone(tz_name)
    now_local = datetime.now(tz)
    yesterday_23 = (now_local.date() - timedelta(days=1)).isoformat() + "T23:00:00"
    return datetime.fromisoformat(yesterday_23).replace(tzinfo=tz).astimezone(timezone.utc)


def _timezone(name: str):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    if name.lower() in {"asia/kolkata", "asia/calcutta"}:
        return timezone(timedelta(hours=5, minutes=30))
    return timezone.utc


def _parse_datetime(value: str) -> datetime:
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = parsedate_to_datetime(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_processed_summaries(db_path: Path, since: datetime) -> list[sqlite3.Row]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT processed_at, received_at, source_date, summary_json "
            "FROM processed_emails ORDER BY processed_at ASC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT processed_at, received_at, summary_json "
            "FROM processed_emails ORDER BY processed_at ASC"
        ).fetchall()
    finally:
        conn.close()

    kept: list[sqlite3.Row] = []
    for row in rows:
        processed_at = _parse_datetime(str(row["processed_at"]))
        if processed_at >= since:
            kept.append(row)
    return kept


def _summary_from_row(row: sqlite3.Row) -> EmailSummary | None:
    try:
        payload = json.loads(row["summary_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    allowed = {field.name for field in fields(EmailSummary)}
    data = {key: payload.get(key) for key in allowed if key in payload}
    for key in ("key_points", "companies", "models", "topics"):
        if not isinstance(data.get(key), list):
            data[key] = []
    if not data.get("message_key"):
        data["message_key"] = f"rebuilt:{row['processed_at']}"
    for key in ("subject", "source_date", "headline", "summary"):
        data[key] = str(data.get(key) or "")
    data["confidence"] = float(data.get("confidence") or 0.7)
    return EmailSummary(**data)


def _sanitize_summary(summary: EmailSummary) -> EmailSummary | None:
    articles = []
    for article in summary.article_items or []:
        cleaned = _sanitize_article(article)
        if cleaned and is_publishable_article(cleaned):
            articles.append(cleaned)

    if not articles:
        fallback = _sanitize_article(
            {
                "url": summary.article_url,
                "title": summary.article_title or summary.headline,
                "description": summary.article_excerpt or summary.summary,
                "summary": summary.summary,
                "key_points": summary.key_points,
                "image_url": summary.article_image_url,
                "image_path": summary.article_image_path,
            }
        )
        if fallback and is_publishable_article(fallback):
            articles.append(fallback)

    if not articles:
        return None

    return EmailSummary(
        message_key=summary.message_key,
        subject=clean_creator_text(summary.subject),
        source_date=summary.source_date,
        headline=clean_creator_text(summary.headline),
        summary=_clean_field(summary.summary),
        key_points=[p for p in (_clean_field(point) for point in summary.key_points) if p],
        companies=summary.companies,
        models=summary.models,
        topics=summary.topics,
        confidence=summary.confidence,
        article_url=str(articles[0].get("url") or ""),
        article_title=str(articles[0].get("title") or ""),
        article_image_path=str(articles[0].get("image_path") or ""),
        article_image_url=str(articles[0].get("image_url") or ""),
        article_excerpt=str(articles[0].get("excerpt") or articles[0].get("description") or ""),
        article_items=articles,
    )


def _sanitize_article(article: dict[str, Any]) -> dict[str, Any] | None:
    raw_combined = " ".join(str(article.get(key) or "") for key in ("title", "description", "excerpt", "summary", "text", "scraped_content"))
    if contains_public_noise(raw_combined):
        return None

    cleaned = dict(article)
    for key in ("title", "description", "excerpt", "summary", "text", "scraped_content", "what_happened", "why_matters", "what_to_watch"):
        cleaned[key] = _clean_field(cleaned.get(key, ""))

    points = cleaned.get("key_points") or []
    if isinstance(points, list):
        cleaned["key_points"] = [p for p in (_clean_field(point) for point in points) if p]
    else:
        cleaned["key_points"] = []

    image_path = str(cleaned.get("image_path") or "")
    if image_path and not Path(image_path).exists():
        cleaned["image_path"] = ""
    cleaned["extra_image_paths"] = [
        path for path in cleaned.get("extra_image_paths") or [] if Path(str(path)).exists()
    ]

    url = str(cleaned.get("url") or "")
    title = str(cleaned.get("title") or "")
    body = " ".join(str(cleaned.get(key) or "") for key in ("description", "summary", "text", "scraped_content"))
    if not url.startswith(("http://", "https://")):
        return None
    if not title or len(body) < 60:
        return None
    if contains_public_noise(f"{title} {body}"):
        return None
    return cleaned


def _clean_field(value: Any) -> str:
    text = clean_creator_text(str(value or ""))
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept: list[str] = []
    for part in parts:
        sentence = clean_creator_text(part).strip()
        if not sentence or contains_public_noise(sentence):
            continue
        if re.search(r"\b(?:Link|Company|Summary)\s*:", sentence, re.I):
            continue
        if len(sentence) < 8:
            continue
        kept.append(sentence)
    if kept:
        return " ".join(kept)
    return "" if contains_public_noise(text) else text


if __name__ == "__main__":
    raise SystemExit(main())
