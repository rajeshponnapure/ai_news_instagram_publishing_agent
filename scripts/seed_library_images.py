"""seed_library_images.py — Download HD Wikimedia Commons images for under-represented AI topics.

Topics currently under-represented in the library:
  - Microsoft  (1 image)
  - Meta       (2 images)
  - Nvidia     (3 images)

This script searches Wikimedia Commons for each topic, filters for HD images
(≥ 1280×720), and downloads them into data/images/ with proper metadata
so the library search index can find them via token overlap scoring.

Usage:
    python scripts/seed_library_images.py [--dry-run] [--max-per-topic 8]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_LIBRARY_DIR = PROJECT_ROOT / "data" / "images"
IMAGE_INDEX_PATH = IMAGE_LIBRARY_DIR / "index.json"

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

STOP_IMAGE_TOKENS = frozenset({
    "about", "after", "article", "blog", "content", "cookie", "from",
    "image", "launch", "latest", "more", "news", "privacy", "release",
    "story", "summary", "technology", "this", "update", "with",
})

# ── Topics to seed ────────────────────────────────────────────────────────────
# (seed_label, wikimedia_search_query, additional_seed_context_for_tokens)
SEED_TOPICS: list[tuple[str, str, str]] = [
    # Microsoft
    ("Microsoft AI", "Microsoft artificial intelligence", "Microsoft AI Copilot Azure cloud computing artificial intelligence"),
    ("Microsoft Copilot", "Microsoft Copilot", "Microsoft Copilot AI assistant productivity artificial intelligence"),
    ("Microsoft Azure", "Microsoft Azure cloud", "Microsoft Azure cloud computing data center AI infrastructure"),
    # Meta
    ("Meta AI", "Meta artificial intelligence", "Meta AI Facebook artificial intelligence machine learning research"),
    ("Meta Llama", "Meta Llama model", "Meta Llama large language model open source AI artificial intelligence"),
    ("Meta Reality Labs", "Meta Quest VR", "Meta virtual reality augmented reality Quest artificial intelligence"),
    # Nvidia
    ("NVIDIA AI", "NVIDIA artificial intelligence", "NVIDIA GPU artificial intelligence deep learning CUDA computing"),
    ("NVIDIA GPU", "NVIDIA GPU chip", "NVIDIA graphics processing unit GPU AI chip semiconductor"),
    ("NVIDIA DGX", "NVIDIA DGX supercomputer", "NVIDIA DGX supercomputer AI training HPC data center"),
    # — Bonus: General AI/tech to broaden coverage —
    ("AI chip semiconductor", "artificial intelligence chip semiconductor", "AI chip semiconductor processor computing artificial intelligence"),
    ("data center AI", "data center artificial intelligence", "data center server AI cloud computing infrastructure"),
    ("robotics AI", "robot artificial intelligence", "robotics robot autonomous artificial intelligence machine learning"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _important_tokens(text: str) -> set[str]:
    """Extract significant alphanumeric tokens (≥4 chars, non-stop-words)."""
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in STOP_IMAGE_TOKENS
    }


def _topic_signature(text: str) -> list[str]:
    tokens = list(
        t for t in _important_tokens(text)
        if t not in {"latest", "update", "article", "story", "image", "new"}
    )
    return sorted(tokens)[:5]


def _safe_print(msg: str) -> None:
    """Print with fallback encoding for Windows cp1252."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def _download_image(url: str, dest: Path) -> bool:
    """Download image from url to dest. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": CHROME_USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower()
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, ".jpg")
            data = resp.read(8_000_000)
        if len(data) < 20_000:
            return False
        dest = dest.with_suffix(suffix)
        dest.write_bytes(data)
        return True
    except Exception as exc:
        _safe_print(f"      [FAIL] Download failed: {exc}")
        return False


def _search_wikimedia_images(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Wikimedia Commons for HD images matching query.

    Returns list of dicts with keys: url, width, height, title, mime.
    Retries up to 3 times with exponential backoff on rate limits.
    """
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrlimit": str(max_results),
        "gsrsearch": query,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|dimensions",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": CHROME_USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:
            if attempt < 2 and "429" in str(exc):
                wait = 5 * (attempt + 1)
                _safe_print(f"      [RATE-LIMIT] Waiting {wait}s...")
                time.sleep(wait)
                continue
            _safe_print(f"      [FAIL] Wikimedia API error: {exc}")
            return []

    results: list[dict[str, Any]] = []
    pages = data.get("query", {}).get("pages", {})
    for page_num, page in pages.items():
        info = (page.get("imageinfo") or [{}])[0]
        img_url = str(info.get("url") or "")
        if not img_url:
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        mime = str(info.get("mime") or "").lower()
        title = str(page.get("title") or "").lower()

        # Filter for HD
        if width < 1280 or height < 720:
            continue
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        # Skip logos/icons/vectors (unless query explicitly mentions them)
        if any(term in title for term in ("logo", "icon", "symbol", "seal", "flag", "vector", "diagram")):
            continue

        results.append({
            "url": img_url,
            "width": width,
            "height": height,
            "title": title,
            "mime": mime,
        })
    return results


def _upsert_index(entry: dict[str, Any]) -> None:
    """Add a single entry to index.json, avoiding duplicates by id."""
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {"images": []}
    try:
        data = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    image_id = entry.get("id", "")
    images = [item for item in data.get("images", []) if item.get("id") != image_id]
    images.append(entry)
    IMAGE_INDEX_PATH.write_text(
        json.dumps({"images": images}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def _wikimedia_thumbnail_url(img_url: str, width: int = 1920) -> str:
    """Convert a full-size Wikimedia URL to a thumbnail URL to avoid rate limits.

    Wikimedia URL pattern:
      https://upload.wikimedia.org/wikipedia/commons/a/ab/Filename.jpg
    Thumbnail pattern:
      https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Filename.jpg/1920px-Filename.jpg
    """
    # Can also try the direct ?width= param, but thumb is more reliable
    if "/thumb/" in img_url or "?width=" in img_url:
        return img_url
    # Split at the /commons/ or /en/ etc to insert /thumb/
    import re
    m = re.search(r"^(https://upload\.wikimedia\.org/wikipedia/[^/]+/)(.*)$", img_url)
    if m:
        base = m.group(1)
        path = m.group(2)
        # path is like "a/ab/Filename.jpg"
        filename = path.rsplit("/", 1)[-1]
        thumb_path = path.rsplit(".", 1)[0]
        ext = path.rsplit(".", 1)[-1] if "." in path else "jpg"
        return f"{base}thumb/{path}/{width}px-{filename}"
    return img_url


def main(dry_run: bool = False, max_per_topic: int = 8) -> int:
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing index to avoid re-downloading known URLs
    existing_urls: set[str] = set()
    try:
        existing = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
        for entry in existing.get("images", []):
            existing_urls.add(str(entry.get("url", "")))
    except (OSError, json.JSONDecodeError):
        pass

    total_downloaded = 0
    total_skipped = 0
    total_found = 0

    for label, search_query, seed_context in SEED_TOPICS:
        print(f"\n{'='*60}")
        print(f"  Topic: {label}")
        print(f"  Query: {search_query!r}")
        print(f"{'='*60}")

        results = _search_wikimedia_images(search_query, max_results=max_per_topic * 2)
        print(f"  Found {len(results)} HD images on Wikimedia")

        taken = 0
        for result in results:
            if taken >= max_per_topic:
                break

            img_url = result["url"]
            # Use thumbnail URL to avoid rate limits
            dl_url = _wikimedia_thumbnail_url(img_url, width=1920)

            if img_url in existing_urls:
                total_skipped += 1
                continue

            # Compute ID from URL to make it deterministic
            cache_key = hashlib.sha1(img_url.encode("utf-8")).hexdigest()[:16]
            dest = IMAGE_LIBRARY_DIR / f"{cache_key}.jpg"
            if dest.exists():
                _safe_print(f"    [CACHED] Already cached: {dest.name}")
                taken += 1
                total_skipped += 1
                continue

            if dry_run:
                print(f"    [DRY RUN] Would download: {img_url[:80]}...")
                print(f"             -> {dest.name} ({result['width']}x{result['height']})")
                taken += 1
                total_found += 1
                continue

            # Download (using thumbnail URL for rate-limit safety)
            print(f"    Downloading {result['width']}x{result['height']}...", end=" ", flush=True)
            ok = _download_image(dl_url, dest)
            if not ok:
                # Fallback: try full-size URL
                print("  (trying full-size...)", end=" ", flush=True)
                ok = _download_image(img_url, dest)
            if not ok:
                _safe_print("FAIL")
                time.sleep(3)
                continue
            _safe_print("OK")
            dest_path = str(dest)

            # Build metadata
            combined_seed = f"{seed_context} {label} {search_query} {result['title']}"
            tokens = sorted(_important_tokens(combined_seed))
            entry: dict[str, Any] = {
                "id": cache_key,
                "url": img_url,
                "seed": combined_seed[:500],
                "path": dest_path,
                "tokens": tokens,
                "topic": _topic_signature(combined_seed),
                "source": "seeded",
            }

            # Update index
            _upsert_index(entry)

            # Also write individual .json metadata file so _iter_image_metadata finds it
            meta_file = IMAGE_LIBRARY_DIR / f"{cache_key}.json"
            meta_file.write_text(json.dumps(entry, ensure_ascii=True), encoding="utf-8")

            existing_urls.add(img_url)
            total_downloaded += 1
            taken += 1
            import random; time.sleep(3 + random.uniform(0, 2))  # Rate-limit courtesy delay + jitter

        if not results:
            print("  (no HD images found)")

    print(f"\n{'='*60}")
    print(f"  Summary:")
    print(f"    Downloaded: {total_downloaded}")
    print(f"    Skipped (already in index): {total_skipped}")
    if dry_run:
        print(f"    Found (dry run): {total_found}")
    print(f"{'='*60}")

    return 0 if total_downloaded > 0 or dry_run else 1


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    max_per_topic = 8
    # Add rate-limit courtesy delay before starting
    print("Waiting 5s before first Wikimedia API call to avoid rate limits...")
    time.sleep(5)
    # Add urllib.error import for retry logic
    import urllib.error

    for arg in sys.argv:
        if arg.startswith("--max-per-topic="):
            try:
                max_per_topic = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    sys.exit(main(dry_run=dry_run, max_per_topic=max_per_topic))
