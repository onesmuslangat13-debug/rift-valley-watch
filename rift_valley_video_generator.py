from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import math
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V25_ARTICLE_PAGE_IMAGE_RESOLVER
#
# PURPOSE
# - One selected real article/story per reel
# - Resolve article-page URLs into actual article photographs
# - Support Markdown image/article links
# - Extract OG images, Twitter images, JSON-LD images,
#   lazy-loaded images, srcset images and normal <img> images
# - Reject HTML pages, placeholders, avatars and obvious logos
# - Use multiple real article photographs when available
# - No source/publisher text in narration
# - No source/publisher text rendered on frames
# - Professional 1080x1920 vertical news reel
# - gTTS narration
# - Final MP4 with audio
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = BASE_DIR / "audio"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
OUTPUT_DIR = BASE_DIR / "output"

SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920

FPS = 30

MIN_DURATION = 18.0
TARGET_DURATION = 23.0
MAX_DURATION = 35.0
HARD_MAX_DURATION = 34.50

MAX_SCENES = 4

REQUEST_TIMEOUT = 25

# Maximum number of candidate URLs extracted from an article page.
MAX_ARTICLE_PAGE_CANDIDATES = 20

# ============================================================
# BRANDING
# ============================================================

BRAND_NAME = "RIFT VALLEY WATCH"

BRAND_TAGLINE = "REAL STORIES. RIFT VALLEY."

# ============================================================
# IMAGE FILTERING
# ============================================================

BAD_IMAGE_TERMS = [
    "logo",
    "logos",
    "avatar",
    "profile",
    "placeholder",
    "default-image",
    "default_image",
    "defaultimage",
    "favicon",
    "icon",
    "icons",
    "sprite",
    "advert",
    "advertisement",
    "banner-ad",
    "banner_ad",
    "thumbnail-placeholder",
    "placeholder-image",
    "placeholder_image",
    "generic",
    "dummy",
    "no-image",
    "no_image",
    "world-cup",
    "worldcup",
    "football",
    "soccer",
    "promo",
    "promotion",
]

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
)

# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
)

HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Accept": (
        "image/avif,image/webp,image/apng,image/svg+xml,"
        "image/*,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# ARTICLE PAGE CACHE
# ============================================================

ARTICLE_PAGE_CACHE = {}


# ============================================================
# BASIC HELPERS
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_unlink(path):
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def clean_generated_files():
    safe_unlink(FINAL_VIDEO)
    safe_unlink(NARRATION_FILE)

    for pattern in [
        "narration_*.mp3",
        "scene_*.mp4",
        "frame_*.jpg",
        "image_*.jpg",
        "candidate_*.jpg",
        "concat*.txt",
    ]:
        for item in VIDEO_WORK_DIR.glob(pattern):
            safe_unlink(item)

    for item in SOURCE_DIR.glob("story_image*.jpg"):
        safe_unlink(item)

    for item in SOURCE_DIR.glob("story_image*.jpeg"):
        safe_unlink(item)

    for item in SOURCE_DIR.glob("story_image*.png"):
        safe_unlink(item)

    for item in SOURCE_DIR.glob("story_image*.webp"):
        safe_unlink(item)


def run_command(command, description="command", check=True):
    print()
    print("=" * 60)
    print(description)
    print("=" * 60)
    print(" ".join(str(x) for x in command))

    result = subprocess.run(
        [str(x) for x in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.stdout:
        print(result.stdout)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code {result.returncode}"
        )

    return result


def command_exists(command):
    return shutil.which(command) is not None


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    # Remove Markdown links while preserving their visible text.
    text = re.sub(
        r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    # Remove URLs.
    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"www\.\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove HTML.
    text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_sentence(text):
    text = clean_text(text)

    if not text:
        return ""

    text = re.sub(r"\s+([,.!?;:])", r"\1", text)

    if text[-1] not in ".!?":
        text += "."

    return text


def word_count(text):
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


# ============================================================
# NARRATION EXCLUSIONS
# ============================================================

NARRATION_EXCLUDED_KEYS = {
    "source",
    "sources",
    "publisher",
    "publication",
    "site",
    "website",
    "domain",
    "credit",
    "credits",
    "byline",
    "author",
    "authors",
    "source_name",
    "source_url",
    "article_url",
    "url",
    "urls",
    "link",
    "links",
    "image_url",
    "image_urls",
    "image",
    "images",
    "photo",
    "photos",
    "media",
    "media_url",
    "media_urls",
    "thumbnail",
    "thumbnail_url",
    "thumbnail_urls",
}


def key_is_excluded(key):
    if key is None:
        return True

    normalized = str(key).strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")

    if normalized in NARRATION_EXCLUDED_KEYS:
        return True

    blocked_fragments = [
        "source",
        "publisher",
        "publication",
        "credit",
        "byline",
        "author",
        "article_url",
        "source_url",
        "image_url",
        "thumbnail",
        "media_url",
    ]

    return any(fragment in normalized for fragment in blocked_fragments)


def collect_text_fields(obj, depth=0):
    """
    Extract useful narrative text from a JSON object while
    deliberately excluding source/publisher/image/media fields.
    """

    if depth > 8:
        return []

    output = []

    if isinstance(obj, dict):
        for key, value in obj.items():

            if key_is_excluded(key):
                continue

            if isinstance(value, str):
                text = clean_text(value)

                if not text:
                    continue

                # Skip very short metadata-like values.
                if len(text) < 3:
                    continue

                # Do not narrate obvious technical fields.
                if re.fullmatch(
                    r"(https?://|www\.)\S+",
                    text,
                    flags=re.IGNORECASE,
                ):
                    continue

                output.append(text)

            elif isinstance(value, (dict, list)):
                output.extend(
                    collect_text_fields(value, depth + 1)
                )

    elif isinstance(obj, list):
        for item in obj:
            output.extend(
                collect_text_fields(item, depth + 1)
            )

    return output


# ============================================================
# JSON LOADING
# ============================================================

def load_json_file(path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except Exception as exc:
        print(f"WARNING: Could not load {path}: {exc}")
        return {}


def load_story():
    story = load_json_file(SELECTED_STORY_FILE)

    if not story:
        raise RuntimeError(
            "selected_story.json is empty or missing."
        )

    print()
    print("=" * 60)
    print("SELECTED STORY LOADED")
    print("=" * 60)
    print(json.dumps(story, indent=2, ensure_ascii=False))

    return story


def load_script():
    if not SELECTED_SCRIPT_FILE.exists():
        print("No selected_script.json found. Building narration from story.")
        return {}

    script = load_json_file(SELECTED_SCRIPT_FILE)

    if not script:
        print("selected_script.json is empty. Building narration from story.")
        return {}

    print()
    print("=" * 60)
    print("SELECTED SCRIPT LOADED")
    print("=" * 60)
    print(json.dumps(script, indent=2, ensure_ascii=False))

    return script


# ============================================================
# STORY HELPERS
# ============================================================

def get_story_title(story):
    if not isinstance(story, dict):
        return "Rift Valley Watch"

    preferred = [
        "title",
        "headline",
        "story_title",
        "news_title",
        "name",
    ]

    for key in preferred:
        value = story.get(key)

        if isinstance(value, str):
            value = clean_text(value)

            if value:
                return value

    return "Rift Valley Watch"


def get_story_source(story):
    """
    Source is retained only for logging/debugging.
    It is NEVER rendered or narrated.
    """

    if not isinstance(story, dict):
        return ""

    keys = [
        "source",
        "publisher",
        "publication",
        "source_name",
        "site",
        "website",
    ]

    for key in keys:
        value = story.get(key)

        if isinstance(value, str):
            value = clean_text(value)

            if value:
                return value

    return ""


# ============================================================
# SENTENCE HELPERS
# ============================================================

def split_into_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    result = []

    for part in parts:
        part = normalize_sentence(part)

        if part:
            result.append(part)

    return result


# ============================================================
# NARRATION BUILDER
# ============================================================

def build_narration(story, script):
    """
    Build narration without source/publisher information.
    """

    script_candidates = []

    if isinstance(script, dict):
        preferred_keys = [
            "narration",
            "script",
            "voiceover",
            "voice_over",
            "text",
            "body",
            "summary",
            "story",
        ]

        for key in preferred_keys:
            if key in script and isinstance(script[key], str):
                value = clean_text(script[key])

                if value:
                    script_candidates.append(value)

    if script_candidates:
        narration = script_candidates[0]

        # Explicitly remove any accidental source lines.
        lines = []

        for line in narration.splitlines():
            lower = line.lower().strip()

            if any(
                token in lower
                for token in [
                    "source:",
                    "sources:",
                    "publisher:",
                    "publication:",
                    "credit:",
                    "credits:",
                    "read more:",
                    "via:",
                ]
            ):
                continue

            if re.search(
                r"https?://|www\.",
                line,
                flags=re.IGNORECASE,
            ):
                continue

            lines.append(line)

        narration = clean_text(" ".join(lines))

        if narration:
            return narration

    # Build from story fields.
    texts = collect_text_fields(story)

    title = get_story_title(story)

    selected = []

    # Title first.
    if title:
        selected.append(title)

    # Avoid duplicate title text.
    normalized_title = re.sub(
        r"\W+",
        " ",
        title.lower(),
    ).strip()

    for text in texts:
        normalized = re.sub(
            r"\W+",
            " ",
            text.lower(),
        ).strip()

        if normalized == normalized_title:
            continue

        if text not in selected:
            selected.append(text)

    narration = " ".join(selected)

    narration = clean_text(narration)

    if not narration:
        raise RuntimeError(
            "Unable to build narration from selected story."
        )

    # Keep narration concise enough for a reel.
    sentences = split_into_sentences(narration)

    if sentences:
        narration = " ".join(sentences)

    return narration


# ============================================================
# NARRATION SHORTENING
# ============================================================

def shorten_narration(text, target_words=115):
    sentences = split_into_sentences(text)

    if not sentences:
        return clean_text(text)

    selected = []
    count = 0

    for sentence in sentences:
        words = word_count(sentence)

        if selected and count + words > target_words:
            break

        selected.append(sentence)
        count += words

    if not selected:
        selected.append(sentences[0])

    return " ".join(selected)


def narration_candidates(narration):
    candidates = []

    base = clean_text(narration)

    if base:
        candidates.append(base)

    shorter = shorten_narration(
        base,
        target_words=105,
    )

    if shorter and shorter not in candidates:
        candidates.append(shorter)

    shorter2 = shorten_narration(
        base,
        target_words=90,
    )

    if shorter2 and shorter2 not in candidates:
        candidates.append(shorter2)

    sentences = split_into_sentences(base)

    if len(sentences) > 4:
        short4 = " ".join(sentences[:4])

        if short4 not in candidates:
            candidates.append(short4)

    if len(sentences) > 3:
        short3 = " ".join(sentences[:3])

        if short3 not in candidates:
            candidates.append(short3)

    return candidates


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(path):
    if not path.exists():
        return 0.0

    if not command_exists("ffprobe"):
        return 0.0

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def generate_tts(text, output_path):
    safe_unlink(output_path)

    print()
    print("=" * 60)
    print("GENERATING NARRATION")
    print("=" * 60)
    print(text)

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(str(output_path))

    if not output_path.exists():
        raise RuntimeError(
            "gTTS did not create narration MP3."
        )

    if output_path.stat().st_size < 1000:
        raise RuntimeError(
            "Generated narration MP3 is too small."
        )

    duration = get_media_duration(output_path)

    print(f"Narration duration: {duration:.2f}s")

    return duration


def create_narration(story, script):
    narration = build_narration(
        story,
        script,
    )

    candidates = narration_candidates(narration)

    print()
    print("=" * 60)
    print("NARRATION CANDIDATES")
    print("=" * 60)

    for index, candidate in enumerate(candidates, 1):
        print(
            f"{index}. {word_count(candidate)} words - "
            f"{candidate}"
        )

    best_candidate = None
    best_duration = None
    best_score = None

    for index, candidate in enumerate(candidates, 1):

        temp_path = AUDIO_DIR / f"narration_candidate_{index}.mp3"

        try:
            duration = generate_tts(
                candidate,
                temp_path,
            )
        except Exception as exc:
            print(
                f"WARNING: TTS candidate {index} failed: {exc}"
            )
            safe_unlink(temp_path)
            continue

        if duration <= 0:
            safe_unlink(temp_path)
            continue

        # Prefer a duration close to TARGET_DURATION.
        score = abs(duration - TARGET_DURATION)

        # Strongly penalize outside the desired range.
        if duration < MIN_DURATION:
            score += (MIN_DURATION - duration) * 3

        if duration > MAX_DURATION:
            score += (duration - MAX_DURATION) * 3

        if best_score is None or score < best_score:
            best_score = score
            best_candidate = temp_path
            best_duration = duration

    if best_candidate is None:
        raise RuntimeError(
            "No usable narration candidate was generated."
        )

    safe_unlink(NARRATION_FILE)

    shutil.copy2(
        best_candidate,
        NARRATION_FILE,
    )

    for item in AUDIO_DIR.glob("narration_candidate_*.mp3"):
        safe_unlink(item)

    final_duration = get_media_duration(
        NARRATION_FILE
    )

    if final_duration <= 0:
        raise RuntimeError(
            "Final narration duration could not be determined."
        )

    # Hard upper bound.
    if final_duration > HARD_MAX_DURATION:
        print(
            f"WARNING: narration is {final_duration:.2f}s, "
            f"above hard target. Video will be capped."
        )

    print(
        f"FINAL NARRATION DURATION: "
        f"{final_duration:.2f}s"
    )

    return final_duration


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_url(value):
    """
    Convert:
        [https://example.com/article](https://example.com/article)
    into:
        https://example.com/article

    Also handles angle brackets and whitespace.
    """

    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    # Markdown link:
    match = re.match(
        r"^\s*\[[^\]]*\]\((https?://[^)]+)\)\s*$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        text = match.group(1).strip()

    # Markdown/autolink angle brackets.
    text = text.strip("<> ")

    # Remove surrounding quotes.
    text = text.strip("\"'")

    # Remove accidental whitespace.
    text = text.strip()

    if not re.match(
        r"^https?://",
        text,
        flags=re.IGNORECASE,
    ):
        return ""

    return text


# ============================================================
# IMAGE URL DETECTION
# ============================================================

def looks_like_direct_image_url(url):
    url = normalize_url(url)

    if not url:
        return False

    try:
        parsed = urlparse(url)
        path = parsed.path.lower()

        if any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return True

        # Common image CDN parameters.
        query = parsed.query.lower()

        image_parameters = [
            "format=image",
            "fm=jpg",
            "fm=jpeg",
            "fm=png",
            "fm=webp",
            "image=",
            "img=",
            "image_url=",
            "imageurl=",
        ]

        if any(
            parameter in query
            for parameter in image_parameters
        ):
            return True

    except Exception:
        pass

    return False


def image_url_is_bad(url):
    url = normalize_url(url)

    if not url:
        return True

    lower = url.lower()

    for term in BAD_IMAGE_TERMS:
        if term in lower:
            return True

    return False


# ============================================================
# IMAGE URL EXTRACTION FROM JSON
# ============================================================

def recursive_image_urls(obj, depth=0):
    """
    Extract likely image URLs.

    IMPORTANT:
    Generic 'url', 'link' and 'article_url' values are NOT
    automatically treated as image URLs. This prevents article
    page URLs from being mistaken for direct images.
    """

    if depth > 10:
        return []

    found = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).strip().lower()

            image_key = any(
                token in key_lower
                for token in [
                    "image",
                    "photo",
                    "picture",
                    "thumbnail",
                    "media",
                    "contenturl",
                    "content_url",
                    "imageurl",
                    "image_url",
                ]
            )

            if image_key:

                if isinstance(value, str):
                    normalized = normalize_url(value)

                    if normalized:
                        found.append(normalized)

                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            normalized = normalize_url(item)

                            if normalized:
                                found.append(normalized)

                        elif isinstance(item, (dict, list)):
                            found.extend(
                                recursive_image_urls(
                                    item,
                                    depth + 1,
                                )
                            )

                elif isinstance(value, dict):
                    found.extend(
                        recursive_image_urls(
                            value,
                            depth + 1,
                        )
                    )

            elif isinstance(value, (dict, list)):
                found.extend(
                    recursive_image_urls(
                        value,
                        depth + 1,
                    )
                )

    elif isinstance(obj, list):

        for item in obj:
            found.extend(
                recursive_image_urls(
                    item,
                    depth + 1,
                )
            )

    elif isinstance(obj, str):

        normalized = normalize_url(obj)

        if normalized and looks_like_direct_image_url(normalized):
            found.append(normalized)

    return found


def get_image_urls(story):
    urls = []

    if not isinstance(story, dict):
        return urls

    preferred_keys = [
        "image_urls",
        "images",
        "image",
        "photos",
        "photo_urls",
        "photo",
        "media_urls",
        "media",
        "article_images",
        "article_image",
        "featured_image",
        "featured_image_url",
        "thumbnail_url",
    ]

    for key in preferred_keys:

        if key not in story:
            continue

        value = story[key]

        if isinstance(value, str):
            normalized = normalize_url(value)

            if normalized:
                urls.append(normalized)

        elif isinstance(value, list):
            for item in value:

                if isinstance(item, str):
                    normalized = normalize_url(item)

                    if normalized:
                        urls.append(normalized)

                elif isinstance(item, (dict, list)):
                    urls.extend(
                        recursive_image_urls(item)
                    )

        elif isinstance(value, (dict, list)):
            urls.extend(
                recursive_image_urls(value)
            )

    # Also search the complete story object for explicit image fields.
    urls.extend(
        recursive_image_urls(story)
    )

    # Deduplicate.
    unique = []

    seen = set()

    for url in urls:
        normalized = normalize_url(url)

        if not normalized:
            continue

        key = normalized.rstrip("/")

        if key in seen:
            continue

        seen.add(key)
        unique.append(normalized)

    return unique


# ============================================================
# SRCSET
# ============================================================

def extract_srcset_urls(value, base_url):
    results = []

    if not isinstance(value, str):
        return results

    for candidate in value.split(","):

        candidate = candidate.strip()

        if not candidate:
            continue

        # srcset format:
        # URL 1200w
        # URL 2x
        parts = candidate.split()

        if not parts:
            continue

        raw_url = parts[0].strip()

        absolute = urljoin(
            base_url,
            raw_url,
        )

        absolute = normalize_url(absolute)

        if absolute:
            results.append(absolute)

    return results


# ============================================================
# JSON-LD IMAGE EXTRACTION
# ============================================================

def extract_jsonld_images(obj, results, base_url, depth=0):
    if depth > 12:
        return

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

            if key_lower in {
                "image",
                "images",
                "contenturl",
                "content_url",
                "thumbnailurl",
                "thumbnail_url",
            }:

                if isinstance(value, str):

                    absolute = urljoin(
                        base_url,
                        value,
                    )

                    absolute = normalize_url(
                        absolute
                    )

                    if absolute:
                        results.append(absolute)

                elif isinstance(value, list):

                    for item in value:

                        if isinstance(item, str):

                            absolute = urljoin(
                                base_url,
                                item,
                            )

                            absolute = normalize_url(
                                absolute
                            )

                            if absolute:
                                results.append(
                                    absolute
                                )

                        elif isinstance(
                            item,
                            (dict, list),
                        ):
                            extract_jsonld_images(
                                item,
                                results,
                                base_url,
                                depth + 1,
                            )

                elif isinstance(
                    value,
                    (dict, list),
                ):

                    extract_jsonld_images(
                        value,
                        results,
                        base_url,
                        depth + 1,
                    )

            elif isinstance(
                value,
                (dict, list),
            ):

                extract_jsonld_images(
                    value,
                    results,
                    base_url,
                    depth + 1,
                )

    elif isinstance(obj, list):

        for item in obj:
            extract_jsonld_images(
                item,
                results,
                base_url,
                depth + 1,
            )


# ============================================================
# ARTICLE PAGE IMAGE RESOLVER
# ============================================================

def resolve_article_page_images(article_url):
    """
    Resolve an article page into actual image URLs.

    Priority:
    1. OpenGraph
    2. Twitter image
    3. JSON-LD
    4. <img> data attributes
    5. srcset
    6. <source srcset>
    """

    article_url = normalize_url(article_url)

    if not article_url:
        return []

    if article_url in ARTICLE_PAGE_CACHE:
        return ARTICLE_PAGE_CACHE[article_url]

    print()
    print("=" * 60)
    print("RESOLVING ARTICLE PAGE FOR IMAGES")
    print("=" * 60)
    print(article_url)

    results = []

    try:
        response = SESSION.get(
            article_url,
            headers=HTML_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        print(
            f"Article page HTTP status: "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            ARTICLE_PAGE_CACHE[article_url] = []
            return []

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        # If this redirected directly to an image,
        # return the final URL as an image candidate.
        final_url = normalize_url(
            response.url
        )

        if (
            final_url
            and looks_like_direct_image_url(final_url)
        ):
            results.append(final_url)

        # If there is no HTML, do not attempt BeautifulSoup.
        if (
            "html" not in content_type
            and "xhtml" not in content_type
            and len(response.content) < 1000
        ):
            ARTICLE_PAGE_CACHE[
                article_url
            ] = results[:MAX_ARTICLE_PAGE_CANDIDATES]

            return ARTICLE_PAGE_CACHE[article_url]

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        base_url = response.url

        # ----------------------------------------------------
        # OpenGraph
        # ----------------------------------------------------

        meta_selectors = [
            ("meta", {"property": "og:image"}),
            ("meta", {"property": "og:image:url"}),
            ("meta", {"property": "og:image:secure_url"}),
            ("meta", {"name": "twitter:image"}),
            ("meta", {"name": "twitter:image:src"}),
            ("meta", {"itemprop": "image"}),
            ("meta", {"property": "image"}),
        ]

        for tag_name, attrs in meta_selectors:

            for tag in soup.find_all(
                tag_name,
                attrs=attrs,
            ):

                content = tag.get("content")

                if not content:
                    continue

                absolute = urljoin(
                    base_url,
                    content,
                )

                absolute = normalize_url(
                    absolute
                )

                if absolute:
                    results.append(absolute)

        # ----------------------------------------------------
        # JSON-LD
        # ----------------------------------------------------

        for script_tag in soup.find_all(
            "script",
            attrs={
                "type": re.compile(
                    r"application/ld\+json",
                    re.IGNORECASE,
                )
            },
        ):

            raw = script_tag.string or script_tag.get_text()

            if not raw:
                continue

            try:
                parsed = json.loads(raw)

                jsonld_results = []

                extract_jsonld_images(
                    parsed,
                    jsonld_results,
                    base_url,
                )

                results.extend(
                    jsonld_results
                )

            except Exception:
                # Some websites contain malformed JSON-LD.
                # Continue with normal HTML extraction.
                continue

        # ----------------------------------------------------
        # <img> elements
        # ----------------------------------------------------

        image_attributes = [
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-image",
            "data-image-src",
            "data-lazy",
            "data-url",
            "data-fallback-src",
        ]

        for img in soup.find_all("img"):

            for attr in image_attributes:

                value = img.get(attr)

                if not value:
                    continue

                absolute = urljoin(
                    base_url,
                    value,
                )

                absolute = normalize_url(
                    absolute
                )

                if absolute:
                    results.append(
                        absolute
                    )

            srcset = img.get("srcset")

            if srcset:
                results.extend(
                    extract_srcset_urls(
                        srcset,
                        base_url,
                    )
                )

            data_srcset = img.get(
                "data-srcset"
            )

            if data_srcset:
                results.extend(
                    extract_srcset_urls(
                        data_srcset,
                        base_url,
                    )
                )

        # ----------------------------------------------------
        # <source srcset>
        # ----------------------------------------------------

        for source in soup.find_all("source"):

            srcset = source.get("srcset")

            if srcset:
                results.extend(
                    extract_srcset_urls(
                        srcset,
                        base_url,
                    )
                )

            data_srcset = source.get(
                "data-srcset"
            )

            if data_srcset:
                results.extend(
                    extract_srcset_urls(
                        data_srcset,
                        base_url,
                    )
                )

        # ----------------------------------------------------
        # Deduplicate and filter
        # ----------------------------------------------------

        unique = []
        seen = set()

        for candidate in results:

            candidate = normalize_url(
                candidate
            )

            if not candidate:
                continue

            if image_url_is_bad(candidate):
                continue

            normalized_key = candidate.rstrip("/")

            if normalized_key in seen:
                continue

            seen.add(normalized_key)
            unique.append(candidate)

        unique = unique[
            :MAX_ARTICLE_PAGE_CANDIDATES
        ]

        print(
            f"Resolved {len(unique)} image candidates "
            f"from article page."
        )

        for index, candidate in enumerate(
            unique,
            1,
        ):
            print(
                f"  IMAGE CANDIDATE {index}: "
                f"{candidate}"
            )

        ARTICLE_PAGE_CACHE[
            article_url
        ] = unique

        return unique

    except Exception as exc:
        print(
            f"WARNING: Article page image resolution failed: "
            f"{exc}"
        )

        ARTICLE_PAGE_CACHE[
            article_url
        ] = []

        return []


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_is_valid(path):
    try:
        with Image.open(path) as image:

            image.verify()

        with Image.open(path) as image:

            width, height = image.size

            if width < 250 or height < 250:
                return False

            if width * height < 100000:
                return False

        return True

    except Exception:
        return False


def image_hash(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((128, 128))

            data = image.tobytes()

        return hashlib.sha256(data).hexdigest()

    except Exception:
        return ""


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url, output_path):
    """
    Download one direct image URL and validate it.

    Returns True only when an actual usable image is saved.
    """

    url = normalize_url(url)

    if not url:
        return False

    if image_url_is_bad(url):
        print(
            f"Skipping blocked image candidate: {url}"
        )
        return False

    temp_path = output_path.with_suffix(
        ".download"
    )

    safe_unlink(temp_path)
    safe_unlink(output_path)

    try:
        print(
            f"Downloading image: {url}"
        )

        response = SESSION.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            print(
                f"Rejected image HTTP "
                f"{response.status_code}: {url}"
            )
            return False

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).lower()

        data = response.content

        if len(data) < 10000:
            print(
                f"Rejected image because response is too small: "
                f"{url}"
            )
            return False

        # A direct image request returning HTML is an article page,
        # login page, block page, etc.
        if (
            "text/html" in content_type
            or "application/xhtml" in content_type
        ):
            print(
                f"Rejected HTML response instead of image: "
                f"{url}"
            )
            return False

        temp_path.write_bytes(data)

        if not image_is_valid(temp_path):
            print(
                f"Rejected invalid image: {url}"
            )
            safe_unlink(temp_path)
            return False

        # Re-open and convert everything to JPEG.
        with Image.open(temp_path) as image:

            image = image.convert("RGB")

            # Normalize EXIF orientation where possible.
            try:
                from PIL import ImageOps

                image = ImageOps.exif_transpose(
                    image
                )
                image = image.convert("RGB")

            except Exception:
                pass

            image.save(
                output_path,
                "JPEG",
                quality=94,
                optimize=True,
            )

        safe_unlink(temp_path)

        if not image_is_valid(output_path):
            safe_unlink(output_path)
            return False

        print(
            f"VALID IMAGE: {output_path}"
        )

        return True

    except Exception as exc:
        print(
            f"Image download failed: {exc}"
        )

        safe_unlink(temp_path)
        safe_unlink(output_path)

        return False


# ============================================================
# IMAGE CANDIDATE EXPANSION
# ============================================================

def expand_image_candidates(original_urls):
    """
    Turn mixed image/article URLs into direct image URLs.

    Article pages are resolved only one level deep.
    """

    expanded = []

    seen = set()

    for raw_url in original_urls:

        url = normalize_url(raw_url)

        if not url:
            continue

        if image_url_is_bad(url):
            continue

        key = url.rstrip("/")

        if key in seen:
            continue

        seen.add(key)

        # Direct image URL.
        if looks_like_direct_image_url(url):
            expanded.append(url)
            continue

        # Otherwise treat it as an article/page URL.
        page_images = resolve_article_page_images(
            url
        )

        for image_url in page_images:

            image_url = normalize_url(
                image_url
            )

            if not image_url:
                continue

            if image_url_is_bad(image_url):
                continue

            image_key = image_url.rstrip("/")

            if image_key in seen:
                continue

            seen.add(image_key)

            expanded.append(image_url)

    return expanded


# ============================================================
# DOWNLOAD REAL ARTICLE PHOTOS
# ============================================================

def download_real_images(story):
    """
    Download up to MAX_SCENES real article photos.

    Handles:
    - direct image URLs
    - article-page URLs
    - Markdown links
    - KBC-style article URLs
    - OG images
    - Twitter images
    - JSON-LD
    - lazy-loaded images
    - srcset
    """

    print()
    print("=" * 60)
    print("REAL ARTICLE IMAGE COLLECTION")
    print("=" * 60)

    original_urls = get_image_urls(
        story
    )

    print(
        f"Initial image/page URLs found: "
        f"{len(original_urls)}"
    )

    for index, url in enumerate(
        original_urls,
        1,
    ):
        print(
            f"  ORIGINAL {index}: {url}"
        )

    if not original_urls:
        raise RuntimeError(
            "Selected story contains no image URLs."
        )

    candidate_urls = expand_image_candidates(
        original_urls
    )

    print()
    print(
        f"Expanded direct image candidates: "
        f"{len(candidate_urls)}"
    )

    unique_hashes = set()
    downloaded = []

    for candidate_index, url in enumerate(
        candidate_urls,
        1,
    ):

        if len(downloaded) >= MAX_SCENES:
            break

        output_path = (
            SOURCE_DIR
            / (
                "story_image.jpg"
                if len(downloaded) == 0
                else f"story_image_{len(downloaded)}.jpg"
            )
        )

        success = download_image(
            url,
            output_path,
        )

        if not success:
            continue

        current_hash = image_hash(
            output_path
        )

        if not current_hash:
            safe_unlink(output_path)
            continue

        if current_hash in unique_hashes:
            print(
                "Duplicate image detected. Skipping."
            )
            safe_unlink(output_path)
            continue

        unique_hashes.add(
            current_hash
        )

        downloaded.append(
            output_path
        )

        print(
            f"Accepted real article photo "
            f"{len(downloaded)}/{MAX_SCENES}"
        )

    if not downloaded:
        raise RuntimeError(
            "No valid real article photos were available."
        )

    print()
    print("=" * 60)
    print("REAL ARTICLE PHOTOS READY")
    print("=" * 60)

    for path in downloaded:
        print(
            f"{path} - "
            f"{path.stat().st_size} bytes"
        )

    return downloaded


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size=size,
            )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
    words = text.split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        test = current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_text_with_shadow(
    draw,
    position,
    text,
    font,
    fill,
    shadow_fill=(0, 0, 0),
    shadow_offset=3,
):
    x, y = position

    draw.text(
        (
            x + shadow_offset,
            y + shadow_offset,
        ),
        text,
        font=font,
        fill=shadow_fill,
    )

    draw.text(
        position,
        text,
        font=font,
        fill=fill,
    )


# ============================================================
# IMAGE COVER CROP
# ============================================================

def cover_crop(image, width, height):
    image = image.convert("RGB")

    source_width, source_height = image.size

    if source_width <= 0 or source_height <= 0:
        raise RuntimeError(
            "Invalid image dimensions."
        )

    target_ratio = width / height
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        # Crop sides.
        new_width = int(
            source_height * target_ratio
        )

        left = (
            source_width - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                source_height,
            )
        )

    else:
        # Crop top/bottom.
        new_height = int(
            source_width / target_ratio
        )

        top = (
            source_height - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                source_width,
                top + new_height,
            )
        )

    return image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


# ============================================================
# FRAME CREATION
# ============================================================

def create_scene_frame(
    image_path,
    title,
    scene_index,
    total_scenes,
):
    """
    Create one professional vertical broadcast frame.

    IMPORTANT:
    No source/publisher/URL is rendered.
    """

    with Image.open(image_path) as image:
        image = image.convert("RGB")
        background = cover_crop(
            image,
            WIDTH,
            HEIGHT,
        )

    # Slightly soften the background for readability.
    blurred = background.filter(
        ImageFilter.GaussianBlur(
            radius=0.7
        )
    )

    canvas = blurred.copy()

    draw = ImageDraw.Draw(
        canvas,
        "RGBA",
    )

    # --------------------------------------------------------
    # Dark lower gradient-like panels
    # --------------------------------------------------------

    # Top branding strip.
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            150,
        ),
        fill=(0, 0, 0, 190),
    )

    # Bottom story panel.
    bottom_start = int(
        HEIGHT * 0.64
    )

    draw.rectangle(
        (
            0,
            bottom_start,
            WIDTH,
            HEIGHT,
        ),
        fill=(0, 0, 0, 190),
    )

    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    brand_font = find_font(
        44,
        bold=True,
    )

    draw_text_with_shadow(
        draw,
        (55, 40),
        BRAND_NAME,
        brand_font,
        (255, 255, 255, 255),
    )

    # Accent line.
    draw.rectangle(
        (
            55,
            105,
            340,
            114,
        ),
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # Scene indicator
    # --------------------------------------------------------

    scene_font = find_font(
        30,
        bold=True,
    )

    scene_text = (
        f"{scene_index}/{total_scenes}"
    )

    bbox = draw.textbbox(
        (0, 0),
        scene_text,
        font=scene_font,
    )

    scene_width = (
        bbox[2] - bbox[0]
    )

    draw_text_with_shadow(
        draw,
        (
            WIDTH - scene_width - 55,
            48,
        ),
        scene_text,
        scene_font,
        (255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # Breaking/news label
    # --------------------------------------------------------

    label_font = find_font(
        30,
        bold=True,
    )

    draw.rounded_rectangle(
        (
            50,
            bottom_start + 55,
            300,
            bottom_start + 105,
        ),
        radius=8,
        fill=(255, 255, 255, 255),
    )

    draw.text(
        (
            72,
            bottom_start + 65,
        ),
        "RIFT VALLEY",
        font=label_font,
        fill=(0, 0, 0, 255),
    )

    # --------------------------------------------------------
    # Headline
    # --------------------------------------------------------

    headline_font = find_font(
        62,
        bold=True,
    )

    title = clean_text(title)

    lines = wrap_text(
        draw,
        title,
        headline_font,
        WIDTH - 110,
    )

    max_lines = 5

    if len(lines) > max_lines:
        lines = lines[:max_lines]

        if lines:
            last = lines[-1]

            if len(last) > 3:
                lines[-1] = (
                    last.rstrip(" .")
                    + "..."
                )

    line_height = 76

    y = bottom_start + 135

    for line in lines:

        draw_text_with_shadow(
            draw,
            (55, y),
            line,
            headline_font,
            (255, 255, 255, 255),
            shadow_fill=(0, 0, 0, 220),
            shadow_offset=4,
        )

        y += line_height

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    footer_font = find_font(
        28,
        bold=True,
    )

    footer_text = BRAND_TAGLINE

    draw_text_with_shadow(
        draw,
        (
            55,
            HEIGHT - 90,
        ),
        footer_text,
        footer_font,
        (255, 255, 255, 255),
        shadow_fill=(0, 0, 0, 230),
    )

    output_path = (
        VIDEO_WORK_DIR
        / f"frame_{scene_index:02d}.jpg"
    )

    canvas.save(
        output_path,
        "JPEG",
        quality=94,
        optimize=True,
    )

    return output_path


def create_scene_frames(
    image_paths,
    title,
):
    frames = []

    total = len(image_paths)

    for index, image_path in enumerate(
        image_paths,
        1,
    ):

        frame = create_scene_frame(
            image_path,
            title,
            index,
            total,
        )

        frames.append(frame)

    return frames


# ============================================================
# SCENE DURATIONS
# ============================================================

def calculate_scene_durations(
    audio_duration,
    number_of_scenes,
):
    if number_of_scenes <= 0:
        return []

    duration = min(
        audio_duration,
        HARD_MAX_DURATION,
    )

    duration = max(
        duration,
        MIN_DURATION,
    )

    # Slightly varied scene timing while ensuring
    # total duration equals the audio duration.
    weights = []

    if number_of_scenes == 1:
        weights = [1.0]

    elif number_of_scenes == 2:
        weights = [0.47, 0.53]

    elif number_of_scenes == 3:
        weights = [0.30, 0.34, 0.36]

    else:
        weights = [
            0.23,
            0.25,
            0.26,
            0.26,
        ]

        weights = weights[:number_of_scenes]

        total_weight = sum(weights)

        weights = [
            value / total_weight
            for value in weights
        ]

    durations = [
        duration * weight
        for weight in weights
    ]

    # Make sure no scene is unrealistically short.
    minimum_scene = 2.5

    if any(
        value < minimum_scene
        for value in durations
    ):
        equal = duration / number_of_scenes

        durations = [
            equal
            for _ in range(number_of_scenes)
        ]

    # Correct floating point rounding.
    difference = (
        duration - sum(durations)
    )

    durations[-1] += difference

    return durations


# ============================================================
# SILENT SCENE VIDEO
# ============================================================

def create_scene_video(
    frame_path,
    duration,
    scene_index,
):
    output_path = (
        VIDEO_WORK_DIR
        / f"scene_{scene_index:02d}.mp4"
    )

    safe_unlink(output_path)

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-i",
        str(frame_path),
        "-t",
        f"{duration:.3f}",
        "-r",
        str(FPS),
        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:"
            f"(ow-iw)/2:(oh-ih)/2"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]

    run_command(
        command,
        f"Creating silent scene {scene_index}",
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene video was not created: "
            f"{output_path}"
        )

    return output_path


# ============================================================
# CONCATENATION
# ============================================================

def concat_scene_videos(
    scene_videos,
    output_path,
):
    concat_file = (
        VIDEO_WORK_DIR
        / "concat_scenes.txt"
    )

    safe_unlink(concat_file)
    safe_unlink(output_path)

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_videos:

            absolute = (
                scene.resolve()
            )

            escaped = (
                str(absolute)
                .replace("'", "'\\''")
            )

            f.write(
                f"file '{escaped}'\n"
            )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(output_path),
    ]

    run_command(
        command,
        "Concatenating scene videos",
    )

    if not output_path.exists():
        raise RuntimeError(
            "Silent concatenated video was not created."
        )

    return output_path


# ============================================================
# FINAL AUDIO MUX
# ============================================================

def mux_audio(
    silent_video,
    audio_file,
    output_file,
):
    safe_unlink(output_file)

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(silent_video),
        "-i",
        str(audio_file),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_file),
    ]

    run_command(
        command,
        "Muxing final narration into MP4",
    )

    if not output_file.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return output_file


# ============================================================
# FINAL DURATION CAP
# ============================================================

def enforce_final_duration(
    input_file,
    audio_file,
    output_file,
):
    """
    Ensure the final video cannot exceed HARD_MAX_DURATION.
    """

    duration = get_media_duration(
        input_file
    )

    if duration <= HARD_MAX_DURATION + 0.10:
        return input_file

    print(
        f"Final silent video is {duration:.2f}s. "
        f"Capping at {HARD_MAX_DURATION:.2f}s."
    )

    temp_output = (
        VIDEO_WORK_DIR
        / "duration_capped.mp4"
    )

    safe_unlink(temp_output)

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_file),
        "-t",
        f"{HARD_MAX_DURATION:.2f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(temp_output),
    ]

    run_command(
        command,
        "Capping video duration",
    )

    return temp_output


# ============================================================
# FINAL VERIFICATION
# ============================================================

def verify_final_video(path):
    print()
    print("=" * 60)
    print("VERIFYING FINAL MP4")
    print("=" * 60)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    print(
        f"File size: {size} bytes"
    )

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    duration = get_media_duration(
        path
    )

    print(
        f"Duration: {duration:.2f}s"
    )

    if duration <= 0:
        raise RuntimeError(
            "Final MP4 duration is invalid."
        )

    if duration > HARD_MAX_DURATION + 0.20:
        raise RuntimeError(
            f"Final MP4 exceeds hard duration limit: "
            f"{duration:.2f}s"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not inspect final MP4."
        )

    width_match = re.search(
        r"width=(\d+)",
        result.stdout,
    )

    height_match = re.search(
        r"height=(\d+)",
        result.stdout,
    )

    codec_types = re.findall(
        r"codec_type=(\w+)",
        result.stdout,
    )

    if not width_match or not height_match:
        raise RuntimeError(
            "Could not determine final video dimensions."
        )

    final_width = int(
        width_match.group(1)
    )

    final_height = int(
        height_match.group(1)
    )

    print(
        f"Dimensions: "
        f"{final_width}x{final_height}"
    )

    if final_width != WIDTH:
        raise RuntimeError(
            f"Incorrect width: {final_width}"
        )

    if final_height != HEIGHT:
        raise RuntimeError(
            f"Incorrect height: {final_height}"
        )

    if "video" not in codec_types:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if "audio" not in codec_types:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    print()
    print(
        "FINAL MP4 VERIFICATION SUCCESSFUL"
    )


# ============================================================
# SELECTED STORY / SCRIPT COMPATIBILITY
# ============================================================

def ensure_selected_story_exists():
    if not SELECTED_STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json was not generated."
        )

    if SELECTED_STORY_FILE.stat().st_size < 10:
        raise RuntimeError(
            "selected_story.json is empty."
        )


def ensure_selected_script_exists():
    """
    selected_script.json is expected by the workflow.
    If the main engine has not created one, create a clean
    compatibility copy containing the generated narration.
    """

    if SELECTED_SCRIPT_FILE.exists():
        existing = load_json_file(
            SELECTED_SCRIPT_FILE
        )

        if existing:
            return existing

    return {}


def write_selected_script_if_missing(
    narration
):
    if SELECTED_SCRIPT_FILE.exists():
        existing = load_json_file(
            SELECTED_SCRIPT_FILE
        )

        if existing:
            return

    payload = {
        "narration": narration,
        "word_count": word_count(narration),
    }

    with SELECTED_SCRIPT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# CLEAN OLD SOURCE IMAGES
# ============================================================

def remove_old_story_images():
    for item in SOURCE_DIR.glob(
        "story_image*"
    ):
        safe_unlink(item)


# ============================================================
# MAIN VIDEO PIPELINE
# ============================================================

def generate_video():
    prepare_directories()

    ensure_selected_story_exists()

    story = load_story()

    script = ensure_selected_script_exists()

    # --------------------------------------------------------
    # Story metadata
    # --------------------------------------------------------

    title = get_story_title(
        story
    )

    source = get_story_source(
        story
    )

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V25")
    print("=" * 60)
    print(f"TITLE: {title}")

    # Source is LOGGING ONLY.
    if source:
        print(
            f"SOURCE FOUND FOR LOGGING ONLY: {source}"
        )

    print(
        "SOURCE WILL NOT APPEAR IN VIDEO OR NARRATION."
    )

    # --------------------------------------------------------
    # Narration
    # --------------------------------------------------------

    narration_text = build_narration(
        story,
        script,
    )

    write_selected_script_if_missing(
        narration_text
    )

    # Re-load after compatibility creation.
    script = load_script()

    audio_duration = create_narration(
        story,
        script,
    )

    if audio_duration < MIN_DURATION:
        print(
            f"WARNING: audio duration "
            f"{audio_duration:.2f}s is below "
            f"minimum {MIN_DURATION:.2f}s."
        )

    # --------------------------------------------------------
    # Real article photographs
    # --------------------------------------------------------

    remove_old_story_images()

    image_paths = download_real_images(
        story
    )

    if not image_paths:
        raise RuntimeError(
            "No valid real article photos were available."
        )

    # --------------------------------------------------------
    # Scene frames
    # --------------------------------------------------------

    frames = create_scene_frames(
        image_paths,
        title,
    )

    if not frames:
        raise RuntimeError(
            "No scene frames were generated."
        )

    # --------------------------------------------------------
    # Scene durations
    # --------------------------------------------------------

    effective_duration = min(
        audio_duration,
        HARD_MAX_DURATION,
    )

    if effective_duration < MIN_DURATION:
        effective_duration = audio_duration

    scene_durations = calculate_scene_durations(
        effective_duration,
        len(frames),
    )

    print()
    print("=" * 60)
    print("SCENE DURATIONS")
    print("=" * 60)

    for index, duration in enumerate(
        scene_durations,
        1,
    ):
        print(
            f"Scene {index}: "
            f"{duration:.3f}s"
        )

    print(
        f"Total scene duration: "
        f"{sum(scene_durations):.3f}s"
    )

    # --------------------------------------------------------
    # Scene videos
    # --------------------------------------------------------

    scene_videos = []

    for index, (
        frame,
        duration,
    ) in enumerate(
        zip(
            frames,
            scene_durations,
        ),
        1,
    ):

        scene_video = create_scene_video(
            frame,
            duration,
            index,
        )

        scene_videos.append(
            scene_video
        )

    # --------------------------------------------------------
    # Concatenate
    # --------------------------------------------------------

    silent_video = (
        VIDEO_WORK_DIR
        / "silent_reel.mp4"
    )

    concat_scene_videos(
        scene_videos,
        silent_video,
    )

    # --------------------------------------------------------
    # Duration safety
    # --------------------------------------------------------

    capped_video = enforce_final_duration(
        silent_video,
        NARRATION_FILE,
        silent_video,
    )

    # --------------------------------------------------------
    # Final mux
    # --------------------------------------------------------

    mux_audio(
        capped_video,
        NARRATION_FILE,
        FINAL_VIDEO,
    )

    # --------------------------------------------------------
    # Final verification
    # --------------------------------------------------------

    verify_final_video(
        FINAL_VIDEO
    )

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH GENERATION SUCCESSFUL")
    print("=" * 60)
    print(
        f"FINAL VIDEO: {FINAL_VIDEO}"
    )

    return FINAL_VIDEO


# ============================================================
# COMPATIBILITY CLEANUP
# ============================================================

def cleanup_temp_files():
    """
    Keep the final MP4, narration and real source photographs.
    Remove temporary scene/render files.
    """

    patterns = [
        "scene_*.mp4",
        "frame_*.jpg",
        "concat*.txt",
        "silent_reel.mp4",
        "duration_capped.mp4",
        "*.download",
    ]

    for pattern in patterns:
        for item in VIDEO_WORK_DIR.glob(pattern):
            safe_unlink(item)

    for item in AUDIO_DIR.glob(
        "narration_candidate_*.mp3"
    ):
        safe_unlink(item)


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("VIDEO GENERATOR")
    print("RVW_VIDEO_V25_ARTICLE_PAGE_IMAGE_RESOLVER")
    print("=" * 70)
    print(
        "Purpose: resolve real article pages into real photographs."
    )
    print(
        "Source/publisher audio and visual overlays: DISABLED."
    )
    print("=" * 70)

    try:
        prepare_directories()

        # Do NOT delete selected_story.json here.
        # The main engine is responsible for selecting the story.
        #
        # Only generated media files are cleaned.
        clean_generated_files()

        if not command_exists("ffmpeg"):
            raise RuntimeError(
                "FFmpeg was not found."
            )

        if not command_exists("ffprobe"):
            raise RuntimeError(
                "FFprobe was not found."
            )

        final_video = generate_video()

        elapsed = (
            time.time() - start_time
        )

        print()
        print("=" * 70)
        print("GENERATION COMPLETE")
        print("=" * 70)
        print(
            f"Elapsed time: {elapsed:.1f}s"
        )
        print(
            f"Output: {final_video}"
        )
        print(
            f"Output size: "
            f"{final_video.stat().st_size} bytes"
        )

        return 0

    except KeyboardInterrupt:
        print(
            "Generation interrupted."
        )
        return 130

    except Exception as exc:
        print()
        print("=" * 70)
        print("VIDEO GENERATOR FAILED")
        print("=" * 70)
        print(
            f"ERROR: {exc}"
        )

        import traceback

        traceback.print_exc()

        return 1

    finally:
        try:
            cleanup_temp_files()
        except Exception as cleanup_exc:
            print(
                f"WARNING: Cleanup failed: "
                f"{cleanup_exc}"
            )


if __name__ == "__main__":
    sys.exit(main())
