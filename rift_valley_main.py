# ============================================================
# RIFT VALLEY WATCH
# MAIN NEWS ENGINE
# COMPLETE REPLACEMENT
#
# Purpose:
#   1. Load and validate data/story.json
#   2. Reject Google News / Facebook junk
#   3. Recover and validate a real article image
#   4. Create clean narration script
#   5. Save selected_story.json
#   6. Run rift_valley_video_generator.py
#   7. Validate final MP4
#   8. Copy final video to:
#        output/rift_valley_watch_reel.mp4
#
# No YouTube upload.
# One story per reel.
# 1080x1920 vertical.
# ============================================================

import os
import re
import sys
import json
import shutil
import subprocess
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ASSETS_DIR / "audio"
SCENES_DIR = OUTPUT_DIR / "scenes"

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

CANONICAL_IMAGE = SOURCE_DIR / "story_image.jpg"

FINAL_GENERATOR_OUTPUT = OUTPUT_DIR / "rift_valley_watch.mp4"
FINAL_REEL = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

REPORT_FILE = DATA_DIR / "visual_report.json"


# ============================================================
# VIDEO REQUIREMENTS
# ============================================================

EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920

MIN_DURATION = 15.0
MAX_DURATION = 90.0

MIN_FILE_SIZE = 100 * 1024


# ============================================================
# HTTP SETTINGS
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# BASIC UTILITIES
# ============================================================

def log(message=""):
    print(message, flush=True)


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Required JSON file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file: {path}\n{exc}"
        ) from exc


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            indent=2,
            ensure_ascii=False,
        )


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def safe_filename(value):
    value = clean_text(value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:100]


# ============================================================
# STORY FIELD HELPERS
# ============================================================

def story_title(story):
    return clean_text(
        story.get("title")
        or story.get("headline")
        or story.get("name")
    )


def story_summary(story):
    return clean_text(
        story.get("summary")
        or story.get("description")
        or story.get("dek")
        or story.get("excerpt")
    )


def story_county(story):
    return clean_text(
        story.get("county")
        or story.get("location")
        or ""
    )


def story_category(story):
    return clean_text(
        story.get("category")
        or "COUNTY NEWS"
    )


def story_date(story):
    return clean_text(
        story.get("date")
        or story.get("published_at")
        or story.get("published")
        or ""
    )


def source_object(story):
    source = story.get("source")

    if isinstance(source, dict):
        return source

    if isinstance(source, str):
        return {
            "name": source,
            "url": story.get("url", ""),
        }

    return {}


def source_name(story):
    source = source_object(story)

    return clean_text(
        source.get("name")
        or story.get("source_name")
        or story.get("publisher")
        or ""
    )


def source_url(story):
    source = source_object(story)

    return clean_text(
        source.get("url")
        or story.get("source_url")
        or story.get("url")
        or ""
    )


def verified_facts(story):
    facts = story.get("verified_facts")

    if isinstance(facts, list):
        return facts

    return []


def official_statement(story):
    statement = story.get("official_statement")

    if not isinstance(statement, dict):
        return {}

    return statement


# ============================================================
# JUNK / BOILERPLATE DETECTION
# ============================================================

JUNK_PATTERNS = [
    "google news",
    "google news app",
    "read full coverage",
    "sign in to google",
    "facebook.com",
    "facebook",
    "facebook app",
    "share on facebook",
    "googleusercontent.com",
    "news.google.com",
    "bing.com/news",
    "yahoo.com/news",
]


def contains_junk(value):
    value = clean_text(value).lower()

    for pattern in JUNK_PATTERNS:
        if pattern in value:
            return True

    return False


def validate_story_cleanliness(story):
    title = story_title(story)
    summary = story_summary(story)
    source = source_name(story)
    url = source_url(story)

    if not title:
        raise RuntimeError(
            "Story has no usable title."
        )

    if contains_junk(title):
        raise RuntimeError(
            f"Rejected junk story title: {title}"
        )

    if contains_junk(summary):
        raise RuntimeError(
            "Story summary contains Google News/Facebook "
            "or other syndicated boilerplate."
        )

    if contains_junk(source):
        raise RuntimeError(
            f"Rejected junk source: {source}"
        )

    if contains_junk(url):
        raise RuntimeError(
            f"Rejected junk source URL: {url}"
        )

    if not story_county(story):
        raise RuntimeError(
            "Story does not contain a county."
        )

    if not source:
        raise RuntimeError(
            "Story does not contain a source name."
        )

    if not url:
        raise RuntimeError(
            "Story does not contain a source URL."
        )


# ============================================================
# OFFICIAL / REAL SOURCE CHECK
# ============================================================

OFFICIAL_DOMAIN_HINTS = [
    ".go.ke",
    "government",
    "gov.ke",
    "parliament.go.ke",
    "president.go.ke",
    "deputypresident.go.ke",
]


def looks_like_official_source(story):
    source = source_object(story)

    source_type = clean_text(
        source.get("type")
    ).upper()

    if source_type == "OFFICIAL_SOURCE":
        return True

    url = source_url(story).lower()

    for hint in OFFICIAL_DOMAIN_HINTS:
        if hint in url:
            return True

    return False


# ============================================================
# IMAGE VALIDATION
# ============================================================

VALID_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


def valid_local_image(path):
    if not path:
        return False

    try:
        path = Path(path)
    except Exception:
        return False

    if not path.exists():
        return False

    if not path.is_file():
        return False

    if path.stat().st_size < 10 * 1024:
        return False

    if path.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
        return False

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

            if width < 300 or height < 200:
                return False

            if width <= 1 or height <= 1:
                return False

        return True

    except Exception:
        return False


# ============================================================
# LOCAL IMAGE DISCOVERY
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

    candidates.extend(
        [
            CANONICAL_IMAGE,
            DATA_DIR / "story_image.jpg",
            DATA_DIR / "story_image.jpeg",
            DATA_DIR / "story_image.png",
            SOURCE_DIR / "story_image.jpg",
            SOURCE_DIR / "story_image.jpeg",
            SOURCE_DIR / "story_image.png",
            ROOT / "story_image.jpg",
        ]
    )

    resolved = []

    for candidate in candidates:
        try:
            candidate = Path(candidate)

            if not candidate.is_absolute():
                candidate = ROOT / candidate

            candidate = candidate.resolve()

            if candidate not in resolved:
                resolved.append(candidate)

        except Exception:
            continue

    return resolved


def find_existing_local_image(story):
    for candidate in local_image_candidates(story):
        if valid_local_image(candidate):
            return candidate

    return None


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def normalize_url(url, base_url):
    if not url:
        return None

    url = clean_text(url)

    if not url:
        return None

    if url.startswith("//"):
        parsed = urlparse(base_url)

        if parsed.scheme:
            return f"{parsed.scheme}:{url}"

        return "https:" + url

    if url.startswith("/"):
        return urljoin(base_url, url)

    if not url.startswith(("http://", "https://")):
        return urljoin(base_url, url)

    return url


def add_image_candidate(candidates, url, base_url):
    url = normalize_url(url, base_url)

    if not url:
        return

    lowered = url.lower()

    bad_extensions = [
        ".svg",
        ".ico",
        ".gif",
        "google-news",
        "googleusercontent",
        "facebook.com",
        "favicon",
        "logo",
        "sprite",
    ]

    for bad in bad_extensions:
        if bad in lowered:
            return

    if url not in candidates:
        candidates.append(url)


def extract_image_candidates_from_html(html_text, page_url):
    candidates = []

    soup = BeautifulSoup(
        html_text,
        "html.parser"
    )

    meta_selectors = [
        ("meta", {"property": "og:image"}),
        ("meta", {"property": "og:image:url"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
        ("meta", {"name": "twitter:image:src"}),
    ]

    for tag_name, attrs in meta_selectors:
        for tag in soup.find_all(
            tag_name,
            attrs=attrs,
        ):
            value = (
                tag.get("content")
                or tag.get("href")
            )

            add_image_candidate(
                candidates,
                value,
                page_url,
            )

    for link in soup.find_all("link"):
        rel = link.get("rel")

        if not rel:
            continue

        rel_text = " ".join(
            rel
            if isinstance(rel, list)
            else [str(rel)]
        ).lower()

        if "image_src" in rel_text:
            add_image_candidate(
                candidates,
                link.get("href"),
                page_url,
            )

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        raw = script.string

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        def inspect_json(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    key_lower = str(key).lower()

                    if key_lower == "image":
                        if isinstance(item, str):
                            add_image_candidate(
                                candidates,
                                item,
                                page_url,
                            )

                        elif isinstance(item, list):
                            for sub in item:
                                if isinstance(sub, str):
                                    add_image_candidate(
                                        candidates,
                                        sub,
                                        page_url,
                                    )

                                elif isinstance(sub, dict):
                                    add_image_candidate(
                                        candidates,
                                        sub.get("url"),
                                        page_url,
                                    )

                        elif isinstance(item, dict):
                            add_image_candidate(
                                candidates,
                                item.get("url"),
                                page_url,
                            )

                    inspect_json(item)

            elif isinstance(value, list):
                for item in value:
                    inspect_json(item)

        inspect_json(data)

    article_selectors = [
        "article img",
        "main img",
        ".article img",
        ".post img",
        ".story img",
        ".entry-content img",
    ]

    for selector in article_selectors:
        for img in soup.select(selector):
            for attr in [
                "src",
                "data-src",
                "data-lazy-src",
                "data-original",
                "data-image",
            ]:
                add_image_candidate(
                    candidates,
                    img.get(attr),
                    page_url,
                )

    return candidates


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def image_url_is_valid(url):
    if not url:
        return False

    lowered = url.lower()

    if lowered.startswith(
        (
            "javascript:",
            "data:",
            "mailto:",
        )
    ):
        return False

    if "google-news" in lowered:
        return False

    if "facebook.com" in lowered:
        return False

    return True


def download_image(url, destination):
    if not image_url_is_valid(url):
        return None

    destination = Path(destination)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = destination.with_suffix(
        ".download"
    )

    try:
        response = requests.get(
            url,
            headers=REQUEST_HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("Content-Type", "")
            .lower()
        )

        if (
            "image" not in content_type
            and not any(
                ext in url.lower()
                for ext in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                ]
            )
        ):
            return None

        if len(response.content) < 10 * 1024:
            return None

        with temp_file.open("wb") as handle:
            handle.write(response.content)

        if not valid_local_image(temp_file):
            try:
                temp_file.unlink()
            except Exception:
                pass

            return None

        shutil.move(
            str(temp_file),
            str(destination),
        )

        return destination

    except Exception as exc:
        log(
            f"Image download failed: {url}\n"
            f"Reason: {exc}"
        )

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass

        return None


# ============================================================
# SOURCE PAGE IMAGE RECOVERY
# ============================================================

def recover_source_image(story):
    log("")
    log("=" * 70)
    log("IMAGE RECOVERY")
    log("=" * 70)

    local = find_existing_local_image(story)

    if local:
        log(
            f"REAL LOCAL IMAGE FOUND: {local}"
        )

        if local.resolve() != CANONICAL_IMAGE.resolve():
            try:
                shutil.copy2(
                    local,
                    CANONICAL_IMAGE,
                )
            except Exception as exc:
                log(
                    f"Could not copy image to canonical path: {exc}"
                )

        return CANONICAL_IMAGE if valid_local_image(
            CANONICAL_IMAGE
        ) else local

    page_url = source_url(story)

    if not page_url:
        raise RuntimeError(
            "No source URL is available for image recovery."
        )

    log(
        f"Checking source page for article image:\n"
        f"{page_url}"
    )

    try:
        response = requests.get(
            page_url,
            headers=REQUEST_HEADERS,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

        html_text = response.text

    except Exception as exc:
        raise RuntimeError(
            "Could not open the official source page "
            f"for image recovery:\n{exc}"
        ) from exc

    candidates = extract_image_candidates_from_html(
        html_text,
        response.url or page_url,
    )

    log(
        f"Image candidates found: {len(candidates)}"
    )

    for index, image_url in enumerate(
        candidates,
        start=1,
    ):
        log(
            f"IMAGE CANDIDATE {index}: {image_url}"
        )

        image = download_image(
            image_url,
            CANONICAL_IMAGE,
        )

        if image and valid_local_image(image):
            log(
                f"REAL IMAGE ACCEPTED: {image}"
            )

            story["local_image"] = str(
                image
            )

            return image

    raise RuntimeError(
        "No usable real article image could be recovered "
        "from the source page. "
        "The video was NOT generated with a fake placeholder."
    )


# ============================================================
# NARRATION
# ============================================================

def get_fact(story, label):
    for item in verified_facts(story):
        if not isinstance(item, dict):
            continue

        item_label = clean_text(
            item.get("label")
        ).upper()

        if item_label == label.upper():
            return clean_text(
                item.get("value")
            )

    return ""


def build_narration_segments(story):
    title = story_title(story)
    county = story_county(story)
    summary = story_summary(story)

    length = get_fact(
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

    route = get_fact(
        story,
        "PROJECT",
    )

    statement = official_statement(
        story
    )

    speaker = clean_text(
        statement.get("speaker")
    )

    quote = clean_text(
        statement.get("quote")
    )

    source = source_name(story)

    segments = []

    # --------------------------------------------------------
    # 1. OPENING
    # --------------------------------------------------------

    segments.append(
        clean_text(
            f"{title}. "
            f"Construction is underway in {county}."
        )
    )

    # --------------------------------------------------------
    # 2. LOCATION
    # --------------------------------------------------------

    location_text = (
        location
        if location
        else county
    )

    segments.append(
        clean_text(
            f"The project is located in "
            f"{location_text}. "
            f"It is being implemented in {county}."
        )
    )

    # --------------------------------------------------------
    # 3. KEY FACTS
    # --------------------------------------------------------

    facts = []

    if length:
        facts.append(
            f"{length}"
            .replace("kilometres", "kilometres")
        )

    if cost:
        facts.append(cost)

    if status:
        facts.append(
            status.rstrip(".")
        )

    if facts:
        facts_text = ". ".join(facts)
        segments.append(
            clean_text(
                f"Key figures: {facts_text}."
            )
        )
    else:
        segments.append(
            clean_text(summary)
        )

    # --------------------------------------------------------
    # 4. ROUTE
    # --------------------------------------------------------

    if route:
        segments.append(
            clean_text(
                f"The reported route is "
                f"{route}."
            )
        )
    else:
        segments.append(
            clean_text(
                "The project connects communities "
                "and key areas within the county."
            )
        )

    # --------------------------------------------------------
    # 5. IMPACT
    # --------------------------------------------------------

    if impact:
        segments.append(
            clean_text(
                f"The project is expected to "
                f"{impact.rstrip('.')}."
            )
        )
    else:
        segments.append(
            clean_text(
                "The project is expected to improve "
                "connectivity and economic activity."
            )
        )

    # --------------------------------------------------------
    # 6. OFFICIAL STATEMENT
    # --------------------------------------------------------

    if speaker and quote:
        statement_text = (
            f"{speaker} said: {quote}"
        )
    elif speaker:
        statement_text = (
            f"{speaker} gave an official statement "
            "on the project."
        )
    else:
        statement_text = (
            "The project information comes from "
            "the official county source."
        )

    segments.append(
        clean_text(statement_text)
    )

    # --------------------------------------------------------
    # 7. SOURCE
    # --------------------------------------------------------

    segments.append(
        clean_text(
            f"Source: {source}."
        )
    )

    # --------------------------------------------------------
    # 8. OUTRO
    # --------------------------------------------------------

    segments.append(
        clean_text(
            f"Rift Valley Watch. "
            f"Verified county news from {county}."
        )
    )

    # Remove empty segments
    segments = [
        segment
        for segment in segments
        if segment
    ]

    if len(segments) < 3:
        raise RuntimeError(
            "Narration generation produced too few segments."
        )

    return segments


def create_script_file(story):
    segments = build_narration_segments(
        story
    )

    full_script = " ".join(
        segments
    )

    script = {
        "full_script": full_script,
        "segments": segments,
        "title": story_title(story),
        "county": story_county(story),
        "source": source_name(story),
    }

    save_json(
        SCRIPT_FILE,
        script,
    )

    log("")
    log(
        f"NARRATION SEGMENTS: {len(segments)}"
    )

    for index, segment in enumerate(
        segments,
        start=1,
    ):
        log(
            f"{index}. {segment}"
        )

    return script


# ============================================================
# STORY CLEANUP
# ============================================================

def prepare_story(story, image_path):
    story = dict(story)

    story["title"] = story_title(story)
    story["county"] = story_county(story)
    story["category"] = story_category(story)
    story["date"] = story_date(story)

    story["local_image"] = str(
        image_path
    )

    source = source_object(story)

    story["source"] = {
        "name": source_name(story),
        "url": source_url(story),
        "type": clean_text(
            source.get("type")
            or "VERIFIED_SOURCE"
        ),
    }

    # Never let a raw URL become the displayed source.
    story["source_name"] = source_name(
        story
    )

    story["source_url"] = source_url(
        story
    )

    return story


# ============================================================
# GENERATOR PATH FIX
# ============================================================

def import_generator():
    generator_path = (
        ROOT / "rift_valley_video_generator.py"
    )

    if not generator_path.exists():
        raise RuntimeError(
            "Missing generator file:\n"
            f"{generator_path}"
        )

    if str(ROOT) not in sys.path:
        sys.path.insert(
            0,
            str(ROOT),
        )

    try:
        import rift_valley_video_generator as generator
    except Exception as exc:
        raise RuntimeError(
            "Could not import "
            "rift_valley_video_generator.py:\n"
            f"{exc}"
        ) from exc

    return generator


def configure_generator(generator):
    """
    The saved generator was originally using:

        Path(__file__).resolve().parent.parent

    This main file is designed to run from the repository root,
    so force the generator to use the actual repository root.
    """

    assignments = {
        "ROOT": ROOT,
        "STORY_FILE": STORY_FILE,
        "SCRIPT_FILE": SCRIPT_FILE,
        "OUTPUT_DIR": OUTPUT_DIR,
        "ASSET_DIR": ASSETS_DIR,
        "SOURCE_IMAGE_DIR": SOURCE_DIR,
        "AUDIO_DIR": AUDIO_DIR,
        "SCENE_DIR": SCENES_DIR,
        "OUTPUT_FILE": FINAL_GENERATOR_OUTPUT,
        "REPORT_FILE": REPORT_FILE,
    }

    for name, value in assignments.items():
        if hasattr(
            generator,
            name,
        ):
            setattr(
                generator,
                name,
                value,
            )


# ============================================================
# GENERATOR EXECUTION
# ============================================================

def run_generator(story):
    generator = import_generator()

    configure_generator(
        generator
    )

    log("")
    log("=" * 70)
    log("RUNNING RIFT VALLEY VIDEO GENERATOR")
    log("=" * 70)

    # Make absolutely sure the generator reads the cleaned
    # story from the correct location.
    save_json(
        STORY_FILE,
        story,
    )

    if not hasattr(
        generator,
        "main",
    ):
        raise RuntimeError(
            "rift_valley_video_generator.py does not "
            "contain the required main() function."
        )

    try:
        result = generator.main()
    except Exception as exc:
        log("")
        log("=" * 70)
        log("VIDEO GENERATOR FAILED")
        log("=" * 70)
        log(str(exc))
        raise

    if FINAL_GENERATOR_OUTPUT.exists():
        return FINAL_GENERATOR_OUTPUT

    # Some generator versions may return their output path.
    if result:
        try:
            result_path = Path(
                str(result)
            )

            if not result_path.is_absolute():
                result_path = (
                    ROOT / result_path
                )

            if result_path.exists():
                return result_path

        except Exception:
            pass

    raise RuntimeError(
        "The video generator completed but "
        "no final MP4 was found."
    )


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def command_exists(command):
    return shutil.which(
        command
    ) is not None


def run_ffprobe(path):
    if not command_exists(
        "ffprobe"
    ):
        raise RuntimeError(
            "ffprobe is not installed or not available "
            "on PATH."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size:stream="
            "codec_type,width,height,r_frame_rate"
        ),
        "-of",
        "json",
        str(path),
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "ffprobe failed:\n"
            + completed.stderr
        )

    try:
        return json.loads(
            completed.stdout
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not parse ffprobe output."
        ) from exc


# ============================================================
# FINAL MP4 VALIDATION
# ============================================================

def validate_mp4(path):
    path = Path(path)

    log("")
    log("=" * 70)
    log("FINAL MP4 QUALITY CONTROL")
    log("=" * 70)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 does not exist: {path}"
        )

    file_size = path.stat().st_size

    if file_size < MIN_FILE_SIZE:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    info = run_ffprobe(
        path
    )

    streams = info.get(
        "streams",
        [],
    )

    format_info = info.get(
        "format",
        {},
    )

    video_stream = None
    audio_stream = None

    for stream in streams:
        codec_type = stream.get(
            "codec_type"
        )

        if codec_type == "video":
            video_stream = stream

        elif codec_type == "audio":
            audio_stream = stream

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
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

    duration = float(
        format_info.get(
            "duration",
            0,
        )
        or 0
    )

    log(
        f"FILE: {path}"
    )

    log(
        f"SIZE: {file_size:,} bytes"
    )

    log(
        f"VIDEO: {width}x{height}"
    )

    log(
        f"DURATION: {duration:.2f} seconds"
    )

    log(
        f"AUDIO: {'YES' if audio_stream else 'NO'}"
    )

    if width != EXPECTED_WIDTH:
        raise RuntimeError(
            f"Wrong video width: {width}. "
            f"Expected {EXPECTED_WIDTH}."
        )

    if height != EXPECTED_HEIGHT:
        raise RuntimeError(
            f"Wrong video height: {height}. "
            f"Expected {EXPECTED_HEIGHT}."
        )

    if duration < MIN_DURATION:
        raise RuntimeError(
            f"Video is too short: {duration:.2f} seconds."
        )

    if duration > MAX_DURATION:
        raise RuntimeError(
            f"Video is unexpectedly long: {duration:.2f} seconds."
        )

    return {
        "file": str(path),
        "size_bytes": file_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "has_video": True,
        "has_audio": True,
        "valid": True,
    }


# ============================================================
# FINAL COPY
# ============================================================

def create_final_reel(source_path):
    source_path = Path(
        source_path
    )

    if not source_path.exists():
        raise RuntimeError(
            f"Generator output not found: {source_path}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if (
        source_path.resolve()
        != FINAL_REEL.resolve()
    ):
        shutil.copy2(
            source_path,
            FINAL_REEL,
        )

    if not FINAL_REEL.exists():
        raise RuntimeError(
            "Could not create final reel."
        )

    return FINAL_REEL


# ============================================================
# VISUAL REPORT
# ============================================================

def write_main_report(
    story,
    image_path,
    qc,
):
    report = {
        "project": "Rift Valley Watch",
        "title": story_title(story),
        "county": story_county(story),
        "category": story_category(story),
        "date": story_date(story),
        "source": {
            "name": source_name(story),
            "url": source_url(story),
            "type": source_object(
                story
            ).get(
                "type",
                "VERIFIED_SOURCE",
            ),
        },
        "image": {
            "path": str(image_path),
            "valid": valid_local_image(
                image_path
            ),
        },
        "output": qc,
        "requirements": {
            "one_story_per_reel": True,
            "real_article_image_required": True,
            "google_news_boilerplate_rejected": True,
            "facebook_boilerplate_rejected": True,
            "youtube_upload": False,
            "resolution": "1080x1920",
            "orientation": "9:16",
        },
    }

    save_json(
        REPORT_FILE,
        report,
    )

    return report


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 70)
    log("RIFT VALLEY WATCH")
    log("MAIN NEWS ENGINE")
    log("=" * 70)

    ensure_directories()

    # --------------------------------------------------------
    # CHECK REQUIRED STORY
    # --------------------------------------------------------

    log("")
    log("LOADING STORY")

    story = load_json(
        STORY_FILE
    )

    validate_story_cleanliness(
        story
    )

    log(
        f"TITLE : {story_title(story)}"
    )

    log(
        f"COUNTY: {story_county(story)}"
    )

    log(
        f"SOURCE: {source_name(story)}"
    )

    log(
        f"URL   : {source_url(story)}"
    )

    if looks_like_official_source(
        story
    ):
        log(
            "SOURCE TYPE: OFFICIAL / VERIFIED"
        )
    else:
        log(
            "SOURCE TYPE: VERIFIED NON-OFFICIAL"
        )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_path = recover_source_image(
        story
    )

    if not valid_local_image(
        image_path
    ):
        raise RuntimeError(
            "Image recovery returned an invalid image."
        )

    # --------------------------------------------------------
    # CLEAN STORY
    # --------------------------------------------------------

    story = prepare_story(
        story,
        image_path,
    )

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    script = create_script_file(
        story
    )

    if not script.get(
        "full_script"
    ):
        raise RuntimeError(
            "No narration was created."
        )

    # --------------------------------------------------------
    # SAVE CLEAN STORY
    # --------------------------------------------------------

    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    save_json(
        STORY_FILE,
        story,
    )

    log("")
    log(
        f"CLEAN STORY SAVED: {SELECTED_STORY_FILE}"
    )

    log(
        f"STORY IMAGE: {story['local_image']}"
    )

    # --------------------------------------------------------
    # REMOVE OLD GENERATED OUTPUT
    # --------------------------------------------------------

    for old_file in [
        FINAL_GENERATOR_OUTPUT,
        FINAL_REEL,
    ]:
        try:
            if old_file.exists():
                old_file.unlink()
        except Exception:
            pass

    # --------------------------------------------------------
    # RUN VIDEO GENERATOR
    # --------------------------------------------------------

    generated_video = run_generator(
        story
    )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    generated_qc = validate_mp4(
        generated_video
    )

    # --------------------------------------------------------
    # CREATE FINAL NAMED REEL
    # --------------------------------------------------------

    final_reel = create_final_reel(
        generated_video
    )

    final_qc = validate_mp4(
        final_reel
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    write_main_report(
        story,
        image_path,
        final_qc,
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH COMPLETE")
    log("=" * 70)

    log(
        f"TITLE    : {story_title(story)}"
    )

    log(
        f"COUNTY   : {story_county(story)}"
    )

    log(
        f"SOURCE   : {source_name(story)}"
    )

    log(
        f"IMAGE    : {image_path}"
    )

    log(
        f"VIDEO    : {final_reel}"
    )

    log(
        f"SIZE     : "
        f"{final_qc['size_bytes']:,} bytes"
    )

    log(
        f"DURATION : "
        f"{final_qc['duration_seconds']:.2f}s"
    )

    log(
        f"FORMAT   : "
        f"{final_qc['width']}x"
        f"{final_qc['height']}"
    )

    log(
        "AUDIO    : YES"
    )

    log(
        "YOUTUBE  : NOT UPLOADED"
    )

    log("")
    log(
        "SUCCESS: FINAL MP4 READY"
    )

    return final_reel


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        log("")
        log(
            "Process cancelled by user."
        )
        sys.exit(130)

    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log(
            str(exc)
        )
        log("")
        sys.exit(1)
