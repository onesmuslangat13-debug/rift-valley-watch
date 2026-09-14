from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse
import hashlib
import json
import re
import shutil
import time
import xml.etree.ElementTree as ET

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: V16_STABLE_REAL_PHOTO
#
# PURPOSE
# ------------------------------------------------------------
# - Fetch fresh Rift Valley news
# - Find current stories
# - Resolve article URLs
# - Extract real article photographs
# - Validate photographs with Pillow
# - Reject placeholders / logos / screenshots
# - Create data/story.json
# - Create data/script.json
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

REQUEST_TIMEOUT = 25

MAX_RSS_ITEMS = 150
MAX_STORIES_TO_TEST = 80
MAX_IMAGES_PER_STORY = 5

MIN_IMAGE_BYTES = 8000
MIN_IMAGE_WIDTH = 240
MIN_IMAGE_HEIGHT = 160
MIN_IMAGE_PIXELS = 60000


# ============================================================
# USER AGENTS
# ============================================================

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
]


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
    "elgeyo marakwet": "Elgeyo-Marakwet",
    "trans nzoia": "Trans Nzoia",
    "west pokot": "West Pokot",
}


# ============================================================
# FORBIDDEN STORY TERMS
# ============================================================

FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# FORBIDDEN IMAGE TERMS
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "google.com",
    "googleusercontent",
    "news.google.com",
    "bing.com",
    "search-result",
    "search_result",
    "search result",
    "screenshot",
    "screen-shot",
    "screen_shot",
    "citizen",
    "ctv",
    "world-cup",
    "world_cup",
    "world cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "defaultimage",
    "no-image",
    "no_image",
    "noimage",
    "favicon",
    "logo",
    "logos",
    "advertisement",
    "advert",
    "adsense",
    "social-share",
    "social_share",
    "share-image",
    "share_image",
]


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_TERMS = [
    "Rift Valley Kenya news",
    "Bomet Kenya news",
    "Kericho Kenya news",
    "Nakuru Kenya news",
    "Nandi Kenya news",
    "Uasin Gishu Kenya news",
    "Narok Kenya news",
    "West Pokot Kenya news",
    "Trans Nzoia Kenya news",
    "Elgeyo Marakwet Kenya news",
    "Samburu Kenya news",
    "Turkana Kenya news",
    "Laikipia Kenya news",
    "Kajiado Kenya news",
]


def build_feed_url(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


RSS_FEEDS = []

for search_term in SEARCH_TERMS:
    RSS_FEEDS.append(
        build_feed_url(search_term)
    )


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = unescape(str(value))
    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )
    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_url(url):
    if not url:
        return ""

    url = unescape(str(url)).strip()

    url = url.replace(
        "&amp;",
        "&",
    )

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(
        ("http://", "https://")
    ):
        return ""

    return url


def safe_filename(value):
    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )

    value = value.strip("_")

    if not value:
        value = "story"

    return value[:90]


def make_hash(value):
    return hashlib.sha1(
        value.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


# ============================================================
# STORY FILTER
# ============================================================

def forbidden_story(text):
    lowered = clean_text(
        text
    ).lower()

    for term in FORBIDDEN_STORY_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# IMAGE FILTER
# ============================================================

def forbidden_image(url):
    lowered = clean_text(
        url
    ).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# COUNTY
# ============================================================

def detect_county(text):
    lowered = clean_text(
        text
    ).lower()

    for county in COUNTIES:
        if county.lower() in lowered:
            return county

    for alias, county in COUNTY_ALIASES.items():
        if alias in lowered:
            return county

    return "Rift Valley"


# ============================================================
# RECENCY
# ============================================================

def is_recent(date_value):
    if not date_value:
        return True

    try:
        parsed = parsedate_to_datetime(
            date_value
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        age_hours = (
            datetime.now(timezone.utc)
            - parsed.astimezone(timezone.utc)
        ).total_seconds() / 3600

        return age_hours <= 96

    except Exception:
        return True


# ============================================================
# HTTP
# ============================================================

def request_url(
    url,
    image=False,
    referer=None,
):
    url = normalize_url(
        url
    )

    if not url:
        return None

    for user_agent in USER_AGENTS:

        headers = {
            "User-Agent": user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        if image:
            headers["Accept"] = (
                "image/avif,image/webp,"
                "image/apng,image/*,*/*;q=0.8"
            )
        else:
            headers["Accept"] = (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            )

        if referer:
            headers["Referer"] = referer

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            if response.status_code < 400:
                return response

            log(
                "    HTTP "
                + str(response.status_code)
                + ": "
                + url
            )

        except Exception as exc:
            log(
                "    Request failed: "
                + str(exc)
            )

        time.sleep(0.4)

    return None


# ============================================================
# RESOLVE ARTICLE URL
# ============================================================

def resolve_article_url(url):
    url = normalize_url(
        url
    )

    if not url:
        return ""

    if "news.google.com" not in url:
        return url

    response = request_url(
        url
    )

    if response is None:
        return url

    final_url = normalize_url(
        response.url
    )

    if final_url:
        return final_url

    return url


# ============================================================
# RSS XML
# ============================================================

def local_name(tag):
    tag = str(tag)

    if "}" in tag:
        tag = tag.split(
            "}",
            1,
        )[1]

    return tag.lower()


def parse_rss(xml_text):
    items = []

    if not xml_text:
        return items

    try:
        root = ET.fromstring(
            xml_text
        )
    except Exception as exc:
        log(
            "RSS XML error: "
            + str(exc)
        )
        return items

    for element in root.iter():

        if local_name(
            element.tag
        ) != "item":
            continue

        item = {
            "title": "",
            "description": "",
            "link": "",
            "pubdate": "",
            "source": "",
            "media_urls": [],
        }

        for child in list(element):

            tag = local_name(
                child.tag
            )

            text = child.text or ""

            if tag == "title":
                item["title"] = clean_text(
                    text
                )

            elif tag == "description":
                item["description"] = clean_text(
                    text
                )

            elif tag == "link":
                item["link"] = normalize_url(
                    text
                )

            elif tag in (
                "pubdate",
                "published",
                "updated",
            ):

                if not item["pubdate"]:
                    item["pubdate"] = clean_text(
                        text
                    )

            elif tag == "source":
                item["source"] = clean_text(
                    text
                )

            elif tag in (
                "content",
                "thumbnail",
                "enclosure",
            ):

                media_url = normalize_url(
                    child.attrib.get(
                        "url",
                        "",
                    )
                )

                if media_url:
                    item["media_urls"].append(
                        media_url
                    )

        if (
            item["title"]
            and item["link"]
        ):
            items.append(
                item
            )

    return items


# ============================================================
# RSS FETCH
# ============================================================

def fetch_feed(feed_url):
    log("")
    log(
        "Fetching RSS:"
    )
    log(
        feed_url
    )

    response = request_url(
        feed_url
    )

    if response is None:
        log(
            "RSS request failed."
        )
        return []

    items = parse_rss(
        response.text
    )

    log(
        "RSS items found: "
        + str(len(items))
    )

    return items


# ============================================================
# EXTRACT IMAGE URLS FROM TEXT
# ============================================================

def extract_image_urls(
    text,
    page_url,
):
    results = []

    if not text:
        return results

    patterns = [
        r"https?://[^\"'<>\\\s]+",
        r"//[^\"'<>\\\s]+",
    ]

    raw_urls = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for value in matches:

            value = value.rstrip(
                "\"'<>),;\\"
            )

            if value.startswith("//"):
                value = "https:" + value

            value = normalize_url(
                value
            )

            if value:
                raw_urls.append(
                    value
                )

    for url in raw_urls:

        lowered = url.lower()

        looks_like_image = any(
            extension in lowered
            for extension in (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".avif",
            )
        )

        if not looks_like_image:
            continue

        if forbidden_image(
            url
        ):
            continue

        absolute = urljoin(
            page_url,
            url,
        )

        absolute = normalize_url(
            absolute
        )

        if (
            absolute
            and absolute not in results
        ):
            results.append(
                absolute
            )

    return results


# ============================================================
# HTML IMAGE EXTRACTION
# ============================================================

def extract_html_images(
    html,
    page_url,
):
    candidates = []

    if not html:
        return candidates

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for value in matches:

            value = urljoin(
                page_url,
                unescape(
                    value
                ),
            )

            value = normalize_url(
                value
            )

            if not value:
                continue

            if forbidden_image(
                value
            ):
                continue

            if value not in candidates:
                candidates.append(
                    value
                )

    # --------------------------------------------------------
    # IMG SRC
    # --------------------------------------------------------

    img_patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-url=["\']([^"\']+)["\']',
    ]

    for pattern in img_patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for value in matches:

            value = urljoin(
                page_url,
                unescape(
                    value
                ),
            )

            value = normalize_url(
                value
            )

            if not value:
                continue

            if forbidden_image(
                value
            ):
                continue

            if value not in candidates:
                candidates.append(
                    value
                )

    # --------------------------------------------------------
    # SRCSET
    # --------------------------------------------------------

    srcset_patterns = [
        r'<img[^>]+srcset=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
    ]

    for pattern in srcset_patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for srcset in matches:

            entries = srcset.split(
                ","
            )

            for entry in entries:

                entry = entry.strip()

                if not entry:
                    continue

                image_url = entry.split()[0]

                image_url = urljoin(
                    page_url,
                    image_url,
                )

                image_url = normalize_url(
                    image_url
                )

                if not image_url:
                    continue

                if forbidden_image(
                    image_url
                ):
                    continue

                if image_url not in candidates:
                    candidates.append(
                        image_url
                    )

    # --------------------------------------------------------
    # Raw image URLs
    # --------------------------------------------------------

    for url in extract_image_urls(
        html,
        page_url,
    ):

        if url not in candidates:
            candidates.append(
                url
            )

    return candidates


# ============================================================
# RSS IMAGE EXTRACTION
# ============================================================

def extract_rss_images(item):
    candidates = []

    for url in item.get(
        "media_urls",
        [],
    ):

        url = normalize_url(
            url
        )

        if not url:
            continue

        if forbidden_image(
            url
        ):
            continue

        if url not in candidates:
            candidates.append(
                url
            )

    description = item.get(
        "description",
        "",
    )

    for url in extract_image_urls(
        description,
        item.get(
            "link",
            "",
        ),
    ):

        if url not in candidates:
            candidates.append(
                url
            )

    return candidates


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(
    path
):
    try:

        if not path.exists():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(
            path
        ) as image:

            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            if width * height < MIN_IMAGE_PIXELS:
                return False

            image.verify()

        return True

    except Exception:
        return False


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    image_url,
    destination,
    referer,
):
    if not image_url:
        return False

    if forbidden_image(
        image_url
    ):
        return False

    response = request_url(
        image_url,
        image=True,
        referer=referer,
    )

    if response is None:
        return False

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    content = response.content

    if (
        "text/html" in content_type
        or "application/xhtml" in content_type
    ):
        return False

    if len(content) < MIN_IMAGE_BYTES:
        return False

    try:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(
            content
        )

        if not validate_image(
            destination
        ):

            destination.unlink(
                missing_ok=True
            )

            return False

        return True

    except Exception:

        destination.unlink(
            missing_ok=True
        )

        return False


# ============================================================
# EXTENSION
# ============================================================

def get_extension(
    url
):
    path = urlparse(
        url
    ).path.lower()

    if path.endswith(
        ".png"
    ):
        return ".png"

    if path.endswith(
        ".webp"
    ):
        return ".webp"

    if path.endswith(
        ".jpeg"
    ):
        return ".jpeg"

    if path.endswith(
        ".avif"
    ):
        return ".avif"

    return ".jpg"


# ============================================================
# DOWNLOAD STORY PHOTOS
# ============================================================

def download_story_images(
    story_id,
    candidates,
    article_url,
):
    story_dir = (
        SOURCE_DIR / story_id
    )

    if story_dir.exists():
        shutil.rmtree(
            story_dir
        )

    story_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    accepted = []
    seen = set()

    for image_url in candidates:

        if len(accepted) >= MAX_IMAGES_PER_STORY:
            break

        image_url = normalize_url(
            image_url
        )

        if not image_url:
            continue

        if forbidden_image(
            image_url
        ):
            continue

        image_hash = make_hash(
            image_url
        )

        if image_hash in seen:
            continue

        seen.add(
            image_hash
        )

        extension = get_extension(
            image_url
        )

        filename = (
            "photo_"
            + str(len(accepted) + 1)
            + extension
        )

        destination = (
            story_dir / filename
        )

        log(
            "    Trying photo:"
        )

        log(
            "    "
            + image_url
        )

        success = download_image(
            image_url,
            destination,
            article_url,
        )

        if not success:

            log(
                "    REJECTED"
            )

            continue

        accepted.append(
            {
                "path": str(
                    destination.relative_to(
                        BASE_DIR
                    )
                ).replace(
                    "\\",
                    "/",
                ),
                "url": image_url,
            }
        )

        log(
            "    ACCEPTED REAL PHOTO"
        )

    return accepted


# ============================================================
# STORY ID
# ============================================================

def create_story_id(
    title
):
    return (
        make_hash(title)
        + "_"
        + safe_filename(
            title[:60]
        )
    )


# ============================================================
# PROCESS STORY
# ============================================================

def process_story(
    item
):
    title = clean_text(
        item.get(
            "title",
            "",
        )
    )

    description = clean_text(
        item.get(
            "description",
            "",
        )
    )

    rss_url = normalize_url(
        item.get(
            "link",
            "",
        )
    )

    published = clean_text(
        item.get(
            "pubdate",
            "",
        )
    )

    source = clean_text(
        item.get(
            "source",
            "",
        )
    )

    if not title:
        return None

    if not rss_url:
        return None

    if forbidden_story(
        title
    ):
