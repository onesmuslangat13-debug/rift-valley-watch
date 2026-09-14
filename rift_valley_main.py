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
# VERSION: RVW_MAIN_V13_REALTIME_STRICT_COUNTY
#
# PURPOSE
# ------------------------------------------------------------
# 1. Find current Rift Valley news.
# 2. Prefer stories published within the last 24 hours.
# 3. Reject stories older than 48 hours.
# 4. Enforce ONE county per reel.
# 5. Reject mixed-county stories.
# 6. Download only real article photographs.
# 7. Produce selected_story.json.
# 8. Produce selected_script.json.
# 9. Produce assets/source/story_image.jpg.
# 10. Work with rift_valley_video_generator.py.
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

# Current approved news sources.
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
    "development",
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
    path.parent.mkdir(parents=True, exist_ok=True)

    temp = path.with_suffix(path.suffix + ".tmp")

    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


# ============================================================
# DATE PARSING
# ============================================================

def parse_datetime_value(value):
    value = clean(value)

    if not value:
        return None

    # ISO formats.
    iso_value = value

    if iso_value.endswith("Z"):
        iso_value = iso_value[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(iso_value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KENYA_TZ)

        return dt.astimezone(timezone.utc)

    except Exception:
        pass

    # RFC 2822 / RSS.
    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KENYA_TZ)

        return dt.astimezone(timezone.utc)

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
            dt = datetime.strptime(value, fmt)
            dt = dt.replace(tzinfo=KENYA_TZ)
            return dt.astimezone(timezone.utc)
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

        if key in meta_names:
            value = (
                meta.get("content")
                or meta.get("datetime")
                or meta.get("value")
            )

            if value:
                candidates.append(("meta", key, value))

    for tag in soup.find_all("time"):
        value = tag.get("datetime") or tag.get_text(" ", strip=True)

        if value:
            candidates.append(("time", "time", value))

    # JSON-LD.
    for script in soup.find_all(
        "script",
        attrs={"type": re.compile(r"application/ld\+json", re.I)}
    ):
        raw = script.string or script.get_text()

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
                    if key in node and node[key]:
                        candidates.append(
                            ("jsonld", key, node[key])
                        )

                for value in node.values():
                    walk(value)

            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(obj)

    # Prefer publication date over modified date.
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

    for source_type, key, value in candidates:
        dt = parse_datetime_value(value)

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
        parsed.sort(key=lambda x: x[0])
        return parsed[0][1], parsed[0][2], parsed[0][3]

    # Conservative visible-text fallback.
    text = clean(soup.get_text(" ", strip=True))

    regexes = [
        r"\b20\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b",
    ]

    for pattern in regexes:
        match = re.search(pattern, text, re.I)

        if match:
            dt = parse_datetime_value(match.group(0))

            if dt:
                return dt, "visible-text", "regex"

    return None, "", ""


def freshness_details(published_at):
    if published_at is None:
        return None

    current = now_utc()

    age_hours = (current - published_at).total_seconds() / 3600.0

    if age_hours < -(FUTURE_TOLERANCE_MINUTES / 60):
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
        "age_hours": round(age_hours, 2),
        "freshness_score": freshness_score,
        "freshness": freshness,
    }


# ============================================================
# COUNTY CLASSIFICATION
# ============================================================

def county_pattern(alias):
    alias = normalize_for_match(alias)

    escaped = re.escape(alias)

    return re.compile(
        r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])",
        re.I,
    )


COUNTY_PATTERNS = {}

for county, aliases in COUNTY_ALIASES.items():
    COUNTY_PATTERNS[county] = []

    # Longest first.
    for alias in sorted(aliases, key=len, reverse=True):
        COUNTY_PATTERNS[county].append(
            (alias, county_pattern(alias))
        )


def county_mentions_in_text(text):
    text = normalize_for_match(text)

    result = {}

    for county, patterns in COUNTY_PATTERNS.items():
        matches = []

        for alias, pattern in patterns:
            found = list(pattern.finditer(text))

            for match in found:
                matches.append(
                    {
                        "alias": alias,
                        "start": match.start(),
                        "end": match.end(),
                    }
                )

        # Prevent double counting overlapping aliases.
        matches.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))

        selected = []

        for item in matches:
            overlap = False

            for existing in selected:
                if not (
                    item["end"] <= existing["start"]
                    or item["start"] >= existing["end"]
                ):
                    overlap = True
                    break

            if not overlap:
                selected.append(item)

        if selected:
            result[county] = selected

    return result


def classify_county(title, summary, body):
    title = clean(title)
    summary = clean(summary)
    body = clean(body)

    title_mentions = county_mentions_in_text(title)
    summary_mentions = county_mentions_in_text(summary)
    early_body = body[:1800]
    early_mentions = county_mentions_in_text(early_body)
    full_mentions = county_mentions_in_text(body)

    # A story title mentioning two counties is almost always unsafe
    # for strict single-county reels.
    title_counties = set(title_mentions.keys())

    if len(title_counties) > 1:
        return None

    weighted = {}

    evidence = {}

    for county in COUNTY_ALIASES:
        score = 0

        if county in title_mentions:
            score += 5 * len(title_mentions[county])

        if county in summary_mentions:
            score += 3 * len(summary_mentions[county])

        if county in early_mentions:
            score += 2 * len(early_mentions[county])

        # Full body gives only weak evidence.
        body_count = len(full_mentions.get(county, []))
        score += min(body_count, 3)

        if score:
            weighted[county] = score

            evidence[county] = {
                "title": len(title_mentions.get(county, [])),
                "summary": len(summary_mentions.get(county, [])),
                "early_body": len(early_mentions.get(county, [])),
                "full_body": body_count,
            }

    if not weighted:
        return None

    ranked = sorted(
        weighted.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    primary_county, primary_score = ranked[0]

    # County must be supported by title, summary or early body.
    primary_strong_evidence = (
        primary_county in title_mentions
        or primary_county in summary_mentions
        or primary_county in early_mentions
    )

    if not primary_strong_evidence:
        return None

    # Reject a meaningful second county.
    if len(ranked) > 1:
        second_county, second_score = ranked[1]

        second_strong = (
            second_county in title_mentions
            or second_county in summary_mentions
            or second_county in early_mentions
        )

        # If another county has meaningful prominent evidence,
        # this is a mixed-county story.
        if second_strong and second_score >= 3:
            return None

        # If the second county has a score close to the primary,
        # reject it.
        if second_score >= 5 and second_score >= primary_score * 0.45:
            return None

    return {
        "county": primary_county,
        "county_mentions": weighted,
        "county_evidence": evidence,
    }


# ============================================================
# HTTP
# ============================================================

def fetch(url, require_html=False):
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
                response.headers.get("content-type", "").lower()
            )

            if "text/html" not in content_type:
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
        r"\s*[\|\-–—]\s*(Citizen Digital|The Star|KBC|Nation|Nation Africa).*$",
        "",
        title,
        flags=re.I,
    )

    title = re.sub(
        r"^(breaking|latest)\s*[:\-]\s*",
        "",
        title,
        flags=re.I,
    )

    return clean(title)


def remove_metadata(text):
    text = clean(text)

    lines = []

    for line in re.split(r"\n+", text):
        line = clean(line)

        if not line:
            continue

        if len(line) < 25:
            continue

        if re.search(
            r"follow us|subscribe|sign up|advertisement|read more|"
            r"share this|related stories|comments|copyright",
            line,
            re.I,
        ):
            continue

        lines.append(line)

    return " ".join(lines)


# ============================================================
# ARTICLE LINK DISCOVERY
# ============================================================

GENERIC_PATHS = {
    "/",
    "/news/",
    "/news",
    "/latest/",
    "/latest",
    "/sports/",
    "/sports",
    "/business/",
    "/business",
    "/politics/",
    "/politics",
    "/entertainment/",
    "/entertainment",
    "/videos/",
    "/videos",
    "/category/",
}


def discover_links(page_url):
    response = fetch(page_url, require_html=True)

    if response is None:
        print("Could not fetch source:", page_url)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    links = []
    seen = set()

    for anchor in soup.find_all("a", href=True):
        href = absolute_url(page_url, anchor.get("href"))

        if not href:
            continue

        if not approved(href):
            continue

        parsed = urlparse(href)
        path = parsed.path.rstrip("/") or "/"

        if path in GENERIC_PATHS:
            continue

        # Remove obvious non-article URLs.
        if re.search(
            r"/(tag|tags|author|authors|search|login|register|"
            r"privacy|terms|contact|about|video|videos|live|"
            r"gallery|galleries|category)/",
            path,
            re.I,
        ):
            continue

        # Need a meaningful path.
        if len(path.strip("/")) < 8:
            continue

        text = clean(anchor.get_text(" ", strip=True))

        if len(text) < 12:
            continue

        key = href.split("#")[0].rstrip("/")

        if key in seen:
            continue

        seen.add(key)

        county_info = classify_county(
            text,
            "",
            href,
        )

        links.append(
            {
                "url": key,
                "anchor_text": text,
                "county_hint": (
                    county_info["county"]
                    if county_info
                    else ""
                ),
            }
        )

    # County-related links first.
    links.sort(
        key=lambda item: (
            0 if item["county_hint"] else 1,
            -len(item["anchor_text"]),
        )
    )

    return links[:MAX_ARTICLES_PER_SOURCE]


# ============================================================
# IMAGE CANDIDATES
# ============================================================

IMAGE_KEYS = {
    "image",
    "images",
    "imageurl",
    "image_url",
    "thumbnailurl",
    "thumbnail_url",
    "contenturl",
    "content_url",
    "src",
    "srcset",
    "poster",
}


def image_url_is_bad(url):
    url_lower = clean(url).lower()

    if not url_lower:
        return True

    if not valid_http_url(url_lower):
        return True

    if blocked(url_lower):
        return True

    for term in BAD_IMAGE_TERMS:
        if term in url_lower:
            return True

    if re.search(
        r"(1x1|pixel|tracking|spacer|transparent)\b",
        url_lower,
        re.I,
    ):
        return True

    return False


def add_image_candidate(candidates, value, base_url):
    if value is None:
        return

    if isinstance(value, dict):
        for key in [
            "url",
            "src",
            "contentUrl",
            "content_url",
        ]:
            if key in value:
                add_image_candidate(
                    candidates,
                    value[key],
                    base_url,
                )
        return

    if isinstance(value, list):
        for item in value:
            add_image_candidate(
                candidates,
                item,
                base_url,
            )
        return

    value = clean(value)

    if not value:
        return

    # srcset can contain multiple URLs.
    if "," in value:
        parts = value.split(",")

        for part in parts:
            tokens = part.strip().split()

            if tokens:
                add_image_candidate(
                    candidates,
                    tokens[0],
                    base_url,
                )

        return

    # Some sites provide whitespace separated srcset.
    if " " in value and (
        " 1x" in value
        or " 2x" in value
        or " 320w" in value
        or " 480w" in value
        or " 640w" in value
        or " 768w" in value
        or " 1024w" in value
    ):
        value = value.split()[0]

    value = absolute_url(base_url, value)

    if image_url_is_bad(value):
        return

    if value not in candidates:
        candidates.append(value)


def scan_json_images(node, candidates, base_url):
    if isinstance(node, dict):
        for key, value in node.items():
            key_clean = re.sub(
                r"[^a-z0-9_]",
                "",
                str(key).lower(),
            )

            # IMPORTANT:
            # Do NOT scan generic "url" fields.
            if key_clean in {
                "image",
                "images",
                "imageurl",
                "image_url",
                "thumbnailurl",
                "thumbnail_url",
                "contenturl",
                "content_url",
                "src",
                "srcset",
                "poster",
            }:
                add_image_candidate(
                    candidates,
                    value,
                    base_url,
                )

            if isinstance(value, (dict, list)):
                scan_json_images(
                    value,
                    candidates,
                    base_url,
                )

    elif isinstance(node, list):
        for item in node:
            scan_json_images(
                item,
                candidates,
                base_url,
            )


def get_image_candidates(soup, article_url):
    candidates = []

    # OpenGraph.
    for meta in soup.find_all(
        "meta",
        attrs={"property": re.compile(r"^og:image", re.I)},
    ):
        add_image_candidate(
            candidates,
            meta.get("content"),
            article_url,
        )

    # Twitter cards.
    for meta in soup.find_all(
        "meta",
        attrs={"name": re.compile(r"^twitter:image", re.I)},
    ):
        add_image_candidate(
            candidates,
            meta.get("content"),
            article_url,
        )

    # Itemprop/property image.
    for tag in soup.find_all(
        attrs={
            "itemprop": re.compile(r"^image$", re.I)
        }
    ):
        for attr in [
            "content",
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
        ]:
            if tag.get(attr):
                add_image_candidate(
                    candidates,
                    tag.get(attr),
                    article_url,
                )

    # JSON-LD.
    for script in soup.find_all(
        "script",
        attrs={"type": re.compile(r"application/ld\+json", re.I)}
    ):
        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        scan_json_images(
            data,
            candidates,
            article_url,
        )

    # Article/main images.
    containers = []

    article_tag = soup.find("article")

    if article_tag:
        containers.append(article_tag)

    main_tag = soup.find("main")

    if main_tag:
        containers.append(main_tag)

    if not containers:
        containers.append(soup)

    for container in containers:
        for img in container.find_all("img"):
            for attr in [
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-url",
                "srcset",
                "data-srcset",
            ]:
                value = img.get(attr)

                if value:
                    add_image_candidate(
                        candidates,
                        value,
                        article_url,
                    )

    # Picture/source elements.
    for source in soup.find_all("source"):
        for attr in [
            "src",
            "srcset",
            "data-srcset",
        ]:
            value = source.get(attr)

            if value:
                add_image_candidate(
                    candidates,
                    value,
                    article_url,
                )

    return candidates


# ============================================================
# IMAGE DOWNLOADING
# ============================================================

def download_image(url):
    if image_url_is_bad(url):
        return None

    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        content_type = (
            response.headers.get("content-type", "")
            .lower()
        )

        if not (
            content_type.startswith("image/")
            or content_type == "application/octet-stream"
        ):
            return None

        data = response.content

        if len(data) < 20000:
            return None

        image = Image.open(BytesIO(data))
        image.load()

        width, height = image.size

        if width < MIN_IMAGE_WIDTH:
            return None

        if height < MIN_IMAGE_HEIGHT:
            return None

        if width * height < MIN_IMAGE_AREA:
            return None

        aspect = width / float(height)

        if aspect < 0.45 or aspect > 3.5:
            return None

        # Reject tiny square graphics.
        if (
            abs(width - height) < 30
            and width < 600
        ):
            return None

        return {
            "url": response.url,
            "bytes": data,
            "width": width,
            "height": height,
            "content_type": content_type,
        }

    except Exception:
        return None


def download_article_images(article_url, candidates):
    valid_images = []
    seen_hashes = set()
    seen_urls = set()

    for url in candidates:
        if len(valid_images) >= MAX_ARTICLE_IMAGES:
            break

        if url in seen_urls:
            continue

        seen_urls.add(url)

        result = download_image(url)

        if result is None:
            continue

        digest = hashlib.sha256(
            result["bytes"]
        ).hexdigest()

        if digest in seen_hashes:
            continue

        seen_hashes.add(digest)

        valid_images.append(result)

    return valid_images


def save_article_images(article_images):
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old generated photos.
    for old in SOURCE_DIR.glob("story_image*.jpg"):
        try:
            old.unlink()
        except Exception:
            pass

    saved = []

    for index, item in enumerate(article_images):
        if index == 0:
            filename = "story_image.jpg"
        else:
            filename = f"story_image_{index}.jpg"

        path = SOURCE_DIR / filename

        try:
            image = Image.open(BytesIO(item["bytes"])).convert("RGB")
            image.save(
                path,
                "JPEG",
                quality=94,
                optimize=True,
            )

            if path.exists() and path.stat().st_size >= 10000:
                saved.append(
                    {
                        "path": str(
                            path.relative_to(ROOT)
                        ).replace("\\", "/"),
                        "url": item["url"],
                        "width": item["width"],
                        "height": item["height"],
                        "size": path.stat().st_size,
                    }
                )

        except Exception:
            continue

    return saved


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(url, source_page=""):
    response = fetch(url, require_html=True)

    if response is None:
        return None

    final_url = response.url

    if not approved(final_url):
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove unwanted page elements.
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
        ]
    ):
        tag.decompose()

    title = ""

    og_title = soup.find(
        "meta",
        attrs={"property": "og:title"},
    )

    if og_title:
        title = clean(og_title.get("content"))

    if not title:
        title_tag = soup.find("title")

        if title_tag:
            title = clean(
                title_tag.get_text(" ", strip=True)
            )

    if not title:
        heading = soup.find("h1")

        if heading:
            title = clean(
                heading.get_text(" ", strip=True)
            )

    title = clean_title(title)

    if len(title) < 12:
        return None

    summary = ""

    for selector in [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
    ]:
        tag = soup.find(*selector)

        if tag:
            summary = clean(tag.get("content"))

            if summary:
                break

    paragraphs = []

    article_container = (
        soup.find("article")
        or soup.find("main")
        or soup
    )

    for p in article_container.find_all("p"):
        text = clean(
            p.get_text(" ", strip=True)
        )

        if len(text) < 30:
            continue

        if re.search(
            r"advertisement|subscribe|sign up|"
            r"follow us|read more|related stories",
            text,
            re.I,
        ):
            continue

        paragraphs.append(text)

    # Deduplicate consecutive/similar paragraphs.
    cleaned_paragraphs = []
    seen_para = set()

    for paragraph in paragraphs:
        key = normalize_for_match(paragraph)

        if not key:
            continue

        if key in seen_para:
            continue

        seen_para.add(key)
        cleaned_paragraphs.append(paragraph)

    body = remove_metadata(
        " ".join(cleaned_paragraphs)
    )

    words = body.split()

    if len(words) < MIN_ARTICLE_BODY_WORDS:
        return None

    published_at, date_source, date_key = (
        extract_publication_datetime(soup)
    )

    if published_at is None:
        # For realtime news, no reliable publication date is unsafe.
        return None

    freshness = freshness_details(published_at)

    if freshness is None:
        return None

    county_info = classify_county(
        title,
        summary,
        body,
    )

    if county_info is None:
        return None

    image_candidates = get_image_candidates(
        soup,
        final_url,
    )

    image_candidates = image_candidates[
        :MAX_STORED_IMAGE_URLS * 4
    ]

    article_images = download_article_images(
        final_url,
        image_candidates,
    )

    if not article_images:
        return None

    image_urls = [
        item["url"]
        for item in article_images
    ]

    positive_score = 0

    combined = normalize_for_match(
        f"{title} {summary} {body[:5000]}"
    )

    for term in POSITIVE_TERMS:
        if term in combined:
            positive_score += 2

    negative_score = 0

    for phrase in NEGATIVE_PHRASES:
        if phrase in combined:
            negative_score += 7

    body_score = min(
        len(words),
        220,
    ) // 5

    image_score = min(
        len(article_images),
        5,
    ) * 3

    county_score = max(
        county_info["county_mentions"].values()
    )

    quality_score = (
        body_score
        + positive_score
        - negative_score
        + image_score
        + county_score
    )

    selection_score = (
        freshness["freshness_score"]
        + quality_score
    )

    return {
        "title": title,
        "summary": summary[:1000],
        "body": body,
        "county": county_info["county"],
        "county_mentions": county_info["county_mentions"],
        "county_evidence": county_info["county_evidence"],
        "published_at": published_at.isoformat(),
        "published_at_kenya": published_at.astimezone(
            KENYA_TZ
        ).isoformat(),
        "publication_date_source": date_source,
        "publication_date_key": date_key,
        "age_hours": freshness["age_hours"],
        "freshness": freshness["freshness"],
        "freshness_score": freshness["freshness_score"],
        "article_url": final_url,
        "source": domain(final_url),
        "source_page": source_page,
        "image_candidates": image_candidates[
            :MAX_STORED_IMAGE_URLS
        ],
        "image_urls": image_urls[
            :MAX_STORED_IMAGE_URLS
        ],
        "image_count": len(image_urls),
        "quality_score": quality_score,
        "selection_score": selection_score,
        "selected_at": now_kenya().isoformat(),
        "generator_version": "RVW_MAIN_V13_REALTIME_STRICT_COUNTY",
    }


# ============================================================
# SCRIPT
# ============================================================

def sentence_split(text):
    text = clean(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        clean(part)
        for part in parts
        if len(clean(part).split()) >= 5
    ]


def build_script(article):
    county = article["county"]
    title = article["title"]
    summary = article.get("summary", "")
    body = article.get("body", "")

    sentences = sentence_split(
        f"{summary} {body}"
    )

    selected = []

    # Opening.
    selected.append(
        f"Here is the latest development from {county}."
    )

    # Headline.
    selected.append(title + ".")

    # Add factual article sentences.
    for sentence in sentences:
        sentence = clean(sentence)

        if not sentence:
            continue

        # Avoid obvious metadata.
        if re.search(
            r"follow us|subscribe|advertisement|"
            r"read more|related stories",
            sentence,
            re.I,
        ):
            continue

        selected.append(sentence)

        words = " ".join(selected).split()

        if len(words) >= 125:
            break

    # Ensure a sensible ending.
    script = " ".join(selected)

    words = script.split()

    if len(words) < 80:
        extra = sentence_split(body)

        for sentence in extra:
            if sentence not in selected:
                selected.append(sentence)

            script = " ".join(selected)

            if len(script.split()) >= 100:
                break

    script = clean(script)

    # Limit excessive length.
    words = script.split()

    if len(words) > 155:
        script = " ".join(words[:155])

        if not script.endswith((".", "!", "?")):
            script += "."

    return script


# ============================================================
# FILE WRITING
# ============================================================

def write_selected_files(article, saved_images, script):
    image_urls = [
        item["url"]
        for item in saved_images
    ]

    image_paths = [
        item["path"]
        for item in saved_images
    ]

    article_data = {
        "title": article["title"],
        "county": article["county"],
        "summary": article["summary"],
        "body": article["body"],
        "article_url": article["article_url"],
        "source": article["source"],
        "source_page": article.get("source_page", ""),
        "published_at": article["published_at"],
        "published_at_kenya": article[
            "published_at_kenya"
        ],
        "age_hours": article["age_hours"],
        "freshness": article["freshness"],
        "freshness_score": article["freshness_score"],
        "county_mentions": article[
            "county_mentions"
        ],
        "county_evidence": article[
            "county_evidence"
        ],
        "image_urls": image_urls[
            :MAX_STORED_IMAGE_URLS
        ],
        "image_paths": image_paths[
            :MAX_STORED_IMAGE_URLS
        ],
        "image_url": (
            image_urls[0]
            if image_urls
            else ""
        ),
        "image_path": (
            image_paths[0]
            if image_paths
            else ""
        ),
        "image_count": len(image_paths),
        "quality_score": article["quality_score"],
        "selection_score": article[
            "selection_score"
        ],
        "selected_at": now_kenya().isoformat(),
        "generator_version": (
            "RVW_MAIN_V13_REALTIME_STRICT_COUNTY"
        ),
    }

    script_data = {
        "title": article["title"],
        "county": article["county"],
        "article_url": article["article_url"],
        "source": article["source"],
        "published_at": article["published_at"],
        "published_at_kenya": article[
            "published_at_kenya"
        ],
        "script": script,
        "word_count": len(script.split()),
        "image_urls": image_urls[
            :MAX_STORED_IMAGE_URLS
        ],
        "image_paths": image_paths[
            :MAX_STORED_IMAGE_URLS
        ],
        "generator_version": (
            "RVW_MAIN_V13_REALTIME_STRICT_COUNTY"
        ),
        "created_at": now_kenya().isoformat(),
    }

    save_json(
        SELECTED_STORY,
        article_data,
    )

    save_json(
        SELECTED_SCRIPT,
        script_data,
    )

    return article_data, script_data


# ============================================================
# VALIDATION
# ============================================================

def validate_story(story, script):
    required_story = [
        "title",
        "county",
        "article_url",
        "source",
        "image_urls",
        "image_paths",
        "published_at",
    ]

    for key in required_story:
        if not story.get(key):
            raise RuntimeError(
                f"Selected story missing: {key}"
            )

    required_script = [
        "title",
        "county",
        "article_url",
        "script",
    ]

    for key in required_script:
        if not script.get(key):
            raise RuntimeError(
                f"Selected script missing: {key}"
            )

    if story["county"] != script["county"]:
        raise RuntimeError(
            "COUNTY MISMATCH: story and script "
            "belong to different counties."
        )

    if story["title"] != script["title"]:
        raise RuntimeError(
            "TITLE MISMATCH: story and script "
            "do not refer to the same article."
        )

    if story["article_url"] != script["article_url"]:
        raise RuntimeError(
            "ARTICLE URL MISMATCH: story and script "
            "do not refer to the same article."
        )

    if not approved(story["article_url"]):
        raise RuntimeError(
            "Selected article is not from an approved source."
        )

    age = float(story.get("age_hours", 999))

    if age > MAX_ARTICLE_AGE_HOURS:
        raise RuntimeError(
            f"Selected article is too old: {age:.2f} hours."
        )

    if len(story["image_paths"]) == 0:
        raise RuntimeError(
            "No validated article images were saved."
        )

    for path_string in story["image_paths"]:
        path = ROOT / path_string

        if not path.exists():
            raise RuntimeError(
                f"Missing selected image: {path}"
            )

        if path.stat().st_size < 10000:
            raise RuntimeError(
                f"Selected image is too small: {path}"
            )

    return True


# ============================================================
# DISCOVERY
# ============================================================

def discover():
    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH - REALTIME DISCOVERY")
    print("=" * 68)
    print("Current Kenya time:", now_kenya().isoformat())
    print(
        f"Maximum article age: "
        f"{MAX_ARTICLE_AGE_HOURS} hours"
    )
    print("")

    all_candidates = []

    for source_page in SOURCE_PAGES:
        print("-" * 68)
        print("SOURCE:", source_page)

        links = discover_links(source_page)

        print(
            "Article links discovered:",
            len(links),
        )

        processed = 0

        for item in links:
            if processed >= MAX_ARTICLES_PER_SOURCE:
                break

            url = item["url"]

            print(
                f"Checking [{processed + 1}] {url}"
            )

            article = extract_article(
                url,
                source_page=source_page,
            )

            processed += 1

            if article is None:
                continue

            print(
                "  ACCEPTED:",
                article["county"],
                "|",
                f"{article['age_hours']:.1f}h",
                "|",
                article["title"][:100],
            )

            all_candidates.append(article)

            if len(all_candidates) >= (
                MAX_SELECTED_CANDIDATES * 2
            ):
                break

        if len(all_candidates) >= (
            MAX_SELECTED_CANDIDATES * 2
        ):
            break

    # Dedupe URLs.
    unique = {}

    for article in all_candidates:
        key = article["article_url"].rstrip("/")

        if key not in unique:
            unique[key] = article

    candidates = list(unique.values())

    # Dedupe identical titles.
    unique_titles = {}

    for article in candidates:
        title_key = normalize_for_match(
            article["title"]
        )

        if title_key not in unique_titles:
            unique_titles[title_key] = article
            continue

        old = unique_titles[title_key]

        if article["selection_score"] > old[
            "selection_score"
        ]:
            unique_titles[title_key] = article

    candidates = list(unique_titles.values())

    # Freshness is the dominant selection criterion.
    candidates.sort(
        key=lambda article: (
            article["freshness_score"],
            article["selection_score"],
            article["quality_score"],
            article["image_count"],
            -article["age_hours"],
        ),
        reverse=True,
    )

    candidates = candidates[
        :MAX_SELECTED_CANDIDATES
    ]

    print("")
    print("=" * 68)
    print("VALID CANDIDATES:", len(candidates))
    print("=" * 68)

    for index, article in enumerate(candidates, 1):
        print(
            f"{index:02d}. "
            f"[{article['county']}] "
            f"{article['age_hours']:.1f}h "
            f"score={article['selection_score']} "
            f"photos={article['image_count']} "
            f"{article['title']}"
        )

    return candidates


def select_best(candidates):
    if not candidates:
        raise RuntimeError(
            "No valid realtime Rift Valley article found."
        )

    # Re-sort with freshness first.
    candidates = sorted(
        candidates,
        key=lambda article: (
            article["freshness_score"],
            article["selection_score"],
            article["quality_score"],
            article["image_count"],
            -article["age_hours"],
        ),
        reverse=True,
    )

    selected = candidates[0]

    print("")
    print("=" * 68)
    print("SELECTED STORY")
    print("=" * 68)
    print("County:", selected["county"])
    print("Title:", selected["title"])
    print("Source:", selected["source"])
    print("URL:", selected["article_url"])
    print(
        "Published:",
        selected["published_at_kenya"],
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
        "Article photos:",
        selected["image_count"],
    )
    print("")

    return selected


# ============================================================
# CLEANUP
# ============================================================

def clean_previous():
    print("")
    print("=" * 68)
    print("CLEANING PREVIOUS GENERATED FILES")
    print("=" * 68)

    paths = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_VIDEO,
        AUDIO_DIR / "narration.mp3",
        AUDIO_DIR / "narration_temp.mp3",
        VIDEO_WORK_DIR / "narration.mp3",
    ]

    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            print(
                "Warning: could not remove",
                path,
                exc,
            )

    # Generated article images.
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for image in SOURCE_DIR.glob("story_image*.jpg"):
        try:
            image.unlink()
        except Exception:
            pass

    # Generated scene files.
    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for pattern in [
        "scene_*.png",
        "scene_*.mp4",
        "concat*.txt",
        "*.tmp",
    ]:
        for path in VIDEO_WORK_DIR.glob(pattern):
            try:
                path.unlink()
            except Exception:
                pass

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Cleanup complete.")


# ============================================================
# PROJECT VERIFICATION
# ============================================================

def verify_project_files():
    print("")
    print("=" * 68)
    print("VERIFYING PROJECT")
    print("=" * 68)

    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py not found."
        )

    print(
        "rift_valley_main.py:",
        Path(__file__).stat().st_size,
        "bytes",
    )

    print(
        "rift_valley_video_generator.py:",
        VIDEO_GENERATOR.stat().st_size,
        "bytes",
    )

    print("Checking Python syntax...")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(Path(__file__)),
        ],
        check=True,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(VIDEO_GENERATOR),
        ],
        check=True,
    )

    print("PYTHON SYNTAX CHECK PASSED")


# ============================================================
# FINAL VIDEO
# ============================================================

def run_generator():
    print("")
    print("=" * 68)
    print("STARTING VIDEO GENERATOR")
    print("=" * 68)

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(VIDEO_GENERATOR),
        ],
        cwd=str(ROOT),
        timeout=VIDEO_TIMEOUT_SECONDS,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "rift_valley_video_generator.py failed "
            f"with exit code {result.returncode}"
        )


def verify_final_video():
    print("")
    print("=" * 68)
    print("VERIFYING FINAL MP4")
    print("=" * 68)

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not generated."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-show_entries",
                "stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(FINAL_VIDEO),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(probe.stdout)

    except Exception as exc:
        raise RuntimeError(
            f"Could not verify final MP4: {exc}"
        )

    streams = data.get("streams", [])

    video_stream = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "audio"
        ),
        None,
    )

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video_stream.get("width", 0)
    )

    height = int(
        video_stream.get("height", 0)
    )

    duration = float(
        data.get("format", {}).get(
            "duration",
            0,
        )
        or 0
    )

    print("MP4:", FINAL_VIDEO)
    print("Size:", size, "bytes")
    print("Width:", width)
    print("Height:", height)
    print("Duration:", round(duration, 2), "seconds")
    print(
        "Video codec:",
        video_stream.get("codec_name"),
    )
    print(
        "Audio codec:",
        audio_stream.get("codec_name"),
    )

    if width != 1080:
        raise RuntimeError(
            f"Video width is {width}, expected 1080."
        )

    if height != 1920:
        raise RuntimeError(
            f"Video height is {height}, expected 1920."
        )

    if duration < 5:
        raise RuntimeError(
            "Final video is shorter than 5 seconds."
        )

    print("")
    print("FINAL MP4 VERIFICATION PASSED")


# ============================================================
# REPORT
# ============================================================

def report_files():
    print("")
    print("=" * 68)
    print("GENERATED FILES")
    print("=" * 68)

    for label, directory in [
        ("OUTPUT", OUTPUT_DIR),
        ("AUDIO", AUDIO_DIR),
        ("SOURCE IMAGES", SOURCE_DIR),
        ("VIDEO WORK", VIDEO_WORK_DIR),
        ("DATA", DATA_DIR),
    ]:
        print("")
        print(label)

        if not directory.exists():
            print("  Directory missing")
            continue

        for path in sorted(directory.glob("*")):
            if path.is_file():
                print(
                    " ",
                    path.relative_to(ROOT),
                    "-",
                    path.stat().st_size,
                    "bytes",
                )


# ============================================================
# MAIN
# ============================================================

def main():
    started = time.time()

    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH")
    print("REALTIME STRICT-COUNTY NEWS ENGINE")
    print("VERSION: RVW_MAIN_V13_REALTIME_STRICT_COUNTY")
    print("=" * 68)
    print(
        "Kenya time:",
        now_kenya().isoformat(),
    )

    clean_previous()

    verify_project_files()

    candidates = discover()

    selected = select_best(candidates)

    script = build_script(selected)

    print("")
    print(
        "SCRIPT WORD COUNT:",
        len(script.split()),
    )

    # Download only already validated article images.
    print("")
    print("=" * 68)
    print("SAVING REAL ARTICLE PHOTOS")
    print("=" * 68)

    validated_images = []

    for url in selected["image_urls"]:
        result = download_image(url)

        if result:
            validated_images.append(result)

        if len(validated_images) >= MAX_ARTICLE_IMAGES:
            break

    if not validated_images:
        raise RuntimeError(
            "Could not save any validated article photos."
        )

    saved_images = save_article_images(
        validated_images
    )

    if not saved_images:
        raise RuntimeError(
            "Validated article photos could not be saved."
        )

    print(
        "Saved article photos:",
        len(saved_images),
    )

    for item in saved_images:
        print(
            " ",
            item["path"],
            "|",
            item["width"],
            "x",
            item["height"],
        )

    # Update selected article with the actual saved images.
    selected["image_urls"] = [
        item["url"]
        for item in saved_images
    ]

    selected["image_paths"] = [
        item["path"]
        for item in saved_images
    ]

    selected["image_url"] = (
        saved_images[0]["url"]
    )

    selected["image_path"] = (
        saved_images[0]["path"]
    )

    selected["image_count"] = len(
        saved_images
    )

    selected["selected_at"] = (
        now_kenya().isoformat()
    )

    story_data, script_data = (
        write_selected_files(
            selected,
            saved_images,
            script,
        )
    )

    validate_story(
        story_data,
        script_data,
    )

    print("")
    print("=" * 68)
    print("SELECTED STORY FILE CREATED")
    print("=" * 68)

    print(
        "County:",
        story_data["county"],
    )

    print(
        "Title:",
        story_data["title"],
    )

    print(
        "Published:",
        story_data["published_at_kenya"],
    )

    print(
        "Age:",
        story_data["age_hours"],
        "hours",
    )

    print(
        "Article URL:",
        story_data["article_url"],
    )

    print(
        "Images:",
        len(story_data["image_paths"]),
    )

    print("")
    print("=" * 68)
    print("SELECTED SCRIPT FILE CREATED")
    print("=" * 68)

    print(
        "County:",
        script_data["county"],
    )

    print(
        "Title:",
        script_data["title"],
    )

    print(
        "Words:",
        script_data["word_count"],
    )

    print("")
    print("Running video generator...")

    run_generator()

    verify_final_video()

    report_files()

    elapsed = time.time() - started

    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH GENERATION SUCCESSFUL")
    print("=" * 68)
    print("")
    print(
        "Final MP4:",
        FINAL_VIDEO.relative_to(ROOT),
    )
    print(
        "Elapsed:",
        round(elapsed, 1),
        "seconds",
    )
    print("")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("")
        print("Generation interrupted.")
        sys.exit(130)
    except Exception as exc:
        print("")
        print("=" * 68)
        print("RIFT VALLEY WATCH GENERATION FAILED")
        print("=" * 68)
        print("")
        print("ERROR:", exc)
        print("")
        sys.exit(1)
