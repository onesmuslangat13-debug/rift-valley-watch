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


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
SOURCE_DIR = ROOT / "assets" / "source"

SELECTED_STORY = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"
STORY_HISTORY = DATA_DIR / "story_history.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ==============================================================
# RIFT VALLEY COUNTIES
# ==============================================================

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


# ==============================================================
# APPROVED PUBLISHER PAGES
# ==============================================================

PUBLISHER_PAGES = [
    "https://citizen.digital/",
    "https://www.the-star.co.ke/news/",
    "https://www.kbc.co.ke/",
    "https://nation.africa/kenya/news",
]


APPROVED_DOMAINS = [
    "citizen.digital",
    "the-star.co.ke",
    "kbc.co.ke",
    "nation.africa",
]


BLOCKED_DOMAINS = [
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
]


BAD_IMAGE_TERMS = [
    "google-news",
    "google_news",
    "googlelogo",
    "google-logo",
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
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
}


SOURCE_NAMES = [
    "KBC Digital",
    "KBC News",
    "KBC",
    "Citizen Digital",
    "Citizen",
    "Daily Nation",
    "Nation Africa",
    "The Star",
    "People Daily",
    "The Standard",
    "Standard Media",
    "Capital News",
    "NTV Kenya",
    "NTV",
    "TV47",
    "Tuko",
]


# ==============================================================
# STORY HISTORY SETTINGS
# ==============================================================

# Number of recent stories that should be protected from reuse.
RECENT_HISTORY_LIMIT = 12

# Maximum number of history records kept permanently.
MAX_HISTORY_RECORDS = 100


# ==============================================================
# LOGGING
# ==============================================================

def log(text=""):
    print(text, flush=True)


# ==============================================================
# BASIC CLEANING
# ==============================================================

def clean(value):

    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = html.unescape(value)

    value = value.replace(
        "\xa0",
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def remove_junk(text):

    text = clean(text)

    if not text:
        return ""

    patterns = [
        r"-\s*Advertisement\s*-",
        r"\bAdvertisement\b",
        r"\[\s*\.\.\.\s*\]",
        r"\(\s*\.\.\.\s*\)",
        r"\.\.\.\s*$",
        r"https?://\S+",
        r"www\.\S+",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            " ",
            text,
            flags=re.I,
        )

    for source in SOURCE_NAMES:

        text = re.sub(
            r"\b"
            + re.escape(source)
            + r"\b",
            " ",
            text,
            flags=re.I,
        )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text,
    )

    text = re.sub(
        r"\s{2,}",
        " ",
        text,
    )

    return clean(text)


def clean_title(title):

    title = clean(title)

    if not title:
        return ""

    changed = True

    while changed:

        changed = False

        for source in SOURCE_NAMES:

            pattern = (
                r"\s*(?:\||-|–|—|:)\s*"
                + re.escape(source)
                + r"\s*$"
            )

            new = re.sub(
                pattern,
                "",
                title,
                flags=re.I,
            )

            if new != title:

                title = new.strip()
                changed = True

    title = re.sub(
        r"\s*[\[\(]\s*"
        r"(?:"
        r"KBC|"
        r"KBC Digital|"
        r"KBC News|"
        r"Citizen|"
        r"Citizen Digital|"
        r"Nation|"
        r"Nation Africa|"
        r"Daily Nation|"
        r"The Star|"
        r"People Daily|"
        r"The Standard|"
        r"Capital News|"
        r"NTV|"
        r"NTV Kenya|"
        r"TV47"
        r")"
        r"\s*[\]\)]\s*$",
        "",
        title,
        flags=re.I,
    )

    title = re.sub(
        r"\s*(?:\||-|–|—|:)\s*$",
        "",
        title,
    )

    return clean(title)


# ==============================================================
# TEXT SIMILARITY
# ==============================================================

def normalize_sentence(text):

    text = remove_junk(text).lower()

    text = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def similarity(a, b):

    aa = set(
        normalize_sentence(a).split()
    )

    bb = set(
        normalize_sentence(b).split()
    )

    if not aa or not bb:
        return 0.0

    return (
        len(aa & bb)
        / max(
            1,
            min(
                len(aa),
                len(bb),
            ),
        )
    )


def split_sentences(text):

    text = remove_junk(text)

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+",
            text,
        )
        if sentence.strip()
    ]


def dedupe_sentences(
    sentences,
    threshold=0.72,
):

    result = []
    seen = set()

    for sentence in sentences:

        sentence = remove_junk(
            sentence
        )

        if len(
            sentence.split()
        ) < 8:

            continue

        key = normalize_sentence(
            sentence
        )

        if not key:
            continue

        if key in seen:
            continue

        if any(
            similarity(
                sentence,
                old,
            ) >= threshold
            for old in result
        ):
            continue

        seen.add(key)
        result.append(sentence)

    return result


# ==============================================================
# JSON
# ==============================================================

def save_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


def load_json(path, default):

    if not path.exists():
        return default

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return data

    except Exception as exc:

        log(
            f"WARNING: Could not read "
            f"{path}: {exc}"
        )

        return default


# ==============================================================
# STORY HISTORY
# ==============================================================

def load_history():

    data = load_json(
        STORY_HISTORY,
        [],
    )

    if not isinstance(data, list):
        return []

    cleaned = []

    for item in data:

        if not isinstance(item, dict):
            continue

        url = clean(
            item.get("url", "")
        )

        title = clean(
            item.get("title", "")
        )

        if not url and not title:
            continue

        cleaned.append(
            {
                "url": url,
                "title": title,
                "county": clean(
                    item.get(
                        "county",
                        "",
                    )
                ),
                "image_md5": clean(
                    item.get(
                        "image_md5",
                        "",
                    )
                ),
                "selected_at": clean(
                    item.get(
                        "selected_at",
                        "",
                    )
                ),
            }
        )

    return cleaned[-MAX_HISTORY_RECORDS:]


def save_history(history):

    history = history[
        -MAX_HISTORY_RECORDS:
    ]

    save_json(
        STORY_HISTORY,
        history,
    )


def add_to_history(article):

    history = load_history()

    url = clean(
        article.get(
            "url",
            "",
        )
    )

    title = clean_title(
        article.get(
            "title",
            "",
        )
    )

    county = clean(
        article.get(
            "county",
            "",
        )
    )

    image_md5 = clean(
        article.get(
            "image",
            {},
        ).get(
            "md5",
            "",
        )
        if isinstance(
            article.get("image"),
            dict,
        )
        else ""
    )

    # Remove an existing identical record
    # before adding the new one.
    filtered = []

    for item in history:

        if (
            url
            and item.get("url") == url
        ):

            continue

        if (
            title
            and item.get("title") == title
        ):

            continue

        filtered.append(item)

    filtered.append(
        {
            "url": url,
            "title": title,
            "county": county,
            "image_md5": image_md5,
            "selected_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }
    )

    save_history(filtered)

    log(
        "HISTORY UPDATED: "
        f"{len(filtered)} records stored."
    )


def history_keys(history):

    urls = set()
    titles = set()
    images = set()

    for item in history:

        url = clean(
            item.get("url", "")
        )

        title = normalize_sentence(
            item.get("title", "")
        )

        image = clean(
            item.get(
                "image_md5",
                "",
            )
        )

        if url:
            urls.add(url)

        if title:
            titles.add(title)

        if image:
            images.add(image)

    return urls, titles, images


def is_recently_used(
    article,
    history,
    recent_limit=RECENT_HISTORY_LIMIT,
):

    recent = history[
        -recent_limit:
    ]

    article_url = clean(
        article.get(
            "url",
            "",
        )
    )

    article_title = normalize_sentence(
        article.get(
            "title",
            "",
        )
    )

    article_image = clean(
        article.get(
            "image",
            {},
        ).get(
            "md5",
            "",
        )
        if isinstance(
            article.get("image"),
            dict,
        )
        else ""
    )

    for item in recent:

        old_url = clean(
            item.get(
                "url",
                "",
            )
        )

        old_title = normalize_sentence(
            item.get(
                "title",
                "",
            )
        )

        old_image = clean(
            item.get(
                "image_md5",
                "",
            )
        )

        if (
            article_url
            and old_url
            and article_url == old_url
        ):

            return True

        if (
            article_title
            and old_title
            and article_title == old_title
        ):

            return True

        if (
            article_image
            and old_image
            and article_image == old_image
        ):

            return True

    return False


# ==============================================================
# URL / DOMAIN
# ==============================================================

def domain(url):

    try:

        return (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
            .removeprefix("www.")
        )

    except Exception:

        return ""


def blocked(url):

    host = domain(url)

    if not host:
        return True

    return any(
        host == item
        or host.endswith(
            "." + item
        )
        for item in BLOCKED_DOMAINS
    )


def approved(url):

    host = domain(url)

    if not host:
        return False

    if blocked(url):
        return False

    return any(
        host == item
        or host.endswith(
            "." + item
        )
        for item in APPROVED_DOMAINS
    )


# ==============================================================
# COUNTY DETECTION
# ==============================================================

def county_from_text(text):

    text = clean(text).lower()

    best = ""
    score = 0

    for county, aliases in COUNTIES.items():

        current = 0

        for alias in aliases:

            if re.search(
                r"\b"
                + re.escape(
                    alias.lower()
                )
                + r"\b",
                text,
            ):

                current += 1

        if current > score:

            best = county
            score = current

    return best


# ==============================================================
# HTTP
# ==============================================================

def fetch(
    url,
    html_only=True,
):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if html_only:

            content_type = (
                response.headers
                .get(
                    "content-type",
                    "",
                )
                .lower()
            )

            if "html" not in content_type:
                return None

        return response

    except Exception as exc:

        log(
            f"FETCH FAILED: "
            f"{url} | {exc}"
        )

        return None


# ==============================================================
# DISCOVER ARTICLE LINKS
# ==============================================================

def discover_links(page_url):

    response = fetch(
        page_url
    )

    if not response:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    result = []
    seen = set()

    for a in soup.find_all(
        "a",
        href=True,
    ):

        url = urljoin(
            page_url,
            clean(
                a.get("href")
            ),
        ).split("#")[0]

        if not approved(url):
            continue

        if url == page_url:
            continue

        if url in seen:
            continue

        path = urlparse(
            url
        ).path.lower()

        if path in (
            "",
            "/",
            "/news",
            "/news/",
            "/category/news/",
            "/search",
        ):

            continue

        seen.add(url)

        text = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        result.append(
            {
                "url": url,
                "text": text,
                "county": county_from_text(
                    text + " " + url
                ),
            }
        )

    return result


# ==============================================================
# IMAGE DISCOVERY
# ==============================================================

def add_image(
    result,
    seen,
    value,
    article_url,
):

    value = clean(value)

    if not value:
        return

    if value.startswith(
        "data:"
    ):
        return

    value = urljoin(
        article_url,
        value,
    )

    if not value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return

    if any(
        term in value.lower()
        for term in BAD_IMAGE_TERMS
    ):
        return

    if value not in seen:

        seen.add(value)

        result.append(value)


def image_candidates(
    soup,
    article_url,
):

    result = []
    seen = set()

    for attrs in (
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"name": "twitter:image"},
        {"property": "twitter:image"},
    ):

        for tag in soup.find_all(
            "meta",
            attrs=attrs,
        ):

            add_image(
                result,
                seen,
                tag.get(
                    "content"
                ),
                article_url,
            )

    def scan(value):

        if isinstance(
            value,
            str,
        ):

            add_image(
                result,
                seen,
                value,
                article_url,
            )

        elif isinstance(
            value,
            list,
        ):

            for item in value:
                scan(item)

        elif isinstance(
            value,
            dict,
        ):

            for key in (
                "image",
                "thumbnailUrl",
                "contentUrl",
                "url",
            ):

                if key in value:
                    scan(
                        value[key]
                    )

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:

            scan(
                json.loads(
                    script.string
                    or script.get_text()
                )
            )

        except Exception:
            pass

    containers = (
        soup.find_all("article")
        or soup.find_all("main")
        or [soup]
    )

    for container in containers:

        for img in container.find_all(
            "img"
        ):

            for key in (
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-original-src",
                "data-fallback-src",
            ):

                add_image(
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

                for item in srcset.split(
                    ","
                ):

                    add_image(
                        result,
                        seen,
                        item.strip()
                        .split(" ")[0],
                        article_url,
                    )

    return result


# ==============================================================
# IMAGE DOWNLOAD
# ==============================================================

def download_image(
    url,
    referer=None,
):

    if any(
        term in url.lower()
        for term in BAD_IMAGE_TERMS
    ):
        return None

    headers = dict(
        HEADERS
    )

    headers["Accept"] = (
        "image/avif,image/webp,"
        "image/apng,image/*,"
        "*/*;q=0.8"
    )

    if referer:
        headers["Referer"] = referer

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )

        if (
            response.status_code != 200
            or len(response.content) < 20000
        ):

            return None

        content_type = (
            response.headers
            .get(
                "content-type",
                "",
            )
            .lower()
        )

        if not (
            content_type.startswith(
                "image/"
            )
            or content_type.endswith(
                "octet-stream"
            )
        ):

            return None

        image = Image.open(
            BytesIO(
                response.content
            )
        )

        image.load()

        if image.width < 400:
            return None

        if image.height < 250:
            return None

        if (
            image.width
            * image.height
            < 150000
        ):

            return None

        return {
            "image": image.copy(),
            "md5": hashlib.md5(
                response.content
            ).hexdigest(),
            "url": response.url,
            "width": image.width,
            "height": image.height,
        }

    except Exception:

        return None


# ==============================================================
# ARTICLE EXTRACTION
# ==============================================================

def extract_article(url):

    response = fetch(url)

    if not response:
        return None

    if not approved(
        response.url
    ):
        return None

    final_url = response.url

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

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

            value = clean(
                tag.get(
                    "content"
                )
            )

            if value:

                title = value
                break

    if not title:

        h1 = soup.find(
            "h1"
        )

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

    title = clean_title(
        title
    )

    if len(title) < 12:
        return None

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

            value = remove_junk(
                tag.get(
                    "content"
                )
            )

            if value:

                summary = value
                break

    paragraphs = []

    container = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if container:

        for p in container.find_all(
            "p"
        ):

            text = remove_junk(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) < 35:
                continue

            low = text.lower()

            excluded = [
                "subscribe",
                "newsletter",
                "privacy policy",
                "cookie policy",
                "terms and conditions",
                "download our app",
            ]

            if any(
                item in low
                for item in excluded
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    body = clean(
        " ".join(
            paragraphs[:20]
        )
    )

    county = county_from_text(
        f"{title} {summary} {body}"
    )

    if not county:
        return None

    if len(
        body.split()
    ) < 45:

        return None

    image = None

    candidates = image_candidates(
        soup,
        final_url,
    )

    for image_url in candidates[:60]:

        image = download_image(
            image_url,
            referer=final_url,
        )

        if image:
            break

    if not image:
        return None

    lower = (
        f"{title} "
        f"{summary} "
        f"{body}"
    ).lower()

    score = (
        min(
            len(body.split()),
            220,
        )
        // 5
    )

    topical_words = [
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
        "development",
        "construction",
        "funding",
        "budget",
        "education",
        "transport",
        "infrastructure",
        "residents",
    ]

    for word in topical_words:

        if re.search(
            r"\b"
            + re.escape(word)
            + r"\b",
            lower,
        ):

            score += 2

    negative_phrases = [
        "charm offensive",
        "crowd erupts",
        "crowd goes wild",
        "dance",
        "chants",
        "rally",
        "campaign",
    ]

    for phrase in negative_phrases:

        if phrase in lower:
            score -= 10

    return {
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "url": final_url,
        "image": image,
        "score": score,
    }


# ==============================================================
# ORIGINAL-STYLE NARRATION BUILD
# ==============================================================

def build_script(article):

    title = clean_title(
        article.get(
            "title",
            "",
        )
    )

    county = clean(
        article.get(
            "county",
            "",
        )
    )

    body = remove_junk(
        article.get(
            "body",
            "",
        )
    )

    sentences = dedupe_sentences(
        split_sentences(body)
    )

    selected = []

    for sentence in sentences:

        if (
            title
            and similarity(
                sentence,
                title,
            ) >= 0.82
        ):
            continue

        if any(
            similarity(
                sentence,
                old,
            ) >= 0.72
            for old in selected
        ):
            continue

        selected.append(sentence)

        word_count = len(
            " ".join(
                selected
            ).split()
        )

        if word_count >= 105:
            break

    narration = " ".join(
        selected
    )

    if not narration:

        raise RuntimeError(
            "Could not create clean narration "
            "from article body."
        )

    if county:

        narration = (
            f"In {county}, "
            f"{narration}"
        )

    return remove_junk(
        narration
    )


# ==============================================================
# SAVE IMAGE
# ==============================================================

def save_image(info):

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_IMAGE.exists():
        FINAL_IMAGE.unlink()

    info["image"].convert(
        "RGB"
    ).save(
        FINAL_IMAGE,
        "JPEG",
        quality=95,
        optimize=True,
    )

    return FINAL_IMAGE


# ==============================================================
# STORY SELECTION
# ==============================================================

def select_best(candidates):

    if not candidates:

        raise RuntimeError(
            "No real Rift Valley article "
            "with a usable image was found."
        )

    # ----------------------------------------------------------
    # Remove duplicate images within this run.
    # ----------------------------------------------------------

    unique = []
    hashes = set()

    for item in candidates:

        image_hash = (
            item["image"]["md5"]
        )

        if image_hash in hashes:
            continue

        hashes.add(
            image_hash
        )

        unique.append(item)

    if not unique:

        raise RuntimeError(
            "No unique real article image "
            "was found."
        )

    # ----------------------------------------------------------
    # Load permanent history.
    # ----------------------------------------------------------

    history = load_history()

    recent = history[
        -RECENT_HISTORY_LIMIT:
    ]

    used_urls, used_titles, used_images = (
        history_keys(history)
    )

    log("")
    log(
        "STORY HISTORY: "
        f"{len(history)} records"
    )

    log(
        "RECENT STORY PROTECTION: "
        f"last {len(recent)} stories"
    )

    # ----------------------------------------------------------
    # First priority:
    # completely new stories never used before.
    # ----------------------------------------------------------

    never_used = []

    for item in unique:

        item_url = clean(
            item.get(
                "url",
                "",
            )
        )

        item_title = normalize_sentence(
            item.get(
                "title",
                "",
            )
        )

        item_image = clean(
            item.get(
                "image",
                {},
            ).get(
                "md5",
                "",
            )
            if isinstance(
                item.get("image"),
                dict,
            )
            else ""
        )

        already_used = (
            (
                item_url
                and item_url in used_urls
            )
            or
            (
                item_title
                and item_title in used_titles
            )
            or
            (
                item_image
                and item_image in used_images
            )
        )

        if not already_used:
            never_used.append(item)

    # ----------------------------------------------------------
    # Sort newest/new candidates by score.
    # ----------------------------------------------------------

    never_used.sort(
        key=lambda x: (
            x["score"],
            len(
                x.get(
                    "body",
                    "",
                ).split()
            ),
        ),
        reverse=True,
    )

    if never_used:

        selected = never_used[0]

        log(
            "SELECTION MODE: "
            "NEW STORY"
        )

        log(
            "SELECTED NEW STORY: "
            f"{selected['county']} | "
            f"{selected['title']} | "
            f"SCORE {selected['score']}"
        )

        return selected

    # ----------------------------------------------------------
    # If every available story has been used before,
    # protect the most recent stories and choose the best
    # older story.
    # ----------------------------------------------------------

    older_candidates = [
        item
        for item in unique
        if not is_recently_used(
            item,
            history,
            RECENT_HISTORY_LIMIT,
        )
    ]

    older_candidates.sort(
        key=lambda x: (
            x["score"],
            len(
                x.get(
                    "body",
                    "",
                ).split()
            ),
        ),
        reverse=True,
    )

    if older_candidates:

        selected = older_candidates[0]

        log(
            "SELECTION MODE: "
            "OLDER STORY AFTER HISTORY FILTER"
        )

        log(
            "SELECTED STORY: "
            f"{selected['county']} | "
            f"{selected['title']} | "
            f"SCORE {selected['score']}"
        )

        return selected

    # ----------------------------------------------------------
    # Absolute fallback:
    # if every available candidate is within the recent
    # protection window, choose the highest scoring story
    # that is NOT the immediately previous story.
    # ----------------------------------------------------------

    previous_url = ""

    if history:

        previous_url = clean(
            history[-1].get(
                "url",
                "",
            )
        )

    fallback = [
        item
        for item in unique
        if clean(
            item.get(
                "url",
                "",
            )
        ) != previous_url
    ]

    if not fallback:
        fallback = unique

    fallback.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    selected = fallback[0]

    log(
        "SELECTION MODE: "
        "FALLBACK"
    )

    log(
        "SELECTED STORY: "
        f"{selected['county']} | "
        f"{selected['title']} | "
        f"SCORE {selected['score']}"
    )

    return selected


# ==============================================================
# WRITE SELECTED STORY
# ==============================================================

def write_files(article):

    image_path = save_image(
        article["image"]
    )

    script = build_script(
        article
    )

    story = {
        "title": clean_title(
            article["title"]
        ),
        "county": clean(
            article["county"]
        ),
        "summary": remove_junk(
            article.get(
                "summary",
                "",
            )
        ),
        "body": remove_junk(
            article.get(
                "body",
                "",
            )
        ),
        "image_path": str(
            image_path.relative_to(
                ROOT
            )
        ).replace(
            "\\",
            "/",
        ),
        "script": script,
        "selected_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "article_url": article["url"],
    }

    selected_script = {
        "title": story["title"],
        "county": story["county"],
        "narration": script,
    }

    save_json(
        SELECTED_STORY,
        story,
    )

    save_json(
        SELECTED_SCRIPT,
        selected_script,
    )

    validate(
        story
    )

    return story


# ==============================================================
# VALIDATION
# ==============================================================

def validate(story):

    title = clean_title(
        story.get(
            "title",
            "",
        )
    )

    narration = remove_junk(
        story.get(
            "script",
            "",
        )
    )

    if not title:

        raise RuntimeError(
            "Story title missing."
        )

    if not story.get(
        "county"
    ):

        raise RuntimeError(
            "Story county missing."
        )

    if len(
        narration.split()
    ) < 45:

        raise RuntimeError(
            "Narration is too short "
            "after cleaning."
        )

    for source in SOURCE_NAMES:

        if re.search(
            r"\b"
            + re.escape(source)
            + r"\b",
            narration,
            flags=re.I,
        ):

            raise RuntimeError(
                "Publisher name found "
                f"in narration: {source}"
            )

    sentences = split_sentences(
        narration
    )

    for i, sentence in enumerate(
        sentences
    ):

        if any(
            similarity(
                sentence,
                previous,
            ) >= 0.78
            for previous in sentences[:i]
        ):

            raise RuntimeError(
                "Repeated sentence detected "
                "in narration."
            )

    if not FINAL_IMAGE.exists():

        raise RuntimeError(
            "Final story image missing."
        )

    with Image.open(
        FINAL_IMAGE
    ) as image:

        image.load()

        if (
            image.width < 400
            or image.height < 250
        ):

            raise RuntimeError(
                "Final story image is invalid."
            )


# ==============================================================
# DISCOVER STORIES
# ==============================================================

def discover():

    candidates = []

    # Keep URLs unique across all publishers.
    seen_article_urls = set()

    for page in PUBLISHER_PAGES:

        log(
            f"CHECKING NEWS PAGE: "
            f"{domain(page)}"
        )

        links = discover_links(
            page
        )

        log(
            f"LOCAL LINKS: {len(links)}"
        )

        # Put links that already mention a Rift Valley
        # county near the front, while still allowing
        # article-page extraction to discover counties.
        links.sort(
            key=lambda x: (
                1 if x["county"] else 0,
                len(x["text"]),
            ),
            reverse=True,
        )

        checked = 0

        for item in links[:80]:

            url = clean(
                item.get(
                    "url",
                    "",
                )
            )

            if not url:
                continue

            if url in seen_article_urls:
                continue

            seen_article_urls.add(url)

            article = extract_article(
                url
            )

            checked += 1

            if article:

                candidates.append(
                    article
                )

                log(
                    "ACCEPTED: "
                    f"{article['county']} | "
                    f"{article['title']} | "
                    f"SCORE {article['score']}"
                )

            time.sleep(
                0.15
            )

            # Collect enough candidates to give
            # the history filter real choice.
            if len(
                candidates
            ) >= 30:

                return candidates

        log(
            f"ARTICLES CHECKED: {checked}"
        )

    return candidates


# ==============================================================
# CLEAN TEMPORARY GENERATED FILES
# ==============================================================

def clean_previous():

    for directory in (
        DATA_DIR,
       
