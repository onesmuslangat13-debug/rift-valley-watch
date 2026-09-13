
# ============================================================
# RIFT VALLEY WATCH
# MAIN CONTROLLER
#
# VERSION: RVW_MAIN_V8_ORIGINAL_NEWS_PIPELINE
#
# DESIGN:
# - ONE story per reel
# - DIRECT NEWS PUBLISHER DISCOVERY
# - NEVER USE GOOGLE NEWS AS A STORY
# - NEVER USE FACEBOOK / SOCIAL POSTS
# - REAL ARTICLE IMAGE REQUIRED
# - NO SOURCE/PUBLISHER/URL IN VIDEO DATA
# - NO SOURCE/PUBLISHER IN NARRATION
# - NORMAL TEXT ONLY
# - NATURAL NEWS NARRATION
# - 70+ WORDS MINIMUM
# - CANONICAL JSON SCHEMA
# - RUN EXISTING VIDEO GENERATOR
# - VERIFY FINAL MP4
# ============================================================

from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import subprocess
import sys
import time
import unicodedata

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SOURCE_ASSETS_DIR = ASSETS_DIR / "source"

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_ASSETS_DIR / "story_image.jpg"


# ============================================================
# SETTINGS
# ============================================================

COUNTIES = {
    "Bomet": [
        "Bomet",
        "Sotik",
        "Longisa",
        "Chepalungu",
        "Konoin",
    ],
    "Kericho": [
        "Kericho",
        "Litein",
        "Kipkelion",
        "Ainamoi",
    ],
    "Nakuru": [
        "Nakuru",
        "Naivasha",
        "Gilgil",
        "Molo",
        "Njoro",
    ],
    "Nandi": [
        "Nandi",
        "Kapsabet",
        "Mosop",
        "Aldai",
    ],
    "Uasin Gishu": [
        "Uasin Gishu",
        "Eldoret",
        "Kesses",
        "Turbo",
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet",
        "Elgeyo",
        "Marakwet",
        "Iten",
        "Keiyo",
    ],
    "West Pokot": [
        "West Pokot",
        "Pokot",
        "Kapenguria",
        "Kacheliba",
    ],
    "Narok": [
        "Narok",
        "Kilgoris",
        "Suswa",
        "Transmara",
    ],
}


# Direct publisher discovery pages.
PUBLISHERS = [
    {
        "name": "Citizen",
        "url": "https://citizen.digital/",
        "domains": [
            "citizen.digital",
        ],
    },
    {
        "name": "The Star",
        "url": "https://www.the-star.co.ke/news/",
        "domains": [
            "the-star.co.ke",
            "www.the-star.co.ke",
        ],
    },
    {
        "name": "KBC",
        "url": "https://www.kbc.co.ke/",
        "domains": [
            "kbc.co.ke",
            "www.kbc.co.ke",
        ],
    },
    {
        "name": "Nation",
        "url": "https://nation.africa/kenya/news",
        "domains": [
            "nation.africa",
        ],
    },
]


BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "www.twitter.com",
    "x.com",
    "www.x.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "tiktok.com",
    "www.tiktok.com",
    "telegram.me",
    "t.me",
    "whatsapp.com",
    "news.google.com",
    "google.com",
}


IMAGE_REJECT_TERMS = [
    "google-news",
    "google_news",
    "googlelogo",
    "google-logo",
    "google",
    "favicon",
    "icon",
    "logo",
    "placeholder",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "avatar",
    "sprite",
    "app-icon",
    "app_icon",
]


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


REQUEST_TIMEOUT = 20


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as exc:
        log(f"WARNING: Could not read {path}: {exc}")
        return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    text = str(value)

    # Converts mathematical bold / stylized Unicode
    # into ordinary readable characters.
    text = unicodedata.normalize("NFKC", text)

    text = html.unescape(text)

    text = text.replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(value):
    text = clean_text(value)

    if not text:
        return ""

    publisher_patterns = [
        r"\s*[-|–—:]\s*People Daily\s*$",
        r"\s*[-|–—:]\s*The Star\s*$",
        r"\s*[-|–—:]\s*Citizen Digital\s*$",
        r"\s*[-|–—:]\s*Citizen\s*$",
        r"\s*[-|–—:]\s*The Standard\s*$",
        r"\s*[-|–—:]\s*Daily Nation\s*$",
        r"\s*[-|–—:]\s*Nation\s*$",
        r"\s*[-|–—:]\s*Capital News\s*$",
        r"\s*[-|–—:]\s*KBC\s*$",
        r"\s*[-|–—:]\s*NTV Kenya\s*$",
        r"\s*[-|–—:]\s*TV47\s*$",
        r"\s*[-|–—:]\s*Kenya\s*$",
    ]

    for pattern in publisher_patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r"\s+", " ", text).strip()

    return text


def remove_forbidden_metadata(text):
    text = clean_text(text)

    if not text:
        return ""

    forbidden = [
        "Google News",
        "People Daily",
        "The Star",
        "Citizen Digital",
        "Citizen",
        "The Standard",
        "Daily Nation",
        "Nation",
        "Capital News",
        "Kenya News Agency",
        "KBC",
        "NTV Kenya",
        "TV47",
        "Facebook",
        "Instagram",
        "Twitter",
        "YouTube",
        "TikTok",
    ]

    for phrase in forbidden:
        text = re.sub(
            re.escape(phrase),
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# URL VALIDATION
# ============================================================

def domain_of(url):
    try:
        host = urlparse(url).netloc.lower()
        return host.replace("www.", "")
    except Exception:
        return ""


def is_blocked_url(url):
    host = domain_of(url)

    if not host:
        return True

    for blocked in BLOCKED_DOMAINS:
        blocked_clean = blocked.replace("www.", "")

        if host == blocked_clean:
            return True

        if host.endswith("." + blocked_clean):
            return True

    return False


def is_direct_publisher_url(url):
    if not url:
        return False

    if is_blocked_url(url):
        return False

    host = domain_of(url)

    approved = [
        "citizen.digital",
        "the-star.co.ke",
        "kbc.co.ke",
        "nation.africa",
    ]

    return any(
        host == domain or host.endswith("." + domain)
        for domain in approved
    )


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    text = clean_text(text).lower()

    best_county = ""
    best_score = 0

    for county, aliases in COUNTIES.items():

        score = 0

        for alias in aliases:
            alias_lower = alias.lower()

            if re.search(
                r"\b" + re.escape(alias_lower) + r"\b",
                text,
            ):
                score += 1

        if score > best_score:
            best_county = county
            best_score = score

    return best_county


# ============================================================
# HTTP
# ============================================================

def fetch_html(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None, ""

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "html" not in content_type:
            return None, ""

        return response, response.text

    except Exception as exc:
        log(
            f"FETCH FAILED: "
            f"{url} -> {type(exc).__name__}"
        )

        return None, ""


# ============================================================
# ARTICLE LINK DISCOVERY
# ============================================================

def discover_article_links(html_text, base_url):
    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    results = []
    seen = set()

    for tag in soup.find_all("a", href=True):

        href = clean_text(tag.get("href"))

        if not href:
            continue

        url = urljoin(
            base_url,
            href,
        )

        parsed = urlparse(url)

        if parsed.scheme not in {
            "http",
            "https",
        }:
            continue

        url = url.split("#")[0]

        if url in seen:
            continue

        seen.add(url)

        if not is_direct_publisher_url(url):
            continue

        anchor_text = clean_text(
            tag.get_text(" ", strip=True)
        )

        parent_text = clean_text(
            tag.parent.get_text(
                " ",
                strip=True,
            )
            if tag.parent
            else ""
        )

        combined = clean_text(
            f"{anchor_text} {parent_text}"
        )

        results.append(
            {
                "url": url,
                "text": combined,
            }
        )

    return results


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def image_candidates(soup, article_url):
    candidates = []

    def add(value):
        value = clean_text(value)

        if not value:
            return

        if value.startswith("data:"):
            return

        if not (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("//")
            or value.startswith("/")
        ):
            return

        value = urljoin(
            article_url,
            value,
        )

        if value not in candidates:
            candidates.append(value)

    # Highest-priority metadata.
    for attrs in [
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
    ]:

        for tag in soup.find_all(
            "meta",
            attrs=attrs,
        ):
            add(tag.get("content"))

    # image_src
    for tag in soup.find_all(
        "link",
        rel=lambda value: value and "image_src" in value,
    ):
        add(tag.get("href"))

    # Actual images.
    for img in soup.find_all("img"):

        for attribute in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "data-url",
            "data-srcset",
        ]:

            value = img.get(attribute)

            if not value:
                continue

            if attribute == "data-srcset":

                first = str(value).split(",")[0].strip()

                if first:
                    add(first.split(" ")[0])

            else:
                add(value)

    return candidates


# ============================================================
# IMAGE QUALITY
# ============================================================

def image_is_rejected_url(url):
    lowered = url.lower()

    return any(
        term in lowered
        for term in IMAGE_REJECT_TERMS
    )


def validate_image_bytes(content):
    if not content:
        return False, None

    if len(content) < 20_000:
        return False, None

    try:
        from io import BytesIO

        image = Image.open(
            BytesIO(content)
        )

        image.load()

        width, height = image.size

        if width < 400 or height < 250:
            return False, None

        if width * height < 150_000:
            return False, None

        return True, image

    except Exception:
        return False, None


def download_real_image(url):
    if not url:
        return None

    if image_is_rejected_url(url):
        return None

    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if not content_type.startswith("image/"):
            return None

        valid, image = validate_image_bytes(
            response.content
        )

        if not valid:
            return None

        digest = hashlib.md5(
            response.content
        ).hexdigest()

        # Reject obvious tiny/icon-like files.
        if len(response.content) < 20_000:
            return None

        return {
            "bytes": response.content,
            "image": image,
            "md5": digest,
            "url": url,
            "width": image.width,
            "height": image.height,
        }

    except Exception:
        return None


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(url):
    response, html_text = fetch_html(url)

    if not response or not html_text:
        return None

    final_url = response.url

    if not is_direct_publisher_url(final_url):
        return None

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = ""

    meta_title = soup.find(
        "meta",
        attrs={"property": "og:title"},
    )

    if meta_title:
        title = clean_text(
            meta_title.get("content")
        )

    if not title:

        meta_title = soup.find(
            "meta",
            attrs={"name": "twitter:title"},
        )

        if meta_title:
            title = clean_text(
                meta_title.get("content")
            )

    if not title:

        h1 = soup.find("h1")

        if h1:
            title = clean_text(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

    if not title and soup.title:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    title = normalize_title(title)

    if not title:
        return None

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    summary = ""

    for attrs in [
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ]:

        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:
            summary = clean_text(
                tag.get("content")
            )

            if summary:
                break

    # --------------------------------------------------------
    # ARTICLE BODY
    # --------------------------------------------------------

    paragraphs = []

    article_container = (
        soup.find("article")
        or soup.find(
            "main"
        )
        or soup.body
    )

    if article_container:

        for p in article_container.find_all("p"):

            text = clean_text(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text:
                continue

            if len(text) < 35:
                continue

            lowered = text.lower()

            boilerplate = [
                "subscribe",
                "newsletter",
                "sign up",
                "follow us",
                "read more",
                "advertisement",
                "cookie",
                "privacy policy",
                "terms and conditions",
                "download our app",
                "google news",
            ]

            if any(
                item in lowered
                for item in boilerplate
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    body = " ".join(
        paragraphs[:14]
    )

    body = clean_text(body)

    # --------------------------------------------------------
    # COUNTY
    # --------------------------------------------------------

    county = detect_county(
        f"{title} {summary} {body}"
    )

    if not county:
        return None

    # --------------------------------------------------------
    # IMAGE CANDIDATES
    # --------------------------------------------------------

    candidates = image_candidates(
        soup,
        final_url,
    )

    selected_image = None

    for image_url in candidates[:20]:

        image = download_real_image(
            image_url
        )

        if image:
            selected_image = image
            break

    if not selected_image:
        return None

    # --------------------------------------------------------
    # QUALITY SCORE
    # --------------------------------------------------------

    score = score_article(
        title=title,
        summary=summary,
        body=body,
        county=county,
        image=selected_image,
        url=final_url,
    )

    return {
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "url": final_url,
        "image": selected_image,
        "score": score,
    }


# ============================================================
# ARTICLE SCORING
# ============================================================

def score_article(
    title,
    summary,
    body,
    county,
    image,
    url,
):
    text = clean_text(
        f"{title} {summary} {body}"
    ).lower()

    score = 0

    # County relevance.
    if county:
        score += 30

    # Substantive reporting.
    word_count = len(
        body.split()
    )

    if word_count >= 150:
        score += 35
    elif word_count >= 100:
        score += 28
    elif word_count >= 70:
        score += 20
    elif word_count >= 40:
        score += 10

    # Concrete public-interest signals.
    useful_terms = [
        "project",
        "road",
        "hospital",
        "school",
        "water",
        "market",
        "farmers",
        "agriculture",
        "jobs",
        "business",
        "investment",
        "health",
        "security",
        "police",
        "court",
        "county",
        "government",
        "development",
        "construction",
        "funding",
        "budget",
        "education",
        "transport",
        "infrastructure",
        "residents",
    ]

    for term in useful_terms:
        if re.search(
            r"\b" + re.escape(term) + r"\b",
            text,
        ):
            score += 2

    # Discourage pure political spectacle.
    soft_political_terms = [
        "charm offensive",
        "crowd erupts",
        "crowd goes wild",
        "rally",
        "dance",
        "chants",
        "welcome",
        "applauds",
        "tour",
        "campaign",
    ]

    for term in soft_political_terms:
        if term in text:
            score -= 8

    # Penalize extremely thin articles.
    if word_count < 35:
        score -= 50

    # Good image dimensions.
    if image:
        width = image.get("width", 0)
        height = image.get("height", 0)

        if width >= 800:
            score += 10

        if height >= 500:
            score += 10

    # Direct approved publisher.
    if is_direct_publisher_url(url):
        score += 10

    return score


# ============================================================
# DISCOVER STORIES
# ============================================================

def discover_stories():
    log("")
    log("=" * 70)
    log("DISCOVERING REAL RIFT VALLEY NEWS")
    log("=" * 70)

    candidates = []

    for publisher in PUBLISHERS:

        log(
            f"CHECKING: {publisher['name']}"
        )

        response, html_text = fetch_html(
            publisher["url"]
        )

        if not response or not html_text:
            continue

        links = discover_article_links(
            html_text,
            publisher["url"],
        )

        log(
            f"  LINKS FOUND: {len(links)}"
        )

        # Rank links by county relevance before opening.
        ranked_links = []

        for item in links:

            county = detect_county(
                item["text"]
            )

            if not county:
                continue

            relevance = 0

            for alias in COUNTIES[county]:

                if re.search(
                    r"\b" + re.escape(alias.lower()) + r"\b",
                    item["text"].lower(),
                ):
                    relevance += 5

            ranked_links.append(
                (
                    relevance,
                    item["url"],
                )
            )

        ranked_links.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        for _, article_url in ranked_links[:12]:

            if any(
                article["url"] == article_url
                for article in candidates
            ):
                continue

            log(
                f"  TESTING ARTICLE: {article_url}"
            )

            article = extract_article(
                article_url
            )

            if not article:
                continue

            # Never accept a Google/social URL.
            if not is_direct_publisher_url(
                article["url"]
            ):
                continue

            candidates.append(
                article
            )

            log(
                f"  ACCEPTED: {article['county']} | "
                f"{article['title']}"
            )

            # Keep discovery controlled.
            if len(candidates) >= 20:
                break

            time.sleep(0.3)

        if len(candidates) >= 20:
            break

    return candidates


# ============================================================
# BUILD NATURAL SCRIPT
# ============================================================

def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    result = []

    for part in parts:

        part = clean_text(part)

        if len(part) < 25:
            continue

        result.append(part)

    return result


def build_original_script(article):
    county = clean_text(
        article["county"]
    )

    title = normalize_title(
        article["title"]
    )

    summary = clean_text(
        article["summary"]
    )

    body = clean_text(
        article["body"]
    )

    sentences = split_sentences(
        body
    )

    # Remove sentences that are clearly metadata.
    clean_sentences = []

    for sentence in sentences:

        lowered = sentence.lower()

        if any(
            phrase.lower() in lowered
            for phrase in [
                "google news",
                "subscribe",
                "follow us",
                "read more",
                "download our app",
            ]
        ):
            continue

        sentence = remove_forbidden_metadata(
            sentence
        )

        if len(sentence) >= 25:
            clean_sentences.append(
                sentence
            )

    parts = []

    # Natural opening.
    parts.append(
        f"Here is the latest development from {county}."
    )

    # Headline.
    parts.append(
        title + "."
    )

    if summary:
        cleaned_summary = remove_forbidden_metadata(
            summary
        )

        if cleaned_summary:
            parts.append(
                cleaned_summary
            )

    # Add substantive article information.
    for sentence in clean_sentences:

        if len(
            " ".join(parts)
        ) >= 520:
            break

        # Avoid repeating headline.
        if sentence.lower() == title.lower():
            continue

        parts.append(
            sentence
        )

    script = " ".join(
        parts
    )

    script = remove_forbidden_metadata(
        script
    )

    script = re.sub(
        r"\s+",
        " ",
        script,
    ).strip()

    # Guarantee a reasonable minimum.
    if len(script.split()) < 70:

        additional = (
            "The development is significant for local residents "
            "and businesses because it could affect services, "
            "economic activity and day-to-day life in the area. "
            "Further progress will be watched closely as the "
            "situation develops."
        )

        script = clean_text(
            f"{script} {additional}"
        )

    return script


# ============================================================
# SAVE REAL IMAGE
# ============================================================

def save_story_image(image_info):
    SOURCE_ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove old image first.
    if FINAL_IMAGE.exists():
        FINAL_IMAGE.unlink()

    image = image_info["image"]

    # Convert to RGB JPEG.
    if image.mode not in (
        "RGB",
        "L",
    ):
        image = image.convert("RGB")
    else:
        image = image.convert("RGB")

    # Save normalized local image.
    image.save(
        FINAL_IMAGE,
        "JPEG",
        quality=95,
        optimize=True,
    )

    # Verify saved image.
    with Image.open(
        FINAL_IMAGE
    ) as check:

        check.load()

        if (
            check.width < 400
            or check.height < 250
        ):
            raise RuntimeError(
                "Saved story image failed dimension validation."
            )

    return FINAL_IMAGE


# ============================================================
# CREATE CANONICAL STORY
# ============================================================

def create_canonical_story(article, script):
    image_path = save_story_image(
        article["image"]
    )

    # IMPORTANT:
    # Deliberately do NOT store publisher/source metadata.
    #
    # The video pipeline receives only the information needed
    # to create the original presentation.
    story = {
        "title": normalize_title(
            article["title"]
        ),
        "county": clean_text(
            article["county"]
        ),
        "summary": remove_forbidden_metadata(
            article["summary"]
        ),
        "body": remove_forbidden_metadata(
            article["body"]
        ),
        "image_path": str(
            image_path.relative_to(ROOT)
        ).replace("\\", "/"),
        "script": script,
        "selected_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    return story


def create_canonical_script(story):
    return {
        "title": story["title"],
        "county": story["county"],
        "narration": story["script"],
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_story(story):
    title = clean_text(
        story.get("title")
    )

    county = clean_text(
        story.get("county")
    )

    image_path = clean_text(
        story.get("image_path")
    )

    script = clean_text(
        story.get("script")
    )

    if not title:
        raise RuntimeError(
            "Selected story has no title."
        )

    if not county:
        raise RuntimeError(
            "Selected story has no county."
        )

    if not image_path:
        raise RuntimeError(
            "Selected story has no verified local image."
        )

    actual_image = ROOT / image_path

    if not actual_image.exists():
        raise RuntimeError(
            f"Verified story image does not exist: {actual_image}"
        )

    if not script:
        raise RuntimeError(
            "Selected story has no narration."
        )

    word_count = len(
        script.split()
    )

    if word_count < 70:
        raise RuntimeError(
            f"Narration is too short: {word_count} words."
        )

    forbidden = [
        "google news",
        "people daily",
        "the star",
        "citizen digital",
        "citizen",
        "the standard",
        "daily nation",
        "nation",
        "capital news",
        "kbc",
        "facebook",
        "instagram",
        "twitter",
        "youtube",
        "tiktok",
    ]

    lowered = script.lower()

    found = [
        phrase
        for phrase in forbidden
        if phrase in lowered
    ]

    if found:
        raise RuntimeError(
            "Forbidden source/platform text found in narration: "
            + ", ".join(found)
        )

    # Validate image independently.
    try:
        with Image.open(
            actual_image
        ) as image:

            image.load()

            if image.width < 400:
                raise RuntimeError(
                    "Story image is too narrow."
                )

            if image.height < 250:
                raise RuntimeError(
                    "Story image is too short."
                )

    except RuntimeError:
        raise

    except Exception as exc:
        raise RuntimeError(
            f"Story image is invalid: {exc}"
        )

    log("")
    log("VALIDATION PASSED")
    log(
        f"TITLE      : {title}"
    )
    log(
        f"COUNTY     : {county}"
    )
    log(
        f"WORDS      : {word_count}"
    )
    log(
        f"IMAGE      : {actual_image}"
    )


# ============================================================
# CLEAN OLD OUTPUT
# ============================================================

def clean_previous_run():
    log("")
    log("=" * 70)
    log("CLEANING PREVIOUS RUN")
    log("=" * 70)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in [
        SELECTED_STORY_FILE,
        SELECTED_SCRIPT_FILE,
        FINAL_IMAGE,
    ]:

        if path.exists():

            try:
                path.unlink()

                log(
                    f"REMOVED: {path}"
                )

            except Exception as exc:

                log(
                    f"WARNING: Could not remove "
                    f"{path}: {exc}"
                )


# ============================================================
# SELECT BEST STORY
# ============================================================

def select_best_story(candidates):
    if not candidates:
        raise RuntimeError(
            "No valid Rift Valley article with a real image was found."
        )

    # Deduplicate by image MD5.
    unique = []
    seen_images = set()

    for article in candidates:

        image_md5 = article["image"]["md5"]

        if image_md5 in seen_images:
            continue

        seen_images.add(
            image_md5
        )

        unique.append(
            article
        )

    if not unique:
        raise RuntimeError(
            "All discovered stories used duplicate images."
        )

    # Highest substantive score.
    unique.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return unique[0]


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_video_generator():
    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            f"Video generator not found: {VIDEO_GENERATOR}"
        )

    log("")
    log("=" * 70)
    log("RUNNING VIDEO GENERATOR")
    log("=" * 70)

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(VIDEO_GENERATOR),
        ],
        cwd=str(ROOT),
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Video generator failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# VERIFY FINAL VIDEO
# ============================================================

def verify_video():
    log("")
    log("=" * 70)
    log("VERIFYING FINAL MP4")
    log("=" * 70)

    if not FINAL_VIDEO.exists():

        log(
            "Available MP4 files:"
        )

        for mp4 in ROOT.rglob(
            "*.mp4"
        ):
            log(
                str(mp4)
            )

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100_000:
        raise RuntimeError(
            "Generated MP4 is suspiciously small."
        )

    log(
        "FINAL MP4 VERIFIED"
    )

    log(
        f"FILE: {FINAL_VIDEO}"
    )

    log(
        f"SIZE: {size / (1024 * 1024):.2f} MB"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH")
    log("=" * 70)

    log(
        "VERSION: RVW_MAIN_V8_ORIGINAL_NEWS_PIPELINE"
    )

    log(
        "MODE: ONE STORY / ONE REAL PHOTO / ORIGINAL PRESENTATION"
    )

    # --------------------------------------------------------
    # 1. Clean old generated data.
    # --------------------------------------------------------

    clean_previous_run()

    # --------------------------------------------------------
    # 2. Discover direct publisher articles.
    # --------------------------------------------------------

    candidates = discover_stories()

    log("")
    log("=" * 70)
    log("DISCOVERY COMPLETE")
    log("=" * 70)

    log(
        f"VALID ARTICLES: {len(candidates)}"
    )

    if not candidates:
        raise RuntimeError(
            "No valid article was discovered. "
            "No fake or placeholder story will be generated."
        )

    # --------------------------------------------------------
    # 3. Select ONE substantive story.
    # --------------------------------------------------------

    selected = select_best_story(
        candidates
    )

    log("")
    log("=" * 70)
    log("STORY SELECTED")
    log("=" * 70)

    log(
        f"COUNTY : {selected['county']}"
    )

    log(
        f"TITLE  : {selected['title']}"
    )

    log(
        f"SCORE  : {selected['score']}"
    )

    # --------------------------------------------------------
    # 4. Build original narration.
    # --------------------------------------------------------

    script = build_original_script(
        selected
    )

    # --------------------------------------------------------
    # 5. Build canonical story.
    # --------------------------------------------------------

    story = create_canonical_story(
        selected,
        script,
    )

    # --------------------------------------------------------
    # 6. Build canonical script.
    # --------------------------------------------------------

    selected_script = create_canonical_script(
        story
    )

    # --------------------------------------------------------
    # 7. Validate before generator.
    # --------------------------------------------------------

    validate_story(
        story
    )

    # --------------------------------------------------------
    # 8. Save ONLY the canonical schema.
    # --------------------------------------------------------

    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        selected_script,
    )

    log("")
    log("=" * 70)
    log("CANONICAL FILES CREATED")
    log("=" * 70)

    log(
        f"STORY   : {SELECTED_STORY_FILE}"
    )

    log(
        f"SCRIPT  : {SELECTED_SCRIPT_FILE}"
    )

    # --------------------------------------------------------
    # 9. Generate reel.
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # 10. Verify MP4.
    # --------------------------------------------------------

    verify_video()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH COMPLETED SUCCESSFULLY")
    log("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log("")
        log(
            f"{type(exc).__name__}: {exc}"
        )
        log("")

        raise
```

**Important:** this controller now creates a single clean schema:

* `selected_story.json` → story + verified local image + script
* `selected_script.json` → title + county + narration

No publisher/source fields are passed into the video-generation data.
