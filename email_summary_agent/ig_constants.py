"""ig_constants.py — graitech Instagram pipeline: all constants, tokens, and theme palettes.

This module is import-free of other ig_* modules so it can be imported by any of them
without triggering circular imports.
"""
from __future__ import annotations

from pathlib import Path

# ── Canvas dimensions ─────────────────────────────────────────────────────────
CANVAS_W = 1080
CANVAS_H = 1350

# Instagram API allows 2-10 children per carousel post.
CHROME_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_INSTAGRAM_CAROUSEL_SLIDES = 10
MAX_ARTICLES_PER_POST = 8
MAX_CAROUSEL_SLIDES = MAX_ARTICLES_PER_POST

# Articles per carousel post for both digest and normal emails.
STORIES_PER_CAROUSEL = 1

# Maximum key points shown on a single article slide before overflow.
MAX_KP_PER_SLIDE = 4

# Hard minimum readable font size — never go below this on any slide.
FONT_MIN_READABLE = 32

POSTING_SLOTS = ("08:00", "14:00", "18:00", "22:00")

# ── Directory paths ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
GRAITECH_LOGO_PATH = ASSETS_DIR / "graitech-logo.png"
WATERMARK_CANDIDATES = [
    PROJECT_ROOT / "GR watermark.png",
    PROJECT_ROOT / "GR Watermark.png",
    PROJECT_ROOT / "GR watermark.svg",
]
FINAL_LOGO_CANDIDATES = [
    PROJECT_ROOT / "GR INSTA LOGO.png",
    PROJECT_ROOT / "GRInstaLogo.png",
    PROJECT_ROOT / "GR INSTA LOGO.svg",
]
ARTICLE_ASSET_DIR = PROJECT_ROOT / "data" / "article_assets"
REFERENCE_IMAGE_DIR = ARTICLE_ASSET_DIR / "reference_images"
IMAGE_LIBRARY_DIR = PROJECT_ROOT / "data" / "images"
IMAGE_INDEX_PATH = IMAGE_LIBRARY_DIR / "index.json"

# ── Brand names used for semantic image search ────────────────────────────────
REFERENCE_BRANDS = (
    "OpenAI", "Google", "DeepMind", "Anthropic", "Microsoft", "Meta",
    "Amazon", "AWS", "NVIDIA", "Apple", "LangChain", "Mistral",
    "Perplexity", "Hugging Face", "Cohere", "Salesforce",
)

# ── graitech Design System color tokens ───────────────────────────────────────
ACCENT_GREEN = "#39FF14"
NEON_RGB = (57, 255, 20)
PAGE_BLACK = "#000000"
TEXT_WHITE = "#FFFFFF"
SOFT_WHITE = "#E8E8E8"
ASH_GRAY = "#A8A8A8"
GT_IRON = "#1E1E1E"
GT_CEMENT_2 = "#3A3A3A"

# ── Dynamic background theme palette ──────────────────────────────────────────
_BG_THEMES: dict[str, dict] = {
    "research": {
        "base": (6, 3, 22), "top": (18, 9, 52),
        "glow": (90, 50, 200), "pattern": "hex", "alpha": 14,
    },
    "tools": {
        "base": (3, 12, 26), "top": (8, 28, 52),
        "glow": (0, 145, 210), "pattern": "circuit", "alpha": 12,
    },
    "industry": {
        "base": (5, 6, 18), "top": (14, 20, 44),
        "glow": (165, 125, 10), "pattern": "lines", "alpha": 16,
    },
    "policy": {
        "base": (3, 20, 22), "top": (8, 40, 46),
        "glow": (20, 165, 150), "pattern": "cross", "alpha": 10,
    },
    "breaking": {
        "base": (22, 3, 3), "top": (46, 9, 9),
        "glow": (225, 55, 15), "pattern": "burst", "alpha": 12,
    },
    "health": {
        "base": (3, 20, 10), "top": (8, 44, 22),
        "glow": (18, 185, 75), "pattern": "cross", "alpha": 10,
    },
    "finance": {
        "base": (8, 12, 4), "top": (20, 26, 10),
        "glow": (148, 205, 72), "pattern": "grid", "alpha": 14,
    },
    "space": {
        "base": (2, 2, 20), "top": (6, 6, 44),
        "glow": (62, 62, 225), "pattern": "dots", "alpha": 18,
    },
    "default": {
        "base": (5, 6, 12), "top": (12, 15, 26),
        "glow": (85, 165, 42), "pattern": "grid", "alpha": 10,
    },
}

# ── Image quality thresholds ──────────────────────────────────────────────────
IMAGE_MIN_HD_W = 1920
IMAGE_MIN_HD_H = 1080

VIDEO_BLOCKED_TERMS = (
    "video", "videos", "reel", "reels", "clip", "clips",
    "short", "shorts",
)

NOISY_ENTITY_TERMS = (
    "releases", "introduces", "designed", "tracks", "posting",
    "angle", "primary", "entities",
)

NOISY_POINT_PREFIXES = (
    "tracks new ai launch activity",
    "best posting angle",
    "primary entities to watch",
    "likely content themes",
)

PUBLIC_BLOCKED_PHRASES = (
    "article 1 title:",
    "article title:",
    "use essential cookies",
    "essential cookies are necessary",
    "advertising partners",
    "show you ads",
    "cookie settings",
    "cookie preferences",
    "customize cookie",
    "accept all cookies",
    "reject all cookies",
    "you may review and change your choices",
    "cookie notice",
    "privacy policy",
    "terms of service",
    "build software better",
    "read every piece of feedback",
    "gitHub is where people build software".lower(),
    "more than 150 million people",
    "contribute to over 420 million projects",
    "get tips, technical guides, and best practices",
    "sign up for",
    "subscribe to",
    "select your cookie",
    "deactivated",
    "footer of this site",
    "read our cookie",
    "how we use them",
    "manage your preferences",
    "opt out",
    "gdpr",
    "ccpa",
    "data protection",
    "third-party cookies",
    "tracking cookies",
    "functional cookies",
    "performance cookies",
    "analytics cookies",
    "marketing cookies",
    "view in browser",
    "unsubscribe",
    "manage subscriptions",
    "email preferences",
    "you are receiving this",
    "sent to you because",
    "no longer wish to receive",
    "are you a robot",
    "prove you are human",
    "detected unusual activity",
    "unusual activity from your computer network",
    "to continue, please click the box",
    "please click the box below",
    "global markets news at your fingertips",
    "bloomberg.com subscription",
    "for inquiries related to this message",
    "contact our support team",
    "support team and provide",
    "please contact our support",
    "enable javascript",
    "access to this page has been denied",
    "checking your browser",
    "verify you are a human",
    "for more details, visit",
    "query met quiet",
    "silence shaped the next question",
    "ask with brighter care",
    "only blank but well lit space",
    "bring your best question",
    "lost page, still warm light",
    "soft signs lean toward the next path",
    "step in, make it yours",
)

STOP_IMAGE_TOKENS = frozenset({
    "about", "after", "article", "blog", "content", "cookie", "from",
    "image", "launch", "latest", "more", "news", "privacy", "release",
    "story", "summary", "technology", "this", "update", "with",
})
