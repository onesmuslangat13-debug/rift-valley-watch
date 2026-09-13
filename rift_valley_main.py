# ============================================================
# RIFT VALLEY WATCH
# MAIN CONTROLLER
# VERSION: RVW_MAIN_V9_CLEAN
#
# ONE STORY
# ONE REAL IMAGE
# NO SOURCE
# NO PUBLISHER
# NO URL IN VIDEO DATA
# NO GOOGLE NEWS
# NO SOCIAL MEDIA
# ============================================================

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


COUNTIES = {
    "Bomet": ["Bomet", "Sotik", "Longisa", "Chepalungu", "Konoin"],
    "Kericho": ["Kericho", "Litein", "Kipkelion", "Ainamoi"],
    "Nakuru": ["Nakuru", "Naivasha", "Gilgil", "Molo", "Njoro"],
    "Nandi": ["Nandi", "Kapsabet", "Mosop", "Aldai"],
    "Uasin Gishu": ["Uasin Gishu", "Eldoret", "Kesses", "Turbo"],
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
    "google",
    "google-news",
    "google_news",
    "googlelogo",
    "google-logo",
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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def log(text=""):
    print(text, flush=True)


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


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


def domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def blocked(url):
    host = domain(url)

    if not host:
        return True

    for item in BLOCKED_DOMAINS:
        item = item.replace("www.", "")

        if host == item or host.endswith("." + item):
            return True

    return False


def approved(url):
    if not url:
        return False

    if blocked(url):
        return False

    host = domain(url)

    for item in APPROVED_DOMAINS:
        if host == item or host.endswith("." + item):
            return True

    return False


def county_from_text(text):
    text = clean(text).lower()

    best = ""
    best_score = 0

    for county, aliases in COUNTIES.items():

        score = 0

        for alias in aliases:

            if re.search(
                r"\b" + re.escape(alias.lower()) + r"\b",
                text,
            ):
                score += 1

        if score > best_score:
            best = county
            best_score = score

    return best


def fetch(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return None

        if "html" not in response.headers.get(
            "content-type",
            "",
        ).lower():
            return None

        return response

    except Exception:
        return None


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
            r"\s*[-|–—:]\s*" +
            re.escape(publisher) +
            r"\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

    return clean(title)


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
            re.escape(item),
            "",
            text,
            flags=re.IGNORECASE,
        )

    return clean(text)


def discover_links(page_url):
    response = fetch(page_url)

    if not response:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    links = []
    seen = set()

    for tag in soup.find_all("a", href=True):

        href = clean(tag.get("href"))

        if not href:
            continue

        url = urljoin(
            page_url,
            href,
        )

        url = url.split("#")[0]

        if not approved(url):
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

        county = county_from_text(text)

        if county:
            links.append(
                {
                    "url": url,
                    "text": text,
                    "county": county,
                }
            )

    return links


def get_image_candidates(soup, article_url):
    result = []
    seen = set()

    def add(value):

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

        if any(
            bad in value.lower()
            for bad in BAD_IMAGE_TERMS
        ):
            return

        if value not in seen:
            seen.add(value)
            result.append(value)

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

    for img in soup.find_all("img"):

        for key in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
        ]:

            value = img.get(key)

            if value:
                add(value)

    return result


def download_image(url):
    if any(
        bad in url.lower()
        for bad in BAD_IMAGE_TERMS
    ):
        return None

    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "Accept": "image/*",
            },
            timeout=20,
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            "",
        ).lower()

        if not content_type.startswith("image/"):
            return None

        if len(response.content) < 20000:
            return None

        image = Image.open(
            BytesIO(response.content)
        )

        image.load()

        if image.width < 400:
            return None

        if image.height < 250:
            return None

        if image.width * image.height < 150000:
            return None

        digest = hashlib.md5(
            response.content
        ).hexdigest()

        return {
            "image": image,
            "md5": digest,
            "url": url,
            "width": image.width,
            "height": image.height,
        }

    except Exception:
        return None


def extract_article(url):
    response = fetch(url)

    if not response:
        return None

    final_url = response.url

    if not approved(final_url):
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    title = ""

    tag = soup.find(
        "meta",
        attrs={"property": "og:title"},
    )

    if tag:
        title = clean(tag.get("content"))

    if not title:

        tag = soup.find(
            "meta",
            attrs={"name": "twitter:title"},
        )

        if tag:
            title = clean(tag.get("content"))

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

    if not title:
        return None

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

            if len(text) < 35:
                continue

            lower = text.lower()

            if any(
                item in lower
                for item in [
                    "google news",
                    "subscribe",
                    "newsletter",
                    "follow us",
                    "privacy policy",
                    "cookie policy",
                    "terms and conditions",
                    "advertisement",
                    "download our app",
                ]
            ):
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    body = clean(
        " ".join(
            paragraphs[:16]
        )
    )

    county = county_from_text(
        f"{title} {summary} {body}"
    )

    if not county:
        return None

    image = None

    for image_url in get_image_candidates(
        soup,
        final_url,
    )[:25]:

        image = download_image(
            image_url
        )

        if image:
            break

    if not image:
        return None

    words = len(
        body.split()
    )

    score = 0

    if words >= 200:
        score += 45
    elif words >= 150:
        score += 38
    elif words >= 100:
        score += 30
    elif words >= 70:
        score += 20
    else:
        score -= 20

    useful = [
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

    lower = f"{title} {summary} {body}".lower()

    for word in useful:
        if re.search(
            r"\b" + re.escape(word) + r"\b",
            lower,
        ):
            score += 2

    unwanted = [
        "charm offensive",
        "crowd erupts",
        "crowd goes wild",
        "dance",
        "chants",
        "rally",
        "campaign",
    ]

    for phrase in unwanted:
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

    sentences = re.split(
        r"(?<=[.!?])\s+",
        body,
    )

    usable = []

    for sentence in sentences:

        sentence = remove_metadata(
            sentence
        )

        if len(sentence) >= 30:
            usable.append(
                sentence
            )

    parts = [
        f"Here is the latest development from {county}.",
        f"{title}.",
    ]

    if summary:
        parts.append(
            summary
        )

    for sentence in usable:

        if len(
            " ".join(parts).split()
        ) >= 130:
            break

        if sentence.lower() == title.lower():
            continue

        parts.append(
            sentence
        )

    script = clean(
        " ".join(parts)
    )

    if len(script.split()) < 70:

        script += (
            " The development is important for local residents "
            "and businesses because it could affect services, "
            "economic activity and everyday life in the area. "
            "Progress will continue to be watched as the "
            "situation develops."
        )

    return remove_metadata(
        script
    )


def save_image(image_info):
    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_IMAGE.exists():
        FINAL_IMAGE.unlink()

    image = image_info["image"].convert(
        "RGB"
    )

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
                "Final image width is invalid."
            )

        if check.height < 250:
            raise RuntimeError(
                "Final image height is invalid."
            )

    return FINAL_IMAGE


def select_best(candidates):
    if not candidates:
        raise RuntimeError(
            "No real Rift Valley article with a usable image was found."
        )

    unique = []
    image_hashes = set()

    for item in candidates:

        digest = item["image"]["md5"]

        if digest in image_hashes:
            continue

        image_hashes.add(digest)
        unique.append(item)

    if not unique:
        raise RuntimeError(
            "No unique real article image was found."
        )

    unique.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return unique[0]


def discover():
    candidates = []

    log("")
    log("=" * 60)
    log("DISCOVERING RIFT VALLEY STORIES")
    log("=" * 60)

    for page in PUBLISHER_PAGES:

        log(
            f"CHECKING NEWS PAGE: {domain(page)}"
        )

        links = discover_links(
            page
        )

        log(
            f"LOCAL LINKS: {len(links)}"
        )

        links.sort(
            key=lambda x: len(x["text"]),
            reverse=True,
        )

        tested = set()

        for item in links[:20]:

            url = item["url"]

            if url in tested:
                continue

            tested.add(url)

            article = extract_article(
                url
            )

            if not article:
                continue

            if not approved(
                article["url"]
            ):
                continue

            candidates.append(
                article
            )

            log(
                f"ACCEPTED: {article['county']} | "
                f"{article['title']}"
            )

            if len(candidates) >= 20:
                return candidates

            time.sleep(0.2)

    return candidates


def validate(story):
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
            "Story title missing."
        )

    if not county:
        raise RuntimeError(
            "Story county missing."
        )

    if not image_path:
        raise RuntimeError(
            "Story image missing."
        )

    image_file = ROOT / image_path

    if not image_file.exists():
        raise RuntimeError(
            f"Story image not found: {image_file}"
        )

    if len(narration.split()) < 70:
        raise RuntimeError(
            "Narration contains fewer than 70 words."
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
        "facebook",
        "instagram",
        "twitter",
        "youtube",
        "tiktok",
    ]

    lower = narration.lower()

    for item in forbidden:

        if item in lower:
            raise RuntimeError(
                "Forbidden metadata found in narration."
            )

    with Image.open(
        image_file
    ) as image:

        image.load()

        if image.width < 400:
            raise RuntimeError(
                "Story image is invalid."
            )

        if image.height < 250:
            raise RuntimeError(
                "Story image is invalid."
            )


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


def clean_previous():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in [
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
    ]:

        if path.exists():
            path.unlink()


def run_generator():
    if not VIDEO_GENERATOR.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py not found."
        )

    log("")
    log("=" * 60)
    log("GENERATING ORIGINAL REEL")
    log("=" * 60)

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

    log("")
    log("=" * 60)
    log("FINAL VIDEO VERIFIED")
    log("=" * 60)

    log(
        f"FILE: {FINAL_VIDEO}"
    )

    log(
        f"SIZE: {size / (1024 * 1024):.2f} MB"
    )


def main():
    log("")
    log("=" * 60)
    log("STARTING RIFT VALLEY WATCH")
    log("=" * 60)

    log(
        "VERSION: RVW_MAIN_V9_CLEAN"
    )

    log(
        "ONE STORY / ONE REAL IMAGE / NO SOURCE"
    )

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
    log("=" * 60)
    log("SELECTED STORY")
    log("=" * 60)

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

    log("")
    log(
        f"NARRATION WORDS: {len(story['script'].split())}"
    )

    log(
        f"IMAGE: {story['image_path']}"
    )

    run_generator()

    verify()

    log("")
    log("=" * 60)
    log("RIFT VALLEY WATCH COMPLETED")
    log("=" * 60)


if __name__ == "__main__":
    main()
