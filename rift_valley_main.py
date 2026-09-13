import os
import sys
import json
import re
import shutil
import random
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# AUTOMATIC MULTI-COUNTY NEWS ENGINE + VIDEO BUILDER
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"
AUDIO_DIR = ASSET_DIR / "audio"
OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
HISTORY_FILE = DATA_DIR / "story_history.json"

SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"

FINAL_OUTPUT = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# ============================================================
# COUNTY CONFIGURATION
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

# Search terms intentionally target actual county stories.
SEARCH_TERMS = [
    '"{county}" Kenya news',
    '"{county}" development Kenya',
    '"{county}" project Kenya',
    '"{county}" government Kenya',
    '"{county}" governor Kenya',
    '"{county}" roads Kenya',
    '"{county}" health Kenya',
    '"{county}" agriculture Kenya',
    '"{county}" education Kenya',
]

# Sources/domains that should never become the final publisher.
BLOCKED_DOMAINS = {
    "news.google.com",
    "google.com",
    "facebook.com",
    "m.facebook.com",
    "fb.watch",
    "youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "t.co",
}

# Search-result boilerplate that must not enter narration.
BLOCKED_TEXT = [
    "google news",
    "read more",
    "sign in",
    "facebook",
    "share this",
    "google play",
    "app store",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# HTTP
# ============================================================

def http_get(
    url,
    timeout=30,
    max_bytes=8_000_000,
):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        data = response.read(
            max_bytes + 1
        )

        if len(data) > max_bytes:
            raise RuntimeError(
                "Response exceeded maximum size."
            )

        return data


# ============================================================
# URL HELPERS
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url


def get_domain(url):

    try:
        parsed = urllib.parse.urlparse(
            url
        )

        domain = (
            parsed.netloc
            .lower()
            .split("@")[-1]
            .split(":")[0]
        )

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def is_blocked_domain(url):

    domain = get_domain(url)

    if not domain:
        return True

    for blocked in BLOCKED_DOMAINS:

        if (
            domain == blocked
            or domain.endswith("." + blocked)
        ):
            return True

    return False


def same_domain(url_a, url_b):

    a = get_domain(url_a)
    b = get_domain(url_b)

    return bool(a and b and a == b)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    text = str(text or "")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = text.replace(
        "\xa0",
        " ",
    )

    return text.strip()


def clean_title(title):

    title = clean_text(title)

    # Remove common publisher suffixes.
    title = re.sub(
        r"\s*[-|–—]\s*(Google News|Facebook).*$",
        "",
        title,
        flags=re.I,
    )

    return title.strip()


def contains_blocked_text(text):

    value = clean_text(
        text
    ).lower()

    return any(
        bad in value
        for bad in BLOCKED_TEXT
    )


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):

    if not value:
        return None

    value = clean_text(
        value
    )

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:

        try:

            result = datetime.strptime(
                value,
                fmt,
            )

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result

        except Exception:
            pass

    return None


def is_recent(date_value):

    parsed = parse_date(
        date_value
    )

    if not parsed:
        return False

    now = datetime.now(
        timezone.utc
    )

    age_days = (
        now - parsed.astimezone(
            timezone.utc
        )
    ).total_seconds() / 86400

    return age_days <= 14


# ============================================================
# RSS DISCOVERY
# ============================================================

def build_google_news_rss_url(
    query
):

    encoded = urllib.parse.quote(
        query
    )

    return (
        "https://news.google.com/rss/search?"
        f"q={encoded}&"
        "hl=en-KE&"
        "gl=KE&"
        "ceid=KE:en"
    )


def parse_rss_items(xml_data):

    items = []

    try:

        root = ET.fromstring(
            xml_data
        )

    except Exception as exc:

        log(
            f"RSS XML parsing failed: {exc}"
        )

        return items

    for item in root.findall(
        ".//item"
    ):

        title = clean_title(
            item.findtext(
                "title",
                "",
            )
        )

        link = clean_text(
            item.findtext(
                "link",
                "",
            )
        )

        description = clean_text(
            item.findtext(
                "description",
                "",
            )
        )

        pub_date = clean_text(
            item.findtext(
                "pubDate",
                "",
            )
        )

        source_node = item.find(
            "source"
        )

        source_name = ""

        if source_node is not None:
            source_name = clean_text(
                source_node.text
            )

        if not title or not link:
            continue

        items.append(
            {
                "title": title,
                "url": link,
                "description": description,
                "date": pub_date,
                "source_name": source_name,
            }
        )

    return items


def search_county_news(
    county
):

    candidates = []

    # Shuffle terms slightly so scheduled runs
    # do not always inspect the same search order.
    terms = SEARCH_TERMS.copy()
    random.shuffle(terms)

    for template in terms:

        query = template.format(
            county=county
        )

        rss_url = (
            build_google_news_rss_url(
                query
            )
        )

        log(
            f"Searching: {query}"
        )

        try:

            data = http_get(
                rss_url,
                timeout=25,
                max_bytes=3_000_000,
            )

            items = parse_rss_items(
                data
            )

            for item in items:

                item["county"] = county

                candidates.append(
                    item
                )

        except Exception as exc:

            log(
                f"Search failed: {exc}"
            )

    return candidates


# ============================================================
# CANDIDATE FILTERING
# ============================================================

def candidate_is_valid(
    candidate
):

    title = clean_text(
        candidate.get("title")
    )

    url = normalize_url(
        candidate.get("url")
    )

    county = clean_text(
        candidate.get("county")
    )

    if not title:
        return False

    if not url:
        return False

    if is_blocked_domain(url):
        return False

    if contains_blocked_text(
        title
    ):
        return False

    if not is_recent(
        candidate.get("date")
    ):
        return False

    # County must appear in the story title,
    # RSS description or URL when possible.
    combined = (
        title
        + " "
        + clean_text(
            candidate.get(
                "description"
            )
        )
        + " "
        + url
    ).lower()

    county_lower = county.lower()

    if county_lower not in combined:
        return False

    return True


def deduplicate_candidates(
    candidates
):

    seen = set()
    result = []

    for candidate in candidates:

        url = normalize_url(
            candidate.get("url")
        )

        title = clean_text(
            candidate.get("title")
        ).lower()

        key = (
            url
            or title
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(
            candidate
        )

    return result


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_meta(
    html,
    property_name=None,
    name=None,
):

    if property_name:

        pattern = (
            r'<meta[^>]+'
            r'(?:property|name)\s*=\s*["\']'
            + re.escape(property_name)
            + r'["\'][^>]+'
            r'content\s*=\s*["\']'
            r'([^"\']+)'
            r'["\']'
        )

    else:

        pattern = (
            r'<meta[^>]+'
            r'name\s*=\s*["\']'
            + re.escape(name)
            + r'["\'][^>]+'
            r'content\s*=\s*["\']'
            r'([^"\']+)'
            r'["\']'
        )

    match = re.search(
        pattern,
        html,
        flags=re.I,
    )

    if match:
        return clean_text(
            match.group(1)
        )

    # Reverse attribute order.
    if property_name:

        pattern = (
            r'<meta[^>]+'
            r'content\s*=\s*["\']'
            r'([^"\']+)'
            r'["\'][^>]+'
            r'(?:property|name)\s*=\s*["\']'
            + re.escape(property_name)
            + r'["\']'
        )

        match = re.search(
            pattern,
            html,
            flags=re.I,
        )

        if match:
            return clean_text(
                match.group(1)
            )

    return ""


def extract_title(
    html
):

    title = extract_meta(
        html,
        property_name="og:title",
    )

    if title:
        return clean_title(
            title
        )

    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        html,
        flags=re.I | re.S,
    )

    if match:

        return clean_title(
            re.sub(
                r"<[^>]+>",
                " ",
                match.group(1),
            )
        )

    return ""


def extract_description(
    html
):

    description = extract_meta(
        html,
        property_name="og:description",
    )

    if description:
        return description

    description = extract_meta(
        html,
        name="description",
    )

    return description


def extract_image_url(
    html,
    page_url,
):

    candidates = []

    for property_name in [
        "og:image",
        "og:image:url",
        "twitter:image",
        "twitter:image:src",
    ]:

        value = extract_meta(
            html,
            property_name=property_name,
        )

        if value:
            candidates.append(
                value
            )

    # JSON-LD image fallback.
    json_images = re.findall(
        r'"image"\s*:\s*"([^"]+)"',
        html,
        flags=re.I,
    )

    candidates.extend(
        json_images
    )

    # link rel=image_src fallback.
    matches = re.findall(
        r'<link[^>]+'
        r'rel=["\']image_src["\']'
        r'[^>]+href=["\']'
        r'([^"\']+)'
        r'["\']',
        html,
        flags=re.I,
    )

    candidates.extend(
        matches
    )

    for candidate in candidates:

        candidate = (
            candidate
            .replace(
                "&amp;",
                "&",
            )
            .strip()
        )

        if not candidate:
            continue

        absolute = urllib.parse.urljoin(
            page_url,
            candidate,
        )

        if absolute.startswith(
            "http://"
        ) or absolute.startswith(
            "https://"
        ):
            return absolute

    return ""


def extract_article_text(
    html
):

    # Remove scripts/styles.
    cleaned = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    cleaned = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        cleaned,
        flags=re.I | re.S,
    )

    cleaned = re.sub(
        r"<noscript\b[^>]*>.*?</noscript>",
        " ",
        cleaned,
        flags=re.I | re.S,
    )

    # Paragraphs first.
    paragraphs = re.findall(
        r"<p\b[^>]*>(.*?)</p>",
        cleaned,
        flags=re.I | re.S,
    )

    text_parts = []

    for paragraph in paragraphs:

        text = re.sub(
            r"<[^>]+>",
            " ",
            paragraph,
        )

        text = clean_text(
            text
        )

        if len(text) >= 40:
            text_parts.append(
                text
            )

    if text_parts:

        return " ".join(
            text_parts
        )

    # Generic fallback.
    text = re.sub(
        r"<[^>]+>",
        " ",
        cleaned,
    )

    return clean_text(
        text
    )


def recover_article(
    candidate
):

    url = normalize_url(
        candidate.get("url")
    )

    if not url:
        return None

    if is_blocked_domain(url):
        return None

    log("")
    log(
        f"Checking article: {url}"
    )

    try:

        data = http_get(
            url,
            timeout=30,
            max_bytes=8_000_000,
        )

        html = data.decode(
            "utf-8",
            errors="ignore",
        )

    except Exception as exc:

        log(
            f"Article download failed: {exc}"
        )

        return None

    title = extract_title(
        html
    )

    description = extract_description(
        html
    )

    image_url = extract_image_url(
        html,
        url,
    )

    article_text = extract_article_text(
        html
    )

    if not title:
        title = clean_title(
            candidate.get("title")
        )

    if not description:
        description = clean_text(
            candidate.get(
                "description"
            )
        )

    # The actual publisher URL must be different
    # from a blocked search/social service.
    if is_blocked_domain(url):
        return None

    # Need meaningful article content.
    if len(article_text) < 250:
        log(
            "Rejected: article content too short."
        )
        return None

    # Need a real image.
    if not image_url:
        log(
            "Rejected: no article image found."
        )
        return None

    # Reject obvious generic/search images.
    if contains_blocked_text(
        image_url
    ):
        log(
            "Rejected: suspicious image URL."
        )
        return None

    log(
        f"ARTICLE TITLE: {title}"
    )

    log(
        f"ARTICLE IMAGE: {image_url}"
    )

    return {
        "title": title,
        "url": url,
        "description": description,
        "image_url": image_url,
        "article_text": article_text,
        "source_name": (
            candidate.get(
                "source_name"
            )
            or get_domain(url)
        ),
        "date": candidate.get(
            "date"
        ),
        "county": candidate.get(
            "county"
        ),
    }


# ============================================================
# STORY HISTORY
# ============================================================

def load_history():

    if not HISTORY_FILE.exists():
        return []

    try:

        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(
                f
            )

        if isinstance(
            data,
            list,
        ):
            return data

    except Exception:
        pass

    return []


def save_history(
    history
):

    # Keep the history small.
    history = history[-100:]

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            history,
            f,
            indent=2,
            ensure_ascii=False,
        )


def story_already_used(
    article,
    history,
):

    url = normalize_url(
        article.get("url")
    )

    title = clean_text(
        article.get("title")
    ).lower()

    for old in history:

        old_url = normalize_url(
            old.get("url")
        )

        old_title = clean_text(
            old.get("title")
        ).lower()

        if url and url == old_url:
            return True

        if title and title == old_title:
            return True

    return False


# ============================================================
# STORY SCORING
# ============================================================

def score_article(
    article
):

    score = 0

    title = clean_text(
        article.get("title")
    ).lower()

    body = clean_text(
        article.get("article_text")
    ).lower()

    county = clean_text(
        article.get("county")
    ).lower()

    source = clean_text(
        article.get("source_name")
    ).lower()

    # Strong relevance.
    if county and county in title:
        score += 25

    if county and county in body:
        score += 15

    # Useful news categories.
    keywords = [
        "project",
        "development",
        "road",
        "hospital",
        "health",
        "school",
        "education",
        "agriculture",
        "farmers",
        "water",
        "business",
        "investment",
        "county government",
        "governor",
        "deputy president",
        "president",
        "minister",
        "government",
    ]

    for keyword in keywords:

        if keyword in title:
            score += 5

        elif keyword in body:
            score += 1

    # Prefer substantial articles.
    if len(body) > 1000:
        score += 10

    if len(body) > 2500:
        score += 5

    # Publisher/source signal.
    if (
        "government" in source
        or ".go.ke" in source
    ):
        score += 20

    # Avoid weak/generic headlines.
    weak_terms = [
        "live",
        "photos",
        "video",
        "watch",
        "click",
        "breaking",
    ]

    for term in weak_terms:

        if term in title:
            score -= 3

    return score


# ============================================================
# FACT EXTRACTION
# ============================================================

def extract_sentences(
    text
):

    text = clean_text(
        text
    )

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    result = []

    for sentence in sentences:

        sentence = clean_text(
            sentence
        )

        if len(sentence) >= 35:
            result.append(
                sentence
            )

    return result


def select_factual_sentences(
    article,
    max_sentences=5,
):

    sentences = extract_sentences(
        article.get(
            "article_text",
            "",
        )
    )

    county = clean_text(
        article.get(
            "county",
            "",
        )
    ).lower()

    useful = []

    keywords = [
        county,
        "project",
        "construction",
        "government",
        "county",
        "million",
        "billion",
        "kilometre",
        "kilometres",
        "hospital",
        "school",
        "road",
        "farmers",
        "agriculture",
        "water",
        "health",
        "education",
        "development",
    ]

    for sentence in sentences:

        lower = sentence.lower()

        if any(
            keyword
            and keyword in lower
            for keyword in keywords
        ):
            useful.append(
                sentence
            )

    if len(useful) < max_sentences:

        for sentence in sentences:

            if sentence not in useful:
                useful.append(
                    sentence
                )

            if len(useful) >= max_sentences:
                break

    return useful[:max_sentences]


# ============================================================
# REAL IMAGE DOWNLOAD
# ============================================================

def valid_image(
    path
):

    try:

        path = Path(
            path
        )

        if not path.exists():
            return False

        if path.stat().st_size < 5000:
            return False

        with Image.open(
            path
        ) as image:

            image.verify()

        return True

    except Exception:
        return False


def download_real_image(
    image_url
):

    if not image_url:
        raise RuntimeError(
            "No article image URL was provided."
        )

    temp = (
        SOURCE_DIR /
        "story_image.tmp"
    )

    if temp.exists():
        temp.unlink()

    log("")
    log(
        "============================================================"
    )
    log(
        "DOWNLOADING REAL ARTICLE IMAGE"
    )
    log(
        "============================================================"
    )

    log(
        f"IMAGE URL: {image_url}"
    )

    try:

        request = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": image_url,
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            data = response.read(
                12_000_000
            )

        with open(
            temp,
            "wb",
        ) as f:

            f.write(data)

        if not valid_image(
            temp
        ):
            raise RuntimeError(
                "Downloaded image is not valid."
            )

        image = Image.open(
            temp
        ).convert(
            "RGB"
        )

        image.save(
            SOURCE_IMAGE,
            "JPEG",
            quality=94,
            optimize=True,
        )

        temp.unlink(
            missing_ok=True
        )

        log(
            f"REAL IMAGE FOUND: {image_url}"
        )

        log(
            f"SAVED: {SOURCE_IMAGE}"
        )

        return SOURCE_IMAGE

    except Exception as exc:

        temp.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            "Real article image download failed: "
            + str(exc)
        )


# ============================================================
# AUTOMATIC STORY SELECTION
# ============================================================

def build_story_from_article(
    article
):

    title = clean_title(
        article.get("title")
    )

    county = clean_text(
        article.get("county")
    )

    source_url = normalize_url(
        article.get("url")
    )

    source_name = clean_text(
        article.get(
            "source_name"
        )
    )

    if not source_name:
        source_name = get_domain(
            source_url
        )

    factual_sentences = (
        select_factual_sentences(
            article,
            5,
        )
    )

    summary = clean_text(
        article.get(
            "description"
        )
    )

    if len(summary) < 80:

        summary = " ".join(
            factual_sentences[:3]
        )

    if not summary:

        summary = (
            "A verified current news "
            f"report from {county}."
        )

    # Keep summary manageable.
    if len(summary) > 650:
        summary = (
            summary[:647].rsplit(
                " ",
                1,
            )[0]
            + "..."
        )

    facts = []

    for sentence in factual_sentences:

        facts.append(
            {
                "label": "CONFIRMED",
                "value": sentence,
            }
        )

    return {
        "title": title,
        "county": (
            county
            if county.lower().endswith(
                "county"
            )
            else county + " County"
        ),
        "category": "COUNTY NEWS",
        "date": (
            parse_date(
                article.get("date")
            ).date().isoformat()
            if parse_date(
                article.get("date")
            )
            else datetime.now(
                timezone.utc
            ).date().isoformat()
        ),
        "source": {
            "name": source_name,
            "url": source_url,
            "type": (
                "OFFICIAL_SOURCE"
                if (
                    "government"
                    in source_name.lower()
                    or ".go.ke"
                    in source_url.lower()
                )
                else "NEWS_SOURCE"
            ),
        },
        "verified_facts": facts,
        "official_statement": {
            "available": False,
            "speaker": "",
            "quote": "",
        },
        "summary": summary,
        "visuals": [
            {
                "type": "ARTICLE_IMAGE",
                "description": (
                    "Real image published with "
                    "the selected article."
                ),
            },
            {
                "type": "LOCATION",
                "description": county,
            },
            {
                "type": "KEY_FACTS",
                "description": (
                    "Confirmed facts from "
                    "the selected article."
                ),
            },
            {
                "type": "IMPACT",
                "description": (
                    "Why the story matters "
                    "to the county."
                ),
            },
            {
                "type": "SOURCE",
                "description": source_name,
            },
        ],
        "editorial": {
            "confirmed": factual_sentences,
            "unconfirmed": [],
        },
        "image_url": article.get(
            "image_url"
        ),
        "article_url": source_url,
    }


def select_story():

    log("")
    log(
        "============================================================"
    )
    log(
        "RIFT VALLEY WATCH NEWS ENGINE"
    )
    log(
        "============================================================"
    )

    history = load_history()

    all_candidates = []

    # Shuffle county order so consecutive runs
    # do not always start with Bomet.
    counties = COUNTIES.copy()
    random.shuffle(
        counties
    )

    for county in counties:

        log("")
        log(
            f"SEARCHING COUNTY: {county}"
        )

        candidates = search_county_news(
            county
        )

        log(
            f"Candidates found: "
            f"{len(candidates)}"
        )

        all_candidates.extend(
            candidates
        )

    all_candidates = (
        deduplicate_candidates(
            all_candidates
        )
    )

    log("")
    log(
        f"TOTAL UNIQUE CANDIDATES: "
        f"{len(all_candidates)}"
    )

    valid_candidates = [
        candidate
        for candidate in all_candidates
        if candidate_is_valid(
            candidate
        )
    ]

    log(
        f"VALID RECENT CANDIDATES: "
        f"{len(valid_candidates)}"
    )

    if not valid_candidates:

        raise RuntimeError(
            "No valid recent county stories "
            "were found."
        )

    # Score candidates first.
    scored = []

    for candidate in valid_candidates:

        score = (
            score_article(
                candidate
            )
        )

        candidate["score"] = score

        scored.append(
            candidate
        )

    scored.sort(
        key=lambda item: item.get(
            "score",
            0,
        ),
        reverse=True,
    )

    log("")
    log(
        "TOP CANDIDATES:"
    )

    for candidate in scored[:10]:

        log(
            f"{candidate['score']:>3} | "
            f"{candidate['county']} | "
            f"{candidate['title']}"
        )

    # Try the best candidates until one has:
    # - real publisher article
    # - meaningful content
    # - real image
    # - not previously used.
    for candidate in scored:

        if story_already_used(
            candidate,
            history,
        ):

            log(
                "Skipping previously used story: "
                + candidate["title"]
            )

            continue

        article = recover_article(
            candidate
        )

        if not article:
            continue

        article["score"] = candidate.get(
            "score",
            0,
        )

        try:

            story = build_story_from_article(
                article
            )

            # Verify final story again.
            if not story.get(
                "title"
            ):
                continue

            if not story.get(
                "summary"
            ):
                continue

            if not story.get(
                "image_url"
            ):
                continue

            image_path = download_real_image(
                story["image_url"]
            )

            if not valid_image(
                image_path
            ):
                continue

            log("")
            log(
                "============================================================"
            )
            log(
                "STORY SELECTED"
            )
            log(
                "============================================================"
            )

            log(
                f"TITLE : {story['title']}"
            )

            log(
                f"COUNTY: {story['county']}"
            )

            log(
                f"SOURCE: {story['source']['name']}"
            )

            log(
                f"IMAGE : {story['image_url']}"
            )

            # Save history immediately after successful
            # story + image verification.
            history.append(
                {
                    "title": story[
                        "title"
                    ],
                    "url": story[
                        "source"
                    ]["url"],
                    "county": story[
                        "county"
                    ],
                    "date": story[
                        "date"
                    ],
                }
            )

            save_history(
                history
            )

            return story

        except Exception as exc:

            log(
                "Candidate rejected during "
                f"verification: {exc}"
            )

    raise RuntimeError(
        "No candidate passed article, "
        "content and real-image verification."
    )


def write_story(
    story
):

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            story,
            f,
            indent=2,
            ensure_ascii=False,
        )

    log(
        f"Story written: {STORY_FILE}"
    )


# ============================================================
# NARRATION
# ============================================================

def shorten_for_narration(
    text,
    max_chars=360,
):

    text = clean_text(
        text
    )

    if len(text) <= max_chars:
        return text

    return (
        text[:max_chars - 3]
        .rsplit(
            " ",
            1,
        )[0]
        + "..."
    )


def build_narration(
    story
):

    title = clean_text(
        story["title"]
    )

    county = clean_text(
        story["county"]
    )

    source_name = clean_text(
        story["source"]["name"]
    )

    summary = clean_text(
        story["summary"]
    )

    facts = story.get(
        "verified_facts",
        [],
    )

    fact_values = []

    for fact in facts:

        value = clean_text(
            fact.get(
                "value"
            )
        )

        if value:
            fact_values.append(
                value
            )

    narration = []

    narration.append(
        (
            f"Here is the latest verified "
            f"county story from {county}. "
            f"{shorten_for_narration(title, 220)}."
        )
    )

    narration.append(
        shorten_for_narration(
            summary,
            390,
        )
    )

    if fact_values:

        narration.append(
            (
                "According to the published report, "
                + shorten_for_narration(
                    fact_values[0],
                    390,
                )
            )
        )

    if len(fact_values) > 1:

        narration.append(
            shorten_for_narration(
                fact_values[1],
                390,
            )
        )

    if len(fact_values) > 2:

        narration.append(
            (
                "The report also states that "
                + shorten_for_narration(
                    fact_values[2],
                    360,
                )
            )
        )

    narration.append(
        (
            f"The story comes from "
            f"{source_name}, based on the "
            "published article reviewed for "
            "this report."
        )
    )

    narration.append(
        (
            "Rift Valley Watch tracks verified "
            "news and developments across the "
            "Rift Valley."
        )
    )

    # Exactly eight scenes.
    while len(narration) < 8:

        narration.insert(
            -1,
            (
                f"More details are contained "
                f"in the published {county} report."
            ),
        )

    return narration[:8]


def write_script(
    narration
):

    script = {
        "segments": [
            {
                "scene": index + 1,
                "text": text,
            }
            for index, text in enumerate(
                narration
            )
        ]
    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            script,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# FONTS
# ============================================================

def get_font(
    size,
    bold=True,
):

    candidates = []

    if bold:

        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Bold.ttf",
            ]
        )

    else:

        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Regular.ttf",
            ]
        )

    for path in candidates:

        if Path(path).exists():

            return ImageFont.truetype(
                path,
                size,
            )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = str(
        text
    ).split()

    lines = []
    current = ""

    for word in words:

        test = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = (
            bbox[2] - bbox[0]
        )

        if width <= max_width:

            current = test

        else:

            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    return lines


# ============================================================
# IMAGE PREPARATION
# ============================================================

def crop_cover(
    image
):

    image = image.convert(
        "RGB"
    )

    ratio = max(
        WIDTH / image.width,
        HEIGHT / image.height,
    )

    new_width = int(
        image.width * ratio
    )

    new_height = int(
        image.height * ratio
    )

    image = image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - WIDTH
    ) // 2

    top = (
        new_height - HEIGHT
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )


def load_background(
    image_path
):

    image = Image.open(
        image_path
    )

    return crop_cover(
        image
    )


# ============================================================
# BASE SCENE
# ============================================================

def create_base_scene(
    image_path,
    scene_number,
    section,
    story,
):

    image = load_background(
        image_path
    )

    draw = ImageDraw.Draw(
        image,
        "RGBA",
    )

    # Top dark strip.
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            170,
        ),
        fill=(0, 0, 0, 190),
    )

    # Bottom dark area.
    draw.rectangle(
        (
            0,
            1450,
            WIDTH,
            HEIGHT,
        ),
        fill=(0, 0, 0, 215),
    )

    small_font = get_font(
        34,
        True,
    )

    draw.text(
        (48, 42),
        "RIFT VALLEY WATCH",
        font=small_font,
        fill=(255, 255, 255, 255),
    )

    scene_font = get_font(
        30,
        True,
    )

    scene_label = (
        f"{scene_number:02d}  |  "
        f"{section.upper()}"
    )

    bbox = draw.textbbox(
        (0, 0),
        scene_label,
        font=scene_font,
    )

    draw.text(
        (
            WIDTH
            - 48
            - (
                bbox[2]
                - bbox[0]
            ),
            45,
        ),
        scene_label,
        font=scene_font,
        fill=(255, 255, 255, 220),
    )

    # County lower-left.
    county_font = get_font(
        30,
        True,
    )

    draw.text(
        (
            48,
            1810,
        ),
        story["county"].upper(),
        font=county_font,
        fill=(255, 255, 255, 230),
    )

    return image, draw


# ============================================================
# SAVE SCENE
# ============================================================

def save_scene_image(
    image,
    index,
):

    path = (
        SCENE_DIR
        / f"scene_{index:02d}.jpg"
    )

    image.save(
        path,
        "JPEG",
        quality=94,
        optimize=True,
    )

    if not valid_image(
        path
    ):

        raise RuntimeError(
            f"Scene image invalid: {path}"
        )

    return path


# ============================================================
# SCENE 1
# ============================================================

def scene_1(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        1,
        "Breaking County News",
        story,
    )

    title_font = get_font(
        66,
        True,
    )

    lines = wrap_text(
        draw,
        story["title"],
        title_font,
        930,
    )

    y = 570

    for line in lines:

        draw.text(
            (
                60,
                y,
            ),
            line,
            font=title_font,
            fill="white",
            stroke_width=3,
            stroke_fill="black",
        )

        y += 82

    return save_scene_image(
        image,
        1,
    )


# ============================================================
# SCENE 2
# ============================================================

def scene_2(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        2,
        "Where It Is",
        story,
    )

    label_font = get_font(
        42,
        True,
    )

    title_font = get_font(
        74,
        True,
    )

    body_font = get_font(
        46,
        True,
    )

    draw.text(
        (
            60,
            520,
        ),
        "LOCATION",
        font=label_font,
        fill="white",
    )

    draw.text(
        (
            60,
            610,
        ),
        story["county"].upper(),
        font=title_font,
        fill="white",
    )

    lines = wrap_text(
        draw,
        story["summary"],
        body_font,
        900,
    )

    y = 780

    for line in lines[:6]:

        draw.text(
            (
                60,
                y,
            ),
            line,
            font=body_font,
            fill="white",
        )

        y += 65

    return save_scene_image(
        image,
        2,
    )


# ============================================================
# SCENE 3
# ============================================================

def scene_3(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        3,
        "Key Facts",
        story,
    )

    title_font = get_font(
        50,
        True,
    )

    body_font = get_font(
        39,
        True,
    )

    draw.text(
        (
            60,
            470,
        ),
        "CONFIRMED FACTS",
        font=title_font,
        fill="white",
    )

    facts = story.get(
        "verified_facts",
        [],
    )

    y = 620

    for fact in facts[:4]:

        value = clean_text(
            fact.get(
                "value"
            )
        )

        lines = wrap_text(
            draw,
            "• " + value,
            body_font,
            900,
        )

        for line in lines[:3]:

            draw.text(
                (
                    60,
                    y,
                ),
                line,
                font=body_font,
                fill="white",
            )

            y += 55

        y += 25

    return save_scene_image(
        image,
        3,
    )


# ============================================================
# SCENE 4
# ============================================================

def scene_4(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        4,
        "The Details",
        story,
    )

    title_font = get_font(
        56,
        True,
    )

    body_font = get_font(
        43,
        True,
    )

    draw.text(
        (
            60,
            470,
        ),
        "WHAT THE REPORT SAYS",
        font=title_font,
        fill="white",
    )

    facts = story.get(
        "verified_facts",
        [],
    )

    y = 620

    for fact in facts[4:8]:

        value = clean_text(
            fact.get(
                "value"
            )
        )

        if not value:
            continue

        lines = wrap_text(
            draw,
            value,
            body_font,
            900,
        )

        for line in lines[:4]:

            draw.text(
                (
                    60,
                    y,
                ),
                line,
                font=body_font,
                fill="white",
            )

            y += 58

        y += 30

    if y < 850:

        lines = wrap_text(
            draw,
            story["summary"],
            body_font,
            900,
        )

        for line in lines[:5]:

            draw.text(
                (
                    60,
                    y,
                ),
                line,
                font=body_font,
                fill="white",
            )

            y += 58

    return save_scene_image(
        image,
        4,
    )


# ============================================================
# SCENE 5
# ============================================================

def scene_5(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        5,
        "Why It Matters",
        story,
    )

    title_font = get_font(
        65,
        True,
    )

    body_font = get_font(
        47,
        True,
    )

    draw.text(
        (
            60,
            480,
        ),
        "WHY IT MATTERS",
        font=title_font,
        fill="white",
    )

    text = story["summary"]

    lines = wrap_text(
        draw,
        text,
        body_font,
        900,
    )

    y = 700

    for line in lines[:8]:

        draw.text(
            (
                60,
                y,
            ),
            line,
            font=body_font,
            fill="white",
        )

        y += 67

    return save_scene_image(
        image,
        5,
    )


# ============================================================
# SCENE 6
# ============================================================

def scene_6(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        6,
        "Verification",
        story,
    )

    title_font = get_font(
        60,
        True,
    )

    body_font = get_font(
        43,
        True,
    )

    draw.text(
        (
            60,
            470,
        ),
        "VERIFIED REPORT",
        font=title_font,
        fill="white",
    )

    text = (
        "This reel is based on a published "
        "article from the source shown in "
        "the final scene."
    )

    lines = wrap_text(
        draw,
        text,
        body_font,
        900,
    )

    y = 650

    for line in lines:

        draw.text(
            (
                60,
                y,
            ),
            line,
            font=body_font,
            fill="white",
        )

        y += 65

    draw.text(
        (
            60,
            y + 60,
        ),
        story["source"]["name"],
        font=title_font,
        fill="white",
    )

    return save_scene_image(
        image,
        6,
    )


# ============================================================
# SCENE 7
# ============================================================

def scene_7(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        7,
        "Published Source",
        story,
    )

    title_font = get_font(
        62,
        True,
    )

    body_font = get_font(
        43,
        True,
    )

    draw.text(
        (
            60,
            500,
        ),
        "SOURCE",
        font=title_font,
        fill="white",
    )

    source_name = story[
        "source"
    ]["name"]

    lines = wrap_text(
        draw,
        source_name,
        title_font,
        900,
    )

    y = 680

    for line in lines:

        draw.text(
            (
                60,
                y,
            ),
            line,
            font=title_font,
            fill="white",
        )

        y += 75

    domain = get_domain(
        story[
            "source"
        ]["url"]
    )

    draw.text(
        (
            60,
            y + 50,
        ),
        domain,
        font=body_font,
        fill="white",
    )

    return save_scene_image(
        image,
        7,
    )


# ============================================================
# SCENE 8
# ============================================================

def scene_8(
    image_path,
    story,
):

    image, draw = create_base_scene(
        image_path,
        8,
        "Rift Valley Watch",
        story,
    )

    title_font = get_font(
        76,
        True,
    )

    body_font = get_font(
        45,
        True,
    )

    draw.text(
        (
            60,
            610,
        ),
        "RIFT VALLEY",
        font=title_font,
        fill="white",
    )

    draw.text(
        (
            60,
            710,
        ),
        "WATCH",
        font=title_font,
        fill="white",
    )

    draw.text(
        (
            60,
            900,
        ),
        "Verified county news.",
        font=body_font,
        fill="white",
    )

    return save_scene_image(
        image,
        8,
    )


# ============================================================
# AUDIO
# ============================================================

def create_audio(
    text,
    index,
):

    output = (
        AUDIO_DIR
        / f"scene_{index:02d}.mp3"
    )

    if output.exists():
        output.unlink()

    log(
        f"Creating narration: "
        f"{output.name}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(
        str(output)
    )

    if not output.exists():

        raise RuntimeError(
            f"Narration was not created: "
            f"{output}"
        )

    if output.stat().st_size < 1000:

        raise RuntimeError(
            f"Narration file is too small: "
            f"{output}"
        )

    return output


# ============================================================
# SCENE VIDEO
# ============================================================

def render_scene(
    image_path,
    audio_path,
    output_path,
):

    font = (
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf"
    )

    if not Path(
        font
    ).exists():

        font = (
            "/usr/share/fonts/truetype/"
            "liberation2/"
            "LiberationSans-Bold.ttf"
        )

    if output_path.exists():
        output_path.unlink()

    cmd = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1"
        ),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-shortest",

        "-r",
        str(FPS),

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        log("")
        log(
            "FFMPEG SCENE ERROR"
        )

        log(
            result.stderr[-10000:]
        )

        raise RuntimeError(
            f"Scene render failed: "
            f"{output_path.name}"
        )

    if not output_path.exists():

        raise RuntimeError(
            f"Scene MP4 missing: "
            f"{output_path}"
        )

    if output_path.stat().st_size < 10000:

        raise RuntimeError(
            f"Scene MP4 is too small: "
            f"{output_path}"
        )

    log(
        f"Scene MP4 created: "
        f"{output_path.name}"
    )


# ============================================================
# CONCATENATE
# ============================================================

def concatenate_scenes(
    scene_files,
):

    if not scene_files:

        raise RuntimeError(
            "No scene MP4 files were created."
        )

    concat_file = (
        OUTPUT_DIR
        / "concat_list.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_files:

            absolute = Path(
                scene
            ).resolve()

            escaped = str(
                absolute
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{escaped}'\n"
            )

    temp_output = (
        OUTPUT_DIR
        / "rift_valley_watch_reel_temp.mp4"
    )

    if temp_output.exists():
        temp_output.unlink()

    log("")
    log(
        "============================================================"
    )
    log(
        "CONCATENATING SCENES"
    )
    log(
        "============================================================"
    )

    cmd_copy = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]

    result = subprocess.run(
        cmd_copy,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if (
        result.returncode != 0
        or not temp_output.exists()
        or temp_output.stat().st_size < 10000
    ):

        if temp_output.exists():
            temp_output.unlink()

        log(
            "Stream-copy concat failed. "
            "Using safe re-encode."
        )

        cmd_reencode = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]

        result = subprocess.run(
            cmd_reencode,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:

            log("")
            log(
                "FINAL CONCAT FFMPEG ERROR"
            )

            log(
                result.stderr[-15000:]
            )

            raise RuntimeError(
                "Could not concatenate "
                "scene MP4 files."
            )

    if not temp_output.exists():

        raise RuntimeError(
            "Temporary final MP4 was not created."
        )

    if temp_output.stat().st_size < 10000:

        raise RuntimeError(
            "Temporary final MP4 is too small."
        )

    shutil.move(
        str(temp_output),
        str(FINAL_OUTPUT),
    )

    log(
        f"FINAL MP4 CREATED: "
        f"{FINAL_OUTPUT}"
    )


# ============================================================
# MP4 VERIFICATION
# ============================================================

def verify_mp4():

    log("")
    log(
        "============================================================"
    )
    log(
        "VERIFYING FINAL MP4"
    )
    log(
        "============================================================"
    )

    if not FINAL_OUTPUT.exists():

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    if FINAL_OUTPUT.stat().st_size < 50000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_OUTPUT),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        log(
            result.stderr
        )

        raise RuntimeError(
            "Final MP4 failed "
            "ffprobe verification."
        )

    log(
        "FINAL MP4 VERIFIED"
    )

    log(
        result.stdout.strip()
    )

    log(
        f"FILE: {FINAL_OUTPUT}"
    )

    log(
        f"SIZE: "
        f"{FINAL_OUTPUT.stat().st_size:,} bytes"
    )


# ============================================================
# CLEAN OUTPUT
# ============================================================

def clean_output():

    if SCENE_DIR.exists():

        for file in SCENE_DIR.iterdir():

            if file.is_file():
                file.unlink()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_OUTPUT.exists():
        FINAL_OUTPUT.unlink()

    temp = (
        OUTPUT_DIR
        / "rift_valley_watch_reel_temp.mp4"
    )

    if temp.exists():
        temp.unlink()

    concat = (
        OUTPUT_DIR
        / "concat_list.txt"
    )

    if concat.exists():
        concat.unlink()

    # Audio is regenerated every run.
    if AUDIO_DIR.exists():

        for file in AUDIO_DIR.iterdir():

            if file.is_file():
                file.unlink()


# ============================================================
# MAIN BUILD
# ============================================================

def build_video(
    story
):

    prepare_directories()

    clean_output()

    # The news engine has already downloaded and
    # verified the real article image.
    if not valid_image(
        SOURCE_IMAGE
    ):

        image_path = download_real_image(
            story.get(
                "image_url"
            )
        )

    else:

        image_path = SOURCE_IMAGE

        log(
            f"Using verified article image: "
            f"{image_path}"
        )

    narration = build_narration(
        story
    )

    write_script(
        narration
    )

    scene_images = [
        scene_1(
            image_path,
            story,
        ),
        scene_2(
            image_path,
            story,
        ),
        scene_3(
            image_path,
            story,
        ),
        scene_4(
            image_path,
            story,
        ),
        scene_5(
            image_path,
            story,
        ),
        scene_6(
            image_path,
            story,
        ),
        scene_7(
            image_path,
            story,
        ),
        scene_8(
            image_path,
            story,
        ),
    ]

    if len(scene_images) != 8:

        raise RuntimeError(
            "Expected 8 scene images."
        )

    scene_files = []

    for index, (
        scene_image,
        narration_text,
    ) in enumerate(
        zip(
            scene_images,
            narration,
        ),
        1,
    ):

        audio_path = create_audio(
            narration_text,
            index,
        )

        scene_output = (
            SCENE_DIR
            / f"scene_{index:02d}.mp4"
        )

        render_scene(
            scene_image,
            audio_path,
            scene_output,
        )

        scene_files.append(
            scene_output
        )

    log("")
    log(
        f"TOTAL SCENE MP4 FILES: "
        f"{len(scene_files)}"
    )

    for scene in scene_files:

        log(
            f"  {scene.name}: "
            f"{scene.stat().st_size:,} bytes"
        )

    concatenate_scenes(
        scene_files
    )

    verify_mp4()


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log(
        "============================================================"
    )
    log(
        "RIFT VALLEY WATCH"
    )
    log(
        "AUTOMATIC MULTI-COUNTY NEWS BUILD"
    )
    log(
        "============================================================"
    )

    log(
        f"ROOT: {ROOT}"
    )

    log(
        f"OUTPUT: {FINAL_OUTPUT}"
    )

    try:

        prepare_directories()

        # ----------------------------------------------------
        # STEP 1: AUTOMATIC NEWS DISCOVERY
        # ----------------------------------------------------

        story = select_story()

        # ----------------------------------------------------
        # STEP 2: WRITE VERIFIED STORY
        # ----------------------------------------------------

        write_story(
            story
        )

        # ----------------------------------------------------
        # STEP 3: BUILD VIDEO
        # ----------------------------------------------------

        build_video(
            story
        )

        log("")
        log(
            "============================================================"
        )
        log(
            "BUILD SUCCESSFUL"
        )
        log(
            "============================================================"
        )

        log(
            f"STORY : {story['title']}"
        )

        log(
            f"COUNTY: {story['county']}"
        )

        log(
            f"SOURCE: {story['source']['name']}"
        )

        log(
            f"FINAL FILE: {FINAL_OUTPUT}"
        )

    except Exception as exc:

        log("")
        log(
            "============================================================"
        )
        log(
            "RIFT VALLEY WATCH FAILED"
        )
        log(
            "============================================================"
        )

        log(
            f"{type(exc).__name__}: {exc}"
        )

        log("")
        log(
            "Output directory:"
        )

        if OUTPUT_DIR.exists():

            for item in OUTPUT_DIR.iterdir():

                try:
                    size = item.stat().st_size
                except Exception:
                    size = 0

                log(
                    f"  {item.name} "
                    f"{size:,} bytes"
                )

        log("")
        log(
            "Scene directory:"
        )

        if SCENE_DIR.exists():

            for item in SCENE_DIR.iterdir():

                try:
                    size = item.stat().st_size
                except Exception:
                    size = 0

                log(
                    f"  {item.name} "
                    f"{size:,} bytes"
                )

        sys.exit(1)


if __name__ == "__main__":
    main()
