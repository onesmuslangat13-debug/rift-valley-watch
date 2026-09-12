# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS ENGINE
# COMPLETE STORY + IMAGE RECOVERY PIPELINE
# ============================================================

import os
import re
import json
import time
import html
import hashlib
import traceback
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = ROOT / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
STANDARD_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"


# ============================================================
# CONFIGURATION
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
]

TRUSTED_DOMAINS = [
    "bomet.go.ke",
    "kericho.go.ke",
    "nakuru.go.ke",
    "nandi.go.ke",
    "uasingishu.go.ke",
    "elgeyomarakwet.go.ke",
    "westpokot.go.ke",
    "narok.go.ke",
    "peopledaily.digital",
    "nation.africa",
    "citizen.digital",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "kbc.co.ke",
]

BLOCKED_DOMAINS = [
    "facebook.com",
    "fb.com",
    "google.com",
    "news.google.com",
    "youtube.com",
    "instagram.com",
    "tiktok.com",
]

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
    "googleusercontent",
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "favicon",
    "logo",
    "placeholder",
    "avatar",
    "sprite",
    "icon",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "blank",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://bomet.go.ke/",
}

REQUEST_TIMEOUT = 25


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


def warn(message):
    print(f"WARNING: {message}", flush=True)


def fail(message):
    raise RuntimeError(message)


# ============================================================
# BASIC UTILITIES
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def is_blocked_domain(url):
    domain = normalize_domain(url)

    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return True

    return False


def is_trusted_domain(url):
    domain = normalize_domain(url)

    for trusted in TRUSTED_DOMAINS:
        if domain == trusted or domain.endswith("." + trusted):
            return True

    return False


def image_url_is_bad(url):
    if not url:
        return True

    lowered = url.lower()

    if not is_http_url(url):
        return True

    if is_blocked_domain(url):
        return True

    for term in BAD_IMAGE_TERMS:
        if term in lowered:
            return True

    if lowered.startswith("data:"):
        return True

    return False


def safe_filename(text):
    text = clean_text(text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text[:150]


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        warn(f"Could not read {path}: {exc}")
        return None


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# RECURSIVE URL EXTRACTION
# ============================================================

def recursive_find_urls(value):
    found = []

    if isinstance(value, str):
        if is_http_url(value):
            found.append(value)

    elif isinstance(value, dict):
        for v in value.values():
            found.extend(recursive_find_urls(v))

    elif isinstance(value, list):
        for item in value:
            found.extend(recursive_find_urls(item))

    return found


def extract_article_url(story):
    """
    Extract the best article/source URL from any reasonable
    story structure.
    """

    if not isinstance(story, dict):
        return None

    source = story.get("source")

    # Normal structured source:
    # {
    #   "name": "...",
    #   "url": "...",
    #   "type": "OFFICIAL_SOURCE"
    # }
    if isinstance(source, dict):
        url = source.get("url")

        if is_http_url(url) and not is_blocked_domain(url):
            return url

    # Other common fields
    for key in [
        "article_url",
        "articleUrl",
        "url",
        "link",
        "source_url",
        "sourceUrl",
        "canonical_url",
        "canonicalUrl",
    ]:
        value = story.get(key)

        if isinstance(value, str):
            if is_http_url(value) and not is_blocked_domain(value):
                return value

        if isinstance(value, dict):
            urls = recursive_find_urls(value)
            for url in urls:
                if not is_blocked_domain(url):
                    return url

    # Last resort: recursively inspect whole object.
    urls = recursive_find_urls(story)

    for url in urls:
        if not is_blocked_domain(url):
            return url

    return None


# ============================================================
# STORY IMAGE URL EXTRACTION
# ============================================================

def extract_story_image_urls(story):
    candidates = []

    if not isinstance(story, dict):
        return candidates

    preferred_keys = [
        "image",
        "image_url",
        "imageUrl",
        "image_uri",
        "imageUri",
        "featured_image",
        "featuredImage",
        "featured_image_url",
        "featuredImageUrl",
        "thumbnail",
        "thumbnail_url",
        "thumbnailUrl",
        "photo",
        "photo_url",
        "photoUrl",
        "hero_image",
        "heroImage",
        "media",
    ]

    for key in preferred_keys:
        value = story.get(key)

        if isinstance(value, str) and is_http_url(value):
            candidates.append(value)

        elif isinstance(value, dict):
            candidates.extend(recursive_find_urls(value))

        elif isinstance(value, list):
            candidates.extend(recursive_find_urls(value))

    # Recursive fallback
    for url in recursive_find_urls(story):
        if url not in candidates:
            candidates.append(url)

    return [
        url for url in candidates
        if is_http_url(url) and not image_url_is_bad(url)
    ]


# ============================================================
# HTTP FETCHING
# ============================================================

def fetch_url(url, timeout=REQUEST_TIMEOUT):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        response.raise_for_status()
        return response

    except Exception as exc:
        warn(f"FETCH FAILED: {url}")
        warn(str(exc))
        return None


# ============================================================
# IMAGE CANDIDATE HELPERS
# ============================================================

def add_candidate(candidates, url, base_url=None, score=0, reason=""):
    if not url:
        return

    url = html.unescape(str(url)).strip()

    if base_url:
        url = urljoin(base_url, url)

    if not is_http_url(url):
        return

    if image_url_is_bad(url):
        return

    candidates.append({
        "url": url,
        "score": int(score),
        "reason": reason,
    })


def extract_srcset(value):
    urls = []

    if not value:
        return urls

    parts = str(value).split(",")

    for part in parts:
        part = part.strip()

        if not part:
            continue

        bits = part.split()

        if bits:
            urls.append(bits[0])

    return urls


# ============================================================
# HTML IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(soup, base_url):
    candidates = []

    # --------------------------------------------------------
    # Open Graph
    # --------------------------------------------------------

    for tag in soup.find_all("meta"):
        prop = (
            tag.get("property")
            or tag.get("name")
            or tag.get("itemprop")
            or ""
        ).lower()

        content = tag.get("content")

        if not content:
            continue

        if prop in [
            "og:image",
            "og:image:url",
            "og:image:secure_url",
        ]:
            add_candidate(
                candidates,
                content,
                base_url,
                100,
                "Open Graph image",
            )

        elif prop in [
            "twitter:image",
            "twitter:image:src",
        ]:
            add_candidate(
                candidates,
                content,
                base_url,
                90,
                "Twitter image",
            )

        elif prop in [
            "image",
            "thumbnail",
            "thumbnailurl",
            "imageurl",
        ]:
            add_candidate(
                candidates,
                content,
                base_url,
                75,
                "Meta image",
            )

    # --------------------------------------------------------
    # image_src
    # --------------------------------------------------------

    for link in soup.find_all("link"):
        rel = link.get("rel") or []

        if isinstance(rel, str):
            rel = [rel]

        rel = [str(x).lower() for x in rel]

        href = link.get("href")

        if href and (
            "image_src" in rel
            or "image" in rel
            or "thumbnail" in rel
        ):
            add_candidate(
                candidates,
                href,
                base_url,
                70,
                "Image link",
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all("script", type="application/ld+json"):

        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        for url in extract_jsonld_images(data):
            add_candidate(
                candidates,
                url,
                base_url,
                95,
                "JSON-LD image",
            )

    # --------------------------------------------------------
    # Article images
    # --------------------------------------------------------

    containers = []

    for selector in [
        "article",
        "main",
        "[role='main']",
        ".article",
        ".post",
        ".entry-content",
        ".post-content",
        ".single-post",
        ".content",
    ]:
        containers.extend(soup.select(selector))

    # Avoid duplicates
    seen_container_ids = set()
    unique_containers = []

    for container in containers:
        marker = id(container)

        if marker not in seen_container_ids:
            seen_container_ids.add(marker)
            unique_containers.append(container)

    for container in unique_containers:

        for img in container.find_all("img"):
            attrs = [
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-image",
                "data-url",
                "data-lazy",
                "data-fallback-src",
            ]

            for attr in attrs:
                value = img.get(attr)

                if value:
                    add_candidate(
                        candidates,
                        value,
                        base_url,
                        80,
                        f"Article image {attr}",
                    )

            for attr in [
                "srcset",
                "data-srcset",
                "data-lazy-srcset",
            ]:
                value = img.get(attr)

                if value:
                    for src in extract_srcset(value):
                        add_candidate(
                            candidates,
                            src,
                            base_url,
                            82,
                            f"Article image {attr}",
                        )

    # --------------------------------------------------------
    # All page images
    # --------------------------------------------------------

    for img in soup.find_all("img"):

        for attr in [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-url",
        ]:
            value = img.get(attr)

            if value:
                add_candidate(
                    candidates,
                    value,
                    base_url,
                    50,
                    f"Page image {attr}",
                )

        for attr in [
            "srcset",
            "data-srcset",
            "data-lazy-srcset",
        ]:
            value = img.get(attr)

            if value:
                for src in extract_srcset(value):
                    add_candidate(
                        candidates,
                        src,
                        base_url,
                        55,
                        f"Page image {attr}",
                    )

    return deduplicate_image_candidates(candidates)


def extract_jsonld_images(data):
    images = []

    if isinstance(data, dict):

        for key in [
            "image",
            "thumbnailUrl",
            "contentUrl",
            "url",
        ]:
            value = data.get(key)

            if isinstance(value, str):
                if value.startswith(("http://", "https://", "/")):
                    images.append(value)

            elif isinstance(value, dict):
                images.extend(extract_jsonld_images(value))

            elif isinstance(value, list):
                images.extend(extract_jsonld_images(value))

        for value in data.values():
            if isinstance(value, (dict, list)):
                images.extend(extract_jsonld_images(value))

    elif isinstance(data, list):
        for item in data:
            images.extend(extract_jsonld_images(item))

    return images


def deduplicate_image_candidates(candidates):
    best = {}

    for item in candidates:

        url = item.get("url")

        if not url:
            continue

        key = url.split("#")[0]

        existing = best.get(key)

        if existing is None or item["score"] > existing["score"]:
            best[key] = item

    result = list(best.values())

    result.sort(
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    return result


# ============================================================
# WORDPRESS REST API RECOVERY
# ============================================================

def wordpress_api_candidates(article_url, title):
    candidates = []

    parsed = urlparse(article_url)

    if not parsed.scheme or not parsed.netloc:
        return candidates

    base = f"{parsed.scheme}://{parsed.netloc}"

    api_root = base.rstrip("/") + "/wp-json/wp/v2"

    slug = parsed.path.rstrip("/").split("/")[-1]

    endpoints = []

    if slug:
        endpoints.append(
            f"{api_root}/posts?slug={quote_plus(slug)}"
        )

        endpoints.append(
            f"{api_root}/pages?slug={quote_plus(slug)}"
        )

    if title:
        endpoints.append(
            f"{api_root}/search?search={quote_plus(title)}&per_page=5"
        )

    for endpoint in endpoints:

        try:
            response = requests.get(
                endpoint,
                headers=HEADERS,
                timeout=15,
            )

            if response.status_code != 200:
                continue

            data = response.json()

            if not isinstance(data, list):
                continue

            for item in data:

                if not isinstance(item, dict):
                    continue

                # Direct rendered link
                link = item.get("link")

                # Featured media
                featured_media = item.get("featured_media")

                if featured_media:
                    media_url = (
                        f"{api_root}/media/"
                        f"{featured_media}"
                    )

                    try:
                        media_response = requests.get(
                            media_url,
                            headers=HEADERS,
                            timeout=15,
                        )

                        if media_response.status_code == 200:
                            media_data = media_response.json()

                            if isinstance(media_data, dict):

                                source_url = (
                                    media_data.get("source_url")
                                    or media_data.get("guid", {}).get("rendered")
                                )

                                if source_url:
                                    add_candidate(
                                        candidates,
                                        source_url,
                                        base,
                                        120,
                                        "WordPress featured media",
                                    )

                                media_details = (
                                    media_data.get("media_details")
                                    or {}
                                )

                                sizes = media_details.get("sizes") or {}

                                for size_name in [
                                    "large",
                                    "medium_large",
                                    "medium",
                                    "full",
                                ]:
                                    size_data = sizes.get(size_name)

                                    if isinstance(size_data, dict):
                                        source = size_data.get("source_url")

                                        if source:
                                            add_candidate(
                                                candidates,
                                                source,
                                                base,
                                                115,
                                                f"WordPress {size_name}",
                                            )

                    except Exception:
                        pass

                # Search endpoint may expose URL only.
                if link and is_http_url(link):
                    try:
                        page = fetch_url(link, timeout=15)

                        if page is not None:
                            soup = BeautifulSoup(
                                page.text,
                                "html.parser",
                            )

                            page_candidates = extract_image_candidates(
                                soup,
                                page.url,
                            )

                            for candidate in page_candidates:
                                candidate["score"] += 20

                            candidates.extend(page_candidates)

                    except Exception:
                        pass

        except Exception as exc:
            warn(f"WordPress recovery failed: {exc}")

    return deduplicate_image_candidates(candidates)


# ============================================================
# DIRECT ARTICLE RECOVERY
# ============================================================

def recover_images_from_article(article_url):
    candidates = []

    if not article_url:
        return candidates

    log("")
    log("============================================================")
    log("OFFICIAL ARTICLE IMAGE RECOVERY")
    log("============================================================")
    log(article_url)

    response = fetch_url(article_url)

    if response is None:
        return candidates

    final_url = response.url

    if is_blocked_domain(final_url):
        warn("Final article URL redirected to a blocked domain.")
        return candidates

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )
    except Exception as exc:
        warn(f"Could not parse article HTML: {exc}")
        return candidates

    candidates.extend(
        extract_image_candidates(
            soup,
            final_url,
        )
    )

    return deduplicate_image_candidates(candidates)


# ============================================================
# IMAGE DOWNLOAD + VALIDATION
# ============================================================

def validate_image_file(path):
    if not path.exists():
        return False

    if path.stat().st_size < 10_000:
        return False

    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size

            log(
                f"IMAGE VALIDATED: "
                f"{width}x{height}, "
                f"{path.stat().st_size} bytes"
            )

            if width < 300 or height < 200:
                return False

            return True

    except Exception as exc:
        warn(f"Image validation failed: {exc}")
        return False


def download_image(url, destination):
    if image_url_is_bad(url):
        return False

    log(f"TRYING IMAGE: {url}")

    try:
        response = requests.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=25,
            allow_redirects=True,
            stream=True,
        )

        if response.status_code != 200:
            warn(
                f"IMAGE HTTP {response.status_code}: {url}"
            )
            return False

        final_url = response.url

        if image_url_is_bad(final_url):
            warn("Rejected image after redirect.")
            return False

        content_type = (
            response.headers.get("Content-Type")
            or ""
        ).lower()

        if "text/html" in content_type:
            warn("Rejected HTML response masquerading as image.")
            return False

        temp_path = destination.with_suffix(".download")

        with temp_path.open("wb") as f:
            total = 0

            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if not chunk:
                    continue

                total += len(chunk)

                if total > 20 * 1024 * 1024:
                    warn("Image larger than 20MB.")
                    break

                f.write(chunk)

        if not temp_path.exists():
            return False

        if temp_path.stat().st_size < 10_000:
            temp_path.unlink(missing_ok=True)
            return False

        # Verify with Pillow
        try:
            from PIL import Image

            with Image.open(temp_path) as image:
                image.verify()

            with Image.open(temp_path) as image:
                width, height = image.size

            if width < 300 or height < 200:
                warn(
                    f"Rejected small image: "
                    f"{width}x{height}"
                )
                temp_path.unlink(missing_ok=True)
                return False

        except Exception as exc:
            warn(f"Downloaded file is not a valid image: {exc}")
            temp_path.unlink(missing_ok=True)
            return False

        # Convert to JPEG for reliable ffmpeg handling
        try:
            from PIL import Image

            with Image.open(temp_path) as image:
                image = image.convert("RGB")

                # Limit extremely large source files
                max_dimension = 3000

                if (
                    image.width > max_dimension
                    or image.height > max_dimension
                ):
                    image.thumbnail(
                        (max_dimension, max_dimension),
                        Image.LANCZOS,
                    )

                image.save(
                    destination,
                    "JPEG",
                    quality=94,
                    optimize=True,
                )

            temp_path.unlink(missing_ok=True)

        except Exception as exc:
            warn(f"JPEG conversion failed: {exc}")
            temp_path.unlink(missing_ok=True)
            return False

        if not validate_image_file(destination):
            destination.unlink(missing_ok=True)
            return False

        log(
            "============================================================"
        )
        log("REAL ARTICLE IMAGE RECOVERED")
        log(f"SAVED: {destination}")
        log(f"SOURCE: {final_url}")
        log(
            "============================================================"
        )

        return True

    except Exception as exc:
        warn(f"Image download failed: {exc}")

        temp_path = destination.with_suffix(".download")
        temp_path.unlink(missing_ok=True)

        return False


# ============================================================
# IMAGE RECOVERY MASTER
# ============================================================

def recover_story_image(story):
    """
    Complete image recovery sequence.

    Priority:
    1. Existing valid local image.
    2. Image URL explicitly inside story.
    3. Official article HTML.
    4. WordPress REST / featured media.
    5. Re-fetch article using canonical URL.
    """

    log("")
    log("============================================================")
    log("STARTING IMAGE RECOVERY")
    log("============================================================")

    # --------------------------------------------------------
    # 1. Existing local image
    # --------------------------------------------------------

    if IMAGE_FILE.exists():
        log(f"LOCAL IMAGE FOUND: {IMAGE_FILE}")

        if validate_image_file(IMAGE_FILE):
            log("Using existing valid article image.")
            return str(IMAGE_FILE)

        IMAGE_FILE.unlink(missing_ok=True)

    # --------------------------------------------------------
    # 2. Image URLs already in story.json
    # --------------------------------------------------------

    candidates = extract_story_image_urls(story)

    if candidates:
        log(
            f"FOUND {len(candidates)} IMAGE URL(S) "
            "INSIDE STORY JSON"
        )

        for url in candidates:
            if download_image(url, IMAGE_FILE):
                return str(IMAGE_FILE)

    # --------------------------------------------------------
    # Article URL
    # --------------------------------------------------------

    article_url = extract_article_url(story)

    if not article_url:
        warn("No usable article URL found in story.")
    else:
        log(f"ARTICLE URL: {article_url}")

    title = clean_text(story.get("title"))

    # --------------------------------------------------------
    # 3. Official article HTML
    # --------------------------------------------------------

    if article_url:
        candidates = recover_images_from_article(
            article_url
        )

        if candidates:
            log(
                f"ARTICLE HTML PRODUCED "
                f"{len(candidates)} IMAGE CANDIDATE(S)"
            )

            for index, candidate in enumerate(
                candidates[:25],
                start=1,
            ):
                log(
                    f"IMAGE CANDIDATE {index}: "
                    f"score={candidate['score']} "
                    f"reason={candidate['reason']}"
                )
                log(candidate["url"])

                if download_image(
                    candidate["url"],
                    IMAGE_FILE,
                ):
                    return str(IMAGE_FILE)

    # --------------------------------------------------------
    # 4. WordPress API recovery
    # --------------------------------------------------------

    if article_url:
        log("")
        log("TRYING WORDPRESS FEATURED MEDIA RECOVERY")

        wp_candidates = wordpress_api_candidates(
            article_url,
            title,
        )

        log(
            f"WORDPRESS RECOVERY PRODUCED "
            f"{len(wp_candidates)} CANDIDATE(S)"
        )

        for candidate in wp_candidates[:30]:

            log(
                f"WP IMAGE: "
                f"score={candidate['score']} "
                f"reason={candidate['reason']}"
            )

            if download_image(
                candidate["url"],
                IMAGE_FILE,
            ):
                return str(IMAGE_FILE)

    # --------------------------------------------------------
    # 5. Final direct retry
    # --------------------------------------------------------

    if article_url:
        log("")
        log("FINAL DIRECT ARTICLE RETRY")

        response = fetch_url(
            article_url,
            timeout=35,
        )

        if response is not None:

            try:
                soup = BeautifulSoup(
                    response.text,
                    "html.parser",
                )

                all_candidates = extract_image_candidates(
                    soup,
                    response.url,
                )

                all_candidates.sort(
                    key=lambda x: x["score"],
                    reverse=True,
                )

                for candidate in all_candidates:

                    if download_image(
                        candidate["url"],
                        IMAGE_FILE,
                    ):
                        return str(IMAGE_FILE)

            except Exception as exc:
                warn(
                    f"Final image retry failed: {exc}"
                )

    # --------------------------------------------------------
    # No image
    # --------------------------------------------------------

    log("")
    log("============================================================")
    log("IMAGE RECOVERY FAILED")
    log("============================================================")
    log(f"Article: {article_url}")
    log(f"Title: {title}")
    log(f"Expected image: {IMAGE_FILE}")
    log("")

    return None


# ============================================================
# STORY QUALITY GATE
# ============================================================

def story_quality_gate(story):
    if not isinstance(story, dict):
        return False, "Story is not an object."

    title = clean_text(story.get("title"))
    summary = clean_text(story.get("summary"))
    county = clean_text(story.get("county"))

    if not title:
        return False, "Missing title."

    if title.lower() in [
        "google news",
        "news",
        "latest news",
    ]:
        return False, "Generic/banned title."

    if not summary:
        return False, "Missing summary."

    if len(summary) < 80:
        return False, "Summary is too short."

    if not county:
        return False, "Missing county."

    source = story.get("source")

    if not isinstance(source, dict):
        return False, "Source must be structured."

    source_name = clean_text(
        source.get("name")
    )

    source_url = source.get("url")

    if not source_name:
        return False, "Missing source name."

    if not is_http_url(source_url):
        return False, "Missing source URL."

    if is_blocked_domain(source_url):
        return False, "Blocked source domain."

    verified_facts = story.get("verified_facts")

    if not isinstance(verified_facts, list):
        return False, "Missing verified facts."

    if len(verified_facts) < 2:
        return False, "Too few verified facts."

    official_statement = story.get(
        "official_statement"
    )

    if official_statement:
        if not isinstance(
            official_statement,
            dict,
        ):
            return False, "Invalid official statement."

    editorial = story.get("editorial")

    if isinstance(editorial, dict):

        confirmed = editorial.get("confirmed")

        if confirmed is not None:
            if not isinstance(confirmed, list):
                return False, "Invalid confirmed facts."

    return True, "PASS"


# ============================================================
# STORY NORMALIZATION
# ============================================================

def normalize_story(story):
    story = dict(story)

    source = story.get("source")

    if not isinstance(source, dict):
        source = {
            "name": "Official Source",
            "url": extract_article_url(story),
            "type": "OFFICIAL_SOURCE",
        }

    source["name"] = (
        clean_text(source.get("name"))
        or "Official Source"
    )

    source["url"] = (
        source.get("url")
        or extract_article_url(story)
    )

    story["source"] = source

    story["title"] = clean_text(
        story.get("title")
    )

    story["county"] = clean_text(
        story.get("county")
    )

    story["category"] = (
        clean_text(story.get("category"))
        or "COUNTY NEWS"
    )

    story["summary"] = clean_text(
        story.get("summary")
    )

    story["local_image"] = str(
        IMAGE_FILE
    )

    return story


# ============================================================
# SCRIPT GENERATION
# ============================================================

def fact_value(story, label):
    facts = story.get("verified_facts", [])

    for fact in facts:
        if not isinstance(fact, dict):
            continue

        if (
            clean_text(fact.get("label")).upper()
            == label.upper()
        ):
            return clean_text(
                fact.get("value")
            )

    return ""


def build_script(story):
    title = clean_text(story.get("title"))
    county = clean_text(story.get("county"))
    source = story.get("source") or {}

    source_name = clean_text(
        source.get("name")
    )

    project = fact_value(
        story,
        "PROJECT",
    )

    road_length = fact_value(
        story,
        "ROAD_LENGTH",
    )

    cost = fact_value(
        story,
        "COST",
    )

    location = fact_value(
        story,
        "LOCATION",
    )

    status = fact_value(
        story,
        "STATUS",
    )

    impact = fact_value(
        story,
        "IMPACT",
    )

    official = story.get(
        "official_statement"
    ) or {}

    speaker = clean_text(
        official.get("speaker")
    )

    quote = clean_text(
        official.get("quote")
    )

    narration = []

    narration.append(
        f"Rift Valley Watch. "
        f"A major road project is underway in "
        f"{county}."
    )

    if project:
        narration.append(
            f"The project covers the "
            f"{project} route."
        )

    if road_length and cost:
        narration.append(
            f"The reported project covers "
            f"{road_length} at a cost of "
            f"{cost}."
        )

    if location:
        narration.append(
            f"The project is located in "
            f"{location}."
        )

    if status:
        narration.append(
            f"Construction status: "
            f"{status.lower()}."
        )

    if impact:
        narration.append(
            f"The county government says the "
            f"project is expected to "
            f"{impact.lower()}."
        )

    if speaker and quote:
        narration.append(
            f"{speaker} said the Roads and "
            f"Transport Ministry has been "
            f"instructed to closely monitor "
            f"construction to ensure speedy "
            f"completion and quality works."
        )

    narration.append(
        f"Source: {source_name}."
    )

    text = " ".join(narration)

    script = {
        "title": title,
        "county": county,
        "source": source_name,
        "source_url": source.get("url"),
        "duration_target": 35,
        "narration": text,
        "local_image": str(IMAGE_FILE),
        "scenes": [
            {
                "scene": 1,
                "type": "PROJECT_TITLE",
                "text": title,
            },
            {
                "scene": 2,
                "type": "LOCATION",
                "text": location or county,
            },
            {
                "scene": 3,
                "type": "DATA",
                "text": (
                    f"{road_length} | {cost}"
                    if road_length and cost
                    else title
                ),
            },
            {
                "scene": 4,
                "type": "PROJECT",
                "text": project or title,
            },
            {
                "scene": 5,
                "type": "OFFICIAL_STATEMENT",
                "text": (
                    f"{speaker}: {quote}"
                    if speaker and quote
                    else (
                        "Construction monitoring "
                        "and quality works."
                    )
                ),
            },
            {
                "scene": 6,
                "type": "SOURCE",
                "text": source_name,
            },
        ],
    }

    return script


# ============================================================
# SAVE SCRIPT
# ============================================================

def save_story_and_script(story, script):
    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    save_json(
        SCRIPT_FILE,
        script,
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    log(
        f"SAVED: {SELECTED_STORY_FILE}"
    )

    log(
        f"SAVED: {SCRIPT_FILE}"
    )

    log(
        f"SAVED: {SELECTED_SCRIPT_FILE}"
    )


# ============================================================
# LOAD STORY
# ============================================================

def load_best_story():
    """
    Prefer the structured story.json because this file already
    contains verified facts and the official source.
    """

    candidates = [
        STORY_FILE,
        SELECTED_STORY_FILE,
    ]

    valid = []

    for path in candidates:

        story = load_json(path)

        if not story:
            continue

        passed, reason = story_quality_gate(
            story
        )

        if passed:
            valid.append(
                (
                    path,
                    story,
                )
            )
        else:
            warn(
                f"Rejected {path.name}: {reason}"
            )

    if not valid:
        fail(
            "No usable structured story was found."
        )

    # Prefer story.json.
    for path, story in valid:
        if path == STORY_FILE:
            log(
                "STRUCTURED STORY FOUND"
            )
            log(
                story.get("title", "")
            )
            return story

    path, story = valid[0]

    log(
        f"STRUCTURED STORY FOUND: {path.name}"
    )

    log(
        story.get("title", "")
    )

    return story


# ============================================================
# VIDEO GENERATOR IMPORT
# ============================================================

def load_video_generator():
    possible_modules = [
        "rift_valley_video_generator",
        "video_generator",
    ]

    last_error = None

    for module_name in possible_modules:

        try:
            module = __import__(
                module_name
            )

            generator = getattr(
                module,
                "generate_video",
                None,
            )

            if callable(generator):
                log(
                    f"VIDEO GENERATOR LOADED: "
                    f"{module_name}.generate_video"
                )

                return generator

        except Exception as exc:
            last_error = exc

    if last_error:
        raise RuntimeError(
            "Could not load video generator: "
            + str(last_error)
        )

    raise RuntimeError(
        "No generate_video() function was found."
    )


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def probe_video(path):
    if not path.exists():
        return None

    try:
        import subprocess

        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        return json.loads(
            result.stdout
        )

    except Exception as exc:
        warn(
            f"ffprobe failed: {exc}"
        )
        return None


# ============================================================
# FINAL VIDEO QC
# ============================================================

def validate_final_video(path):
    log("")
    log("============================================================")
    log("FINAL VIDEO QUALITY CONTROL")
    log("============================================================")

    if not path.exists():
        fail(
            f"Final video does not exist: {path}"
        )

    if path.stat().st_size < 100_000:
        fail(
            "Final video is suspiciously small."
        )

    probe = probe_video(path)

    if not probe:
        fail(
            "ffprobe could not inspect final video."
        )

    streams = probe.get(
        "streams",
        [],
    )

    video_stream = None
    audio_stream = None

    for stream in streams:

        if stream.get("codec_type") == "video":
            video_stream = stream

        elif stream.get("codec_type") == "audio":
            audio_stream = stream

    if video_stream is None:
        fail(
            "Final video has no video stream."
        )

    if audio_stream is None:
        fail(
            "Final video has no audio stream."
        )

    width = int(
        video_stream.get("width", 0)
    )

    height = int(
        video_stream.get("height", 0)
    )

    duration = float(
        probe.get("format", {})
        .get("duration", 0)
        or 0
    )

    codec = (
        video_stream.get("codec_name")
        or ""
    ).lower()

    audio_codec = (
        audio_stream.get("codec_name")
        or ""
    ).lower()

    log(f"WIDTH: {width}")
    log(f"HEIGHT: {height}")
    log(f"DURATION: {duration:.2f}s")
    log(f"VIDEO CODEC: {codec}")
    log(f"AUDIO CODEC: {audio_codec}")
    log(
        f"SIZE: {path.stat().st_size} bytes"
    )

    if width != 1080 or height != 1920:
        fail(
            f"Incorrect dimensions: "
            f"{width}x{height}"
        )

    if codec != "h264":
        warn(
            f"Video codec is {codec}, expected H.264."
        )

    if audio_codec not in [
        "aac",
        "mp3",
        "opus",
    ]:
        warn(
            f"Unexpected audio codec: "
            f"{audio_codec}"
        )

    if duration < 25:
        fail(
            f"Video is too short: "
            f"{duration:.2f}s"
        )

    if duration > 45:
        fail(
            f"Video is too long: "
            f"{duration:.2f}s"
        )

    log(
        "FINAL VIDEO QC: PASS"
    )

    return True


# ============================================================
# OUTPUT DISCOVERY
# ============================================================

def find_generated_video():
    preferred = [
        FINAL_VIDEO,
        STANDARD_VIDEO,
        OUTPUT_DIR / "rift_valley_watch_reel.mp4",
        OUTPUT_DIR / "rift_valley_watch.mp4",
    ]

    for path in preferred:
        if path.exists():
            return path

    mp4_files = sorted(
        OUTPUT_DIR.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if mp4_files:
        return mp4_files[0]

    return None


# ============================================================
# MAIN VIDEO GENERATION
# ============================================================

def generate_final_video(story):
    log("")
    log("============================================================")
    log("STARTING VIDEO GENERATION")
    log("============================================================")

    if not IMAGE_FILE.exists():
        fail(
            "No article image exists before video generation."
        )

    if not validate_image_file(
        IMAGE_FILE
    ):
        fail(
            "Article image failed validation."
        )

    generator = load_video_generator()

    # IMPORTANT:
    # generate_video() accepts ONE story argument.
    result = generator(story)

    log(
        f"VIDEO GENERATOR RETURNED: {result}"
    )

    generated = None

    if isinstance(result, str):
        generated = Path(result)

    elif isinstance(result, Path):
        generated = result

    elif isinstance(result, dict):

        for key in [
            "output",
            "output_file",
            "video",
            "video_path",
            "path",
        ]:
            value = result.get(key)

            if value:
                generated = Path(
                    str(value)
                )
                break

    # If generator did not return a path,
    # discover the MP4 in output/.
    if generated is None or not generated.exists():
        generated = find_generated_video()

    if generated is None:
        fail(
            "Video generator completed but no MP4 "
            "was produced."
        )

    log(
        f"GENERATED VIDEO: {generated}"
    )

    # Normalize final filename
    if generated.resolve() != FINAL_VIDEO.resolve():

        if FINAL_VIDEO.exists():
            FINAL_VIDEO.unlink()

        generated.replace(
            FINAL_VIDEO
        )

        generated = FINAL_VIDEO

    validate_final_video(
        generated
    )

    return generated


# ============================================================
# MAIN
# ============================================================

def main():

    started = time.time()

    log("")
    log("============================================================")
    log("RIFT VALLEY WATCH")
    log("OFFICIAL COUNTY NEWS PIPELINE")
    log("============================================================")
    log(f"ROOT: {ROOT}")
    log(f"DATA: {DATA_DIR}")
    log(f"SOURCE: {SOURCE_DIR}")
    log(f"OUTPUT: {OUTPUT_DIR}")

    try:

        # ----------------------------------------------------
        # 1. Load structured story
        # ----------------------------------------------------

        story = load_best_story()

        log("")
        log("SELECTED STORY")
        log(
            f"TITLE: {story.get('title')}"
        )
        log(
            f"COUNTY: {story.get('county')}"
        )

        source = story.get(
            "source"
        ) or {}

        log(
            f"SOURCE: {source.get('name')}"
        )
        log(
            f"ARTICLE: {source.get('url')}"
        )

        # ----------------------------------------------------
        # 2. Normalize story
        # ----------------------------------------------------

        story = normalize_story(
            story
        )

        # ----------------------------------------------------
        # 3. Recover real article image
        # ----------------------------------------------------

        recovered = recover_story_image(
            story
        )

        if not recovered:
            fail(
                "No usable real article image could be "
                "recovered from the official source."
            )

        story["local_image"] = recovered

        # ----------------------------------------------------
        # 4. Build narration/script
        # ----------------------------------------------------

        script = build_script(
            story
        )

        # ----------------------------------------------------
        # 5. Save selected data
        # ----------------------------------------------------

        save_story_and_script(
            story,
            script,
        )

        # ----------------------------------------------------
        # 6. Generate final MP4
        # ----------------------------------------------------

        final_video = generate_final_video(
            story
        )

        # ----------------------------------------------------
        # 7. Final confirmation
        # ----------------------------------------------------

        elapsed = time.time() - started

        log("")
        log("============================================================")
        log("RIFT VALLEY WATCH SUCCESS")
        log("============================================================")
        log(
            f"FINAL MP4: {final_video}"
        )
        log(
            f"IMAGE: {IMAGE_FILE}"
        )
        log(
            f"SOURCE: {source.get('name')}"
        )
        log(
            f"ELAPSED: {elapsed:.1f}s"
        )
        log("============================================================")

        return 0

    except Exception as exc:

        log("")
        log("============================================================")
        log("RIFT VALLEY WATCH FAILED")
        log("============================================================")
        log(
            f"{type(exc).__name__}: {exc}"
        )
        log("")
        traceback.print_exc()
        log("")
        log("============================================================")

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )
