# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE V6
#
# PURPOSE
# - Fetch fresh Rift Valley news at runtime
# - Prioritize today's events
# - Cover the entire Rift Valley
# - Prioritize politics + major regional developments
# - Exclude Rigathi Gachagua
# - Avoid Citizen branding
# - Download genuine article photographs
# - Support multiple genuine article photographs
# - Create data/story.json
# - Create data/script.json
# - Preserve compatibility with rift_valley_main.py
# ============================================================

import json
import hashlib
import html
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone, timedelta


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
TODAY_PRIORITY_HOURS = 24
RECENT_PRIORITY_HOURS = 48
REQUEST_TIMEOUT = 20
MAX_IMAGES_PER_STORY = 6

USER_AGENT = (
    "Mozilla/5.0 "
    "(X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# ============================================================
# RIFT VALLEY COVERAGE
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
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chebunyo",
        "Chepalungu",
        "Konoin",
        "Kipkelion",
    ],

    "Kericho": [
        "Kericho",
        "Litein",
        "Londiani",
        "Ainamoi",
        "Bureti",
        "Belgut",
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

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Mai Mahiu",
        "Mara",
        "Transmara",
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Nandi Hills",
        "Mosop",
        "Aldai",
        "Emgwen",
    ],

    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Turbo",
        "Kesses",
        "Soy",
        "Moiben",
    ],

    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Iten",
        "Kapsowar",
        "Keiyo",
        "Marakwet",
        "Kabarnet",
    ],

    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Sigor",
        "Pokot",
    ],

    "Trans Nzoia": [
        "Trans Nzoia",
        "Kitale",
        "Endebess",
        "Kiminini",
        "Cherangany",
        "Saboti",
    ],

    "Samburu": [
        "Samburu",
        "Maralal",
        "Baragoi",
        "Wamba",
    ],

    "Turkana": [
        "Turkana",
        "Lodwar",
        "Kakuma",
        "Lokichar",
        "Kalokol",
    ],

    "Laikipia": [
        "Laikipia",
        "Nanyuki",
        "Rumuruti",
        "Nyahururu",
        "Ndaragwa",
    ],

    "Kajiado": [
        "Kajiado",
        "Kitengela",
        "Ngong",
        "Loitokitok",
        "Namanga",
        "Isinya",
        "Magadi",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [

    '"Rift Valley" Kenya news',

    '"Rift Valley" Kenya politics',
    '"Rift Valley" Kenya government',
    '"Rift Valley" Kenya Ruto',
    '"Rift Valley" Kenya UDA',
    '"Rift Valley" Kenya 2027 politics',

    '"Rift Valley" Kenya development',
    '"Rift Valley" Kenya roads',
    '"Rift Valley" Kenya infrastructure',
    '"Rift Valley" Kenya projects',

    '"Rift Valley" Kenya business',
    '"Rift Valley" Kenya economy',
    '"Rift Valley" Kenya investment',
    '"Rift Valley" Kenya agriculture',

    '"Rift Valley" Kenya security',
    '"Rift Valley" Kenya health',
    '"Rift Valley" Kenya education',

    '"Bomet" Kenya news',
    '"Kericho" Kenya news',
    '"Nakuru" Kenya news',
    '"Narok" Kenya news',
    '"Nandi" Kenya news',
    '"Uasin Gishu" Kenya news',
    '"Elgeyo-Marakwet" Kenya news',
    '"West Pokot" Kenya news',
    '"Trans Nzoia" Kenya news',
    '"Samburu" Kenya news',
    '"Turkana" Kenya news',
    '"Laikipia" Kenya news',
    '"Kajiado" Kenya news',

    '"William Ruto" "Rift Valley"',
    '"President Ruto" "Rift Valley"',
    '"UDA" "Rift Valley"',
    '"Rift Valley" governor Kenya',
    '"Rift Valley" MP Kenya',
    '"Rift Valley" senator Kenya',
]


# ============================================================
# HARD EXCLUSIONS
# ============================================================

FORBIDDEN_NAMES = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# SOURCE PRIORITY
#
# Citizen removed deliberately.
# The renderer must never introduce Citizen branding.
# ============================================================

TRUSTED_SOURCES = {
    "kenya news agency": 28,
    "government of kenya": 27,
    "county government": 25,
    "nation": 22,
    "the standard": 22,
    "standard media": 22,
    "kbc": 22,
    "capital fm": 20,
    "the star": 20,
    "ntv kenya": 20,
    "business daily": 20,
    "business daily africa": 20,
    "the east african": 18,
    "people daily": 17,
    "tuko": 15,
}


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {

    "POLITICS": [
        "president",
        "ruto",
        "uda",
        "politics",
        "political",
        "governor",
        "senator",
        "mp ",
        "member of parliament",
        "election",
        "2027",
        "party",
        "campaign",
        "rally",
        "coalition",
        "government",
        "deputy president",
        "cabinet",
    ],

    "DEVELOPMENT": [
        "development",
        "project",
        "launched",
        "construction",
        "funding",
        "government project",
        "county project",
        "development plan",
    ],

    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "railway",
        "airport",
        "water",
        "sewer",
        "infrastructure",
        "construction",
        "dam",
    ],

    "BUSINESS & ECONOMY": [
        "business",
        "economy",
        "investment",
        "investor",
        "market",
        "trade",
        "company",
        "jobs",
        "employment",
        "industry",
        "finance",
        "revenue",
    ],

    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "tea",
        "coffee",
        "maize",
        "livestock",
        "dairy",
        "crop",
        "harvest",
        "fertilizer",
        "farming",
    ],

    "HEALTH": [
        "health",
        "hospital",
        "doctor",
        "patients",
        "disease",
        "clinic",
        "medical",
        "healthcare",
    ],

    "EDUCATION": [
        "education",
        "school",
        "schools",
        "university",
        "students",
        "teachers",
        "college",
        "education ministry",
    ],

    "SECURITY": [
        "police",
        "security",
        "crime",
        "arrest",
        "attack",
        "fire",
        "accident",
        "missing",
        "terror",
        "bandit",
        "investigation",
        "death",
    ],
}


# ============================================================
# IMAGE EXCLUSION TERMS
# ============================================================

BAD_IMAGE_TERMS = [
    "citizen",
    "citizen-tv",
    "citizen_tv",
    "ctv",
    "world-cup",
    "world_cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "generic",
    "profile-picture",
    "profile_picture",
    "profilepic",
    "logo",
    "logos",
    "icon",
    "sprite",
    "favicon",
    "thumbnail-placeholder",
    "no-image",
    "no_image",
]


# ============================================================
# HTTP
# ============================================================

def http_get(url, timeout=REQUEST_TIMEOUT):

    if not url:
        return b""

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            return response.read()

    except Exception:
        return b""


# ============================================================
# CLEANING
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = html.unescape(str(value))

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def clean_title(value):

    value = clean_text(value)

    value = re.sub(
        r"\s*-\s*(Citizen Digital|Nation|KBC|The Star|The Standard|NTV).*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    return value.strip(" -")


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):

    if not value:
        return None

    value = value.strip()

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M GMT",
        "%a, %d %b %Y %H:%M:%S %Z",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def fetch_google_news(query):

    encoded = urllib.parse.quote_plus(
        query
    )

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )

    raw = http_get(url)

    if not raw:
        return []

    try:
        root = ET.fromstring(raw)

    except Exception:
        return []

    results = []

    for item in root.findall(".//item"):

        title = clean_title(
            item.findtext("title", "")
        )

        link = clean_text(
            item.findtext("link", "")
        )

        description = clean_text(
            item.findtext("description", "")
        )

        pub_date = clean_text(
            item.findtext("pubDate", "")
        )

        source_element = item.find("source")

        source = ""

        if source_element is not None:
            source = clean_text(
                source_element.text
            )

        if not title or not link:
            continue

        results.append({
            "title": title,
            "url": link,
            "description": description,
            "published": pub_date,
            "source": source,
            "query": query,
        })

    return results


# ============================================================
# IMAGE URL NORMALIZATION
# ============================================================

def absolute_url(base_url, image_url):

    if not image_url:
        return ""

    image_url = html.unescape(
        image_url.strip()
    )

    if image_url.startswith("//"):
        return "https:" + image_url

    if image_url.startswith("http://"):
        return image_url

    if image_url.startswith("https://"):
        return image_url

    return urllib.parse.urljoin(
        base_url,
        image_url
    )


# ============================================================
# IMAGE QUALITY FILTER
# ============================================================

def image_url_is_allowed(image_url):

    if not image_url:
        return False

    lower = image_url.lower()

    for term in BAD_IMAGE_TERMS:

        if term in lower:
            return False

    return True


# ============================================================
# EXTRACT IMAGE URLS
# ============================================================

def extract_image_urls(page, base_url):

    if not page:
        return []

    text = page.decode(
        "utf-8",
        errors="ignore"
    )

    candidates = []

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        r'<img[^>]+src=["\']([^"\']+)["\']',

        r'<img[^>]+data-src=["\']([^"\']+)["\']',

        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',

        r'<img[^>]+data-original=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for value in matches:

            absolute = absolute_url(
                base_url,
                value
            )

            if not absolute:
                continue

            if not image_url_is_allowed(
                absolute
            ):
                continue

            if absolute not in candidates:
                candidates.append(
                    absolute
                )

    return candidates


# ============================================================
# ARTICLE IMAGES
# ============================================================

def find_article_images(url):

    page = http_get(
        url,
        timeout=REQUEST_TIMEOUT
    )

    if not page:
        return []

    candidates = extract_image_urls(
        page,
        url
    )

    return candidates[:MAX_IMAGES_PER_STORY]


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_bytes(content):

    if not content:
        return False

    if len(content) < 10000:
        return False

    try:

        from PIL import Image
        from io import BytesIO

        image = Image.open(
            BytesIO(content)
        )

        width, height = image.size

        if width < 400 or height < 300:
            return False

        if width * height < 160000:
            return False

        return True

    except Exception:
        return False


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    image_url,
    story_id,
    index
):

    if not image_url:
        return ""

    if not image_url_is_allowed(
        image_url
    ):
        return ""

    try:

        request = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "image/avif,image/webp,"
                    "image/apng,image/svg+xml,"
                    "image/*,*/*;q=0.8"
                ),
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            content = response.read()

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

        if not validate_image_bytes(
            content
        ):
            return ""

        extension = ".jpg"

        if "webp" in content_type:
            extension = ".webp"

        elif "png" in content_type:
            extension = ".png"

        elif "avif" in content_type:
            extension = ".avif"

        elif "jpeg" in content_type:
            extension = ".jpg"

        filename = (
            f"story_{story_id}_{index}{extension}"
        )

        output = SOURCE_DIR / filename

        with open(
            output,
            "wb"
        ) as f:

            f.write(content)

        return (
            "assets/source/"
            + filename
        )

    except Exception:
        return ""


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    matches = []

    for county, aliases in COUNTY_ALIASES.items():

        for alias in aliases:

            if alias.lower() in text:

                matches.append(
                    county
                )

                break

    if not matches:
        return ""

    for county in matches:

        if county.lower() in text:
            return county

    return matches[0]


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword.lower() in text:
                score += 1

        scores[category] = score

    best = max(
        scores,
        key=scores.get
    )

    if scores[best] == 0:
        return "REGIONAL NEWS"

    return best


# ============================================================
# EXCLUSION
# ============================================================

def is_forbidden(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    for name in FORBIDDEN_NAMES:

        if name in text:
            return True

    return False


# ============================================================
# TRUSTED SOURCE SCORE
# ============================================================

def source_score(source):

    source_lower = clean_text(
        source
    ).lower()

    score = 0

    for name, points in TRUSTED_SOURCES.items():

        if name in source_lower:

            score = max(
                score,
                points
            )

    return score


# ============================================================
# POLITICAL PRIORITY
# ============================================================

def political_score(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    score = 0

    priority_terms = {

        "william ruto": 35,
        "president ruto": 35,
        "ruto": 25,
        "uda": 20,
        "governor": 18,
        "senator": 18,
        "mp ": 15,
        "member of parliament": 15,
        "2027": 25,
        "election": 20,
        "politics": 15,
        "political": 15,
        "party": 12,
        "government": 10,
        "cabinet": 15,
    }

    for term, points in priority_terms.items():

        if term in text:
            score += points

    return min(
        score,
        60
    )


# ============================================================
# FRESHNESS SCORE
# ============================================================

def freshness_score(
    published
):

    dt = parse_date(
        published
    )

    if dt is None:
        return 0

    now = datetime.now(
        timezone.utc
    )

    age = (
        now - dt
    ).total_seconds() / 3600

    if age < 0:
        age = 0

    if age <= 6:
        return 80

    if age <= 12:
        return 70

    if age <= 24:
        return 60

    if age <= 36:
        return 35

    if age <= 48:
        return 15

    return 0


# ============================================================
# FRESHNESS LABEL
# ============================================================

def freshness_label(
    published
):

    dt = parse_date(
        published
    )

    if dt is None:
        return "UNKNOWN"

    now = datetime.now(
        timezone.utc
    )

    age = (
        now - dt
    ).total_seconds() / 3600

    if age <= 24:
        return "TODAY"

    if age <= 48:
        return "RECENT"

    return "OLD"


# ============================================================
# RELEVANCE
# ============================================================

def relevance_score(
    title,
    description
):

    text = (
        f"{title} {description}"
    ).lower()

    score = 0

    for county in COUNTIES:

        if county.lower() in text:
            score += 12

    regional_terms = [
        "rift valley",
        "eldoret",
        "nakuru",
        "narok",
        "kericho",
        "bomet",
        "nandi",
        "turkana",
        "pokot",
        "samburu",
        "laikipia",
        "kajiado",
        "trans nzoia",
        "marakwet",
    ]

    for term in regional_terms:

        if term in text:
            score += 5

    return min(
        score,
        50
    )


# ============================================================
# STORY ID
# ============================================================

def story_id(
    title,
    url
):

    raw = (
        title
        + "|"
        + url
    ).encode(
        "utf-8"
    )

    return hashlib.sha1(
        raw
    ).hexdigest()[:12]


# ============================================================
# NORMALIZE STORY
# ============================================================

def normalize_story(
    item
):

    title = clean_title(
        item.get("title")
    )

    description = clean_text(
        item.get("description")
    )

    source = clean_text(
        item.get("source")
    )

    url = clean_text(
        item.get("url")
    )

    published = clean_text(
        item.get("published")
    )

    county = detect_county(
        title,
        description
    )

    category = detect_category(
        title,
        description
    )

    currentness = freshness_label(
        published
    )

    freshness = freshness_score(
        published
    )

    relevance = relevance_score(
        title,
        description
    )

    politics = political_score(
        title,
        description
    )

    source_points = source_score(
        source
    )

    score = (
        freshness
        + relevance
        + politics
        + source_points
    )

    return {

        "title": title,

        "county": (
            county
            if county
            else "Rift Valley"
        ),

        "category": category,

        "description": description,

        "source": source,

        "url": url,

        "published": published,

        "currentness": currentness,

        "freshness_score": freshness,

        "relevance_score": relevance,

        "political_score": politics,

       
