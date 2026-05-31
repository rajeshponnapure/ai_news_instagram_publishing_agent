"""memory_store.py — durable, typed cross-cycle memory (SQLite, stdlib-only).

Shares the same SQLite file as :class:`db.AgentStore` (``settings.db_path``) but
owns its own connection and tables. Stores story fingerprints, keypoints, image
perceptual hashes, topic coverage, published posts, a carryover queue, and the
verification audit trail.

SimHash and perceptual hashes are stored as hex TEXT (64-bit unsigned values
exceed SQLite's signed-integer range).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import text_similarity as ts
from . import perceptual_image as pi

# Retention windows (days). image_memory is kept indefinitely.
RETENTION = {
    "story_memory": 90,
    "keypoint_memory": 45,
    "topic_memory": 30,
    "published_posts": 120,
    "carryover_articles": 3,
}

# Duplicate thresholds (mirror docs/PIPELINE_ARCHITECTURE.md §4.4).
STORY_DUP_COSINE = 0.92
STORY_CLUSTER_COSINE = 0.82
KEYPOINT_DUP_JACCARD = 0.85
SUMMARY_DUP_COSINE = 0.93
TOPIC_RECENT_DAYS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = db_path
        if isinstance(db_path, Path):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS story_memory (
                story_id TEXT PRIMARY KEY,
                canonical_url TEXT,
                content_sha256 TEXT,
                simhash TEXT,
                title TEXT,
                fp_text TEXT,
                entities TEXT,
                topic TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                times_seen INTEGER DEFAULT 1,
                published INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_story_sha ON story_memory(content_sha256);
            CREATE INDEX IF NOT EXISTS idx_story_seen ON story_memory(last_seen_at);

            CREATE TABLE IF NOT EXISTS keypoint_memory (
                kp_id TEXT PRIMARY KEY,
                text TEXT,
                simhash TEXT,
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS image_memory (
                image_id TEXT PRIMARY KEY,
                path TEXT,
                src_url TEXT,
                ahash TEXT,
                dhash TEXT,
                used_in_post TEXT,
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS topic_memory (
                topic_sig TEXT PRIMARY KEY,
                last_covered_at TEXT,
                count INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS published_posts (
                post_id TEXT PRIMARY KEY,
                batch_dir TEXT,
                story_ids TEXT,
                headline TEXT,
                summary_sha TEXT,
                summary_text TEXT,
                published_at TEXT
            );

            CREATE TABLE IF NOT EXISTS carryover_articles (
                story_id TEXT PRIMARY KEY,
                payload_json TEXT,
                queued_at TEXT,
                attempts INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS verification_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                round INTEGER,
                status TEXT,
                confidence REAL,
                report_json TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS rejected_articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                raw_json TEXT,
                reason TEXT,
                source_email_subject TEXT,
                rejected_at TEXT,
                attempts INTEGER DEFAULT 0,
                last_retried_at TEXT,
                resolution TEXT DEFAULT 'pending'
            );
            """
        )
        # Migrate existing DBs: add resolution column if missing
        try:
            self.conn.execute("ALTER TABLE rejected_articles ADD COLUMN resolution TEXT DEFAULT 'pending'")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        self.conn.commit()

    # ── stories ───────────────────────────────────────────────────────────────

    def find_duplicate_story(
        self, *, sha: str, simhash_val: int, fp_text: str, max_age_days: int = 90
    ) -> tuple[str, float] | None:
        """Return (story_id, score) of the best matching prior story, or None.

        Caller compares ``score`` against STORY_DUP_COSINE / STORY_CLUSTER_COSINE.
        """
        row = self.conn.execute(
            "SELECT story_id FROM story_memory WHERE content_sha256 = ? LIMIT 1", (sha,)
        ).fetchone()
        if row:
            return (row["story_id"], 1.0)
        cutoff = _cutoff_iso(max_age_days)
        best: tuple[str, float] | None = None
        for r in self.conn.execute(
            "SELECT story_id, simhash, fp_text FROM story_memory WHERE last_seen_at >= ?",
            (cutoff,),
        ):
            score = ts.cosine(fp_text, r["fp_text"] or "")
            other = pi.from_hex(r["simhash"]) if r["simhash"] else None
            if other is not None and ts.simhash_similar(simhash_val, other, max_hamming=3):
                score = max(score, 0.95)
            if best is None or score > best[1]:
                best = (r["story_id"], score)
        return best

    def record_story(
        self,
        *,
        canonical_url: str,
        sha: str,
        simhash_val: int,
        title: str,
        fp_text: str,
        entities: list[str],
        topic: str,
        story_id: str | None = None,
        published: bool = False,
    ) -> str:
        story_id = story_id or uuid.uuid4().hex
        now = _now()
        existing = self.conn.execute(
            "SELECT story_id FROM story_memory WHERE story_id = ? OR content_sha256 = ? LIMIT 1",
            (story_id, sha),
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE story_memory SET last_seen_at = ?, times_seen = times_seen + 1, "
                "published = MAX(published, ?) WHERE story_id = ?",
                (now, 1 if published else 0, existing["story_id"]),
            )
            self.conn.commit()
            return existing["story_id"]
        self.conn.execute(
            "INSERT INTO story_memory (story_id, canonical_url, content_sha256, simhash, title, "
            "fp_text, entities, topic, first_seen_at, last_seen_at, times_seen, published) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                story_id,
                canonical_url,
                sha,
                pi.hex_hash(simhash_val),
                title,
                fp_text,
                json.dumps(entities, ensure_ascii=True),
                topic,
                now,
                now,
                1 if published else 0,
            ),
        )
        self.conn.commit()
        return story_id

    def mark_story_published(self, story_id: str) -> None:
        self.conn.execute(
            "UPDATE story_memory SET published = 1, last_seen_at = ? WHERE story_id = ?",
            (_now(), story_id),
        )
        self.conn.commit()

    # ── keypoints ───────────────────────────────────────────────────────────────

    def is_keypoint_seen(self, text: str, *, max_age_days: int = 45) -> bool:
        cutoff = _cutoff_iso(max_age_days)
        sh = ts.simhash(text)
        for r in self.conn.execute(
            "SELECT text, simhash FROM keypoint_memory WHERE used_at >= ?", (cutoff,)
        ):
            if ts.jaccard(text, r["text"] or "") >= KEYPOINT_DUP_JACCARD:
                return True
            other = pi.from_hex(r["simhash"]) if r["simhash"] else None
            if other is not None and ts.simhash_similar(sh, other, max_hamming=3):
                return True
        return False

    def record_keypoints(self, points: list[str]) -> None:
        now = _now()
        self.conn.executemany(
            "INSERT INTO keypoint_memory (kp_id, text, simhash, used_at) VALUES (?, ?, ?, ?)",
            [(uuid.uuid4().hex, p, pi.hex_hash(ts.simhash(p)), now) for p in points if p],
        )
        self.conn.commit()

    # ── images ───────────────────────────────────────────────────────────────────

    def load_used_image_hashes(self) -> list[tuple[int | None, int | None]]:
        out = []
        for r in self.conn.execute("SELECT ahash, dhash FROM image_memory"):
            out.append((pi.from_hex(r["ahash"]), pi.from_hex(r["dhash"])))
        return out

    def load_used_image_paths(self) -> set[str]:
        return {r["path"] for r in self.conn.execute("SELECT path FROM image_memory") if r["path"]}

    def is_image_used(self, ahash: int | None, dhash: int | None) -> bool:
        return pi.is_duplicate(ahash, dhash, self.load_used_image_hashes())

    def record_image(
        self, *, path: str, src_url: str, ahash: int | None, dhash: int | None, post: str = ""
    ) -> None:
        if not path:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO image_memory (image_id, path, src_url, ahash, dhash, "
            "used_in_post, used_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ts.content_sha256(path)[:24],
                path,
                src_url,
                pi.hex_hash(ahash),
                pi.hex_hash(dhash),
                post,
                _now(),
            ),
        )
        self.conn.commit()

    # ── topics ───────────────────────────────────────────────────────────────────

    def is_topic_recent(self, topic_sig: str, *, days: int = TOPIC_RECENT_DAYS) -> bool:
        if not topic_sig:
            return False
        row = self.conn.execute(
            "SELECT last_covered_at FROM topic_memory WHERE topic_sig = ? LIMIT 1", (topic_sig,)
        ).fetchone()
        return bool(row and row["last_covered_at"] >= _cutoff_iso(days))

    def record_topic(self, topic_sig: str) -> None:
        if not topic_sig:
            return
        self.conn.execute(
            "INSERT INTO topic_memory (topic_sig, last_covered_at, count) VALUES (?, ?, 1) "
            "ON CONFLICT(topic_sig) DO UPDATE SET last_covered_at = excluded.last_covered_at, "
            "count = count + 1",
            (topic_sig, _now()),
        )
        self.conn.commit()

    # ── published posts (summary-level dedup) ─────────────────────────────────────

    def is_summary_published(self, summary_text: str, *, max_age_days: int = 120) -> bool:
        sha = ts.content_sha256(summary_text)
        if self.conn.execute(
            "SELECT 1 FROM published_posts WHERE summary_sha = ? LIMIT 1", (sha,)
        ).fetchone():
            return True
        cutoff = _cutoff_iso(max_age_days)
        for r in self.conn.execute(
            "SELECT summary_text FROM published_posts WHERE published_at >= ?", (cutoff,)
        ):
            if ts.cosine(summary_text, r["summary_text"] or "") >= SUMMARY_DUP_COSINE:
                return True
        return False

    def record_published_post(
        self, *, post_id: str, batch_dir: str, story_ids: list[str], headline: str, summary_text: str
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO published_posts (post_id, batch_dir, story_ids, headline, "
            "summary_sha, summary_text, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                post_id,
                batch_dir,
                json.dumps(story_ids, ensure_ascii=True),
                headline,
                ts.content_sha256(summary_text),
                summary_text,
                _now(),
            ),
        )
        self.conn.commit()

    # ── carryover queue ───────────────────────────────────────────────────────────

    def push_carryover(self, story_id: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO carryover_articles (story_id, payload_json, queued_at, attempts) "
            "VALUES (?, ?, ?, 0) ON CONFLICT(story_id) DO UPDATE SET attempts = attempts + 1",
            (story_id, json.dumps(payload, ensure_ascii=True), _now()),
        )
        self.conn.commit()

    def pop_carryover(self, limit: int) -> list[dict]:
        if limit <= 0:
            return []
        rows = self.conn.execute(
            "SELECT story_id, payload_json FROM carryover_articles ORDER BY queued_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            try:
                payload = json.loads(r["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            payload["_carryover_story_id"] = r["story_id"]
            out.append(payload)
            self.conn.execute("DELETE FROM carryover_articles WHERE story_id = ?", (r["story_id"],))
        self.conn.commit()
        return out

    def carryover_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM carryover_articles").fetchone()
        return int(row["n"]) if row else 0

    # ── rejected articles (catch-all for quality-filter drops) ──────────────────

    def save_rejected_article(
        self, *, url: str, title: str, article: dict, reason: str, source_email_subject: str = ""
    ) -> None:
        """Persist an article that failed quality checks for later re-evaluation."""
        if not url.startswith(("http://", "https://")):
            return  # URL is required for retry
        # Use ON CONFLICT so attempts are preserved/incremented on re-rejection
        # (INSERT OR REPLACE would reset attempts to 0).
        self.conn.execute(
            "INSERT INTO rejected_articles (url, title, raw_json, reason, "
            "source_email_subject, rejected_at, attempts) VALUES (?, ?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(url) DO UPDATE SET "
            "  raw_json = excluded.raw_json, reason = excluded.reason, "
            "  source_email_subject = excluded.source_email_subject, "
            "  rejected_at = excluded.rejected_at, "
            "  attempts = attempts + 1",
            (url, title, json.dumps(article, ensure_ascii=True), reason,
             source_email_subject, _now()),
        )
        self.conn.commit()

    def get_rejected_count(self) -> int:
        """Return how many rejected articles are waiting for retry."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM rejected_articles").fetchone()
        return int(row["n"]) if row else 0

    def resolve_rejected_article(self, url: str, resolution: str = 'recovered') -> None:
        """Mark a rejected article as resolved (recovered or exhausted).

        Resolved articles are excluded from future ``pop_rejected_for_retry`` calls.
        """
        self.conn.execute(
            "UPDATE rejected_articles SET resolution = ?, last_retried_at = ? WHERE url = ?",
            (resolution, _now(), url),
        )
        self.conn.commit()

    def pop_rejected_for_retry(self, *, min_retry_interval_hours: int = 24, max_attempts: int = 3, limit: int = 20) -> list[dict]:
        """Pop articles that are eligible for retry (cooldown elapsed, not exhausted).

        Returns article dicts with '_rejected_url', '_rejected_reason', and
        '_rejected_attempts' keys added so the recovery pipeline can report
        on retry outcomes.
        """
        # Compute a cutoff in the past: "don't retry if retried less than N hours ago"
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=min_retry_interval_hours)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT url, title, raw_json, reason, attempts "
            "FROM rejected_articles "
            "WHERE attempts < ? "
            "AND (resolution IS NULL OR resolution = 'pending') "
            "AND (last_retried_at IS NULL OR last_retried_at < ?) "
            "ORDER BY rejected_at ASC LIMIT ?",
            (max_attempts, cutoff, limit),
        ).fetchall()
        result = []
        for r in rows:
            try:
                article = json.loads(r["raw_json"])
            except (TypeError, json.JSONDecodeError):
                article = {"url": r["url"], "title": r["title"]}
            article["_rejected_url"] = r["url"]
            article["_rejected_reason"] = r["reason"]
            article["_rejected_attempts"] = r["attempts"]
            result.append(article)
            self.conn.execute(
                "UPDATE rejected_articles SET attempts = attempts + 1, last_retried_at = ? WHERE url = ?",
                (_now(), r["url"]),
            )
        self.conn.commit()
        return result

    def clear_rejected(self) -> int:
        """Remove all rejected articles (after successful recovery)."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM rejected_articles").fetchone()
        count = int(row["n"]) if row else 0
        self.conn.execute("DELETE FROM rejected_articles")
        self.conn.commit()
        return count

    def count_rejected_by_reason(self) -> dict[str, int]:
        """Return breakdown of why articles were rejected (pending only)."""
        by_reason: dict[str, int] = {}
        for r in self.conn.execute(
            "SELECT reason, COUNT(*) AS n FROM rejected_articles "
            "WHERE resolution IS NULL OR resolution = 'pending' "
            "GROUP BY reason ORDER BY n DESC"
        ):
            by_reason[str(r["reason"])] = int(r["n"])
        return by_reason

    def get_retry_summary(self, max_attempts: int = 3) -> dict[str, dict[str, int]]:
        """Return counts by reason category broken down by resolution status.

        Infers ``exhausted`` from ``attempts >= max_attempts`` when no
        explicit resolution was set (e.g. for articles created before the
        ``resolution`` column was added).

        Returns nested dict::

            {
                'quality_filter': {'pending': 3, 'recovered': 2, 'exhausted': 1},
                'promo_pattern':  {'pending': 1, 'recovered': 0, 'exhausted': 2},
            }
        """
        by_reason: dict[str, dict[str, int]] = {}
        for r in self.conn.execute(
            "SELECT reason, "
            "  CASE "
            "    WHEN COALESCE(resolution, 'pending') = 'recovered' THEN 'recovered' "
            "    WHEN COALESCE(resolution, 'pending') = 'exhausted' THEN 'exhausted' "
            "    WHEN attempts >= ? THEN 'exhausted' "
            "    ELSE 'pending' "
            "  END AS res, "
            "  COUNT(*) AS n "
            "FROM rejected_articles GROUP BY reason, res ORDER BY reason, res",
            (max_attempts,),
        ):
            reason = str(r["reason"])
            res = str(r["res"])
            if reason not in by_reason:
                by_reason[reason] = {'pending': 0, 'recovered': 0, 'exhausted': 0}
            by_reason[reason][res] = int(r["n"])
        return by_reason

    # ── verification audit ───────────────────────────────────────────────────────

    def record_verification(
        self, *, post_id: str, round_no: int, status: str, confidence: float, report: dict
    ) -> None:
        self.conn.execute(
            "INSERT INTO verification_audit (post_id, round, status, confidence, report_json, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, round_no, status, confidence, json.dumps(report, ensure_ascii=True), _now()),
        )
        self.conn.commit()

    # ── retention ───────────────────────────────────────────────────────────────

    def prune(self) -> None:
        self.conn.execute(
            "DELETE FROM story_memory WHERE published = 0 AND last_seen_at < ?",
            (_cutoff_iso(RETENTION["story_memory"]),),
        )
        self.conn.execute(
            "DELETE FROM keypoint_memory WHERE used_at < ?",
            (_cutoff_iso(RETENTION["keypoint_memory"]),),
        )
        self.conn.execute(
            "DELETE FROM topic_memory WHERE last_covered_at < ?",
            (_cutoff_iso(RETENTION["topic_memory"]),),
        )
        self.conn.execute(
            "DELETE FROM carryover_articles WHERE queued_at < ? OR attempts >= 3",
            (_cutoff_iso(RETENTION["carryover_articles"]),),
        )
        self.conn.commit()
