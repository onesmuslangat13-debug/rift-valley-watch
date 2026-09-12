import os
import re
import json
import time
import html
import hashlib
import traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS SELECTION + VERIFICATION PIPELINE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

STORY_FILE = os.path.join(DATA_DIR, "story.json")
SCRIPT_FILE = os.path.join(DATA_DIR, "script.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


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
        "Kaplong",
        "Chebunyo",
    ],
    "Kericho": [
        "Kericho",
        "Litein",
        "Kipkelion",
        "Londiani",
        "Ainamoi",
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
        "Nandi Hills",
        "Mosoriot",
        "Aldai",
    ],
    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Moiben",
        "Turbo",
        "Soy",
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo Marakwet",
        "Elgeyo-Marakwet",
        "Iten",
        "Keiyo",
        "Marakwet",
        "Kabarnet",
    ],
    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Pokot",
        "Sigor",
    ],
    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Ololulunga",
        "Transmara",
    ],
}

RSS_TIMEOUT = 10
ARTICLE_TIMEOUT = 12
IMAGE_TIMEOUT = 8
SEARCH_TIMEOUT = 10

MAX_AGE_HOURS = 96
MAX_CANDIDATES_TO_VERIFY = 15
MAX_VERIFIED_TO_COMPARE = 5

BING_RESULT_LIMIT = 8
MAX_BING_IMAGES = 10
MAX_IMAGE_CHECKS = 8

RSS_DELAY = 0.15

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 "
    "RiftValleyWatch/2.0"
)


# ============================================================
# TEXT AND URL HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, bytes):
        value = value.decode(
            "utf-8",
            errors="ignore",
        )

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

    value = BeautifulSoup(
        value,
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_title(title):
    title = clean_text(title).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        "",
        title,
    )

    return re.sub(
        r"\s+",
        " ",
        title,
    ).strip()


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return (
            parsed.scheme.lower() in {
                "http",
                "https",
            }
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def hostname(url):
    try:
        return urlparse(
            url
        ).netloc.lower().split(":")[0]
    except Exception:
        return ""


def is_search_engine_url(url):
    host = hostname(url)

    blocked = [
        "google.com",
        "google.co.ke",
        "news.google.com",
        "bing.com",
        "bing.net",
        "yahoo.com",
        "duckduckgo.com",
        "search.brave.com",
        "r.bing.com",
    ]

    return any(
        host == domain
        or host.endswith("." + domain)
        for domain in blocked
    )


def is_svg_url(url):
    if not url:
        return True

    lower = url.lower()

    return (
        ".svg" in lower
        or "image/svg" in lower
        or lower.startswith(
            "data:image/svg"
        )
    )


def now_utc():
    return datetime.now(
        timezone.utc
    )


def story_hash(title, url):
    raw = (
        normalize_title(title)
        + "|"
        + clean_text(url).lower()
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value

    else:
        text = clean_text(value)

        if not text:
            return None

        dt = None

        try:
            parsed = feedparser._parse_date(text)

            if parsed:
                dt = datetime(
                    parsed.tm_year,
                    parsed.tm_mon,
                    parsed.tm_mday,
                    parsed.tm_hour,
                    parsed.tm_min,
                    parsed.tm_sec,
                    tzinfo=timezone.utc,
                )

        except Exception:
            dt = None

        if dt is None:
            formats = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d %B %Y",
                "%B %d, %Y",
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

                    break

                except Exception:
                    continue

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def is_recent(
    value,
    allow_missing=True,
):
    dt = parse_date(value)

    if dt is None:
        return allow_missing

    age = now_utc() - dt

    return age <= timedelta(
        hours=MAX_AGE_HOURS
    )


# ============================================================
# HTTP
# ============================================================

def get_response(
    url,
    timeout,
):
    return requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
        },
        timeout=timeout,
        allow_redirects=True,
    )


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


def parse_feed(feed_url):
    try:
        response = get_response(
            feed_url,
            RSS_TIMEOUT,
        )

        response.raise_for_status()

        parsed = feedparser.parse(
            response.content
        )

        return parsed

    except Exception as exc:
        print(
            f"RSS request failed: {exc}"
        )

        return None


def get_rss_media_image(entry):
    candidates = []

    for item in entry.get(
        "media_content",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("url", "")
            )

    for item in entry.get(
        "media_thumbnail",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("url", "")
            )

    for item in entry.get(
        "enclosures",
        [],
    ):
        if isinstance(item, dict):
            candidates.append(
                item.get("href", "")
            )

    for url in candidates:
        if (
            valid_http_url(url)
            and not is_svg_url(url)
            and not is_search_engine_url(url)
        ):
            return url

    return ""


# ============================================================
# GOOGLE NEWS URL RESOLUTION
# ============================================================

def unwrap_google_news_url(url):
    if not valid_http_url(url):
        return ""

    if not is_search_engine_url(url):
        return url

    try:
        response = get_response(
            url,
            SEARCH_TIMEOUT,
        )

        final_url = response.url

        if (
            valid_http_url(final_url)
            and not is_search_engine_url(final_url)
        ):
            return final_url

    except Exception:
        pass

    return ""


# ============================================================
# BING WEB SEARCH
# ============================================================

def bing_search(query):
    results = []

    try:
        url = (
            "https://www.bing.com/search?"
            f"q={quote_plus(query)}"
            "&count=10"
            "&setlang=en-KE"
        )

        response = get_response(
            url,
            SEARCH_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for item in soup.select(
            "li.b_algo"
        ):
            anchor = item.select_one(
                "h2 a"
            )

            if not anchor:
                continue

            title = clean_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

            url = anchor.get(
                "href",
                "",
            )

            caption = item.select_one(
                ".b_caption p"
            )

            summary = ""

            if caption:
                summary = clean_text(
                    caption.get_text(
                        " ",
                        strip=True,
                    )
                )

            if (
                not title
                or not valid_http_url(url)
                or is_search_engine_url(url)
            ):
                continue

            results.append(
                {
                    "title": title,
                    "url": url,
                    "summary": summary,
                }
            )

            if len(results) >= BING_RESULT_LIMIT:
                break

    except Exception as exc:
        print(
            f"Bing search failed: {exc}"
        )

    return results


# ============================================================
# IMAGE EXTRACTION AND VALIDATION
# ============================================================

def extract_image_candidates(
    soup,
    base_url,
):
    candidates = []

    def add(value):
        if not value:
            return

        value = html.unescape(
            str(value)
        ).strip()

        value = urljoin(
            base_url,
            value,
        )

        if not valid_http_url(value):
            return

        if is_svg_url(value):
            return

        if is_search_engine_url(value):
            return

        if value not in candidates:
            candidates.append(value)

    for meta in soup.find_all(
        "meta"
    ):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:
            add(
                meta.get(
                    "content",
                    "",
                )
            )

    for link in soup.find_all(
        "link"
    ):
        rel = link.get(
            "rel",
            [],
        )

        if isinstance(
            rel,
            str,
        ):
            rel = [rel]

        rel = [
            str(item).lower()
            for item in rel
        ]

        if "image_src" in rel:
            add(
                link.get(
                    "href",
                    "",
                )
            )

    for image in soup.find_all(
        "img"
    ):
        for attribute in [
            "src",
            "data-src",
            "data-original",
            "data-image",
            "data-lazy-src",
            "data-lazy",
        ]:
            add(
                image.get(
                    attribute,
                    "",
                )
            )

    return candidates


def verify_image(url):
    if not valid_http_url(url):
        return False

    if is_svg_url(url):
        return False

    if is_search_engine_url(url):
        return False

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/*,*/*;q=0.8",
            },
            timeout=IMAGE_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers
            .get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if (
            "image/" not in content_type
            or "svg" in content_type
        ):
            return False

        data = response.content

        if len(data) < 5000:
            return False

        valid_signatures = [
            data[:3] == b"\xff\xd8\xff",
            data[:8] == b"\x89PNG\r\n\x1a\n",
            (
                len(data) > 12
                and data[:4] == b"RIFF"
                and data[8:12] == b"WEBP"
            ),
            data[:6] in {
                b"GIF87a",
                b"GIF89a",
            },
        ]

        return any(
            valid_signatures
        )

    except Exception:
        return False


def first_valid_image(
    candidates,
):
    for index, url in enumerate(
        candidates[:MAX_IMAGE_CHECKS],
        start=1,
    ):
        print(
            f"Checking image "
            f"{index}/{min(len(candidates), MAX_IMAGE_CHECKS)}"
        )

        if verify_image(url):
            print(
                "VALID REAL IMAGE FOUND"
            )

            return url

    return ""


def extract_bing_image_urls(
    text,
):
    urls = []

    patterns = [
        r'"murl":"(.*?)"',
        r'"turl":"(.*?)"',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.I,
        )

        for value in matches:
            value = (
                value
                .replace("\\/", "/")
                .replace('\\"', '"')
            )

            if (
                valid_http_url(value)
                and not is_svg_url(value)
                and not is_search_engine_url(value)
                and value not in urls
            ):
                urls.append(value)

    return urls


def bing_image_search(query):
    try:
        url = (
            "https://www.bing.com/images/search?"
            f"q={quote_plus(query)}"
            "&form=HDRSC2"
        )

        response = get_response(
            url,
            SEARCH_TIMEOUT,
        )

        response.raise_for_status()

        return extract_bing_image_urls(
            response.text
        )[:MAX_BING_IMAGES]

    except Exception as exc:
        print(
            f"Bing image search failed: {exc}"
        )

        return []


def image_search_fallback(
    title,
    source_name,
):
    queries = [
        title,
        f"{title} {source_name}",
    ]

    for query in queries:
        print(
            "Image fallback search:",
            query,
        )

        urls = bing_image_search(
            query
        )

        image = first_valid_image(
            urls
        )

        if image:
            return image

    return ""


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def fetch_article(url):
    if not valid_http_url(url):
        return None

    try:
        response = get_response(
            url,
            ARTICLE_TIMEOUT,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "Content-Type",
                "",
            )
            .lower()
        )

        if "html" not in content_type:
            return None

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        return {
            "url": response.url,
            "html": response.text,
            "soup": soup,
        }

    except Exception as exc:
        print(
            f"Article fetch failed: {exc}"
        )

        return None


def extract_article_summary(
    soup,
    fallback="",
):
    selectors = [
        "article p",
        "main p",
        "[itemprop='articleBody'] p",
        ".article-body p",
        ".story-body p",
        ".entry-content p",
        ".post-content p",
    ]

    paragraphs = []

    for selector in selectors:
        found = soup.select(
            selector
        )

        if not found:
            continue

        for paragraph in found:
            text = clean_text(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                len(text) >= 45
                and text not in paragraphs
            ):
                paragraphs.append(
                    text
                )

        if paragraphs:
            break

    if not paragraphs:
        meta = soup.find(
            "meta",
            attrs={
                "name": "description"
            },
        )

        if meta:
            paragraphs.append(
                clean_text(
                    meta.get(
                        "content",
                        "",
                    )
                )
            )

    if not paragraphs:
        return clean_text(
            fallback
        )[:1800]

    return clean_text(
        " ".join(paragraphs)
    )[:1800]


def extract_published_date(
    soup,
):
    names = [
        "article:published_time",
        "date",
        "pubdate",
        "publishdate",
        "timestamp",
    ]

    for name in names:

        meta = soup.find(
            "meta",
            attrs={
                "property": name
            },
        )

        if not meta:
            meta = soup.find(
                "meta",
                attrs={
                    "name": name
                },
            )

        if meta:
            value = clean_text(
                meta.get(
                    "content",
                    "",
                )
            )

            if value:
                return value

    time_tag = soup.find(
        "time"
    )

    if time_tag:
        return (
            time_tag.get(
                "datetime",
                "",
            )
            or clean_text(
                time_tag.get_text(
                    " ",
                    strip=True,
                )
            )
        )

    return ""


# ============================================================
# COUNTY RELEVANCE
# ============================================================

def county_relevance(
    title,
    summary,
    county,
):
    text = (
        normalize_title(title)
        + " "
        + normalize_title(summary)
    )

    score = 0

    county_words = normalize_title(
        county
    ).split()

    if county_words and all(
        word in text
        for word in county_words
    ):
        score += 30

    for alias in COUNTY_ALIASES.get(
        county,
        [],
    ):
        alias_words = normalize_title(
            alias
        ).split()

        if alias_words and all(
            word in text
            for word in alias_words
        ):
            score += 20
            break

    return score


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def verify_article_candidate(
    title,
    url,
    county,
    fallback_summary="",
):
    resolved_url = unwrap_google_news_url(
        url
    )

    if not resolved_url:
        return None

    article = fetch_article(
        resolved_url
    )

    if not article:
        return None

    soup = article["soup"]

    page_title = ""

    og_title = soup.find(
        "meta",
        property="og:title",
    )

    if og_title:
        page_title = clean_text(
            og_title.get(
                "content",
                "",
            )
        )

    if not page_title:
        title_tag = soup.find(
            "title"
        )

        if title_tag:
            page_title = clean_text(
                title_tag.get_text(
                    " ",
                    strip=True,
                )
            )

    if not page_title:
        page_title = title

    summary = extract_article_summary(
        soup,
        fallback_summary,
    )

    if len(summary) < 80:
        return None

    relevance = county_relevance(
        page_title,
        summary,
        county,
    )

    if relevance < 10:
        print(
            "Rejected: insufficient "
            "county relevance."
        )

        return None

    source_host = hostname(
        article["url"]
    )

    source_name = source_host

    if source_name.startswith(
        "www."
    ):
        source_name = source_name[4:]

    image_candidates = (
        extract_image_candidates(
            soup,
            article["url"],
        )
    )

    image = first_valid_image(
        image_candidates
    )

    if not image:
        image = image_search_fallback(
            page_title,
            source_name,
        )

    if not image:
        print(
            "Rejected: no valid image."
        )

        return None

    published = extract_published_date(
        soup
    )

    return {
        "title": page_title,
        "summary": summary,
        "article_text": summary,
        "url": article["url"],
        "resolved_url": article["url"],
        "source_name": source_name,
        "source": source_name,
        "published": published,
        "county": county,
        "image": image,
        "image_url": image,
    }


def enrich_story(
    entry,
    county,
):
    title = clean_text(
        entry.get(
            "title",
            "",
        )
    )

    url = clean_text(
        entry.get(
            "link",
            "",
        )
    )

    summary = clean_text(
        entry.get(
            "summary",
            entry.get(
                "description",
                "",
            ),
        )
    )

    if not title or not url:
        return None

    return verify_article_candidate(
        title,
        url,
        county,
        summary,
    )


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):
    title = story.get(
        "title",
        "",
    )

    summary = story.get(
        "summary",
        "",
    )

    county = story.get(
        "county",
        "",
    )

    source = story.get(
        "source_name",
        "",
    ).lower()

    text = (
        title.lower()
        + " "
        + summary.lower()
    )

    score = county_relevance(
        title,
        summary,
        county,
    )

    keywords = [
        "government",
        "development",
        "road",
        "hospital",
        "school",
        "water",
        "project",
        "budget",
        "investment",
        "business",
        "jobs",
        "health",
        "education",
        "security",
        "court",
        "governor",
        "minister",
        "president",
        "funding",
        "construction",
    ]

    for keyword in keywords:
        if keyword in text:
            score += 3

    if story.get("image"):
        score += 25

    if story.get("article_text"):
        score += 20

    if source:
        score += 10

    trusted_sources = [
        "nation.africa",
        "standardmedia.co.ke",
        "citizen.digital",
        "the-star.co.ke",
        "capitalfm.co.ke",
        "kbc.co.ke",
        "kenyanews.go.ke",
        "tuko.co.ke",
        "businessdailyafrica.com",
        "bomet.go.ke",
        "kericho.go.ke",
        "nakuru.go.ke",
        "nandi.go.ke",
        "uasingishu.go.ke",
        "narok.go.ke",
    ]

    if any(
        item in source
        for item in trusted_sources
    ):
        score += 20

    return score


# ============================================================
# CANDIDATE COLLECTION
# ============================================================

def collect_candidates():
    candidates = []

    seen_titles = set()
    seen_urls = set()

    print()
    print("=" * 70)
    print("COLLECTING RIFT VALLEY NEWS")
    print("=" * 70)

    rss_queries = []

    for county in COUNTIES:

        rss_queries.extend(
            [
                (
                    county,
                    f'"{county}" Kenya',
                ),
                (
                    county,
                    f'"{county}" latest Kenya',
                ),
                (
                    county,
                    f'"{county}" development Kenya',
                ),
                (
                    county,
                    f'"{county}" government Kenya',
                ),
            ]
        )

        for alias in COUNTY_ALIASES.get(
            county,
            [],
        )[:5]:

            if alias.lower() == county.lower():
                continue

            rss_queries.append(
                (
                    county,
                    f'"{alias}" Kenya',
                )
            )

    print(
        f"RSS queries: {len(rss_queries)}"
    )

    for index, (
        county,
        query,
    ) in enumerate(
        rss_queries,
        start=1,
    ):

        print(
            f"[RSS {index}/{len(rss_queries)}] "
            f"{query}"
        )

        parsed = parse_feed(
            google_news_rss(query)
        )

        if not parsed:
            continue

        for entry in getattr(
            parsed,
            "entries",
            [],
        ):

            title = clean_text(
                entry.get(
                    "title",
                    "",
                )
            )

            link = clean_text(
                entry.get(
                    "link",
                    "",
                )
            )

            published = (
                entry.get(
                    "published",
                    "",
                )
                or entry.get(
                    "updated",
                    "",
                )
            )

            if not title or not link:
                continue

            # Do not reject missing dates.
            if published and not is_recent(
                published
            ):
                continue

            normalized = normalize_title(
                title
            )

            if normalized in seen_titles:
                continue

            resolved = unwrap_google_news_url(
                link
            )

            if not resolved:
                continue

            if resolved in seen_urls:
                continue

            seen_titles.add(
                normalized
            )

            seen_urls.add(
                resolved
            )

            candidates.append(
                {
                    "entry": entry,
                    "county": county,
                    "title": title,
                    "url": link,
                    "published": published,
                    "summary": clean_text(
                        entry.get(
                            "summary",
                            entry.get(
                                "description",
                                "",
                            ),
                        )
                    ),
                }
            )

        time.sleep(
            RSS_DELAY
        )

    print(
        f"RSS candidates: {len(candidates)}"
    )

    # ========================================================
    # BING FALLBACK
    # ========================================================

    if len(candidates) < 12:

        print()
        print("=" * 70)
        print("RUNNING BING DISCOVERY FALLBACK")
        print("=" * 70)

        bing_queries = []

        for county in COUNTIES:

            bing_queries.extend(
                [
                    (
                        county,
                        f"{county} Kenya latest news",
                    ),
                    (
                        county,
                        f"{county} Kenya development news",
                    ),
                    (
                        county,
                        f"{county} Kenya government news",
                    ),
                ]
            )

            for alias in COUNTY_ALIASES.get(
                county,
                [],
            )[:3]:

                bing_queries.append(
                    (
                        county,
                        f"{alias} Kenya latest news",
                    )
                )

        for index, (
            county,
            query,
        ) in enumerate(
            bing_queries,
            start=1,
        ):

            print(
                f"[BING {index}/{len(bing_queries)}] "
                f"{query}"
            )

            for result in bing_search(
                query
            ):

                title = clean_text(
                    result.get(
                        "title",
                        "",
                    )
                )

                url = clean_text(
                    result.get(
                        "url",
                        "",
                    )
                )

                summary = clean_text(
                    result.get(
                        "summary",
                        "",
                    )
                )

                if not title or not url:
                    continue

                normalized = normalize_title(
                    title
                )

                if normalized in seen_titles:
                    continue

                if url in seen_urls:
                    continue

                seen_titles.add(
                    normalized
                )

                seen_urls.add(
                    url
                )

                candidates.append(
                    {
                        "entry": {
                            "title": title,
                            "link": url,
                            "summary": summary,
                            "published": "",
                        },
                        "county": county,
                        "title": title,
                        "url": url,
                        "published": "",
                        "summary": summary,
                    }
                )

    print()
    print("=" * 70)
    print(
        f"TOTAL CANDIDATES FOUND: "
        f"{len(candidates)}"
    )
    print("=" * 70)

    for index, candidate in enumerate(
        candidates[:25],
        start=1,
    ):
        print(
            f"{index}. "
            f"[{candidate.get('county')}] "
            f"{candidate.get('title')}"
        )

    return candidates


# ============================================================
# SELECT ONE STORY
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError(
            "No Rift Valley candidates found "
            "from RSS or Bing discovery."
        )

    print()
    print("=" * 70)
    print("VERIFYING PUBLISHER ARTICLES")
    print("=" * 70)

    verified = []

    for index, candidate in enumerate(
        candidates[:MAX_CANDIDATES_TO_VERIFY],
        start=1,
    ):

        print()
        print("-" * 70)
        print(
            f"VERIFYING "
            f"{index}/{min(len(candidates), MAX_CANDIDATES_TO_VERIFY)}"
        )

        print(
            f"County: {candidate.get('county')}"
        )

        print(
            f"Title: {candidate.get('title')}"
        )

        try:

            story = enrich_story(
                candidate.get(
                    "entry",
                    {},
                ),
                candidate.get(
                    "county",
                    "",
                ),
            )

            if not story:
                print(
                    "REJECTED."
                )
                continue

            story["score"] = score_story(
                story
            )

            verified.append(
                story
            )

            print(
                "VERIFIED:",
                story.get("title"),
            )

            print(
                "Score:",
                story.get("score"),
            )

            if len(verified) >= MAX_VERIFIED_TO_COMPARE:
                break

        except Exception as exc:
            print(
                f"Verification error: {exc}"
            )
            traceback.print_exc()

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking available candidates."
        )

    verified.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    story = verified[0]

    story["story_id"] = story_hash(
        story.get(
            "title",
            "",
        ),
        story.get(
            "url",
            "",
        ),
    )

    story["selected_at"] = (
        now_utc().isoformat()
    )

    narration = (
        f"Here is the latest update from "
        f"{story.get('county', 'the Rift Valley')}. "
        f"{story.get('title', '')}. "
        f"{story.get('summary', '')} "
        f"The development is being watched for "
        f"its impact on residents, businesses "
        f"and the wider region. "
        f"This report comes from "
        f"{story.get('source_name', 'the publisher')}."
    )

    story["narration"] = clean_text(
        narration
    )

    print()
    print("=" * 70)
    print("ONE STORY SELECTED")
    print("=" * 70)

    print(
        f"Title: {story.get('title')}"
    )

    print(
        f"County: {story.get('county')}"
    )

    print(
        f"Source: {story.get('source_name')}"
    )

    print(
        f"Score: {story.get('score')}"
    )

    return story


# ============================================================
# SCRIPT
# ============================================================

def build_script(story):
    title = clean_text(
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

    county = clean_text(
        story.get(
            "county",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    narration = clean_text(
        story.get(
            "narration",
            "",
        )
    )

    if not narration:
        narration = clean_text(
            f"Here is the latest update from "
            f"{county}. "
            f"{title}. "
            f"{summary}"
        )

    return {
        "title": title,
        "county": county,
        "source": source,
        "summary": summary,
        "narration": narration,
        "segments": [
            {
                "label": "BREAKING",
                "text": title,
            },
            {
                "label": "WHAT WE KNOW",
                "text": summary,
            },
            {
                "label": "WHY IT MATTERS",
                "text": (
                    "The development is being "
                    "watched for its impact on "
                    "residents, services, "
                    "businesses and the wider region."
                ),
            },
            {
                "label": "SOURCE",
                "text": source,
            },
        ],
    }


# ============================================================
# FILE WRITING
# ============================================================

def write_json(
    path,
    data,
):
    temporary = path + ".tmp"

    with open(
        temporary,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temporary,
        path,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("AUTOMATED NEWS PIPELINE")
    print("=" * 70)

    story = select_story()

    script = build_script(
        story
    )

    write_json(
        STORY_FILE,
        story,
    )

    write_json(
        SCRIPT_FILE,
        script,
    )

    print(
        f"Story saved: {STORY_FILE}"
    )

    print(
        f"Script saved: {SCRIPT_FILE}"
    )

    from rift_valley_video_generator import (
        generate_video,
    )

    result = generate_video(
        story,
        script,
    )

    print()
    print("=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)

    print(
        f"Video: {result.get('output')}"
    )

    print(
        f"Duration: {result.get('duration'):.2f}s"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print()
        print("=" * 70)
        print("PIPELINE FAILED")
        print("=" * 70)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        traceback.print_exc()

        raise
