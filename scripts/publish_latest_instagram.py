from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings  # noqa: E402
from email_summary_agent.publisher import (  # noqa: E402
    publish_ready_carousels,
    write_publish_manifest,
)

# Only consider batches generated within the last N days.
# Older batches are never re-published — this is the primary guard against
# duplicate posts when old batch directories accumulate.
MAX_BATCH_AGE_DAYS = 1


def main() -> int:
    settings = Settings.from_env()
    settings.validate_instagram_publish()

    print(f"public_media_base_url = {settings.public_media_base_url!r}")
    if not settings.public_media_base_url:
        print("PUBLIC_MEDIA_BASE_URL is not set. This must be set to the GitHub Pages URL")
        print("where slides are publicly reachable. The workflow sets it from the")
        print("deploy-pages job output. Ensure deploy-pages ran successfully.")
        return 0

    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    batches = (
        [path for path in settings.instagram_dir.iterdir() if path.is_dir()]
        if settings.instagram_dir.exists()
        else []
    )
    if not batches:
        print("No Instagram carousel batches found.")
        return 0

    selected = _find_latest_publishable_batch(batches, settings.public_media_base_url)
    if not selected:
        print("No unpublished Instagram carousel batch found.")
        return 0
    batch_dir, manifest_path = selected

    try:
        published = publish_ready_carousels(settings, manifest_path)
    except Exception as exc:
        print(f"ERROR during publish: {exc}")
        published = 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for post in manifest.get("posts", []):
        status = post.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    print(
        f"Published {published} Instagram carousel(s) "
        f"from {batch_dir}. Statuses: {statuses}"
    )
    permanently_failed = statuses.get("publish_failed", 0)
    retryable = statuses.get("publish_failed_retryable", 0)
    if retryable and not permanently_failed:
        print(f"{retryable} post(s) failed with retryable errors — will retry next run.")
        return 0
    return 1 if permanently_failed else 0


def _batch_is_recent(batch_dir: Path) -> bool:
    """Return True if batch_dir was created within MAX_BATCH_AGE_DAYS days.

    Batch directory names follow the pattern YYYYMMDD-HHMMSS so we can
    parse the date directly from the directory name without stat calls.
    If the name cannot be parsed we fall back to the directory mtime.
    """
    name = batch_dir.name
    try:
        # Name format: 20250523-143000
        dt = datetime.strptime(name[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt
        return age <= timedelta(days=MAX_BATCH_AGE_DAYS)
    except ValueError:
        pass
    try:
        mtime = batch_dir.stat().st_mtime
        age = datetime.now(timezone.utc).timestamp() - mtime
        return age <= MAX_BATCH_AGE_DAYS * 86400
    except OSError:
        return False


def _batch_is_fully_published(manifest_path: Path) -> bool:
    """Return True when every post in the manifest is in a terminal published state.

    A post is considered fully published if it has a published_at timestamp OR
    its status is "published" (backwards-compatible with old manifests that were
    written before published_at was introduced).
    """
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    posts = manifest.get("posts", [])
    if not posts:
        return False
    return all(
        post.get("published_at") or post.get("status") == "published"
        for post in posts
    )


def _find_latest_publishable_batch(
    batches: list[Path],
    public_media_base_url: str,
) -> tuple[Path, Path] | None:
    # Sort newest-first (batch dirs are YYYYMMDD-HHMMSS so string sort works)
    for batch_dir in sorted(batches, key=lambda p: p.name, reverse=True):
        # Guard 1: skip batches older than MAX_BATCH_AGE_DAYS
        if not _batch_is_recent(batch_dir):
            print(f"Skipping old batch: {batch_dir.name}")
            continue

        carousel_dirs = [p for p in sorted(batch_dir.iterdir()) if p.is_dir()]
        if not carousel_dirs:
            continue

        # Guard 2: if an existing manifest shows every post already published,
        # skip without calling write_publish_manifest (which rewrites statuses).
        existing_manifest = batch_dir / "publish_manifest.json"
        if _batch_is_fully_published(existing_manifest):
            print(f"Skipping fully published batch: {batch_dir.name}")
            continue

        manifest_path = write_publish_manifest(carousel_dirs, public_media_base_url)
        if not manifest_path:
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # Guard 3: check for posts that are neither published nor permanently failed
        has_pending = any(
            not post.get("published_at") and
            post.get("status") not in {"published", "publish_failed"}
            for post in manifest.get("posts", [])
        )
        if has_pending:
            return batch_dir, manifest_path
    return None


if __name__ == "__main__":
    raise SystemExit(main())
