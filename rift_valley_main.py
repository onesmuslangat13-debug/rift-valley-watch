# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS ENGINE
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
VIDEO_FILE = os.path.join(
    OUTPUT_DIR,
    "rift_valley_watch_reel.mp4",
)

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
        "bomet",
        "sotik",
        "chepalungu",
        "konoin",
        "bomet east",
        "bomet central",
        "longisa",
        "kaplong",
        "sigorwet",
        "mogogosiek",
    ],
    "Kericho": [
        "kericho",
        "litein",
        "belgut",
        "ainamoi",
        "kipkelion",
        "kipkelion east",
        "kipkelion west",
        "bureti",
        "sigowet",
        "soin",
        "kapsoit",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "bahati",
        "subukia",
        "rongai",
        "kuresoi",
        "kuresoi north",
        "kuresoi south",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "chesumei",
        "emgwen",
        "aldai",
        "nandi hills",
        "tindiret",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "soy",
        "turbo",
        "ainabkoi",
        "kapseret",
        "kesses",
        "moiben",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "marakwet",
        "elgeyo",
        "iten",
        "keiyo",
        "keiyo north",
        "keiyo south",
        "marakwet east",
        "marakwet west",
        "cherangany",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "sigor",
        "pokot south",
        "pokot central",
        "pokot north",
        "kipkomo",
        "kacheliba",
    ],
    "Narok": [
        "narok",
        "narok north",
        "narok south",
        "transmara",
        "transmara west",
        "transmara east",
        "ololulunga",
        "suswa",
        "maasai mara",
        "mara",
    ],
}


# ============================================================
# SPEED SETTINGS
# ============================================================

RSS_TIMEOUT = 5
ARTICLE_TIMEOUT = 6
IMAGE_TIMEOUT = 4
SEARCH_TIMEOUT = 5

MAX_AGE_HOURS = 72

MAX_CANDIDATES_TO_VERIFY = 12
MAX_VERIFIED_TO_COMPARE = 6

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

    value = re.sub(
        r"https?://\S+",
        "",
        value,
    )

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


def truncate_text(text, limit=800):
    text = clean_text(text)

    if len(text) <= limit:
        return text

    shortened = text[:limit].rsplit(" ", 1)[0]

    return shortened + "..."


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

    blocked = [
        "google.",
        "bing.com",
        "search.yahoo.",
        "duckduckgo.com",
    ]

    return any(
        item in host
        for item in blocked
    )


def is_svg_url(url):
    if not url:
        return True

    lower = url.lower()

    return (
        ".svg" in lower
        or "sprite" in lower
        or "favicon" in lower
    )


def story_hash(title, url=""):
    raw = (
        normalize_title(title)
        + "|"
        + clean_text(url)
    )

    return hashlib.sha1(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def now_utc():
    return datetime.now(timezone.utc)


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    text = clean_text(value)

    if not text:
        return None

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M %z",
        "%d %b %Y %H:%M:%S %z",
        "%d %b %Y %H:%M %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
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

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            continue

    try:
        from email.utils import (
            parsedate_to_datetime
        )

        dt = parsedate_to_datetime(text)

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def is_recent(dt, max_hours=MAX_AGE_HOURS):
    if not dt:
        return True

    age = now_utc() - dt

    return age <= timedelta(
        hours=max_hours
    )


# ============================================================
# REQUEST
# ============================================================

def get_response(
    url,
    timeout=RSS_TIMEOUT,
    allow_redirects=True,
):
    if not valid_http_url(url):
        return None

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

        if response.status_code >= 400:
            return None

        return response

    except Exception:
        return None


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_rss(query):
    encoded = quote_plus(query)

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}&hl=en-KE&gl=KE&ceid=KE:en"
    )

    return get_response(
        url,
        timeout=RSS_TIMEOUT,
    )


def parse_feed(response, county_hint):
    candidates = []

    if response is None:
        return candidates

    try:
        feed = feedparser.parse(
            response.content
        )
    except Exception:
        return candidates

    for entry in feed.entries[:8]:

        title = clean_text(
            getattr(
                entry,
                "title",
                "",
            )
        )

        link = clean_text(
            getattr(
                entry,
                "link",
                "",
            )
        )

        summary = clean_text(
            getattr(
                entry,
                "summary",
                getattr(
                    entry,
                    "description",
                    "",
                ),
            )
        )

        published_raw = (
            getattr(
                entry,
                "published",
                "",
            )
            or getattr(
                entry,
                "updated",
                "",
            )
        )

        published = parse_date(
            published_raw
        )

        if not title or not link:
            continue

        if (
            published
            and not is_recent(published)
        ):
            continue

        image = get_rss_media_image(entry)

        candidates.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "published": (
                    published.isoformat()
                    if published
                    else ""
                ),
                "county_hint": county_hint,
                "rss_image": image,
            }
        )

    return candidates


def get_rss_media_image(entry):
    try:
        media_content = getattr(
            entry,
            "media_content",
            [],
        )

        for item in media_content or []:
            url = item.get("url", "")

            if (
                valid_http_url(url)
                and not is_svg_url(url)
            ):
                return url

    except Exception:
        pass

    try:
        media_thumbnail = getattr(
            entry,
            "media_thumbnail",
            [],
        )

        for item in media_thumbnail or []:
            url = item.get("url", "")

            if (
                valid_http_url(url)
                and not is_svg_url(url)
            ):
                return url

    except Exception:
        pass

    try:
        links = getattr(
            entry,
            "links",
            [],
        )

        for item in links or []:
            rel = item.get("rel", "")
            typ = item.get("type", "")
            url = item.get("href", "")

            if (
                rel == "enclosure"
                and "image" in typ.lower()
                and valid_http_url(url)
                and not is_svg_url(url)
            ):
                return url

    except Exception:
        pass

    return ""


# ============================================================
# GOOGLE NEWS URL RESOLUTION
# ============================================================

def unwrap_google_news_url(url):
    if not valid_http_url(url):
        return ""

    if "news.google.com" not in hostname(url):
        return url

    response = get_response(
        url,
        timeout=ARTICLE_TIMEOUT,
        allow_redirects=True,
    )

    if response is None:
        return url

    final_url = response.url

    if valid_http_url(final_url):
        if "news.google.com" not in hostname(
            final_url
        ):
            return final_url

    return url


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query):
    url = (
        "https://www.bing.com/search?"
        f"q={quote_plus(query)}"
        f"&count={BING_RESULT_LIMIT}"
    )

    response = get_response(
        url,
        timeout=SEARCH_TIMEOUT,
    )

    if response is None:
        return []

    results = []

    try:
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
            )

            title = clean_text(
                link.get_text(
                    " ",
                    strip=True,
                )
            )

            snippet_node = item.select_one(
                ".b_caption p"
            )

            snippet = ""

            if snippet_node:
                snippet = clean_text(
                    snippet_node.get_text(
                        " ",
                        strip=True,
                    )
                )

            if not valid_http_url(href):
                continue

            if is_search_engine_url(href):
                continue

            results.append(
                {
                    "title": title,
                    "url": href,
                    "summary": snippet,
                }
            )

    except Exception:
        return []

    return results


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(
    soup,
    base_url,
):
    images = []

    if soup is None:
        return images

    meta_names = [
        "og:image",
        "twitter:image",
        "twitter:image:src",
    ]

    for name in meta_names:

        node = soup.find(
            "meta",
            attrs={
                "property": name,
            },
        )

        if node is None:
            node = soup.find(
                "meta",
                attrs={
                    "name": name,
                },
            )

        if node:
            content = node.get(
                "content",
                "",
            )

            if content:
                images.append(content)

    for img in soup.find_all("img")[:30]:

        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or img.get("data-original")
        )

        if src:
            images.append(src)

    normalized = []

    for image in images:

        if not image:
            continue

        image = html.unescape(
            image.strip()
        )

        if image.startswith("//"):
            image = "https:" + image

        elif image.startswith("/"):
            parsed = urlparse(base_url)

            image = (
                parsed.scheme
                + "://"
                + parsed.netloc
                + image
            )

        if not valid_http_url(image):
            continue

        if is_svg_url(image):
            continue

        if image not in normalized:
            normalized.append(image)

    return normalized


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

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        if (
            "image/" not in content_type
            and not url.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
        ):
            return False

        return True

    except Exception:
        return False


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(
    article_html,
    article_url,
):
    if not article_html:
        return ""

    try:
        soup = BeautifulSoup(
            article_html,
            "html.parser",
        )

        candidates = extract_image_candidates(
            soup,
            article_url,
        )

        for image in candidates[
            :MAX_IMAGE_CHECKS
        ]:
            if validate_image_url(image):
                return image

    except Exception:
        pass

    return ""


# ============================================================
# BING IMAGE FALLBACK
# ============================================================

def bing_image_fallback(title, county):
    query = (
        f"{title} {county} Kenya news photo"
    )

    url = (
        "https://www.bing.com/images/search?"
        f"q={quote_plus(query)}"
        "&form=HDRSC2&first=1"
    )

    response = get_response(
        url,
        timeout=SEARCH_TIMEOUT,
    )

    if response is None:
        return ""

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for node in soup.select(
            "a.iusc"
        )[:MAX_BING_IMAGES]:

            metadata = node.get(
                "m",
                "",
            )

            if not metadata:
                continue

            try:
                data = json.loads(metadata)

                image_url = data.get(
                    "murl",
                    "",
                )

                if (
                    valid_http_url(image_url)
                    and not is_svg_url(image_url)
                ):
                    if validate_image_url(
                        image_url
                    ):
                        return image_url

            except Exception:
                continue

    except Exception:
        pass

    return ""


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_article(url):
    if not valid_http_url(url):
        return {}

    resolved = unwrap_google_news_url(url)

    if not valid_http_url(resolved):
        resolved = url

    response = get_response(
        resolved,
        timeout=ARTICLE_TIMEOUT,
    )

    if response is None:
        return {
            "url": resolved,
            "title": "",
            "body": "",
            "image": "",
            "source": hostname(resolved),
            "published": None,
        }

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for node in soup(
            [
                "script",
                "style",
                "noscript",
                "svg",
            ]
        ):
            node.decompose()

        title = ""

        og_title = soup.find(
            "meta",
            property="og:title",
        )

        if og_title:
            title = clean_text(
                og_title.get(
                    "content",
                    "",
                )
            )

        if not title and soup.title:
            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        paragraphs = []

        for paragraph in soup.find_all("p"):
            text = clean_text(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 35:
                paragraphs.append(text)

        body = " ".join(paragraphs)

        image = find_article_image(
            response.text,
            response.url,
        )

        source = ""

        meta_site = soup.find(
            "meta",
            property="og:site_name",
        )

        if meta_site:
            source = clean_text(
                meta_site.get(
                    "content",
                    "",
                )
            )

        if not source:
            source = hostname(response.url)

        published = None

        for meta_name in [
            "article:published_time",
            "datePublished",
            "pubdate",
        ]:
            node = soup.find(
                "meta",
                attrs={
                    "property": meta_name,
                },
            )

            if node is None:
                node = soup.find(
                    "meta",
                    attrs={
                        "name": meta_name,
                    },
                )

            if node:
                published = parse_date(
                    node.get(
                        "content",
                        "",
                    )
                )

                if published:
                    break

        return {
            "url": response.url,
            "title": title,
            "body": body,
            "image": image,
            "source": source,
            "published": published,
        }

    except Exception:
        return {
            "url": resolved,
            "title": "",
            "body": "",
            "image": "",
            "source": hostname(resolved),
            "published": None,
        }


# ============================================================
# COUNTY DETECTION
# ============================================================

def county_match_score(text, county):
    text = clean_text(text).lower()

    score = 0

    aliases = COUNTY_ALIASES.get(
        county,
        [],
    )

    for alias in aliases:

        alias_lower = alias.lower()

        if alias_lower in text:
            score += 1

            if alias_lower == county.lower():
                score += 2

    return score


def detect_county(
    title,
    body,
    hint="",
):
    combined = (
        clean_text(title)
        + " "
        + clean_text(body)
    )

    scores = {}

    for county in COUNTIES:
        scores[county] = county_match_score(
            combined,
            county,
        )

    best_county = max(
        scores,
        key=scores.get,
    )

    if scores[best_county] > 0:
        return best_county

    if hint in COUNTIES:
        return hint

    return ""


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

    politics = [
        "president",
        "mp ",
        "governor",
        "senator",
        "deputy president",
        "politician",
        "politics",
        "party",
        "election",
        "government",
        "ruto",
        "uda",
        "odm",
        "parliament",
        "assembly",
        "ward",
        "campaign",
    ]

    crime = [
        "police",
        "arrested",
        "murder",
        "killed",
        "robbery",
        "crime",
        "suspect",
        "court",
        "charged",
    ]

    business = [
        "business",
        "economy",
        "market",
        "company",
        "investment",
        "jobs",
        "employment",
        "trade",
        "farmers",
        "agriculture",
    ]

    health = [
        "hospital",
        "health",
        "disease",
        "doctor",
        "patients",
        "clinic",
    ]

    if any(word in text for word in politics):
        return "Politics"

    if any(word in text for word in crime):
        return "Crime & Security"

    if any(word in text for word in business):
        return "Business & Economy"

    if any(word in text for word in health):
        return "Health"

    return "Rift Valley News"


# ============================================================
# VERIFY CANDIDATE
# ============================================================

def verify_candidate(candidate):
    title = clean_text(
        candidate.get("title", "")
    )

    original_url = clean_text(
        candidate.get("url", "")
    )

    rss_summary = clean_text(
        candidate.get("summary", "")
    )

    county_hint = clean_text(
        candidate.get("county_hint", "")
    )

    rss_image = clean_text(
        candidate.get("rss_image", "")
    )

    print()
    print("--------------------------------------------")
    print("VERIFYING:", title[:150])

    if not title:
        print("REJECTED: empty title")
        return None

    article = {}

    try:
        article = fetch_article(
            original_url
        )
    except Exception as exc:
        print(
            "Article fetch failed:",
            repr(exc),
        )

    article_title = clean_text(
        article.get("title", "")
    )

    article_body = clean_text(
        article.get("body", "")
    )

    article_url = clean_text(
        article.get("url", "")
    )

    article_image = clean_text(
        article.get("image", "")
    )

    article_source = clean_text(
        article.get("source", "")
    )

    article_date = article.get(
        "published"
    )

    final_title = (
        article_title
        or title
    )

    final_body = (
        article_body
        or rss_summary
    )

    final_url = (
        article_url
        or original_url
    )

    county = detect_county(
        final_title,
        final_body,
        county_hint,
    )

    if not county:
        county = county_hint

    if county not in COUNTIES:
        print(
            "REJECTED: county unknown"
        )
        return None

    published = (
        article_date
        or parse_date(
            candidate.get(
                "published",
                "",
            )
        )
    )

    if (
        published
        and not is_recent(published)
    ):
        print(
            "REJECTED: story too old:",
            published.isoformat(),
        )
        return None

    # --------------------------------------------------------
    # IMAGE 1: ARTICLE
    # --------------------------------------------------------

    image = ""

    if article_image:
        if validate_image_url(
            article_image
        ):
            image = article_image
            print("IMAGE: article")

    # --------------------------------------------------------
    # IMAGE 2: RSS
    # --------------------------------------------------------

    if not image and rss_image:
        if validate_image_url(rss_image):
            image = rss_image
            print("IMAGE: RSS")

    # --------------------------------------------------------
    # IMAGE 3: ARTICLE PAGE
    # --------------------------------------------------------

    if not image and final_url:
        try:
            response = get_response(
                final_url,
                timeout=ARTICLE_TIMEOUT,
            )

            if response is not None:
                image = find_article_image(
                    response.text,
                    response.url,
                )

                if image:
                    print(
                        "IMAGE: page extraction"
                    )

        except Exception:
            pass

    # --------------------------------------------------------
    # IMAGE 4: BING
    # --------------------------------------------------------

    if not image:
        print(
            "Trying Bing image fallback..."
        )

        image = bing_image_fallback(
            final_title,
            county,
        )

        if image:
            print(
                "IMAGE: Bing fallback"
            )

    if not image:
        print(
            "REJECTED: no usable image"
        )
        return None

    source_name = (
        article_source
        or hostname(final_url)
        or "News Source"
    )

    source_name = re.sub(
        r"^www\.",
        "",
        source_name,
        flags=re.I,
    )

    summary = rss_summary

    if not summary and final_body:
        summary = truncate_text(
            final_body,
            450,
        )

    if not summary:
        summary = final_title

    category = story_category(
        final_title,
        final_body,
    )

    story = {
        "title": final_title,
        "county": county,
        "category": category,
        "published": (
            published.isoformat()
            if published
            else ""
        ),
        "summary": summary,
        "body": truncate_text(
            final_body,
            3000,
        ),
        "image": image,
        "image_url": image,
        "source_name": source_name,
        "source": source_name,
        "url": final_url,
        "resolved_url": final_url,
        "verified": True,
        "story_id": story_hash(
            final_title,
            final_url,
        ),
    }

    print("VERIFIED:", final_title[:150])
    print("COUNTY:", county)
    print("SOURCE:", source_name)
    print("IMAGE:", image[:150])

    return story


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):
    score = 0

    title = clean_text(
        story.get("title", "")
    ).lower()

    body = clean_text(
        story.get("body", "")
    ).lower()

    if story.get("county"):
        score += 20

    if story.get("verified"):
        score += 30

    if story.get("image"):
        score += 25

    if story.get("published"):
        score += 10

    keywords = [
        "today",
        "latest",
        "new",
        "announces",
        "says",
        "reports",
        "launches",
        "approves",
        "arrested",
        "killed",
        "elected",
        "apologises",
        "apologizes",
        "accuses",
        "orders",
        "opens",
        "reveals",
    ]

    for keyword in keywords:
        if keyword in title:
            score += 4

    if len(body) >= 300:
        score += 5

    if len(body) >= 700:
        score += 5

    return score


# ============================================================
# CANDIDATE COLLECTION
# ============================================================

def collect_candidates():
    print()
    print("============================================")
    print("COLLECTING RIFT VALLEY NEWS")
    print("============================================")

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
            '"Uasin Gishu Kenya latest news',
        ),
        (
            "Elgeyo-Marakwet",
            'Elgeyo-Marakwet Kenya latest news',
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

    for county, query in queries:
        print("RSS:", county)

        try:
            response = google_news_rss(
                query
            )

            items = parse_feed(
                response,
                county,
            )

            print(
                "  found",
                len(items),
            )

            for item in items:
                key = normalize_title(
                    item.get(
                        "title",
                        "",
                    )
                )

                if not key:
                    continue

                if key in seen:
                    continue

                seen.add(key)
                candidates.append(item)

        except Exception as exc:
            print(
                "RSS error:",
                repr(exc),
            )

        if RSS_DELAY:
            time.sleep(RSS_DELAY)

    # --------------------------------------------------------
    # BING FALLBACK
    # --------------------------------------------------------

    if len(candidates) < 4:
        print()
        print(
            "RSS returned few candidates. "
            "Using Bing fallback."
        )

        bing_queries = [
            "Bomet Kenya latest news",
            "Kericho Kenya latest news",
            "Nakuru Kenya latest news",
            "Uasin Gishu Kenya latest news",
        ]

        for query in bing_queries:
            print("Bing:", query)

            try:
                results = bing_search(query)

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

                    summary = clean_text(
                        result.get(
                            "summary",
                            "",
                        )
                    )

                    if not title or not url:
                        continue

                    key = normalize_title(title)

                    if key in seen:
                        continue

                    hint = detect_county(
                        title,
                        summary,
                    )

                    if not hint:
                        continue

                    seen.add(key)

                    candidates.append(
                        {
                            "title": title,
                            "url": url,
                            "summary": summary,
                            "published": "",
                            "county_hint": hint,
                            "rss_image": "",
                        }
                    )

            except Exception as exc:
                print(
                    "Bing error:",
                    repr(exc),
                )

    def sort_key(item):
        dt = parse_date(
            item.get(
                "published",
                "",
            )
        )

        if dt:
            return dt.timestamp()

        return 0

    candidates.sort(
        key=sort_key,
        reverse=True,
    )

    print()
    print(
        "TOTAL CANDIDATES:",
        len(candidates),
    )

    return candidates


# ============================================================
# SELECT STORY
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError(
            "No Rift Valley candidates were found."
        )

    verified = []

    limit = min(
        len(candidates),
        MAX_CANDIDATES_TO_VERIFY,
    )

    print()
    print(
        "VERIFYING UP TO",
        limit,
        "CANDIDATES",
    )

    for index, candidate in enumerate(
        candidates[:limit],
        start=1,
    ):
        print()
        print(
            "[%d/%d] %s"
            % (
                index,
                limit,
                candidate.get(
                    "title",
                    "",
                )[:140],
            )
        )

        try:
            story = verify_candidate(
                candidate
            )

            if story:
                verified.append(story)
                print("ACCEPTED")
            else:
                print("REJECTED")

        except Exception as exc:
            print(
                "Verification exception:",
                repr(exc),
            )
            traceback.print_exc()

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking candidates."
        )

    for story in verified:
        story["_score"] = score_story(
            story
        )

    verified.sort(
        key=lambda item: (
            item.get("_score", 0),
            item.get("published", ""),
        ),
        reverse=True,
    )

    selected = verified[0]

    selected.pop(
        "_score",
        None,
    )

    print()
    print("============================================")
    print("SELECTED STORY")
    print("============================================")
    print(
        "TITLE:",
        selected.get("title", ""),
    )
    print(
        "COUNTY:",
        selected.get("county", ""),
    )
    print(
        "CATEGORY:",
        selected.get("category", ""),
    )
    print(
        "SOURCE:",
        selected.get("source_name", ""),
    )
    print(
        "IMAGE:",
        selected.get("image", ""),
    )

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean_text(
        story.get("title", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    category = clean_text(
        story.get("category", "")
    )

    source = clean_text(
        story.get("source_name", "")
    )

    if not summary:
        summary = title

    narration = (
        "Rift Valley Watch. "
        f"Here is the latest news from {county}. "
        f"{title}. "
        f"{summary}. "
        f"This is a {category} story "
        f"reported by {source}."
    )

    return clean_text(narration)


# ============================================================
# SCRIPT
# ============================================================

def build_script(story):
    narration = build_narration(story)

    script = {
        "title": story.get(
            "title",
            "",
        ),
        "county": story.get(
            "county",
            "",
        ),
        "category": story.get(
            "category",
            "",
        ),
        "narration": narration,
        "source_name": story.get(
            "source_name",
            "",
        ),
        "source": story.get(
            "source",
            "",
        ),
        "url": story.get(
            "url",
            "",
        ),
        "image": story.get(
            "image",
            "",
        ),
        "duration_target": 35,
    }

    return script


# ============================================================
# JSON WRITER
# ============================================================

def write_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# VIDEO GENERATOR IMPORT
# ============================================================

def import_video_generator():
    try:
        from rift_valley_video_generator import (
            generate_video
        )

        return generate_video

    except Exception as exc:
        print()
        print(
            "Could not import "
            "rift_valley_video_generator."
        )
        print(
            "ERROR:",
            repr(exc),
        )
        raise


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    print()
    print("============================================")
    print("RIFT VALLEY WATCH")
    print("AUTOMATED NEWS VIDEO PIPELINE")
    print("============================================")
    print()

    try:
        # ----------------------------------------------------
        # 1. SELECT STORY
        # ----------------------------------------------------

        story = select_story()

        # ----------------------------------------------------
        # 2. BUILD SCRIPT
        # ----------------------------------------------------

        script = build_script(story)

        # ----------------------------------------------------
        # 3. SAVE STORY
        # ----------------------------------------------------

        write_json(
            STORY_FILE,
            story,
        )

        print()
        print(
            "Saved:",
            STORY_FILE,
        )

        # ----------------------------------------------------
        # 4. SAVE SCRIPT
        # ----------------------------------------------------

        write_json(
            SCRIPT_FILE,
            script,
        )

        print(
            "Saved:",
            SCRIPT_FILE,
        )

        # ----------------------------------------------------
        # 5. GENERATE VIDEO
        # ----------------------------------------------------

        generate_video = import_video_generator()

        print()
        print("GENERATING VIDEO...")
        print()

        result = generate_video(story)

        print()
        print(
            "VIDEO GENERATOR RESULT:",
            repr(result),
        )

        # ----------------------------------------------------
        # 6. CHECK FINAL MP4
        # ----------------------------------------------------

        if not os.path.exists(VIDEO_FILE):

            # Some generators may return another path.
            if isinstance(result, str):
                if os.path.exists(result):
                    print(
                        "Generator returned:",
                        result,
                    )

            raise RuntimeError(
                "Video generator completed but "
                "output/rift_valley_watch_reel.mp4 "
                "was not created."
            )

        file_size = os.path.getsize(
            VIDEO_FILE
        )

        if file_size <= 0:
            raise RuntimeError(
                "Final MP4 exists but is empty."
            )

        elapsed = time.time() - start_time

        print()
        print("============================================")
        print("RIFT VALLEY WATCH COMPLETE")
        print("============================================")
        print(
            "VIDEO:",
            VIDEO_FILE,
        )
        print(
            "SIZE:",
            "%.2f MB"
            % (
                file_size / 1024 / 1024
            ),
        )
        print(
            "RUNTIME:",
            "%.1f seconds"
            % elapsed,
        )
        print()
        print("SUCCESS")
        print()

        return VIDEO_FILE

    except Exception as exc:
        print()
        print("============================================")
        print("RIFT VALLEY WATCH FAILED")
        print("============================================")
        print(
            "ERROR:",
            repr(exc),
        )
        print()

        traceback.print_exc()

        raise


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
