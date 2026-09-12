# ============================================================
# RIFT VALLEY WATCH
# FAST + VERIFIED NEWS ENGINE
#
# Purpose:
#   1. Collect recent Rift Valley stories
#   2. Rank candidates
#   3. Resolve Google News URLs to real publishers
#   4. Verify publisher articles
#   5. Verify real article images
#   6. Use controlled Bing fallback when necessary
#   7. Select ONE strongest verified story
#   8. Save story.json + script.json
#   9. Generate the video
#
# Performance goals:
#   - Avoid endless network waits
#   - Avoid duplicate searches
#   - Check only the strongest candidates
#   - Fail fast when a source is unusable
# ============================================================

import os
import re
import json
import time
import html
import hashlib
import traceback

from datetime import datetime, timezone, timedelta

from urllib.parse import (
    urlparse,
    urljoin,
    quote_plus,
    unquote,
)

import requests
import feedparser

from bs4 import BeautifulSoup

from rift_valley_video_generator import generate_video


# ============================================================
# CONFIGURATION
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
]


COUNTY_ALIASES = {
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chebunyo",
        "Konoin",
    ],

    "Kericho": [
        "Kericho",
        "Litein",
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
    ],

    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Aldai",
        "Mosop",
        "Emgwen",
        "Chesumei",
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
        "Keiyo",
        "Marakwet",
        "Kapcherop",
        "Kapsowar",
    ],

    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Pokot",
        "Sigor",
        "Pokot South",
    ],

    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Transmara",
        "Mara",
        "Ololulunga",
    ],
}


# ============================================================
# FILES
# ============================================================

OUTPUT_DIR = "data"

STORY_FILE = os.path.join(
    OUTPUT_DIR,
    "story.json",
)

SCRIPT_FILE = os.path.join(
    OUTPUT_DIR,
    "script.json",
)


# ============================================================
# PERFORMANCE SETTINGS
# ============================================================

# Separate timeouts prevent one slow service from blocking
# the whole pipeline.

RSS_TIMEOUT = 8
ARTICLE_TIMEOUT = 8
IMAGE_TIMEOUT = 6
SEARCH_TIMEOUT = 8


# Maximum age of news to consider.
MAX_AGE_HOURS = 72


# Only examine the strongest candidates.
MAX_CANDIDATES_TO_VERIFY = 8


# Stop once we have enough verified stories to compare.
TARGET_VERIFIED_STORIES = 2


# Maximum Bing results checked for one search.
BING_RESULT_LIMIT = 4


# Maximum image URLs checked from one article.
MAX_IMAGE_CHECKS = 5


# Maximum Bing image URLs checked per query.
MAX_BING_IMAGES = 8


# Short pause between RSS calls.
RSS_DELAY = 0.1


# ============================================================
# USER AGENT
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
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
}


IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "image/avif,image/webp,image/apng,"
        "image/*,*/*;q=0.8"
    ),
    "Referer": "https://www.google.com/",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(
        str(value)
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_title(title):
    title = clean_text(title)

    title = re.sub(
        r"\s*[-|–—]\s*"
        r"(People Daily|Citizen Digital|The Star|Nation|"
        r"Standard Media|KBC|Capital FM|TUKO|Kenyans\.co\.ke)"
        r"\s*$",
        "",
        title,
        flags=re.I,
    )

    return title.strip()


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return (
            parsed.scheme in (
                "http",
                "https",
            )
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def hostname(url):
    try:
        return (
            urlparse(url).hostname
            or ""
        ).lower()

    except Exception:
        return ""


def publisher_domain(url):
    host = hostname(url)

    if host.startswith("www."):
        host = host[4:]

    return host


def is_google_news_url(url):
    host = hostname(url)

    return (
        host == "news.google.com"
        or host.endswith(".news.google.com")
        or host == "google.com"
        or host.endswith(".google.com")
    )


def is_search_engine_url(url):
    host = hostname(url)

    blocked = {
        "google.com",
        "www.google.com",
        "news.google.com",
        "www.news.google.com",
        "bing.com",
        "www.bing.com",
        "r.bing.com",
        "images.bing.com",
        "search.yahoo.com",
        "yahoo.com",
        "www.yahoo.com",
    }

    if host in blocked:
        return True

    if host.endswith(".google.com"):
        return True

    if host.endswith(".bing.com"):
        return True

    return False


def is_svg_url(url):
    path = urlparse(url).path.lower()

    return (
        path.endswith(".svg")
        or ".svg?" in path
        or path.endswith(".svg/")
    )


def now_utc():
    return datetime.now(
        timezone.utc
    )


def parse_date(value):
    if not value:
        return None

    try:
        parsed = feedparser._parse_date(
            value
        )

        if parsed:
            return datetime(
                parsed.tm_year,
                parsed.tm_mon,
                parsed.tm_mday,
                parsed.tm_hour,
                parsed.tm_min,
                parsed.tm_sec,
                tzinfo=timezone.utc,
            )

    except Exception:
        pass

    return None


def is_recent(dt):
    if not dt:
        return True

    age = now_utc() - dt

    return (
        timedelta(hours=0)
        <= age
        <= timedelta(
            hours=MAX_AGE_HOURS
        )
    )


def title_similarity(a, b):
    a = normalize_title(a).lower()
    b = normalize_title(b).lower()

    if not a or not b:
        return 0.0

    words_a = {
        x
        for x in re.findall(
            r"[a-z0-9]+",
            a,
        )
        if len(x) > 2
    }

    words_b = {
        x
        for x in re.findall(
            r"[a-z0-9]+",
            b,
        )
        if len(x) > 2
    }

    if not words_a or not words_b:
        return 0.0

    overlap = len(
        words_a & words_b
    )

    return overlap / max(
        1,
        min(
            len(words_a),
            len(words_b),
        ),
    )


def story_hash(title):
    return hashlib.md5(
        normalize_title(title)
        .lower()
        .encode("utf-8")
    ).hexdigest()[:12]


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_rss(query):
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def build_feed_urls():

    feeds = []

    for county in COUNTIES:

        # IMPORTANT:
        # Reduced from 3 queries per county to 2.
        queries = [
            f'"{county}" Kenya',
            f'"{county}" development government',
        ]

        for query in queries:

            feeds.append(
                {
                    "county": county,
                    "url": google_news_rss(
                        query
                    ),
                }
            )

    return feeds


# ============================================================
# RSS IMAGE EXTRACTION
# ============================================================

def get_rss_media_image(entry):

    candidates = []

    media_content = entry.get(
        "media_content",
        [],
    )

    for item in (
        media_content or []
    ):

        if isinstance(item, dict):

            for key in (
                "url",
                "href",
            ):

                value = item.get(key)

                if value:
                    candidates.append(
                        value
                    )

    media_thumbnail = entry.get(
        "media_thumbnail",
        [],
    )

    for item in (
        media_thumbnail or []
    ):

        if isinstance(item, dict):

            value = item.get(
                "url"
            )

            if value:
                candidates.append(
                    value
                )

    for key in (
        "image",
        "image_url",
        "thumbnail",
    ):

        value = entry.get(key)

        if isinstance(
            value,
            str,
        ):
            candidates.append(
                value
            )

    raw = (
        entry.get(
            "description",
            "",
        )
        or entry.get(
            "summary",
            "",
        )
        or ""
    )

    if raw:

        soup = BeautifulSoup(
            raw,
            "html.parser",
        )

        for img in soup.find_all(
            "img"
        ):

            for attr in (
                "src",
                "data-src",
                "data-original",
                "data-image",
                "data-lazy-src",
            ):

                value = img.get(
                    attr
                )

                if value:
                    candidates.append(
                        value
                    )

    for value in candidates:

        if (
            value
            and valid_http_url(value)
        ):
            return value

    return None


# ============================================================
# RSS PARSER
# ============================================================

def parse_feed(
    feed_url,
    county,
):

    print("")
    print(
        "RSS:",
        feed_url,
    )

    try:

        response = requests.get(
            feed_url,
            headers=HEADERS,
            timeout=RSS_TIMEOUT,
        )

        response.raise_for_status()

        parsed = feedparser.parse(
            response.content
        )

    except Exception as exc:

        print(
            "RSS failed:",
            exc,
        )

        return []

    results = []

    for entry in parsed.entries:

        title = clean_text(
            entry.get(
                "title",
                "",
            )
        )

        if not title:
            continue

        link = entry.get(
            "link",
            "",
        )

        published_value = (
            entry.get(
                "published"
            )
            or entry.get(
                "updated"
            )
            or entry.get(
                "created"
            )
            or ""
        )

        published_dt = parse_date(
            published_value
        )

        if not is_recent(
            published_dt
        ):
            continue

        raw_description = (
            entry.get(
                "description",
                "",
            )
            or entry.get(
                "summary",
                "",
            )
            or ""
        )

        description = clean_text(
            raw_description
        )

        source_name = ""

        source = entry.get(
            "source"
        )

        if isinstance(
            source,
            dict,
        ):

            source_name = clean_text(
                source.get(
                    "title",
                    "",
                )
                or source.get(
                    "name",
                    "",
                )
            )

        if not source_name:
            source_name = (
                "Unknown Source"
            )

        image = get_rss_media_image(
            entry
        )

        results.append(
            {
                "title": title,
                "description": description,
                "summary": description,
                "url": link,
                "published": (
                    published_dt.isoformat()
                    if published_dt
                    else ""
                ),
                "published_dt": published_dt,
                "county": county,
                "source_name": source_name,
                "rss_image": image,
                "raw_description": (
                    raw_description
                ),
                "verification": "",
                "image": image,
            }
        )

    return results


# ============================================================
# ARTICLE IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(
    soup,
    base_url,
):

    candidates = []

    if not soup:
        return candidates

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta",
        attrs={
            "property": "og:image"
        },
    ):

        value = tag.get(
            "content"
        )

        if value:

            candidates.append(
                urljoin(
                    base_url,
                    value,
                )
            )

    # --------------------------------------------------------
    # Twitter
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta",
        attrs={
            "name": "twitter:image"
        },
    ):

        value = tag.get(
            "content"
        )

        if value:

            candidates.append(
                urljoin(
                    base_url,
                    value,
                )
            )

    # --------------------------------------------------------
    # Other metadata
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta"
    ):

        prop = (
            tag.get(
                "property",
                "",
            )
            or tag.get(
                "name",
                "",
            )
        ).lower()

        if prop in (
            "og:image:url",
            "twitter:image:src",
            "image",
        ):

            value = tag.get(
                "content"
            )

            if value:

                candidates.append(
                    urljoin(
                        base_url,
                        value,
                    )
                )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    ):

        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:

            data = json.loads(
                raw
            )

        except Exception:

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

            image = obj.get(
                "image"
            )

            if isinstance(
                image,
                str,
            ):

                candidates.append(
                    urljoin(
                        base_url,
                        image,
                    )
                )

            elif isinstance(
                image,
                dict,
            ):

                value = (
                    image.get(
                        "url"
                    )
                    or image.get(
                        "contentUrl"
                    )
                )

                if value:

                    candidates.append(
                        urljoin(
                            base_url,
                            value,
                        )
                    )

            elif isinstance(
                image,
                list,
            ):

                for value in image:

                    if isinstance(
                        value,
                        str,
                    ):

                        candidates.append(
                            urljoin(
                                base_url,
                                value,
                            )
                        )

    # --------------------------------------------------------
    # HTML images
    # --------------------------------------------------------

    for tag in soup.find_all(
        [
            "img",
            "source",
        ]
    ):

        for attr in (
            "src",
            "data-src",
            "data-original",
            "data-image",
            "data-lazy-src",
            "srcset",
            "data-srcset",
        ):

            value = tag.get(
                attr
            )

            if not value:
                continue

            if (
                " " in value
                and "," in value
            ):

                for item in value.split(
                    ","
                ):

                    item = item.strip()

                    if item:

                        candidates.append(
                            item.split()[0]
                        )

            else:

                candidates.append(
                    value
                )

    # --------------------------------------------------------
    # Clean
    # --------------------------------------------------------

    cleaned = []

    for candidate in candidates:

        candidate = html.unescape(
            str(candidate)
        ).strip()

        if not candidate:
            continue

        candidate = candidate.replace(
            "\\/",
            "/",
        )

        if not valid_http_url(
            candidate
        ):

            candidate = urljoin(
                base_url,
                candidate,
            )

        if not valid_http_url(
            candidate
        ):
            continue

        if is_search_engine_url(
            candidate
        ):
            continue

        if is_svg_url(
            candidate
        ):
            continue

        if candidate not in cleaned:

            cleaned.append(
                candidate
            )

    return cleaned


# ============================================================
# IMAGE VERIFICATION
# ============================================================

def verify_image(url):

    if not valid_http_url(
        url
    ):
        return None

    if is_search_engine_url(
        url
    ):
        return None

    if is_svg_url(
        url
    ):
        return None

    try:

        response = requests.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=IMAGE_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        final_url = response.url

        if not valid_http_url(
            final_url
        ):
            return None

        if is_search_engine_url(
            final_url
        ):
            return None

        if is_svg_url(
            final_url
        ):
            return None

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if "svg" in content_type:
            return None

        data = response.raw.read(
            65536
        )

        if (
            not data
            or len(data) < 1000
        ):
            return None

        valid_magic = (
            data.startswith(
                b"\xff\xd8\xff"
            )
            or data.startswith(
                b"\x89PNG\r\n\x1a\n"
            )
            or data.startswith(
                b"GIF87a"
            )
            or data.startswith(
                b"GIF89a"
            )
            or (
                data[:4] == b"RIFF"
                and data[8:12] == b"WEBP"
            )
        )

        valid_type = any(
            x in content_type
            for x in (
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "image/avif",
            )
        )

        if (
            not valid_magic
            and not valid_type
        ):
            return None

        return final_url

    except Exception as exc:

        print(
            "Image verification error:",
            exc,
        )

        return None


# ============================================================
# FIRST VALID IMAGE
# ============================================================

def first_valid_image(
    candidates,
    max_checks=MAX_IMAGE_CHECKS,
):

    seen = set()

    checks = 0

    for url in candidates:

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        if checks >= max_checks:
            print(
                "Image check limit reached."
            )
            break

        checks += 1

        print(
            f"Checking image "
            f"{checks}/{max_checks}"
        )

        verified = verify_image(
            url
        )

        if verified:

            print(
                "REAL IMAGE FOUND:",
                verified,
            )

            return verified

    return None


# ============================================================
# ARTICLE FETCHING
# ============================================================

def fetch_article(url):

    if not valid_http_url(
        url
    ):
        return None

    if is_google_news_url(
        url
    ):
        return None

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True,
        )

        final_url = response.url

        if not valid_http_url(
            final_url
        ):
            return None

        if is_google_news_url(
            final_url
        ):
            return None

        if is_search_engine_url(
            final_url
        ):
            return None

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if (
            "html" not in content_type
            and "text" not in content_type
        ):
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        return {
            "response": response,
            "final_url": final_url,
            "soup": soup,
        }

    except Exception as exc:

        print(
            "Article fetch failed:",
            exc,
        )

        return None


# ============================================================
# ARTICLE SUMMARY
# ============================================================

def extract_article_summary(
    soup
):

    if not soup:
        return ""

    candidates = []

    for selector in (
        (
            "meta",
            {
                "name": "description"
            },
        ),
        (
            "meta",
            {
                "property": "og:description"
            },
        ),
        (
            "meta",
            {
                "name": "twitter:description"
            },
        ),
    ):

        tag = soup.find(
            selector[0],
            attrs=selector[1],
        )

        if (
            tag
            and tag.get("content")
        ):

            candidates.append(
                clean_text(
                    tag.get(
                        "content"
                    )
                )
            )

    paragraphs = soup.find_all(
        "p"
    )

    for p in paragraphs[:20]:

        text = clean_text(
            p.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) >= 50:

            candidates.append(
                text
            )

    for text in candidates:

        if len(text) >= 50:

            return text[:700]

    return ""


# ============================================================
# VERIFY ARTICLE CANDIDATE
# ============================================================

def verify_article_candidate(
    candidate_url,
    original_title,
):

    if not valid_http_url(
        candidate_url
    ):
        return None

    if is_google_news_url(
        candidate_url
    ):
        return None

    if is_search_engine_url(
        candidate_url
    ):
        return None

    article = fetch_article(
        candidate_url
    )

    if not article:
        return None

    final_url = article[
        "final_url"
    ]

    soup = article[
        "soup"
    ]

    if is_google_news_url(
        final_url
    ):
        return None

    if is_search_engine_url(
        final_url
    ):
        return None

    page_title = ""

    if soup.title:

        page_title = clean_text(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    if not page_title:

        og_title = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            },
        )

        if og_title:

            page_title = clean_text(
                og_title.get(
                    "content",
                    "",
                )
            )

    similarity = title_similarity(
        original_title,
        page_title,
    )

    print(
        "Article title:",
        page_title,
    )

    print(
        "Title similarity:",
        round(
            similarity,
            3,
        ),
    )

    # --------------------------------------------------------
    # Title verification
    # --------------------------------------------------------

    if similarity < 0.18:

        print(
            "Rejected article: "
            "title mismatch"
        )

        return None

    # --------------------------------------------------------
    # Image extraction
    # --------------------------------------------------------

    image_candidates = (
        extract_image_candidates(
            soup,
            final_url,
        )
    )

    image = first_valid_image(
        image_candidates
    )

    summary = (
        extract_article_summary(
            soup
        )
    )

    return {
        "url": final_url,
        "title": (
            page_title
            if page_title
            else original_title
        ),
        "summary": summary,
        "image": image,
        "resolved_domain": (
            publisher_domain(
                final_url
            )
        ),
        "verification": (
            "publisher_article"
        ),
    }


# ============================================================
# UNWRAP GOOGLE NEWS
# ============================================================

def unwrap_google_news_url(
    url
):

    if not url:
        return None

    if not is_google_news_url(
        url
    ):
        return url

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=ARTICLE_TIMEOUT,
            allow_redirects=True,
        )

        final_url = response.url

        if (
            valid_http_url(
                final_url
            )
            and not is_google_news_url(
                final_url
            )
            and not is_search_engine_url(
                final_url
            )
        ):

            return final_url

    except Exception as exc:

        print(
            "Google News unwrap failed:",
            exc,
        )

    return None


# ============================================================
# BING WEB SEARCH
# ============================================================

def bing_search(
    query,
    limit=BING_RESULT_LIMIT,
):

    url = (
        "https://www.bing.com/search?"
        f"q={quote_plus(query)}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            "Bing search failed:",
            exc,
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    results = []

    for item in soup.select(
        "li.b_algo"
    ):

        a = item.find(
            "a"
        )

        if not a:
            continue

        href = a.get(
            "href"
        )

        if not href:
            continue

        title = clean_text(
            a.get_text(
                " ",
                strip=True,
            )
        )

        if not valid_http_url(
            href
        ):
            continue

        if is_search_engine_url(
            href
        ):
            continue

        snippet = ""

        paragraph = item.find(
            "p"
        )

        if paragraph:

            snippet = clean_text(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

        results.append(
            {
                "title": title,
                "url": href,
                "snippet": snippet,
            }
        )

        if len(results) >= limit:
            break

    return results


# ============================================================
# RESOLVE GOOGLE NEWS STORY
# ============================================================

def resolve_publisher_article(
    story
):

    title = normalize_title(
        story.get(
            "title",
            "",
        )
    )

    source_name = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    county = clean_text(
        story.get(
            "county",
            "",
        )
    )

    google_url = story.get(
        "url",
        "",
    )

    print("")
    print(
        "---------------- ARTICLE RESOLUTION ----------------"
    )

    print(
        "Title:",
        title,
    )

    print(
        "Source:",
        source_name,
    )

    print(
        "County:",
        county,
    )

    # --------------------------------------------------------
    # METHOD 1
    # Direct Google News redirect
    # --------------------------------------------------------

    direct = unwrap_google_news_url(
        google_url
    )

    if direct:

        print(
            "Direct publisher URL:",
            direct,
        )

        verified = (
            verify_article_candidate(
                direct,
                title,
            )
        )

        if verified:

            return verified

    # --------------------------------------------------------
    # METHOD 2
    # Controlled Bing search
    # --------------------------------------------------------

    queries = [
        f'"{title}" "{source_name}"',
        f'"{title}" {county} Kenya',
    ]

    for query in queries:

        print("")
        print(
            "Bing article search:",
            query,
        )

        results = bing_search(
            query,
            limit=BING_RESULT_LIMIT,
        )

        for result in results:

            result_url = result.get(
                "url",
                "",
            )

            if is_search_engine_url(
                result_url
            ):
                continue

            verified = (
                verify_article_candidate(
                    result_url,
                    title,
                )
            )

            if verified:

                print(
                    "PUBLISHER ARTICLE FOUND:",
                    verified["url"],
                )

                return verified

    return None


# ============================================================
# BING IMAGE URL EXTRACTION
# ============================================================

def extract_bing_image_urls(
    raw_html
):

    urls = []

    patterns = [
        r'"murl":"(https?://[^"]+)"',
        r'"turl":"(https?://[^"]+)"',
        r'\\"murl\\":\\"(https?://[^"]+)\\"',
        r'\\"turl\\":\\"(https?://[^"]+)\\"',
    ]

    for pattern in patterns:

        for match in re.findall(
            pattern,
            raw_html,
            flags=re.I,
        ):

            urls.append(
                match
            )

    soup = BeautifulSoup(
        raw_html,
        "html.parser",
    )

    for tag in soup.find_all(
        "img"
    ):

        for attr in (
            "src",
            "data-src",
            "data-murl",
            "data-sourceurl",
            "data-original",
        ):

            value = tag.get(
                attr
            )

            if value:

                urls.append(
                    value
                )

    cleaned = []

    for url in urls:

        url = html.unescape(
            str(url)
        )

        url = url.replace(
            "\\/",
            "/",
        )

        try:

            url = unquote(
                url
            )

        except Exception:
            pass

        if not valid_http_url(
            url
        ):
            continue

        host = hostname(
            url
        )

        if host == "r.bing.com":
            continue

        if host.endswith(
            ".bing.com"
        ):
            continue

        if host in (
            "bing.com",
            "www.bing.com",
        ):
            continue

        if is_google_news_url(
            url
        ):
            continue

        if is_svg_url(
            url
        ):
            continue

        if url not in cleaned:

            cleaned.append(
                url
            )

    return cleaned


# ============================================================
# BING IMAGE SEARCH
# ============================================================

def bing_image_search(
    query
):

    search_url = (
        "https://www.bing.com/images/search?"
        f"q={quote_plus(query)}"
    )

    print(
        "Image search:",
        query,
    )

    try:

        response = requests.get(
            search_url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:

        print(
            "Bing image search failed:",
            exc,
        )

        return []

    urls = extract_bing_image_urls(
        response.text
    )

    return urls[
        :MAX_BING_IMAGES
    ]


# ============================================================
# IMAGE SEARCH FALLBACK
# ============================================================

def image_search_fallback(
    story
):

    title = normalize_title(
        story.get(
            "title",
            "",
        )
    )

    county = clean_text(
        story.get(
            "county",
            "",
        )
    )

    source_name = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    print("")
    print(
        "---------------- IMAGE FALLBACK ----------------"
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # DO NOT repeat the full publisher search here.
    #
    # The caller already attempted publisher resolution.
    # We only perform a small image search.
    # --------------------------------------------------------

    image_queries = [
        f'"{title}" {county}',
        f'"{title}" Kenya',
    ]

    for query in image_queries:

        image_urls = bing_image_search(
            query
        )

        for image_url in image_urls:

            if is_search_engine_url(
                image_url
            ):
                continue

            if is_svg_url(
                image_url
            ):
                continue

            verified_image = verify_image(
                image_url
            )

            if not verified_image:
                continue

            # ------------------------------------------------
            # IMAGE ALONE IS NOT ENOUGH.
            #
            # We still require a publisher article URL.
            # ------------------------------------------------

            current_url = story.get(
                "url",
                "",
            )

            if (
                not valid_http_url(
                    current_url
                )
                or is_google_news_url(
                    current_url
                )
                or is_search_engine_url(
                    current_url
                )
            ):

                print(
                    "Image found but current "
                    "URL is not a publisher URL."
                )

                continue

            story["image"] = (
                verified_image
            )

            story["verification"] = (
                "verified_image_search"
            )

            print(
                "FINAL REAL IMAGE:",
                verified_image,
            )

            return verified_image

    return None


# ============================================================
# COUNTY RELEVANCE
# ============================================================

def county_relevance(
    story
):

    county = story.get(
        "county",
        "",
    )

    aliases = COUNTY_ALIASES.get(
        county,
        [county],
    )

    text = (
        story.get(
            "title",
            "",
        )
        + " "
        + story.get(
            "description",
            "",
        )
        + " "
        + story.get(
            "summary",
            "",
        )
    ).lower()

    score = 0

    for alias in aliases:

        if (
            alias.lower()
            in text
        ):

            score += 1

    return score


# ============================================================
# STORY SCORING
# ============================================================

def score_story(
    story
):

    title = normalize_title(
        story.get(
            "title",
            "",
        )
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    score = 0

    # --------------------------------------------------------
    # Currentness
    # --------------------------------------------------------

    published_dt = story.get(
        "published_dt"
    )

    if published_dt:

        age_hours = (
            now_utc()
            - published_dt
        ).total_seconds() / 3600

        if age_hours <= 12:

            score += 35

        elif age_hours <= 24:

            score += 28

        elif age_hours <= 48:

            score += 18

        else:

            score += 10

    # --------------------------------------------------------
    # County relevance
    # --------------------------------------------------------

    score += min(
        county_relevance(
            story
        ) * 8,
        24,
    )

    # --------------------------------------------------------
    # Article usefulness
    # --------------------------------------------------------

    if len(summary) >= 100:

        score += 10

    if len(title) >= 30:

        score += 5

    # --------------------------------------------------------
    # Important topics
    # --------------------------------------------------------

    important_words = [
        "road",
        "project",
        "hospital",
        "school",
        "market",
        "water",
        "county",
        "government",
        "governor",
        "senator",
        "mp",
        "development",
        "budget",
        "jobs",
        "investment",
        "business",
        "health",
        "education",
        "infrastructure",
        "economy",
        "security",
        "land",
        "agriculture",
    ]

    lower_text = (
        title
        + " "
        + summary
    ).lower()

    for word in important_words:

        if re.search(
            r"\b"
            + re.escape(word)
            + r"\b",
            lower_text,
        ):

            score += 2

    return score


# ============================================================
# STORY ENRICHMENT
# ============================================================

def enrich_story(
    candidate
):

    title = normalize_title(
        candidate.get(
            "title",
            "",
        )
    )

    if not title:
        return None

    candidate["title"] = title

    # --------------------------------------------------------
    # Publisher resolution
    # --------------------------------------------------------

    resolved = (
        resolve_publisher_article(
            candidate
        )
    )

    if resolved:

        candidate["url"] = (
            resolved["url"]
        )

        if resolved.get(
            "summary"
        ):

            candidate["summary"] = (
                resolved[
                    "summary"
                ]
            )

        candidate[
            "resolved_domain"
        ] = (
            resolved[
                "resolved_domain"
            ]
        )

        if resolved.get(
            "image"
        ):

            candidate["image"] = (
                resolved["image"]
            )

        candidate[
            "verification"
        ] = "publisher_article"

    # --------------------------------------------------------
    # RSS image
    # --------------------------------------------------------

    if not candidate.get(
        "image"
    ):

        rss_image = candidate.get(
            "rss_image"
        )

        if rss_image:

            print(
                "Checking RSS image..."
            )

            verified_rss_image = (
                verify_image(
                    rss_image
                )
            )

            if verified_rss_image:

                candidate["image"] = (
                    verified_rss_image
                )

                print(
                    "REAL RSS IMAGE FOUND:",
                    verified_rss_image,
                )

    # --------------------------------------------------------
    # Bing image fallback
    # --------------------------------------------------------

    if not candidate.get(
        "image"
    ):

        fallback_image = (
            image_search_fallback(
                candidate
            )
        )

        if fallback_image:

            candidate["image"] = (
                fallback_image
            )

            candidate[
                "verification"
            ] = (
                "verified_image_search"
            )

    # --------------------------------------------------------
    # Final URL checks
    # --------------------------------------------------------

    final_url = candidate.get(
        "url",
        "",
    )

    if not valid_http_url(
        final_url
    ):

        print(
            "Rejected: invalid final "
            "article URL."
        )

        return None

    if is_google_news_url(
        final_url
    ):

        print(
            "Rejected: final URL is "
            "Google News."
        )

        return None

    if is_search_engine_url(
        final_url
    ):

        print(
            "Rejected: final URL is "
            "search engine."
        )

        return None

    # --------------------------------------------------------
    # Final image check
    # --------------------------------------------------------

    final_image = candidate.get(
        "image",
        "",
    )

    if not final_image:

        print(
            "Rejected: no real article image."
        )

        return None

    verified_final_image = (
        verify_image(
            final_image
        )
    )

    if not verified_final_image:

        print(
            "Rejected: final image "
            "validation failed."
        )

        return None

    candidate["image"] = (
        verified_final_image
    )

    # --------------------------------------------------------
    # Domain
    # --------------------------------------------------------

    candidate[
        "resolved_domain"
    ] = publisher_domain(
        final_url
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    candidate["summary"] = clean_text(
        candidate.get(
            "summary",
            "",
        )
    )

    if len(
        candidate["summary"]
    ) < 60:

        candidate["summary"] = (
            clean_text(
                candidate.get(
                    "description",
                    "",
                )
            )
        )

    if len(
        candidate["summary"]
    ) < 60:

        candidate["summary"] = (
            candidate["title"]
        )

    # --------------------------------------------------------
    # Score + ID
    # --------------------------------------------------------

    candidate["score"] = (
        score_story(
            candidate
        )
    )

    candidate["id"] = (
        story_hash(
            candidate["title"]
        )
    )

    return candidate


# ============================================================
# DISCOVER STORIES
# ============================================================

def collect_candidates():

    start_time = time.time()

    all_candidates = []

    feeds = build_feed_urls()

    print("")
    print(
        "============================================================"
    )

    print(
        "COLLECTING RIFT VALLEY STORIES"
    )

    print(
        "============================================================"
    )

    print(
        "RSS feeds:",
        len(feeds),
    )

    for feed in feeds:

        county = feed[
            "county"
        ]

        url = feed[
            "url"
        ]

        stories = parse_feed(
            url,
            county,
        )

        print(
            f"{county}: "
            f"{len(stories)} recent items"
        )

        all_candidates.extend(
            stories
        )

        time.sleep(
            RSS_DELAY
        )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    unique = {}

    for story in all_candidates:

        key = normalize_title(
            story.get(
                "title",
                "",
            )
        ).lower()

        if not key:
            continue

        if key not in unique:

            unique[key] = story

    candidates = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Preliminary scoring
    # --------------------------------------------------------

    for candidate in candidates:

        candidate[
            "_pre_score"
        ] = score_story(
            candidate
        )

    candidates.sort(
        key=lambda x: x.get(
            "_pre_score",
            0,
        ),
        reverse=True,
    )

    elapsed = (
        time.time()
        - start_time
    )

    print("")
    print(
        "Candidate collection complete."
    )

    print(
        "Unique candidates:",
        len(candidates),
    )

    print(
        "Collection time:",
        round(
            elapsed,
            2,
        ),
        "seconds",
    )

    return candidates


# ============================================================
# SELECT VERIFIED STORY
# ============================================================

def select_story():

    total_start = time.time()

    candidates = (
        collect_candidates()
    )

    print("")
    print(
        "============================================================"
    )

    print(
        f"VERIFYING TOP "
        f"{min(len(candidates), MAX_CANDIDATES_TO_VERIFY)} "
        f"CANDIDATES"
    )

    print(
        "============================================================"
    )

    if not candidates:

        raise RuntimeError(
            "No recent Rift Valley "
            "stories were found."
        )

    # --------------------------------------------------------
    # CRITICAL PERFORMANCE LIMIT
    # --------------------------------------------------------

    candidates = candidates[
        :MAX_CANDIDATES_TO_VERIFY
    ]

    verified = []

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        candidate_start = (
            time.time()
        )

        print("")
        print(
            "============================================================"
        )

        print(
            f"CHECKING CANDIDATE "
            f"{index}/{len(candidates)}"
        )

        print(
            "Title:",
            candidate.get(
                "title",
                "",
            ),
        )

        print(
            "County:",
            candidate.get(
                "county",
                "",
            ),
        )

        print(
            "Source:",
            candidate.get(
                "source_name",
                "",
            ),
        )

        print(
            "Pre-score:",
            candidate.get(
                "_pre_score",
                0,
            ),
        )

        print(
            "============================================================"
        )

        try:

            enriched = enrich_story(
                candidate
            )

        except Exception as exc:

            print(
                "Candidate failed:",
                exc,
            )

            traceback.print_exc()

            enriched = None

        candidate
