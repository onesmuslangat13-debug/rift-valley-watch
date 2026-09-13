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


VERSION = "RVW_MAIN_V16_STORY_SELECTION_STABLE"

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSET_DIR = BASE_DIR / "assets" / "source"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"
FINAL_IMAGE = ASSET_DIR / "story_image.jpg"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

HISTORY_FILE = DATA_DIR / "story_history.json"

REQUEST_TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


PUBLISHERS = [
    {
        "name": "Citizen Digital",
        "url": "https://citizen.digital/",
        "domain": "citizen.digital",
    },
    {
        "name": "The Star",
        "url": "https://www.the-star.co.ke/news/",
        "domain": "the-star.co.ke",
    },
    {
        "name": "KBC",
        "url": "https://www.kbc.co.ke/",
        "domain": "kbc.co.ke",
    },
    {
        "name": "Nation Africa",
        "url": "https://nation.africa/kenya/news",
        "domain": "nation.africa",
    },
]


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


RUTO_TERMS = [
    "william ruto",
    "president ruto",
    "president william ruto",
    "head of state",
    "state house",
    "presidential tour",
    "working tour",
    "president",
    "ruto",
]


DEVELOPMENT_TERMS = [
    "road",
    "roads",
    "hospital",
    "hospitals",
    "market",
    "markets",
    "water",
    "electricity",
    "housing",
    "school",
    "schools",
    "tvet",
    "agriculture",
    "industrial park",
    "industrial parks",
    "manufacturing",
    "infrastructure",
    "project",
    "projects",
    "jobs",
    "airport",
    "airports",
    "port",
    "ports",
    "railway",
    "development",
    "construction",
]


POLITICAL_TERMS = [
    "politics",
    "political",
    "2027",
    "election",
    "elections",
    "opposition",
    "campaign",
    "alliance",
    "coalition",
    "party",
    "parties",
    "leader",
    "leaders",
    "mp",
    "senator",
    "governor",
    "uda",
    "odm",
]


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    if not value:
        return ""

    value = BeautifulSoup(str(value), "html.parser").get_text(" ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(url):
    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    if url.startswith("/"):
        return ""

    return url


def domain_allowed(url):
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False

    host = host.split(":")[0]

    if host in BLOCKED_DOMAINS:
        return False

    return any(
        host == domain or host.endswith("." + domain)
        for domain in [
            "citizen.digital",
            "the-star.co.ke",
            "kbc.co.ke",
            "nation.africa",
        ]
    )


def article_is_relevant(title, summary):
    text = f"{title} {summary}".lower()

    county_hit = any(
        county.lower() in text
        for county in COUNTIES
    )

    ruto_hit = any(
        term in text
        for term in RUTO_TERMS
    )

    development_hit = any(
        term in text
        for term in DEVELOPMENT_TERMS
    )

    political_hit = any(
        term in text
        for term in POLITICAL_TERMS
    )

    return (
        county_hit
        or ruto_hit
        or (development_hit and political_hit)
    )


def determine_story_type(title, summary):
    text = f"{title} {summary}".lower()

    county_hit = any(
        county.lower() in text
        for county in COUNTIES
    )

    ruto_hit = any(
        term in text
        for term in RUTO_TERMS
    )

    development_hit = any(
        term in text
        for term in DEVELOPMENT_TERMS
    )

    political_hit = any(
        term in text
        for term in POLITICAL_TERMS
    )

    if ruto_hit and development_hit:
        return "Ruto Development Tour"

    if ruto_hit and political_hit:
        return "Ruto Political Tour"

    if ruto_hit:
        return "Ruto National Tour"

    if county_hit:
        return "Rift Valley"

    if development_hit:
        return "Development"

    if political_hit:
        return "Politics"

    return "County News"


def detect_county(title, summary):
    text = f"{title} {summary}".lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county

    return "Rift Valley"


def load_history():
    if not HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(
            HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            return data

    except Exception:
        pass

    return []


def save_history(history):
    history = history[-100:]

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def story_key(article):
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


def extract_image_from_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:
        print(
            f"[IMAGE] Page request failed: {exc}"
        )
        return ""

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates = []

    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = meta.get("content")

        if not content:
            continue

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:
            candidates.append(content)

    for img in soup.find_all("img"):
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-lazy-src")
            or ""
        )

        if src:
            candidates.append(
                urljoin(
                    url,
                    src,
                )
            )

    for candidate in candidates:
        candidate = urljoin(
            url,
            candidate,
        )

        if candidate.startswith("data:"):
            continue

        if candidate.lower().endswith(
            (
                ".svg",
                ".gif",
            )
        ):
            continue

        return candidate

    return ""


def download_image(image_url):
    if not image_url:
        return False

    try:
        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        if len(response.content) < 10000:
            print(
                "[IMAGE] Image response too small."
            )
            return False

        temp_file = ASSET_DIR / "story_image_temp"

        temp_file.write_bytes(
            response.content
        )

        try:
            image = Image.open(
                temp_file
            )

            image.verify()

        except Exception as exc:
            print(
                f"[IMAGE] Invalid image: {exc}"
            )

            try:
                temp_file.unlink()
            except Exception:
                pass

            return False

        temp_file.replace(
            FINAL_IMAGE
        )

        print(
            f"[IMAGE] Saved: {FINAL_IMAGE}"
        )

        return True

    except Exception as exc:
        print(
            f"[IMAGE] Download failed: {exc}"
        )
        return False


def fetch_page_links(publisher):
    print(
        f"[FETCH] {publisher['name']}: "
        f"{publisher['url']}"
    )

    try:
        response = requests.get(
            publisher["url"],
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:
        print(
            f"[FETCH] Failed: {exc}"
        )
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    links = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href = normalize_url(
            urljoin(
                publisher["url"],
                anchor.get("href"),
            )
        )

        title = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not href or not title:
            continue

        if not domain_allowed(href):
            continue

        if len(title) < 20:
            continue

        links.append(
            {
                "url": href,
                "link_title": title,
                "publisher": publisher["name"],
                "domain": publisher["domain"],
            }
        )

    unique = []
    seen = set()

    for item in links:
        if item["url"] in seen:
            continue

        seen.add(
            item["url"]
        )

        unique.append(item)

    print(
        f"[FETCH] {publisher['name']}: "
        f"{len(unique)} links found."
    )

    return unique[:100]


def extract_article(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

    except Exception as exc:
        print(
            f"[ARTICLE] Request failed: {exc}"
        )
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    title = ""

    for selector in [
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "twitter:title"}),
    ]:
        node = soup.find(
            selector[0],
            selector[1],
        )

        if node and node.get("content"):
            title = clean_text(
                node.get("content")
            )
            break

    if not title:
        node = soup.find("h1")

        if node:
            title = clean_text(
                node.get_text(
                    " ",
                    strip=True,
                )
            )

    if not title and soup.title:
        title = clean_text(
            soup.title.get_text()
        )

    paragraphs = []

    for paragraph in soup.find_all(
        "p"
    ):
        text = clean_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) >= 40:
            paragraphs.append(text)

    body = " ".join(
        paragraphs[:30]
    )

    summary = body[:1500]

    image_url = ""

    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = meta.get("content")

        if not content:
            continue

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:
            image_url = urljoin(
                url,
                content,
            )
            break

    if not image_url:
        image_url = extract_image_from_page(
            url
        )

    if not title:
        return None

    if len(body.split()) < 35:
        return None

    return {
        "title": title,
        "url": url,
        "body": body,
        "summary": summary,
        "image_url": image_url,
    }


def score_article(article):
    title = article.get(
        "title",
        "",
    )

    body = article.get(
        "body",
        "",
    )

    text = f"{title} {body}".lower()

    score = 0

    for county in COUNTIES:
        if county.lower() in text:
            score += 35

    ruto_count = sum(
        1
        for term in RUTO_TERMS
        if term in text
    )

    development_count = sum(
        1
        for term in DEVELOPMENT_TERMS
        if term in text
    )

    political_count = sum(
        1
        for term in POLITICAL_TERMS
        if term in text
    )

    score += ruto_count * 18
    score += development_count * 8
    score += political_count * 6

    if len(body.split()) >= 100:
        score += 10

    if article.get("image_url"):
        score += 20

    return score


def collect_candidates():
    candidates = []

    for publisher in PUBLISHERS:
        links = fetch_page_links(
            publisher
        )

        for link in links:
            title = link["link_title"]

            if not article_is_relevant(
                title,
                title,
            ):
                continue

            article = extract_article(
                link["url"]
            )

            if not article:
                continue

            article["publisher"] = (
                link["publisher"]
            )

            article["domain"] = (
                link["domain"]
            )

            if not article_is_relevant(
                article["title"],
                article["body"],
            ):
                continue

            article["story_type"] = (
                determine_story_type(
                    article["title"],
                    article["body"],
                )
            )

            article["county"] = (
                detect_county(
                    article["title"],
                    article["body"],
                )
            )

            article["score"] = score_article(
                article
            )

            candidates.append(
                article
            )

    unique = []
    seen = set()

    for article in sorted(
        candidates,
        key=lambda x: x.get(
            "score",
            0,
        ),
        reverse=True,
    ):
        key = (
            article.get("title", "")
            .strip()
            .lower()
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(article)

    return unique


def choose_story(candidates):
    history = load_history()

    recent_keys = set(
        history[-20:]
    )

    available = [
        article
        for article in candidates
        if story_key(article)
        not in recent_keys
    ]

    if not available:
        print(
            "[SELECT] All candidates were "
            "recently used. Resetting rotation."
        )

        available = candidates

    if not available:
        raise RuntimeError(
            "No usable news candidates were found."
        )

    run_number = int(
        os.environ.get(
            "GITHUB_RUN_NUMBER",
            "0",
        )
    )

    attempt = int(
        os.environ.get(
            "GITHUB_RUN_ATTEMPT",
            "1",
        )
    )

    rotation = (
        run_number
        + attempt
    ) % min(
        10,
        len(available),
    )

    ordered = (
        available[rotation:]
        + available[:rotation]
    )

    print(
        f"[SELECT] Candidates available: "
        f"{len(available)}"
    )

    for index, article in enumerate(
        ordered[:10],
        start=1,
    ):
        print(
            f"[CANDIDATE {index}] "
            f"{article['title']} "
            f"| score={article['score']} "
            f"| {article['publisher']}"
        )

    return ordered


def build_narration(article):
    title = clean_text(
        article.get(
            "title",
            "",
        )
    )

    body = clean_text(
        article.get(
            "body",
            "",
        )
    )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        body,
    )

    sentences = [
        clean_text(sentence)
        for sentence in sentences
        if len(
            clean_text(sentence).split()
        ) >= 6
    ]

    selected = []

    for sentence in sentences:
        candidate = " ".join(
            selected
            + [sentence]
        )

        if len(
            candidate.split()
        ) > 145:
            break

        selected.append(sentence)

        if len(
            candidate.split()
        ) >= 75:
            break

    narration = (
        f"{title}. "
        + " ".join(selected)
    )

    narration = clean_text(
        narration
    )

    return narration


def word_count(text):
    return len(
        re.findall(
            r"\b\w+\b",
            text or "",
        )
    )


def split_sentences(text):
    return re.split(
        r"(?<=[.!?])\s+",
        text or "",
    )


def sentence_key(sentence):
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        sentence.lower(),
    ).strip()


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


def write_story(article):
    data = {
        "title": article["title"],
        "url": article["url"],
        "story_type": article["story_type"],
        "county": article["county"],
        "publisher": article.get(
            "publisher",
            "",
        ),
        "domain": article.get(
            "domain",
            "",
        ),
        "image_url": article.get(
            "image_url",
            "",
        ),
        "body": article.get(
            "body",
            "",
        ),
        "summary": article.get(
            "summary",
            "",
        ),
        "score": article.get(
            "score",
            0,
        ),
    }

    STORY_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"[STORY] selected_story.json written: "
        f"{STORY_FILE}"
    )


def write_script(article, narration):
    data = {
        "title": article["title"],
        "county": article["county"],
        "story_type": article["story_type"],
        "narration": narration,
    }

    SCRIPT_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"[SCRIPT] selected_script.json written: "
        f"{SCRIPT_FILE}"
    )


def run_generator():
    generator = (
        BASE_DIR
        / "rift_valley_video_generator.py"
    )

    if not generator.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py "
            "was not found."
        )

    print(
        "[VIDEO] Starting video generator..."
    )

    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(generator),
        ],
        cwd=str(BASE_DIR),
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Video generator failed with "
            f"exit code {result.returncode}."
        )


def verify_mp4():
    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not generated."
        )

    if FINAL_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is unexpectedly small."
        )

    print(
        f"[VIDEO] Final MP4 verified: "
        f"{FINAL_VIDEO}"
    )


def main():
    ensure_directories()

    print("=" * 70)
    print(VERSION)
    print("=" * 70)

    # Remove only files that must be regenerated.
    for file in [
        STORY_FILE,
        SCRIPT_FILE,
        FINAL_IMAGE,
    ]:
        try:
            if file.exists():
                file.unlink()
        except Exception:
            pass

    print()
    print("=" * 70)
    print("COLLECTING CURRENT NEWS")
    print("=" * 70)

    candidates = collect_candidates()

    print(
        f"[RESULT] Total usable candidates: "
        f"{len(candidates)}"
    )

    if not candidates:
        raise RuntimeError(
            "No relevant current stories were found "
            "from the approved publishers."
        )

    print()
    print("=" * 70)
    print("SELECTING STORY")
    print("=" * 70)

    ordered_candidates = choose_story(
        candidates
    )

    selected = None

    for index, article in enumerate(
        ordered_candidates,
        start=1,
    ):
        print()
        print(
            f"[TRY {index}] "
            f"{article['title']}"
        )

        image_url = article.get(
            "image_url",
            "",
        )

        if not image_url:
            print(
                "[REJECT] No article image found."
            )
            continue

        print(
            f"[IMAGE] {image_url}"
        )

        if not download_image(
            image_url
        ):
            print(
                "[REJECT] Article image "
                "could not be downloaded."
            )
            continue

        narration = build_narration(
            article
        )

        if word_count(
            narration
        ) < 45:
            print(
                "[REJECT] Narration too short."
            )
            continue

        try:
            validate(
                article,
                narration,
            )
        except Exception as exc:
            print(
                f"[REJECT] Validation failed: "
                f"{exc}"
            )
            continue

        selected = article
        break

    if selected is None:
        raise RuntimeError(
            "No candidate passed story and image "
            "validation. selected_story.json "
            "was therefore not created."
        )

    print()
    print("=" * 70)
    print("SELECTED STORY")
    print("=" * 70)

    print(
        f"HEADLINE: {selected['title']}"
    )

    print(
        f"COUNTY: {selected['county']}"
    )

    print(
        f"TYPE: {selected['story_type']}"
    )

    print(
        f"IMAGE: {selected['image_url']}"
    )

    # IMPORTANT:
    # Write selected_story.json BEFORE starting
    # the video generator.
    write_story(
        selected
    )

    narration = build_narration(
        selected
    )

    write_script(
        selected,
        narration,
    )

    history = load_history()

    key = story_key(
        selected
    )

    if key not in history:
        history.append(key)

    save_history(
        history
    )

    print()
    print("=" * 70)
    print("VERIFYING STORY FILES")
    print("=" * 70)

    if not STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json was not created."
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "selected_script.json was not created."
        )

    if not FINAL_IMAGE.exists():
        raise RuntimeError(
            "Story image was not created."
        )

    print(
        "[OK] selected_story.json exists."
    )

    print(
        "[OK] selected_script.json exists."
    )

    print(
        "[OK] story_image.jpg exists."
    )

    print()
    print("=" * 70)
    print("STARTING VIDEO GENERATOR")
    print("=" * 70)

    run_generator()

    verify_mp4()

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "Generation interrupted."
        )
        sys.exit(1)
    except Exception as exc:
        print()
        print("=" * 70)
        print("GENERATION FAILED")
        print("=" * 70)
        print(
            f"ERROR: {exc}"
        )
        print("=" * 70)
        sys.exit(1)
