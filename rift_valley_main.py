import os
import re
import json
import time
import html
import hashlib
import traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS SELECTION + VERIFICATION PIPELINE
#
# FAST / GITHUB ACTIONS VERSION
# ONE STORY PER REEL
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

STORY_FILE = os.path.join(DATA_DIR, "story.json")
SCRIPT_FILE = os.path.join(DATA_DIR, "script.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# CONFIGURATION
# ============================================================

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
        "Bomet",
        "Sotik",
        "Longisa",
        "Kaplong",
        "Chebunyo",
    ],
    "Kericho": [
        "Kericho",
        "Litein",
        "Kipkelion",
        "Londiani",
        "Ainamoi",
    ],
    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
        "Bahati",
    ],
    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Nandi Hills",
        "Mosoriot",
        "Aldai",
    ],
    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Moiben",
        "Turbo",
        "Soy",
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo Marakwet",
        "Elgeyo-Marakwet",
        "Iten",
        "Keiyo",
        "Marakwet",
        "Kabarnet",
    ],
    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Pokot",
        "Sigor",
    ],
    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Ololulunga",
        "Transmara",
    ],
}


# ============================================================
# FAST GITHUB ACTIONS SETTINGS
# ============================================================

RSS_TIMEOUT = 5
ARTICLE_TIMEOUT = 6
IMAGE_TIMEOUT = 4
SEARCH_TIMEOUT = 5

MAX_AGE_HOURS = 72

MAX_CANDIDATES_TO_VERIFY = 4
MAX_VERIFIED_TO_COMPARE = 2

BING_RESULT_LIMIT = 5
MAX_BING_IMAGES = 5
MAX_IMAGE_CHECKS = 4

RSS_DELAY = 0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 "
    "RiftValleyWatch/3.0"
)


# ============================================================
# TEXT AND URL HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, bytes):
        value = value.decode(
            "utf-8",
            errors="ignore",
        )

    value = html.unescape(str(value))

    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = BeautifulSoup(
        value,
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_title(title):
    title = clean_text(title).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        "",
        title,
    )

    return re.sub(
        r"\s+",
        " ",
        title,
    ).strip()


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return (
            parsed.scheme.lower()
            in {"http", "https"}
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def hostname(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )
    except Exception:
        return ""


def is_search_engine_url(url):
    host = hostname(url)

    blocked = [
        "google.com",
        "google.co.ke",
        "news.google.com",
        "bing.com",
        "bing.net",
        "yahoo.com",
        "duckduckgo.com",
        "search.brave.com",
        "r.bing.com",
    ]

    return any(
        host == domain
        or host.endswith("." + domain)
        for domain in blocked
    )


def is_svg_url(url):
    if not url:
        return True

    lower = url.lower()

    return (
        ".svg" in lower
        or "image/svg" in lower
        or lower.startswith(
            "data:image/svg"
        )
    )


def now_utc():
    return datetime.now(
        timezone.utc
    )


def story_hash(title, url):
    raw = (
        normalize_title(title)
        + "|"
        + clean_text(url).lower()
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value

    else:
        text = clean_text(value)

        if not text:
            return None

        dt = None

        try:
            parsed = feedparser._parse_date(text)

            if parsed:
                dt = datetime(
                    parsed.tm_year,
                    parsed.tm_mon,
                    parsed.tm_mday,
                    parsed.tm_hour,
                    parsed.tm_min,
                    parsed.tm_sec,
                    tzinfo=timezone.utc,
                )

        except Exception:
            dt = None

        if dt is None:
            formats = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d %B %Y",
                "%B %d, %Y",
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(
                        text,
                        fmt,
                    )

                    if dt.tzinfo is None:
                        dt = dt.replace(
                            tzinfo=timezone.utc
                        )

                    break

                except Exception:
                    continue

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def is_recent(
    value,
    allow_missing=True,
):
    dt = parse_date(value)

    if dt is None:
        return allow_missing

    age = now_utc() - dt

    if age < timedelta(
        minutes=-30
    ):
        return False

    return age <= timedelta(
        hours=MAX_AGE_HOURS
    )


# ============================================================
# HTTP
# ============================================================

def get_response(
    url,
    timeout,
):
    return requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        },
        timeout=timeout,
        allow_redirects=True,
    )


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_rss(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def parse_feed(feed_url):
    try:
        response = get_response(
            feed_url,
            RSS_TIMEOUT,
        )

        response.raise_for_status()

        parsed = feedparser.parse(
            response.content
        )

        entries = getattr(
            parsed,
            "entries",
            [],
        )

        if not entries:
            return None

        return parsed

    except Exception as exc:
        print(
            f"RSS request failed: {exc}"
        )

        return None


def get_rss_media_image(entry):
    candidates = []

    for item in entry.get(
        "media_content",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("url", "")
            )

    for item in entry.get(
        "media_thumbnail",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("url", "")
            )

    for item in entry.get(
        "enclosures",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("href", "")
            )

    for url in candidates:
        if (
            valid_http_url(url)
            and not is_svg_url(url)
            and not is_search_engine_url(url)
        ):
            return url

    return ""


# ============================================================
# GOOGLE NEWS URL RESOLUTION
# ============================================================

def unwrap_google_news_url(url):
    if not valid_http_url(url):
        return ""

    if not is_search_engine_url(url):
        return url

    try:
        response = get_response(
            url,
            SEARCH_TIMEOUT,
        )

        final_url = response.url

        if (
            valid_http_url(final_url)
            and not is_search_engine_url(final_url)
        ):
            return final_url

    except Exception:
        pass

    return ""


# ============================================================
# BING WEB SEARCH
# ============================================================

def bing_search(query):
    results = []

    try:
        url = (
            "https://www.bing.com/search?"
            f"q={quote_plus(query)}"
            "&count=5"
            "&setlang=en-KE"
        )

        response = get_response(
            url,
            SEARCH_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
       
