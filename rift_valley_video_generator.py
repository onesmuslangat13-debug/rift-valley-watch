from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import time

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V23_DURATION_HARD_CAP
#
# PURPOSE
# - One selected real news story
# - Multiple real article photos/scenes when available
# - No generic avatars/placeholders/logos
# - Professional 1080x1920 vertical news reel
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

# IMPORTANT:
# Keep this below 35 seconds so encoding/container overhead
# cannot push the final MP4 above the workflow limit.
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
            "image/avif,image/webp,image/apng,image/svg+xml,"
            "image/*,*/*;q=0.8"
        ),
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
    print("RVW_VIDEO_V23_DURATION_HARD_CAP")
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

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"www\.\S+", " ", text)

    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    text = re.sub(
        r"\b(source|photo|image|credit)\s*:\s*[^.]+\.?",
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

    text = re.sub(r"\s+", " ", text)

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
    ]

    for term in blocked:
        if term in s:
            return True

    return False


# ============================================================
# COLLECT TEXT FIELDS
# ============================================================

def collect_text_fields(obj, results=None):
    if results is None:
        results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

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

                    cleaned = normalize_sentence(value)

                    if cleaned:
                        results.append(cleaned)

            elif isinstance(value, (dict, list)):

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
        print(f"ERROR: {path} does not exist.")
        return None

    if path.stat().st_size == 0:
        print(f"ERROR: {path} is empty.")
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

    print("Looking for:", STORY_FILE)

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
            "Source:",
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

    print("Looking for:", SCRIPT_FILE)

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

    if not isinstance(story, dict):
        return "Rift Valley Watch"

    candidates = [
        story.get("title"),
        story.get("headline"),
        story.get("name"),
    ]

    nested = story.get("story")

    if isinstance(nested, dict):

        candidates.extend(
            [
                nested.get("title"),
                nested.get("headline"),
            ]
        )

    for item in candidates:

        value = clean_text(item)

        if value:
            return value

    return "Rift Valley Watch"


def get_story_source(story):

    if not isinstance(story, dict):
        return ""

    candidates = [
        story.get("source"),
        story.get("publisher"),
        story.get("site"),
        story.get("source_name"),
        story.get("publication"),
    ]

    nested = story.get("story")

    if isinstance(nested, dict):

        candidates.extend(
            [
                nested.get("source"),
                nested.get("publisher"),
                nested.get("site"),
            ]
        )

    for item in candidates:

        value = clean_text(item)

        if value:
            return value

    return ""


# ============================================================
# NARRATION BUILDING
# ============================================================

def split_into_sentences(text):

    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    results = []

    for part in parts:

        part = normalize_sentence(part)

        if not part:
            continue

        if is_bad_narration_sentence(part):
            continue

        results.append(part)

    return results


def build_narration(story, script):

    candidates = []

    if script is not None:

        candidates.extend(
            collect_text_fields(script)
        )

    if story is not None:

        candidates.extend(
            collect_text_fields(story)
        )

    cleaned = []

    seen = set()

    for text in candidates:

        sentences = split_into_sentences(
            text
        )

        for sentence in sentences:

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
            cleaned.append(sentence)

    if not cleaned:
        return ""

    combined = " ".join(cleaned)

    combined = re.sub(
        r"\s+",
        " ",
        combined,
    ).strip()

    return combined


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

        wc = word_count(sentence)

        if count + wc <= max_words:

            selected.append(sentence)
            count += wc

        else:

            remaining = max_words - count

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

    return " ".join(
        selected
    ).strip()


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

        unique.append(candidate)

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
        round(duration, 2),
        "seconds",
    )

    return duration


# ============================================================
# CREATE SAFE NARRATION
#
# IMPORTANT:
# This function now measures actual gTTS duration and keeps
# shortening the narration until it safely fits below 34.5 sec.
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

    # Sort candidates so the one closest to target
    # length is tested first.
    candidates.sort(
        key=lambda x: abs(
            word_count(x) - TARGET_WORDS
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

        # Perfect range.
        if (
            MIN_DURATION
            <= duration
            <= HARD_MAX_DURATION
        ):

            print("")
            print(
                "ACCEPTED NARRATION DURATION:",
                round(duration, 2),
                "seconds",
            )

            return (
                candidate,
                duration,
            )

    # --------------------------------------------------------
    # If none of the standard candidates fit, dynamically
    # shorten based on the measured TTS speed.
    # --------------------------------------------------------

    print("")
    print(
        "No standard narration candidate fit "
        "the duration limit."
    )

    if temp_candidates:

        # Use the shortest valid candidate as the base.
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

                if (
                    not candidate
                    or word_count(candidate)
                    < MIN_WORDS
                ):
                    continue

                test_file = (
                    AUDIO_DIR
                    / (
                        f"tts_dynamic_{index:02d}.mp3"
                    )
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
                    round(duration, 2),
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

    # --------------------------------------------------------
    # Final fallback:
    # Use the shortest measured narration if it is valid.
    # --------------------------------------------------------

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
            round(selected[1], 2),
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

    # --------------------------------------------------------
    # Safety check.
    # --------------------------------------------------------

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
        round(final_duration, 2),
        "seconds",
    )

    print(
        "NARRATION WORD COUNT:",
        word_count(text),
    )

    print("")

    return final_duration


# ============================================================
# IMAGE URL EXTRACTION
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
                    or "url" in key_lower
                ):

                    if value.startswith("http"):

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

    elif isinstance(obj, list):

        for item in obj:

            recursive_image_urls(
                item,
                results,
            )

    return results


def get_image_urls(story):

    urls = []

    if not isinstance(
        story,
        dict,
    ):

        return urls

    # Preferred explicit image_urls.
    explicit = story.get(
        "image_urls"
    )

    if isinstance(
        explicit,
        list,
    ):

        urls.extend(
            str(x)
            for x in explicit
            if (
                isinstance(x, str)
                and x.startswith("http")
            )
        )

    elif (
        isinstance(explicit, str)
        and explicit.startswith("http")
    ):

        urls.append(explicit)

    # Other common fields.
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

        value = story.get(key)

        if (
            isinstance(value, str)
            and value.startswith("http")
        ):

            urls.append(value)

        elif isinstance(
            value,
            list,
        ):

            for item in value:

                if (
                    isinstance(item, str)
                    and item.startswith("http")
                ):

                    urls.append(item)

                elif isinstance(
                    item,
                    dict,
                ):

                    for candidate in recursive_image_urls(
                        item
                    ):

                        urls.append(
                            candidate
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

    # Recursive fallback.
    urls.extend(
        recursive_image_urls(story)
    )

    # Deduplicate.
    final = []

    seen = set()

    for url in urls:

        url = url.strip()

        if not url:
            continue

        normalized = (
            url.lower()
            .split("?")[0]
        )

        if normalized in seen:
            continue

        seen.add(normalized)
        final.append(url)

    return final


# ============================================================
# IMAGE URL VALIDATION
# ============================================================

def image_url_is_bad(url):

    value = url.lower()

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

        if image_url_is_bad(url):

            print(
                "Rejected URL:",
                url,
            )

            return False

        response = SESSION.get(
            url,
            timeout=20,
            allow_redirects=True,
        )

        if response.status_code != 200:

            print(
                "HTTP error:",
                response.status_code,
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

        return False


# ============================================================
# IMAGE QUALITY CHECK
# ============================================================

def image_is_valid(path):

    try:

        with Image.open(path) as im:

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

            ratio = width / float(
                height
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

            # Reject very small square/icon-like images.
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
                for minimum, maximum
                in extrema
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

        with Image.open(path) as im:

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
        "Image URLs discovered:",
        len(urls),
    )

    if not urls:

        print(
            "ERROR: No image URLs found in selected story."
        )

        return []

    # Clean previous scene images.
    for old in SOURCE_DIR.glob(
        "story_image_*.jpg"
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

        print(url)

        temp_path = (
            SOURCE_DIR
            / (
                f"_candidate_{image_index}.jpg"
            )
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
            hashes.add(digest)

        final_path = (
            SOURCE_DIR
            / (
                f"story_image_"
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
            "ACCEPTED:",
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

    # Compatibility image.
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

    source_w, source_h = (
        image.size
    )

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
# ============================================================

def create_scene_frame(
    image_path,
    title,
    source,
    scene_number,
    total_scenes,
):

    image = Image.open(
        image_path
    ).convert("RGB")

    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

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

    # Photo shadow.
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

    source_font = load_font(
        24,
        bold=False,
    )

    source_clean = clean_text(
        source
    )

    if source_clean:

        source_text = (
            f"Source: {source_clean}"
        )

        draw.text(
            (
                75,
                panel_y
                + panel_height
                - 90,
            ),
            source_text,
            font=source_font,
            fill=MID_GREY,
        )

    # --------------------------------------------------------
    # Footer
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
    source,
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
            / (
                f"scene_{index:02d}.jpg"
            )
        )

        print(
            f"Creating scene "
            f"{index}/{total_scenes}:",
            image_path,
        )

        frame = create_scene_frame(
            image_path,
            title,
            source,
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

    # --------------------------------------------------------
    # HARD CAP
    #
    # Never allow the scene video to exceed the safe maximum.
    # --------------------------------------------------------

    target_duration = max(
        MIN_DURATION,
        min(
            HARD_MAX_DURATION,
            duration,
        ),
    )

    print(
        "Requested duration:",
        round(duration, 2),
        "seconds",
    )

    print(
        "Video target duration:",
        round(target_duration, 2),
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

        # Required by concat demuxer.
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

    # --------------------------------------------------------
    # Measure actual generated video.
    # --------------------------------------------------------

    actual_duration = get_audio_duration(
        silent_video
    )

    print(
        "Generated silent video duration:",
        round(actual_duration, 2),
        "seconds",
    )

    # If concat produces a slight timing excess,
    # explicitly trim it.
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
            round(actual_duration, 2),
            "seconds",
        )

    print(
        "Silent video:",
        silent_video,
    )

    return silent_video


# ============================================================
# PREPARE FINAL AUDIO
#
# This creates a final audio file whose duration is guaranteed
# not to exceed HARD_MAX_DURATION.
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
        round(duration, 2),
        "seconds",
    )

    # --------------------------------------------------------
    # Normally this should already be below the hard cap.
    # --------------------------------------------------------

    if duration <= HARD_MAX_DURATION:

        print(
            "Narration is already within hard limit."
        )

        return audio_file

    # --------------------------------------------------------
    # Absolute fallback: trim audio to hard cap.
    # This should rarely happen because create_safe_narration()
    # already controls the TTS length.
    # --------------------------------------------------------

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
        round(capped_duration, 2),
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

    # --------------------------------------------------------
    # Get both durations.
    # --------------------------------------------------------

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
        round(video_duration, 2),
        "seconds",
    )

    print(
        "Audio duration:",
        round(audio_duration, 2),
        "seconds",
    )

    # --------------------------------------------------------
    # Determine final duration.
    #
    # Never exceed HARD_MAX_DURATION.
    # Also never exceed either stream's duration.
    # --------------------------------------------------------

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
        round(final_duration, 2),
        "seconds",
    )

    # --------------------------------------------------------
    # Explicitly trim video and audio to identical duration.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Measure actual final duration.
    # --------------------------------------------------------

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
        round(actual_final_duration, 2),
        "seconds",
    )

    # --------------------------------------------------------
    # Emergency final hard-cap pass.
    #
    # This protects against unusual MP4 timestamp/container
    # behaviour where ffprobe duration can be slightly longer.
    # --------------------------------------------------------

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
            round(actual_final_duration, 2),
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
        round(final_duration, 3),
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

    # --------------------------------------------------------
    # Duration checks.
    #
    # The final file must actually be within the hard cap.
    # --------------------------------------------------------

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

    # Additional normal maximum check.
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

    # Scene/video temporary files.
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

    # Clean old TTS test files.
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
            "SOURCE:",
            source or "Not provided",
        )

        print("")

        # ----------------------------------------------------
        # Build narration candidates.
        # ----------------------------------------------------

        narration, measured_duration = (
            create_safe_narration(
                story,
                script,
            )
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
        # ----------------------------------------------------

        image_paths = download_real_images(
            story
        )

        if not image_paths:

            raise RuntimeError(
                "No valid real article photos were available."
            )

        # ----------------------------------------------------
        # Scene count.
        # ----------------------------------------------------

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
            source,
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

        # ----------------------------------------------------
        # Final status.
        # ----------------------------------------------------

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
