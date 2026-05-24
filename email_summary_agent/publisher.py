from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from .config import Settings


def write_publish_manifest(carousel_dirs: list[Path], public_media_base_url: str = "") -> Path | None:
    if not carousel_dirs:
        return None
    batch_dir = carousel_dirs[0].parent
    manifest_path = batch_dir / "publish_manifest.json"
    existing_posts = _existing_manifest_posts(manifest_path)
    posts = []
    for index, carousel_dir in enumerate(carousel_dirs):
        slides = sorted(carousel_dir.glob("slide_*.png"))[:20]
        caption_path = carousel_dir / "caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""
        existing = existing_posts.get(str(carousel_dir), {})
        existing_status = existing.get("status", "")
        status = "ready_for_upload" if not public_media_base_url else "ready_for_publish"
        if existing_status in {"published", "container_created", "publish_failed_retryable", "publish_failed"}:
            status = existing_status
        posts.append(
            {
                "folder": str(carousel_dir),
                "caption": caption,
                "local_slides": [str(path) for path in slides],
                "public_slide_urls": [
                    _public_url(public_media_base_url, batch_dir, path)
                    for path in slides
                    if public_media_base_url
                ],
                "status": status,
                **_carry_publish_fields(existing),
            }
        )
    manifest_path.write_text(json.dumps({"posts": posts}, ensure_ascii=True, indent=2), encoding="utf-8")
    return manifest_path


def publish_ready_carousels(settings: Settings, manifest_path: Path) -> int:
    if not settings.auto_publish_instagram:
        return 0
    if not settings.ig_user_id or not settings.ig_access_token:
        raise ValueError("IG_USER_ID and IG_ACCESS_TOKEN are required for Instagram auto-publishing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    published = 0
    posts = manifest.get("posts", [])
    print(f"publish_ready_carousels: manifest has {len(posts)} post(s)")
    for post_idx, post in enumerate(posts, 1):
        folder = post.get("folder", f"post-{post_idx}")
        status = post.get("status", "unknown")
        # Hard guard: never republish a post that already has a published_at timestamp,
        # regardless of what status the manifest carries.  This prevents duplicates
        # when write_publish_manifest() is called multiple times across runs.
        if post.get("published_at"):
            print(f"  [{post_idx}] SKIP (already published at {post['published_at']}): {folder}")
            continue
        if post.get("status") not in {"ready_for_publish", "ready_for_upload", "container_created", "publish_failed_retryable"}:
            print(f"  [{post_idx}] SKIP (status={status!r} not publishable): {folder}")
            continue
        urls = [url for url in post.get("public_slide_urls", []) if url]
        if len(urls) < 2:
            folder = post.get("folder", "unknown")
            print(
                f"SKIPPING carousel '{folder}': only {len(urls)} public URL(s) found "
                f"(Instagram requires ≥2). Check that PUBLIC_MEDIA_BASE_URL is set "
                f"and the batch was deployed to GitHub Pages before publishing."
            )
            post["status"] = "publish_failed"
            post["error"] = f"Only {len(urls)} public slide URL(s); Instagram requires at least 2."
            manifest_path.write_text(
                __import__("json").dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
            )
            continue
        try:
            # Instagram enforces a minimum gap between consecutive posts.
            # Wait 30 seconds before every post after the first so the API
            # does not reject the second and subsequent carousels with a
            # rate-limit error when a single run processes multiple emails.
            if published > 0:
                print(f"Waiting 30 s before next carousel to respect Instagram rate limits …")
                time.sleep(30)

            creation_id = post.get("creation_id")
            if creation_id:
                # Check whether the previously-stored container is still usable.
                status = _container_status(settings, creation_id)
                if status.get("status_code") in {"ERROR", "EXPIRED"}:
                    creation_id = None
            creation_id = creation_id or _create_carousel_container(settings, urls[:20], post.get("caption", ""))
            post["creation_id"] = creation_id
            post["status"] = "container_created"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            _wait_until_container_ready(settings, creation_id)
            _publish_container_with_retry(settings, creation_id)
            post["status"] = "published"
            post["published_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            print(f"Published carousel {published + 1}: {post.get('folder', '')}")
            published += 1
        except RuntimeError as exc:
            post["status"] = "publish_failed_retryable" if _is_retryable_publish_error(str(exc)) else "publish_failed"
            post["error"] = str(exc)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            if post["status"] == "publish_failed":
                raise
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    return published


def _create_carousel_container(settings: Settings, image_urls: list[str], caption: str) -> str:
    child_ids = []
    for image_url in image_urls:
        child = _graph_post(
            settings,
            f"{settings.ig_user_id}/media",
            {
                "image_url": image_url,
                "is_carousel_item": "true",
            },
        )
        child_ids.append(child["id"])
    parent = _graph_post(
        settings,
        f"{settings.ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption[:2200],
        },
    )
    return parent["id"]


def _publish_container(settings: Settings, creation_id: str) -> dict:
    return _graph_post(
        settings,
        f"{settings.ig_user_id}/media_publish",
        {"creation_id": creation_id},
    )


def _publish_container_with_retry(settings: Settings, creation_id: str) -> dict:
    last_error = ""
    for attempt in range(1, 7):
        try:
            return _publish_container(settings, creation_id)
        except RuntimeError as exc:
            last_error = str(exc)
            if not _is_retryable_publish_error(last_error):
                raise
            time.sleep(min(90, attempt * 15))
    raise RuntimeError(last_error or f"Instagram container {creation_id} was not ready for publishing.")


def _wait_until_container_ready(settings: Settings, creation_id: str) -> None:
    """Poll until the media container is FINISHED. Max wait ~8 minutes."""
    last_status = ""
    for attempt in range(1, 17):  # up to 16 attempts
        status = _container_status(settings, creation_id)
        last_status = status.get("status_code", "") or status.get("status", "")
        if last_status == "FINISHED":
            return
        if last_status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(
                f"Instagram media container {creation_id} failed with status {last_status}: {status}"
            )
        # Back-off: 10s, 15s, 20s … capped at 30s
        time.sleep(min(30, 10 + attempt * 5))
    raise RuntimeError(
        f"Instagram media container {creation_id} was not ready after waiting. Last status: {last_status}"
    )


def _container_status(settings: Settings, creation_id: str) -> dict:
    return _graph_get(
        settings,
        creation_id,
        {"fields": "status_code,status"},
    )


def _graph_post(settings: Settings, path: str, fields: dict[str, str]) -> dict:
    url = f"https://graph.facebook.com/{settings.ig_api_version}/{path}"
    payload = {**fields, "access_token": settings.ig_access_token}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph API request failed for {path}: {exc.code} {exc.reason}. Response: {body}") from exc


def _graph_get(settings: Settings, path: str, fields: dict[str, str]) -> dict:
    url = f"https://graph.facebook.com/{settings.ig_api_version}/{path}"
    query = urllib.parse.urlencode({**fields, "access_token": settings.ig_access_token})
    request = urllib.request.Request(f"{url}?{query}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph API request failed for {path}: {exc.code} {exc.reason}. Response: {body}") from exc


def _is_retryable_publish_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "media id is not available",
            "not ready for publishing",
            "was not ready",
            '"code":9007',
            '"error_subcode":2207027',
            "temporarily",
            "transient",
        )
    )


def _public_url(base_url: str, batch_dir: Path, local_path: Path) -> str:
    relative = local_path.relative_to(batch_dir).as_posix()
    return base_url.rstrip("/") + "/" + urllib.parse.quote(batch_dir.name) + "/" + urllib.parse.quote(relative)


def _existing_manifest_posts(manifest_path: Path) -> dict[str, dict]:
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    posts = {}
    for post in manifest.get("posts", []):
        folder = str(post.get("folder", ""))
        if folder:
            posts[folder] = post
    return posts


def _carry_publish_fields(existing: dict) -> dict:
    """Carry over publish-state fields from an existing manifest entry."""
    fields = {}
    for key in ("creation_id", "published_at", "error"):
        if key in existing:
            fields[key] = existing[key]
    return fields
