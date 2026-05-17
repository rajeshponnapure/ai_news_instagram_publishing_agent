from __future__ import annotations

import json
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
    posts = []
    for index, carousel_dir in enumerate(carousel_dirs):
        slides = sorted(carousel_dir.glob("slide_*.png"))[:10]
        caption_path = carousel_dir / "caption.txt"
        posts.append(
            {
                "folder": str(carousel_dir),
                "caption": caption_path.read_text(encoding="utf-8") if caption_path.exists() else "",
                "local_slides": [str(path) for path in slides],
                "public_slide_urls": [
                    _public_url(public_media_base_url, batch_dir, path)
                    for path in slides
                    if public_media_base_url
                ],
                "status": "ready_for_upload" if not public_media_base_url else "ready_for_publish",
            }
        )
    manifest_path = batch_dir / "publish_manifest.json"
    manifest_path.write_text(json.dumps({"posts": posts}, ensure_ascii=True, indent=2), encoding="utf-8")
    return manifest_path


def publish_ready_carousels(settings: Settings, manifest_path: Path) -> int:
    if not settings.auto_publish_instagram:
        return 0
    if not settings.ig_user_id or not settings.ig_access_token:
        raise ValueError("IG_USER_ID and IG_ACCESS_TOKEN are required for Instagram auto-publishing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    published = 0
    for post in manifest.get("posts", []):
        if post.get("status") not in {"ready_for_publish", "ready_for_upload"}:
            continue
        urls = [url for url in post.get("public_slide_urls", []) if url]
        if len(urls) < 2:
            continue
        creation_id = _create_carousel_container(settings, urls[:10], post.get("caption", ""))
        _publish_container(settings, creation_id)
        post["status"] = "published"
        post["creation_id"] = creation_id
        published += 1
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


def _public_url(base_url: str, batch_dir: Path, local_path: Path) -> str:
    relative = local_path.relative_to(batch_dir).as_posix()
    return base_url.rstrip("/") + "/" + urllib.parse.quote(batch_dir.name) + "/" + urllib.parse.quote(relative)


