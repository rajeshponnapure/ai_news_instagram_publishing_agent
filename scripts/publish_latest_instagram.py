from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_summary_agent.config import Settings
from email_summary_agent.publisher import publish_ready_carousels, write_publish_manifest


def main() -> int:
    settings = Settings.from_env()
    settings.validate_instagram_publish()
    batches = [path for path in settings.instagram_dir.iterdir() if path.is_dir()] if settings.instagram_dir.exists() else []
    if not batches:
        print("No Instagram carousel batches found.")
        return 0
    batch_dir = max(batches, key=lambda path: path.name)
    carousel_dirs = [path for path in sorted(batch_dir.iterdir()) if path.is_dir()]
    if not carousel_dirs:
        print(f"No carousel folders found in {batch_dir}.")
        return 0

    manifest_path = write_publish_manifest(carousel_dirs, settings.public_media_base_url)
    if not manifest_path:
        print("No publish manifest was created.")
        return 0

    published = publish_ready_carousels(settings, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses = {}
    for post in manifest.get("posts", []):
        status = post.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    print(f"Published {published} carousel(s) from {batch_dir}. Statuses: {statuses}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
