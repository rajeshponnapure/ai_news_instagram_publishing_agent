from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import EmailItem, EmailSummary


class AgentStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = db_path
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_emails (
                message_key TEXT PRIMARY KEY,
                uid TEXT,
                message_id TEXT,
                sender TEXT,
                subject TEXT,
                received_at TEXT,
                processed_at TEXT NOT NULL,
                report_path TEXT,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS mailbox_watermarks (
                mailbox_key TEXT PRIMARY KEY,
                last_uid INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def start_run(self) -> int:
        now = _now()
        cursor = self.connection.execute(
            "INSERT INTO runs (started_at, status, message) VALUES (?, ?, ?)",
            (now, "running", ""),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def mark_stale_runs(self) -> None:
        self.connection.execute(
            """
            UPDATE runs
            SET finished_at = ?, status = ?, message = ?
            WHERE status = ? AND finished_at IS NULL
            """,
            (_now(), "abandoned", "Run was still marked running when a later run started.", "running"),
        )
        self.connection.commit()

    def finish_run(self, run_id: int, status: str, message: str) -> None:
        self.connection.execute(
            "UPDATE runs SET finished_at = ?, status = ?, message = ? WHERE id = ?",
            (_now(), status, message, run_id),
        )
        self.connection.commit()

    def is_processed(self, message_key: str) -> bool:
        cursor = self.connection.execute(
            "SELECT 1 FROM processed_emails WHERE message_key = ? LIMIT 1",
            (message_key,),
        )
        return cursor.fetchone() is not None

    def get_mailbox_watermark(self, mailbox_key: str) -> int:
        cursor = self.connection.execute(
            "SELECT last_uid FROM mailbox_watermarks WHERE mailbox_key = ? LIMIT 1",
            (mailbox_key,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def set_mailbox_watermark(self, mailbox_key: str, last_uid: int) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO mailbox_watermarks (mailbox_key, last_uid, updated_at)
            VALUES (?, ?, ?)
            """,
            (mailbox_key, int(last_uid), _now()),
        )
        self.connection.commit()

    def get_state(self, key: str) -> str:
        cursor = self.connection.execute(
            "SELECT value FROM agent_state WHERE key = ? LIMIT 1",
            (key,),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else ""

    def set_state(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO agent_state (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, value, _now()),
        )
        self.connection.commit()

    def mark_processed(
        self,
        email: EmailItem,
        summary: EmailSummary,
        report_path: Path | None,
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO processed_emails (
                message_key,
                uid,
                message_id,
                sender,
                subject,
                received_at,
                processed_at,
                report_path,
                summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email.message_key,
                email.uid,
                email.message_id,
                email.sender,
                email.subject,
                email.date,
                _now(),
                str(report_path) if report_path else "",
                json.dumps(summary.to_dict(), ensure_ascii=True),
            ),
        )
        self.connection.commit()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
