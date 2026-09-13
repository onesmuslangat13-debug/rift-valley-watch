import json
import os
import re
import sys
import time
import hashlib
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


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

NEWS_SOURCES = [
    "https://www.google.com/search?q=",
    "https://www.bing.com/news/search?q=",
]

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
)

BAD_TERMS = [
    "google news",
    "facebook",
    "sign in",
    "subscribe",
    "advertisement",
    "cookie",
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
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def valid_text(value, minimum=20):
    value = clean_text(value)

    if len(value) < minimum:
        return False

    lowered = value.lower()

    for term in BAD_TERMS:
        if term in lowered:
            return False

    return True


def shorten(text, maximum=500):
    text = clean_text(text)

    if len(text) <= maximum:
        return text

    text = text[:maximum]

    if " " in text:
        text = text.rsplit(" ", 1)[0]

    return text.rstrip(" ,.;:-") + "..."


def normalize_url(url):
    url = clean_text(url)

    if not url:
        return ""

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("/"):
        return ""

    if not url.startswith(("http://", "https://")):
        return ""

    return url


# ============================================================
# HTTP
# ============================================================

def fetch(url, timeout=25):
    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,*/*;q=0.8"
            ),
        },
        timeout=timeout,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# SEARCH QUERIES
# ============================================================

def build_queries():
    queries = []

    for county in COUNTIES:
        queries.extend(
            [
                f"{county} County latest news development",
                f"{county} County Government latest statement",
                f"{county} Kenya project news",
                f"{county} Kenya official news",
            ]
        )

    return queries


# ============================================================
# SEARCH ENGINE RESULTS
# ============================================================

def search_google(query):
    encoded = urllib.parse.quote_plus(query)

    url = (
        "https://www.google.com/search?"
        f"q={encoded}&tbm=nws"
    )

    html = fetch(url)

    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    for article in soup.select("article"):
        link = article.find("a", href=True)

        if not link:
            continue

        href = normalize_url(link.get("href"))

        if not href:
            continue

        title_node = article.find(
            ["h3", "h4"]
        )

        title = clean_text(
            title_node.get_text(" ", strip=True)
            if title_node
            else link.get_text(" ", strip=True)
        )

        description = clean_text(
            article.get_text(" ", strip=True)
        )

        if not title:
            continue

        candidates.append(
            {
                "title": title,
                "url": href,
                "summary": description,
                "search_query": query,
            }
        )

    return candidates


def search_bing(query):
    encoded = urllib.parse.quote_plus(query)

    url = (
        "https://www.bing.com/news/search?"
        f"q={encoded}"
    )

    html = fetch(url)

    soup = BeautifulSoup(html, "html.parser")

    candidates = []

    for item in soup.select(
        "div.news-card, div.news-card-body, article"
    ):
        link = item.find("a", href=True)

        if not link:
            continue

        href = normalize_url(link.get("href"))

        if not href:
            continue

        title_node = item.find(
            ["a", "h2", "h3"]
        )

        title = clean_text(
            title_node.get_text(" ", strip=True)
            if title_node
            else ""
        )

        summary = clean_text(
            item.get_text(" ", strip=True)
        )

        if not title:
            continue

        candidates.append(
            {
                "title": title,
                "url": href,
                "summary": summary,
                "search_query": query,
            }
        )

    return candidates


def collect_candidates():
    log("")
    log("============================================================")
    log("SEARCHING CURRENT COUNTY NEWS")
    log("============================================================")

    candidates = []

    for query in build_queries():
        log(f"Searching: {query}")

        for search_function in (
            search_google,
            search_bing,
        ):
            try:
                results = search_function(query)
                candidates.extend(results)
            except Exception as exc:
                log(
                    f"Search failed for "
                    f"{search_function.__name__}: {exc}"
                )

        time.sleep(0.5)

    unique = {}

    for candidate in candidates:
        url = candidate.get("url", "")

        if not url:
            continue

        key = hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()

        unique[key] = candidate

    result = list(unique.values())

    log(
        f"Unique candidate stories found: "
        f"{len(result)}"
    )

    return result


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    text = clean_text(text).lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county + " County"

    return ""


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_image_candidates(soup, base_url):
    candidates = []

    selectors = [
        ("meta", {"property": "og:image"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
        ("link", {"rel": "image_src"}),
    ]

    for tag_name, attrs in selectors:
        for tag in soup.find_all(tag_name, attrs=attrs):
            value = (
                tag.get("content")
                or tag.get("href")
                or ""
            )

            value = clean_text(value)

            if not value:
                continue

            absolute = urllib.parse.urljoin(
                base_url,
                value,
            )

            if absolute not in candidates:
                candidates.append(absolute)

    for image in soup.find_all("img"):
        value = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-lazy-src")
            or ""
        )

        value = clean_text(value)

        if not value:
            continue

        absolute = urllib.parse.urljoin(
            base_url,
            value,
        )

        if absolute not in candidates:
            candidates.append(absolute)

    return candidates


def recover_real_image(article_url):
    log("")
    log("RECOVERING REAL ARTICLE IMAGE")

    try:
        html = fetch(article_url)
    except Exception as exc:
        log(f"Article fetch failed: {exc}")
        return ""

    soup = BeautifulSoup(html, "html.parser")

    image_candidates = extract_image_candidates(
        soup,
        article_url,
    )

    for index, image_url in enumerate(
        image_candidates,
        1,
    ):
        try:
            log(
                f"Trying article image "
                f"{index}/{len(image_candidates)}"
            )

            response = requests.get(
                image_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": article_url,
                },
                timeout=25,
            )

            response.raise_for_status()

            content = response.content

            if len(content) < 5000:
                continue

            temporary = SOURCE_DIR / "candidate_image"

            temporary.write_bytes(content)

            from PIL import Image

            with Image.open(temporary) as image:
                image.verify()

            with Image.open(temporary) as image:
                image = image.convert("RGB")

                if image.width < 300 or image.height < 200:
                    continue

                output = SOURCE_DIR / "story_image.jpg"

                image.save(
                    output,
                    "JPEG",
                    quality=95,
                )

            temporary.unlink(missing_ok=True)

            log(f"REAL IMAGE FOUND: {image_url}")
            log(f"Saved image: {output}")

            return image_url

        except Exception:
            continue

    log("No usable article image found.")

    return ""


# ============================================================
# ARTICLE VERIFICATION
# ============================================================

def extract_article_text(soup):
    selectors = [
        "article",
        "main",
        "[itemprop='articleBody']",
        ".article-body",
        ".entry-content",
        ".post-content",
        ".story-content",
    ]

    blocks = []

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(
                node.get_text(" ", strip=True)
            )

            if len(text) > 150:
                blocks.append(text)

    if blocks:
        return max(
            blocks,
            key=len,
        )

    paragraphs = []

    for paragraph in soup.find_all("p"):
        text = clean_text(
            paragraph.get_text(" ", strip=True)
        )

        if len(text) >= 40:
            paragraphs.append(text)

    return " ".join(paragraphs)


def verify_candidate(candidate):
    url = candidate.get("url", "")
    title = clean_text(candidate.get("title", ""))

    if not url or not title:
        return None

    if not valid_text(title, 15):
        return None

    try:
        html = fetch(url)
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")

    article_text = extract_article_text(soup)

    if not valid_text(article_text, 120):
        return None

    combined = clean_text(
        title + " " + article_text
    )

    county = detect_county(combined)

    if not county:
        return None

    lowered = combined.lower()

    positive_score = sum(
        1
        for term in POSITIVE_TERMS
        if term in lowered
    )

    if positive_score < 2:
        return None

    source_name = ""

    publisher_meta = soup.find(
        "meta",
        attrs={
            "property": "og:site_name"
        },
    )

    if publisher_meta:
        source_name = clean_text(
            publisher_meta.get("content")
        )

    if not source_name:
        source_name = urllib.parse.urlparse(
            url
        ).netloc.replace("www.", "")

    image_url = recover_real_image(url)

    if not image_url:
        return None

    summary = shorten(
        article_text,
        650,
    )

    category = "COUNTY NEWS"

    if any(
        term in lowered
        for term in [
            "road",
            "construction",
            "project",
            "development",
        ]
    ):
        category = "DEVELOPMENT"

    elif any(
        term in lowered
        for term in [
            "budget",
            "finance",
            "funding",
        ]
    ):
        category = "FINANCE"

    elif any(
        term in lowered
        for term in [
            "hospital",
            "health",
            "clinic",
        ]
    ):
        category = "HEALTH"

    story = {
        "title": shorten(title, 180),
        "county": county,
        "category": category,
        "date": datetime.now(
            timezone.utc
        ).date().isoformat(),
        "source_name": source_name,
        "url": url,
        "resolved_url": url,
        "image": image_url,
        "summary": summary,
        "verified": True,
        "verification": {
            "article_fetched": True,
            "article_text_found": True,
            "real_image_found": True,
            "county_detected": True,
        },
    }

    return story


# ============================================================
# STORY SELECTION
# ============================================================

def score_candidate(candidate):
    title = clean_text(
        candidate.get("title", "")
    ).lower()

    summary = clean_text(
        candidate.get("summary", "")
    ).lower()

    text = title + " " + summary

    score = 0

    for county in COUNTIES:
        if county.lower() in text:
            score += 10

    for term in POSITIVE_TERMS:
        if term in text:
            score += 2

    if any(
        term in title
        for term in [
            "google news",
            "facebook",
            "sign in",
        ]
    ):
        score -= 100

    return score


def select_verified_story():
    candidates = collect_candidates()

    candidates.sort(
        key=score_candidate,
        reverse=True,
    )

    for index, candidate in enumerate(
        candidates,
        1,
    ):
        log("")
        log(
            f"VERIFYING CANDIDATE "
            f"{index}/{len(candidates)}"
        )

        story = verify_candidate(candidate)

        if story:
            log("")
            log("VERIFIED STORY SELECTED")
            log(f"Title: {story['title']}")
            log(f"County: {story['county']}")
            log(f"Source: {story['source_name']}")
            log(f"Image: {story['image']}")

            return story

    raise RuntimeError(
        "No verified county story with a real image "
        "could be selected."
    )


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean_text(story.get("title"))
    county = clean_text(story.get("county"))
    summary = clean_text(story.get("summary"))
    source = clean_text(story.get("source_name"))

    return (
        f"Here is the latest verified update from "
        f"{county}. "
        f"{title}. "
        f"{summary} "
        f"This report is based on information published "
        f"by {source}. "
        f"Rift Valley Watch. Verified county news "
        f"and developments."
    )


def write_story_files(story):
    narration = build_narration(story)

    script = {
        "title": story.get("title", ""),
        "county": story.get("county", ""),
        "category": story.get("category", ""),
        "source_name": story.get("source_name", ""),
        "url": story.get("url", ""),
        "image": story.get("image", ""),
        "narration": narration,
    }

    for path, payload in [
        (STORY_FILE, story),
        (SELECTED_STORY_FILE, story),
        (SCRIPT_FILE, script),
        (SELECTED_SCRIPT_FILE, script),
    ]:
        path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    log(f"Story written: {STORY_FILE}")
    log(f"Script written: {SCRIPT_FILE}")


# ============================================================
# MAIN
# ============================================================

def main():
    log("")
    log("============================================================")
    log("RIFT VALLEY WATCH")
    log("AUTOMATIC MULTI-COUNTY NEWS ENGINE")
    log("============================================================")

    log(f"Root: {ROOT}")
    log(f"Counties: {', '.join(COUNTIES)}")

    prepare_directories()

    story = select_verified_story()

    write_story_files(story)

    log("")
    log("============================================================")
    log("NEWS ENGINE SUCCESSFUL")
    log("============================================================")

    log(f"Selected story: {story['title']}")
    log(f"County: {story['county']}")
    log(f"Source: {story['source_name']}")
    log("")
    log(
        "The video generator can now read "
        "data/story.json and data/script.json."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("")
        log("============================================================")
        log("RIFT VALLEY WATCH NEWS ENGINE FAILED")
        log("============================================================")
        log(f"{type(exc).__name__}: {exc}")
        sys.exit(1)
