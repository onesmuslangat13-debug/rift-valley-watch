import os
import re
import sys
import json
import time
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# MAIN STORY SELECTION ENGINE
# ============================================================

VERSION = "RVW_MAIN_V18_SYNTAX_FIXED"

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_WORK_DIR = ASSETS_DIR / "video_work"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"
HISTORY_FILE = DATA_DIR / "story_history.json"

FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

GENERATOR_FILE = BASE_DIR / "rift_valley_video_generator.py"

REQUEST_TIMEOUT = 25
IMAGE_TIMEOUT = 25

MIN_ARTICLE_WORDS = 35
MIN_SCRIPT_WORDS = 45
MAX_SCRIPT_WORDS = 145

MAX_CANDIDATES_PER_SOURCE = 25
MAX_TOTAL_CANDIDATES = 120

MAX_IMAGE_BYTES = 12 * 1024 * 1024


# ============================================================
# DIRECTORIES
# ============================================================

for directory in [
    DATA_DIR,
    ASSETS_DIR,
    SOURCE_DIR,
    AUDIO_DIR,
    VIDEO_WORK_DIR,
    OUTPUT_DIR,
]:
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
    }
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
    "bomet": [
        "bomet",
        "sotik",
        "chepalungu",
        "konoin",
        "chebunyo",
    ],
    "kericho": [
        "kericho",
        "litein",
        "ainamoi",
        "belgut",
        "kipkelion",
        "sigowet",
        "soin",
    ],
    "nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "subukia",
        "bahati",
        "rongai",
    ],
    "nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "aldai",
        "chesumei",
        "emgwen",
    ],
    "uasin gishu": [
        "uasin gishu",
        "eldoret",
        "ainabkoi",
        "kapseret",
        "kesses",
        "moiben",
        "soy",
        "turbo",
    ],
    "elgeyo-marakwet": [
        "elgeyo",
        "marakwet",
        "iten",
        "keiyo",
        "kapsowar",
        "tambach",
    ],
    "west pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "sigor",
        "kacheliba",
        "pokot south",
    ],
    "narok": [
        "narok",
        "kilgoris",
        "transmara",
        "ololulunga",
        "suswa",
        "mara",
    ],
}


# ============================================================
# APPROVED SOURCES
# ============================================================

APPROVED_PUBLISHERS = [
    {
        "name": "Citizen Digital",
        "base_url": "https://citizen.digital/",
        "domain": "citizen.digital",
        "sections": [
            "https://citizen.digital/news",
            "https://citizen.digital/kenya",
            "https://citizen.digital/business",
        ],
    },
    {
        "name": "The Star",
        "base_url": "https://www.the-star.co.ke/",
        "domain": "the-star.co.ke",
        "sections": [
            "https://www.the-star.co.ke/news/",
            "https://www.the-star.co.ke/counties/",
            "https://www.the-star.co.ke/business/",
        ],
    },
    {
        "name": "KBC",
        "base_url": "https://www.kbc.co.ke/",
        "domain": "kbc.co.ke",
        "sections": [
            "https://www.kbc.co.ke/category/news/",
            "https://www.kbc.co.ke/category/counties/",
            "https://www.kbc.co.ke/category/national/",
        ],
    },
    {
        "name": "Nation Africa",
        "base_url": "https://nation.africa/kenya",
        "domain": "nation.africa",
        "sections": [
            "https://nation.africa/kenya/news",
            "https://nation.africa/kenya/counties",
            "https://nation.africa/kenya/business",
        ],
    },
]


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
# TERMS
# ============================================================

RUTO_TERMS = [
    "william ruto",
    "president ruto",
    "president william ruto",
    "ruto",
    "state house",
    "presidency",
    "presidential",
]

DEVELOPMENT_TERMS = [
    "road",
    "roads",
    "highway",
    "hospital",
    "health",
    "school",
    "university",
    "water",
    "irrigation",
    "dam",
    "electricity",
    "power",
    "housing",
    "market",
    "bridge",
    "railway",
    "airport",
    "infrastructure",
    "development",
    "project",
    "launch",
    "opened",
    "commissioned",
    "construction",
    "funding",
    "investment",
]

POLITICAL_TERMS = [
    "election",
    "2027",
    "campaign",
    "opposition",
    "government",
    "parliament",
    "mp",
    "senator",
    "governor",
    "deputy president",
    "president",
    "party",
    "politics",
    "political",
]

URGENT_TERMS = [
    "breaking",
    "latest",
    "today",
    "new",
    "alert",
    "death",
    "dead",
    "killed",
    "arrested",
    "arrest",
    "missing",
    "accident",
    "crash",
    "fire",
    "flood",
    "evacuated",
    "hospital",
    "court",
    "charged",
    "rescue",
]

LOW_VALUE_TERMS = [
    "opinion",
    "editorial",
    "lifestyle",
    "horoscope",
    "entertainment",
    "sports",
    "football",
    "celebrity",
    "gossip",
    "video:",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def word_count(text):
    return len(
        re.findall(
            r"\b[\w’'-]+\b",
            text or "",
        )
    )


def text_key(text):
    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def sentence_key(sentence):
    return text_key(sentence)


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        clean_text(part)
        for part in parts
        if clean_text(part)
    ]


def normalize_title(title):
    title = clean_text(title)

    title = re.sub(
        r"\s*[-|]\s*(Citizen Digital|The Star|KBC|Nation Africa)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip()


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


def domain_of(url):
    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )
    except Exception:
        return ""


def is_blocked_url(url):
    domain = domain_of(url)

    if not domain:
        return True

    if domain in BLOCKED_DOMAINS:
        return True

    for blocked in BLOCKED_DOMAINS:
        if domain.endswith("." + blocked):
            return True

    return False


def is_approved_url(url):
    domain = domain_of(url)

    if not domain:
        return False

    if is_blocked_url(url):
        return False

    for publisher in APPROVED_PUBLISHERS:
        approved_domain = publisher["domain"]

        if (
            domain == approved_domain
            or domain.endswith("." + approved_domain)
        ):
            return True

    return False


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path, default=None):
    path = Path(path)

    if not path.exists():
        return default

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)

    except Exception:
        return default


def save_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(path)


# ============================================================
# HISTORY
# ============================================================

def load_history():
    history = load_json(
        HISTORY_FILE,
        default=[],
    )

    if not isinstance(history, list):
        return []

    return history


def story_identifier(article):
    raw = (
        article.get("url", "")
        + "|"
        + article.get("title", "")
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()


def history_contains(article, history):
    identifier = story_identifier(article)

    for item in history:
        if not isinstance(item, dict):
            continue

        if item.get("id") == identifier:
            return True

        if (
            item.get("url")
            and item.get("url") == article.get("url")
        ):
            return True

    return False


def add_to_history(article):
    history = load_history()

    identifier = story_identifier(article)

    history = [
        item
        for item in history
        if not (
            isinstance(item, dict)
            and item.get("id") == identifier
        )
    ]

    history.insert(
        0,
        {
            "id": identifier,
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "county": article.get("county", ""),
            "published": article.get(
                "published",
                "",
            ),
            "timestamp": int(time.time()),
        },
    )

    save_json(
        HISTORY_FILE,
        history[:100],
    )


# ============================================================
# FETCH
# ============================================================

def fetch_url(url):
    try:
        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if not response.content:
            return None

        return response

    except Exception as exc:
        print(
            f"[FETCH] Failed: {url} | {exc}"
        )

        return None


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    text_lower = clean_text(text).lower()

    best_county = ""
    best_hits = 0

    for county, aliases in COUNTY_ALIASES.items():
        hits = 0

        for alias in aliases:
            if alias.lower() in text_lower:
                hits += 1

        if hits > best_hits:
            best_hits = hits
            best_county = county

    if best_county:
        return best_county.title()

    return ""


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def valid_image_url(url):
    if not url:
        return False

    url = normalize_url(url)

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return False

    if is_blocked_url(url):
        return False

    return True


def image_candidates_from_html(
    html,
    page_url,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = []

    for meta in soup.find_all("meta"):
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

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:
            candidates.append(
                urljoin(
                    page_url,
                    content,
                )
            )

    for link in soup.find_all("link"):
        rel = " ".join(
            link.get("rel", [])
        ).lower()

        href = (
            link.get("href")
            or ""
        ).strip()

        if (
            href
            and "image_src" in rel
        ):
            candidates.append(
                urljoin(
                    page_url,
                    href,
                )
            )

    for img in soup.find_all("img"):
        values = [
            img.get("src"),
            img.get("data-src"),
            img.get("data-lazy-src"),
            img.get("data-original"),
        ]

        srcset = img.get("srcset")

        if srcset:
            first = srcset.split(",")[0].strip()

            if first:
                values.append(
                    first.split(" ")[0]
                )

        for value in values:
            if not value:
                continue

            candidates.append(
                urljoin(
                    page_url,
                    value,
                )
            )

    unique = []
    seen = set()

    for candidate in candidates:
        candidate = normalize_url(candidate)

        if not valid_image_url(candidate):
            continue

        if candidate in seen:
            continue

        seen.add(candidate)

        unique.append(candidate)

    return unique


def download_image(
    url,
    destination,
):
    try:
        response = SESSION.get(
            url,
            timeout=IMAGE_TIMEOUT,
            stream=True,
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
            "image" not in content_type
            and not url.lower().split("?")[0].endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".avif",
                )
            )
        ):
            return False

        temporary = Path(
            str(destination) + ".tmp"
        )

        total = 0

        with temporary.open("wb") as handle:
            for chunk in response.iter_content(
                chunk_size=65536
            ):
                if not chunk:
                    continue

                total += len(chunk)

                if total > MAX_IMAGE_BYTES:
                    temporary.unlink(
                        missing_ok=True
                    )

                    return False

                handle.write(chunk)

        try:
            with Image.open(
                temporary
            ) as image:
                image.verify()

        except Exception:
            temporary.unlink(
                missing_ok=True
            )

            return False

        temporary.replace(destination)

        return True

    except Exception as exc:
        print(
            f"[IMAGE] Failed: {url} | {exc}"
        )

        try:
            Path(
                str(destination) + ".tmp"
            ).unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return False


def download_article_image(
    article,
    html,
):
    urls = image_candidates_from_html(
        html,
        article.get("url", ""),
    )

    if not urls:
        return False

    FINAL_IMAGE.unlink(
        missing_ok=True
    )

    for index, image_url in enumerate(
        urls[:20],
        start=1,
    ):
        print(
            f"[IMAGE] Trying image {index}: "
            f"{image_url}"
        )

        if download_image(
            image_url,
            FINAL_IMAGE,
        ):
            try:
                with Image.open(
                    FINAL_IMAGE
                ) as image:
                    width, height = image.size

                    if width < 300 or height < 200:
                        FINAL_IMAGE.unlink(
                            missing_ok=True
                        )

                        continue

                    print(
                        "[IMAGE] Valid article image "
                        f"selected: {width}x{height}"
                    )

                    return True

            except Exception:
                FINAL_IMAGE.unlink(
                    missing_ok=True
                )

    return False


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article_text(soup):
    paragraphs = []

    article_container = (
        soup.find("article")
        or soup.find("main")
        or soup
    )

    for element in article_container.find_all(
        [
            "p",
            "h2",
            "h3",
        ]
    ):
        text = clean_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        if len(text) < 25:
            continue

        paragraphs.append(text)

    result = []
    seen = set()

    for paragraph in paragraphs:
        key = text_key(paragraph)

        if key in seen:
            continue

        seen.add(key)
        result.append(paragraph)

    return " ".join(result)


def extract_meta_description(soup):
    for name in [
        "description",
        "og:description",
        "twitter:description",
    ]:
        meta = soup.find(
            "meta",
            attrs={
                "name": name,
            },
        )

        if not meta:
            meta = soup.find(
                "meta",
                attrs={
                    "property": name,
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

    return ""


def extract_published_date(soup):
    candidates = []

    for meta in soup.find_all("meta"):
        key = (
            meta.get("property")
            or meta.get("name")
            or meta.get("itemprop")
            or ""
        ).lower()

        value = (
            meta.get("content")
            or ""
        ).strip()

        if not value:
            continue

        if any(
            term in key
            for term in [
                "published",
                "datepublished",
                "article:published",
                "date",
            ]
        ):
            candidates.append(value)

    time_tag = soup.find("time")

    if time_tag:
        candidates.append(
            time_tag.get(
                "datetime",
                "",
            )
        )

        candidates.append(
            time_tag.get_text(
                " ",
                strip=True,
            )
        )

    for value in candidates:
        value = clean_text(value)

        if value:
            return value

    return ""


def parse_article(
    url,
    publisher,
):
    response = fetch_url(url)

    if response is None:
        return None

    final_url = response.url

    if not is_approved_url(final_url):
        return None

    soup = BeautifulSoup(
        response.content,
        "html.parser",
    )

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

    if not title:
        title_tag = soup.find("h1")

        if title_tag:
            title = clean_text(
                title_tag.get_text(
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

    article_text = extract_article_text(soup)

    meta_description = extract_meta_description(soup)

    combined_text = clean_text(
        title
        + " "
        + meta_description
        + " "
        + article_text
    )

    if word_count(article_text) < MIN_ARTICLE_WORDS:
        if word_count(combined_text) < MIN_ARTICLE_WORDS:
            return None

    county = detect_county(combined_text)

    if not county:
        return None

    image_urls = image_candidates_from_html(
        response.text,
        final_url,
    )

    return {
        "title": title,
        "url": final_url,
        "publisher": publisher.get(
            "name",
            "",
        ),
        "domain": publisher.get(
            "domain",
            "",
        ),
        "county": county,
        "published": extract_published_date(soup),
        "description": meta_description,
        "text": article_text,
        "image_urls": image_urls,
    }


# ============================================================
# LINK COLLECTION
# ============================================================

def looks_like_article_link(
    url,
    anchor_text="",
):
    if not is_approved_url(url):
        return False

    path = (
        urlparse(url)
        .path
        .lower()
    )

    text = clean_text(anchor_text).lower()

    if len(text) < 15:
        return False

    if path in {
        "",
        "/",
        "/news",
        "/kenya/news",
        "/counties",
        "/business",
    }:
        return False

    blocked_path_terms = [
        "/video",
        "/videos",
        "/podcast",
        "/sports",
        "/entertainment",
        "/lifestyle",
        "/opinion",
        "/cartoon",
        "/author/",
        "/tag/",
        "/search",
    ]

    for term in blocked_path_terms:
        if term in path:
            return False

    return True


def collect_links_from_page(page_url):
    response = fetch_url(page_url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.content,
        "html.parser",
    )

    links = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href = anchor.get(
            "href",
            "",
        ).strip()

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not href:
            continue

        absolute = urljoin(
            page_url,
            href,
        )

        absolute = absolute.split("#")[0]

        if not looks_like_article_link(
            absolute,
            text,
        ):
            continue

        links.append(
            {
                "url": absolute,
                "anchor_text": text,
            }
        )

    unique = []
    seen = set()

    for item in links:
        url = item["url"]

        if url in seen:
            continue

        seen.add(url)
        unique.append(item)

    return unique


# ============================================================
# RSS
# ============================================================

def collect_rss_candidates(publisher):
    candidates = []

    rss_urls = [
        publisher["base_url"] + "feed/",
        publisher["base_url"] + "feed",
        publisher["base_url"] + "rss",
    ]

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)

            if not feed.entries:
                continue

            for entry in feed.entries[
                :MAX_CANDIDATES_PER_SOURCE
            ]:
                link = entry.get(
                    "link",
                    "",
                )

                title = clean_text(
                    entry.get(
                        "title",
                        "",
                    )
                )

                if not link or not title:
                    continue

                if not is_approved_url(link):
                    continue

                candidates.append(
                    {
                        "url": link,
                        "anchor_text": title,
                    }
                )

            if candidates:
                break

        except Exception as exc:
            print(
                f"[RSS] {publisher['name']} failed: {exc}"
            )

    return candidates


# ============================================================
# DISCOVERY
# ============================================================

def discover_candidate_urls():
    all_candidates = []
    seen = set()

    for publisher in APPROVED_PUBLISHERS:
        print()
        print("=" * 70)
        print(
            f"COLLECTING: {publisher['name']}"
        )
        print("=" * 70)

        source_candidates = []

        source_candidates.extend(
            collect_rss_candidates(
                publisher
            )
        )

        for section in publisher["sections"]:
            if len(source_candidates) >= MAX_CANDIDATES_PER_SOURCE:
                break

            try:
                links = collect_links_from_page(
                    section
                )

                source_candidates.extend(
                    links[:MAX_CANDIDATES_PER_SOURCE]
                )

            except Exception as exc:
                print(
                    f"[LINKS] Failed {section}: {exc}"
                )

        local_seen = set()

        for candidate in source_candidates:
            url = candidate.get(
                "url",
                "",
            )

            if not url:
                continue

            if url in local_seen:
                continue

            local_seen.add(url)

            if url in seen:
                continue

            seen.add(url)

            all_candidates.append(
                {
                    "url": url,
                    "anchor_text": candidate.get(
                        "anchor_text",
                        "",
                    ),
                    "publisher": publisher,
                }
            )

            if len(all_candidates) >= MAX_TOTAL_CANDIDATES:
                break

        if len(all_candidates) >= MAX_TOTAL_CANDIDATES:
            break

    print()
    print(
        f"[DISCOVERY] Candidate URLs found: "
        f"{len(all_candidates)}"
    )

    return all_candidates


# ============================================================
# RELEVANCE
# ============================================================

def relevance_score(article):
    title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    text = clean_text(
        article.get(
            "text",
            "",
        )
    )

    county = clean_text(
        article.get(
            "county",
            "",
        )
    )

    combined = (
        title
        + " "
        + text
    ).lower()

    score = 0

    if county:
        score += 35

    for item in COUNTIES:
        if item.lower() in combined:
            score += 10

    for term in RUTO_TERMS:
        if term in combined:
            score += 15

    development_hits = sum(
        1
        for term in DEVELOPMENT_TERMS
        if term in combined
    )

    score += min(
        development_hits * 4,
        24,
    )

    political_hits = sum(
        1
        for term in POLITICAL_TERMS
        if term in combined
    )

    score += min(
        political_hits * 3,
        18,
    )

    urgent_hits = sum(
        1
        for term in URGENT_TERMS
        if term in combined
    )

    score += min(
        urgent_hits * 5,
        25,
    )

    title_lower = title.lower()

    for term in (
        RUTO_TERMS
        + URGENT_TERMS
        + DEVELOPMENT_TERMS
    ):
        if term in title_lower:
            score += 7

    article_words = word_count(text)

    if article_words >= 150:
        score += 10
    elif article_words >= 100:
        score += 7
    elif article_words >= 60:
        score += 4

    if article.get("image_urls"):
        score += 15

    for term in LOW_VALUE_TERMS:
        if term in title_lower:
            score -= 50

    if len(title) < 30:
        score -= 15

    return score


def is_relevant_story(article):
    title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    text = clean_text(
        article.get(
            "text",
            "",
        )
    )

    if not title:
        return False

    if not article.get("url"):
        return False

    if not is_approved_url(
        article.get(
            "url",
            "",
        )
    ):
        return False

    if word_count(text) < MIN_ARTICLE_WORDS:
        return False

    county = article.get(
        "county",
        "",
    )

    if not county:
        return False

    combined = (
        title
        + " "
        + text
    ).lower()

    county_match = False

    for aliases in COUNTY_ALIASES.values():
        for alias in aliases:
            if alias.lower() in combined:
                county_match = True
                break

        if county_match:
            break

    ruto_match = any(
        term in combined
        for term in RUTO_TERMS
    )

    if not county_match and not ruto_match:
        return False

    title_lower = title.lower()

    for term in LOW_VALUE_TERMS:
        if term in title_lower:
            return False

    return True


# ============================================================
# NARRATION
# ============================================================

def clean_for_narration(text):
    text = clean_text(text)

    text = re.sub(
        r"\b(read more|click here|subscribe|share this story)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"@\w+",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def first_useful_sentences(
    article,
    max_sentences=8,
):
    title = clean_for_narration(
        article.get(
            "title",
            "",
        )
    )

    description = clean_for_narration(
        article.get(
            "description",
            "",
        )
    )

    article_text = clean_for_narration(
        article.get(
            "text",
            "",
        )
    )

    sentences = []

    if title:
        sentences.append(
            title.rstrip(".!?") + "."
        )

    for source in [
        description,
        article_text,
    ]:
        if not source:
            continue

        for sentence in split_sentences(source):
            sentence = clean_for_narration(
                sentence
            )

            if word_count(sentence) < 5:
                continue

            key = sentence_key(sentence)

            if not key:
                continue

            if any(
                sentence_key(existing) == key
                for existing in sentences
            ):
                continue

            sentences.append(sentence)

            if len(sentences) >= max_sentences:
                return sentences

    return sentences


def build_narration(article):
    title = clean_for_narration(
        article.get(
            "title",
            "",
        )
    )

    county = clean_for_narration(
        article.get(
            "county",
            "",
        )
    )

    sentences = first_useful_sentences(
        article,
        max_sentences=10,
    )

    if not sentences:
        raise RuntimeError(
            "Could not build narration."
        )

    body = []

    for sentence in sentences:
        sentence = clean_for_narration(
            sentence
        )

        if not sentence:
            continue

        if (
            title
            and sentence_key(sentence)
            == sentence_key(title + ".")
        ):
            if not body:
                body.append(sentence)

            continue

        body.append(sentence)

    script = " ".join(body)

    script = clean_for_narration(script)

    if (
        county
        and county.lower()
        not in script.lower()[:180]
    ):
        script = (
            f"In {county}, "
            + script
        )

    words = script.split()

    if len(words) > MAX_SCRIPT_WORDS:
        trimmed = []
        count = 0

        for sentence in split_sentences(script):
            sentence_words = sentence.split()

            if (
                count
                + len(sentence_words)
                > MAX_SCRIPT_WORDS
            ):
                break

            trimmed.append(sentence)
            count += len(sentence_words)

        script = " ".join(trimmed)

    if word_count(script) < MIN_SCRIPT_WORDS:
        additional = clean_for_narration(
            article.get(
                "text",
                "",
            )
        )

        existing_keys = {
            sentence_key(sentence)
            for sentence in split_sentences(script)
        }

        for sentence in split_sentences(additional):
            if sentence_key(sentence) in existing_keys:
                continue

            candidate = clean_text(
                script
                + " "
                + sentence
            )

            if word_count(candidate) > MAX_SCRIPT_WORDS:
                break

            script = candidate

            if word_count(script) >= MIN_SCRIPT_WORDS:
                break

    return clean_text(script)


# ============================================================
# STORY TYPE
# ============================================================

def determine_story_type(article):
    combined = (
        clean_text(
            article.get(
                "title",
                "",
            )
        )
        + " "
        + clean_text(
            article.get(
                "text",
                "",
            )
        )
    ).lower()

    if any(
        term in combined
        for term in [
            "accident",
            "crash",
            "fire",
            "flood",
            "killed",
            "dead",
            "missing",
            "arrested",
            "arrest",
            "rescue",
            "evacuated",
        ]
    ):
        return "Breaking News"

    if any(
        term in combined
        for term in RUTO_TERMS
    ):
        return "National & Regional Affairs"

    if any(
        term in combined
        for term in DEVELOPMENT_TERMS
    ):
        return "Development"

    if any(
        term in combined
        for term in POLITICAL_TERMS
    ):
        return "Politics & Public Affairs"

    return "Rift Valley News"


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

    if not article.get("story_type"):
        raise RuntimeError(
            "Story type is missing."
        )

    if word_count(script) < 45:
        raise RuntimeError(
            "Narration contains fewer than 45 words."
        )

    if not FINAL_IMAGE.exists():
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

    forbidden_attribution_patterns = [
        r"\baccording to nation africa\b",
        r"\baccording to daily nation\b",
        r"\bnation africa reports\b",
        r"\bdaily nation reports\b",
        r"\breported by nation africa\b",
        r"\breported by daily nation\b",

        r"\baccording to citizen digital\b",
        r"\bcitizen digital reports\b",
        r"\breported by citizen digital\b",

        r"\baccording to the star\b",
        r"\bthe star reports\b",
        r"\breported by the star\b",

        r"\baccording to kbc\b",
        r"\bkbc reports\b",
        r"\breported by kbc\b",

        r"\baccording to people daily\b",
        r"\bpeople daily reports\b",
        r"\breported by people daily\b",

        r"\baccording to standard media\b",
        r"\bstandard media reports\b",
        r"\breported by standard media\b",

        r"\baccording to capital news\b",
        r"\bcapital news reports\b",
        r"\breported by capital news\b",

        r"\baccording to ntv\b",
        r"\bntv reports\b",
        r"\breported by ntv\b",

        r"\baccording to tv47\b",
        r"\btv47 reports\b",
        r"\breported by tv47\b",
    ]

    for pattern in forbidden_attribution_patterns:
        if re.search(
            pattern,
            script_lower,
            flags=re.IGNORECASE,
        ):
            raise RuntimeError(
                "Publisher attribution detected "
                "in narration."
            )

    sentences = split_sentences(
        script
    )

    seen = set()

    for sentence in sentences:
        key = sentence_key(
            sentence
        )

        if not key:
            continue

        if key in seen:
            raise RuntimeError(
                "Repeated sentence detected."
            )

        seen.add(key)

    print(
        "[VALIDATION] Story and narration passed."
    )


# ============================================================
# PROCESS CANDIDATE
# ============================================================

def process_candidate(candidate):
    url = candidate.get(
        "url",
        "",
    )

    publisher = candidate.get(
        "publisher",
        {},
    )

    print()
    print("-" * 70)
    print(
        f"[CANDIDATE] {url}"
    )
    print("-" * 70)

    if not is_approved_url(url):
        print(
            "[SKIP] Domain not approved."
        )
        return None

    response = fetch_url(url)

    if response is None:
        print(
            "[SKIP] Article could not be fetched."
        )
        return None

    article = parse_article(
        response.url,
        publisher,
    )

    if not article:
        print(
            "[SKIP] Could not parse article."
        )
        return None

    if not is_relevant_story(article):
        print(
            "[SKIP] Article is not relevant."
        )
        return None

    article["score"] = relevance_score(
        article
    )

    article["story_type"] = determine_story_type(
        article
    )

    if history_contains(
        article,
        load_history(),
    ):
        print(
            "[SKIP] Story already used."
        )
        return None

    try:
        script = build_narration(
            article
        )
    except Exception as exc:
        print(
            f"[SKIP] Narration failed: {exc}"
        )
        return None

    if word_count(script) < MIN_SCRIPT_WORDS:
        print(
            "[SKIP] Narration too short."
        )
        return None

    FINAL_IMAGE.unlink(
        missing_ok=True
    )

    if not download_article_image(
        article,
        response.text,
    ):
        print(
            "[SKIP] Could not download a valid "
            "article image."
        )
        return None

    try:
        validate(
            article,
            script,
        )

    except Exception as exc:
        print(
            f"[SKIP] Validation failed: {exc}"
        )

        FINAL_IMAGE.unlink(
            missing_ok=True
        )

        return None

    print()
    print("=" * 70)
    print("[CANDIDATE ACCEPTED]")
    print("=" * 70)
    print(
        f"HEADLINE: {article['title']}"
    )
    print(
        f"COUNTY: {article['county']}"
    )
    print(
        f"TYPE: {article['story_type']}"
    )
    print(
        f"SCORE: {article['score']}"
    )
    print(
        f"WORDS: {word_count(script)}"
    )
    print("=" * 70)

    article["script"] = script

    return article


# ============================================================
# SAVE SELECTED STORY
# ============================================================

def save_selected_story(article):
    story_data = {
        "title": article.get(
            "title",
            "",
        ),
        "url": article.get(
            "url",
            "",
        ),
        "publisher": article.get(
            "publisher",
            "",
        ),
        "domain": article.get(
            "domain",
            "",
        ),
        "county": article.get(
            "county",
            "",
        ),
        "published": article.get(
            "published",
            "",
        ),
        "description": article.get(
            "description",
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
        "image_urls": article.get(
            "image_urls",
            [],
        ),
    }

    script_data = {
        "title": article.get(
            "title",
            "",
        ),
        "county": article.get(
            "county",
            "",
        ),
        "story_type": article.get(
            "story_type",
            "",
        ),
        "script": article.get(
            "script",
            "",
        ),
        "word_count": word_count(
            article.get(
                "script",
                "",
            )
        ),
    }

    save_json(
        STORY_FILE,
        story_data,
    )

    save_json(
        SCRIPT_FILE,
        script_data,
    )

    print(
        "[FILES] selected_story.json created."
    )

    print(
        "[FILES] selected_script.json created."
    )

    if not STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json was not generated."
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "selected_script.json was not generated."
        )


# ============================================================
# SELECT STORY
# ============================================================

def select_story():
    candidates = discover_candidate_urls()

    if not candidates:
        raise RuntimeError(
            "No candidate story URLs were discovered."
        )

    history = load_history()

    parsed_candidates = []

    print()
    print("=" * 70)
    print("[STORY SELECTION] Parsing candidates")
    print("=" * 70)

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        url = candidate.get(
            "url",
            "",
        )

        publisher = candidate.get(
            "publisher",
            {},
        )

        print()
        print(
            f"[PARSE {index}/{len(candidates)}] "
            f"{url}"
        )

        if not url:
            continue

        if not is_approved_url(url):
            print(
                "[SKIP] URL is not approved."
            )
            continue

        if history_contains(
            {
                "url": url,
                "title": candidate.get(
                    "anchor_text",
                    "",
                ),
            },
            history,
        ):
            print(
                "[SKIP] Candidate already appears "
                "in history."
            )

        try:
            article = parse_article(
                url,
                publisher,
            )

        except Exception as exc:
            print(
                f"[SKIP] Parse error: {exc}"
            )
            continue

        if not article:
            print(
                "[SKIP] Article could not be parsed."
            )
            continue

        if not is_relevant_story(article):
            print(
                "[SKIP] Article is not relevant."
            )
            continue

        if history_contains(
            article,
            history,
        ):
            print(
                "[SKIP] Story already used."
            )
            continue

        article["score"] = relevance_score(
            article
        )

        article["story_type"] = determine_story_type(
            article
        )

        parsed_candidates.append(
            article
        )

    if not parsed_candidates:
        raise RuntimeError(
            "No relevant unused stories were found."
        )

    parsed_candidates.sort(
        key=lambda item: (
            item.get(
                "score",
                0,
            ),
            word_count(
                item.get(
                    "text",
                    "",
                )
            ),
            len(
                item.get(
                    "image_urls",
                    [],
                )
            ),
        ),
        reverse=True,
    )

    print()
    print("=" * 70)
    print(
        "[STORY SELECTION] Ranked candidates"
    )
    print("=" * 70)

    for index, article in enumerate(
        parsed_candidates[:15],
        start=1,
    ):
        print(
            f"{index}. "
            f"{article.get('score', 0)} | "
            f"{article.get('county', '')} | "
            f"{article.get('title', '')}"
        )

    print("=" * 70)

    print()
    print("=" * 70)
    print(
        "[STORY SELECTION] Testing candidates "
        "for final acceptance"
    )
    print("=" * 70)

    for index, article in enumerate(
        parsed_candidates,
        start=1,
    ):
        print()
        print(
            f"[FINAL TEST {index}/{len(parsed_candidates)}]"
        )
        print(
            article.get(
                "title",
                "",
            )
        )

        FINAL_IMAGE.unlink(
            missing_ok=True
        )

        try:
            response = fetch_url(
                article.get(
                    "url",
                    "",
                )
            )

            if response is None:
                print(
                    "[SKIP] Could not fetch final article."
                )
                continue

            refreshed = parse_article(
                response.url,
                {
                    "name": article.get(
                        "publisher",
                        "",
                    ),
                    "domain": article.get(
                        "domain",
                        "",
                    ),
                },
            )

            if not refreshed:
                print(
                    "[SKIP] Refreshed article could "
                    "not be parsed."
                )
                continue

            refreshed["score"] = relevance_score(
                refreshed
            )

            refreshed["story_type"] = determine_story_type(
                refreshed
            )

            if history_contains(
                refreshed,
                history,
            ):
                print(
                    "[SKIP] Refreshed story is already "
                    "in history."
                )
                continue

            script = build_narration(
                refreshed
            )

            if word_count(script) < MIN_SCRIPT_WORDS:
                print(
                    "[SKIP] Final narration is too short."
                )
                continue

            if not download_article_image(
                refreshed,
                response.text,
            ):
                print(
                    "[SKIP] No valid article image "
                    "could be downloaded."
                )
                continue

            try:
                validate(
                    refreshed,
                    script,
                )

            except Exception as exc:
                print(
                    f"[SKIP] Final validation failed: {exc}"
                )

                FINAL_IMAGE.unlink(
                    missing_ok=True
                )

                continue

            refreshed["script"] = script

            save_selected_story(
                refreshed
            )

            add_to_history(
                refreshed
            )

            print()
            print("=" * 70)
            print("[STORY SELECTED]")
            print("=" * 70)
            print(
                f"HEADLINE: "
                f"{refreshed.get('title', '')}"
            )
            print(
                f"COUNTY: "
                f"{refreshed.get('county', '')}"
            )
            print(
                f"TYPE: "
                f"{refreshed.get('story_type', '')}"
            )
            print(
                f"SCORE: "
                f"{refreshed.get('score', 0)}"
            )
            print(
                f"WORDS: "
                f"{word_count(script)}"
            )
            print(
                f"IMAGE: "
                f"{FINAL_IMAGE}"
            )
            print("=" * 70)

            return refreshed

        except Exception as exc:
            print(
                f"[SKIP] Candidate failed: {exc}"
            )

            FINAL_IMAGE.unlink(
                missing_ok=True
            )

    raise RuntimeError(
        "No candidate passed final story, "
        "image, narration and validation checks."
    )


# ============================================================
# VERIFY SELECTED FILES
# ============================================================

def verify_selected_files():
    print()
    print("=" * 70)
    print("[VERIFY] Checking selected story files")
    print("=" * 70)

    if not STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json was not generated."
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "selected_script.json was not generated."
        )

    if not FINAL_IMAGE.exists():
        raise RuntimeError(
            "story_image.jpg was not generated."
        )

    story = load_json(
        STORY_FILE,
        default=None,
    )

    script_data = load_json(
        SCRIPT_FILE,
        default=None,
    )

    if not isinstance(
        story,
        dict,
    ):
        raise RuntimeError(
            "selected_story.json is not valid JSON."
        )

    if not isinstance(
        script_data,
        dict,
    ):
        raise RuntimeError(
            "selected_script.json is not valid JSON."
        )

    if not story.get("title"):
        raise RuntimeError(
            "Selected story title is missing."
        )

    if not story.get("url"):
        raise RuntimeError(
            "Selected story URL is missing."
        )

    script = script_data.get(
        "script",
        "",
    )

    if word_count(script) < MIN_SCRIPT_WORDS:
        raise RuntimeError(
            "Selected narration is too short."
        )

    try:
        with Image.open(
            FINAL_IMAGE
        ) as image:
            image.verify()

    except Exception as exc:
        raise RuntimeError(
            f"Selected image is invalid: {exc}"
        )

    print(
        "[VERIFY] selected_story.json OK"
    )

    print(
        "[VERIFY] selected_script.json OK"
    )

    print(
        "[VERIFY] story_image.jpg OK"
    )

    print(
        f"[VERIFY] Script words: "
        f"{word_count(script)}"
    )

    print(
        "[VERIFY] All selected files are valid."
    )


# ============================================================
# VIDEO GENERATOR
# ============================================================

def run_video_generator():
    if not GENERATOR_FILE.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py does not exist."
        )

    print()
    print("=" * 70)
    print(
        "[VIDEO] Starting video generator."
    )
    print("=" * 70)

    command = [
        sys.executable,
        "-u",
        str(GENERATOR_FILE),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Video generator failed with "
            f"exit code {result.returncode}."
        )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    if FINAL_VIDEO.stat().st_size < 10000:
        raise RuntimeError(
            "Generated MP4 is unexpectedly small."
        )

    print(
        "[VIDEO] Final MP4 generated successfully."
    )

    print(
        f"[VIDEO] {FINAL_VIDEO}"
    )

    print(
        f"[VIDEO] Size: "
        f"{FINAL_VIDEO.stat().st_size:,} bytes"
    )


# ============================================================
# CLEAN PREVIOUS GENERATED SELECTION
# ============================================================

def clean_previous_selection():
    STORY_FILE.unlink(
        missing_ok=True
    )

    SCRIPT_FILE.unlink(
        missing_ok=True
    )

    FINAL_IMAGE.unlink(
        missing_ok=True
    )

    FINAL_VIDEO.unlink(
        missing_ok=True
    )

    print(
        "[CLEAN] Previous generated selection removed."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print(
        "RIFT VALLEY WATCH"
    )
    print(
        "MAIN STORY SELECTION ENGINE"
    )
    print(
        f"VERSION: {VERSION}"
    )
    print("=" * 70)

    print(
        f"BASE DIR: {BASE_DIR}"
    )

    print(
        f"STORY FILE: {STORY_FILE}"
    )

    print(
        f"SCRIPT FILE: {SCRIPT_FILE}"
    )

    print(
        f"IMAGE FILE: {FINAL_IMAGE}"
    )

    print(
        f"VIDEO FILE: {FINAL_VIDEO}"
    )

    print("=" * 70)

    try:
        clean_previous_selection()

        selected = select_story()

        if not selected:
            raise RuntimeError(
                "Story selection returned no story."
            )

        verify_selected_files()

        run_video_generator()

        if not FINAL_VIDEO.exists():
            raise RuntimeError(
                "Final MP4 does not exist after "
                "video generation."
            )

        print()
        print("=" * 70)
        print(
            "RIFT VALLEY WATCH GENERATION COMPLETE"
        )
        print("=" * 70)

        print(
            f"HEADLINE: "
            f"{selected.get('title', '')}"
        )

        print(
            f"COUNTY: "
            f"{selected.get('county', '')}"
        )

        print(
            f"TYPE: "
            f"{selected.get('story_type', '')}"
        )

        print(
            f"MP4: {FINAL_VIDEO}"
        )

        print(
            f"SIZE: "
            f"{FINAL_VIDEO.stat().st_size:,} bytes"
        )

        print("=" * 70)

        return 0

    except KeyboardInterrupt:
        print()
        print(
            "[STOPPED] Generation interrupted."
        )
        return 130

    except Exception as exc:
        print()
        print("=" * 70)
        print(
            "[FATAL ERROR]"
        )
        print("=" * 70)

        print(
            str(exc)
        )

        print("=" * 70)

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
