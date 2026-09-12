# ============================================================
# RIFT VALLEY WATCH
# COMPLETE MAIN NEWS ENGINE
# ============================================================

import os
import re
import json
import time
import html
import hashlib
import traceback

from datetime import datetime, timezone

from urllib.parse import (
    urlparse,
    urljoin,
    quote_plus,
    parse_qs,
    unquote,
)

import requests
import feedparser

from bs4 import BeautifulSoup


# ============================================================
# BASE DIRECTORIES
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "output",
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
)

AUDIO_DIR = os.path.join(
    BASE_DIR,
    "audio",
)

ASSETS_DIR = os.path.join(
    BASE_DIR,
    "assets",
)


# ============================================================
# OUTPUT FILES
# ============================================================

STORY_FILE = os.path.join(
    DATA_DIR,
    "selected_story.json",
)

SCRIPT_FILE = os.path.join(
    DATA_DIR,
    "selected_script.json",
)

# IMPORTANT:
# The video generator creates this exact filename.
VIDEO_FILE = os.path.join(
    OUTPUT_DIR,
    "rift_valley_watch_reel.mp4",
)


# ============================================================
# NETWORK SETTINGS
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

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36 "
    "RiftValleyWatch/1.0"
)


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
        "bomet county",
        "bomet town",
        "sotik",
        "chepalungu",
        "konoin",
        "mau forest",
    ],

    "Kericho": [
        "kericho",
        "kericho county",
        "kericho town",
        "litein",
        "belgut",
        "ainamoi",
        "kipkelion",
        "sigowet",
        "soin",
    ],

    "Nakuru": [
        "nakuru",
        "nakuru county",
        "nakuru town",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "bahati",
        "rongai",
        "subukia",
    ],

    "Nandi": [
        "nandi",
        "nandi county",
        "kapsabet",
        "nandi hills",
        "mosoriot",
        "chesumei",
        "aldai",
        "tindiret",
    ],

    "Uasin Gishu": [
        "uasin gishu",
        "uasin gishu county",
        "eldoret",
        "eldoret town",
        "moiben",
        "ainabkoi",
        "kapseret",
        "kesses",
        "soy",
        "turbo",
    ],

    "Elgeyo-Marakwet": [
        "elgeyo marakwet",
        "elgeyo-marakwet",
        "elgeyo",
        "marakwet",
        "iten",
        "kabarnet",
        "keiyo",
        "keiyo north",
        "keiyo south",
        "marakwet east",
        "marakwet west",
    ],

    "West Pokot": [
        "west pokot",
        "west pokot county",
        "kapenguria",
        "pokot",
        "sigor",
        "kacheliba",
        "pokot south",
        "pokot central",
    ],

    "Narok": [
        "narok",
        "narok county",
        "narok town",
        "kilgoris",
        "transmara",
        "mara",
        "suswa",
        "ololulunga",
    ],
}


# ============================================================
# DIRECTORY SETUP
# ============================================================

def ensure_directories():

    directories = [
        BASE_DIR,
        OUTPUT_DIR,
        DATA_DIR,
        AUDIO_DIR,
        ASSETS_DIR,
    ]

    for directory in directories:

        if directory:
            os.makedirs(
                directory,
                exist_ok=True,
            )


# ============================================================
# BASIC TEXT HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    value = html.unescape(
        value
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


def truncate_text(
    text,
    length=400,
):

    text = clean_text(
        text
    )

    if len(text) <= length:
        return text

    truncated = text[:length]

    if " " in truncated:

        truncated = truncated.rsplit(
            " ",
            1,
        )[0]

    return (
        truncated.rstrip(
            " ,.;:-"
        )
        + "..."
    )


def normalize_title(title):

    title = clean_text(
        title
    ).lower()

    title = re.sub(
        r"[^\w\s]",
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

        parsed = urlparse(
            str(url).strip()
        )

        return (
            parsed.scheme
            in (
                "http",
                "https",
            )
            and bool(
                parsed.netloc
            )
        )

    except Exception:

        return False


def hostname(url):

    try:

        return urlparse(
            url
        ).netloc

    except Exception:

        return ""


def is_svg_url(url):

    if not url:
        return False

    lower = url.lower()

    if ".svg" in lower:
        return True

    if "image/svg" in lower:
        return True

    return False


# ============================================================
# TIME / DATE HELPERS
# ============================================================

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

        if value.tzinfo is None:

            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    value = clean_text(
        value
    )

    if not value:
        return None

    # --------------------------------------------------------
    # ISO
    # --------------------------------------------------------

    try:

        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # COMMON WEB DATES
    # --------------------------------------------------------

    formats = [

        "%a, %d %b %Y %H:%M:%S %z",

        "%a, %d %b %Y %H:%M:%S GMT",

        "%d %b %Y %H:%M:%S %z",

        "%Y-%m-%d %H:%M:%S",

        "%Y-%m-%d",

        "%d/%m/%Y",

        "%d-%m-%Y",
    ]

    for fmt in formats:

        try:

            parsed = datetime.strptime(
                value,
                fmt,
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except Exception:

            continue

    return None


def is_recent(value):

    parsed = parse_date(
        value
    )

    if parsed is None:
        return False

    age = (
        now_utc() - parsed
    ).total_seconds() / 3600

    if age < -6:
        return True

    return age <= MAX_AGE_HOURS


# ============================================================
# HTTP
# ============================================================

def get_response(
    url,
    timeout=10,
):

    if not valid_http_url(
        url
    ):
        return None

    headers = {

        "User-Agent": USER_AGENT,

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,"
            "image/webp,"
            "*/*;q=0.8"
        ),

        "Accept-Language":
            "en-US,en;q=0.9",
    }

    try:

        response = requests.get(

            url,

            headers=headers,

            timeout=timeout,

            allow_redirects=True,
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

    encoded = quote_plus(
        query
    )

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def parse_feed(feed_url):

    try:

        response = get_response(
            feed_url,
            timeout=RSS_TIMEOUT,
        )

        if response is None:
            return []

        feed = feedparser.parse(
            response.content
        )

        return list(
            getattr(
                feed,
                "entries",
                [],
            )
        )

    except Exception:

        return []


# ============================================================
# GOOGLE NEWS URL RESOLUTION
# ============================================================

def unwrap_google_news_url(url):

    if not url:
        return ""

    if (
        "news.google.com"
        not in url.lower()
    ):
        return url

    try:

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

            values = query.get(
                key,
                [],
            )

            if values:

                candidate = unquote(
                    values[0]
                )

                if valid_http_url(
                    candidate
                ):

                    return candidate

    except Exception:
        pass

    response = get_response(
        url,
        timeout=SEARCH_TIMEOUT,
    )

    if response is not None:

        final_url = response.url

        if valid_http_url(
            final_url
        ):

            if (
                "news.google.com"
                not in final_url.lower()
            ):

                return final_url

    return url


# ============================================================
# BING SEARCH
# ============================================================

def bing_search(query):

    results = []

    encoded = quote_plus(
        query
    )

    url = (
        "https://www.bing.com/search?"
        f"q={encoded}"
        f"&count={BING_RESULT_LIMIT}"
        "&setlang=en"
    )

    response = get_response(
        url,
        timeout=SEARCH_TIMEOUT,
    )

    if response is None:
        return results

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for item in soup.select(
            "li.b_algo"
        )[:BING_RESULT_LIMIT]:

            link = item.find(
                "a"
            )

            if link is None:
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

            paragraph = item.find(
                "p"
            )

            summary = ""

            if paragraph:

                summary = clean_text(
                    paragraph.get_text(
                        " ",
                        strip=True,
                    )
                )

            if valid_http_url(
                href
            ):

                results.append(
                    {
                        "title": title,
                        "url": href,
                        "summary": summary,
                    }
                )

    except Exception:
        pass

    return results


# ============================================================
# RSS IMAGE
# ============================================================

def get_rss_media_image(
    entry
):

    media_content = entry.get(
        "media_content",
        [],
    )

    for media in media_content:

        if not isinstance(
            media,
            dict,
        ):
            continue

        url = (
            media.get("url")
            or media.get("href")
            or ""
        )

        if (
            valid_http_url(url)
            and not is_svg_url(url)
        ):

            return url

    media_thumbnail = entry.get(
        "media_thumbnail",
        [],
    )

    for media in media_thumbnail:

        if not isinstance(
            media,
            dict,
        ):
            continue

        url = media.get(
            "url",
            "",
        )

        if (
            valid_http_url(url)
            and not is_svg_url(url)
        ):

            return url

    enclosures = entry.get(
        "enclosures",
        [],
    )

    for enclosure in enclosures:

        if not isinstance(
            enclosure,
            dict,
        ):
            continue

        url = (
            enclosure.get("href")
            or enclosure.get("url")
        )

        if (
            valid_http_url(url)
            and not is_svg_url(url)
        ):

            return url

    return ""


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(
    soup,
    base_url,
):

    candidates = []

    selectors = [

        (
            "meta",
            {
                "property":
                    "og:image"
            },
        ),

        (
            "meta",
            {
                "name":
                    "twitter:image"
            },
        ),

        (
            "meta",
            {
                "property":
                    "twitter:image"
            },
        ),

        (
            "link",
            {
                "rel":
                    "image_src"
            },
        ),
    ]

    for tag_name, attrs in selectors:

        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):

            value = (
                tag.get("content")
                or tag.get("href")
                or ""
            )

            if value:

                candidates.append(
                    value
                )

    for image in soup.find_all(
        "img"
    ):

        for key in [

            "src",

            "data-src",

            "data-original",

            "data-lazy-src",

            "data-image",
        ]:

            value = image.get(
                key
            )

            if value:

                candidates.append(
                    value
                )

    output = []

    seen = set()

    for value in candidates:

        value = clean_text(
            value
        )

        if not value:
            continue

        if value.startswith(
            "//"
        ):

            value = (
                "https:"
                + value
            )

        elif value.startswith(
            "/"
        ):

            value = urljoin(
                base_url,
                value,
            )

        elif not value.startswith(
            "http"
        ):

            value = urljoin(
                base_url,
                value,
            )

        if not valid_http_url(
            value
        ):
            continue

        if is_svg_url(
            value
        ):
            continue

        if value in seen:
            continue

        seen.add(
            value
        )

        output.append(
            value
        )

    return output


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_url(url):

    if not valid_http_url(
        url
    ):
        return False

    if is_svg_url(
        url
    ):
        return False

    response = get_response(
        url,
        timeout=IMAGE_TIMEOUT,
    )

    if response is None:
        return False

    content_type = (
        response.headers.get(
            "Content-Type",
            "",
        )
        .lower()
    )

    valid_types = [

        "image/jpeg",

        "image/png",

        "image/webp",

        "image/gif",

        "image/avif",
    ]

    for image_type in valid_types:

        if image_type in content_type:
            return True

    data = response.content[:20]

    signatures = [

        b"\xff\xd8\xff",

        b"\x89PNG",

        b"GIF8",

        b"RIFF",
    ]

    return any(
        data.startswith(
            signature
        )
        for signature in signatures
    )


# ============================================================
# ARTICLE IMAGE
# ============================================================

def find_article_image(
    article_url,
    rss_image="",
):

    if rss_image:

        if validate_image_url(
            rss_image
        ):

            return rss_image

    response = get_response(
        article_url,
        timeout=ARTICLE_TIMEOUT,
    )

    if response is None:
        return ""

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        candidates = (
            extract_image_candidates(
                soup,
                article_url,
            )
        )

        checked = 0

        for image_url in candidates:

            if (
                checked
                >= MAX_IMAGE_CHECKS
            ):
                break

            checked += 1

            if validate_image_url(
                image_url
            ):

                return image_url

    except Exception:
        pass

    return ""


# ============================================================
# BING IMAGE FALLBACK
# ============================================================

def bing_image_fallback(
    title,
    county,
):

    queries = [

        f"{title} {county} Kenya",

        f"{county} Kenya latest news",
    ]

    for query in queries:

        results = bing_search(
            query
        )

        for item in results[
            :MAX_BING_IMAGES
        ]:

            url = item.get(
                "url",
                "",
            )

            if not valid_http_url(
                url
            ):
                continue

            image = find_article_image(
                url,
                "",
            )

            if image:
                return image

    return ""


# ============================================================
# ARTICLE FETCH
# ============================================================

def fetch_article(url):

    response = get_response(
        url,
        timeout=ARTICLE_TIMEOUT,
    )

    if response is None:

        return {
            "title": "",
            "summary": "",
            "image": "",
            "date": None,
            "text": "",
        }

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

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

        if (
            not title
            and soup.title
        ):

            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True,
                )
            )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = ""

        meta_description = soup.find(
            "meta",
            attrs={
                "name":
                    "description"
            },
        )

        if meta_description:

            description = clean_text(
                meta_description.get(
                    "content",
                    "",
                )
            )

        if not description:

            og_description = soup.find(
                "meta",
                property=
                    "og:description",
            )

            if og_description:

                description = clean_text(
                    og_description.get(
                        "content",
                        "",
                    )
                )

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        image = ""

        candidates = (
            extract_image_candidates(
                soup,
                url,
            )
        )

        checked = 0

        for candidate in candidates:

            if (
                checked
                >= MAX_IMAGE_CHECKS
            ):
                break

            checked += 1

            if validate_image_url(
                candidate
            ):

                image = candidate

                break

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        date_value = None

        date_meta_names = [

            "article:published_time",

            "article:modified_time",

            "date",

            "pubdate",

            "publish-date",

            "published_time",
        ]

        for meta_name in date_meta_names:

            tag = soup.find(
                "meta",
                attrs={
                    "property":
                        meta_name
                },
            )

            if tag is None:

                tag = soup.find(
                    "meta",
                    attrs={
                        "name":
                            meta_name
                    },
                )

            if tag:

                date_value = tag.get(
                    "content"
                )

                if date_value:
                    break

        # ----------------------------------------------------
        # ARTICLE BODY
        # ----------------------------------------------------

        paragraphs = []

        for paragraph in soup.find_all(
            "p"
        )[:40]:

            text = clean_text(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 30:

                paragraphs.append(
                    text
                )

        body_text = " ".join(
            paragraphs[:10]
        )

        return {

            "title": title,

            "summary": description,

            "image": image,

            "date": date_value,

            "text": body_text,
        }

    except Exception:

        return {

            "title": "",

            "summary": "",

            "image": "",

            "date": None,

            "text": "",
        }


# ============================================================
# COUNTY DETECTION
# ============================================================

def county_match_score(
    county,
    text,
):

    text = clean_text(
        text
    ).lower()

    score = 0

    aliases = COUNTY_ALIASES.get(
        county,
        [],
    )

    for alias in aliases:

        if alias.lower() in text:

            score += 1

    return score


def detect_county(
    title,
    summary="",
    source="",
):

    combined = " ".join(
        [
            title,
            summary,
            source,
        ]
    )

    scores = {}

    for county in COUNTIES:

        scores[county] = (
            county_match_score(
                county,
                combined,
            )
        )

    best_county = max(
        scores,
        key=scores.get,
    )

    if (
        scores[best_county]
        <= 0
    ):

        return ""

    return best_county


# ============================================================
# STORY CATEGORY
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

    categories = [

        (
            "Politics",
            [
                "president",
                " mp ",
                "governor",
                "senator",
                "politician",
                "politics",
                "government",
                "county assembly",
                "election",
                "party",
            ],
        ),

        (
            "Business",
            [
                "business",
                "company",
                "investment",
                "market",
                "trade",
                "economy",
                "economic",
                "jobs",
                "employment",
            ],
        ),

        (
            "Security",
            [
                "police",
                "arrest",
                "crime",
                "attack",
                "murder",
                "robbery",
                "security",
            ],
        ),

        (
            "Agriculture",
            [
                "farmer",
                "farming",
                "agriculture",
                "maize",
                "tea",
                "coffee",
                "livestock",
                "cattle",
            ],
        ),

        (
            "Health",
            [
                "hospital",
                "health",
                "disease",
                "doctor",
                "patients",
                "medical",
            ],
        ),

        (
            "Education",
            [
                "school",
                "education",
                "student",
                "teacher",
                "university",
                "college",
            ],
        ),

        (
            "Infrastructure",
            [
                "road",
                "bridge",
                "construction",
                "water",
                "electricity",
                "infrastructure",
            ],
        ),
    ]

    for category, keywords in categories:

        for keyword in keywords:

            if keyword in text:

                return category

    return "County News"


# ============================================================
# STORY HASH
# ============================================================

def story_hash(
    title,
    url,
):

    raw = (
        clean_text(title)
        + "|"
        + clean_text(url)
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:16]


# ============================================================
# VERIFY CANDIDATE
# ============================================================

def verify_candidate(
    candidate
):

    title = clean_text(
        candidate.get(
            "title",
            "",
        )
    )

    url = clean_text(
        candidate.get(
            "url",
            "",
        )
    )

    summary = clean_text(
        candidate.get(
            "summary",
            "",
        )
    )

    source_name = clean_text(
        candidate.get(
            "source_name",
            "",
        )
    )

    county = clean_text(
        candidate.get(
            "county",
            "",
        )
    )

    published = candidate.get(
        "published"
    )

    if not title:
        return None

    if not url:
        return None

    if not valid_http_url(
        url
    ):
        return None

    if not county:

        county = detect_county(
            title,
            summary,
            source_name,
        )

    if not county:
        return None

    # --------------------------------------------------------
    # RESOLVE GOOGLE NEWS URL
    # --------------------------------------------------------

    article_url = (
        unwrap_google_news_url(
            url
        )
    )

    if not valid_http_url(
        article_url
    ):

        article_url = url

    # --------------------------------------------------------
    # FETCH ARTICLE
    # --------------------------------------------------------

    article = fetch_article(
        article_url
    )

    article_title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    article_summary = clean_text(
        article.get(
            "summary",
            "",
        )
    )

    article_text = clean_text(
        article.get(
            "text",
            "",
        )
    )

    final_title = (
        article_title
        or title
    )

    final_summary = (
        article_summary
        or summary
        or truncate_text(
            article_text,
            350,
        )
        or final_title
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image = clean_text(
        candidate.get(
            "image",
            "",
        )
    )

    if not image:

        image = clean_text(
            article.get(
                "image",
                "",
            )
        )

    if not image:

        image = find_article_image(
            article_url,
            candidate.get(
                "rss_image",
                "",
            ),
        )

    if not image:

        image = bing_image_fallback(
            final_title,
            county,
        )

    if not image:
        return None

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if published:

        final_date = published

    else:

        final_date = article.get(
            "date"
        )

    # --------------------------------------------------------
    # COUNTY RECHECK
    # --------------------------------------------------------

    combined_text = " ".join(
        [
            final_title,
            final_summary,
            article_text,
        ]
    )

    detected = detect_county(
        final_title,
        final_summary,
        combined_text,
    )

    if detected:

        county = detected

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    category = story_category(
        final_title,
        final_summary,
    )

    # --------------------------------------------------------
    # VERIFIED STORY
    # --------------------------------------------------------

    result = {

        "id": story_hash(
            final_title,
            article_url,
        ),

        "title": final_title,

        "summary": truncate_text(
            final_summary,
            420,
        ),

        "county": county,

        "category": category,

        "source_name": (
            source_name
            or hostname(
                article_url
            )
        ),

        "source": article_url,

        "url": article_url,

        "resolved_url": article_url,

        "image": image,

        "image_url": image,

        "published": final_date,

        "verified": True,
    }

    return result


# ============================================================
# STORY SCORING
# ============================================================

def score_story(
    story
):

    score = 0

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

    published = story.get(
        "published"
    )

    text = (
        title
        + " "
        + summary
    ).lower()

    if title:
        score += 20

    if summary:
        score += 10

    if story.get(
        "image"
    ):
        score += 25

    if story.get(
        "verified"
    ):
        score += 20

    if story.get(
        "county"
    ):
        score += 10

    if story.get(
        "source_name"
    ):
        score += 5

    parsed = parse_date(
        published
    )

    if parsed:

        age_hours = (
            now_utc()
            - parsed
        ).total_seconds() / 3600

        if age_hours <= 12:

            score += 30

        elif age_hours <= 24:

            score += 25

        elif age_hours <= 48:

            score += 15

        elif age_hours <= 72:

            score += 8

    breaking_terms = [

        "breaking",

        "latest",

        "today",

        "dies",

        "killed",

        "arrested",

        "announces",

        "launches",

        "orders",

        "suspends",

        "elected",

        "resigns",
    ]

    for keyword in breaking_terms:

        if keyword in text:

            score += 3

    return score


# ============================================================
# CANDIDATE COLLECTION
# ============================================================

def collect_candidates():

    candidates = []

    queries = [

        "Bomet Kenya latest news",

        "Kericho Kenya latest news",

        "Nakuru Kenya latest news",

        "Nandi Kenya latest news",

        "Uasin Gishu Kenya latest news",

        "Elgeyo Marakwet Kenya latest news",

        "West Pokot Kenya latest news",

        "Narok Kenya latest news",
    ]

    for query in queries:

        county = detect_county(
            query,
            "",
            "",
        )

        feed_url = google_news_rss(
            query
        )

        entries = parse_feed(
            feed_url
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

            summary = clean_text(
                entry.get(
                    "summary",
                    "",
                )
            )

            published = (
                entry.get(
                    "published"
                )
                or entry.get(
                    "updated"
                )
                or ""
            )

            if not title:
                continue

            if not link:
                continue

            if not is_recent(
                published
            ):
                continue

            source_name = ""

            if " - " in title:

                parts = title.rsplit(
                    " - ",
                    1,
                )

                if len(parts) == 2:

                    possible_source = clean_text(
                        parts[1]
                    )

                    if possible_source:

                        source_name = (
                            possible_source
                        )

            rss_image = (
                get_rss_media_image(
                    entry
                )
            )

            candidate = {

                "title": title,

                "url": link,

                "summary": summary,

                "county": county,

                "source_name":
                    source_name,

                "published":
                    published,

                "rss_image":
                    rss_image,

                "image":
                    rss_image,
            }

            candidates.append(
                candidate
            )

        if RSS_DELAY > 0:

            time.sleep(
                RSS_DELAY
            )

    # --------------------------------------------------------
    # DEDUPE
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

    # --------------------------------------------------------
    # BING FALLBACK
    # --------------------------------------------------------

    if len(candidates) < 4:

        fallback_queries = [

            "Bomet Kenya latest news",

            "Kericho Kenya latest news",

            "Nakuru Kenya latest news",

            "Uasin Gishu Kenya latest news",
        ]

        for query in fallback_queries:

            results = bing_search(
                query
            )

            county = detect_county(
                query,
                "",
                "",
            )

            for item in results:

                candidate = {

                    "title": clean_text(
                        item.get(
                            "title",
                            "",
                        )
                    ),

                    "url": clean_text(
                        item.get(
                            "url",
                            "",
                        )
                    ),

                    "summary": clean_text(
                        item.get(
                            "summary",
                            "",
                        )
                    ),

                    "county": county,

                    "source_name":
                        hostname(
                            item.get(
                                "url",
                                "",
                            )
                        ),

                    "published": "",

                    "rss_image": "",

                    "image": "",
                }

                if (
                    candidate["title"]
                    and candidate["url"]
                ):

                    candidates.append(
                        candidate
                    )

    return candidates


# ============================================================
# SELECT STORY
# ============================================================

def select_story():

    print(
        "\n=============================="
    )

    print(
        "COLLECTING RIFT VALLEY NEWS"
    )

    print(
        "=============================="
    )

    candidates = collect_candidates()

    print(
        f"Candidates collected: "
        f"{len(candidates)}"
    )

    if not candidates:

        raise RuntimeError(
            "No recent Rift Valley "
            "candidates found."
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

    candidates = candidates[
        :MAX_CANDIDATES_TO_VERIFY
    ]

    verified = []

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        print(
            f"\nVerifying candidate "
            f"{index}/"
            f"{len(candidates)}:"
        )

        print(
            candidate.get(
                "title",
                "",
            )
        )

        try:

            story = verify_candidate(
                candidate
            )

            if story:

                story["score"] = (
                    score_story(
                        story
                    )
                )

                verified.append(
                    story
                )

                print(
                    "VERIFIED:",
                    story.get(
                        "county"
                    ),
                    "|",
                    story.get(
                        "source_name"
                    ),
                )

            else:

                print(
                    "Rejected: "
                    "verification failed."
                )

        except Exception as exc:

            print(
                "Verification error:",
                exc,
            )

    if not verified:

        raise RuntimeError(
            "No recent story passed "
            "verification after checking "
            "candidates."
        )

    verified.sort(

        key=lambda item:
            item.get(
                "score",
                0,
            ),

        reverse=True,
    )

    verified = verified[
        :MAX_VERIFIED_TO_COMPARE
    ]

    selected = verified[0]

    print(
        "\n=============================="
    )

    print(
        "SELECTED STORY"
    )

    print(
        "=============================="
    )

    print(
        "County:",
        selected.get(
            "county"
        ),
    )

    print(
        "Category:",
        selected.get(
            "category"
        ),
    )

    print(
        "Title:",
        selected.get(
            "title"
        ),
    )

    print(
        "Source:",
        selected.get(
            "source_name"
        ),
    )

    print(
        "Image:",
        selected.get(
            "image"
        ),
    )

    print(
        "Score:",
        selected.get(
            "score"
        ),
    )

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story
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

    if not summary:
        summary = title

    narration = (
        "Rift Valley Watch. "
        f"Here is the latest news "
        f"from {county}. "
        f"{title}. "
        f"{summary}. "
        f"This is a {category} "
        f"story reported by "
        f"{source}."
    )

    return clean_text(
        narration
    )


# ============================================================
# SCRIPT
# ============================================================

def build_script(
    story
):

    narration = build_narration(
        story
    )

    return {

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


# ============================================================
# JSON
# ============================================================

def write_json(
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

    except Exception:

        print(
            "\nCould not import "
            "rift_valley_video_generator."
        )

        traceback.print_exc()

        raise


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    ensure_directories()

    print(
        "\n======================================"
    )

    print(
        "RIFT VALLEY WATCH VIDEO PIPELINE"
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # 1. SELECT VERIFIED STORY
    # --------------------------------------------------------

    story = select_story()

    # --------------------------------------------------------
    # 2. BUILD SCRIPT
    # --------------------------------------------------------

    script = build_script(
        story
    )

    narration = clean_text(
        script.get(
            "narration",
            "",
        )
    )

    if not narration:

        raise RuntimeError(
            "Narration generation failed."
        )

    # --------------------------------------------------------
    # 3. NARRATION HANDOFF
    # --------------------------------------------------------

    story["narration"] = narration

    story["image"] = (
        story.get(
            "image",
            "",
        )
        or script.get(
            "image",
            "",
        )
    )

    story["image_url"] = (
        story.get(
            "image",
            "",
        )
    )

    story["source_name"] = (
        story.get(
            "source_name",
            "",
        )
        or script.get(
            "source_name",
            "",
        )
    )

    story["source"] = (
        story.get(
            "source",
            "",
        )
        or script.get(
            "source",
            "",
        )
    )

    story["url"] = (
        story.get(
            "url",
            "",
        )
        or script.get(
            "url",
            "",
        )
    )

    # --------------------------------------------------------
    # 4. SAVE STORY AND SCRIPT
    # --------------------------------------------------------

    write_json(
        STORY_FILE,
        story,
    )

    write_json(
        SCRIPT_FILE,
        script,
    )

    print(
        "\nStory saved:"
    )

    print(
        STORY_FILE
    )

    print(
        "\nScript saved:"
    )

    print(
        SCRIPT_FILE
    )

    print(
        "\nNarration prepared successfully."
    )

    # --------------------------------------------------------
    # 5. IMPORT VIDEO GENERATOR
    # --------------------------------------------------------

    generate_video = (
        import_video_generator()
    )

    # --------------------------------------------------------
    # 6. GENERATE VIDEO
    # --------------------------------------------------------

    print(
        "\n=============================="
    )

    print(
        "GENERATING VIDEO"
    )

    print(
        "=============================="
    )

    # IMPORTANT:
    # generate_video accepts ONE argument only.
    result = generate_video(
        story
    )

    # --------------------------------------------------------
    # 7. RESOLVE GENERATED FILE
    # --------------------------------------------------------

    if isinstance(
        result,
        str,
    ):

        generated_file = result

    elif isinstance(
        result,
        dict,
    ):

        generated_file = (
            result.get(
                "output"
            )
            or result.get(
                "output_file"
            )
            or result.get(
                "video"
            )
            or VIDEO_FILE
        )

    else:

        generated_file = VIDEO_FILE

    if not generated_file:

        generated_file = VIDEO_FILE

    if not os.path.isabs(
        generated_file
    ):

        generated_file = os.path.join(
            BASE_DIR,
            generated_file,
        )

    # --------------------------------------------------------
    # 8. ACTUAL GENERATOR OUTPUT FALLBACK
    # --------------------------------------------------------
    #
    # The generator has already reported:
    #
    # output/rift_valley_watch_reel.mp4
    #
    # Always recognize that file if it exists.
    # --------------------------------------------------------

    actual_reel_file = os.path.join(
        OUTPUT_DIR,
        "rift_valley_watch_reel.mp4",
    )

    if os.path.exists(
        actual_reel_file
    ):

        generated_file = (
            actual_reel_file
        )

    # --------------------------------------------------------
    # 9. FINAL FILE CHECK
    # --------------------------------------------------------

    if not os.path.exists(
        generated_file
    ):

        raise RuntimeError(
            "Video generator completed, "
            "but the MP4 file was not found: "
            + generated_file
        )

    file_size = os.path.getsize(
        generated_file
    )

    if file_size <= 0:

        raise RuntimeError(
            "Generated MP4 is empty."
        )

    # --------------------------------------------------------
    # 10. FINISHED
    # --------------------------------------------------------

    elapsed = (
        time.time()
        - start_time
    )

    print(
        "\n======================================"
    )

    print(
        "RIFT VALLEY WATCH VIDEO SUCCESSFUL"
    )

    print(
        "======================================"
    )

    print(
        "Created:",
        os.path.relpath(
            generated_file,
            BASE_DIR,
        ),
    )

    print(
        "File:",
        generated_file,
    )

    print(
        "Size:",
        f"{file_size / 1024 / 1024:.2f} MB",
    )

    print(
        "Pipeline time:",
        f"{elapsed:.1f} seconds",
    )

    print(
        "\nRIFT VALLEY WATCH FINISHED."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
