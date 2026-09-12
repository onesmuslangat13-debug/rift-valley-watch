# ============================================================
# RIFT VALLEY WATCH
# FAST NEWS SELECTION + VERIFICATION + IMAGE FALLBACK
# ============================================================

import os
import re
import json
import time
import html
import hashlib
import traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

STORY_FILE = os.path.join(DATA_DIR, "story.json")
SCRIPT_FILE = os.path.join(DATA_DIR, "script.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


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
]

COUNTY_ALIASES = {
    "Bomet": [
        "bomet",
        "sotik",
        "konoin",
        "chepalungu",
        "bomet east",
        "bomet central",
    ],
    "Kericho": [
        "kericho",
        "litein",
        "belgut",
        "kipkelion",
        "ainamoi",
        "sigowet",
        "soin",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "bahati",
        "subukia",
        "rongai",
        "njoro",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "chesumei",
        "aldai",
        "emgwen",
        "tinderet",
        "nandi hills",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "soy",
        "ainabkoi",
        "kapseret",
        "kesses",
        "turbo",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "keiyo",
        "marakwet",
        "itEn",
        "iten",
        "kapsowar",
        "cherangany",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "pokot",
        "sigor",
        "kacheliba",
        "pokot south",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "transmara",
        "suswa",
        "ololulunga",
        "narok north",
        "narok south",
    ],
}


# ============================================================
# FAST SETTINGS
# ============================================================

RSS_TIMEOUT = 5
ARTICLE_TIMEOUT = 6
IMAGE_TIMEOUT = 4
SEARCH_TIMEOUT = 5

MAX_AGE_HOURS = 72

MAX_CANDIDATES_TO_VERIFY = 4
MAX_VERIFIED_TO_COMPARE = 2

BING_RESULT_LIMIT = 5
MAX_BING_IMAGES = 5
MAX_IMAGE_CHECKS = 4

RSS_DELAY = 0


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_title(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def truncate_text(value, length=240):
    value = clean_text(value)

    if len(value) <= length:
        return value

    return value[:length].rsplit(" ", 1)[0] + "..."


def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url)

        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def hostname(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_search_engine_url(url):
    host = hostname(url)

    return any(
        x in host
        for x in [
            "google.",
            "bing.com",
            "search.yahoo.",
        ]
    )


def is_svg_url(url):
    if not url:
        return False

    return ".svg" in url.lower()


def story_hash(title, url):
    raw = (
        normalize_title(title)
        + "|"
        + clean_text(url)
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def now_utc():
    return datetime.now(timezone.utc)


# ============================================================
# DATE PARSING
# ============================================================

def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    text = clean_text(value)

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            result = datetime.strptime(text, fmt)

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result.astimezone(timezone.utc)

        except Exception:
            pass

    return None


def is_recent(date_value):
    parsed = parse_date(date_value)

    if parsed is None:
        return False

    cutoff = now_utc() - timedelta(
        hours=MAX_AGE_HOURS
    )

    return parsed >= cutoff


# ============================================================
# REQUEST
# ============================================================

def get_response(url, timeout):
    if not valid_http_url(url):
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        return response

    except Exception as exc:
        print(
            f"Request failed: "
            f"{url} | {exc}"
        )

        return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_rss(query):
    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}&"
        "hl=en-KE&"
        "gl=KE&"
        "ceid=KE:en"
    )


def parse_feed(feed_url, county):
    print(
        f"RSS: {county} -> {feed_url}"
    )

    response = get_response(
        feed_url,
        RSS_TIMEOUT,
    )

    if response is None:
        return []

    try:
        feed = feedparser.parse(
            response.content
        )

    except Exception as exc:
        print(
            f"RSS parse failed: {exc}"
        )

        return []

    results = []

    for entry in feed.entries[:8]:
        title = clean_text(
            entry.get("title", "")
        )

        url = clean_text(
            entry.get("link", "")
        )

        summary = clean_text(
            entry.get("summary", "")
        )

        published = (
            entry.get("published")
            or entry.get("updated")
            or ""
        )

        if not title or not url:
            continue

        if not valid_http_url(url):
            continue

        date_value = parse_date(
            published
        )

        results.append(
            {
                "title": title,
                "url": url,
                "summary": summary,
                "published": (
                    date_value.isoformat()
                    if date_value
                    else ""
                ),
                "county_hint": county,
                "source_name": "",
                "image_url": "",
            }
        )

    return results


# ============================================================
# RSS MEDIA IMAGE
# ============================================================

def get_rss_media_image(entry):
    candidates = []

    media_content = entry.get(
        "media_content",
        [],
    )

    if isinstance(media_content, list):
        for item in media_content:
            if isinstance(item, dict):
                candidates.append(
                    item.get("url", "")
                )

    media_thumbnail = entry.get(
        "media_thumbnail",
        [],
    )

    if isinstance(media_thumbnail, list):
        for item in media_thumbnail:
            if isinstance(item, dict):
                candidates.append(
                    item.get("url", "")
                )

    for url in candidates:
        if (
            valid_http_url(url)
            and not is_svg_url(url)
        ):
            return url

    return ""


# ============================================================
# GOOGLE NEWS URL UNWRAP
# ============================================================

def unwrap_google_news_url(url):
    if not valid_http_url(url):
        return ""

    if "news.google.com" not in hostname(url):
        return url

    response = get_response(
        url,
        ARTICLE_TIMEOUT,
    )

    if response is None:
        return url

    final_url = response.url

    if (
        valid_http_url(final_url)
        and "news.google.com" not in hostname(
            final_url
        )
    ):
        return final_url

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    for tag in soup.find_all(
        "a",
        href=True,
    ):
        href = tag.get("href", "")

        if (
            valid_http_url(href)
            and "news.google.com"
            not in hostname(href)
        ):
            return href

    return url


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query, limit=5):
    url = (
        "https://www.bing.com/search?"
        f"q={quote_plus(query)}"
    )

    response = get_response(
        url,
        SEARCH_TIMEOUT,
    )

    if response is None:
        return []

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception as exc:
        print(
            f"Bing parse failed: {exc}"
        )

        return []

    results = []

    for item in soup.select("li.b_algo"):
        link = item.select_one(
            "h2 a"
        )

        if link is None:
            continue

        href = link.get(
            "href",
            "",
        )

        title = clean_text(
            link.get_text(" ", strip=True)
        )

        paragraph = item.select_one(
            ".b_caption p"
        )

        summary = ""

        if paragraph:
            summary = clean_text(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

        if (
            valid_http_url(href)
            and not is_search_engine_url(
                href
            )
        ):
            results.append(
                {
                    "title": title,
                    "url": href,
                    "summary": summary,
                }
            )

        if len(results) >= limit:
            break

    return results


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def extract_image_candidates(
    soup,
    page_url,
):
    candidates = []

    meta_names = [
        "og:image",
        "twitter:image",
        "twitter:image:src",
        "thumbnail",
    ]

    for name in meta_names:
        tag = soup.find(
            "meta",
            attrs={
                "property": name
            },
        )

        if tag is None:
            tag = soup.find(
                "meta",
                attrs={
                    "name": name
                },
            )

        if tag:
            content = tag.get(
                "content",
                "",
            )

            if content:
                candidates.append(
                    content
                )

    for link in soup.find_all(
        "link",
        href=True,
    ):
        rel = " ".join(
            link.get("rel", [])
        ).lower()

        if (
            "image" in rel
            or "thumbnail" in rel
        ):
            candidates.append(
                link.get("href", "")
            )

    for image in soup.find_all(
        "img",
        src=True,
    )[:30]:
        candidates.append(
            image.get("src", "")
        )

    cleaned = []

    for candidate in candidates:
        candidate = html.unescape(
            candidate
        )

        if not valid_http_url(
            candidate
        ):
            try:
                from urllib.parse import urljoin

                candidate = urljoin(
                    page_url,
                    candidate,
                )

            except Exception:
                continue

        if not valid_http_url(
            candidate
        ):
            continue

        if is_svg_url(candidate):
            continue

        if candidate not in cleaned:
            cleaned.append(
                candidate
            )

    return cleaned


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_url(url):
    if not valid_http_url(url):
        return False

    if is_svg_url(url):
        return False

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=IMAGE_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return False

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if (
            "image/" not in content_type
            and "octet-stream"
            not in content_type
        ):
            return False

        return True

    except Exception:
        return False


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(
    article_url,
):
    if not valid_http_url(
        article_url
    ):
        return ""

    response = get_response(
        article_url,
        ARTICLE_TIMEOUT,
    )

    if response is None:
        return ""

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception:
        return ""

    candidates = extract_image_candidates(
        soup,
        response.url,
    )

    checked = 0

    for candidate in candidates:
        if checked >= MAX_IMAGE_CHECKS:
            break

        checked += 1

        if validate_image_url(
            candidate
        ):
            return candidate

    return ""


# ============================================================
# BING IMAGE FALLBACK
# ============================================================

def bing_image_fallback(
    title,
    county,
):
    query = (
        f"{title} {county} Kenya"
    )

    print(
        f'Image search: "{query}"'
    )

    search_url = (
        "https://www.bing.com/images/search?"
        f"q={quote_plus(query)}"
    )

    response = get_response(
        search_url,
        SEARCH_TIMEOUT,
    )

    if response is None:
        return ""

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception:
        return ""

    candidates = []

    for tag in soup.find_all(
        "a",
        class_="iusc",
    )[:MAX_BING_IMAGES]:
        raw = tag.get(
            "m",
            "",
        )

        if not raw:
            continue

        try:
            metadata = json.loads(
                raw
            )

        except Exception:
            continue

        for key in [
            "turl",
            "murl",
        ]:
            candidate = metadata.get(
                key,
                "",
            )

            if (
                valid_http_url(candidate)
                and not is_svg_url(
                    candidate
                )
            ):
                candidates.append(
                    candidate
                )

    checked = 0

    for candidate in candidates:
        if checked >= MAX_IMAGE_CHECKS:
            break

        checked += 1

        if validate_image_url(
            candidate
        ):
            print(
                "REAL IMAGE FOUND: "
                + candidate
            )

            return candidate

    return ""


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_article(
    candidate,
):
    url = candidate.get(
        "url",
        "",
    )

    if not valid_http_url(url):
        return None

    resolved_url = unwrap_google_news_url(
        url
    )

    if (
        not valid_http_url(
            resolved_url
        )
    ):
        resolved_url = url

    response = get_response(
        resolved_url,
        ARTICLE_TIMEOUT,
    )

    if response is None:
        return None

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception:
        return None

    title = candidate.get(
        "title",
        "",
    )

    page_title = soup.title

    if page_title:
        page_title = clean_text(
            page_title.get_text(
                " ",
                strip=True,
            )
        )

        if page_title:
            title = page_title

    paragraphs = []

    for paragraph in soup.find_all(
        "p"
    ):
        text = clean_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) >= 40:
            paragraphs.append(text)

    body = " ".join(
        paragraphs[:20]
    )

    image_url = ""

    images = extract_image_candidates(
        soup,
        response.url,
    )

    checked = 0

    for image in images:
        if checked >= MAX_IMAGE_CHECKS:
            break

        checked += 1

        if validate_image_url(
            image
        ):
            image_url = image
            break

    source_name = ""

    source_meta = soup.find(
        "meta",
        attrs={
            "property": "og:site_name"
        },
    )

    if source_meta:
        source_name = clean_text(
            source_meta.get(
                "content",
                "",
            )
        )

    if not source_name:
        source_name = hostname(
            resolved_url
        )

    return {
        "title": title,
        "url": resolved_url,
        "body": body,
        "image_url": image_url,
        "source_name": source_name,
    }


# ============================================================
# COUNTY MATCH
# ============================================================

def county_match_score(
    text,
    county,
):
    text = clean_text(
        text
    ).lower()

    score = 0

    for alias in COUNTY_ALIASES.get(
        county,
        [],
    ):
        alias = alias.lower()

        if alias in text:
            if alias == county.lower():
                score += 10
            else:
                score += 5

    return score


def detect_county(
    title,
    summary="",
    hinted_county="",
):
    text = (
        clean_text(title)
        + " "
        + clean_text(summary)
    )

    best_county = hinted_county
    best_score = 0

    for county in COUNTIES:
        score = county_match_score(
            text,
            county,
        )

        if score > best_score:
            best_county = county
            best_score = score

    return best_county


# ============================================================
# CATEGORY
# ============================================================

def story_category(
    title,
    body,
):
    text = (
        clean_text(title)
        + " "
        + clean_text(body)
    ).lower()

    if any(
        word in text
        for word in [
            "road",
            "bridge",
            "water",
            "hospital",
            "school",
            "project",
            "construction",
            "development",
        ]
    ):
        return "DEVELOPMENT"

    if any(
        word in text
        for word in [
            "police",
            "arrest",
            "court",
            "crime",
            "murder",
            "robbery",
            "investigation",
        ]
    ):
        return "SECURITY"

    if any(
        word in text
        for word in [
            "farmer",
            "agriculture",
            "tea",
            "maize",
            "livestock",
            "drought",
            "rain",
        ]
    ):
        return "AGRICULTURE"

    if any(
        word in text
        for word in [
            "mp",
            "governor",
            "senator",
            "president",
            "politician",
            "government",
            "party",
            "election",
        ]
    ):
        return "POLITICS"

    if any(
        word in text
        for word in [
            "business",
            "company",
            "economy",
            "market",
            "investment",
            "jobs",
        ]
    ):
        return "BUSINESS"

    return "COUNTY NEWS"


# ============================================================
# VERIFY CANDIDATE
# ============================================================

def verify_candidate(
    candidate,
):
    print(
        "Verifying: "
        + candidate.get(
            "title",
            "",
        )
    )

    article = fetch_article(
        candidate
    )

    if article is None:
        print(
            "Rejected: article could not "
            "be fetched."
        )

        return None

    title = article.get(
        "title",
        "",
    )

    body = article.get(
        "body",
        "",
    )

    county = detect_county(
        title,
        body,
        candidate.get(
            "county_hint",
            "",
        ),
    )

    if not county:
        print(
            "Rejected: county not identified."
        )

        return None

    combined = (
        title
        + " "
        + body
    ).lower()

    if county.lower() not in combined:
        aliases = COUNTY_ALIASES.get(
            county,
            [],
        )

        if not any(
            alias.lower() in combined
            for alias in aliases
        ):
            print(
                "Rejected: county not verified."
            )

            return None

    image_url = article.get(
        "image_url",
        "",
    )

    if not image_url:
        image_url = bing_image_fallback(
            title,
            county,
        )

    if not image_url:
        print(
            "Rejected: no valid article "
            "image or fallback image."
        )

        return None

    published = candidate.get(
        "published",
        "",
    )

    if published:
        if not is_recent(
            published
        ):
            print(
                "Rejected: story is too old."
            )

            return None

    source_name = article.get(
        "source_name",
        "",
    )

    if not source_name:
        source_name = (
            candidate.get(
                "source_name",
                "",
            )
            or hostname(
                article.get(
                    "url",
                    "",
                )
            )
        )

    verified = {
        "title": clean_text(title),
        "county": county,
        "category": story_category(
            title,
            body,
        ),
        "date": published,
        "summary": truncate_text(
            body,
            360,
        ),
        "body": body,
        "image": image_url,
        "image_url": image_url,
        "source_name": clean_text(
            source_name
        ),
        "source": clean_text(
            source_name
        ),
        "url": article.get(
            "url",
            candidate.get(
                "url",
                "",
            ),
        ),
        "resolved_url": article.get(
            "url",
            candidate.get(
                "url",
                "",
            ),
        ),
        "verified": True,
        "story_id": story_hash(
            title,
            article.get(
                "url",
                candidate.get(
                    "url",
                    "",
                ),
            ),
        ),
    }

    return verified


# ============================================================
# STORY SCORE
# ============================================================

def score_story(
    story,
):
    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    body = clean_text(
        story.get(
            "body",
            "",
        )
    )

    county = story.get(
        "county",
        "",
    )

    text = (
        title
        + " "
        + body
    ).lower()

    score = 0

    score += county_match_score(
        text,
        county,
    )

    if len(body) >= 200:
        score += 20

    if story.get(
        "image"
    ):
        score += 20

    if story.get(
        "source_name"
    ):
        score += 10

    important_terms = [
        "million",
        "billion",
        "project",
        "road",
        "hospital",
        "school",
        "government",
        "governor",
        "mp",
        "senator",
        "police",
        "court",
        "farmers",
        "jobs",
    ]

    for term in important_terms:
        if term in text:
            score += 2

    return score


# ============================================================
# CANDIDATE COLLECTION
# ============================================================

def collect_candidates():
    queries = [
        (
            "Bomet",
            '"Bomet" Kenya latest news',
        ),
        (
            "Kericho",
            '"Kericho" Kenya latest news',
        ),
        (
            "Nakuru",
            '"Nakuru" Kenya latest news',
        ),
        (
            "Nandi",
            '"Nandi" Kenya latest news',
        ),
        (
            "Uasin Gishu",
            '"Uasin Gishu" Kenya latest news',
        ),
        (
            "Elgeyo-Marakwet",
            '"Elgeyo-Marakwet Kenya latest news',
        ),
        (
            "West Pokot",
            '"West Pokot" Kenya latest news',
        ),
        (
            "Narok",
            '"Narok" Kenya latest news',
        ),
    ]

    candidates = []

    print("=" * 60)
    print("COLLECTING RIFT VALLEY CANDIDATES")
    print("=" * 60)

    for county, query in queries:
        feed_url = google_news_rss(
            query
        )

        items = parse_feed(
            feed_url,
            county,
        )

        for item in items:
            published = item.get(
                "published",
                "",
            )

            if published and not is_recent(
                published
            ):
                continue

            item["county_hint"] = county

            candidates.append(
                item
            )

        if RSS_DELAY:
            time.sleep(
                RSS_DELAY
            )

    # --------------------------------------------------------
    # BING FALLBACK
    # --------------------------------------------------------

    if len(candidates) < 4:
        print("=" * 60)
        print("USING BING FALLBACK")
        print("=" * 60)

        fallback_queries = [
            "Bomet Kenya latest news",
            "Kericho Kenya latest news",
            "Nakuru Kenya latest news",
            "Uasin Gishu Kenya latest news",
        ]

        for query in fallback_queries:
            results = bing_search(
                query,
                BING_RESULT_LIMIT,
            )

            for result in results:
                county = detect_county(
                    result.get(
                        "title",
                        "",
                    ),
                    result.get(
                        "summary",
                        "",
                    ),
                )

                if not county:
                    continue

                candidates.append(
                    {
                        "title": result.get(
                            "title",
                            "",
                        ),
                        "url": result.get(
                            "url",
                            "",
                        ),
                        "summary": result.get(
                            "summary",
                            "",
                        ),
                        "published": "",
                        "county_hint": county,
                        "source_name": "",
                        "image_url": "",
                    }
                )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    unique = {}
    for candidate in candidates:
        key = normalize_title(
            candidate.get(
                "title",
                "",
            )
        )

        if not key:
            continue

        if key not in unique:
            unique[key] = candidate

    candidates = list(
        unique.values()
    )

    # Newest first where dates exist
    candidates.sort(
        key=lambda item: (
            parse_date(
                item.get(
                    "published",
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

    print(
        f"Candidates collected: "
        f"{len(candidates)}"
    )

    return candidates


# ============================================================
# STORY SELECTION
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError(
            "No recent Rift Valley candidates found."
        )

    verified = []

    print("=" * 60)
    print("VERIFYING CANDIDATES")
    print("=" * 60)

    for candidate in candidates[
        :MAX_CANDIDATES_TO_VERIFY
    ]:
        try:
            story = verify_candidate(
                candidate
            )

            if story:
                story["score"] = score_story(
                    story
                )

                verified.append(
                    story
                )

        except Exception as exc:
            print(
                "Candidate verification "
                f"failed: {exc}"
            )

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking candidates."
        )

    verified.sort(
        key=lambda x: x.get(
            "score",
            0,
        ),
        reverse=True,
    )

    finalists = verified[
        :MAX_VERIFIED_TO_COMPARE
    ]

    selected = finalists[0]

    print("=" * 60)
    print("SELECTED STORY")
    print("=" * 60)

    print(
        "Title: "
        + selected.get(
            "title",
            "",
        )
    )

    print(
        "County: "
        + selected.get(
            "county",
            "",
        )
    )

    print(
        "Category: "
        + selected.get(
            "category",
            "",
        )
    )

    print(
        "Source: "
        + selected.get(
            "source_name",
            "",
        )
    )

    print(
        "Image: "
        + selected.get(
            "image",
            "",
        )
    )

    print(
        "Score: "
        + str(
            selected.get(
                "score",
                0,
            )
        )
    )

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story,
):
    title = clean_text(
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

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    category = clean_text(
        story.get(
            "category",
            "",
        )
    )

    parts = []

    parts.append(
        f"Rift Valley Watch. "
        f"{county}."
    )

    parts.append(
        title
    )

    if summary:
        parts.append(
            summary
        )

    if category:
        parts.append(
            f"This is a {category.lower()} "
            f"development."
        )

    if source:
        parts.append(
            f"According to {source}."
        )

    parts.append(
        "Rift Valley Watch will continue "
        "to track developments across "
        "the region."
    )

    return " ".join(
        parts
    )


# ============================================================
# SCRIPT
# ============================================================

def build_script(
    story,
):
    narration = build_narration(
        story
    )

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

    category = clean_text(
        story.get(
            "category",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    segments = [
        {
            "scene": 1,
            "type": "opening",
            "text": (
                f"RIFT VALLEY WATCH | "
                f"{county.upper()}"
            ),
        },
        {
            "scene": 2,
            "type": "headline",
            "text": title,
        },
        {
            "scene": 3,
            "type": "details",
            "text": summary,
        },
        {
            "scene": 4,
            "type": "closing",
            "text": (
                f"{category} | "
                f"{source}"
            ),
        },
    ]

    return {
        "title": title,
        "county": county,
        "category": category,
        "source": source,
        "source_name": source,
        "summary": summary,
        "narration": narration,
        "segments": segments,
    }


# ============================================================
# JSON
# ============================================================

def write_json(
    path,
    data,
):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# VIDEO GENERATOR IMPORT
# ============================================================

def import_video_generator():
    try:
        from rift_valley_video_generator import generate_video

        return generate_video

    except Exception as exc:
        print(
            "Could not import "
            "rift_valley_video_generator:"
        )

        print(
            repr(exc)
        )

        raise


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    print("=" * 60)
    print("RIFT VALLEY WATCH")
    print("FAST NEWS-TO-VIDEO PIPELINE")
    print("=" * 60)

    print(
        f"Data directory: {DATA_DIR}"
    )

    print(
        f"Output directory: {OUTPUT_DIR}"
    )

    # --------------------------------------------------------
    # SELECT ONE VERIFIED STORY
    # --------------------------------------------------------

    story = select_story()

    # --------------------------------------------------------
    # BUILD SCRIPT
    # --------------------------------------------------------

    script = build_script(
        story
    )

    # --------------------------------------------------------
    # SAVE STORY
    # --------------------------------------------------------

    write_json(
        STORY_FILE,
        story,
    )

    # --------------------------------------------------------
    # SAVE SCRIPT
    # --------------------------------------------------------

    write_json(
        SCRIPT_FILE,
        script,
    )

    print("=" * 60)
    print("DATA FILES CREATED")
    print("=" * 60)

    print(
        STORY_FILE
    )

    print(
        SCRIPT_FILE
    )

    # --------------------------------------------------------
    # GENERATE VIDEO
    # --------------------------------------------------------

    generate_video = (
        import_video_generator()
    )

    print("=" * 60)
    print("GENERATING VIDEO")
    print("=" * 60)

    result = generate_video(
        story,
        script,
    )

    if result is None:
        result = {}

    if not isinstance(
        result,
        dict,
    ):
        result = {
            "result": result
        }

    # --------------------------------------------------------
    # RESULT DETAILS
    # --------------------------------------------------------

    try:
        duration = float(
            result.get(
                "duration",
                0,
            )
        )

    except Exception:
        duration = 0.0

    output_path = result.get(
        "output_path",
        os.path.join(
            OUTPUT_DIR,
            "rift_valley_watch_reel.mp4",
        ),
    )

    elapsed = (
        time.time()
        - start_time
    )

    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)

    print(
        f"Output: {output_path}"
    )

    print(
        f"Duration: {duration:.2f}s"
    )

    print(
        f"Runtime: {elapsed:.2f}s"
    )

    # --------------------------------------------------------
    # FINAL FILE CHECK
    # --------------------------------------------------------

    if not os.path.exists(
        output_path
    ):
        raise RuntimeError(
            "Video generator reported "
            "completion but the MP4 file "
            "does not exist: "
            + output_path
        )

    file_size = os.path.getsize(
        output_path
    )

    if file_size <= 0:
        raise RuntimeError(
            "Generated MP4 is empty."
        )

    print(
        f"File size: "
        f"{file_size / 1024 / 1024:.2f} MB"
    )

    print("=" * 60)
    print("RIFT VALLEY WATCH REEL READY")
    print("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print("=" * 60)
        print("PIPELINE FAILED")
        print("=" * 60)

        print(
            str(exc)
        )

        traceback.print_exc()

        raise
