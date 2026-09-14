from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin
from html import unescape
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
MAX_ITEMS = 100
MAX_TEST = 50
MAX_PHOTOS = 5

MIN_BYTES = 8000
MIN_WIDTH = 240
MIN_HEIGHT = 160

USER_AGENT = "Mozilla/5.0 Chrome/131.0 Safari/537.36"


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
    "world-cup",
    "world cup",
    "avatar",
    "placeholder",
    "default-image",
    "no-image",
    "favicon",
    "logo",
    "advertisement",
    "adsense",
]


SEARCHES = [
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


def log(text=""):
    print(text, flush=True)


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

    if not url.startswith("http://"):
        if not url.startswith("https://"):
            return ""

    return url


def hash_text(text):
    return hashlib.sha1(
        text.encode("utf-8", errors="ignore")
    ).hexdigest()[:16]


def blocked_story(text):
    value = clean(text).lower()

    for word in BLOCKED_STORIES:
        if word in value:
            return True

    return False


def blocked_image(url):
    value = clean(url).lower()

    for word in BLOCKED_IMAGES:
        if word in value:
            return True

    return False


def detect_county(text):
    value = clean(text).lower()

    for county in COUNTIES:
        if county.lower() in value:
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


def request_url(url, image=False, referer=""):
    url = normalize_url(url)

    if not url:
        return None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }

    if image:
        headers["Accept"] = "image/*,*/*;q=0.8"
    else:
        headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"

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
        log("REQUEST FAILED: " + str(exc))
        return None


def make_feed(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query + " when:3d")
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def strip_tag(tag):
    value = str(tag)

    if "}" in value:
        value = value.split("}", 1)[1]

    return value.lower()


def parse_feed(text):
    items = []

    try:
        root = ET.fromstring(text)
    except Exception as exc:
        log("RSS PARSE ERROR: " + str(exc))
        return items

    for element in root.iter():

        if strip_tag(element.tag) != "item":
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

            tag = strip_tag(child.tag)
            value = child.text or ""

            if tag == "title":
                item["title"] = clean(value)

            elif tag == "description":
                item["description"] = clean(value)

            elif tag == "link":
                item["link"] = normalize_url(value)

            elif tag in ["pubdate", "published", "updated"]:
                if not item["pubdate"]:
                    item["pubdate"] = clean(value)

            elif tag == "source":
                item["source"] = clean(value)

            elif tag in ["content", "thumbnail", "enclosure"]:

                media_url = normalize_url(
                    child.attrib.get("url", "")
                )

                if media_url:
                    item["media"].append(media_url)

        if item["title"] and item["link"]:
            items.append(item)

    return items


def fetch_feed(url):
    log("")
    log("RSS FEED: " + url)

    response = request_url(url)

    if response is None:
        log("RSS REQUEST FAILED")
        return []

    items = parse_feed(response.text)

    log("RSS ITEMS: " + str(len(items)))

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

    final_url = normalize_url(response.url)

    if final_url:
        return final_url

    return url


def add_candidate(images, value, base_url):
    if not value:
        return

    value = unescape(str(value)).strip()

    if value.startswith("data:"):
        return

    value = urljoin(base_url, value)
    value = normalize_url(value)

    if not value:
        return

    if blocked_image(value):
        return

    if value not in images:
        images.append(value)


def html_images(html, page_url):
    images = []

    if not html:
        return images

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
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
                value = value.split(",", 1)[0]

            add_candidate(
                images,
                value,
                page_url,
            )

    return images


def rss_images(item):
    images = []

    for value in item.get("media", []):

        add_candidate(
            images,
            value,
            item.get("link", ""),
        )

    description = item.get("description", "")

    urls = re.findall(
        r"https?://[^\"'<>\\\s]+",
        description,
        flags=re.IGNORECASE,
    )

    for value in urls:

        value = value.rstrip("\"'<>),;")

        lower = value.lower()

        if ".jpg" in lower:
            add_candidate(
                images,
                value,
                item.get("link", ""),
            )

        elif ".jpeg" in lower:
            add_candidate(
                images,
                value,
                item.get("link", ""),
            )

        elif ".png" in lower:
            add_candidate(
                images,
                value,
                item.get("link", ""),
            )

        elif ".webp" in lower:
            add_candidate(
                images,
                value,
                item.get("link", ""),
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

            image.verify()

        return True

    except Exception:
        return False


def image_extension(url):
    lower = url.lower()

    if ".png" in lower:
        return ".png"

    if ".webp" in lower:
        return ".webp"

    if ".jpeg" in lower:
        return ".jpeg"

    return ".jpg"


def download_images(story_id, urls, article_url):
    folder = SOURCE_DIR / story_id

    if folder.exists():
        shutil.rmtree(folder)

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    accepted = []

    for url in urls:

        if len(accepted) >= MAX_PHOTOS:
            break

        if blocked_image(url):
            continue

        number = len(accepted) + 1

        path = folder / (
            "photo_"
            + str(number)
            + image_extension(url)
        )

        log("PHOTO: " + url)

        response = request_url(
            url,
            image=True,
            referer=article_url,
        )

        if response is None:
            log("REJECTED")
            continue

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "text/html" in content_type:
            log("REJECTED HTML")
            continue

        if len(response.content) < MIN_BYTES:
            log("REJECTED SMALL")
            continue

        try:
            path.write_bytes(response.content)
        except Exception:
            log("REJECTED WRITE")
            continue

        if not valid_image(path):

            path.unlink(
                missing_ok=True
            )

            log("REJECTED INVALID IMAGE")
            continue

        relative = str(
            path.relative_to(BASE_DIR)
        ).replace("\\", "/")

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


def process_item(item):

    title = clean(
        item.get("title", "")
    )

    description = clean(
        item.get("description", "")
    )

    link = normalize_url(
        item.get("link", "")
    )

    published = clean(
        item.get("pubdate", "")
    )

    source = clean(
        item.get("source", "")
    )

    if not title:
        return None

    if not link:
        return None

    if blocked_story(title):
        log("BLOCKED STORY: " + title)
        return None

    if not recent(published):
        log("OLD STORY: " + title)
        return None

    log("")
    log("TESTING: " + title)

    article_url = resolve_article(link)

    response = request_url(article_url)

    html = ""

    if response is not None:
        final_url = normalize_url(response.url)

        if final_url:
            article_url = final_url

        html = response.text

    page_images = html_images(
        html,
        article_url,
    )

    feed_images = rss_images(item)

    candidates = []

    for value in page_images:

        if value not in candidates:
            candidates.append(value)

    for value in feed_images:

        if value not in candidates:
            candidates.append(value)

    log(
        "HTML IMAGE CANDIDATES: "
        + str(len(page_images))
    )

    log(
        "RSS IMAGE CANDIDATES: "
        + str(len(feed_images))
    )

    log(
        "TOTAL IMAGE CANDIDATES: "
        + str(len(candidates))
    )

    if not candidates:
        log("NO IMAGE URL FOUND")
        return None

    story_id = hash_text(title)

    photos = download_images(
        story_id,
        candidates,
        article_url,
    )

    if not photos:
        log("NO VALID REAL ARTICLE PHOTO")
        return None

    county = detect_county(
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


def date_sort(item):
    try:

        value = parsedate_to_datetime(
            item.get("pubdate", "")
        )

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.timestamp()

    except Exception:
        return 0


def shorten(text, maximum=260):
    text = clean(text)

    if len(text) <= maximum:
        return text

    text = text[:maximum]

    if " " in text:
        text = text.rsplit(" ", 1)[0]

    return text.rstrip(".,;:") + "."


def make_script(story):

    title = clean(
        story.get("title", "")
    )

    description = clean(
        story.get("description", "")
    )

    county = clean(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    source = clean(
        story.get("source", "")
    )

    if not source:
        source = "Rift Valley Watch"

    parts = []

    parts.append(
        "Rift Valley Watch breaking news."
    )

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
            shorten(description)
        )

    parts.append(
        "We are monitoring the story "
        "and will bring you verified updates."
    )

    scenes = []

    images = story.get(
        "images",
        [],
    )

    for index, photo in enumerate(images):

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

    narration = " ".join(parts)

    return {
        "story_id": story.get(
            "id",
            "",
        ),
        "title": title,
        "county": county,
        "source": source,
        "narration": narration,
        "scenes": scenes,
    }


def main():

    log("")
    log("============================================================")
    log("RIFT VALLEY WATCH NEWS ENGINE")
    log("VERSION V20")
    log("============================================================")
    log("")

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for child in list(SOURCE_DIR.iterdir()):

        try:

            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        except Exception:
            pass

    all_items = []

    seen_titles = set()
    seen_links = set()

    for query in SEARCHES:

        items = fetch_feed(
            make_feed(query)
        )

        for item in items:

            title = clean(
                item.get("title", "")
            )

            link = normalize_url(
                item.get("link", "")
            )

            title_key = title.lower()
            link_key = link.lower()

            if not title_key:
                continue

            if title_key in seen_titles:
                continue

            if link_key in seen_links:
                continue

            seen_titles.add(title_key)
            seen_links.add(link_key)

            all_items.append(item)

            if len(all_items) >= MAX_ITEMS:
                break

        if len(all_items) >= MAX_ITEMS:
            break

    log("")
    log("TOTAL RSS STORIES: " + str(len(all_items)))
    log("")

    all_items.sort(
        key=date_sort,
        reverse=True,
    )

    valid = []

    tested = 0

    for item in all_items:

        if tested >= MAX_TEST:
            break

        tested += 1

        story = process_item(item)

        if story is None:
            continue

        valid.append(story)

        if len(valid) >= 8:
            break

    if not valid:

        log("")
        log("============================================================")
        log("NEWS ENGINE FAILED")
        log("============================================================")
        log("No valid story with a real article photograph was found.")
        log("")

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

    script = make_script(selected)

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            selected,
            file,
            indent=2,
            ensure_ascii=False,
        )

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            script,
            file,
            indent=2,
            ensure_ascii=False,
        )

    log("")
    log("============================================================")
    log("NEWS ENGINE SUCCESS")
    log("============================================================")
    log("STORY: " + selected["title"])
    log("COUNTY: " + selected["county"])
    log("SOURCE: " + selected["source"])
    log(
        "REAL PHOTOS: "
        + str(selected["image_count"])
    )
    log(
        "STORY JSON: "
        + str(STORY_FILE)
    )
    log(
        "SCRIPT JSON: "
        + str(SCRIPT_FILE)
    )
    log("============================================================")


if __name__ == "__main__":
    main()
