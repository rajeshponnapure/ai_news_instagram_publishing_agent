"""ig_image.py — image selection, downloading, and library management for the Instagram pipeline."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .ig_constants import (
    IMAGE_LIBRARY_DIR,
    IMAGE_INDEX_PATH,
    IMAGE_MIN_HD_W,
    IMAGE_MIN_HD_H,
    REFERENCE_IMAGE_DIR,
    REFERENCE_BRANDS,
    STOP_IMAGE_TOKENS,
)
from .ig_utils import _source_label_from_url, _tighten


# ─────────────────────────────────────────────────────────────────────────────
# Image quality validation
# ─────────────────────────────────────────────────────────────────────────────

def _validate_image_hd(path: str) -> bool:
    """Return True when the image at `path` meets the minimum HD resolution."""
    if not path:
        return False
    try:
        from PIL import Image as _PIL
        img = _PIL.open(path)
        w, h = img.size
        return w >= IMAGE_MIN_HD_W and h >= IMAGE_MIN_HD_H
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Primary selection entry points
# ─────────────────────────────────────────────────────────────────────────────

def _select_article_image(article: dict[str, Any], topic: str) -> str:
    """Smart image selection pipeline (no deduplication guard)."""
    return _select_unique_article_image(article, topic, set(), set())


def _select_unique_article_image(
    article: dict[str, Any],
    topic: str,
    used_image_urls: set[str],
    used_image_paths: set[str],
) -> str:
    """Deduplicated image selection pipeline.

    Priority order:
    1. Article's own featured/hero image (og:image fetch — highest relevance)
    2. Shared image library — best semantic match not yet used
    3. Wikimedia Commons web search — unique fresh download
    4. Return empty string (slide layer generates an AI illustration)
    """
    title = str(article.get("title") or "")
    query_text = _tighten(_image_query_text(article, topic), 1200)

    # ── 0. Scrape og:image directly from the article URL ─────────────────────
    article_url = str(article.get("url") or "")
    if article_url and not article.get("image_url") and not article.get("image_path"):
        scraped_url = _fetch_og_image_from_url(article_url)
        if scraped_url and scraped_url not in used_image_urls:
            local = _download_to_library(scraped_url, query_text or title or topic)
            if local and local not in used_image_paths:
                used_image_urls.add(scraped_url)
                used_image_paths.add(local)
                article["image_url"] = scraped_url
                article["image_path"] = local
                return local

    # ── 1. Blog/article image (pre-populated by summariser) ──────────────────
    for key in ("image_path", "image_url"):
        value = str(article.get(key, "") or "").strip()
        if not value:
            continue
        if value.startswith(("http://", "https://")):
            if value in used_image_urls:
                continue
            local = _download_to_library(value, query_text or title or topic)
            if local and local not in used_image_paths:
                used_image_urls.add(value)
                used_image_paths.add(local)
                return local
        else:
            path = Path(value)
            if path.exists() and value not in used_image_paths:
                if _validate_image_hd(value):
                    used_image_paths.add(value)
                    return value

    # ── 1b. Non-HD local fallback ─────────────────────────────────────────────
    for key in ("image_path",):
        value = str(article.get(key, "") or "").strip()
        if not value:
            continue
        path = Path(value)
        if path.exists() and value not in used_image_paths:
            used_image_paths.add(value)
            return value

    # ── 2. Shared image library — deduplicated semantic match ─────────────────
    library_match = _find_library_image_unique(query_text or title or topic, used_image_paths)
    if library_match:
        used_image_paths.add(library_match)
        return library_match

    # ── 3. Web image search — fresh download ──────────────────────────────────
    web_image = _find_reference_image_for_article_unique(article, topic, used_image_paths)
    if web_image:
        used_image_paths.add(web_image)
        return web_image

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# og:image scraping
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_og_image_from_url(article_url: str) -> str:
    """Scrape the article page and return the best image URL found."""
    if not article_url or not article_url.startswith(("http://", "https://")):
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0; +https://graitech.ai)",
        "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    raw_html = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(article_url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw_html = resp.read(500_000).decode("utf-8", errors="replace")
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
                continue
            print(f"  [img] _fetch_og_image_from_url failed for {article_url[:80]}: {exc}")

    if not raw_html:
        return ""

    import re
    # 1. og:image
    og = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not og:
        og = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*>',
            raw_html, re.I,
        )
    if og:
        img_url = og.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            print(f"  [img] Found og:image for {article_url[:60]}: ...{img_url[-50:]}")
            return img_url

    # 2. twitter:image
    tw = re.search(
        r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not tw:
        tw = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']twitter:image["\'][^>]*>',
            raw_html, re.I,
        )
    if tw:
        img_url = tw.group(1).strip()
        if img_url.startswith(("http://", "https://")):
            print(f"  [img] Found twitter:image for {article_url[:60]}: ...{img_url[-50:]}")
            return img_url

    # 3. First substantive <img> in article/main content area
    content_block = re.search(r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>', raw_html, re.I | re.S)
    search_zone = content_block.group(1) if content_block else raw_html
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', search_zone, re.I):
        src = img_match.group(1).strip()
        if (
            src.startswith(("http://", "https://"))
            and any(ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp"))
            and not any(skip in src.lower() for skip in ("logo", "icon", "avatar", "pixel", "tracking", "badge", "1x1", "spacer"))
        ):
            print(f"  [img] Found <img> tag in article body for {article_url[:60]}: ...{src[-50:]}")
            return src

    print(f"  [img] No image found in {article_url[:60]}")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Image library management
# ─────────────────────────────────────────────────────────────────────────────

def _download_to_library(url: str, seed_text: str) -> str | None:
    """Download an image URL to the shared data/images library and return the local path."""
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        cached = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
        if cached.exists():
            return str(cached)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AIInstagramAgent/1.0)",
            "Referer": url,
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower().strip()
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type, ".jpg")
            data = resp.read(8_000_000)
    except Exception:
        return None
    if len(data) < 8_000:
        return None
    dest = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
    dest.write_bytes(data)
    meta_data = {
        "url": url,
        "seed": seed_text,
        "path": str(dest),
        "tokens": sorted(_important_image_tokens(seed_text)),
        "topic": _image_topic_signature(seed_text),
    }
    meta = IMAGE_LIBRARY_DIR / f"{cache_key}.json"
    meta.write_text(json.dumps(meta_data, ensure_ascii=True), encoding="utf-8")
    _upsert_image_index(cache_key, meta_data)
    return str(dest)


def _find_library_image(query: str) -> str | None:
    """Search the data/images library for an image relevant to the query."""
    if not IMAGE_LIBRARY_DIR.exists():
        return None
    query_tokens = _important_image_tokens(query)
    if not query_tokens:
        return None
    query_brand = _brand_tokens(query)
    query_signature = _image_topic_signature(query)
    best_path: str | None = None
    best_score = 0.0
    for image_id, meta in _iter_image_metadata():
        seed = str(meta.get("seed", ""))
        meta_tokens = set(meta.get("tokens") or []) or _important_image_tokens(seed)
        overlap = query_tokens & meta_tokens
        score = len(overlap) / max(4, len(query_tokens)) if overlap else 0.0
        if query_brand:
            score += 0.25 * len(query_brand & meta_tokens)
        if query_signature and query_signature == _image_topic_signature(seed):
            score += 0.18
        if any(token in seed.lower() for token in query_tokens):
            score += 0.10
        if any(token in overlap for token in query_brand):
            score += 0.20
        if score <= best_score:
            continue
        candidate = _image_path_from_metadata(image_id, meta)
        if candidate:
            best_score = score
            best_path = str(candidate)
    return best_path if best_score >= 0.45 else None


def _find_library_image_unique(query: str, exclude_paths: set[str]) -> str | None:
    """Like _find_library_image but skips any path already in exclude_paths."""
    if not IMAGE_LIBRARY_DIR.exists():
        return None
    query_tokens = _important_image_tokens(query)
    if not query_tokens:
        return None
    query_brand = _brand_tokens(query)
    query_signature = _image_topic_signature(query)
    best_path: str | None = None
    best_score = 0.0
    for image_id, meta in _iter_image_metadata():
        candidate = _image_path_from_metadata(image_id, meta)
        if not candidate:
            continue
        candidate_str = str(candidate)
        if candidate_str in exclude_paths:
            continue
        seed = str(meta.get("seed", ""))
        meta_tokens = set(meta.get("tokens") or []) or _important_image_tokens(seed)
        overlap = query_tokens & meta_tokens
        score = len(overlap) / max(4, len(query_tokens)) if overlap else 0.0
        if query_brand:
            score += 0.25 * len(query_brand & meta_tokens)
        if query_signature and query_signature == _image_topic_signature(seed):
            score += 0.18
        if any(token in seed.lower() for token in query_tokens):
            score += 0.10
        if any(token in overlap for token in query_brand):
            score += 0.20
        if score > best_score:
            best_score = score
            best_path = candidate_str
    return best_path if best_score >= 0.45 else None


def _iter_image_metadata() -> list[tuple[str, dict[str, Any]]]:
    items: dict[str, dict[str, Any]] = {}
    try:
        data = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
        for item in data.get("images", []):
            image_id = str(item.get("id") or "")
            if image_id:
                items[image_id] = item
    except Exception:
        pass
    for meta_file in IMAGE_LIBRARY_DIR.glob("*.json"):
        if meta_file.name == IMAGE_INDEX_PATH.name:
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta.setdefault("id", meta_file.stem)
        items[meta_file.stem] = meta
    return sorted(items.items())


def _upsert_image_index(image_id: str, meta: dict[str, Any]) -> None:
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {"images": []}
    try:
        data = json.loads(IMAGE_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    images = [item for item in data.get("images", []) if item.get("id") != image_id]
    images.append({"id": image_id, **meta})
    IMAGE_INDEX_PATH.write_text(json.dumps({"images": images}, ensure_ascii=True, indent=2), encoding="utf-8")


def _image_path_from_metadata(image_id: str, meta: dict[str, Any]) -> Path | None:
    raw_path = str(meta.get("path") or "")
    if raw_path:
        path = Path(raw_path)
        if path.exists():
            return path
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = IMAGE_LIBRARY_DIR / f"{image_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Token utilities
# ─────────────────────────────────────────────────────────────────────────────

def _important_image_tokens(text: str) -> set[str]:
    import re
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in STOP_IMAGE_TOKENS
    }


def _brand_tokens(text: str) -> set[str]:
    lowered = (text or "").lower()
    return {
        token
        for brand in REFERENCE_BRANDS
        if brand.lower() in lowered
        for token in _important_image_tokens(brand)
    }


def _image_topic_signature(text: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in _important_image_tokens(text)
        if token not in {"latest", "update", "article", "story", "image"}
    ]
    return tuple(sorted(tokens)[:5])


def _image_query_text(article: dict[str, Any], topic: str) -> str:
    return " ".join(
        str(part or "")
        for part in (
            article.get("title"),
            article.get("description"),
            article.get("summary"),
            article.get("excerpt"),
            " ".join(article.get("key_points", [])[:6]) if isinstance(article.get("key_points"), list) else "",
            topic,
            _source_label_from_url(str(article.get("url") or "")),
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Remote download helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_image_source(image_path: str) -> Path | None:
    value = str(image_path or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return _download_remote_image(value)
    path = Path(value)
    if path.exists():
        return path
    return None


def _download_remote_image(url: str) -> Path | None:
    try:
        tmp_dir = Path(tempfile.gettempdir()) / "ai_news_instagram"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg"
        dest = tmp_dir / f"img_{abs(hash(url))}{suffix}"
        _download_url(url, dest)
        return dest
    except Exception:
        return None


def _download_url(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        dest.write_bytes(response.read())


# ─────────────────────────────────────────────────────────────────────────────
# Wikimedia / reference image search
# ─────────────────────────────────────────────────────────────────────────────

def _find_reference_image_for_article(article: dict[str, Any], topic: str) -> str | None:
    for query in _reference_image_queries(article, topic):
        cache_key = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            cached = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
            if cached.exists():
                return str(cached)
        image_url = _search_wikimedia_image(query)
        if image_url:
            downloaded = _download_reference_image(image_url, cache_key, query)
            if downloaded:
                return downloaded
    return None


def _find_reference_image_for_article_unique(
    article: dict[str, Any], topic: str, exclude_paths: set[str]
) -> str | None:
    """Like _find_reference_image_for_article but skips already-used images."""
    for query in _reference_image_queries(article, topic):
        cache_key = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            cached = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
            if cached.exists() and str(cached) not in exclude_paths:
                return str(cached)
        image_url = _search_wikimedia_image(query)
        if image_url:
            downloaded = _download_reference_image(image_url, cache_key, query)
            if downloaded and downloaded not in exclude_paths:
                return downloaded
    return None


def _reference_image_queries(article: dict[str, Any], topic: str) -> list[str]:
    import re
    title = _strip_decorative_symbols_local(str(article.get("title") or "")).strip()
    description = _strip_decorative_symbols_local(
        str(article.get("description") or article.get("summary") or article.get("excerpt") or "")
    ).strip()
    source = _source_label_from_url(str(article.get("url") or ""))
    raw_candidates = [
        title, description,
        *_brand_queries(title),
        *_brand_queries(description),
        source, topic,
        "artificial intelligence" if "ai" in f"{title} {topic}".lower() else "",
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        query = re.sub(r"\b(update|launch|announces|announced|new|latest|story|research|hub|plans)\b", " ", raw, flags=re.I)
        query = re.sub(r"[^A-Za-z0-9 .&+-]+", " ", query)
        query = re.sub(r"\s+", " ", query).strip()
        query = _tighten(query, 120)
        key = query.lower()
        if len(query) >= 3 and key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def _strip_decorative_symbols_local(text: str) -> str:
    import unicodedata as _ud
    import re
    cleaned = [c for c in (text or "") if _ud.category(c) != "So"]
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def _brand_queries(text: str) -> list[str]:
    lowered = text.lower()
    return [brand for brand in REFERENCE_BRANDS if brand.lower() in lowered]


def _search_wikimedia_image(query: str) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrlimit": "10",
        "gsrsearch": query,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "AIInstagramNewsAgent/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        title = str(page.get("title") or "").lower()
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "").lower()
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        image_url = str(info.get("url") or "")
        if not image_url:
            continue
        if not _image_result_matches_query(query, title, image_url):
            continue
        if mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if width < 1280 or height < 720:
            continue
        if any(term in title for term in ("logo", "icon", "symbol", "seal", "flag")) and not _query_looks_like_company(query):
            continue
        return image_url
    return None


def _image_result_matches_query(query: str, title: str, image_url: str) -> bool:
    haystack = f"{title} {urllib.parse.unquote(image_url).lower()}"
    tokens = _important_query_tokens(query)
    if not tokens:
        return False
    return any(token in haystack for token in tokens)


def _important_query_tokens(query: str) -> list[str]:
    import re
    blocked = {
        "the", "and", "for", "with", "from", "that", "this",
        "news", "model", "models", "release", "support", "endpoint",
        "endpoints", "technology",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", query.lower())
    return [token for token in tokens if token not in blocked and len(token) >= 4]


def _download_reference_image(image_url: str, cache_key: str, seed_text: str = "") -> str | None:
    try:
        request = urllib.request.Request(image_url, headers={"User-Agent": "AIInstagramNewsAgent/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(content_type)
            if not suffix:
                return None
            data = response.read(5_000_000)
    except Exception:
        return None
    if len(data) < 20_000:
        return None
    REFERENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = REFERENCE_IMAGE_DIR / f"{cache_key}{suffix}"
    dest.write_bytes(data)
    lib_dest = IMAGE_LIBRARY_DIR / f"{cache_key}{suffix}"
    if not lib_dest.exists():
        lib_dest.write_bytes(data)
    meta_data = {
        "url": image_url,
        "seed": seed_text or image_url,
        "path": str(lib_dest),
        "tokens": sorted(_important_image_tokens(seed_text or image_url)),
    }
    (IMAGE_LIBRARY_DIR / f"{cache_key}.json").write_text(json.dumps(meta_data, ensure_ascii=True), encoding="utf-8")
    _upsert_image_index(cache_key, meta_data)
    return str(dest)


def _query_looks_like_company(query: str) -> bool:
    lowered = query.lower()
    return any(
        company.lower() in lowered
        for company in ("openai", "google", "microsoft", "meta", "amazon", "aws", "nvidia", "anthropic")
    )
