from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from io import BytesIO

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# MAIN CONTROLLER
#
# VERSION:
# RVW_MAIN_V12_MULTI_PHOTO_JSON_STABLE
#
# PURPOSE
# - Discover real Rift Valley news
# - Select one strong story
# - Collect multiple real article photos
# - Save selected_story.json BEFORE generator starts
# - Save selected_script.json BEFORE generator starts
# - Launch RVW_VIDEO_V22
# - Verify final MP4
# ============================================================


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ROOT / "audio"
VIDEO_WORK_DIR = ASSETS_DIR / "video_work"

SELECTED_STORY = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ============================================================
# COUNTIES
# ============================================================

COUNTIES = {
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chepalungu",
        "Konoin",
    ],

    "Kericho": [
        "Kericho",
        "Litein",
        "Kipkelion",
        "Ainamoi",
    ],

    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Mosop",
        "Aldai",
    ],

    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Turbo",
    ],

    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Elgeyo",
        "Marakwet",
        "Iten",
        "Keiyo",
    ],

    "West Pokot": [
        "West Pokot",
        "Pokot",
        "Kapenguria",
        "Kacheliba",
    ],

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Transmara",
    ],
}


# ============================================================
# NEWS SOURCES
# ============================================================

PUBLISHER_PAGES = [
    "https://citizen.digital/",
    "https://www.the-star.co.ke/news/",
    "https://www.kbc.co.ke/",
    "https://nation.africa/kenya/news",
]


APPROVED_DOMAINS = [
    "citizen.digital",
    "the-star.co.ke",
    "kbc.co.ke",
    "nation.africa",
]


BLOCKED_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "telegram.me",
    "t.me",
    "whatsapp.com",
    "google.com",
    "news.google.com",
]


# ============================================================
# BAD IMAGE TERMS
# ============================================================

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
    "google_news",
    "googlelogo",
    "google-logo",
    "favicon",
    "icon",
    "logo",
    "placeholder",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "avatar",
    "sprite",
    "app-icon",
    "app_icon",
    "loading",
    "spinner",
    "advert",
    "advertisement",
    "banner",
    "world-cup",
    "worldcup",
    "profile",
    "generic",
]


# ============================================================
# REQUEST HEADERS
# ============================================================

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
        "application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,"
        "image/svg+xml,image/*,*/*;q=0.8"
    ),
}


SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# SETTINGS
# ============================================================

MAX_ARTICLES_PER_SOURCE = 60
MAX_SELECTED_CANDIDATES = 20

MAX_ARTICLE_IMAGES = 8
MAX_STORED_IMAGE_URLS = 8

MIN_ARTICLE_BODY_WORDS = 45

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

VIDEO_TIMEOUT_SECONDS = 900


# ============================================================
# LOGGING
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = html.unescape(value)

    value = value.replace(
        "\xa0",
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# JSON
# ============================================================

def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.flush()

    temp_path.replace(path)


# ============================================================
# DOMAIN
# ============================================================

def domain(url):
    try:

        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
            .removeprefix("www.")
        )

    except Exception:
        return ""


def blocked(url):
    host = domain(url)

    if not host:
        return True

    return any(
        host == x
        or host.endswith("." + x)
        for x in BLOCKED_DOMAINS
    )


def approved(url):
    host = domain(url)

    if not host:
        return False

    if blocked(url):
        return False

    return any(
        host == x
        or host.endswith("." + x)
        for x in APPROVED_DOMAINS
    )


# ============================================================
# COUNTY DETECTION
# ============================================================

def county_from_text(text):
    text = clean(text).lower()

    best = ""
    best_score = 0

    for county, aliases in COUNTIES.items():

        score = 0

        for alias in aliases:

            if re.search(
                r"\b"
                + re.escape(alias.lower())
                + r"\b",
                text,
            ):
                score += 1

        if score > best_score:
            best = county
            best_score = score

    return best


# ============================================================
# HTTP FETCH
# ============================================================

def fetch(
    url,
    accept_html=True,
    timeout=25,
):
    try:

        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code != 200:
            log(
                f"FETCH HTTP {response.status_code}: {url}"
            )

            return None

        if accept_html:

            content_type = (
                response.headers
                .get(
                    "content-type",
                    "",
                )
                .lower()
            )

            if "html" not in content_type:
                return None

        return response

    except Exception as exc:

        log(
            f"FETCH FAILED: {url} | {exc}"
        )

        return None


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    title = clean(title)

    publishers = [
        "People Daily",
        "The Star",
        "Citizen Digital",
        "Citizen",
        "The Standard",
        "Daily Nation",
        "Nation",
        "Capital News",
        "KBC",
        "NTV Kenya",
        "TV47",
    ]

    for publisher in publishers:

        title = re.sub(
            r"\s*[-|–—:]\s*"
            + re.escape(publisher)
            + r"\s*$",
            "",
            title,
            flags=re.I,
        )

    return clean(title)


# ============================================================
# REMOVE METADATA
# ============================================================

def remove_metadata(text):
    text = clean(text)

    patterns = [
        r"\bGoogle News\b",
        r"\bPeople Daily\b",
        r"\bThe Star\b",
        r"\bCitizen Digital\b",
        r"\bThe Standard\b",
        r"\bDaily Nation\b",
        r"\bCapital News\b",
        r"\bKBC\b",
        r"\bNTV Kenya\b",
        r"\bTV47\b",
        r"\bFacebook\b",
        r"\bInstagram\b",
        r"\bTwitter\b",
        r"\bYouTube\b",
        r"\bTikTok\b",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# LINK DISCOVERY
# ============================================================

def discover_links(page_url):
    response = fetch(page_url)

    if not response:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    result = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):

        raw_href = clean(
            a.get("href")
        )

        if not raw_href:
            continue

        url = urljoin(
            page_url,
            raw_href,
        )

        url = url.split("#")[0]

        if not approved(url):
            continue

        if url == page_url:
            continue

        if url in seen:
            continue

        path = (
            urlparse(url)
            .path
            .lower()
            .rstrip("/")
        )

        excluded_paths = {
            "",
            "/",
            "/news",
            "/search",
            "/category/news",
        }

        if path in excluded_paths:
            continue

        text = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        county = county_from_text(
            text + " " + url
        )

        seen.add(url)

        result.append(
            {
                "url": url,
                "text": text,
                "county": county,
            }
        )

    return result


# ============================================================
# IMAGE CANDIDATE ADDER
# ============================================================

def add_image_candidate(
    result,
    seen,
    value,
    article_url,
):
    value = clean(value)

    if not value:
        return

    if value.startswith("data:"):
        return

    value = urljoin(
        article_url,
        value,
    )

    if not value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return

    low = value.lower()

    if any(
        term in low
        for term in BAD_IMAGE_TERMS
    ):
        return

    # Ignore obvious tracking pixels.
    if (
        "pixel" in low
        or "tracking" in low
    ):
        return

    normalized = value.strip()

    if normalized not in seen:

        seen.add(normalized)

        result.append(
            normalized
        )


# ============================================================
# RECURSIVE JSON IMAGE SCANNER
# ============================================================

def scan_json_images(
    value,
    result,
    seen,
    article_url,
):
    if isinstance(value, str):

        if (
            value.startswith("http://")
            or value.startswith("https://")
        ):
            add_image_candidate(
                result,
                seen,
                value,
                article_url,
            )

        return

    if isinstance(value, list):

        for item in value:

            scan_json_images(
                item,
                result,
                seen,
                article_url,
            )

        return

    if isinstance(value, dict):

        preferred_keys = [
            "image",
            "images",
            "thumbnailUrl",
            "contentUrl",
            "url",
            "src",
            "srcset",
        ]

        for key in preferred_keys:

            if key in value:

                scan_json_images(
                    value[key],
                    result,
                    seen,
                    article_url,
                )


# ============================================================
# GET IMAGE CANDIDATES FROM ARTICLE
# ============================================================

def get_image_candidates(
    soup,
    article_url,
):
    result = []
    seen = set()

    # --------------------------------------------------------
    # OpenGraph / Twitter
    # --------------------------------------------------------

    meta_attributes = [
        {
            "property": "og:image"
        },
        {
            "property": "og:image:url"
        },
        {
            "property": "og:image:secure_url"
        },
        {
            "name": "twitter:image"
        },
        {
            "name": "twitter:image:src"
        },
        {
            "property": "twitter:image"
        },
    ]

    for attrs in meta_attributes:

        for tag in soup.find_all(
            "meta",
            attrs=attrs,
        ):

            add_image_candidate(
                result,
                seen,
                tag.get("content"),
                article_url,
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        raw = (
            script.string
            or script.get_text()
            or ""
        )

        if not raw:
            continue

        try:

            data = json.loads(raw)

            scan_json_images(
                data,
                result,
                seen,
                article_url,
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # Article/main images
    # --------------------------------------------------------

    containers = (
        soup.find_all("article")
        or soup.find_all("main")
        or [soup]
    )

    for container in containers:

        for img in container.find_all(
            "img"
        ):

            attributes = [
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-original-src",
                "data-fallback-src",
                "data-lazy",
            ]

            for key in attributes:

                add_image_candidate(
                    result,
                    seen,
                    img.get(key),
                    article_url,
                )

            srcset = (
                img.get("srcset")
                or img.get("data-srcset")
            )

            if srcset:

                for item in srcset.split(","):

                    item = item.strip()

                    if not item:
                        continue

                    candidate = item.split(
                        " "
                    )[0]

                    add_image_candidate(
                        result,
                        seen,
                        candidate,
                        article_url,
                    )

    return result


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    referer=None,
):
    if any(
        term in url.lower()
        for term in BAD_IMAGE_TERMS
    ):
        return None

    headers = {
        **HEADERS,
        "Accept": (
            "image/avif,image/webp,"
            "image/apng,image/*,*/*;q=0.8"
        ),
    }

    if referer:
        headers["Referer"] = referer

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        data = response.content

        if len(data) < 20000:
            return None

        content_type = (
            response.headers
            .get(
                "content-type",
                "",
            )
            .lower()
        )

        if (
            not content_type.startswith(
                "image/"
            )
            and not content_type.endswith(
                "octet-stream"
            )
        ):
            return None

        image = Image.open(
            BytesIO(data)
        )

        image.load()

        width = image.width
        height = image.height

        if width < MIN_IMAGE_WIDTH:
            return None

        if height < MIN_IMAGE_HEIGHT:
            return None

        if (
            width * height
            < MIN_IMAGE_AREA
        ):
            return None

        ratio = width / float(height)

        if ratio < 0.45 or ratio > 3.5:
            return None

        # Reject tiny square icons.
        if (
            width == height
            and width < 500
        ):
            return None

        return {
            "image": image.copy(),
            "md5": hashlib.md5(
                data
            ).hexdigest(),
            "url": response.url,
            "width": width,
            "height": height,
        }

    except Exception:
        return None


# ============================================================
# DOWNLOAD MULTIPLE ARTICLE IMAGES
# ============================================================

def download_article_images(
    soup,
    article_url,
):
    log("")
    log("COLLECTING REAL ARTICLE PHOTOS")
    log("-" * 70)

    candidates = get_image_candidates(
        soup,
        article_url,
    )

    log(
        f"IMAGE CANDIDATES FOUND: {len(candidates)}"
    )

    valid = []
    hashes = set()

    for index, image_url in enumerate(
        candidates[:MAX_ARTICLE_IMAGES * 8],
        start=1,
    ):

        log(
            f"IMAGE TEST {index}: {image_url}"
        )

        image_info = download_image(
            image_url,
            referer=article_url,
        )

        if not image_info:
            continue

        image_hash = image_info["md5"]

        if image_hash in hashes:
            continue

        hashes.add(image_hash)

        valid.append(
            {
                "url": image_info["url"],
                "width": image_info["width"],
                "height": image_info["height"],
                "md5": image_hash,
            }
        )

        log(
            "ACCEPTED REAL PHOTO: "
            f"{image_info['width']}x"
            f"{image_info['height']}"
        )

        if len(valid) >= MAX_ARTICLE_IMAGES:
            break

    log(
        f"VALID REAL ARTICLE PHOTOS: {len(valid)}"
    )

    return valid


# ============================================================
# EXTRACT ARTICLE
# ============================================================

def extract_article(url):
    response = fetch(url)

    if not response:
        return None

    if not approved(response.url):
        return None

    final_url = response.url

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title = ""

    title_meta = [
        {
            "property": "og:title"
        },
        {
            "name": "twitter:title"
        },
    ]

    for attrs in title_meta:

        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:

            title = clean(
                tag.get("content")
            )

            if title:
                break

    if not title:

        h1 = soup.find("h1")

        if h1:
            title = clean(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

    if not title and soup.title:

        title = clean(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    title = clean_title(title)

    if len(title) < 12:
        return None

    # --------------------------------------------------------
    # Description
    # --------------------------------------------------------

    summary = ""

    description_meta = [
        {
            "property": "og:description"
        },
        {
            "name": "description"
        },
        {
            "name": "twitter:description"
        },
    ]

    for attrs in description_meta:

        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:

            summary = clean(
                tag.get("content")
            )

            if summary:
                break

    # --------------------------------------------------------
    # Article paragraphs
    # --------------------------------------------------------

    paragraphs = []

    container = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if container:

        for p in container.find_all(
            "p"
        ):

            text = clean(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            low = text.lower()

            if len(text) < 35:
                continue

            excluded = [
                "subscribe",
                "newsletter",
                "privacy policy",
                "cookie policy",
                "terms and conditions",
                "advertisement",
                "download our app",
                "sign up",
                "all rights reserved",
            ]

            if any(
                item in low
                for item in excluded
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    body = clean(
        " ".join(
            paragraphs[:20]
        )
    )

    county = county_from_text(
        f"{title} {summary} {body}"
    )

    if not county:
        return None

    if (
        len(body.split())
        < MIN_ARTICLE_BODY_WORDS
    ):
        return None

    # --------------------------------------------------------
    # Real photos
    # --------------------------------------------------------

    image_candidates = (
        download_article_images(
            soup,
            final_url,
        )
    )

    if not image_candidates:
        log(
            "REJECTED: no usable real article photos"
        )

        return None

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    lower = (
        f"{title} "
        f"{summary} "
        f"{body}"
    ).lower()

    score = min(
        len(body.split()),
        220,
    ) // 5

    positive_terms = [
        "project",
        "road",
        "hospital",
        "school",
        "water",
        "market",
        "farmers",
        "agriculture",
        "jobs",
        "business",
        "investment",
        "health",
        "security",
        "police",
        "court",
        "development",
        "construction",
        "funding",
        "budget",
        "education",
        "transport",
        "infrastructure",
        "residents",
        "county",
        "government",
        "president",
        "minister",
        "mp",
        "senator",
        "governor",
    ]

    for word in positive_terms:

        if re.search(
            r"\b"
            + re.escape(word)
            + r"\b",
            lower,
        ):
            score += 2

    negative_phrases = [
        "crowd erupts",
        "crowd goes wild",
        "dance",
        "chants",
        "campaign rally",
        "campaign trail",
        "celebration",
        "funeral",
        "birthday",
    ]

    for phrase in negative_phrases:

        if phrase in lower:
            score -= 7

    # Stronger score when several real photos
    # are available.
    score += min(
        len(image_candidates),
        5,
    ) * 3

    return {
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "url": final_url,
        "image_candidates": image_candidates,
        "score": score,
    }


# ============================================================
# BUILD NARRATION
# ============================================================

def build_script(article):
    title = clean_title(
        article["title"]
    )

    county = clean(
        article["county"]
    )

    summary = remove_metadata(
        article["summary"]
    )

    body = remove_metadata(
        article["body"]
    )

    parts = []

    # Opening.
    parts.append(
        f"Here is the latest development "
        f"from {county}."
    )

    # Headline.
    parts.append(
        f"{title}."
    )

    # Summary.
    if (
        summary
        and summary.lower()
        != title.lower()
    ):

        parts.append(summary)

    # Body.
    body_sentences = re.split(
        r"(?<=[.!?])\s+",
        body,
    )

    seen = {
        x.lower()
        for x in parts
    }

    for sentence in body_sentences:

        sentence = remove_metadata(
            sentence
        )

        if len(sentence) < 35:
            continue

        key = sentence.lower()

        if key in seen:
            continue

        seen.add(key)

        parts.append(sentence)

        if (
            len(
                " ".join(parts).split()
            )
            >= 135
        ):
            break

    script = clean(
        " ".join(parts)
    )

    # Remove accidental metadata.
    script = re.sub(
        r"\bSource\s*:\s*.*$",
        "",
        script,
        flags=re.I,
    )

    script = re.sub(
        r"\bPhoto\s*:\s*.*$",
        "",
        script,
        flags=re.I,
    )

    script = re.sub(
        r"\s+",
        " ",
        script,
    )

    return script.strip()


# ============================================================
# VALIDATE STORY
# ============================================================

def validate_story(story):
    if not isinstance(
        story,
        dict,
    ):
        raise RuntimeError(
            "Selected story is not a dictionary."
        )

    title = clean(
        story.get("title")
    )

    county = clean(
        story.get("county")
    )

    script = clean(
        story.get("script")
    )

    if not title:
        raise RuntimeError(
            "Story title missing."
        )

    if not county:
        raise RuntimeError(
            "Story county missing."
        )

    if not script:
        raise RuntimeError(
            "Story narration missing."
        )

    if len(
        script.split()
    ) < 45:
        raise RuntimeError(
            "Narration is too short."
        )

    image_urls = story.get(
        "image_urls"
    )

    if not isinstance(
        image_urls,
        list,
    ):
        raise RuntimeError(
            "image_urls is missing."
        )

    if not image_urls:
        raise RuntimeError(
            "No real article image URLs were saved."
        )

    article_url = clean(
        story.get("article_url")
    )

    if not article_url:
        raise RuntimeError(
            "Article URL missing."
        )

    if not approved(
        article_url
    ):
        raise RuntimeError(
            "Article source is not approved."
        )

    return True


# ============================================================
# WRITE SELECTED FILES
# ============================================================

def write_selected_files(article):
    log("")
    log("=" * 70)
    log("WRITING SELECTED STORY FILES")
    log("=" * 70)

    script = build_script(
        article
    )

    image_candidates = (
        article.get(
            "image_candidates",
            [],
        )
    )

    image_urls = []

    seen = set()

    for item in image_candidates:

        if isinstance(
            item,
            dict,
        ):
            url = clean(
                item.get("url")
            )

        else:
            url = clean(item)

        if not url:
            continue

        if url in seen:
            continue

        if any(
            term in url.lower()
            for term in BAD_IMAGE_TERMS
        ):
            continue

        seen.add(url)

        image_urls.append(url)

        if (
            len(image_urls)
            >= MAX_STORED_IMAGE_URLS
        ):
            break

    if not image_urls:
        raise RuntimeError(
            "No usable image URLs available."
        )

    # --------------------------------------------------------
    # Compatibility image URL.
    # --------------------------------------------------------

    first_image_url = image_urls[0]

    # --------------------------------------------------------
    # Story object.
    # --------------------------------------------------------

    story = {
        "title": clean_title(
            article["title"]
        ),

        "county": clean(
            article["county"]
        ),

        "summary": remove_metadata(
            article["summary"]
        ),

        "body": remove_metadata(
            article["body"]
        ),

        "script": script,

        "article_url": clean(
            article["url"]
        ),

        "source": domain(
            article["url"]
        ),

        "image_url": first_image_url,

        "image_urls": image_urls,

        "image_path": (
            "assets/source/"
            "story_image.jpg"
        ),

        "selected_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "generator_version": (
            "RVW_MAIN_V12_MULTI_PHOTO"
        ),
    }

    # --------------------------------------------------------
    # Script object.
    # --------------------------------------------------------

    selected_script = {
        "title": story["title"],
        "county": story["county"],
        "narration": story["script"],
        "article_url": story[
            "article_url"
        ],
        "source": story["source"],
    }

    # --------------------------------------------------------
    # Validate BEFORE saving.
    # --------------------------------------------------------

    validate_story(
        story
    )

    # --------------------------------------------------------
    # Save selected_story.json.
    # --------------------------------------------------------

    save_json(
        SELECTED_STORY,
        story,
    )

    # --------------------------------------------------------
    # Save selected_script.json.
    # --------------------------------------------------------

    save_json(
        SELECTED_SCRIPT,
        selected_script,
    )

    # --------------------------------------------------------
    # HARD CHECK.
    # --------------------------------------------------------

    if not SELECTED_STORY.exists():
        raise RuntimeError(
            "selected_story.json was not created."
        )

    if (
        SELECTED_STORY.stat().st_size
        < 100
    ):
        raise RuntimeError(
            "selected_story.json was created but is empty."
        )

    if not SELECTED_SCRIPT.exists():
        raise RuntimeError(
            "selected_script.json was not created."
        )

    if (
        SELECTED_SCRIPT.stat().st_size
        < 50
    ):
        raise RuntimeError(
            "selected_script.json was created but is empty."
        )

    # --------------------------------------------------------
    # Reload and verify JSON.
    # --------------------------------------------------------

    with SELECTED_STORY.open(
        "r",
        encoding="utf-8",
    ) as f:

        loaded_story = json.load(f)

    with SELECTED_SCRIPT.open(
        "r",
        encoding="utf-8",
    ) as f:

        loaded_script = json.load(f)

    if not loaded_story.get(
        "image_urls"
    ):
        raise RuntimeError(
            "Saved selected_story.json "
            "does not contain image_urls."
        )

    if not loaded_script.get(
        "narration"
    ):
        raise RuntimeError(
            "Saved selected_script.json "
            "does not contain narration."
        )

    log("")
    log(
        "selected_story.json CREATED SUCCESSFULLY"
    )

    log(
        f"SIZE: "
        f"{SELECTED_STORY.stat().st_size} bytes"
    )

    log(
        "selected_script.json CREATED SUCCESSFULLY"
    )

    log(
        f"SIZE: "
        f"{SELECTED_SCRIPT.stat().st_size} bytes"
    )

    log(
        f"REAL PHOTO URLS SAVED: "
        f"{len(image_urls)}"
    )

    for index, url in enumerate(
        image_urls,
        start=1,
    ):
        log(
            f"PHOTO {index}: {url}"
        )

    return story


# ============================================================
# SAVE FIRST REAL IMAGE
#
# This is kept for the GitHub workflow compatibility check.
# V22 itself can download the multiple image_urls.
# ============================================================

def save_first_image(article):
    log("")
    log("=" * 70)
    log("SAVING COMPATIBILITY STORY IMAGE")
    log("=" * 70)

    image_candidates = article.get(
        "image_candidates",
        [],
    )

    if not image_candidates:
        raise RuntimeError(
            "No image candidate available."
        )

    for item in image_candidates:

        if isinstance(
            item,
            dict,
        ):
            url = clean(
                item.get("url")
            )

        else:
            url = clean(item)

        if not url:
            continue

        image_info = download_image(
            url,
            referer=article["url"],
        )

        if not image_info:
            continue

        try:

            SOURCE_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )

            if FINAL_IMAGE.exists():
                FINAL_IMAGE.unlink()

            image_info["image"].convert(
                "RGB"
            ).save(
                FINAL_IMAGE,
                "JPEG",
                quality=95,
                optimize=True,
            )

            with Image.open(
                FINAL_IMAGE
            ) as check:

                check.load()

                if (
                    check.width
                    < MIN_IMAGE_WIDTH
                ):
                    continue

                if (
                    check.height
                    < MIN_IMAGE_HEIGHT
                ):
                    continue

            log(
                "COMPATIBILITY IMAGE SAVED:"
            )

            log(
                str(FINAL_IMAGE)
            )

            log(
                "SIZE: "
                f"{image_info['width']}x"
                f"{image_info['height']}"
            )

            return FINAL_IMAGE

        except Exception as exc:

            log(
                f"FAILED TO SAVE IMAGE: {exc}"
            )

    raise RuntimeError(
        "Unable to save a valid compatibility story image."
    )


# ============================================================
# SELECT BEST STORY
# ============================================================

def select_best(candidates):
    if not candidates:

        raise RuntimeError(
            "No real Rift Valley article "
            "with usable photos was found."
        )

    unique = []
    seen_urls = set()

    for item in candidates:

        article_url = clean(
            item.get("url")
        )

        if not article_url:
            continue

        if article_url in seen_urls:
            continue

        seen_urls.add(
            article_url
        )

        unique.append(item)

    if not unique:

        raise RuntimeError(
            "No unique article candidates found."
        )

    unique.sort(
        key=lambda x: (
            x.get(
                "score",
                0,
            ),
            len(
                x.get(
                    "image_candidates",
                    [],
                )
            ),
        ),
        reverse=True,
    )

    return unique[0]


# ============================================================
# DISCOVER NEWS
# ============================================================

def discover():
    candidates = []

    log("")
    log("=" * 70)
    log("DISCOVERING RIFT VALLEY NEWS")
    log("=" * 70)

    for page in PUBLISHER_PAGES:

        log("")
        log(
            f"CHECKING NEWS PAGE: "
            f"{domain(page)}"
        )

        links = discover_links(
            page
        )

        log(
            f"LOCAL LINKS FOUND: "
            f"{len(links)}"
        )

        # Put county-detected links first.
        links.sort(
            key=lambda x: (
                1
                if x.get("county")
                else 0,
                len(
                    x.get(
                        "text",
                        "",
                    )
                ),
            ),
            reverse=True,
        )

        for item in links[
            :MAX_ARTICLES_PER_SOURCE
        ]:

            article = extract_article(
                item["url"]
            )

            if not article:
                continue

            if not approved(
                article["url"]
            ):
                continue

            candidates.append(
                article
            )

            log(
                "ACCEPTED ARTICLE:"
            )

            log(
                f"{article['county']} | "
                f"{article['title']} | "
                f"SCORE {article['score']} | "
                f"PHOTOS "
                f"{len(article['image_candidates'])}"
            )

            if (
                len(candidates)
                >= MAX_SELECTED_CANDIDATES
            ):
                return candidates

            time.sleep(0.10)

    return candidates


# ============================================================
# CLEAN PREVIOUS GENERATED FILES
# ============================================================

def clean_previous():
    log("")
    log("=" * 70)
    log("CLEANING PREVIOUS GENERATED FILES")
    log("=" * 70)

    directories = [
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
        AUDIO_DIR,
        VIDEO_WORK_DIR,
    ]

    for directory in directories:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    files_to_remove = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
    ]

    for path in files_to_remove:

        try:

            if path.exists():
                path.unlink()

        except Exception as exc:

            log(
                f"WARNING: Could not remove "
                f"{path}: {exc}"
            )

    # Remove generated source photos.
    for pattern in [
        "story_image_*.jpg",
        "_candidate_*.jpg",
    ]:

        for path in SOURCE_DIR.glob(
            pattern
        ):

            try:
                path.unlink()
            except Exception:
                pass

    # Remove generated scene files.
    for pattern in [
        "scene_*.jpg",
        "silent_video.mp4",
        "scenes.txt",
        "narration.mp3",
    ]:

        for path in VIDEO_WORK_DIR.glob(
            pattern
        ):

            try:
                path.unlink()
            except Exception:
                pass

    # Remove old audio.
    for path in [
        AUDIO_DIR / "narration.mp3",
        AUDIO_DIR / "narration_temp.mp3",
        AUDIO_DIR / "narration_best.mp3",
    ]:

        try:

            if path.exists():
                path.unlink()

        except Exception:
            pass


# ============================================================
# VERIFY PROJECT FILES
# ============================================================

def verify_project_files():
    log("")
    log("=" * 70)
    log("VERIFYING PROJECT FILES")
    log("=" * 70)

    if not VIDEO_GENERATOR.exists():

        raise RuntimeError(
            "rift_valley_video_generator.py "
            "not found."
        )

    log(
        "MAIN FILE: "
        f"{Path(__file__).name}"
    )

    log(
        "VIDEO GENERATOR: "
        f"{VIDEO_GENERATOR.name}"
    )

    # Syntax check both files.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(Path(__file__)),
            str(VIDEO_GENERATOR),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:

        log(
            result.stdout
        )

        raise RuntimeError(
            "Python syntax check failed."
        )

    log(
        "PYTHON SYNTAX CHECK PASSED"
    )


# ============================================================
# HARD VERIFY SELECTED JSON
# ============================================================

def verify_selected_files():
    log("")
    log("=" * 70)
    log("VERIFYING SELECTED JSON FILES")
    log("=" * 70)

    if not SELECTED_STORY.exists():

        raise RuntimeError(
            "ERROR: selected_story.json "
            "was not generated."
        )

    if (
        SELECTED_STORY.stat().st_size
        == 0
    ):

        raise RuntimeError(
            "ERROR: selected_story.json "
            "is empty."
        )

    if not SELECTED_SCRIPT.exists():

        raise RuntimeError(
            "ERROR: selected_script.json "
            "was not generated."
        )

    if (
        SELECTED_SCRIPT.stat().st_size
        == 0
    ):

        raise RuntimeError(
            "ERROR: selected_script.json "
            "is empty."
        )

    try:

        with SELECTED_STORY.open(
            "r",
            encoding="utf-8",
        ) as f:

            story = json.load(f)

        with SELECTED_SCRIPT.open(
            "r",
            encoding="utf-8",
        ) as f:

            script = json.load(f)

    except Exception as exc:

        raise RuntimeError(
            "Saved JSON could not be parsed: "
            f"{exc}"
        )

    if not story.get("title"):

        raise RuntimeError(
            "selected_story.json has no title."
        )

    if not story.get("county"):

        raise RuntimeError(
            "selected_story.json has no county."
        )

    if not story.get("script"):

        raise RuntimeError(
            "selected_story.json has no script."
        )

    if not story.get("image_urls"):

        raise RuntimeError(
            "selected_story.json has no image_urls."
        )

    if not script.get("narration"):

        raise RuntimeError(
            "selected_script.json has no narration."
        )

    log(
        "SELECTED STORY JSON: VALID"
    )

    log(
        f"TITLE: {story['title']}"
    )

    log(
        f"COUNTY: {story['county']}"
    )

    log(
        f"IMAGE URLS: "
        f"{len(story['image_urls'])}"
    )

    log(
        "SELECTED SCRIPT JSON: VALID"
    )

    log(
        f"NARRATION WORDS: "
        f"{len(script['narration'].split())}"
    )


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_generator():
    log("")
    log("=" * 70)
    log("STARTING RVW_VIDEO_V22")
    log("=" * 70)

    if not VIDEO_GENERATOR.exists():

        raise RuntimeError(
            "rift_valley_video_generator.py "
            "not found."
        )

    # IMPORTANT:
    # Verify JSON exists BEFORE launching V22.
    verify_selected_files()

    log("")
    log(
        "LAUNCHING VIDEO GENERATOR:"
    )

    log(
        str(VIDEO_GENERATOR)
    )

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(VIDEO_GENERATOR),
        ],
        cwd=str(ROOT),
        env={
            **__import__(
                "os"
            ).environ,
            "PYTHONUNBUFFERED": "1",
        },
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Video generator failed with "
            f"exit code {result.returncode}"
        )

    log(
        "VIDEO GENERATOR COMPLETED SUCCESSFULLY"
    )


# ============================================================
# VERIFY FINAL MP4
# ============================================================

def verify_final_video():
    log("")
    log("=" * 70)
    log("VERIFYING FINAL MP4")
    log("=" * 70)

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final Rift Valley Watch MP4 "
            "was not generated."
        )

    size = FINAL_VIDEO.stat().st_size

    log(
        f"FINAL MP4 SIZE: "
        f"{size / 1048576:.2f} MB"
    )

    if size < 100000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream="
            "codec_type,"
            "codec_name,"
            "width,"
            "height,"
            "sample_rate,"
            "channels",
            "-show_entries",
            "format=duration,size",
            "-of",
            "default=noprint_wrappers=1",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if probe.returncode != 0:

        log(
            probe.stdout
        )

        raise RuntimeError(
            "Final MP4 failed FFprobe validation."
        )

    log("")
    log(
        probe.stdout
    )

    width_probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    height_probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    audio_probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:

        width = int(
            width_probe.stdout.strip()
        )

        height = int(
            height_probe.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Unable to read final video dimensions."
        )

    has_audio = bool(
        audio_probe.stdout.strip()
    )

    if width != 1080:

        raise RuntimeError(
            f"Wrong video width: {width}"
        )

    if height != 1920:

        raise RuntimeError(
            f"Wrong video height: {height}"
        )

    if not has_audio:

        raise RuntimeError(
            "Final MP4 does not contain audio."
        )

    duration_probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:

        duration = float(
            duration_probe.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Final MP4 duration could not be read."
        )

    if duration < 5:

        raise RuntimeError(
            "Final MP4 is too short."
        )

    log("")
    log(
        "FINAL VIDEO VERIFIED SUCCESSFULLY"
    )

    log(
        f"RESOLUTION: {width}x{height}"
    )

    log(
        f"DURATION: {duration:.2f} seconds"
    )

    log(
        "AUDIO: PRESENT"
    )

    log(
        f"FILE: {FINAL_VIDEO}"
    )


# ============================================================
# FINAL DIRECTORY REPORT
# ============================================================

def report_files():
    log("")
    log("=" * 70)
    log("FINAL OUTPUT REPORT")
    log("=" * 70)

    paths = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
    ]

    for path in paths:

        if path.exists():

            log(
                f"OK  {path} "
                f"({path.stat().st_size} bytes)"
            )

        else:

            log(
                f"MISSING  {path}"
            )


# ============================================================
# MAIN
# ============================================================

def main():
    try:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH")
        log("=" * 70)
        log(
            "VERSION: "
            "RVW_MAIN_V12_MULTI_PHOTO_JSON_STABLE"
        )
        log("=" * 70)

        # ----------------------------------------------------
        # Prepare.
        # ----------------------------------------------------

        clean_previous()

        verify_project_files()

        # ----------------------------------------------------
        # Discover.
        # ----------------------------------------------------

        candidates = discover()

        log("")
        log(
            f"VALID STORIES FOUND: "
            f"{len(candidates)}"
        )

        if not candidates:

            raise RuntimeError(
                "No valid Rift Valley stories "
                "with real article photos were found."
            )

        # ----------------------------------------------------
        # Select.
        # ----------------------------------------------------

        selected = select_best(
            candidates
        )

        log("")
        log("=" * 70)
        log("SELECTED STORY")
        log("=" * 70)

        log(
            f"COUNTY: "
            f"{selected['county']}"
        )

        log(
            f"TITLE: "
            f"{selected['title']}"
        )

        log(
            f"SOURCE: "
            f"{domain(selected['url'])}"
        )

        log(
            f"SCORE: "
            f"{selected['score']}"
        )

        log(
            f"REAL PHOTOS: "
            f"{len(selected['image_candidates'])}"
        )

        log(
            f"ARTICLE: "
            f"{selected['url']}"
        )

        # ----------------------------------------------------
        # Save compatibility image.
        # ----------------------------------------------------

        save_first_image(
            selected
        )

        # ----------------------------------------------------
        # Write JSON.
        # ----------------------------------------------------

        story = write_selected_files(
            selected
        )

        # ----------------------------------------------------
        # HARD CHECK BEFORE GENERATOR.
        # ----------------------------------------------------

        verify_selected_files()

        # ----------------------------------------------------
        # Run V22.
        # ----------------------------------------------------

        run_generator()

        # ----------------------------------------------------
        # Verify final MP4.
        # ----------------------------------------------------

        verify_final_video()

        # ----------------------------------------------------
        # Report.
        # ----------------------------------------------------

        report_files()

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH COMPLETED SUCCESSFULLY")
        log("=" * 70)

        log(
            f"FINAL VIDEO: {FINAL_VIDEO}"
        )

        return 0

    except KeyboardInterrupt:

        log("")
        log(
            "Generation interrupted."
        )

        return 130

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH GENERATION FAILED")
        log("=" * 70)

        log(
            f"ERROR: {exc}"
        )

        import traceback

        traceback.print_exc()

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
