from pathlib import Path
import html
import json
import re
import time
from urllib.parse import quote_plus, urljoin, urlparse, unquote

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE
# VERSION: RVW_NEWS_ENGINE_V10_STABLE_NO_BS4
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_JSON = DATA_DIR / "story.json"
SCRIPT_JSON = DATA_DIR / "script.json"

MAX_STORIES = 8
MAX_IMAGES_PER_STORY = 6

MIN_IMAGE_BYTES = 5000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}

IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "image/avif,image/webp,image/apng,"
        "image/jpeg,image/png,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# COUNTIES
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


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    "Rift Valley Kenya latest news",
    "Bomet Kenya latest news",
    "Kericho Kenya latest news",
    "Nakuru Kenya latest news",
    "Nandi Kenya latest news",
    "Uasin Gishu Kenya latest news",
    "Elgeyo Marakwet Kenya latest news",
    "West Pokot Kenya latest news",
    "Narok Kenya latest news",
    "Trans Nzoia Kenya latest news",
    "Samburu Kenya latest news",
    "Turkana Kenya latest news",
    "Laikipia Kenya latest news",
    "Kajiado Kenya latest news",
    "Rift Valley Kenya politics",
    "Rift Valley Kenya development",
    "Rift Valley Kenya economy",
    "Rift Valley Kenya agriculture",
    "Rift Valley Kenya health",
    "Rift Valley Kenya education",
    "Rift Valley Kenya security",
]


# ============================================================
# SOURCE SCORES
# ============================================================

SOURCE_SCORES = {
    "nation.africa": 9,
    "peopledaily.digital": 8,
    "kbc.co.ke": 8,
    "standardmedia.co.ke": 8,
    "the-star.co.ke": 8,
    "businessdailyafrica.com": 8,
    "capitalfm.co.ke": 7,
    "kenyans.co.ke": 7,
    "tuko.co.ke": 6,
}


# ============================================================
# FORBIDDEN TERMS
# ============================================================

FORBIDDEN_STORY_TERMS = [
    "rigathi gachagua",
    "gachagua",
]

FORBIDDEN_SOURCE_TERMS = [
    "citizen.digital",
    "citizentv.co.ke",
    "citizen tv",
    "citizen digital",
    "citizen",
    "ctv",
]

FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizentv",
    "citizen-digital",
    "citizen_digital",
    "ctv",
    "worldcup",
    "world-cup",
    "world_cup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "profile-picture",
    "profile_picture",
    "generic-avatar",
    "generic_avatar",
    "dummy-image",
    "dummy_image",
    "no-image",
    "no_image",
    "missing-image",
    "missing_image",
    "search-result",
    "search_results",
    "search-results",
    "search_result",
    "serp",
    "gstatic",
    "googleusercontent",
    "google-news",
    "bing",
    "yandex",
]


SEARCH_ENGINE_DOMAINS = {
    "google.com",
    "www.google.com",
    "google.co.ke",
    "www.google.co.ke",
    "news.google.com",
    "images.google.com",
    "googleusercontent.com",
    "www.googleusercontent.com",
    "gstatic.com",
    "www.gstatic.com",
    "bing.com",
    "www.bing.com",
    "bing.net",
    "search.yahoo.com",
    "images.search.yahoo.com",
    "yandex.com",
    "yandex.ru",
    "duckduckgo.com",
}


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(str(message), flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CLEAN OLD IMAGES
# ============================================================

def clean_old_images():

    extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    }

    removed = 0

    for path in SOURCE_DIR.rglob("*"):

        if not path.is_file():
            continue

        try:

            if path.name.endswith(".download"):
                path.unlink()
                removed += 1
                continue

            if path.suffix.lower() in extensions:
                path.unlink()
                removed += 1

        except Exception:
            pass

    log(
        f"Old source images removed: {removed}"
    )


# ============================================================
# JSON
# ============================================================

def save_json(path, payload):

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
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(path)


# ============================================================
# TEXT
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_html_text(value):

    if not value:
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

    value = re.sub(
        r"<noscript\b[^>]*>.*?</noscript>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ============================================================
# URL
# ============================================================

def domain_of(url):

    try:

        host = urlparse(url).netloc.lower()
        host = host.split(":")[0]

        if host.startswith("www."):
            host = host[4:]

        return host

    except Exception:
        return ""


def is_search_engine_domain(url):

    host = domain_of(url)

    if not host:
        return True

    for domain in SEARCH_ENGINE_DOMAINS:

        if host == domain:
            return True

        if host.endswith("." + domain):
            return True

    return False


def absolute_url(url, base_url):

    if not url:
        return ""

    url = html.unescape(str(url)).strip()
    url = url.replace("\\/", "/")

    if url.startswith("//"):
        url = "https:" + url

    return urljoin(base_url, url)


# ============================================================
# FORBIDDEN CHECKS
# ============================================================

def forbidden_story(text):

    value = normalize_text(text).lower()

    for term in FORBIDDEN_STORY_TERMS:

        if term in value:
            return True

    return False


def forbidden_source(value):

    value = normalize_text(value).lower()

    for term in FORBIDDEN_SOURCE_TERMS:

        if term in value:
            return True

    return False


def forbidden_image_url(url):

    if not url:
        return True

    value = html.unescape(str(url)).strip()

    if not value:
        return True

    lowered = value.lower()

    if lowered.startswith("data:"):
        return True

    if lowered.startswith("blob:"):
        return True

    if is_search_engine_domain(value):
        return True

    parsed = urlparse(value)

    host = parsed.netloc.lower()
    path = unquote(parsed.path).lower()
    query = unquote(parsed.query).lower()

    combined = host + " " + path + " " + query

    for term in FORBIDDEN_IMAGE_TERMS:

        if term in combined:
            return True

    search_patterns = [
        "/search",
        "/search?",
        "/imghp",
        "/images/search",
        "tbm=isch",
        "udm=2",
        "search?q=",
        "search?query=",
        "image-search",
        "image_search",
        "search-results",
        "search_result",
        "serp",
    ]

    for pattern in search_patterns:

        if pattern in combined:
            return True

    return False


# ============================================================
# HTTP
# ============================================================

def fetch_url(
    url,
    headers=None,
    timeout=REQUEST_TIMEOUT,
):

    try:

        response = SESSION.get(
            url,
            headers=headers or HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        return response

    except Exception as exc:

        log(
            f"FETCH FAILED: {url}"
        )

        log(
            f"Reason: {exc}"
        )

        return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_url(query):

    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def strip_xml_tag(text, tag):

    pattern = (
        rf"<{tag}\b[^>]*>"
        rf"(.*?)"
        rf"</{tag}>"
    )

    match = re.search(
        pattern,
        text,
        flags=re.I | re.S,
    )

    if not match:
        return ""

    return clean_html_text(
        match.group(1)
    )


def extract_rss_items(xml):

    items = []

    blocks = re.findall(
        r"<item\b[^>]*>"
        r"(.*?)"
        r"</item>",
        xml,
        flags=re.I | re.S,
    )

    for block in blocks:

        title = strip_xml_tag(
            block,
            "title",
        )

        description = strip_xml_tag(
            block,
            "description",
        )

        link = strip_xml_tag(
            block,
            "link",
        )

        pub_date = strip_xml_tag(
            block,
            "pubDate",
        )

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "description": description,
                "url": link,
                "published": pub_date,
            }
        )

    return items


def fetch_rss_query(query):

    url = google_news_url(query)

    response = fetch_url(
        url,
        headers={
            **HEADERS,
            "Accept": (
                "application/rss+xml,"
                "application/xml,"
                "text/xml,*/*"
            ),
        },
    )

    if response is None:
        return []

    return extract_rss_items(
        response.text
    )


# ============================================================
# COUNTY
# ============================================================

def extract_county(text):

    value = normalize_text(text).lower()

    for county in COUNTIES:

        if county.lower() in value:
            return county

    aliases = {
        "elgeyo marakwet": "Elgeyo-Marakwet",
        "elgeyo-marakwet": "Elgeyo-Marakwet",
        "uasin-gishu": "Uasin Gishu",
        "uasin gishu": "Uasin Gishu",
        "west pokot": "West Pokot",
        "trans nzoia": "Trans Nzoia",
    }

    for alias, county in aliases.items():

        if alias in value:
            return county

    return ""


# ============================================================
# SOURCE
# ============================================================

def source_name_from_url(url):

    host = domain_of(url)

    mapping = {
        "nation.africa": "Nation",
        "peopledaily.digital": "People Daily",
        "kbc.co.ke": "KBC",
        "standardmedia.co.ke": "The Standard",
        "the-star.co.ke": "The Star",
        "businessdailyafrica.com": "Business Daily",
        "capitalfm.co.ke": "Capital FM",
        "kenyans.co.ke": "Kenyans.co.ke",
        "tuko.co.ke": "Tuko",
    }

    if host in mapping:
        return mapping[host]

    if host:
        return host

    return "Unknown Source"


def source_score(url):

    host = domain_of(url)

    if forbidden_source(host):
        return -100

    if host in SOURCE_SCORES:
        return SOURCE_SCORES[host]

    for domain, score in SOURCE_SCORES.items():

        if host.endswith("." + domain):
            return score

    return 3


# ============================================================
# CATEGORY
# ============================================================

def infer_category(text):

    value = normalize_text(text).lower()

    categories = [
        (
            "Politics",
            [
                "governor",
                "senator",
                " mp ",
                "politics",
                "political",
                "president",
                "cabinet",
                "election",
                "party",
                "government",
            ],
        ),
        (
            "Development",
            [
                "road",
                "project",
                "development",
                "construction",
                "water",
                "infrastructure",
            ],
        ),
        (
            "Business",
            [
                "business",
                "economy",
                "investment",
                "market",
                "company",
                "trade",
            ],
        ),
        (
            "Agriculture",
            [
                "farmer",
                "farmers",
                "agriculture",
                "maize",
                "tea",
                "coffee",
                "livestock",
                "crop",
            ],
        ),
        (
            "Health",
            [
                "hospital",
                "health",
                "disease",
                "medical",
                "clinic",
            ],
        ),
        (
            "Education",
            [
                "school",
                "education",
                "student",
                "university",
                "college",
            ],
        ),
        (
            "Security",
            [
                "police",
                "crime",
                "security",
                "arrest",
                "court",
            ],
        ),
    ]

    for category, terms in categories:

        for term in terms:

            if term in value:
                return category

    return "Regional Affairs"


# ============================================================
# STORY SCORE
# ============================================================

def story_relevance_score(item):

    text = (
        normalize_text(
            item.get("title", "")
        )
        + " "
        + normalize_text(
            item.get("description", "")
        )
    ).lower()

    score = 0

    if extract_county(text):
        score += 20

    important_terms = [
        "government",
        "president",
        "deputy president",
        "minister",
        "cabinet",
        "governor",
        "senator",
        " mp ",
        "member of parliament",
        "county assembly",
        "development",
        "road",
        "hospital",
        "school",
        "university",
        "health",
        "education",
        "business",
        "economy",
        "investment",
        "agriculture",
        "farmers",
        "security",
        "police",
        "court",
        "election",
        "politics",
        "budget",
        "project",
        "water",
        "jobs",
    ]

    padded = " " + text + " "

    for term in important_terms:

        if term in padded:
            score += 2

    return score


# ============================================================
# STORY NORMALIZATION
# ============================================================

def normalize_story(item):

    title = normalize_text(
        item.get("title", "")
    )

    description = normalize_text(
        item.get("description", "")
    )

    url = normalize_text(
        item.get("url", "")
    )

    published = normalize_text(
        item.get("published", "")
    )

    combined = title + " " + description

    county = extract_county(
        combined
    )

    category = infer_category(
        combined
    )

    source = source_name_from_url(
        url
    )

    return {
        "title": title,
        "headline": title,
        "summary": description,
        "description": description,
        "url": url,
        "source_url": url,
        "source": source,
        "publisher": source,
        "published": published,
        "county": county,
        "category": category,
    }


# ============================================================
# META IMAGE EXTRACTION
# ============================================================

def extract_meta_content(
    page_html,
    names,
):

    for name in names:

        escaped = re.escape(name)

        patterns = [
            (
                r"<meta\b[^>]*"
                r"(?:property|name|itemprop)"
                r"\s*=\s*['\"]"
                + escaped
                + r"['\"][^>]*"
                r"content\s*=\s*['\"]"
                r"([^'\"]+)"
                r"['\"]"
            ),
            (
                r"<meta\b[^>]*"
                r"content\s*=\s*['\"]"
                r"([^'\"]+)"
                r"['\"][^>]*"
                r"(?:property|name|itemprop)"
                r"\s*=\s*['\"]"
                + escaped
                + r"['\"]"
            ),
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                page_html,
                flags=re.I | re.S,
            )

            if match:
                value = html.unescape(
                    match.group(1)
                ).strip()

                if value:
                    return value

    return ""


# ============================================================
# JSON-LD IMAGES
# ============================================================

def extract_jsonld_images(page_html):

    results = []

    scripts = re.findall(
        r"<script\b[^>]*"
        r'type\s*=\s*["\']application/ld\+json["\']'
        r"[^>]*>"
        r"(.*?)"
        r"</script>",
        page_html,
        flags=re.I | re.S,
    )

    def walk(value):

        if isinstance(value, dict):

            for key, child in value.items():

                key_lower = str(key).lower()

                if key_lower in {
                    "image",
                    "thumbnailurl",
                    "contenturl",
                }:

                    if isinstance(
                        child,
                        str,
                    ):

                        results.append(child)

                    elif isinstance(
                        child,
                        list,
                    ):

                        for entry in child:

                            if isinstance(
                                entry,
                                str,
                            ):

                                results.append(
                                    entry
                                )

                            elif isinstance(
                                entry,
                                dict,
                            ):

                                for subkey in [
                                    "url",
                                    "contentUrl",
                                    "thumbnailUrl",
                                ]:

                                    if entry.get(
                                        subkey
                                    ):

                                        results.append(
                                            str(
                                                entry[
                                                    subkey
                                                ]
                                            )
                                        )

                    elif isinstance(
                        child,
                        dict,
                    ):

                        for subkey in [
                            "url",
                            "contentUrl",
                            "thumbnailUrl",
                        ]:

                            if child.get(
                                subkey
                            ):

                                results.append(
                                    str(
                                        child[
                                            subkey
                                        ]
                                    )
                                )

                walk(child)

        elif isinstance(
            value,
            list,
        ):

            for entry in value:
                walk(entry)

    for raw in scripts:

        raw = html.unescape(
            raw
        ).strip()

        if not raw:
            continue

        try:

            data = json.loads(
                raw
            )

        except Exception:

            continue

        walk(data)

    return results


# ============================================================
# IMAGE URL CLEANING
# ============================================================

def clean_image_url(
    value,
    page_url,
):

    if not value:
        return ""

    value = html.unescape(
        str(value)
    ).strip()

    value = value.replace(
        "\\/",
        "/",
    )

    if value.startswith("data:"):
        return ""

    value = absolute_url(
        value,
        page_url,
    )

    if not value:
        return ""

    if forbidden_image_url(
        value
    ):
        return ""

    return value


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def extract_image_urls_from_html(
    page_html,
    page_url,
):

    candidates = []

    def add(
        value,
        priority,
        reason,
    ):

        cleaned = clean_image_url(
            value,
            page_url,
        )

        if not cleaned:
            return

        candidates.append(
            {
                "url": cleaned,
                "priority": priority,
                "reason": reason,
            }
        )

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    og_image = extract_meta_content(
        page_html,
        [
            "og:image",
            "og:image:url",
            "og:image:secure_url",
        ],
    )

    if og_image:
        add(
            og_image,
            120,
            "og:image",
        )

    # --------------------------------------------------------
    # Twitter
    # --------------------------------------------------------

    twitter_image = extract_meta_content(
        page_html,
        [
            "twitter:image",
            "twitter:image:src",
        ],
    )

    if twitter_image:
        add(
            twitter_image,
            100,
            "twitter:image",
        )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    jsonld_images = (
        extract_jsonld_images(
            page_html
        )
    )

    for image in jsonld_images:

        add(
            image,
            95,
            "jsonld",
        )

    # --------------------------------------------------------
    # IMG TAGS
    # --------------------------------------------------------

    img_tags = re.findall(
        r"<img\b[^>]*>",
        page_html,
        flags=re.I | re.S,
    )

    for tag in img_tags:

        attributes = re.findall(
            r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)"
            r"\s*=\s*"
            r"['\"]"
            r"([^'\"]*)"
            r"['\"]",
            tag,
            flags=re.I | re.S,
        )

        attr_map = {}

        for key, value in attributes:

            attr_map[
                key.lower()
            ] = html.unescape(
                value
            ).strip()

        direct_attributes = [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-url",
            "data-fallback-src",
        ]

        for attr in direct_attributes:

            value = attr_map.get(
                attr,
                "",
            )

            if value:
                add(
                    value,
                    75,
                    attr,
                )

        srcset_attributes = [
            "srcset",
            "data-srcset",
            "data-lazy-srcset",
        ]

        for attr in srcset_attributes:

            value = attr_map.get(
                attr,
                "",
            )

            if not value:
                continue

            parts = value.split(",")

            for part in parts:

                part = part.strip()

                if not part:
                    continue

                image_url = part.split()[0]

                add(
                    image_url,
                    70,
                    attr,
                )

    # --------------------------------------------------------
    # SOURCE TAGS
    # --------------------------------------------------------

    source_tags = re.findall(
        r"<source\b[^>]*>",
        page_html,
        flags=re.I | re.S,
    )

    for tag in source_tags:

        attributes = re.findall(
            r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)"
            r"\s*=\s*"
            r"['\"]"
            r"([^'\"]*)"
            r"['\"]",
            tag,
            flags=re.I | re.S,
        )

        attr_map = {}

        for key, value in attributes:

            attr_map[
                key.lower()
            ] = html.unescape(
                value
            ).strip()

        for attr in [
            "src",
            "data-src",
            "srcset",
            "data-srcset",
        ]:

            value = attr_map.get(
                attr,
                "",
            )

            if not value:
                continue

            for part in value.split(","):

                part = part.strip()

                if not part:
                    continue

                image_url = part.split()[0]

                add(
                    image_url,
                    60,
                    "source-" + attr,
                )

    # --------------------------------------------------------
    # Raw absolute image URLs
    # --------------------------------------------------------

    raw_urls = re.findall(
        r"https?://[^\"'<>\s]+",
        page_html,
        flags=re.I,
    )

    for raw_url in raw_urls:

        raw_url = html.unescape(
            raw_url
        )

        if forbidden_image_url(
            raw_url
        ):
            continue

        lower = raw_url.lower()

        image_like = False

        extensions = [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".avif",
            ".bmp",
            ".gif",
        ]

        for extension in extensions:

            if extension in lower:

                image_like = True
                break

        if not image_like:

            markers = [
                "/images/",
                "/image/",
                "/img/",
                "/media/",
                "/uploads/",
                "/upload/",
                "/photo/",
                "/photos/",
                "/wp-content/",
                "/featured/",
            ]

            for marker in markers:

                if marker in lower:

                    image_like = True
                    break

        if image_like:

            add(
                raw_url,
                
