from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V21_REAL_PHOTO_AUDIO_FIXED
#
# PURPOSE
# - One selected real story
# - Multiple real article photos
# - Reject unrelated/placeholder images
# - No source/credit wording in narration
# - Longer narration
# - Stable TTS/audio timing
# - Vertical 1080x1920 reel
# ============================================================

VERSION = "RVW_VIDEO_V21_REAL_PHOTO_AUDIO_FIXED"

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
ASSETS_DIR = BASE_DIR / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ASSETS_DIR / "audio"
VIDEO_WORK_DIR = ASSETS_DIR / "video"

STORY_FILE = BASE_DIR / "selected_story.json"
SCRIPT_FILE = BASE_DIR / "selected_script.json"

FINAL_IMAGE = SOURCE_DIR / "story_image.jpg"
FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
FINAL_AUDIO = AUDIO_DIR / "narration.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MAX_SCENES = 4

MIN_REEL_DURATION = 18.0
TARGET_REEL_DURATION = 23.0
MAX_REEL_DURATION = 35.0

MIN_NARRATION_WORDS = 65
TARGET_NARRATION_WORDS = 95
MAX_NARRATION_WORDS = 125

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0 Safari/537.36"
)


# ============================================================
# IMAGE FILTER
# ============================================================

BAD_IMAGE_TERMS = [
    "avatar",
    "placeholder",
    "profile",
    "profile-picture",
    "profile_pic",
    "profilepic",
    "default-user",
    "default_user",
    "default-avatar",
    "default_avatar",
    "user-icon",
    "user_icon",
    "usericon",
    "logo",
    "logos",
    "icon",
    "icons",
    "favicon",
    "sprite",
    "thumbnail-placeholder",
    "loading",
    "spinner",
    "advert",
    "advertisement",
    "ads",
    "banner",
    "world-cup",
    "worldcup",
    "football",
    "soccer",
    "promo",
    "promotion",
    "placeholder-image",
    "placeholder_image",
    "no-image",
    "no_image",
    "noimage",
    "generic",
    "dummy",
    "wp-user",
    "author",
    "default",
]


# ============================================================
# DIRECTORY SETUP
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_print(text):
    try:
        print(str(text))
    except Exception:
        pass


def clean_spaces(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = text.replace("\t", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_text(text):
    """
    Remove HTML, URLs and source/credit attribution
    before text reaches the narration engine.
    """

    if not text:
        return ""

    text = str(text)

    # Remove HTML.
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove URLs.
    text = re.sub(
        r"https?://\S+|www\.\S+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove explicit attribution phrases.
    attribution_patterns = [
        r"\bsource\s*:\s*[^.?!]+[.?!]?",
        r"\bsources\s*:\s*[^.?!]+[.?!]?",
        r"\bimage\s+source\s*:\s*[^.?!]+[.?!]?",
        r"\bphoto\s+source\s*:\s*[^.?!]+[.?!]?",
        r"\bimage\s+credit\s*:\s*[^.?!]+[.?!]?",
        r"\bphoto\s+credit\s*:\s*[^.?!]+[.?!]?",
        r"\bphoto\s+by\s*:\s*[^.?!]+[.?!]?",
        r"\bphoto\s+by\s+[^.?!]+[.?!]?",
        r"\bcredit\s*:\s*[^.?!]+[.?!]?",
        r"\bcourtesy\s+of\s+[^.?!]+[.?!]?",
        r"\bfile\s+photo\s*:\s*[^.?!]+[.?!]?",
        r"\breported\s+by\s+[^.?!]+[.?!]?",
        r"\breport\s+by\s+[^.?!]+[.?!]?",
        r"\bvia\s+[^.?!]+[.?!]?",
    ]

    for pattern in attribution_patterns:
        text = re.sub(
            pattern,
            " ",
            text,
            flags=re.IGNORECASE,
        )

    # Remove common publisher/source labels.
    text = re.sub(
        r"\b(source|credit|photo|image)\s*[-|]\s*"
        r"(citizen|nation|the star|kbc|people daily|standard|"
        r"ntv|tuko|kenyans\.co\.ke|county government)[^.!?]*",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove bracketed source labels.
    text = re.sub(
        r"\[\s*(source|credit|photo|image)[^\]]*\]",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Remove source/credit at beginning.
    text = re.sub(
        r"^(source|credit|photo credit|image credit)"
        r"\s*[:\-|]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = clean_spaces(text)

    text = re.sub(
        r"\s+([,.!?])",
        r"\1",
        text,
    )

    return text.strip()


def sentence_split(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    result = []

    for part in parts:
        part = clean_spaces(part)

        if part:
            result.append(part)

    return result


def word_count(text):
    if not text:
        return 0

    return len(
        re.findall(
            r"\b[\w’'-]+\b",
            text,
            flags=re.UNICODE,
        )
    )


# ============================================================
# JSON
# ============================================================

def load_json_file(path):
    if not path.exists():
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as exc:
        safe_print(
            f"WARNING: Could not read "
            f"{path.name}: {exc}"
        )

        return {}


def load_story():
    story = load_json_file(
        STORY_FILE
    )

    if not story:
        safe_print(
            "ERROR: selected_story.json "
            "is empty or missing."
        )

        return {}

    return story


def load_script():
    return load_json_file(
        SCRIPT_FILE
    )


# ============================================================
# TEXT COLLECTION
# ============================================================

def collect_text_fields(story, script):

    candidates = []

    field_names = [
        "narration",
        "script",
        "voiceover",
        "voice_over",
        "summary",
        "description",
        "body",
        "content",
        "article_text",
        "story",
        "text",
        "excerpt",
        "short_summary",
    ]

    for source in [script, story]:

        if not isinstance(source, dict):
            continue

        for field in field_names:

            value = source.get(field)

            if isinstance(value, str):

                cleaned = clean_text(
                    value
                )

                if cleaned:
                    candidates.append(
                        cleaned
                    )

    nested = story.get("story")

    if isinstance(nested, dict):

        for field in field_names:

            value = nested.get(field)

            if isinstance(value, str):

                cleaned = clean_text(
                    value
                )

                if cleaned:
                    candidates.append(
                        cleaned
                    )

    result = []
    seen = set()

    for item in candidates:

        key = re.sub(
            r"\W+",
            " ",
            item.lower(),
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


# ============================================================
# NARRATION FILTER
# ============================================================

def is_bad_narration_sentence(sentence):

    lowered = sentence.lower()

    blocked = [
        "source:",
        "sources:",
        "image source",
        "photo source",
        "image credit",
        "photo credit",
        "credit:",
        "courtesy of",
        "file photo",
        "reported by",
        "report by",
        "via ",
        "www.",
        "http://",
        "https://",
    ]

    for term in blocked:

        if term in lowered:
            return True

    return False


def remove_bad_sentences(sentences):

    result = []

    for sentence in sentences:

        sentence = clean_text(
            sentence
        )

        if not sentence:
            continue

        if is_bad_narration_sentence(
            sentence
        ):
            continue

        if word_count(sentence) < 3:
            continue

        result.append(sentence)

    return result


# ============================================================
# BUILD NARRATION
# ============================================================

def build_narration(story, script):

    fields = collect_text_fields(
        story,
        script,
    )

    sentences = []

    for field in fields:

        for sentence in sentence_split(
            field
        ):

            if is_bad_narration_sentence(
                sentence
            ):
                continue

            sentence = clean_text(
                sentence
            )

            if sentence:
                sentences.append(
                    sentence
                )

    # De-duplicate.
    final_sentences = []

    seen = set()

    for sentence in sentences:

        key = re.sub(
            r"\W+",
            " ",
            sentence.lower(),
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        final_sentences.append(
            sentence
        )

    narration_parts = []

    total_words = 0

    for sentence in final_sentences:

        sentence_words = word_count(
            sentence
        )

        if sentence_words <= 0:
            continue

        if (
            total_words + sentence_words
            <= MAX_NARRATION_WORDS
        ):

            narration_parts.append(
                sentence
            )

            total_words += sentence_words

        else:

            remaining = (
                MAX_NARRATION_WORDS
                - total_words
            )

            if remaining >= 8:

                words = sentence.split()

                partial = " ".join(
                    words[:remaining]
                )

                partial = clean_text(
                    partial
                )

                if partial:

                    if not partial.endswith(
                        (".", "!", "?")
                    ):
                        partial += "."

                    narration_parts.append(
                        partial
                    )

            break

    narration = clean_text(
        " ".join(
            narration_parts
        )
    )

    # Fallback if extracted text is too short.
    if word_count(narration) < MIN_NARRATION_WORDS:

        headline = clean_text(
            story.get("headline")
            or story.get("title")
            or story.get("name")
            or ""
        )

        summary = clean_text(
            story.get("summary")
            or story.get("description")
            or story.get("excerpt")
            or ""
        )

        location = clean_text(
            story.get("county")
            or story.get("location")
            or ""
        )

        fallback_parts = []

        if headline:
            fallback_parts.append(
                headline
            )

        if summary:
            fallback_parts.append(
                summary
            )

        if location:
            if location.lower() not in (
                narration.lower()
            ):
                fallback_parts.append(
                    f"The development is being "
                    f"closely watched in {location}."
                )

        fallback = clean_text(
            " ".join(
                fallback_parts
            )
        )

        if word_count(fallback) > word_count(
            narration
        ):
            narration = fallback

    return clean_text(narration)


# ============================================================
# SHORTEN NARRATION
# ============================================================

def shorten_narration(
    text,
    max_words,
):

    sentences = remove_bad_sentences(
        sentence_split(text)
    )

    if not sentences:
        return ""

    result = []
    total = 0

    for sentence in sentences:

        count = word_count(
            sentence
        )

        if total + count <= max_words:

            result.append(
                sentence
            )

            total += count

        else:

            remaining = (
                max_words - total
            )

            if remaining >= 8:

                words = sentence.split()

                partial = " ".join(
                    words[:remaining]
                )

                partial = clean_text(
                    partial
                )

                if partial:

                    if not partial.endswith(
                        (".", "!", "?")
                    ):
                        partial += "."

                    result.append(
                        partial
                    )

            break

    return clean_text(
        " ".join(result)
    )


# ============================================================
# AUDIO DURATION
# ============================================================

def get_audio_duration(
    audio_file
):

    if not audio_file.exists():
        return 0.0

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_file),
    ]

    try:

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        value = result.stdout.strip()

        if value:
            return float(value)

    except Exception as exc:

        safe_print(
            f"WARNING: Could not read "
            f"audio duration: {exc}"
        )

    return 0.0


# ============================================================
# TTS
# ============================================================

def generate_tts(
    text,
    output_file,
):

    text = clean_text(text)

    if not text:
        return False

    try:

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if output_file.exists():
            output_file.unlink()

        safe_print("")
        safe_print(
            "=" * 60
        )
        safe_print(
            "FINAL NARRATION SENT TO TTS"
        )
        safe_print(
            "=" * 60
        )
        safe_print(text)
        safe_print(
            "=" * 60
        )
        safe_print(
            f"WORD COUNT: {word_count(text)}"
        )
        safe_print(
            "=" * 60
        )
        safe_print("")

        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(output_file)
        )

        return output_file.exists()

    except Exception as exc:

        safe_print(
            f"ERROR: TTS generation "
            f"failed: {exc}"
        )

        return False


# ============================================================
# SAFE NARRATION
# ============================================================

def create_safe_narration(
    story,
    script,
):

    base = build_narration(
        story,
        script,
    )

    if not base:

        safe_print(
            "ERROR: No narration text "
            "could be created."
        )

        return "", 0.0

    base = clean_text(base)

    candidates = []

    base_words = word_count(
        base
    )

    target_sizes = [
        min(
            MAX_NARRATION_WORDS,
            base_words,
        ),
        120,
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
        65,
    ]

    seen_sizes = set()

    for size in target_sizes:

        if size in seen_sizes:
            continue

        seen_sizes.add(size)

        candidate = shorten_narration(
            base,
            size,
        )

        candidate = clean_text(
            candidate
        )

        if not candidate:
            continue

        if candidate in candidates:
            continue

        candidates.append(
            candidate
        )

    best_text = ""
    best_duration = 0.0

    for index, candidate in enumerate(
        candidates
    ):

        temp_audio = (
            AUDIO_DIR
            / f"tts_test_{index}.mp3"
        )

        if not generate_tts(
            candidate,
            temp_audio,
        ):
            continue

        duration = get_audio_duration(
            temp_audio
        )

        safe_print(
            f"TTS TEST {index + 1}: "
            f"{word_count(candidate)} words / "
            f"{duration:.2f} seconds"
        )

        if duration <= 0:
            continue

        if duration > MAX_REEL_DURATION:
            continue

        if duration > best_duration:

            best_duration = duration
            best_text = candidate

        if (
            duration >= TARGET_REEL_DURATION
            and duration <= MAX_REEL_DURATION
        ):

            shutil.copy2(
                temp_audio,
                FINAL_AUDIO,
            )

            return (
                candidate,
                duration,
            )

    # Fallback to longest successful narration.
    if best_text and best_duration > 0:

        final_temp = (
            AUDIO_DIR
            / "tts_best.mp3"
        )

        if generate_tts(
            best_text,
            final_temp,
        ):

            shutil.copy2(
                final_temp,
                FINAL_AUDIO,
            )

            return (
                best_text,
                best_duration,
            )

    return "", 0.0


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def get_image_urls(story):

    urls = []

    if not isinstance(
        story,
        dict,
    ):
        return urls

    possible_fields = [
        "image_urls",
        "images",
        "image_url",
        "image",
        "photo",
        "photos",
        "article_images",
        "media",
    ]

    for field in possible_fields:

        value = story.get(field)

        if isinstance(value, str):

            if value.startswith("http"):
                urls.append(value)

        elif isinstance(value, list):

            for item in value:

                if isinstance(item, str):

                    if item.startswith(
                        "http"
                    ):
                        urls.append(item)

                elif isinstance(item, dict):

                    for key in [
                        "url",
                        "src",
                        "image_url",
                        "original",
                    ]:

                        candidate = item.get(
                            key
                        )

                        if (
                            isinstance(
                                candidate,
                                str,
                            )
                            and candidate.startswith(
                                "http"
                            )
                        ):
                            urls.append(
                                candidate
                            )

        elif isinstance(value, dict):

            for key in [
                "url",
                "src",
                "image_url",
                "original",
            ]:

                candidate = value.get(
                    key
                )

                if (
                    isinstance(
                        candidate,
                        str,
                    )
                    and candidate.startswith(
                        "http"
                    )
                ):
                    urls.append(
                        candidate
                    )

    # Nested story object.
    nested = story.get(
        "story"
    )

    if isinstance(
        nested,
        dict,
    ):

        for field in possible_fields:

            value = nested.get(
                field
            )

            if isinstance(
                value,
                str,
            ):

                if value.startswith(
                    "http"
                ):
                    urls.append(value)

            elif isinstance(
                value,
                list,
            ):

                for item in value:

                    if isinstance(
                        item,
                        str,
                    ):

                        if item.startswith(
                            "http"
                        ):
                            urls.append(
                                item
                            )

                    elif isinstance(
                        item,
                        dict,
                    ):

                        candidate = (
                            item.get("url")
                            or item.get("src")
                            or item.get("image_url")
                            or item.get("original")
                        )

                        if (
                            isinstance(
                                candidate,
                                str,
                            )
                            and candidate.startswith(
                                "http"
                            )
                        ):
                            urls.append(
                                candidate
                            )

    # Deduplicate.
    result = []
    seen = set()

    for url in urls:

        url = url.strip()

        if not url:
            continue

        key = url.lower().split("?")[0]

        if key in seen:
            continue

        seen.add(key)

        result.append(url)

    return result


def image_url_looks_bad(url):

    lowered = url.lower()

    for term in BAD_IMAGE_TERMS:

        if term in lowered:
            return True

    return False


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    url,
    destination,
):

    if image_url_looks_bad(
        url
    ):

        safe_print(
            f"REJECTED IMAGE URL: {url}"
        )

        return False

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "image/avif,image/webp,"
            "image/apng,image/jpeg,"
            "image/png,*/*"
        ),
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
            .lower()
        )

        content = response.content

        if len(content) < 10000:
            return False

        if (
            "text/html" in content_type
            or content[:20]
            .lower()
            .startswith(
                b"<!doctype"
            )
            or content[:20]
            .lower()
            .startswith(
                b"<html"
            )
        ):
            return False

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(
            destination,
            "wb",
        ) as f:
            f.write(content)

        # First validation.
        with Image.open(
            destination
        ) as im:
            im.verify()

        # Second validation.
        with Image.open(
            destination
        ) as im:

            width, height = im.size

            if width < 350:
                return False

            if height < 250:
                return False

            area = width * height

            if area < 150000:
                return False

            ratio = width / float(
                height
            )

            # Extremely wide banner.
            if ratio > 4.0:
                return False

            # Extremely tall profile graphic.
            if ratio < 0.35:
                return False

            # Small square icon.
            if (
                abs(ratio - 1.0) < 0.03
                and width < 700
            ):
                return False

            # Basic blank-image detection.
            rgb = im.convert(
                "RGB"
            )

            small = rgb.resize(
                (32, 32)
            )

            pixels = list(
                small.getdata()
            )

            brightness = []

            for r, g, b in pixels:

                brightness.append(
                    (r + g + b) / 3
                )

            if brightness:

                average = (
                    sum(brightness)
                    / len(brightness)
                )

                variance = (
                    sum(
                        (x - average) ** 2
                        for x in brightness
                    )
                    / len(brightness)
                )

                if variance < 8:
                    return False

        return True

    except Exception as exc:

        safe_print(
            f"Image download failed: "
            f"{exc}"
        )

        try:

            if destination.exists():
                destination.unlink()

        except Exception:
            pass

        return False


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(path):

    try:

        with Image.open(
            path
        ) as im:

            im = im.convert(
                "RGB"
            )

            im.thumbnail(
                (96, 96)
            )

            return hashlib.md5(
                im.tobytes()
            ).hexdigest()

    except Exception:
        return ""


# ============================================================
# DOWNLOAD STORY IMAGES
# ============================================================

def download_story_images(
    story
):

    # Remove old numbered scene images.
    for path in SOURCE_DIR.glob(
        "story_image_*.jpg"
    ):

        try:
            path.unlink()
        except Exception:
            pass

    image_urls = get_image_urls(
        story
    )

    safe_print("")
    safe_print(
        "=" * 60
    )
    safe_print(
        f"IMAGE URLS FOUND: "
        f"{len(image_urls)}"
    )
    safe_print(
        "=" * 60
    )

    for index, url in enumerate(
        image_urls,
        start=1,
    ):

        safe_print(
            f"{index}. {url}"
        )

    safe_print(
        "=" * 60
    )

    downloaded = []
    hashes = set()

    for url in image_urls:

        if len(downloaded) >= MAX_SCENES:
            break

        temp_name = (
            f"story_image_"
            f"{len(downloaded) + 1}.jpg"
        )

        destination = (
            SOURCE_DIR
            / temp_name
        )

        safe_print(
            f"TRYING PHOTO: {url}"
        )

        if not download_image(
            url,
            destination,
        ):

            safe_print(
                "  -> rejected"
            )

            continue

        h = image_hash(
            destination
        )

        if h and h in hashes:

            safe_print(
                "  -> duplicate rejected"
            )

            try:
                destination.unlink()
            except Exception:
                pass

            continue

        if h:
            hashes.add(h)

        downloaded.append(
            destination
        )

        safe_print(
            f"  -> ACCEPTED: "
            f"{destination.name}"
        )

    # Compatibility path for older code.
    if downloaded:

        try:

            shutil.copy2(
                downloaded[0],
                FINAL_IMAGE,
            )

        except Exception as exc:

            safe_print(
                "WARNING: Could not create "
                f"compatibility image: {exc}"
            )

    safe_print("")
    safe_print(
        f"VALID ARTICLE PHOTOS: "
        f"{len(downloaded)}"
    )
    safe_print("")

    return downloaded


# ============================================================
# FONT
# ============================================================

def find_font(
    size,
    bold=False,
):

    candidates = []

    if bold:

        candidates.extend([
            "/usr/share/fonts/truetype/"
            "dejavu/DejaVuSans-Bold.ttf",

            "/usr/share/fonts/truetype/"
            "liberation2/"
            "LiberationSans-Bold.ttf",
        ])

    else:

        candidates.extend([
            "/usr/share/fonts/truetype/"
            "dejavu/DejaVuSans.ttf",

            "/usr/share/fonts/truetype/"
            "liberation2/"
            "LiberationSans-Regular.ttf",
        ])

    candidates.append(
        "/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans.ttf"
    )

    for candidate in candidates:

        if Path(candidate).exists():

            try:

                return ImageFont.truetype(
                    candidate,
                    size,
                )

            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# TEXT WRAP
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
            bbox[2] - bbox[0]
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


# ============================================================
# CROP COVER
# ============================================================

def crop_cover(
    image,
    width,
    height,
):

    image = image.convert(
        "RGB"
    )

    src_w, src_h = image.size

    target_ratio = (
        width / float(height)
    )

    src_ratio = (
        src_w / float(src_h)
    )

    if src_ratio > target_ratio:

        new_w = int(
            src_h * target_ratio
        )

        left = (
            src_w - new_w
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_w,
                src_h,
            )
        )

    else:

        new_h = int(
            src_w / target_ratio
        )

        top = (
            src_h - new_h
        ) // 2

        image = image.crop(
            (
                0,
                top,
                src_w,
                top + new_h,
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
# SCENE FRAME
# ============================================================

def make_scene_frame(
    image_path,
    headline,
    scene_index,
    output_path,
):

    with Image.open(
        image_path
    ) as source:

        source = source.convert(
            "RGB"
        )

        # Background.
        background = crop_cover(
            source,
            WIDTH,
            HEIGHT,
        )

        background = background.filter(
            ImageFilter.GaussianBlur(
                radius=18
            )
        )

        overlay = Image.new(
            "RGBA",
            (
                WIDTH,
                HEIGHT,
            ),
            (
                0,
                0,
                0,
                95,
            ),
        )

        background = (
            Image.alpha_composite(
                background.convert(
                    "RGBA"
                ),
                overlay,
            )
        )

        canvas = background.convert(
            "RGB"
        )

        draw = ImageDraw.Draw(
            canvas
        )

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        header_h = 165

        draw.rectangle(
            (
                0,
                0,
                WIDTH,
                header_h,
            ),
            fill=(
                9,
                18,
                38,
            ),
        )

        logo_font = find_font(
            50,
            bold=True,
        )

        small_font = find_font(
            25,
            bold=True,
        )

        draw.text(
            (
                45,
                35,
            ),
            "RIFT VALLEY WATCH",
            font=logo_font,
            fill=(
                255,
                255,
                255,
            ),
        )

        draw.text(
            (
                48,
                103,
            ),
            "REGIONAL NEWS • CURRENT AFFAIRS",
            font=small_font,
            fill=(
                200,
                210,
                225,
            ),
        )

        # ----------------------------------------------------
        # MAIN PHOTO
        # ----------------------------------------------------

        photo_top = 185
        photo_bottom = 1250

        photo_width = 930

        photo_height = (
            photo_bottom
            - photo_top
        )

        photo = crop_cover(
            source,
            photo_width,
            photo_height,
        )

        photo_x = (
            WIDTH
            - photo_width
        ) // 2

        # Shadow.
        shadow = Image.new(
            "RGBA",
            (
                photo_width + 30,
                photo_height + 30,
            ),
            (
                0,
                0,
                0,
                0,
            ),
        )

        shadow_draw = ImageDraw.Draw(
            shadow
        )

        shadow_draw.rounded_rectangle(
            (
                10,
                10,
                photo_width + 20,
                photo_height + 20,
            ),
            radius=22,
            fill=(
                0,
                0,
                0,
                150,
            ),
        )

        canvas.paste(
            shadow,
            (
                photo_x - 5,
                photo_top - 5,
            ),
            shadow,
        )

        canvas.paste(
            photo,
            (
                photo_x,
                photo_top,
            ),
        )

        # ----------------------------------------------------
        # SCENE LABEL
        # ----------------------------------------------------

        scene_font = find_font(
            25,
            bold=True,
        )

        label = (
            "RIFT VALLEY WATCH  •  "
            f"SCENE {scene_index}"
        )

        draw.rounded_rectangle(
            (
                48,
                1210,
                390,
                1270,
            ),
            radius=12,
            fill=(
                9,
                18,
                38,
            ),
        )

        draw.text(
            (
                70,
                1227,
            ),
            label,
            font=scene_font,
            fill=(
                255,
                255,
                255,
            ),
        )

        # ----------------------------------------------------
        # HEADLINE
        # ----------------------------------------------------

        panel_top = 1300
        panel_bottom = 1850

        draw.rounded_rectangle(
            (
                35,
                panel_top,
                WIDTH - 35,
                panel_bottom,
            ),
            radius=25,
            fill=(
                8,
                17,
                35,
            ),
        )

        headline_font = find_font(
            56,
            bold=True,
        )

        headline = clean_text(
            headline
        )

        lines = wrap_text(
            draw,
            headline,
            headline_font,
            WIDTH - 120,
        )

        max_lines = 5

        if len(lines) > max_lines:

            lines = lines[
                :max_lines
            ]

            last = lines[-1]

            if len(last) > 3:

                lines[-1] = (
                    last.rstrip(
                        "., "
                    )
                    + "..."
                )

        y = (
            panel_top
            + 55
        )

        for line in lines:

            draw.text(
                (
                    65,
                    y,
                ),
                line,
                font=headline_font,
                fill=(
                    255,
                    255,
                    255,
                ),
            )

            bbox = draw.textbbox(
                (
                    0,
                    0,
                ),
                line,
                font=headline_font,
            )

            line_height = (
                bbox[3]
                - bbox[1]
            )

            y += (
                line_height
                + 18
            )

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------

        footer_font = find_font(
            23,
            bold=True,
        )

        draw.text(
            (
                55,
                1875,
            ),
            "FOLLOW RIFT VALLEY WATCH FOR MORE UPDATES",
            font=footer_font,
            fill=(
                210,
                220,
                235,
            ),
        )

        canvas.save(
            output_path,
            quality=95,
        )


# ============================================================
# PREPARE SCENES
# ============================================================

def prepare_scene_frames(
    images,
    headline,
    duration,
):

    if not images:
        return []

    selected = images[
        :MAX_SCENES
    ]

    scene_count = len(
        selected
    )

    if duration <= 0:
        duration = TARGET_REEL_DURATION

    scene_duration = (
        duration
        / float(scene_count)
    )

    frames = []

    for index, image_path in enumerate(
        selected,
        start=1,
    ):

        frame_path = (
            VIDEO_WORK_DIR
            / f"scene_{index:02d}.jpg"
        )

        make_scene_frame(
            image_path,
            headline,
            index,
            frame_path,
        )

        frames.append(
            (
                frame_path,
                scene_duration,
            )
        )

    return frames


# ============================================================
# CREATE SILENT VIDEO
# ============================================================

def create_video_from_scenes(
    scenes,
    output_file,
):

    if not scenes:
        return False

    concat_file = (
        VIDEO_WORK_DIR
        / "concat.txt"
    )

    try:

        with open(
            concat_file,
            "w",
            encoding="utf-8",
        ) as f:

            for frame_path, duration in scenes:

                safe_path = (
                    frame_path
                    .resolve()
                    .as_posix()
                )

                safe_path = safe_path.replace(
                    "'",
                    "'\\''",
                )

                f.write(
                    f"file '{safe_path}'\n"
                )

                f.write(
                    f"duration {duration:.4f}\n"
                )

            # Repeat final frame.
            final_path = (
                scenes[-1][0]
                .resolve()
                .as_posix()
                .replace(
                    "'",
                    "'\\''",
                )
            )

            f.write(
                f"file '{final_path}'\n"
            )

        cmd = [
            "ffmpeg",
            "-y",

            "-f",
            "concat",

            "-safe",
            "0",

            "-i",
            str(concat_file),

            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:"
                "(ow-iw)/2:(oh-ih)/2"
            ),

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

            str(output_file),
        ]

        safe_print("")
        safe_print(
            "CREATING VIDEO..."
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:

            safe_print(
                "FFMPEG VIDEO ERROR:"
            )

            safe_print(
                result.stderr[-5000:]
            )

            return False

        return output_file.exists()

    except Exception as exc:

        safe_print(
            f"ERROR creating video: "
            f"{exc}"
        )

        return False


# ============================================================
# COMBINE AUDIO
# ============================================================

def combine_audio(
    video_file,
    audio_file,
    output_file,
    duration,
):

    if not video_file.exists():

        safe_print(
            "ERROR: Video file does not exist."
        )

        return False

    if not audio_file.exists():

        safe_print(
            "ERROR: Audio file does not exist."
        )

        return False

    actual_audio_duration = (
        get_audio_duration(
            audio_file
        )
    )

    if actual_audio_duration <= 0:

        safe_print(
            "ERROR: Audio duration is zero."
        )

        return False

    # Actual audio controls final length.
    duration = actual_audio_duration

    safe_print(
        f"FINAL AUDIO DURATION: "
        f"{duration:.2f} seconds"
    )

    duration_arg = (
        f"{duration + 0.15:.3f}"
    )

    cmd = [
        "ffmpeg",
        "-y",

        "-i",
        str(video_file),

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

        "-t",
        duration_arg,

        "-movflags",
        "+faststart",

        str(output_file),
    ]

    safe_print("")
    safe_print(
        "COMBINING VIDEO + NARRATION..."
    )

    try:

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:

            safe_print(
                "FFMPEG AUDIO ERROR:"
            )

            safe_print(
                result.stderr[-7000:]
            )

            return False

        return output_file.exists()

    except Exception as exc:

        safe_print(
            f"ERROR combining audio: "
            f"{exc}"
        )

        return False


# ============================================================
# VERIFY
# ============================================================

def verify_final_video(
    path
):

    if not path.exists():
        return False

    if path.stat().st_size < 50000:
        return False

    cmd = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "format=duration",

        "-show_entries",
        "stream=codec_type",

        "-of",
        "default=noprint_wrappers=1",

        str(path),
    ]

    try:

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        safe_print("")
        safe_print(
            "=" * 60
        )
        safe_print(
            "FINAL VIDEO VERIFICATION"
        )
        safe_print(
            "=" * 60
        )

        safe_print(
            result.stdout
        )

        safe_print(
            "=" * 60
        )

        return (
            result.returncode == 0
        )

    except Exception as exc:

        safe_print(
            f"WARNING: Verification "
            f"failed: {exc}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    prepare_directories()

    safe_print("")
    safe_print(
        "=" * 70
    )
    safe_print(
        "RIFT VALLEY WATCH VIDEO GENERATOR"
    )
    safe_print(
        VERSION
    )
    safe_print(
        "=" * 70
    )
    safe_print("")

    # --------------------------------------------------------
    # LOAD STORY
    # --------------------------------------------------------

    story = load_story()

    if not story:

        safe_print(
            "ERROR: selected_story.json "
            "was not loaded."
        )

        sys.exit(1)

    script = load_script()

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    headline = clean_text(
        story.get("headline")
        or story.get("title")
        or story.get("name")
        or "Rift Valley Latest News"
    )

    safe_print(
        f"HEADLINE: {headline}"
    )

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration, audio_duration = (
        create_safe_narration(
            story,
            script,
        )
    )

    if not narration:

        safe_print(
            "ERROR: Could not create narration."
        )

        sys.exit(1)

    if audio_duration <= 0:

        safe_print(
            "ERROR: Narration duration invalid."
        )

        sys.exit(1)

    safe_print("")
    safe_print(
        "=" * 60
    )
    safe_print(
        "SELECTED FINAL NARRATION"
    )
    safe_print(
        "=" * 60
    )
    safe_print(narration)
    safe_print(
        "=" * 60
    )
    safe_print(
        f"WORDS: {word_count(narration)}"
    )
    safe_print(
        f"AUDIO: {audio_duration:.2f}s"
    )
    safe_print(
        "=" * 60
    )
    safe_print("")

    # --------------------------------------------------------
    # DOWNLOAD MULTIPLE PHOTOS
    # --------------------------------------------------------

    images = download_story_images(
        story
    )

    if not images:

        safe_print("")
        safe_print(
            "ERROR: No valid article photos "
            "were found."
        )
        safe_print(
            "The generator will NOT use a "
            "random placeholder or unrelated graphic."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # PREPARE SCENES
    # --------------------------------------------------------

    scenes = prepare_scene_frames(
        images,
        headline,
        audio_duration,
    )

    if not scenes:

        safe_print(
            "ERROR: Could not prepare scenes."
        )

        sys.exit(1)

    safe_print("")
    safe_print(
        f"SCENES CREATED: {len(scenes)}"
    )

    for frame, duration in scenes:

        safe_print(
            f"  {frame.name} = "
            f"{duration:.2f}s"
        )

    # --------------------------------------------------------
    # SILENT VIDEO
    # --------------------------------------------------------

    silent_video = (
        VIDEO_WORK_DIR
        / "silent_reel.mp4"
    )

    if silent_video.exists():

        try:
            silent_video.unlink()
        except Exception:
            pass

    if not create_video_from_scenes(
        scenes,
        silent_video,
    ):

        safe_print(
            "ERROR: Silent video "
            "creation failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # FINAL VIDEO
    # --------------------------------------------------------

    if FINAL_VIDEO.exists():

        try:
            FINAL_VIDEO.unlink()
        except Exception:
            pass

    if not combine_audio(
        silent_video,
        FINAL_AUDIO,
        FINAL_VIDEO,
        audio_duration,
    ):

        safe_print(
            "ERROR: Final video "
            "creation failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    if not verify_final_video(
        FINAL_VIDEO
    ):

        safe_print(
            "ERROR: Final video "
            "verification failed."
        )

        sys.exit(1)

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    safe_print("")
    safe_print(
        "=" * 70
    )
    safe_print(
        "SUCCESS"
    )
    safe_print(
        "=" * 70
    )

    safe_print(
        f"FINAL VIDEO: {FINAL_VIDEO}"
    )

    safe_print(
        f"FINAL AUDIO: {FINAL_AUDIO}"
    )

    safe_print(
        f"PHOTOS USED: {len(images)}"
    )

    safe_print(
        f"NARRATION WORDS: "
        f"{word_count(narration)}"
    )

    safe_print(
        f"NARRATION DURATION: "
        f"{audio_duration:.2f}s"
    )

    safe_print(
        "=" * 70
    )


if __name__ == "__main__":
    main()
