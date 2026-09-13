from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
from io import BytesIO
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
# RIFT VALLEY WATCH
# MAIN CONTROLLER
# VERSION: V11 ROBUST IMAGE + MP4
# ============================================================

VERSION = "RVW_MAIN_V11_ROBUST"

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"

SELECTED_STORY = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ============================================================
# COUNTIES
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


# ============================================================
# APPROVED PUBLISHERS
# ============================================================

PUBLISHER_PAGES = [
    "https://citizen.digital/",
    "https://www.the-star.co.ke/news/",
    "https://www.kbc.co.ke/",
    "https://nation.africa/kenya/news",
]

APPROVED_DOMAINS = {
    "citizen.digital",
    "the-star.co.ke",
    "kbc.co.ke",
    "nation.africa",
}

BLOCKED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "telegram.me",
    "t.me",
    "whatsapp.com",
    "google.com",
    "news.google.com",
}


# ============================================================
# IMAGE FILTERS
# ============================================================

BAD_IMAGE_TERMS = {
    "googlelogo",
    "google-logo",
    "google-news",
    "google_news",
    "favicon",
    "placeholder",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
    "avatar",
    "sprite",
    "app-icon",
    "app_icon",
}


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ============================================================
# LOGGING
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEXT
# ============================================================

def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = html.unescape(value)
    value = value.replace("\xa0", " ")

    return re.sub(r"\s+", " ", value).strip()


def first_nonempty(*values):
    for value in values:
        text = clean(value)
        if text:
            return text

    return ""


# ============================================================
# URL
# ============================================================

def get_domain(url):
    try:
        return urlparse(url).netloc.lower().split(":")[0].replace(
            "www.",
            "",
        )
    except Exception:
        return ""


def is_blocked(url):
    host = get_domain(url)

    if not host:
        return True

    return any(
        host == blocked
        or host.endswith("." + blocked)
        for blocked in BLOCKED_DOMAINS
    )


def is_approved(url):
    if not url or is_blocked(url):
        return False

    host = get_domain(url)

    return any(
        host == approved
        or host.endswith("." + approved)
        for approved in APPROVED_DOMAINS
    )


def normalize_url(url):
    url = clean(url)

    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url

    if not url.startswith(("http://", "https://")):
        return ""

    return url.split("#")[0].strip()


# ============================================================
# COUNTY DETECTION
# ============================================================

def county_from_text(text):
    text = clean(text).lower()

    best_county = ""
    best_score = 0

    for county, aliases in COUNTIES.items():
        score = 0

        for alias in aliases:
            pattern = r"\b" + re.escape(alias.lower()) + r"\b"

            if re.search(pattern, text):
                score += 1

        if score > best_score:
            best_county = county
            best_score = score

    return best_county


# ============================================================
# HTTP
# ============================================================

def fetch(url):
    try:
        response = SESSION.get(
            url,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:
            log(
                f"HTTP {response.status_code}: {url}"
            )
            return None

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if "html" not in content_type:
            return None

        return response

    except Exception as exc:
        log(
            f"FETCH FAILED: {url} | {exc}"
        )
        return None


# ============================================================
# TITLE
# ============================================================

def clean_title(title):
    title = clean(title)

    publishers = [
        "People Daily",
        "The Star",
        "Citizen Digital",
        "Citizen",
        "The Standard",
        "Daily Nation",
        "Nation",
        "Capital News",
        "KBC",
        "NTV Kenya",
        "TV47",
    ]

    for publisher in publishers:
        title = re.sub(
            r"\s*[-|–—:]\s*"
            + re.escape(publisher)
            + r"\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

    return clean(title)


# ============================================================
# REMOVE SOURCE LANGUAGE
# ============================================================

def remove_source_language(text):
    text = clean(text)

    patterns = [
        r"\baccording to\s+[^.]+",
        r"\breported by\s+[^.]+",
        r"\breport from\s+[^.]+",
        r"\bsource\s*:\s*[^.]+",
        r"\bvia\s+[^.]+",
        r"\bas reported by\s+[^.]+",
        r"\bthe source said\b",
        r"\bthe publisher said\b",
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"\s+([,.])",
        r"\1",
        text,
    )

    return clean(text)


# ============================================================
# REMOVE PUBLISHER NAMES
# WORD-BOUNDARY SAFE
# ============================================================

def remove_metadata(text):
    text = clean(text)

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
        "KBC",
        "NTV Kenya",
        "TV47",
        "Facebook",
        "Instagram",
        "Twitter",
        "YouTube",
        "TikTok",
    ]

    for item in forbidden:
        text = re.sub(
            r"\b" + re.escape(item) + r"\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

    return clean(text)


# ============================================================
# DISCOVER LINKS
# ============================================================

def discover_links(page_url):
    response = fetch(page_url)

    if not response:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    results = []
    seen = set()

    for tag in soup.find_all(
        "a",
        href=True,
    ):
        url = normalize_url(
            urljoin(
                page_url,
                tag.get("href"),
            )
        )

        if not url:
            continue

        if not is_approved(url):
            continue

        if url in seen:
            continue

        seen.add(url)

        text = clean(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        county = county_from_text(
            text + " " + url
        )

        results.append(
            {
                "url": url,
                "text": text,
                "county": county,
            }
        )

    return results


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def add_image_candidate(
    result,
    seen,
    value,
    article_url,
):
    value = clean(value)

    if not value:
        return

    if value.startswith("data:"):
        return

    value = urljoin(
        article_url,
        value,
    )

    value = normalize_url(value)

    if not value:
        return

    lower = value.lower()

    if any(
        term in lower
        for term in BAD_IMAGE_TERMS
    ):
        return

    if value not in seen:
        seen.add(value)
        result.append(value)


def get_image_candidates(
    soup,
    article_url,
):
    result = []
    seen = set()

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    metadata = [
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
    ]

    for attrs in metadata:
        for tag in soup.find_all(
            "meta",
            attrs=attrs,
        ):
            add_image_candidate(
                result,
                seen,
                tag.get("content"),
                article_url,
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    def scan_json(value):
        if isinstance(value, str):
            add_image_candidate(
                result,
                seen,
                value,
                article_url,
            )

        elif isinstance(value, list):
            for item in value:
                scan_json(item)

        elif isinstance(value, dict):
            for key in (
                "image",
                "thumbnailUrl",
                "contentUrl",
            ):
                if key in value:
                    scan_json(value[key])

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        try:
            raw = script.string or script.get_text()

            if not raw:
                continue

            scan_json(
                json.loads(raw)
            )

        except Exception:
            continue

    # --------------------------------------------------------
    # Article images
    # --------------------------------------------------------

    containers = soup.find_all("article")

    if not containers:
        containers = soup.find_all("main")

    if not containers:
        containers = [soup]

    for container in containers:
        for img in container.find_all("img"):
            for key in (
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-original-src",
            ):
                add_image_candidate(
                    result,
                    seen,
                    img.get(key),
                    article_url,
                )

            srcset = (
                img.get("srcset")
                or img.get("data-srcset")
            )

            if srcset:
                for item in srcset.split(","):
                    candidate = item.strip().split(" ")[0]

                    add_image_candidate(
                        result,
                        seen,
                        candidate,
                        article_url,
                    )

    return result


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    image_url,
    article_url,
):
    image_url = normalize_url(image_url)

    if not image_url:
        return None

    lower = image_url.lower()

    if any(
        term in lower
        for term in BAD_IMAGE_TERMS
    ):
        return None

    headers = {
        **HEADERS,
        "Accept": (
            "image/avif,image/webp,"
            "image/apng,image/svg+xml,"
            "image/*,*/*;q=0.8"
        ),
        "Referer": article_url,
    }

    try:
        response = SESSION.get(
            image_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if len(response.content) < 20000:
            return None

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        try:
            image = Image.open(
                BytesIO(response.content)
            )

            image.load()

        except Exception:
            return None

        if image.width < 400:
            return None

        if image.height < 250:
            return None

        if image.width * image.height < 150000:
            return None

        return {
            "image": image.copy(),
            "md5": hashlib.md5(
                response.content
            ).hexdigest(),
            "url": image_url,
            "width": image.width,
            "height": image.height,
            "content_type": content_type,
        }

    except Exception:
        return None


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(url):
    response = fetch(url)

    if not response:
        return None

    final_url = normalize_url(
        response.url
    )

    if not is_approved(final_url):
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = ""

    for attrs in (
        {"property": "og:title"},
        {"name": "twitter:title"},
    ):
        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:
            title = clean(
                tag.get("content")
            )

            if title:
                break

    if not title:
        h1 = soup.find("h1")

        if h1:
            title = clean(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

    if not title and soup.title:
        title = clean(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    title = clean_title(title)

    if len(title) < 12:
        return None

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = ""

    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ):
        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:
            summary = clean(
                tag.get("content")
            )

            if summary:
                break

    summary = remove_metadata(
        summary
    )

    # --------------------------------------------------------
    # BODY
    # --------------------------------------------------------

    paragraphs = []

    container = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if container:
        for paragraph in container.find_all("p"):
            text = clean(
                paragraph.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) < 35:
                continue

            lower = text.lower()

            junk = [
                "subscribe",
                "newsletter",
                "follow us",
                "privacy policy",
                "cookie policy",
                "terms and conditions",
                "advertisement",
                "download our app",
                "google news",
            ]

            if any(
                item in lower
                for item in junk
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    body = clean(
        " ".join(
            paragraphs[:20]
        )
    )

    body = remove_metadata(body)

    if len(body.split()) < 50:
        return None

    # --------------------------------------------------------
    # COUNTY
    # --------------------------------------------------------

    county = county_from_text(
        " ".join(
            [
                title,
                summary,
                body,
            ]
        )
    )

    if not county:
        return None

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image = None

    candidates = get_image_candidates(
        soup,
        final_url,
    )

    for image_url in candidates[:50]:
        image = download_image(
            image_url,
            final_url,
        )

        if image:
            break

    if not image:
        return None

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    published = ""

    date_selectors = [
        {"property": "article:published_time"},
        {"property": "og:published_time"},
        {"name": "date"},
        {"name": "publish-date"},
        {"itemprop": "datePublished"},
    ]

    for attrs in date_selectors:
        tag = soup.find(
            "meta",
            attrs=attrs,
        )

        if tag:
            published = clean(
                tag.get("content")
            )

            if published:
                break

    if not published:
        tag = soup.find(
            attrs={
                "itemprop": "datePublished"
            }
        )

        if tag:
            published = clean(
                tag.get("content")
                or tag.get_text(
                    " ",
                    strip=True,
                )
            )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    words = len(
        body.split()
    )

    score = 0

    if words >= 300:
        score += 50
    elif words >= 200:
        score += 42
    elif words >= 150:
        score += 34
    elif words >= 100:
        score += 25
    elif words >= 70:
        score += 15
    else:
        score -= 20

    useful_terms = [
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
        "development",
        "construction",
        "funding",
        "budget",
        "education",
        "transport",
        "infrastructure",
        "residents",
        "county",
        "government",
    ]

    combined = (
        f"{title} {summary} {body}"
    ).lower()

    for term in useful_terms:
        if re.search(
            r"\b"
            + re.escape(term)
            + r"\b",
            combined,
        ):
            score += 2

    political_terms = [
        "president",
        "deputy president",
        "governor",
        "senator",
        "mp",
        "member of parliament",
        "government",
    ]

    for term in political_terms:
        if re.search(
            r"\b"
            + re.escape(term)
            + r"\b",
            combined,
        ):
            score += 1

    low_value_terms = [
        "dance",
        "chants",
        "crowd goes wild",
        "crowd erupts",
    ]

    for term in low_value_terms:
        if term in combined:
            score -= 8

    # Prefer dated articles.
    if published:
        score += 8

    return {
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "url": final_url,
        "image": image,
        "published": published,
        "score": score,
    }


# ============================================================
# SCRIPT
# ============================================================

def build_script(article):
    county = clean(
        article["county"]
    )

    title = clean_title(
        article["title"]
    )

    summary = remove_metadata(
        article["summary"]
    )

    body = remove_metadata(
        article["body"]
    )

    parts = [
        f"Here is the latest development from {county}.",
        f"{title}.",
    ]

    if summary:
        parts.append(summary)

    sentences = re.split(
        r"(?<=[.!?])\s+",
        body,
    )

    for sentence in sentences:
        sentence = remove_metadata(
            sentence
        )

        if len(sentence) < 35:
            continue

        if sentence.lower() == title.lower():
            continue

        candidate = " ".join(
            parts + [sentence]
        )

        if len(candidate.split()) > 135:
            break

        parts.append(sentence)

        if len(
            " ".join(parts).split()
        ) >= 85:
            break

    script = remove_source_language(
        " ".join(parts)
    )

    script = remove_metadata(
        script
    )

    words = len(
        script.split()
    )

    if words < 70:
        return ""

    return script


# ============================================================
# SAVE IMAGE
# ============================================================

def save_image(image_info):
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_IMAGE.exists():
        FINAL_IMAGE.unlink()

    image = image_info["image"]

    image = image.convert("RGB")

    image.save(
        FINAL_IMAGE,
        "JPEG",
        quality=95,
        optimize=True,
    )

    with Image.open(
        FINAL_IMAGE
    ) as check:
        check.load()

        if check.width < 400:
            raise RuntimeError(
                "Saved article image width is too small."
            )

        if check.height < 250:
            raise RuntimeError(
                "Saved article image height is too small."
            )

    return FINAL_IMAGE


# ============================================================
# SELECT BEST
# ============================================================

def select_best(candidates):
    if not candidates:
        raise RuntimeError(
            "No real Rift Valley article with a usable image was found."
        )

    unique = []
    image_hashes = set()
    urls = set()
    titles = set()

    for item in candidates:
        image_hash = item["image"]["md5"]

        title_key = clean(
            item["title"]
        ).lower()

        url_key = item["url"].lower()

        if image_hash in image_hashes:
            continue

        if url_key in urls:
            continue

        if title_key in titles:
            continue

        image_hashes.add(image_hash)
        urls.add(url_key)
        titles.add(title_key)

        unique.append(item)

    if not unique:
        raise RuntimeError(
            "No unique real article was available."
        )

    unique.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return unique[0]


# ============================================================
# DISCOVERY
# ============================================================

def discover():
    candidates = []

    log("")
    log("=" * 70)
    log("DISCOVERING RIFT VALLEY STORIES")
    log("=" * 70)

    for page in PUBLISHER_PAGES:
        publisher = get_domain(page)

        log("")
        log(
            f"CHECKING NEWS PAGE: {publisher}"
        )

        links = discover_links(page)

        log(
            f"DISCOVERED LINKS: {len(links)}"
        )

        links.sort(
            key=lambda item: (
                1 if item["county"] else 0,
                len(item["text"]),
            ),
            reverse=True,
        )

        tested = set()

        for item in links[:60]:
            url = item["url"]

            if url in tested:
                continue

            tested.add(url)

            log(
                f"TESTING: {url}"
            )

            article = extract_article(
                url
            )

            if not article:
                continue

            if not is_approved(
                article["url"]
            ):
                continue

            script = build_script(
                article
            )

            if len(script.split()) < 70:
                log(
                    "SKIPPED: narration too short"
                )
                continue

            article["generated_script"] = script

            candidates.append(
                article
            )

            log(
                f"ACCEPTED: "
                f"{article['county']} | "
                f"{article['title']} | "
                f"SCORE {article['score']}"
            )

            if len(candidates) >= 20:
                return candidates

            time.sleep(0.2)

    return candidates


# ============================================================
# WRITE FILES
# ============================================================

def write_files(article):
    image_path = save_image(
        article["image"]
    )

    script = article.get(
        "generated_script"
    ) or build_script(
        article
    )

    if len(script.split()) < 70:
        raise RuntimeError(
            "Generated narration contains fewer than 70 words."
        )

    story = {
        "title": clean_title(
            article["title"]
        ),
        "county": clean(
            article["county"]
        ),
        "summary": remove_metadata(
            article["summary"]
        ),
        "body": remove_metadata(
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

    selected_script = {
        "title": story["title"],
        "county": story["county"],
        "narration": story["script"],
    }

    save_json(
        SELECTED_STORY,
        story,
    )

    save_json(
        SELECTED_SCRIPT,
        selected_script,
    )

    return story


# ============================================================
# JSON
# ============================================================

def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
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
# VALIDATE STORY
# ============================================================

def validate_story(story):
    title = clean(
        story.get("title")
    )

    county = clean(
        story.get("county")
    )

    image_path = clean(
        story.get("image_path")
    )

    narration = clean(
        story.get("script")
    )

    if not title:
        raise RuntimeError(
            "Story title is missing."
        )

    if not county:
        raise RuntimeError(
            "Story county is missing."
        )

    if not image_path:
        raise RuntimeError(
            "Story image path is missing."
        )

    image_file = (
        ROOT / image_path
    )

    if not image_file.exists():
        raise RuntimeError(
            f"Story image does not exist: {image_file}"
        )

    if len(narration.split()) < 70:
        raise RuntimeError(
            "Narration contains fewer than 70 words."
        )

    # Only reject actual attribution phrases,
    # not ordinary words such as "international".
    forbidden_patterns = [
        r"\bgoogle news\b",
        r"\bpeople daily\b",
        r"\bthe star\b",
        r"\bcitizen digital\b",
        r"\bthe standard\b",
        r"\bdaily nation\b",
        r"\bcapital news\b",
        r"\bntv kenya\b",
        r"\btv47\b",
        r"\bfacebook\b",
        r"\binstagram\b",
        r"\btwitter\b",
        r"\byoutube\b",
        r"\btiktok\b",
    ]

    lower = narration.lower()

    for pattern in forbidden_patterns:
        if re.search(
            pattern,
            lower,
        ):
            raise RuntimeError(
                "Forbidden source metadata found in narration."
            )

    with Image.open(
        image_file
    ) as image:
        image.load()

        if image.width < 400:
            raise RuntimeError(
                "Story image width is too small."
            )

        if image.height < 250:
            raise RuntimeError(
                "Story image height is too small."
            )


# ============================================================
# CLEAN PREVIOUS OUTPUT
# ============================================================

def clean_previous():
    prepare_directories()

    paths = [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
    ]

    for path in paths:
        try:
            if path.exists():
                path.unlink()
                log(
                    f"REMOVED OLD FILE: {path}"
                )
        except Exception as exc:
            raise RuntimeError(
                f"Could not remove old file {path}: {exc}"
            )


# ============================================================
# RUN GENERATOR
# ============================================================

def run_generator():
    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py not found."
        )

    log("")
    log("=" * 70)
    log("STARTING VIDEO GENERATOR")
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
            + str(result.returncode)
        )


# ============================================================
# VERIFY MP4
# ============================================================

def verify():
    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final Rift Valley Watch MP4 was not generated."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(FINAL_VIDEO),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:
        raise RuntimeError(
            "FFprobe failed on final MP4."
        )

    try:
        info = json.loads(
            probe.stdout
        )
    except Exception:
        raise RuntimeError(
            "Could not parse FFprobe output."
        )

    streams = info.get(
        "streams",
        [],
    )

    video_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
    ]

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    if not video_streams:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if not audio_streams:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    video = video_streams[0]

    if video.get("width") != 1080:
        raise RuntimeError(
            f"Video width is {video.get('width')}, expected 1080."
        )

    if video.get("height") != 1920:
        raise RuntimeError(
            f"Video height is {video.get('height')}, expected 1920."
        )

    duration = float(
        info.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
        or 0
    )

    if duration < 5:
        raise RuntimeError(
            "Final MP4 duration is less than 5 seconds."
        )

    log("")
    log("=" * 70)
    log("FINAL VIDEO VERIFIED")
    log("=" * 70)
    log(
        f"FILE: {FINAL_VIDEO}"
    )
    log(
        f"SIZE: {size / (1024 * 1024):.2f} MB"
    )
    log(
        f"DURATION: {duration:.2f}s"
    )
    log(
        "VIDEO: 1080x1920"
    )
    log(
        "AUDIO: PRESENT"
    )
    log(
        "MP4 QC PASSED"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    prepare_directories()

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH")
    log("=" * 70)
    log(
        f"VERSION: {VERSION}"
    )
    log(
        "ONE STORY / ONE REAL IMAGE / NO SOURCE"
    )
    log("=" * 70)

    clean_previous()

    candidates = discover()

    log("")
    log(
        f"VALID STORIES FOUND: {len(candidates)}"
    )

    selected = select_best(
        candidates
    )

    log("")
    log("=" * 70)
    log("SELECTED STORY")
    log("=" * 70)
    log(
        f"COUNTY: {selected['county']}"
    )
    log(
        f"TITLE: {selected['title']}"
    )
    log(
        f"SCORE: {selected['score']}"
    )

    story = write_files(
        selected
    )

    validate_story(
        story
    )

    log("")
    log(
        f"NARRATION WORDS: "
        f"{len(story['script'].split())}"
    )

    log(
        f"IMAGE: {story['image_path']}"
    )

    run_generator()

    verify()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH COMPLETED SUCCESSFULLY")
    log("=" * 70)


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log(
            f"ERROR: {exc}"
        )
        log("=" * 70)
        raise
