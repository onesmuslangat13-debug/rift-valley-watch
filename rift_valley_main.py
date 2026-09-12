# ============================================================
# RIFT VALLEY WATCH
# MAIN PIPELINE V8
#
# COMPLETE REPLACEMENT
#
# Purpose:
#   1. Load the verified story.
#   2. Reject Google News / Facebook / junk stories.
#   3. Recover a real article image.
#   4. Save the image to assets/source/story_image.jpg.
#   5. Attach story["local_image"].
#   6. Generate clean narration text.
#   7. Call rift_valley_video_generator.video_generator(story).
#   8. Validate the final MP4.
#
# IMPORTANT:
#   This file is intentionally independent of the old broken
#   1,600+ line rift_valley_main.py.
# ============================================================

import os
import re
import io
import json
import html
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ASSETS_DIR / "audio"
OUTPUT_DIR = ROOT / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"

SCRIPT_FILE = DATA_DIR / "script.txt"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

# Some versions of the generator use this filename.
GENERATOR_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"

VISUAL_REPORT = OUTPUT_DIR / "visual_report.json"


# ============================================================
# SETTINGS
# ============================================================

REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

COUNTIES = {
    "bomet",
    "kericho",
    "nakuru",
    "nandi",
    "uasin gishu",
    "elgeyo-marakwet",
    "elgeyo marakwet",
    "west pokot",
    "narok",
}


# ============================================================
# BAD CONTENT FILTERS
# ============================================================

BAD_IMAGE_TERMS = [
    "google",
    "google-news",
    "google_news",
    "facebook",
    "fbcdn",
    "favicon",
    "logo",
    "icon",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "sprite",
    "tracking",
    "tracker",
    "pixel",
    "blank",
    "spinner",
    "loading",
    ".svg",
]

BAD_STORY_TERMS = [
    "google news",
    "google-news",
    "facebook",
    "facebook.com",
    "read more on google",
    "google news app",
    "google news story",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def is_http_url(value):
    value = clean_text(value).lower()

    return (
        value.startswith("http://")
        or value.startswith("https://")
    )


# ============================================================
# COMMAND HELPERS
# ============================================================

def command_exists(name):
    return shutil.which(name) is not None


def run_command(command, check=True):
    print()
    print("COMMAND:")
    print(" ".join(str(x) for x in command))
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.stdout:
        print(result.stdout[-5000:])

    if result.stderr:
        print(result.stderr[-5000:])

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code "
            f"{result.returncode}"
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    path = Path(path)

    if not path.exists():
        return None

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        print(
            f"WARNING: Failed reading {path}: {exc}"
        )

        return None


def save_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with open(
        temporary,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        temporary,
        path,
    )


# ============================================================
# STORY LOADING
# ============================================================

def load_story():
    story = load_json(
        STORY_FILE
    )

    if not story:
        story = load_json(
            SELECTED_STORY_FILE
        )

    if not story:
        raise RuntimeError(
            "No usable story was found in "
            "data/story.json or "
            "data/selected_story.json."
        )

    if not isinstance(story, dict):
        raise RuntimeError(
            "Story JSON must contain an object."
        )

    return story


# ============================================================
# STORY FIELDS
# ============================================================

def get_source_name(story):
    source = story.get("source")

    if isinstance(source, dict):
        return clean_text(
            source.get("name")
            or source.get("publisher")
            or ""
        )

    if isinstance(source, str):
        if is_http_url(source):
            return ""

        return clean_text(source)

    return ""


def get_source_url(story):
    source = story.get("source")

    if isinstance(source, dict):
        return clean_text(
            source.get("url")
            or source.get("link")
            or source.get("source_url")
            or ""
        )

    if isinstance(source, str):
        if is_http_url(source):
            return clean_text(source)

    return ""


def get_title(story):
    return clean_text(
        story.get("title")
        or story.get("headline")
        or ""
    )


def get_county(story):
    return clean_text(
        story.get("county")
        or story.get("location")
        or "Rift Valley"
    )


def get_summary(story):
    return clean_text(
        story.get("summary")
        or story.get("description")
        or ""
    )


# ============================================================
# STORY QUALITY CONTROL
# ============================================================

def contains_bad_story_text(value):
    value = clean_text(value).lower()

    for term in BAD_STORY_TERMS:
        if term in value:
            return True

    return False


def validate_story(story):
    print()
    print("=" * 60)
    print("STORY QUALITY CONTROL")
    print("=" * 60)

    title = get_title(story)
    county = get_county(story)
    summary = get_summary(story)
    source = get_source_name(story)
    url = get_source_url(story)

    if not title:
        raise RuntimeError(
            "Story rejected: missing title."
        )

    if not county:
        raise RuntimeError(
            "Story rejected: missing county."
        )

    if not source:
        raise RuntimeError(
            "Story rejected: missing publisher name."
        )

    if not url:
        raise RuntimeError(
            "Story rejected: missing source URL."
        )

    if contains_bad_story_text(title):
        raise RuntimeError(
            "Story rejected: title contains "
            "Google News/Facebook boilerplate."
        )

    if contains_bad_story_text(summary):
        raise RuntimeError(
            "Story rejected: summary contains "
            "Google News/Facebook boilerplate."
        )

    if contains_bad_story_text(source):
        raise RuntimeError(
            "Story rejected: invalid source."
        )

    county_normalized = county.lower()

    if county_normalized not in COUNTIES:
        print(
            "WARNING: County is outside configured "
            "Rift Valley county list:",
            county,
        )

    print("TITLE :", title)
    print("COUNTY:", county)
    print("SOURCE:", source)
    print("URL   :", url)

    return True


# ============================================================
# IMAGE VALIDATION
# ============================================================

def valid_image_file(path):
    if not path:
        return False

    try:
        path = Path(path)

        if not path.exists():
            return False

        if path.stat().st_size < 10_000:
            return False

        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

            if width < 300:
                return False

            if height < 200:
                return False

        return True

    except Exception as exc:
        print(
            "IMAGE VALIDATION FAILED:",
            path,
            exc,
        )

        return False


def valid_image_bytes(data):
    try:
        with Image.open(
            io.BytesIO(data)
        ) as image:
            width, height = image.size

            if width < 300:
                return False

            if height < 200:
                return False

            image.verify()

        return True

    except Exception:
        return False


def bad_image_url(url):
    if not url:
        return True

    value = str(url).lower()

    for term in BAD_IMAGE_TERMS:
        if term in value:
            return True

    return False


# ============================================================
# LOCAL IMAGE SEARCH
# ============================================================

def local_image_candidates(story):
    candidates = []

    for key in [
        "local_image",
        "image_path",
        "localImage",
        "local_image_path",
    ]:
        value = story.get(key)

        if value:
            candidates.append(
                Path(str(value))
            )

    candidates.extend([
        IMAGE_FILE,
        SOURCE_DIR / "story_image.png",
        SOURCE_DIR / "story_image.webp",
        SOURCE_DIR / "article_image.jpg",
        SOURCE_DIR / "article_image.png",
        SOURCE_DIR / "article_image.webp",
        DATA_DIR / "story_image.jpg",
        DATA_DIR / "story_image.png",
        ROOT / "story_image.jpg",
    ])

    unique = []

    seen = set()

    for candidate in candidates:
        try:
            candidate = Path(candidate)

            if not candidate.is_absolute():
                candidate = ROOT / candidate

            candidate = candidate.resolve()

            key = str(candidate).lower()

            if key in seen:
                continue

            seen.add(key)
            unique.append(candidate)

        except Exception:
            continue

    return unique


def find_local_image(story):
    print()
    print("=" * 60)
    print("LOCAL SOURCE IMAGE CHECK")
    print("=" * 60)

    for candidate in local_image_candidates(
        story
    ):
        print(
            "CHECK:",
            candidate,
        )

        if valid_image_file(candidate):
            print(
                "VALID LOCAL IMAGE:",
                candidate,
            )

            return str(candidate)

    print(
        "No valid local source image found."
    )

    return None


# ============================================================
# HTML IMAGE EXTRACTION
# ============================================================

def extract_srcset(value):
    results = []

    if not value:
        return results

    for item in str(value).split(","):
        item = item.strip()

        if not item:
            continue

        parts = item.split()

        if parts:
            results.append(
                parts[0]
            )

    return results


def add_candidate(
    candidates,
    value,
    base_url,
):
    if not value:
        return

    value = clean_text(value)

    if not value:
        return

    if value.startswith("//"):
        value = "https:" + value

    value = urljoin(
        base_url,
        value,
    )

    if not is_http_url(value):
        return

    if bad_image_url(value):
        return

    candidates.append(value)


def extract_images_from_html(
    html_text,
    base_url,
):
    candidates = []

    if not html_text:
        return candidates

    if BeautifulSoup is None:
        print(
            "WARNING: BeautifulSoup unavailable."
        )

        return candidates

    soup = BeautifulSoup(
        html_text,
        "html.parser",
    )

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    selectors = [
        (
            "meta",
            {"property": "og:image"},
        ),
        (
            "meta",
            {"property": "og:image:url"},
        ),
        (
            "meta",
            {"name": "twitter:image"},
        ),
        (
            "meta",
            {"property": "twitter:image"},
        ),
        (
            "meta",
            {"name": "twitter:image:src"},
        ),
        (
            "meta",
            {"itemprop": "image"},
        ),
    ]

    for tag_name, attrs in selectors:
        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):
            add_candidate(
                candidates,
                tag.get("content")
                or tag.get("href"),
                base_url,
            )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    ):
        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        def inspect(value):
            found = []

            if isinstance(
                value,
                dict,
            ):
                for key, item in value.items():

                    if str(key).lower() == "image":

                        if isinstance(
                            item,
                            str,
                        ):
                            found.append(item)

                        elif isinstance(
                            item,
                            list,
                        ):
                            for entry in item:
                                if isinstance(
                                    entry,
                                    str,
                                ):
                                    found.append(
                                        entry
                                    )

                                elif isinstance(
                                    entry,
                                    dict,
                                ):
                                    for field in [
                                        "url",
                                        "contentUrl",
                                    ]:
                                        if entry.get(
                                            field
                                        ):
                                            found.append(
                                                entry[
                                                    field
                                                ]
                                            )

                        elif isinstance(
                            item,
                            dict,
                        ):
                            for field in [
                                "url",
                                "contentUrl",
                            ]:
                                if item.get(field):
                                    found.append(
                                        item[field]
                                    )

                    found.extend(
                        inspect(item)
                    )

            elif isinstance(
                value,
                list,
            ):
                for entry in value:
                    found.extend(
                        inspect(entry)
                    )

            return found

        for image in inspect(data):
            add_candidate(
                candidates,
                image,
                base_url,
            )

    # --------------------------------------------------------
    # ARTICLE IMAGES
    # --------------------------------------------------------

    containers = []

    for selector in [
        "article",
        "main",
        "[role='main']",
        ".article",
        ".story",
        ".post",
        ".entry-content",
        ".article-content",
        ".story-content",
    ]:
        try:
            containers.extend(
                soup.select(selector)
            )
        except Exception:
            pass

    if not containers:
        containers = [soup]

    for container in containers:

        for image in container.find_all(
            "img"
        ):

            for attr in [
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-lazy",
            ]:
                add_candidate(
                    candidates,
                    image.get(attr),
                    base_url,
                )

            for attr in [
                "srcset",
                "data-srcset",
                "data-lazy-srcset",
            ]:
                for value in extract_srcset(
                    image.get(attr)
                ):
                    add_candidate(
                        candidates,
                        value,
                        base_url,
                    )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    unique = []

    seen = set()

    for url in candidates:

        key = url.lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(url)

    return unique


# ============================================================
# WORDPRESS FALLBACK
# ============================================================

def wordpress_image_candidates(
    article_url
):
    candidates = []

    parsed = urlparse(
        article_url
    )

    if not parsed.scheme:
        return candidates

    if not parsed.netloc:
        return candidates

    base = (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
    )

    api = (
        base.rstrip("/")
        + "/wp-json/wp/v2/posts"
    )

    try:
        response = requests.get(
            api,
            params={
                "per_page": 100,
            },
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        if not response.ok:
            return candidates

        posts = response.json()

        target_path = (
            parsed.path.rstrip("/")
        )

        for post in posts:

            link = clean_text(
                post.get("link")
            )

            if not link:
                continue

            post_path = (
                urlparse(link)
                .path
                .rstrip("/")
            )

            if (
                target_path != post_path
                and target_path not in post_path
                and post_path not in target_path
            ):
                continue

            media_id = post.get(
                "featured_media"
            )

            if not media_id:
                continue

            media_api = (
                base.rstrip("/")
                + "/wp-json/wp/v2/media/"
                + str(media_id)
            )

            media_response = requests.get(
                media_api,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            if not media_response.ok:
                continue

            media = media_response.json()

            source_url = clean_text(
                media.get("source_url")
            )

            if source_url:
                add_candidate(
                    candidates,
                    source_url,
                    base,
                )

    except Exception as exc:
        print(
            "WordPress fallback failed:",
            exc,
        )

    return candidates


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_source_image(
    image_url,
):
    print()
    print(
        "DOWNLOADING IMAGE:"
    )
    print(image_url)

    response = requests.get(
        image_url,
        headers={
            **HEADERS,
            "Referer": "",
        },
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    data = response.content

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
        .lower()
    )

    if (
        "image" not in content_type
        and not valid_image_bytes(data)
    ):
        raise RuntimeError(
            "URL did not return a valid image."
        )

    if not valid_image_bytes(data):
        raise RuntimeError(
            "Downloaded content failed "
            "image validation."
        )

    with Image.open(
        io.BytesIO(data)
    ) as image:

        image = image.convert(
            "RGB"
        )

        image.save(
            IMAGE_FILE,
            "JPEG",
            quality=95,
        )

    if not valid_image_file(
        IMAGE_FILE
    ):
        raise RuntimeError(
            "Saved source image failed "
            "validation."
        )

    return str(IMAGE_FILE)


# ============================================================
# SOURCE IMAGE RECOVERY
# ============================================================

def recover_source_image(
    story
):
    # --------------------------------------------------------
    # 1. LOCAL IMAGE
    # --------------------------------------------------------

    local = find_local_image(
        story
    )

    if local:
        return local

    # --------------------------------------------------------
    # 2. ARTICLE URL
    # --------------------------------------------------------

    article_url = get_source_url(
        story
    )

    if not article_url:
        raise RuntimeError(
            "No source URL is available "
            "for image recovery."
        )

    print()
    print("=" * 60)
    print("ARTICLE IMAGE RECOVERY")
    print("=" * 60)

    print(
        "ARTICLE:",
        article_url,
    )

    candidates = []

    # --------------------------------------------------------
    # 3. FETCH ARTICLE
    # --------------------------------------------------------

    try:
        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = (
            response.url
            or article_url
        )

        candidates.extend(
            extract_images_from_html(
                response.text,
                final_url,
            )
        )

        print(
            "HTML IMAGE CANDIDATES:",
            len(candidates),
        )

    except Exception as exc:
        print(
            "Article fetch/image extraction failed:",
            exc,
        )

    # --------------------------------------------------------
    # 4. WORDPRESS
    # --------------------------------------------------------

    try:
        candidates.extend(
            wordpress_image_candidates(
                article_url
            )
        )

    except Exception as exc:
        print(
            "WordPress recovery failed:",
            exc,
        )

    # --------------------------------------------------------
    # 5. UNIQUE
    # --------------------------------------------------------

    unique = []

    seen = set()

    for url in candidates:

        url = clean_text(url)

        if not url:
            continue

        if bad_image_url(url):
            continue

        key = url.lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(url)

    print(
        "TOTAL IMAGE CANDIDATES:",
        len(unique),
    )

    # --------------------------------------------------------
    # 6. TRY IMAGES
    # --------------------------------------------------------

    for index, url in enumerate(
        unique[:50],
        1,
    ):

        print()
        print(
            f"TRY IMAGE {index}/{min(len(unique), 50)}"
        )
        print(url)

        try:
            saved = (
                download_source_image(
                    url
                )
            )

            if valid_image_file(
                saved
            ):
                print()
                print(
                    "REAL SOURCE IMAGE RECOVERED:"
                )
                print(saved)

                return saved

        except Exception as exc:
            print(
                "Rejected:",
                exc,
            )

    raise RuntimeError(
        "No usable real article image "
        "could be recovered. The reel "
        "was stopped instead of using "
        "a fake or placeholder image."
    )


# ============================================================
# FACT EXTRACTION
# ============================================================

def get_fact(
    story,
    label,
):
    facts = (
        story.get(
            "verified_facts"
        )
        or []
    )

    for fact in facts:

        if not isinstance(
            fact,
            dict,
        ):
            continue

        fact_label = clean_text(
            fact.get("label")
        ).upper()

        if fact_label == label.upper():
            return clean_text(
                fact.get("value")
            )

    return ""


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story
):
    title = get_title(
        story
    )

    county = get_county(
        story
    )

    summary = get_summary(
        story
    )

    source = get_source_name(
        story
    )

    road_length = get_fact(
        story,
        "ROAD_LENGTH",
    )

    cost = get_fact(
        story,
        "COST",
    )

    location = get_fact(
        story,
        "LOCATION",
    )

    status = get_fact(
        story,
        "STATUS",
    )

    impact = get_fact(
        story,
        "IMPACT",
    )

    parts = []

    parts.append(
        f"Rift Valley Watch. "
        f"Here is the latest development "
        f"from {county}."
    )

    parts.append(
        title + "."
    )

    if road_length:
        parts.append(
            f"The project covers "
            f"{road_length}."
        )

    if cost:
        parts.append(
            f"The reported project cost "
            f"is {cost}."
        )

    if location:
        parts.append(
            f"The project is located in "
            f"{location}."
        )

    if status:
        parts.append(
            f"The current status is "
            f"{status.lower()}."
        )

    if impact:
        parts.append(
            f"The project is expected to "
            f"{impact.lower()}."
        )

    if summary:
        summary_clean = summary

        if (
            summary_clean.lower()
            not in " ".join(parts).lower()
        ):
            parts.append(
                summary_clean
            )

    if source:
        parts.append(
            f"According to {source}."
        )

    narration = " ".join(
        clean_text(x)
        for x in parts
        if clean_text(x)
    )

    # Remove accidental duplicate whitespace.
    narration = re.sub(
        r"\s+",
        " ",
        narration,
    ).strip()

    return narration


def save_narration(
    narration
):
    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            narration
        )

    return SCRIPT_FILE


# ============================================================
# PREPARE STORY
# ============================================================

def prepare_story(
    story
):
    image_path = recover_source_image(
        story
    )

    story["local_image"] = str(
        Path(image_path).resolve()
    )

    # Keep source structured.
    source = story.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        source["name"] = get_source_name(
            story
        )

        source["url"] = get_source_url(
            story
        )

        story["source"] = source

    narration = build_narration(
        story
    )

    story["narration"] = narration

    story["script"] = narration

    story["audio_text"] = narration

    save_narration(
        narration
    )

    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    print()
    print("=" * 60)
    print("STORY PREPARED")
    print("=" * 60)

    print(
        "IMAGE:",
        story["local_image"],
    )

    print(
        "SOURCE:",
        get_source_name(story),
    )

    print(
        "NARRATION:",
        narration,
    )

    return story


# ============================================================
# IMPORT GENERATOR
# ============================================================

def import_video_generator():
    print()
    print("=" * 60)
    print("LOADING VIDEO GENERATOR")
    print("=" * 60)

    # Most common project location.
    try:
        import rift_valley_video_generator

        print(
            "Loaded:",
            "rift_valley_video_generator",
        )

        return (
            rift_valley_video_generator
        )

    except Exception as first_error:

        print(
            "Normal import failed:",
            first_error,
        )

    # Explicit dynamic import.
    generator_file = (
        ROOT
        / "rift_valley_video_generator.py"
    )

    if not generator_file.exists():
        raise RuntimeError(
            "rift_valley_video_generator.py "
            "was not found in the repository root."
        )

    import importlib.util

    spec = (
        importlib.util.spec_from_file_location(
            "rift_valley_video_generator",
            str(generator_file),
        )
    )

    if spec is None:
        raise RuntimeError(
            "Could not create generator import spec."
        )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        module
    )

    print(
        "Loaded generator from:",
        generator_file,
    )

    return module


# ============================================================
# GENERATOR EXECUTION
# ============================================================

def run_video_generator(
    story
):
    generator = (
        import_video_generator()
    )

    if not hasattr(
        generator,
        "video_generator",
    ):
        raise RuntimeError(
            "rift_valley_video_generator.py "
            "does not expose video_generator()."
        )

    function = (
        generator.video_generator
    )

    print()
    print("=" * 60)
    print("STARTING VIDEO GENERATION")
    print("=" * 60)

    # IMPORTANT:
    # Current V7 generator expects ONE story argument.
    result = function(
        story
    )

    print()
    print(
        "VIDEO GENERATOR RETURNED:",
        result,
    )

    return result


# ============================================================
# FINAL VIDEO DISCOVERY
# ============================================================

def locate_final_video():
    candidates = [
        FINAL_VIDEO,
        GENERATOR_VIDEO,
        OUTPUT_DIR
        / "rift_valley_watch.mp4",
        OUTPUT_DIR
        / "rift_valley_watch_reel.mp4",
        OUTPUT_DIR
        / "final.mp4",
    ]

    for candidate in candidates:

        if not candidate.exists():
            continue

        try:
            if candidate.stat().st_size < 100_000:
                continue
        except Exception:
            continue

        return candidate

    return None


# ============================================================
# MP4 VALIDATION
# ============================================================

def validate_video(
    video_path
):
    video_path = Path(
        video_path
    )

    if not video_path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if video_path.stat().st_size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    if not command_exists(
        "ffprobe"
    ):
        print(
            "WARNING: ffprobe unavailable; "
            "performing file
