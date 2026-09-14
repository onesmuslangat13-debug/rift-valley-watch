from pathlib import Path
import json
import re
import html
import hashlib
import shutil
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, unquote

import requests
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME OFFICIAL / PRIMARY NEWS ENGINE
# VERSION: V27_STABLE_OFFICIAL_PHOTOS
#
# PURPOSE
# - Official / primary sources only
# - Rift Valley developments
# - President William Ruto national activities
# - Real article / official photographs
# - Multiple photographs where available
# - No media publishers
# - No Google/Bing screenshots
# - No Gachagua-focused stories
# - Creates story + script + selected files
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

ASSETS_DIR = (
    BASE_DIR
    / "assets"
    / "source"
)

STORY_FILE = (
    DATA_DIR
    / "story.json"
)

SELECTED_STORY_FILE = (
    DATA_DIR
    / "selected_story.json"
)

SCRIPT_FILE = (
    DATA_DIR
    / "script.json"
)

SELECTED_SCRIPT_FILE = (
    DATA_DIR
    / "selected_script.json"
)


# ============================================================
# SETTINGS
# ============================================================

TIMEOUT = 25

MAX_ITEMS = 220

MAX_TEST = 140

MAX_PHOTOS = 6

MIN_BYTES = 7000

MIN_WIDTH = 300

MIN_HEIGHT = 200

RECENT_HOURS = 168


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0.0.0 "
    "Safari/537.36"
)


HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}


session = requests.Session()

session.headers.update(
    HEADERS
)


# ============================================================
# RIFT VALLEY COVERAGE
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
# BLOCKED CONTENT
# ============================================================

BLOCKED_TERMS = [
    "gachagua",
    "rigathi",
]


BLOCKED_SOURCE_DOMAINS = {
    "k24tv.co.ke",
    "citizen.digital",
    "standardmedia.co.ke",
    "nation.africa",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "ntvkenya.co.ke",
    "kenyans.co.ke",
    "tuko.co.ke",
    "mpasho.co.ke",
    "pulselive.co.ke",
    "people.co.ke",
    "thekenyatimes.com",
    "kbc.co.ke",
    "kenyanews.go.ke",

    # Search / discovery domains
    "news.google.com",
    "google.com",
    "google.co.ke",
    "bing.com",
}


BLOCKED_IMAGE_TERMS = [
    "news.google.com",
    "google.com/search",
    "googleusercontent.com",
    "bing.com/images",
    "search-result",
    "searchresults",
    "screenshot",
    "citizen",
    "ctv",
    "k24",
    "world-cup",
    "avatar",
    "placeholder",
    "default-image",
    "no-image",
    "no_image",
    "favicon",
    "advertisement",
    "adsense",
    "advert",
]


# ============================================================
# APPROVED OFFICIAL DOMAINS
# ============================================================

OFFICIAL_EXTRA_HOSTS = {
    "president.go.ke",
    "statehousekenya.go.ke",
    "mygov.go.ke",
    "hudumakenya.go.ke",

    "kra.go.ke",
    "kws.go.ke",
    "nema.go.ke",
    "kmd.go.ke",
    "ndma.go.ke",

    "kenha.co.ke",
    "kplc.co.ke",
    "epra.go.ke",

    "health.go.ke",
    "education.go.ke",
    "interior.go.ke",
    "transport.go.ke",
    "roads.go.ke",
}


# ============================================================
# SOCIAL SOURCES
# ============================================================

SOCIAL_HOSTS = {
    "x.com",
    "twitter.com",
    "facebook.com",
    "www.facebook.com",
    "www.x.com",
    "www.twitter.com",
}


# ============================================================
# GOOGLE NEWS DISCOVERY QUERIES
#
# Google is ONLY used for discovery.
# Final source MUST be official / primary.
# ============================================================

GOOGLE_RSS = (
    "https://news.google.com/rss/search"
)


SEARCH_QUERIES = [

    # --------------------------------------------------------
    # PRESIDENT WILLIAM RUTO
    # --------------------------------------------------------

    'site:president.go.ke "William Ruto"',

    'site:president.go.ke "President Ruto"',

    'site:statehousekenya.go.ke "William Ruto"',

    'site:x.com/WilliamsRuto "Ruto"',

    'site:twitter.com/WilliamsRuto "Ruto"',

    'site:facebook.com/WilliamsRuto "Ruto"',


    # --------------------------------------------------------
    # RIFT VALLEY COUNTIES
    # --------------------------------------------------------

    'site:go.ke "Bomet" "2026"',

    'site:go.ke "Kericho" "2026"',

    'site:go.ke "Nakuru" "2026"',

    'site:go.ke "Nandi" "2026"',

    'site:go.ke "Uasin Gishu" "2026"',

    'site:go.ke "Elgeyo-Marakwet" "2026"',

    'site:go.ke "West Pokot" "2026"',

    'site:go.ke "Narok" "2026"',

    'site:go.ke "Trans Nzoia" "2026"',

    'site:go.ke "Samburu" "2026"',

    'site:go.ke "Turkana" "2026"',

    'site:go.ke "Laikipia" "2026"',

    'site:go.ke "Kajiado" "2026"',

    'site:go.ke "Rift Valley" "2026"',


    # --------------------------------------------------------
    # OFFICIAL GOVERNMENT AGENCIES
    # --------------------------------------------------------

    'site:kws.go.ke "Rift Valley"',

    'site:kmd.go.ke "Rift Valley"',

    'site:ndma.go.ke "Rift Valley"',

    'site:nema.go.ke "Rift Valley"',

    'site:kenha.co.ke "Rift Valley"',

    'site:health.go.ke "Rift Valley"',

    'site:interior.go.ke "Rift Valley"',

    'site:transport.go.ke "Rift Valley"',
]


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[NEWS ENGINE] {message}",
        flush=True,
    )


# ============================================================
# FILE CLEANING
# ============================================================

def clean_directory(path):

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in path.iterdir():

        try:

            if (
                item.is_file()
                or item.is_symlink()
            ):
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception as exc:

            log(
                f"Could not clean {item}: {exc}"
            )


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = html.unescape(
        str(url)
    ).strip()

    url = url.replace(
        "\\/",
        "/",
    )

    url = url.replace(
        "\\u0026",
        "&",
    )

    url = unquote(
        url
    )

    if url.startswith("//"):
        url = "https:" + url

    if not re.match(
        r"^https?://",
        url,
        re.I,
    ):
        return ""

    return url


# ============================================================
# HOST
# ============================================================

def host_of(url):

    try:

        return (
            urlparse(
                normalize_url(url)
            )
            .netloc
            .lower()
            .split(":")[0]
        )

    except Exception:
        return ""


# ============================================================
# DOMAIN MATCH
# ============================================================

def domain_matches(
    host,
    domain,
):

    host = (
        host
        or ""
    ).lower().strip(".")

    domain = (
        domain
        or ""
    ).lower().strip(".")

    return (
        host == domain
        or host.endswith(
            "." + domain
        )
    )


# ============================================================
# BLOCKED DOMAIN
# ============================================================

def is_blocked_domain(url):

    host = host_of(
        url
    )

    if not host:
        return True

    for domain in BLOCKED_SOURCE_DOMAINS:

        if domain_matches(
            host,
            domain,
        ):
            return True

    return False


# ============================================================
# OFFICIAL GOVERNMENT HOST
# ============================================================

def is_official_government_host(
    url
):

    host = host_of(
        url
    )

    if not host:
        return False

    if is_blocked_domain(
        url
    ):
        return False

    # Kenyan government domains.
    if host.endswith(
        ".go.ke"
    ):
        return True

    # Approved official organizations.
    for domain in OFFICIAL_EXTRA_HOSTS:

        if domain_matches(
            host,
            domain,
        ):
            return True

    return False


# ============================================================
# OFFICIAL SOCIAL
# ============================================================

def is_official_social_url(
    url
):

    url = normalize_url(
        url
    )

    parsed = urlparse(
        url
    )

    host = (
        parsed.netloc
        .lower()
        .split(":")[0]
    )

    path = (
        parsed.path
        .lower()
    )

    if host not in SOCIAL_HOSTS:
        return False

    if (
        "williamsruto"
        in path
    ):
        return True

    if (
        "statehousekenya"
        in path
    ):
        return True

    return False


# ============================================================
# ALLOWED PRIMARY URL
# ============================================================

def is_allowed_primary_url(
    url
):

    url = normalize_url(
        url
    )

    if not url:
        return False

    if is_blocked_domain(
        url
    ):
        return False

    return (
        is_official_government_host(
            url
        )
        or is_official_social_url(
            url
        )
    )


# ============================================================
# BLOCKED STORY TERMS
# ============================================================

def contains_blocked_term(
    text
):

    value = str(
        text or ""
    ).lower()

    return any(
        term in value
        for term in BLOCKED_TERMS
    )


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(
    title
):

    title = html.unescape(
        str(
            title or ""
        )
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    title = re.sub(
        r"\s+-\s+"
        r"(K24|Citizen TV|Citizen Digital|"
        r"Nation|The Star|Standard Media|"
        r"People Daily|KBC|NTV Kenya)"
        r"\s*$",
        "",
        title,
        flags=re.I,
    )

    return title.strip()


# ============================================================
# TITLE KEY
# ============================================================

def title_key(
    title
):

    value = clean_title(
        title
    ).lower()

    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# HASH
# ============================================================

def hash_text(
    text
):

    return hashlib.sha256(
        str(text).encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


# ============================================================
# COUNTY
# ============================================================

def detect_county(
    text
):

    value = str(
        text or ""
    ).lower()

    for county in COUNTIES:

        if (
            county.lower()
            in value
        ):
            return county

    if (
        "rift valley"
        in value
    ):
        return "Rift Valley"

    return ""


# ============================================================
# DATE PARSER
# ============================================================

def parse_date(
    value
):

    if not value:
        return None

    value = str(
        value
    ).strip()

    formats = [

        "%a, %d %b %Y %H:%M:%S %z",

        "%a, %d %b %Y %H:%M:%S GMT",

        "%a, %d %b %Y %H:%M GMT",

        "%Y-%m-%dT%H:%M:%S%z",

        "%Y-%m-%dT%H:%M:%S",

        "%Y-%m-%dT%H:%M",

    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt,
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except ValueError:
            continue

    return None


# ============================================================
# RECENT CHECK
# ============================================================

def recent(
    value
):

    dt = parse_date(
        value
    )

    if not dt:
        return True

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=RECENT_HOURS
        )
    )

    return dt >= cutoff


# ============================================================
# HTTP REQUEST
# ============================================================

def request_url(
    url,
    *,
    allow_redirects=True,
    timeout=TIMEOUT,
):

    try:

        return session.get(
            normalize_url(url),
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

    except Exception as exc:

        log(
            f"REQUEST FAILED: {url} | {exc}"
        )

        return None


# ============================================================
# GOOGLE RSS URL
# ============================================================

def google_feed_url(
    query
):

    from urllib.parse import quote_plus

    return (
        GOOGLE_RSS
        + "?q="
        + quote_plus(query)
        + "&hl=en-KE"
        + "&gl=KE"
        + "&ceid=KE:en"
    )


# ============================================================
# XML CLEANING
# ============================================================

def strip_xml(
    text
):

    text = html.unescape(
        str(
            text or ""
        )
    )

    text = re.sub(
        r"<!\[CDATA\[(.*?)\]\]>",
        r"\1",
        text,
        flags=re.S,
    )

    return text.strip()


# ============================================================
# RSS PARSER
# ============================================================

def parse_rss(
    xml_text
):

    items = []

    if not xml_text:
        return items

    matches = re.findall(
        r"<item\b.*?</item>",
        xml_text,
        flags=re.I | re.S,
    )

    for block in matches:

        def field(name):

            match = re.search(
                rf"<{name}\b[^>]*>"
                r"(.*?)"
                rf"</{name}>",
                block,
                flags=re.I | re.S,
            )

            if not match:
                return ""

            return strip_xml(
                match.group(1)
            )

        title = field(
            "title"
        )

        link = field(
            "link"
        )

        pub_date = field(
            "pubDate"
        )

        description = field(
            "description"
        )

        source = field(
            "source"
        )

        source_url = ""

        source_match = re.search(
            r"<source\b[^>]*"
            r"url=[\"']([^\"']+)"
            r"[\"'][^>]*>",
            block,
            flags=re.I,
        )

        if source_match:

            source_url = normalize_url(
                source_match.group(1)
            )

        image_urls = []

        for match in re.findall(
            r"(?:url|href)"
            r"=[\"']"
            r"([^\"']+"
            r"\.(?:jpg|jpeg|png|webp)"
            r"(?:\?[^\"']*)?)"
            r"[\"']",
            block,
            flags=re.I,
        ):

            image_urls.append(
                normalize_url(
                    match
                )
            )

        items.append(
            {
                "title": clean_title(
                    title
                ),
                "link": normalize_url(
                    link
                ),
                "pub_date": pub_date,
                "description": description,
                "source": source,
                "source_url": source_url,
                "rss_images": image_urls,
            }
        )

    return items


# ============================================================
# FETCH RSS
# ============================================================

def fetch_feed(
    query
):

    url = google_feed_url(
        query
    )

    response = request_url(
        url
    )

    if not response:
        return []

    if response.status_code != 200:

        log(
            "Google RSS HTTP "
            f"{response.status_code}: "
            f"{query}"
        )

        return []

    return parse_rss(
        response.text
    )


# ============================================================
# EXTRACT URLS FROM HTML
# ============================================================

def extract_urls(
    text
):

    if not text:
        return []

    text = html.unescape(
        str(text)
    )

    text = text.replace(
        "\\/",
        "/",
    )

    candidates = []

    patterns = [

        r'https?://[^\s"\'<>\\]+',

        r'https?%3A%2F%2F'
        r'[^"\'<>\\ ]+',

    ]

    for pattern in patterns:

        candidates.extend(
            re.findall(
                pattern,
                text,
                flags=re.I,
            )
        )

    decoded = unquote(
        text
    )

    if decoded != text:

        candidates.extend(
            re.findall(
                r'https?://'
                r'[^\s"\'<>\\]+',
                decoded,
                flags=re.I,
            )
        )

    cleaned = []

    for candidate in candidates:

        candidate = normalize_url(
            candidate.rstrip(
                ".,);]}>"
            )
        )

        if candidate:
            cleaned.append(
                candidate
            )

    return list(
        dict.fromkeys(
            cleaned
        )
    )


# ============================================================
# GOOGLE URL CHECK
# ============================================================

def is_google_url(
    url
):

    host = host_of(
        url
    )

    return (
        domain_matches(
            host,
            "news.google.com",
        )
        or domain_matches(
            host,
            "google.com",
        )
        or domain_matches(
            host,
            "google.co.ke",
        )
    )


# ============================================================
# DIRECT SOURCE FROM RSS SOURCE FIELD
# ============================================================

def direct_official_from_source(
    item
):

    source_url = normalize_url(
        item.get(
            "source_url",
            "",
        )
    )

    if is_allowed_primary_url(
        source_url
    ):
        return source_url

    return ""


# ============================================================
# GOOGLE LINK RESOLVER
# ============================================================

def resolve_google_link(
    link,
    title="",
):

    link = normalize_url(
        link
    )

    if not link:
        return ""

    if is_allowed_primary_url(
        link
    ):
        return link

    if not is_google_url(
        link
    ):
        return ""

    response = request_url(
        link,
        allow_redirects=True,
    )

    if response:

        final_url = normalize_url(
            response.url
        )

        if is_allowed_primary_url(
            final_url
        ):
            return final_url

        urls = extract_urls(
            response.text
        )

        for candidate in urls:

            if is_allowed_primary_url(
                candidate
            ):
                return candidate

    # Sometimes the target is encoded
    # directly inside the RSS link.
    for candidate in extract_urls(
        link
    ):

        if is_allowed_primary_url(
            candidate
        ):
            return candidate

    return ""


# ============================================================
# OFFICIAL TITLE REDISCOVERY
# ============================================================

def search_official_by_title(
    title
):

    title = clean_title(
        title
    )

    if not title:
        return ""

    query = (
        '"'
        + title.replace(
            '"',
            "",
        )
        + '"'
    )

    feed = fetch_feed(
        query
    )

    for item in feed[:20]:

        direct = direct_official_from_source(
            item
        )

        if direct:
            return direct

        resolved = resolve_google_link(
            item.get(
                "link",
                "",
            ),
            item.get(
                "title",
                "",
            ),
        )

        if resolved:
            return resolved

    return ""


# ============================================================
# ARTICLE RESOLUTION
# ============================================================

def resolve_article(
    item
):

    title = clean_title(
        item.get(
            "title",
            "",
        )
    )

    direct = direct_official_from_source(
        item
    )

    if direct:
        return direct

    link = normalize_url(
        item.get(
            "link",
            "",
        )
    )

    if is_allowed_primary_url(
        link
    ):
        return link

    resolved = resolve_google_link(
        link,
        title,
    )

    if resolved:
        return resolved

    # Exact-title rediscovery.
    resolved = search_official_by_title(
        title
    )

    if resolved:
        return resolved

    return ""


# ============================================================
# IMAGE BLOCK FILTER
# ============================================================

def image_blocked(
    url
):

    url = normalize_url(
        url
    )

    if not url:
        return True

    value = url.lower()

    for term in BLOCKED_IMAGE_TERMS:

        if term in value:
            return True

    image_host = host_of(
        url
    )

    for domain in BLOCKED_SOURCE_DOMAINS:

        if domain_matches(
            image_host,
            domain,
        ):
            return True

    return False


# ============================================================
# META IMAGE EXTRACTION
# ============================================================

def extract_meta_images(
    page_url,
    text
):

    if not text:
        return []

    results = []

    patterns = [

        r'<meta[^>]+'
        r'property=["\']og:image["\']'
        r'[^>]+content=["\']([^"\']+)',

        r'<meta[^>]+'
        r'content=["\']([^"\']+)["\']'
        r'[^>]+property=["\']og:image["\']',

        r'<meta[^>]+'
        r'name=["\']twitter:image["\']'
        r'[^>]+content=["\']([^"\']+)',

        r'<meta[^>]+'
        r'content=["\']([^"\']+)["\']'
        r'[^>]+name=["\']twitter:image["\']',

        r'<meta[^>]+'
        r'property=["\']og:image:url["\']'
        r'[^>]+content=["\']([^"\']+)',

    ]

    for pattern in patterns:

        for value in re.findall(
            pattern,
            text,
            flags=re.I | re.S,
        ):

            results.append(
                urljoin(
                    page_url,
                    html.unescape(
                        value
                    ),
                )
            )

    return results


# ============================================================
# IMG IMAGE EXTRACTION
# ============================================================

def extract_img_images(
    page_url,
    text
):

    if not text:
        return []

    results = []

    tags = re.findall(
        r"<img\b[^>]*>",
        text,
        flags=re.I | re.S,
    )

    attributes = [
        "src",
        "data-src",
        "data-original",
        "data-lazy-src",
        "data-image",
        "data-url",
    ]

    for tag in tags:

        for attr in attributes:

            match = re.search(
                rf'{attr}\s*=\s*'
                r'["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if match:

                results.append(
                    urljoin(
                        page_url,
                        html.unescape(
                            match.group(1)
                        ),
                    )
                )

        srcset_match = re.search(
            r'srcset\s*=\s*'
            r'["\']([^"\']+)["\']',
            tag,
            flags=re.I,
        )

        if srcset_match:

            parts = (
                srcset_match.group(
                    1
                ).split(",")
            )

            for part in parts:

                candidate = (
                    part
                    .strip()
                    .split(" ")[0]
                )

                if candidate:

                    results.append(
                        urljoin(
                            page_url,
                            html.unescape(
                                candidate
                            ),
                        )
                    )

    return results


# ============================================================
# JSON-LD IMAGE EXTRACTION
# ============================================================

def extract_json_images(
    page_url,
    text
):

    if not text:
        return []

    results = []

    matches = re.findall(
        r'"(?:image|contentUrl|thumbnailUrl)"'
        r'\s*:\s*"([^"]+)"',
        text,
        flags=re.I,
    )

    for match in matches:

        value = (
            match
            .replace(
                "\\/",
                "/",
            )
            .replace(
                '\\"',
                '"',
            )
        )

        results.append(
            urljoin(
                page_url,
                html.unescape(
                    value
                ),
            )
        )

    return results


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def image_candidates(
    page_url,
    page_text,
    rss_images=None,
):

    results = []

    results.extend(
        rss_images or []
    )

    results.extend(
        extract_meta_images(
            page_url,
            page_text,
        )
    )

    results.extend(
        extract_json_images(
            page_url,
            page_text,
        )
    )

    results.extend(
        extract_img_images(
            page_url,
            page_text,
        )
    )

    final = []

    seen = set()

    for url in results:

        url = normalize_url(
            url
        )

        if not url:
            continue

        if image_blocked(
            url
        ):
            continue

        key = (
            url
            .lower()
            .split("?")[0]
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        final.append(
            url
        )

    return final


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(
    path
):

    try:

        if not path.exists():
            return False

        if (
            path.stat().st_size
            < MIN_BYTES
        ):
            return False

        with Image.open(
            path
        ) as image:

            width, height = (
                image.size
            )

            if width < MIN_WIDTH:
                return False

            if height < MIN_HEIGHT:
                return False

            image.verify()

        return True

    except Exception:
        return False


# ============================================================
# IMAGE EXTENSION
# ============================================================

def image_extension(
    url,
    content_type=""
):

    value = (
        urlparse(
            normalize_url(url)
        )
        .path
        .lower()
    )

    if value.endswith(
        ".png"
    ):
        return ".png"

    if value.endswith(
        ".webp"
    ):
        return ".webp"

    if value.endswith(
        ".gif"
    ):
        return ".gif"

    if (
        value.endswith(".jpeg")
        or value.endswith(".jpg")
    ):
        return ".jpg"

    content_type = (
        content_type
        or ""
    ).lower()

    if "png" in content_type:
        return ".png"

    if "webp" in content_type:
        return ".webp"

    return ".jpg"


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    target,
):

    try:

        response = session.get(
            normalize_url(url),
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
            headers={
                "Accept": (
                    "image/avif,"
                    "image/webp,"
                    "image/apng,"
                    "image/svg+xml,"
                    "image/*,"
                    "*/*;q=0.8"
                ),
                "Referer": (
                    "https://www.google.com/"
                ),
            },
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "content-type",
                "",
            )
            .lower()
        )

        # Reject HTML pretending to be an image.
        if (
            "image" not in content_type
            and not re.search(
                r"\.(jpg|jpeg|png|webp)"
                r"(?:$|\?)",
                url,
                flags=re.I,
            )
        ):
            return False

        data = response.content

        if (
            len(data)
            < MIN_BYTES
        ):
            return False

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_bytes(
            data
        )

        if not validate_image(
            target
        ):

            target.unlink(
                missing_ok=True
            )

            return False

        return True

    except Exception as exc:

        try:

            target.unlink(
                missing_ok=True
            )

        except Exception:
            pass

        log(
            f"IMAGE ERROR: {exc}"
        )

        return False


# ============================================================
# DOWNLOAD MULTIPLE IMAGES
# ============================================================

def download_images(
    page_url,
    candidates,
    story_id,
):

    story_dir = (
        ASSETS_DIR
        / story_id
    )

    story_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    photos = []

    seen_hashes = set()

    for index, url in enumerate(
        candidates
    ):

        if (
            len(photos)
            >= MAX_PHOTOS
        ):
            break

        filename_base = (
            f"photo_{index + 1:02d}"
        )

        target = (
            story_dir
            / (
                filename_base
                + image_extension(
                    url
                )
            )
        )

        if not download_image(
            url,
            target,
        ):
            continue

        try:

            data_hash = (
                hashlib.sha256(
                    target.read_bytes()
                ).hexdigest()
            )

            if data_hash in seen_hashes:

                target.unlink(
                    missing_ok=True
                )

                continue

            seen_hashes.add(
                data_hash
            )

            with Image.open(
                target
            ) as image:

                width, height = (
                    image.size
                )

            photos.append(
                {
                    "path": str(
                        target.relative_to(
                            BASE_DIR
                        )
                    ).replace(
                        "\\",
                        "/",
                    ),
                    "url": url,
                    "width": width,
                    "height": height,
                }
            )

        except Exception:

            target.unlink(
                missing_ok=True
            )

    return photos


# ============================================================
# PAGE RELEVANCE
# ============================================================

def page_relevant(
    page_text,
    title,
):

    if not page_text:
        return False

    title_words = [
        word.lower()
        for word in re.findall(
            r"[A-Za-z]{4,}",
            title,
        )
    ]

    if not title_words:
        return True

    lower = page_text.lower()

    matches = sum(
        1
        for word in set(
            title_words
        )
        if word in lower
    )

    return matches >= min(
        4,
        max(
            2,
            len(
                set(
                    title_words
                )
            )
            // 3,
        ),
    )


# ============================================================
# FETCH OFFICIAL PAGE
# ============================================================

def fetch_official_page(
    url
):

    response = request_url(
        url,
        allow_redirects=True,
    )

    if not response:
        return None

    if response.status_code != 200:
        return None

    final_url = normalize_url(
        response.url
    )

    if not is_allowed_primary_url(
        final_url
    ):
        return None

    return response


# ============================================================
# BUILD STORY
# ============================================================

def build_story(
    item,
    official_url,
    photos,
):

    title = clean_title(
        item.get(
            "title",
            "",
        )
    )

    description = re.sub(
        r"<[^>]+>",
        " ",
        str(
            item.get(
                "description",
                "",
            )
        ),
    )

    description = html.unescape(
        description
    )

    description = re.sub(
        r"\s+",
        " ",
        description,
    ).strip()

    county = detect_county(
        title
        + " "
        + description
    )

    host = host_of(
        official_url
    )

    combined = (
        title
        + " "
        + description
    ).lower()

    national = (
        "ruto" in combined
        or "president" in combined
        or "state house" in combined
        or "william ruto" in combined
    )

    if national:

        story_type = (
            "National Presidential Activity"
        )

        region = "Kenya"

    else:

        story_type = (
            "Rift Valley Development"
        )

        region = "Rift Valley"

    return {
        "id": hash_text(
            title
            + official_url
        ),

        "title": title,

        "description": description,

        "source": host,

        "source_url": official_url,

        "publisher": host,

        "county": county,

        "region": region,

        "story_type": story_type,

        "published": item.get(
            "pub_date",
            "",
        ),

        "photos": photos,

        "image_count": len(
            photos
        ),

        "real_photos": True,

        "primary_source": True,

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ============================================================
# PROCESS ONE ITEM
# ============================================================

def process_item(
    item
):

    title = clean_title(
        item.get(
            "title",
            "",
        )
    )

    if not title:
        return None

    if contains_blocked_term(
        title
    ):
        return None

    if not recent(
        item.get(
            "pub_date",
            "",
        )
    ):
        return None

    official_url = resolve_article(
        item
    )

    if not official_url:
        return None

    if contains_blocked_term(
        official_url
    ):
        return None

    response = fetch_official_page(
        official_url
    )

    if not response:
        return None

    page_url = normalize_url(
        response.url
    )

    page_text = response.text

    if not page_relevant(
        page_text,
        title,
    ):

        # Social pages can be difficult
        # to parse reliably.
        if not is_official_social_url(
            page_url
        ):
            return None

    candidates = image_candidates(
        page_url,
        page_text,
        item.get(
            "rss_images",
            [],
        ),
    )

    if not candidates:
        return None

    story_id = hash_text(
        title
        + page_url
    )

    photos = download_images(
        page_url,
        candidates,
        story_id,
    )

    if not photos:
        return None

    return build_story(
        item,
        page_url,
        photos,
    )


# ============================================================
# STORY SCORE
# ============================================================

def story_score(
    story
):

    score = 0

    title = (
        story.get(
            "title",
            "",
        )
        .lower()
    )

    if story.get(
        "primary_source"
    ):
        score += 50

    score += min(
        30,
        story.get(
            "image_count",
            0,
        )
        * 5,
    )

    if story.get(
        "county"
    ):
        score += 15

    if (
        "ruto" in title
        or "president" in title
    ):
        score += 10

    published = parse_date(
        story.get(
            "published",
            "",
        )
    )

    if published:

        age_hours = (
            datetime.now(
                timezone.utc
            )
            - published
        ).total_seconds() / 3600

        score += max(
            0,
            int(
                24
                - min(
                    24,
                    age_hours,
                )
            ),
        )

    return score


# ============================================================
# STORY SORT KEY
# ============================================================

def story_sort_key(
    story
):

    published = parse_date(
        story.get(
            "published",
            "",
        )
    )

    timestamp = (
        published.timestamp()
        if published
        else 0
    )

    return (
        story_score(
            story
        ),
        timestamp,
    )


# ============================================================
# SHORTEN
# ============================================================

def shorten(
    text,
    limit=240,
):

    text = re.sub(
        r"\s+",
        " ",
        str(
            text or ""
        ),
    ).strip()

    if len(text) <= limit:
        return text

    return (
        text[
            :limit - 1
        ].rstrip()
        + "…"
    )


# ============================================================
# SCRIPT
# ============================================================

def make_script(
    story
):

    title = story.get(
        "title",
        "Latest development",
    )

    description = story.get(
        "description",
        "",
    )

    source = story.get(
        "source",
        "official source",
    )

    county = story.get(
        "county",
        "",
    )

    story_type = story.get(
        "story_type",
        "Rift Valley Development",
    )

    if (
        story_type
        == "National Presidential Activity"
    ):

        opening = (
            "Rift Valley Watch breaking news. "
            "President William Ruto is at the "
            "centre of the latest national "
            "development."
        )

    else:

        opening = (
            "Rift Valley Watch breaking news. "
            "A major development has emerged "
            "from the Rift Valley."
        )

    location_line = ""

    if county:

        location_line = (
            f"The latest update comes from "
            f"{county}. "
        )

    body = shorten(
        description,
        360,
    )

    if not body:

        body = (
            "Officials have released an "
            "update on the development."
        )

    narration = (
        f"{opening} "
        f"{location_line}"
        f"{title}. "
        f"{body} "
        f"The information comes from "
        f"the official source, {source}."
    )

    return {
        "title": title,
        "headline": title,
        "narration": narration,
        "source": source,
        "source_url": story.get(
            "source_url",
            "",
        ),
        "county": county,
        "story_type": story_type,
        "image_count": story.get(
            "image_count",
            0,
        ),
    }


# ============================================================
# WRITE JSON
# ============================================================

def write_json(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 72)

    log(
        "RIFT VALLEY WATCH "
        "OFFICIAL NEWS ENGINE V27"
    )

    log("=" * 72)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Clean previous downloaded
    # source photographs.
    clean_directory(
        ASSETS_DIR
    )

    all_items = []

    seen_titles = set()

    log(
        "Running "
        f"{len(SEARCH_QUERIES)} "
        "official discovery searches..."
    )

    # --------------------------------------------------------
    # DISCOVERY
    # --------------------------------------------------------

    for query in SEARCH_QUERIES:

        try:

            feed_items = fetch_feed(
                query
            )

            for item in feed_items:

                title = clean_title(
                    item.get(
                        "title",
                        "",
                    )
                )

                key = title_key(
                    title
                )

                if not key:
                    continue

                if key in seen_titles:
                    continue

                if contains_blocked_term(
                    title
                ):
                    continue

                seen_titles.add(
                    key
                )

                all_items.append(
                    item
                )

                if (
                    len(all_items)
                    >= MAX_ITEMS
                ):
                    break

        except Exception as exc:

            log(
                f"SEARCH ERROR: {exc}"
            )

        if (
            len(all_items)
            >= MAX_ITEMS
        ):
            break

    log(
        "Discovery items collected: "
        f"{len(all_items)}"
    )

    if not all_items:

        raise RuntimeError(
            "No discovery items were found."
        )

    # --------------------------------------------------------
    # NEWEST FIRST
    # --------------------------------------------------------

    all_items.sort(
        key=lambda item: (
            parse_date(
                item.get(
                    "pub_date",
                    "",
                )
            )
            or datetime(
                1970,
                1,
                1,
                tzinfo=timezone.utc,
            )
        ),
        reverse=True,
    )

    valid_stories = []

    tested = 0

    official_resolved = 0

    # --------------------------------------------------------
    # PROCESS ITEMS
    # --------------------------------------------------------

    for item in all_items:

        if (
            tested
            >= MAX_TEST
        ):
            break

        tested += 1

        title = clean_title(
            item.get(
                "title",
                "",
            )
        )

        log(
            f"[{tested}/"
            f"{min(MAX_TEST, len(all_items))}] "
            f"Testing: {title}"
        )

        try:

            official_url = resolve_article(
                item
            )

            if official_url:

                official_resolved += 1

            story = process_item(
                item
            )

            if not story:
                continue

            duplicate = False

            for existing in valid_stories:

                if (
                    title_key(
                        existing.get(
                            "title",
                            "",
                        )
                    )
                    ==
                    title_key(
                        story.get(
                            "title",
                            "",
                        )
                    )
                ):

                    duplicate = True

                    break

            if duplicate:
                continue

            valid_stories.append(
                story
            )

            log(
                "VALID STORY FOUND: "
                f"{story['title']} | "
                f"{story['source']} | "
                f"{story['image_count']} photos"
            )

            if (
                len(valid_stories)
                >= 8
            ):
                break

        except Exception as exc:

            log(
                f"ITEM ERROR: {exc}"
            )

    # --------------------------------------------------------
    # FAILURE DIAGNOSTICS
    # --------------------------------------------------------

    if not valid_stories:

        log("=" * 72)

        log(
            "NEWS ENGINE FAILED"
        )

        log(
            f"Discovery items: "
            f"{len(all_items)}"
        )

        log(
            f"Items tested: "
            f"{tested}"
        )

        log(
            f"Official URLs resolved: "
            f"{official_resolved}"
        )

        log(
            "No valid official/primary "
            "story with a real photograph "
            "was found."
        )

        log("=" * 72)

        raise RuntimeError(
            "No valid official primary "
            "stories with real photographs "
            "were found."
        )

    # --------------------------------------------------------
    # RANK STORIES
    # --------------------------------------------------------

    valid_stories.sort(
        key=story_sort_key,
        reverse=True,
    )

    selected = valid_stories[0]

    # --------------------------------------------------------
    # SELECTED STORY LOG
    # --------------------------------------------------------

    log("=" * 72)

    log(
        "SELECTED STORY"
    )

    log("=" * 72)

    log(
        selected.get(
            "title",
            "",
        )
    )

    log(
        "Source: "
        + selected.get(
            "source",
            "",
        )
    )

    log(
        "Photos: "
        + str(
            selected.get(
                "image_count",
                0,
            )
        )
    )

    log(
        "URL: "
        + selected.get(
            "source_url",
            "",
        )
    )

    log("=" * 72)

    # --------------------------------------------------------
    # SCRIPT
    # --------------------------------------------------------

    script = make_script(
        selected
    )

    # --------------------------------------------------------
    # WRITE FILES
    # --------------------------------------------------------

    write_json(
        STORY_FILE,
        valid_stories,
    )

    write_json(
        SELECTED_STORY_FILE,
        selected,
    )

    write_json(
        SCRIPT_FILE,
        [
            make_script(
                story
            )
            for story in valid_stories
        ],
    )

    write_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    log(
        f"Wrote {STORY_FILE}"
    )

    log(
        f"Wrote {SELECTED_STORY_FILE}"
    )

    log(
        f"Wrote {SCRIPT_FILE}"
    )

    log(
        f"Wrote {SELECTED_SCRIPT_FILE}"
    )

    log(
        "REAL-TIME NEWS ENGINE "
        "COMPLETED SUCCESSFULLY"
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
