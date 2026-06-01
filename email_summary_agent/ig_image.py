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
    CHROME_USER_AGENT,
    IMAGE_LIBRARY_DIR,
    IMAGE_INDEX_PATH,
    IMAGE_MIN_HD_W,
    IMAGE_MIN_HD_H,
    REFERENCE_IMAGE_DIR,
    REFERENCE_BRANDS,
    STOP_IMAGE_TOKENS,
)
from .http_utils import urlopen_with_cert_fallback
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


def _is_perceptual_dupe(path: str, used_image_hashes: list | None) -> bool:
    """True when ``path`` is a perceptual duplicate of an already-used image."""
    if not used_image_hashes or not path:
        return False
    try:
        from . import perceptual_image as pi

        ahash, dhash = pi.hashes_for(path)
        return pi.is_duplicate(ahash, dhash, used_image_hashes)
    except Exception:
        return False


def _register_hash(path: str, used_image_hashes: list | None) -> None:
    if used_image_hashes is None or not path:
        return
    try:
        from . import perceptual_image as pi

        used_image_hashes.append(pi.hashes_for(path))
    except Exception:
        pass


def _accept(path: str, used_image_paths: set[str], used_image_hashes: list | None) -> bool:
    """Accept a resolved local path unless it perceptually duplicates a used one."""
    if path in used_image_paths:
        return False
    if _is_perceptual_dupe(path, used_image_hashes):
        return False
    used_image_paths.add(path)
    _register_hash(path, used_image_hashes)
    return True


def _accept_article_image(path: str, used_image_paths: set[str], used_image_hashes: list | None) -> bool:
    """Register a same-article image without replacing it with cross-article fallback."""
    if path in used_image_paths:
        return False
    if _is_perceptual_dupe(path, used_image_hashes):
        return False
    used_image_paths.add(path)
    _register_hash(path, used_image_hashes)
    return True


def _select_unique_article_image(
    article: dict[str, Any],
    topic: str,
    used_image_urls: set[str],
    used_image_paths: set[str],
    used_image_hashes: list | None = None,
) -> str:
    """Select only an image extracted from the same article.

    Priority order:
    1. Article's own featured/hero image (og:image fetch — highest relevance)
    2. Shared image library — best semantic match not yet used
    3. Wikimedia Commons web search — unique fresh download

    When ``used_image_hashes`` is supplied, every resolved candidate is also
    checked for *perceptual* duplication (aHash/dHash) so the same picture is
    never reused even under a different URL/path.
    """
    title = str(article.get("title") or "")
    query_text = _tighten(_image_query_text(article, topic), 1200)

    article_url = str(article.get("url") or "")
    if article_url and not article.get("_og_scraped"):
        # Always attempt OG image extraction from the article URL,
        # even if cached image_url/image_path exists from a prior run.
        scraped_url = _fetch_og_image_from_url(article_url)
        if scraped_url:
            article["image_url"] = scraped_url
            article["image_path"] = ""  # invalidate cached fallback path
        article["_og_scraped"] = True

    for kind, value in _same_article_image_candidates(article):
        if kind == "url":
            local = _download_to_library(value, query_text or title or topic)
            if local and _accept_article_image(local, used_image_paths, used_image_hashes):
                used_image_urls.add(value)
                article["image_url"] = value
                article["image_path"] = local
                article["image_source"] = "article"
                return local
        else:
            path = Path(value)
            if path.exists() and _accept_article_image(value, used_image_paths, used_image_hashes):
                article["image_path"] = value
                article["image_source"] = "article"
                return value

    _log_image_failure(article, title, topic)
    return ""

    # ── Fallback 1: Shared image library (topic-matched, deduplicated) ──
    library_path = _find_library_image_unique(query_text, used_image_paths)
    if library_path:
        path = Path(library_path)
        if path.exists() and _accept_article_image(library_path, used_image_paths, used_image_hashes):
            article["image_path"] = library_path
            article["image_source"] = "fallback"
            print(f"  [img] Library fallback for {title[:40]!r}: {path.name}")
            return library_path

    # ── Fallback 2: Wikimedia Commons search for brand/query matches ──
    ref_path = _find_reference_image_for_article_unique(article, topic, used_image_paths)
    if ref_path:
        article["image_path"] = ref_path
        article["image_source"] = "fallback"
        print(f"  [img] Wikimedia fallback for {title[:40]!r}: {Path(ref_path).name}")
        return ref_path

    # ── Fallback 3 (last resort): Best-effort library match, any score ──
    last_resort = _find_library_image_unique(query_text, used_image_paths, min_score=0.0)
    if last_resort:
        path = Path(last_resort)
        if path.exists() and _accept_article_image(last_resort, used_image_paths, used_image_hashes):
            article["image_path"] = last_resort
            article["image_source"] = "fallback"
            print(f"  [img] BEST-EFFORT library fallback for {title[:40]!r}: {path.name}")
            return last_resort

    _log_image_failure(article, title, topic)
    return ""

def _log_image_failure(article: dict[str, Any], title: str, topic: str) -> None:
    """Log diagnostic details when no article-sourced image can be resolved."""
    article_url = str(article.get("url") or "")[:80]
    has_og = bool(article.get("image_url"))
    has_path = bool(article.get("image_path"))
    has_extra_urls = bool(article.get("extra_image_urls"))
    has_extra_paths = bool(article.get("extra_image_paths"))
    print(
        f"  [img] No article-sourced image for "
        f"title={title[:60]!r} url={article_url!r} "
        f"og_url={has_og} path={has_path} "
        f"extra_urls={has_extra_urls} extra_paths={has_extra_paths}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# og:image scraping
# ─────────────────────────────────────────────────────────────────────────────

# ── Bloomberg-specific user agents that bypass 403 ──
_BLOOMBERG_CRAWLER_AGENTS = [
    # Googlebot — the most reliable
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    # Twitterbot — allowed for link preview generation
    "Twitterbot/1.0",
    # Facebook crawler — allowed for link previews
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    # LinkedIn crawler
    "LinkedInBot/1.0 (compatible; Mozilla/5.0; +http://www.linkedin.com/robot.txt)",
]


def _is_bloomberg_url(url: str) -> bool:
    """True when the URL is a Bloomberg article or feature page."""
    if not url:
        return False
    lowered = url.lower()
    return "bloomberg.com" in lowered and (
        "/news/articles/" in lowered
        or "/news/features/" in lowered
        or "/news/newsletters/" in lowered
        or "/opinion/articles/" in lowered
        or "/graphics/" in lowered
    )


def _fetch_bloomberg_og_image(article_url: str) -> str:
    """Extract a hero image from a Bloomberg article using multiple strategies.

    Strategy flow:
    1. Crawler user-agents — try Googlebot, Twitterbot, Facebook, LinkedIn
       Allowed by Bloomberg for link preview generation.
       Parse __NEXT_DATA__ JSON from the response for image URLs.
    2. Google Cache — fetch from webcache.googleusercontent.com
    3. Slug-based CDN construction — last resort fallback

    Returns the absolute image URL, or empty string if all strategies fail.
    """
    if not article_url:
        return ""

    import json
    import re
    import urllib.parse

    def _extract_next_data_image(html: str) -> str | None:
        """Parse __NEXT_DATA__ <script> from Bloomberg page HTML and find image URLs."""
        # Strategy 1a: Parse __NEXT_DATA__ JSON
        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>',
            html, re.I | re.S,
        )
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None

        # Traverse the state tree looking for image URLs
        # Common paths in Bloomberg's state: props.pageProps, etc.
        def _walk(obj: Any, depth: int = 0) -> list[str]:
            """Recursively walk the JSON tree collecting image URLs."""
            results: list[str] = []
            if depth > 8:
                return results
            if isinstance(obj, dict):
                for key, val in obj.items():
                    key_lower = key.lower()
                    # Check image-related keys
                    if key_lower in ("image", "images", "lede", "ledeimage", "socialimage", "thumbnail", "hero", "photo"):
                        if isinstance(val, str) and val.startswith("http"):
                            results.append(val)
                        elif isinstance(val, dict):
                            # Nested image object with url/contentUrl keys
                            for sub_key in ("url", "contentUrl", "src", "srcset", "data-src"):
                                sub_val = val.get(sub_key)
                                if isinstance(sub_val, str) and sub_val.startswith("http"):
                                    results.append(sub_val)
                    # Recurse into dicts and lists
                    results.extend(_walk(val, depth + 1))
            elif isinstance(obj, list):
                for item in obj:
                    results.extend(_walk(item, depth + 1))
            return results

        found = _walk(data)
        # Filter for Bloomberg CDN URLs, prefer the largest version
        cdn_urls = [
            u for u in found
            if "assets.bwbx.io" in u and not any(term in u.lower() for term in ("logo", "icon", "favicon"))
        ]
        if cdn_urls:
            # Return the first high-quality CDN URL
            return cdn_urls[0]
        # Fallback to any found image URL
        for url in found:
            if url.startswith("http") and not any(
                term in url.lower() for term in ("logo", "icon", "favicon", "svg", "pixel", "tracking")
            ):
                return url
        return None

    def _extract_image_from_meta_or_json(html: str) -> str | None:
        """Extract image from open-graph meta tags or JSON-LD in Bloomberg HTML."""
        # og:image
        for p in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*>',
        ]:
            m = re.search(p, html, re.I)
            if m:
                url = m.group(1).strip()
                if url.startswith("http") and "assets.bwbx.io" in url:
                    return url
        # twitter:image
        for p in [
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\'][^>]*>',
        ]:
            m = re.search(p, html, re.I)
            if m:
                url = m.group(1).strip()
                if url.startswith("http") and "assets.bwbx.io" in url:
                    return url
        # JSON-LD structured data
        for jsm in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.I | re.S,
        ):
            try:
                ld = json.loads(jsm.group(1))
            except json.JSONDecodeError:
                continue
            items = ld if isinstance(ld, list) else [ld]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for img_field in ("image", "thumbnailUrl", "thumbnail", "primaryImageOfPage"):
                    val = item.get(img_field)
                    if isinstance(val, str) and val.startswith("http") and "assets.bwbx.io" in val:
                        return val
                    if isinstance(val, dict):
                        for sub_field in ("url", "contentUrl"):
                            sub = val.get(sub_field)
                            if isinstance(sub, str) and sub.startswith("http"):
                                return sub
        # link[rel=image_src]
        m = re.search(r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\'][^>]*>', html, re.I)
        if m:
            url = m.group(1).strip()
            if url.startswith("http"):
                return url
        return None

    def _try_google_cache(article_url: str) -> str | None:
        """Try fetching the article via Google Cache and extracting images."""
        import time
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{urllib.parse.quote(article_url)}&strip=1&vwsrc=0"
        try:
            req = urllib.request.Request(
                cache_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
            )
            with urlopen_with_cert_fallback(req, timeout=15) as resp:
                html = resp.read(500_000).decode("utf-8", errors="replace")
            # First try __NEXT_DATA__ from cache response
            result = _extract_next_data_image(html)
            if result:
                return result
            # Fallback to meta tags
            result = _extract_image_from_meta_or_json(html)
            if result:
                return result
        except Exception:
            pass
        return None

    # ── Strategy 1: Try each crawler user-agent ──
    for ua in _BLOOMBERG_CRAWLER_AGENTS:
        import time
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        raw_html = ""
        for attempt in range(2):
            try:
                req = urllib.request.Request(article_url, headers=headers)
                with urlopen_with_cert_fallback(req, timeout=20) as resp:
                    raw_html = resp.read(500_000).decode("utf-8", errors="replace")
                break
            except Exception:
                if attempt == 0:
                    time.sleep(2)
                    continue

        if not raw_html or len(raw_html) < 500:
            continue

        # Check if we got a real page (not a paywall/403)
        lower = raw_html.lower()
        if any(term in lower for term in ("are you a robot", "access to this page has been denied", "enable javascript", "checking your browser")):
            continue

        # Try extracting from __NEXT_DATA__ first (most reliable)
        result = _extract_next_data_image(raw_html)
        if result:
            print(f"  [img] Bloomberg: __NEXT_DATA__ extracted image via {ua.split('/')[0]} for {article_url[:60]}: ...{result[-50:]}")
            return result

        # Fallback to meta/JSON-LD extraction
        result = _extract_image_from_meta_or_json(raw_html)
        if result:
            print(f"  [img] Bloomberg: meta extracted image via {ua.split('/')[0]} for {article_url[:60]}: ...{result[-50:]}")
            return result

        # If first crawler succeeded in getting the page but found no image, continue to next
        # (Don't fall through to cache yet — try the next agent)

    # ── Strategy 2: Google Cache (last resort for crawler-blocked pages) ──
    result = _try_google_cache(article_url)
    if result:
        print(f"  [img] Bloomberg: Google Cache extraction for {article_url[:60]}: ...{result[-50:]}")
        return result

    print(f"  [img] Bloomberg: All strategies exhausted for {article_url[:60]}")
    return ""


def _is_low_value_image_candidate(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(
        term in lowered
        for term in (
            "logo", "icon", "avatar", "pixel", "tracking", "badge",
            "1x1", "spacer", "sprite", "placeholder", "transparent",
        )
    )


def _same_article_image_candidates(article: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(kind: str, value: Any) -> None:
        raw = str(value or "").strip()
        if not raw or raw in seen or _is_low_value_image_candidate(raw):
            return
        seen.add(raw)
        candidates.append((kind, raw))

    add("path", article.get("image_path"))
    add("url", article.get("image_url"))
    for value in article.get("extra_image_paths") or []:
        add("path", value)
    for value in article.get("extra_image_urls") or []:
        add("url", value)
    return candidates


def _fetch_og_image_from_url(article_url: str) -> str:
    """Scrape the article page and return the best image URL found.

    Uses a multi-strategy approach with 9 layers of fallbacks:
    1. og:image / og:image:secure_url
    2. twitter:image
    3. article:image / news:image
    4. link[rel=image_src]
    5. JSON-LD structured data (@graph, ImageObject, thumbnail)
    6. schema.org meta (itemprop=image)
    7. First large <figure> or <img> in <article>/<main>/content areas
    8. First <img> anywhere with large dimensions (width >= 400)
    9. First <img> anywhere as absolute last resort

    Handles relative URL resolution, low-value filters, and CDN patterns.
    """
    if not article_url or not article_url.startswith(("http://", "https://")):
        return ""
    
    from urllib.parse import urljoin
    
    headers = {
        "User-Agent": CHROME_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # ── Bloomberg bypass ──
    if _is_bloomberg_url(article_url):
        return _fetch_bloomberg_og_image(article_url)

    raw_html = ""
    for attempt in range(2):
        try:
            req = urllib.request.Request(article_url, headers=headers)
            with urlopen_with_cert_fallback(req, timeout=25) as resp:
                raw_html = resp.read(500_000).decode("utf-8", errors="replace")
            break
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
                continue
            print(f"  [img] _fetch_og_image_from_url failed for {article_url[:80]}: {exc}")

    if not raw_html:
        print(f"  [img] No HTML content fetched for {article_url[:60]}")
        return ""

    import re
    
    def _resolve(url: str) -> str:
        """Resolve a potentially relative URL against the article URL."""
        if not url:
            return ""
        url = url.strip()
        if url.startswith(("http://", "https://", "//")):
            if url.startswith("//"):
                return f"https:{url}"
            return url
        if url.startswith("/"):
            parsed = urllib.parse.urlparse(article_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        return urljoin(article_url, url)
    
    def _is_low_value(url: str) -> bool:
        lowered = url.lower()
        return any(
            term in lowered
            for term in (
                "logo", "icon", "avatar", "pixel", "tracking", "badge",
                "1x1", "spacer", "sprite", "placeholder", "transparent",
                "favicon", "analytics", "beacon", "clear.gif",
                "data:image", "svg+xml",
            )
        )
    
    def _has_img_ext(url: str) -> bool:
        return any(ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))
    
    found_urls: list[str] = []  # List of (priority, url) tuples
    
    # ── Strategy 1: og:image ──
    for pattern in [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\'][^>]*>',
        r'<meta[^>]+property=["\']og:image:secure_url["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
    ]:
        m = re.search(pattern, raw_html, re.I)
        if m:
            url = _resolve(m.group(1))
            if url and not _is_low_value(url):
                found_urls.append(url)
                print(f"  [img] Found og:image for {article_url[:60]}: ...{url[-50:]}")
                return url

    # ── Strategy 2: twitter:image ──
    for pattern in [
        r'<meta[^>]+(?:name|property)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']twitter:image["\'][^>]*>',
    ]:
        m = re.search(pattern, raw_html, re.I)
        if m:
            url = _resolve(m.group(1))
            if url and not _is_low_value(url):
                found_urls.append(url)
                print(f"  [img] Found twitter:image for {article_url[:60]}: ...{url[-50:]}")
                return url

    # ── Strategy 3: article:image / news:image ──
    for pattern in [
        r'<meta[^>]+property=["\']article:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:image["\'][^>]*>',
        r'<meta[^>]+property=["\']news:image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
    ]:
        m = re.search(pattern, raw_html, re.I)
        if m:
            url = _resolve(m.group(1))
            if url and not _is_low_value(url):
                found_urls.append(url)
                print(f"  [img] Found article:image for {article_url[:60]}: ...{url[-50:]}")
                return url

    # ── Strategy 4: link[rel=image_src] ──
    m = re.search(
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not m:
        m = re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']image_src["\'][^>]*>',
            raw_html, re.I,
        )
    if m:
        url = _resolve(m.group(1))
        if url and not _is_low_value(url):
            found_urls.append(url)
            print(f"  [img] Found image_src link for {article_url[:60]}: ...{url[-50:]}")
            return url

    # ── Strategy 5: JSON-LD structured data ──
    for jsm in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html, re.I | re.S,
    ):
        try:
            ld = json.loads(jsm.group(1))
        except json.JSONDecodeError:
            continue
        # Handle @graph
        items = ld.get("@graph", [ld]) if isinstance(ld, dict) else [ld]
        if isinstance(ld, list):
            items = ld
        for item in items:
            if not isinstance(item, dict):
                continue
            # Check various image fields
            for img_field in ("image", "thumbnailUrl", "thumbnail", "primaryImageOfPage"):
                val = item.get(img_field)
                if not val:
                    continue
                if isinstance(val, str):
                    url = _resolve(val)
                    if url and not _is_low_value(url) and _has_img_ext(url):
                        found_urls.append(url)
                        print(f"  [img] Found JSON-LD image for {article_url[:60]}: ...{url[-50:]}")
                        return url
                elif isinstance(val, dict):
                    for sub_field in ("url", "contentUrl", "content_url"):
                        sub = val.get(sub_field, "")
                        if sub:
                            url = _resolve(str(sub))
                            if url and not _is_low_value(url):
                                found_urls.append(url)
                                print(f"  [img] Found JSON-LD nested image for {article_url[:60]}: ...{url[-50:]}")
                                return url
    
    # ── Strategy 6: schema.org itemprop=image ──
    m = re.search(
        r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        raw_html, re.I,
    )
    if not m:
        m = re.search(
            r'<img[^>]+itemprop=["\']image["\'][^>]+src=["\']([^"\']+)["\'][^>]*>',
            raw_html, re.I,
        )
    if m:
        url = _resolve(m.group(1))
        if url and not _is_low_value(url):
            found_urls.append(url)
            print(f"  [img] Found itemprop=image for {article_url[:60]}: ...{url[-50:]}")
            return url

    # ── Strategy 7: First large <figure> / <img> in content areas ──
    content_block = re.search(r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>', raw_html, re.I | re.S)
    search_zone = content_block.group(1) if content_block else raw_html
    
    # Try <figure> first (often contains featured image)
    for fig_match in re.finditer(r'<figure[^>]*>.*?<img[^>]+src=["\']([^"\']+)["\'][^>]*>.*?</figure>', search_zone, re.I | re.S):
        src = fig_match.group(1).strip()
        url = _resolve(src)
        if url and not _is_low_value(url) and _has_img_ext(url):
            found_urls.append(url)
            print(f"  [img] Found <figure><img> for {article_url[:60]}: ...{url[-50:]}")
            return url
    
    # Then try standalone <img> with width >= 400 or large-enough looking
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', search_zone, re.I):
        src = img_match.group(1).strip()
        # Check for width attribute
        width_attr = re.search(r'width=["\']?(\d+)["\']?', img_match.group(0), re.I)
        img_width = int(width_attr.group(1)) if width_attr else 0
        url = _resolve(src)
        if not url or _is_low_value(url):
            continue
        if img_width >= 400 or (not width_attr and _has_img_ext(url)):
            found_urls.append(url)
            print(f"  [img] Found <img> in content for {article_url[:60]}: ...{url[-50:]}")
            return url

    # ── Strategy 8: Any <img> with width >= 400 anywhere in page ──
    for img_match in re.finditer(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', raw_html, re.I,
    ):
        src = img_match.group(1).strip()
        width_attr = re.search(r'width=["\']?(\d+)["\']?', img_match.group(0), re.I)
        img_width = int(width_attr.group(1)) if width_attr else 0
        url = _resolve(src)
        if url and not _is_low_value(url) and img_width >= 400 and _has_img_ext(url):
            found_urls.append(url)
            print(f"  [img] Found large <img> for {article_url[:60]}: ...{url[-50:]}")
            return url

    # ── Strategy 9: Absolute last resort - any <img> with image extension ──
    for img_match in re.finditer(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', raw_html, re.I,
    ):
        src = img_match.group(1).strip()
        url = _resolve(src)
        if url and not _is_low_value(url) and _has_img_ext(url):
            found_urls.append(url)
            print(f"  [img] Found last-resort <img> for {article_url[:60]}: ...{url[-50:]}")
            return url

    if found_urls:
        best = found_urls[0]
        print(f"  [img] Using best-effort image for {article_url[:60]}: ...{best[-50:]}")
        return best
        
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
            "User-Agent": CHROME_USER_AGENT,
            "Referer": url,
        }
        req = urllib.request.Request(url, headers=headers)
        with urlopen_with_cert_fallback(req, timeout=12) as resp:
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


def _find_library_image_unique(query: str, exclude_paths: set[str], min_score: float = 0.45) -> str | None:
    """Like _find_library_image but skips any path already in exclude_paths.

    ``min_score`` controls the minimum similarity threshold.
    Default 0.45 (high confidence). Pass 0.0 to accept any match as last resort.
    """
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
    return best_path if best_score >= min_score else None


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
    request = urllib.request.Request(url, headers={"User-Agent": CHROME_USER_AGENT})
    with urlopen_with_cert_fallback(request, timeout=8) as response:
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
        request = urllib.request.Request(url, headers={"User-Agent": CHROME_USER_AGENT})
        with urlopen_with_cert_fallback(request, timeout=10) as response:
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
        request = urllib.request.Request(image_url, headers={"User-Agent": CHROME_USER_AGENT})
        with urlopen_with_cert_fallback(request, timeout=12) as response:
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
