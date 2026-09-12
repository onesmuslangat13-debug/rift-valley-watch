# ============================================================
# RIFT VALLEY WATCH
# Automated News Selection + Verification + Video Generation
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
)

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

BRAND = "Rift Valley Watch"

OUTPUT_DIR = "data"
STORY_FILE = os.path.join(
    OUTPUT_DIR,
    "story.json",
)
SCRIPT_FILE = os.path.join(
    OUTPUT_DIR,
    "script.json",
)

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
        "Mulot",
    ],
    "Kericho": [
        "Kericho",
        "Litein",
        "Londiani",
        "Kipkelion",
        "Ainamoi",
    ],
    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
        "Bahati",
        "Rongai",
    ],
    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Nandi Hills",
        "Mosop",
        "Aldai",
        "Chesumei",
    ],
    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Turbo",
        "Kesses",
        "Moiben",
        "Soy",
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Iten",
        "Kapsowar",
        "Keiyo",
        "Marakwet",
        "Chepkorio",
    ],
    "West Pokot": [
        "West Pokot",
        "Kapenguria",
        "Kacheliba",
        "Pokot",
        "Sigor",
        "Chepareria",
    ],
    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Ololulunga",
        "Emurua Dikirr",
    ],
}


RSS_TIMEOUT = 8
ARTICLE_TIMEOUT = 10
IMAGE_TIMEOUT = 8
SEARCH_TIMEOUT = 8

MAX_AGE_HOURS = 72
MAX_CANDIDATES_TO_VERIFY = 10

BING_RESULT_LIMIT = 5
MAX_IMAGE_CHECKS = 6
MAX_BING_IMAGES = 8

RSS_DELAY = 0.15

USER_AGENT = (
    "Mozilla/5.0 (compatible; "
    "RiftValleyWatch/1.0)"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
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
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_title(title):
    title = clean_text(
        title
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
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
    if not url:
        return ""

    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )

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
        "news.google.com" in host
        or (
            "google.com" in host
            and "/search" in url
        )
    )


def is_search_engine_url(url):
    host = hostname(url)

    return any(
        domain in host
        for domain in [
            "bing.com",
            "google.com",
            "search.yahoo.com",
            "duckduckgo.com",
        ]
    )


def is_svg_url(url):
    if not url:
        return False

    return ".svg" in url.lower()


def now_utc():
    return datetime.now(
        timezone.utc
    )


def parse_date(value):
    if not value:
        return None

    if isinstance(
        value,
        datetime,
    ):
        dt = value

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    value = str(value).strip()

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

    try:
        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
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


def is_recent(value):
    dt = parse_date(
        value
    )

    if not dt:
        return False

    age = now_utc() - dt

    return (
        timedelta(hours=-2)
        <= age
        <= timedelta(
            hours=MAX_AGE_HOURS
        )
    )


def title_similarity(
    a,
    b,
):
    a_words = set(
        normalize_title(a).split()
    )

    b_words = set(
        normalize_title(b).split()
    )

    if not a_words or not b_words:
        return 0.0

    intersection = len(
        a_words.intersection(
            b_words
        )
    )

    union = len(
        a_words.union(
            b_words
        )
    )

    if union == 0:
        return 0.0

    return intersection / union


def story_hash(
    title,
    url="",
):
    raw = (
        normalize_title(title)
        + "|"
        + clean_text(url)
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:16]


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_rss(
    query
):
    encoded = quote_plus(
        query
    )

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def build_feed_urls():
    urls = []

    for county in COUNTIES:

        queries = [
            f'"{county}" Kenya',
            f'"{county}" development government',
        ]

        for query in queries:
            urls.append(
                google_news_rss(
                    query
                )
            )

    return urls


# ============================================================
# RSS
# ============================================================

def parse_feed(
    feed_url
):
    try:

        response = requests.get(
            feed_url,
            headers=HEADERS,
            timeout=RSS_TIMEOUT,
        )

        response.raise_for_status()

        return feedparser.parse(
            response.content
        )

    except Exception as exc:

        print(
            f"RSS failed: "
            f"{feed_url} -> {exc}"
        )

        return None


def get_rss_media_image(
    entry
):
    candidates = []

    for item in entry.get(
        "media_content",
        [],
    ):

        if isinstance(
            item,
            dict,
        ):

            url = item.get(
                "url"
            )

            if url:
                candidates.append(
                    url
                )

    for item in entry.get(
        "media_thumbnail",
        [],
    ):

        if isinstance(
            item,
            dict,
        ):

            url = item.get(
                "url"
            )

            if url:
                candidates.append(
                    url
                )

    for link in entry.get(
        "links",
        [],
    ):

        if not isinstance(
            link,
            dict,
        ):
            continue

        href = link.get(
            "href",
            "",
        )

        content_type = link.get(
            "type",
            "",
        )

        if (
            href
            and "image"
            in content_type.lower()
        ):
            candidates.append(
                href
            )

    description = (
        entry.get("summary")
        or entry.get("description")
        or ""
    )

    soup = BeautifulSoup(
        description,
        "html.parser",
    )

    for img in soup.find_all(
        "img"
    ):

        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-original")
        )

        if src:
            candidates.append(
                src
            )

    return candidates


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(
    soup,
    article_url,
):
    candidates = []

    for meta in soup.find_all(
        "meta"
    ):

        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = (
            meta.get("content")
            or ""
        ).strip()

        if not content:
            continue

        if prop in (
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        ):

            candidates.append(
                urljoin(
                    article_url,
                    content,
                )
            )

    for link in soup.find_all(
        "link"
    ):

        href = link.get(
            "href"
        )

        if not href:
            continue

        rel = " ".join(
            link.get(
                "rel",
                [],
            )
        ).lower()

        if (
            "image_src" in rel
            or "image" in rel
        ):

            candidates.append(
                urljoin(
                    article_url,
                    href,
                )
            )

    for img in soup.find_all(
        "img"
    ):

        sources = [
            img.get("src"),
            img.get("data-src"),
            img.get("data-original"),
            img.get("data-lazy-src"),
        ]

        for src in sources:

            if src:
                candidates.append(
                    urljoin(
                        article_url,
                        src,
                    )
                )

        srcset = img.get(
            "srcset"
        )

        if srcset:

            for item in srcset.split(
                ","
            ):

                item = item.strip()

                if not item:
                    continue

                src = item.split()[0]

                candidates.append(
                    urljoin(
                        article_url,
                        src,
                    )
                )

    # JSON-LD
    for script in soup.find_all(
        "script",
        type="application/ld+json",
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

        def inspect(
            obj
        ):

            if isinstance(
                obj,
                dict,
            ):

                image = obj.get(
                    "image"
                )

                if isinstance(
                    image,
                    str,
                ):

                    candidates.append(
                        urljoin(
                            article_url,
                            image,
                        )
                    )

                elif isinstance(
                    image,
                    dict,
                ):

                    url = image.get(
                        "url"
                    )

                    if url:
                        candidates.append(
                            urljoin(
                                article_url,
                                url,
                            )
                        )

                elif isinstance(
                    image,
                    list,
                ):

                    for item in image:

                        if isinstance(
                            item,
                            str,
                        ):

                            candidates.append(
                                urljoin(
                                    article_url,
                                    item,
                                )
                            )

                for value in obj.values():
                    inspect(value)

            elif isinstance(
                obj,
                list,
            ):

                for item in obj:
                    inspect(item)

        inspect(data)

    result = []
    seen = set()

    for url in candidates:

        if not valid_http_url(
            url
        ):
            continue

        if is_svg_url(
            url
        ):
            continue

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


# ============================================================
# IMAGE VERIFICATION
# ============================================================

def verify_image(
    image_url,
    referer=None,
):
    if not valid_http_url(
        image_url
    ):
        return False

    if is_svg_url(
        image_url
    ):
        return False

    headers = dict(
        HEADERS
    )

    if referer:
        headers["Referer"] = referer

    try:

        response = requests.get(
            image_url,
            headers=headers,
            timeout=IMAGE_TIMEOUT,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        if (
            "image"
            not in content_type
        ):
            return False

        if len(
            response.content
        ) < 5000:
            return False

        return True

    except Exception:
        return False


def first_valid_image(
    candidates,
    article_url=None,
):
    checked = 0

    for url in candidates:

        if checked >= MAX_IMAGE_CHECKS:
            break

        checked += 1

        print(
            f"Checking image: {url}"
        )

        if verify_image(
            url,
            article_url,
        ):

            print(
                f"REAL IMAGE FOUND: {url}"
            )

            return url

        print(
            "Rejected image."
        )

    return None


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_article(
    url
):
    if not valid_http_url(
        url
    ):
        return None

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=ARTICLE_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        return soup

    except Exception as exc:

        print(
            f"Article fetch failed: "
            f"{url} -> {exc}"
        )

        return None


def extract_article_summary(
    soup,
    fallback="",
):
    for selector in [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
        ("meta", {"name": "twitter:description"}),
    ]:

        tag = soup.find(
            selector[0],
            attrs=selector[1],
        )

        if tag and tag.get(
            "content"
        ):

            text = clean_text(
                tag.get(
                    "content"
                )
            )

            if len(text) >= 40:
                return text

    paragraphs = []

    article = soup.find(
        "article"
    )

    if article:

        for p in article.find_all(
            "p"
        ):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 30:
                paragraphs.append(
                    text
                )

    if not paragraphs:

        for p in soup.find_all(
            "p"
        ):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 30:
                paragraphs.append(
                    text
                )

    if paragraphs:

        return " ".join(
            paragraphs[:5]
        )[:1200]

    return clean_text(
        fallback
    )


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def verify_article_candidate(
    candidate
):
    url = candidate.get(
        "url"
    )

    if not valid_http_url(
        url
    ):
        return None

    if is_google_news_url(
        url
    ):
        return None

    if is_search_engine_url(
        url
    ):
        return None

    soup = fetch_article(
        url
    )

    if not soup:
        return None

    page_title = ""

    og_title = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        },
    )

    if og_title:
        page_title = clean_text(
            og_title.get(
                "content"
            )
        )

    if not page_title:

        title_tag = soup.find(
            "title"
        )

        if title_tag:
            page_title = clean_text(
                title_tag.get_text()
            )

    if not page_title:
        page_title = candidate.get(
            "title",
            "",
        )

    similarity = title_similarity(
        candidate.get(
            "title",
            "",
        ),
        page_title,
    )

    if similarity < 0.15:

        print(
            "Rejected: article title "
            "did not match."
        )

        return None

    images = extract_image_candidates(
        soup,
        url,
    )

    image_url = first_valid_image(
        images,
        url,
    )

    if not image_url:

        print(
            "Rejected: no valid "
            "RSS/article image found."
        )

        return None

    summary = extract_article_summary(
        soup,
        candidate.get(
            "summary",
            "",
        ),
    )

    if len(summary) < 40:

        print(
            "Rejected: article summary "
            "too short."
        )

        return None

    verified = dict(
        candidate
    )

    verified["title"] = page_title
    verified["summary"] = summary
    verified["url"] = url
    verified["resolved_url"] = url
    verified["image"] = image_url
    verified["verified"] = True
    verified["publisher_domain"] = (
        publisher_domain(url)
    )

    verified["source_name"] = (
        verified.get(
            "source_name"
        )
        or publisher_domain(url)
        or "Published report"
    )

    return verified


# ============================================================
# GOOGLE NEWS RESOLUTION
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
            timeout=SEARCH_TIMEOUT,
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
        ):

            return final_url

    except Exception:
        pass

    return None


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(
    query
):
    url = (
        "https://www.bing.com/search"
        "?q="
        + quote_plus(query)
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        results = []

        for item in soup.select(
            "li.b_algo"
        ):

            a = item.find(
                "a",
                href=True,
            )

            if not a:
                continue

            href = a.get(
                "href"
            )

            title = clean_text(
                a.get_text(
                    " ",
                    strip=True,
                )
            )

            p = item.find(
                "p"
            )

            snippet = (
                clean_text(
                    p.get_text(
                        " ",
                        strip=True,
                    )
                )
                if p
                else ""
            )

            if valid_http_url(
                href
            ):

                results.append(
                    {
                        "title": title,
                        "url": href,
                        "summary": snippet,
                    }
                )

            if len(results) >= BING_RESULT_LIMIT:
                break

        return results

    except Exception as exc:

        print(
            f"Bing search failed: {exc}"
        )

        return []


def resolve_publisher_article(
    title,
    original_url=None,
):
    if (
        original_url
        and valid_http_url(
            original_url
        )
        and not is_google_news_url(
            original_url
        )
        and not is_search_engine_url(
            original_url
        )
    ):

        return original_url

    results = bing_search(
        f'"{title}" Kenya'
    )

    for result in results:

        url = result.get(
            "url"
        )

        if not valid_http_url(
            url
        ):
            continue

        if is_search_engine_url(
            url
        ):
            continue

        return url

    return None


# ============================================================
# BING IMAGE FALLBACK
# ============================================================

def extract_bing_image_urls(
    html_text
):
    urls = []

    patterns = [
        r'"murl":"(.*?)"',
        r'"turl":"(.*?)"',
        r'"mediaurl":"(.*?)"',
    ]

    for pattern in patterns:

        for match in re.findall(
            pattern,
            html_text,
            flags=re.I,
        ):

            decoded = (
                match
                .replace(
                    "\\/",
                    "/",
                )
                .replace(
                    "\\u002f",
                    "/",
                )
            )

            if valid_http_url(
                decoded
            ):

                urls.append(
                    decoded
                )

    return urls


def bing_image_search(
    query
):
    url = (
        "https://www.bing.com/images/search"
        "?q="
        + quote_plus(query)
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT,
        )

        response.raise_for_status()

        urls = extract_bing_image_urls(
            response.text
        )

        result = []
        seen = set()

        for url in urls:

            if url in seen:
                continue

            if is_svg_url(
                url
            ):
                continue

            seen.add(url)
            result.append(url)

            if len(result) >= MAX_BING_IMAGES:
                break

        return result

    except Exception as exc:

        print(
            f"Bing image search failed: "
            f"{exc}"
        )

        return []


def image_search_fallback(
    title,
    source_name="",
):
    query = clean_text(
        f"{title} {source_name}"
    )

    print(
        f'Image search: "{query}"'
    )

    urls = bing_image_search(
        query
    )

    for url in urls:

        if verify_image(
            url
        ):

            print(
                f"REAL IMAGE FOUND: {url}"
            )

            return url

    print(
        "SS fallback rejected: "
        "no valid image found."
    )

    return None


# ============================================================
# COUNTY RELEVANCE
# ============================================================

def county_relevance(
    title,
    summary,
    county,
):
    text = (
        clean_text(title)
        + " "
        + clean_text(summary)
    ).lower()

    score = 0

    for alias in COUNTY_ALIASES.get(
        county,
        [county],
    ):

        if alias.lower() in text:
            score += 1

    return score


# ============================================================
# STORY SCORING
# ============================================================

def score_story(
    story
):
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

    text = (
        title
        + " "
        + summary
    ).lower()

    score = 0

    score += (
        county_relevance(
            title,
            summary,
            county,
        )
        * 15
    )

    keywords = {
        "development": 12,
        "road": 10,
        "project": 10,
        "hospital": 10,
        "school": 8,
        "water": 8,
        "business": 8,
        "investment": 8,
        "jobs": 8,
        "government": 7,
        "funding": 7,
        "budget": 7,
        "construction": 8,
        "launch": 6,
        "opened": 6,
        "health": 7,
        "education": 7,
        "agriculture": 7,
        "farmers": 7,
        "market": 6,
        "security": 6,
        "economy": 7,
    }

    for keyword, points in keywords.items():

        if keyword in text:
            score += points

    if len(summary) >= 300:
        score += 8

    elif len(summary) >= 150:
        score += 4

    if story.get(
        "publisher_domain"
    ):
        score += 8

    if story.get(
        "image"
    ):
        score += 15

    published = parse_date(
        story.get(
            "published"
        )
    )

    if published:

        age_hours = (
            now_utc()
            - published
        ).total_seconds() / 3600

        if age_hours <= 12:
            score += 20

        elif age_hours <= 24:
            score += 14

        elif age_hours <= 48:
            score += 8

    return score


# ============================================================
# ENRICH STORY
# ============================================================

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

    summary = clean_text(
        entry.get(
            "summary",
            entry.get(
                "description",
                "",
            ),
        )
    )

    published = (
        entry.get(
            "published"
        )
        or entry.get(
            "updated"
        )
    )

    link = clean_text(
        entry.get(
            "link",
            "",
        )
    )

    if not title or not link:
        return None

    if not is_recent(
        published
    ):
        return None

    story = {
        "title": title,
        "summary": summary,
        "url": link,
        "published": published,
        "county": county,
        "source_name": (
            publisher_domain(link)
            or "Published report"
        ),
        "image": None,
        "verified": False,
    }

    # Google News -> publisher
    resolved = unwrap_google_news_url(
        link
    )

    if resolved:
        story["url"] = resolved

    # Verify actual article
    verified = verify_article_candidate(
        story
    )

    if verified:
        return verified

    # Search publisher
    resolved_url = resolve_publisher_article(
        title,
        story.get(
            "url"
        ),
    )

    if resolved_url:

        story["url"] = resolved_url

        verified = verify_article_candidate(
            story
        )

        if verified:
            return verified

    # Controlled image fallback
    fallback_image = image_search_fallback(
        title,
        story.get(
            "source_name",
            "",
        ),
    )

    if fallback_image:

        story["image"] = fallback_image

        # Re-check article
        if story.get(
            "url"
        ):

            verified = verify_article_candidate(
                story
            )

            if verified:

                verified["image"] = (
                    fallback_image
                )

                return verified

    return None


# ============================================================
# COLLECT CANDIDATES
# ============================================================

def collect_candidates():
    candidates = []
    seen = set()

    feeds = build_feed_urls()

    print(
        f"Checking {len(feeds)} "
        "Google News RSS feeds..."
    )

    for feed_url in feeds:

        parsed = parse_feed(
            feed_url
        )

        if not parsed:
            continue

        entries = getattr(
            parsed,
            "entries",
            [],
        )

        for entry in entries:

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

            if not title or not link:
                continue

            summary = clean_text(
                entry.get(
                    "summary",
                    entry.get(
                        "description",
                        "",
                    ),
                )
            )

            text = (
                title
                + " "
                + summary
            ).lower()

            county_match = None

            for county in COUNTIES:

                for alias in COUNTY_ALIASES.get(
                    county,
                    [county],
                ):

                    if alias.lower() in text:

                        county_match = county
                        break

                if county_match:
                    break

            if not county_match:
                continue

            published = (
                entry.get(
                    "published"
                )
                or entry.get(
                    "updated"
                )
            )

            if not is_recent(
                published
            ):
                continue

            h = story_hash(
                title,
                link,
            )

            if h in seen:
                continue

            seen.add(h)

            candidates.append(
                {
                    "entry": entry,
                    "county": county_match,
                    "title": title,
                    "url": link,
                    "published": published,
                }
            )

        time.sleep(
            RSS_DELAY
        )

    candidates.sort(
        key=lambda item: (
            parse_date(
                item.get(
                    "published"
                )
            )
            or datetime(
                2000,
                1,
                1,
                tzinfo=timezone.utc,
            )
        ),
        reverse=True,
    )

    print(
        f"Collected {len(candidates)} "
        "recent candidates."
    )

    return candidates


# ============================================================
# SELECT ONE STORY
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:

        raise RuntimeError(
            "No recent Rift Valley "
            "candidates found."
        )

    verified = []

    for index, candidate in enumerate(
        candidates[
            :MAX_CANDIDATES_TO_VERIFY
        ],
        start=1,
    ):

        print()
        print(
            "=" * 70
        )

        print(
            f"VERIFYING CANDIDATE "
            f"{index}/"
            f"{min(len(candidates), MAX_CANDIDATES_TO_VERIFY)}"
        )

        print(
            candidate["title"]
        )

        try:

            story = enrich_story(
                candidate["entry"],
                candidate["county"],
            )

            if not story:

                print(
                    "Rejected: article did "
                    "not pass verification."
                )

                continue

            story["score"] = score_story(
                story
            )

            verified.append(
                story
            )

            print(
                "VERIFIED STORY:"
            )

            print(
                story["title"]
            )

            print(
                f"Score: {story['score']}"
            )

        except Exception as exc:

            print(
                f"Verification error: {exc}"
            )

            traceback.print_exc()

    if not verified:

        raise RuntimeError(
            "No recent story passed "
            "verification after checking "
            "candidates."
        )

    # Select the strongest story.
    verified.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    story = verified[0]

    # ONE STORY ONLY
    story["story_id"] = story_hash(
        story["title"],
        story["url"],
    )

    story["selected_at"] = (
        now_utc().isoformat()
    )

    return story


# ============================================================
# SCRIPT
# ============================================================

def build_script(
    story
):
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
            "Rift Valley",
        )
    )

    source = clean_text(
        story.get(
            "source_name",
            "reported article",
        )
    )

    narration = clean_text(
        (
            f"Rift Valley Watch. "
            f"Here is the latest regional "
            f"update from {county}. "
            f"{title}. "
            f"{summary}. "
            f"The report comes from "
            f"{source}."
        )
    )

    return {
        "brand": BRAND,
        "title": title,
        "county": county,
        "narration": narration,
        "source": source,
        "source_url": (
            story.get(
                "resolved_url"
            )
            or story.get(
                "url"
            )
        ),
        "generated_at": (
            now_utc().isoformat()
        ),
    }


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    path,
    data,
):
    directory = os.path.dirname(
        path
    )

    if directory:
        os.makedirs(
            directory,
            exist_ok=True,
        )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# GENERATOR
# ============================================================

def generate_video(
    story,
    script,
):
    try:

        from rift_valley_video_generator import (
            generate_video as video_generator
        )

    except Exception as exc:

        raise RuntimeError(
            "Unable to import "
            "rift_valley_video_generator.py: "
            f"{exc}"
        ) from exc

    return video_generator(
        story,
        script,
    )


# ============================================================
# FINAL QC
# ============================================================

def basic_output_qc():
    output_file = os.path.join(
        "output",
        "rift_valley_watch_reel.mp4",
    )

    if not os.path.exists(
        output_file
    ):

        raise RuntimeError(
            "Video was not generated: "
            f"{output_file}"
        )

    size = os.path.getsize(
        output_file
    )

    if size < 50_000:

        raise RuntimeError(
            "Video QC failed: output "
            "file is too small."
        )

    print()
    print(
        "=" * 70
    )

    print(
        "VIDEO QC PASSED"
    )

    print(
        f"Output: {output_file}"
    )

    print(
        f"Size: {size:,} bytes"
    )

    print(
        "=" * 70
    )

    return output_file


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH"
    )

    print(
        "AUTOMATED REGIONAL NEWS PIPELINE"
    )

    print(
        "=" * 70
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    os.makedirs(
        "output",
        exist_ok=True,
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print()
    print(
        "STEP 1: SELECTING ONE VERIFIED STORY"
    )

    story = select_story()

    print()
    print(
        "SELECTED STORY"
    )

    print(
        f"Title: {story['title']}"
    )

    print(
        f"County: {story['county']}"
    )

    print(
        f"Source: {story.get('source_name', '')}"
    )

    print(
        f"Image: {story.get('image', '')}"
    )

    print(
        f"Score: {story.get('score', 0)}"
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print()
    print(
        "STEP 2: BUILDING SCRIPT"
    )

    script = build_script(
        story
    )

    print(
        f"Narration characters: "
        f"{len(script['narration'])}"
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print()
    print(
        "STEP 3: SAVING STORY.JSON"
    )

    save_json(
        STORY_FILE,
        story,
    )

    print(
        f"Saved {STORY_FILE}"
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    print()
    print(
        "STEP 4: SAVING SCRIPT.JSON"
    )

    save_json(
        SCRIPT_FILE,
        script,
    )

    print(
        f"Saved {SCRIPT_FILE}"
    )

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    print()
    print(
        "STEP 5: GENERATING VIDEO"
    )

    output_file = generate_video(
        story,
        script,
    )

    print(
        f"Generator returned: "
        f"{output_file}"
    )

    # --------------------------------------------------------
    # STEP 6
    # --------------------------------------------------------

    print()
    print(
        "STEP 6: FINAL OUTPUT QC"
    )

    final_file = basic_output_qc()

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH COMPLETED SUCCESSFULLY"
    )

    print(
        f"Story:  {STORY_FILE}"
    )

    print(
        f"Script: {SCRIPT_FILE}"
    )

    print(
        f"Video:  {final_file}"
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "Process interrupted."
        )

        raise

    except Exception as exc:

        print()
        print(
            "=" * 70
        )

        print(
            "RIFT VALLEY WATCH FAILED"
        )

        print(
            f"ERROR: {exc}"
        )

        print(
            "=" * 70
        )

        traceback.print_exc()

        raise
