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

DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"
VIDEO_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# SETTINGS
# ============================================================

TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

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
        "kaplong",
        "longisa",
        "sigor",
        "chebunyo",
    ],
    "Kericho": [
        "kericho",
        "ainamoi",
        "belgut",
        "bureti",
        "kipkelion",
        "litein",
        "londiani",
        "chepseon",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "bahati",
        "subukia",
        "rongai",
        "njoro",
        "kuresoi",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "chesumei",
        "emgwen",
        "aldai",
        "nandi hills",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "ainabkoi",
        "kapseret",
        "kesses",
        "soy",
        "turbo",
        "moiben",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo",
        "marakwet",
        "elgeyo-marakwet",
        "it-en",
        "iten",
        "keiyo",
        "keiyo north",
        "keiyo south",
        "marakwet east",
        "marakwet west",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "pokot",
        "pokot south",
        "pokot central",
        "pokot north",
        "kipkomo",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "emurua dikir",
        "narok north",
        "narok south",
        "narok west",
        "narok east",
    ],
}


# ============================================================
# TRUSTED / BLOCKED SOURCES
# ============================================================

TRUSTED_DOMAINS = {
    "peopledaily.digital",
    "nation.africa",
    "citizen.digital",
    "the-star.co.ke",
    "capitalfm.co.ke",
    "kbc.co.ke",
    "standardmedia.co.ke",
    "kenyanews.go.ke",
    "president.go.ke",
    "deputypresident.go.ke",
    "governmentpress.go.ke",
    "parliament.go.ke",
}

BLOCKED_DOMAINS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "google.com",
    "news.google.com",
    "youtube.com",
    "www.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
}

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
    "googleusercontent",
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "favicon",
    "logo",
    "placeholder",
    "avatar",
    "sprite",
    "icon",
    "default-image",
    "default_image",
    "no-image",
    "no_image",
]


# ============================================================
# RSS SOURCES
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


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def first(*values):
    for value in values:
        if value is not None and str(value).strip():
            return value
    return ""


def shorten(text, limit=180):
    text = clean(text)

    if len(text) <= limit:
        return text

    shortened = text[:limit].rsplit(" ", 1)[0]
    return shortened.rstrip(" ,.;:") + "…"


def now_utc():
    return datetime.now(timezone.utc)


def parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    text = str(value).strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except Exception:
        return None


def is_recent(value, hours=72):
    dt = parse_date(value)

    if not dt:
        return False

    age = now_utc() - dt

    return timedelta(hours=-2) <= age <= timedelta(hours=hours)


def domain_of(url):
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def is_blocked_domain(url):
    domain = domain_of(url)

    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return True

    return False


def is_trusted_domain(url):
    domain = domain_of(url)

    for trusted in TRUSTED_DOMAINS:
        if domain == trusted or domain.endswith("." + trusted):
            return True

    return False


def publisher_from_url(url):
    domain = domain_of(url)

    mapping = {
        "peopledaily.digital": "People Daily",
        "nation.africa": "Nation",
        "citizen.digital": "Citizen Digital",
        "the-star.co.ke": "The Star",
        "capitalfm.co.ke": "Capital FM",
        "kbc.co.ke": "KBC",
        "standardmedia.co.ke": "The Standard",
        "kenyanews.go.ke": "Kenya News Agency",
        "president.go.ke": "State House",
        "deputypresident.go.ke": "Office of the Deputy President",
        "governmentpress.go.ke": "Government Press",
        "parliament.go.ke": "Parliament of Kenya",
    }

    if domain in mapping:
        return mapping[domain]

    return domain.replace(".co.ke", "").replace(".com", "").title()


# ============================================================
# JSON
# ============================================================

def load_json(path):
    try:
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return None


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# HTTP
# ============================================================

def fetch(url, timeout=TIMEOUT):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        response.raise_for_status()

        return response

    except Exception as exc:
        print(f"FETCH FAILED: {url}")
        print(f"Reason: {exc}")
        return None


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(title="", summary="", text="", url=""):
    combined = " ".join(
        [
            clean(title),
            clean(summary),
            clean(text),
            clean(url),
        ]
    ).lower()

    best_county = None
    best_score = 0

    for county, aliases in COUNTY_ALIASES.items():
        score = 0

        for alias in aliases:
            if re.search(
                r"\b" + re.escape(alias.lower()) + r"\b",
                combined,
            ):
                score += 1

        if score > best_score:
            best_score = score
            best_county = county

    return best_county


# ============================================================
# ARTICLE TEXT EXTRACTION
# ============================================================

def article_soup(url):
    response = fetch(url)

    if not response:
        return None, None

    try:
        soup = BeautifulSoup(
            response.content,
            "html.parser",
        )

        return soup, response.url

    except Exception:
        return None, None


def extract_article_text(soup):
    if not soup:
        return ""

    paragraphs = []

    for tag in soup.find_all(
        ["article", "main", "section"]
    ):
        for p in tag.find_all("p"):
            text = clean(p.get_text(" ", strip=True))

            if len(text) >= 30:
                paragraphs.append(text)

    if not paragraphs:
        for p in soup.find_all("p"):
            text = clean(p.get_text(" ", strip=True))

            if len(text) >= 30:
                paragraphs.append(text)

    seen = set()
    output = []

    for paragraph in paragraphs:
        key = paragraph.lower()

        if key in seen:
            continue

        seen.add(key)
        output.append(paragraph)

    return " ".join(output[:80])


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_url_is_bad(url):
    if not url:
        return True

    lower = url.lower()

    if lower.startswith("data:"):
        return True

    for term in BAD_IMAGE_TERMS:
        if term in lower:
            return True

    return False


def valid_image_bytes(data):
    if not data or len(data) < 5000:
        return False

    if data[:3] == b"\xff\xd8\xff":
        return True

    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True

    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True

    return False


def save_image_bytes(data):
    if not valid_image_bytes(data):
        return False

    try:
        from PIL import Image
        from io import BytesIO

        image = Image.open(BytesIO(data))
        image.load()

        width, height = image.size

        print(
            f"IMAGE FOUND: {width}x{height}"
        )

        if width < 250 or height < 200:
            print("IMAGE REJECTED: too small")
            return False

        if width < height and width < 500:
            print("IMAGE REJECTED: narrow image")
            return False

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        else:
            image = image.convert("RGB")

        image.save(
            IMAGE_FILE,
            "JPEG",
            quality=95,
        )

        print(
            f"IMAGE SAVED: {IMAGE_FILE}"
        )

        return True

    except Exception as exc:
        print(f"IMAGE SAVE FAILED: {exc}")
        return False


def download_image(url):
    if not url:
        return False

    if image_url_is_bad(url):
        print(
            f"IMAGE URL REJECTED: {url}"
        )
        return False

    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept": (
                    "image/avif,image/webp,"
                    "image/apng,image/svg+xml,"
                    "image/*,*/*;q=0.8"
                ),
            },
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = response.url

        if image_url_is_bad(final_url):
            print(
                f"IMAGE REDIRECT REJECTED: {final_url}"
            )
            return False

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if (
            "image" not in content_type
            and not valid_image_bytes(response.content)
        ):
            print(
                f"NOT AN IMAGE: {content_type}"
            )
            return False

        return save_image_bytes(
            response.content
        )

    except Exception as exc:
        print(
            f"IMAGE DOWNLOAD FAILED: {url}"
        )
        print(exc)
        return False


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(soup, base_url):
    candidates = []

    if not soup:
        return candidates

    # --------------------------------------------------------
    # META
    # --------------------------------------------------------

    selectors = [
        ("meta", {"property": "og:image"}),
        ("meta", {"property": "og:image:url"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
        ("meta", {"itemprop": "image"}),
    ]

    for tag_name, attrs in selectors:
        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):
            value = tag.get("content")

            if value:
                candidates.append(
                    urljoin(base_url, value)
                )

    # --------------------------------------------------------
    # LINK IMAGE
    # --------------------------------------------------------

    for tag in soup.find_all(
        "link",
        href=True,
    ):
        rel = " ".join(
            tag.get("rel", [])
        ).lower()

        if "image_src" in rel:
            candidates.append(
                urljoin(
                    base_url,
                    tag["href"],
                )
            )

    # --------------------------------------------------------
    # ARTICLE IMG TAGS
    # --------------------------------------------------------

    article_containers = []

    article = soup.find("article")

    if article:
        article_containers.append(article)

    main = soup.find("main")

    if main:
        article_containers.append(main)

    article_containers.append(soup)

    for container in article_containers:
        for img in container.find_all(
            "img"
        ):
            attrs = [
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-image",
                "data-lazy",
            ]

            for attr in attrs:
                value = img.get(attr)

                if value:
                    candidates.append(
                        urljoin(
                            base_url,
                            value,
                        )
                    )

            srcset = img.get("srcset")

            if srcset:
                for part in srcset.split(","):
                    value = part.strip().split(" ")[0]

                    if value:
                        candidates.append(
                            urljoin(
                                base_url,
                                value,
                            )
                        )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    final = []
    seen = set()

    for url in candidates:
        url = str(url).strip()

        if not url:
            continue

        if image_url_is_bad(url):
            continue

        if url in seen:
            continue

        seen.add(url)
        final.append(url)

    return final


def recover_from_article(url):
    if not url:
        return False, ""

    if is_blocked_domain(url):
        return False, ""

    print("")
    print("-" * 60)
    print("IMAGE RECOVERY")
    print("-" * 60)
    print(f"Article: {url}")

    soup, final_url = article_soup(url)

    if not soup:
        print("ARTICLE COULD NOT BE FETCHED")
        return False, ""

    candidates = extract_image_candidates(
        soup,
        final_url or url,
    )

    print(
        f"Image candidates found: {len(candidates)}"
    )

    for candidate in candidates:
        print(
            f"Trying image: {candidate}"
        )

        if download_image(candidate):
            return True, candidate

    print(
        "No usable article image found."
    )

    return False, ""


# ============================================================
# LOCAL IMAGE
# ============================================================

def recover_local_image():
    if not IMAGE_FILE.exists():
        return False

    try:
        if IMAGE_FILE.stat().st_size < 5000:
            return False

        from PIL import Image

        image = Image.open(IMAGE_FILE)
        image.verify()

        print(
            f"Existing local image found: "
            f"{IMAGE_FILE}"
        )

        return True

    except Exception:
        return False


# ============================================================
# STORY QUALITY
# ============================================================

def story_quality_gate(story):
    if not isinstance(story, dict):
        return False, "Story is not a dictionary."

    title = clean(
        first(
            story.get("title"),
            story.get("headline"),
        )
    )

    summary = clean(
        first(
            story.get("summary"),
            story.get("description"),
            story.get("content"),
        )
    )

    url = clean(
        first(
            story.get("url"),
            story.get("link"),
            story.get("article_url"),
        )
    )

    source = clean(
        first(
            story.get("source"),
            story.get("publisher"),
        )
    )

    if not title:
        return False, "Missing title."

    if len(title) < 20:
        return False, "Title too short."

    if title.lower() in {
        "google news",
        "facebook",
        "news",
    }:
        return False, "Invalid title."

    if not summary or len(summary) < 50:
        return False, "Summary too short."

    bad_phrases = [
        "google news",
        "sign in to google",
        "facebook",
        "see more stories",
        "google news app",
        "news.google.com",
    ]

    combined = (
        title + " " +
        summary + " " +
        source
    ).lower()

    for phrase in bad_phrases:
        if phrase in combined:
            return False, (
                f"Blocked boilerplate: {phrase}"
            )

    if url and is_blocked_domain(url):
        return False, "Blocked source domain."

    county = first(
        story.get("county"),
        detect_county(
            title,
            summary,
            story.get("content", ""),
            url,
        ),
    )

    if not county:
        return False, "No Rift Valley county detected."

    story["county"] = county

    return True, "OK"


# ============================================================
# STRUCTURED STORY
# ============================================================

def load_existing_structured_story():
    story = load_json(STORY_FILE)

    if not story:
        return None

    ok, reason = story_quality_gate(story)

    if not ok:
        print(
            f"Existing story rejected: {reason}"
        )
        return None

    print("")
    print("=" * 60)
    print("STRUCTURED STORY FOUND")
    print("=" * 60)
    print(
        clean(
            first(
                story.get("title"),
                story.get("headline"),
            )
        )
    )

    return story


# ============================================================
# RSS
# ============================================================

def parse_feed(source_name, feed_url):
    print("")
    print(
        f"Checking RSS: {source_name}"
    )

    try:
        response = fetch(feed_url)

        if not response:
            return []

        feed = feedparser.parse(
            response.content
        )

        results = []

        for entry in feed.entries[:40]:
            title = clean(
                entry.get("title", "")
            )

            link = clean(
                entry.get("link", "")
            )

            summary = clean(
                first(
                    entry.get("summary"),
                    entry.get("description"),
                )
            )

            published = first(
                entry.get("published"),
                entry.get("updated"),
            )

            if not title or not link:
                continue

            county = detect_county(
                title,
                summary,
                "",
                link,
            )

            if not county:
                continue

            if not is_recent(
                published,
                hours=96,
            ):
                continue

            if is_blocked_domain(link):
                continue

            results.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "published": published,
                    "source": source_name,
                    "county": county,
                }
            )

        return results

    except Exception as exc:
        print(
            f"RSS FAILED: {source_name}"
        )
        print(exc)
        return []


def collect_rss_candidates():
    candidates = []

    for source_name, feed_url in RSS_FEEDS:
        candidates.extend(
            parse_feed(
                source_name,
                feed_url,
            )
        )

    return candidates


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def verify_article(candidate):
    url = candidate.get("url", "")

    if not url:
        return None

    if is_blocked_domain(url):
        return None

    soup, final_url = article_soup(url)

    if not soup:
        return None

    title = clean(
        first(
            candidate.get("title"),
            soup.find("h1").get_text(
                " ",
                strip=True,
            )
            if soup.find("h1")
            else "",
        )
    )

    summary = clean(
        candidate.get("summary", "")
    )

    article_text = extract_article_text(
        soup
    )

    if len(article_text) < 100:
        return None

    county = detect_county(
        title,
        summary,
        article_text,
        final_url or url,
    )

    if not county:
        return None

    image_candidates = extract_image_candidates(
        soup,
        final_url or url,
    )

    source = candidate.get(
        "source"
    ) or publisher_from_url(
        final_url or url
    )

    result = {
        "title": title,
        "headline": title,
        "summary": summary,
        "content": article_text[:12000],
        "url": final_url or url,
        "source": source,
        "publisher": source,
        "county": county,
        "published": candidate.get(
            "published"
        ),
        "image_candidates": image_candidates,
        "verified": True,
        "editorial": {
            "confirmed": True,
        },
    }

    return result


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):
    score = 0

    title = clean(
        story.get("title", "")
    ).lower()

    summary = clean(
        story.get("summary", "")
    ).lower()

    content = clean(
        story.get("content", "")
    ).lower()

    url = story.get("url", "")

    if is_trusted_domain(url):
        score += 40

    if story.get("verified"):
        score += 25

    if story.get("editorial", {}).get(
        "confirmed"
    ):
        score += 25

    if len(content) >= 1000:
        score += 15

    if story.get("image_candidates"):
        score += 15

    important_terms = [
        "project",
        "road",
        "hospital",
        "school",
        "water",
        "development",
        "county",
        "government",
        "funding",
        "construction",
        "launch",
        "investment",
        "security",
        "business",
        "health",
        "education",
        "infrastructure",
    ]

    for term in important_terms:
        if term in title:
            score += 3

    if "google news" in title:
        score -= 1000

    if "facebook" in title:
        score -= 1000

    if "google news" in summary:
        score -= 1000

    return score


# ============================================================
# STORY SELECTION
# ============================================================

def select_story():
    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH STORY SELECTION")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. EXISTING STRUCTURED STORY
    # --------------------------------------------------------

    structured = load_existing_structured_story()

    if structured:
        story = dict(structured)

        # Try local image first.
        if not recover_local_image():
            article_url = first(
                story.get("url"),
                story.get("article_url"),
            )

            recovered, image_url = (
                recover_from_article(
                    article_url
                )
            )

            if recovered:
                story["image_url"] = image_url
                story["local_image"] = str(
                    IMAGE_FILE
                )

        else:
            story["local_image"] = str(
                IMAGE_FILE
            )

        if IMAGE_FILE.exists():
            story["local_image"] = str(
                IMAGE_FILE
            )

        save_json(
            SELECTED_STORY_FILE,
            story,
        )

        return story

    # --------------------------------------------------------
    # 2. RSS DISCOVERY
    # --------------------------------------------------------

    candidates = collect_rss_candidates()

    print(
        f"RSS candidates: {len(candidates)}"
    )

    verified = []

    for candidate in candidates:
        article = verify_article(
            candidate
        )

        if not article:
            continue

        ok, reason = story_quality_gate(
            article
        )

        if not ok:
            print(
                f"Rejected: {reason}"
            )
            continue

        article["score"] = score_story(
            article
        )

        verified.append(article)

    if not verified:
        raise RuntimeError(
            "No recent verified Rift Valley story "
            "passed the content-quality gate."
        )

    verified.sort(
        key=lambda x: (
            x.get("score", 0),
            parse_date(
                x.get("published")
            )
            or datetime(
                1970,
                1,
                1,
                tzinfo=timezone.utc,
            ),
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # 3. IMAGE RECOVERY
    # --------------------------------------------------------

    selected = None

    for candidate in verified:
        print("")
        print(
            f"IMAGE CHECK: {candidate['title']}"
        )

        if recover_local_image():
            selected = candidate
            candidate["local_image"] = str(
                IMAGE_FILE
            )
            break

        image_candidates = candidate.get(
            "image_candidates",
            [],
        )

        recovered = False

        for image_url in image_candidates:
            if download_image(image_url):
                candidate["image_url"] = image_url
                candidate["local_image"] = str(
                    IMAGE_FILE
                )
                recovered = True
                break

        if not recovered:
            recovered, image_url = (
                recover_from_article(
                    candidate.get("url", "")
                )
            )

            if recovered:
                candidate["image_url"] = (
                    image_url
                )
                candidate["local_image"] = str(
                    IMAGE_FILE
                )

        if recovered:
            selected = candidate
            break

    if not selected:
        raise RuntimeError(
            "No verified story has a usable article "
            "image after all image recovery methods."
        )

    # --------------------------------------------------------
    # FINAL STORY VALIDATION
    # --------------------------------------------------------

    ok, reason = story_quality_gate(
        selected
    )

    if not ok:
        raise RuntimeError(
            f"Selected story failed final validation: "
            f"{reason}"
        )

    if not IMAGE_FILE.exists():
        raise RuntimeError(
            "Image recovery reported success but "
            "assets/source/story_image.jpg does not exist."
        )

    selected["local_image"] = str(
        IMAGE_FILE
    )

    selected["image_path"] = str(
        IMAGE_FILE
    )

    selected["image_verified"] = True

    save_json(
        SELECTED_STORY_FILE,
        selected,
    )

    print("")
    print("=" * 70)
    print("SELECTED STORY")
    print("=" * 70)
    print(
        selected.get("title")
    )
    print(
        f"County: {selected.get('county')}"
    )
    print(
        f"Source: {selected.get('source')}"
    )
    print(
        f"Score: {selected.get('score', 0)}"
    )
    print(
        f"Image: {IMAGE_FILE}"
    )
    print("=" * 70)

    return selected


# ============================================================
# STORY NORMALIZATION
# ============================================================

def normalize_story(story):
    title = clean(
        first(
            story.get("title"),
            story.get("headline"),
        )
    )

    summary = clean(
        first(
            story.get("summary"),
            story.get("description"),
            story.get("content"),
        )
    )

    content = clean(
        first(
            story.get("content"),
            summary,
        )
    )

    url = clean(
        first(
            story.get("url"),
            story.get("article_url"),
            story.get("link"),
        )
    )

    source = clean(
        first(
            story.get("source"),
            story.get("publisher"),
            publisher_from_url(url),
        )
    )

    county = first(
        story.get("county"),
        detect_county(
            title,
            summary,
            content,
            url,
        ),
    )

    normalized = dict(story)

    normalized.update(
        {
            "title": title,
            "headline": title,
            "summary": summary,
            "content": content,
            "url": url,
            "source": source,
            "publisher": source,
            "county": county,
            "local_image": str(
                IMAGE_FILE
            ),
        }
    )

    return normalized


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean(
        story.get("title")
    )

    county = clean(
        story.get("county")
    )

    summary = clean(
        story.get("summary")
    )

    source = clean(
        story.get("source")
    )

    content = clean(
        story.get("content")
    )

    if not summary:
        summary = content[:400]

    # Remove common garbage.
    for phrase in [
        "Google News",
        "Facebook",
        "Instagram",
        "YouTube",
        "TikTok",
        "Read more",
        "Click here",
    ]:
        summary = re.sub(
            re.escape(phrase),
            "",
            summary,
            flags=re.IGNORECASE,
        )

    summary = re.sub(
        r"\s+",
        " ",
        summary,
    ).strip()

    # Keep narration factual and natural.
    parts = []

    parts.append(
        f"Rift Valley Watch. "
        f"Here is the latest update from {county}."
    )

    parts.append(title + ".")

    if summary:
        parts.append(
            shorten(
                summary,
                430,
            )
        )

    if source:
        parts.append(
            f"The report is from {source}."
        )

    narration = " ".join(parts)

    narration = re.sub(
        r"\s+",
        " ",
        narration,
    ).strip()

    return narration


# ============================================================
# SCRIPT
# ============================================================

def build_script(story):
    narration = build_narration(
        story
    )

    county = clean(
        story.get("county")
    )

    title = clean(
        story.get("title")
    )

    summary = clean(
        story.get("summary")
    )

    source = clean(
        story.get("source")
    )

    script = {
        "title": title,
        "county": county,
        "source": source,
        "narration": narration,
        "duration_target": 35,
        "local_image": str(
            IMAGE_FILE
        ),
        "scenes": [
            {
                "type": "headline",
                "title": title,
            },
            {
                "type": "location",
                "title": county,
            },
            {
                "type": "facts",
                "text": shorten(
                    summary,
                    220,
                ),
            },
            {
                "type": "details",
                "text": shorten(
                    story.get(
                        "content",
                        "",
                    ),
                    260,
                ),
            },
            {
                "type": "source",
                "title": source,
            },
        ],
    }

    save_json(
        SCRIPT_FILE,
        script,
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    return script


# ============================================================
# VIDEO GENERATION
# ============================================================

def generate_video(story):
    print("")
    print("=" * 70)
    print("VIDEO GENERATION")
    print("=" * 70)

    if not IMAGE_FILE.exists():
        raise RuntimeError(
            "No local article image exists before "
            "video generation."
        )

    story = normalize_story(
        story
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # The current video generator accepts ONE argument.
    # Do not pass script as a second positional argument.
    # --------------------------------------------------------

    from rift_valley_video_generator import (
        generate_video as video_generator
    )

    output = video_generator(
        story
    )

    if output:
        output_path = Path(
            str(output)
        )

        if output_path.exists():
            print(
                f"Video generator returned: "
                f"{output_path}"
            )

            # Copy/normalize final location.
            if output_path.resolve() != (
                VIDEO_FILE.resolve()
            ):
                import shutil

                shutil.copy2(
                    output_path,
                    VIDEO_FILE,
                )

    if not VIDEO_FILE.exists():
        raise RuntimeError(
            "Video generator completed but "
            "the expected MP4 was not created."
        )

    return VIDEO_FILE


# ============================================================
# FFPROBE
# ============================================================

def ffprobe_json(path):
    import subprocess

    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe failed:\n"
            + result.stderr
        )

    return json.loads(
        result.stdout
    )


# ============================================================
# FINAL VIDEO QC
# ============================================================

def final_video_qc(path):
    print("")
    print("=" * 70)
    print("FINAL VIDEO QC")
    print("=" * 70)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if path.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    info = ffprobe_json(
        path
    )

    streams = info.get(
        "streams",
        [],
    )

    video_stream = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "audio"
        ),
        None,
    )

    if not video_stream:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if not audio_stream:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video_stream.get(
            "width",
            0,
        )
    )

    height = int(
        video_stream.get(
            "height",
            0,
        )
    )

    codec = video_stream.get(
        "codec_name",
        "",
    )

    audio_codec = audio_stream.get(
        "codec_name",
        "",
    )

    duration_text = (
        info.get("format", {})
        .get("duration", "0")
    )

    duration = float(
        duration_text
    )

    print(
        f"Resolution: {width}x{height}"
    )

    print(
        f"Video codec: {codec}"
    )

    print(
        f"Audio codec: {audio_codec}"
    )

    print(
        f"Duration: {duration:.2f}s"
    )

    if width != 1080 or height != 1920:
        raise RuntimeError(
            f"Wrong video resolution: "
            f"{width}x{height}"
        )

    if codec != "h264":
        raise RuntimeError(
            f"Wrong video codec: {codec}"
        )

    if audio_codec not in {
        "aac",
        "mp3",
    }:
        raise RuntimeError(
            f"Unsupported audio codec: "
            f"{audio_codec}"
        )

    if not 31.5 <= duration <= 38.5:
        raise RuntimeError(
            f"Video duration outside target range: "
            f"{duration:.2f}s"
        )

    print(
        "FINAL VIDEO QC: PASSED"
    )

    return True


# ============================================================
# FINAL DATA DIRECTORY REPORT
# ============================================================

def report_files():
    print("")
    print("=" * 70)
    print("FINAL FILE CHECK")
    print("=" * 70)

    for directory in [
        DATA_DIR,
        SOURCE_DIR,
        OUTPUT_DIR,
    ]:
        print("")
        print(
            f"Directory: {directory}"
        )

        if not directory.exists():
            print(
                "DIRECTORY DOES NOT EXIST"
            )
            continue

        for item in sorted(
            directory.iterdir()
        ):
            if item.is_file():
                try:
                    size = item.stat().st_size
                    print(
                        f"  {item.name} "
                        f"({size:,} bytes)"
                    )
                except Exception:
                    print(
                        f"  {item.name}"
                    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("AUTOMATED NEWS VIDEO PIPELINE")
    print("=" * 70)

    print(
        f"Root: {ROOT}"
    )

    print(
        f"Data: {DATA_DIR}"
    )

    print(
        f"Image: {IMAGE_FILE}"
    )

    print(
        f"Output: {VIDEO_FILE}"
    )

    try:
        # ----------------------------------------------------
        # STORY
        # ----------------------------------------------------

        story = select_story()

        # ----------------------------------------------------
        # NORMALIZE
        # ----------------------------------------------------

        story = normalize_story(
            story
        )

        # ----------------------------------------------------
        # FINAL STORY CHECK
        # ----------------------------------------------------

        ok, reason = story_quality_gate(
            story
        )

        if not ok:
            raise RuntimeError(
                f"Final story rejected: {reason}"
            )

        # ----------------------------------------------------
        # IMAGE MUST EXIST
        # ----------------------------------------------------

        if not IMAGE_FILE.exists():
            raise RuntimeError(
                "No article image available at "
                f"{IMAGE_FILE}"
            )

        story["local_image"] = str(
            IMAGE_FILE
        )

        story["image_path"] = str(
            IMAGE_FILE
        )

        story["image_verified"] = True

        # ----------------------------------------------------
        # SCRIPT
        # ----------------------------------------------------

        script = build_script(
            story
        )

        if not script.get(
            "narration"
        ):
            raise RuntimeError(
                "No narration was generated."
            )

        # ----------------------------------------------------
        # SAVE SELECTED STORY AGAIN
        # ----------------------------------------------------

        save_json(
            SELECTED_STORY_FILE,
            story,
        )

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        video = generate_video(
            story
        )

        # ----------------------------------------------------
        # QC
        # ----------------------------------------------------

        final_video_qc(
            video
        )

        # ----------------------------------------------------
        # REPORT
        # ----------------------------------------------------

        report_files()

        print("")
        print("=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print(
            f"FINAL MP4: {VIDEO_FILE}"
        )
        print(
            f"SIZE: {VIDEO_FILE.stat().st_size:,} bytes"
        )
        print("=" * 70)

        return 0

    except Exception as exc:
        print("")
        print("=" * 70)
        print("RIFT VALLEY WATCH FAILED")
        print("=" * 70)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print("")
        traceback.print_exc()

        print("")
        report_files()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
