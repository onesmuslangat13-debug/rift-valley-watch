from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time

import requests
from bs4 import BeautifulSoup
from PIL import Image
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS ENGINE
# VERSION: RVW_MAIN_V14_STABLE_REALTIME_MULTI_PHOTO
#
# PURPOSE
# - Select one current Rift Valley story
# - Strict county matching
# - Real article photographs
# - Multiple photographs where available
# - Avoid obvious broadcaster/logo images
# - Generate narration
# - Write selected_story.json
# - Write selected_script.json
# - Run the video renderer
# ============================================================


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
VIDEO_WORK_DIR = ASSETS_DIR / "video_work"
AUDIO_DIR = ROOT / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"


# ============================================================
# SETTINGS
# ============================================================

MAX_ARTICLE_AGE_HOURS = 48
PREFERRED_FRESH_HOURS = 24
FUTURE_TOLERANCE_MINUTES = 15

MAX_ARTICLES_PER_SOURCE = 35
MAX_SELECTED_CANDIDATES = 30
MAX_ARTICLE_IMAGES = 8
MAX_STORED_IMAGE_URLS = 8

MIN_BODY_WORDS = 45
MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

REQUEST_TIMEOUT = 25
VIDEO_TIMEOUT = 900

KENYA_TZ = timezone(timedelta(hours=3))

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
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


# ============================================================
# APPROVED NEWS SOURCES
#
# Citizen Digital is intentionally excluded because the user
# requested that Citizen TV branding not appear in the reel.
# ============================================================

SOURCE_PAGES = [
    {
        "name": "The Star",
        "url": "https://www.the-star.co.ke/news/",
        "domain": "the-star.co.ke",
    },
    {
        "name": "Nation",
        "url": "https://nation.africa/kenya/news",
        "domain": "nation.africa",
    },
    {
        "name": "KBC",
        "url": "https://www.kbc.co.ke/",
        "domain": "kbc.co.ke",
    },
    {
        "name": "People Daily",
        "url": "https://peopledaily.digital/",
        "domain": "peopledaily.digital",
    },
    {
        "name": "Capital News",
        "url": "https://www.capitalfm.co.ke/news/",
        "domain": "capitalfm.co.ke",
    },
    {
        "name": "NTV Kenya",
        "url": "https://ntvkenya.co.ke/news/",
        "domain": "ntvkenya.co.ke",
    },
    {
        "name": "Standard",
        "url": "https://www.standardmedia.co.ke/",
        "domain": "standardmedia.co.ke",
    },
]


APPROVED_DOMAINS = {
    item["domain"]
    for item in SOURCE_PAGES
}


# ============================================================
# COUNTY CONFIGURATION
# ============================================================

COUNTIES = {
    "Bomet": [
        "bomet",
        "sotik",
        "longisa",
        "chepalungu",
        "konoin",
        "bomet county",
        "sotik town",
    ],
    "Kericho": [
        "kericho",
        "litein",
        "kipkelion",
        "ainamoi",
        "belgut",
        "bureti",
        "kapkugerwet",
        "kericho county",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "bahati",
        "subukia",
        "rongai",
        "nakuru county",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "aldai",
        "chesumei",
        "emgwen",
        "tindiret",
        "nandi hills",
        "nandi county",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "kesses",
        "turbo",
        "ainabkoi",
        "moiben",
        "soy",
        "uasin gishu county",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "elgeyo",
        "marakwet",
        "iten",
        "keiyo",
        "keiyo south",
        "keiyo north",
        "kapcherop",
        "kapsowar",
        "elgeyo-marakwet county",
    ],
    "West Pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "kacheliba",
        "sigor",
        "pokot south",
        "pokot central",
        "pokot north",
        "west pokot county",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "suswa",
        "transmara",
        "narok north",
        "narok south",
        "loita",
        "narok county",
    ],
}


# ============================================================
# IMAGE FILTERING
# ============================================================

BAD_IMAGE_TERMS = {
    "favicon",
    "icon",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "generic",
    "world-cup",
    "worldcup",
    "logo-only",
    "logo_only",
    "sprite",
    "tracking",
    "pixel",
    "spacer",
    "blank",
    "transparent",
    "thumbnail-placeholder",
    "profile-placeholder",
    "profile_avatar",
    "advert",
    "advertisement",
    "banner-ad",
    "banner_ad",
    "facebook-icon",
    "twitter-icon",
    "youtube-icon",
    "instagram-icon",
    "whatsapp-icon",
}


# These specifically target obvious Citizen TV branding/file names.
# We do NOT reject the citizen.digital domain here because a
# syndicated image may have a neutral filename.
BRANDING_IMAGE_TERMS = {
    "citizen-tv",
    "citizentv",
    "citizen_tv",
    "citizen-logo",
    "citizen_logo",
    "citizenlogo",
    "ctv-logo",
    "ctv_logo",
    "ctvlogo",
    "citizen-digital-logo",
    "citizen_digital_logo",
}


POSITIVE_TERMS = {
    "president",
    "deputy president",
    "governor",
    "senator",
    "mp",
    "member of parliament",
    "county",
    "government",
    "govt",
    "school",
    "hospital",
    "road",
    "roads",
    "police",
    "security",
    "business",
    "market",
    "agriculture",
    "farmers",
    "farmer",
    "tea",
    "coffee",
    "health",
    "education",
    "water",
    "electricity",
    "housing",
    "development",
    "project",
    "court",
    "election",
    "county assembly",
    "parliament",
    "cabinet",
    "economy",
    "investment",
    "jobs",
    "employment",
    "flood",
    "flooding",
    "accident",
    "crime",
    "fire",
    "community",
    "residents",
    "hospital",
}


NEGATIVE_PHRASES = {
    "opinion",
    "analysis",
    "explainer",
    "throwback",
    "archive",
    "watch:",
    "video:",
    "podcast",
    "commentary",
}


GENERIC_PATH_TERMS = {
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/authors/",
    "/search",
    "/page/",
    "/gallery/",
    "/video/",
    "/videos/",
    "/live/",
}


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


def section(title):
    log("")
    log("=" * 64)
    log(title)
    log("=" * 64)


# ============================================================
# FILESYSTEM
# ============================================================

def ensure_directories():
    directories = [
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
        VIDEO_WORK_DIR,
        AUDIO_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def clean_previous():
    section("CLEANING PREVIOUS GENERATED FILES")

    for path in [
        STORY_FILE,
        SCRIPT_FILE,
        NARRATION_FILE,
        FINAL_VIDEO,
    ]:
        try:
            if path.exists():
                path.unlink()
                log(f"Removed: {path}")
        except Exception as exc:
            log(f"Warning: could not remove {path}: {exc}")

    for pattern in [
        "story_image*.jpg",
        "story_image*.jpeg",
        "story_image*.png",
        "story_image*.webp",
    ]:
        for path in SOURCE_DIR.glob(pattern):
            try:
                path.unlink()
                log(f"Removed: {path}")
            except Exception as exc:
                log(f"Warning: could not remove {path}: {exc}")

    scene_dirs = [
        VIDEO_WORK_DIR / "scene_images",
        VIDEO_WORK_DIR / "scene_videos",
    ]

    for directory in scene_dirs:
        if directory.exists():
            try:
                shutil.rmtree(directory)
                log(f"Removed: {directory}")
            except Exception as exc:
                log(f"Warning: could not remove {directory}: {exc}")

    for filename in [
        "narration.mp3",
        "concat.txt",
        "final_video.mp4",
        "muxed_video.mp4",
    ]:
        path = VIDEO_WORK_DIR / filename
        if path.exists():
            try:
                path.unlink()
                log(f"Removed: {path}")
            except Exception:
                pass

    ensure_directories()

    log("Clean-up complete.")


# ============================================================
# URL HELPERS
# ============================================================

def normalize_url(url):
    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url


def domain_from_url(url):
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_approved_domain(url):
    domain = domain_from_url(url)

    if not domain:
        return False

    for approved in APPROVED_DOMAINS:
        if domain == approved or domain.endswith("." + approved):
            return True

    return False


def same_domain(url_a, url_b):
    a = domain_from_url(url_a)
    b = domain_from_url(url_b)

    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


# ============================================================
# HTTP
# ============================================================

def fetch_url(url, timeout=REQUEST_TIMEOUT):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code != 200:
            log(
                f"HTTP {response.status_code}: "
                f"{response.url}"
            )
            return None

        if not response.content:
            return None

        return response

    except requests.RequestException as exc:
        log(f"Request failed: {url} -> {exc}")
        return None
    except Exception as exc:
        log(f"Unexpected request error: {url} -> {exc}")
        return None


# ============================================================
# DATE PARSING
# ============================================================

def parse_datetime(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    # ISO format.
    try:
        iso_text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KENYA_TZ)

        return dt.astimezone(KENYA_TZ)
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%B %d, %Y %H:%M",
        "%B %d, %Y",
        "%b %d, %Y %H:%M",
        "%b %d, %Y",
        "%d %B %Y %H:%M",
        "%d %B %Y",
        "%d %b %Y %H:%M",
        "%d %b %Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=KENYA_TZ)
        except Exception:
            continue

    return None


def extract_publication_datetime(soup):
    selectors = [
        ("meta", {"property": "article:published_time"}, "content"),
        ("meta", {"property": "article:published"}, "content"),
        ("meta", {"name": "article:published_time"}, "content"),
        ("meta", {"name": "publish-date"}, "content"),
        ("meta", {"name": "publication-date"}, "content"),
        ("meta", {"name": "date"}, "content"),
        ("time", {"datetime": True}, "datetime"),
    ]

    for tag_name, attrs, attr_name in selectors:
        tags = soup.find_all(tag_name, attrs=attrs)

        for tag in tags:
            value = tag.get(attr_name)

            dt = parse_datetime(value)

            if dt:
                return dt

    # JSON-LD.
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(" ", strip=True)

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        objects = []

        if isinstance(data, dict):
            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(graph)

        elif isinstance(data, list):
            objects.extend(data)

        for item in objects:
            if not isinstance(item, dict):
                continue

            for key in [
                "datePublished",
                "dateCreated",
                "dateModified",
            ]:
                dt = parse_datetime(item.get(key))

                if dt:
                    return dt

    # Visible time elements as fallback.
    for tag in soup.find_all("time"):
        text = tag.get_text(" ", strip=True)

        dt = parse_datetime(text)

        if dt:
            return dt

    return None


# ============================================================
# FRESHNESS
# ============================================================

def now_kenya():
    return datetime.now(KENYA_TZ)


def article_age_hours(publication_dt):
    if not publication_dt:
        return 999999

    now = now_kenya()
    delta = now - publication_dt

    return delta.total_seconds() / 3600.0


def freshness_score(publication_dt):
    age = article_age_hours(publication_dt)

    if age < 0:
        return -100

    if age <= 6:
        return 120

    if age <= 12:
        return 100

    if age <= 24:
        return 80

    if age <= 36:
        return 50

    if age <= MAX_ARTICLE_AGE_HOURS:
        return 20

    return -100


def is_fresh(publication_dt):
    if not publication_dt:
        return False

    age = article_age_hours(publication_dt)

    if age < -(FUTURE_TOLERANCE_MINUTES / 60):
        return False

    if age > MAX_ARTICLE_AGE_HOURS:
        return False

    return True


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    text = text.replace("\xa0", " ")

    return text.strip()


def clean_title(title):
    title = clean_text(title)

    if not title:
        return ""

    title = re.sub(
        r"^\s*(breaking|latest)\s*[:\-|]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s*[\-|–—]\s*(the star|nation|kbc|ntv|standard|"
        r"people daily|capital news)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip(" -|:")


def word_count(text):
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


def normalize_for_matching(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# COUNTY CLASSIFICATION
# ============================================================

def county_matches(text, county):
    normalized = normalize_for_matching(text)

    matches = []

    for term in COUNTIES[county]:
        term_normalized = normalize_for_matching(term)

        if not term_normalized:
            continue

        pattern = r"\b" + re.escape(term_normalized) + r"\b"

        if re.search(pattern, normalized):
            matches.append(term)

    return matches


def classify_county(title, summary, body):
    title_text = normalize_for_matching(title)
    summary_text = normalize_for_matching(summary)
    body_text = normalize_for_matching(body)

    scores = {}

    for county, terms in COUNTIES.items():
        score = 0

        for term in terms:
            normalized_term = normalize_for_matching(term)

            if not normalized_term:
                continue

            pattern = r"\b" + re.escape(normalized_term) + r"\b"

            if re.search(pattern, title_text):
                score += 5

            if re.search(pattern, summary_text):
                score += 3

            early_body = body_text[:2500]

            if re.search(pattern, early_body):
                score += 2

            full_count = len(re.findall(pattern, body_text))

            score += min(full_count, 3)

        scores[county] = score

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    if not ranked:
        return None, 0, scores

    best_county, best_score = ranked[0]

    if best_score < 5:
        return None, best_score, scores

    # If two counties have strong competing scores, reject.
    if len(ranked) > 1:
        second_county, second_score = ranked[1]

        if second_score >= 8 and second_score >= best_score * 0.75:
            return None, best_score, scores

    return best_county, best_score, scores


# ============================================================
# TITLE FILTERING
# ============================================================

def title_is_bad(title):
    normalized = normalize_for_matching(title)

    if not normalized:
        return True

    for phrase in NEGATIVE_PHRASES:
        if phrase in normalized:
            return True

    if len(normalized) < 15:
        return True

    return False


# ============================================================
# ARTICLE LINK DISCOVERY
# ============================================================

def is_probable_article_url(url, source_url):
    if not url:
        return False

    url = normalize_url(url)

    if not url.startswith("http"):
        return False

    if not is_approved_domain(url):
        return False

    if not same_domain(url, source_url):
        return False

    parsed = urlparse(url)

    path = parsed.path.lower()

    if not path or path == "/":
        return False

    for bad_path in GENERIC_PATH_TERMS:
        if bad_path in path:
            return False

    if path.endswith(
        (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".svg",
            ".pdf",
            ".mp4",
            ".mp3",
        )
    ):
        return False

    segments = [
        segment
        for segment in path.split("/")
        if segment
    ]

    if len(segments) < 1:
        return False

    return True


def discover_links(source):
    response = fetch_url(source["url"])

    if response is None:
        return []

    soup = BeautifulSoup(
        response.content,
        "html.parser",
    )

    results = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")

        if not href:
            continue

        absolute = urljoin(
            response.url,
            href,
        )

        absolute = absolute.split("#")[0]

        if not is_probable_article_url(
            absolute,
            response.url,
        ):
            continue

        if absolute in seen:
            continue

        text = clean_text(
            anchor.get_text(" ", strip=True)
        )

        if len(text) < 10:
            continue

        seen.add(absolute)

        results.append(
            {
                "url": absolute,
                "link_text": text,
            }
        )

        if len(results) >= MAX_ARTICLES_PER_SOURCE:
            break

    return results


# ============================================================
# IMAGE URL FILTER
# ============================================================

def image_url_is_bad(url):
    if not url:
        return True

    url = normalize_url(url)

    if not url.startswith("http"):
        return True

    lower_url = url.lower()

    parsed = urlparse(lower_url)

    path_and_query = (
        parsed.path + "?" + parsed.query
    )

    for term in BAD_IMAGE_TERMS:
        if term in path_and_query:
            return True

    for term in BRANDING_IMAGE_TERMS:
        if term in path_and_query:
            return True

    if lower_url.startswith("data:"):
        return True

    return False


# ============================================================
# IMAGE CANDIDATE EXTRACTION
# ============================================================

def add_image_candidate(candidates, url):
    url = normalize_url(url)

    if image_url_is_bad(url):
        return

    if url not in candidates:
        candidates.append(url)


def extract_json_ld_images(soup, candidates):
    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        raw = script.string or script.get_text(
            " ",
            strip=True,
        )

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        objects = []

        if isinstance(data, dict):
            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(graph)

        elif isinstance(data, list):
            objects.extend(data)

        for item in objects:
            if not isinstance(item, dict):
                continue

            image = item.get("image")

            if isinstance(image, str):
                add_image_candidate(
                    candidates,
                    image,
                )

            elif isinstance(image, dict):
                url = image.get("url")

                if isinstance(url, str):
                    add_image_candidate(
                        candidates,
                        url,
                    )

            elif isinstance(image, list):
                for value in image:
                    if isinstance(value, str):
                        add_image_candidate(
                            candidates,
                            value,
                        )
                    elif isinstance(value, dict):
                        url = value.get("url")

                        if isinstance(url, str):
                            add_image_candidate(
                                candidates,
                                url,
                            )


def extract_image_candidates(soup, article_url):
    candidates = []

    # OpenGraph.
    for tag in soup.find_all(
        "meta",
        property=re.compile(
            r"^og:image",
            re.IGNORECASE,
        ),
    ):
        value = tag.get("content")

        if value:
            add_image_candidate(
                candidates,
                urljoin(article_url, value),
            )

    # Twitter cards.
    for tag in soup.find_all(
        "meta",
        attrs={
            "name": re.compile(
                r"^twitter:image",
                re.IGNORECASE,
            )
        },
    ):
        value = tag.get("content")

        if value:
            add_image_candidate(
                candidates,
                urljoin(article_url, value),
            )

    # JSON-LD.
    extract_json_ld_images(
        soup,
        candidates,
    )

    # Itemprop image.
    for tag in soup.find_all(
        attrs={
            "itemprop": re.compile(
                r"image",
                re.IGNORECASE,
            )
        }
    ):
        for attr in [
            "content",
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
        ]:
            value = tag.get(attr)

            if value:
                add_image_candidate(
                    candidates,
                    urljoin(article_url, value),
                )

    # Source and picture elements.
    for tag in soup.find_all(
        ["source", "img"]
    ):
        attrs = [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "srcset",
            "data-srcset",
        ]

        for attr in attrs:
            value = tag.get(attr)

            if not value:
                continue

            if attr in {
                "srcset",
                "data-srcset",
            }:
                pieces = [
                    piece.strip()
                    for piece in value.split(",")
                ]

                for piece in pieces:
                    url_part = piece.split(" ")[0]

                    if url_part:
                        add_image_candidate(
                            candidates,
                            urljoin(
                                article_url,
                                url_part,
                            ),
                        )
            else:
                add_image_candidate(
                    candidates,
                    urljoin(
                        article_url,
                        value,
                    ),
                )

    return candidates[:MAX_STORED_IMAGE_URLS]


# ============================================================
# IMAGE FINGERPRINT
# ============================================================

def image_fingerprint(image):
    try:
        gray = image.convert("L")
        gray = gray.resize(
            (32, 32),
            Image.Resampling.LANCZOS,
        )

        pixels = list(gray.getdata())

        if not pixels:
            return None

        average = sum(pixels) / len(pixels)

        bits = 0

        for value in pixels:
            bits <<= 1

            if value >= average:
                bits |= 1

        return bits

    except Exception:
        return None


def fingerprint_distance(first, second):
    if first is None or second is None:
        return 999999

    return (first ^ second).bit_count()


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url):
    if image_url_is_bad(url):
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        if (
            "image" not in content_type
            and not response.content.startswith(b"\xff\xd8")
            and not response.content.startswith(b"\x89PNG")
            and not response.content.startswith(b"RIFF")
        ):
            return None

        if len(response.content) < 20000:
            return None

        image = Image.open(
            __import__("io").BytesIO(
                response.content
            )
        )

        image.load()

        width, height = image.size

        if width < MIN_IMAGE_WIDTH:
            return None

        if height < MIN_IMAGE_HEIGHT:
            return None

        if width * height < MIN_IMAGE_AREA:
            return None

        ratio = width / float(height)

        if ratio < 0.45 or ratio > 3.5:
            return None

        # Reject extremely small square icons.
        if (
            width == height
            and width < 700
        ):
            return None

        fingerprint = image_fingerprint(
            image
        )

        return {
            "url": url,
            "bytes": response.content,
            "image": image,
            "width": width,
            "height": height,
            "fingerprint": fingerprint,
        }

    except Exception:
        return None


def download_article_images(
    image_urls,
    max_images=MAX_ARTICLE_IMAGES,
):
    accepted = []
    hashes = set()
    fingerprints = []

    for url in image_urls:
        if len(accepted) >= max_images:
            break

        log(f"Trying image: {url}")

        item = download_image(url)

        if item is None:
            log("  Rejected.")
            continue

        digest = hashlib.sha256(
            item["bytes"]
        ).hexdigest()

        if digest in hashes:
            log("  Duplicate byte image.")
            continue

        duplicate_visual = False

        for previous in fingerprints:
            distance = fingerprint_distance(
                item["fingerprint"],
                previous,
            )

            if distance <= 70:
                duplicate_visual = True
                break

        if duplicate_visual:
            log("  Visually duplicate image.")
            continue

        hashes.add(digest)
        fingerprints.append(
            item["fingerprint"]
        )

        accepted.append(item)

        log(
            "  ACCEPTED: "
            f"{item['width']}x{item['height']}"
        )

    return accepted


# ============================================================
# SAVE IMAGES
# ============================================================

def save_article_images(image_items):
    saved_paths = []
    saved_urls = []
    saved_metadata = []

    for index, item in enumerate(image_items):
        if index == 0:
            filename = "story_image.jpg"
        else:
            filename = f"story_image_{index}.jpg"

        output_path = SOURCE_DIR / filename

        try:
            image = item["image"].convert("RGB")

            image.save(
                output_path,
                "JPEG",
                quality=94,
                optimize=True,
            )

            if not output_path.exists():
                continue

            size = output_path.stat().st_size

            if size < 10000:
                output_path.unlink()
                continue

            saved_paths.append(
                str(
                    output_path.relative_to(ROOT)
                ).replace("\\", "/")
            )

            saved_urls.append(
                item["url"]
            )

            saved_metadata.append(
                {
                    "path": saved_paths[-1],
                    "url": item["url"],
                    "width": item["width"],
                    "height": item["height"],
                    "size": size,
                }
            )

            log(
                f"Saved image {index + 1}: "
                f"{output_path}"
            )

        except Exception as exc:
            log(
                f"Could not save image "
                f"{index + 1}: {exc}"
            )

    return (
        saved_paths,
        saved_urls,
        saved_metadata,
    )


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(source, article_url):
    log("")
    log(f"ARTICLE: {article_url}")

    response = fetch_url(article_url)

    if response is None:
        return None

    final_url = response.url

    if not is_approved_domain(final_url):
        log("Rejected: final URL is not approved.")
        return None

    soup = BeautifulSoup(
        response.content,
        "html.parser",
    )

    # Remove non-article elements.
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "form",
            "aside",
            "iframe",
        ]
    ):
        tag.decompose()

    title = ""

    og_title = soup.find(
        "meta",
        property="og:title",
    )

    if og_title:
        title = og_title.get(
            "content",
            "",
        )

    if not title:
        title_tag = soup.find("title")

        if title_tag:
            title = title_tag.get_text(
                " ",
                strip=True,
            )

    if not title:
        h1 = soup.find("h1")

        if h1:
            title = h1.get_text(
                " ",
                strip=True,
            )

    title = clean_title(title)

    if title_is_bad(title):
        log("Rejected: bad or weak title.")
        return None

    summary = ""

    for attrs in [
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ]:
        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:
            summary = clean_text(
                tag.get("content", "")
            )

            if summary:
                break

    paragraphs = []

    for paragraph in soup.find_all("p"):
        text = clean_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        if word_count(text) < 5:
            continue

        lowered = text.lower()

        if any(
            phrase in lowered
            for phrase in [
                "cookie",
                "subscribe to our newsletter",
                "follow us on",
                "advertisement",
            ]
        ):
            continue

        paragraphs.append(text)

    body = " ".join(paragraphs)
    body = clean_text(body)

    if word_count(body) < MIN_BODY_WORDS:
        log(
            "Rejected: article body too short."
        )
        return None

    publication_dt = extract_publication_datetime(
        soup
    )

    if not publication_dt:
        log(
            "Rejected: publication date not found."
        )
        return None

    if not is_fresh(publication_dt):
        log(
            "Rejected: article is outside "
            "freshness window."
        )
        return None

    county, county_score, county_scores = (
        classify_county(
            title,
            summary,
            body,
        )
    )

    if not county:
        log(
            "Rejected: strict county classification "
            "failed."
        )
        return None

    combined_text = (
        title + " " +
        summary + " " +
        body
    ).lower()

    positive_score = 0

    for term in POSITIVE_TERMS:
        if term in combined_text:
            positive_score += 1

    negative_score = 0

    for phrase in NEGATIVE_PHRASES:
        if phrase in combined_text:
            negative_score += 8

    image_urls = extract_image_candidates(
        soup,
        final_url,
    )

    if not image_urls:
        log(
            "Rejected: no image candidates."
        )
        return None

    log(
        f"Image candidates found: "
        f"{len(image_urls)}"
    )

    image_items = download_article_images(
        image_urls,
        max_images=MAX_ARTICLE_IMAGES,
    )

    if not image_items:
        log(
            "Rejected: no usable real photographs."
        )
        return None

    image_score = min(
        len(image_items) * 8,
        40,
    )

    quality_score = (
        min(word_count(body), 500) / 10
        + positive_score
        - negative_score
        + image_score
        + county_score
    )

    age = article_age_hours(
        publication_dt
    )

    selection_score = (
        freshness_score(publication_dt)
        + quality_score
    )

    return {
        "source": source["name"],
        "source_domain": source["domain"],
        "url": final_url,
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "county_score": county_score,
        "county_scores": county_scores,
        "publication_datetime": publication_dt.isoformat(),
        "age_hours": round(age, 2),
        "freshness_score": freshness_score(
            publication_dt
        ),
        "quality_score": round(
            quality_score,
            2,
        ),
        "selection_score": round(
            selection_score,
            2,
        ),
        "image_count": len(image_items),
        "image_items": image_items,
        "image_urls": [
            item["url"]
            for item in image_items
        ],
        "body_word_count": word_count(body),
    }


# ============================================================
# STORY SCORING
# ============================================================

def story_sort_key(story):
    return (
        story.get("freshness_score", -999),
        story.get("image_count", 0),
        story.get("selection_score", -999),
        story.get("quality_score", -999),
    )


def select_best(stories):
    if not stories:
        return None

    stories = sorted(
        stories,
        key=story_sort_key,
        reverse=True,
    )

    section("TOP STORY CANDIDATES")

    for index, story in enumerate(
        stories[:10],
        start=1,
    ):
        log(
            f"{index}. "
            f"[{story['county']}] "
            f"{story['title']}"
        )
        log(
            f"   Source: {story['source']} | "
            f"Age: {story['age_hours']:.1f}h | "
            f"Images: {story['image_count']} | "
            f"Score: {story['selection_score']}"
        )

    return stories[0]


# ============================================================
# SCRIPT GENERATION
# ============================================================

def sentence_cleanup(text):
    text = clean_text(text)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def split_into_sentences(text):
    text = sentence_cleanup(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        part.strip()
        for part in parts
        if word_count(part) >= 6
    ]


def build_script(story):
    county = story["county"]
    title = story["title"]
    summary = story.get("summary", "")
    body = story.get("body", "")

    sentences = split_into_sentences(
        body
    )

    selected_sentences = []

    if summary:
        selected_sentences.append(
            sentence_cleanup(summary)
        )

    for sentence in sentences:
        if len(selected_sentences) >= 6:
            break

        normalized = sentence.lower()

        if normalized in {
            item.lower()
            for item in selected_sentences
        }:
            continue

        selected_sentences.append(
            sentence
        )

    script_parts = [
        f"Here is the latest development "
        f"from {county} County.",
        title + ".",
    ]

    for sentence in selected_sentences:
        if word_count(
            " ".join(script_parts)
        ) >= 125:
            break

        script_parts.append(sentence)

    script = " ".join(
        sentence_cleanup(part)
        for part in script_parts
        if part
    )

    script = re.sub(
        r"\s+",
        " ",
        script,
    ).strip()

    words = word_count(script)

    # If too short, add more factual article text.
    if words < 80:
        for sentence in sentences:
            if sentence in script:
                continue

            script += " " + sentence

            if word_count(script) >= 90:
                break

    words = word_count(script)

    # Keep narration comfortably below very long single-image
    # durations while still providing useful information.
    if words > 155:
        words_list = script.split()

        script = " ".join(
            words_list[:155]
        )

        if not script.endswith((".", "!", "?")):
            script += "."

    return script


# ============================================================
# NARRATION
# ============================================================

def generate_narration(script):
    section("GENERATING NARRATION")

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = AUDIO_DIR / (
        "narration_temp.mp3"
    )

    try:
        if temp_file.exists():
            temp_file.unlink()

        tts = gTTS(
            text=script,
            lang="en",
            slow=False,
        )

        tts.save(
            str(temp_file)
        )

        if not temp_file.exists():
            raise RuntimeError(
                "gTTS did not create the MP3."
            )

        size = temp_file.stat().st_size

        if size < 1000:
            raise RuntimeError(
                "Generated narration is too small."
            )

        temp_file.replace(
            NARRATION_FILE
        )

        log(
            f"Narration generated: "
            f"{NARRATION_FILE}"
        )

        log(
            f"Narration size: "
            f"{NARRATION_FILE.stat().st_size} bytes"
        )

        return True

    except Exception as exc:
        log(
            f"Narration generation failed: "
            f"{exc}"
        )

        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

        return False


# ============================================================
# STORY JSON
# ============================================================

def make_story_json(story, image_paths, image_urls):
    return {
        "version": "RVW_MAIN_V14",
        "generated_at": now_kenya().isoformat(),
        "source": story["source"],
        "source_domain": story["source_domain"],
        "url": story["url"],
        "title": story["title"],
        "summary": story["summary"],
        "body": story["body"],
        "county": story["county"],
        "county_score": story["county_score"],
        "county_scores": story["county_scores"],
        "publication_datetime": (
            story["publication_datetime"]
        ),
        "age_hours": story["age_hours"],
        "freshness_score": (
            story["freshness_score"]
        ),
        "quality_score": (
            story["quality_score"]
        ),
        "selection_score": (
            story["selection_score"]
        ),
        "image_count": len(image_paths),
        "image_paths": image_paths,
        "image_urls": image_urls,
        "image_sources": [
            {
                "path": path,
                "url": url,
            }
            for path, url in zip(
                image_paths,
                image_urls,
            )
        ],
    }


def write_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# VALIDATION
# ============================================================

def validate_selected_story(story_data):
    section("VALIDATING SELECTED STORY")

    required_fields = [
        "source",
        "source_domain",
        "url",
        "title",
        "county",
        "publication_datetime",
        "image_paths",
        "image_urls",
    ]

    for field in required_fields:
        if field not in story_data:
            raise RuntimeError(
                f"Missing selected story field: "
                f"{field}"
            )

    if not story_data["title"]:
        raise RuntimeError(
            "Selected story title is empty."
        )

    if not story_data["county"]:
        raise RuntimeError(
            "Selected story county is empty."
        )

    if not is_approved_domain(
        story_data["url"]
    ):
        raise RuntimeError(
            "Selected story URL is not approved."
        )

    if story_data["source_domain"] == "citizen.digital":
        raise RuntimeError(
            "Citizen Digital must not be selected."
        )

    publication_dt = parse_datetime(
        story_data[
            "publication_datetime"
        ]
    )

    if not publication_dt:
        raise RuntimeError(
            "Selected publication date is invalid."
        )

    if not is_fresh(publication_dt):
        raise RuntimeError(
            "Selected story is outside freshness window."
        )

    image_paths = story_data["image_paths"]

    if not image_paths:
        raise RuntimeError(
            "No story images were selected."
        )

    existing_images = []

    for relative_path in image_paths:
        image_path = ROOT / relative_path

        if not image_path.exists():
            raise RuntimeError(
                f"Story image missing: "
                f"{image_path}"
            )

        try:
            with Image.open(image_path) as image:
                image.verify()

            with Image.open(image_path) as image:
                width, height = image.size

            if (
                width < MIN_IMAGE_WIDTH
                or height < MIN_IMAGE_HEIGHT
            ):
                raise RuntimeError(
                    f"Story image too small: "
                    f"{image_path}"
                )

            existing_images.append(
                image_path
            )

        except Exception as exc:
            raise RuntimeError(
                f"Invalid story image "
                f"{image_path}: {exc}"
            )

    log(
        f"Selected county: "
        f"{story_data['county']}"
    )

    log(
        f"Selected source: "
        f"{story_data['source']}"
    )

    log(
        f"Selected title: "
        f"{story_data['title']}"
    )

    log(
        f"Verified real images: "
        f"{len(existing_images)}"
    )

    log("SELECTED STORY VALIDATION PASSED")


def validate_selected_script(script_data):
    section("VALIDATING SELECTED SCRIPT")

    script = script_data.get(
        "script",
        "",
    )

    if not script:
        raise RuntimeError(
            "Selected script is empty."
        )

    words = word_count(script)

    if words < 50:
        raise RuntimeError(
            "Selected script is too short."
        )

    if words > 180:
        raise RuntimeError(
            "Selected script is too long."
        )

    log(
        f"Narration words: {words}"
    )

    log(
        "SELECTED SCRIPT VALIDATION PASSED"
    )


# ============================================================
# PROJECT VALIDATION
# ============================================================

def verify_project_files():
    section("VERIFYING PROJECT FILES")

    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py "
            "was not found."
        )

    log(
        f"Main: {__file__}"
    )

    log(
        f"Video generator: "
        f"{VIDEO_GENERATOR}"
    )

    log("")
    log("Checking Python syntax...")

    result_main = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(Path(__file__)),
        ],
        capture_output=True,
        text=True,
    )

    if result_main.returncode != 0:
        log(result_main.stdout)
        log(result_main.stderr)

        raise RuntimeError(
            "rift_valley_main.py failed syntax check."
        )

    result_renderer = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(VIDEO_GENERATOR),
        ],
        capture_output=True,
        text=True,
    )

    if result_renderer.returncode != 0:
        log(result_renderer.stdout)
        log(result_renderer.stderr)

        raise RuntimeError(
            "rift_valley_video_generator.py "
            "failed syntax check."
        )

    log(
        "PYTHON SYNTAX CHECK PASSED"
    )


# ============================================================
# DISCOVERY
# ============================================================

def discover():
    section("DISCOVERING CURRENT RIFT VALLEY STORIES")

    candidates = []
    seen_urls = set()

    for source in SOURCE_PAGES:
        log("")
        log(
            f"SOURCE: {source['name']}"
        )

        links = discover_links(source)

        log(
            f"Article links found: "
            f"{len(links)}"
        )

        for item in links:
            article_url = item["url"]

            if article_url in seen_urls:
                continue

            seen_urls.add(article_url)

            story = extract_article(
                source,
                article_url,
            )

            if story is None:
                continue

            candidates.append(story)

            log(
                "ACCEPTED: "
                f"[{story['county']}] "
                f"{story['title']}"
            )

            if (
                len(candidates)
                >= MAX_SELECTED_CANDIDATES
            ):
                break

        if (
            len(candidates)
            >= MAX_SELECTED_CANDIDATES
        ):
            break

    log("")
    log(
        f"Usable candidates: "
        f"{len(candidates)}"
    )

    return candidates


# ============================================================
# GENERATOR EXECUTION
# ============================================================

def run_generator():
    section("RUNNING VIDEO GENERATOR")

    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "Video generator file does not exist."
        )

    command = [
        sys.executable,
        "-u",
        str(VIDEO_GENERATOR),
    ]

    log(
        "Command: "
        + " ".join(command)
    )

    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            timeout=VIDEO_TIMEOUT,
            check=False,
        )

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Video generator timed out."
        )

    if result.returncode != 0:
        raise RuntimeError(
            "Video generator failed with "
            f"exit code {result.returncode}."
        )

    log(
        "Video generator completed."
    )


# ============================================================
# FINAL VIDEO VALIDATION
# ============================================================

def ffprobe_value(
    args,
    file_path,
):
    command = [
        "ffprobe",
        "-v",
        "error",
        *args,
        str(file_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def verify_final_video():
    section("VERIFYING FINAL MP4")

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not generated."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    width = ffprobe_value(
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    height = ffprobe_value(
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    duration = ffprobe_value(
        [
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    video_codec = ffprobe_value(
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    audio_codec = ffprobe_value(
        [
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    audio_stream = ffprobe_value(
        [
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
        ],
        FINAL_VIDEO,
    )

    log(
        f"MP4 size: {size} bytes"
    )

    log(
        f"Width: {width}"
    )

    log(
        f"Height: {height}"
    )

    log(
        f"Duration: {duration} seconds"
    )

    log(
        f"Video codec: {video_codec}"
    )

    log(
        f"Audio codec: {audio_codec}"
    )

    if width != "1080":
        raise RuntimeError(
            f"Video width is {width}, expected 1080."
        )

    if height != "1920":
        raise RuntimeError(
            f"Video height is {height}, expected 1920."
        )

    if not audio_stream:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    try:
        duration_value = float(
            duration
        )
    except Exception:
        duration_value = 0

    if duration_value < 5:
        raise RuntimeError(
            "Final MP4 duration is less than 5 seconds."
        )

    log("")
    log(
        "FINAL MP4 VERIFICATION PASSED"
    )


# ============================================================
# REPORT
# ============================================================

def report_files():
    section("GENERATED FILES")

    log("")
    log("SELECTED STORY:")
    if STORY_FILE.exists():
        log(str(STORY_FILE))
        log(
            f"Size: "
            f"{STORY_FILE.stat().st_size} bytes"
        )

    log("")
    log("SELECTED SCRIPT:")
    if SCRIPT_FILE.exists():
        log(str(SCRIPT_FILE))
        log(
            f"Size: "
            f"{SCRIPT_FILE.stat().st_size} bytes"
        )

    log("")
    log("NARRATION:")
    if NARRATION_FILE.exists():
        log(str(NARRATION_FILE))
        log(
            f"Size: "
            f"{NARRATION_FILE.stat().st_size} bytes"
        )

    log("")
    log("STORY IMAGES:")

    image_files = sorted(
        SOURCE_DIR.glob(
            "story_image*"
        )
    )

    for image_file in image_files:
        log(
            f"{image_file} "
            f"({image_file.stat().st_size} bytes)"
        )

    log("")
    log("FINAL VIDEO:")

    if FINAL_VIDEO.exists():
        log(str(FINAL_VIDEO))
        log(
            f"Size: "
            f"{FINAL_VIDEO.stat().st_size} bytes"
        )


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    section(
        "RIFT VALLEY WATCH"
    )

    log(
        "RVW_MAIN_V14_STABLE_REALTIME_MULTI_PHOTO"
    )

    log(
        f"Root: {ROOT}"
    )

    try:
        ensure_directories()

        clean_previous()

        verify_project_files()

        candidates = discover()

        if not candidates:
            raise RuntimeError(
                "No current usable Rift Valley "
                "article was found."
            )

        selected = select_best(
            candidates
        )

        if selected is None:
            raise RuntimeError(
                "No story could be selected."
            )

        section("SELECTED STORY")

        log(
            f"County: {selected['county']}"
        )

        log(
            f"Source: {selected['source']}"
        )

        log(
            f"Title: {selected['title']}"
        )

        log(
            f"Published: "
            f"{selected['publication_datetime']}"
        )

        log(
            f"Age: "
            f"{selected['age_hours']:.2f} hours"
        )

        log(
            f"Images available: "
            f"{selected['image_count']}"
        )

        # Save the photographs selected during article extraction.
        image_paths, image_urls, image_metadata = (
            save_article_images(
                selected["image_items"]
            )
        )

        if not image_paths:
            raise RuntimeError(
                "No article photograph could be saved."
            )

        # Build narration.
        script = build_script(
            selected
        )

        script_word_count = word_count(
            script
        )

        section("SELECTED SCRIPT")

        log(script)
        log("")
        log(
            f"Word count: "
            f"{script_word_count}"
        )

        if not generate_narration(
            script
        ):
            raise RuntimeError(
                "Narration generation failed."
            )

        story_data = make_story_json(
            selected,
            image_paths,
            image_urls,
        )

        # Add explicit provenance.
        story_data[
            "image_metadata"
        ] = image_metadata

        story_data[
            "narration_file"
        ] = "audio/narration.mp3"

        story_data[
            "renderer"
        ] = (
            "rift_valley_video_generator.py"
        )

        script_data = {
            "version": "RVW_MAIN_V14",
            "generated_at": (
                now_kenya().isoformat()
            ),
            "county": selected["county"],
            "title": selected["title"],
            "script": script,
            "word_count": script_word_count,
            "source": selected["source"],
            "source_url": selected["url"],
            "image_count": len(image_paths),
            "image_paths": image_paths,
            "image_urls": image_urls,
            "narration_file": (
                "audio/narration.mp3"
            ),
        }

        write_json(
            STORY_FILE,
            story_data,
        )

        write_json(
            SCRIPT_FILE,
            script_data,
        )

        validate_selected_story(
            story_data
        )

        validate_selected_script(
            script_data
        )

        log("")
        log(
            "selected_story.json written:"
        )
        log(
            str(STORY_FILE)
        )

        log("")
        log(
            "selected_script.json written:"
        )
        log(
            str(SCRIPT_FILE)
        )

        run_generator()

        verify_final_video()

        report_files()

        elapsed = time.time() - start_time

        section(
            "RIFT VALLEY WATCH GENERATION SUCCESSFUL"
        )

        log(
            f"Final MP4: {FINAL_VIDEO}"
        )

        log(
            f"Total runtime: "
            f"{elapsed:.1f} seconds"
        )

        log("")
        log(
            "REAL ARTICLE PHOTOS USED: "
            f"{len(image_paths)}"
        )

        log(
            "Citizen Digital was excluded "
            "as a news source."
        )

        log(
            "Generation completed successfully."
        )

        return 0

    except KeyboardInterrupt:
        log("")
        log(
            "Generation interrupted."
        )
        return 130

    except Exception as exc:
        section(
            "RIFT VALLEY WATCH GENERATION FAILED"
        )

        log(
            f"ERROR: {exc}"
        )

        log("")
        log(
            "Traceback:"
        )

        import traceback

        traceback.print_exc()

        return 1


if __name__ == "__main__":
    sys.exit(main())
