# ============================================================
# RIFT VALLEY WATCH
# COMPLETE MAIN PIPELINE
#
# FIXES:
# - Structured story nested source object
# - Article URL extraction
# - Real article image recovery
# - OG:image / Twitter image / article img extraction
# - RSS fallback if structured URL is missing
# - Google News used ONLY for discovery
# - Google/Facebook/placeholder images rejected
# - Local image saved to assets/source/story_image.jpg
# - Current video generator called with ONE argument
# - Handles generator output filename differences
# - Final MP4 validation
# ============================================================

import os
import re
import json
import html
import shutil
import traceback
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, quote_plus

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

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"

# Support both known generator names.
VIDEO_REEL = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
VIDEO_STANDARD = OUTPUT_DIR / "rift_valley_watch.mp4"

FINAL_VIDEO = VIDEO_REEL

for directory in (
    DATA_DIR,
    ASSETS_DIR,
    SOURCE_DIR,
    OUTPUT_DIR,
):
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# SETTINGS
# ============================================================

TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
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
]

COUNTY_ALIASES = {
    "Bomet": [
        "bomet",
        "sotik",
        "chepalungu",
        "konoin",
        "kaplong",
        "longisa",
        "sigor",
        "chebunyo",
    ],
    "Kericho": [
        "kericho",
        "ainamoi",
        "belgut",
        "bureti",
        "kipkelion",
        "litein",
        "londiani",
        "chepseon",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "bahati",
        "subukia",
        "rongai",
        "njoro",
        "kuresoi",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "chesumei",
        "emgwen",
        "aldai",
        "nandi hills",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "ainabkoi",
        "kapseret",
        "kesses",
        "soy",
        "turbo",
        "moiben",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo",
        "marakwet",
        "elgeyo-marakwet",
        "iten",
        "keiyo",
        "keiyo north",
        "keiyo south",
        "marakwet east",
        "marakwet west",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "pokot",
        "pokot south",
        "pokot central",
        "pokot north",
        "kipkomo",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "emurua dikir",
        "narok north",
        "narok south",
        "narok west",
        "narok east",
    ],
}


# ============================================================
# SOURCES
# ============================================================

TRUSTED_DOMAINS = {
    "peopledaily.digital",
    "nation.africa",
    "citizen.digital",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "kbc.co.ke",
    "standardmedia.co.ke",
    "kenyanews.go.ke",
    "president.go.ke",
    "deputypresident.go.ke",
    "parliament.go.ke",
}

BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "google.com",
    "www.google.com",
    "news.google.com",
    "youtube.com",
    "www.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
}

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
]

RSS_FEEDS = [
    (
        "People Daily",
        "https://peopledaily.digital/feed",
    ),
    (
        "Nation",
        "https://nation.africa/kenya/rss.xml",
    ),
    (
        "Citizen Digital",
        "https://citizen.digital/feed",
    ),
    (
        "The Star",
        "https://www.the-star.co.ke/rss",
    ),
    (
        "Capital FM",
        "https://www.capitalfm.co.ke/news/feed/",
    ),
    (
        "KBC",
        "https://www.kbc.co.ke/feed/",
    ),
]


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    text = html.unescape(str(value))

    try:
        text = BeautifulSoup(
            text,
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )
    except Exception:
        text = re.sub(
            r"<[^>]+>",
            " ",
            text,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def first(*values):
    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            if value.strip():
                return value.strip()
        else:
            return value

    return ""


def shorten(text, limit=250):
    text = clean(text)

    if len(text) <= limit:
        return text

    return (
        text[:limit]
        .rsplit(" ", 1)[0]
        .rstrip(" ,.;:")
        + "…"
    )


def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    text = str(value).strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            result = datetime.strptime(
                text,
                fmt,
            )

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        ).astimezone(
            timezone.utc
        )

    except Exception:
        return None


def is_recent(value, hours=96):
    dt = parse_date(value)

    if not dt:
        return False

    age = (
        datetime.now(timezone.utc)
        - dt
    )

    return (
        timedelta(hours=-2)
        <= age
        <= timedelta(hours=hours)
    )


def domain_of(url):
    if not url:
        return ""

    try:
        host = urlparse(
            str(url)
        ).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def is_blocked_domain(url):
    domain = domain_of(url)

    return any(
        domain == blocked
        or domain.endswith("." + blocked)
        for blocked in BLOCKED_DOMAINS
    )


def is_trusted_domain(url):
    domain = domain_of(url)

    return any(
        domain == trusted
        or domain.endswith("." + trusted)
        for trusted in TRUSTED_DOMAINS
    )


def publisher_from_url(url):
    domain = domain_of(url)

    mapping = {
        "peopledaily.digital": "People Daily",
        "nation.africa": "Nation",
        "citizen.digital": "Citizen Digital",
        "the-star.co.ke": "The Star",
        "capitalfm.co.ke": "Capital FM",
        "kbc.co.ke": "KBC",
        "standardmedia.co.ke": "The Standard",
        "kenyanews.go.ke": "Kenya News Agency",
        "president.go.ke": "State House",
        "deputypresident.go.ke": "Office of the Deputy President",
        "parliament.go.ke": "Parliament of Kenya",
    }

    if domain in mapping:
        return mapping[domain]

    return (
        domain
        .replace(".co.ke", "")
        .replace(".com", "")
        .replace(".org", "")
        .replace("-", " ")
        .title()
    )


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(
            f"JSON LOAD FAILED: {path}"
        )
        print(exc)
        return None


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# HTTP
# ============================================================

def fetch(url, timeout=TIMEOUT):
    if not url:
        return None

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
        print(
            f"FETCH FAILED: {url}"
        )
        print(
            f"Reason: {exc}"
        )
        return None


# ============================================================
# RECURSIVE URL EXTRACTION
#
# THIS IS THE IMPORTANT FIX.
#
# The structured story uses:
#
# "source": {
#     "name": "...",
#     "url": "..."
# }
#
# Older code expected:
#
# "source": "..."
#
# We now search the complete story recursively.
# ============================================================

def recursive_values(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key), value

            yield from recursive_values(
                value
            )

    elif isinstance(obj, list):
        for item in obj:
            yield from recursive_values(
                item
            )


def looks_like_url(value):
    if not isinstance(value, str):
        return False

    value = value.strip()

    return (
        value.startswith("http://")
        or value.startswith("https://")
    )


def extract_story_urls(story):
    urls = []
    seen = set()

    for key, value in recursive_values(
        story
    ):
        key_lower = key.lower()

        if not isinstance(
            value,
            str,
        ):
            continue

        value = value.strip()

        if not looks_like_url(value):
            continue

        if value in seen:
            continue

        # Image URL is useful too, but article URL
        # gets priority later.
        seen.add(value)

        urls.append(
            {
                "key": key_lower,
                "url": value,
            }
        )

    # Prioritize article/source URL.
    priority = []

    for item in urls:
        key = item["key"]

        if any(
            token in key
            for token in (
                "article",
                "source",
                "story",
                "link",
                "url",
            )
        ):
            priority.append(item)

    remainder = [
        item
        for item in urls
        if item not in priority
    ]

    return priority + remainder


def extract_article_url(story):
    candidates = []

    # Direct fields.
    for key in (
        "article_url",
        "articleUrl",
        "url",
        "link",
        "source_url",
        "sourceUrl",
        "story_url",
        "storyUrl",
    ):
        value = story.get(key)

        if looks_like_url(value):
            candidates.append(value)

    # Nested source object.
    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        for key in (
            "url",
            "link",
            "article_url",
            "articleUrl",
        ):
            value = source.get(key)

            if looks_like_url(value):
                candidates.append(value)

    # Recursive fallback.
    for item in extract_story_urls(
        story
    ):
        candidates.append(
            item["url"]
        )

    seen = set()

    for url in candidates:
        if url in seen:
            continue

        seen.add(url)

        if is_blocked_domain(url):
            continue

        # Avoid treating obvious image files
        # as the article URL.
        path = urlparse(
            url
        ).path.lower()

        if any(
            path.endswith(ext)
            for ext in (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".gif",
            )
        ):
            continue

        return url

    return ""


def extract_story_image_urls(story):
    candidates = []
    seen = set()

    # Explicit common fields.
    for key in (
        "image_url",
        "imageUrl",
        "image",
        "thumbnail",
        "thumbnail_url",
        "thumbnailUrl",
        "photo",
        "photo_url",
        "photoUrl",
        "local_image",
        "image_path",
    ):
        value = story.get(key)

        if isinstance(
            value,
            str,
        ) and value.strip():
            candidates.append(
                value.strip()
            )

    # Nested source.
    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        for key in (
            "image",
            "image_url",
            "imageUrl",
            "thumbnail",
            "thumbnail_url",
        ):
            value = source.get(key)

            if isinstance(
                value,
                str,
            ) and value.strip():
                candidates.append(
                    value.strip()
                )

    # Recursive.
    for item in extract_story_urls(
        story
    ):
        key = item["key"]

        if any(
            token in key
            for token in (
                "image",
                "photo",
                "thumbnail",
                "picture",
                "media",
            )
        ):
            candidates.append(
                item["url"]
            )

    for value in candidates:
        if not looks_like_url(
            value
        ):
            continue

        if value in seen:
            continue

        seen.add(value)

        if is_blocked_domain(
            value
        ):
            continue

        if not image_url_is_bad(
            value
        ):
            yield value


# ============================================================
# COUNTY
# ============================================================

def detect_county(
    title="",
    summary="",
    content="",
    url="",
):
    text = " ".join(
        [
            clean(title),
            clean(summary),
            clean(content),
            clean(url),
        ]
    ).lower()

    best = None
    best_score = 0

    for county, aliases in COUNTY_ALIASES.items():
        score = 0

        for alias in aliases:
            if re.search(
                r"\b"
                + re.escape(
                    alias.lower()
                )
                + r"\b",
                text,
            ):
                score += 1

        if score > best_score:
            best_score = score
            best = county

    return best


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_url_is_bad(url):
    if not url:
        return True

    lower = str(url).lower()

    if lower.startswith(
        "data:"
    ):
        return True

    return any(
        term in lower
        for term in BAD_IMAGE_TERMS
    )


def validate_image_file(path):
    path = Path(path)

    if not path.exists():
        return False

    if path.stat().st_size < 5000:
        return False

    try:
        from PIL import Image

        with Image.open(
            path
        ) as image:
            image.verify()

        with Image.open(
            path
        ) as image:
            width, height = image.size

        if width < 400:
            return False

        if height < 300:
            return False

        if width * height < 250000:
            return False

        return True

    except Exception as exc:
        print(
            f"IMAGE VALIDATION FAILED: {exc}"
        )
        return False


def save_image_as_jpeg(
    raw_bytes,
    destination=IMAGE_FILE,
):
    try:
        from io import BytesIO
        from PIL import Image

        image = Image.open(
            BytesIO(raw_bytes)
        )

        image.load()

        width, height = image.size

        print(
            f"Downloaded image dimensions: "
            f"{width}x{height}"
        )

        if width < 400:
            print(
                "IMAGE REJECTED: width < 400"
            )
            return False

        if height < 300:
            print(
                "IMAGE REJECTED: height < 300"
            )
            return False

        if width * height < 250000:
            print(
                "IMAGE REJECTED: too small"
            )
            return False

        image = image.convert(
            "RGB"
        )

        image.save(
            destination,
            "JPEG",
            quality=95,
            optimize=True,
        )

        return validate_image_file(
            destination
        )

    except Exception as exc:
        print(
            "IMAGE CONVERSION FAILED:"
        )
        print(exc)
        return False


def download_image(
    image_url,
):
    if not image_url:
        return False

    if image_url_is_bad(
        image_url
    ):
        print(
            f"REJECTED IMAGE URL: "
            f"{image_url}"
        )
        return False

    print(
        f"TRYING IMAGE: {image_url}"
    )

    try:
        response = requests.get(
            image_url,
            headers={
                **HEADERS,
                "Accept": (
                    "image/avif,"
                    "image/webp,"
                    "image/apng,"
                    "image/svg+xml,"
                    "image/*,*/*;q=0.8"
                ),
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = response.url

        if image_url_is_bad(
            final_url
        ):
            print(
                "IMAGE REDIRECT REJECTED"
            )
            return False

        content_type = (
            response.headers
            .get(
                "content-type",
                "",
            )
            .lower()
        )

        if (
            "image"
            not in content_type
            and not response.content.startswith(
                (
                    b"\xff\xd8\xff",
                    b"\x89PNG",
                    b"GIF8",
                    b"RIFF",
                )
            )
        ):
            print(
                f"NOT AN IMAGE: "
                f"{content_type}"
            )
            return False

        if save_image_as_jpeg(
            response.content
        ):
            print(
                f"REAL IMAGE SAVED: "
                f"{IMAGE_FILE}"
            )
            return True

    except Exception as exc:
        print(
            f"IMAGE DOWNLOAD FAILED: "
            f"{image_url}"
        )
        print(exc)

    return False


# ============================================================
# ARTICLE IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(
    soup,
    base_url,
):
    candidates = []

    if not soup:
        return candidates

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    selectors = [
        (
            "meta",
            {"property": "og:image"},
        ),
        (
            "meta",
            {"property": "og:image:url"},
        ),
        (
            "meta",
            {"name": "og:image"},
        ),
        (
            "meta",
            {"name": "twitter:image"},
        ),
        (
            "meta",
            {"property": "twitter:image"},
        ),
        (
            "meta",
            {"itemprop": "image"},
        ),
    ]

    for tag_name, attrs in selectors:
        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):
            value = tag.get(
                "content"
            )

            if value:
                candidates.append(
                    urljoin(
                        base_url,
                        value,
                    )
                )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        raw = script.string

        if not raw:
            continue

        try:
            data = json.loads(
                raw
            )

        except Exception:
            continue

        def inspect_json_ld(obj):
            if isinstance(
                obj,
                dict,
            ):
                for key, value in obj.items():
                    key_lower = str(
                        key
                    ).lower()

                    if (
                        key_lower
                        in {
                            "image",
                            "thumbnailurl",
                            "contenturl",
                        }
                    ):
                        if isinstance(
                            value,
                            str,
                        ):
                            candidates.append(
                                urljoin(
                                    base_url,
                                    value,
                                )
                            )

                        elif isinstance(
                            value,
                            list,
                        ):
                            for item in value:
                                if isinstance(
                                    item,
                                    str,
                                ):
                                    candidates.append(
                                        urljoin(
                                            base_url,
                                            item,
                                        )
                                    )

                                elif isinstance(
                                    item,
                                    dict,
                                ):
                                    nested = item.get(
                                        "url"
                                    )

                                    if nested:
                                        candidates.append(
                                            urljoin(
                                                base_url,
                                                nested,
                                            )
                                        )

                    inspect_json_ld(
                        value
                    )

            elif isinstance(
                obj,
                list,
            ):
                for item in obj:
                    inspect_json_ld(
                        item
                    )

        inspect_json_ld(
            data
        )

    # --------------------------------------------------------
    # LINK IMAGE
    # --------------------------------------------------------

    for link in soup.find_all(
        "link",
        href=True,
    ):
        rel = " ".join(
            link.get(
                "rel",
                [],
            )
        ).lower()

        if (
            "image_src"
            in rel
        ):
            candidates.append(
                urljoin(
                    base_url,
                    link["href"],
                )
            )

    # --------------------------------------------------------
    # ARTICLE IMG TAGS
    # --------------------------------------------------------

    containers = []

    article = soup.find(
        "article"
    )

    if article:
        containers.append(
            article
        )

    main = soup.find(
        "main"
    )

    if main:
        containers.append(
            main
        )

    # Whole page last.
    containers.append(
        soup
    )

    for container in containers:
        for img in container.find_all(
            "img"
        ):
            for attr in (
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-lazy",
                "data-original-src",
            ):
                value = img.get(
                    attr
                )

                if value:
                    candidates.append(
                        urljoin(
                            base_url,
                            value,
                        )
                    )

            srcset = img.get(
                "srcset"
            )

            if srcset:
                for item in srcset.split(
                    ","
                ):
                    url_value = (
                        item.strip()
                        .split(" ")[0]
                    )

                    if url_value:
                        candidates.append(
                            urljoin(
                                base_url,
                                url_value,
                            )
                        )

    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    final = []
    seen = set()

    for candidate in candidates:
        candidate = str(
            candidate
        ).strip()

        if not candidate:
            continue

        if candidate in seen:
            continue

        seen.add(
            candidate
        )

        if image_url_is_bad(
            candidate
        ):
            continue

        final.append(
            candidate
        )

    return final


def recover_from_article(
    article_url,
):
    if not article_url:
        print(
            "No article URL available."
        )
        return False

    if is_blocked_domain(
        article_url
    ):
        print(
            "Article URL is blocked."
        )
        return False

    print("")
    print(
        "=" * 70
    )
    print(
        "ARTICLE IMAGE RECOVERY"
    )
    print(
        "=" * 70
    )

    print(
        f"ARTICLE: {article_url}"
    )

    response = fetch(
        article_url
    )

    if not response:
        return False

    final_url = response.url

    try:
        soup = BeautifulSoup(
            response.content,
            "html.parser",
        )
    except Exception:
        return False

    candidates = extract_image_candidates(
        soup,
        final_url,
    )

    print(
        f"IMAGE CANDIDATES: "
        f"{len(candidates)}"
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"[{index}] {candidate}"
        )

    for candidate in candidates:
        if download_image(
            candidate
        ):
            return True

    return False


# ============================================================
# RSS DISCOVERY
# ============================================================

def parse_rss(
    source_name,
    feed_url,
):
    results = []

    print(
        f"Checking {source_name}"
    )

    response = fetch(
        feed_url
    )

    if not response:
        return results

    try:
        feed = feedparser.parse(
            response.content
        )
    except Exception:
        return results

    for entry in feed.entries[:60]:
        title = clean(
            entry.get(
                "title",
                "",
            )
        )

        link = clean(
            entry.get(
                "link",
                "",
            )
        )

        summary = clean(
            first(
                entry.get(
                    "summary"
                ),
                entry.get(
                    "description"
                ),
            )
        )

        published = first(
            entry.get(
                "published"
            ),
            entry.get(
                "updated"
            ),
        )

        if not title or not link:
            continue

        if is_blocked_domain(
            link
        ):
            continue

        county = detect_county(
            title,
            summary,
            "",
            link,
        )

        if not county:
            continue

        if published and not is_recent(
            published,
            hours=120,
        ):
            continue

        results.append(
            {
                "title": title,
                "summary": summary,
                "url": link,
                "source": source_name,
                "published": published,
                "county": county,
            }
        )

    return results


def discover_from_rss(
    title="",
    county="",
):
    candidates = []

    for source_name, feed_url in RSS_FEEDS:
        candidates.extend(
            parse_rss(
                source_name,
                feed_url,
            )
        )

    if not candidates:
        return None

    title_words = set(
        re.findall(
            r"[a-z0-9]+",
            clean(title).lower(),
        )
    )

    best = None
    best_score = -1

    for item in candidates:
        item_text = (
            item["title"]
            + " "
            + item["summary"]
        ).lower()

        score = 0

        if county and (
            county.lower()
            in item_text
        ):
            score += 20

        for word in title_words:
            if len(word) >= 4 and word in item_text:
                score += 2

        if is_trusted_domain(
            item["url"]
        ):
            score += 10

        if score > best_score:
            best_score = score
            best = item

    return best


# ============================================================
# STRUCTURED STORY
# ============================================================

def story_quality_gate(
    story
):
    if not isinstance(
        story,
        dict,
    ):
        return False, (
            "Story is not a dictionary."
        )

    title = clean(
        first(
            story.get(
                "title"
            ),
            story.get(
                "headline"
            ),
        )
    )

    summary = clean(
        first(
            story.get(
                "summary"
            ),
            story.get(
                "description"
            ),
            story.get(
                "content"
            ),
        )
    )

    if len(title) < 15:
        return False, (
            "Title is missing or too short."
        )

    if title.lower() in {
        "google news",
        "facebook",
        "news",
    }:
        return False, (
            "Invalid generic title."
        )

    if len(summary) < 30:
        # Structured story may use verified facts
        # instead of a conventional summary.
        if not story.get(
            "verified_facts"
        ):
            return False, (
                "Story contains insufficient content."
            )

    combined = (
        title
        + " "
        + summary
    ).lower()

    for bad in (
        "google news app",
        "sign in to google",
        "see more stories",
        "news.google.com",
    ):
        if bad in combined:
            return False, (
                f"Blocked boilerplate: {bad}"
            )

    county = first(
        story.get(
            "county"
        ),
        detect_county(
            title,
            summary,
            clean(
                story.get(
                    "content",
                    "",
                )
            ),
            extract_article_url(
                story
            ),
        ),
    )

    if not county:
        return False, (
            "No Rift Valley county detected."
        )

    return True, "OK"


def load_structured_story():
    story = load_json(
        STORY_FILE
    )

    if not story:
        return None

    ok, reason = story_quality_gate(
        story
    )

    if not ok:
        print(
            f"STRUCTURED STORY REJECTED: "
            f"{reason}"
        )
        return None

    print("")
    print(
        "=" * 70
    )
    print(
        "STRUCTURED STORY FOUND"
    )
    print(
        "=" * 70
    )

    print(
        clean(
            first(
                story.get(
                    "title"
                ),
                story.get(
                    "headline"
                ),
            )
        )
    )

    article_url = extract_article_url(
        story
    )

    print(
        f"ARTICLE URL: "
        f"{article_url or 'NOT FOUND'}"
    )

    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        print(
            f"SOURCE: "
            f"{source.get('name', '')}"
        )
    else:
        print(
            f"SOURCE: "
            f"{clean(source)}"
        )

    return story


# ============================================================
# IMAGE RECOVERY FOR STRUCTURED STORY
# ============================================================

def ensure_story_image(
    story
):
    print("")
    print(
        "=" * 70
    )
    print(
        "ENSURING REAL ARTICLE IMAGE"
    )
    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # 1. Existing local image
    # --------------------------------------------------------

    if validate_image_file(
        IMAGE_FILE
    ):
        print(
            "VALID LOCAL IMAGE ALREADY EXISTS."
        )
        return True

    if IMAGE_FILE.exists():
        try:
            IMAGE_FILE.unlink()
        except Exception:
            pass

    # --------------------------------------------------------
    # 2. Explicit image URL fields
    # --------------------------------------------------------

    image_urls = list(
        extract_story_image_urls(
            story
        )
    )

    if image_urls:
        print(
            f"STRUCTURED IMAGE URLS: "
            f"{len(image_urls)}"
        )

        for image_url in image_urls:
            if download_image(
                image_url
            ):
                story["image_url"] = (
                    image_url
                )
                story["local_image"] = str(
                    IMAGE_FILE
                )
                story["image_path"] = str(
                    IMAGE_FILE
                )
                return True

    # --------------------------------------------------------
    # 3. Extract article URL correctly
    # --------------------------------------------------------

    article_url = extract_article_url(
        story
    )

    # --------------------------------------------------------
    # 4. Article page recovery
    # --------------------------------------------------------

    if article_url:
        if recover_from_article(
            article_url
        ):
            story["article_url"] = (
                article_url
            )
            story["local_image"] = str(
                IMAGE_FILE
            )
            story["image_path"] = str(
                IMAGE_FILE
            )
            story["image_verified"] = True
            return True

    # --------------------------------------------------------
    # 5. RSS fallback
    #
    # This is discovery only.
    # We never use Google News as publisher.
    # --------------------------------------------------------

    title = clean(
        first(
            story.get(
                "title"
            ),
            story.get(
                "headline"
            ),
        )
    )

    county = first(
        story.get(
            "county"
        ),
        detect_county(
            title,
            story.get(
                "summary",
                "",
            ),
        ),
    )

    print("")
    print(
        "DIRECT ARTICLE IMAGE RECOVERY FAILED."
    )
    print(
        "Trying trusted RSS discovery fallback..."
    )

    fallback = discover_from_rss(
        title=title,
        county=county,
    )

    if fallback:
        fallback_url = fallback.get(
            "url",
            "",
        )

        print(
            f"FALLBACK ARTICLE: "
            f"{fallback_url}"
        )

        if (
            fallback_url
            and not is_blocked_domain(
                fallback_url
            )
        ):
            if recover_from_article(
                fallback_url
            ):
                story["article_url"] = (
                    fallback_url
                )
                story["url"] = (
                    fallback_url
                )
                story["source"] = (
                    fallback.get(
                        "source",
                        publisher_from_url(
                            fallback_url
                        ),
                    )
                )
                story["local_image"] = str(
                    IMAGE_FILE
                )
                story["image_path"] = str(
                    IMAGE_FILE
                )
                story["image_verified"] = True
                return True

    # --------------------------------------------------------
    # Nothing worked
    # --------------------------------------------------------

    print("")
    print(
        "NO REAL ARTICLE IMAGE COULD BE RECOVERED."
    )

    return False


# ============================================================
# NORMALIZE STORY
# ============================================================

def normalize_story(
    story
):
    title = clean(
        first(
            story.get(
                "title"
            ),
            story.get(
                "headline"
            ),
        )
    )

    summary = clean(
        first(
            story.get(
                "summary"
            ),
            story.get(
                "description"
            ),
        )
    )

    content = clean(
        first(
            story.get(
                "content"
            ),
            summary,
        )
    )

    article_url = extract_article_url(
        story
    )

    county = first(
        story.get(
            "county"
        ),
        detect_county(
            title,
            summary,
            content,
            article_url,
        ),
    )

    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        source_name = clean(
            first(
                source.get(
                    "name"
                ),
                publisher_from_url(
                    article_url
                ),
            )
        )

        source_url = clean(
            first(
                source.get(
                    "url"
                ),
                article_url,
            )
        )

        source_obj = dict(
            source
        )

        source_obj["name"] = (
            source_name
        )

        source_obj["url"] = (
            source_url
        )

    else:
        source_name = clean(
            first(
                source,
                publisher_from_url(
                    article_url
                ),
            )
        )

        source_obj = {
            "name": source_name,
            "url": article_url,
        }

    normalized = dict(
        story
    )

    normalized.update(
        {
            "title": title,
            "headline": title,
            "summary": summary,
            "content": content,
            "county": county,
            "article_url": article_url,
            "url": article_url,
            "source": source_obj,
            "publisher": source_name,
            "local_image": str(
                IMAGE_FILE
            ),
            "image_path": str(
                IMAGE_FILE
            ),
        }
    )

    return normalized


# ============================================================
# SCRIPT
# ============================================================

def build_script(
    story
):
    title = clean(
        story.get(
            "title"
        )
    )

    county = clean(
        story.get(
            "county"
        )
    )

    summary = clean(
        story.get(
            "summary"
        )
    )

    content = clean(
        story.get(
            "content"
        )
    )

    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        source_name = clean(
            source.get(
                "name"
            )
        )
    else:
        source_name = clean(
            source
        )

    if not summary:
        summary = shorten(
            content,
            450,
        )

    narration_parts = [
        (
            "Rift Valley Watch. "
            f"Here is the latest update from "
            f"{county}."
        ),
        f"{title}.",
    ]

    if summary:
        narration_parts.append(
            shorten(
                summary,
                430,
            )
        )

    if source_name:
        narration_parts.append(
            f"The report is from "
            f"{source_name}."
        )

    narration = " ".join(
        narration_parts
    )

    script = {
        "title": title,
        "county": county,
        "source": source_name,
        "source_url": story.get(
            "article_url",
            "",
        ),
        "narration": narration,
        "duration_target": 35,
        "local_image": str(
            IMAGE_FILE
        ),
    }

    save_json(
        SCRIPT_FILE,
        script,
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    return script


# ============================================================
# VIDEO GENERATOR
# ============================================================

def find_generated_video():
    candidates = [
        VIDEO_REEL,
        VIDEO_STANDARD,
        OUTPUT_DIR
        / "rift_valley_watch_reel_final.mp4",
        OUTPUT_DIR
        / "rift_valley_watch_final.mp4",
    ]

    for path in candidates:
        if (
            path.exists()
            and path.stat().st_size > 100000
        ):
            return path

    # Last-resort search.
    for path in OUTPUT_DIR.glob(
        "*.mp4"
    ):
        if (
            path.exists()
            and path.stat().st_size > 100000
        ):
            return path

    return None


def generate_video(
    story
):
    print("")
    print(
        "=" * 70
    )
    print(
        "VIDEO GENERATION"
    )
    print(
        "=" * 70
    )

    if not validate_image_file(
        IMAGE_FILE
    ):
        raise RuntimeError(
            "No valid article image exists before "
            "video generation."
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # Current rift_valley_video_generator.py
    # accepts ONE positional argument.
    # --------------------------------------------------------

    from rift_valley_video_generator import (
        generate_video as video_generator
    )

    # The generator reads the normalized story,
    # including nested source information.
    result = video_generator(
        story
    )

    print(
        f"Generator returned: {result}"
    )

    generated = find_generated_video()

    if generated is None:
        raise RuntimeError(
            "Video generator finished but no usable "
            "MP4 was found in output/."
        )

    # Ensure our final filename is consistent.
    if generated.resolve() != (
        FINAL_VIDEO.resolve()
    ):
        shutil.copy2(
            generated,
            FINAL_VIDEO,
        )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return FINAL_VIDEO


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def ffprobe(
    path
):
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
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe failed:\n"
            + result.stderr
        )

    return json.loads(
        result.stdout
    )


def final_video_qc(
    path
):
    print("")
    print(
        "=" * 70
    )
    print(
        "FINAL VIDEO QC"
    )
    print(
        "=" * 70
    )

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if path.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    info = ffprobe(
        path
    )

    streams = info.get(
        "streams",
        [],
    )

    video = next(
        (
            item
            for item in streams
            if item.get(
                "codec_type"
            )
            == "video"
        ),
        None,
    )

    audio = next(
        (
            item
            for item in streams
            if item.get(
                "codec_type"
            )
            == "audio"
        ),
        None,
    )

    if not video:
        raise RuntimeError(
            "MP4 has no video stream."
        )

    if not audio:
        raise RuntimeError(
            "MP4 has no audio stream."
        )

    width = int(
        video.get(
            "width",
            0,
        )
    )

    height = int(
        video.get(
            "height",
            0,
        )
    )

    codec = video.get(
        "codec_name",
        "",
    )

    audio_codec = audio.get(
        "codec_name",
        "",
    )

    duration = float(
        info.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
    )

    print(
        f"Resolution: "
        f"{width}x{height}"
    )

    print(
        f"Video codec: "
        f"{codec}"
    )

    print(
        f"Audio codec: "
        f"{audio_codec}"
    )

    print(
        f"Duration: "
        f"{duration:.2f}s"
    )

    if (
        width != 1080
        or height != 1920
    ):
        raise RuntimeError(
            f"Wrong resolution: "
            f"{width}x{height}"
        )

    if codec != "h264":
        raise RuntimeError(
            f"Wrong video codec: "
            f"{codec}"
        )

    if audio_codec != "aac":
        raise RuntimeError(
            f"Wrong audio codec: "
            f"{audio_codec}"
        )

    # Accept a reasonable short-form news runtime.
    if not (
        20 <= duration <= 45
    ):
        raise RuntimeError(
            f"Unexpected video duration: "
            f"{duration:.2f}s"
        )

    print(
        "FINAL VIDEO QC: PASSED"
    )


# ============================================================
# REPORT
# ============================================================

def report_files():
    print("")
    print(
        "=" * 70
    )
    print(
        "FINAL FILE CHECK"
    )
    print(
        "=" * 70
    )

    for directory in (
        DATA_DIR,
        SOURCE_DIR,
        OUTPUT_DIR,
    ):
        print("")
        print(
            f"Directory: {directory}"
        )

        if not directory.exists():
            print(
                "DIRECTORY DOES NOT EXIST"
            )
            continue

        files = sorted(
            directory.iterdir()
        )

        if not files:
            print(
                "EMPTY"
            )
            continue

        for item in files:
            if item.is_file():
                try:
                    print(
                        f"  {item.name} "
                        f"({item.stat().st_size:,} bytes)"
                    )
                except Exception:
                    print(
                        f"  {item.name}"
                    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print(
        "=" * 70
    )
    print(
        "RIFT VALLEY WATCH"
    )
    print(
        "AUTOMATED REGIONAL NEWS VIDEO PIPELINE"
    )
    print(
        "=" * 70
    )

    try:
        # ----------------------------------------------------
        # STEP 1
        # LOAD STRUCTURED STORY
        # ----------------------------------------------------

        story = load_structured_story()

        if story is None:
            raise RuntimeError(
                "No valid structured story was available."
            )

        # ----------------------------------------------------
        # STEP 2
        # NORMALIZE BEFORE IMAGE RECOVERY
        # ----------------------------------------------------

        story = normalize_story(
            story
        )

        print("")
        print(
            f"Story: "
            f"{story.get('title')}"
        )

        print(
            f"County: "
            f"{story.get('county')}"
        )

        print(
            f"Article URL: "
            f"{story.get('article_url')}"
        )

        source = story.get(
            "source"
        )

        if isinstance(
            source,
            dict,
        ):
            print(
                f"Source: "
                f"{source.get('name')}"
            )

            print(
                f"Source URL: "
                f"{source.get('url')}"
            )

        # ----------------------------------------------------
        # STEP 3
        # REAL IMAGE RECOVERY
        # ----------------------------------------------------

        if not ensure_story_image(
            story
        ):
            raise RuntimeError(
                "No article image available at "
                f"{IMAGE_FILE}"
            )

        # ----------------------------------------------------
        # STEP 4
        # FINAL IMAGE VALIDATION
        # ----------------------------------------------------

        if not validate_image_file(
            IMAGE_FILE
        ):
            raise RuntimeError(
                "Recovered image failed final validation."
            )

        story["local_image"] = str(
            IMAGE_FILE
        )

        story["image_path"] = str(
            IMAGE_FILE
        )

        story["image_verified"] = True

        # ----------------------------------------------------
        # STEP 5
        # SCRIPT
        # ----------------------------------------------------

        build_script(
            story
        )

        # ----------------------------------------------------
        # STEP 6
        # SAVE SELECTED STORY
        # ----------------------------------------------------

        save_json(
            SELECTED_STORY_FILE,
            story,
        )

        print("")
        print(
            "SELECTED STORY SAVED."
        )

        # ----------------------------------------------------
        # STEP 7
        # VIDEO
        # ----------------------------------------------------

        video = generate_video(
            story
        )

        # ----------------------------------------------------
        # STEP 8
        # FINAL QC
        # ----------------------------------------------------

        final_video_qc(
            video
        )

        # ----------------------------------------------------
        # STEP 9
        # REPORT
        # ----------------------------------------------------

        report_files()

        print("")
        print(
            "=" * 70
        )
        print(
            "RIFT VALLEY WATCH SUCCESS"
        )
        print(
            "=" * 70
        )

        print(
            f"FINAL MP4: "
            f"{FINAL_VIDEO}"
        )

        print(
            f"IMAGE: "
            f"{IMAGE_FILE}"
        )

        return 0

    except Exception as exc:
        print("")
        print(
            "=" * 70
        )
        print(
            "RIFT VALLEY WATCH FAILED"
        )
        print(
            "=" * 70
        )

        print(
            f"{type(exc).__name__}: "
            f"{exc}"
        )

        print("")
        traceback.print_exc()

        report_files()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
