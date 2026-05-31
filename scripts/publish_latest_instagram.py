from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings  # noqa: E402
from email_summary_agent.publisher import (  # noqa: E402
    publish_ready_carousels,
    write_publish_manifest,
)

# Older batches are never re-published unless this window is explicitly raised.
MAX_BATCH_AGE_DAYS = int(os.environ.get("PUBLISH_MAX_BATCH_AGE_DAYS", "3"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish generated Instagram carousel batches.")
    parser.add_argument("--all", action="store_true", help="Publish every pending recent batch, oldest first.")
    args = parser.parse_args()

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

    if args.all:
        selected_batches = _find_publishable_batches(batches, settings.public_media_base_url)
    else:
        selected = _find_latest_publishable_batch(batches, settings.public_media_base_url)
        selected_batches = [selected] if selected else []

    if not selected_batches:
        print("No unpublished Instagram carousel batch found.")
        return 0

    total_published = 0
    permanently_failed = 0
    retryable = 0
    for batch_dir, manifest_path in selected_batches:
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
        total_published += published
        permanently_failed += statuses.get("publish_failed", 0)
        retryable += statuses.get("publish_failed_retryable", 0)

    if retryable and not permanently_failed:
        print(f"{retryable} post(s) failed with retryable errors; will retry next run.")
        return 0
    print(f"Total published this run: {total_published}")
    return 1 if permanently_failed else 0


def _batch_is_recent(batch_dir: Path) -> bool:
    name = batch_dir.name
    try:
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
    for batch_dir in sorted(batches, key=lambda p: p.name, reverse=True):
        selected = _manifest_if_batch_has_pending(batch_dir, public_media_base_url)
        if selected:
            return selected
    return None


def _find_publishable_batches(
    batches: list[Path],
    public_media_base_url: str,
) -> list[tuple[Path, Path]]:
    selected: list[tuple[Path, Path]] = []
    for batch_dir in sorted(batches, key=lambda p: p.name):
        item = _manifest_if_batch_has_pending(batch_dir, public_media_base_url)
        if item:
            selected.append(item)
    return selected


def _manifest_if_batch_has_pending(
    batch_dir: Path,
    public_media_base_url: str,
) -> tuple[Path, Path] | None:
    if not _batch_is_recent(batch_dir):
        print(f"Skipping old batch: {batch_dir.name}")
        return None

    carousel_dirs = [p for p in sorted(batch_dir.iterdir()) if p.is_dir()]
    if not carousel_dirs:
        return None

    existing_manifest = batch_dir / "publish_manifest.json"
    if _batch_is_fully_published(existing_manifest):
        print(f"Skipping fully published batch: {batch_dir.name}")
        return None

    manifest_path = write_publish_manifest(carousel_dirs, public_media_base_url)
    if not manifest_path:
        return None

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    has_pending = any(
        not post.get("published_at")
        and post.get("status") not in {"published", "publish_failed"}
        for post in manifest.get("posts", [])
    )
    return (batch_dir, manifest_path) if has_pending else None


if __name__ == "__main__":
    raise SystemExit(main())
