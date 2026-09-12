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
# RIFT VALLEY WATCH
# MAIN NEWS SELECTION + VERIFICATION PIPELINE
#
# FAST GITHUB ACTIONS VERSION
# ONE STORY PER REEL
# ============================================================


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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 "
    "RiftValleyWatch/4.0"
)


# ============================================================
# TEXT HELPERS
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

    try:
        value = BeautifulSoup(
            value,
            "html.parser",
        ).get_text(
            " ",
            strip=True,
        )
    except Exception:
        pass

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_title(title):
    text = clean_text(title).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        "",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def truncate_text(text, maximum=500):
    text = clean_text(text)

    if len(text) <= maximum:
        return text

    shortened = text[:maximum].rsplit(
        " ",
        1,
    )[0]

    return shortened.rstrip(" ,.;:") + "..."


# ============================================================
# URL HELPERS
# ============================================================

def valid_http_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(str(url).strip())

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
        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )
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

    lower = str(url).lower()

    return (
        ".svg" in lower
        or "image/svg" in lower
        or lower.startswith(
            "data:image/svg"
        )
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

def now_utc():
    return datetime.now(
        timezone.utc
    )


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


def is_recent(value, allow_missing=True):
    dt = parse_date(value)

    if dt is None:
        return allow_missing

    age = now_utc() - dt

    if age < timedelta(
        minutes=-30
    ):
        return False

    return age <= timedelta(
        hours=MAX_AGE_HOURS
    )


# ============================================================
# HTTP
# ============================================================

def get_response(url, timeout):
    return requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
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

        entries = getattr(
            parsed,
            "entries",
            [],
        )

        if not entries:
            return None

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
            "&count=5"
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
            link = item.select_one(
                "h2 a"
            )

            if not link:
                continue

            href = link.get(
                "href",
                "",
            ).strip()

            title = clean_text(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                not valid_http_url(href)
                or is_search_engine_url(href)
            ):
                continue

            if not title:
                continue

            results.append(
                {
                    "title": title,
                    "url": href,
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
# ARTICLE IMAGE EXTRACTION
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
            str(value).strip()
        )

        if value.startswith("//"):
            value = "https:" + value

        elif value.startswith("/"):
            value = (
                urlparse(base_url).scheme
                + "://"
                + urlparse(base_url).netloc
                + value
            )

        elif not value.startswith(
            ("http://", "https://")
        ):
            return

        if (
            valid_http_url(value)
            and not is_svg_url(value)
            and not is_search_engine_url(value)
            and value not in candidates
        ):
            candidates.append(value)

    meta_names = [
        "og:image",
        "twitter:image",
        "twitter:image:src",
    ]

    for name in meta_names:
        tag = soup.find(
            "meta",
            attrs={
                "property": name
            },
        )

        if not tag:
            tag = soup.find(
                "meta",
                attrs={
                    "name": name
                },
            )

        if tag:
            add(
                tag.get(
                    "content",
                    "",
                )
            )

    for tag in soup.find_all(
        "img"
    ):
        add(
            tag.get(
                "src",
                "",
            )
        )

        add(
            tag.get(
                "data-src",
                "",
            )
        )

        add(
            tag.get(
                "data-original",
                "",
            )
        )

        srcset = tag.get(
            "srcset",
            "",
        )

        if srcset:
            for part in srcset.split(","):
                add(
                    part.strip().split(" ")[0]
                )

        if len(candidates) >= MAX_BING_IMAGES:
            break

    return candidates


def validate_image_url(url):
    if (
        not valid_http_url(url)
        or is_svg_url(url)
    ):
        return False

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,"
                "image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            timeout=IMAGE_TIMEOUT,
            allow_redirects=True,
            stream=True,
        )

        if response.status_code != 200:
            response.close()
            return False

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        if not content_type.startswith(
            "image/"
        ):
            response.close()
            return False

        if "svg" in content_type:
            response.close()
            return False

        chunk = response.raw.read(
            32
        )

        response.close()

        if not chunk:
            return False

        signatures = [
            b"\xff\xd8\xff",
            b"\x89PNG",
            b"RIFF",
            b"GIF8",
            b"BM",
        ]

        return any(
            chunk.startswith(signature)
            for signature in signatures
        )

    except Exception:
        return False


def find_article_image(
    article_url,
    soup,
    rss_image="",
):
    candidates = []

    if rss_image:
        candidates.append(
            rss_image
        )

    candidates.extend(
        extract_image_candidates(
            soup,
            article_url,
        )
    )

    checked = 0

    for image_url in candidates:
        if checked >= MAX_IMAGE_CHECKS:
            break

        checked += 1

        if validate_image_url(
            image_url
        ):
            return image_url

    return ""


def bing_image_fallback(
    title,
    article_url="",
):
    queries = [
        f"{title} Kenya",
        f"{title} photo",
    ]

    checked = 0

    for query in queries:
        if checked >= MAX_BING_IMAGES:
            break

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

            soup = BeautifulSoup(
                response.text,
                "html.parser",
            )

            for image in soup.select(
                "a.iusc"
            ):
                metadata = image.get(
                    "m",
                    "",
                )

                if not metadata:
                    continue

                try:
                    data = json.loads(
                        html.unescape(
                            metadata
                        )
                    )
                except Exception:
                    continue

                image_url = (
                    data.get("turl")
                    or data.get("murl")
                    or ""
                )

                if not valid_http_url(
                    image_url
                ):
                    continue

                if is_svg_url(
                    image_url
                ):
                    continue

                checked += 1

                if validate_image_url(
                    image_url
                ):
                    return image_url

                if checked >= MAX_BING_IMAGES:
                    break

        except Exception as exc:
            print(
                f"Bing image search failed: {exc}"
            )

    return ""


# ============================================================
# ARTICLE FETCHING
# ============================================================

def fetch_article(
    url,
    rss_image="",
):
    if not valid_http_url(url):
        return None

    try:
        response = get_response(
            url,
            ARTICLE_TIMEOUT,
        )

        response.raise_for_status()

        final_url = response.url

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        title = ""

        og_title = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            },
        )

        if og_title:
            title = clean_text(
                og_title.get(
                    "content",
                    "",
                )
            )

        if not title:
            title_tag = soup.find(
                "title"
            )

            if title_tag:
                title = clean_text(
                    title_tag.get_text(
                        " ",
                        strip=True,
                    )
                )

        description = ""

        for attrs in [
            {
                "name": "description"
            },
            {
                "property": "og:description"
            },
            {
                "name": "twitter:description"
            },
        ]:
            tag = soup.find(
                "meta",
                attrs=attrs,
            )

            if tag:
                description = clean_text(
                    tag.get(
                        "content",
                        "",
                    )
                )

                if description:
                    break

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
                paragraphs.append(
                    text
                )

        body_text = " ".join(
            paragraphs[:12]
        )

        summary = (
            description
            if len(description) >= 40
            else body_text
        )

        image_url = find_article_image(
            final_url,
            soup,
            rss_image,
        )

        published = ""

        date_selectors = [
            (
                "meta",
                {
                    "property": "article:published_time"
                },
            ),
            (
                "meta",
                {
                    "property": "og:published_time"
                },
            ),
            (
                "meta",
                {
                    "name": "publishdate"
                },
            ),
            (
                "meta",
                {
                    "name": "date"
                },
            ),
        ]

        for tag_name, attrs in date_selectors:
            tag = soup.find(
                tag_name,
                attrs=attrs,
            )

            if tag:
                published = clean_text(
                    tag.get(
                        "content",
                        "",
                    )
                )

                if published:
                    break

        if not published:
            time_tag = soup.find(
                "time"
            )

            if time_tag:
                published = clean_text(
                    time_tag.get(
                        "datetime",
                        "",
                    )
                    or time_tag.get_text(
                        " ",
                        strip=True,
                    )
                )

        return {
            "final_url": final_url,
            "title": title,
            "summary": truncate_text(
                summary,
                900,
            ),
            "body": truncate_text(
                body_text,
                1800,
            ),
            "image": image_url,
            "published": published,
            "hostname": hostname(
                final_url
            ),
        }

    except Exception as exc:
        print(
            f"Article fetch failed: {exc}"
        )

        return None


# ============================================================
# COUNTY RELEVANCE
# ============================================================

def county_match_score(
    county,
    text,
):
    text_lower = clean_text(
        text
    ).lower()

    score = 0

    aliases = COUNTY_ALIASES.get(
        county,
        [county],
    )

    for alias in aliases:
        alias_lower = alias.lower()

        if alias_lower in text_lower:
            if alias_lower == county.lower():
                score += 8
            else:
                score += 5

    return score


def detect_county(
    title,
    summary,
    preferred_county="",
):
    combined = (
        clean_text(title)
        + " "
        + clean_text(summary)
    )

    scores = []

    for county in COUNTIES:
        score = county_match_score(
            county,
            combined,
        )

        if (
            preferred_county
            and county == preferred_county
        ):
            score += 10

        scores.append(
            (
                score,
                county,
            )
        )

    scores.sort(
        reverse=True
    )

    if not scores:
        return preferred_county

    best_score, best_county = scores[0]

    if best_score <= 0:
        return preferred_county

    return best_county


# ============================================================
# STORY CATEGORY / IMPORTANCE
# ============================================================

def story_category(
    title,
    summary,
):
    text = (
        clean_text(title)
        + " "
        + clean_text(summary)
    ).lower()

    categories = {
        "DEVELOPMENT": [
            "road",
            "hospital",
            "school",
            "water",
            "project",
            "development",
            "construction",
            "infrastructure",
            "bridge",
            "market",
        ],
        "POLITICS": [
            "mp ",
            "governor",
            "senator",
            "president",
            "deputy president",
            "politician",
            "political",
            "party",
            "election",
            "campaign",
        ],
        "SECURITY": [
            "arrest",
            "police",
            "crime",
            "murder",
            "robbery",
            "accident",
            "missing",
            "suspect",
            "security",
        ],
        "ECONOMY": [
            "business",
            "economy",
            "market",
            "trade",
            "farmers",
            "agriculture",
            "prices",
            "income",
            "investment",
        ],
        "HEALTH": [
            "hospital",
            "health",
            "disease",
            "doctor",
            "patients",
            "clinic",
            "medical",
        ],
        "EDUCATION": [
            "school",
            "student",
            "university",
            "education",
            "teacher",
            "exam",
            "college",
        ],
    }

    best_category = "COUNTY NEWS"
    best_score = 0

    for category, words in categories.items():
        score = sum(
            1
            for word in words
            if word in text
        )

        if score > best_score:
            best_score = score
            best_category = category

    return best_category


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def verify_candidate(candidate):
    title = clean_text(
        candidate.get(
            "title",
            "",
        )
    )

    url = candidate.get(
        "url",
        "",
    )

    rss_image = candidate.get(
        "rss_image",
        "",
    )

    if not title or not valid_http_url(
        url
    ):
        return None

    resolved_url = unwrap_google_news_url(
        url
    )

    if not resolved_url:
        resolved_url = url

    if is_search_engine_url(
        resolved_url
    ):
        return None

    article = fetch_article(
        resolved_url,
        rss_image,
    )

    if not article:
        return None

    article_title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    if not article_title:
        article_title = title

    article_summary = clean_text(
        article.get(
            "summary",
            "",
        )
    )

    article_body = clean_text(
        article.get(
            "body",
            "",
        )
    )

    combined = (
        article_title
        + " "
        + article_summary
        + " "
        + article_body
    )

    county = detect_county(
        article_title,
        combined,
        candidate.get(
            "county",
            "",
        ),
    )

    county_score = county_match_score(
        county,
        combined,
    )

    if county_score <= 0:
        return None

    published = (
        article.get(
            "published",
            "",
        )
        or candidate.get(
            "published",
            "",
        )
    )

    if not is_recent(
        published,
        allow_missing=True,
    ):
        return None

    image_url = article.get(
        "image",
        "",
    )

    if not image_url:
        image_url = bing_image_fallback(
            article_title,
            resolved_url,
        )

    if not image_url:
        return None

    source_name = (
        clean_text(
            candidate.get(
                "source_name",
                "",
            )
        )
        or clean_text(
            article.get(
                "hostname",
                "",
            )
        )
    )

    category = story_category(
        article_title,
        article_summary,
    )

    return {
        "title": article_title,
        "county": county,
        "category": category,
        "date": (
            parse_date(
                published
            ).date().isoformat()
            if parse_date(published)
            else now_utc().date().isoformat()
        ),
        "published": published,
        "source_name": source_name,
        "url": resolved_url,
        "image": image_url,
        "summary": truncate_text(
            article_summary
            or article_body,
            850,
        ),
        "story_id": story_hash(
            article_title,
            resolved_url,
        ),
    }


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):
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

    published = parse_date(
        story.get(
            "published",
            "",
        )
    )

    score = 0

    # Recent stories get priority.
    if published:
        age_hours = (
            now_utc() - published
        ).total_seconds() / 3600

        if age_hours <= 6:
            score += 45
        elif age_hours <= 12:
            score += 35
        elif age_hours <= 24:
            score += 25
        elif age_hours <= 48:
            score += 15
        else:
            score += 5

    # Strong local relevance.
    score += min(
        25,
        county_match_score(
            story.get(
                "county",
                "",
            ),
            title
            + " "
            + summary,
        ),
    )

    # Newsworthy terms.
    high_value_words = [
        "announces",
        "launches",
        "approves",
        "opens",
        "orders",
        "arrests",
        "killed",
        "dies",
        "accident",
        "project",
        "billion",
        "million",
        "hospital",
        "road",
        "farmers",
        "school",
        "governor",
        "mp",
        "senator",
        "president",
    ]

    text = (
        title
        + " "
        + summary
    ).lower()

    for word in high_value_words:
        if word in text:
            score += 3

    # Prefer substantial summaries.
    if len(summary) >= 180:
        score += 8
    elif len(summary) >= 80:
        score += 4

    # Real image is mandatory and therefore adds confidence.
    if valid_http_url(
        story.get(
            "image",
            "",
        )
    ):
        score += 10

    story["score"] = score

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
    seen = set()

    print(
        "============================================================"
    )
    print(
        "COLLECTING RIFT VALLEY CANDIDATES"
    )
    print(
        "============================================================"
    )

    for county, query in queries:
        print(
            f"RSS: {county}"
        )

        feed = parse_feed(
            google_news_rss(query)
        )

        if not feed:
            continue

        entries = getattr(
            feed,
            "entries",
            [],
        )

        for entry in entries[:8]:
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

            if not title or not url:
                continue

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

            if not is_recent(
                published,
                allow_missing=True,
            ):
                continue

            key = normalize_title(
                title
            )

            if key in seen:
                continue

            seen.add(key)

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
                )

            rss_image = get_rss_media_image(
                entry
            )

            candidates.append(
                {
                    "county": county,
                    "title": title,
                    "url": url,
                    "published": published,
                    "source_name": source_name,
                    "rss_image": rss_image,
                }
            )

    print(
        f"RSS candidates collected: {len(candidates)}"
    )

    # ========================================================
    # BING FALLBACK
    # Only used when RSS gives too few candidates.
    # ========================================================

    if len(candidates) < 4:
        print(
            "RSS returned fewer than 4 candidates."
        )
        print(
            "Running limited Bing fallback..."
        )

        fallback_queries = [
            (
                "Bomet",
                "Bomet Kenya latest news",
            ),
            (
                "Kericho",
                "Kericho Kenya latest news",
            ),
            (
                "Nakuru",
                "Nakuru Kenya latest news",
            ),
            (
                "Uasin Gishu",
                "Uasin Gishu Kenya latest news",
            ),
        ]

        for county, query in fallback_queries:
            if len(candidates) >= 8:
                break

            results = bing_search(
                query
            )

            for result in results:
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

                if not title:
                    continue

                if not valid_http_url(
                    url
                ):
                    continue

                key = normalize_title(
                    title
                )

                if key in seen:
                    continue

                seen.add(key)

                candidates.append(
                    {
                        "county": county,
                        "title": title,
                        "url": url,
                        "published": "",
                        "source_name": "",
                        "rss_image": "",
                    }
                )

    # Newest first.
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

    candidates = candidates[
        :MAX_CANDIDATES_TO_VERIFY
    ]

    print(
        f"Candidates selected for verification: "
        f"{len(candidates)}"
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"{index}. "
            f"{candidate.get('county')} - "
            f"{candidate.get('title')}"
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

    print(
        "============================================================"
    )
    print(
        "VERIFYING CANDIDATES"
    )
    print(
        "============================================================"
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"VERIFY {index}/{len(candidates)}: "
            f"{candidate.get('title')}"
        )

        try:
            story = verify_candidate(
                candidate
            )

            if story:
                score_story(
                    story
                )

                verified.append(
                    story
                )

                print(
                    "  VERIFIED"
                )
                print(
                    f"  County: {story.get('county')}"
                )
                print(
                    f"  Source: {story.get('source_name')}"
                )
                print(
                    f"  Score: {story.get('score')}"
                )
            else:
                print(
                    "  REJECTED"
                )

        except Exception as exc:
            print(
                f"  Verification error: {exc}"
            )

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking candidates."
        )

    verified.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    verified = verified[
        :MAX_VERIFIED_TO_COMPARE
    ]

    story = verified[0]

    story["selected_at"] = (
        now_utc().isoformat()
    )

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

    print(
        "============================================================"
    )
    print(
        "SELECTED STORY"
    )
    print(
        "============================================================"
    )
    print(
        f"Title: {story.get('title')}"
    )
    print(
        f"County: {story.get('county')}"
    )
    print(
        f"Category: {story.get('category')}"
    )
    print(
        f"Source: {story.get('source_name')}"
    )
    print(
        f"URL: {story.get('url')}"
    )
    print(
        f"Score: {story.get('score')}"
    )
    print(
        f"Image: {story.get('image')}"
    )

    return story


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean_text(
        story.get(
            "title",
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
            "",
        )
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    if not summary:
        summary = (
            "More details are expected "
            "as the situation develops."
        )

    if source:
        source_sentence = (
            f"The report was published by {source}."
        )
    else:
        source_sentence = (
            "The report was published by the cited news source."
        )

    narration = (
        f"Rift Valley Watch. "
        f"{title}. "
        f"This is the latest development from "
        f"{county} County. "
        f"{summary} "
        f"{source_sentence}"
    )

    return truncate_text(
        narration,
        1200,
    )


# ============================================================
# SCRIPT GENERATION
# ============================================================

def build_script(story):
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

    source = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    summary = clean_text(
        story.get(
            "summary",
            "",
        )
    )

    category = clean_text(
        story.get(
            "category",
            "COUNTY NEWS",
        )
    )

    narration = build_narration(
        story
    )

    why_it_matters = (
        f"The development is relevant to "
        f"residents and stakeholders in "
        f"{county} County."
    )

    return {
        "title": title,
        "county": county,
        "category": category,
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
                "text": why_it_matters,
            },
            {
                "label": "SOURCE",
                "text": source,
            },
        ],
    }


# ============================================================
# JSON WRITING
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
# VIDEO GENERATOR IMPORT
# ============================================================

def import_video_generator():
    try:
        from rift_valley_video_generator import (
