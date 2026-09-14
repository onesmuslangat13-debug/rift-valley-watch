from pathlib import Path
import html
import json
import re
import shutil
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V8_STABLE_REAL_ARTICLE_PHOTOS
#
# PURPOSE
# - Fetch fresh Rift Valley news
# - Prioritize current/recent stories
# - Cover Rift Valley counties
# - Reject Gachagua-focused stories
# - Reject Citizen/CTV material
# - Download REAL article photographs
# - Reject Google/Bing/search-result screenshots
# - Convert downloaded images to genuine JPEG files
# - Produce data/story.json
# - Produce data/script.json
# - Keep multiple genuine article photographs per story
# - Remain compatible with rift_valley_main.py V36
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_JSON = DATA_DIR / "story.json"
SCRIPT_JSON = DATA_DIR / "script.json"

MAX_STORIES = 8
MAX_IMAGES_PER_STORY = 6

MIN_IMAGE_BYTES = 5000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/png,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# COUNTIES
# ============================================================

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
    "Trans Nzoia",
    "Samburu",
    "Turkana",
    "Laikipia",
    "Kajiado",
]

COUNTY_ALIASES = {
    "uasin gishu": "Uasin Gishu",
    "uasin-gishu": "Uasin Gishu",
    "elgeyo marakwet": "Elgeyo-Marakwet",
    "elgeyo-marakwet": "Elgeyo-Marakwet",
    "west pokot": "West Pokot",
    "trans nzoia": "Trans Nzoia",
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    "Rift Valley Kenya latest news",
    "Bomet latest news Kenya",
    "Kericho latest news Kenya",
    "Nakuru latest news Kenya",
    "Nandi latest news Kenya",
    "Uasin Gishu latest news Kenya",
    "Elgeyo Marakwet latest news Kenya",
    "West Pokot latest news Kenya",
    "Narok latest news Kenya",
    "Trans Nzoia latest news Kenya",
    "Samburu latest news Kenya",
    "Turkana latest news Kenya",
    "Laikipia latest news Kenya",
    "Kajiado latest news Kenya",
    "Rift Valley Kenya politics latest",
    "Rift Valley Kenya development latest",
    "Rift Valley Kenya government latest",
    "Rift Valley Kenya economy latest",
    "Rift Valley Kenya education latest",
    "Rift Valley Kenya health latest",
    "Rift Valley Kenya security latest",
]


# ============================================================
# TRUSTED SOURCES
# ============================================================

SOURCE_SCORES = {
    "citizen.digital": 0,
    "citizentv.co.ke": 0,
    "the-star.co.ke": 8,
    "standardmedia.co.ke": 8,
    "nation.africa": 9,
    "peopledaily.digital": 8,
    "kbc.co.ke": 8,
    "capitalfm.co.ke": 7,
    "kenyans.co.ke": 7,
    "tuko.co.ke": 6,
    "kenyamoja.com": 5,
    "businessdailyafrica.com": 8,
    "capitalfm.co.ke": 7,
}


# ============================================================
# FORBIDDEN CONTENT
# ============================================================

FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "gachagua",
]

FORBIDDEN_SOURCE_TERMS = [
    "citizen.digital",
    "citizentv.co.ke",
    "citizen tv",
    "citizen digital",
    "ctv",
]

FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizentv",
    "citizen-digital",
    "ctv",
    "worldcup",
    "world-cup",
    "world_cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "profile-picture",
    "profile_picture",
    "generic-avatar",
    "generic_avatar",
    "dummy-image",
    "dummy_image",
    "no-image",
    "no_image",
    "missing-image",
    "missing_image",
    "search-result",
    "search_results",
    "search-results",
    "serp",
    "gstatic",
    "googleusercontent",
    "google-news",
    "bing",
    "yandex",
]


# ============================================================
# SEARCH ENGINE DOMAINS
# ============================================================

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "www.google.com",
    "google.co.ke",
    "www.google.co.ke",
    "news.google.com",
    "images.google.com",
    "googleusercontent.com",
    "www.googleusercontent.com",
    "gstatic.com",
    "www.gstatic.com",
    "bing.com",
    "www.bing.com",
    "bing.net",
    "search.yahoo.com",
    "images.search.yahoo.com",
    "yandex.com",
    "yandex.ru",
    "duckduckgo.com",
}


# ============================================================
# HELPERS
# ============================================================

def log(message):
    print(message, flush=True)


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def clean_old_images():
    """
    Remove images produced by previous news-engine runs.

    This deliberately removes all common raster formats so stale
    Google screenshots or old images cannot be recovered later.
    """
    extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".bmp",
        ".tif",
        ".tiff",
    }

    removed = 0

    for path in SOURCE_DIR.rglob("*"):
        if not path.is_file():
            continue

        if path.name.endswith(".download"):
            try:
                path.unlink()
                removed += 1
            except Exception:
                pass
            continue

        if path.suffix.lower() in extensions:
            try:
                path.unlink()
                removed += 1
            except Exception:
                pass

    log(f"Removed {removed} old source image files.")


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )


def normalize_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def clean_html_text(value):
    if not value:
        return ""

    value = html.unescape(value)

    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(r"<[^>]+>", " ", value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def domain_of(url):
    try:
        host = urlparse(url).netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_search_engine_domain(url):
    host = domain_of(url)

    if not host:
        return True

    for domain in SEARCH_ENGINE_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True

    return False


def forbidden_text(text):
    value = normalize_text(text).lower()

    return any(term in value for term in FORBIDDEN_STORY_TERMS)


def forbidden_source(url_or_source):
    value = normalize_text(url_or_source).lower()

    return any(term in value for term in FORBIDDEN_SOURCE_TERMS)


def forbidden_image_url(url):
    if not url:
        return True

    value = html.unescape(str(url)).strip()

    if not value:
        return True

    lowered = value.lower()

    if lowered.startswith("data:"):
        return True

    if lowered.startswith("blob:"):
        return True

    if is_search_engine_domain(value):
        return True

    parsed = urlparse(value)

    host = parsed.netloc.lower()

    path_query = (
        unquote(parsed.path)
        + " "
        + unquote(parsed.query)
    ).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    obvious_search_patterns = [
        "/search",
        "/imghp",
        "/images/search",
        "tbm=isch",
        "udm=2",
        "search?q=",
        "search?query=",
        "q=google",
        "q=bing",
        "/search?",
        "serp",
        "search-results",
        "search_result",
        "image-search",
        "image_search",
    ]

    for pattern in obvious_search_patterns:
        if pattern in path_query:
            return True

    if "google" in host:
        return True

    if "gstatic" in host:
        return True

    if "bing" in host:
        return True

    if "yandex" in host:
        return True

    return False


def looks_like_image_url(url):
    if not url:
        return False

    lowered = url.lower()

    if forbidden_image_url(url):
        return False

    parsed = urlparse(url)

    path = parsed.path.lower()

    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    )

    if path.endswith(image_extensions):
        return True

    image_words = [
        "/image/",
        "/images/",
        "/img/",
        "/photo/",
        "/photos/",
        "/media/",
        "/uploads/",
        "/upload/",
        "/wp-content/",
        "/featured/",
        "/stories/",
    ]

    return any(word in lowered for word in image_words)


def absolute_url(url, base_url):
    if not url:
        return ""

    url = html.unescape(str(url)).strip()

   
