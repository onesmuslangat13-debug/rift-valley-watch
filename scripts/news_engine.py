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


# ============================================================
# RIFT VALLEY WATCH
# OFFICIAL PRIMARY NEWS ENGINE V26
#
# PURPOSE
# - Discover fresh official/primary-source developments
# - Cover the entire Rift Valley
# - Cover major national developments involving President Ruto
# - Use official government / institutional sources only
# - Allow official President William Ruto social accounts
# - Download REAL photographs from official pages
# - Reject media publishers
# - Reject Google/Bing search pages as sources
# - Reject Gachagua stories
# - Create:
#       data/story.json
#       data/selected_story.json
#       data/script.json
#       data/selected_script.json
#
# IMPORTANT
# Google News is used ONLY as a discovery mechanism.
# Google News is NEVER accepted as the final source.
# ============================================================


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets" / "source"

TIMEOUT = 25

MAX_ITEMS = 220
MAX_TEST = 160
MAX_PHOTOS = 6

MIN_BYTES = 7000
MIN_WIDTH = 300
MIN_HEIGHT = 200


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
# BLOCKED SOURCE DOMAINS
#
# These are deliberately blocked.
# The project must NOT use media publishers.
# ============================================================

BLOCKED_SOURCE_DOMAINS = [
    "k24tv.co.ke",
    "k24",

    "citizen.digital",
    "citizentv",
    "royalmedia",

    "nation.africa",
    "nationmedia",

    "standardmedia.co.ke",
    "standardmedia",

    "the-star.co.ke",
    "the-star",

    "capitalfm.co.ke",
    "capitalfm",

    "ntvkenya.co.ke",
    "ntvkenya",

    "kbc.co.ke",
    "kbc",

    "kenyanews.go.ke",
    "kna",

    "tuko.co.ke",
    "tuko",

    "kenyans.co.ke",

    "pulse.co.ke",

    "mpasho.co.ke",

    "people.co.ke",
    "peopledaily.digital",

    "kenyatimes.co.ke",

    "southriftmedia",
    "bometnewswire",

    "google.com",
    "googleusercontent.com",

    "bing.com",
]


# ============================================================
# BLOCKED IMAGE TERMS
# ============================================================

BLOCKED_IMAGE_TERMS = [
    "k24",
    "citizen",
    "ctv",

    "nation.africa",
    "standardmedia",
    "the-star.co.ke",
    "capitalfm",
    "ntvkenya",
    "kbc.co.ke",

    "google.com/search",
    "googleusercontent.com",
    "bing.com",

    "search-result",
    "search_result",
    "searchresults",

    "screenshot",

    "placeholder",
    "no-image",
    "no_image",

    "avatar",
    "favicon",
    "sprite",

    "logo",

    "advert",
    "adsense",

    "world-cup",
]


# ============================================================
# OFFICIAL NON-GO.KE DOMAINS
# ============================================================

OFFICIAL_EXTRA_HOSTS = {
    "president.go.ke",
    "statehousekenya.go.ke",

    "kenyaforestservice.org",
    "redcross.or.ke",

    "meteo.go.ke",
    "ndma.go.ke",
    "nema.go.ke",
    "kws.go.ke",

    "kenha.co.ke",
    "kplc.co.ke",
    "epra.go.ke",
}


# ============================================================
# DISCOVERY SEARCHES
#
# Google News is only the discovery layer.
# ============================================================

SEARCHES = [

    # --------------------------------------------------------
    # PRESIDENT RUTO / STATE HOUSE
    # --------------------------------------------------------

    'site:president.go.ke "President William Ruto"',
    'site:president.go.ke "William Ruto" tour Kenya',
    'site:president.go.ke "William Ruto" visit',
    'site:president.go.ke "William Ruto" launch',
    'site:president.go.ke "William Ruto" commission',
    'site:president.go.ke "William Ruto" development',
    'site:president.go.ke "President Ruto" September 2026',
    'site:president.go.ke "State House" September 2026',

    # --------------------------------------------------------
    # PRESIDENT RUTO X
    # --------------------------------------------------------

    'site:x.com/WilliamsRuto/status "Ruto"',
    'site:x.com/WilliamsRuto "Kenya"',
    'site:x.com/WilliamsRuto "tour"',
    'site:x.com/WilliamsRuto "President Ruto"',
    'site:x.com/WilliamsRuto "September 2026"',

    # --------------------------------------------------------
    # PRESIDENT RUTO FACEBOOK
    # --------------------------------------------------------

    'site:facebook.com/williamsamoeiruto "William Ruto"',
    'site:facebook.com/williamsamoeiruto Kenya',
    'site:facebook.com/williamsamoeiruto "President Ruto"',

    # --------------------------------------------------------
    # GENERAL OFFICIAL GOVERNMENT
    # --------------------------------------------------------

    'site:go.ke "September 2026" Kenya',
    'site:go.ke "2026" "county government" project',
    'site:go.ke "September 2026" government Kenya',

    # --------------------------------------------------------
    # COUNTY SOURCES
    # --------------------------------------------------------

    'site:go.ke "2026" "Bomet County"',
    'site:go.ke "2026" "Kericho County"',
    'site:go.ke "2026" "Nakuru County"',
    'site:go.ke "2026" "Nandi County"',
    'site:go.ke "2026" "Uasin Gishu County"',
    'site:go.ke "2026" "Elgeyo-Marakwet County"',
    'site:go.ke "2026" "West Pokot County"',
    'site:go.ke "2026" "Narok County"',
    'site:go.ke "2026" "Trans Nzoia County"',
    'site:go.ke "2026" "Samburu County"',
    'site:go.ke "2026" "Turkana County"',
    'site:go.ke "2026" "Laikipia County"',
    'site:go.ke "2026" "Kajiado County"',

    'site:go.ke "September 2026" Bomet',
    'site:go.ke "September 2026" Kericho',
    'site:go.ke "September 2026" Nakuru',
    'site:go.ke "September 2026" Nandi',
    'site:go.ke "September 2026" "Uasin Gishu"',
    'site:go.ke "September 2026" Narok',
    'site:go.ke "September 2026" "Trans Nzoia"',
    'site:go.ke "September 2026" Samburu',
    'site:go.ke "September 2026" Turkana',
    'site:go.ke "September 2026" Laikipia',
    'site:go.ke "September 2026" Kajiado',

    # --------------------------------------------------------
    # SECURITY
    # --------------------------------------------------------

    'site:police.go.ke Kenya September 2026',
    'site:dci.go.ke Kenya September 2026',
    'site:interior.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # HEALTH
    # --------------------------------------------------------

    'site:health.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # ROADS / TRANSPORT
    # --------------------------------------------------------

    'site:transport.go.ke Kenya September 2026',
    'site:roads.go.ke Kenya September 2026',
    'site:kenha.co.ke Kenya September 2026',
    'site:kenyarevenueauthority.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # ENERGY
    # --------------------------------------------------------

    'site:energy.go.ke Kenya September 2026',
    'site:kplc.co.ke Kenya September 2026',
    'site:epra.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # EDUCATION
    # --------------------------------------------------------

    'site:education.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # AGRICULTURE
    # --------------------------------------------------------

    'site:agriculture.go.ke Kenya September 2026',
    'site:kephis.org Kenya September 2026',

    # --------------------------------------------------------
    # ENVIRONMENT / WEATHER / DISASTER
    # --------------------------------------------------------

    'site:environment.go.ke Kenya September 2026',
    'site:kws.go.ke Kenya September 2026',
    'site:meteo.go.ke Kenya September 2026',
    'site:ndma.go.ke Kenya September 2026',
    'site:nema.go.ke Kenya September 2026',
    'site:kenyaforestservice.org Kenya September 2026',

    # --------------------------------------------------------
    # TREASURY / ECONOMY
    # --------------------------------------------------------

    'site:treasury.go.ke Kenya September 2026',

    # --------------------------------------------------------
    # WATER
    # --------------------------------------------------------

    'site:water.go.ke Kenya September 2026',
]


# ============================================================
# REQUEST SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    value = unescape(str(value or ""))

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


# ============================================================
# URL HELPERS
# ============================================================

def host_of(url):
    try:
        return (
            urlparse(url)
            .hostname
            or ""
        ).lower().lstrip("www.")
    except Exception:
        return ""


def domain_matches(host, domain):
    return (
        host == domain
        or host.endswith("." + domain)
    )


def is_blocked_domain(url):
    host = host_of(url)

    if not host:
        return True

    for item in BLOCKED_SOURCE_DOMAINS:

        item = item.lower().lstrip("www.")

        if item in host:
            return True

    return False


# ============================================================
# OFFICIAL GOVERNMENT HOST CHECK
# ============================================================

def is_official_government_host(url):

    host = host_of(url)

    if not host:
        return False

    if is_blocked_domain(url):
        return False

    # Kenya government domains.
    if host.endswith(".go.ke"):
        return True

    # Selected official institutions.
    for domain in OFFICIAL_EXTRA_HOSTS:

        if domain_matches(host, domain):
            return True

    return False


# ============================================================
# PRESIDENT RUTO SOCIAL CHECK
# ============================================================

def is_official_social_url(url):

    try:

        parsed = urlparse(url)

        host = (
            parsed.hostname
            or ""
        ).lower()

        path = (
            parsed.path
            or ""
        ).lower().rstrip("/")

        # X / Twitter
        if host in {
            "x.com",
            "www.x.com",
            "twitter.com",
            "www.twitter.com",
        }:

            return (
                path.startswith("/williamsruto")
                or
                path.startswith("/williamsamoeiruto")
                or
                path.startswith("/presidentruto")
            )

        # Facebook
        if host in {
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
        }:

            return (
                "williamsamoeiruto" in path
                or
                "williamsruto" in path
                or
                "presidentwilliamruto" in path
            )

    except Exception:
        pass

    return False


# ============================================================
# FINAL SOURCE VALIDATION
# ============================================================

def is_allowed_primary_url(url):

    if not url:
        return False

    if is_blocked_domain(url):
        return False

    if is_official_government_host(url):
        return True

    if is_official_social_url(url):
        return True

    return False


# ============================================================
# STORY BLOCKING
# ============================================================

def blocked_story(title, text=""):

    blob = (
        f"{title} {text}"
    ).lower()

    for blocked in BLOCKED_STORIES:

        if blocked in blob:
            return True

    return False


# ============================================================
# IMAGE BLOCKING
# ============================================================

def blocked_image_url(url):

    value = (
        unescape(str(url or ""))
        .lower()
    )

    if not value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return True

    for term in BLOCKED_IMAGE_TERMS:

        if term in value:
            return True

    return False


# ============================================================
# NORMALIZE URL
# ============================================================

def normalize_url(url, base=None):

    if not url:
        return ""

    url = unescape(
        str(url).strip()
    )

    url = (
        url
        .replace("\\/", "/")
        .replace("\\u003d", "=")
        .replace("\\u0026", "&")
    )

    url = re.sub(
        r"^url\((.*)\)$",
        r"\1",
        url,
        flags=re.I,
    ).strip("'\" ")

    if base:
        url = urljoin(
            base,
            url
        )

    return url


# ============================================================
# DATE PARSER
# ============================================================

def parse_date(value):

    if not value:
        return None

    try:

        dt = parsedate_to_datetime(
            value
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

    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d",
    ]:

        try:

            dt = datetime.strptime(
                value.strip(),
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
# HTML URL EXTRACTION
# ============================================================

def html_candidates(
    html,
    base_url
):

    text = unescape(
        html or ""
    )

    text = (
        text
        .replace("\\u003d", "=")
        .replace("\\u0026", "&")
        .replace("\\/", "/")
    )

    found = []

    patterns = [

        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',

        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+name=["\']twitter:url["\'][^>]+content=["\']([^"\']+)',

        r'<a[^>]+href=["\'](https?://[^"\']+)',

        r'"url"\s*:\s*"([^"]+)"',

        r'"canonical"\s*:\s*"([^"]+)"',

        r'data-url=["\']([^"\']+)',

        r'data-n-au=["\']([^"\']+)',

        r'href=([\'"])(https?://[^\'"]+)\1',
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.I,
        ):

            try:
                value = match.group(
                    match.lastindex
                )
            except Exception:
                continue

            value = normalize_url(
                value,
                base_url,
            )

            if value.startswith(
                (
                    "http://",
                    "https://",
                )
            ):

                found.append(
                    value
                )

    # Raw URLs embedded in JavaScript/JSON.
    for match in re.finditer(
        r'https?://[^\s"\'<>\\]+',
        text,
        flags=re.I,
    ):

        value = normalize_url(
            match.group(0),
            base_url,
        )

        if value.startswith(
            (
                "http://",
                "https://",
            )
        ):

            found.append(
                value
            )

    output = []
    seen = set()

    for url in found:

        url = url.split(
            "#",
            1
        )[0]

        if url not in seen:

            seen.add(url)
            output.append(url)

    return output


# ============================================================
# RSS SOURCE URL
# ============================================================

def source_url_from_item(item):

    for key in [
        "source_url",
        "source",
    ]:

        value = item.get(
            key,
            "",
        )

        if value:
            return normalize_url(
                value
            )

    return ""


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_rss(query):

    url = (
        "https://news.google.com/rss/search?q="
        +
        quote_plus(query)
        +
        "&hl=en-KE&gl=KE&ceid=KE:en"
    )

    try:

        response = session.get(
            url,
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        return response.text

    except Exception as exc:

        print(
            f"RSS ERROR: {exc}"
        )

        return ""


# ============================================================
# RSS PARSER
# ============================================================

def parse_feed(xml_text):

    items = []

    if not xml_text:
        return items

    try:

        root = ET.fromstring(
            xml_text
        )

    except Exception:

        return items

    for node in root.findall(
        ".//item"
    ):

        def txt(tag):

            child = node.find(
                tag
            )

            if child is None:
                return ""

            return clean_text(
                child.text
            )

        link = txt("link")
        title = txt("title")
        description = txt("description")
        published = txt("pubDate")

        source_node = node.find(
            "source"
        )

        source_name = clean_text(
            source_node.text
            if source_node is not None
            else ""
        )

        source_url = ""

        if source_node is not None:

            source_url = normalize_url(
                source_node.attrib.get(
                    "url",
                    "",
                )
            )

        if not title or not link:
            continue

        items.append({

            "title": title,

            "description": description,

            "published": published,

            "source_name": source_name,

            "source_url": source_url,

            "google_url": link,
        })

    return items


# ============================================================
# GOOGLE NEWS ARTICLE RESOLUTION
# ============================================================

def direct_official_candidates_from_google(
    google_url
):

    candidates = []

    try:

        response = session.get(
            google_url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                "Referer":
                    "https://news.google.com/"
            },
        )

        final_url = normalize_url(
            response.url
        )

        if is_allowed_primary_url(
            final_url
        ):

            candidates.append(
                final_url
            )

        html = (
            response.text
            or ""
        )

        for url in html_candidates(
            html,
            final_url,
        ):

            if is_allowed_primary_url(
                url
            ):

                candidates.append(
                    url
                )

        # Look directly for official URLs
        # inside Google HTML.
        for domain in [
            "president.go.ke",
            "statehousekenya.go.ke",
            ".go.ke",
            "williamsruto",
            "williamsamoeiruto",
        ]:

            if domain not in html.lower():
                continue

            raw_urls = re.findall(
                r'https?://[^\s"\'<>\\]+',
                html,
                flags=re.I,
            )

            for raw_url in raw_urls:

                url = normalize_url(
                    raw_url
                )

                if is_allowed_primary_url(
                    url
                ):

                    candidates.append(
                        url
                    )

    except Exception as exc:

        print(
            f"GOOGLE RESOLVE ERROR: {exc}"
        )

    # Try query parameters.
    try:

        query = parse_qs(
            urlparse(
                google_url
            ).query
        )

        for key in [
            "url",
            "u",
            "q",
            "target",
            "dest",
            "destination",
        ]:

            for value in query.get(
                key,
                [],
            ):

                value = unquote(
                    value
                )

                if is_allowed_primary_url(
                    value
                ):

                    candidates.append(
                        value
                    )

    except Exception:
        pass

    return unique_urls(
        candidates
    )


# ============================================================
# EXACT TITLE OFFICIAL REDISCOVERY
# ============================================================

def search_official_by_title(
    title,
    source_url=""
):

    searches = []

    host = host_of(
        source_url
    )

    if (
        host
        and
        is_official_government_host(
            source_url
        )
    ):

        searches.append(
            f'site:{host} "{title}"'
        )

    elif is_official_social_url(
        source_url
    ):

        searches.append(
            f'"{title}" site:x.com/WilliamsRuto'
        )

        searches.append(
            f'"{title}" site:facebook.com/williamsamoeiruto'
        )

    else:

        searches.append(
            f'"{title}" site:president.go.ke'
        )

        searches.append(
            f'"{title}" site:go.ke'
        )

    for query in searches[:3]:

        feed = google_rss(
            query
        )

        items = parse_feed(
            feed
        )

        for item in items:

            candidates = []

            if item.get(
                "source_url"
            ):

                candidates.append(
                    item["source_url"]
                )

            candidates.extend(
                direct_official_candidates_from_google(
                    item["google_url"]
                )
            )

            for candidate in candidates:

                if is_allowed_primary_url(
                    candidate
                ):

                    return candidate

    return ""


# ============================================================
# RESOLVE ARTICLE
# ============================================================

def resolve_article(item):

    google_url = item.get(
        "google_url",
        ""
    )

    source_url = source_url_from_item(
        item
    )

    candidates = []

    # RSS source can already be official.
    if is_allowed_primary_url(
        source_url
    ):

        candidates.append(
            source_url
        )

    # Direct URL if already official.
    if is_allowed_primary_url(
        google_url
    ):

        candidates.append(
            google_url
        )

    # Resolve opaque Google RSS article URL.
    candidates.extend(
        direct_official_candidates_from_google(
            google_url
        )
    )

    for candidate in unique_urls(
        candidates
    ):

        if is_allowed_primary_url(
            candidate
        ):

            return candidate

    # Final recovery:
    # search the exact title against the official domain.
    recovered = search_official_by_title(
        item.get(
            "title",
            ""
        ),
        source_url,
    )

    if recovered:
        return recovered

    return ""


# ============================================================
# FETCH OFFICIAL PAGE
# ============================================================

def fetch_page(url):

    try:

        response = session.get(
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={
                "Referer":
                    "https://www.google.com/"
            },
        )

        response.raise_for_status()

        final_url = normalize_url(
            response.url
        )

        # The final destination must remain official.
        if not is_allowed_primary_url(
            final_url
        ):

            print(
                f"FINAL SOURCE REJECTED: {final_url}"
            )

            return None

        return {

            "url": final_url,

            "html":
                response.text
                or "",

            "content_type":
                response.headers.get(
                    "content-type",
                    "",
                ),
        }

    except Exception as exc:

        print(
            f"PAGE ERROR {url}: {exc}"
        )

        return None


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def image_candidates(
    html,
    page_url
):

    text = unescape(
        html or ""
    )

    text = (
        text
        .replace("\\u003d", "=")
        .replace("\\u0026", "&")
        .replace("\\/", "/")
    )

    found = []

    patterns = [

        # OpenGraph
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',

        # Twitter
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',

        # Generic image metadata
        r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)',

        # image_src
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)',

        # JSON
        r'"image"\s*:\s*"([^"]+)"',

        r'"imageUrl"\s*:\s*"([^"]+)"',

        r'"contentUrl"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.I,
        ):

            found.append(
                match.group(1)
            )

    # IMG tags.
    img_tags = re.findall(
        r"<img\b[^>]*>",
        text,
        flags=re.I,
    )

    for tag in img_tags:

        for attr in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "data-lazy",
            "srcset",
            "data-srcset",
        ]:

            match = re.search(
                rf'{attr}\s*=\s*["\']([^"\']+)["\']',
                tag,
                flags=re.I,
            )

            if not match:
                continue

            value = match.group(
                1
            )

            if attr.endswith(
                "srcset"
            ):

                value = (
                    value
                    .split(",")[0]
                    .strip()
                    .split(" ")[0]
                )

            found.append(
                value
            )

    # JSON-LD image arrays.
    for match in re.finditer(
        r'"image"\s*:\s*\[\s*(.*?)\s*\]',
        text,
        flags=re.I | re.S,
    ):

        urls = re.findall(
            r'"(https?://[^"]+)"',
            match.group(1),
        )

        found.extend(
            urls
        )

    output = []
    seen = set()

    for raw in found:

        url = normalize_url(
            raw,
            page_url,
        )

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        if blocked_image_url(
            url
        ):
            continue

        if url not in seen:

            seen.add(url)

            output.append(
                url
            )

    return output


# ============================================================
# IMAGE VALIDATION AGAINST SOURCE
# ============================================================

def image_allowed_for_page(
    image_url,
    page_url
):

    if blocked_image_url(
        image_url
    ):

        return False

    # For President Ruto social posts,
    # images can legitimately come from
    # X/Twitter/Facebook CDNs.
    if is_official_social_url(
        page_url
    ):

        image_host = host_of(
            image_url
        )

        return (
            image_host.endswith(
                "twimg.com"
            )
            or
            image_host.endswith(
                "twitter.com"
            )
            or
            image_host.endswith(
                "fbcdn.net"
            )
            or
            image_host.endswith(
                "facebook.com"
            )
            or
            bool(image_host)
        )

    return True


# ============================================================
# VALIDATE IMAGE FILE
# ============================================================

def validate_image(path):

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
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    target
):

    try:

        response = session.get(
            url,
            timeout=TIMEOUT,
            stream=True,
            allow_redirects=True,
            headers={
                "Accept":
                    "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                "Referer":
                    "https://www.google.com/",
            },
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "content-type",
                ""
            )
            .lower()
        )

        data = response.content

        if len(data) < MIN_BYTES:
            return False

        target.parent.mkdir(
