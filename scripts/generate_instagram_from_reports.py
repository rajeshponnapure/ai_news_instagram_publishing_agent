from __future__ import annotations

import sys
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings  # noqa: E402
from email_summary_agent.instagram import write_instagram_carousels  # noqa: E402
from email_summary_agent.models import EmailSummary  # noqa: E402


def parse_report(path: Path) -> list[EmailSummary]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    summaries: list[EmailSummary] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"###\s*\d+\.\s*(.+)", line)
        if m:
            headline = m.group(1).strip()
            i += 1
            source_date = ""
            confidence = 0.0
            article_url = ""
            article_title = ""
            article_excerpt = ""
            summary_text = ""
            key_points: list[str] = []
            companies: list[str] = []
            models: list[str] = []
            topics: list[str] = []
            # read block until next ###
            block_lines: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("### "):
                block_lines.append(lines[i])
                i += 1
            block = "\n".join(block_lines)
            # extract fields
            sd = re.search(r"Source date:\s*(.+)", block)
            if sd:
                source_date = sd.group(1).strip()
            conf = re.search(r"Confidence:\s*([0-9.]+)", block)
            if conf:
                try:
                    confidence = float(conf.group(1))
                except Exception:
                    confidence = 0.0
            aurl = re.search(r"Article:\s*(https?://\S+)", block)
            if aurl:
                article_url = aurl.group(1).strip()
            atitle = re.search(r"Article title:\s*(.+)", block)
            if atitle:
                article_title = atitle.group(1).strip()
            aex = re.search(r"^Article excerpt:\s*(.+)$", block, re.MULTILINE)
            if aex:
                article_excerpt = aex.group(1).strip()
            # summary is the first paragraph after metadata
            parts = re.split(r"\n{2,}", block)
            # find the paragraph that doesn't start with meta labels
            for p in parts:
                s = p.strip()
                if not s:
                    continue
                if s.startswith("Source date:") or s.startswith("Confidence:") or s.startswith("Article:") or s.startswith("Article title:") or s.startswith("Article excerpt:") or s.startswith("Key points:") or s.startswith("Companies:") or s.startswith("Models:") or s.startswith("Topics:"):
                    continue
                if s.startswith("-"):
                    continue
                # first non-meta paragraph is the summary
                summary_text = s
                break
            # key points
            for kp in re.findall(r"^-\s*(.+)$", block, re.MULTILINE):
                key_points.append(kp.strip())
            comp = re.search(r"Companies:\s*(.+)", block)
            if comp:
                companies = [c.strip() for c in comp.group(1).split(",") if c.strip()]
            mods = re.search(r"Models:\s*(.+)", block)
            if mods:
                models = [m.strip() for m in mods.group(1).split(",") if m.strip()]
            tps = re.search(r"Topics:\s*(.+)", block)
            if tps:
                topics = [t.strip() for t in tps.group(1).split(",") if t.strip()]

            summary = EmailSummary(
                message_key=headline,
                subject="",
                source_date=source_date,
                headline=headline,
                summary=summary_text,
                key_points=key_points,
                companies=companies,
                models=models,
                topics=topics,
                confidence=confidence,
                article_url=article_url,
                article_title=article_title,
                article_excerpt=article_excerpt,
            )
            summaries.append(summary)
        else:
            i += 1
    return summaries


def main() -> int:
    settings = Settings.from_env()
    reports_dir = settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    all_summaries: list[EmailSummary] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(reports_dir.glob("*_ai_news_report.md")):
        all_summaries.extend(parse_report(path))
    unique_summaries: list[EmailSummary] = []
    for summary in all_summaries:
        key = (summary.headline.strip().lower(), summary.source_date.strip())
        if key in seen:
            continue
        seen.add(key)
        unique_summaries.append(summary)

    if not unique_summaries:
        print("No summaries found in reports directory.")
        return 0

    # generate carousels for every parsed summary
    carousel_dirs = write_instagram_carousels(unique_summaries, settings.instagram_dir, clear_existing=True)
    print(f"Generated {len(carousel_dirs)} carousel folders at {settings.instagram_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
