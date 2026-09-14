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


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

TIMEOUT = 25
MAX_ITEMS = 120
MAX_TEST = 60
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


FORBIDDEN_STORIES = [
    "rigathi gachagua",
    "gachagua",
]


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


def log(text=""):
    print(text, flush=True)


def clean(text):
    if text is None:
        return ""

    text = unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_url(url):
    if not url:
        return ""

    url = unescape(str(url)).strip()
    url = url.replace("&amp;", "&")

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(("http://", "https://")):
        return ""

    return url


def hash_text(text):
    return hashlib.sha1(
        text.encode("utf-8", errors="ignore")
    ).hexdigest()[:16]


def safe_name(text):
    text = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        text,
    )

    text = text.strip("_")

    if not text:
        return "story"

    return text[:80]


def forbidden_story(text):
    text = clean(text).lower()

    for term in FORBIDDEN_STORIES:
        if term in text:
            return True

    return False


def forbidden_image(url):
    url = clean(url).lower()

    for term in FORBIDDEN_IMAGES:
        if term in url:
            return True

    return False


def detect_county(text):
    text = clean(text).lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county

    return "Rift Valley"


def recent(date_text):
    if not date_text:
        return True

    try:
        value = parsedate_to_datetime(date_text)

        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        hours = (
            datetime.now(timezone.utc)
            - value.astimezone(timezone.utc)
        ).total_seconds() / 3600

        return hours <= 96

    except Exception:
        return True


def request_url(url, image=False, referer=None):
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
            "Request failed: "
            + str(exc)
        )
        return None


def build_feed(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def local_tag(tag):
    tag = str(tag)

    if "}" in tag:
        tag = tag.split("}", 1)[1]

    return tag.lower()


def parse_rss(text):
    items = []

    try:
        root = ET.fromstring(text)
    except Exception as exc:
        log(
            "RSS parse error: "
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
                media = normalize_url(
                    child.attrib.get(
                        "url",
                        "",
                    )
                )

                if media:
                    item["media"].append(
                        media
                    )

        if item["title"] and item["link"]:
            items.append(item)

    return items


def fetch_feed(url):
    log("")
    log("RSS FEED:")
    log(url)

    response = request_url(url)

    if response is None:
        return []

    items = parse_rss(response.text)

    log(
        "RSS ITEMS: "
        + str(len(items))
    )

    return items


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


def add_candidate(
    candidates,
    value,
    page_url,
):
    if not value:
        return

    value = unescape(str(value)).strip()

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


def html_images(html, page_url):
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

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

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
            ext in lower
            for ext in (
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
            ext in lower
            for ext in (
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


def extension(url):
    path = urlparse(
        url
    ).path.lower()

    if path.endswith(".png"):
        return ".png"

    if path.endswith(".webp"):
        return ".webp"

    if path.endswith(".jpeg"):
        return ".jpeg"

    if path.endswith(".avif"):
        return ".avif"

    return ".jpg"


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

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    if (
        "text/html" in content_type
        or "xhtml" in content_type
    ):
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


def download_photos(
    story_id,
    candidates,
    article_url,
):
    folder = (
        SOURCE_DIR / story_id
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

        if key in seen:
            continue

        seen.add(key)

        path = (
            folder
            / (
                "photo_"
                + str(len(accepted) + 1)
                + extension(url)
            )
        )

        log(
            "PHOTO:"
        )
        log(
            url
        )

        success = download_photo(
            url,
            path,
            article_url,
        )

        if not success:
            log(
                "REJECTED"
            )
            continue

        relative = str(
            path.relative_to(
                BASE_DIR
            )
        ).replace(
            "\\",
            "/",
        )

        accepted.append(
            {
                "path": relative,
                "url": url,
            }
        )

        log(
            "ACCEPTED REAL PHOTO:"
        )
        log(
            relative
        )

    return accepted


def story_id(title):
    return (
        hash_text(title)
        + "_"
        + safe_name(title[:60])
    )


def process_item(item):

    title = clean(
        item.get(
            "title",
            "",
        )
    )

    description = clean(
        item.get(
            "description",
            "",
        )
    )

    link = normalize_url(
        item.get(
            "link",
            "",
        )
    )

    published = clean(
        item.get(
            "pubdate",
            "",
        )
    )

    source = clean(
        item.get(
            "source",
            "",
        )
    )

    if not title:
        return None

    if not link:
        return None

    if forbidden_story(title):
        log(
            "FORBIDDEN STORY:"
        )
        log(title)
        return None

    if not recent(published):
        log(
            "OLD STORY:"
        )
        log(title)
        return None

    log("")
    log(
        "------------------------------------------------------------"
    )
    log(
        "TESTING:"
    )
    log(title)

    article_url = resolve_article(
        link
    )

    response = request_url(
        article_url
    )

    page_html = ""

    if response is not None:
        final_url = normalize_url(
            response.url
        )

        if final_url:
            article_url = final_url

        page_html = response.text

    page_candidates = html_images(
        page_html,
        article_url,
    )

    rss_candidates = rss_images(
        item
    )

    candidates = []

    for value in (
        page_candidates
        + rss_candidates
    ):

        if value not in candidates:
            candidates.append(value)

    log(
        "HTML IMAGE CANDIDATES: "
        + str(
            len(page_candidates)
        )
    )

    log(
        "RSS IMAGE CANDIDATES: "
        + str(
            len(rss_candidates)
        )
    )

    log(
        "TOTAL IMAGE CANDIDATES: "
        + str(
            len(candidates)
        )
    )

    if not candidates:
        log(
            "NO IMAGE URL FOUND"
        )
        return None

    sid = story_id(
        title
    )

    photos = download_photos(
        sid,
        candidates,
        article_url,
    )

    if not photos:
        log(
            "NO VALID REAL ARTICLE PHOTO"
        )
        return None

    county = detect_county(
        title
        + " "
        + description
        + " "
        + page_html[:10000]
    )

    return {
        "id": sid,
        "title": title,
        "description": description,
        "summary": description,
        "county": county,
        "source": source,
        "published": published,
        "article_url": article_url,
        "images": photos,
        "image_count": len(photos),
        "fetched_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


def shorten(text,
