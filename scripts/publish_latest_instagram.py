from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings
from email_summary_agent.publisher import (
    publish_ready_carousels,
    write_publish_manifest,
)


def main() -> int:
    settings = Settings.from_env()
    settings.validate_instagram_publish()

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

    published = publish_ready_carousels(settings, manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for post in manifest.get("posts", []):
        status = post.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    print(
        f"Published {published} Instagram carousel(s) "
        f"from {batch_dir}. Statuses: {statuses}"
    )
    failed = statuses.get("publish_failed", 0)
    return 1 if failed else 0


def _find_latest_publishable_batch(
    batches: list[Path],
    public_media_base_url: str,
) -> tuple[Path, Path] | None:
    for batch_dir in sorted(batches, key=lambda path: path.name, reverse=True):
        carousel_dirs = [path for path in sorted(batch_dir.iterdir()) if path.is_dir()]
        if not carousel_dirs:
            continue
        manifest_path = write_publish_manifest(carousel_dirs, public_media_base_url)
        if not manifest_path:
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        has_pending = any(
            post.get("status") not in {"published", "publish_failed"}
            for post in manifest.get("posts", [])
        )
        if has_pending:
            return batch_dir, manifest_path
    return None


if __name__ == "__main__":
    raise SystemExit(main())
