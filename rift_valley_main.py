# ============================================================
# RIFT VALLEY WATCH
# rift_valley_main.py
# COMPLETE REPLACEMENT
# ============================================================

import os
import re
import json
import html
import hashlib
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urljoin, quote_plus

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = ROOT / "output"

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"
VIDEO_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

REQUEST_TIMEOUT = 25
MAX_AGE_HOURS = 72


# ============================================================
# HTTP
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


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

ALIASES = {
    "Bomet": [
        "Bomet", "Chepalungu", "Sotik", "Konoin",
        "Longisa", "Kaplong"
    ],
    "Kericho": [
        "Kericho", "Ainamoi", "Belgut", "Bureti",
        "Kipkelion", "Londiani", "Litein"
    ],
    "Nakuru": [
        "Nakuru", "Naivasha", "Gilgil", "Molo",
        "Njoro", "Bahati", "Rongai", "Subukia"
    ],
    "Nandi": [
        "Nandi", "Kapsabet", "Mosop", "Aldai",
        "Emgwen", "Chesumei", "Tindiret"
    ],
    "Uasin Gishu": [
        "Uasin Gishu", "Eldoret", "Turbo", "Kesses",
        "Soy", "Moiben", "Ainabkoi"
    ],
    "Elgeyo-Marakwet": [
        "Elgeyo-Marakwet", "Iten", "Keiyo",
        "Marakwet", "Keiyo South", "Keiyo North",
        "Marakwet East", "Marakwet West"
    ],
    "West Pokot": [
        "West Pokot", "Kapenguria", "Kacheliba",
        "Pokot South", "Pokot Central", "Sigor"
    ],
    "Narok": [
        "Narok", "Kilgoris", "Narok North",
        "Narok South", "Transmara", "Emurua Dikirr"
    ],
}


# ============================================================
# SOURCES
# ============================================================

TRUSTED_DOMAINS = {
    "citizen.digital",
    "citizen.co.ke",
    "nation.africa",
    "standardmedia.co.ke",
    "the-star.co.ke",
    "peopledaily.digital",
    "kenyanews.go.ke",
    "capitalfm.co.ke",
    "kbc.co.ke",
    "ntvkenya.co.ke",
    "tv47.digital",
    "tuko.co.ke",
    "businessdailyafrica.com",
    "businessdailyafrica.co.ke",
    "president.go.ke",
    "deputypresident.go.ke",
    "parliament.go.ke",
    "kenyalaw.org",
    "gov.ke",
    "go.ke",
}

BLOCKED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "google.com",
    "news.google.com",
    "bing.com",
    "r.bing.com",
    "twitter.com",
    "x.com",
}

BAD_PHRASES = [
    "google news",
    "news from around the web",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "sign in to continue",
    "log in to continue",
    "cookie policy",
    "privacy policy",
    "subscribe to continue",
    "javascript is disabled",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def first(*values):
    for value in values:
        value = clean(value)
        if value:
            return value
    return ""


def shorten(text, limit=400):
    text = clean(text)

    if len(text) <= limit:
        return text

    text = text[:limit]

    if " " in text:
        text = text.rsplit(" ", 1)[0]

    return text.rstrip(".,;:") + "..."


def read_json(path):
    path = Path(path)

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print("JSON read error:", path, exc)
        return {}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


def fetch(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        return response

    except Exception as exc:
        print("Request failed:", url, exc)
        return None


# ============================================================
# URL HELPERS
# ============================================================

def normalize_url(url):
    url = clean(url)

    if url.startswith("//"):
        url = "https:" + url

    return url


def domain(url):
    try:
        host = urlparse(normalize_url(url)).hostname or ""
        host = host.lower()

        if host.startswith("www."):
            host = host[4:]

        return host
    except Exception:
        return ""


def blocked(url):
    d = domain(url)

    return (
        d in BLOCKED_DOMAINS
        or any(d.endswith("." + x) for x in BLOCKED_DOMAINS)
    )


def trusted(url):
    d = domain(url)

    return (
        d in TRUSTED_DOMAINS
        or any(d.endswith("." + x) for x in TRUSTED_DOMAINS)
    )


def bad_text(text):
    text = clean(text).lower()

    return any(
        phrase in text
        for phrase in BAD_PHRASES
    )


# ============================================================
# DATE
# ============================================================

def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    value = clean(value)

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d %b %Y %H:%M",
        "%d %B %Y %H:%M",
        "%a, %d %b %Y %H:%M:%S %z",
    ]

    for fmt in formats:
        try:
            result = datetime.strptime(value, fmt)

            if result.tzinfo is None:
                result = result.replace(
                    tzinfo=timezone.utc
                )

            return result.astimezone(timezone.utc)

        except Exception:
            pass

    return None


def recent(value):
    parsed = parse_date(value)

    if parsed is None:
        return False

    return (
        datetime.now(timezone.utc) - parsed
        <= timedelta(hours=MAX_AGE_HOURS)
    )


# ============================================================
# COUNTY
# ============================================================

def detect_county(text):
    text = clean(text).lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county

    for county, names in ALIASES.items():
        for name in names:
            if name.lower() in text:
                return county

    return ""


# ============================================================
# IMAGE VALIDATION
# ============================================================

def valid_image(path):
    if not path:
        return False

    path = Path(path)

    if not path.exists():
        return False

    try:
        if path.stat().st_size < 5000:
            return False

        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size

            if width < 400 or height < 250:
                return False

            image.verify()

        return True

    except Exception:
        return False


def bad_image_url(url):
    url = normalize_url(url)

    if not url or blocked(url):
        return True

    value = url.lower()

    bad = [
        "favicon",
        "placeholder",
        "avatar",
        "google-news",
        "google_news",
        "facebook-icon",
        "youtube-icon",
        "instagram-icon",
        "tiktok-icon",
    ]

    return any(x in value for x in bad)


def download_image(url):
    if bad_image_url(url):
        return False

    response = fetch(url)

    if response is None:
        return False

    raw = response.content
    content_type = response.headers.get(
        "content-type", ""
    ).lower()

    if (
        "image" not in content_type
        and not raw.startswith(b"\xff\xd8")
        and not raw.startswith(b"\x89PNG")
        and not raw.startswith(b"RIFF")
    ):
        return False

    try:
        from io import BytesIO
        from PIL import Image

        image = Image.open(
            BytesIO(raw)
        ).convert("RGB")

        width, height = image.size

        if width < 400 or height < 250:
            return False

        IMAGE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image.save(
            IMAGE_FILE,
            "JPEG",
            quality=95,
        )

        if valid_image(IMAGE_FILE):
            print("REAL ARTICLE IMAGE:", IMAGE_FILE)
            return True

    except Exception as exc:
        print("Image conversion failed:", exc)

    return False


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def image_candidates(soup, base_url):
    result = []

    selectors = [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
    ]

    for tag_name, attrs in selectors:
        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):
            value = tag.get("content")

            if value:
                result.append(
                    urljoin(base_url, value)
                )

    for image in soup.find_all("img"):
        for attr in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
        ]:
            value = image.get(attr)

            if value:
                result.append(
                    urljoin(base_url, value)
                )

    unique = []
    seen = set()

    for url in result:
        url = normalize_url(url)

        if url and url not in seen:
            seen.add(url)
            unique.append(url)

    return unique


def recover_from_article(url):
    response = fetch(url)

    if response is None:
        return ""

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for candidate in image_candidates(
            soup,
            response.url,
        ):
            if download_image(candidate):
                return candidate

    except Exception as exc:
        print(
            "Article image recovery failed:",
            exc,
        )

    return ""


# ============================================================
# CRITICAL IMAGE RECOVERY
# ============================================================

def recover_image(story):
    story = story or {}

    # 1. Existing local image
    local_candidates = [
        IMAGE_FILE,
        SOURCE_DIR / "prepared_story_image.jpg",
        ASSETS_DIR / "story_image.jpg",
        ROOT / "story_image.jpg",
    ]

    for path in local_candidates:
        if valid_image(path):

            if Path(path).resolve() != IMAGE_FILE.resolve():
                try:
                    import shutil
                    shutil.copy2(path, IMAGE_FILE)
                except Exception:
                    continue

            if valid_image(IMAGE_FILE):
                print(
                    "IMAGE RECOVERY: existing local image"
                )
                story["local_image"] = str(
                    IMAGE_FILE
                )
                return str(IMAGE_FILE)

    # 2. URL fields
    urls = [
        story.get("image"),
        story.get("image_url"),
        story.get("imageUrl"),
        story.get("featured_image"),
        story.get("featuredImage"),
        story.get("thumbnail"),
    ]

    for url in urls:
        url = clean(url)

        if url and download_image(url):
            story["image"] = url
            story["local_image"] = str(
                IMAGE_FILE
            )
            return str(IMAGE_FILE)

    # 3. Article page
    article_url = first(
        story.get("source_url"),
        story.get("url"),
        story.get("link"),
    )

    if article_url:
        image_url = recover_from_article(
            article_url
        )

        if image_url:
            story["image"] = image_url
            story["local_image"] = str(
                IMAGE_FILE
            )
            return str(IMAGE_FILE)

    return ""


# ============================================================
# STORY QUALITY
# ============================================================

def confirmed(story):
    if story.get("confirmed") is True:
        return True

    if story.get("verified") is True:
        return True

    editorial = story.get("editorial")

    if isinstance(editorial, dict):
        if editorial.get("confirmed") is True:
            return True

    facts = story.get("verified_facts")

    if isinstance(facts, list) and facts:
        return True

    if isinstance(facts, dict) and facts:
        return True

    statement = first(
        story.get("official_statement"),
        story.get("official_quote"),
        story.get("statement"),
    )

    return len(statement) >= 30


def quality_gate(story):
    if not isinstance(story, dict):
        return False

    title = first(
        story.get("title"),
        story.get("headline"),
    )

    summary = first(
        story.get("summary"),
        story.get("description"),
        story.get("content"),
    )

    url = first(
        story.get("source_url"),
        story.get("url"),
        story.get("link"),
    )

    county = first(
        story.get("county")
    )

    if not county:
        county = detect_county(
            title + " " + summary
        )

        if county:
            story["county"] = county

    if len(title) < 20:
        return False

    if len(summary) < 60:
        return False

    if title.lower() in {
        "google news",
        "news",
        "latest news",
    }:
        return False

    if bad_text(
        title + " " + summary
    ):
        return False

    if not county:
        return False

    if url and blocked(url):
        return False

    if not confirmed(story):
        return False

    return True


# ============================================================
# EXISTING STRUCTURED STORY
# ============================================================

def load_structured_story():
    files = [
        STORY_FILE,
        DATA_DIR / "verified_story.json",
        DATA_DIR / "verified_story_data.json",
        DATA_DIR / "stories.json",
    ]

    best = None
    best_score = -1

    for path in files:
        data = read_json(path)

        if not data:
            continue

        records = []

        if isinstance(data, dict):
            if isinstance(
                data.get("stories"),
                list,
            ):
                records = data["stories"]
            else:
                records = [data]

        elif isinstance(data, list):
            records = data

        for story in records:
            if not isinstance(story, dict):
                continue

            if not quality_gate(story):
                continue

            score = 100

            if story.get("verified"):
                score += 40

            if story.get("verified_facts"):
                score += 30

            if story.get("official_statement"):
                score += 30

            if trusted(
                first(
                    story.get("source_url"),
                    story.get("url"),
                )
            ):
                score += 30

            if recover_image(story):
                score += 40

            if score > best_score:
                best = dict(story)
                best_score = score

    return best


# ============================================================
# RSS
# ============================================================

RSS_FEEDS = [
    (
        "People Daily",
        "https://peopledaily.digital/feed",
    ),
    (
        "Nation",
        "https://nation.africa/kenya/rss.xml",
    ),
    (
        "Citizen Digital",
        "https://citizen.digital/feed",
    ),
    (
        "The Star",
        "https://www.the-star.co.ke/rss",
    ),
    (
        "Capital FM",
        "https://www.capitalfm.co.ke/news/feed/",
    ),
    (
        "KBC",
        "https://www.kbc.co.ke/feed/",
    ),
]


def rss_candidates():
    result = []

    for source_name, feed_url in RSS_FEEDS:
        print("Checking:", source_name)

        try:
            response = fetch(feed_url)

            if response is None:
                continue

            feed = feedparser.parse(
                response.content
            )

            for entry in feed.entries[:40]:
                title = clean(
                    entry.get("title")
                )

                link = clean(
                    entry.get("link")
                )

                summary = clean(
                    entry.get("summary")
                )

                if not title or not link:
                    continue

                if blocked(link):
                    continue

                county = detect_county(
                    title + " " + summary
                )

                if not county:
                    continue

                result.append(
                    {
                        "title": title,
                        "summary": summary,
                        "source_name": source_name,
                        "source_url": link,
                        "published": first(
                            entry.get("published"),
                            entry.get("updated"),
                        ),
                        "county": county,
                    }
                )

        except Exception as exc:
            print(
                "RSS error:",
                source_name,
                exc,
            )

    return result


# ============================================================
# GOOGLE NEWS DISCOVERY
# GOOGLE IS NEVER TREATED AS THE SOURCE
# ============================================================

def google_candidates():
    result = []

    for county in COUNTIES:
        query = (
            f'"{county}" Kenya '
            f'after:{datetime.now().strftime("%Y-%m-%d")}'
        )

        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}"
            "&hl=en-KE&gl=KE&ceid=KE:en"
        )

        try:
            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:
                title = clean(
                    entry.get("title")
                )

                link = clean(
                    entry.get("link")
                )

                summary = clean(
                    entry.get("summary")
                )

                if not title or not link:
                    continue

                if title.lower() == "google news":
                    continue

                county_found = detect_county(
                    title + " " + summary
                ) or county

                result.append(
                    {
                        "title": title,
                        "summary": summary,
                        "source_url": link,
                        "source_name": "",
                        "published": first(
                            entry.get("published"),
                            entry.get("updated"),
                        ),
                        "county": county_found,
                    }
                )

        except Exception as exc:
            print(
                "Google discovery error:",
                county,
                exc,
            )

    return result


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def article_text(soup):
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
        ]
    ):
        tag.decompose()

    return clean(
        soup.get_text(
            " ",
            strip=True,
        )
    )


def verify_candidate(candidate):
    url = first(
        candidate.get("source_url"),
        candidate.get("url"),
        candidate.get("link"),
    )

    if not url:
        return None

    response = fetch(url)

    if response is None:
        return None

    final_url = response.url

    if blocked(final_url):
        return None

    try:
        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )
    except Exception:
        return None

    title = first(
        candidate.get("title"),
        soup.title.get_text(
            strip=True
        ) if soup.title else "",
    )

    description_tag = soup.find(
        "meta",
        attrs={
            "name": "description"
        },
    )

    description = ""

    if description_tag:
        description = clean(
            description_tag.get("content")
        )

    summary = first(
        candidate.get("summary"),
        description,
    )

    text = article_text(soup)

    if len(text) < 300:
        return None

    if bad_text(
        title + " " + summary
    ):
        return None

    county = first(
        candidate.get("county"),
        detect_county(
            title + " " + summary + " " + text[:3000]
        ),
    )

    if not county:
        return None

    image = ""

    for image_url in image_candidates(
        soup,
        final_url,
    ):
        if download_image(image_url):
            image = image_url
            break

    if not valid_image(IMAGE_FILE):
        return None

    result = {
        "title": title,
        "summary": shorten(
            summary,
            800,
        ),
        "description": shorten(
            text,
            1500,
        ),
        "source_name": first(
            candidate.get("source_name"),
            domain(final_url),
        ),
        "source_url": final_url,
        "source_domain": domain(final_url),
        "published": first(
            candidate.get("published"),
            candidate.get("date"),
        ),
        "county": county,
        "image": image,
        "local_image": str(IMAGE_FILE),
        "verified": trusted(final_url),
        "verified_facts": [],
        "editorial": {
            "confirmed": trusted(final_url)
        },
    }

    if not result["verified"]:
        return None

    return result


# ============================================================
# SCORE
# ============================================================

def score(story):
    value = 0

    if trusted(
        story.get("source_url", "")
    ):
        value += 50

    if story.get("verified"):
        value += 50

    if story.get("verified_facts"):
        value += 30

    if story.get("official_statement"):
        value += 30

    if valid_image(
        story.get("local_image", "")
    ):
        value += 40

    if len(
        story.get("summary", "")
    ) > 150:
        value += 20

    if bad_text(
        story.get("title", "")
        + " "
        + story.get("summary", "")
    ):
        value -= 300

    return value


# ============================================================
# SELECT STORY
# ============================================================

def select_story():
    print()
    print("=" * 60)
    print("STORY SELECTION")
    print("=" * 60)

    # FIRST: use properly structured verified story
    structured = load_structured_story()

    if structured:
        print(
            "Using existing structured verified story:"
        )
        print(
            structured.get("title")
        )

        if recover_image(structured):
            structured["score"] = (
                score(structured) + 200
            )

            return structured

    # SECOND: collect fresh stories
    candidates = (
        rss_candidates()
        + google_candidates()
    )

    # Deduplicate
    unique = []
    seen = set()

    for item in candidates:
        key = hashlib.sha1(
            (
                clean(item.get("title"))
                + "|"
                + clean(item.get("source_url"))
            ).encode("utf-8")
        ).hexdigest()

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    print(
        "Candidates:",
        len(unique)
    )

    verified = []

    for item in unique:
        print(
            "Checking:",
            shorten(
                item.get("title"),
                160,
            )
        )

        try:
            story = verify_candidate(
                item
            )

            if not story:
                continue

            if story.get("published"):
                if not recent(
                    story.get("published")
                ):
                    continue

            if not quality_gate(
                story
            ):
                continue

            if not recover_image(
                story
            ):
                continue

            story["score"] = score(
                story
            )

            verified.append(
                story
            )

        except Exception as exc:
            print(
                "Candidate failed:",
                exc,
            )

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking available sources."
        )

    verified.sort(
        key=lambda x: x.get(
            "score",
            0,
        ),
        reverse=True,
    )

    selected = verified[0]

    print()
    print("=" * 60)
    print("SELECTED STORY")
    print("=" * 60)
    print(
        "Title:",
        selected.get("title"),
    )
    print(
        "County:",
        selected.get("county"),
    )
    print(
        "Source:",
        selected.get("source_name"),
    )
    print(
        "Image:",
        selected.get("local_image"),
    )
    print("=" * 60)

    return selected


# ============================================================
# NORMALIZE
# ============================================================

def normalize_story(story):
    story = dict(story)

    story["title"] = first(
        story.get("title"),
        story.get("headline"),
    )

    story["summary"] = first(
        story.get("summary"),
        story.get("description"),
    )

    story["source_url"] = first(
        story.get("source_url"),
        story.get("url"),
        story.get("link"),
    )

    story["source_name"] = first(
        story.get("source_name"),
        story.get("publisher"),
        domain(
            story.get("source_url")
        ),
        "Verified report",
    )

    story["county"] = first(
        story.get("county"),
        detect_county(
            story["title"]
            + " "
            + story["summary"]
        ),
    )

    image = recover_image(
        story
    )

    if not image:
        raise RuntimeError(
            "Selected story has no usable article image."
        )

    story["local_image"] = str(
        IMAGE_FILE
    )

    story["verified"] = True

    if not isinstance(
        story.get("editorial"),
        dict,
    ):
        story["editorial"] = {}

    story["editorial"]["confirmed"] = True
    story["editorial"]["one_story_reel"] = True

    return story


# ============================================================
# VIDEO VALIDATION
# ============================================================

def validate_story_for_video(story):
    if not isinstance(
        story,
        dict,
    ):
        raise RuntimeError(
            "Selected story is invalid."
        )

    if len(
        first(story.get("title"))
    ) < 15:
        raise RuntimeError(
            "Story has no usable title."
        )

    if not first(
        story.get("summary")
    ):
        raise RuntimeError(
            "Story has no usable summary."
        )

    if not first(
        story.get("county")
    ):
        raise RuntimeError(
            "Story has no county."
        )

    image = recover_image(
        story
    )

    if not image:
        raise RuntimeError(
            "No usable article image URL or "
            "local article image was provided."
        )

    if not valid_image(image):
        raise RuntimeError(
            "Recovered article image failed validation."
        )

    story["local_image"] = str(
        IMAGE_FILE
    )

    return True


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = first(
        story.get("title"),
        "Regional update",
    )

    county = first(
        story.get("county"),
        "the Rift Valley",
    )

    summary = shorten(
        first(
            story.get("summary"),
            story.get("description"),
        ),
        500,
    )

    statement = shorten(
        first(
            story.get("official_statement"),
            story.get("official_quote"),
        ),
        250,
    )

    speaker = first(
        story.get("official_source"),
        story.get("speaker"),
        story.get("quoted_person"),
    )

    parts = [
        f"Here is the latest verified update from {county}.",
        title,
    ]

    if summary:
        parts.append(summary)

    if statement:
        if speaker:
            parts.append(
                f"{speaker} said {statement}"
            )
        else:
            parts.append(
                f"Officials said {statement}"
            )

    parts.append(
        "Rift Valley Watch will continue "
        "tracking verified developments across the region."
    )

    narration = clean(
        " ".join(parts)
    )

    for phrase in [
        "Google News",
        "google news",
        "Facebook",
        "facebook",
        "Instagram",
        "instagram",
        "YouTube",
        "youtube",
        "TikTok",
        "tiktok",
    ]:
        narration = narration.replace(
            phrase,
            "",
        )

    return clean(narration)


# ============================================================
# SCRIPT
# ============================================================

def build_script(story):
    narration = build_narration(
        story
    )

    if not narration:
        raise RuntimeError(
            "No narration was generated."
        )

    return {
        "project": "Rift Valley Watch",
        "title": story["title"],
        "county": story["county"],
        "source_name": story["source_name"],
        "source_url": story["source_url"],
        "image": story.get("image", ""),
        "local_image": story["local_image"],
        "narration": narration,
        "duration_target": 35,
        "one_story": True,
    }


# ============================================================
# GENERATE VIDEO
# ============================================================

def generate_video(story):
    validate_story_for_video(
        story
    )

    script = build_script(
        story
    )

    write_json(
        STORY_FILE,
        story,
    )

    write_json(
        SELECTED_STORY_FILE,
        story,
    )

    write_json(
        SCRIPT_FILE,
        script,
    )

    write_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    print()
    print("=" * 60)
    print("VIDEO GENERATION")
    print("=" * 60)
    print(
        "Image:",
        story["local_image"],
    )

    try:
        from rift_valley_video_generator import (
            generate_video as video_generator
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not import "
            "rift_valley_video_generator.py: "
            + str(exc)
        )

    output = video_generator(
        story,
        script,
    )

    if output is None:
        output = VIDEO_FILE

    output = Path(output)

    if not output.exists():
        if VIDEO_FILE.exists():
            output = VIDEO_FILE

    if not output.exists():
        raise RuntimeError(
            "Video generator completed but "
            "no final MP4 was created."
        )

    return output


# ============================================================
# FINAL MP4 QC
# ============================================================

def final_video_qc(path):
    import subprocess

    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe failed."
        )

    data = json.loads(
        result.stdout
    )

    video = None
    audio = None

    for stream in data.get(
        "streams",
        [],
    ):
        if stream.get("codec_type") == "video":
            video = stream

        if stream.get("codec_type") == "audio":
            audio = stream

    if video is None:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if audio is None:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video.get("width", 0)
    )

    height = int(
        video.get("height", 0)
    )

    vcodec = video.get(
        "codec_name"
    )

    acodec = audio.get(
        "codec_name"
    )

    duration = float(
        data.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
    )

    if width != 1080:
        raise RuntimeError(
            f"Wrong width: {width}"
        )

    if height != 1920:
        raise RuntimeError(
            f"Wrong height: {height}"
        )

    if vcodec != "h264":
        raise RuntimeError(
            f"Wrong video codec: {vcodec}"
        )

    if acodec != "aac":
        raise RuntimeError(
            f"Wrong audio codec: {acodec}"
        )

    if duration < 31.5:
        raise RuntimeError(
            f"Video too short: {duration:.2f}s"
        )

    if duration > 38.5:
        raise RuntimeError(
            f"Video too long: {duration:.2f}s"
        )

    print()
    print("=" * 60)
    print("FINAL VIDEO QC PASSED")
    print("=" * 60)
    print(
        f"Resolution: {width}x{height}"
    )
    print(
        f"Duration: {duration:.2f}s"
    )
    print(
        f"Video: {vcodec}"
    )
    print(
        f"Audio: {acodec}"
    )
    print(
        f"MP4: {path}"
    )
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_directories()

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH")
    print("AUTOMATED VERIFIED NEWS REEL")
    print("=" * 60)

    story = select_story()

    if not story:
        raise RuntimeError(
            "No story selected."
        )

    story = normalize_story(
        story
    )

    validate_story_for_video(
        story
    )

    video = generate_video(
        story
    )

    final_video_qc(
        video
    )

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH COMPLETE")
    print("=" * 60)
    print(
        "Story:",
        story["title"],
    )
    print(
        "County:",
        story["county"],
    )
    print(
        "Source:",
        story["source_name"],
    )
    print(
        "Image:",
        story["local_image"],
    )
    print(
        "MP4:",
        video,
    )
    print(
        "YouTube upload: DISABLED"
    )
    print(
        "STATUS: SUCCESS"
    )
    print("=" * 60)

    return video


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print()
        print("=" * 60)
        print("RIFT VALLEY WATCH FAILED")
        print("=" * 60)
        print(
            type(exc).__name__ + ":",
            str(exc),
        )
        print("=" * 60)

        traceback.print_exc()

        raise
