# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V6_STABLE_MULTIPHOTO
#
# PURPOSE
# - Fetch fresh Rift Valley news at runtime
# - Prioritize current/recent stories
# - Cover the wider Rift Valley region
# - Prioritize politics + major regional developments
# - Exclude Rigathi Gachagua completely
# - Exclude Citizen/Citizen Digital/Citizen TV
# - Download REAL article photographs
# - Attempt to collect MULTIPLE real article photographs
# - Avoid logos, avatars, placeholders and generic images
# - Create data/story.json
# - Create data/script.json
#
# OUTPUT
#   data/story.json
#   data/script.json
#   assets/source/story_image*.jpg
#
# COMPATIBILITY
#   rift_valley_main.py
#   rift_valley_video_generator.py
# ============================================================

from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, quote
import hashlib
import html
import json
import re
import time

import requests


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"


# ============================================================
# SETTINGS
# ============================================================

MAX_STORIES = 8
MAX_IMAGES_PER_STORY = 6

TODAY_PRIORITY_HOURS = 24
RECENT_PRIORITY_HOURS = 72

REQUEST_TIMEOUT = 25

MIN_IMAGE_BYTES = 10000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# REGION
# ============================================================

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Narok",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Trans Nzoia",
    "Samburu",
    "Turkana",
    "Laikipia",
    "Kajiado",
]


COUNTY_ALIASES = {
    "bomet": [
        "bomet",
        "sotik",
        "chepalungu",
        "konoin",
        "kipkelion",
        "longisa",
    ],
    "kericho": [
        "kericho",
        "litein",
        "bureti",
        "belgut",
        "ainamoi",
        "kipkelion",
    ],
    "nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "bahati",
        "subukia",
        "rongai",
        "kuresoi",
    ],
    "narok": [
        "narok",
        "kilgoris",
        "transmara",
        "ololulunga",
        "suswa",
        "mara",
    ],
    "nandi": [
        "nandi",
        "kapsabet",
        "mosoriot",
        "aldai",
        "chesumei",
        "emgwen",
    ],
    "uasin gishu": [
        "uasin gishu",
        "eldoret",
        "ainabkoi",
        "kapseret",
        "kesses",
        "moiben",
        "soy",
        "turbo",
    ],
    "elgeyo-marakwet": [
        "elgeyo",
        "marakwet",
        "iten",
        "keiyo",
        "keiyo south",
        "keiyo north",
        "kapcherop",
        "kapsowar",
    ],
    "west pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "sigor",
        "kacheliba",
        "pokot south",
    ],
    "trans nzoia": [
        "trans nzoia",
        "kitale",
        "endebess",
        "cherangany",
        "kiminini",
        "saboti",
    ],
    "samburu": [
        "samburu",
        "maralal",
        "baragoi",
        "samburu east",
        "samburu north",
    ],
    "turkana": [
        "turkana",
        "lodwar",
        "kakuma",
        "lokichoggio",
        "turkana central",
        "turkana west",
    ],
    "laikipia": [
        "laikipia",
        "nanyuki",
        "nyahururu",
        "rumuruti",
        "ol pejeta",
    ],
    "kajiado": [
        "kajiado",
        "kitengela",
        "ngong",
        "namanga",
        "ongata rongai",
        "isinya",
        "loitokitok",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    "Rift Valley Kenya latest news today",
    "Rift Valley Kenya politics today",
    "Rift Valley Kenya development today",
    "Rift Valley Kenya infrastructure today",
    "Rift Valley Kenya business economy today",
    "Rift Valley Kenya agriculture today",
    "Rift Valley Kenya health today",
    "Rift Valley Kenya education today",
    "Rift Valley Kenya security today",
    "Bomet latest news today",
    "Kericho latest news today",
    "Nakuru latest news today",
    "Narok latest news today",
    "Nandi latest news today",
    "Uasin Gishu latest news today",
    "Elgeyo Marakwet latest news today",
    "West Pokot latest news today",
    "Trans Nzoia latest news today",
    "Samburu latest news today",
    "Turkana latest news today",
    "Laikipia latest news today",
    "Kajiado latest news today",
    "Kenya Rift Valley governor latest",
    "Kenya Rift Valley MP latest",
    "Kenya Rift Valley roads projects",
    "Kenya Rift Valley agriculture latest",
    "Kenya Rift Valley investment latest",
]


# ============================================================
# SOURCES
# ============================================================

TRUSTED_SOURCES = {
    "nation": 24,
    "daily nation": 24,
    "the standard": 23,
    "standard media": 23,
    "kbc": 22,
    "capital fm": 21,
    "the star": 21,
    "ntv kenya": 21,
    "kenya news agency": 24,
    "business daily": 23,
    "business daily africa": 23,
    "the east african": 22,
    "people daily": 19,
    "tuko": 15,
    "county government": 25,
    "government of kenya": 25,
    "ministry": 22,
    "state department": 22,
}


# ============================================================
# FORBIDDEN TERMS
# ============================================================

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


FORBIDDEN_SOURCE_TERMS = [
    "citizen",
    "citizen digital",
    "citizen tv",
]


FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizen-digital",
    "citizen_tv",
    "citizentv",
    "world-cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default",
    "profile",
    "generic",
    "logo",
    "sprite",
    "icon",
    "favicon",
    "advert",
    "advertisement",
    "banner",
]


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {
    "POLITICS": [
        "politics",
        "political",
        "governor",
        "governors",
        "mp",
        "mps",
        "member of parliament",
        "senator",
        "senators",
        "uda",
        "parliament",
        "county assembly",
        "assembly",
        "election",
        "elections",
        "campaign",
        "party",
        "ruto",
        "president",
        "deputy president",
        "minister",
        "cabinet",
    ],
    "DEVELOPMENT": [
        "development",
        "project",
        "projects",
        "funding",
        "construction",
        "facility",
        "facilities",
        "programme",
        "program",
        "investment",
    ],
    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "bridges",
        "railway",
        "airport",
        "water",
        "dam",
        "electricity",
        "power",
        "infrastructure",
    ],
    "BUSINESS & ECONOMY": [
        "business",
        "economy",
        "economic",
        "investment",
        "investor",
        "trade",
        "market",
        "markets",
        "industry",
        "company",
        "companies",
        "jobs",
        "employment",
        "finance",
        "bank",
        "banking",
    ],
    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "farming",
        "tea",
        "coffee",
        "maize",
        "milk",
        "livestock",
        "dairy",
        "crop",
        "crops",
        "harvest",
        "fertilizer",
        "fertiliser",
    ],
    "HEALTH": [
        "health",
        "hospital",
        "hospitals",
        "clinic",
        "clinics",
        "doctor",
        "doctors",
        "medicine",
        "medical",
        "disease",
        "patients",
    ],
    "EDUCATION": [
        "education",
        "school",
        "schools",
        "student",
        "students",
        "university",
        "college",
        "teacher",
        "teachers",
        "education ministry",
    ],
    "SECURITY": [
        "security",
        "police",
        "crime",
        "arrest",
        "arrests",
        "suspect",
        "suspects",
        "terror",
        "terrorism",
        "accident",
        "accidents",
        "fire",
        "flood",
        "disaster",
    ],
}


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def http_get(url, timeout=REQUEST_TIMEOUT):
    try:
        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response

    except Exception as exc:
        print(
            f"[NEWS] GET failed: {url} -> {exc}"
        )
        return None


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = html.unescape(str(value))

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

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


def clean_title(title):
    title = clean_text(title)

    patterns = [
        r"\s*[-|–—]\s*Citizen Digital.*$",
        r"\s*[-|–—]\s*Citizen TV.*$",
        r"\s*[-|–—]\s*Nation.*$",
        r"\s*[-|–—]\s*KBC.*$",
        r"\s*[-|–—]\s*The Star.*$",
        r"\s*[-|–—]\s*The Standard.*$",
        r"\s*[-|–—]\s*People Daily.*$",
    ]

    for pattern in patterns:
        title = re.sub(
            pattern,
            "",
            title,
            flags=re.I,
        )

    return clean_text(title)


# ============================================================
# FORBIDDEN CHECKS
# ============================================================

def contains_forbidden_text(text):
    lowered = clean_text(text).lower()

    return any(
        term in lowered
        for term in FORBIDDEN_TERMS
    )


def forbidden_source(source_name):
    lowered = clean_text(source_name).lower()

    return any(
        term in lowered
        for term in FORBIDDEN_SOURCE_TERMS
    )


def forbidden_image_url(url):
    lowered = clean_text(url).lower()

    return any(
        term in lowered
        for term in FORBIDDEN_IMAGE_TERMS
    )


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):
    if not value:
        return None

    text = clean_text(value)

    # ISO format.
    try:
        normalized = text.replace(
            "Z",
            "+00:00",
        )

        dt = datetime.fromisoformat(
            normalized
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(timezone.utc)

    except Exception:
        pass

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%d %b %Y %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
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

            return dt.astimezone(timezone.utc)

        except Exception:
            continue

    return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def fetch_google_news(query):
    encoded = quote(query)

    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )

    response = http_get(url)

    if response is None:
        return []

    text = response.text

    items = re.findall(
        r"<item>(.*?)</item>",
        text,
        flags=re.I | re.S,
    )

    results = []

    for item in items:
        title_match = re.search(
            r"<title>(.*?)</title>",
            item,
            flags=re.I | re.S,
        )

        link_match = re.search(
            r"<link>(.*?)</link>",
            item,
            flags=re.I | re.S,
        )

        pub_match = re.search(
            r"<pubDate>(.*?)</pubDate>",
            item,
            flags=re.I | re.S,
        )

        source_match = re.search(
            r"<source[^>]*>(.*?)</source>",
            item,
            flags=re.I | re.S,
        )

        description_match = re.search(
            r"<description>(.*?)</description>",
            item,
            flags=re.I | re.S,
        )

        title = clean_title(
            title_match.group(1)
            if title_match
            else ""
        )

        link = clean_text(
            link_match.group(1)
            if link_match
            else ""
        )

        pub_date = clean_text(
            pub_match.group(1)
            if pub_match
            else ""
        )

        source = clean_text(
            source_match.group(1)
            if source_match
            else ""
        )

        description = clean_text(
            description_match.group(1)
            if description_match
            else ""
        )

        if not title or not link:
            continue

        results.append(
            {
                "title": title,
                "url": link,
                "date_raw": pub_date,
                "source_name": source,
                "description": description,
                "query": query,
            }
        )

    return results


# ============================================================
# ARTICLE IMAGE EXTRACTION
# ============================================================

def absolute_url(base_url, image_url):
    if not image_url:
        return ""

    image_url = html.unescape(
        clean_text(image_url)
    )

    image_url = image_url.strip(
        "\"' "
    )

    if image_url.startswith("//"):
        parsed = urlparse(base_url)

        return (
            f"{parsed.scheme}:{image_url}"
        )

    return urljoin(
        base_url,
        image_url,
    )


def extract_meta_images(page_url, html_text):
    images = []

    # Open Graph images.
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html_text,
            flags=re.I,
        )

        for match in matches:
            image = absolute_url(
                page_url,
                match,
            )

            if image:
                images.append(image)

    return images


def extract_json_ld_images(page_url, html_text):
    images = []

    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.I | re.S,
    )

    for block in blocks:
        block = html.unescape(
            block.strip()
        )

        try:
            data = json.loads(block)
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

        for obj in objects:
            if not isinstance(obj, dict):
                continue

            image_value = obj.get("image")

            if isinstance(image_value, str):
                images.append(
                    absolute_url(
                        page_url,
                        image_value,
                    )
                )

            elif isinstance(image_value, list):
                for item in image_value:
                    if isinstance(item, str):
                        images.append(
                            absolute_url(
                                page_url,
                                item,
                            )
                        )

                    elif isinstance(item, dict):
                        url = item.get("url")

                        if url:
                            images.append(
                                absolute_url(
                                    page_url,
                                    url,
                                )
                            )

            elif isinstance(image_value, dict):
                url = image_value.get("url")

                if url:
                    images.append(
                        absolute_url(
                            page_url,
                            url,
                        )
                    )

    return images


def extract_article_img_urls(page_url, html_text):
    images = []

    # Standard src.
    patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html_text,
            flags=re.I,
        )

        for match in matches:
            image = absolute_url(
                page_url,
                match,
            )

            if image:
                images.append(image)

    # srcset.
    srcsets = re.findall(
        r'<img[^>]+srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in srcsets:
        entries = srcset.split(",")

        for entry in entries:
            value = entry.strip().split(" ")[0]

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    return images


def image_candidate_score(url):
    lowered = url.lower()

    score = 0

    positive_terms = [
        "article",
        "news",
        "upload",
        "uploads",
        "media",
        "images",
        "image",
        "photo",
        "content",
        "wp-content",
    ]

    negative_terms = [
        "logo",
        "icon",
        "favicon",
        "avatar",
        "profile",
        "placeholder",
        "sprite",
        "banner",
        "advert",
        "ads",
        "facebook",
        "twitter",
        "instagram",
        "youtube",
        "worldcup",
        "world-cup",
    ]

    for term in positive_terms:
        if term in lowered:
            score += 3

    for term in negative_terms:
        if term in lowered:
            score -= 20

    if forbidden_image_url(url):
        score -= 100

    return score


def find_article_images(article_url):
    response = http_get(
        article_url,
        timeout=REQUEST_TIMEOUT,
    )

    if response is None:
        return []

    page = response.text

    candidates = []

    candidates.extend(
        extract_meta_images(
            article_url,
            page,
        )
    )

    candidates.extend(
        extract_json_ld_images(
            article_url,
            page,
        )
    )

    candidates.extend(
        extract_article_img_urls(
            article_url,
            page,
        )
    )

    # De-duplicate URLs.
    unique = []
    seen = set()

    for url in candidates:
        url = clean_text(url)

        if not url:
            continue

        if not url.startswith(
            ("http://", "https://")
        ):
            continue

        normalized = url.split("?")[0].lower()

        if normalized in seen:
            continue

        seen.add(normalized)

        if forbidden_image_url(url):
            continue

        unique.append(url)

    unique.sort(
        key=image_candidate_score,
        reverse=True,
    )

    return unique[:30]


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def image_has_valid_dimensions(path):
    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

        return True

    except Exception:
        return False


def download_image(url, destination):
    if not url:
        return False

    if forbidden_image_url(url):
        return False

    try:
        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            "image" not in content_type
            and not url.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
        ):
            return False

        temporary = destination.with_suffix(
            ".download"
        )

        with temporary.open("wb") as handle:
            for chunk in response.iter_content(
                chunk_size=65536
            ):
                if chunk:
                    handle.write(chunk)

        if not temporary.exists():
            return False

        if temporary.stat().st_size < MIN_IMAGE_BYTES:
            temporary.unlink(missing_ok=True)
            return False

        if not image_has_valid_dimensions(
            temporary
        ):
            temporary.unlink(missing_ok=True)
            return False

        temporary.replace(destination)

        return True

    except Exception as exc:
        try:
            destination.with_suffix(
                ".download"
            ).unlink(
                missing_ok=True
            )
        except Exception:
            pass

        print(
            f"[NEWS] Image download failed: "
            f"{url} -> {exc}"
        )

        return False


# ============================================================
# IMAGE SIGNATURE
# ============================================================

def file_signature(path):
    try:
        digest = hashlib.sha256()

        with path.open(
            "rb"
        ) as handle:
            while True:
                chunk = handle.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    lowered = clean_text(
        text
    ).lower()

    best_county = ""

    best_score = 0

    for county, aliases in COUNTY_ALIASES.items():
        score = 0

        for alias in aliases:
            if alias in lowered:
                score += 1

        if score > best_score:
            best_score = score
            best_county = county

    if not best_county:
        return ""

    return best_county.title()


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(text):
    lowered = clean_text(
        text
    ).lower()

    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword in lowered:
                score += 1

        scores[category] = score

    best_category = max(
        scores,
        key=scores.get,
    )

    if scores[best_category] <= 0:
        return "DEVELOPMENT"

    return best_category


# ============================================================
# SOURCE SCORE
# ============================================================

def source_score(source_name):
    lowered = clean_text(
        source_name
    ).lower()

    best = 5

    for source, score in TRUSTED_SOURCES.items():
        if source in lowered:
            best = max(
                best,
                score,
            )

    return best


# ============================================================
# POLITICAL SCORE
# ============================================================

def political_score(text):
    lowered = clean_text(
        text
    ).lower()

    keywords = [
        "president",
        "deputy president",
        "governor",
        "mp",
        "mps",
        "senator",
        "senators",
        "parliament",
        "uda",
        "ruto",
        "county assembly",
        "election",
        "elections",
        "politics",
    ]

    return sum(
        1
        for keyword in keywords
        if keyword in lowered
    )


# ============================================================
# FRESHNESS
# ============================================================

def freshness_score(dt):
    if dt is None:
        return 0

    now = datetime.now(
        timezone.utc
    )

    age = now - dt

    hours = max(
        0,
        age.total_seconds() / 3600,
    )

    if hours <= TODAY_PRIORITY_HOURS:
        return 40

    if hours <= RECENT_PRIORITY_HOURS:
        return 25

    if hours <= 168:
        return 10

    return 0


# ============================================================
# RELEVANCE
# ============================================================

def relevance_score(item):
    title = clean_text(
        item.get("title")
    )

    description = clean_text(
        item.get("description")
    )

    source = clean_text(
        item.get("source_name")
    )

    combined = (
        f"{title} "
        f"{description}"
    )

    if contains_forbidden_text(
        combined
    ):
        return -1000

    if forbidden_source(source):
        return -1000

    county = detect_county(
        combined
    )

    category = detect_category(
        combined
    )

    score = 0

    # Rift Valley relevance.
    if county:
        score += 35

    if "rift valley" in combined.lower():
        score += 25

    # Source quality.
    score += source_score(
        source
    )

    # Freshness.
    dt = parse_date(
        item.get("date_raw")
    )

    score += freshness_score(
        dt
    )

    # Category.
    category_weights = {
        "POLITICS": 18,
        "DEVELOPMENT": 17,
        "INFRASTRUCTURE": 17,
        "BUSINESS & ECONOMY": 16,
        "AGRICULTURE": 14,
        "HEALTH": 12,
        "EDUCATION": 12,
        "SECURITY": 13,
    }

    score += category_weights.get(
        category,
        5,
    )

    # Political relevance.
    score += min(
        political_score(combined) * 2,
        12,
    )

    # Strong titles.
    if len(title) >= 35:
        score += 5

    if len(description) >= 80:
        score += 5

    return score


# ============================================================
# STORY ID
# ============================================================

def story_id(item):
    title = clean_text(
        item.get("title")
    ).lower()

    url = clean_text(
        item.get("url")
    ).lower()

    raw = (
        f"{title}|{url}"
    )

    return hashlib.sha1(
        raw.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:12]


# ============================================================
# NORMALIZE STORY
# ============================================================

def normalize_story(item):
    title = clean_title(
        item.get("title")
    )

    description = clean_text(
        item.get("description")
    )

    source_name = clean_text(
        item.get("source_name")
    )

    url = clean_text(
        item.get("url")
    )

    combined = (
        f"{title} "
        f"{description}"
    )

    county = detect_county(
        combined
    )

    category = detect_category(
        combined
    )

    dt = parse_date(
        item.get("date_raw")
    )

    if dt:
        date_value = dt.isoformat()
    else:
        date_value = ""

    return {
        "id": story_id(item),
        "title": title,
        "county": county,
        "category": category,
        "date": date_value,
        "source": {
            "name": source_name,
            "url": url,
            "type": (
                "OFFICIAL_SOURCE"
                if (
                    "county government"
                    in source_name.lower()
                    or "government of kenya"
                    in source_name.lower()
                    or "ministry"
                    in source_name.lower()
                )
                else "NEWS_SOURCE"
            ),
        },
        "summary": description,
        "article_url": url,
        "images": [],
        "image": "",
        "image_path": "",
        "image_urls": [],
        "verified_facts": [],
        "official_statement": {
            "available": False,
            "speaker": "",
            "quote": "",
        },
        "visuals": [],
        "editorial": {
            "confirmed": [],
            "unconfirmed": [],
        },
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate(items):
    unique = []

    seen_urls = set()
    seen_titles = set()

    for item in items:
        url = clean_text(
            item.get("url")
        ).lower()

        title = re.sub(
            r"[^a-z0-9]+",
            " ",
            clean_text(
                item.get("title")
            ).lower(),
        ).strip()

        if url and url in seen_urls:
            continue

        if title and title in seen_titles:
            continue

        if url:
            seen_urls.add(url)

        if title:
            seen_titles.add(title)

        unique.append(item)

    return unique


# ============================================================
# DIVERSE SELECTION
# ============================================================

def select_diverse_stories(items):
    ranked = sorted(
        items,
        key=relevance_score,
        reverse=True,
    )

    selected = []

    counties_seen = set()
    categories_seen = set()

    # First pass: diversity.
    for item in ranked:
        if len(selected) >= MAX_STORIES:
            break

        text = (
            f"{item.get('title', '')} "
            f"{item.get('description', '')}"
        )

        county = detect_county(text)
        category = detect_category(text)

        if (
            county
            and county.lower()
            in counties_seen
            and category
            and category in categories_seen
        ):
            continue

        selected.append(item)

        if county:
            counties_seen.add(
                county.lower()
            )

        if category:
            categories_seen.add(
                category
            )

    # Second pass: fill remaining slots.
    if len(selected) < MAX_STORIES:
        selected_ids = {
            story_id(item)
            for item in selected
        }

        for item in ranked:
            if len(selected) >= MAX_STORIES:
                break

            if story_id(item) in selected_ids:
                continue

            selected.append(item)

    return selected


# ============================================================
# DOWNLOAD STORY IMAGES
# ============================================================

def download_story_images(story, story_number):
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    article_url = story.get(
        "article_url"
    )

    if not article_url:
        article_url = (
            story.get("source", {})
            .get("url", "")
        )

    if not article_url:
        return []

    image_urls = find_article_images(
        article_url
    )

    if not image_urls:
        print(
            "[NEWS] No article images found: "
            f"{story.get('title')}"
        )

        return []

    downloaded = []

    signatures = set()

    for index, image_url in enumerate(
        image_urls,
        start=1,
    ):
        if len(downloaded) >= MAX_IMAGES_PER_STORY:
            break

        if forbidden_image_url(
            image_url
        ):
            continue

        if index == 1:
            filename = (
                f"story_{story_number}_image.jpg"
            )
        else:
            filename = (
                f"story_{story_number}_"
                f"image_{index}.jpg"
            )

        destination = (
            SOURCE_DIR / filename
        )

        # Try download.
        if not download_image(
            image_url,
            destination,
        ):
            continue

        signature = file_signature(
            destination
        )

        if signature and signature in signatures:
            destination.unlink(
                missing_ok=True
            )
            continue

        if signature:
            signatures.add(
                signature
            )

        downloaded.append(
            {
                "path": str(
                    destination.relative_to(
                        BASE_DIR
                    )
                ),
                "url": image_url,
                "file": destination.name,
            }
        )

        print(
            "[NEWS] Downloaded image "
            f"{len(downloaded)}: "
            f"{destination.name}"
        )

    return downloaded


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean_text(
        story.get("title")
    )

    summary = clean_text(
        story.get("summary")
    )

    county = clean_text(
        story.get("county")
    )

    category = clean_text(
        story.get("category")
    )

    source = (
        story.get("source", {})
        if isinstance(
            story.get("source"),
            dict,
        )
        else {}
    )

    source_name = clean_text(
        source.get("name")
    )

    parts = []

    if title:
        parts.append(
            title + "."
        )

    if summary:
        parts.append(
            summary
        )

    if county:
        parts.append(
            f"The development is being "
            f"followed in {county}."
        )

    if category:
        parts.append(
            f"This is a {category.lower()} "
            f"update from Rift Valley Watch."
        )

    if source_name:
        parts.append(
            f"Source: {source_name}."
        )

    narration = " ".join(
        clean_text(part)
        for part in parts
        if clean_text(part)
    )

    narration = clean_text(
        narration
    )

    if contains_forbidden_text(
        narration
    ):
        return ""

    return narration


# ============================================================
# VISUAL METADATA
# ============================================================

def build_visuals(story):
    visuals = []

    title = clean_text(
        story.get("title")
    )

    county = clean_text(
        story.get("county")
    )

    category = clean_text(
        story.get("category")
    )

    images = story.get(
        "images",
        [],
    )

    if title:
        visuals.append(
            {
                "type": "REAL_ARTICLE_PHOTO",
                "description": title,
            }
        )

    if county:
        visuals.append(
            {
                "type": "LOCATION",
                "description": county,
            }
        )

    if category:
        visuals.append(
            {
                "type": "CATEGORY",
                "description": category,
            }
        )

    if isinstance(images, list):
        for index, image in enumerate(
            images,
            start=1,
        ):
            visuals.append(
                {
                    "type": "REAL_ARTICLE_PHOTO",
                    "description": (
                        f"Article photograph "
                        f"{index}"
                    ),
                    "image": image,
                }
            )

    source = story.get(
        "source",
        {},
    )

    if isinstance(source, dict):
        source_name = clean_text(
            source.get("name")
        )

        if source_name:
            visuals.append(
                {
                    "type": "SOURCE_CARD",
                    "description": source_name,
                }
            )

    return visuals


# ============================================================
# STORY JSON
# ============================================================

def write_story_json(stories):
    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "region": "Rift Valley, Kenya",
        "story_count": len(stories),
        "stories": stories,
    }

    save_json(
        STORY_FILE,
        payload,
    )

    print(
        f"[NEWS] Wrote {STORY_FILE}"
    )


# ============================================================
# SCRIPT JSON
# ============================================================

def write_script_json(stories):
    scripts = []

    for story in stories:
        narration = build_narration(
            story
        )

        scripts.append(
            {
                "id": story.get("id", ""),
                "title": story.get(
                    "title",
                    "",
                ),
                "county": story.get(
                    "county",
                    "",
                ),
                "category": story.get(
                    "category",
                    "",
                ),
                "narration": narration,
                "images": story.get(
                    "images",
                    [],
                ),
            }
        )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "scripts": scripts,
    }

    save_json(
        SCRIPT_FILE,
        payload,
    )

    print(
        f"[NEWS] Wrote {SCRIPT_FILE}"
    )


# ============================================================
# SAVE JSON
# ============================================================

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
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(path)


# ============================================================
# CLEAN OLD SOURCE IMAGES
# ============================================================

def clean_old_images():
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in SOURCE_DIR.iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            continue

        try:
            path.unlink()
        except Exception as exc:
            print(
                f"[NEWS] Could not remove "
                f"{path}: {exc}"
            )


# ============================================================
# COLLECT NEWS
# ============================================================

def collect_news():
    print()
    print("=" * 72)
    print(
        "RIFT VALLEY WATCH - "
        "REAL-TIME NEWS ENGINE V6"
    )
    print("=" * 72)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    clean_old_images()

    all_items = []

    # --------------------------------------------------------
    # Fetch Google News RSS results.
    # --------------------------------------------------------

    for number, query in enumerate(
        SEARCH_QUERIES,
        start=1,
    ):
        print(
            f"[NEWS] Search {number}/"
            f"{len(SEARCH_QUERIES)}: "
            f"{query}"
        )

        try:
            items = fetch_google_news(
                query
            )

            all_items.extend(items)

        except Exception as exc:
            print(
                f"[NEWS] Search failed: "
                f"{exc}"
            )

        # Small pause to reduce request pressure.
        time.sleep(0.15)

    print(
        f"[NEWS] Raw results: "
        f"{len(all_items)}"
    )

    # --------------------------------------------------------
    # Filter forbidden content.
    # --------------------------------------------------------

    filtered = []

    for item in all_items:
        title = clean_text(
            item.get("title")
        )

        description = clean_text(
            item.get("description")
        )

        source = clean_text(
            item.get("source_name")
        )

        combined = (
            f"{title} "
            f"{description}"
        )

        if contains_forbidden_text(
            combined
        ):
            continue

        if forbidden_source(
            source
        ):
            continue

        if not title:
            continue

        if not item.get("url"):
            continue

        filtered.append(item)

    print(
        f"[NEWS] After content filtering: "
        f"{len(filtered)}"
    )

    # --------------------------------------------------------
    # Deduplicate.
    # --------------------------------------------------------

    filtered = deduplicate(
        filtered
    )

    print(
        f"[NEWS] After deduplication: "
        f"{len(filtered)}"
    )

    # --------------------------------------------------------
    # Require actual Rift Valley relevance.
    # --------------------------------------------------------

    relevant = []

    for item in filtered:
        text = (
            f"{item.get('title', '')} "
            f"{item.get('description', '')}"
        )

        county = detect_county(
            text
        )

        if (
            county
            or "rift valley"
            in text.lower()
        ):
            relevant.append(item)

    print(
        f"[NEWS] Rift Valley relevant: "
        f"{len(relevant)}"
    )

    # If too few regional results survive,
    # use the strongest remaining results.
    if len(relevant) < 4:
        relevant = sorted(
            filtered,
            key=relevance_score,
            reverse=True,
        )[:20]

    selected_raw = select_diverse_stories(
        relevant
    )

    print(
        f"[NEWS] Selected candidates: "
        f"{len(selected_raw)}"
    )

    # --------------------------------------------------------
    # Normalize and download real article images.
    # --------------------------------------------------------

    stories = []

    for number, item in enumerate(
        selected_raw,
        start=1,
    ):
        story = normalize_story(
            item
        )

        title = clean_text(
            story.get("title")
        )

        if contains_forbidden_text(
            title
        ):
            continue

        print()
        print(
            f"[NEWS] STORY {number}: "
            f"{title}"
        )

        print(
            f"[NEWS] County: "
            f"{story.get('county', '')}"
        )

        print(
            f"[NEWS] Category: "
            f"{story.get('category', '')}"
        )

        print(
            f"[NEWS] Source: "
            f"{story.get('source', {}).get('name', '')}"
        )

        images = download_story_images(
            story,
            number,
        )

        if not images:
            print(
                "[NEWS] Story rejected: "
                "no valid real article photo."
            )
            continue

        story["images"] = [
            item["path"]
            for item in images
        ]

        story["image_urls"] = [
            item["url"]
            for item in images
        ]

        story["image"] = story[
            "images"
        ][0]

        story["image_path"] = story[
            "images"
        ][0]

        story["visuals"] = build_visuals(
            story
        )

        # Basic confirmed editorial fields.
        story["editorial"]["confirmed"] = [
            f"Published source: "
            f"{story.get('source', {}).get('name', '')}",
        ]

        if story.get("county"):
            story["editorial"]["confirmed"].append(
                f"Location: "
                f"{story.get('county')}"
            )

        if story.get("date"):
            story["editorial"]["confirmed"].append(
                f"Publication date: "
                f"{story.get('date')}"
            )

        stories.append(
            story
        )

        if len(stories) >= MAX_STORIES:
            break

    # --------------------------------------------------------
    # Emergency fallback.
    # --------------------------------------------------------

    if not stories:
        raise RuntimeError(
            "News engine found no usable "
            "Rift Valley stories with valid "
            "real article photographs."
        )

    # --------------------------------------------------------
    # Write outputs.
    # --------------------------------------------------------

    write_story_json(
        stories
    )

    write_script_json(
        stories
    )

    print()
    print("=" * 72)
    print(
        "NEWS ENGINE COMPLETED SUCCESSFULLY"
    )
    print("=" * 72)

    print(
        f"[NEWS] Final stories: "
        f"{len(stories)}"
    )

    for index, story in enumerate(
        stories,
        start=1,
    ):
        print(
            f"[NEWS] {index}. "
            f"{story.get('title', '')}"
        )

        print(
            f"       County: "
            f"{story.get('county', '')}"
        )

        print(
            f"       Category: "
            f"{story.get('category', '')}"
        )

        print(
            f"       Photos: "
            f"{len(story.get('images', []))}"
        )

    print()
    print(
        f"[NEWS] Story file: "
        f"{STORY_FILE}"
    )

    print(
        f"[NEWS] Script file: "
        f"{SCRIPT_FILE}"
    )

    return stories


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        collect_news()

    except KeyboardInterrupt:
        print(
            "[NEWS] Interrupted."
        )
        raise SystemExit(130)

    except Exception as exc:
        print()
        print(
            "=" * 72
        )
        print(
            "NEWS ENGINE FAILED"
        )
        print(
            "=" * 72
        )
        print(
            f"ERROR: {exc}"
        )

        raise SystemExit(1)
