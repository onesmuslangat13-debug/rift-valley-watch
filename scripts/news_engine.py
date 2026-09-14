from pathlib import Path
import json
import re
import html
import hashlib
import time
import shutil
import sys
from urllib.parse import urljoin, urlparse, quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET

from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V11_STABLE_NO_BS4
#
# PURPOSE
# - Fetch fresh Rift Valley news
# - Cover multiple Rift Valley counties
# - Prefer today's/recent stories
# - Download REAL article photographs
# - Reject Google/Bing/search screenshots
# - Reject logos, avatars, placeholders and generic graphics
# - Create data/story.json
# - Create data/script.json
# - Compatible with rift_valley_main.py
#
# DEPENDENCIES
# - Python standard library
# - requests is NOT required
# - bs4 is NOT required
# - Pillow
# ============================================================


VERSION = "RVW_NEWS_ENGINE_V11_STABLE_NO_BS4"


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_JSON = DATA_DIR / "story.json"
SCRIPT_JSON = DATA_DIR / "script.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SETTINGS
# ============================================================

MAX_STORIES = 12
MAX_IMAGES_PER_STORY = 6

MIN_IMAGE_BYTES = 6000
MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250

REQUEST_TIMEOUT = 20
IMAGE_TIMEOUT = 30

MAX_ARTICLE_BYTES = 5_000_000
MAX_IMAGE_BYTES = 15_000_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36 "
    "RiftValleyWatch/11.0"
)


# ============================================================
# RIFT VALLEY COUNTIES
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
        "Konoin",
        "Chepalungu",
        "Longisa",
        "Kipkelion",
    ],
    "Kericho": [
        "Kericho",
        "Ainamoi",
        "Belgut",
        "Bureti",
        "Kipkelion",
        "Litein",
    ],
    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Bahati",
        "Rongai",
        "Njoro",
    ],
    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Aldai",
        "Emgwen",
        "Mosop",
        "Chesumei",
        "Nandi Hills",
    ],
    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Ainabkoi",
        "Kapseret",
        "Soy",
        "Moiben",
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo",
        "Marakwet",
        "Iten",
        "Keiyo",
        "Kapsowar",
        "Kabarnet",
    ],
    "West Pokot": [
        "West Pokot",
        "Pokot",
        "Kapenguria",
        "Kacheliba",
        "Sigor",
        "Pokot South",
    ],
    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Mau",
        "Transmara",
    ],
    "Trans Nzoia": [
        "Trans Nzoia",
        "Kitale",
        "Endebess",
        "Kwanza",
        "Saboti",
        "Cherangany",
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
    ],
    "Laikipia": [
        "Laikipia",
        "Nanyuki",
        "Nyahururu",
        "Rumuruti",
    ],
    "Kajiado": [
        "Kajiado",
        "Kitengela",
        "Ngong",
        "Loitokitok",
        "Isinya",
        "Namanga",
        "Kiserian",
    ],
}


# ============================================================
# FORBIDDEN STORY TERMS
# ============================================================

FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "rigathi",
    "gachagua",
]


# ============================================================
# FORBIDDEN IMAGE TERMS
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "news.google.com",
    "bing.com",
    "bingusercontent.com",
    "search.yahoo.com",
    "yahoo.com/search",
    "duckduckgo.com",
    "search-results",
    "search_results",
    "searchresult",
    "search-result",
    "google-image",
    "google_images",
    "googleimage",
    "bing-image",
    "bing_images",
    "screenshot",
    "screen-shot",
    "screen_shot",
    "citizen",
    "citizen-digital",
    "citizentv",
    "ctv",
    "world-cup",
    "worldcup",
    "avatar",
    "profile-picture",
    "profile_picture",
    "placeholder",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "missing-image",
    "missing_image",
    "generic-avatar",
    "generic_avatar",
    "dummy-image",
    "dummy_image",
    "logo",
    "favicon",
    "icon",
    "sprite",
    "banner",
    "advert",
    "advertisement",
    "ads.",
    "/ads/",
    "author",
    "share",
    "social",
]


# ============================================================
# TRUSTED / KNOWN NEWS DOMAINS
# ============================================================

SOURCE_SCORES = {
    "citizen.digital": 0,
    "nation.africa": 10,
    "standardmedia.co.ke": 10,
    "the-star.co.ke": 9,
    "peopledaily.digital": 9,
    "capitalfm.co.ke": 8,
    "kbc.co.ke": 8,
    "kenyanews.go.ke": 10,
    "capitalnews.co.ke": 8,
    "businessdailyafrica.com": 8,
    "tuko.co.ke": 5,
    "ntvkenya.co.ke": 7,
    "kenyatoday.com": 5,
    "theeastafrican.co.ke": 8,
    "kenyamoja.com": 4,
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    "Rift Valley Kenya latest news",
    "Bomet latest news Kenya",
    "Kericho latest news Kenya",
    "Nakuru latest news Kenya",
    "Nandi latest news Kenya",
    "Uasin Gishu Eldoret latest news",
    "Elgeyo Marakwet latest news",
    "West Pokot latest news",
    "Narok latest news Kenya",
    "Trans Nzoia Kitale latest news",
    "Samburu latest news Kenya",
    "Turkana latest news Kenya",
    "Laikipia latest news Kenya",
    "Kajiado latest news Kenya",
    "Rift Valley politics Kenya latest",
    "Rift Valley business Kenya latest",
    "Rift Valley development Kenya latest",
    "Rift Valley county government latest",
]


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


def error(message):
    print(f"ERROR: {message}", flush=True)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

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

    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(url, base_url=None):
    if not url:
        return ""

    url = html.unescape(str(url)).strip()

    url = url.replace("\\/", "/")

    if url.startswith("//"):
        url = "https:" + url

    if base_url:
        url = urljoin(base_url, url)

    return url


def canonical_url(url):
    try:
        parsed = urlparse(url)

        if not parsed.scheme or not parsed.netloc:
            return ""

        host = parsed.netloc.lower()

        path = parsed.path.rstrip("/")

        return f"{parsed.scheme.lower()}://{host}{path}"

    except Exception:
        return ""


def hostname(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0]
    except Exception:
        return ""


def is_http_url(url):
    try:
        scheme = urlparse(url).scheme.lower()
        return scheme in ("http", "https")
    except Exception:
        return False


# ============================================================
# FORBIDDEN CHECKS
# ============================================================

def contains_forbidden_story_term(text):
    text = clean_text(text).lower()

    for term in FORBIDDEN_STORY_TERMS:
        if term in text:
            return True

    return False


def forbidden_image_url(url):
    lower = str(url).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in lower:
            return True

    return False


# ============================================================
# HTTP
# ============================================================

def fetch_bytes(url, timeout=REQUEST_TIMEOUT, max_bytes=MAX_ARTICLE_BYTES):
    if not is_http_url(url):
        return b""

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/avif,"
                    "image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        with urlopen(request, timeout=timeout) as response:
            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return b""
                except Exception:
                    pass

            data = response.read(max_bytes + 1)

            if len(data) > max_bytes:
                return b""

            return data

    except Exception:
        return b""


def fetch_text(url):
    data = fetch_bytes(
        url,
        timeout=REQUEST_TIMEOUT,
        max_bytes=MAX_ARTICLE_BYTES,
    )

    if not data:
        return ""

    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding, errors="ignore")
        except Exception:
            pass

    return ""


# ============================================================
# RSS
# ============================================================

def google_news_rss_url(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-KE&gl=KE&ceid=KE:en"
    )


def parse_rss(xml_text):
    items = []

    if not xml_text:
        return items

    try:
        root = ET.fromstring(xml_text)

    except Exception:
        return items

    for item in root.findall(".//item"):
        title = ""

        link = ""

        description = ""

        pub_date = ""

        source_name = ""

        source_url = ""

        title_node = item.find("title")

        link_node = item.find("link")

        description_node = item.find("description")

        date_node = item.find("pubDate")

        source_node = item.find("source")

        if title_node is not None and title_node.text:
            title = clean_text(title_node.text)

        if link_node is not None and link_node.text:
            link = clean_text(link_node.text)

        if description_node is not None and description_node.text:
            description = clean_text(description_node.text)

        if date_node is not None and date_node.text:
            pub_date = clean_text(date_node.text)

        if source_node is not None:
            source_name = clean_text(source_node.text or "")

            source_url = clean_text(
                source_node.attrib.get("url", "")
            )

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "published": pub_date,
                "source_name": source_name,
                "source_url": source_url,
            }
        )

    return items


# ============================================================
# HTML EXTRACTION
# ============================================================

def extract_meta_content(page, property_name):
    pattern = re.compile(
        r'<meta\b[^>]*'
        r'(?:property|name|itemprop)\s*=\s*["\']'
        + re.escape(property_name)
        + r'["\'][^>]*'
        r'content\s*=\s*["\']([^"\']+)["\']',
        re.I,
    )

    match = pattern.search(page)

    if match:
        return html.unescape(match.group(1).strip())

    reverse_pattern = re.compile(
        r'<meta\b[^>]*'
        r'content\s*=\s*["\']([^"\']+)["\'][^>]*'
        r'(?:property|name|itemprop)\s*=\s*["\']'
        + re.escape(property_name)
        + r'["\']',
        re.I,
    )

    match = reverse_pattern.search(page)

    if match:
        return html.unescape(match.group(1).strip())

    return ""


def extract_title(page):
    value = extract_meta_content(page, "og:title")

    if value:
        return clean_text(value)

    value = extract_meta_content(page, "twitter:title")

    if value:
        return clean_text(value)

    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        page,
        flags=re.I | re.S,
    )

    if match:
        return clean_text(match.group(1))

    return ""


def extract_description(page):
    for key in [
        "og:description",
        "twitter:description",
        "description",
    ]:
        value = extract_meta_content(page, key)

        if value:
            return clean_text(value)

    return ""


def extract_canonical(page, base_url):
    match = re.search(
        r'<link\b[^>]*rel\s*=\s*["\']canonical["\'][^>]*'
        r'href\s*=\s*["\']([^"\']+)["\']',
        page,
        flags=re.I,
    )

    if match:
        return normalize_url(match.group(1), base_url)

    return ""


# ============================================================
# ARTICLE BODY
# ============================================================

def extract_article_text(page):
    candidates = []

    article_matches = re.findall(
        r"<article\b[^>]*>(.*?)</article>",
        page,
        flags=re.I | re.S,
    )

    candidates.extend(article_matches)

    main_matches = re.findall(
        r"<main\b[^>]*>(.*?)</main>",
        page,
        flags=re.I | re.S,
    )

    candidates.extend(main_matches)

    for candidate in candidates:
        text = clean_text(candidate)

        if len(text) > 200:
            paragraphs = re.split(
                r"(?<=[.!?])\s+",
                text,
            )

            paragraphs = [
                p.strip()
                for p in paragraphs
                if len(p.strip()) > 35
            ]

            text = " ".join(paragraphs[:12])

            if len(text) > 200:
                return text[:4000]

    paragraphs = re.findall(
        r"<p\b[^>]*>(.*?)</p>",
        page,
        flags=re.I | re.S,
    )

    cleaned = []

    for paragraph in paragraphs:
        text = clean_text(paragraph)

        if len(text) < 40:
            continue

        lower = text.lower()

        if any(
            word in lower
            for word in [
                "subscribe",
                "advertisement",
                "cookie",
                "sign up",
                "follow us",
            ]
        ):
            continue

        cleaned.append(text)

    return " ".join(cleaned[:15])[:4000]


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def add_unique(items, value):
    value = normalize_url(value)

    if not value:
        return

    if not is_http_url(value):
        return

    if forbidden_image_url(value):
        return

    if value not in items:
        items.append(value)


def extract_srcset(value, results):
    if not value:
        return

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        parts = item.split()

        if parts:
            add_unique(results, parts[0])


def extract_images_from_jsonld(page, results):
    scripts = re.findall(
        r'<script\b[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>'
        r'(.*?)</script>',
        page,
        flags=re.I | re.S,
    )

    for script in scripts:
        raw = html.unescape(script).strip()

        if not raw:
            continue

        try:
            data = json.loads(raw)

        except Exception:
            continue

        def walk(value):
            if isinstance(value, dict):
                for key, val in value.items():
                    key_lower = str(key).lower()

                    if key_lower in (
                        "image",
                        "images",
                        "thumbnail",
                        "thumbnailurl",
                        "contenturl",
                    ):
                        if isinstance(val, str):
                            add_unique(results, val)

                        elif isinstance(val, list):
                            for entry in val:
                                if isinstance(entry, str):
                                    add_unique(results, entry)

                                elif isinstance(entry, dict):
                                    for nested_key in (
                                        "url",
                                        "contentUrl",
                                        "thumbnailUrl",
                                    ):
                                        nested = entry.get(nested_key)

                                        if isinstance(nested, str):
                                            add_unique(
                                                results,
                                                nested,
                                            )

                    walk(val)

            elif isinstance(value, list):
                for entry in value:
                    walk(entry)

        walk(data)


def extract_image_urls(page, base_url):
    results = []

    # --------------------------------------------------------
    # META IMAGES
    # --------------------------------------------------------

    for key in [
        "og:image",
        "og:image:url",
        "og:image:secure_url",
        "twitter:image",
        "twitter:image:src",
        "image",
    ]:
        value = extract_meta_content(page, key)

        if value:
            add_unique(
                results,
                normalize_url(value, base_url),
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    extract_images_from_jsonld(
        page,
        results,
    )

    # --------------------------------------------------------
    # IMG TAGS
    # --------------------------------------------------------

    img_tags = re.findall(
        r"<img\b[^>]*>",
        page,
        flags=re.I | re.S,
    )

    for tag in img_tags:
        attributes = dict(
            re.findall(
                r'([:\w-]+)\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )
        )

        for key in [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-url",
            "data-filename",
        ]:
            value = attributes.get(key)

            if value:
                add_unique(
                    results,
                    normalize_url(value, base_url),
                )

        for key in [
            "srcset",
            "data-srcset",
        ]:
            value = attributes.get(key)

            if value:
                local_results = []

                extract_srcset(
                    value,
                    local_results,
                )

                for item in local_results:
                    add_unique(
                        results,
                        normalize_url(item, base_url),
                    )

    # --------------------------------------------------------
    # SOURCE TAGS
    # --------------------------------------------------------

    source_tags = re.findall(
        r"<source\b[^>]*>",
        page,
        flags=re.I | re.S,
    )

    for tag in source_tags:
        attributes = dict(
            re.findall(
                r'([:\w-]+)\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )
        )

        for key in [
            "src",
            "data-src",
            "srcset",
            "data-srcset",
        ]:
            value = attributes.get(key)

            if not value:
                continue

            if "srcset" in key:
                local_results = []

                extract_srcset(
                    value,
                    local_results,
                )

                for item in local_results:
                    add_unique(
                        results,
                        normalize_url(item, base_url),
                    )
            else:
                add_unique(
                    results,
                    normalize_url(value, base_url),
                )

    # --------------------------------------------------------
    # ABSOLUTE IMAGE URLS IN PAGE
    # --------------------------------------------------------

    raw_urls = re.findall(
        r'https?://[^"\'<>\s]+?\.(?:jpg|jpeg|png|webp|avif)(?:\?[^"\'<>\s]*)?',
        page,
        flags=re.I,
    )

    for value in raw_urls:
        add_unique(
            results,
            value,
        )

    return results


# ============================================================
# IMAGE URL SCORING
# ============================================================

def score_image_url(url):
    lower = url.lower()

    if forbidden_image_url(url):
        return -999

    score = 0

    positive_terms = [
        "article",
        "news",
        "upload",
        "uploads",
        "media",
        "image",
        "images",
        "photo",
        "photos",
        "content",
        "featured",
        "story",
        "wp-content",
        "wp-content/uploads",
    ]

    negative_terms = [
        "logo",
        "icon",
        "favicon",
        "avatar",
        "profile",
        "author",
        "placeholder",
        "default",
        "banner",
        "advert",
        "ads",
        "social",
        "share",
        "sprite",
    ]

    for term in positive_terms:
        if term in lower:
            score += 2

    for term in negative_terms:
        if term in lower:
            score -= 8

    extension = Path(
        urlparse(url).path
    ).suffix.lower()

    if extension in (
        ".jpg",
        ".jpeg",
        ".webp",
        ".png",
    ):
        score += 3

    return score


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_is_valid(path):
    try:
        if not path.exists():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            if width * height < 150_000:
                return False

            image.verify()

        return True

    except Exception:
        return False


def image_signature(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((80, 80))

            data = image.tobytes()

            return hashlib.sha256(data).hexdigest()

    except Exception:
        return ""


def convert_to_jpeg(source_path, target_path):
    try:
        with Image.open(source_path) as image:
            image = image.convert("RGB")

            image.thumbnail(
                (2400, 2400),
                Image.Resampling.LANCZOS,
            )

            image.save(
                target_path,
                "JPEG",
                quality=91,
                optimize=True,
            )

        if not image_is_valid(target_path):
            target_path.unlink(
                missing_ok=True
            )

            return False

        return True

    except Exception:
        target_path.unlink(
            missing_ok=True
        )

        return False


# ============================================================
# CLEAN OLD SOURCE IMAGES
# ============================================================

def clean_old_images():
    log("")
    log("=" * 68)
    log("CLEANING OLD DOWNLOADED IMAGES")
    log("=" * 68)

    extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".bmp",
        ".tif",
        ".tiff",
    }

    removed = 0

    for path in SOURCE_DIR.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in extensions:
            continue

        try:
            path.unlink()
            removed += 1
        except Exception:
            pass

    log(f"Old images removed: {removed}")


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_real_image(url, story_key, index):
    if not url:
        return ""

    if not is_http_url(url):
        return ""

    if forbidden_image_url(url):
        return ""

    source_host = hostname(url)

    if not source_host:
        return ""

    digest = hashlib.sha256(
        f"{story_key}|{index}|{url}".encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:18]

    temp_path = SOURCE_DIR / f"{digest}.download"

    final_path = SOURCE_DIR / f"{digest}.jpg"

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "image/avif,image/webp,image/apng,"
                    "image/svg+xml,image/*,*/*;q=0.8"
                ),
                "Referer": (
                    f"https://{source_host}/"
                ),
            },
        )

        with urlopen(
            request,
            timeout=IMAGE_TIMEOUT,
        ) as response:

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
                .lower()
            )

            if "text/html" in content_type:
                return ""

            data = response.read(
                MAX_IMAGE_BYTES + 1
            )

            if len(data) > MAX_IMAGE_BYTES:
                return ""

            if len(data) < MIN_IMAGE_BYTES:
                return ""

            temp_path.write_bytes(data)

        if not temp_path.exists():
            return ""

        # ----------------------------------------------------
        # PIL opens the actual bytes. This prevents mislabeled
        # WebP/PNG/AVIF files from being saved as fake JPGs.
        # ----------------------------------------------------

        if not convert_to_jpeg(
            temp_path,
            final_path,
        ):
            return ""

        temp_path.unlink(
            missing_ok=True
        )

        if not image_is_valid(final_path):
            final_path.unlink(
                missing_ok=True
            )

            return ""

        return str(
            final_path.relative_to(BASE_DIR)
        ).replace("\\", "/")

    except Exception:
        temp_path.unlink(
            missing_ok=True
        )

        final_path.unlink(
            missing_ok=True
        )

        return ""


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(title, description, article_text):
    combined = " ".join(
        [
            title or "",
            description or "",
            article_text or "",
        ]
    ).lower()

    matches = []

    for county, aliases in COUNTY_ALIASES.items():
        score = 0

        for alias in aliases:
            if alias.lower() in combined:
                score += 1

        if score:
            matches.append(
                (
                    score,
                    county,
                )
            )

    if not matches:
        return ""

    matches.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return matches[0][1]


# ============================================================
# CATEGORY
# ============================================================

def detect_category(title, description, article_text):
    text = " ".join(
        [
            title or "",
            description or "",
            article_text or "",
        ]
    ).lower()

    categories = [
        (
            "Politics",
            [
                "president",
                "mp",
                "governor",
                "senator",
                "politician",
                "political",
                "election",
                "party",
                "parliament",
                "assembly",
                "ward",
                "politics",
            ],
        ),
        (
            "Business",
            [
                "business",
                "economy",
                "investment",
                "company",
                "market",
                "trade",
                "revenue",
                "industry",
                "bank",
                "finance",
            ],
        ),
        (
            "Agriculture",
            [
                "farmer",
                "farmers",
                "agriculture",
                "tea",
                "maize",
                "livestock",
                "crop",
                "coffee",
                "milk",
                "fertilizer",
            ],
        ),
        (
            "Security",
            [
                "police",
                "arrest",
                "crime",
                "security",
                "attack",
                "murder",
                "accident",
                "robbery",
                "court",
            ],
        ),
        (
            "Development",
            [
                "road",
                "hospital",
                "school",
                "project",
                "development",
                "water",
                "electricity",
                "infrastructure",
                "construction",
            ],
        ),
        (
            "Health",
            [
                "hospital",
                "health",
                "disease",
                "doctor",
                "medical",
                "patients",
                "clinic",
            ],
        ),
        (
            "Education",
            [
                "school",
                "students",
                "university",
                "education",
                "teachers",
                "exam",
            ],
        ),
    ]

    best_category = "Regional News"

    best_score = 0

    for category, terms in categories:
        score = 0

        for term in terms:
            if term in text:
                score += 1

        if score > best_score:
            best_score = score
            best_category = category

    return best_category


# ============================================================
# SOURCE NAME
# ============================================================

def clean_source_name(name, url):
    name = clean_text(name)

    if name:
        return name

    host = hostname(url)

    if not host:
        return "Unknown Source"

    host = host.replace(
        "www.",
        "",
    )

    return host


# ============================================================
# STORY KEY
# ============================================================

def story_key(title, url):
    raw = (
        clean_text(title).lower()
        + "|"
        + canonical_url(url).lower()
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:20]


# ============================================================
# ARTICLE FETCH
# ============================================================

def enrich_article(item):
    title = clean_text(
        item.get("title", "")
    )

    link = normalize_url(
        item.get("link", "")
    )

    description = clean_text(
        item.get("description", "")
    )

    source_name = clean_source_name(
        item.get("source_name", ""),
        link,
    )

    published = clean_text(
        item.get("published", "")
    )

    if not link:
        return None

    if contains_forbidden_story_term(title):
        return None

    page = fetch_text(link)

    if not page:
        return None

    canonical = extract_canonical(
        page,
        link,
    )

    if canonical:
        link = canonical

    page_title = extract_title(page)

    if page_title:
        title = page_title

    page_description = extract_description(
        page
    )

    if page_description:
        description = page_description

    article_text = extract_article_text(
        page
    )

    image_urls = extract_image_urls(
        page,
        link,
    )

    scored_images = []

    for image_url in image_urls:
        score = score_image_url(
            image_url
        )

        if score <= -900:
            continue

        scored_images.append(
            (
                score,
                image_url,
            )
        )

    scored_images.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    county = detect_county(
        title,
        description,
        article_text,
    )

    category = detect_category(
        title,
        description,
        article_text,
    )

    if not county:
        return None

    if contains_forbidden_story_term(
        title + " " + article_text
    ):
        return None

    return {
        "title": title,
        "url": link,
        "description": description,
        "summary": description,
        "article_text": article_text,
        "published": published,
        "source": source_name,
        "source_name": source_name,
        "county": county,
        "category": category,
        "image_candidates": [
            url
            for _, url in scored_images[:20]
        ],
    }


# ============================================================
# DOWNLOAD STORY IMAGES
# ============================================================

def download_story_images(story):
    title = story.get(
        "title",
        "",
    )

    key = story_key(
        title,
        story.get("url", ""),
    )

    candidates = story.get(
        "image_candidates",
        [],
    )

    local_images = []

    signatures = set()

    for index, image_url in enumerate(
        candidates
    ):

        if len(local_images) >= MAX_IMAGES_PER_STORY:
            break

        path_string = download_real_image(
            image_url,
            key,
            index,
        )

        if not path_string:
            continue

        path = BASE_DIR / path_string

        signature = image_signature(
            path
        )

        if not signature:
            path.unlink(
                missing_ok=True
            )

            continue

        if signature in signatures:
            path.unlink(
                missing_ok=True
            )

            continue

        signatures.add(signature)

        local_images.append(
            path_string
        )

    return local_images


# ============================================================
# STORY QUALITY SCORE
# ============================================================

def story_quality_score(story):
    score = 0

    title = clean_text(
        story.get("title", "")
    )

    description = clean_text(
        story.get("description", "")
    )

    article_text = clean_text(
        story.get("article_text", "")
    )

    source = clean_source_name(
        story.get("source_name", ""),
        story.get("url", ""),
    )

    county = story.get(
        "county",
        "",
    )

    images = story.get(
        "images",
        [],
    )

    host = hostname(
        story.get("url", "")
    )

    # County
    if county:
        score += 15

    # Real photos
    score += min(
        len(images) * 15,
        60,
    )

    # Article content
    if len(article_text) >= 500:
        score += 15
    elif len(article_text) >= 250:
        score += 10
    elif len(article_text) >= 100:
        score += 5

    # Description
    if len(description) >= 100:
        score += 5

    # Source
    for domain, source_score in SOURCE_SCORES.items():
        if domain in host:
            score += source_score
            break

    # Strong title
    if len(title) >= 30:
        score += 5

    # Freshness indicator
    published = clean_text(
        story.get("published", "")
    ).lower()

    for term in [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "today",
        "hour",
        "minute",
    ]:
        if term in published:
            score += 5
            break

    return score


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_stories(stories):
    result = []

    seen_urls = set()

    seen_titles = set()

    for story in stories:
        url = canonical_url(
            story.get("url", "")
        )

        title = clean_text(
            story.get("title", "")
        ).lower()

        title_key = re.sub(
            r"[^a-z0-9]+",
            " ",
            title,
        ).strip()

        if url and url in seen_urls:
            continue

        if title_key and title_key in seen_titles:
            continue

        if url:
            seen_urls.add(url)

        if title_key:
            seen_titles.add(title_key)

        result.append(story)

    return result


# ============================================================
# COLLECT STORIES
# ============================================================

def collect_stories():
    all_items = []

    log("")
    log("=" * 68)
    log("FETCHING FRESH RIFT VALLEY NEWS")
    log("=" * 68)

    for query in SEARCH_QUERIES:
        log(f"Searching: {query}")

        rss_url = google_news_rss_url(
            query
        )

        xml = fetch_text(
            rss_url
        )

        if not xml:
            log("  No RSS response")
            continue

        items = parse_rss(
            xml
        )

        log(
            f"  RSS results: {len(items)}"
        )

        all_items.extend(items)

        time.sleep(0.4)

    return all_items


# ============================================================
# BUILD STORIES
# ============================================================

def build_stories(items):
    stories = []

    seen_links = set()

    log("")
    log("=" * 68)
    log("ENRICHING ARTICLES AND RECOVERING REAL PHOTOS")
    log("=" * 68)

    for index, item in enumerate(items):
        link = canonical_url(
            item.get("link", "")
        )

        if not link:
            continue

        if link in seen_links:
            continue

        seen_links.add(link)

        title = clean_text(
            item.get("title", "")
        )

        if not title:
            continue

        if contains_forbidden_story_term(
            title
        ):
            log(
                f"SKIP forbidden story: {title}"
            )
            continue

        log(
            f"[{index + 1}] {title[:110]}"
        )

        story = enrich_article(
            item
        )

        if not story:
            log(
                "    Could not enrich article"
            )
            continue

        log(
            f"    County: {story.get('county')}"
        )

        log(
            f"    Source: {story.get('source_name')}"
        )

        candidates = story.get(
            "image_candidates",
            [],
        )

        log(
            f"    Image candidates: {len(candidates)}"
        )

        images = download_story_images(
            story
        )

        if not images:
            log(
                "    REAL ARTICLE PHOTOS: 0"
            )
            continue

        log(
            f"    REAL ARTICLE PHOTOS: {len(images)}"
        )

        story["images"] = images

        # Compatibility fields
        story["image"] = images[0]

        story["image_path"] = images[0]

        story["image_paths"] = images

        story["article_images"] = images

        story["photo_count"] = len(images)

        story["quality_score"] = story_quality_score(
            story
        )

        # Remove temporary candidates from final output
        story.pop(
            "image_candidates",
            None,
        )

        stories.append(
            story
        )

        if len(stories) >= MAX_STORIES:
            break

    return deduplicate_stories(
        stories
    )


# ============================================================
# SCRIPT BUILDER
# ============================================================

def first_sentences(text, maximum=4):
    text = clean_text(text)

    if not text:
        return []

    pieces = re.split(
        r"(?<=[
