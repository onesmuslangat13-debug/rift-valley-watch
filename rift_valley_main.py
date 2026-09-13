import json
import os
import re
import sys
import time
import hashlib
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# AUTOMATIC MULTI-COUNTY NEWS ENGINE
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"

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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8"
        ),
    }
)

BAD_TERMS = [
    "google news",
    "facebook",
    "sign in",
    "subscribe",
    "advertisement",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "youtube",
    "instagram",
    "tiktok",
]

POSITIVE_TERMS = [
    "county",
    "government",
    "project",
    "development",
    "road",
    "hospital",
    "school",
    "water",
    "market",
    "budget",
    "construction",
    "official",
    "launch",
    "inspection",
    "statement",
    "governor",
    "deputy president",
    "minister",
    "mp",
    "senator",
    "ward",
    "constituency",
    "kenya",
]

IMAGE_BAD_TERMS = [
    "logo",
    "icon",
    "avatar",
    "favicon",
    "sprite",
    "placeholder",
    "default",
    "banner",
    "advert",
    "facebook",
    "google",
    "twitter",
    "x.com",
    "youtube",
]


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def shorten(text, maximum=500):
    text = clean_text(text)

    if len(text) <= maximum:
        return text

    text = text[:maximum]

    if " " in text:
        text = text.rsplit(" ", 1)[0]

    return text.rstrip(" ,.;:-") + "..."


def valid_text(value, minimum=20):
    value = clean_text(value)

    if len(value) < minimum:
        return False

    lowered = value.lower()

    bad_count = sum(
        1 for term in BAD_TERMS
        if term in lowered
    )

    return bad_count < 2


def normalize_url(url, base_url=""):
    url = clean_text(url)

    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url

    if base_url:
        url = urllib.parse.urljoin(base_url, url)

    if not url.startswith(("http://", "https://")):
        return ""

    return url


# ============================================================
# HTTP
# ============================================================

def fetch_response(url, timeout=25):
    return SESSION.get(
        url,
        timeout=timeout,
        allow_redirects=True,
    )


def fetch_html(url, timeout=25):
    response = fetch_response(url, timeout)

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "",
    ).lower()

    if (
        "text/html" not in content_type
        and "application/xhtml" not in content_type
        and not response.text
    ):
        raise RuntimeError(
            "Publisher did not return an HTML page."
        )

    return response.text, response.url


# ============================================================
# SEARCH
# ============================================================

def build_queries():
    queries = []

    for county in COUNTIES:
        queries.extend(
            [
                f'"{county}" Kenya latest news',
                f'"{county} County" latest development',
                f'"{county} County Government" news',
                f'"{county}" Kenya project',
                f'"{county}" Kenya road hospital development',
            ]
        )

    return queries


def search_google(query):
    url = (
        "https://www.google.com/search?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "tbm": "nws",
                "num": 10,
            }
        )
    )

    try:
        html, _ = fetch_html(url)
    except Exception as exc:
        log(f"Google search failed: {exc}")
        return []

    soup = BeautifulSoup(html, "html.parser")

    results = []

    for container in soup.select(
        "div.SoaBEf, article, div.Gx5Zad"
    ):
        links = container.find_all(
            "a",
            href=True,
        )

        if not links:
            continue

        link = None

        for candidate in links:
            href = candidate.get("href", "")

            if (
                href.startswith("http://")
                or href.startswith("https://")
            ):
                link = candidate
                break

        if not link:
            continue

        href = normalize_url(
            link.get("href")
        )

        if not href:
            continue

        title_node = container.find(
            ["h3", "h4"]
        )

        title = clean_text(
            title_node.get_text(
                " ",
                strip=True,
            )
            if title_node
            else link.get_text(
                " ",
                strip=True,
            )
        )

        text = clean_text(
            container.get_text(
                " ",
                strip=True,
            )
        )

        if not title:
            continue

        if len(title) < 10:
            continue

        results.append(
            {
                "title": title,
                "url": href,
                "summary": text,
                "search_query": query,
            }
        )

    return results


def search_bing(query):
    url = (
        "https://www.bing.com/news/search?"
        + urllib.parse.urlencode(
            {
                "q": query,
            }
        )
    )

    try:
        html, _ = fetch_html(url)
    except Exception as exc:
        log(f"Bing search failed: {exc}")
        return []

    soup = BeautifulSoup(html, "html.parser")

    results = []

    selectors = [
        "div.news-card",
        "div.news-card-body",
        "div.t_s",
        "article",
    ]

    containers = []

    for selector in selectors:
        containers.extend(
            soup.select(selector)
        )

    for container in containers:
        link = container.find(
            "a",
            href=True,
        )

        if not link:
            continue

        href = normalize_url(
            link.get("href")
        )

        if not href:
            continue

        title_node = (
            container.find("h2")
            or container.find("h3")
            or link
        )

        title = clean_text(
            title_node.get_text(
                " ",
                strip=True,
            )
        )

        summary = clean_text(
            container.get_text(
                " ",
                strip=True,
            )
        )

        if not title or len(title) < 10:
            continue

        results.append(
            {
                "title": title,
                "url": href,
                "summary": summary,
                "search_query": query,
            }
        )

    return results


def collect_candidates():
    log("")
    log("============================================================")
    log("SEARCHING CURRENT COUNTY NEWS")
    log("============================================================")

    all_candidates = []

    queries = build_queries()

    for number, query in enumerate(
        queries,
        1,
    ):
        log(
            f"[{number}/{len(queries)}] {query}"
        )

        google_results = search_google(query)

        all_candidates.extend(
            google_results
        )

        bing_results = search_bing(query)

        all_candidates.extend(
            bing_results
        )

        time.sleep(0.3)

    unique = {}

    for candidate in all_candidates:
        url = candidate.get(
            "url",
            "",
        )

        if not url:
            continue

        parsed = urllib.parse.urlparse(url)

        domain = parsed.netloc.lower()

        if (
            "google." in domain
            or "bing.com" in domain
        ):
            continue

        key = hashlib.sha256(
            url.split("#")[0].encode(
                "utf-8"
            )
        ).hexdigest()

        if key not in unique:
            unique[key] = candidate

    candidates = list(
        unique.values()
    )

    log("")
    log(
        f"Unique candidate stories found: "
        f"{len(candidates)}"
    )

    return candidates


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    lowered = clean_text(text).lower()

    matches = []

    for county in COUNTIES:
        if county.lower() in lowered:
            matches.append(county)

    if not matches:
        return ""

    return matches[0] + " County"


# ============================================================
# ARTICLE TEXT
# ============================================================

def extract_article_text(soup):
    selectors = [
        "[itemprop='articleBody']",
        "article",
        "main",
        ".article-body",
        ".article-content",
        ".entry-content",
        ".post-content",
        ".story-content",
        ".single-post-content",
        ".td-post-content",
        ".content-area",
    ]

    blocks = []

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(text) >= 200:
                blocks.append(text)

    if blocks:
        return max(
            blocks,
            key=len,
        )

    paragraphs = []

    for paragraph in soup.find_all("p"):
        text = clean_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) >= 40:
            paragraphs.append(text)

    return " ".join(
        paragraphs
    )


# ============================================================
# SOURCE NAME
# ============================================================

def get_source_name(soup, url):
    selectors = [
        (
            "meta",
            {"property": "og:site_name"},
        ),
        (
            "meta",
            {"name": "application-name"},
        ),
        (
            "meta",
            {"name": "publisher"},
        ),
    ]

    for tag_name, attrs in selectors:
        tag = soup.find(
            tag_name,
            attrs=attrs,
        )

        if tag:
            value = clean_text(
                tag.get("content")
            )

            if (
                value
                and len(value) < 100
                and "google" not in value.lower()
            ):
                return value

    for selector in [
        "header .site-title",
        ".site-title",
        ".site-name",
        ".publisher",
        ".brand",
    ]:
        node = soup.select_one(
            selector
        )

        if node:
            value = clean_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

            if value and len(value) < 100:
                return value

    domain = urllib.parse.urlparse(
        url
    ).netloc.lower()

    domain = domain.replace(
        "www.",
        "",
    )

    return domain


# ============================================================
# IMAGE CANDIDATES
# ============================================================

def add_image_candidate(
    candidates,
    value,
    base_url,
):
    if not value:
        return

    value = clean_text(value)

    if value.startswith("data:"):
        return

    absolute = normalize_url(
        value,
        base_url,
    )

    if not absolute:
        return

    lowered = absolute.lower()

    if any(
        term in lowered
        for term in IMAGE_BAD_TERMS
    ):
        return

    if absolute not in candidates:
        candidates.append(
            absolute
        )


def extract_image_candidates(
    soup,
    base_url,
):
    candidates = []

    # --------------------------------------------------------
    # Highest priority: publisher metadata
    # --------------------------------------------------------

    for attrs in [
        {"property": "og:image"},
        {"property": "og:image:url"},
        {"property": "og:image:secure_url"},
        {"name": "twitter:image"},
        {"name": "twitter:image:src"},
        {"property": "twitter:image"},
    ]:
        for tag in soup.find_all(
            "meta",
            attrs=attrs,
        ):
            add_image_candidate(
                candidates,
                tag.get("content"),
                base_url,
            )

    # --------------------------------------------------------
    # JSON-LD structured data
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    ):
        raw = script.string or script.get_text(
            " ",
            strip=True,
        )

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        objects = []

        if isinstance(data, list):
            objects.extend(data)

        elif isinstance(data, dict):
            objects.append(data)

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list,
            ):
                objects.extend(
                    graph
                )

        for obj in objects:
            if not isinstance(
                obj,
                dict,
            ):
                continue

            image = obj.get(
                "image"
            )

            if isinstance(
                image,
                str,
            ):
                add_image_candidate(
                    candidates,
                    image,
                    base_url,
                )

            elif isinstance(
                image,
                list,
            ):
                for item in image:
                    if isinstance(
                        item,
                        str,
                    ):
                        add_image_candidate(
                            candidates,
                            item,
                            base_url,
                        )

            elif isinstance(
                image,
                dict,
            ):
                add_image_candidate(
                    candidates,
                    image.get("url"),
                    base_url,
                )

    # --------------------------------------------------------
    # Link image metadata
    # --------------------------------------------------------

    for tag in soup.find_all(
        "link"
    ):
        rel = tag.get(
            "rel",
            [],
        )

        if isinstance(
            rel,
            str,
        ):
            rel = [rel]

        rel_lower = [
            str(x).lower()
            for x in rel
        ]

        if (
            "image_src" in rel_lower
            or "image" in rel_lower
        ):
            add_image_candidate(
                candidates,
                tag.get("href"),
                base_url,
            )

    # --------------------------------------------------------
    # Images including lazy-load attributes
    # --------------------------------------------------------

    for image in soup.find_all(
        "img"
    ):
        for attribute in [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-url",
            "data-filename",
        ]:
            add_image_candidate(
                candidates,
                image.get(attribute),
                base_url,
            )

        srcset = image.get(
            "srcset"
        )

        if srcset:
            for item in srcset.split(","):
                item = item.strip()

                if not item:
                    continue

                image_url = item.split(
                    " "
                )[0]

                add_image_candidate(
                    candidates,
                    image_url,
                    base_url,
                )

    return candidates


# ============================================================
# IMAGE DOWNLOAD / VALIDATION
# ============================================================

def download_and_validate_image(
    image_url,
    article_url,
    output_path,
):
    try:
        response = SESSION.get(
            image_url,
            headers={
                "Referer": article_url,
                "User-Agent": USER_AGENT,
                "Accept": (
                    "image/avif,image/webp,image/apng,"
                    "image/svg+xml,image/*,*/*;q=0.8"
                ),
            },
            timeout=30,
            allow_redirects=True,
        )

        response.raise_for_status()

        content = response.content

        if len(content) < 5000:
            return False

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        if (
            "image" not in content_type
            and not image_url.lower().split("?")[0].endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                )
            )
        ):
            return False

        temporary = SOURCE_DIR / (
            "image_validation.tmp"
        )

        temporary.write_bytes(
            content
        )

        try:
            with Image.open(
                temporary
            ) as image:
                image.load()

                width = image.width
                height = image.height

                if width < 300 or height < 200:
                    return False

                # Reject tiny portrait/avatar-type images.
                if width < 500 and height < 500:
                    return False

                rgb = image.convert(
                    "RGB"
                )

                rgb.save(
                    output_path,
                    "JPEG",
                    quality=94,
                    optimize=True,
                )

        finally:
            temporary.unlink(
                missing_ok=True
            )

        if (
            output_path.exists()
            and output_path.stat().st_size > 10000
        ):
            return True

    except Exception as exc:
        log(
            f"Image failed: "
            f"{str(exc)[:120]}"
        )

    return False


def recover_real_image(article_url):
    log("")
    log("------------------------------------------------------------")
    log("REAL IMAGE RECOVERY")
    log("------------------------------------------------------------")

    try:
        html, final_url = fetch_html(
            article_url,
            timeout=30,
        )
    except Exception as exc:
        log(
            f"Article page unavailable: {exc}"
        )
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = extract_image_candidates(
        soup,
        final_url,
    )

    log(
        f"Image candidates discovered: "
        f"{len(candidates)}"
    )

    # Try all publisher images.
    for index, image_url in enumerate(
        candidates,
        1,
    ):
        log(
            f"Trying image "
            f"{index}/{len(candidates)}"
        )

        if download_and_validate_image(
            image_url,
            final_url,
            IMAGE_FILE,
        ):
            log(
                f"REAL IMAGE FOUND: "
                f"{image_url}"
            )
            log(
                f"SAVED: {IMAGE_FILE}"
            )

            return image_url

    # --------------------------------------------------------
    # Secondary recovery:
    # Search the article HTML for direct image URLs.
    # --------------------------------------------------------

    log(
        "Metadata images failed. "
        "Scanning article HTML for direct images..."
    )

    raw_urls = re.findall(
        r'https?://[^"\'>\s]+?\.(?:jpg|jpeg|png|webp)',
        html,
        flags=re.IGNORECASE,
    )

    seen = set()

    for image_url in raw_urls:
        image_url = image_url.rstrip(
            ".,);]"
        )

        if image_url in seen:
            continue

        seen.add(
            image_url
        )

        if any(
            term in image_url.lower()
            for term in IMAGE_BAD_TERMS
        ):
            continue

        if download_and_validate_image(
            image_url,
            final_url,
            IMAGE_FILE,
        ):
            log(
                f"REAL IMAGE FOUND FROM HTML: "
                f"{image_url}"
            )

            return image_url

    log(
        "No usable real article image recovered."
    )

    return ""


# ============================================================
# DATE EXTRACTION
# ============================================================

def extract_publication_date(
    soup,
):
    selectors = [
        (
            "meta",
            {"property": "article:published_time"},
        ),
        (
            "meta",
            {"name": "article:published_time"},
        ),
        (
            "meta",
            {"name": "publish-date"},
        ),
        (
            "meta",
            {"name": "date"},
        ),
        (
            "meta",
            {"property": "og:updated_time"},
        ),
    ]

    for tag_name, attrs in selectors:
        tag = soup.find(
            tag_name,
            attrs=attrs,
        )

        if tag:
            value = clean_text(
                tag.get("content")
            )

            if value:
                return value

    for tag in soup.find_all(
        "time"
    ):
        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        value = clean_text(
            value
        )

        if value:
            return value

    return datetime.now(
        timezone.utc
    ).date().isoformat()


# ============================================================
# CATEGORY
# ============================================================

def detect_category(text):
    lowered = clean_text(
        text
    ).lower()

    if any(
        term in lowered
        for term in [
            "road",
            "roads",
            "construction",
            "project",
            "development",
            "infrastructure",
        ]
    ):
        return "DEVELOPMENT"

    if any(
        term in lowered
        for term in [
            "budget",
            "finance",
            "funding",
            "revenue",
            "allocation",
        ]
    ):
        return "FINANCE"

    if any(
        term in lowered
        for term in [
            "hospital",
            "health",
            "clinic",
            "medical",
        ]
    ):
        return "HEALTH"

    if any(
        term in lowered
        for term in [
            "school",
            "education",
            "student",
            "university",
        ]
    ):
        return "EDUCATION"

    return "COUNTY NEWS"


# ============================================================
# CANDIDATE SCORE
# ============================================================

def score_candidate(candidate):
    title = clean_text(
        candidate.get(
            "title",
            "",
        )
    ).lower()

    summary = clean_text(
        candidate.get(
            "summary",
            "",
        )
    ).lower()

    text = title + " " + summary

    score = 0

    for county in COUNTIES:
        if county.lower() in text:
            score += 20

    for term in POSITIVE_TERMS:
        if term in text:
            score += 3

    # Strong preference for specific news language.
    for term in [
        "today",
        "latest",
        "announced",
        "launched",
        "approved",
        "construction",
        "project",
        "statement",
        "inspection",
        "development",
    ]:
        if term in title:
            score += 5

    for term in BAD_TERMS:
        if term in title:
            score -= 100

    return score


# ============================================================
# VERIFY ARTICLE
# ============================================================

def verify_candidate(
    candidate,
):
    url = clean_text(
        candidate.get(
            "url",
            "",
        )
    )

    title = clean_text(
        candidate.get(
            "title",
            "",
        )
    )

    if not url or not title:
        return None

    if len(title) < 15:
        return None

    lowered_title = title.lower()

    if any(
        term in lowered_title
        for term in [
            "google news",
            "facebook",
            "sign in",
        ]
    ):
        return None

    try:
        html, final_url = fetch_html(
            url,
            timeout=30,
        )
    except Exception as exc:
        log(
            f"Article fetch failed: "
            f"{str(exc)[:150]}"
        )
        return None

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    article_text = extract_article_text(
        soup
    )

    if len(article_text) < 120:
        log(
            "Rejected: insufficient article text."
        )
        return None

    combined = clean_text(
        title
        + " "
        + article_text
    )

    county = detect_county(
        combined
    )

    if not county:
        log(
            "Rejected: county not detected."
        )
        return None

    lowered = combined.lower()

    positive_score = sum(
        1
        for term in POSITIVE_TERMS
        if term in lowered
    )

    if positive_score < 2:
        log(
            "Rejected: weak county-news relevance."
        )
        return None

    source_name = get_source_name(
        soup,
        final_url,
    )

    # Never allow search-engine source names.
    if any(
        term in source_name.lower()
        for term in [
            "google",
            "bing",
            "facebook",
        ]
    ):
        source_name = urllib.parse.urlparse(
            final_url
        ).netloc.replace(
            "www.",
            "",
        )

    log(
        f"Article verified: "
        f"{source_name}"
    )

    image_url = recover_real_image(
        final_url
    )

    if not image_url:
        log(
            "Rejected: no real publisher image."
        )
        return None

    publication_date = extract_publication_date(
        soup
    )

    category = detect_category(
        combined
    )

    summary = shorten(
        article_text,
        650,
    )

    story = {
        "title": shorten(
            title,
            180,
        ),
        "county": county,
        "category": category,
        "date": publication_date,
        "source_name": source_name,
        "url": final_url,
        "resolved_url": final_url,
        "image": image_url,
        "local_image": str(
            IMAGE_FILE.relative_to(ROOT)
        ).replace(
            "\\",
            "/",
        ),
        "summary": summary,
        "verified": True,
        "verification": {
            "article_fetched": True,
            "article_text_found": True,
            "county_detected": True,
            "real_image_found": True,
            "publisher_source": True,
        },
    }

    return story


# ============================================================
# STORY SELECTION
# ============================================================

def select_verified_story():
    candidates = collect_candidates()

    candidates.sort(
        key=score_candidate,
        reverse=True,
    )

    if not candidates:
        raise RuntimeError(
            "No news candidates were found."
        )

    # Keep trying candidates until a complete
    # verified article + real image is found.
    for index, candidate in enumerate(
        candidates,
        1,
    ):
        log("")
        log(
            "============================================================"
        )
        log(
            f"VERIFYING CANDIDATE "
            f"{index}/{len(candidates)}"
        )
        log(
            f"TITLE: {candidate.get('title', '')}"
        )
        log(
            f"URL: {candidate.get('url', '')}"
        )
        log(
            "============================================================"
        )

        try:
            story = verify_candidate(
                candidate
            )
        except Exception as exc:
            log(
                f"Candidate error: "
                f"{type(exc).__name__}: {exc}"
            )
            story = None

        if story:
            log("")
            log(
                "============================================================"
            )
            log(
                "VERIFIED STORY SELECTED"
            )
            log(
                "============================================================"
            )
            log(
                f"Title : {story['title']}"
            )
            log(
                f"County: {story['county']}"
            )
            log(
                f"Source: {story['source_name']}"
            )
            log(
                f"Image : {story['image']}"
            )

            return story

    raise RuntimeError(
        "No verified county story with a real image "
        "could be selected after checking all candidates."
    )


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story,
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

    source = clean_text(
        story.get(
            "source_name",
            "",
        )
    )

    return (
        f"Here is the latest verified update "
        f"from {county}. "
        f"{title}. "
        f"{summary} "
        f"This report is based on information "
        f"published by {source}. "
        f"Rift Valley Watch. "
        f"Verified county news and developments."
    )


# ============================================================
# WRITE DATA
# ============================================================

def write_story_files(
    story,
):
    narration = build_narration(
        story
    )

    script = {
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
        "source_name": story.get(
            "source_name",
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
        "local_image": story.get(
            "local_image",
            "",
        ),
        "narration": narration,
    }

    payloads = [
        (
            STORY_FILE,
            story,
        ),
        (
            SELECTED_STORY_FILE,
            story,
        ),
        (
            SCRIPT_FILE,
            script,
        ),
        (
            SELECTED_SCRIPT_FILE,
            script,
        ),
    ]

    for path, payload in payloads:
        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        log(
            f"Wrote: {path}"
        )


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
        "AUTOMATIC MULTI-COUNTY NEWS ENGINE"
    )
    log(
        "============================================================"
    )

    log(
        f"Root: {ROOT}"
    )

    log(
        "Counties: "
        + ", ".join(COUNTIES)
    )

    prepare_directories()

    # Remove stale image so an old story image can never
    # accidentally be presented as the new story image.
    if IMAGE_FILE.exists():
        IMAGE_FILE.unlink()

    story = select_verified_story()

    write_story_files(
        story
    )

    log("")
    log(
        "============================================================"
    )
    log(
        "NEWS ENGINE SUCCESSFUL"
    )
    log(
        "============================================================"
    )

    log(
        f"Selected story: {story['title']}"
    )

    log(
        f"County: {story['county']}"
    )

    log(
        f"Source: {story['source_name']}"
    )

    log(
        f"Real image: {story['image']}"
    )

    log(
        f"Local image: {story['local_image']}"
    )

    log("")
    log(
        "data/story.json ready."
    )

    log(
        "data/script.json ready."
    )

    log(
        "Video generator can now run."
    )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        log("")
        log(
            "Process interrupted."
        )
        sys.exit(1)

    except Exception as exc:
        log("")
        log(
            "============================================================"
        )
        log(
            "RIFT VALLEY WATCH NEWS ENGINE FAILED"
        )
        log(
            "============================================================"
        )
        log(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
