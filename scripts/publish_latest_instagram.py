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
    publish_ready_facebook_posts,
    publish_instagram_story,
    write_publish_manifest,
)


def main() -> int:
    settings = Settings.from_env()
    settings.validate_instagram_publish()

    # Facebook validation is optional — skip gracefully if not configured
    fb_enabled = bool(settings.auto_publish_facebook and settings.fb_page_id and settings.fb_page_access_token)
    if fb_enabled:
        try:
            settings.validate_facebook_publish()
        except ValueError as exc:
            print(f"WARNING: Facebook publishing disabled — {exc}")
            fb_enabled = False

    settings.instagram_dir.mkdir(parents=True, exist_ok=True)
    batches = (
        [path for path in settings.instagram_dir.iterdir() if path.is_dir()]
        if settings.instagram_dir.exists()
        else []
    )
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

    # ── Instagram carousels ───────────────────────────────────────────────────
    published = publish_ready_carousels(settings, manifest_path)

    # ── Instagram Story — post the cover slide of the best carousel ───────────
    story_published = 0
    if published > 0 and settings.auto_publish_instagram:
        try:
            story_published = publish_instagram_story(settings, manifest_path)
            if story_published:
                print(f"Published {story_published} Instagram Story.")
        except Exception as story_exc:
            print(f"WARNING: Instagram Story publish failed (carousels were published): {story_exc}")

    # ── Facebook page posts ───────────────────────────────────────────────────
    facebook_published = 0
    if fb_enabled:
        try:
            facebook_published = publish_ready_facebook_posts(settings, manifest_path)
        except RuntimeError as fb_exc:
            print(f"WARNING: Facebook publishing failed: {fb_exc}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for post in manifest.get("posts", []):
        status = post.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    print(
        f"Published {published} Instagram carousel(s), "
        f"{story_published} Story, "
        f"{facebook_published} Facebook post(s) "
        f"from {batch_dir}. Statuses: {statuses}"
    )
    failed = statuses.get("publish_failed", 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
