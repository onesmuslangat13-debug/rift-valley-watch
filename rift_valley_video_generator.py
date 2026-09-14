from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import time

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V25_ARTICLE_IMAGE_RESOLVER
#
# PURPOSE
# - One selected real news story
# - Multiple real article photos/scenes when available
# - Correctly resolves article URLs into real article images
# - No generic avatars/placeholders/logos
# - Professional 1080x1920 vertical news reel
# - NO SOURCE DISPLAYED ON VIDEO
# - NO SOURCE/PUBLISHER READ IN AUDIO
# - Stable narration/audio handling
# - Automatic narration duration control
# - Hard final duration safety cap
# - Correct data/audio/video paths for GitHub Actions
# - Final MP4:
#       output/rift_valley_watch_reel.mp4
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"

SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = BASE_DIR / "audio"
VIDEO_WORK_DIR = ASSETS_DIR / "video_work"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_AUDIO = AUDIO_DIR / "narration.mp3"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MAX_SCENES = 4

MIN_DURATION = 18.0
TARGET_DURATION = 23.0
MAX_DURATION = 35.0
HARD_MAX_DURATION = 34.50

MIN_WORDS = 65
TARGET_WORDS = 95
MAX_WORDS = 125


# ============================================================
# BRANDING
# ============================================================

BRAND_NAME = "RIFT VALLEY WATCH"

SUB_BRAND = "REGIONAL NEWS • CURRENT AFFAIRS"

NAVY = (8, 19, 36)
DARK_NAVY = (4, 11, 22)
WHITE = (255, 255, 255)
LIGHT_GREY = (218, 224, 232)
MID_GREY = (158, 170, 184)
RED = (215, 45, 45)
BLACK = (0, 0, 0)


# ============================================================
# IMAGE FILTERS
# ============================================================

BAD_IMAGE_TERMS = [
    "avatar",
    "placeholder",
    "profile",
    "logo",
    "icon",
    "favicon",
    "sprite",
    "world-cup",
    "worldcup",
    "advert",
    "advertisement",
    "banner",
    "loading",
    "generic",
    "default",
    "thumbnail",
    "thumb",
    "pixel",
    "transparent",
    "social",
    "whatsapp",
    "facebook",
    "twitter",
    "instagram",
    "youtube",
    "share",
    "author",
    "user",
    "person-placeholder",
    "headshot-placeholder",
]


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/128.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,image/svg+xml,image/*,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
)


# ============================================================
# DIRECTORY SETUP
# ============================================================

def prepare_directories():

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)

    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("RVW_VIDEO_V25_ARTICLE_IMAGE_RESOLVER")
    print("=" * 70)
    print("")
    print("BASE DIR:", BASE_DIR)
    print("STORY FILE:", STORY_FILE)
    print("SCRIPT FILE:", SCRIPT_FILE)
    print("AUDIO DIR:", AUDIO_DIR)
    print("SOURCE DIR:", SOURCE_DIR)
    print("VIDEO WORK DIR:", VIDEO_WORK_DIR)
    print("OUTPUT DIR:", OUTPUT_DIR)
    print("")
    print("MAX VIDEO DURATION:", MAX_DURATION)
    print("HARD AUDIO/VIDEO CAP:", HARD_MAX_DURATION)
    print("")
    print("SOURCE DISPLAY: DISABLED")
    print("SOURCE NARRATION: DISABLED")
    print("ARTICLE URL IMAGE RESOLUTION: ENABLED")
    print("")


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(command, check=True):

    print("")
    print("RUNNING:")
    print(" ".join(str(x) for x in command))
    print("")

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if check and result.returncode != 0:

        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"https?://\S+",
        " ",
        text,
    )

    text = re.sub(
        r"www\.\S+",
        " ",
        text,
    )

    text = text.replace(
        "&nbsp;",
        " ",
    )

    text = text.replace(
        "&amp;",
        "&",
    )

    text = text.replace(
        "&quot;",
        '"',
    )

    text = text.replace(
        "&#39;",
        "'",
    )

    text = re.sub(
        r"\b(source|sources|photo|image|credit)\s*:\s*[^.]+\.?",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(courtesy of|photo courtesy of|image courtesy of)\b[^.]*\.?",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_sentence(text):

    text = clean_text(text)

    text = re.sub(
        r"^(breaking|latest|update)\s*[:\-]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def word_count(text):

    return len(
        re.findall(
            r"\b[\w’'-]+\b",
            text or "",
        )
    )


# ============================================================
# SOURCE / ATTRIBUTION FILTER
# ============================================================

NARRATION_EXCLUDED_KEYS = {
    "source",
    "sources",
    "publisher",
    "publishers",
    "site",
    "site_name",
    "source_name",
    "publication",
    "publication_name",
    "publisher_name",
    "author",
    "authors",
    "byline",
    "credit",
    "photo_credit",
    "image_credit",
    "image_source",
    "photo_source",
    "source_url",
    "article_url",
    "url",
    "link",
    "links",
    "image_url",
    "image_urls",
    "photo_url",
    "photo_urls",
    "thumbnail",
    "thumbnail_url",
    "featured_image",
    "featured_image_url",
    "media_url",
}


# ============================================================
# REMOVE SOURCE ATTRIBUTION FROM NARRATION
# ============================================================

def remove_source_attribution(text):

    if not text:
        return ""

    text = clean_text(text)

    patterns = [
        r"\bsource\s*[:\-–—]\s*[^.!?]+[.!?]?",
        r"\bsources\s*[:\-–—]\s*[^.!?]+[.!?]?",
        r"\bphoto\s*[:\-–—]\s*[^.!?]+[.!?]?",
        r"\bimage\s*[:\-–—]\s*[^.!?]+[.!?]?",
        r"\bphoto\s+credit\s*[:\-–—]?\s*[^.!?]+[.!?]?",
        r"\bimage\s+credit\s*[:\-–—]?\s*[^.!?]+[.!?]?",
        r"\bphoto\s+source\s*[:\-–—]?\s*[^.!?]+[.!?]?",
        r"\bimage\s+source\s*[:\-–—]?\s*[^.!?]+[.!?]?",
        r"\bimage\s+courtesy\s+of\s+[^.!?]+[.!?]?",
        r"\bphoto\s+courtesy\s+of\s+[^.!?]+[.!?]?",
        r"\bcourtesy\s+of\s+[^.!?]+[.!?]?",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            " ",
            text,
            flags=re.IGNORECASE,
        )

    # Remove common leading attribution phrases.
    text = re.sub(
        r"^\s*(?:according to|as reported by|reported by|published by)\s+[^,;:]+[,;:]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# NARRATION FILTER
# ============================================================

def is_bad_narration_sentence(sentence):

    s = sentence.lower().strip()

    blocked = [
        "source:",
        "sources:",
        "photo:",
        "photo credit",
        "image credit",
        "image courtesy",
        "photo courtesy",
        "image source",
        "photo source",
        "source provided",
        "source says",
        "according to the source",
        "courtesy of",
        "read more",
        "click here",
        "subscribe",
        "follow us",
        "visit our website",
        "www.",
        "http://",
        "https://",
        "advertisement",
        "advert",
        "copyright",
        "all rights reserved",
        "staff writer",
        "by staff",
        "byline",
    ]

    for term in blocked:

        if term in s:
            return True

    return False


# ============================================================
# COLLECT NARRATION TEXT FIELDS
# ============================================================

def collect_text_fields(
    obj,
    results=None,
):

    if results is None:
        results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower().strip()

            if key_lower in NARRATION_EXCLUDED_KEYS:
                continue

            if any(
                term in key_lower
                for term in [
                    "source",
                    "publisher",
                    "publication",
                    "credit",
                    "byline",
                    "author",
                ]
            ):
                continue

            if isinstance(value, str):

                if key_lower in {
                    "title",
                    "headline",
                    "description",
                    "summary",
                    "content",
                    "body",
                    "text",
                    "script",
                    "narration",
                    "story",
                    "article",
                }:

                    cleaned = normalize_sentence(
                        value
                    )

                    cleaned = remove_source_attribution(
                        cleaned
                    )

                    if cleaned and not is_bad_narration_sentence(
                        cleaned
                    ):

                        results.append(
                            cleaned
                        )

            elif isinstance(
                value,
                (dict, list),
            ):

                collect_text_fields(
                    value,
                    results,
                )

    elif isinstance(obj, list):

        for item in obj:

            collect_text_fields(
                item,
                results,
            )

    return results


# ============================================================
# LOAD JSON
# ============================================================

def load_json_file(path):

    if not path.exists():

        print(
            f"ERROR: {path} does not exist."
        )

        return None

    if path.stat().st_size == 0:

        print(
            f"ERROR: {path} is empty."
        )

        return None

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return data

    except Exception as exc:

        print(
            f"ERROR loading {path}: {exc}"
        )

        return None


def load_story():

    print("")
    print("=" * 70)
    print("LOADING SELECTED STORY")
    print("=" * 70)

    print(
        "Looking for:",
        STORY_FILE,
    )

    story = load_json_file(
        STORY_FILE
    )

    if story is None:

        print(
            "ERROR: selected_story.json was not loaded."
        )

        return None

    if isinstance(story, dict):

        print(
            "Selected story loaded successfully."
        )

        print(
            "Headline:",
            story.get("title")
            or story.get("headline")
            or story.get("name")
            or "N/A",
        )

        print(
            "Source metadata:",
            story.get("source")
            or story.get("publisher")
            or story.get("site")
            or "N/A",
        )

    return story


def load_script():

    print("")
    print("=" * 70)
    print("LOADING SELECTED SCRIPT")
    print("=" * 70)

    print(
        "Looking for:",
        SCRIPT_FILE,
    )

    script = load_json_file(
        SCRIPT_FILE
    )

    if script is None:

        print(
            "WARNING: selected_script.json was not loaded."
        )

        print(
            "The generator will attempt to build narration "
            "from story data."
        )

    return script


# ============================================================
# GET STORY VALUES
# ============================================================

def get_story_title(story):

    if not isinstance(
        story,
        dict,
    ):

        return "Rift Valley Watch"

    candidates = [
        story.get("title"),
        story.get("headline"),
        story.get("name"),
    ]

    nested = story.get("story")

    if isinstance(
        nested,
        dict,
    ):

        candidates.extend(
            [
                nested.get("title"),
                nested.get("headline"),
            ]
        )

    for item in candidates:

        value = clean_text(
            item
        )

        if value:
            return value

    return "Rift Valley Watch"


# ============================================================
# GET SOURCE METADATA
# ============================================================

def get_story_source(story):

    if not isinstance(
        story,
        dict,
    ):

        return ""

    candidates = [
        story.get("source"),
        story.get("publisher"),
        story.get("site"),
        story.get("source_name"),
        story.get("publication"),
    ]

    nested = story.get("story")

    if isinstance(
        nested,
        dict,
    ):

        candidates.extend(
            [
                nested.get("source"),
                nested.get("publisher"),
                nested.get("site"),
            ]
        )

    for item in candidates:

        value = clean_text(
            item
        )

        if value:
            return value

    return ""


# ============================================================
# NARRATION SENTENCE SPLITTING
# ============================================================

def split_into_sentences(text):

    text = clean_text(
        text
    )

    text = remove_source_attribution(
        text
    )

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    results = []

    for part in parts:

        part = normalize_sentence(
            part
        )

        part = remove_source_attribution(
            part
        )

        if not part:
            continue

        if is_bad_narration_sentence(
            part
        ):
            continue

        results.append(
            part
        )

    return results


# ============================================================
# BUILD NARRATION
# ============================================================

def build_narration(
    story,
    script,
):

    candidates = []

    if script is not None:

        candidates.extend(
            collect_text_fields(
                script
            )
        )

    if story is not None:

        candidates.extend(
            collect_text_fields(
                story
            )
        )

    cleaned = []

    seen = set()

    for text in candidates:

        text = remove_source_attribution(
            text
        )

        sentences = split_into_sentences(
            text
        )

        for sentence in sentences:

            sentence = remove_source_attribution(
                sentence
            )

            if not sentence:
                continue

            key = re.sub(
                r"\W+",
                "",
                sentence.lower(),
            )

            if not key:
                continue

            if key in seen:
                continue

            seen.add(key)

            cleaned.append(
                sentence
            )

    if not cleaned:

        return ""

    combined = " ".join(
        cleaned
    )

    combined = remove_source_attribution(
        combined
    )

    combined = re.sub(
        r"\s+",
        " ",
        combined,
    ).strip()

    final_sentences = []

    for sentence in split_into_sentences(
        combined
    ):

        sentence = remove_source_attribution(
            sentence
        )

        if not sentence:
            continue

        if not is_bad_narration_sentence(
            sentence
        ):

            final_sentences.append(
                sentence
            )

    return " ".join(
        final_sentences
    ).strip()


# ============================================================
# SHORTEN NARRATION
# ============================================================

def shorten_narration(
    text,
    max_words=MAX_WORDS,
):

    sentences = split_into_sentences(
        text
    )

    if not sentences:
        return ""

    selected = []
    count = 0

    for sentence in sentences:

        wc = word_count(
            sentence
        )

        if count + wc <= max_words:

            selected.append(
                sentence
            )

            count += wc

        else:

            remaining = (
                max_words - count
            )

            if remaining >= 8:

                words = sentence.split()

                partial = " ".join(
                    words[:remaining]
                )

                partial = partial.rstrip(
                    ",;:-"
                )

                if partial:

                    selected.append(
                        partial + "."
                    )

            break

    result = " ".join(
        selected
    ).strip()

    return remove_source_attribution(
        result
    )


def trim_to_word_limit(
    text,
    max_words,
):

    words = text.split()

    if len(words) <= max_words:
        return text

    trimmed = " ".join(
        words[:max_words]
    )

    trimmed = trimmed.rstrip(
        ",;:-"
    )

    if not trimmed.endswith(
        (".", "!", "?")
    ):

        trimmed += "."

    return trimmed


# ============================================================
# BUILD NARRATION CANDIDATES
# ============================================================

def build_narration_candidates(
    story,
    script,
):

    base = build_narration(
        story,
        script,
    )

    base = remove_source_attribution(
        base
    )

    if not base:
        return []

    candidates = []

    original_words = word_count(
        base
    )

    if (
        MIN_WORDS
        <= original_words
        <= MAX_WORDS
    ):

        candidates.append(
            base
        )

    limits = [
        TARGET_WORDS,
        MAX_WORDS,
        115,
        110,
        105,
        100,
        95,
        90,
        85,
        80,
        75,
        70,
        MIN_WORDS,
    ]

    for limit in limits:

        candidate = shorten_narration(
            base,
            limit,
        )

        if not candidate:
            continue

        wc = word_count(
            candidate
        )

        if (
            MIN_WORDS
            <= wc
            <= MAX_WORDS
        ):

            candidates.append(
                candidate
            )

    unique = []

    seen = set()

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            candidate
        )

    return unique


# ============================================================
# TTS DURATION
# ============================================================

def get_audio_duration(path):

    if not path.exists():
        return 0.0

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        return 0.0

    try:

        return float(
            result.stdout.strip()
        )

    except Exception:

        return 0.0


# ============================================================
# GENERATE ONE TTS FILE
# ============================================================

def generate_single_tts(
    text,
    output_path,
):

    text = remove_source_attribution(
        text
    )

    if not text:

        raise RuntimeError(
            "Cannot generate TTS from empty/source-only text."
        )

    try:

        if output_path.exists():
            output_path.unlink()

    except Exception:
        pass

    print("")
    print(
        "Generating gTTS:",
        word_count(text),
        "words",
    )

    try:

        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(output_path)
        )

    except Exception as exc:

        raise RuntimeError(
            f"gTTS failed: {exc}"
        )

    if not output_path.exists():

        raise RuntimeError(
            "gTTS did not create the MP3 file."
        )

    if output_path.stat().st_size < 1000:

        raise RuntimeError(
            "Generated narration MP3 is too small."
        )

    duration = get_audio_duration(
        output_path
    )

    if duration <= 0:

        raise RuntimeError(
            "Unable to determine TTS audio duration."
        )

    print(
        "Generated duration:",
        round(
            duration,
            2,
        ),
        "seconds",
    )

    return duration


# ============================================================
# CREATE SAFE NARRATION
# ============================================================

def create_safe_narration(
    story,
    script,
):

    candidates = build_narration_candidates(
        story,
        script,
    )

    if not candidates:

        print(
            "ERROR: No usable narration text was found."
        )

        return "", 0.0

    candidates.sort(
        key=lambda x: abs(
            word_count(x)
            - TARGET_WORDS
        )
    )

    print("")
    print("=" * 70)
    print("TESTING NARRATION LENGTH")
    print("=" * 70)

    temp_candidates = []

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):

        candidate = remove_source_attribution(
            candidate
        )

        test_file = (
            AUDIO_DIR
            / f"tts_test_{index:02d}.mp3"
        )

        try:

            duration = generate_single_tts(
                candidate,
                test_file,
            )

        except Exception as exc:

            print(
                "TTS candidate failed:",
                exc,
            )

            continue

        temp_candidates.append(
            (
                candidate,
                duration,
                test_file,
            )
        )

        print(
            f"Candidate {index}: "
            f"{word_count(candidate)} words -> "
            f"{duration:.2f} seconds"
        )

        if (
            MIN_DURATION
            <= duration
            <= HARD_MAX_DURATION
        ):

            print("")
            print(
                "ACCEPTED NARRATION DURATION:",
                round(
                    duration,
                    2,
                ),
                "seconds",
            )

            return (
                candidate,
                duration,
            )

    print("")
    print(
        "No standard narration candidate fit "
        "the duration limit."
    )

    if temp_candidates:

        shortest = min(
            temp_candidates,
            key=lambda item: item[1],
        )

        base_text = shortest[0]
        base_duration = shortest[1]
        base_words = word_count(
            base_text
        )

        if base_duration > HARD_MAX_DURATION:

            estimated_words = int(
                base_words
                * (
                    HARD_MAX_DURATION
                    / base_duration
                )
                * 0.94
            )

            estimated_words = max(
                MIN_WORDS,
                min(
                    estimated_words,
                    base_words - 1,
                ),
            )

            print(
                "Dynamic word target:",
                estimated_words,
            )

            dynamic_limits = []

            current = estimated_words

            while current >= MIN_WORDS:

                dynamic_limits.append(
                    current
                )

                current -= 5

            for index, limit in enumerate(
                dynamic_limits,
                start=1,
            ):

                candidate = shorten_narration(
                    build_narration(
                        story,
                        script,
                    ),
                    limit,
                )

                candidate = remove_source_attribution(
                    candidate
                )

                if (
                    not candidate
                    or word_count(candidate)
                    < MIN_WORDS
                ):

                    continue

                test_file = (
                    AUDIO_DIR
                    / f"tts_dynamic_{index:02d}.mp3"
                )

                try:

                    duration = generate_single_tts(
                        candidate,
                        test_file,
                    )

                except Exception as exc:

                    print(
                        "Dynamic TTS failed:",
                        exc,
                    )

                    continue

                print(
                    "Dynamic candidate:",
                    word_count(candidate),
                    "words ->",
                    round(
                        duration,
                        2,
                    ),
                    "seconds",
                )

                if (
                    MIN_DURATION
                    <= duration
                    <= HARD_MAX_DURATION
                ):

                    print("")
                    print(
                        "DYNAMIC NARRATION ACCEPTED"
                    )

                    return (
                        candidate,
                        duration,
                    )

    valid_fallbacks = [
        item
        for item in temp_candidates
        if (
            item[1] >= MIN_DURATION
            and item[1] <= MAX_DURATION
        )
    ]

    if valid_fallbacks:

        selected = min(
            valid_fallbacks,
            key=lambda item: item[1],
        )

        print("")
        print(
            "USING SHORTEST VALID NARRATION:",
            round(
                selected[1],
                2,
            ),
            "seconds",
        )

        return (
            selected[0],
            selected[1],
        )

    raise RuntimeError(
        "Unable to create narration within "
        "the allowed duration."
    )


# ============================================================
# GENERATE FINAL NARRATION AUDIO
# ============================================================

def generate_tts(
    text,
    expected_duration=None,
):

    text = remove_source_attribution(
        text
    )

    if not text:

        raise RuntimeError(
            "Cannot generate TTS from empty narration."
        )

    print("")
    print("=" * 70)
    print("CREATING FINAL NARRATION AUDIO")
    print("=" * 70)

    temp_audio = (
        AUDIO_DIR
        / "narration_temp.mp3"
    )

    best_audio = (
        AUDIO_DIR
        / "narration_best.mp3"
    )

    for path in [
        temp_audio,
        best_audio,
        FINAL_AUDIO,
    ]:

        try:

            if path.exists():
                path.unlink()

        except Exception:
            pass

    duration = generate_single_tts(
        text,
        temp_audio,
    )

    if duration > HARD_MAX_DURATION:

        raise RuntimeError(
            "Final narration is still longer than "
            f"the hard limit: {duration:.2f}s"
        )

    if duration < MIN_DURATION:

        raise RuntimeError(
            "Final narration is shorter than "
            f"the minimum: {duration:.2f}s"
        )

    shutil.copy2(
        temp_audio,
        best_audio,
    )

    shutil.copy2(
        best_audio,
        FINAL_AUDIO,
    )

    final_duration = get_audio_duration(
        FINAL_AUDIO
    )

    print("")
    print(
        "FINAL NARRATION:",
        FINAL_AUDIO,
    )

    print(
        "FINAL AUDIO DURATION:",
        round(
            final_duration,
            2,
        ),
        "seconds",
    )

    print(
        "NARRATION WORD COUNT:",
        word_count(text),
    )

    print("")

    return final_duration


# ============================================================
# IMAGE URL HELPERS
# ============================================================

def looks_like_url(value):

    if not isinstance(value, str):
        return False

    value = value.strip()

    return value.startswith(
        (
            "http://",
            "https://",
        )
    )


def is_direct_image_url(url):

    if not looks_like_url(url):
        return False

    lower = url.lower().split("?")[0].split("#")[0]

    image_extensions = (
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

    return lower.endswith(
        image_extensions
    )


def looks_like_article_url(url):

    if not looks_like_url(url):
        return False

    lower = url.lower()

    if is_direct_image_url(url):
        return False

    article_terms = [
        "/news/",
        "/story/",
        "/article/",
        "/articles/",
        "/202",
        "/politics/",
        "/business/",
        "/counties/",
        "/bomet-",
        "/kericho-",
        "/nakuru-",
        "/nandi-",
        "/uasin",
        "/narok-",
        "/west-pokot",
        "/elgeyo",
        "/marakwet",
    ]

    for term in article_terms:

        if term in lower:
            return True

    return True


def normalize_image_url(url):

    if not isinstance(url, str):
        return ""

    url = url.strip()

    if not url:
        return ""

    if url.startswith("//"):
        url = "https:" + url

    return url


# ============================================================
# RECURSIVE IMAGE URL EXTRACTION
# ============================================================

def recursive_image_urls(
    obj,
    results=None,
):

    if results is None:
        results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

            if isinstance(value, str):

                if (
                    "image" in key_lower
                    or "photo" in key_lower
                    or "media" in key_lower
                    or "thumbnail" in key_lower
                ):

                    if looks_like_url(value):

                        results.append(
                            value
                        )

            elif isinstance(
                value,
                (dict, list),
            ):

                recursive_image_urls(
                    value,
                    results,
                )

    elif isinstance(
        obj,
        list,
    ):

        for item in obj:

            recursive_image_urls(
                item,
                results,
            )

    return results


# ============================================================
# EXTRACT IMAGES FROM ARTICLE PAGE
#
# This is the important V25 fix.
#
# If selected_story.json contains:
#
# https://www.kbc.co.ke/bomet-breaks-ground...
#
# that is an ARTICLE URL, not an image URL.
#
# We open the article and extract:
# - og:image
# - twitter:image
# - JSON-LD images
# - img src
# - img data-src
# - img data-lazy-src
# - srcset
# ============================================================

def extract_images_from_article_page(
    article_url,
):

    print("")
    print(
        "RESOLVING ARTICLE PAGE FOR REAL PHOTOS:"
    )

    print(
        article_url
    )

    if not looks_like_url(article_url):

        return []

    candidates = []

    try:

        response = SESSION.get(
            article_url,
            timeout=25,
            allow_redirects=True,
        )

    except Exception as exc:

        print(
            "Article page request failed:",
            exc,
        )

        return []

    if response.status_code != 200:

        print(
            "Article page HTTP status:",
            response.status_code,
        )

        return []

    content_type = (
        response.headers.get(
            "content-type",
            ""
        )
        .lower()
    )

    if "html" not in content_type:

        print(
            "URL did not return HTML:",
            content_type,
        )

        return []

    final_url = response.url

    print(
        "Resolved article URL:",
        final_url,
    )

    try:

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

    except Exception as exc:

        print(
            "BeautifulSoup parsing failed:",
            exc,
        )

        return []

    # --------------------------------------------------------
    # OpenGraph image.
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta"
    ):

        prop = (
            tag.get("property")
            or tag.get("name")
            or ""
        ).strip().lower()

        content = (
            tag.get("content")
            or ""
        ).strip()

        if not content:
            continue

        if prop in {
            "og:image",
            "og:image:url",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
            "twitter:image:url",
        }:

            candidates.append(
                content
            )

    # --------------------------------------------------------
    # JSON-LD structured data.
    # --------------------------------------------------------

    for script_tag in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        raw = script_tag.string or script_tag.get_text()

        if not raw:
            continue

        try:

            parsed = json.loads(
                raw
            )

            candidates.extend(
                recursive_image_urls(
                    parsed
                )
            )

        except Exception:

            # Some publishers have malformed JSON-LD.
            # Continue to normal HTML extraction.
            pass

    # --------------------------------------------------------
    # Standard HTML images.
    # --------------------------------------------------------

    for img in soup.find_all(
        "img"
    ):

        for attr in [
            "src",
            "data-src",
            "data-original",
            "data-lazy-src",
            "data-image",
            "data-url",
        ]:

            value = img.get(
                attr
            )

            if looks_like_url(value):

                candidates.append(
                    value
                )

        # ----------------------------------------------------
        # srcset
        # ----------------------------------------------------

        srcset = img.get(
            "srcset"
        )

        if srcset:

            for item in srcset.split(","):

                item = item.strip()

                if not item:
                    continue

                parts = item.split()

                if parts:

                    candidate = parts[0]

                    if looks_like_url(
                        candidate
                    ):

                        candidates.append(
                            candidate
                        )

    # --------------------------------------------------------
    # Canonical URL-relative image references.
    # --------------------------------------------------------

    from urllib.parse import urljoin

    normalized = []

    for candidate in candidates:

        if not isinstance(
            candidate,
            str,
        ):
            continue

        candidate = candidate.strip()

        if not candidate:
            continue

        if candidate.startswith(
            (
                "data:",
                "javascript:",
                "#",
            )
        ):
            continue

        if candidate.startswith("//"):

            candidate = (
                "https:"
                + candidate
            )

        elif not candidate.startswith(
            (
                "http://",
                "https://",
            )
        ):

            candidate = urljoin(
                final_url,
                candidate,
            )

        if looks_like_url(
            candidate
        ):

            normalized.append(
                candidate
            )

    # --------------------------------------------------------
    # De-duplicate.
    # --------------------------------------------------------

    final = []

    seen = set()

    for candidate in normalized:

        candidate = normalize_image_url(
            candidate
        )

        if not candidate:
            continue

        key = (
            candidate.lower()
            .split("?")[0]
            .split("#")[0]
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        final.append(
            candidate
        )

    print(
        "Images extracted from article page:",
        len(final),
    )

    for index, candidate in enumerate(
        final[:20],
        start=1,
    ):

        print(
            f"  ARTICLE IMAGE {index}:",
            candidate,
        )

    return final


# ============================================================
# GET IMAGE URLS FROM STORY JSON
# ============================================================

def get_image_urls(story):

    urls = []

    if not isinstance(
        story,
        dict,
    ):

        return urls

    explicit = story.get(
        "image_urls"
    )

    if isinstance(
        explicit,
        list,
    ):

        for item in explicit:

            if looks_like_url(
                item
            ):

                urls.append(
                    str(item)
                )

    elif looks_like_url(
        explicit
    ):

        urls.append(
            explicit
        )

    # --------------------------------------------------------
    # Standard image fields.
    # --------------------------------------------------------

    for key in [
        "image_url",
        "image",
        "photo",
        "photo_url",
        "thumbnail",
        "thumbnail_url",
        "og_image",
        "featured_image",
        "featured_image_url",
        "media_url",
    ]:

        value = story.get(
            key
        )

        if looks_like_url(
            value
        ):

            urls.append(
                value
            )

        elif isinstance(
            value,
            list,
        ):

            for item in value:

                if looks_like_url(
                    item
                ):

                    urls.append(
                        item
                    )

                elif isinstance(
                    item,
                    dict,
                ):

                    urls.extend(
                        recursive_image_urls(
                            item
                        )
                    )

        elif isinstance(
            value,
            dict,
        ):

            urls.extend(
                recursive_image_urls(
                    value
                )
            )

    # --------------------------------------------------------
    # Search nested story structure.
    # --------------------------------------------------------

    urls.extend(
        recursive_image_urls(
            story
        )
    )

    # --------------------------------------------------------
    # De-duplicate initial candidates.
    # --------------------------------------------------------

    initial = []

    seen = set()

    for url in urls:

        if not looks_like_url(
            url
        ):
            continue

        url = normalize_image_url(
            url
        )

        key = (
            url.lower()
            .split("?")[0]
            .split("#")[0]
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        initial.append(
            url
        )

    print("")
    print(
        "INITIAL IMAGE/ARTICLE URL CANDIDATES:",
        len(initial),
    )

    # --------------------------------------------------------
    # CRITICAL FIX:
    #
    # Resolve article URLs into actual image URLs.
    #
    # Direct image URLs are retained.
    # Article URLs are NEVER sent to download_image().
    # --------------------------------------------------------

    final = []

    final_seen = set()

    for url in initial:

        if is_direct_image_url(
            url
        ):

            key = (
                url.lower()
                .split("?")[0]
                .split("#")[0]
            )

            if key not in final_seen:

                final_seen.add(
                    key
                )

                final.append(
                    url
                )

            continue

        # ----------------------------------------------------
        # This is not a direct image URL.
        # Treat it as an article page and resolve it.
        # ----------------------------------------------------

        print("")
        print(
            "NON-DIRECT IMAGE URL DETECTED."
        )

        print(
            "Resolving article/media page:",
            url,
        )

        article_images = (
            extract_images_from_article_page(
                url
            )
        )

        for image_url in article_images:

            if not is_direct_image_url(
                image_url
            ):

                # Even extracted candidates can sometimes
                # still be page URLs. Do not download them.
                continue

            key = (
                image_url.lower()
                .split("?")[0]
                .split("#")[0]
            )

            if key in final_seen:
                continue

            final_seen.add(
                key
            )

            final.append(
                image_url
            )

    print("")
    print(
        "FINAL DIRECT IMAGE URL CANDIDATES:",
        len(final),
    )

    for index, url in enumerate(
        final[:30],
        start=1,
    ):

        print(
            f"  IMAGE URL {index}:",
            url,
        )

    return final


# ============================================================
# IMAGE URL VALIDATION
# ============================================================

def image_url_is_bad(url):

    if not isinstance(
        url,
        str,
    ):

        return True

    value = url.lower()

    if not is_direct_image_url(
        value
    ):

        return True

    for term in BAD_IMAGE_TERMS:

        if term in value:
            return True

    return False


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    url,
    output_path,
):

    try:

        # ----------------------------------------------------
        # NEVER attempt to download an article page as image.
        # ----------------------------------------------------

        if not is_direct_image_url(
            url
        ):

            print(
                "Rejected non-direct image URL:",
                url,
            )

            return False

        if image_url_is_bad(
            url
        ):

            print(
                "Rejected URL:",
                url,
            )

            return False

        response = SESSION.get(
            url,
            timeout=25,
            allow_redirects=True,
        )

        if response.status_code != 200:

            print(
                "HTTP error:",
                response.status_code,
                url,
            )

            return False

        content_type = (
            response.headers.get(
                "content-type",
                ""
            )
            .lower()
        )

        # ----------------------------------------------------
        # A direct image candidate must actually return image
        # content. This prevents HTML article pages from being
        # saved as .jpg files.
        # ----------------------------------------------------

        if (
            content_type
            and not content_type.startswith(
                "image/"
            )
        ):

            print(
                "Rejected non-image content:",
                content_type,
                url,
            )

            return False

        data = response.content

        if len(data) < 10000:

            print(
                "Rejected tiny image:",
                url,
            )

            return False

        output_path.write_bytes(
            data
        )

        try:

            with Image.open(
                output_path
            ) as im:

                im.verify()

        except Exception:

            print(
                "Invalid image:",
                url,
            )

            try:
                output_path.unlink()
            except Exception:
                pass

            return False

        return True

    except Exception as exc:

        print(
            "Image download failed:",
            exc,
        )

        try:

            if output_path.exists():
                output_path.unlink()

        except Exception:
            pass

        return False


# ============================================================
# IMAGE QUALITY CHECK
# ============================================================

def image_is_valid(path):

    try:

        with Image.open(
            path
        ) as im:

            width, height = im.size

            if (
                width < 350
                or height < 250
            ):

                print(
                    "Rejected small image:",
                    width,
                    "x",
                    height,
                )

                return False

            area = width * height

            if area < 150000:

                print(
                    "Rejected low-area image."
                )

                return False

            ratio = (
                width
                / float(height)
            )

            if (
                ratio < 0.45
                or ratio > 3.5
            ):

                print(
                    "Rejected extreme aspect ratio:",
                    ratio,
                )

                return False

            if (
                abs(width - height) < 10
                and width < 500
            ):

                print(
                    "Rejected icon-like square."
                )

                return False

            rgb = im.convert(
                "RGB"
            )

            small = rgb.resize(
                (64, 64)
            )

            extrema = small.getextrema()

            channel_ranges = [
                maximum - minimum
                for minimum, maximum in extrema
            ]

            if max(channel_ranges) < 8:

                print(
                    "Rejected flat/blank image."
                )

                return False

            return True

    except Exception as exc:

        print(
            "Image validation error:",
            exc,
        )

        return False


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(path):

    try:

        with Image.open(
            path
        ) as im:

            thumb = im.convert(
                "RGB"
            )

            thumb.thumbnail(
                (64, 64)
            )

            data = thumb.tobytes()

            return hashlib.md5(
                data
            ).hexdigest()

    except Exception:

        return ""


# ============================================================
# DOWNLOAD MULTIPLE REAL PHOTOS
# ============================================================

def download_real_images(story):

    print("")
    print("=" * 70)
    print("DOWNLOADING REAL ARTICLE PHOTOS")
    print("=" * 70)

    urls = get_image_urls(
        story
    )

    print(
        "Direct image URLs ready for download:",
        len(urls),
    )

    if not urls:

        print(
            "ERROR: No direct image URLs found "
            "after article-page resolution."
        )

        return []

    for old in SOURCE_DIR.glob(
        "story_image_*.jpg"
    ):

        try:
            old.unlink()
        except Exception:
            pass

    for old in SOURCE_DIR.glob(
        "_candidate_*.jpg"
    ):

        try:
            old.unlink()
        except Exception:
            pass

    try:

        if FINAL_IMAGE.exists():
            FINAL_IMAGE.unlink()

    except Exception:
        pass

    valid_paths = []
    hashes = set()

    image_index = 1

    for url in urls:

        if len(valid_paths) >= MAX_SCENES:
            break

        print("")
        print(
            "IMAGE CANDIDATE",
            image_index,
        )

        print(
            url
        )

        # ----------------------------------------------------
        # Absolute safety:
        # article URLs should never reach this function.
        # ----------------------------------------------------

        if not is_direct_image_url(
            url
        ):

            print(
                "SKIPPED: URL is not a direct image."
            )

            image_index += 1
            continue

        temp_path = (
            SOURCE_DIR
            / f"_candidate_{image_index}.jpg"
        )

        try:

            if temp_path.exists():
                temp_path.unlink()

        except Exception:
            pass

        success = download_image(
            url,
            temp_path,
        )

        if not success:

            image_index += 1
            continue

        if not image_is_valid(
            temp_path
        ):

            try:
                temp_path.unlink()
            except Exception:
                pass

            image_index += 1
            continue

        digest = image_hash(
            temp_path
        )

        if (
            digest
            and digest in hashes
        ):

            print(
                "Rejected duplicate image."
            )

            try:
                temp_path.unlink()
            except Exception:
                pass

            image_index += 1
            continue

        if digest:
            hashes.add(
                digest
            )

        final_path = (
            SOURCE_DIR
            / (
                "story_image_"
                f"{len(valid_paths) + 1}.jpg"
            )
        )

        try:

            with Image.open(
                temp_path
            ) as im:

                converted = im.convert(
                    "RGB"
                )

                converted.save(
                    final_path,
                    "JPEG",
                    quality=94,
                    optimize=True,
                )

            temp_path.unlink()

        except Exception as exc:

            print(
                "Image conversion failed:",
                exc,
            )

            try:
                temp_path.unlink()
            except Exception:
                pass

            image_index += 1
            continue

        valid_paths.append(
            final_path
        )

        print(
            "ACCEPTED REAL ARTICLE PHOTO:",
            final_path,
        )

        image_index += 1

    if not valid_paths:

        print("")
        print(
            "ERROR: No valid real article photos "
            "were downloaded."
        )

        return []

    shutil.copy2(
        valid_paths[0],
        FINAL_IMAGE,
    )

    print("")
    print(
        "VALID REAL PHOTOS:",
        len(valid_paths),
    )

    print(
        "Compatibility image:",
        FINAL_IMAGE,
    )

    print("")

    for path in valid_paths:

        try:

            with Image.open(
                path
            ) as im:

                print(
                    path.name,
                    "->",
                    im.size,
                    "->",
                    path.stat().st_size,
                    "bytes",
                )

        except Exception:
            pass

    return valid_paths


# ============================================================
# FONT LOADING
# ============================================================

def load_font(
    size,
    bold=False,
):

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

    for font_path in candidates:

        if Path(font_path).exists():

            try:

                return ImageFont.truetype(
                    font_path,
                    size=size,
                )

            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = (
            bbox[2]
            - bbox[0]
        )

        if width <= max_width:

            current = test

        else:

            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    return lines


def draw_wrapped_text(
    draw,
    text,
    font,
    x,
    y,
    max_width,
    fill,
    line_spacing=12,
    max_lines=None,
):

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    if max_lines is not None:

        lines = lines[
            :max_lines
        ]

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        bbox = draw.textbbox(
            (x, y),
            line,
            font=font,
        )

        line_height = (
            bbox[3]
            - bbox[1]
        )

        y += (
            line_height
            + line_spacing
        )

    return y


# ============================================================
# IMAGE COVER CROP
# ============================================================

def cover_crop(
    image,
    width,
    height,
):

    image = image.convert(
        "RGB"
    )

    source_w, source_h = image.size

    source_ratio = (
        source_w
        / float(source_h)
    )

    target_ratio = (
        width
        / float(height)
    )

    if source_ratio > target_ratio:

        new_height = source_h

        new_width = int(
            source_h
            * target_ratio
        )

    else:

        new_width = source_w

        new_height = int(
            source_w
            / target_ratio
        )

    left = max(
        0,
        (
            source_w
            - new_width
        )
        // 2,
    )

    top = max(
        0,
        (
            source_h
            - new_height
        )
        // 2,
    )

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height,
        )
    )

    return image.resize(
        (
            width,
            height,
        ),
        Image.Resampling.LANCZOS,
    )


# ============================================================
# CREATE SCENE FRAME
#
# SOURCE IS INTENTIONALLY NOT DISPLAYED.
# ============================================================

def create_scene_frame(
    image_path,
    title,
    scene_number,
    total_scenes,
):

    image = Image.open(
        image_path
    ).convert("RGB")

    background = cover_crop(
        image,
        WIDTH,
        HEIGHT,
    )

    background = background.filter(
        ImageFilter.GaussianBlur(18)
    )

    dark_overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 145),
    )

    background = background.convert(
        "RGBA"
    )

    background.alpha_composite(
        dark_overlay
    )

    canvas = background

    # --------------------------------------------------------
    # Main photo
    # --------------------------------------------------------

    photo_width = 970
    photo_height = 820

    photo = cover_crop(
        image,
        photo_width,
        photo_height,
    )

    photo = photo.convert(
        "RGB"
    )

    photo_x = (
        WIDTH
        - photo_width
    ) // 2

    photo_y = 365

    shadow = Image.new(
        "RGBA",
        canvas.size,
        (0, 0, 0, 0),
    )

    shadow_draw = ImageDraw.Draw(
        shadow
    )

    shadow_draw.rounded_rectangle(
        (
            photo_x - 10,
            photo_y - 10,
            photo_x
            + photo_width
            + 10,
            photo_y
            + photo_height
            + 10,
        ),
        radius=22,
        fill=(0, 0, 0, 170),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(14)
    )

    canvas.alpha_composite(
        shadow
    )

    canvas.alpha_composite(
        photo.convert("RGBA"),
        (
            photo_x,
            photo_y,
        ),
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    header_height = 270

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            header_height,
        ),
        fill=NAVY,
    )

    draw.rectangle(
        (
            0,
            header_height - 8,
            WIDTH,
            header_height,
        ),
        fill=RED,
    )

    brand_font = load_font(
        58,
        bold=True,
    )

    sub_font = load_font(
        27,
        bold=False,
    )

    draw.text(
        (55, 52),
        BRAND_NAME,
        font=brand_font,
        fill=WHITE,
    )

    draw.text(
        (58, 135),
        SUB_BRAND,
        font=sub_font,
        fill=LIGHT_GREY,
    )

    # --------------------------------------------------------
    # Scene indicator
    # --------------------------------------------------------

    scene_font = load_font(
        28,
        bold=True,
    )

    scene_text = (
        f"REPORT {scene_number}/{total_scenes}"
    )

    scene_bbox = draw.textbbox(
        (0, 0),
        scene_text,
        font=scene_font,
    )

    scene_width = (
        scene_bbox[2]
        - scene_bbox[0]
    )

    draw.rounded_rectangle(
        (
            WIDTH
            - scene_width
            - 95,
            48,
            WIDTH - 45,
            98,
        ),
        radius=12,
        fill=RED,
    )

    draw.text(
        (
            WIDTH
            - scene_width
            - 70,
            57,
        ),
        scene_text,
        font=scene_font,
        fill=WHITE,
    )

    # --------------------------------------------------------
    # Headline panel
    # --------------------------------------------------------

    panel_y = 1230
    panel_height = 525

    draw.rounded_rectangle(
        (
            40,
            panel_y,
            WIDTH - 40,
            panel_y + panel_height,
        ),
        radius=28,
        fill=(4, 12, 24, 235),
        outline=(255, 255, 255, 35),
        width=2,
    )

    label_font = load_font(
        25,
        bold=True,
    )

    draw.text(
        (
            75,
            panel_y + 35,
        ),
        "RIFT VALLEY UPDATE",
        font=label_font,
        fill=RED,
    )

    headline_font = load_font(
        49,
        bold=True,
    )

    headline = clean_text(
        title
    )

    draw_wrapped_text(
        draw,
        headline,
        headline_font,
        75,
        panel_y + 90,
        WIDTH - 150,
        WHITE,
        line_spacing=13,
        max_lines=5,
    )

    # --------------------------------------------------------
    # NO SOURCE TEXT.
    # --------------------------------------------------------

    footer_y = 1810

    draw.rectangle(
        (
            0,
            footer_y,
            WIDTH,
            HEIGHT,
        ),
        fill=DARK_NAVY,
    )

    footer_font = load_font(
        24,
        bold=True,
    )

    draw.text(
        (
            55,
            footer_y + 35,
        ),
        "RIFT VALLEY WATCH",
        font=footer_font,
        fill=WHITE,
    )

    footer_small = load_font(
        21,
        bold=False,
    )

    draw.text(
        (
            55,
            footer_y + 82,
        ),
        "Independent regional news coverage",
        font=footer_small,
        fill=MID_GREY,
    )

    final = canvas.convert(
        "RGB"
    )

    return final


# ============================================================
# CREATE ALL SCENE FRAMES
# ============================================================

def create_scene_frames(
    image_paths,
    title,
):

    print("")
    print("=" * 70)
    print("CREATING REAL-PHOTO SCENES")
    print("=" * 70)

    if not image_paths:

        raise RuntimeError(
            "No valid image paths available."
        )

    total_scenes = len(
        image_paths
    )

    frame_paths = []

    for index, image_path in enumerate(
        image_paths,
        start=1,
    ):

        frame_path = (
            VIDEO_WORK_DIR
            / f"scene_{index:02d}.jpg"
        )

        print(
            f"Creating scene "
            f"{index}/{total_scenes}:",
            image_path,
        )

        frame = create_scene_frame(
            image_path,
            title,
            index,
            total_scenes,
        )

        frame.save(
            frame_path,
            "JPEG",
            quality=93,
            optimize=True,
        )

        frame_paths.append(
            frame_path
        )

    print("")
    print(
        "SCENE FRAMES CREATED:",
        len(frame_paths),
    )

    return frame_paths


# ============================================================
# CREATE SILENT VIDEO
# ============================================================

def create_silent_video(
    frame_paths,
    duration,
):

    print("")
    print("=" * 70)
    print("CREATING SILENT VIDEO")
    print("=" * 70)

    if not frame_paths:

        raise RuntimeError(
            "No scene frames found."
        )

    if duration <= 0:

        raise RuntimeError(
            "Invalid target duration."
        )

    target_duration = max(
        MIN_DURATION,
        min(
            HARD_MAX_DURATION,
            duration,
        ),
    )

    print(
        "Requested duration:",
        round(
            duration,
            2,
        ),
        "seconds",
    )

    print(
        "Video target duration:",
        round(
            target_duration,
            2,
        ),
        "seconds",
    )

    total_scenes = len(
        frame_paths
    )

    base_duration = (
        target_duration
        / total_scenes
    )

    concat_file = (
        VIDEO_WORK_DIR
        / "scenes.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for frame_path in frame_paths:

            f.write(
                "file "
                + "'"
                + str(
                    frame_path.resolve()
                ).replace(
                    "'",
                    "'\\''",
                )
                + "'\n"
            )

            f.write(
                f"duration "
                f"{base_duration:.4f}\n"
            )

        last_frame = frame_paths[-1]

        f.write(
            "file "
            + "'"
            + str(
                last_frame.resolve()
            ).replace(
                "'",
                "'\\''",
            )
            + "'\n"
        )

    silent_video = (
        VIDEO_WORK_DIR
        / "silent_video.mp4"
    )

    if silent_video.exists():

        silent_video.unlink()

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(silent_video),
        ]
    )

    if not silent_video.exists():

        raise RuntimeError(
            "Silent video was not generated."
        )

    if silent_video.stat().st_size < 50000:

        raise RuntimeError(
            "Silent video is unexpectedly small."
        )

    actual_duration = get_audio_duration(
        silent_video
    )

    print(
        "Generated silent video duration:",
        round(
            actual_duration,
            2,
        ),
        "seconds",
    )

    if actual_duration > HARD_MAX_DURATION:

        print(
            "Silent video exceeded hard cap."
        )

        capped_video = (
            VIDEO_WORK_DIR
            / "silent_video_capped.mp4"
        )

        if capped_video.exists():
            capped_video.unlink()

        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent_video),
                "-t",
                f"{HARD_MAX_DURATION:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(capped_video),
            ]
        )

        if not capped_video.exists():

            raise RuntimeError(
                "Unable to cap silent video duration."
            )

        shutil.move(
            str(capped_video),
            str(silent_video),
        )

        actual_duration = get_audio_duration(
            silent_video
        )

        print(
            "Capped silent video duration:",
            round(
                actual_duration,
                2,
            ),
            "seconds",
        )

    print(
        "Silent video:",
        silent_video,
    )

    return silent_video


# ============================================================
# PREPARE FINAL AUDIO
# ============================================================

def prepare_final_audio(
    audio_file,
):

    print("")
    print("=" * 70)
    print("PREPARING FINAL AUDIO")
    print("=" * 70)

    if not audio_file.exists():

        raise RuntimeError(
            "Narration audio does not exist."
        )

    duration = get_audio_duration(
        audio_file
    )

    if duration <= 0:

        raise RuntimeError(
            "Invalid narration duration."
        )

    print(
        "Original narration duration:",
        round(
            duration,
            2,
        ),
        "seconds",
    )

    if duration <= HARD_MAX_DURATION:

        print(
            "Narration is already within hard limit."
        )

        return audio_file

    capped_audio = (
        AUDIO_DIR
        / "narration_capped.mp3"
    )

    if capped_audio.exists():
        capped_audio.unlink()

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_file),
            "-t",
            f"{HARD_MAX_DURATION:.3f}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(capped_audio),
        ]
    )

    if not capped_audio.exists():

        raise RuntimeError(
            "Failed to create capped narration."
        )

    capped_duration = get_audio_duration(
        capped_audio
    )

    if capped_duration <= 0:

        raise RuntimeError(
            "Capped narration duration is invalid."
        )

    print(
        "Capped narration duration:",
        round(
            capped_duration,
            2,
        ),
        "seconds",
    )

    shutil.copy2(
        capped_audio,
        FINAL_AUDIO,
    )

    return FINAL_AUDIO


# ============================================================
# MUX AUDIO + VIDEO
# ============================================================

def mux_audio(
    silent_video,
    audio_file,
):

    print("")
    print("=" * 70)
    print("MUXING AUDIO + VIDEO")
    print("=" * 70)

    if not silent_video.exists():

        raise RuntimeError(
            "Silent video does not exist."
        )

    if not audio_file.exists():

        raise RuntimeError(
            "Narration audio does not exist."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_VIDEO.exists():

        try:
            FINAL_VIDEO.unlink()
        except Exception:
            pass

    video_duration = get_audio_duration(
        silent_video
    )

    audio_duration = get_audio_duration(
        audio_file
    )

    if video_duration <= 0:

        raise RuntimeError(
            "Invalid silent video duration."
        )

    if audio_duration <= 0:

        raise RuntimeError(
            "Invalid narration duration."
        )

    print(
        "Silent video duration:",
        round(
            video_duration,
            2,
        ),
        "seconds",
    )

    print(
        "Audio duration:",
        round(
            audio_duration,
            2,
        ),
        "seconds",
    )

    final_duration = min(
        video_duration,
        audio_duration,
        HARD_MAX_DURATION,
    )

    if final_duration < MIN_DURATION:

        raise RuntimeError(
            "Final duration would be below minimum: "
            f"{final_duration:.2f}s"
        )

    print(
        "FINAL TARGET DURATION:",
        round(
            final_duration,
            2,
        ),
        "seconds",
    )

    run_command(
        [
            "ffmpeg",
            "-y",
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
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-t",
            f"{final_duration:.3f}",
            "-shortest",
            "-movflags",
            "+faststart",
            str(FINAL_VIDEO),
        ]
    )

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final MP4 was not generated."
        )

    if FINAL_VIDEO.stat().st_size < 100000:

        raise RuntimeError(
            "Final MP4 is unexpectedly small."
        )

    actual_final_duration = get_audio_duration(
        FINAL_VIDEO
    )

    print("")
    print(
        "FINAL VIDEO:",
        FINAL_VIDEO,
    )

    print(
        "FINAL VIDEO SIZE:",
        FINAL_VIDEO.stat().st_size,
        "bytes",
    )

    print(
        "ACTUAL FINAL DURATION:",
        round(
            actual_final_duration,
            2,
        ),
        "seconds",
    )

    if actual_final_duration > HARD_MAX_DURATION:

        print("")
        print(
            "WARNING: Final MP4 still exceeds hard cap."
        )

        print(
            "Running emergency duration trim..."
        )

        emergency_video = (
            VIDEO_WORK_DIR
            / "final_duration_capped.mp4"
        )

        if emergency_video.exists():
            emergency_video.unlink()

        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(FINAL_VIDEO),
                "-t",
                f"{HARD_MAX_DURATION:.3f}",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(emergency_video),
            ]
        )

        if not emergency_video.exists():

            raise RuntimeError(
                "Emergency duration trim failed."
            )

        shutil.move(
            str(emergency_video),
            str(FINAL_VIDEO),
        )

        actual_final_duration = get_audio_duration(
            FINAL_VIDEO
        )

        print(
            "Emergency-capped duration:",
            round(
                actual_final_duration,
                2,
            ),
            "seconds",
        )

    return FINAL_VIDEO


# ============================================================
# VERIFY FINAL VIDEO
# ============================================================

def verify_final_video():

    print("")
    print("=" * 70)
    print("VERIFYING FINAL VIDEO")
    print("=" * 70)

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final video does not exist."
        )

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,"
            "sample_rate,channels",
            "-of",
            "default=noprint_wrappers=1",
            str(FINAL_VIDEO),
        ],
        check=False,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "ffprobe failed on final MP4."
        )

    width_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    height_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    audio_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    video_codec_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    audio_codec_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(FINAL_VIDEO),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:

        width = int(
            width_result.stdout.strip()
        )

        height = int(
            height_result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Unable to determine final video dimensions."
        )

    has_audio = bool(
        audio_result.stdout.strip()
    )

    video_codec = (
        video_codec_result.stdout.strip()
    )

    audio_codec = (
        audio_codec_result.stdout.strip()
    )

    if width != WIDTH:

        raise RuntimeError(
            f"Wrong video width: {width}"
        )

    if height != HEIGHT:

        raise RuntimeError(
            f"Wrong video height: {height}"
        )

    if not has_audio:

        raise RuntimeError(
            "Final video has no audio stream."
        )

    final_duration = get_audio_duration(
        FINAL_VIDEO
    )

    print("")
    print(
        "FINAL WIDTH:",
        width,
    )

    print(
        "FINAL HEIGHT:",
        height,
    )

    print(
        "FINAL DURATION:",
        round(
            final_duration,
            3,
        ),
        "seconds",
    )

    print(
        "VIDEO CODEC:",
        video_codec or "unknown",
    )

    print(
        "AUDIO CODEC:",
        audio_codec or "unknown",
    )

    print(
        "AUDIO STREAM: YES"
    )

    print("")

    if final_duration < (
        MIN_DURATION - 0.50
    ):

        raise RuntimeError(
            "Final video is too short: "
            f"{final_duration:.2f} seconds."
        )

    if final_duration > HARD_MAX_DURATION:

        raise RuntimeError(
            "Final video is too long: "
            f"{final_duration:.2f} seconds."
        )

    if final_duration > MAX_DURATION:

        raise RuntimeError(
            "Final video exceeds maximum duration: "
            f"{final_duration:.2f} seconds."
        )

    print(
        "DURATION CHECK: PASS"
    )

    print(
        f"Duration is within "
        f"{MIN_DURATION:.0f}-{MAX_DURATION:.0f} seconds."
    )

    print("")
    print(
        "FINAL VIDEO VERIFICATION SUCCESSFUL"
    )


# ============================================================
# COPY COMPATIBILITY FILES
# ============================================================

def finalize_compatibility_files(
    image_paths,
):

    if not image_paths:
        return

    first = image_paths[0]

    if first.exists():

        shutil.copy2(
            first,
            FINAL_IMAGE,
        )

    if FINAL_AUDIO.exists():

        AUDIO_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    print("")
    print(
        "COMPATIBILITY FILES READY"
    )

    print(
        "Story image:",
        FINAL_IMAGE,
    )

    print(
        "Narration:",
        FINAL_AUDIO,
    )

    print(
        "Video:",
        FINAL_VIDEO,
    )


# ============================================================
# CLEAN WORKING FILES
# ============================================================

def clean_working_files():

    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for pattern in [
        "scene_*.jpg",
        "silent_video.mp4",
        "silent_video_capped.mp4",
        "scenes.txt",
        "final_duration_capped.mp4",
        "narration.mp3",
    ]:

        for path in VIDEO_WORK_DIR.glob(
            pattern
        ):

            try:
                path.unlink()
            except Exception:
                pass

    for pattern in [
        "tts_test_*.mp3",
        "tts_dynamic_*.mp3",
        "narration_temp.mp3",
        "narration_best.mp3",
        "narration_capped.mp3",
    ]:

        for path in AUDIO_DIR.glob(
            pattern
        ):

            try:
                path.unlink()
            except Exception:
                pass

    for pattern in [
        "_candidate_*.jpg",
    ]:

        for path in SOURCE_DIR.glob(
            pattern
        ):

            try:
                path.unlink()
            except Exception:
                pass


# ============================================================
# MAIN
# ============================================================

def main():

    try:

        prepare_directories()

        clean_working_files()

        # ----------------------------------------------------
        # Load story.
        # ----------------------------------------------------

        story = load_story()

        if story is None:

            raise RuntimeError(
                "selected_story.json could not be loaded."
            )

        # ----------------------------------------------------
        # Load script.
        # ----------------------------------------------------

        script = load_script()

        # ----------------------------------------------------
        # Story details.
        # ----------------------------------------------------

        title = get_story_title(
            story
        )

        source = get_story_source(
            story
        )

        print("")
        print("=" * 70)
        print("SELECTED STORY")
        print("=" * 70)

        print(
            "TITLE:",
            title,
        )

        print(
            "SOURCE METADATA:",
            source or "Not provided",
        )

        print("")

        print(
            "SOURCE WILL NOT APPEAR IN VIDEO."
        )

        print(
            "SOURCE WILL NOT BE SPOKEN IN AUDIO."
        )

        print("")

        # ----------------------------------------------------
        # Build narration.
        # ----------------------------------------------------

        narration, measured_duration = (
            create_safe_narration(
                story,
                script,
            )
        )

        narration = remove_source_attribution(
            narration
        )

        if not narration:

            raise RuntimeError(
                "No valid narration was generated."
            )

        print("")
        print("=" * 70)
        print("SELECTED NARRATION")
        print("=" * 70)

        print(narration)

        print("")

        print(
            "NARRATION WORDS:",
            word_count(narration),
        )

        print(
            "MEASURED TTS DURATION:",
            round(
                measured_duration,
                2,
            ),
            "seconds",
        )

        # ----------------------------------------------------
        # Generate final narration.
        # ----------------------------------------------------

        narration_duration = generate_tts(
            narration,
            measured_duration,
        )

        if narration_duration <= 0:

            raise RuntimeError(
                "Narration duration is invalid."
            )

        if narration_duration > HARD_MAX_DURATION:

            raise RuntimeError(
                "Narration exceeded hard duration cap "
                "after final generation."
            )

        # ----------------------------------------------------
        # Prepare final audio.
        # ----------------------------------------------------

        final_audio = prepare_final_audio(
            FINAL_AUDIO
        )

        final_audio_duration = get_audio_duration(
            final_audio
        )

        if final_audio_duration <= 0:

            raise RuntimeError(
                "Final narration audio is invalid."
            )

        if final_audio_duration > HARD_MAX_DURATION:

            raise RuntimeError(
                "Final narration audio exceeds hard cap."
            )

        # ----------------------------------------------------
        # Images.
        #
        # V25 now resolves article URLs into actual images.
        # ----------------------------------------------------

        image_paths = download_real_images(
            story
        )

        if not image_paths:

            raise RuntimeError(
                "No valid real article photos were available."
            )

        image_paths = image_paths[
            :MAX_SCENES
        ]

        print("")
        print(
            "USING",
            len(image_paths),
            "REAL PHOTO(S) FOR VIDEO",
        )

        # ----------------------------------------------------
        # Create scenes.
        # ----------------------------------------------------

        frame_paths = create_scene_frames(
            image_paths,
            title,
        )

        if not frame_paths:

            raise RuntimeError(
                "No scene frames were created."
            )

        # ----------------------------------------------------
        # Create silent video.
        # ----------------------------------------------------

        silent_video = create_silent_video(
            frame_paths,
            final_audio_duration,
        )

        # ----------------------------------------------------
        # Mux narration.
        # ----------------------------------------------------

        final_video = mux_audio(
            silent_video,
            final_audio,
        )

        # ----------------------------------------------------
        # Compatibility files.
        # ----------------------------------------------------

        finalize_compatibility_files(
            image_paths
        )

        # ----------------------------------------------------
        # Verify final MP4.
        # ----------------------------------------------------

        verify_final_video()

        final_verified_duration = (
            get_audio_duration(
                FINAL_VIDEO
            )
        )

        print("")
        print("=" * 70)
        print(
            "RIFT VALLEY WATCH GENERATION SUCCESSFUL"
        )
        print("=" * 70)

        print("")
        print("FINAL MP4:")
        print(FINAL_VIDEO)

        print("")

        print(
            "REAL PHOTOS USED:",
            len(image_paths),
        )

        print(
            "NARRATION WORDS:",
            word_count(narration),
        )

        print(
            "NARRATION DURATION:",
            round(
                narration_duration,
                2,
            ),
            "seconds",
        )

        print(
            "VERIFIED FINAL DURATION:",
            round(
                final_verified_duration,
                2,
            ),
            "seconds",
        )

        print("")

        print(
            "SOURCE DISPLAY: NONE"
        )

        print(
            "SOURCE AUDIO: NONE"
        )

        print(
            "ARTICLE URL RESOLUTION: SUCCESS"
        )

        print(
            "FINAL OUTPUT IS WITHIN DURATION LIMIT."
        )

        print(
            "SUCCESS"
        )

        print("")

        return 0

    except KeyboardInterrupt:

        print("")
        print(
            "Generation interrupted by user."
        )

        return 130

    except Exception as exc:

        print("")
        print("=" * 70)
        print(
            "RIFT VALLEY WATCH GENERATION FAILED"
        )
        print("=" * 70)

        print("")

        print(
            "ERROR:",
            exc,
        )

        print("")

        import traceback

        traceback.print_exc()

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
