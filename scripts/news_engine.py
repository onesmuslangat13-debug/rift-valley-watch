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


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

TIMEOUT = 20
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

BLOCKED_STORIES = [
    "rigathi gachagua",
    "gachagua",
]

BLOCKED_IMAGES = [
    "google.com",
    "googleusercontent",
    "news.google.com",
    "bing.com",
    "search-result",
    "search_result",
    "screenshot",
    "citizen",
    "ctv",
    "world cup",
    "avatar",
    "placeholder",
    "default-image",
    "no-image",
    "favicon",
    "logo",
    "advertisement",
    "adsense",
    "social-share",
]

QUERIES = [
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


def log(value=""):
    print(value, flush=True)


def clean(value):
    if value is None:
        return ""

    value = unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(value):
    if not value:
        return ""

    value = unescape(str(value)).strip()
    value = value.replace("&amp;", "&")

    if value.startswith("//"):
        value = "https:" + value

    if not value.startswith("http://") and not value.startswith("https://"):
        return ""

    return value


def blocked_story(text):
    text = clean(text).lower()

    for term in BLOCKED_STORIES:
        if term in text:
            return True

    return False


def blocked_image(url):
    url = clean(url).lower()

    for term in BLOCKED_IMAGES:
        if term in url:
            return True

    return False


def sha(text):
    return hashlib.sha1(
        text.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


def county_for(text):
    text = clean(text).lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county

    return "Rift Valley"


def is_recent(date_text):
    if not date_text:
        return True

    try:
        dt = parsedate_to_datetime(date_text)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        age = (
            datetime.now(timezone.utc)
            - dt.astimezone(timezone.utc)
        )

        return age.total_seconds() <= 96 * 3600

    except Exception:
        return True


def get(
    url,
    image=False,
    referer="",
):
    url = normalize_url(url)

    if not url:
        return None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
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
            return None

        return response

    except Exception as exc:
        log(
            "REQUEST FAILED: "
            + str(exc)
        )
        return None


def feed_url(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def tag_name(tag):
    tag = str(tag)

    if "}" in tag:
        tag = tag.split(
            "}",
            1,
        )[1]

    return tag.lower()


def parse_feed(text):
    result = []

    try:
        root = ET.fromstring(text)

    except Exception as exc:
        log(
            "RSS PARSE FAILED: "
            + str(exc)
        )
        return result

    for item in root.iter():

        if tag_name(item.tag) != "item":
            continue

        row = {
            "title": "",
            "description": "",
            "link": "",
            "pubdate": "",
            "source": "",
            "media": [],
        }

        for child in list(item):

            name = tag_name(child.tag)
            value = child.text or ""

            if name == "title":
                row["title"] = clean(value)

            elif name == "description":
                row["description"] = clean(value)

            elif name == "link":
                row["link"] = normalize_url(value)

            elif name in (
                "pubdate",
                "published",
                "updated",
            ):
                if not row["pubdate"]:
                    row["pubdate"] = clean(value)

            elif name == "source":
                row["source"] = clean(value)

            elif name in (
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
                    row["media"].append(
                        media
                    )

        if row["title"] and row["link"]:
            result.append(row)

    return result


def fetch_feed(url):
    log(
        "RSS FEED: "
        + url
    )

    response = get(url)

    if response is None:
        return []

    items = parse_feed(
        response.text
    )

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

    response = get(url)

    if response is None:
        return url

    final_url = normalize_url(
        response.url
    )

    if final_url:
        return final_url

    return url


def add_image(
    images,
    value,
    base_url,
):
    if not value:
        return

    value = unescape(
        str(value)
    ).strip()

    if value.startswith("data:"):
        return

    value = normalize_url(
        urljoin(
            base_url,
            value,
        )
    )

    if not value:
        return

    if blocked_image(value):
        return

    if value not in images:
        images.append(value)


def find_html_images(
    html,
    page_url,
):
    images = []

    if not html:
        return images

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            re.IGNORECASE,
        )

        for value in matches:

            if "," in value and " " in value:
                value = value.split(
                    ",",
                    1,
                )[0]

            add_image(
                images,
                value,
                page_url,
            )

    raw_urls = re.findall(
        r"https?://[^\"'<>\\\s]+",
        html,
        re.IGNORECASE,
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

        add_image(
            images,
            value,
            page_url,
        )

    return images


def find_rss_images(item):
    images = []

    for value in item.get(
        "media",
        [],
    ):

        add_image(
            images,
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

    raw_urls = re.findall(
        r"https?://[^\"'<>\\\s]+",
        description,
        re.IGNORECASE,
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

        add_image(
            images,
            value,
            item.get(
                "link",
                "",
            ),
        )

    return images


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


def image_ext(url):

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


def download_images(
    story_id,
    urls,
    article_url,
):
    folder = (
        SOURCE_DIR
        / story_id
    )

    if folder.exists():
        shutil.rmtree(
            folder
        )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    accepted = []
    seen = set()

    for url in urls:

        if len(accepted) >= MAX_PHOTOS:
            break

        key = sha(url)

        if key in seen:
            continue

        if blocked_image(url):
            continue

        seen.add(key)

        number = len(accepted) + 1

        path = (
            folder
            / (
                "photo_"
                + str(number)
                + image_ext(url)
            )
        )

        log(
            "PHOTO: "
            + url
        )

        response = get(
            url,
            image=True,
            referer=article_url,
        )

        if response is None:

            log("REJECTED")

            continue

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        if "text/html" in content_type:

            log("REJECTED HTML")

            continue

        if "xhtml" in content_type:

            log("REJECTED XHTML")

            continue

        if len(response.content) < MIN_BYTES:

            log("REJECTED SMALL")

            continue

        try:

            path.write_bytes(
                response.content
            )

        except Exception:

            log("REJECTED WRITE")

            continue

        if not valid_image(path):

            path.unlink(
                missing_ok=True
            )

            log(
                "REJECTED INVALID IMAGE"
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
            "ACCEPTED REAL PHOTO: "
            + relative
        )

    return accepted


def shorten(
    text,
    maximum=260,
):
    text = clean(text)

    if len(text) <= maximum:
        return text

    text = text[:maximum]

    if " " in text:
        text = text.rsplit(
            " ",
            1,
        )[0]

    return text.rstrip(
        ".,;:"
    ) + "."


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

    if blocked_story(title):
        return None

    if not is_recent(published):
        return None

    log(
        "TESTING: "
        + title
    )

    article_url = resolve_article(
        link
    )

    response = get(
        article_url
    )

    html = ""

    if response is not None:

        final_url = normalize_url(
            response.url
        )

        if final_url:
            article_url = final_url

        html = response.text

    page_images = find_html_images(
        html,
        article_url,
    )

    rss_images = find_rss_images(
        item
    )

    urls = []

    for value in (
        page_images
        + rss_images
    ):

        if value not in urls:
            urls.append(value)

    log(
        "HTML IMAGE CANDIDATES: "
        + str(len(page_images))
    )

    log(
        "RSS IMAGE CANDIDATES: "
        + str(len(rss_images))
    )

    log(
        "TOTAL IMAGE CANDIDATES: "
        + str(len(urls))
    )

    if not urls:
        return None

    story_id = sha(title)

    photos = download_images(
        story_id,
        urls,
        article_url,
    )

    if not photos:
        return None

    county = county_for(
        title
        + " "
        + description
        + " "
        + html[:10000]
    )

    return {
        "id": story_id,
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


def date_value(item):

    try:

        dt = parsedate_to_datetime(
            item.get(
                "pubdate",
                "",
            )
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.timestamp()

    except Exception:

        return 0


def make_script(story):

    title = clean(
        story.get(
            "title",
            "",
        )
    )

    description = clean(
        story.get(
            "description",
            "",
        )
    )

    county = clean(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    source = clean(
        story.get(
            "source",
            "",
        )
    )

    if not source:
        source = "Rift Valley Watch"

    parts = [
        "Rift Valley Watch breaking news."
    ]

    if county != "Rift Valley":

        parts.append(
            "Reports from "
            + county
            + "."
        )

    parts.append(
        title
        + "."
    )

    if description:

        parts.append(
            shorten(
                description
            )
        )

    parts.append(
        "We are monitoring the story "
        "and will bring you verified updates."
    )

    scenes = []

    for index, photo in enumerate(
        story.get(
            "images",
            [],
        )
    ):

        scenes.append(
            {
                "scene": index + 1,
                "text": title,
                "image_index": index,
                "image_path": photo.get(
                    "path",
                    "",
                ),
            }
        )

    return {
        "story_id": story.get(
            "id",
            "",
        ),
        "title": title,
        "county": county,
        "source": source,
        "narration": " ".join(parts),
        "scenes": scenes,
    }


def main():

    log(
        "============================================================"
    )

    log(
        "RIFT VALLEY WATCH NEWS ENGINE V19"
    )

    log(
        "============================================================"
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for child in list(
        SOURCE_DIR.iterdir()
    ):

        try:

            if child.is_dir():

                shutil.rmtree(
                    child
                )

            else:

                child.unlink()

        except Exception:
            pass

    items = []

    titles = set()
    links = set()

    for query in QUERIES:

        feed_items = fetch_feed(
            feed_url(query)
        )

        for item in feed_items:

            title_key = clean(
                item.get(
                    "title",
                    "",
                )
            ).lower()

            link_key = normalize_url(
                item.get(
                    "link",
                    "",
                )
            ).lower()

            if not title_key:
                continue

            if title_key in titles:
                continue

            if link_key in links:
                continue

            titles.add(
                title_key
            )

            links.add(
                link_key
            )

            items.append(
                item
            )

            if len(items) >= MAX_ITEMS:
                break

        if len(items) >= MAX_ITEMS:
            break

    log(
        "TOTAL RSS STORIES: "
        + str(len(items))
    )

    items.sort(
        key=date_value,
        reverse=True,
    )

    valid = []

    for item in items[:MAX_TEST]:

        result = process_item(
            item
        )

        if result is not None:

            valid.append(
                result
            )

        if len(valid) >= 8:
            break

    if not valid:

        raise RuntimeError(
            "No valid stories with real article photographs were found."
        )

    valid.sort(
        key=lambda item: item.get(
            "published",
            "",
        ),
        reverse=True,
    )

    selected = valid[0]

    script = make_script(
        selected
    )

    STORY_FILE.write_text(
        json.dumps(
           
