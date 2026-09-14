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
# VERSION: RVW_MAIN_V14_MULTI_PHOTO_CLEAN
#
# PURPOSE
# ------------------------------------------------------------
# 1. Find current Rift Valley news.
# 2. Prefer stories published within the last 24 hours.
# 3. Reject stories older than 48 hours.
# 4. Enforce ONE county per reel.
# 5. Reject mixed-county stories.
# 6. Find multiple genuine article photographs.
# 7. Reject obvious placeholder / logo / broadcaster image URLs.
# 8. Produce selected_story.json.
# 9. Produce selected_script.json.
# 10. Produce assets/source/story_image*.jpg.
# 11. Run the video generator.
# 12. Verify the final 1080x1920 MP4.
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
# SETTINGS
# ============================================================

MAX_ARTICLE_AGE_HOURS = 48
PREFERRED_FRESH_HOURS = 24
FUTURE_TOLERANCE_MINUTES = 15

MAX_ARTICLES_PER_SOURCE = 40
MAX_SELECTED_CANDIDATES = 25

MAX_ARTICLE_IMAGES = 8
MAX_STORED_IMAGE_URLS = 8

MIN_ARTICLE_BODY_WORDS = 45

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

REQUEST_TIMEOUT = 25
VIDEO_TIMEOUT_SECONDS = 900

KENYA_TZ = timezone(timedelta(hours=3))


# ============================================================
# APPROVED NEWS SOURCES
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
# IMAGE FILTERS
# ============================================================

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
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
    "dummy",
    "sample-image",
    "sample_image",
]

# These are rejected when they appear in an IMAGE URL/path.
# This prevents obvious broadcaster-branded images from being
# deliberately selected where the filename exposes the branding.
BROADCASTER_IMAGE_TERMS = [
    "citizen-tv",
    "citizentv",
    "citizen_tv",
    "citizen-digital",
    "citizendigital",
    "citizen_digital",
    "ctv-logo",
    "ctv_logo",
    "kbc-logo",
    "kbc_logo",
    "kbc-tv",
    "kbctv",
    "nation-logo",
    "nation_logo",
    "ntv-logo",
    "ntv_logo",
    "ntvkenya",
]

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
]

NEGATIVE_PHRASES = [
    "opinion",
    "analysis",
    "explainer",
    "throwback",
    "years ago",
    "archive",
    "watch:",
    "video:",
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
        host = urlparse(url).netloc.lower().split(":")[0]

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def blocked(url):
    host = domain(url)

    for bad in BLOCKED_DOMAINS:
        if (
            host == bad
            or host.endswith("." + bad)
        ):
            return True

    return False


def approved(url):
    host = domain(url)

    if blocked(url):
        return False

    for good in APPROVED_DOMAINS:
        if (
            host == good
            or host.endswith("." + good)
        ):
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
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d %B %Y %H:%M",
        "%d %B %Y",
        "%B %d, %Y %H:%M",
        "%B %d, %Y",
        "%d %b %Y %H:%M",
        "%d %b %Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(
                value,
                fmt,
            )

            dt = dt.replace(
                tzinfo=KENYA_TZ
            )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            continue

    return None


def extract_publication_datetime(soup):
    candidates = []

    meta_names = [
        "article:published_time",
        "datePublished",
        "datepublished",
        "publishdate",
        "pubdate",
        "published",
        "publication_date",
        "date",
        "dc.date",
        "dcterms.date",
        "parsely-pub-date",
        "article:modified_time",
    ]

    for meta in soup.find_all("meta"):
        key = clean(
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
        ).lower()

        if key not in meta_names:
            continue

        value = (
            meta.get("content")
            or meta.get("datetime")
            or meta.get("value")
        )

        if value:
            candidates.append(
                (
                    "meta",
                    key,
                    value,
                )
            )

    for tag in soup.find_all("time"):
        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        if value:
            candidates.append(
                (
                    "time",
                    "time",
                    value,
                )
            )

    for script in soup.find_all(
        "script",
        attrs={
            "type": re.compile(
                r"application/ld\+json",
                re.I,
            )
        },
    ):
        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:
            obj = json.loads(raw)
        except Exception:
            continue

        def walk(node):
            if isinstance(node, dict):
                for key in [
                    "datePublished",
                    "dateCreated",
                    "dateModified",
                ]:
                    if (
                        key in node
                        and node[key]
                    ):
                        candidates.append(
                            (
                                "jsonld",
                                key,
                                node[key],
                            )
                        )

                for value in node.values():
                    if isinstance(
                        value,
                        (dict, list),
                    ):
                        walk(value)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(obj)

    priority = {
        "datePublished": 1,
        "article:published_time": 1,
        "publishdate": 1,
        "pubdate": 1,
        "published": 1,
        "dateCreated": 2,
        "time": 3,
        "date": 4,
        "dateModified": 8,
        "article:modified_time": 8,
    }

    parsed = []

    for (
        source_type,
        key,
        value,
    ) in candidates:

        dt = parse_datetime_value(
            value
        )

        if dt:
            parsed.append(
                (
                    priority.get(key, 6),
                    dt,
                    source_type,
                    key,
                    clean(value),
                )
            )

    if parsed:
        parsed.sort(
            key=lambda item: (
                item[0],
                -item[1].timestamp(),
            )
        )

        chosen = parsed[0]

        return (
            chosen[1],
            chosen[2],
            chosen[3],
        )

    text = clean(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    regexes = [
        r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b",
    ]

    for pattern in regexes:
        match = re.search(
            pattern,
            text,
            re.I,
        )

        if match:
            dt = parse_datetime_value(
                match.group(0)
            )

            if dt:
                return (
                    dt,
                    "visible-text",
                    "regex",
                )

    return None, "", ""


def freshness_details(published_at):
    if published_at is None:
        return None

    current = now_utc()

    age_hours = (
        current - published_at
    ).total_seconds() / 3600.0

    if age_hours < -(
        FUTURE_TOLERANCE_MINUTES / 60
    ):
        return None

    if age_hours > MAX_ARTICLE_AGE_HOURS:
        return None

    if age_hours <= 6:
        freshness_score = 120
    elif age_hours <= 12:
        freshness_score = 100
    elif age_hours <= 24:
        freshness_score = 80
    elif age_hours <= 36:
        freshness_score = 50
    else:
        freshness_score = 20

    freshness = "fresh"

    if age_hours > PREFERRED_FRESH_HOURS:
        freshness = "older-than-24h"

    if age_hours <= 0:
        age_hours = 0

    return {
        "age_hours": round(
            age_hours,
            2,
        ),
        "freshness_score": freshness_score,
        "freshness": freshness,
    }


# ============================================================
# COUNTY CLASSIFICATION
# ============================================================

def county_pattern(alias):
    alias = normalize_for_match(
        alias
    )

    escaped = re.escape(alias)

    return re.compile(
        r"(?<![a-z0-9])"
        + escaped
        + r"(?![a-z0-9])",
        re.I,
    )


COUNTY_PATTERNS = {}

for county, aliases in COUNTY_ALIASES.items():
    COUNTY_PATTERNS[county] = []

    for alias in sorted(
        aliases,
        key=len,
        reverse=True,
    ):
        COUNTY_PATTERNS[county].append(
            (
                alias,
                county_pattern(alias),
            )
        )


def county_mentions_in_text(text):
    text = normalize_for_match(
        text
    )

    result = {}

    for county, patterns in COUNTY_PATTERNS.items():
        matches = []

        for alias, pattern in patterns:
            found = list(
                pattern.finditer(text)
            )

            for match in found:
                matches.append(
                    {
                        "alias": alias,
                        "start": match.start(),
                        "end": match.end(),
                    }
                )

        matches.sort(
            key=lambda item: (
                item["start"],
                -(
                    item["end"]
                    - item["start"]
                ),
            )
        )

        selected = []

        for item in matches:
            overlap = False

            for existing in selected:
                if not (
                    item["end"]
                    <= existing["start"]
                    or item["start"]
                    >= existing["end"]
                ):
                    overlap = True
                    break

            if not overlap:
                selected.append(item)

        if selected:
            result[county] = selected

    return result


def classify_county(
    title,
    summary,
    body,
):
    title = clean(title)
    summary = clean(summary)
    body = clean(body)

    title_mentions = county_mentions_in_text(
        title
    )

    summary_mentions = county_mentions_in_text(
        summary
    )

    early_body = body[:1800]

    early_mentions = county_mentions_in_text(
        early_body
    )

    full_mentions = county_mentions_in_text(
        body
    )

    title_counties = set(
        title_mentions.keys()
    )

    if len(title_counties) > 1:
        return None

    weighted = {}
    evidence = {}

    for county in COUNTY_ALIASES:
        score = 0

        if county in title_mentions:
            score += (
                5
                * len(
                    title_mentions[county]
                )
            )

        if county in summary_mentions:
            score += (
                3
                * len(
                    summary_mentions[county]
                )
            )

        if county in early_mentions:
            score += (
                2
                * len(
                    early_mentions[county]
                )
            )

        body_count = len(
            full_mentions.get(
                county,
                [],
            )
        )

        score += min(
            body_count,
            3,
        )

        if score:
            weighted[county] = score

            evidence[county] = {
                "title": len(
                    title_mentions.get(
                        county,
                        [],
                    )
                ),
                "summary": len(
                    summary_mentions.get(
                        county,
                        [],
                    )
                ),
                "early_body": len(
                    early_mentions.get(
                        county,
                        [],
                    )
                ),
                "full_body": body_count,
            }

    if not weighted:
        return None

    ranked = sorted(
        weighted.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    primary_county = ranked[0][0]
    primary_score = ranked[0][1]

    primary_strong_evidence = (
        primary_county in title_mentions
        or primary_county in summary_mentions
        or primary_county in early_mentions
    )

    if not primary_strong_evidence:
        return None

    if len(ranked) > 1:
        second_county = ranked[1][0]
        second_score = ranked[1][1]

        second_strong = (
            second_county in title_mentions
            or second_county in summary_mentions
            or second_county in early_mentions
        )

        if (
            second_strong
            and second_score >= 3
        ):
            return None

        if (
            second_score >= 5
            and second_score
            >= primary_score * 0.45
        ):
            return None

    return {
        "county": primary_county,
        "county_mentions": weighted,
        "county_evidence": evidence,
    }


# ============================================================
# HTTP
# ============================================================

def fetch(
    url,
    require_html=False,
):
    if not valid_http_url(url):
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

        if require_html:
            content_type = (
                response.headers.get(
                    "content-type",
                    "",
                ).lower()
            )

            if (
                "text/html"
                not in content_type
            ):
                return None

        return response

    except Exception:
        return None


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    title = clean(title)

    title = re.sub(
        r"\s*[\|\-–—]\s*"
        r"(Citizen Digital|The Star|KBC|Nation|Nation Africa)"
        r".*$",
        "",
        title,
        flags=re.I,
    )

    title = re.sub(
        r"^(breaking|latest
