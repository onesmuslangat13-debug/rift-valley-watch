from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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
# MAIN NEWS ENGINE
#
# VERSION: RVW_MAIN_V14_REALTIME_MULTI_SOURCE_DEDUP
#
# PURPOSE
# ------------------------------------------------------------
# 1. Find current Rift Valley news.
# 2. Prefer stories published within the last 24 hours.
# 3. Reject stories older than 48 hours.
# 4. Enforce ONE county per reel.
# 5. Reject mixed-county stories.
# 6. Search multiple Kenyan news sources.
# 7. Download multiple real article photographs.
# 8. Reject obvious placeholder/logo/broadcaster image URLs.
# 9. Prevent repeated articles using story_history.json.
# 10. Produce selected_story.json.
# 11. Produce selected_script.json.
# 12. Produce real article photographs.
# 13. Work with rift_valley_video_generator.py V27.
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

STORY_HISTORY = DATA_DIR / "story_history.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


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

MIN_ARTICLE_BODY_WORDS = 45

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

REQUEST_TIMEOUT = 25
VIDEO_TIMEOUT_SECONDS = 900

KENYA_TZ = timezone(timedelta(hours=3))

# Do not reuse an article during this period.
HISTORY_RETENTION_DAYS = 14

# Strongly prefer articles with multiple real photographs.
MULTI_IMAGE_BONUS = 5

# ============================================================
# APPROVED NEWS SOURCES
#
# Citizen Digital and KBC are intentionally excluded from the
# primary source list so their broadcaster branding is less
# likely to enter the final reel.
#
# The image filter below also rejects obvious broadcaster/logo
# image URLs if they appear elsewhere.
# ============================================================

SOURCE_PAGES = [
    "https://www.the-star.co.ke/news/",
    "https://nation.africa/kenya/news",
    "https://www.pd.co.ke/",
    "https://www.capitalfm.co.ke/news/",
    "https://ntvkenya.co.ke/news/",
    "https://www.standardmedia.co.ke/",
]

APPROVED_DOMAINS = {
    "the-star.co.ke",
    "nation.africa",
    "pd.co.ke",
    "capitalfm.co.ke",
    "ntvkenya.co.ke",
    "standardmedia.co.ke",
}

BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "tiktok.com",
    "www.tiktok.com",
    "telegram.me",
    "t.me",
    "whatsapp.com",
    "www.whatsapp.com",
    "news.google.com",
    "google.com",
    "www.google.com",
}


# ============================================================
# COUNTY DEFINITIONS
# ============================================================

COUNTY_ALIASES = {
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
        "Belgut",
        "Bureti",
        "Kapkugerwet",
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
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Mosop",
        "Aldai",
        "Chesumei",
        "Emgwen",
        "Tindiret",
        "Nandi Hills",
    ],

    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Turbo",
        "Ainabkoi",
        "Moiben",
        "Soy",
    ],

    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Elgeyo",
        "Marakwet",
        "Iten",
        "Keiyo",
        "Keiyo South",
        "Keiyo North",
        "Kapcherop",
        "Kapsowar",
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
    ],

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Transmara",
        "Narok North",
        "Narok South",
        "Loita",
    ],
}


# ============================================================
# BAD IMAGE TERMS
# ============================================================

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
    "googlelogo",
    "favicon",
    "icon",
    "logo",
    "logos",
    "placeholder",
    "default-image",
    "default_image",
    "defaultimage",
    "no-image",
    "no_image",
    "noimage",
    "avatar",
    "sprite",
    "app-icon",
    "loading",
    "spinner",
    "advert",
    "advertisement",
    "banner",
    "world-cup",
    "worldcup",
    "profile",
    "generic",
    "thumbnail-placeholder",
    "thumbnail_placeholder",
    "placeholder-image",
    "placeholder_image",
    "stock-placeholder",
    "user-placeholder",
    "blank",
    "empty-image",
    "empty_image",
    "transparent",
    "tracking",
    "pixel",
    "spacer",
]


# ============================================================
# BROADCASTER / BRAND IMAGE TERMS
#
# These are deliberately checked against IMAGE URLS and file
# names, not article titles.
#
# This helps stop obvious branded graphics/logos from becoming
# article photographs.
# ============================================================

BROADCASTER_IMAGE_TERMS = [
    "citizen",
    "citizentv",
    "citizen-tv",
    "citizen_digital",
    "citizen-digital",
    "ctv",
    "kbc",
    "kbc-tv",
    "kbcnews",
    "ntv",
    "ntvkenya",
    "ntv-kenya",
    "ntv_logo",
    "ntv-logo",
    "standardmedia-logo",
    "standard-logo",
    "nation-logo",
    "star-logo",
    "people-daily-logo",
]


# ============================================================
# POSITIVE TERMS
# ============================================================

POSITIVE_TERMS = [
    "president",
    "governor",
    "deputy president",
    "cabinet secretary",
    "minister",
    "mp",
    "senator",
    "county",
    "government",
    "school",
    "hospital",
    "road",
    "security",
    "police",
    "court",
    "business",
    "farmers",
    "agriculture",
    "education",
    "health",
    "development",
    "project",
    "economy",
    "accident",
    "fire",
    "flood",
    "weather",
    "community",
    "election",
    "development",
    "investment",
    "water",
    "market",
    "transport",
    "crime",
    "residents",
]


# ============================================================
# NEGATIVE PHRASES
# ============================================================

NEGATIVE_PHRASES = [
    "opinion",
    "analysis",
    "explainer",
    "throwback",
    "years ago",
    "archive",
    "watch:",
    "video:",
    "podcast",
    "live blog",
    "gallery",
]


# ============================================================
# HTTP HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
}


# ============================================================
# BASIC HELPERS
# ============================================================

def now_utc():
    return datetime.now(timezone.utc)


def now_kenya():
    return datetime.now(KENYA_TZ)


def clean(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_for_match(value):
    value = clean(value).lower()
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9\s-]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(url):
    url = clean(url)

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        scheme = parsed.scheme.lower()
        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        path = parsed.path.rstrip("/")

        normalized = (
            f"{scheme}://{host}{path}"
        )

        return normalized

    except Exception:
        return url.rstrip("/")


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    temp.replace(path)


def domain(url):
    try:
        host = (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def blocked(url):
    host = domain(url)

    for bad in BLOCKED_DOMAINS:
        if host == bad or host.endswith("." + bad):
            return True

    return False


def approved(url):
    host = domain(url)

    if blocked(url):
        return False

    for good in APPROVED_DOMAINS:
        if host == good or host.endswith("." + good):
            return True

    return False


def absolute_url(base, value):
    value = clean(value)

    if not value:
        return ""

    if value.startswith("//"):
        return "https:" + value

    return urljoin(base, value)


def valid_http_url(url):
    try:
        parsed = urlparse(url)

        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
        )

    except Exception:
        return False


# ============================================================
# STORY HISTORY
# ============================================================

def story_identity(article):
    url = normalize_url(
        article.get("article_url", "")
    )

    title = normalize_for_match(
        article.get("title", "")
    )

    raw = (
        url
        + "|"
        + title
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def load_story_history():
    if not STORY_HISTORY.exists():
        return []

    try:
        with STORY_HISTORY.open(
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)

    except Exception as exc:
        print(
            "WARNING: Could not read story history:",
            exc,
        )

        return []

    if isinstance(data, dict):
        entries = data.get(
            "stories",
            [],
        )
    elif isinstance(data, list):
        entries = data
    else:
        return []

    if not isinstance(entries, list):
        return []

    return entries


def prune_story_history(entries):
    cutoff = (
        now_utc()
        - timedelta(
            days=HISTORY_RETENTION_DAYS
        )
    )

    cleaned_entries = []

    for item in entries:
        if not isinstance(item, dict):
            continue

        used_at = parse_datetime_value(
            item.get("used_at", "")
        )

        if used_at is None:
            continue

        if used_at >= cutoff:
            cleaned_entries.append(item)

    return cleaned_entries


def save_story_history(entries):
    entries = prune_story_history(entries)

    save_json(
        STORY_HISTORY,
        {
            "version": 1,
            "retention_days": HISTORY_RETENTION_DAYS,
            "updated_at": now_kenya().isoformat(),
            "stories": entries,
        },
    )


def history_identity_set(entries):
    result = set()

    for item in entries:
        if not isinstance(item, dict):
            continue

        identity = clean(
            item.get("identity", "")
        )

        if identity:
            result.add(identity)

        url = normalize_url(
            item.get("article_url", "")
        )

        if url:
            result.add(
                "url:" + url
            )

    return result


def record_selected_story(article):
    entries = load_story_history()
    entries = prune_story_history(entries)

    identity = story_identity(article)

    record = {
        "identity": identity,
        "article_url": normalize_url(
            article.get("article_url", "")
        ),
        "title": clean(
            article.get("title", "")
        ),
        "county": clean(
            article.get("county", "")
        ),
        "source": clean(
            article.get("source", "")
        ),
        "used_at": now_kenya().isoformat(),
    }

    # Remove an older duplicate identity if present.
    entries = [
        item
        for item in entries
        if not (
            isinstance(item, dict)
            and (
                item.get("identity") == identity
                or normalize_url(
                    item.get("article_url", "")
                )
                == record["article_url"]
            )
        )
    ]

    entries.append(record)

    save_story_history(entries)

    print("")
    print("=" * 68)
    print("STORY HISTORY UPDATED")
    print("=" * 68)
    print(
        "History file:",
        STORY_HISTORY,
    )
    print(
        "Stored stories:",
        len(entries),
    )


# ============================================================
# DATE PARSING
# ============================================================

def parse_datetime_value(value):
    value = clean(value)

    if not value:
        return None

    iso_value = value

    if iso_value.endswith("Z"):
        iso_value = (
            iso_value[:-1]
            + "+00:00"
        )

    try:
        dt = datetime.fromisoformat(
            iso_value
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=KENYA_TZ
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(
            value
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=KENYA_TZ
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%
