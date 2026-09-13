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
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"

SELECTED_STORY = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ============================================================
# RIFT VALLEY COUNTIES
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
# APPROVED NEWS SOURCES
# ============================================================

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


# ============================================================
# BLOCKED SOURCES
# ============================================================

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


# ============================================================
# BAD IMAGE TERMS
# ============================================================

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


# ============================================================
# HTTP HEADERS
# ============================================================

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


# ============================================================
# LOGGING
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# GENERAL CLEANING
# ============================================================

def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    value = unicodedata.normalize("NFKC", str(value))

    value = html.unescape(value)

    value = value.replace("\xa0", " ")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


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
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# DOMAIN
# ============================================================

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


# ============================================================
# BLOCKED URL
# ============================================================

def blocked(url):

    host = domain(url)

    if not host:
        return True

    return any(
        host == item
        or host.endswith("." + item)
        for item in BLOCKED_DOMAINS
    )


# ============================================================
# APPROVED URL
# ============================================================

def approved(url):

    host = domain(url)

    if not host:
        return False

    if blocked(url):
        return False

    return any(
        host == item
        or host.endswith("." + item)
        for item in APPROVED_DOMAINS
    )


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

            if re.search(
                r"\b"
                + re.escape(alias.lower())
                + r"\b",
                text,
            ):
                score += 1

        if score > best_score:

            best_county = county
            best_score = score

    return best_county


# ============================================================
# HTTP FETCH
# ============================================================

def fetch(url, accept_html=True):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if accept_html:

            content_type = (
                response.headers
                .get("content-type", "")
                .lower()
            )

            if "html" not in content_type:
                return None

        return response

    except Exception as exc:

        log(
            f"FETCH FAILED: {url} | {exc}"
        )

        return None


# ============================================================
# CLEAN HEADLINE
# ============================================================

def clean_title(title):
    """
    Remove publisher/source branding from headlines.

    Examples:

    Ruto pitches development agenda in South Rift | KBC Digital
    ->
    Ruto pitches development agenda in South Rift

    Ruto launches project in Bomet - Citizen Digital
    ->
    Ruto launches project in Bomet
    """

    title = clean(title)

    if not title:
        return ""

    publishers = [
        "People Daily",
        "The Star",
        "The-Star",
        "Citizen Digital",
        "Citizen",
        "The Standard",
        "Daily Nation",
        "Nation Africa",
        "Nation",
        "Capital News",
        "KBC Digital",
        "KBC News",
        "KBC",
        "NTV Kenya",
        "NTV",
        "TV47",
        "Tuko",
        "Kenya News",
        "Kenya Broadcasting Corporation",
    ]

    changed = True

    while changed:

        changed = False

        for publisher in publishers:

            pattern = (
                r"\s*(?:\||-|–|—|:)\s*"
                + re.escape(publisher)
                + r"\s*$"
            )

            cleaned = re.sub(
                pattern,
                "",
                title,
                flags=re.I,
            )

            if cleaned != title:

                title = cleaned.strip()

                changed = True

    # Remove trailing publisher in brackets.

    title = re.sub(
        r"\s*[\[(]\s*"
        r"(?:"
        r"KBC(?: Digital| News)?"
        r"|Citizen(?: Digital)?"
        r"|Nation(?: Africa)?"
        r"|The Star"
        r"|People Daily"
        r"|The Standard"
        r"|Capital News"
        r"|NTV(?: Kenya)?"
        r"|TV47"
        r")"
        r"\s*[\])]\s*$",
        "",
        title,
        flags=re.I,
    )

    return clean(title)


# ============================================================
# REMOVE SOURCE / PUBLISHER METADATA
# ============================================================

def remove_metadata(text):
    """
    Remove explicit publisher attribution without destroying
    normal words.

    IMPORTANT:
    We do NOT blindly delete words such as 'nation' because
    that can corrupt legitimate article sentences.
    """

    text = clean(text)

    if not text:
        return ""

    patterns = [

        # Example:
        # according to KBC Digital
        r"\b(?:as|according to|reported by|reported in|reports from|speaking to)\s+"
        r"(?:KBC(?: Digital| News)?|Citizen(?: Digital)?|Nation(?: Africa)?|The Star|People Daily|The Standard|Capital News|NTV(?: Kenya)?|TV47)\b[,.]?",

        # Example:
        # KBC Digital reported
        r"\b(?:KBC(?: Digital| News)?|Citizen(?: Digital)?|Nation(?: Africa)?|The Star|People Daily|The Standard|Capital News|NTV(?: Kenya)?|TV47)\s+"
        r"(?:reported|reports|said|noted|states|stated)\b[,:]?",

        # Explicit publisher names.
        r"\b(?:KBC Digital|KBC News|Citizen Digital|Daily Nation|Nation Africa|People Daily|The Star|The Standard|Capital News|NTV Kenya|TV47)\b",

        # URLs.
        r"https?://\S+",
        r"www\.\S+",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            "",
            text,
            flags=re.I,
        )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text,
    )

    text = re.sub(
        r"[ ]{2,}",
        " ",
        text,
    )

    return clean(text)


# ============================================================
# NORMALIZE SENTENCE
# ============================================================

def normalize_sentence(text):

    text = remove_metadata(text)

    text = text.lower()

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


# ============================================================
# SENTENCE SIMILARITY
# ============================================================

def sentence_similarity(a, b):
    """
    Word-overlap similarity used to prevent repeated narration.
    """

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


# ============================================================
# DISCOVER ARTICLE LINKS
# ============================================================

def discover_links(page_url):

    response = fetch(page_url)

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
            clean(a.get("href")),
        ).split("#")[0]

        if not approved(url):
            continue

        if url == page_url:
            continue

        if url in seen:
            continue

        path = urlparse(url).path.lower()

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

        county = county_from_text(
            text + " " + url
        )

        result.append(
            {
                "url": url,
                "text": text,
                "county": county,
            }
        )

    return result


# ============================================================
# ADD IMAGE CANDIDATE
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

    if not value.startswith(
        ("http://", "https://")
    ):
        return

    low = value.lower()

    if any(
        term in low
        for term in BAD_IMAGE_TERMS
    ):
        return

    if value not in seen:

        seen.add(value)

        result.append(value)


# ============================================================
# GET IMAGE CANDIDATES
# ============================================================

def get_image_candidates(
    soup,
    article_url,
):

    result = []
    seen = set()

    meta_attributes = [
        {
            "property": "og:image"
        },
        {
            "property": "og:image:url"
        },
        {
            "name": "twitter:image"
        },
        {
            "property": "twitter:image"
        },
    ]

    for attrs in meta_attributes:

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

    def scan_json(value):

        if isinstance(
            value,
            str,
        ):

            add_image_candidate(
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

                scan_json(item)

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

                    scan_json(
                        value[key]
                    )

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:

            data = json.loads(
                script.string
                or script.get_text()
            )

            scan_json(data)

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

                    candidate = (
                        item.strip()
                        .split(" ")[0]
                    )

                    add_image_candidate(
                        result,
                        seen,
                        candidate,
                        article_url,
                    )

    return result


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    referer=None,
):

    if any(
        term in url.lower()
        for term in BAD_IMAGE_TERMS
    ):
        return None

    headers = {
        **HEADERS,
        "Accept": (
            "image/avif,"
            "image/webp,"
            "image/apng,"
            "image/*,"
            "*/*;q=0.8"
        ),
    }

    if referer:

        headers["Referer"] = referer

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if len(response.content) < 20000:
            return None

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if not (
            content_type.startswith("image/")
            or content_type.endswith(
                "octet-stream"
            )
        ):
            return None

        image = Image.open(
            BytesIO(response.content)
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


# ============================================================
# EXTRACT ARTICLE
# ============================================================

def extract_article(url):

    response = fetch(url)

    if not response:
        return None

    if not approved(response.url):
        return None

    final_url = response.url

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = ""

    for attrs in [
        {"property": "og:title"},
        {"name": "twitter:title"},
    ]:

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

            summary = clean(
                tag.get("content")
            )

            if summary:
                break

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

        for p in container.find_all("p"):

            text = clean(
                p.get_text(
                    " ",
                    strip=True,
                )
            )

            low = text.lower()

            if len(text) < 35:
                continue

            excluded = [
                "subscribe",
                "newsletter",
                "privacy policy",
                "cookie policy",
                "terms and conditions",
                "advertisement",
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
            paragraphs[:18]
        )
    )

    # --------------------------------------------------------
    # COUNTY
    # --------------------------------------------------------

    county = county_from_text(
        f"{title} {summary} {body}"
    )

    if not county:
        return None

    if len(body.split()) < 45:
        return None

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image = None

    candidates = get_image_candidates(
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

    # --------------------------------------------------------
    # SCORING
    # --------------------------------------------------------

    lower = (
        f"{title} {summary} {body}"
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

    score += 10

    return {
        "title": title,
        "summary": summary,
        "body": body,
        "county": county,
        "url": final_url,
        "image": image,
        "score": score,
    }


# ============================================================
# BUILD ORIGINAL NON-REPETITIVE SCRIPT
# ============================================================

def build_script(article):
    """
    Creates narration from unique factual article content.

    IMPORTANT:
    - The headline is NOT spoken again.
    - Publisher names are removed.
    - Repeated sentences are removed.
    - Similar sentences are removed.
    - Generic filler is avoided.
    """

    title = clean_title(
        article["title"]
    )

    county = clean(
        article["county"]
    )

    summary = remove_metadata(
        article.get(
            "summary",
            "",
        )
    )

    body = remove_metadata(
        article.get(
            "body",
            "",
        )
    )

    candidates = []

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if (
        summary
        and summary.lower()
        != title.lower()
    ):

        candidates.append(
            summary
        )

    # --------------------------------------------------------
    # BODY SENTENCES
    # --------------------------------------------------------

    for sentence in re.split(
        r"(?<=[.!?])\s+",
        body,
    ):

        sentence = remove_metadata(
            sentence
        )

        if len(
            sentence.split()
        ) < 10:

            continue

        candidates.append(
            sentence
        )

    # --------------------------------------------------------
    # UNIQUE SENTENCE SELECTION
    # --------------------------------------------------------

    selected = []

    seen_keys = set()

    for sentence in candidates:

        sentence = clean(
            sentence
        )

        key = normalize_sentence(
            sentence
        )

        if not key:
            continue

        if key in seen_keys:
            continue

        # Prevent similar sentences.
        if any(
            sentence_similarity(
                sentence,
                previous,
            )
            >= 0.72
            for previous in selected
        ):
            continue

        # Prevent headline from being repeated.
        if (
            title
            and sentence_similarity(
                sentence,
                title,
            )
            >= 0.82
        ):
            continue

        seen_keys.add(key)

        selected.append(
            sentence
        )

        if len(
            " ".join(selected).split()
        ) >= 105:

            break

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = " ".join(
        selected
    )

    if county and narration:

        narration = (
            f"In {county}, "
            f"{narration}"
        )

    narration = clean(
        narration
    )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if len(
        narration.split()
    ) < 45:

        fallback = []

        for sentence in re.split(
            r"(?<=[.!?])\s+",
            body,
        ):

            sentence = remove_metadata(
                sentence
            )

            if len(
                sentence.split()
            ) < 8:

                continue

            if any(
                sentence_similarity(
                    sentence,
                    previous,
                )
                >= 0.72
                for previous in fallback
            ):
                continue

            fallback.append(
                sentence
            )

            if len(
                " ".join(fallback).split()
            ) >= 70:

                break

        if fallback:

            narration = clean(
                f"In {county}, "
                + " ".join(fallback)
            )

    return narration


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

    image_info["image"].convert(
        "RGB"
    ).save(
        FINAL_IMAGE,
        "JPEG",
        quality=95,
        optimize=True,
    )

    with Image.open(
        FINAL_IMAGE
    ) as check:

        check.load()

        if (
            check.width < 400
            or check.height < 250
        ):

            raise RuntimeError(
                "Final image is invalid."
            )

    return FINAL_IMAGE


# ============================================================
# SELECT BEST STORY
# ============================================================

def select_best(candidates):

    if not candidates:

        raise RuntimeError(
            "No real Rift Valley article "
            "with a usable image was found."
        )

    unique = []

    hashes = set()

    for item in candidates:

        image_hash = (
            item["image"]["md5"]
        )

        if image_hash in hashes:
            continue

        hashes.add(image_hash)

        unique.append(
            item
        )

    if not unique:

        raise RuntimeError(
            "No unique real article image "
            "was found."
        )

    unique.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return unique[0]


# ============================================================
# DISCOVER STORIES
# ============================================================

def discover():

    candidates = []

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

        links.sort(
            key=lambda x: (
                1 if x["county"] else 0,
                len(x["text"]),
            ),
            reverse=True,
        )

        for item in links[:60]:

            article = extract_article(
                item["url"]
            )

            if (
                article
                and approved(
                    article["url"]
                )
            ):

                candidates.append(
                    article
                )

                log(
                    "ACCEPTED: "
                    f"{article['county']} | "
                    f"{article['title']}"
                )

                if len(
                    candidates
                ) >= 20:

                    return candidates

            time.sleep(0.15)

    return candidates


# ============================================================
# VALIDATE STORY
# ============================================================

def validate(story):

    if not clean(
        story.get("title")
    ):

        raise RuntimeError(
            "Story title missing."
        )

    if not clean(
        story.get("county")
    ):

        raise RuntimeError(
            "Story county missing."
        )

    image_file = (
        ROOT
        / clean(
            story.get(
                "image_path"
            )
        )
    )

    if not image_file.exists():

        raise RuntimeError(
            f"Story image not found: "
            f"{image_file}"
        )

    narration = clean(
        story.get(
            "script"
        )
    )

    if len(
        narration.split()
    ) < 45:

        raise RuntimeError(
            "Narration is too short."
        )

    # --------------------------------------------------------
    # ABSOLUTELY NO SOURCE BRANDING
    # --------------------------------------------------------

    forbidden = [

        r"\bgoogle news\b",
        r"\bpeople daily\b",
        r"\bthe star\b",
        r"\bcitizen digital\b",
        r"\bthe standard\b",
        r"\bdaily nation\b",
        r"\bcapital news\b",
        r"\bkbc(?: digital| news)?\b",
        r"\bntv kenya\b",
        r"\btv47\b",

        r"\bfacebook\b",
        r"\binstagram\b",
        r"\btwitter\b",
        r"\byoutube\b",
        r"\btiktok\b",

        r"https?://",
        r"www\.",
    ]

    lower = narration.lower()

    if any(
        re.search(
            pattern,
            lower,
        )
        for pattern in forbidden
    ):

        raise RuntimeError(
            "Publisher/social metadata "
            "found in narration."
        )

    # --------------------------------------------------------
    # CHECK REPETITION
    # --------------------------------------------------------

    sentences = [
        item.strip()
        for item in re.split(
            r"(?<=[.!?])\s+",
            narration,
        )
        if item.strip()
    ]

    for i, sentence in enumerate(
        sentences
    ):

        if any(
            sentence_similarity(
                sentence,
                previous,
            )
            >= 0.78
            for previous in sentences[:i]
        ):

            raise RuntimeError(
                "Repeated sentence "
                "detected in narration."
            )

    # --------------------------------------------------------
    # IMAGE VALIDATION
    # --------------------------------------------------------

    with Image.open(
        image_file
    ) as im:

        im.load()

        if (
            im.width < 400
            or im.height < 250
        ):

            raise RuntimeError(
                "Story image is invalid."
            )


# ============================================================
# WRITE STORY + SCRIPT
# ============================================================

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

        "summary": remove_metadata(
            article.get(
                "summary",
                "",
            )
        ),

        "body": remove_metadata(
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

        "selected_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        # Kept internally for verification.
        # It is NOT displayed in the video.
        "article_url": article["url"],
    }

    selected_script = {
        "title": story["title"],
        "county": story["county"],
        "narration": story["script"],
    }

    validate(
        story
    )

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
# DELETE OLD OUTPUTS
# ============================================================

def clean_previous():

    for directory in [
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
    ]:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    for path in [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
    ]:

        if path.exists():

            path.unlink()


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_generator():

    if not VIDEO_GENERATOR.exists():

        raise RuntimeError(
            "rift_valley_video_generator.py "
            "not found."
        )

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
            "Video generator failed "
            f"with exit code "
            f"{result.returncode}"
        )


# ============================================================
# VERIFY FINAL MP4
# ============================================================

def verify():

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final Rift Valley Watch MP4 "
            "was not generated."
        )

    if FINAL_VIDEO.stat().st_size < 100000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(FINAL_VIDEO),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:

        raise RuntimeError(
            "Final MP4 failed "
            "FFprobe validation."
        )

    try:

        duration = float(
            probe.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Final MP4 duration "
            "could not be read."
        )

    if duration < 5:

        raise RuntimeError(
            "Final MP4 is too short."
        )

    log(
        "FINAL VIDEO VERIFIED: "
        f"{FINAL_VIDEO} | "
        f"{FINAL_VIDEO.stat().st_size / 1048576:.2f} MB | "
        f"{duration:.2f}s"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 70)

    log(
        "STARTING RIFT VALLEY WATCH"
    )

    log("=" * 70)

    log(
        "VERSION: "
        "RVW_MAIN_V12_ORIGINAL_NONREPETITIVE"
    )

    clean_previous()

    candidates = discover()

    log(
        f"VALID STORIES FOUND: "
        f"{len(candidates)}"
    )

    selected = select_best(
        candidates
    )

    log(
        "SELECTED: "
        f"{selected['county']} | "
        f"{selected['title']} | "
        f"SCORE "
        f"{selected['score']}"
    )

    story = write_files(
        selected
    )

    log(
        "CLEAN HEADLINE: "
        f"{story['title']}"
    )

    log(
        "NARRATION WORDS: "
        f"{len(story['script'].split())}"
    )

    log(
        "IMAGE: "
        f"{story['image_path']}"
    )

    run_generator()

    verify()

    log(
        "RIFT VALLEY WATCH COMPLETED"
    )


if __name__ == "__main__":
    main()
