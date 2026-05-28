"""perceptual_image.py — Pillow-only perceptual image hashing.

No ``imagehash`` / numpy dependency. Provides 64-bit average-hash (aHash) and
difference-hash (dHash) plus Hamming distance, so the pipeline can detect
visually duplicate images even when the URL/path differs.

A duplicate is declared when EITHER hash is within ``DUP_HAMMING`` bits of a
previously used image.
"""
from __future__ import annotations

# Two near-identical images typically differ by <=6 bits on a 64-bit hash.
DUP_HAMMING = 6


def _load_gray(path: str, size: tuple[int, int]):
    from PIL import Image

    with Image.open(path) as img:
        return img.convert("L").resize(size, Image.LANCZOS)


def average_hash(path: str) -> int | None:
    """64-bit average hash (8x8). Returns None if the image can't be read."""
    try:
        small = _load_gray(path, (8, 8))
    except Exception:
        return None
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, px in enumerate(pixels):
        if px >= avg:
            bits |= 1 << i
    return bits


def difference_hash(path: str) -> int | None:
    """64-bit difference hash (9x8 -> 8x8 horizontal gradient)."""
    try:
        small = _load_gray(path, (9, 8))
    except Exception:
        return None
    pixels = list(small.getdata())
    bits = 0
    idx = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            if left > right:
                bits |= 1 << idx
            idx += 1
    return bits


def hashes_for(path: str) -> tuple[int | None, int | None]:
    """Return (ahash, dhash) for an image path."""
    return average_hash(path), difference_hash(path)


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count("1")


_FULL64 = (1 << 64) - 1


def _degenerate(value: int | None) -> bool:
    """A hash carrying no information (flat / solid image) — skip it for dedup."""
    return value is None or value == 0 or value == _FULL64


def is_duplicate(
    ahash: int | None,
    dhash: int | None,
    used: list[tuple[int | None, int | None]],
    *,
    max_hamming: int = DUP_HAMMING,
) -> bool:
    """True if (ahash, dhash) is within ``max_hamming`` of any used pair.

    Degenerate (all-zero / all-one) hashes from flat images are ignored so two
    unrelated low-detail images aren't wrongly treated as duplicates.
    """
    for used_a, used_d in used:
        if not _degenerate(ahash) and not _degenerate(used_a) and hamming(ahash, used_a) <= max_hamming:
            return True
        if not _degenerate(dhash) and not _degenerate(used_d) and hamming(dhash, used_d) <= max_hamming:
            return True
    return False


def hex_hash(value: int | None) -> str:
    return f"{value:016x}" if value is not None else ""


def from_hex(value: str) -> int | None:
    try:
        return int(value, 16) if value else None
    except ValueError:
        return None


def image_dimensions(path: str) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def looks_text_heavy(path: str, *, extreme_fraction: float = 0.82) -> bool:
    """Heuristic: detect screenshot/text-dominated images (poor as a slide photo).

    Screenshots and text pages have most pixels at the extremes (near-black text
    on near-white background); photographs spread across the tonal range. Returns
    True only when an overwhelming fraction of pixels are extreme. Fails open
    (returns False) when the image can't be read.
    """
    try:
        small = _load_gray(path, (32, 32))
    except Exception:
        return False
    pixels = list(small.getdata())
    if not pixels:
        return False
    extreme = sum(1 for px in pixels if px < 24 or px > 232)
    return (extreme / len(pixels)) >= extreme_fraction
