from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs
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
# VERSION: V14_SYNTAX_SAFE_REAL_PHOTOS
#
# PURPOSE
# - Fetch current Rift Valley news
# - Select one strong story
# - Download real article photographs
# - Reject placeholders, logos, screenshots and unrelated images
# - Create data/story.json
# - Create data/script.json
# - Avoid BeautifulSoup dependency
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

MAX_STORIES = 12
MAX_IMAGES = 5

REQUEST_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
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


FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


FORBIDDEN_IMAGE_TERMS = [
    "google",
    "bing",
    "search result",
    "search-result",
    "screenshot",
    "screen-shot",
    "citizen",
    "ctv",
    "world cup",
    "avatar",
    "placeholder",
    "default image",
    "no image",
    "favicon",
    "logo",
    "advert",
    "advertisement",
    "social share",
    "share image",
    "thumbnail placeholder",
]


RSS_FEEDS = [
    "https://news.google.com/rss/search?q="
    + quote_plus("Rift Valley Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Bomet Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Kericho Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Nakuru Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Nandi Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Uasin Gishu Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("Narok Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",

    "https://news.google.com/rss/search?q="
    + quote_plus("West Pokot Kenya news when:2d")
    + "&hl=en-KE&gl=KE&ceid=KE:en",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def log(message):
    print(message, flush=True)


def clean_text(value):
    if value is None:
        return ""

    value = unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(url):
    if not url:
        return ""

    url = unescape(str(url)).strip()

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(("http://", "https://")):
        return ""

    return url


def safe_filename(value):
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value)
    return value[:100].strip("_") or "file"


def file_hash(value):
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def is_recent_date(date_value):
    if not date_value:
        return True

    try:
        parsed = parsedate_to_datetime(date_value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        age_hours = (
            datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        ).total_seconds() / 3600

        return age_hours <= 96

    except Exception:
        return True


def detect_county(text):
    lowered = clean_text(text).lower()

    for county in COUNTIES:
        if county.lower() in lowered:
            return county

    for alias, county in COUNTY_ALIASES.items():
        if alias in lowered:
            return county

    return "Rift Valley"


def contains_forbidden_story_term(text):
    lowered = clean_text(text).lower()

    for term in FORBIDDEN_STORY_TERMS:
        if term in lowered:
            return True

    return False


def contains_forbidden_image_term(url):
    lowered = clean_text(url).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# HTTP
# ============================================================

def fetch_response(url, accept_html=True):
    headers = dict(HEADERS)

    if not accept_html:
        headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        return response

    except Exception as exc:
        log(f"HTTP fetch failed: {url} | {exc}")
        return None


def resolve_google_news_url(url):
    url = normalize_url(url)

    if not url:
        return ""

    if "news.google.com" not in url:
        return url

    response = fetch_response(url)

    if response is None:
        return url

    final_url = normalize_url(response.url)

    if final_url:
        return final_url

    return url


# ============================================================
# RSS PARSING
# ============================================================

def parse_rss_items(xml_text):
    items = []

    if not xml_text:
        return items

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        log(f"RSS XML parse failed: {exc}")
        return items

    for element in root.iter():
        if element.tag.lower().endswith("item"):
            item = {}

            for child in list(element):
                tag = child.tag.lower()

                if "}" in tag:
                    tag = tag.split("}", 1)[1]

                text = child.text or ""

                if tag in {
                    "title",
                    "description",
                    "link",
                    "pubdate",
                    "published",
                    "updated",
                    "source",
                    "content",
                    "encoded",
                }:
                    item[tag] = clean_text(text)

                if tag in {"enclosure", "content"}:
                    item["media_url"] = normalize_url(
                        child.attrib.get("url", "")
                    )

            if item.get("title") and item.get("link"):
                items.append(item)

    return items


def fetch_feed_items(feed_url):
    log(f"Fetching RSS feed: {feed_url}")

    response = fetch_response(feed_url)

    if response is None:
        return []

    return parse_rss_items(response.text)


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_urls_from_text(text):
    if not text:
        return []

    urls = re.findall(
        r"https?://[^\s\"'<>]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\s\"'<>]+)?",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = []

    for url in urls:
        url = url.rstrip("),.;")

        if url not in cleaned:
            cleaned.append(url)

    return cleaned


def extract_html_image_urls(html, page_url):
    candidates = []

    if not html:
        return candidates

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html, flags=re.IGNORECASE)

        for match in matches:
            value = match

            if "," in value and " " in value:
                value = value.split(",", 1)[0].strip()

            value = normalize_url(urljoin(page_url, value))

            if value and value not in candidates:
                candidates.append(value)

    for url in extract_urls_from_text(html):
        if url not in candidates:
            candidates.append(url)

    return candidates


def extract_rss_image_urls(item):
    candidates = []

    fields = [
        item.get("media_url", ""),
        item.get("description", ""),
        item.get("content", ""),
        item.get("encoded", ""),
    ]

    for field in fields:
        for url in extract_urls_from_text(field):
            if url not in candidates:
                candidates.append(url)

    return candidates


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_file(path):
    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        if width < 240 or height < 160:
            return False

        if width * height < 100000:
            return False

        return True

    except Exception:
        return False


def download_image(url, destination):
    url = normalize_url(url)

    if not url:
        return False

    if contains_forbidden_image_term(url):
        log(f"Rejected forbidden image URL: {url}")
        return False

    response = fetch_response(url, accept_html=False)

    if response is None:
        return False

    content_type = response.headers.get("content-type", "").lower()

    if "text/html" in content_type:
        return False

    content = response.content

    if len(content) < 10000:
        return False

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        if not validate_image_file(destination):
            destination.unlink(missing_ok=True)
            return False

        return True

    except Exception as exc:
        log(f"Image save failed: {url} | {exc}")
        return False


def download_unique_images(candidates, story_key):
    story_dir = SOURCE_DIR / story_key

    if story_dir.exists():
        shutil.rmtree(story_dir)

    story_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    seen_hashes = set()

    for index, url in enumerate(candidates):
        if len(downloaded) >= MAX_IMAGES:
            break

        if not url:
            continue

        if contains_forbidden_image_term(url):
            continue

        url_hash = file_hash(url)

        if url_hash in seen_hashes:
            continue

        seen_hashes.add(url_hash)

        extension = ".jpg"

        parsed_path = urlparse(url).path.lower()

        if parsed_path.endswith(".png"):
            extension = ".png"
        elif parsed_path.endswith(".webp"):
            extension = ".webp"
        elif parsed_path.endswith(".jpeg"):
            extension = ".jpeg"

        destination = story_dir / f"photo_{index + 1}{extension}"

        log(f"Trying article image {index + 1}: {url}")

        if download_image(url, destination):
            downloaded.append(
                {
                    "path": str(destination.relative_to(BASE_DIR)),
                    "url": url,
                }
            )

            log(f"Accepted real article image: {destination}")

    return downloaded


# ============================================================
# STORY ENRICHMENT
# ============================================================

def build_story_key(title):
    return safe_filename(file_hash(title) + "_" + title[:50])


def enrich_item(item):
    title = clean_text(item.get("title", ""))
    description = clean_text(item.get("description", ""))
    rss_link = normalize_url(item.get("link", ""))
    published = clean_text(
        item.get("pubdate")
        or item.get("published")
        or item.get("updated")
        or ""
    )

    if not title or not rss_link:
        return None

    if contains_forbidden_story_term(title):
        log(f"Rejected forbidden story: {title}")
        return None

    if not is_recent_date(published):
        log(f"Rejected old story: {title}")
        return None

    article_url = resolve_google_news_url(rss_link)

    page_html = ""
    page_image_urls = []

    page_response = fetch_response(article_url)

    if page_response is not None:
        article_url = normalize_url(page_response.url) or article_url
        page_html = page_response.text
        page_image_urls = extract_html_image_urls(page_html, article_url)

    rss_image_urls = extract_rss_image_urls(item)

    image_candidates = []

    for image_url in page_image_urls + rss_image_urls:
        image_url = normalize_url(image_url)

        if not image_url:
            continue

        if contains_forbidden_image_term(image_url):
            continue

        if image_url not in image_candidates:
            image_candidates.append(image_url)

    log(f"Story: {title}")
    log(f"Article URL: {article_url}")
    log(f"Page image candidates: {len(page_image_urls)}")
    log(f"RSS image candidates: {len(rss_image_urls)}")
    log(f"Total image candidates: {len(image_candidates)}")

    story_key = build_story_key(title)

    images = download_unique_images(
        image_candidates,
        story_key,
    )

    if not images:
        log(f"Rejected because no real article image downloaded: {title}")
        return None

    combined_text = " ".join(
        [
            title,
            description,
            page_html[:10000],
        ]
    )

    county = detect_county(combined_text)

    story = {
        "id": story_key,
        "title": title,
        "description": description,
        "summary": description,
        "county": county,
        "source": item.get("source", ""),
        "published": published,
        "article_url": article_url,
        "images": images,
        "image_count": len(images),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    return story


# ============================================================
# SCRIPT GENERATION
# ============================================================

def shorten_text(text, maximum=240):
    text = clean_text(text)

    if len(text) <= maximum:
        return text

    shortened = text[:maximum].rsplit(" ", 1)[0]
    return shortened.rstrip(".,;:") + "."


def generate_script(story):
    title = clean_text(story.get("title", ""))
    description = clean_text(
        story.get("description")
        or story.get("summary")
        or ""
    )
    county = clean_text(story.get("county", "Rift Valley"))
    source = clean_text(story.get("source", ""))

    if not source:
        source = "Rift Valley Watch"

    parts = []

    parts.append("Rift Valley Watch breaking news.")

    if county and county != "Rift Valley":
        parts.append(f"Reports from {county}.")

    parts.append(title + ".")

    if description:
        parts.append(shorten_text(description, 260))

    parts.append(
        "We will continue monitoring developments and bring you verified updates."
    )

    narration = " ".join(parts)
    narration = re.sub(r"\s+", " ", narration).strip()

    return {
        "story_id": story.get("id", ""),
        "title": title,
        "county": county,
        "source": source,
        "narration": narration,
        "scenes": [
            {
                "scene": 1,
                "text": title,
                "image_index": 0,
            }
        ],
    }


# ============================================================
# MAIN
# ============================================================

def main():
    log("")
    log("=" * 60)
    log("RIFT VALLEY WATCH NEWS ENGINE V14")
    log("=" * 60)
    log("")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    all_items = []
    seen_links = set()
    seen_titles = set()

    for feed_url in RSS_FEEDS:
        feed_items = fetch_feed_items(feed_url)

        for item in feed_items:
            title = clean_text(item.get("title", ""))
            link = normalize_url(item.get("link", ""))

            title_key = title.lower()
            link_key = link.lower()

            if title_key in seen_titles:
                continue

            if link_key in seen_links:
                continue

            seen_titles.add(title_key)
            seen_links.add(link_key)

            all_items.append(item)

    log("")
    log(f"RSS items collected: {len(all_items)}")
    log("")

    stories = []

    for item in all_items[:MAX_STORIES]:
        story = enrich_item(item)

        if story is None:
            continue

        stories.append(story)

    if not stories:
        raise RuntimeError(
            "No valid stories with real article photographs were found."
        )

    stories.sort(
        key=lambda story: story.get("published", ""),
        reverse=True,
    )

    selected_story = stories[0]
    selected_script = generate_script(selected_story)

    STORY_FILE.write_text(
        json.dumps(selected_story, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    SCRIPT_FILE.write_text(
        json.dumps(selected_script, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log("")
    log("=" * 60)
    log("NEWS ENGINE SUCCESS")
    log("=" * 60)
    log(f"Selected story: {selected_story.get('title', '')}")
    log(f"County: {selected_story.get('county', '')}")
    log(f"Images: {selected_story.get('image_count', 0)}")
    log(f"Story file: {STORY_FILE}")
    log(f"Script file: {SCRIPT_FILE}")
    log("")


if __name__ == "__main__":
    main()
