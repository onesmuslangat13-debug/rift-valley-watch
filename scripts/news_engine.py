from pathlib import Path
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote
from html import unescape
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

import requests
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

TIMEOUT = 20
MAX_ITEMS = 180
MAX_TEST = 120
MAX_PHOTOS = 5

MIN_BYTES = 8000
MIN_WIDTH = 240
MIN_HEIGHT = 160

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
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


# ============================================================
# BLOCKED STORIES
# ============================================================

BLOCKED_STORIES = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# MEDIA SOURCES ARE NOT ALLOWED
#
# Google/Bing are discovery mechanisms only.
# They can NEVER become the final source.
# ============================================================

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
    "news.google.com",
    "google.com",
    "google.co.ke",
    "bing.com",
}


# ============================================================
# BLOCKED IMAGE PATTERNS
# ============================================================

BLOCKED_IMAGES = [
    "news.google.com",
    "google.com/search",
    "google.co.ke/search",
    "bing.com/search",
    "search-result",
    "search_result",
    "screenshot",
    "citizen",
    "ctv",
    "k24",
    "world-cup",
    "world cup",
    "avatar",
    "placeholder",
    "default-image",
    "no-image",
    "favicon",
    "advertisement",
    "adsense",
]


# ============================================================
# DISCOVERY SEARCHES
#
# These are intentionally broad.
#
# The search layer may return media results, but the engine
# will reject them unless the final URL is an official
# primary source.
# ============================================================

SEARCHES = [

    # --------------------------------------------------------
    # STATE HOUSE / PRESIDENT WILLIAM RUTO
    # --------------------------------------------------------

    "site:president.go.ke President William Ruto",

    "site:president.go.ke William Ruto tour Kenya",

    "site:president.go.ke William Ruto county tour",

    "site:president.go.ke William Ruto development projects",

    "site:president.go.ke President Ruto launches",

    "site:president.go.ke President Ruto commissions",

    "site:president.go.ke President Ruto visits",

    "site:president.go.ke President Ruto announces",

    "site:x.com/WilliamsRuto William Ruto Kenya",

    "site:x.com/WilliamsRuto President Ruto",

    "site:x.com/WilliamsRuto Ruto tour",

    "site:x.com/WilliamsRuto Kenya county",

    "site:facebook.com William Samoei Ruto Kenya",

    "site:facebook.com/williamsamoeiruto William Ruto",

    "President William Ruto official Kenya tour",

    "President William Ruto official government announcement",

    # --------------------------------------------------------
    # OFFICIAL RIFT VALLEY COUNTY SOURCES
    # --------------------------------------------------------

    "site:go.ke Bomet county government",

    "site:go.ke Kericho county government",

    "site:go.ke Nakuru county government",

    "site:go.ke Nandi county government",

    "site:go.ke Uasin Gishu county government",

    "site:go.ke Elgeyo Marakwet county government",

    "site:go.ke West Pokot county government",

    "site:go.ke Narok county government",

    "site:go.ke Trans Nzoia county government",

    "site:go.ke Samburu county government",

    "site:go.ke Turkana county government",

    "site:go.ke Laikipia county government",

    "site:go.ke Kajiado county government",

    # --------------------------------------------------------
    # OFFICIAL NATIONAL AGENCIES
    # --------------------------------------------------------

    "site:police.go.ke Kenya Police",

    "site:dci.go.ke Kenya DCI",

    "site:meteo.go.ke Kenya weather",

    "site:ndma.go.ke Kenya drought",

    "site:ndma.go.ke Kenya floods",

    "site:kws.go.ke Kenya wildlife",

    "site:kenyaforestservice.org Kenya Forest Service",

    "site:nema.go.ke Kenya environment",

    "site:kenha.co.ke Kenya roads",

    "site:kenha.go.ke Kenya roads",

    "site:health.go.ke Kenya Ministry Health",

    "site:education.go.ke Kenya Ministry Education",

    "site:transport.go.ke Kenya transport",

    "site:agriculture.go.ke Kenya agriculture",

    "site:interior.go.ke Kenya Interior",

    "site:energy.go.ke Kenya energy",

    "site:kenyapower.co.ke Kenya Power",

    "site:epra.go.ke Kenya energy",

    "site:redcross.or.ke Kenya Red Cross",
]


# ============================================================
# LOGGING
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean(value):

    if value is None:
        return ""

    text = unescape(str(value))

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
# URL NORMALIZATION
# ============================================================

def normalize_url(value):

    if not value:
        return ""

    url = unescape(
        str(value)
    ).strip()

    url = url.replace(
        "&amp;",
        "&",
    )

    url = url.replace(
        "\\/",
        "/",
    )

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return ""

    return url


# ============================================================
# HASH
# ============================================================

def hash_text(text):

    return hashlib.sha1(
        text.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()[:16]


# ============================================================
# BLOCKED STORY
# ============================================================

def blocked_story(text):

    value = clean(
        text
    ).lower()

    for word in BLOCKED_STORIES:

        if word in value:
            return True

    return False


# ============================================================
# HOST EXTRACTION
# ============================================================

def host_of(url):

    url = normalize_url(
        url
    )

    if not url:
        return ""

    host = (
        urlparse(url)
        .netloc
        .lower()
        .split("@")[-1]
        .split(":")[0]
    )

    if host.startswith("www."):
        host = host[4:]

    return host


# ============================================================
# GOOGLE URL
# ============================================================

def is_google_url(url):

    host = host_of(
        url
    )

    if not host:
        return False

    return (
        host == "news.google.com"
        or host == "google.com"
        or host.endswith(
            ".google.com"
        )
        or host.endswith(
            ".google.co.ke"
        )
    )


# ============================================================
# DISCOVERY URL
# ============================================================

def is_discovery_url(url):

    host = host_of(
        url
    )

    if not host:
        return True

    if is_google_url(
        url
    ):
        return True

    if host == "bing.com":
        return True

    if host.endswith(
        ".bing.com"
    ):
        return True

    return False


# ============================================================
# MEDIA DOMAIN
# ============================================================

def is_media_domain(url):

    host = host_of(
        url
    )

    return host in BLOCKED_SOURCE_DOMAINS


# ============================================================
# OFFICIAL GOVERNMENT HOST
# ============================================================

def is_official_government_host(host):

    host = (
        host or ""
    ).lower()

    if not host:
        return False

    if is_media_domain(
        "https://" + host
    ):
        return False

    # State House
    if (
        host == "president.go.ke"
        or host.endswith(
            ".president.go.ke"
        )
    ):
        return True

    # Kenyan government domains
    if host.endswith(
        ".go.ke"
    ):
        return True

    # Selected official institutional domains
    allowed = [

        "kenyaforestservice.org",

        "redcross.or.ke",

    ]

    for domain in allowed:

        if (
            host == domain
            or host.endswith(
                "." + domain
            )
        ):
            return True

    return False


# ============================================================
# OFFICIAL RUTO SOCIAL URL
# ============================================================

def is_official_social_url(url):

    normalized = normalize_url(
        url
    )

    if not normalized:
        return False

    parsed = urlparse(
        normalized
    )

    host = parsed.netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    path = parsed.path.lower()

    # --------------------------------------------------------
    # X / TWITTER
    # --------------------------------------------------------

    if host in [
        "x.com",
        "twitter.com",
    ]:

        allowed_names = [
            "/williamsruto",
            "/williamsamoeiruto",
            "/presidentruto",
        ]

        for name in allowed_names:

            if path.startswith(
                name
            ):
                return True

        return False

    # --------------------------------------------------------
    # FACEBOOK
    # --------------------------------------------------------

    if host in [
        "facebook.com",
        "m.facebook.com",
    ]:

        allowed_names = [
            "williamsamoeiruto",
            "williamsruto",
            "presidentwilliamruto",
        ]

        for name in allowed_names:

            if name in path:
                return True

        return False

    return False


# ============================================================
# ALLOWED PRIMARY SOURCE
# ============================================================

def is_allowed_primary_url(url):

    url = normalize_url(
        url
    )

    if not url:
        return False

    if is_discovery_url(
        url
    ):
        return False

    if is_media_domain(
        url
    ):
        return False

    if is_official_social_url(
        url
    ):
        return True

    host = host_of(
        url
    )

    return is_official_government_host(
        host
    )


# ============================================================
# BLOCKED ARTICLE URL
# ============================================================

def is_blocked_article_url(url):

    return not is_allowed_primary_url(
        url
    )


# ============================================================
# SOURCE NAME
# ============================================================

def publisher_from_domain(url):

    host = host_of(
        url
    )

    if not host:
        return ""

    known = {

        "president.go.ke":
            "State House Kenya",

        "police.go.ke":
            "Kenya National Police Service",

        "dci.go.ke":
            "DCI Kenya",

        "meteo.go.ke":
            "Kenya Meteorological Department",

        "ndma.go.ke":
            "NDMA Kenya",

        "kws.go.ke":
            "Kenya Wildlife Service",

        "nema.go.ke":
            "NEMA Kenya",

        "kenha.co.ke":
            "Kenya National Highways Authority",

        "kenha.go.ke":
            "Kenya National Highways Authority",

        "health.go.ke":
            "Ministry of Health",

        "education.go.ke":
            "Ministry of Education",

        "transport.go.ke":
            "Ministry of Roads and Transport",

        "agriculture.go.ke":
            "Ministry of Agriculture",

        "interior.go.ke":
            "Ministry of Interior",

        "energy.go.ke":
            "Ministry of Energy",

        "kenyapower.co.ke":
            "Kenya Power",

        "epra.go.ke":
            "EPRA",

        "redcross.or.ke":
            "Kenya Red Cross",

        "kenyaforestservice.org":
            "Kenya Forest Service",
    }

    if host in known:
        return known[host]

    # --------------------------------------------------------
    # RUTO SOCIAL
    # --------------------------------------------------------

    if is_official_social_url(
        url
    ):

        return "President William Ruto"

    # --------------------------------------------------------
    # GENERIC GO.KE
    # --------------------------------------------------------

    if host.endswith(
        ".go.ke"
    ):

        name = (
            host
            .split(".")[0]
            .replace(
                "-",
                " ",
            )
            .title()
        )

        if name:
            return name

        return "Official Government Source"

    return "Official Primary Source"


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_story_title(title):

    title = clean(
        title
    )

    if not title:
        return ""

    patterns = [

        r"\s*[-|]\s*(Google News|Google)\s*$",

        r"\s*[-|]\s*K24(?:\s*TV)?\s*$",

        r"\s*[-|]\s*Citizen(?: Digital| TV)?\s*$",

        r"\s*[-|]\s*(The Standard|Nation|The Star|KBC|NTV Kenya)\s*$",
    ]

    for pattern in patterns:

        title = re.sub(
            pattern,
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()

    return title


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):

    value = clean(
        text
    ).lower()

    for county in COUNTIES:

        if county.lower() in value:
            return county

    return "National"


# ============================================================
# RECENCY
# ============================================================

def recent(date_text):

    if not date_text:
        return True

    try:

        value = parsedate_to_datetime(
            date_text
        )

        if value.tzinfo is None:

            value = value.replace(
                tzinfo=timezone.utc
            )

        hours = (
            datetime.now(
                timezone.utc
            )
            - value.astimezone(
                timezone.utc
            )
        ).total_seconds() / 3600

        return hours <= 120

    except Exception:

        return True


# ============================================================
# REQUEST
# ============================================================

def request_url(
    url,
    image=False,
    referer="",
):

    url = normalize_url(
        url
    )

    if not url:
        return None

    headers = {

        "User-Agent":
            USER_AGENT,

        "Accept-Language":
            "en-US,en;q=0.9",

        "Connection":
            "keep-alive",
    }

    if image:

        headers["Accept"] = (
            "image/avif,image/webp,image/apng,"
            "image/svg+xml,image/*,*/*;q=0.8"
        )

    else:

        headers["Accept"] = (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        )

    if referer:

        headers["Referer"] = referer

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:

            log(
                "HTTP "
                + str(response.status_code)
                + ": "
                + url
            )

            return None

        return response

    except Exception as exc:

        log(
            "REQUEST FAILED: "
            + str(exc)
        )

        return None


# ============================================================
# GOOGLE NEWS RSS DISCOVERY
# ============================================================

def make_feed(query):

    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(
            query
            + " when:5d"
        )
        + "&hl=en-KE&gl=KE&ceid=KE:en"
    )


# ============================================================
# XML TAG
# ============================================================

def strip_tag(tag):

    value = str(
        tag
    )

    if "}" in value:

        value = value.split(
            "}",
            1,
        )[1]

    return value.lower()


# ============================================================
# PARSE RSS
# ============================================================

def parse_feed(text):

    items = []

    try:

        root = ET.fromstring(
            text
        )

    except Exception as exc:

        log(
            "RSS PARSE ERROR: "
            + str(exc)
        )

        return items

    for element in root.iter():

        if strip_tag(
            element.tag
        ) != "item":

            continue

        item = {

            "title":
                "",

            "description":
                "",

            "raw_description":
                "",

            "link":
                "",

            "pubdate":
                "",

            "source":
                "",

            "source_url":
                "",

            "media":
                [],
        }

        for child in element:

            tag = strip_tag(
                child.tag
            )

            serialized = ET.tostring(
                child,
                encoding="unicode",
                method="xml",
            )

            raw_value = "".join(
                child.itertext()
            )

            if tag == "title":

                item["title"] = clean(
                    raw_value
                )

            elif tag == "description":

                item["raw_description"] = unescape(
                    serialized
                )

                item["description"] = clean(
                    raw_value
                )

            elif tag == "link":

                item["link"] = normalize_url(
                    child.attrib.get(
                        "href",
                        "",
                    )
                    or raw_value
                )

            elif tag in [
                "pubdate",
                "published",
                "updated",
                "date",
            ]:

                if not item["pubdate"]:

                    item["pubdate"] = clean(
                        raw_value
                    )

            elif tag == "source":

                item["source"] = clean(
                    raw_value
                )

                item["source_url"] = normalize_url(
                    child.attrib.get(
                        "url",
                        "",
                    )
                )

            # ------------------------------------------------
            # RECURSIVE MEDIA EXTRACTION
            # ------------------------------------------------

            for node in child.iter():

                for attribute_name in [

                    "url",

                    "href",

                    "src",

                    "data-src",

                    "data-original",

                    "data-lazy-src",

                    "data-lazyload",

                    "data-image",
                ]:

                    media_url = normalize_url(
                        node.attrib.get(
                            attribute_name,
                            "",
                        )
                    )

                    if (
                        media_url
                        and media_url
                        not in item["media"]
                    ):

                        item["media"].append(
                            media_url
                        )

                for attribute_name in [

                    "srcset",

                    "data-srcset",
                ]:

                    srcset = node.attrib.get(
                        attribute_name,
                        "",
                    )

                    if not srcset:
                        continue

                    for piece in srcset.split(","):

                        candidate = normalize_url(
                            piece.strip().split(" ")[0]
                        )

                        if (
                            candidate
                            and candidate
                            not in item["media"]
                        ):

                            item["media"].append(
                                candidate
                            )

        if (
            item["title"]
            and item["link"]
        ):

            items.append(
                item
            )

    return items


# ============================================================
# FETCH FEED
# ============================================================

def fetch_feed(url):

    log("")

    log(
        "RSS FEED: "
        + url
    )

    response = request_url(
        url
    )

    if response is None:

        log(
            "RSS REQUEST FAILED"
        )

        return []

    items = parse_feed(
        response.text
    )

    log(
        "RSS ITEMS: "
        + str(
            len(items)
        )
    )

    return items


# ============================================================
# EXTRACT OFFICIAL URL FROM GOOGLE PAGE
# ============================================================

def extract_external_url_from_html(
    html,
    fallback_url="",
):

    if not html:
        return ""

    candidates = []

    patterns = [

        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',

        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',

        r'<meta[^>]+itemprop=["\']url["\'][^>]+content=["\']([^"\']+)',
    ]

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

        except Exception:

            matches = []

        for value in matches:

            candidate = normalize_url(
                unquote(value)
            )

            if (
                candidate
                and is_allowed_primary_url(
                    candidate
                )
            ):

                candidates.append(
                    candidate
                )

    # --------------------------------------------------------
    # JSON-LD / GENERAL URL FALLBACK
    # --------------------------------------------------------

    href_patterns = [

        r'href=["\'](https?://[^"\']+)',

        r'"(?:url|mainEntityOfPage|contentUrl)"\s*:\s*"([^"]+)',
    ]

    for pattern in href_patterns:

        try:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

        except Exception:

            matches = []

        for value in matches:

            candidate = normalize_url(
                unquote(value)
            )

            if (
                not candidate
                or not is_allowed_primary_url(
                    candidate
                )
            ):

                continue

            candidates.append(
                candidate
            )

    for candidate in candidates:

        return candidate

    return fallback_url


# ============================================================
# RESOLVE GOOGLE NEWS TO OFFICIAL SOURCE
# ============================================================

def resolve_article(
    url,
    source_url="",
):

    url = normalize_url(
        url
    )

    if not url:
        return ""

    # Already official.
    if is_allowed_primary_url(
        url
    ):

        return url

    # Non-Google non-official URLs are rejected.
    if not is_google_url(
        url
    ):

        return ""

    log(
        "GOOGLE NEWS LINK DETECTED"
    )

    response = request_url(
        url
    )

    if response is not None:

        final_url = normalize_url(
            response.url
        )

        if is_allowed_primary_url(
            final_url
        ):

            log(
                "RESOLVED OFFICIAL URL: "
                + final_url
            )

            return final_url

        extracted = extract_external_url_from_html(
            response.text or ""
        )

        if extracted:

            log(
                "EXTRACTED OFFICIAL URL: "
                + extracted
            )

            return extracted

    # --------------------------------------------------------
    # GOOGLE QUERY PARAMETER FALLBACK
    # --------------------------------------------------------

    parsed = urlparse(
        url
    )

    query = parse_qs(
        parsed.query
    )

    for key in [
        "url",
        "u",
        "q",
    ]:

        for value in query.get(
            key,
            [],
        ):

            candidate = normalize_url(
                unquote(value)
            )

            if is_allowed_primary_url(
                candidate
            ):

                log(
                    "QUERY OFFICIAL URL: "
                    + candidate
                )

                return candidate

    # --------------------------------------------------------
    # RSS SOURCE URL
    #
    # Only accept it if it is itself an official URL.
    # --------------------------------------------------------

    if is_allowed_primary_url(
        source_url
    ):

        return source_url

    return ""


# ============================================================
# IMAGE CANDIDATE
# ============================================================

def add_candidate(
    images,
    value,
    base_url,
):

    if not value:
        return

    value = unescape(
        str(value)
    ).strip()

    value = value.replace(
        "\\/",
        "/",
    )

    value = value.strip(
        "\"'<>"
    )

    if value.startswith(
        "data:"
    ):

        return

    if value.startswith(
        "//"
    ):

        value = "https:" + value

    value = urljoin(
        base_url,
        value,
    )

    value = normalize_url(
        value
    )

    if not value:
        return

    if blocked_image(
        value
    ):

        return

    if value not in images:

        images.append(
            value
        )


# ============================================================
# IMAGE BLOCK
# ============================================================

def blocked_image(url):

    value = unescape(
        str(url)
    ).lower()

    for word in BLOCKED_IMAGES:

        if word in value:
            return True

    return False


# ============================================================
# SRCSET
# ============================================================

def add_srcset(
    images,
    value,
    base_url,
):

    if not value:
        return

    for piece in str(
        value
    ).split(","):

        candidate = (
            piece.strip()
            .split(" ")[0]
        )

        add_candidate(
            images,
            candidate,
            base_url,
        )


# ============================================================
# HTML IMAGES
# ============================================================

def html_images(
    html,
    page_url,
):

    images = []

    if not html:
        return images

    patterns = [

        r'<meta[^>]+(?:property|name)=["\']'
        r'(?:og:image|og:image:url|twitter:image|twitter:image:src)'
        r'["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\']'
        r'[^>]+(?:property|name)=["\']'
        r'(?:og:image|og:image:url|twitter:image|twitter:image:src)'
        r'["\']',

        r'<meta[^>]+itemprop=["\']image["\']'
        r'[^>]+content=["\']([^"\']+)',

        r'<link[^>]+(?:rel=["\'][^"\']*image_src[^"\']*["\']'
        r'|as=["\']image["\'])'
        r'[^>]+href=["\']([^"\']+)',

        r'<link[^>]+href=["\']([^"\']+)["\']'
        r'[^>]+(?:rel=["\'][^"\']*image_src[^"\']*["\']'
        r'|as=["\']image["\'])',

        r'<(?:img|source)[^>]+'
        r'(?:src|data-src|data-original|data-lazy-src|'
        r'data-lazyload|data-image)=["\']([^"\']+)',

        r'<(?:img|source)[^>]+'
        r'(?:srcset|data-srcset)=["\']([^"\']+)',
    ]

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

        except Exception:

            matches = []

        for value in matches:

            if not value:
                continue

            if (
                "srcset"
                in pattern.lower()
            ):

                add_srcset(
                    images,
                    value,
                    page_url,
                )

            else:

                add_candidate(
                    images,
                    value,
                    page_url,
                )

    # --------------------------------------------------------
    # JSON-LD IMAGES
    # --------------------------------------------------------

    json_patterns = [

        r'"image"\s*:\s*"([^"]+)"',

        r'"thumbnailUrl"\s*:\s*"([^"]+)"',

        r'"contentUrl"\s*:\s*"([^"]+)"',
    ]

    for pattern in json_patterns:

        try:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

        except Exception:

            matches = []

        for value in matches:

            add_candidate(
                images,
                value,
                page_url,
            )

    return images


# ============================================================
# EXTRACT IMAGE URLS FROM TEXT
# ============================================================

def extract_urls_from_text(
    text,
    base_url,
):

    images = []

    if not text:
        return images

    raw = unescape(
        str(text)
    )

    raw = raw.replace(
        "\\/",
        "/",
    )

    patterns = [

        r'(?:src|data-src|data-original|'
        r'data-lazy-src|data-lazyload|'
        r'data-image|content)=["\']([^"\']+)["\']',

        r'https?://[^"\'<>\s]+',
    ]

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                raw,
                flags=re.IGNORECASE,
            )

        except Exception:

            matches = []

        for value in matches:

            if isinstance(
                value,
                tuple,
            ):

                value = value[0]

            value = str(
                value
            ).strip()

            value = value.rstrip(
                "\"'<>),;"
            )

            if not value:
                continue

            lower = value.lower()

            looks_like_image = (

                ".jpg" in lower

                or ".jpeg" in lower

                or ".png" in lower

                or ".webp" in lower

                or ".avif" in lower

                or "image" in lower

                or "photo" in lower

                or "media" in lower
            )

            if looks_like_image:

                add_candidate(
                    images,
                    value,
                    base_url,
                )

    return images


# ============================================================
# RSS IMAGES
# ============================================================

def rss_images(item):

    images = []

    base_url = item.get(
        "link",
        "",
    )

    for value in item.get(
        "media",
        [],
    ):

        add_candidate(
            images,
            value,
            base_url,
        )

    raw_description = item.get(
        "raw_description",
        "",
    )

    for value in extract_urls_from_text(
        raw_description,
        base_url,
    ):

        add_candidate(
            images,
            value,
            base_url,
        )

    description = item.get(
        "description",
        "",
    )

    for value in extract_urls_from_text(
        description,
        base_url,
    ):

        add_candidate(
            images,
            value,
            base_url,
        )

    return images


# ============================================================
# IMAGE VALIDATION
# ============================================================

def valid_image(path):

    try:

        if not path.exists():
            return False

        if path.stat().st_size < MIN_BYTES:
            return False

        with Image.open(
            path
        ) as image:

            width, height = image.size

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

def image_extension(url):

    lower = url.lower()

    if ".png" in lower:
        return ".png"

    if ".webp" in lower:
        return ".webp"

    if ".jpeg" in lower:
        return ".jpeg"

    if ".avif" in lower:
        return ".avif"

    return ".jpg"


# ============================================================
# REAL IMAGE RESPONSE
# ============================================================

def response_is_real_image(
    response,
):

    if response is None:
        return False

    content = response.content

    if not content:
        return False

    if len(content) < MIN_BYTES:
        return False

    content_type = response.headers.get(
        "content-type",
        "",
    ).lower()

    if (
        "text/html"
        in content_type
    ):

        return False

    if (
        "text/plain"
        in content_type
    ):

        return False

    head = (
        content[:100]
        .lstrip()
        .lower()
    )

    if head.startswith(
        b"<!doctype"
    ):

        return False

    if head.startswith(
        b"<html"
    ):

        return False

    if head.startswith(
        b"<head"
    ):

        return False

    return True


# ============================================================
# DOWNLOAD REAL PHOTOS
# ============================================================

def download_images(
    story_id,
    urls,
    article_url,
):

    folder = (
        SOURCE_DIR
        / story_id
    )

    if folder.exists():

        shutil.rmtree(
            folder
        )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    accepted = []

    seen_urls = set()

    for url in urls:

        if len(
            accepted
        ) >= MAX_PHOTOS:

            break

        url = normalize_url(
            url
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(
            url
        )

        if blocked_image(
            url
        ):

            log(
                "BLOCKED IMAGE: "
                + url
            )

            continue

        number = (
            len(accepted)
            + 1
        )

        path = (
            folder
            / (
                "photo_"
                + str(number)
                + image_extension(url)
            )
        )

        log(
            "PHOTO ATTEMPT "
            + str(number)
            + ": "
            + url
        )

        response = request_url(
            url,
            image=True,
            referer=article_url,
        )

        if response is None:

            log(
                "REJECTED REQUEST"
            )

            continue

        final_url = normalize_url(
            response.url
        )

        if (
            final_url
            and blocked_image(
                final_url
            )
        ):

            log(
                "REJECTED BLOCKED FINAL URL"
            )

            continue

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        log(
            "CONTENT TYPE: "
            + content_type
        )

        log(
            "IMAGE BYTES: "
            + str(
                len(
                    response.content
                )
            )
        )

        if not response_is_real_image(
            response
        ):

            log(
                "REJECTED NOT IMAGE"
            )

            continue

        try:

            path.write_bytes(
                response.content
            )

            if not valid_image(
                path
            ):

                path.unlink(
                    missing_ok=True
                )

                log(
                    "REJECTED INVALID IMAGE"
                )

                continue

        except Exception:

            path.unlink(
                missing_ok=True
            )

            log(
                "REJECTED SAVE ERROR"
            )

            continue

        relative = str(
            path.relative_to(
                BASE_DIR
            )
        ).replace(
            "\\",
            "/",
        )

        accepted.append(
            {
                "path":
                    relative,

                "url":
                    (
                        final_url
                        or url
                    ),
            }
        )

        log(
            "ACCEPTED REAL OFFICIAL PHOTO: "
            + relative
        )

    return accepted


# ============================================================
# PROCESS STORY
# ============================================================

def process_item(
    item,
):

    raw_title = clean(
        item.get(
            "title",
            "",
        )
    )

    title = clean_story_title(
        raw_title
    )

    description = clean(
        item.get(
            "description",
            "",
        )
    )

    link = normalize_url(
        item.get(
            "link",
            "",
        )
    )

    published = clean(
        item.get(
            "pubdate",
            "",
        )
    )

    source_hint = clean(
        item.get(
            "source",
            "",
        )
    )

    source_url = normalize_url(
        item.get(
            "source_url",
            "",
        )
    )

    if not title:
        return None

    if not link:
        return None

    if blocked_story(
        raw_title
        + " "
        + description
    ):

        log(
            "BLOCKED STORY: "
            + raw_title
        )

        return None

    if not recent(
        published
    ):

        log(
            "OLD STORY: "
            + title
        )

        return None

    log("")

    log(
        "============================================================"
    )

    log(
        "TESTING PRIMARY SOURCE STORY: "
        + title
    )

    log(
        "============================================================"
    )

    # --------------------------------------------------------
    # RESOLVE GOOGLE DISCOVERY RESULT
    # --------------------------------------------------------

    article_url = resolve_article(
        link,
        source_url,
    )

    if not article_url:

        log(
            "NO VERIFIED OFFICIAL PRIMARY URL"
        )

        return None

    # --------------------------------------------------------
    # HARD SOURCE CHECK
    # --------------------------------------------------------

    if not is_allowed_primary_url(
        article_url
    ):

        log(
            "REJECTED NON-OFFICIAL SOURCE: "
            + article_url
        )

        return None

    log(
        "OFFICIAL SOURCE URL: "
        + article_url
    )

    log(
        "OFFICIAL SOURCE: "
        + publisher_from_domain(
            article_url
        )
    )

    # --------------------------------------------------------
    # LOAD OFFICIAL PAGE
    # --------------------------------------------------------

    response = request_url(
        article_url
    )

    html = ""

    if response is not None:

        final_url = normalize_url(
            response.url
        )

        if (
            final_url
            and is_allowed_primary_url(
                final_url
            )
        ):

            article_url = final_url

        html = response.text or ""

    else:

        log(
            "OFFICIAL PAGE REQUEST FAILED"
        )

    # --------------------------------------------------------
    # FINAL HARD SOURCE CHECK
    # --------------------------------------------------------

    if not is_allowed_primary_url(
        article_url
    ):

        log(
            "REJECTED FINAL URL"
        )

        return None

    # --------------------------------------------------------
    # IMAGE EXTRACTION
    # --------------------------------------------------------

    page_images = html_images(
        html,
        article_url,
    )

    feed_images = rss_images(
        item
    )

    embedded_images = extract_urls_from_text(
        html,
        article_url,
    )

    candidates = []

    for value in (
        page_images
        + feed_images
        + embedded_images
    ):

        if value not in candidates:

            candidates.append(
                value
            )

    log(
        "HTML IMAGE CANDIDATES: "
        + str(
            len(
                page_images
            )
        )
    )

    log(
        "RSS IMAGE CANDIDATES: "
        + str(
            len(
                feed_images
            )
        )
    )

    log(
        "EMBEDDED IMAGE CANDIDATES: "
        + str(
            len(
                embedded_images
            )
        )
    )

    log(
        "TOTAL IMAGE CANDIDATES: "
        + str(
            len(
                candidates
            )
        )
    )

    if not candidates:

        log(
            "NO OFFICIAL PHOTO URL FOUND"
        )

        return None

    # --------------------------------------------------------
    # DOWNLOAD PHOTOS
    # --------------------------------------------------------

    story_id = hash_text(
        title
    )

    photos = download_images(
        story_id,
        candidates,
        article_url,
    )

    if not photos:

        log(
            "NO VALID OFFICIAL REAL PHOTO"
        )

        return None

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source = publisher_from_domain(
        article_url
    )

    if not source:

        source = (
            source_hint
            or "Official Primary Source"
        )

    # --------------------------------------------------------
    # CONTENT TEXT
    # --------------------------------------------------------

    full_text = (
        title
        + " "
        + description
        + " "
        + html[:12000]
    )

    county = detect_county(
        full_text
    )

    lower_text = full_text.lower()

    # --------------------------------------------------------
    # PRESIDENTIAL NATIONAL COVERAGE
    # --------------------------------------------------------

    national_president = (

        "william ruto"
        in lower_text

        or "president ruto"
        in lower_text

        or "state house"
        in lower_text

        or source
        == "State House Kenya"

        or source
        == "President William Ruto"
    )

    if national_president:

        coverage_type = (
            "presidential_national"
        )

    else:

        coverage_type = (
            "rift_valley_official"
        )

    return {

        "id":
            story_id,

        "title":
            title,

        "description":
            description,

        "summary":
            description,

        "county":
            county,

        "coverage_type":
            coverage_type,

        "source":
            source,

        "published":
            published,

        "article_url":
            article_url,

        "images":
            photos,

        "image_count":
            len(
                photos
            ),

        "fetched_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }


# ============================================================
# DATE SORT
# ============================================================

def date_sort(item):

    try:

        value = parsedate_to_datetime(
            item.get(
                "published",
                item.get(
                    "pubdate",
                    "",
                ),
            )
        )

        if value.tzinfo is None:

            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.timestamp()

    except Exception:

        return 0


# ============================================================
# SHORTEN
# ============================================================

def shorten(
    text,
    maximum=260,
):

    text = clean(
        text
    )

    if len(text) <= maximum:

        return text

    text = text[:maximum]

    if " " in text:

        text = text.rsplit(
            " ",
            1,
        )[0]

    return (
        text.rstrip(
            ".,;:"
        )
        + "."
    )


# ============================================================
# SCRIPT
# ============================================================

def make_script(
    story,
):

    title = clean(
        story.get(
            "title",
            "",
        )
    )

    description = clean(
        story.get(
            "description",
            "",
        )
    )

    county = clean(
        story.get(
            "county",
            "National",
        )
    )

    source = clean(
        story.get(
            "source",
            "",
        )
    )

    if not source:

        source = (
            "Official Primary Source"
        )

    coverage_type = story.get(
        "coverage_type",
        "",
    )

    parts = []

    parts.append(
        "Rift Valley Watch breaking news."
    )

    # --------------------------------------------------------
    # PRESIDENTIAL NATIONAL STORY
    # --------------------------------------------------------

    if (
        coverage_type
        == "presidential_national"
    ):

        parts.append(
            "President William Ruto is "
            "at the centre of this "
            "national development."
        )

    elif county != "National":

        parts.append(
            "Reports from "
            + county
            + "."
        )

    parts.append(
        title
        + "."
    )

    if description:

        parts.append(
            shorten(
                description
            )
        )

    parts.append(
        "We are monitoring the official "
        "information and will bring you "
        "verified updates."
    )

    scenes = []

    images = story.get(
        "images",
        [],
    )

    for index, photo in enumerate(
        images
    ):

        scenes.append(
            {
                "scene":
                    index + 1,

                "text":
                    title,

                "image_index":
                    index,

                "image_path":
                    photo.get(
                        "path",
                        "",
                    ),
            }
        )

    narration = " ".join(
        parts
    )

    return {

        "story_id":
            story.get(
                "id",
                "",
            ),

        "title":
            title,

        "county":
            county,

        "source":
            source,

        "narration":
            narration,

        "scenes":
            scenes,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    log("")

    log(
        "============================================================"
    )

    log(
        "RIFT VALLEY WATCH NEWS ENGINE"
    )

    log(
        "VERSION V25 OFFICIAL PRIMARY SOURCES ONLY"
    )

    log(
        "============================================================"
    )

    log("")

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # CLEAN PREVIOUS SOURCE PHOTOS
    # --------------------------------------------------------

    for child in list(
        SOURCE_DIR.iterdir()
    ):

        try:

            if child.is_dir():

                shutil.rmtree(
                    child
                )

            else:

                child.unlink()

        except Exception:

            pass

    # --------------------------------------------------------
    # DISCOVER STORIES
    # --------------------------------------------------------

    all_items = []

    seen_titles = set()

    seen_links = set()

    for query in SEARCHES:

        items = fetch_feed(
            make_feed(query)
        )

        for item in items:

            title = clean(
                item.get(
                    "title",
                    "",
                )
            )

            link = normalize_url(
                item.get(
                    "link",
                    "",
                )
            )

            title_key = title.lower()

            link_key = link.lower()

            if not title_key:
                continue

            if blocked_story(
                title
            ):
                continue

            if title_key in seen_titles:
                continue

            if (
                link_key
                and link_key
                in seen_links
            ):

                continue

            seen_titles.add(
                title_key
            )

            if link_key:

                seen_links.add(
                    link_key
                )

            all_items.append(
                item
            )

            if (
                len(all_items)
                >= MAX_ITEMS
            ):

                break

        if (
            len(all_items)
            >= MAX_ITEMS
        ):

            break

    log("")

    log(
        "TOTAL DISCOVERY STORIES: "
        + str(
            len(all_items)
        )
    )

    log(
        "MEDIA SOURCES ARE NOT ACCEPTED."
    )

    log(
        "ONLY OFFICIAL PRIMARY SOURCES MAY PASS."
    )

    log(
        "STATE HOUSE AND PRESIDENT WILLIAM RUTO "
        "OFFICIAL SOCIAL CONTENT ARE INCLUDED."
    )

    log("")

    # --------------------------------------------------------
    # NEWEST FIRST
    # --------------------------------------------------------

    all_items.sort(
        key=date_sort,
        reverse=True,
    )

    # --------------------------------------------------------
    # TEST STORIES
    # --------------------------------------------------------

    valid = []

    tested = 0

    for item in all_items:

        if (
            tested
            >= MAX_TEST
        ):

            break

        tested += 1

        story = process_item(
            item
        )

        if story is None:

            continue

        valid.append(
            story
        )

        if (
            len(valid)
            >= 8
        ):

            break

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------

    if not valid:

        log("")

        log(
            "============================================================"
        )

        log(
            "NEWS ENGINE FAILED"
        )

        log(
            "============================================================"
        )

        log(
            "No valid official/primary story "
            "with a real official photograph was found."
        )

        log("")

        raise RuntimeError(
            "No valid official primary stories "
            "with real photographs were found."
        )

    # --------------------------------------------------------
    # SELECT NEWEST VALID STORY
    # --------------------------------------------------------

    valid.sort(
        key=date_sort,
        reverse=True,
    )

    selected = valid[0]

    # --------------------------------------------------------
    # CREATE SCRIPT
    # --------------------------------------------------------

    script = make_script(
        selected
    )

    # --------------------------------------------------------
    # WRITE STORY JSON
    # --------------------------------------------------------

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            selected,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # WRITE SCRIPT JSON
    # --------------------------------------------------------

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            script,
            file,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    log("")

    log(
        "============================================================"
    )

    log(
        "NEWS ENGINE SUCCESS"
    )

    log(
        "============================================================"
    )

    log(
        "STORY: "
        + selected["title"]
    )

    log(
        "COUNTY: "
        + selected["county"]
    )

    log(
        "COVERAGE TYPE: "
        + selected["coverage_type"]
    )

    log(
        "SOURCE: "
        + selected["source"]
    )

    log(
        "ARTICLE URL: "
        + selected["article_url"]
    )

    log(
        "REAL PHOTOS: "
        + str(
            selected["image_count"]
        )
    )

    log(
        "STORY JSON: "
        + str(
            STORY_FILE
        )
    )

    log(
        "SCRIPT JSON: "
        + str(
            SCRIPT_FILE
        )
    )

    log(
        "============================================================"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
