# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V7_REAL_PHOTO_RECOVERY
#
# PURPOSE
# - Fetch fresh Rift Valley news at runtime
# - Prioritize today's/recent news
# - Cover the wider Rift Valley
# - Prioritize politics + major regional developments
# - Exclude Rigathi Gachagua
# - Exclude Citizen / Citizen Digital / Citizen TV
# - Find REAL article photographs using multiple methods
# - Download multiple unique article photographs when available
# - Never use avatars/placeholders/logos as article photos
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
        "image/svg+xml,image/*,*/*;q=0.8"
    ),
    "Referer": "https://news.google.com/",
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
        "litein",
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
        "buru",
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
# FORBIDDEN CONTENT
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
    "citizen_digital",
    "citizen-tv",
    "citizen_tv",
    "citizentv",

    "world-cup",
    "worldcup",

    "avatar",
    "avatars",

    "placeholder",
    "default-image",
    "default_image",
    "default",

    "profile",
    "profile-picture",
    "profile_picture",

    "generic",

    "logo",
    "logos",

    "sprite",
    "favicon",
    "icon",

    "advert",
    "advertisement",
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

SESSION.headers.update(
    HEADERS
)


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
            request_headers.update(
                headers
            )

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

    text = html.unescape(
        str(value)
    )

    text = text.replace(
        "\r",
        " ",
    )

    text = text.replace(
        "\n",
        " ",
    )

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
    title = clean_text(
        title
    )

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

    return clean_text(
        title
    )


# ============================================================
# FORBIDDEN CHECKS
# ============================================================

def contains_forbidden_text(text):
    lowered = clean_text(
        text
    ).lower()

    for term in FORBIDDEN_TERMS:
        if term in lowered:
            return True

    return False


def forbidden_source(source_name):
    lowered = clean_text(
        source_name
    ).lower()

    for term in FORBIDDEN_SOURCE_TERMS:
        if term in lowered:
            return True

    return False


def forbidden_image_url(url):
    lowered = clean_text(
        url
    ).lower()

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

    text = clean_text(
        value
    )

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

        return dt.astimezone(
            timezone.utc
        )

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
    encoded = quote(
        query
    )

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

    # --------------------------------------------------------
    # Primary XML parser.
    # --------------------------------------------------------

    try:
        root = ET.fromstring(
            xml_text
        )

        for item in root.findall(
            ".//item"
        ):
            title = ""

            link = ""

            pub_date = ""

            source_name = ""

            description = ""

            rss_image_urls = []

            title_node = item.find(
                "title"
            )

            if title_node is not None:
                title = clean_title(
                    title_node.text or ""
                )

            link_node = item.find(
                "link"
            )

            if link_node is not None:
                link = clean_text(
                    link_node.text or ""
                )

            pub_node = item.find(
                "pubDate"
            )

            if pub_node is not None:
                pub_date = clean_text(
                    pub_node.text or ""
                )

            source_node = item.find(
                "source"
            )

            if source_node is not None:
                source_name = clean_text(
                    source_node.text or ""
                )

            description_node = item.find(
                "description"
            )

            if description_node is not None:
                description = clean_text(
                    description_node.text or ""
                )

            # ------------------------------------------------
            # RSS media namespace.
            # ------------------------------------------------

            for child in list(item):
                tag = child.tag

                if not isinstance(
                    tag,
                    str,
                ):
                    continue

                lowered_tag = tag.lower()

                if (
                    "content" in lowered_tag
                    or "thumbnail" in lowered_tag
                ):
                    image_url = (
                        child.attrib.get(
                            "url",
                            "",
                        )
                    )

                    if image_url:
                        rss_image_urls.append(
                            image_url
                        )

                if (
                    lowered_tag.endswith(
                        "enclosure"
                    )
                ):
                    image_url = (
                        child.attrib.get(
                            "url",
                            "",
                        )
                    )

                    item_type = (
                        child.attrib.get(
                            "type",
                            "",
                        )
                        .lower()
                    )

                    if (
                        image_url
                        and (
                            "image"
                            in item_type
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
            "[NEWS] XML RSS parser warning: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # Fallback regex parser.
    # --------------------------------------------------------

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
            r"(?:url|href)=['\"]([^'\"]+\.(?:jpg|jpeg|png|webp)(?:\?[^'\"]*)?)['\"]",
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
        clean_text(
            image_url
        )
    )

    image_url = image_url.strip(
        "\"' "
    )

    if image_url.startswith(
        "//"
    ):
        parsed = urlparse(
            base_url
        )

        return (
            f"{parsed.scheme}:"
            f"{image_url}"
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
        # OpenGraph.
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        # Twitter.
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        # Other common image metadata.
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
                images.append(
                    image
                )

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
            data = json.loads(
                block
            )

        except Exception:
            # Some publishers include invalid JSON-LD.
            continue

        objects = []

        if isinstance(
            data,
            dict,
        ):
            objects.append(
                data
            )

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list,
            ):
                objects.extend(
                    graph
                )

        elif isinstance(
            data,
            list,
        ):
            objects.extend(
                data
            )

        for obj in objects:
            if not isinstance(
                obj,
                dict,
            ):
                continue

            image_value = obj.get(
                "image"
            )

            if isinstance(
                image_value,
                str,
            ):
                image = absolute_url(
                    page_url,
                    image_value,
                )

                if image:
                    images.append(
                        image
                    )

            elif isinstance(
                image_value,
                list,
            ):
                for item in image_value:
                    if isinstance(
                        item,
                        str,
                    ):
                        image = absolute_url(
                            page_url,
                            item,
                        )

                        if image:
                            images.append(
                                image
                            )

                    elif isinstance(
                        item,
                        dict,
                    ):
                        image_value_url = (
                            item.get(
                                "url"
                            )
                            or item.get(
                                "contentUrl"
                            )
                        )

                        if image_value_url:
                            image = absolute_url(
                                page_url,
                                image_value_url,
                            )

                            if image:
                                images.append(
                                    image
                                )

            elif isinstance(
                image_value,
                dict,
            ):
                image_value_url = (
                    image_value.get(
                        "url"
                    )
                    or image_value.get(
                        "contentUrl"
                    )
                )

                if image_value_url:
                    image = absolute_url(
                        page_url,
                        image_value_url,
                    )

                    if image:
                        images.append(
                            image
                        )

    return images


# ============================================================
# HTML IMAGE TAG EXTRACTION
# ============================================================

def extract_article_img_urls(
    page_url,
    html_text,
):
    images = []

    # --------------------------------------------------------
    # Standard src/data-src/lazy attributes.
    # --------------------------------------------------------

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
                images.append(
                    image
                )

    # --------------------------------------------------------
    # srcset.
    # --------------------------------------------------------

    srcsets = re.findall(
        r'<img[^>]+srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in srcsets:
        entries = srcset.split(
            ","
        )

        for entry in entries:
            value = entry.strip()

            if not value:
                continue

            value = value.split(
                " "
            )[0].strip()

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    # --------------------------------------------------------
    # Lazy srcset.
    # --------------------------------------------------------

    lazy_srcsets = re.findall(
        r'<img[^>]+data-srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in lazy_srcsets:
        entries = srcset.split(
            ","
        )

        for entry in entries:
            value = entry.strip()

            if not value:
                continue

            value = value.split(
                " "
            )[0].strip()

            if value:
                images.append(
                    absolute_url(
                        page_url,
                        value,
                    )
                )

    # --------------------------------------------------------
    # Picture/source elements.
    # --------------------------------------------------------

    source_urls = re.findall(
        r'<source[^>]+srcset=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )

    for srcset in source_urls:
        entries = srcset.split(
            ","
        )

        for entry in entries:
            value = entry.strip()

            if not value:
                continue

            value = value.split(
                " "
            )[0].strip()

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
    page_url,
    html_text,
):
    images = []

    # Find absolute image URLs embedded anywhere
    # in the article HTML.
    matches = re.findall(
        r'https?://[^"\'>\s)]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'>\s)]*)?',
        html_text,
        flags=re.I,
    )

    for match in matches:
        image = absolute_url(
            page_url,
            match,
        )

        if image:
            images.append(
                image
            )

    return images


# ============================================================
# IMAGE URL SCORING
# ============================================================

def image_candidate_score(url):
    lowered = clean_text(
        url
    ).lower()

    score = 0

    strong_positive = [
        "article",
        "articles",
        "news",
        "upload",
        "uploads",
        "media",
        "images",
        "image",
        "photo",
        "photos",
        "content",
        "wp-content",
        "wp-content/uploads",
        "featured",
        "feature",
        "story",
    ]

    weak_positive = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]

    negative = [
        "logo",
        "logos",
        "icon",
        "icons",
        "favicon",
        "sprite",
        "avatar",
        "profile",
        "placeholder",
        "default",
        "banner",
        "advert",
        "advertisement",
        "/ads/",
        "facebook",
        "twitter",
        "instagram",
        "youtube",
        "whatsapp",
        "worldcup",
        "world-cup",
        "author",
        "share",
    ]

    for term in strong_positive:
        if term in lowered:
            score += 4

    for term in weak_positive:
        if term in lowered:
            score += 2

    for term in negative:
        if term in lowered:
            score -= 30

    if forbidden_image_url(
        url
    ):
        score -= 100

    # Prefer URLs that look like actual photographs.
    if re.search(
        r"\.(jpg|jpeg|png|webp)(\?|$)",
        lowered,
    ):
        score += 5

    return score


# ============================================================
# CANDIDATE DEDUPLICATION
# ============================================================

def dedupe_image_urls(
    urls,
    base_url="",
):
    unique = []

    seen = set()

    for raw_url in urls:
        if not raw_url:
            continue

        url = absolute_url(
            base_url,
            raw_url,
        )

        url = clean_text(
            url
        )

        if not url:
            continue

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        if forbidden_image_url(
            url
        ):
            continue

        # Strip tracking parameters for duplicate detection.
        normalized = url.split(
            "?"
        )[0].lower()

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        unique.append(
            url
        )

    unique.sort(
        key=image_candidate_score,
        reverse=True,
    )

    return unique


# ============================================================
# ARTICLE IMAGE DISCOVERY
# ============================================================

def find_article_images(
    article_url,
    rss_image_urls=None,
):
    candidates = []

    # --------------------------------------------------------
    # First: images already supplied by Google News RSS.
    # --------------------------------------------------------

    if isinstance(
        rss_image_urls,
        list,
    ):
        candidates.extend(
            rss_image_urls
        )

    # --------------------------------------------------------
    # Fetch article itself.
    # --------------------------------------------------------

    response = http_get(
        article_url,
        timeout=REQUEST_TIMEOUT,
    )

    if response is not None:
        page = response.text

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

        candidates.extend(
            extract_image_urls_from_html(
                article_url,
                page,
            )
        )

    candidates = dedupe_image_urls(
        candidates,
        article_url,
    )

    print(
        "[NEWS] Image candidates found: "
        f"{len(candidates)}"
    )

    return candidates[:50]


# ============================================================
# IMAGE CONTENT VALIDATION
# ============================================================

def validate_image_file(
    path
):
    try:
        from PIL import Image

        if not path.exists():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(
            path
        ) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            # Verify the image can actually be loaded.
            image.verify()

        return True

    except Exception:
        return False


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    url,
    destination,
    referer="",
):
    if not url:
        return False

    if forbidden_image_url(
        url
    ):
        return False

    headers = IMAGE_HEADERS.copy()

    if referer:
        headers["Referer"] = referer

    try:
        response = SESSION.get(
            url,
            timeout=IMAGE_TIMEOUT,
            allow_redirects=True,
            stream=True,
            headers=headers,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        # Some servers incorrectly return
        # application/octet-stream for images,
        # so don't reject solely on content type.
        allowed_type = (
            "image" in content_type
            or "octet-stream"
            in content_type
            or not content_type
        )

        if not allowed_type:
            return False

        temporary = destination.with_suffix(
            ".download"
        )

        with temporary.open(
            "wb"
        ) as handle:
            total = 0

            for chunk in response.iter_content(
                chunk_size=65536
            ):
                if not chunk:
                    continue

                handle.write(
                    chunk
                )

                total += len(
                    chunk
                )

                # Prevent pathological downloads.
                if total > 25 * 1024 * 1024:
                    break

        if not temporary.exists():
            return False

        if temporary.stat().st_size < MIN_IMAGE_BYTES:
            temporary.unlink(
                missing_ok=True
            )

            return False

        if not validate_image_file(
            temporary
        ):
            temporary.unlink(
                missing_ok=True
            )

            return False

        temporary.replace(
            destination
        )

        return True

    except Exception as exc:
        try:
            temporary = destination.with_suffix(
                ".download"
            )

            temporary.unlink(
                missing_ok=True
            )

        except Exception:
            pass

        print(
            "[NEWS] Image failed: "
            f"{url} -> {exc}"
        )

        return False


# ============================================================
# FILE SIGNATURE
# ============================================================

def file_signature(
    path
):
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

                digest.update(
                    chunk
                )

        return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# DOWNLOAD MULTIPLE ARTICLE PHOTOS
# ============================================================

def download_story_images(
    story,
    story_number,
):
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    article_url = clean_text(
        story.get(
            "article_url"
        )
    )

    if not article_url:
        article_url = clean_text(
            story.get(
                "source",
                {}
            ).get(
                "url",
                ""
            )
        )

    if not article_url:
        return []

    rss_image_urls = story.get(
        "rss_image_urls",
        [],
    )

    image_urls = find_article_images(
        article_url,
        rss_image_urls,
    )

    if not image_urls:
        print(
            "[NEWS] No image candidates: "
            f"{story.get('title')}"
        )

        return []

    downloaded = []

    signatures = set()

    for candidate_number, image_url in enumerate(
        image_urls,
        start=1,
    ):
        if len(downloaded) >= MAX_IMAGES_PER_STORY:
            break

        if forbidden_image_url(
            image_url
        ):
            continue

        # ----------------------------------------------------
        # Always save as JPG after validation through PIL.
        # The renderer supports JPG reliably.
        # ----------------------------------------------------

        if len(downloaded) == 0:
            filename = (
                f"story_{story_number}_image.jpg"
            )

        else:
            filename = (
                f"story_{story_number}_image_"
                f"{len(downloaded) + 1}.jpg"
            )

        destination = (
            SOURCE_DIR / filename
        )

        print(
            "[NEWS] Trying image "
            f"{candidate_number}/"
            f"{len(image_urls)}: "
            f"{image_url}"
        )

        success = download_image(
            image_url,
            destination,
            referer=article_url,
        )

        if not success:
            continue

        signature = file_signature(
            destination
        )

        if (
            signature
            and signature in signatures
        ):
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
                "file": destination.name,
                "url": image_url,
            }
        )

        print(
            "[NEWS] REAL PHOTO ACCEPTED: "
            f"{destination.name}"
        )

    return downloaded


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(
    text
):
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

def detect_category(
    text
):
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

def source_score(
    source_name
):
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

def political_score(
    text
):
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
# FRESHNESS SCORE
# ============================================================

def freshness_score(
    dt
):
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

    if hours <= 24:
        return 40

    if hours <= 72:
        return 25

    if hours <= 168:
        return 10

    return 0


# ============================================================
# RELEVANCE SCORE
# ============================================================

def relevance_score(
    item
):
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

    if forbidden_source(
        source
    ):
        return -1000

    county = detect_county(
        combined
    )

    category = detect_category(
        combined
    )

    score = 0

    if county:
        score += 35

    if "rift valley" in combined.lower():
        score += 25

    score += source_score(
        source
    )

    dt = parse_date(
        item.get("date_raw")
    )

    score += freshness_score(
        dt
    )

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

    score += min(
        political_score(
            combined
        ) * 2,
        12,
    )

    if len(title) >= 35:
        score += 5

    if len(description) >= 80:
        score += 5

    return score


# ============================================================
# STORY ID
# ============================================================

def story_id(
    item
):
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

def normalize_story(
    item
):
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
        "id": story_id(
            item
        ),
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
                    or "state department"
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

        "rss_image_urls": item.get(
            "rss_image_urls",
            [],
        ),

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

def deduplicate(
    items
):
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

        if (
            url
            and url in seen_urls
        ):
            continue

        if (
            title
            and title in seen_titles
        ):
            continue

        if url:
            seen_urls.add(
                url
            )

        if title:
            seen_titles.add(
                title
            )

        unique.append(
            item
        )

    return unique


# ============================================================
# DIVERSE SELECTION
# ============================================================

def select_diverse_stories(
    items
):
    ranked = sorted(
        items,
        key=relevance_score,
        reverse=True,
    )

    selected = []

    counties_seen = set()

    categories_seen = set()

    # --------------------------------------------------------
    # First pass: regional diversity.
    # --------------------------------------------------------

    for item in ranked:
        if len(selected) >= MAX_STORIES:
            break

        text = (
            f"{item.get('title', '')} "
            f"{item.get('description', '')}"
        )

        county = detect_county(
            text
        )

        category = detect_category(
            text
        )

        if (
            county
            and county.lower()
            in counties_seen
            and category
            and category in categories_seen
        ):
            continue

        selected.append(
            item
        )

        if county:
            counties_seen.add(
                county.lower()
            )

        if category:
            categories_seen.add(
                category
            )

    # --------------------------------------------------------
    # Second pass: fill remaining positions.
    # --------------------------------------------------------

    if len(selected) < MAX_STORIES:
        selected_ids = {
            story_id(item)
            for item in selected
        }

        for item in ranked:
            if len(selected) >= MAX_STORIES:
                break

            if story_id(
                item
            ) in selected_ids:
                continue

            selected.append(
                item
            )

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story
):
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

    source = story.get(
        "source",
        {},
    )

    if not isinstance(
        source,
        dict,
    ):
        source = {}

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

    narration = clean_text(
        " ".join(
            parts
        )
    )

    if contains_forbidden_text(
        narration
    ):
        return ""

    return narration


# ============================================================
# VISUAL METADATA
# ============================================================

def build_visuals(
    story
):
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

    if isinstance(
        images,
        list,
    ):
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

    if isinstance(
        source,
        dict,
    ):
        source_name = clean_text(
            source.get("name")
        )

        if (
            source_name
            and not forbidden_source(
                source_name
            )
        ):
            visuals.append(
                {
                    "type": "SOURCE_CARD",
                    "description": source_name,
                }
            )

    return visuals


# ============================================================
# JSON SAVE
# ============================================================

def save_json(
    path,
    data,
):
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

    temporary.replace(
        path
    )


# ============================================================
# STORY JSON
# ============================================================

def write_story_json(
    stories
):
    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "region": (
            "Rift Valley, Kenya"
        ),

        "story_count": len(
            stories
        ),

        "stories": stories,
    }

    save_json(
        STORY_FILE,
        payload,
    )

    print(
        f"[NEWS] Wrote: "
        f"{STORY_FILE}"
    )


# ============================================================
# SCRIPT JSON
# ============================================================

def write_script_json(
    stories
):
    scripts = []

    for story in stories:
        narration = build_narration(
            story
        )

        scripts.append(
            {
                "id": story.get(
                    "id",
                    "",
                ),

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
        f"[NEWS] Wrote: "
        f"{SCRIPT_FILE}"
    )


# ============================================================
# CLEAN OLD IMAGES
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
            ".download",
        }:
            continue

        try:
            path.unlink()

        except Exception as exc:
            print(
                "[NEWS] Could not remove "
                f"{path}: {exc}"
            )


# ============================================================
# COLLECT NEWS
# ============================================================

def collect_news():
    print()
    print(
        "=" * 72
    )
    print(
        "RIFT VALLEY WATCH"
    )
    print(
        "REAL-TIME NEWS ENGINE V7"
    )
    print(
        "REAL PHOTO RECOVERY"
    )
    print(
        "=" * 72
    )

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
    # FETCH NEWS
    # --------------------------------------------------------

    total_queries = len(
        SEARCH_QUERIES
    )

    for number, query in enumerate(
        SEARCH_QUERIES,
        start=1,
    ):
        print()
        print(
            f"[NEWS] SEARCH "
            f"{number}/{total_queries}: "
            f"{query}"
        )

        try:
            items = fetch_google_news(
                query
            )

            all_items.extend(
                items
            )

            print(
                "[NEWS] Results returned: "
                f"{len(items)}"
            )

        except Exception as exc:
            print(
                "[NEWS] Search error: "
                f"{exc}"
            )

        time.sleep(
            0.12
        )

    print()
    print(
        "[NEWS] Raw results: "
        f"{len(all_items)}"
    )

    # --------------------------------------------------------
    # FILTER
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

        if not title:
            continue

        if not item.get(
            "url"
        ):
            continue

        if contains_forbidden_text(
            combined
        ):
            continue

        if forbidden_source(
            source
        ):
            continue

        filtered.append(
            item
        )

    print(
        "[NEWS] After content filtering: "
        f"{len(filtered)}"
    )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    filtered = deduplicate(
        filtered
    )

    print(
        "[NEWS] After deduplication: "
        f"{len(filtered)}"
    )

    # --------------------------------------------------------
    # REGIONAL RELEVANCE
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
            relevant.append(
                item
            )

    print(
        "[NEWS] Rift Valley relevant: "
        f"{len(relevant)}"
    )

    if len(relevant) < 6:
        relevant = sorted(
            filtered,
            key=relevance_score,
            reverse=True,
        )[:30]

        print(
            "[NEWS] Expanded candidate "
            "pool because regional results "
            "were limited."
        )

    # --------------------------------------------------------
    # RANK CANDIDATES
    # --------------------------------------------------------

    selected_raw = select_diverse_stories(
        relevant
    )

    print(
        "[NEWS] Initial candidates: "
        f"{len(selected_raw)}"
    )

    # --------------------------------------------------------
    # PROCESS CANDIDATES
    #
    # Do NOT fail because one publisher has no
    # accessible image. Move to the next story.
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

        if not title:
            continue

        if contains_forbidden_text(
            title
        ):
            print(
                "[NEWS] Rejected forbidden "
                f"story: {title}"
            )

            continue

        source_name = clean_text(
            story.get(
                "source",
                {}
            ).get(
                "name",
                "",
            )
        )

        if forbidden_source(
            source_name
        ):
            print(
                "[NEWS] Rejected forbidden "
                f"source: {source_name}"
            )

            continue

        print()
        print(
            "-" * 72
        )

        print(
            f"[NEWS] CANDIDATE {number}"
        )

        print(
            f"[NEWS] Title: {title}"
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
            f"{source_name}"
        )

        print(
            f"[NEWS] Article: "
            f"{story.get('article_url', '')}"
        )

        images = download_story_images(
            story,
            len(stories) + 1,
        )

        if not images:
            print(
                "[NEWS] REJECTED: "
                "No usable real article "
                "photograph could be downloaded."
            )

            continue

        # ----------------------------------------------------
        # Save image metadata.
        # ----------------------------------------------------

        story["images"] = [
            image["path"]
            for image in images
        ]

        story["image_urls"] = [
            image["url"]
            for image in images
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

        # ----------------------------------------------------
        # Confirmed editorial information.
        # ----------------------------------------------------

        story["editorial"][
            "confirmed"
        ] = []

        if source_name:
            story["editorial"][
                "confirmed"
            ].append(
                "Published by "
                f"{source_name}."
            )

        if story.get(
            "county"
        ):
            story["editorial"][
                "confirmed"
            ].append(
                "Location: "
                f"{story.get('county')}."
            )

        if story.get(
            "category"
        ):
            story["editorial"][
                "confirmed"
            ].append(
                "Category: "
                f"{story.get('category')}."
            )

        if story.get(
            "date"
        ):
            story["editorial"][
                "confirmed"
            ].append(
                "Publication date: "
                f"{story.get('date')}."
            )

        stories.append(
            story
        )

        print()
        print(
            "[NEWS] STORY ACCEPTED"
        )

        print(
            f"[NEWS] Real photographs: "
            f"{len(images)}"
        )

        # We only need enough stories to give
        # the main orchestrator a good selection.
        if len(stories) >= MAX_STORIES:
            break

    # --------------------------------------------------------
    # SECOND IMAGE RECOVERY PASS
    #
    # If the first ranked candidates failed, inspect
    # additional candidates rather than immediately
    # failing the entire workflow.
    # --------------------------------------------------------

    if len(stories) < 3:
        accepted_ids = {
            story.get(
                "id",
                "",
            )
            for story in stories
        }

        remaining = sorted(
            relevant,
            key=relevance_score,
            reverse=True,
        )

        for item in remaining:
            if len(stories) >= MAX_STORIES:
                break

            item_id = story_id(
                item
            )

            if item_id in accepted_ids:
                continue

            story = normalize_story(
                item
            )

            title = clean_text(
                story.get("title")
            )

            if not title:
                continue

            if contains_forbidden_text(
                title
            ):
                continue

            source_name = clean_text(
                story.get(
                    "source",
                    {}
                ).get(
                    "name",
                    "",
                )
            )

            if forbidden_source(
                source_name
            ):
                continue

            print()
            print(
                "[NEWS] SECOND-PASS IMAGE "
                f"RECOVERY: {title}"
            )

            images = download_story_images(
                story,
                len(stories) + 1,
            )

            if not images:
                continue

            story["images"] = [
                image["path"]
                for image in images
            ]

            story["image_urls"] = [
                image["url"]
                for image in images
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

            story["editorial"][
                "confirmed"
            ] = [
                (
                    "Published by "
                    f"{source_name}."
                )
                if source_name
                else "",
                (
                    "Location: "
                    f"{story.get('county')}."
                )
                if story.get("county")
                else "",
            ]

            story["editorial"][
                "confirmed"
            ] = [
                value
                for value in story[
                    "editorial"
                ]["confirmed"]
                if value
            ]

            stories.append(
                story
            )

            accepted_ids.add(
                item_id
            )

            print(
                "[NEWS] SECOND-PASS STORY "
                "ACCEPTED"
            )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    if not stories:
        raise RuntimeError(
            "No valid Rift Valley story "
            "with a real article photograph "
            "could be produced."
        )

    # --------------------------------------------------------
    # Make sure every story has at least
    # one valid image file.
    # --------------------------------------------------------

    final_stories = []

    for story in stories:
        valid_images = []

        for image_path in story.get(
            "images",
            [],
        ):
            candidate = (
                BASE_DIR / image_path
            )

            if validate_image_file(
                candidate
            ):
                valid_images.append(
                    image_path
                )

        if not valid_images:
            print(
                "[NEWS] Removing story with "
                "invalid final images: "
                f"{story.get('title')}"
            )

            continue

        story["images"] = valid_images

        story["image"] = valid_images[0]

        story["image_path"] = valid_images[0]

        final_stories.append(
            story
        )

    stories = final_stories

    if not stories:
        raise RuntimeError(
            "All downloaded photographs "
            "failed final image validation."
        )

    # --------------------------------------------------------
    # WRITE OUTPUTS
    # --------------------------------------------------------

    write_story_json(
        stories
    )

    write_script_json(
        stories
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print()
    print(
        "=" * 72
    )

    print(
        "NEWS ENGINE V7 COMPLETED SUCCESSFULLY"
    )

    print(
        "=" * 72
    )

    print(
        f"[NEWS] Final stories: "
        f"{len(stories)}"
    )

    total_images = 0

    for index, story in enumerate(
        stories,
        start=1,
    ):
        image_count = len(
            story.get(
                "images",
                [],
            )
        )

        total_images += image_count

        print()
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
            f"       Source: "
            f"{story.get('source', {}).get('name', '')}"
        )

        print(
            f"       Real photos: "
            f"{image_count}"
        )

        for image in story.get(
            "images",
            [],
        ):
            print(
                f"         - {image}"
            )

    print()
    print(
        f"[NEWS] Total real photographs: "
        f"{total_images}"
    )

    print(
        f"[NEWS] Story JSON: "
        f"{STORY_FILE}"
    )

    print(
        f"[NEWS] Script JSON: "
        f"{SCRIPT_FILE}"
    )

    print(
        "=" * 72
    )

    return stories


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        collect_news()

    except KeyboardInterrupt:
        print()
        print(
            "[NEWS] Interrupted."
        )

        raise SystemExit(
            130
        )

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

        raise SystemExit(
            1
        )
