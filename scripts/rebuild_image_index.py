"""rebuild_image_index.py — Scan data/images/ and rebuild index.json.

Includes all 52 existing library images (with metadata) plus the 50 orphan
gen_* images that were never indexed. For orphan images we generate minimal
metadata from PIL dimensions, file size, and filename heuristics.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Add project root so we can import ig_image / ig_constants
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from email_summary_agent.ig_constants import (
    IMAGE_LIBRARY_DIR,
    IMAGE_INDEX_PATH,
    STOP_IMAGE_TOKENS,
    REFERENCE_BRANDS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Token extraction helpers  (mirrored from ig_image.py to keep script standalone)
# ─────────────────────────────────────────────────────────────────────────────

def _important_image_tokens(text: str) -> set[str]:
    """Extract meaningful image-search tokens from text."""
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", (text or "").lower())
        if token not in STOP_IMAGE_TOKENS
    }


def _image_topic_signature(text: str) -> tuple[str, ...]:
    tokens = [
        token
        for token in _important_image_tokens(text)
        if token not in {"latest", "update", "article", "story", "image"}
    ]
    return tuple(sorted(tokens)[:5])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

BRAND_NAMES = [b.lower() for b in REFERENCE_BRANDS]

# Tokens we can assign to gen_* images based on size/Dim categories
SIZE_CLASS_TOKENS: dict[str, set[str]] = {
    "tiny": {"small", "thumbnail"},
    "small": {"small"},
    "medium": {"medium"},
    "large": {"large", "highres"},
    "xlarge": {"large", "highres", "ultrahd"},
}

def _size_class(size_kb: int) -> str:
    if size_kb < 30:
        return "tiny"
    elif size_kb < 100:
        return "small"
    elif size_kb < 500:
        return "medium"
    elif size_kb < 2000:
        return "large"
    return "xlarge"


# Broad AI/tech seed topics used as last-resort tokens for orphan gen_* images.
# These guarantee at least token-level overlap with almost any AI news article
# query ("openai", "gpt", "model", "launch", "ai" → "ai" matches).
_BROAD_AI_SEED_TOKENS = {
    "ai", "artificial", "intelligence", "technology", "machine", "learning",
    "deep", "neural", "network", "data", "science", "research",
    "innovation", "future", "digital", "computer",
}

def _generate_gen_tokens(filename: str, width: int, height: int, size_kb: int) -> list[str]:
    """Generate search tokens for an orphan gen_* image.

    The returned tokens include broad AI/tech terms so these images have
    a small-but-nonzero overlap chance with article queries, making them
    usable as a true last-resort fallback when no better image matches.
    """
    tokens: set[str] = set()

    # From filename — extract any meaningful parts
    name_stem = Path(filename).stem
    core = re.sub(r"^gen_", "", name_stem)
    if not re.match(r"^[0-9a-f]{10,}$", core):
        tokens.add(core)

    # Brand matches: check filename for known brands
    lowered = filename.lower()
    for brand in BRAND_NAMES:
        if brand in lowered:
            tokens.add(brand)
            for word in brand.split():
                if len(word) >= 4:
                    tokens.add(word)

    # Size class
    tokens.update(SIZE_CLASS_TOKENS.get(_size_class(size_kb), set()))

    # HD quality
    if width >= 1920 and height >= 1080:
        tokens.add("hd")
        tokens.add("highres")
    elif width >= 1280 and height >= 720:
        tokens.add("hdready")

    # Generic AI/tech tokens (all ≥4 chars so _important_image_tokens picks them up)
    for token in _BROAD_AI_SEED_TOKENS:
        tokens.add(token)
    tokens.add("generated")
    tokens.add("illustration")

    return sorted(tokens)


def _get_image_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) using PIL, or (0, 0) on failure."""
    try:
        from PIL import Image as _PIL
        img = _PIL.open(path)
        return img.size
    except Exception:
        return (0, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def rebuild_index(dry_run: bool = False, verbose: bool = True) -> int:
    img_dir = IMAGE_LIBRARY_DIR
    if not img_dir.exists():
        print(f"ERROR: {img_dir} not found")
        return 1

    all_files = [f for f in os.listdir(img_dir) if os.path.isfile(img_dir / f)]

    # Separate image files, metadata .json files, and the index itself
    image_files: list[str] = []
    meta_files: dict[str, dict] = {}  # stem -> parsed json content
    for fname in sorted(all_files):
        if fname == "index.json" or fname == "index.json.backup":
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            image_files.append(fname)
        elif ext == ".json":
            try:
                meta = json.loads((img_dir / fname).read_text(encoding="utf-8"))
                meta_files[os.path.splitext(fname)[0]] = meta
            except Exception:
                pass

    # Group by stem
    images: dict[str, dict] = {}  # stem -> entry
    orphan_count = 0
    meta_count = 0

    for fname in image_files:
        stem = os.path.splitext(fname)[0]
        full_path = img_dir / fname
        size_kb = full_path.stat().st_size // 1024
        width, height = _get_image_dimensions(full_path)

        if stem in meta_files:
            # Already has metadata — use it
            meta = meta_files[stem]
            entry = {
                "id": meta.get("id", stem),
                "url": meta.get("url", ""),
                "seed": meta.get("seed", ""),
                "path": meta.get("path", str(full_path)),
                "tokens": meta.get("tokens", []),
                "topic": meta.get("topic"),
                "source": meta.get("source", "downloaded"),
            }
            # Ensure path is correct
            if not os.path.exists(entry["path"]):
                entry["path"] = str(full_path)
            images[stem] = entry
            meta_count += 1
            if verbose:
                print(f"  [meta] {fname:45s} {size_kb:5}KB  {width}x{height}")
        else:
            # Orphan — generate metadata
            tokens = _generate_gen_tokens(fname, width, height, size_kb)
            seed_text = f"generated image {width}x{height} {_size_class(size_kb)}"
            topic = _image_topic_signature(seed_text)
            entry = {
                "id": stem,
                "url": "",
                "seed": seed_text,
                "path": str(full_path),
                "tokens": tokens,
                "topic": topic,
                "source": "generated",
            }
            images[stem] = entry
            orphan_count += 1
            if verbose:
                token_str = ", ".join(tokens[:8])
                print(f"  [gen]  {fname:45s} {size_kb:5}KB  {width}x{height}  tokens=[{token_str}]")

    # Build the index list
    index_entries = []
    for stem in sorted(images.keys()):
        entry = images[stem]
        # Normalise entry: ensure all expected keys
        normalised = {
            "id": entry["id"],
            "url": entry.get("url", ""),
            "seed": entry.get("seed", ""),
            "path": entry.get("path", str(img_dir / f"{stem}.jpg")),
            "tokens": entry.get("tokens", []),
            "topic": entry.get("topic"),
            "source": entry.get("source", "unknown"),
        }
        index_entries.append(normalised)

    output = {"images": index_entries}

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — would write {len(index_entries)} entries to index.json")
        print(f"  Meta-based: {meta_count}")
        print(f"  Orphan gen_: {orphan_count}")
        print(f"  Total image files on disk: {len(image_files)}")
        print(f"  Total metadata files: {len(meta_files)}")
    else:
        IMAGE_INDEX_PATH.write_text(
            json.dumps(output, ensure_ascii=True, indent=2),
            encoding="utf-8"
        )
        print(f"\n{'='*60}")
        print(f"REBUILT index.json with {len(index_entries)} entries")
        print(f"  Meta-based: {meta_count}")
        print(f"  Orphan gen_: {orphan_count}")
        print(f"  Total image files on disk: {len(image_files)}")
        print(f"  Written to: {IMAGE_INDEX_PATH}")
        print(f"  Size: {IMAGE_INDEX_PATH.stat().st_size:,} bytes")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild data/images/index.json from all image files")
    parser.add_argument("--dry-run", action="store_true", help="Scan and report without writing")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress per-file output")
    args = parser.parse_args()
    sys.exit(rebuild_index(dry_run=args.dry_run, verbose=not args.quiet))
