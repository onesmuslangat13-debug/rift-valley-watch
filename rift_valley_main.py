from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta
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
# RVW_MAIN_V13_REALTIME_STRICT_COUNTY
#
# PURPOSE
# - Select ONE current article
# - Enforce strict county isolation
# - Reject stale stories
# - Reject ambiguous multi-county stories
# - Resolve REAL article photos
# - Never use generic placeholders/logos/avatars
# - Generate selected_story.json
# - Generate selected_script.json
# - Launch the existing video generator
#
# COMPATIBLE WITH:
# rift_valley_video_generator.py V25
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
# VERSION
# ============================================================

MAIN_GENERATOR_VERSION = "RVW_MAIN_V13_REALTIME_STRICT_COUNTY"


# ============================================================
# COUNTY CONFIGURATION
# ============================================================

COUNTY_ALIASES = {
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chepalungu",
        "Konoin",
        "Kembu",
        "Kaplong",
        "Koiwa",
        "Ndanai",
        "Sigor",
    ],

    "Kericho": [
        "Kericho",
        "Litein",
        "Kipkelion",
        "Ainamoi",
        "Belgut",
        "Bureti",
        "Londiani",
        "Kabianga",
        "Kapsoit",
        "Kapsuser",
    ],

    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
        "Bahati",
        "Subukia",
        "Rongai",
        "Kuresoi",
        "Mai Mahiu",
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Mosop",
        "Aldai",
        "Emgwen",
        "Chesumei",
        "Nandi Hills",
        "Kabiyet",
        "Kebulwet",
    ],

    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Turbo",
        "Moiben",
        "Ainabkoi",
        "Soy",
        "Kapseret",
    ],

    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Elgeyo",
        "Marakwet",
        "Iten",
        "Keiyo",
        "Keiyo South",
        "Keiyo North",
        "Marakwet East",
        "Marakwet West",
        "Kapsowar",
        "Chebiemit",
        "Tambach",
    ],

    "West Pokot": [
        "West Pokot",
        "Pokot",
        "Kapenguria",
        "Kacheliba",
        "Sigor",
        "Pokot South",
        "Pokot Central",
        "Pokot North",
        "Alale",
        "Chepareria",
    ],

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Transmara",
        "Narok North",
        "Narok South",
        "Loita",
        "Ewaso Ng'iro",
        "Ewaso Ngiro",
    ],
}


COUNTIES = list(COUNTY_ALIASES.keys())


# ============================================================
# NEWS SOURCES
# ============================================================

SOURCE_PAGES = [
    "https://citizen.digital/",
    "https://www.the-star.co.ke/news/",
    "https://www.kbc.co.ke/",
    "https://nation.africa/kenya/news",
]


APPROVED_DOMAINS = {
    "citizen.digital",
    "the-star.co.ke",
    "kbc.co.ke",
    "nation.africa",
}


BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "tiktok.com",
    "www.tiktok.com",
    "telegram.me",
    "t.me",
    "whatsapp.com",
    "google.com",
    "news.google.com",
}


# ============================================================
# IMAGE FILTERS
# ============================================================

BAD_IMAGE_TERMS = {
    "google",
    "google-news",
    "google_news",
    "googlelogo",
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
    "dummy",
    "blank",
    "transparent",
    "tracking",
    "pixel",
}


# ============================================================
# SETTINGS
# ============================================================

MAX_ARTICLES_PER_SOURCE = 45
MAX_SELECTED_CANDIDATES = 20
MAX_ARTICLE_IMAGES = 8
MAX_STORED_IMAGE_URLS = 8

MIN_ARTICLE_BODY_WORDS = 45

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

# Strict freshness.
#
# Articles older than this are rejected.
MAX_ARTICLE_AGE_HOURS = 48

# Strong preference for the newest stories.
EXCELLENT_FRESHNESS_HOURS = 12
GOOD_FRESHNESS_HOURS = 24
ACCEPTABLE_FRESHNESS_HOURS = 36

# Future dates beyond this tolerance are rejected.
FUTURE_TOLERANCE_MINUTES = 15

REQUEST_TIMEOUT = 25
IMAGE_TIMEOUT = 30

VIDEO_TIMEOUT_SECONDS = 900


# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-KE,en-US;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


IMAGE_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def clean(value):
    if value is None:
        return ""

    value = html.unescape(str(value))

    value = unicodedata.normalize(
        "NFKC",
        value,
    )

    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_for_match(value):
    value = clean(value).lower()

    value = value.replace("’", "'")
    value = value.replace("–", "-")
    value = value.replace("—", "-")

    return value


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    temporary.replace(path)


def domain(url):
    try:
        hostname = urlparse(url).hostname or ""
        hostname = hostname.lower().strip()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:
        return ""


def blocked(url):
    host = domain(url)

    if not host:
        return True

    for blocked_domain in BLOCKED_DOMAINS:
        if host == blocked_domain:
            return True

        if host.endswith("." + blocked_domain):
            return True

    return False


def approved(url):
    host = domain(url)

    if not host:
        return False

    if blocked(url):
        return False

    for approved_domain in APPROVED_DOMAINS:
        if host == approved_domain:
            return True

        if host.endswith("." + approved_domain):
            return True

    return False


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def absolute_url(base_url, value):
    value = clean(value)

    if not value:
        return ""

    if value.startswith("//"):
        return "https:" + value

    return urljoin(
        base_url,
        value,
    )


# ============================================================
# FETCH
# ============================================================

def fetch(url, require_html=False):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            print(
                f"    HTTP {response.status_code}: {url}"
            )
            return None

        if require_html:
            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                ).lower()
            )

            if (
                "html" not in content_type
                and "xhtml" not in content_type
            ):
                return None

        return response

    except Exception as exc:
        print(
            f"    FETCH FAILED: {url} -> {exc}"
        )
        return None


# ============================================================
# COUNTY DETECTION
# ============================================================

def alias_pattern(alias):
    escaped = re.escape(
        normalize_for_match(alias)
    )

    escaped = escaped.replace(
        r"\ ",
        r"\s+",
    )

    return re.compile(
        r"(?<![a-z0-9])"
        + escaped
        + r"(?![a-z0-9])",
        re.IGNORECASE,
    )


def count_alias(text, alias):
    if not text:
        return 0

    pattern = alias_pattern(alias)

    return len(
        pattern.findall(
            normalize_for_match(text)
        )
    )


def county_scores(title="", summary="", body=""):
    title = clean(title)
    summary = clean(summary)
    body = clean(body)

    scores = {}
    raw_counts = {}

    for county, aliases in COUNTY_ALIASES.items():

        title_count = 0
        summary_count = 0
        body_count = 0

        for alias in aliases:
            title_count += count_alias(
                title,
                alias,
            )

            summary_count += count_alias(
                summary,
                alias,
            )

            body_count += count_alias(
                body,
                alias,
            )

        weighted = (
            title_count * 8
            + summary_count * 5
            + body_count
        )

        scores[county] = weighted

        raw_counts[county] = (
            title_count
            + summary_count
            + body_count
        )

    return scores, raw_counts


def counties_in_title(title):
    found = []

    for county, aliases in COUNTY_ALIASES.items():
        for alias in aliases:
            if count_alias(title, alias) > 0:
                found.append(county)
                break

    return found


def detect_primary_county(title, summary, body):
    scores, raw_counts = county_scores(
        title,
        summary,
        body,
    )

    ordered = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    if not ordered:
        return {
            "county": "",
            "scores": {},
            "raw_counts": {},
            "ambiguous": True,
            "reason": "No counties detected.",
        }

    primary_county = ordered[0][0]
    primary_score = ordered[0][1]

    second_county = ""
    second_score = 0

    if len(ordered) > 1:
        second_county = ordered[1][0]
        second_score = ordered[1][1]

    title_counties = counties_in_title(
        title
    )

    # --------------------------------------------------------
    # A title containing two counties is considered ambiguous.
    # --------------------------------------------------------

    if len(title_counties) > 1:
        return {
            "county": primary_county,
            "scores": scores,
            "raw_counts": raw_counts,
            "ambiguous": True,
            "reason": (
                "Multiple counties detected in article title."
            ),
        }

    # --------------------------------------------------------
    # The primary county must have meaningful evidence.
    # --------------------------------------------------------

    if primary_score < 5:
        return {
            "county": primary_county,
            "scores": scores,
            "raw_counts": raw_counts,
            "ambiguous": True,
            "reason": (
                "Insufficient county evidence."
            ),
        }

    # --------------------------------------------------------
    # Reject stories where two counties have comparable
    # importance.
    # --------------------------------------------------------

    if (
        second_score >= 8
        and second_score >= primary_score * 0.55
    ):
        return {
            "county": primary_county,
            "scores": scores,
            "raw_counts": raw_counts,
            "ambiguous": True,
            "reason": (
                f"Competing counties: "
                f"{primary_county} and {second_county}."
            ),
        }

    # --------------------------------------------------------
    # Reject articles that explicitly put two counties in
    # the headline/summary.
    # --------------------------------------------------------

    summary_counties = []

    for county, aliases in COUNTY_ALIASES.items():
        for alias in aliases:
            if count_alias(summary, alias) > 0:
                summary_counties.append(county)
                break

    combined_strong = set(
        title_counties
        + summary_counties
    )

    if len(combined_strong) > 1:
        return {
            "county": primary_county,
            "scores": scores,
            "raw_counts": raw_counts,
            "ambiguous": True,
            "reason": (
                "Multiple counties appear in headline/summary."
            ),
        }

    # --------------------------------------------------------
    # If another county is mentioned many times in body,
    # reject it.
    # --------------------------------------------------------

    if (
        second_score >= 12
        and second_score >= primary_score * 0.40
    ):
        return {
            "county": primary_county,
            "scores": scores,
            "raw_counts": raw_counts,
            "ambiguous": True,
            "reason": (
                f"Secondary county has substantial presence: "
                f"{second_county}."
            ),
        }

    return {
        "county": primary_county,
        "scores": scores,
        "raw_counts": raw_counts,
        "ambiguous": False,
        "reason": "Single dominant county detected.",
    }


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    title = clean(title)

    title = re.sub(
        r"\s+\|\s+[^|]+$",
        "",
        title,
    )

    title = re.sub(
        r"\s+-\s+(Citizen Digital|The Star|KBC|Nation)$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"^\s*(BREAKING|LATEST)\s*:\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return clean(title)


# ============================================================
# METADATA CLEANING
# ============================================================

def remove_metadata(text):
    text = clean(text)

    remove_patterns = [
        r"follow us on .*",
        r"subscribe to .*",
        r"read more .*",
        r"click here .*",
        r"advertisement",
        r"advertising",
    ]

    for pattern in remove_patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    return clean(text)


# ============================================================
# ARTICLE LINK DISCOVERY
# ============================================================

def is_probable_article_link(url, anchor_text=""):
    if not approved(url):
        return False

    parsed = urlparse(url)

    path = (
        parsed.path or ""
    ).lower()

    if len(path) < 8:
        return False

    excluded_fragments = [
        "/video",
        "/videos",
        "/photo",
        "/photos",
        "/gallery",
        "/author",
        "/authors",
        "/tag",
        "/tags",
        "/category",
        "/categories",
        "/search",
        "/contact",
        "/about",
        "/privacy",
        "/terms",
        "/advert",
        "/login",
        "/signup",
        "/subscribe",
    ]

    for fragment in excluded_fragments:
        if fragment in path:
            return False

    text = clean(anchor_text)

    if len(text) < 15:
        return False

    return True


def discover_links(page_url):
    print("")
    print(
        "    DISCOVERING ARTICLES:",
        page_url,
    )

    response = fetch(
        page_url,
        require_html=True,
    )

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    links = []
    seen = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href")

        if not href:
            continue

        url = absolute_url(
            page_url,
            href,
        )

        if not valid_http_url(url):
            continue

        if not approved(url):
            continue

        text = clean(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not is_probable_article_link(
            url,
            text,
        ):
            continue

        normalized = url.split("#")[0].rstrip("/")

        if normalized in seen:
            continue

        seen.add(normalized)

        title_counties = counties_in_title(
            text
        )

        links.append(
            {
                "url": normalized,
                "anchor_text": text,
                "county_hint": (
                    title_counties[0]
                    if len(title_counties) == 1
                    else ""
                ),
                "county_count": len(
                    title_counties
                ),
            }
        )

    # --------------------------------------------------------
    # Prioritize links with a single county hint.
    # --------------------------------------------------------

    links.sort(
        key=lambda item: (
            0
            if item["county_hint"]
            else 1,
            item["county_count"],
        )
    )

    print(
        f"    Discovered {len(links)} article candidates."
    )

    return links[:MAX_ARTICLES_PER_SOURCE]


# ============================================================
# PUBLICATION DATE EXTRACTION
# ============================================================

DATE_META_NAMES = {
    "article:published_time",
    "article:published",
    "datepublished",
    "datepublishedtime",
    "publishdate",
    "published",
    "published_time",
    "publication_date",
    "date",
    "pubdate",
    "dc.date",
    "dc.date.issued",
    "datecreated",
}


def parse_datetime_value(value):
    value = clean(value)

    if not value:
        return None

    value = value.replace(
        "Z",
        "+00:00",
    )

    # --------------------------------------------------------
    # ISO date/time.
    # --------------------------------------------------------

    try:
        parsed = datetime.fromisoformat(
            value
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Common date formats.
    # --------------------------------------------------------

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y %H:%M",
        "%b %d, %Y %H:%M",
        "%d %B %Y %H:%M",
        "%d %b %Y %H:%M",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(
                value,
                fmt,
            )

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

            return parsed

        except Exception:
            continue

    return None


def recursive_find_dates(value):
    found = []

    if isinstance(value, dict):
        for key, child in value.items():

            key_normalized = (
                clean(key)
                .lower()
                .replace(" ", "")
                .replace("-", "")
                .replace("_", "")
            )

            if key_normalized in {
                "datepublished",
                "datecreated",
                "publishedtime",
                "publisheddate",
            }:
                if isinstance(child, str):
                    parsed = parse_datetime_value(
                        child
                    )

                    if parsed:
                        found.append(
                            (
                                key_normalized,
                                parsed,
                            )
                        )

            found.extend(
                recursive_find_dates(child)
            )

    elif isinstance(value, list):
        for child in value:
            found.extend(
                recursive_find_dates(child)
            )

    return found


def extract_publication_date(soup):
    candidates = []

    # --------------------------------------------------------
    # Meta tags.
    # --------------------------------------------------------

    for meta in soup.find_all("meta"):

        key = clean(
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
            or ""
        ).lower()

        value = clean(
            meta.get("content")
            or ""
        )

        if not value:
            continue

        key_normalized = (
            key
            .replace(" ", "")
            .replace("-", "")
            .replace("_", "")
        )

        if (
            key in DATE_META_NAMES
            or key_normalized in DATE_META_NAMES
        ):
            parsed = parse_datetime_value(
                value
            )

            if parsed:
                candidates.append(
                    (
                        "metadata",
                        parsed,
                    )
                )

    # --------------------------------------------------------
    # <time datetime="">
    # --------------------------------------------------------

    for tag in soup.find_all("time"):

        value = clean(
            tag.get("datetime")
            or tag.get("content")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        parsed = parse_datetime_value(
            value
        )

        if parsed:
            candidates.append(
                (
                    "time",
                    parsed,
                )
            )

    # --------------------------------------------------------
    # JSON-LD.
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.IGNORECASE,
            )
        },
    ):

        raw = script.string or script.get_text()

        raw = clean(raw)

        if not raw:
            continue

        try:
            data = json.loads(raw)

        except Exception:
            continue

        for key, parsed in recursive_find_dates(
            data
        ):

            if key == "datepublished":
                candidates.append(
                    (
                        "jsonld_published",
                        parsed,
                    )
                )

            else:
                candidates.append(
                    (
                        "jsonld",
                        parsed,
                    )
                )

    # --------------------------------------------------------
    # Prefer explicitly published timestamps.
    # --------------------------------------------------------

    if not candidates:
        return None, ""

    published = [
        item
        for item in candidates
        if (
            "published" in item[0]
            or item[0] == "metadata"
        )
    ]

    if published:
        published.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return (
            published[0][1],
            published[0][0],
        )

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    return (
        candidates[0][1],
        candidates[0][0],
    )


def validate_publication_date(published_at):
    if published_at is None:
        return {
            "valid": False,
            "reason": "No publication timestamp found.",
            "age_hours": None,
            "freshness": "UNKNOWN",
        }

    now = datetime.now(
        timezone.utc
    )

    if published_at > now + timedelta(
        minutes=FUTURE_TOLERANCE_MINUTES
    ):
        return {
            "valid": False,
            "reason": "Publication date is in the future.",
            "age_hours": None,
            "freshness": "INVALID",
        }

    age_seconds = (
        now - published_at
    ).total_seconds()

    age_hours = age_seconds / 3600.0

    if age_hours < 0:
        age_hours = 0

    if age_hours > MAX_ARTICLE_AGE_HOURS:
        return {
            "valid": False,
            "reason": (
                f"Article is {age_hours:.1f} hours old."
            ),
            "age_hours": age_hours,
            "freshness": "STALE",
        }

    if age_hours <= EXCELLENT_FRESHNESS_HOURS:
        freshness = "EXCELLENT"

    elif age_hours <= GOOD_FRESHNESS_HOURS:
        freshness = "VERY GOOD"

    elif age_hours <= ACCEPTABLE_FRESHNESS_HOURS:
        freshness = "GOOD"

    else:
        freshness = "ACCEPTABLE"

    return {
        "valid": True,
        "reason": "Article is within realtime window.",
        "age_hours": age_hours,
        "freshness": freshness,
    }


def freshness_score(age_hours):
    if age_hours is None:
        return 0

    if age_hours <= 3:
        return 140

    if age_hours <= 6:
        return 125

    if age_hours <= 12:
        return 110

    if age_hours <= 18:
        return 95

    if age_hours <= 24:
        return 80

    if age_hours <= 36:
        return 55

    if age_hours <= 48:
        return 25

    return 0


# ============================================================
# IMAGE HELPERS
# ============================================================

def bad_image_url(url):
    if not valid_http_url(url):
        return True

    lowered = (
        normalize_for_match(url)
    )

    for term in BAD_IMAGE_TERMS:
        if term in lowered:
            return True

    parsed = urlparse(url)

    path = (
        parsed.path
        or ""
    ).lower()

    if path.endswith(
        (
            ".svg",
            ".ico",
        )
    ):
        return True

    if "data:image" in lowered:
        return True

    return False


def add_image_candidate(
    candidates,
    url,
    base_url,
):
    url = absolute_url(
        base_url,
        url,
    )

    if not valid_http_url(url):
        return

    if bad_image_url(url):
        return

    # Remove obvious tracking/query noise where possible.
    url = url.strip()

    if url not in candidates:
        candidates.append(url)


def parse_srcset(
    srcset,
    candidates,
    base_url,
):
    if not srcset:
        return

    parts = srcset.split(",")

    for part in parts:
        item = part.strip()

        if not item:
            continue

        pieces = item.split()

        if not pieces:
            continue

        add_image_candidate(
            candidates,
            pieces[0],
            base_url,
        )


def recursive_find_images(
    value,
    candidates,
    base_url,
):
    if isinstance(value, dict):

        preferred_keys = {
            "image",
            "images",
            "imageurl",
            "image_url",
            "imageurlsecure",
            "thumbnail",
            "thumbnailurl",
            "thumbnail_url",
            "contenturl",
            "content_url",
            "contentimage",
            "content_image",
        }

        for key, child in value.items():

            key_normalized = (
                clean(key)
                .lower()
                .replace("-", "")
                .replace("_", "")
                .replace(" ", "")
            )

            if (
                key_normalized
                in {
                    item.replace(
                        "_",
                        "",
                    ).replace(
                        "-",
                        "",
                    )
                    for item in preferred_keys
                }
            ):

                if isinstance(child, str):
                    add_image_candidate(
                        candidates,
                        child,
                        base_url,
                    )

                elif isinstance(child, list):
                    for item in child:
                        if isinstance(
                            item,
                            str,
                        ):
                            add_image_candidate(
                                candidates,
                                item,
                                base_url,
                            )

                        elif isinstance(
                            item,
                            dict,
                        ):
                            recursive_find_images(
                                item,
                                candidates,
                                base_url,
                            )

                elif isinstance(
                    child,
                    dict,
                ):
                    recursive_find_images(
                        child,
                        candidates,
                        base_url,
                    )

            # Continue recursion.
            if isinstance(
                child,
                (dict, list),
            ):
                recursive_find_images(
                    child,
                    candidates,
                    base_url,
                )

    elif isinstance(value, list):

        for child in value:
            recursive_find_images(
                child,
                candidates,
                base_url,
            )


def get_image_candidates(
    soup,
    article_url,
):
    candidates = []

    # --------------------------------------------------------
    # OpenGraph.
    # --------------------------------------------------------

    for meta in soup.find_all(
        "meta"
    ):

        property_name = clean(
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = clean(
            meta.get("content")
            or ""
        )

        if not content:
            continue

        if property_name in {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }:

            add_image_candidate(
                candidates,
                content,
                article_url,
            )

    # --------------------------------------------------------
    # Itemprop image.
    # --------------------------------------------------------

    for tag in soup.find_all(
        attrs={
            "itemprop": re.compile(
                r"image",
                re.IGNORECASE,
            )
        }
    ):

        for attribute in [
            "content",
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
        ]:

            value = tag.get(
                attribute
            )

            if value:
                add_image_candidate(
                    candidates,
                    value,
                    article_url,
                )

    # --------------------------------------------------------
    # JSON-LD.
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.IGNORECASE,
            )
        },
    ):

        raw = script.string or script.get_text()

        raw = clean(raw)

        if not raw:
            continue

        try:
            data = json.loads(raw)

        except Exception:
            continue

        recursive_find_images(
            data,
            candidates,
            article_url,
        )

    # --------------------------------------------------------
    # Actual article/main images.
    # --------------------------------------------------------

    containers = []

    for selector in [
        "article",
        "main",
        "[role='main']",
    ]:

        containers.extend(
            soup.select(selector)
        )

    if not containers:
        containers = [
            soup
        ]

    for container in containers:

        for image in container.find_all(
            "img"
        ):

            attributes = [
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-filename",
                "data-url",
            ]

            for attribute in attributes:

                value = image.get(
                    attribute
                )

                if value:
                    add_image_candidate(
                        candidates,
                        value,
                        article_url,
                    )

            parse_srcset(
                image.get("srcset"),
                candidates,
                article_url,
            )

            parse_srcset(
                image.get("data-srcset"),
                candidates,
                article_url,
            )

    return candidates[:100]


# ============================================================
# IMAGE DOWNLOAD / VALIDATION
# ============================================================

def download_image(
    url,
    destination,
):
    try:

        response = requests.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=IMAGE_TIMEOUT,
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
            and "octet-stream" not in content_type
        ):
            return None

        content = response.content

        if len(content) < 20_000:
            return None

        image = Image.open(
            BytesIO(content)
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

        # Reject tiny square-like icons.
        if (
            abs(width - height)
            < 20
            and width < 700
        ):
            return None

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        rgb_image = image.convert(
            "RGB"
        )

        rgb_image.save(
            destination,
            "JPEG",
            quality=94,
            optimize=True,
        )

        return {
            "requested_url": url,
            "final_url": response.url,
            "width": width,
            "height": height,
            "bytes": len(content),
            "path": str(destination),
        }

    except Exception:
        return None


def download_article_images(
    article_url,
    candidates,
):
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results = []
    seen_final_urls = set()

    for index, image_url in enumerate(
        candidates[:100]
    ):

        if len(results) >= MAX_ARTICLE_IMAGES:
            break

        print(
            f"      Checking image "
            f"{index + 1}: {image_url[:140]}"
        )

        destination = (
            SOURCE_DIR
            / f"story_image_{len(results) + 1}.jpg"
        )

        result = download_image(
            image_url,
            destination,
        )

        if result is None:
            continue

        final_url = (
            result.get(
                "final_url"
            )
            or image_url
        )

        if final_url in seen_final_urls:
            try:
                destination.unlink()
            except Exception:
                pass

            continue

        seen_final_urls.add(
            final_url
        )

        result["article_url"] = article_url

        results.append(
            result
        )

        print(
            f"      VALID REAL PHOTO: "
            f"{result['width']}x{result['height']}"
        )

    return results


# ============================================================
# ARTICLE TEXT EXTRACTION
# ============================================================

def extract_article_text(
    soup,
    title,
    description,
):
    paragraphs = []

    # --------------------------------------------------------
    # Prefer article containers.
    # --------------------------------------------------------

    containers = []

    for selector in [
        "article",
        "[itemprop='articleBody']",
        "main",
    ]:

        selected = soup.select(
            selector
        )

        if selected:
            containers.extend(
                selected
            )

    if not containers:
        containers = [
            soup
        ]

    seen = set()

    for container in containers:

        for paragraph in container.find_all(
            ["p", "h2", "h3"]
        ):

            text = clean(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text:
                continue

            if len(text) < 35:
                continue

            normalized = normalize_for_match(
                text
            )

            if normalized in seen:
                continue

            seen.add(
                normalized
            )

            # ------------------------------------------------
            # Remove obvious navigation/social junk.
            # ------------------------------------------------

            junk_terms = [
                "share this article",
                "follow us",
                "subscribe",
                "advertisement",
                "read also",
                "related stories",
                "click here",
                "download our app",
                "sign up",
            ]

            if any(
                term in normalized
                for term in junk_terms
            ):
                continue

            paragraphs.append(
                text
            )

    # --------------------------------------------------------
    # Remove duplicate consecutive paragraphs.
    # --------------------------------------------------------

    cleaned = []

    previous = ""

    for paragraph in paragraphs:

        normalized = normalize_for_match(
            paragraph
        )

        if normalized == previous:
            continue

        previous = normalized

        cleaned.append(
            paragraph
        )

    body = " ".join(
        cleaned
    )

    body = clean(
        body
    )

    if not body:
        body = clean(
            description
        )

    return body


# ============================================================
# STORY QUALITY SCORING
# ============================================================

POSITIVE_TERMS = [
    "county government",
    "governor",
    "deputy governor",
    "president",
    "government",
    "minister",
    "cabinet",
    "parliament",
    "mp",
    "senator",
    "development",
    "project",
    "launch",
    "launched",
    "hospital",
    "road",
    "school",
    "education",
    "health",
    "security",
    "police",
    "court",
    "arrest",
    "business",
    "economy",
    "farmers",
    "agriculture",
    "teachers",
    "residents",
    "accident",
    "flood",
    "fire",
    "crime",
    "community",
]


NEGATIVE_PHRASES = [
    "advertisement",
    "sponsored",
    "opinion",
    "lifestyle",
    "horoscope",
    "quiz",
    "watch live",
    "photo gallery",
]


def article_quality_score(
    title,
    summary,
    body,
    image_count,
):
    combined = normalize_for_match(
        " ".join(
            [
                title,
                summary,
                body,
            ]
        )
    )

    words = len(
        combined.split()
    )

    score = min(
        words // 5,
        220,
    )

    for term in POSITIVE_TERMS:

        if term in combined:
            score += 2

    for phrase in NEGATIVE_PHRASES:

        if phrase in combined:
            score -= 7

    score += min(
        image_count * 4,
        20,
    )

    # Better titles receive a small bonus.
    title_words = len(
        title.split()
    )

    if 6 <= title_words <= 25:
        score += 10

    if len(title) > 180:
        score -= 10

    return max(
        score,
        0,
    )


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(
    article_url,
    anchor_text="",
):
    print("")
    print(
        "    EXTRACTING:",
        article_url,
    )

    response = fetch(
        article_url,
        require_html=True,
    )

    if response is None:
        return None

    final_url = (
        response.url
        or article_url
    )

    if not approved(final_url):
        print(
            "      REJECTED: redirected outside approved source."
        )
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # Title.
    # --------------------------------------------------------

    title = ""

    og_title = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        },
    )

    if og_title:
        title = clean(
            og_title.get("content")
        )

    if not title:

        title_tag = soup.find(
            "title"
        )

        if title_tag:
            title = clean(
                title_tag.get_text()
            )

    if not title:

        heading = soup.find(
            "h1"
        )

        if heading:
            title = clean(
                heading.get_text(
                    " ",
                    strip=True,
                )
            )

    title = clean_title(
        title
    )

    if len(title) < 10:
        print(
            "      REJECTED: weak title."
        )
        return None

    # --------------------------------------------------------
    # Description.
    # --------------------------------------------------------

    description = ""

    for meta_name in [
        "description",
        "og:description",
        "twitter:description",
    ]:

        meta = soup.find(
            "meta",
            attrs={
                "name": meta_name
            },
        )

        if not meta:

            meta = soup.find(
                "meta",
                attrs={
                    "property": meta_name
                },
            )

        if meta:

            description = clean(
                meta.get("content")
            )

            if description:
                break

    description = remove_metadata(
        description
    )

    # --------------------------------------------------------
    # Publication date.
    # --------------------------------------------------------

    published_at, date_source = (
        extract_publication_date(
            soup
        )
    )

    freshness = validate_publication_date(
        published_at
    )

    if not freshness["valid"]:

        print(
            "      REJECTED FRESHNESS:",
            freshness["reason"],
        )

        return None

    age_hours = freshness[
        "age_hours"
    ]

    # --------------------------------------------------------
    # Body.
    # --------------------------------------------------------

    body = extract_article_text(
        soup,
        title,
        description,
    )

    word_count = len(
        body.split()
    )

    if word_count < MIN_ARTICLE_BODY_WORDS:

        print(
            "      REJECTED: body too short:",
            word_count,
        )

        return None

    # --------------------------------------------------------
    # County.
    # --------------------------------------------------------

    county_result = detect_primary_county(
        title,
        description,
        body,
    )

    if county_result["ambiguous"]:

        print(
            "      REJECTED COUNTY:",
            county_result["reason"],
        )

        return None

    county = county_result[
        "county"
    ]

    if not county:

        print(
            "      REJECTED: no county."
        )

        return None

    # --------------------------------------------------------
    # Image candidates.
    # --------------------------------------------------------

    image_candidates = get_image_candidates(
        soup,
        final_url,
    )

    if not image_candidates:

        print(
            "      REJECTED: no article image candidates."
        )

        return None

    # --------------------------------------------------------
    # Download and validate real article photos.
    # --------------------------------------------------------

    image_results = download_article_images(
        final_url,
        image_candidates,
    )

    if not image_results:

        print(
            "      REJECTED: no valid real article photos."
        )

        return None

    image_urls = []

    for result in image_results:

        final_image_url = (
            result.get(
                "final_url"
            )
            or result.get(
                "requested_url"
            )
        )

        if (
            final_image_url
            and final_image_url not in image_urls
        ):
            image_urls.append(
                final_image_url
            )

    image_urls = image_urls[
        :MAX_STORED_IMAGE_URLS
    ]

    # --------------------------------------------------------
    # Quality.
    # --------------------------------------------------------

    quality_score = article_quality_score(
        title,
        description,
        body,
        len(image_urls),
    )

    fresh_score = freshness_score(
        age_hours
    )

    county_score = county_result[
        "scores"
    ].get(
        county,
        0,
    )

    # County confidence contribution.
    county_confidence_score = min(
        county_score,
        60,
    )

    selection_score = (
        quality_score
        + fresh_score
        + county_confidence_score
    )

    published_iso = (
        published_at.astimezone(
            timezone.utc
        ).isoformat()
        if published_at
        else ""
    )

    print(
        f"      ACCEPTED: {county}"
    )

    print(
        f"      TITLE: {title}"
    )

    print(
        f"      PUBLISHED: {published_iso}"
    )

    print(
        f"      AGE: {age_hours:.1f} hours"
    )

    print(
        f"      FRESHNESS: {freshness['freshness']}"
    )

    print(
        f"      PHOTOS: {len(image_urls)}"
    )

    print(
        f"      QUALITY SCORE: {quality_score}"
    )

    print(
        f"      FRESHNESS SCORE: {fresh_score}"
    )

    print(
        f"      SELECTION SCORE: {selection_score}"
    )

    return {
        "title": title,
        "summary": description,
        "body": body,
        "county": county,
        "county_scores": county_result[
            "scores"
        ],
        "county_mentions": county_result[
            "raw_counts"
        ],
        "county_evidence": county_result[
            "reason"
        ],
        "url": final_url,
        "article_url": final_url,
        "source": domain(final_url),
        "anchor_text": clean(
            anchor_text
        ),
        "published_at": published_iso,
        "published_at_utc": published_iso,
        "publication_date_source": date_source,
        "age_hours": round(
            age_hours,
            2,
        ),
        "freshness": freshness[
            "freshness"
        ],
        "quality_score": quality_score,
        "freshness_score": fresh_score,
        "county_score": county_confidence_score,
        "selection_score": selection_score,
        "word_count": word_count,
        "image_candidates": image_candidates,
        "image_urls": image_urls,
        "image_results": image_results,
    }


# ============================================================
# NARRATION SCRIPT
# ============================================================

def split_sentences(text):
    text = clean(
        text
    )

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        clean(part)
        for part in parts
        if len(clean(part)) > 20
    ]


def build_script(article):
    county = clean(
        article["county"]
    )

    title = clean(
        article["title"]
    )

    summary = clean(
        article["summary"]
    )

    body = clean(
        article["body"]
    )

    sentences = split_sentences(
        body
    )

    script_parts = []

    opening = (
        f"In {county} County, "
        f"the latest development is "
        f"making headlines."
    )

    script_parts.append(
        opening
    )

    script_parts.append(
        title
    )

    if summary:
        script_parts.append(
            summary
        )

    # --------------------------------------------------------
    # Add article sentences until a useful narration length
    # is reached.
    # --------------------------------------------------------

    current_words = len(
        " ".join(
            script_parts
        ).split()
    )

    for sentence in sentences:

        if current_words >= 125:
            break

        normalized = normalize_for_match(
            sentence
        )

        # Avoid obvious navigation/social material.
        if any(
            term in normalized
            for term in [
                "follow us",
                "subscribe",
                "advertisement",
                "read more",
                "click here",
            ]
        ):
            continue

        script_parts.append(
            sentence
        )

        current_words = len(
            " ".join(
                script_parts
            ).split()
        )

    # --------------------------------------------------------
    # Hard maximum.
    # --------------------------------------------------------

    script = " ".join(
        script_parts
    )

    script = clean(
        script
    )

    words = script.split()

    if len(words) > 190:
        script = " ".join(
            words[:190]
        )

        if not script.endswith(
            (".", "!", "?")
        ):
            script += "."

    return script


# ============================================================
# STORY VALIDATION
# ============================================================

def validate_story(article):
    if not article:
        return False

    required = [
        "title",
        "county",
        "body",
        "article_url",
        "image_urls",
        "published_at",
    ]

    for key in required:

        if not article.get(key):
            print(
                f"VALIDATION FAILED: missing {key}"
            )
            return False

    if article["county"] not in COUNTIES:

        print(
            "VALIDATION FAILED: invalid county."
        )

        return False

    if not approved(
        article["article_url"]
    ):

        print(
            "VALIDATION FAILED: unapproved article domain."
        )

        return False

    freshness = validate_publication_date(
        parse_datetime_value(
            article["published_at"]
        )
    )

    if not freshness["valid"]:

        print(
            "VALIDATION FAILED: story is not fresh."
        )

        return False

    if len(
        article["image_urls"]
    ) < 1:

        print(
            "VALIDATION FAILED: no valid image."
        )

        return False

    county_result = detect_primary_county(
        article["title"],
        article["summary"],
        article["body"],
    )

    if county_result["ambiguous"]:

        print(
            "VALIDATION FAILED: county is ambiguous."
        )

        return False

    if county_result["county"] != article[
        "county"
    ]:

        print(
            "VALIDATION FAILED: county mismatch."
        )

        return False

    return True


# ============================================================
# WRITE SELECTED FILES
# ============================================================

def write_selected_files(article):
    selected_at = datetime.now(
        timezone.utc
    ).isoformat()

    script = build_script(
        article
    )

    image_urls = [
        url
        for url in article.get(
            "image_urls",
            [],
        )
        if valid_http_url(url)
    ]

    image_urls = image_urls[
        :MAX_STORED_IMAGE_URLS
    ]

    story_data = {
        "title": article["title"],
        "county": article["county"],
        "summary": article["summary"],
        "body": article["body"],
        "article_url": article["article_url"],
        "url": article["article_url"],
        "source": article["source"],
        "published_at": article["published_at"],
        "published_at_utc": article["published_at_utc"],
        "publication_date_source": article[
            "publication_date_source"
        ],
        "age_hours": article["age_hours"],
        "freshness": article["freshness"],
        "quality_score": article[
            "quality_score"
        ],
        "freshness_score": article[
            "freshness_score"
        ],
        "county_score": article[
            "county_score"
        ],
        "selection_score": article[
            "selection_score"
        ],
        "county_scores": article[
            "county_scores"
        ],
        "county_mentions": article[
            "county_mentions"
        ],
        "county_evidence": article[
            "county_evidence"
        ],
        "word_count": article[
            "word_count"
        ],
        "image_url": (
            image_urls[0]
            if image_urls
            else ""
        ),
        "image_urls": image_urls,
        "image_path": str(
            FINAL_IMAGE
        ),
        "selected_at": selected_at,
        "generator_version": MAIN_GENERATOR_VERSION,
    }

    script_data = {
        "title": article["title"],
        "county": article["county"],
        "script": script,
        "narration": script,
        "article_url": article["article_url"],
        "source": article["source"],
        "published_at": article[
            "published_at"
        ],
        "age_hours": article[
            "age_hours"
        ],
        "freshness": article[
            "freshness"
        ],
        "image_urls": image_urls,
        "selected_at": selected_at,
        "generator_version": MAIN_GENERATOR_VERSION,
    }

    save_json(
        SELECTED_STORY,
        story_data,
    )

    save_json(
        SELECTED_SCRIPT,
        script_data,
    )

    print("")
    print(
        "============================================================"
    )
    print(
        "SELECTED STORY FILES WRITTEN"
    )
    print(
        "============================================================"
    )

    print(
        "County:",
        article["county"],
    )

    print(
        "Title:",
        article["title"],
    )

    print(
        "Published:",
        article["published_at"],
    )

    print(
        "Age:",
        article["age_hours"],
        "hours",
    )

    print(
        "Freshness:",
        article["freshness"],
    )

    print(
        "Article:",
        article["article_url"],
    )

    print(
        "Photos:",
        len(image_urls),
    )

    print(
        "Script words:",
        len(
            script.split()
        ),
    )

    print(
        "selected_story.json:",
        SELECTED_STORY,
    )

    print(
        "selected_script.json:",
        SELECTED_SCRIPT,
    )


# ============================================================
# SAVE FIRST IMAGE
# ============================================================

def save_first_image(article):
    print("")
    print(
        "============================================================"
    )
    print(
        "SAVING PRIMARY STORY IMAGE"
    )
    print(
        "============================================================"
    )

    FINAL_IMAGE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Prefer already validated image URLs.
    # --------------------------------------------------------

    for index, image_url in enumerate(
        article.get(
            "image_urls",
            [],
        )
    ):

        print(
            f"  Primary image candidate {index + 1}:"
        )

        result = download_image(
            image_url,
            FINAL_IMAGE,
        )

        if result:

            print(
                "  PRIMARY IMAGE SAVED"
            )

            print(
                "  Source:",
                result["final_url"],
            )

            print(
                "  Dimensions:",
                result["width"],
                "x",
                result["height"],
            )

            article[
                "primary_image_url"
            ] = result["final_url"]

            return True

    # --------------------------------------------------------
    # Fallback to image candidates.
    # --------------------------------------------------------

    for index, image_url in enumerate(
        article.get(
            "image_candidates",
            [],
        )
    ):

        result = download_image(
            image_url,
            FINAL_IMAGE,
        )

        if result:

            print(
                "  PRIMARY IMAGE SAVED FROM FALLBACK"
            )

            article[
                "primary_image_url"
            ] = result["final_url"]

            return True

    print(
        "ERROR: Could not save primary story image."
    )

    return False


# ============================================================
# STORY SELECTION
# ============================================================

def select_best(candidates):
    if not candidates:
        return None

    # --------------------------------------------------------
    # Revalidate every candidate before selection.
    # --------------------------------------------------------

    valid = []

    for candidate in candidates:

        if not validate_story(
            candidate
        ):
            continue

        valid.append(
            candidate
        )

    if not valid:
        return None

    # --------------------------------------------------------
    # Freshness dominates.
    #
    # First: age
    # Second: overall selection score
    # Third: quality
    # Fourth: photo count
    # --------------------------------------------------------

    valid.sort(
        key=lambda item: (
            item.get(
                "age_hours",
                9999,
            ),
            -item.get(
                "selection_score",
                0,
            ),
            -item.get(
                "quality_score",
                0,
            ),
            -len(
                item.get(
                    "image_urls",
                    [],
                )
            ),
        )
    )

    # --------------------------------------------------------
    # A slightly more editorial ranking:
    #
    # Among very recent stories (<12 hours), allow the highest
    # scoring recent story to win, provided it isn't materially
    # older than the newest candidate.
    # --------------------------------------------------------

    newest_age = valid[0].get(
        "age_hours",
        9999,
    )

    recent_candidates = [
        item
        for item in valid
        if item.get(
            "age_hours",
            9999,
        ) <= min(
            EXCELLENT_FRESHNESS_HOURS,
            newest_age + 6,
        )
    ]

    if recent_candidates:

        recent_candidates.sort(
            key=lambda item: (
                -item.get(
                    "selection_score",
                    0,
                ),
                item.get(
                    "age_hours",
                    9999,
                ),
            )
        )

        selected = recent_candidates[0]

    else:
        selected = valid[0]

    print("")
    print(
        "============================================================"
    )
    print(
        "BEST STORY SELECTED"
    )
    print(
        "============================================================"
    )

    print(
        "County:",
        selected["county"],
    )

    print(
        "Title:",
        selected["title"],
    )

    print(
        "Published:",
        selected["published_at"],
    )

    print(
        "Age:",
        selected["age_hours"],
        "hours",
    )

    print(
        "Freshness:",
        selected["freshness"],
    )

    print(
        "Selection score:",
        selected["selection_score"],
    )

    print(
        "Photos:",
        len(
            selected["image_urls"]
        ),
    )

    print(
        "Article:",
        selected["article_url"],
    )

    return selected


# ============================================================
# DISCOVERY ENGINE
# ============================================================

def discover():
    print("")
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH DISCOVERY"
    )
    print(
        "REALTIME + STRICT COUNTY MODE"
    )
    print(
        "============================================================"
    )

    print(
        "Maximum article age:",
        MAX_ARTICLE_AGE_HOURS,
        "hours",
    )

    candidates = []

    global_seen_urls = set()

    for source_page in SOURCE_PAGES:

        print("")
        print(
            "SOURCE:",
            source_page,
        )

        links = discover_links(
            source_page
        )

        source_valid = 0

        for index, link in enumerate(
            links
        ):

            if len(candidates) >= (
                MAX_SELECTED_CANDIDATES
                * 2
            ):
                break

            article_url = link[
                "url"
            ]

            normalized_url = (
                article_url
                .split("?")[0]
                .rstrip("/")
            )

            if normalized_url in global_seen_urls:
                continue

            global_seen_urls.add(
                normalized_url
            )

            print("")
            print(
                f"  ARTICLE {index + 1}/{len(links)}"
            )

            article = extract_article(
                article_url,
                link.get(
                    "anchor_text",
                    "",
                ),
            )

            if article is None:
                continue

            source_valid += 1

            candidates.append(
                article
            )

        print(
            f"  Valid stories from source: "
            f"{source_valid}"
        )

    print("")
    print(
        "============================================================"
    )
    print(
        "DISCOVERY COMPLETE"
    )
    print(
        "============================================================"
    )

    print(
        "Valid candidates:",
        len(candidates),
    )

    # --------------------------------------------------------
    # Deduplicate by URL.
    # --------------------------------------------------------

    unique = {}

    for candidate in candidates:

        key = (
            candidate["article_url"]
            .split("?")[0]
            .rstrip("/")
        )

        existing = unique.get(
            key
        )

        if (
            existing is None
            or candidate[
                "selection_score"
            ]
            > existing[
                "selection_score"
            ]
        ):
            unique[key] = candidate

    candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Keep the best candidates for logging.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            item.get(
                "age_hours",
                9999,
            ),
            -item.get(
                "selection_score",
                0,
            ),
        )
    )

    print("")
    print(
        "CURRENT VALID STORIES:"
    )

    for index, candidate in enumerate(
        candidates[:20],
        start=1,
    ):

        print(
            f"{index:02d}. "
            f"{candidate['county']} | "
            f"{candidate['age_hours']:.1f}h | "
            f"{candidate['freshness']} | "
            f"{candidate['selection_score']} | "
            f"{candidate['title'][:100]}"
        )

    return candidates[
        :MAX_SELECTED_CANDIDATES
    ]


# ============================================================
# CLEAN PREVIOUS GENERATED FILES
# ============================================================

def clean_previous():
    print("")
    print(
        "============================================================"
    )
    print(
        "CLEANING PREVIOUS GENERATED FILES"
    )
    print(
        "============================================================"
    )

    files_to_remove = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
        AUDIO_DIR / "narration.mp3",
        AUDIO_DIR / "narration_temp.mp3",
        VIDEO_WORK_DIR / "narration.mp3",
    ]

    for path in files_to_remove:

        try:

            if path.exists():

                if path.is_file():
                    path.unlink()

                    print(
                        "Removed:",
                        path,
                    )

        except Exception as exc:

            print(
                "Could not remove:",
                path,
                exc,
            )

    # --------------------------------------------------------
    # Remove generated article photos.
    # --------------------------------------------------------

    if SOURCE_DIR.exists():

        for path in SOURCE_DIR.glob(
            "story_image_*.jpg"
        ):

            try:
                path.unlink()

                print(
                    "Removed:",
                    path,
                )

            except Exception:
                pass

    # --------------------------------------------------------
    # Remove generated scene files.
    # --------------------------------------------------------

    if VIDEO_WORK_DIR.exists():

        for path in VIDEO_WORK_DIR.iterdir():

            try:

                if path.is_file():
                    path.unlink()

            except Exception:
                pass

    # --------------------------------------------------------
    # Ensure directories exist.
    # --------------------------------------------------------

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Clean-up complete."
    )


# ============================================================
# PROJECT VERIFICATION
# ============================================================

def verify_project_files():
    print("")
    print(
        "============================================================"
    )
    print(
        "VERIFYING PROJECT"
    )
    print(
        "============================================================"
    )

    if not VIDEO_GENERATOR.exists():

        print(
            "ERROR: rift_valley_video_generator.py not found."
        )

        return False

    print(
        "rift_valley_main.py:"
    )

    print(
        ROOT / "rift_valley_main.py"
    )

    print(
        "rift_valley_video_generator.py:"
    )

    print(
        VIDEO_GENERATOR
    )

    print("")
    print(
        "Checking Python syntax..."
    )

    main_check = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(
                ROOT
                / "rift_valley_main.py"
            ),
        ],
        capture_output=True,
        text=True,
    )

    if main_check.returncode != 0:

        print(
            main_check.stdout
        )

        print(
            main_check.stderr
        )

        return False

    generator_check = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(
                VIDEO_GENERATOR
            ),
        ],
        capture_output=True,
        text=True,
    )

    if generator_check.returncode != 0:

        print(
            generator_check.stdout
        )

        print(
            generator_check.stderr
        )

        return False

    print(
        "PYTHON SYNTAX CHECK PASSED"
    )

    return True


# ============================================================
# SELECTED FILE VERIFICATION
# ============================================================

def verify_selected_files():
    print("")
    print(
        "============================================================"
    )
    print(
        "VERIFYING SELECTED STORY"
    )
    print(
        "============================================================"
    )

    if not SELECTED_STORY.exists():

        print(
            "ERROR: selected_story.json missing."
        )

        return False

    if not SELECTED_SCRIPT.exists():

        print(
            "ERROR: selected_script.json missing."
        )

        return False

    try:

        with SELECTED_STORY.open(
            "r",
            encoding="utf-8",
        ) as handle:
            story = json.load(handle)

        with SELECTED_SCRIPT.open(
            "r",
            encoding="utf-8",
        ) as handle:
            script = json.load(handle)

    except Exception as exc:

        print(
            "ERROR: Could not load selected JSON:",
            exc,
        )

        return False

    # --------------------------------------------------------
    # Story fields.
    # --------------------------------------------------------

    required_story_fields = [
        "title",
        "county",
        "article_url",
        "published_at",
        "image_urls",
    ]

    for field in required_story_fields:

        if not story.get(field):

            print(
                f"ERROR: selected_story missing {field}"
            )

            return False

    # --------------------------------------------------------
    # Script fields.
    # --------------------------------------------------------

    required_script_fields = [
        "title",
        "county",
        "script",
        "article_url",
    ]

    for field in required_script_fields:

        if not script.get(field):

            print(
                f"ERROR: selected_script missing {field}"
            )

            return False

    # --------------------------------------------------------
    # Story/script consistency.
    # --------------------------------------------------------

    if story["county"] != script["county"]:

        print(
            "ERROR: Story/script county mismatch."
        )

        print(
            "Story:",
            story["county"],
        )

        print(
            "Script:",
            script["county"],
        )

        return False

    if story["title"] != script["title"]:

        print(
            "ERROR: Story/script title mismatch."
        )

        return False

    if (
        story["article_url"]
        != script["article_url"]
    ):

        print(
            "ERROR: Story/script article URL mismatch."
        )

        return False

    # --------------------------------------------------------
    # Freshness validation.
    # --------------------------------------------------------

    published_at = parse_datetime_value(
        story["published_at"]
    )

    freshness = validate_publication_date(
        published_at
    )

    if not freshness["valid"]:

        print(
            "ERROR: Selected story is not fresh:"
        )

        print(
            freshness["reason"]
        )

        return False

    # --------------------------------------------------------
    # County validation.
    # --------------------------------------------------------

    county_result = detect_primary_county(
        story["title"],
        story.get(
            "summary",
            "",
        ),
        story.get(
            "body",
            "",
        ),
    )

    if county_result["ambiguous"]:

        print(
            "ERROR: Selected story has ambiguous county."
        )

        print(
            county_result["reason"]
        )

        return False

    if county_result["county"] != story[
        "county"
    ]:

        print(
            "ERROR: Selected story county failed revalidation."
        )

        return False

    # --------------------------------------------------------
    # Image validation.
    # --------------------------------------------------------

    if not isinstance(
        story["image_urls"],
        list,
    ):

        print(
            "ERROR: image_urls is not a list."
        )

        return False

    if len(
        story["image_urls"]
    ) < 1:

        print(
            "ERROR: No story images."
        )

        return False

    print(
        "Selected county:",
        story["county"],
    )

    print(
        "Selected title:",
        story["title"],
    )

    print(
        "Published:",
        story["published_at"],
    )

    print(
        "Age:",
        story.get(
            "age_hours",
            "unknown",
        ),
    )

    print(
        "Freshness:",
        story.get(
            "freshness",
            "unknown",
        ),
    )

    print(
        "Story images:",
        len(
            story["image_urls"]
        ),
    )

    print(
        "Story/script consistency: PASSED"
    )

    print(
        "Freshness validation: PASSED"
    )

    print(
        "County validation: PASSED"
    )

    return True


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_generator():
    print("")
    print(
        "============================================================"
    )
    print(
        "STARTING RIFT VALLEY WATCH VIDEO GENERATOR"
    )
    print(
        "============================================================"
    )

    if not VIDEO_GENERATOR.exists():

        print(
            "ERROR: Video generator does not exist."
        )

        return False

    try:

        completed = subprocess.run(
            [
                sys.executable,
                "-u",
                str(VIDEO_GENERATOR),
            ],
            cwd=str(ROOT),
            timeout=VIDEO_TIMEOUT_SECONDS,
        )

        if completed.returncode != 0:

            print(
                "ERROR: Video generator failed."
            )

            print(
                "Exit code:",
                completed.returncode,
            )

            return False

        print(
            "VIDEO GENERATOR FINISHED SUCCESSFULLY"
        )

        return True

    except subprocess.TimeoutExpired:

        print(
            "ERROR: Video generator timed out."
        )

        return False

    except Exception as exc:

        print(
            "ERROR running video generator:",
            exc,
        )

        return False


# ============================================================
# FINAL VIDEO VERIFICATION
# ============================================================

def verify_final_video():
    print("")
    print(
        "============================================================"
    )
    print(
        "VERIFYING FINAL MP4"
    )
    print(
        "============================================================"
    )

    if not FINAL_VIDEO.exists():

        print(
            "ERROR: Final MP4 was not generated."
        )

        return False

    size = FINAL_VIDEO.stat().st_size

    print(
        "MP4:",
        FINAL_VIDEO,
    )

    print(
        "Size:",
        size,
        "bytes",
    )

    if size < 100_000:

        print(
            "ERROR: MP4 is too small."
        )

        return False

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_VIDEO),
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
        )

        print("")
        print(
            "FFprobe:"
        )

        print(
            result.stdout
        )

        if result.returncode != 0:

            print(
                result.stderr
            )

            return False

    except Exception as exc:

        print(
            "ERROR running ffprobe:",
            exc,
        )

        return False

    # --------------------------------------------------------
    # Width.
    # --------------------------------------------------------

    try:

        width_result = subprocess.run(
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
            capture_output=True,
            text=True,
            timeout=60,
        )

        width = clean(
            width_result.stdout
        )

    except Exception:
        width = ""

    # --------------------------------------------------------
    # Height.
    # --------------------------------------------------------

    try:

        height_result = subprocess.run(
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
            capture_output=True,
            text=True,
            timeout=60,
        )

        height = clean(
            height_result.stdout
        )

    except Exception:
        height = ""

    # --------------------------------------------------------
    # Duration.
    # --------------------------------------------------------

    try:

        duration_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(FINAL_VIDEO),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        duration_text = clean(
            duration_result.stdout
        )

        duration = float(
            duration_text
        )

    except Exception:

        duration = 0

    # --------------------------------------------------------
    # Audio.
    # --------------------------------------------------------

    try:

        audio_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type,codec_name",
                "-of",
                "default=noprint_wrappers=1",
                str(FINAL_VIDEO),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        audio_info = clean(
            audio_result.stdout
        )

    except Exception:

        audio_info = ""

    print(
        "Width:",
        width,
    )

    print(
        "Height:",
        height,
    )

    print(
        "Duration:",
        duration,
        "seconds",
    )

    print(
        "Audio:",
        audio_info,
    )

    if width != "1080":

        print(
            "ERROR: Video width is not 1080."
        )

        return False

    if height != "1920":

        print(
            "ERROR: Video height is not 1920."
        )

        return False

    if duration < 5:

        print(
            "ERROR: Video duration is too short."
        )

        return False

    if not audio_info:

        print(
            "ERROR: Video contains no audio."
        )

        return False

    print("")
    print(
        "FINAL MP4 VERIFICATION PASSED"
    )

    return True


# ============================================================
# REPORT
# ============================================================

def report_files():
    print("")
    print(
        "============================================================"
    )
    print(
        "GENERATED FILE REPORT"
    )
    print(
        "============================================================"
    )

    paths = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
        AUDIO_DIR / "narration.mp3",
    ]

    for path in paths:

        if path.exists():

            try:
                size = path.stat().st_size

            except Exception:
                size = 0

            print(
                f"FOUND: {path} "
                f"({size:,} bytes)"
            )

        else:

            print(
                f"NOT FOUND: {path}"
            )

    print("")
    print(
        "Source directory:"
    )

    if SOURCE_DIR.exists():

        for path in sorted(
            SOURCE_DIR.glob("*")
        ):

            if path.is_file():

                print(
                    " ",
                    path.name,
                    f"({path.stat().st_size:,} bytes)",
                )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print(
        "################################################################"
    )
    print(
        "# RIFT VALLEY WATCH"
    )
    print(
        "# REALTIME NEWS VIDEO PIPELINE"
    )
    print(
        f"# {MAIN_GENERATOR_VERSION}"
    )
    print(
        "################################################################"
    )

    start_time = time.time()

    # --------------------------------------------------------
    # Clean.
    # --------------------------------------------------------

    clean_previous()

    # --------------------------------------------------------
    # Verify project.
    # --------------------------------------------------------

    if not verify_project_files():

        print(
            "ERROR: Project verification failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Discover current stories.
    # --------------------------------------------------------

    candidates = discover()

    if not candidates:

        print("")
        print(
            "============================================================"
        )
        print(
            "ERROR: NO CURRENT VALID STORIES FOUND"
        )
        print(
            "============================================================"
        )

        print(
            "All discovered articles were rejected because they "
            "were stale, lacked valid publication dates, had "
            "ambiguous counties, lacked sufficient article text, "
            "or lacked valid real article photos."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Select best.
    # --------------------------------------------------------

    selected = select_best(
        candidates
    )

    if selected is None:

        print(
            "ERROR: No valid story survived final selection."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Final story validation.
    # --------------------------------------------------------

    if not validate_story(
        selected
    ):

        print(
            "ERROR: Selected story failed final validation."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Save primary image.
    # --------------------------------------------------------

    if not save_first_image(
        selected
    ):

        print(
            "ERROR: Primary article image could not be saved."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Update primary image information.
    # --------------------------------------------------------

    selected["image_path"] = str(
        FINAL_IMAGE
    )

    if selected.get(
        "primary_image_url"
    ):

        primary_url = selected[
            "primary_image_url"
        ]

        existing_urls = selected.get(
            "image_urls",
            [],
        )

        if primary_url in existing_urls:

            existing_urls.remove(
                primary_url
            )

        selected[
            "image_urls"
        ] = [
            primary_url
        ] + existing_urls

        selected[
            "image_urls"
        ] = selected[
            "image_urls"
        ][:MAX_STORED_IMAGE_URLS]

    # --------------------------------------------------------
    # Write selected JSON.
    # --------------------------------------------------------

    write_selected_files(
        selected
    )

    # --------------------------------------------------------
    # Verify JSON.
    # --------------------------------------------------------

    if not verify_selected_files():

        print(
            "ERROR: Selected story/script verification failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Verify primary image.
    # --------------------------------------------------------

    if not FINAL_IMAGE.exists():

        print(
            "ERROR: Primary story image missing."
        )

        sys.exit(1)

    image_size = FINAL_IMAGE.stat().st_size

    if image_size < 10_000:

        print(
            "ERROR: Primary story image is too small."
        )

        sys.exit(1)

    print("")
    print(
        "PRIMARY IMAGE VERIFICATION PASSED"
    )

    # --------------------------------------------------------
    # Generate video.
    # --------------------------------------------------------

    if not run_generator():

        print(
            "ERROR: Video generation failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Final video verification.
    # --------------------------------------------------------

    if not verify_final_video():

        print(
            "ERROR: Final MP4 verification failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Report.
    # --------------------------------------------------------

    report_files()

    elapsed = (
        time.time()
        - start_time
    )

    print("")
    print(
        "################################################################"
    )
    print(
        "# RIFT VALLEY WATCH GENERATION SUCCESSFUL"
    )
    print(
        "################################################################"
    )

    print(
        "County:",
        selected["county"],
    )

    print(
        "Story:",
        selected["title"],
    )

    print(
        "Published:",
        selected["published_at"],
    )

    print(
        "Age:",
        selected["age_hours"],
        "hours",
    )

    print(
        "Freshness:",
        selected["freshness"],
    )

    print(
        "Article:",
        selected["article_url"],
    )

    print(
        "Photos:",
        len(
            selected["image_urls"]
        ),
    )

    print(
        "Final MP4:",
        FINAL_VIDEO,
    )

    print(
        "Elapsed:",
        f"{elapsed:.1f}",
        "seconds",
    )

    print(
        "################################################################"
    )


if __name__ == "__main__":
    main()
