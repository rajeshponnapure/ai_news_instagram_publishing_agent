from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path | None = None) -> None:
    """Load a simple .env file without requiring python-dotenv."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _path_env(name: str, default: str) -> Path:
    raw = os.environ.get(name, default)
    path = Path(raw)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    email_sender_filter: str
    email_folder: str
    lookback_hours: int
    max_emails_per_run: int
    poll_interval_minutes: int
    email_check_interval_minutes: int
    summary_provider: str
    ollama_url: str
    ollama_model: str
    db_path: Path
    reports_dir: Path
    instagram_dir: Path
    create_instagram_posts: bool
    process_all_matching: bool
    enrich_articles: bool
    max_article_links_per_email: int
    article_assets_dir: Path
    public_media_base_url: str
    auto_publish_instagram: bool
    ig_user_id: str
    ig_access_token: str
    ig_api_version: str
    auto_publish_facebook: bool
    fb_page_id: str
    fb_page_access_token: str
    fb_app_id: str
    fb_app_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        return cls(
            imap_host=os.environ.get("IMAP_HOST", "imap.gmail.com"),
            imap_port=_int_env("IMAP_PORT", 993),
            imap_username=os.environ.get("IMAP_USERNAME", ""),
            imap_password=os.environ.get("IMAP_PASSWORD", ""),
            email_sender_filter=os.environ.get(
                "EMAIL_SENDER_FILTER",
                "grdevelopers.co@gmail.com",
            ),
            email_folder=os.environ.get("EMAIL_FOLDER", "INBOX"),
            lookback_hours=_int_env("LOOKBACK_HOURS", 24),
            max_emails_per_run=_int_env("MAX_EMAILS_PER_RUN", 20),
            poll_interval_minutes=_int_env("POLL_INTERVAL_MINUTES", 1),
            email_check_interval_minutes=_int_env("EMAIL_CHECK_INTERVAL_MINUTES", 50),
            summary_provider=os.environ.get("SUMMARY_PROVIDER", "auto").lower(),
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
            db_path=_path_env("DB_PATH", "data/agent.sqlite3"),
            reports_dir=_path_env("REPORTS_DIR", "reports"),
            instagram_dir=_path_env("INSTAGRAM_DIR", "reports/instagram_posts"),
            create_instagram_posts=_bool_env("CREATE_INSTAGRAM_POSTS", True),
            process_all_matching=_bool_env("PROCESS_ALL_MATCHING", False),
            enrich_articles=_bool_env("ENRICH_ARTICLES", True),
            max_article_links_per_email=_int_env("MAX_ARTICLE_LINKS_PER_EMAIL", 5),
            article_assets_dir=_path_env("ARTICLE_ASSETS_DIR", "data/article_assets"),
            public_media_base_url=os.environ.get("PUBLIC_MEDIA_BASE_URL", ""),
            auto_publish_instagram=_bool_env("AUTO_PUBLISH_INSTAGRAM", False),
            ig_user_id=os.environ.get("IG_USER_ID", ""),
            ig_access_token=os.environ.get("IG_ACCESS_TOKEN", ""),
            ig_api_version=os.environ.get("IG_API_VERSION", "v24.0"),
            auto_publish_facebook=_bool_env("AUTO_PUBLISH_FACEBOOK", False),
            fb_page_id=os.environ.get("FB_PAGE_ID", ""),
            fb_page_access_token=os.environ.get("FB_PAGE_ACCESS_TOKEN", os.environ.get("IG_ACCESS_TOKEN", "")),
            fb_app_id=os.environ.get("FB_APP_ID", ""),
            fb_app_secret=os.environ.get("FB_APP_SECRET", ""),
        )

    def validate_email_access(self) -> None:
        missing = []
        placeholder_values = {
            "",
            "your_email@gmail.com",
            "your_gmail_app_password",
            "sender_address_of_your_ai_news_agent@example.com",
            "your_ai_news_agent_sender@example.com",
        }
        if self.imap_username in placeholder_values:
            missing.append("IMAP_USERNAME")
        if self.imap_password in placeholder_values:
            missing.append("IMAP_PASSWORD")
        if self.email_sender_filter in placeholder_values:
            missing.append("EMAIL_SENDER_FILTER")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"Missing email settings: {joined}. Fill the .env file before reading Gmail."
            )

    def validate_instagram_publish(self) -> None:
        if not self.auto_publish_instagram:
            return
        missing = []
        if not self.public_media_base_url:
            missing.append("PUBLIC_MEDIA_BASE_URL")
        if not self.ig_user_id or not self.ig_user_id.isdigit():
            missing.append("IG_USER_ID (numeric Meta Instagram Business/Creator account ID)")
        if not self.ig_access_token:
            missing.append("IG_ACCESS_TOKEN")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"Instagram auto-publishing is enabled but these values are missing or invalid: {joined}."
            )

    def validate_facebook_publish(self) -> None:
        if not self.auto_publish_facebook:
            return
        missing = []
        if not self.public_media_base_url:
            missing.append("PUBLIC_MEDIA_BASE_URL")
        if not self.fb_page_id or not self.fb_page_id.isdigit():
            missing.append("FB_PAGE_ID")
        if not self.fb_page_access_token:
            missing.append("FB_PAGE_ACCESS_TOKEN")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(
                f"Facebook auto-publishing is enabled but these values are missing or invalid: {joined}."
            )


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
