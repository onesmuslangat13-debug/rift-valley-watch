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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


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
    url = url.replace("\\/", "/")

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith("http://") and not url.startswith("https://"):
        return ""

    return url


def hash_text(text):
    return hashlib.sha1(
        text.encode(
            "utf-8",
            errors="ignore",
        )
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
            value = value.replace(
                tzinfo=timezone.utc
            )

        hours = (
            datetime.now(timezone.utc)
            - value.astimezone(timezone.utc)
        ).total_seconds() / 3600

        return hours <= 96

    except Exception:
        return True


def request_url(
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
        "Connection": "keep-alive",
    }

    if image:
        headers["Accept"] = (
            "image/avif,image/webp,image/apng,"
            "image/svg+xml,image/*,*/*;q=0.8"
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


def make_feed(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(
            query + " when:3d"
        )
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


def strip_tag(tag):
    value = str(tag)

    if "}" in value:
        value = value.split(
            "}",
            1,
        )[1]

    return value.lower()


def parse_feed(text):
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

        if strip_tag(element.tag) != "item":
            continue

        item = {
            "title": "",
            "description": "",
            "raw_description": "",
            "link": "",
            "pubdate": "",
            "source": "",
            "media": [],
        }

        for child in list(element):

            tag = strip_tag(child.tag)

            raw_value = child.text or ""
            value = raw_value

            if tag == "title":

                item["title"] = clean(
                    value
                )

            elif tag == "description":

                item["raw_description"] = (
                    unescape(
                        str(value)
                    )
                )

                item["description"] = clean(
                    value
                )

            elif tag == "link":

                item["link"] = normalize_url(
                    value
                )

            elif tag in [
                "pubdate",
                "published",
                "updated",
                "date",
            ]:

                if not item["pubdate"]:

                    item["pubdate"] = clean(
                        value
                    )

            elif tag == "source":

                item["source"] = clean(
                    value
                )

            elif tag in [
                "content",
                "thumbnail",
                "enclosure",
                "image",
                "media",
            ]:

                for attribute_name in [
                    "url",
                    "href",
                    "src",
                    "data-src",
                ]:

                    media_url = normalize_url(
                        child.attrib.get(
                            attribute_name,
                            "",
                        )
                    )

                    if media_url:

                        item["media"].append(
                            media_url
                        )

            else:

                for attribute_name in [
                    "url",
                    "href",
                    "src",
                    "data-src",
                ]:

                    attribute_value = (
                        normalize_url(
                            child.attrib.get(
                                attribute_name,
                                "",
                            )
                        )
                    )

                    if attribute_value:

                        item["media"].append(
                            attribute_value
                        )

        if (
            item["title"]
            and item["link"]
        ):
            items.append(item)

    return items


def fetch_feed(url):
    log("")
    log(
        "RSS FEED: "
        + url
    )

    response = request_url(url)

    if response is None:
        log(
            "RSS REQUEST FAILED"
        )
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
    images,
    value,
    base_url,
):
    if not value:
        return

    value = unescape(
        str(value)
    ).strip()

    value = value.replace(
        "\\/",
        "/",
    )

    value = value.strip(
        "\"'<>"
    )

    if value.startswith("data:"):
        return

    if value.startswith("//"):
        value = "https:" + value

    value = urljoin(
        base_url,
        value,
    )

    value = normalize_url(
        value
    )

    if not value:
        return

    if blocked_image(value):
        return

    if value not in images:
        images.append(value)


def html_images(
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
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)',
        r'<link[^>]+rel=["\'][^"\']*image_src[^"\']*["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'][^"\']*image_src[^"\']*["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazyload=["\']([^"\']+)["\']',
        r'<img[^>]+data-image=["\']([^"\']+)["\']',
        r'<source[^>]+src=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
        r'<img[^>]+srcset=["\']([^"\']+)["\']',
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

            if not value:
                continue

            if "," in value:

                pieces = value.split(
                    ","
                )

                for piece in pieces:

                    candidate = piece.strip()

                    if " " in candidate:
                        candidate = candidate.split(
                            " ",
                            1,
                        )[0]

                    add_candidate(
                        images,
                        candidate,
                        page_url,
                    )

            else:

                if (
                    " " in value
                    and "srcset"
                    in pattern.lower()
                ):
                    value = value.split(
                        " ",
                        1,
                    )[0]

                add_candidate(
                    images,
                    value,
                    page_url,
                )

    return images


def extract_urls_from_text(
    text,
    base_url,
):
    images = []

    if not text:
        return images

    raw = unescape(
        str(text)
    )

    patterns = [
        r'https?://[^"\'<>\s]+',
        r'(?:src|data-src|data-original|data-lazy-src|content)=["\']([^"\']+)["\']',
        r'url\(["\']?([^"\')]+)',
    ]

    for pattern in patterns:

        try:
            matches = re.findall(
                pattern,
                raw,
                flags=re.IGNORECASE,
            )
        except Exception:
            matches = []

        for value in matches:

            if isinstance(
                value,
                tuple,
            ):
                value = value[0]

            value = str(
                value
            ).strip()

            value = value.rstrip(
                "\"'<>),;"
            )

            if not value:
                continue

            lower = value.lower()

            looks_like_image = (
                ".jpg" in lower
                or ".jpeg" in lower
                or ".png" in lower
                or ".webp" in lower
                or ".avif" in lower
                or "image" in lower
                or "photo" in lower
                or "media" in lower
            )

            if looks_like_image:

                add_candidate(
                    images,
                    value,
                    base_url,
                )

    return images


def rss_images(item):
    images = []

    base_url = item.get(
        "link",
        "",
    )

    for value in item.get(
        "media",
        [],
    ):

        add_candidate(
            images,
            value,
            base_url,
        )

    raw_description = item.get(
        "raw_description",
        "",
    )

    description = item.get(
        "description",
        "",
    )

    raw_candidates = (
        extract_urls_from_text(
            raw_description,
            base_url,
        )
    )

    for value in raw_candidates:

        if value not in images:
            images.append(value)

    description_candidates = (
        extract_urls_from_text(
            description,
            base_url,
        )
    )

    for value in description_candidates:

        if value not in images:
            images.append(value)

    return images


def extract_absolute_image_urls(
    text,
    base_url,
):
    return extract_urls_from_text(
        text,
        base_url,
    )


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

    if ".avif" in lower:
        return ".avif"

    return ".jpg"


def response_is_real_image(
    response,
):
    if response is None:
        return False

    content = response.content

    if not content:
        return False

    if len(content) < MIN_BYTES:
        return False

    content_type = response.headers.get(
        "content-type",
        "",
    ).lower()

    if "text/html" in content_type:
        return False

    if content.startswith(
        b"<!DOCTYPE"
    ):
        return False

    if content.startswith(
        b"<html"
    ):
        return False

    if content.startswith(
        b"<HTML"
    ):
        return False

    return True


def save_response_image(
    response,
    path,
):
    try:

        if not response_is_real_image(
            response
        ):
            return False

        path.write_bytes(
            response.content
        )

        return valid_image(
            path
        )

    except Exception:
        return False


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
    seen_urls = set()

    for url in urls:

        if len(accepted) >= MAX_PHOTOS:
            break

        url = normalize_url(
            url
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        if blocked_image(url):
            log(
                "BLOCKED IMAGE: "
                + url
            )
            continue

        number = (
            len(accepted) + 1
        )

        path = folder / (
            "photo_"
            + str(number)
            + image_extension(url)
        )

        log(
            "PHOTO ATTEMPT "
            + str(number)
            + ": "
            + url
        )

        response = request_url(
            url,
            image=True,
            referer=article_url,
        )

        if response is None:
            log(
                "REJECTED REQUEST"
            )
            continue

        final_url = normalize_url(
            response.url
        )

        if (
            final_url
            and blocked_image(
                final_url
            )
        ):
            log(
                "REJECTED BLOCKED FINAL URL"
            )
            continue

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        log(
            "CONTENT TYPE: "
            + content_type
        )

        log(
            "IMAGE BYTES: "
            + str(
                len(
                    response.content
                )
            )
        )

        if not response_is_real_image(
            response
        ):
            log(
                "REJECTED NOT IMAGE"
            )
            continue

        if not save_response_image(
            response,
            path,
        ):

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
                "url": (
                    final_url
                    or url
                ),
            }
        )

        log(
            "ACCEPTED REAL PHOTO: "
            + relative
        )

    return accepted


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

        log(
            "BLOCKED STORY: "
            + title
        )

        return None

    if not recent(published):

        log(
            "OLD STORY: "
            + title
        )

        return None

    log("")
    log(
        "============================================================"
    )
    log(
        "TESTING STORY: "
        + title
    )
    log(
        "============================================================"
    )

    article_url = resolve_article(
        link
    )

    response = request_url(
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

        log(
            "ARTICLE URL: "
            + article_url
        )

    else:

        log(
            "ARTICLE PAGE REQUEST FAILED"
        )

    page_images = html_images(
        html,
        article_url,
    )

    feed_images = rss_images(
        item
    )

    embedded_images = (
        extract_absolute_image_urls(
            html,
            article_url,
        )
    )

    candidates = []

    for value in page_images:

        if value not in candidates:
            candidates.append(value)

    for value in feed_images:

        if value not in candidates:
            candidates.append(value)

    for value in embedded_images:

        if value not in candidates:
            candidates.append(value)

    log(
        "HTML IMAGE CANDIDATES: "
        + str(
            len(page_images)
        )
    )

    log(
        "RSS IMAGE CANDIDATES: "
        + str(
            len(feed_images)
        )
    )

    log(
        "EMBEDDED IMAGE CANDIDATES: "
        + str(
            len(embedded_images)
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

    story_id = hash_text(
        title
    )

    photos = download_images(
        story_id,
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
            item.get(
                "pubdate",
                "",
            )
        )

        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.timestamp()

    except Exception:
        return 0


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
        source = (
            "Rift Valley Watch"
        )

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
            shorten(
                description
            )
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

    for index, photo in enumerate(
        images
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

    narration = " ".join(
        parts
    )

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
    log(
        "============================================================"
    )
    log(
        "RIFT VALLEY WATCH NEWS ENGINE"
    )
    log(
        "VERSION V22 RSS RAW IMAGE RECOVERY"
    )
    log(
        "============================================================"
    )
    log("")

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

    all_items = []

    seen_titles = set()
    seen_links = set()

    for query in SEARCHES:

        items = fetch_feed(
            make_feed(query)
        )

        for item in items:

            title = clean(
                item.get(
                    "title",
                    "",
                )
            )

            link = normalize_url(
                item.get(
                    "link",
                    "",
                )
            )

            title_key = title.lower()
            link_key = link.lower()

            if not title_key:
                continue

            if title_key in seen_titles:
                continue

            if link_key in seen_links:
                continue

            seen_titles.add(
                title_key
            )

            seen_links.add(
                link_key
            )

            all_items.append(
                item
            )

            if len(all_items) >= MAX_ITEMS:
                break

        if len(all_items) >= MAX_ITEMS:
            break

    log("")
    log(
        "TOTAL RSS STORIES: "
        + str(
            len(all_items)
        )
    )
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

        story = process_item(
            item
        )

        if story is None:
            continue

        valid.append(
            story
        )

        if len(valid) >= 8:
            break

    if not valid:

        log("")
        log(
            "============================================================"
        )
        log(
            "NEWS ENGINE FAILED"
        )
        log(
            "============================================================"
        )
        log(
            "No valid story with a real article photograph was found."
        )
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

    script = make_script(
        selected
    )

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
    log(
        "============================================================"
    )
    log(
        "NEWS ENGINE SUCCESS"
    )
    log(
        "============================================================"
    )
    log(
        "STORY: "
        + selected["title"]
    )
    log(
        "COUNTY: "
        + selected["county"]
    )
    log(
        "SOURCE: "
        + selected["source"]
    )
    log(
        "REAL PHOTOS: "
        + str(
            selected["image_count"]
        )
    )
    log(
        "STORY JSON: "
        + str(
            STORY_FILE
        )
    )
    log(
        "SCRIPT JSON: "
        + str(
            SCRIPT_FILE
        )
    )
    log(
        "============================================================"
    )


if __name__ == "__main__":
    main()
