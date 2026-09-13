from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS ENGINE
# ============================================================

VERSION = "RVW_MAIN_V15_NATIONAL_RUTO_ROTATION"

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
SOURCE_DIR = ROOT / "assets" / "source"
AUDIO_DIR = ROOT / "audio"

SELECTED_STORY = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"
HISTORY_FILE = DATA_DIR / "story_history.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"
NARRATION = AUDIO_DIR / "narration.mp3"


# ============================================================
# DIRECTORIES
# ============================================================

for directory in (
    DATA_DIR,
    OUTPUT_DIR,
    SOURCE_DIR,
    AUDIO_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


REQUEST_TIMEOUT = 20


# ============================================================
# PUBLISHER PAGES
# ============================================================

PUBLISHER_PAGES = [
    "https://citizen.digital/",
    "https://www.the-star.co.ke/news/",
    "https://www.kbc.co.ke/",
    "https://nation.africa/kenya/news",
]


# ============================================================
# APPROVED PUBLISHER DOMAINS
# ============================================================

APPROVED_DOMAINS = {
    "citizen.digital",
    "www.citizen.digital",
    "the-star.co.ke",
    "www.the-star.co.ke",
    "kbc.co.ke",
    "www.kbc.co.ke",
    "nation.africa",
    "www.nation.africa",
}


# ============================================================
# BLOCKED DOMAINS
# ============================================================

BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
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
    "www.whatsapp.com",
    "google.com",
    "www.google.com",
    "news.google.com",
}


# ============================================================
# RIFT VALLEY COUNTIES
# ============================================================

RIFT_VALLEY_COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
]


# ============================================================
# OTHER KENYAN REGIONS
# ============================================================

OTHER_REGIONS = [
    "Nyanza",
    "Western",
    "Coast",
    "Eastern",
    "Central",
    "Mt Kenya",
    "Northern Kenya",
    "Nairobi",
]


# ============================================================
# COUNTY MAP
# ============================================================

COUNTY_NAMES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
    "Kisumu",
    "Siaya",
    "Migori",
    "Homa Bay",
    "Kakamega",
    "Bungoma",
    "Busia",
    "Vihiga",
    "Kisii",
    "Nyamira",
    "Mombasa",
    "Kwale",
    "Kilifi",
    "Tana River",
    "Lamu",
    "Taita Taveta",
    "Garissa",
    "Wajir",
    "Mandera",
    "Marsabit",
    "Isiolo",
    "Meru",
    "Tharaka Nithi",
    "Embu",
    "Kitui",
    "Machakos",
    "Makueni",
    "Kiambu",
    "Murang'a",
    "Kirinyaga",
    "Nyeri",
    "Nyandarua",
    "Laikipia",
    "Samburu",
    "Trans Nzoia",
    "Turkana",
    "Baringo",
    "Kajiado",
    "Machakos",
    "Nairobi",
]


# ============================================================
# SOURCE NAMES
# Used only to clean narration.
# ============================================================

SOURCE_NAMES = [
    "Citizen Digital",
    "Citizen",
    "Daily Nation",
    "Nation Africa",
    "Nation",
    "The Star",
    "KBC Digital",
    "KBC News",
    "KBC",
    "People Daily",
    "The Standard",
    "Standard Media",
    "Capital News",
    "NTV Kenya",
    "NTV",
    "TV47",
    "Tuko",
]


# ============================================================
# STORY TOPIC SIGNALS
# ============================================================

RUTO_TERMS = [
    "william ruto",
    "president ruto",
    "president william ruto",
    "ruto",
    "head of state",
    "state house",
    "presidential tour",
    "president's tour",
    "presidential working tour",
    "working tour",
]


DEVELOPMENT_TERMS = [
    "road",
    "roads",
    "highway",
    "hospital",
    "health centre",
    "health center",
    "market",
    "water project",
    "water",
    "electricity",
    "power",
    "housing",
    "affordable housing",
    "school",
    "tveta",
    "tvets",
    "university",
    "dam",
    "irrigation",
    "farmers",
    "agriculture",
    "industrial park",
    "industrial",
    "factory",
    "manufacturing",
    "infrastructure",
    "development",
    "project",
    "projects",
    "jobs",
    "employment",
    "airport",
    "port",
    "railway",
]


POLITICAL_TERMS = [
    "politics",
    "political",
    "2027",
    "election",
    "opposition",
    "campaign",
    "alliance",
    "coalition",
    "party",
    "leaders",
    "politicians",
    "mp",
    "senator",
    "governor",
    "deputy president",
    "uda",
    "odm",
]


RIFT_TERMS = [
    "bomet",
    "kericho",
    "nakuru",
    "nandi",
    "uasin gishu",
    "elgeyo-marakwet",
    "west pokot",
    "narok",
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = unicodedata.normalize("NFKC", value)

    value = re.sub(r"\s+", " ", value)
    value = value.strip()

    return value


def normalize_key(value):
    value = clean_text(value).lower()

    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def canonical_url(url):
    try:
        parsed = urlparse(url)

        if not parsed.scheme:
            return ""

        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        path = parsed.path.rstrip("/")

        return f"{parsed.scheme.lower()}://{host}{path}"

    except Exception:
        return ""


def domain_allowed(url):
    try:
        host = urlparse(url).netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        if host in BLOCKED_DOMAINS:
            return False

        if host in APPROVED_DOMAINS:
            return True

        return False

    except Exception:
        return False


def word_count(text):
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def safe_get(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if not response.text:
            return None

        return response

    except Exception as exc:
        print(f"[REQUEST FAILED] {url} -> {exc}")

        return None


# ============================================================
# CLEAN ARTICLE TEXT
# ============================================================

def remove_junk(text):
    text = clean_text(text)

    if not text:
        return ""

    # Remove URLs.
    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove common web artifacts.
    text = re.sub(
        r"\[[^\]]{1,100}\]",
        "",
        text,
    )

    text = re.sub(
        r"\([^)]{0,80}\b(?:Getty|Reuters|AFP)\b[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove publisher attribution where it is obvious.
    for source in SOURCE_NAMES:
        text = re.sub(
            rf"\b{re.escape(source)}\s*[:\-–—]\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            rf"\b{re.escape(source)}\s+reports\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            rf"\baccording to {re.escape(source)}\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_title(title):
    title = remove_junk(title)

    for separator in [
        " | ",
        " - ",
        " – ",
        " — ",
        " :: ",
    ]:
        if separator in title:
            parts = title.split(separator)

            if len(parts) >= 2:
                left = parts[0].strip()

                if 4 <= word_count(left) <= 25:
                    title = left
                    break

    return title.strip()


# ============================================================
# COUNTY / REGION DETECTION
# ============================================================

def detect_county(text):
    text_lower = text.lower()

    for county in sorted(COUNTY_NAMES, key=len, reverse=True):
        if county.lower() in text_lower:
            return county

    return ""


def detect_region(text):
    text_lower = text.lower()

    if any(term in text_lower for term in RIFT_TERMS):
        return "Rift Valley"

    if any(
        term in text_lower
        for term in [
            "kisumu",
            "siaya",
            "migori",
            "homa bay",
            "nyanza",
            "kisii",
            "nyamira",
        ]
    ):
        return "Nyanza"

    if any(
        term in text_lower
        for term in [
            "kakamega",
            "bungoma",
            "busia",
            "vihiga",
            "western kenya",
        ]
    ):
        return "Western"

    if any(
        term in text_lower
        for term in [
            "mombasa",
            "kwale",
            "kilifi",
            "lamu",
            "taita taveta",
            "coast",
        ]
    ):
        return "Coast"

    if any(
        term in text_lower
        for term in [
            "garissa",
            "wajir",
            "mandera",
            "marsabit",
            "isiolo",
            "northern kenya",
        ]
    ):
        return "Northern Kenya"

    if any(
        term in text_lower
        for term in [
            "meru",
            "embu",
            "kitui",
            "machakos",
            "makueni",
            "eastern kenya",
        ]
    ):
        return "Eastern"

    if any(
        term in text_lower
        for term in [
            "kiambu",
            "murang'a",
            "muranga",
            "kirinyaga",
            "nyeri",
            "nyandarua",
            "central kenya",
            "mt kenya",
        ]
    ):
        return "Central / Mt Kenya"

    if "nairobi" in text_lower:
        return "Nairobi"

    return ""


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def image_candidates(soup, base_url):
    candidates = []

    def add(value):
        if not value:
            return

        value = html.unescape(str(value)).strip()

        if value.startswith("//"):
            value = "https:" + value

        value = urljoin(base_url, value)

        if value.startswith("http"):
            candidates.append(value)

    # Open Graph.
    for tag in soup.find_all("meta"):
        prop = (
            tag.get("property")
            or tag.get("name")
            or ""
        ).lower()

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:
            add(tag.get("content"))

    # JSON-LD.
    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            data = json.loads(script.string or script.get_text())

        except Exception:
            continue

        def extract_json_images(obj):
            if isinstance(obj, dict):
                image = obj.get("image")

                if isinstance(image, str):
                    add(image)

                elif isinstance(image, dict):
                    add(image.get("url"))

                elif isinstance(image, list):
                    for item in image:
                        if isinstance(item, str):
                            add(item)

                        elif isinstance(item, dict):
                            add(item.get("url"))

                for value in obj.values():
                    extract_json_images(value)

            elif isinstance(obj, list):
                for item in obj:
                    extract_json_images(item)

        extract_json_images(data)

    # HTML images.
    for img in soup.find_all("img"):
        for attribute in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
        ]:
            add(img.get(attribute))

        srcset = img.get("srcset")

        if srcset:
            for item in srcset.split(","):
                add(item.strip().split(" ")[0])

    # Remove duplicates while preserving order.
    seen = set()
    result = []

    for item in candidates:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


def download_image(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            return None

        content = response.content

        if len(content) < 15_000:
            return None

        image = Image.open(BytesIO(content))

        image.load()

        width, height = image.size

        if width < 500 or height < 300:
            return None

        if width * height < 250_000:
            return None

        if width > 6000 or height > 6000:
            return None

        if image.mode not in {
            "RGB",
            "RGBA",
            "L",
            "LA",
        }:
            image = image.convert("RGB")

        raw_hash = hashlib.md5(content).hexdigest()

        return {
            "url": url,
            "width": width,
            "height": height,
            "md5": raw_hash,
            "image": image.convert("RGB"),
        }

    except Exception:
        return None


# ============================================================
# ARTICLE BODY EXTRACTION
# ============================================================

def extract_article_body(soup):
    paragraphs = []

    selectors = [
        "article p",
        "main p",
        "[itemprop='articleBody'] p",
        ".article-body p",
        ".story-body p",
        ".content p",
    ]

    found = []

    for selector in selectors:
        found = soup.select(selector)

        if found:
            break

    if not found:
        found = soup.find_all("p")

    for paragraph in found:
        text = remove_junk(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if word_count(text) < 5:
            continue

        if len(text) < 30:
            continue

        paragraphs.append(text)

    # Remove exact duplicate paragraphs.
    unique = []
    seen = set()

    for paragraph in paragraphs:
        key = normalize_key(paragraph)

        if key in seen:
            continue

        seen.add(key)
        unique.append(paragraph)

    return unique


# ============================================================
# STORY TYPE
# ============================================================

def classify_story(title, body, county, region):
    text = (
        f"{title} "
        f"{body} "
        f"{county} "
        f"{region}"
    ).lower()

    ruto_hits = sum(
        1
        for term in RUTO_TERMS
        if term in text
    )

    development_hits = sum(
        1
        for term in DEVELOPMENT_TERMS
        if term in text
    )

    political_hits = sum(
        1
        for term in POLITICAL_TERMS
        if term in text
    )

    rift_hits = sum(
        1
        for term in RIFT_TERMS
        if term in text
    )

    if ruto_hits >= 1 and development_hits >= 1:
        return "Ruto Development Tour"

    if ruto_hits >= 1 and political_hits >= 1:
        return "Ruto Political Tour"

    if ruto_hits >= 1:
        return "Ruto National Tour"

    if rift_hits >= 1:
        return "Rift Valley"

    if development_hits >= 1:
        return "Development"

    if political_hits >= 1:
        return "Politics"

    return "County News"


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(url):
    if not domain_allowed(url):
        return None

    canonical = canonical_url(url)

    if not canonical:
        return None

    response = safe_get(url)

    if response is None:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # Remove elements that pollute extraction.
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "form",
            "nav",
            "footer",
        ]
    ):
        tag.decompose()

    title = ""

    og_title = soup.find(
        "meta",
        property="og:title",
    )

    if og_title:
        title = og_title.get("content", "")

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    title = clean_title(title)

    if not title:
        return None

    paragraphs = extract_article_body(soup)

    body = " ".join(paragraphs)

    body = remove_junk(body)

    if word_count(body) < 45:
        return None

    county = detect_county(
        f"{title} {body}"
    )

    region = detect_region(
        f"{title} {body}"
    )

    story_type = classify_story(
        title,
        body,
        county,
        region,
    )

    # ========================================================
    # IMAGE
    # ========================================================

    image = None

    for candidate_url in image_candidates(
        soup,
        response.url,
    ):
        image = download_image(candidate_url)

        if image is not None:
            break

    if image is None:
        return None

    # ========================================================
    # SCORE
    # ========================================================

    text_lower = (
        f"{title} {body}"
    ).lower()

    score = 0

    # Strong base score for substantial articles.
    score += min(word_count(body), 450) / 12

    # Strong national Ruto signal.
    ruto_hits = sum(
        1
        for term in RUTO_TERMS
        if term in text_lower
    )

    score += ruto_hits * 18

    # Development signal.
    development_hits = sum(
        1
        for term in DEVELOPMENT_TERMS
        if term in text_lower
    )

    score += min(
        development_hits * 4,
        30,
    )

    # Political signal.
    political_hits = sum(
        1
        for term in POLITICAL_TERMS
        if term in text_lower
    )

    score += min(
        political_hits * 3,
        25,
    )

    # Rift Valley priority.
    if region == "Rift Valley":
        score += 20

    # Ruto tour priority.
    if story_type in {
        "Ruto Development Tour",
        "Ruto Political Tour",
        "Ruto National Tour",
    }:
        score += 25

    # Penalise obvious low-value entertainment/event material.
    penalty_terms = [
        "crowd erupts",
        "crowd goes wild",
        "dance",
        "dancing",
        "chants",
        "chanting",
        "celebrity",
        "fashion",
        "birthday",
        "wedding",
    ]

    for term in penalty_terms:
        if term in text_lower:
            score -= 10

    # Penalise clickbait.
    if "watch:" in text_lower:
        score -= 8

    if "photos:" in text_lower:
        score -= 5

    if "video:" in text_lower:
        score -= 5

    return {
        "title": title,
        "url": canonical,
        "source_url": response.url,
        "county": county,
        "region": region,
        "story_type": story_type,
        "body": body,
        "paragraphs": paragraphs,
        "score": round(score, 2),
        "image": image,
        "discovered_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ============================================================
# DISCOVER ARTICLE LINKS
# ============================================================

def discover_links(page_url):
    response = safe_get(page_url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    links = []

    for anchor in soup.find_all("a"):
        href = anchor.get("href")

        if not href:
            continue

        absolute = urljoin(
            response.url,
            href,
        )

        if not domain_allowed(absolute):
            continue

        canonical = canonical_url(
            absolute
        )

        if not canonical:
            continue

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if word_count(text) < 3:
            continue

        if len(text) < 20:
            continue

        if len(text) > 300:
            text = text[:300]

        links.append(
            {
                "url": canonical,
                "text": text,
            }
        )

    # Deduplicate.
    result = []
    seen = set()

    for item in links:
        if item["url"] in seen:
            continue

        seen.add(item["url"])
        result.append(item)

    return result


# ============================================================
# DISCOVER STORIES
# ============================================================

def discover():
    print()
    print("=" * 70)
    print("DISCOVERING CURRENT KENYAN STORIES")
    print("=" * 70)

    candidates = []

    for publisher_page in PUBLISHER_PAGES:
        print()
        print(f"[PUBLISHER] {publisher_page}")

        links = discover_links(
            publisher_page
        )

        print(
            f"[LINKS FOUND] {len(links)}"
        )

        # Prioritise likely relevant links.
        links.sort(
            key=lambda item: (
                bool(
                    detect_county(
                        item["text"]
                    )
                ),
                any(
                    term in item["text"].lower()
                    for term in RUTO_TERMS
                ),
                any(
                    term in item["text"].lower()
                    for term in DEVELOPMENT_TERMS
                ),
                len(item["text"]),
            ),
            reverse=True,
        )

        # Check substantially more links.
        for index, link in enumerate(
            links[:100],
            start=1,
        ):
            print(
                f"[CHECK {index:03d}] "
                f"{link['text'][:100]}"
            )

            article = extract_article(
                link["url"]
            )

            if article is None:
                continue

            candidates.append(article)

            print(
                "[ACCEPTED] "
                f"{article['story_type']} | "
                f"{article['region'] or 'Kenya'} | "
                f"{article['title'][:90]} | "
                f"score={article['score']}"
            )

            # Continue collecting.
            if len(candidates) >= 80:
                break

        if len(candidates) >= 80:
            break

    print()
    print(
        f"[TOTAL ACCEPTED] {len(candidates)}"
    )

    return candidates


# ============================================================
# DEDUPLICATE STORIES
# ============================================================

def deduplicate_candidates(candidates):
    unique = []

    seen_urls = set()
    seen_titles = set()
    seen_images = set()

    for article in candidates:
        url_key = canonical_url(
            article.get("url", "")
        )

        title_key = normalize_key(
            article.get("title", "")
        )

        image_info = article.get(
            "image",
            {},
        )

        image_key = image_info.get(
            "md5",
            "",
        )

        if url_key and url_key in seen_urls:
            continue

        if title_key and title_key in seen_titles:
            continue

        if image_key and image_key in seen_images:
            continue

        if url_key:
            seen_urls.add(url_key)

        if title_key:
            seen_titles.add(title_key)

        if image_key:
            seen_images.add(image_key)

        unique.append(article)

    return unique


# ============================================================
# STORY HISTORY
# ============================================================

def load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(
            HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            return data

    except Exception as exc:
        print(
            f"[HISTORY WARNING] {exc}"
        )

    return []


def save_history(history):
    try:
        HISTORY_FILE.write_text(
            json.dumps(
                history[-100:],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:
        print(
            f"[HISTORY SAVE WARNING] {exc}"
        )


def history_identity(story):
    return {
        "url": canonical_url(
            story.get("url", "")
        ),
        "title": normalize_key(
            story.get("title", "")
        ),
        "image_md5": story.get(
            "image_md5",
            "",
        ),
    }


def remember_story(story):
    history = load_history()

    identity = history_identity(
        story
    )

    entry = {
        "url": identity["url"],
        "title": identity["title"],
        "image_md5": identity["image_md5"],
        "county": story.get(
            "county",
            "",
        ),
        "region": story.get(
            "region",
            "",
        ),
        "story_type": story.get(
            "story_type",
            "",
        ),
        "selected_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    # Remove exact duplicate.
    history = [
        item
        for item in history
        if not (
            item.get("url") == entry["url"]
            or (
                entry["image_md5"]
                and item.get("image_md5")
                == entry["image_md5"]
            )
        )
    ]

    history.append(entry)

    save_history(history)

    print(
        "[HISTORY] Recorded selected story"
    )


def seed_previous_story():
    """
    If the repository already has selected_story.json
    from an earlier version, preserve that story in history
    before deleting it.
    """

    if not SELECTED_STORY.exists():
        return

    try:
        data = json.loads(
            SELECTED_STORY.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, dict):
            return

        url = data.get("url", "")
        title = data.get("title", "")

        image_md5 = data.get(
            "image_md5",
            "",
        )

        if not url and not title:
            return

        history = load_history()

        entry = {
            "url": canonical_url(url),
            "title": normalize_key(title),
            "image_md5": image_md5,
            "county": data.get(
                "county",
                "",
            ),
            "region": data.get(
                "region",
                "",
            ),
            "story_type": data.get(
                "story_type",
                "",
            ),
            "selected_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        history.append(entry)

        # Remove duplicates while keeping recent records.
        cleaned = []

        seen = set()

        for item in reversed(history):
            key = (
                item.get("url", ""),
                item.get("title", ""),
                item.get("image_md5", ""),
            )

            if key in seen:
                continue

            seen.add(key)
            cleaned.append(item)

        cleaned.reverse()

        save_history(cleaned)

        print(
            "[HISTORY] Seeded previous selected story"
        )

    except Exception as exc:
        print(
            f"[HISTORY SEED WARNING] {exc}"
        )


# ============================================================
# SELECT STORY
# ============================================================

def select_best(candidates):
    candidates = deduplicate_candidates(
        candidates
    )

    if not candidates:
        raise RuntimeError(
            "No usable stories were discovered."
        )

    candidates.sort(
        key=lambda item: (
            item.get("score", 0),
            word_count(
                item.get("body", "")
            ),
        ),
        reverse=True,
    )

    history = load_history()

    # Last 15 stories are considered recently used.
    recent_history = history[-15:]

    recent_urls = {
        canonical_url(
            item.get("url", "")
        )
        for item in recent_history
        if item.get("url")
    }

    recent_titles = {
        normalize_key(
            item.get("title", "")
        )
        for item in recent_history
        if item.get("title")
    }

    recent_images = {
        item.get("image_md5", "")
        for item in recent_history
        if item.get("image_md5")
    }

    fresh = []

    for article in candidates:
        url = canonical_url(
            article.get("url", "")
        )

        title = normalize_key(
            article.get("title", "")
        )

        image_md5 = article.get(
            "image",
            {},
        ).get(
            "md5",
            "",
        )

        if url in recent_urls:
            continue

        if title in recent_titles:
            continue

        if image_md5 and image_md5 in recent_images:
            continue

        fresh.append(article)

    if fresh:
        pool = fresh

        print(
            f"[FRESH STORIES] {len(pool)}"
        )

    else:
        print(
            "[WARNING] All candidates were recently used."
        )

        # Fall back to the complete candidate pool.
        pool = candidates

    # ========================================================
    # ROTATION
    # ========================================================
    #
    # GitHub Actions gives every workflow run a unique
    # GITHUB_RUN_NUMBER.
    #
    # GITHUB_RUN_ATTEMPT also changes when a run is manually
    # rerun.
    #
    # This prevents the generator from selecting the same
    # highest-scoring article every time.
    # ========================================================

    run_number = os.environ.get(
        "GITHUB_RUN_NUMBER"
    )

    run_attempt = os.environ.get(
        "GITHUB_RUN_ATTEMPT"
    )

    try:
        if run_number:
            seed = int(run_number)

            if run_attempt:
                seed = (
                    seed * 100
                    + int(run_attempt)
                )

        else:
            seed = int(time.time())

    except Exception:
        seed = int(time.time())

    # Use the strongest 15 candidates rather than allowing
    # a very weak article to be selected.
    rotation_pool = pool[:15]

    if not rotation_pool:
        rotation_pool = pool

    index = seed % len(
        rotation_pool
    )

    selected = rotation_pool[index]

    print()
    print("=" * 70)
    print("SELECTED STORY")
    print("=" * 70)

    print(
        f"TITLE      : {selected['title']}"
    )

    print(
        f"TYPE       : {selected['story_type']}"
    )

    print(
        f"REGION     : "
        f"{selected['region'] or 'Kenya'}"
    )

    print(
        f"COUNTY     : "
        f"{selected['county'] or 'National'}"
    )

    print(
        f"SCORE      : "
        f"{selected['score']}"
    )

    print(
        f"URL        : "
        f"{selected['url']}"
    )

    print(
        f"ROTATION   : "
        f"{index + 1}/{len(rotation_pool)}"
    )

    print("=" * 70)

    return selected


# ============================================================
# NARRATION
# ============================================================

def split_sentences(text):
    text = clean_text(text)

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

        if word_count(sentence) < 5:
            continue

        result.append(sentence)

    return result


def sentence_key(sentence):
    return normalize_key(sentence)


def build_script(article):
    title = clean_title(
        article.get("title", "")
    )

    county = article.get(
        "county",
        "",
    )

    region = article.get(
        "region",
        "",
    )

    body = remove_junk(
        article.get("body", "")
    )

    sentences = split_sentences(
        body
    )

    selected_sentences = []

    seen = set()

    title_key = normalize_key(
        title
    )

    for sentence in sentences:
        key = sentence_key(
            sentence
        )

        if not key:
            continue

        if key in seen:
            continue

        # Avoid simply repeating the headline.
        if (
            title_key
            and (
                key == title_key
                or title_key in key
                or key in title_key
            )
        ):
            continue

        seen.add(key)
        selected_sentences.append(
            sentence
        )

        if word_count(
            " ".join(
                selected_sentences
            )
        ) >= 105:
            break

    narration_body = " ".join(
        selected_sentences
    )

    # Trim very long narration.
    words = narration_body.split()

    if len(words) > 125:
        narration_body = " ".join(
            words[:125]
        )

    # ========================================================
    # ORIGINAL INTRO
    # ========================================================

    if article.get("story_type") in {
        "Ruto Development Tour",
        "Ruto Political Tour",
        "Ruto National Tour",
    }:
        intro = (
            "President William Ruto is continuing "
            "his national political and development "
            "engagements, with the latest developments "
            "drawing attention across the country."
        )

    elif region == "Rift Valley":
        intro = (
            f"In the Rift Valley, {county or 'the region'} "
            "is at the centre of the latest developments."
        )

    elif county:
        intro = (
            f"In {county}, "
            "a major development is drawing attention."
        )

    else:
        intro = (
            "Across Kenya, a major development "
            "is drawing attention."
        )

    script = (
        f"{intro} "
        f"{title}. "
        f"{narration_body}"
    )

    script = remove_junk(
        script
    )

    # Remove accidental duplicate sentences.
    final_sentences = split_sentences(
        script
    )

    unique = []
    seen = set()

    for sentence in final_sentences:
        key = sentence_key(
            sentence
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(sentence)

    script = " ".join(unique)

    # Keep narration inside a useful reel length.
    words = script.split()

    if len(words) > 145:
        script = " ".join(
            words[:145]
        )

    if len(words) < 45:
        raise RuntimeError(
            "Generated narration is too short."
        )

    return script.strip()


# ============================================================
# SAVE IMAGE
# ============================================================

def save_image(image_info):
    image = image_info.get(
        "image"
    )

    if image is None:
        raise RuntimeError(
            "No valid article image available."
        )

    image = image.convert(
        "RGB"
    )

    # Resize only if excessively large.
    max_dimension = 3000

    if max(
        image.size
    ) > max_dimension:
        image.thumbnail(
            (
                max_dimension,
                max_dimension,
            ),
            Image.Resampling.LANCZOS,
        )

    image.save(
        FINAL_IMAGE,
        format="JPEG",
        quality=95,
        optimize=True,
    )

    if not FINAL_IMAGE.exists():
        raise RuntimeError(
            "Article image was not saved."
        )

    if FINAL_IMAGE.stat().st_size < 10_000:
        raise RuntimeError(
            "Saved article image is too small."
        )

    print(
        f"[IMAGE SAVED] {FINAL_IMAGE}"
    )


# ============================================================
# WRITE STORY FILES
# ============================================================

def write_files(article, script):
    image_info = article.get(
        "image",
        {},
    )

    story = {
        "title": article.get(
            "title",
            "",
        ),
        "url": article.get(
            "url",
            "",
        ),
        "source_url": article.get(
            "source_url",
            "",
        ),
        "county": article.get(
            "county",
            "",
        ),
        "region": article.get(
            "region",
            "",
        ),
        "story_type": article.get(
            "story_type",
            "",
        ),
        "score": article.get(
            "score",
            0,
        ),
        "image_url": image_info.get(
            "url",
            "",
        ),
        "image_md5": image_info.get(
            "md5",
            "",
        ),
        "selected_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    script_data = {
        "title": story["title"],
        "county": story["county"],
        "region": story["region"],
        "story_type": story[
            "story_type"
        ],
        "narration": script,
    }

    SELECTED_STORY.write_text(
        json.dumps(
            story,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    SELECTED_SCRIPT.write_text(
        json.dumps(
            script_data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "[FILES] selected_story.json saved"
    )

    print(
        "[FILES] selected_script.json saved"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate(article, script):
    if not article.get("title"):
        raise RuntimeError(
            "Story title is missing."
        )

    if not article.get("url"):
        raise RuntimeError(
            "Story URL is missing."
        )

    if not article.get(
        "story_type"
    ):
        raise RuntimeError(
            "Story type is missing."
        )

    if word_count(script) < 45:
        raise RuntimeError(
            "Narration contains fewer than 45 words."
        )

    if FINAL_IMAGE.exists() is False:
        raise RuntimeError(
            "Final article image does not exist."
        )

    try:
        image = Image.open(
            FINAL_IMAGE
        )

        image.verify()

    except Exception as exc:
        raise RuntimeError(
            f"Final image is invalid: {exc}"
        )

    script_lower = script.lower()

    # Prevent publisher branding inside narration.
    for source in SOURCE_NAMES:
        if source.lower() in script_lower:
            raise RuntimeError(
                "Publisher name detected in narration: "
                f"{source}"
            )

    # Detect repeated sentences.
    sentences = split_sentences(
        script
    )

    seen = set()

    for sentence in sentences:
        key = sentence_key(
            sentence
        )

        if key in seen:
            raise RuntimeError(
                "Repeated sentence detected."
            )

        seen.add(key)

    print(
        "[VALIDATION] Story and narration passed."
    )


# ============================================================
# CLEAN PREVIOUS GENERATED FILES
# ============================================================

def clean_previous():
    print()
    print("=" * 70)
    print("CLEANING PREVIOUS GENERATED OUTPUT")
    print("=" * 70)

    # IMPORTANT:
    # Preserve the previous selected story in history
    # before deleting selected_story.json.
    seed_previous_story()

    files_to_delete = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
        NARRATION,
    ]

    for path in files_to_delete:
        try:
            if path.exists():
                path.unlink()

                print(
                    f"[DELETED] {path}"
                )

        except Exception as exc:
            print(
                f"[CLEAN WARNING] "
                f"{path}: {exc}"
            )


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_generator():
    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "Video generator was not found: "
            f"{VIDEO_GENERATOR}"
        )

    print()
    print("=" * 70)
    print("RUNNING VIDEO GENERATOR")
    print("=" * 70)

    command = [
        sys.executable,
        "-u",
        str(VIDEO_GENERATOR),
    ]

    result = subprocess.run(
        command,
        cwd=str(ROOT),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Video generator failed with "
            f"exit code {result.returncode}."
        )

    print(
        "[GENERATOR] Completed successfully."
    )


# ============================================================
# VERIFY FINAL MP4
# ============================================================

def verify():
    print()
    print("=" * 70)
    print("VERIFYING FINAL MP4")
    print("=" * 70)

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    size = FINAL_VIDEO.stat().st_size

    print(
        f"[MP4 SIZE] {size:,} bytes"
    )

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(FINAL_VIDEO),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "ffprobe failed."
            )

        duration_text = (
            result.stdout.strip()
        )

        duration = float(
            duration_text
        )

        print(
            f"[DURATION] {duration:.2f} seconds"
        )

        if duration < 5:
            raise RuntimeError(
                "Final MP4 is shorter than 5 seconds."
            )

    except ValueError:
        raise RuntimeError(
            "Could not read MP4 duration."
        )

    print()
    print(
        "[SUCCESS] Final MP4 verified:"
    )

    print(
        FINAL_VIDEO
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print(
        f"RIFT VALLEY WATCH "
        f"{VERSION}"
    )
    print("=" * 70)

    print()
    print(
        "Coverage:"
    )

    print(
        "• Rift Valley county news"
    )

    print(
        "• President Ruto political tours"
    )

    print(
        "• President Ruto development tours"
    )

    print(
        "• Major national political developments"
    )

    print(
        "• Major development projects across Kenya"
    )

    print("=" * 70)

    clean_previous()

    candidates = discover()

    if not candidates:
        raise RuntimeError(
            "No usable real news stories were found."
        )

    selected = select_best(
        candidates
    )

    script = build_script(
        selected
    )

    print()
    print("=" * 70)
    print("NARRATION")
    print("=" * 70)

    print(script)

    print("=" * 70)

    save_image(
        selected["image"]
    )

    validate(
        selected,
        script,
    )

    write_files(
        selected,
        script,
    )

    run_generator()

    verify()

    # Only remember the story after the MP4 succeeds.
    story_for_history = {
        "url": selected.get(
            "url",
            "",
        ),
        "title": selected.get(
            "title",
            "",
        ),
        "image_md5": selected.get(
            "image",
            {},
        ).get(
            "md5",
            "",
        ),
        "county": selected.get(
            "county",
            "",
        ),
        "region": selected.get(
            "region",
            "",
        ),
        "story_type": selected.get(
            "story_type",
            "",
        ),
    }

    remember_story(
        story_for_history
    )

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH COMPLETED")
    print("=" * 70)

    print(
        f"FINAL MP4: {FINAL_VIDEO}"
    )

    print(
        f"STORY    : {selected['title']}"
    )

    print(
        f"TYPE     : {selected['story_type']}"
    )

    print(
        f"REGION   : "
        f"{selected['region'] or 'Kenya'}"
    )

    print(
        f"COUNTY   : "
        f"{selected['county'] or 'National'}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
