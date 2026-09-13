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

VIDEO_GENERATOR = ROOT / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"


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


def log(text=""):
    print(text, flush=True)


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

        result.append(
            sentence
        )

    return result


def save_json(
    path,
    data,
):

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


def discover_links(
    page_url,
):

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

        result.append(
            value
        )


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
        "image/avif,"
        "image/webp,"
        "image/apng,"
        "image/*,"
        "*/*;q=0.8"
    )

    if referer:

        headers["Referer"] = (
            referer
        )

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

            if len(
                text
            ) < 35:

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

                paragraphs.append(
                    text
                )

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

        selected.append(
            sentence
        )

        if len(
            " ".join(
                selected
            ).split()
        ) >= 105:

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

        hashes.add(
            image_hash
        )

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

            if article:

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

            time.sleep(
                0.15
            )

    return candidates


def clean_previous():

    for directory in (
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
    ):

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    for path in (
        SELECTED_STORY,
        SELECTED_SCRIPT,
        FINAL_IMAGE,
        FINAL_VIDEO,
    ):

        if path.exists():

            path.unlink()


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


def verify():

    if (
        not FINAL_VIDEO.exists()
        or FINAL_VIDEO.stat().st_size < 100000
    ):

        raise RuntimeError(
            "Final Rift Valley Watch MP4 "
            "was not generated correctly."
        )

    result = subprocess.run(
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

    if result.returncode != 0:

        raise RuntimeError(
            "Final MP4 failed FFprobe validation."
        )

    video_duration = float(
        result.stdout.strip()
    )

    if video_duration < 5:

        raise RuntimeError(
            "Final MP4 is too short."
        )

    log(
        "FINAL VIDEO VERIFIED: "
        f"{FINAL_VIDEO} | "
        f"{FINAL_VIDEO.stat().st_size / 1048576:.2f} MB | "
        f"{video_duration:.2f}s"
    )


def main():

    log("=" * 70)

    log(
        "STARTING RIFT VALLEY WATCH"
    )

    log(
        "VERSION: "
        "RVW_MAIN_V13_CLEAN_SCRIPT"
    )

    log("=" * 70)

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
        f"SCORE {selected['score']}"
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
        "NARRATION CLEANUP: "
        "Advertisement markers removed; "
        "truncation markers removed; "
        "duplicates removed"
    )

    save_json(
        SELECTED_SCRIPT,
        {
            "title": story["title"],
            "county": story["county"],
            "narration": story["script"],
        },
    )

    run_generator()

    verify()

    log(
        "RIFT VALLEY WATCH COMPLETED"
    )


if __name__ == "__main__":

    main()
