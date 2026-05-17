from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .models import EmailSummary


def write_report(
    summaries: list[EmailSummary],
    reports_dir: Path,
    source_label: str = "email inbox",
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone()
    report_path = reports_dir / f"{now.strftime('%Y%m%d-%H%M%S')}_ai_news_report.md"
    content = build_report_markdown(summaries, source_label, now.isoformat(timespec="seconds"))
    report_path.write_text(content, encoding="utf-8")
    latest_path = reports_dir / "latest.md"
    latest_path.write_text(content, encoding="utf-8")
    return report_path


def build_report_markdown(
    summaries: list[EmailSummary],
    source_label: str,
    generated_at: str,
) -> str:
    company_counts = Counter(company for summary in summaries for company in summary.companies)
    topic_counts = Counter(topic for summary in summaries for topic in summary.topics)
    model_counts = Counter(model for summary in summaries for model in summary.models)

    lines: list[str] = [
        "# AI News Summary Report",
        "",
        f"Generated: {generated_at}",
        f"Source: {source_label}",
        f"Emails summarized: {len(summaries)}",
        "",
        "## Executive Brief",
        "",
    ]
    lines.extend(_executive_brief(summaries))

    lines.extend(
        [
            "",
            "## Most Mentioned Companies",
            "",
            _counter_line(company_counts, "No clear company mentions found."),
            "",
            "## Most Mentioned Models",
            "",
            _counter_line(model_counts, "No clear model mentions found."),
            "",
            "## Main Topics",
            "",
            _counter_line(topic_counts, "No clear topic clusters found."),
            "",
            "## Voice Script Hooks",
            "",
        ]
    )
    lines.extend(f"- {hook}" for hook in build_voice_hooks(summaries))

    lines.extend(["", "## Per-Email Summaries", ""])
    for index, summary in enumerate(summaries, start=1):
        lines.extend(
            [
                f"### {index}. {summary.headline}",
                "",
                f"Source date: {summary.source_date or 'Unknown'}",
                f"Confidence: {summary.confidence:.2f}",
            ]
        )
        if summary.article_url:
            lines.append(f"Article: {summary.article_url}")
        if summary.article_title:
            lines.append(f"Article title: {summary.article_title}")
        if summary.article_excerpt:
            lines.extend(["", f"Article excerpt: {summary.article_excerpt}"])
        lines.extend(["", summary.summary, "", "Key points:"])
        lines.extend(f"- {point}" for point in summary.key_points)
        if summary.companies:
            lines.append(f"Companies: {', '.join(summary.companies)}")
        if summary.models:
            lines.append(f"Models: {', '.join(summary.models)}")
        if summary.topics:
            lines.append(f"Topics: {', '.join(summary.topics)}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def build_voice_hooks(summaries: list[EmailSummary]) -> list[str]:
    hooks: list[str] = []
    for summary in summaries[:6]:
        entity = summary.companies[0] if summary.companies else "AI"
        topic = summary.topics[0] if summary.topics else "the AI world"
        hooks.append(f"{entity} just made a move in {topic}: {summary.headline}")
    if not hooks:
        hooks.append("Here are the biggest AI updates you should know today.")
    return hooks


def _executive_brief(summaries: list[EmailSummary]) -> list[str]:
    points: list[str] = []
    for summary in summaries:
        for point in summary.key_points:
            if point not in points:
                points.append(point)
            if len(points) >= 7:
                break
        if len(points) >= 7:
            break
    return [f"- {point}" for point in points] or ["- No new summaries were generated."]


def _counter_line(counter: Counter[str], empty: str) -> str:
    if not counter:
        return empty
    return ", ".join(f"{name} ({count})" for name, count in counter.most_common(8))
