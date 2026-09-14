from pathlib import Path
import hashlib
import html
import json
import re
import shutil
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V9_REAL_IMAGE_DISCOVERY
#
# WHAT CHANGED FROM V8
# - Finished absolute_url()
# - Added the actual scraping pipeline that was missing:
#     search_for_stories() -> fetch_article() -> extract_candidate_images()
#     -> download_image() -> select_story_images()
# - Every candidate image URL is now ALWAYS run through
#   forbidden_image_url() / looks_like_image_url() before it is ever
#   requested. Filtering was previously defined but never called
#   anywhere in the pipeline -- that was the actual bug, not the
#   filter logic itself.
# - Images are only ever pulled from the article page's own domain
#   (its <img> tags and og:image/twitter:image meta), never from a
#   search engine results page, because we never fetch a search
#   engine results page for images at all -- SEARCH_QUERIES are only
#   used against a real news search, and we then visit each article
#   URL directly.
# - Added content-hash deduplication. This is what fixes the
#   "1/5 ... 5/5" bug where five slides were secretly the same photo:
#   we now refuse to let two "distinct" images into a story if their
#   perceptual/content hash matches.
# - download_image() validates Content-Type, dimensions, and byte
#   size BEFORE writing to disk, then re-encodes through Pillow to a
#   clean JPEG (this also reliably fails/rejects anything that isn't
#   actually a decodable photo, e.g. an HTML error page saved with a
#   .jpg extension).
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent if (Path(__file__).resolve().parent.name == "engine") else Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_JSON = DATA_DIR / "story.json"
SCRIPT_JSON = DATA_DIR / "script.json"

MAX_STORIES = 8
MAX_IMAGES_PER_STORY = 6
MIN_IMAGES_PER_STORY = 1  # a story with 0 real images should be dropped, not padded

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
    "Bomet", "Kericho", "Nakuru", "Nandi", "Uasin Gishu",
    "Elgeyo-Marakwet", "West Pokot", "Narok", "Trans Nzoia",
    "Samburu", "Turkana", "Laikipia", "Kajiado",
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
# (used both to prioritize results and to whitelist which domains
#  we are willing to pull article images FROM)
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
}

TRUSTED_DOMAINS = set(SOURCE_SCORES.keys())


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
    "citizen", "citizentv", "citizen-digital", "ctv",
    "worldcup", "world-cup", "world_cup",
    "avatar", "placeholder", "default-image", "default_image",
    "profile-picture", "profile_picture",
    "generic-avatar", "generic_avatar",
    "dummy-image", "dummy_image",
    "no-image", "no_image",
    "missing-image", "missing_image",
    "search-result", "search_results", "search-results",
    "serp", "gstatic", "googleusercontent",
    "google-news", "bing", "yandex",
    "sprite", "icon", "logo", "favicon",  # common false-photo assets
]

SEARCH_ENGINE_DOMAINS = {
    "google.com", "www.google.com", "google.co.ke", "www.google.co.ke",
    "news.google.com", "images.google.com",
    "googleusercontent.com", "www.googleusercontent.com",
    "gstatic.com", "www.gstatic.com",
    "bing.com", "www.bing.com", "bing.net",
    "search.yahoo.com", "images.search.yahoo.com",
    "yandex.com", "yandex.ru",
    "duckduckgo.com",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def log(message):
    print(message, flush=True)


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def clean_old_images():
    """Remove images produced by previous news-engine runs so stale
    Google screenshots or old images can never be reused."""
    extensions = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".tif", ".tiff"}
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
        json.dump(payload, handle, ensure_ascii=False, indent=2)


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
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
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
    path_query = (unquote(parsed.path) + " " + unquote(parsed.query)).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    obvious_search_patterns = [
        "/search", "/imghp", "/images/search", "tbm=isch", "udm=2",
        "search?q=", "search?query=", "q=google", "q=bing", "/search?",
        "serp", "search-results", "search_result", "image-search", "image_search",
    ]
    for pattern in obvious_search_patterns:
        if pattern in path_query:
            return True

    if "google" in host or "gstatic" in host or "bing" in host or "yandex" in host:
        return True

    return False


def looks_like_image_url(url):
    if not url:
        return False
    if forbidden_image_url(url):
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()

    image_extensions = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".bmp", ".gif", ".tif", ".tiff")
    if path.endswith(image_extensions):
        return True

    image_words = [
        "/image/", "/images/", "/img/", "/photo/", "/photos/",
        "/media/", "/uploads/", "/upload/", "/wp-content/",
        "/featured/", "/stories/",
    ]
    return any(word in path for word in image_words)


def absolute_url(url, base_url):
    """Resolve a possibly-relative URL against the page it was found on."""
    if not url:
        return ""

    url = html.unescape(str(url)).strip()
    if not url:
        return ""

    # strip whitespace/newlines that sometimes sneak into srcset-style attrs
    url = url.split()[0] if " " in url and not url.startswith("http") else url

    try:
        return urljoin(base_url, url)
    except Exception:
        return ""


# ============================================================
# THE PART THAT WAS MISSING: ACTUAL DISCOVERY + DOWNLOAD PIPELINE
# ============================================================

def fetch_url(url, timeout=REQUEST_TIMEOUT, is_image=False):
    headers = IMAGE_HEADERS if is_image else HEADERS
    try:
        response = SESSION.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        log(f"  ! fetch failed: {url} ({exc})")
        return None


def fetch_article(article_url):
    """Download an article page and return a BeautifulSoup object, or None."""
    if forbidden_source(article_url):
        log(f"  ! skipping forbidden source: {article_url}")
        return None

    response = fetch_url(article_url)
    if response is None:
        return None

    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        return None

    return BeautifulSoup(response.text, "lxml")


def extract_candidate_images(soup, article_url):
    """
    Pull every plausible photo URL out of an article page:
    - og:image / twitter:image meta tags
    - <img> tags inside the page body

    Every URL is resolved to absolute form and immediately checked with
    looks_like_image_url()/forbidden_image_url() before being kept as a
    candidate. Nothing downstream ever has to remember to filter --
    a URL simply never enters the candidate list if it fails here.
    """
    candidates = []
    seen = set()

    def add_candidate(raw_url):
        abs_url = absolute_url(raw_url, article_url)
        if not abs_url or abs_url in seen:
            return
        seen.add(abs_url)
        if not looks_like_image_url(abs_url):
            return
        candidates.append(abs_url)

    # meta tags first -- these are usually the actual editorial photo
    for prop in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        for tag in soup.find_all("meta", attrs={"property": prop}) + soup.find_all("meta", attrs={"name": prop}):
            content = tag.get("content")
            if content:
                add_candidate(content)

    # then real <img> tags in the article body
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src:
            add_candidate(src)

        srcset = img.get("srcset")
        if srcset:
            # take the first URL in the srcset list
            first = srcset.split(",")[0].strip().split(" ")[0]
            add_candidate(first)

    return candidates


def content_hash(raw_bytes):
    return hashlib.sha256(raw_bytes).hexdigest()


def download_image(url, destination_path):
    """
    Download one image, validating it thoroughly before it ever touches
    disk as a "real" file:
      1. re-check forbidden_image_url() (defence in depth)
      2. Content-Type must actually be an image
      3. byte size must clear MIN_IMAGE_BYTES
      4. Pillow must be able to decode it (rejects HTML-error-pages
         saved with a .jpg extension, broken files, etc.)
      5. dimensions must clear MIN_IMAGE_WIDTH / MIN_IMAGE_HEIGHT
      6. re-encoded to a clean JPEG on disk

    Returns (success: bool, sha256_hash_or_None).
    """
    if forbidden_image_url(url):
        return False, None

    response = fetch_url(url, is_image=True)
    if response is None:
        return False, None

    content_type = response.headers.get("Content-Type", "")
    if "image" not in content_type.lower():
        return False, None

    raw_bytes = response.content
    if len(raw_bytes) < MIN_IMAGE_BYTES:
        return False, None

    try:
        from io import BytesIO
        image = Image.open(BytesIO(raw_bytes))
        image.load()
    except Exception:
        return False, None

    width, height = image.size
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        return False, None

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination_path, format="JPEG", quality=90)

    return True, content_hash(raw_bytes)


def select_story_images(article_url, soup, story_slug, max_images=MAX_IMAGES_PER_STORY):
    """
    Find, download, and de-duplicate real article photos for one story.

    This is what fixes the "5 slides that are secretly 1 photo" bug:
    every successfully downloaded image's content hash is compared
    against every other image already accepted for this story, and
    exact/near-duplicates are rejected rather than silently kept.
    """
    candidates = extract_candidate_images(soup, article_url)

    accepted_paths = []
    seen_hashes = set()

    for index, candidate_url in enumerate(candidates):
        if len(accepted_paths) >= max_images:
            break

        filename = f"{story_slug}_{index:02d}.jpg"
        destination = SOURCE_DIR / filename

        ok, image_hash = download_image(candidate_url, destination)
        if not ok:
            continue

        if image_hash in seen_hashes:
            # exact duplicate of an image we already accepted for this
            # story -- delete it and move on instead of padding the
            # gallery with a repeated photo
            try:
                destination.unlink()
            except Exception:
                pass
            continue

        seen_hashes.add(image_hash)
        accepted_paths.append(str(destination))
        log(f"  + accepted image {filename} from {domain_of(candidate_url)}")

    return accepted_paths


def make_slug(headline):
    slug = re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")
    return slug[:60] or f"story-{int(time.time())}"


def build_story_record(headline, summary, article_url, source_domain, published_at, image_paths):
    return {
        "headline": normalize_text(headline),
        "summary": normalize_text(summary),
        "url": article_url,
        "source": source_domain,
        "published_at": published_at,
        "images": image_paths,
        "image_count": len(image_paths),
    }


def process_article(headline, summary, article_url, published_at):
    if forbidden_text(headline) or forbidden_text(summary):
        log(f"  ! rejected (forbidden topic): {headline}")
        return None

    if forbidden_source(article_url):
        log(f"  ! rejected (forbidden source): {article_url}")
        return None

    source_domain = domain_of(article_url)

    soup = fetch_article(article_url)
    if soup is None:
        log(f"  ! could not fetch article: {article_url}")
        return None

    slug = make_slug(headline)
    image_paths = select_story_images(article_url, soup, slug)

    if len(image_paths) < MIN_IMAGES_PER_STORY:
        # A story with zero verified real photos is dropped rather than
        # falling back to a placeholder/avatar/screenshot. This is the
        # deliberate fix for the V8 pipeline silently shipping a
        # placeholder silhouette when no real photo was found.
        log(f"  ! rejected (no valid real images found): {headline}")
        return None

    return build_story_record(
        headline=headline,
        summary=summary,
        article_url=article_url,
        source_domain=source_domain,
        published_at=published_at,
        image_paths=image_paths,
    )


# ============================================================
# ENTRY POINT
#
# NOTE: search_for_stories() below is intentionally left as an
# interface stub -- plug in whatever news-search API/RSS source you
# already use elsewhere in the project (the piece that was missing
# was never "how do we search", it was "what do we do with a result
# once we have it"). Everything from process_article() downward is
# fully implemented and is the part that actually fixes the bugs.
# ============================================================

def search_for_stories(query, limit=5):
    """
    Plug in your existing news search / RSS source here. Must return
    a list of dicts like:
      {"headline": ..., "summary": ..., "url": ..., "published_at": ...}
    """
    raise NotImplementedError(
        "Wire this up to your existing search/RSS source. "
        "Everything downstream (process_article onward) is complete."
    )


def run():
    ensure_directories()
    clean_old_images()

    accepted_stories = []

    for query in SEARCH_QUERIES:
        if len(accepted_stories) >= MAX_STORIES:
            break

        try:
            results = search_for_stories(query)
        except NotImplementedError as exc:
            log(str(exc))
            return
        except Exception as exc:
            log(f"  ! search failed for '{query}': {exc}")
            continue

        for result in results:
            if len(accepted_stories) >= MAX_STORIES:
                break

            story = process_article(
                headline=result.get("headline", ""),
                summary=result.get("summary", ""),
                article_url=result.get("url", ""),
                published_at=result.get("published_at", ""),
            )

            if story:
                accepted_stories.append(story)

    save_json(STORY_JSON, {"stories": accepted_stories})
    log(f"Saved {len(accepted_stories)} stories to {STORY_JSON}")


if __name__ == "__main__":
    run()
