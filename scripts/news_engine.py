# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V8_REAL_PHOTO_LOCK
#
# PURPOSE
# - Fetch fresh Rift Valley news at runtime
# - Prioritize today's/recent news
# - Cover the wider Rift Valley
# - Prioritize politics + major regional developments
# - Exclude Rigathi Gachagua
# - Exclude Citizen / Citizen Digital / Citizen TV
# - Reject Google/Bing/search-result images
# - Find REAL article photographs
# - Validate image bytes with PIL
# - Normalize accepted photographs to real JPEG files
# - Download multiple UNIQUE article photographs when available
# - Reject avatars/placeholders/logos/banners/social images
# - Continue to another story when one publisher blocks images
# - Create data/story.json
# - Create data/script.json
#
# OUTPUT
#   data/story.json
#   data/script.json
#   assets/source/story_1_image.jpg
#   assets/source/story_1_image_2.jpg
#   ...
#
# COMPATIBILITY
#   rift_valley_main.py
#   rift_valley_video_generator.py
# ============================================================

from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, quote
import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET

import requests
from PIL import Image


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

MIN_IMAGE_BYTES = 10000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024

REQUEST_TIMEOUT = 25
IMAGE_TIMEOUT = 30

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
    "Cache-Control": "no-cache",
}

IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "image/avif,image/webp,image/apng,"
        "image/jpeg,image/png,image/*,*/*;q=0.8"
    ),
    "Cache-Control": "no-cache",
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
        "longisa",
        "sigor",
        "chebunyo",
        "kaplong",
    ],
    "kericho": [
        "kericho",
        "litein",
        "bureti",
        "belgut",
        "ainamoi",
        "kipkelion",
        "kapsoit",
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
        "njoro",
    ],
    "narok": [
        "narok",
        "kilgoris",
        "transmara",
        "ololulunga",
        "suswa",
        "mara",
        "olkiramatian",
    ],
    "nandi": [
        "nandi",
        "kapsabet",
        "mosoriot",
        "aldai",
        "chesumei",
        "emgwen",
        "nandi hills",
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
    "Bomet politics today",
    "Bomet development today",

    "Kericho latest news today",
    "Kericho politics today",
    "Kericho development today",

    "Nakuru latest news today",
    "Nakuru politics today",
    "Nakuru development today",

    "Narok latest news today",
    "Narok politics today",
    "Narok development today",

    "Nandi latest news today",
    "Nandi politics today",
    "Nandi development today",

    "Uasin Gishu latest news today",
    "Eldoret latest news today",
    "Uasin Gishu politics today",

    "Elgeyo Marakwet latest news today",
    "Elgeyo Marakwet politics today",

    "West Pokot latest news today",
    "West Pokot politics today",

    "Trans Nzoia latest news today",
    "Trans Nzoia politics today",

    "Samburu latest news today",
    "Samburu politics today",

    "Turkana latest news today",
    "Turkana politics today",

    "Laikipia latest news today",
    "Laikipia politics today",

    "Kajiado latest news today",
    "Kajiado politics today",

    "Kenya Rift Valley governor latest",
    "Kenya Rift Valley MP latest",
    "Kenya Rift Valley roads projects",
    "Kenya Rift Valley agriculture latest",
    "Kenya Rift Valley investment latest",
]


# ============================================================
# TRUSTED SOURCES
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
# FORBIDDEN STORY CONTENT
# ============================================================

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


FORBIDDEN_SOURCE_TERMS = [
    "citizen digital",
    "citizen tv",
    "citizen",
]


# ============================================================
# FORBIDDEN IMAGE CONTENT
#
# IMPORTANT:
# These are applied to both the IMAGE URL and LOCAL PATH.
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizen-digital",
    "citizen_digital",
    "citizen-tv",
    "citizen_tv",
    "citizentv",

    "world-cup",
    "worldcup",
    "world_cup",

    "avatar",
    "avatars",

    "placeholder",
    "place-holder",
    "default-image",
    "default_image",
    "default-image",
    "defaultimage",

    "profile",
    "profile-picture",
    "profile_picture",
    "profilephoto",
    "profile-photo",

    "generic",
    "dummy",

    "logo",
    "logos",

    "sprite",
    "favicon",
    "icon",
    "icons",

    "advert",
    "advertisement",
    "advertising",
    "ads",

    "banner",

    "facebook",
    "twitter",
    "instagram",
    "youtube",
    "whatsapp",

    "author",
    "author-image",
    "author_image",
    "authorphoto",
    "author-photo",

    "share-image",
    "share_image",
]


# ============================================================
# SEARCH-ENGINE / SCREENSHOT REJECTION
# ============================================================

SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "www.google.com",
    "news.google.com",
    "images.google.com",
    "googleusercontent.com",
    "gstatic.com",

    "bing.com",
    "www.bing.com",

    "search.yahoo.com",
    "yahoo.com",

    "duckduckgo.com",
    "www.duckduckgo.com",

    "search.brave.com",
    "brave.com",
}


SEARCH_ENGINE_PATH_TERMS = [
    "/search",
    "/images/search",
    "/imghp",
    "/imgres",
    "/results",
    "/serp",
    "search?",
    "q=",
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
        "governorship",
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
        "parties",
        "ruto",
        "president",
        "deputy president",
        "minister",
        "cabinet",
        "government",
        "politician",
        "politicians",
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
        "initiative",
        "development plan",
    ],

    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "bridges",
        "railway",
        "rail",
        "airport",
        "water",
        "dam",
        "electricity",
        "power",
        "infrastructure",
        "sewer",
        "housing",
    ],

    "BUSINESS & ECONOMY": [
        "business",
        "economy",
        "economic",
        "investment",
        "investor",
        "investors",
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
        "enterprise",
        "revenue",
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
        "horticulture",
        "pastoral",
        "pastoralist",
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
        "healthcare",
        "maternal",
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
        "learning",
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
        "bandit",
        "bandits",
    ],
}


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# HTTP GET
# ============================================================

def http_get(
    url,
    timeout=REQUEST_TIMEOUT,
    headers=None,
):
    try:
        request_headers = HEADERS.copy()

        if headers:
            request_headers.update(headers)

        response = SESSION.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=request_headers,
        )

        response.raise_for_status()

        return response

    except Exception as exc:
        print(
            "[NEWS] Request failed: "
            f"{url} -> {exc}"
        )
        return None


# ============================================================
# TEXT
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


# ============================================================
# TITLE CLEANING
# ============================================================

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

    for term in FORBIDDEN_TERMS:
        if term in lowered:
            return True

    return False


def forbidden_source(source_name):
    lowered = clean_text(source_name).lower()

    for term in FORBIDDEN_SOURCE_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# IMAGE URL SAFETY
# ============================================================

def is_search_engine_url(url):
    if not url:
        return True

    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":")[0]
        path = (parsed.path or "").lower()
        query = (parsed.query or "").lower()

        if host in SEARCH_ENGINE_DOMAINS:
            return True

        if host.endswith(".google.com"):
            return True

        if host.endswith(".googleusercontent.com"):
            return True

        if host.endswith(".gstatic.com"):
            return True

        for term in SEARCH_ENGINE_PATH_TERMS:
            if term in path or term in query:
                return True

    except Exception:
        return True

    return False


def forbidden_image_url(url):
    lowered = clean_text(url).lower()

    if is_search_engine_url(url):
        return True

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# LOCAL IMAGE SAFETY
# ============================================================

def forbidden_local_image_path(path):
    lowered = clean_text(path).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):
    if not value:
        return None

    text = clean_text(value)

    try:
        normalized = text.replace(
            "Z",
            "+00:00",
        )

        dt = datetime.fromisoformat(normalized)

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
        "%a, %d %b %Y %H:%M GMT",
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

            return dt.astimezone(
                timezone.utc
            )

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

    response = http_get(
        url,
        timeout=REQUEST_TIMEOUT,
    )

    if response is None:
        return []

    xml_text = response.text
    results = []

    try:
        root = ET.fromstring(xml_text)

        for item in root.findall(".//item"):
            title = ""
            link = ""
            pub_date = ""
            source_name = ""
            description = ""
            rss_image_urls = []

            node = item.find("title")
            if node is not None:
                title = clean_title(
                    node.text or ""
                )

            node = item.find("link")
            if node is not None:
                link = clean_text(
                    node.text or ""
                )

            node = item.find("pubDate")
            if node is not None:
                pub_date = clean_text(
                    node.text or ""
                )

            node = item.find("source")
            if node is not None:
                source_name = clean_text(
                    node.text or ""
                )

            node = item.find("description")
            if node is not None:
                description = clean_text(
                    node.text or ""
                )

            for child in list(item):
                tag = child.tag

                if not isinstance(tag, str):
                    continue

                lowered_tag = tag.lower()

                if (
                    "content" in lowered_tag
                    or "thumbnail" in lowered_tag
                ):
                    image_url = child.attrib.get(
                        "url",
                        "",
                    )

                    if image_url:
                        rss_image_urls.append(
                            image_url
                        )

                if lowered_tag.endswith("enclosure"):
                    image_url = child.attrib.get(
                        "url",
                        "",
                    )

                    item_type = child.attrib.get(
                        "type",
                        "",
                    ).lower()

                    if (
                        image_url
                        and (
                            "image" in item_type
                            or not item_type
                        )
                    ):
                        rss_image_urls.append(
                            image_url
                        )

            if title and link:
                results.append(
                    {
                        "title": title,
                        "url": link,
                        "date_raw": pub_date,
                        "source_name": source_name,
                        "description": description,
                        "query": query,
                        "rss_image_urls": rss_image_urls,
                    }
                )

        if results:
            return results

    except Exception as exc:
        print(
            "[NEWS] XML parser warning: "
            f"{exc}"
        )

    items = re.findall(
        r"<item>(.*?)</item>",
        xml_text,
        flags=re.I | re.S,
    )

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

        if not title_match or not link_match:
            continue

        rss_image_urls = re.findall(
            r'(?:url|href)=["\']([^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)["\']',
            item,
            flags=re.I,
        )

        results.append(
            {
                "title": clean_title(
                    title_match.group(1)
                ),
                "url": clean_text(
                    link_match.group(1)
                ),
                "date_raw": (
                    clean_text(
                        pub_match.group(1)
                    )
                    if pub_match
                    else ""
                ),
                "source_name": (
                    clean_text(
                        source_match.group(1)
                    )
                    if source_match
                    else ""
                ),
                "description": (
                    clean_text(
                        description_match.group(1)
                    )
                    if description_match
                    else ""
                ),
                "query": query,
                "rss_image_urls": rss_image_urls,
            }
        )

    return results


# ============================================================
# URL HELPERS
# ============================================================

def absolute_url(
    base_url,
    image_url,
):
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


# ============================================================
# HTML IMAGE EXTRACTION
# ============================================================

def extract_meta_images(
    page_url,
    html_text,
):
    images = []

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+itemprop=["\']image["\']',
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


# ============================================================
# JSON-LD IMAGE EXTRACTION
# ============================================================

def extract_json_ld_images(
    page_url,
    html_text,
):
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

        if not block:
            continue

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
                image = absolute_url(
                    page_url,
                    image_value,
                )

                if image:
                    images.append(image)

            elif isinstance(image_value, list):
                for item in image_value:
                    if isinstance(item, str):
                        image = absolute_url(
                            page_url,
                            item,
                        )

                        if image:
                            images.append(image)

                    elif isinstance(item, dict):
                        image_value_url = (
                            item.get("url")
                            or item.get("contentUrl")
                        )

                        if image_value_url:
                            image = absolute_url(
                                page_url,
                                image_value_url,
                            )

                            if image:
                                images.append(image)

            elif isinstance(image_value, dict):
                image_value_url = (
                    image_value.get("url")
                    or image_value.get("contentUrl")
                )

                if image_value_url:
                    image = absolute_url(
                        page_url,
                        image_value_url,
                    )

                    if image:
                        images.append(image)

    return images


# ============================================================
# HTML IMG EXTRACTION
# ============================================================

def extract_article_img_urls(
    page_url,
    html_text,
):
    images = []

    patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)["\']',
        r'<img[^>]+data-original=["\']([^"\']+)["\']',
        r'<img[^>]+data-image=["\']([^"\']+)["\']',
        r'<img[^>]+data-url=["\']([^"\']+)["\']',
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

    srcsets = re.findall(
        r'<img[^>]+srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in srcsets:
        for entry in srcset.split(","):
            value = entry.strip()

            if not value:
                continue

            value = value.split(" ")[0].strip()

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    lazy_srcsets = re.findall(
        r'<img[^>]+data-srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in lazy_srcsets:
        for entry in srcset.split(","):
            value = entry.strip()

            if not value:
                continue

            value = value.split(" ")[0].strip()

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    source_urls = re.findall(
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in source_urls:
        for entry in srcset.split(","):
            value = entry.strip()

            if not value:
                continue

            value = value.split(" ")[0].strip()

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    return images


# ============================================================
# GENERIC URL IMAGE EXTRACTION
# ============================================================

def extract_image_urls_from_html(
