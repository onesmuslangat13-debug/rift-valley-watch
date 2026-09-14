from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE
# VERSION: V18 SYNTAX-SAFE REAL PHOTO ENGINE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

TIMEOUT = 25
MAX_ITEMS = 150
MAX_TEST = 80
MAX_PHOTOS = 5

MIN_BYTES = 8000
MIN_WIDTH = 240
MIN_HEIGHT = 160
MIN_PIXELS = 60000

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


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


# ============================================================
# BLOCKED STORIES
# ============================================================

FORBIDDEN_STORIES = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# BLOCKED IMAGE URL TERMS
# ============================================================

FORBIDDEN_IMAGES = [
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
    "world cup",
    "world-cup",
    "world_cup",
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
]


# ============================================================
# SEARCHES
# ============================================================

SEARCH_TERMS = [
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
    "Rift Valley Kenya news",
]


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_url(value):
    if not value:
        return ""

    url = unescape(str(value)).strip()
    url = url.replace("&amp;", "&")

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("http://") and not url.startswith("https://"):
        return ""

    return url


def hash_text(value):
    return hashlib.sha1(
        value.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


def safe_name(value):
    text = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )

    text = text.strip("_")

    if not text:
        return "story"

    return text[:80]


# ============================================================
# FILTERS
# ============================================================

def forbidden_story(value):
    text = clean(value).lower()

    for term in FORBIDDEN_STORIES:
        if term in text:
            return True

    return False


def forbidden_image(value):
    text = clean(value).lower()

    for term in FORBIDDEN_IMAGES:
        if term in text:
            return True

    return False


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    value = clean(text).lower()

    for county in COUNTIES:
        if county.lower() in value:
            return county

    return "Rift Valley"


# ============================================================
# DATE CHECK
# ============================================================

def recent(date_text):
    if not date_text:
        return True

    try:
        value = parsedate_to_datetime(date_text)

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        age_hours = (
            datetime.now(timezone.utc)
            - value.astimezone(timezone.utc)
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
    url = normalize_url(url)

    if not url:
        return None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    if image:
        headers["Accept"] = (
            "image/avif,image/webp,image/apng,"
            "image/*,*/*;q=0.8"
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
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            log(
                "HTTP "
                + str(response.status_code)
                + ": "
                + url
            )
            return None

        return response

    except Exception as exc:
        log(
            "REQUEST FAILED: "
            + str(exc)
        )
        return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def build_feed(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def local_tag(tag):
    value = str(tag)

    if "}" in value:
        value = value.split(
            "}",
            1,
        )[1]

    return value.lower()


# ============================================================
# RSS PARSER
# ============================================================

def parse_rss(text):
    items = []

    try:
        root = ET.fromstring(text)

    except Exception as exc:
        log(
            "RSS PARSE ERROR: "
            + str(exc)
        )
        return items

    for element in root.iter():

        if local_tag(element.tag) != "item":
            continue

        item = {
            "title": "",
            "description": "",
            "link": "",
            "pubdate": "",
            "source": "",
            "media": [],
        }

        for child in list(element):

            tag = local_tag(child.tag)
            value = child.text or ""

            if tag == "title":
                item["title"] = clean(value)

            elif tag == "description":
                item["description"] = clean(value)

            elif tag == "link":
                item["link"] = normalize_url(value)

            elif tag in (
                "pubdate",
                "published",
                "updated",
            ):
                if not item["pubdate"]:
                    item["pubdate"] = clean(value)

            elif tag == "source":
                item["source"] = clean(value)

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
                    item["media"].append(
                        media_url
                    )

        if item["title"] and item["link"]:
            items.append(item)

    return items


# ============================================================
# FETCH RSS
# ============================================================

def fetch_feed(url):
    log("")
    log("RSS FEED:")
    log(url)

    response = request_url(url)

    if response is None:
        return []

    items = parse_rss(
        response.text
    )

    log(
        "RSS ITEMS: "
        + str(len(items))
    )

    return items


# ============================================================
# RESOLVE ARTICLE URL
# ============================================================

def resolve_article(url):
    url = normalize_url(url)

    if not url:
        return ""

    if "news.google.com" not in url:
        return url

    response = request_url(url)

    if response is None:
        return url

    final_url = normalize_url(
        response.url
    )

    if final_url:
        return final_url

    return url


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def add_candidate(
    candidates,
    value,
    page_url,
):
    if not value:
        return

    value = unescape(
        str(value)
    ).strip()

    if value.startswith("data:"):
        return

    value = urljoin(
        page_url,
        value,
    )

    value = normalize_url(value)

    if not value:
        return

    if forbidden_image(value):
        return

    if value not in candidates:
        candidates.append(value)


def html_images(
    html,
    page_url,
):
    candidates = []

    if not html:
        return candidates

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:

        try:
            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )
        except Exception:
            matches = []

        for value in matches:

            if "," in value and " " in value:
                value = value.split(
                    ",",
                    1,
                )[0]

            add_candidate(
                candidates,
                value,
                page_url,
            )

    raw_urls = re.findall(
        r"https?://[^\"'<>\\\s]+",
        html,
        flags=re.IGNORECASE,
    )

    for value in raw_urls:

        value = value.rstrip(
            "\"'<>),;\\"
        )

        lower = value.lower()

        if not any(
            extension_name in lower
            for extension_name in (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".avif",
            )
        ):
            continue

        add_candidate(
            candidates,
            value,
            page_url,
        )

    return candidates


def rss_images(item):
    candidates = []

    for value in item.get(
        "media",
        [],
    ):
        add_candidate(
            candidates,
            value,
            item.get(
                "link",
                "",
            ),
        )

    description = item.get(
        "description",
        "",
    )

    urls = re.findall(
        r"https?://[^\"'<>\\\s]+",
        description,
        flags=re.IGNORECASE,
    )

    for value in urls:

        value = value.rstrip(
            "\"'<>),;\\"
        )

        lower = value.lower()

        if not any(
            extension_name in lower
            for extension_name in (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".avif",
            )
        ):
            continue

        add_candidate(
            candidates,
            value,
            item.get(
                "link",
                "",
            ),
        )

    return candidates


# ============================================================
# IMAGE VALIDATION
# ============================================================

def valid_image(path):

    try:

        if not path.exists():
            return False

        if path.stat().st_size < MIN_BYTES:
            return False

        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_WIDTH:
                return False

            if height < MIN_HEIGHT:
                return False

            if width * height < MIN_PIXELS:
                return False

            image.verify()

        return True

    except Exception:
        return False


# ============================================================
# FILE EXTENSION
# ============================================================

def image_extension(url):

    path = urlparse(url).path.lower()

    if path.endswith(".png"):
        return ".png"

    if path.endswith(".webp"):
        return ".webp"

    if path.endswith(".jpeg"):
        return ".jpeg"

    if path.endswith(".avif"):
        return ".avif"

    return ".jpg"


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_photo(
    url,
    destination,
    referer,
):
    response = request_url(
        url,
        image=True,
        referer=referer,
    )

    if response is None:
        return False

    content_type = response.headers.get(
        "content-type",
        "",
    ).lower()

    if "text/html" in content_type:
        return False

    if "xhtml" in content_type:
        return False

    if len(response.content) < MIN_BYTES:
        return False

    try:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(
            response.content
        )

        if not valid_image(
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
# DOWNLOAD MULTIPLE PHOTOS
# ============================================================

def download_photos(
    story_id_value,
    candidates,
    article_url,
):
    folder = (
        SOURCE_DIR
        / story_id_value
    )

    if folder.exists():
        shutil.rmtree(folder)

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    accepted = []
    seen = set()

    for url in candidates:

        if len(accepted) >= MAX_PHOTOS:
            break

        url = normalize_url(url)

        if not url:
            continue

        if forbidden_image(url):
            continue

        key = hash_text(url)

        if key in
