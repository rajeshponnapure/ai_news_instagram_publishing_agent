from __future__ import annotations

import imaplib
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser
from typing import Iterable

from .config import Settings
from .models import EmailItem

class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.parts.append(cleaned)

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): value for key, value in attrs if key and value}
        if tag == "a":
            href = attrs_map.get("href", "").strip()
            if href and href.startswith(("http://", "https://")):
                self.parts.append(f"\n{href}\n")
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def get_text(self) -> str:
        return " ".join(self.parts)

def _clean_text(text: str) -> str:
    text = _repair_mojibake(text)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _repair_mojibake(text: str) -> str:
    if not text or not re.search(r"[\u00c3\u00c2\u00e2\u00f0]", text):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if len(repaired.strip()) >= max(1, len(text.strip()) // 2) else text

def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return _clean_text(parser.get_text())

def _decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return str(raw or "")
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")

def extract_body(message: EmailMessage) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if message.is_multipart():
        walk: Iterable[Message] = message.walk()
    else:
        walk = [message]

    for part in walk:
        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", "")).lower()
        if "attachment" in disposition:
            continue
        if content_type == "text/plain":
            plain_parts.append(_clean_text(_decode_payload(part)))
        elif content_type == "text/html":
            html_parts.append(_html_to_text(_decode_payload(part)))

    body_parts: list[str] = []
    body_parts.extend(part for part in plain_parts if part)
    for part in html_parts:
        if part and part not in body_parts:
            body_parts.append(part)
    return "\n\n".join(body_parts)

class ImapEmailClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._imap: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "ImapEmailClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        try:
            # 15-second timeout ensures it gracefully fails if there is no internet
            self._imap = imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port, timeout=15)
            self._imap.login(self.settings.imap_username, self.settings.imap_password)
            status, _ = self._imap.select(self.settings.email_folder, readonly=True)
            if status != "OK":
                raise RuntimeError(f"Could not open email folder {self.settings.email_folder!r}")
        except (socket.error, socket.timeout, imaplib.IMAP4.error) as e:
            raise ConnectionError(f"Network offline or disconnected. ({e})")

    def close(self) -> None:
        if self._imap is None:
            return
        try:
            self._imap.close()
        except Exception:
            pass

        try:
            self._imap.logout()
        except Exception:
            pass
        finally:
            self._imap = None

    def fetch_recent(self) -> list[EmailItem]:
        return self.fetch_matching(all_matching=False)

    def fetch_all_from_sender(self) -> list[EmailItem]:
        return self.fetch_matching(all_matching=True)

    def fetch_latest_from_sender(self) -> list[EmailItem]:
        items = self.fetch_matching(all_matching=True)
        return items[-1:] if items else []

    def fetch_latest_uid(self) -> int:
        if self._imap is None:
            raise RuntimeError("IMAP client is not connected")
        criteria: list[str] = []
        if self.settings.email_sender_filter:
            criteria.extend(["FROM", f'"{self.settings.email_sender_filter}"'])
        if not criteria:
            criteria = ["ALL"]
        status, data = self._imap.uid("SEARCH", None, *criteria)
        if status != "OK":
            return 0
        uids = data[0].split() if data and data[0] else []
        if not uids:
            return 0
        return max(int(uid.decode("ascii", errors="ignore") or 0) for uid in uids)

    def fetch_matching(self, all_matching: bool = False, since_uid: int | None = None) -> list[EmailItem]:
        if self._imap is None:
            raise RuntimeError("IMAP client is not connected")

        criteria: list[str] = []
        if self.settings.email_sender_filter:
            criteria.extend(["FROM", f'"{self.settings.email_sender_filter}"'])
        if since_uid:
            criteria.extend(["UID", f"{since_uid + 1}:*"])
        elif not all_matching:
            since = datetime.now(timezone.utc) - timedelta(hours=self.settings.lookback_hours)
            criteria.extend(["SINCE", since.strftime("%d-%b-%Y")])
        if not criteria:
            criteria = ["ALL"]

        try:
            status, data = self._imap.uid("SEARCH", None, *criteria)
        except (socket.error, socket.timeout, ssl.SSLError, imaplib.IMAP4.error, TimeoutError, OSError) as exc:
            raise ConnectionError(f"Network offline or disconnected during IMAP search. ({exc})") from exc
        if status != "OK":
            raise RuntimeError(f"IMAP search failed with criteria: {' '.join(criteria)}")

        uids = data[0].split() if data and data[0] else []
        selected = uids if all_matching else uids[-100:]
        emails: list[EmailItem] = []

        # Process in normal order (oldest to newest) so we clear the backlog chronologically
        for raw_uid in selected:
            uid = raw_uid.decode("ascii", errors="ignore")
            try:
                status, fetched = self._imap.uid("FETCH", raw_uid, "(RFC822)")
            except (socket.error, socket.timeout, ssl.SSLError, imaplib.IMAP4.error, TimeoutError, OSError) as exc:
                raise ConnectionError(f"Network offline or disconnected during IMAP fetch. ({exc})") from exc
            if status != "OK" or not fetched:
                continue
            raw_message = self._extract_raw_message(fetched)
            if not raw_message:
                continue
            message = BytesParser(policy=policy.default).parsebytes(raw_message)
            subject = _repair_mojibake(str(message.get("Subject", "")).strip())
            sender = _repair_mojibake(str(message.get("From", "")).strip())
            emails.append(
                EmailItem(
                    uid=uid,
                    message_id=str(message.get("Message-ID", "")).strip(),
                    sender=sender,
                    subject=subject or "(no subject)",
                    date=str(message.get("Date", "")).strip(),
                    body=extract_body(message),
                )
            )

        return emails

    @staticmethod
    def _extract_raw_message(fetched: list[bytes | tuple]) -> bytes:
        for item in fetched:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                return item[1]
        return b""
