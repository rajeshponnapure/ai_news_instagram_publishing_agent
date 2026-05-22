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
        slides = sorted(carousel_dir.glob("slide_*.png"))[:10]
        caption_path = carousel_dir / "caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""
        existing = existing_posts.get(str(carousel_dir), {})
        existing_status = existing.get("status", "")
        status = "ready_for_upload" if not public_media_base_url else "ready_for_publish"
        if existing_status in {"published", "container_created", "publish_failed_retryable", "publish_failed"}:
            status = existing_status
        story_score, story_reason = _score_story_candidate(carousel_dir, caption, len(slides))
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
                "story_score": existing.get("story_score", story_score),
                "story_selected_reason": existing.get("story_selected_reason", story_reason),
                **_carry_publish_fields(existing),
            }
        )
    manifest_path.write_text(json.dumps({"posts": posts}, ensure_ascii=True, indent=2), encoding="utf-8")
    return manifest_path


def publish_instagram_story(settings: Settings, manifest_path: Path) -> int:
    """Publish the cover slide of the highest-quality carousel as an Instagram Story.

    Picks the first successfully published carousel post, takes its first
    public slide URL (the cover/image slide), and posts it as a Story via
    the Instagram Graph API media container flow with ``media_type=IMAGE``.

    Returns 1 if a story was published, 0 otherwise.
    """
    if not settings.auto_publish_instagram:
        return 0
    if not settings.ig_user_id or not settings.ig_access_token:
        return 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Find the best published post — prefer the one with the most slides
    best_post: dict | None = None
    for post in manifest.get("posts", []):
        if post.get("status") != "published":
            continue
        if post.get("story_published"):
            continue  # already posted as a story
        urls = [u for u in post.get("public_slide_urls", []) if u]
        if not urls:
            continue
        if best_post is None or _story_rank(post) > _story_rank(best_post):
            best_post = post

    if not best_post:
        return 0

    # Use the first slide (cover/image slide) as the story image
    story_url = [u for u in best_post.get("public_slide_urls", []) if u][0]

    try:
        # Create a single-image media container for the Story
        container = _graph_post(
            settings,
            f"{settings.ig_user_id}/media",
            {
                "image_url": story_url,
                "media_type": "IMAGE",
                "is_story": "true",
            },
        )
        story_container_id = container.get("id", "")
        if not story_container_id:
            raise RuntimeError(f"Instagram did not return a story container ID. Response: {container}")

        _wait_until_container_ready(settings, story_container_id)

        _graph_post(
            settings,
            f"{settings.ig_user_id}/media_publish",
            {"creation_id": story_container_id},
        )
        best_post["story_published"] = True
        best_post["story_published_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        best_post["story_selected_reason"] = best_post.get("story_selected_reason") or "Highest quality score among published carousels."
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
        return 1
    except RuntimeError as exc:
        print(f"WARNING: Instagram Story publish failed: {exc}")
        return 0


def publish_ready_carousels(settings: Settings, manifest_path: Path) -> int:
    if not settings.auto_publish_instagram:
        return 0
    if not settings.ig_user_id or not settings.ig_access_token:
        raise ValueError("IG_USER_ID and IG_ACCESS_TOKEN are required for Instagram auto-publishing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    published = 0
    for post in manifest.get("posts", []):
        if post.get("status") not in {"ready_for_publish", "ready_for_upload", "container_created", "publish_failed_retryable"}:
            continue
        urls = [url for url in post.get("public_slide_urls", []) if url]
        if len(urls) < 2:
            continue
        try:
            creation_id = post.get("creation_id") or _create_carousel_container(settings, urls[:10], post.get("caption", ""))
            post["creation_id"] = creation_id
            post["status"] = "container_created"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            _wait_until_container_ready(settings, creation_id)
            _publish_container_with_retry(settings, creation_id)
            post["status"] = "published"
            post["published_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            if settings.auto_publish_facebook:
                try:
                    _publish_facebook_post(settings, post)
                except RuntimeError as fb_exc:
                    # Facebook failure must not abort a successful Instagram publish
                    post["facebook_status"] = "publish_failed"
                    post["facebook_error"] = str(fb_exc)
                    print(f"WARNING: Facebook publish failed (Instagram was published successfully): {fb_exc}")
            published += 1
        except RuntimeError as exc:
            post["status"] = "publish_failed_retryable" if _is_retryable_publish_error(str(exc)) else "publish_failed"
            post["error"] = str(exc)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            if post["status"] == "publish_failed":
                raise
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    return published


def publish_ready_facebook_posts(settings: Settings, manifest_path: Path) -> int:
    if not settings.auto_publish_facebook:
        return 0
    if not settings.fb_page_id or not settings.fb_page_access_token:
        raise ValueError("FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN are required for Facebook auto-publishing.")
    _preflight_facebook_publish(settings)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    published = 0
    for post in manifest.get("posts", []):
        if post.get("facebook_status") == "published":
            continue
        if post.get("status") not in {"published", "ready_for_publish"}:
            continue
        urls = [url for url in post.get("public_slide_urls", []) if url]
        if not urls:
            continue
        try:
            _publish_facebook_post(settings, post)
            published += 1
        except RuntimeError as exc:
            post["facebook_status"] = "publish_failed"
            post["facebook_error"] = str(exc)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
            # Re-raise so the caller knows publishing failed and can set exit code 1
            raise
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    return published


def _score_story_candidate(carousel_dir: Path, caption: str, slide_count: int) -> tuple[float, str]:
    metadata_path = carousel_dir / "metadata.json"
    metadata = {}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    article_items = metadata.get("article_items") or []
    has_article_image = any(
        item.get("image_path") or item.get("image_url")
        for item in article_items
        if isinstance(item, dict)
    )
    has_source = bool(metadata.get("article_url") or any(isinstance(item, dict) and item.get("url") for item in article_items))
    article_count = len([item for item in article_items if isinstance(item, dict)])
    caption_words = re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", caption or "")
    concrete_facts = len(re.findall(r"\b(?:20\d{2}|\d+(?:\.\d+)?%?|GPT|Claude|Gemini|Llama|API|GPU|AI)\b", caption or "", flags=re.I))
    noise_hits = len(re.findall(r"\b(cookie|unsubscribe|privacy policy|terms of service|primary entities|likely themes)\b", caption or "", flags=re.I))
    source_links = len(re.findall(r"https?://\S+", caption or ""))
    source_domains = len({re.sub(r"^https?://(?:www\.)?([^/]+).*$", r"\1", item.get("url", ""), flags=re.I) for item in article_items if isinstance(item, dict) and item.get("url")})

    score = 0.0
    score += min(slide_count, 10) * 0.08
    score += 0.35 if has_article_image else 0.0
    score += 0.20 if has_source else 0.0
    score += min(article_count, 4) * 0.05
    score += min(len(caption_words) / 120, 0.25)
    score += min(concrete_facts * 0.05, 0.20)
    score += min(source_links * 0.03, 0.12)
    score += min(source_domains * 0.04, 0.12)
    score -= min(noise_hits * 0.20, 0.60)
    score = round(max(0.0, min(score, 1.0)), 3)

    reasons = []
    if has_article_image:
        reasons.append("article image available")
    if has_source:
        reasons.append("source URL available")
    if concrete_facts:
        reasons.append(f"{concrete_facts} concrete signal(s)")
    if source_links:
        reasons.append(f"{source_links} source link(s)")
    if not reasons:
        reasons.append("best available carousel")
    return score, ", ".join(reasons)


def _story_rank(post: dict) -> tuple[float, int]:
    urls = [url for url in post.get("public_slide_urls", []) if url]
    try:
        score = float(post.get("story_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return score, len(urls)


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


def _publish_facebook_post(settings: Settings, post: dict) -> None:
    """Publish a multi-image post to a Facebook Page.

    Requires a Page Access Token with the ``pages_manage_posts`` and
    ``pages_read_engagement`` permissions.  The old ``publish_actions``
    user-level permission is NOT required and must NOT be used.

    Flow:
      1. Upload each slide as an unpublished photo (``published=false``).
      2. Attach all photo IDs to a single ``/{page_id}/feed`` post.

    If photo staging fails with a 403/deprecated error the function raises a
    ``RuntimeError`` with a human-readable explanation of which permissions
    are needed so the caller can surface it clearly.
    """
    if post.get("facebook_status") == "published":
        return
    urls = [url for url in post.get("public_slide_urls", []) if url][:10]
    if not urls:
        return

    media_ids = []
    for image_url in urls:
        try:
            photo = _facebook_graph_post(
                settings,
                f"{settings.fb_page_id}/photos",
                {
                    "url": image_url,
                    "published": "false",
                },
            )
        except RuntimeError as exc:
            error_body = str(exc)
            if "publish_actions" in error_body or "deprecated" in error_body.lower():
                raise RuntimeError(
                    "Facebook photo upload failed because the token is missing required permissions. "
                    "You need a Page Access Token (not a User token) with 'pages_manage_posts' and "
                    "'pages_read_engagement' permissions. The old 'publish_actions' permission is "
                    f"deprecated and must not be used. Original error: {error_body}"
                ) from exc
            raise
        if photo.get("id"):
            media_ids.append(photo["id"])

    if not media_ids:
        raise RuntimeError("Facebook did not return any uploaded photo IDs.")

    fields: dict[str, str] = {
        "message": _facebook_caption(post.get("caption", "")),
        "published": "true",
    }
    for index, media_id in enumerate(media_ids):
        fields[f"attached_media[{index}]"] = json.dumps({"media_fbid": media_id})

    result = _facebook_graph_post(settings, f"{settings.fb_page_id}/feed", fields)
    post["facebook_status"] = "published"
    post["facebook_post_id"] = result.get("id", "")
    post["facebook_published_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def _facebook_caption(caption: str) -> str:
    caption = re.sub(r"\n{3,}", "\n\n", caption or "").strip()
    suffix = "\n\nAlso published on Instagram by Graitech."
    return (caption[:4500] + suffix)[:5000]


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


def _facebook_graph_post(settings: Settings, path: str, fields: dict[str, str]) -> dict:
    url = f"https://graph.facebook.com/{settings.ig_api_version}/{path}"
    payload = {**fields, "access_token": settings.fb_page_access_token}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Facebook Graph API request failed for {path}: {exc.code} {exc.reason}. Response: {body}") from exc


def _preflight_facebook_publish(settings: Settings) -> None:
    if not settings.fb_app_id or not settings.fb_app_secret:
        return
    app_access_token = f"{settings.fb_app_id}|{settings.fb_app_secret}"
    query = urllib.parse.urlencode({
        "input_token": settings.fb_page_access_token,
        "access_token": app_access_token,
    })
    request = urllib.request.Request(f"https://graph.facebook.com/debug_token?{query}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Facebook token debug failed: {exc.code} {exc.reason}. Response: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Facebook token debug failed: {exc}") from exc

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if not data.get("is_valid"):
        raise RuntimeError(f"Facebook Page access token is invalid or expired: {payload}")

    token_type = str(data.get("type", "")).upper()
    if token_type and token_type != "PAGE":
        raise RuntimeError(f"Facebook token type must be PAGE, got {token_type}. Debug payload: {payload}")

    scopes = {str(scope) for scope in data.get("scopes", []) if str(scope)}
    required_scopes = {"pages_manage_posts", "pages_read_engagement"}
    missing_scopes = sorted(required_scopes - scopes)
    if missing_scopes:
        raise RuntimeError(f"Facebook token is missing required scopes: {', '.join(missing_scopes)}. Debug payload: {payload}")


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
    carried = {}
    for key in (
        "creation_id",
        "published_at",
        "error",
        "facebook_status",
        "facebook_post_id",
        "facebook_published_at",
        "facebook_error",
        "story_published",
        "story_published_at",
    ):
        if existing.get(key):
            carried[key] = existing[key]
    return carried
