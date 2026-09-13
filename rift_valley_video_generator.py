from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import math

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V16_MULTI_REAL_PHOTOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
ASSET_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = ASSET_DIR / "story_image.jpg"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

TEMP_VIDEO = WORK_DIR / "multi_scene_video.mp4"
OVERLAY_FILE = WORK_DIR / "overlay.png"
PREPARED_IMAGE = WORK_DIR / "prepared_image.jpg"

AUDIO_FILE = AUDIO_DIR / "narration.mp3"
TEMP_AUDIO = AUDIO_DIR / "narration_temp.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_DURATION = 15
MAX_DURATION = 60

MIN_NARRATION_WORDS = 80
MAX_NARRATION_WORDS = 145

# Number of different real article photos to use when available.
MAX_REAL_PHOTOS = 5

# Minimum number of photos/scenes desired.
MIN_REAL_PHOTOS = 2

REQUEST_TIMEOUT = 25
IMAGE_TIMEOUT = 25
MAX_IMAGE_BYTES = 12 * 1024 * 1024

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[RIFT VALLEY WATCH] {message}",
        flush=True
    )


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():

    for directory in [
        OUTPUT_DIR,
        DATA_DIR,
        ASSET_DIR,
        WORK_DIR,
        AUDIO_DIR,
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True
        )

    log(f"BASE DIR: {BASE_DIR}")
    log(f"AUDIO DIR: {AUDIO_DIR}")
    log(f"AUDIO FILE: {AUDIO_FILE}")


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
    }
)


# ============================================================
# PUBLISHER NAMES
# ============================================================

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


# ============================================================
# TEXT CLEANING
# ============================================================

def remove_source_language(text):

    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"https?://\S+|www\.\S+",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bAdvertisement\b",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bAdvert\b",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\[[^\]]*\]",
        "",
        text
    )

    for source in SOURCE_NAMES:

        text = re.sub(
            rf"\b{re.escape(source)}\b",
            "",
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(
        r"\bas reported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\breported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text
    )

    return text.strip()


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):

    if not title:
        return "Latest Rift Valley Update"

    title = str(title)

    title = re.sub(
        r"\s*[\|\-–—:]\s*(KBC Digital|KBC News|KBC|"
        r"Citizen Digital|Citizen|Daily Nation|Nation Africa|"
        r"The Star|People Daily|The Standard|Standard Media|"
        r"Capital News|NTV Kenya|NTV|TV47|Tuko).*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r"\[[^\]]*\]",
        "",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


# ============================================================
# JSON
# ============================================================

def load_json(path):

    if not path.exists():
        return {}

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as exc:

        log(
            f"WARNING: Could not read {path}: {exc}"
        )

        return {}


def load_story():

    story = load_json(
        STORY_FILE
    )

    if not story:

        raise RuntimeError(
            f"Selected story file not found or empty: {STORY_FILE}"
        )

    return story


def load_script():

    script = load_json(
        SCRIPT_FILE
    )

    if not script:

        log(
            "WARNING: selected_script.json is missing or empty."
        )

    return script


# ============================================================
# SENTENCE PROCESSING
# ============================================================

def normalize_sentences(text):

    if not text:
        return []

    text = remove_source_language(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    cleaned = []

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        if len(sentence.split()) < 4:
            continue

        cleaned.append(
            sentence
        )

    return cleaned


def sentence_similarity(a, b):

    a_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            a.lower()
        )
    )

    b_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            b.lower()
        )
    )

    if not a_words or not b_words:
        return 0

    return len(
        a_words & b_words
    ) / max(
        1,
        min(
            len(a_words),
            len(b_words)
        )
    )


def deduplicate_sentences(sentences):

    result = []

    for sentence in sentences:

        duplicate = False

        for previous in result:

            if sentence_similarity(
                sentence,
                previous
            ) >= 0.82:

                duplicate = True
                break

        if not duplicate:

            result.append(
                sentence
            )

    return result


# ============================================================
# NARRATION HELPERS
# ============================================================

def add_sentence_candidates(
    container,
    value
):

    if not value:
        return

    if not isinstance(
        value,
        str
    ):
        return

    cleaned = remove_source_language(
        value
    )

    if not cleaned:
        return

    sentences = normalize_sentences(
        cleaned
    )

    for sentence in sentences:

        if sentence not in container:

            container.append(
                sentence
            )


def clean_narration_text(text):

    if not text:
        return ""

    text = remove_source_language(
        text
    )

    text = re.sub(
        r"^\s*Here is the latest development from [^.]+\.?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^\s*Here is the latest update from [^.]+\.?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^\s*Latest development from [^.]+\.?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"^\s*Latest update from [^.]+\.?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def word_count(text):

    if not text:
        return 0

    return len(
        re.findall(
            r"\b[\w'-]+\b",
            text
        )
    )


def trim_to_max_words(
    text,
    maximum
):

    words = text.split()

    if len(words) <= maximum:
        return text.strip()

    trimmed = " ".join(
        words[:maximum]
    )

    if not re.search(
        r"[.!?]$",
        trimmed
    ):

        trimmed += "."

    return trimmed.strip()


# ============================================================
# NARRATION
# ============================================================

def get_narration(
    story,
    script
):

    log("")
    log("=" * 70)
    log("BUILDING NARRATION")
    log("=" * 70)

    direct_candidates = []

    if isinstance(
        script,
        dict
    ):

        for key in [
            "narration",
            "script",
            "voiceover",
            "voice_over",
            "voiceover_text",
            "narration_text",
            "text",
            "body",
            "content",
        ]:

            value = script.get(
                key,
                ""
            )

            if (
                isinstance(value, str)
                and value.strip()
            ):

                cleaned = clean_narration_text(
                    value
                )

                if cleaned:

                    direct_candidates.append(
                        cleaned
                    )

                    log(
                        f"SCRIPT FIELD FOUND: {key} "
                        f"({word_count(cleaned)} words)"
                    )

    if isinstance(
        story,
        dict
    ):

        for key in [
            "narration",
            "script",
            "voiceover",
            "voice_over",
            "narration_text",
        ]:

            value = story.get(
                key,
                ""
            )

            if (
                isinstance(value, str)
                and value.strip()
            ):

                cleaned = clean_narration_text(
                    value
                )

                if cleaned:

                    direct_candidates.append(
                        cleaned
                    )

                    log(
                        f"STORY FIELD FOUND: {key} "
                        f"({word_count(cleaned)} words)"
                    )

    for candidate in direct_candidates:

        count = word_count(
            candidate
        )

        if count >= MIN_NARRATION_WORDS:

            log(
                f"USING DIRECT NARRATION: "
                f"{count} words"
            )

            return trim_to_max_words(
                candidate,
                MAX_NARRATION_WORDS
            )

    sentence_pool = []

    if isinstance(
        story,
        dict
    ):

        for key in [
            "description",
            "summary",
            "body",
            "content",
            "article",
            "text",
        ]:

            add_sentence_candidates(
                sentence_pool,
                story.get(
                    key,
                    ""
                )
            )

    for candidate in direct_candidates:

        add_sentence_candidates(
            sentence_pool,
            candidate
        )

    sentence_pool = deduplicate_sentences(
        sentence_pool
    )

    log(
        f"UNIQUE NARRATION SENTENCES: "
        f"{len(sentence_pool)}"
    )

    selected = []

    for sentence in sentence_pool:

        test = " ".join(
            selected + [sentence]
        )

        if word_count(test) > MAX_NARRATION_WORDS:
            break

        selected.append(
            sentence
        )

        if word_count(test) >= MIN_NARRATION_WORDS:
            break

    narration = " ".join(
        selected
    )

    if word_count(narration) < MIN_NARRATION_WORDS:

        for candidate in direct_candidates:

            candidate_sentences = normalize_sentences(
                candidate
            )

            for sentence in candidate_sentences:

                if sentence in selected:
                    continue

                test = " ".join(
                    selected + [sentence]
                )

                if word_count(test) > MAX_NARRATION_WORDS:
                    continue

                selected.append(
                    sentence
                )

                narration = " ".join(
                    selected
                )

                if word_count(narration) >= MIN_NARRATION_WORDS:
                    break

            if word_count(narration) >= MIN_NARRATION_WORDS:
                break

    if word_count(narration) < MIN_NARRATION_WORDS:

        title = clean_title(
            story.get(
                "title",
                ""
            )
            if isinstance(
                story,
                dict
            )
            else ""
        )

        description = clean_narration_text(
            story.get(
                "description",
                ""
            )
            if isinstance(
                story,
                dict
            )
            else ""
        )

        body = clean_narration_text(
            story.get(
                "body",
                ""
            )
            if isinstance(
                story,
                dict
            )
            else ""
        )

        fallback_parts = []

        if title:
            fallback_parts.append(
                title
            )

        if description:
            fallback_parts.append(
                description
            )

        if body:
            fallback_parts.append(
                body
            )

        fallback_text = " ".join(
            fallback_parts
        )

        fallback_sentences = normalize_sentences(
            fallback_text
        )

        fallback_sentences = deduplicate_sentences(
            fallback_sentences
        )

        selected = []

        for sentence in fallback_sentences:

            test = " ".join(
                selected + [sentence]
            )

            if word_count(test) > MAX_NARRATION_WORDS:
                break

            selected.append(
                sentence
            )

            if word_count(test) >= MIN_NARRATION_WORDS:
                break

        narration = " ".join(
            selected
        )

    narration = clean_narration_text(
        narration
    )

    narration = trim_to_max_words(
        narration,
        MAX_NARRATION_WORDS
    )

    count = word_count(
        narration
    )

    log(
        f"FINAL NARRATION WORD COUNT: {count}"
    )

    if count < MIN_NARRATION_WORDS:

        log("")
        log("=" * 70)
        log("NARRATION DATA TOO SHORT")
        log("=" * 70)

        if isinstance(
            story,
            dict
        ):

            log(
                "Available story keys: "
                + ", ".join(
                    str(k)
                    for k in story.keys()
                )
            )

        if isinstance(
            script,
            dict
        ):

            log(
                "Available script keys: "
                + ", ".join(
                    str(k)
                    for k in script.keys()
                )
            )

        log("=" * 70)

        raise RuntimeError(
            "Narration is too short after all available "
            "story and script text was combined."
        )

    return narration


# ============================================================
# AUDIO UTILITIES
# ============================================================

def remove_old_audio():

    for path in [
        AUDIO_FILE,
        TEMP_AUDIO,
    ]:

        try:

            if path.exists():

                path.unlink()

                log(
                    f"REMOVED OLD AUDIO: {path}"
                )

        except Exception as exc:

            raise RuntimeError(
                f"Could not remove old audio {path}: {exc}"
            )


def check_command(
    command_name
):

    path = shutil.which(
        command_name
    )

    if not path:

        raise RuntimeError(
            f"Required command not found: "
            f"{command_name}"
        )

    log(
        f"{command_name.upper()}: {path}"
    )

    return path


def validate_audio_file(
    path
):

    if not path.exists():

        raise RuntimeError(
            f"Narration MP3 does not exist: {path}"
        )

    size = path.stat().st_size

    log(
        f"NARRATION SIZE: {size:,} bytes"
    )

    if size < 1000:

        raise RuntimeError(
            f"Narration MP3 is too small: {size} bytes"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "ffprobe could not read narration MP3.\n"
            + result.stderr
        )

    codec = result.stdout.strip()

    if not codec:

        raise RuntimeError(
            "Narration MP3 contains no audio stream."
        )

    log(
        f"NARRATION CODEC: {codec}"
    )

    return True


# ============================================================
# GENERATE AUDIO
# ============================================================

def generate_audio(
    narration
):

    log("")
    log("=" * 70)
    log("GENERATING NARRATION AUDIO")
    log("=" * 70)

    if not narration.strip():

        raise RuntimeError(
            "Narration text is empty."
        )

    count = word_count(
        narration
    )

    log(
        f"NARRATION CHARACTERS: {len(narration)}"
    )

    log(
        f"NARRATION WORDS: {count}"
    )

    log(
        f"MINIMUM WORDS REQUIRED: "
        f"{MIN_NARRATION_WORDS}"
    )

    if count < MIN_NARRATION_WORDS:

        raise RuntimeError(
            f"Narration is too short: "
            f"{count} words. "
            f"Minimum required: "
            f"{MIN_NARRATION_WORDS}."
        )

    log(
        "TTS ENGINE: gTTS"
    )

    remove_old_audio()

    try:

        from gtts import gTTS

    except Exception as exc:

        raise RuntimeError(
            "gTTS could not be imported. "
            "Install it with: pip install gTTS\n"
            f"Import error: {exc}"
        )

    try:

        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
            lang_check=True
        )

        log(
            "gTTS OBJECT CREATED"
        )

        tts.save(
            str(TEMP_AUDIO)
        )

        log(
            f"gTTS SAVE COMPLETED: "
            f"{TEMP_AUDIO}"
        )

    except Exception as exc:

        log("")
        log("=" * 70)
        log("G TTS FAILED")
        log("=" * 70)

        log(
            f"ERROR TYPE: "
            f"{type(exc).__name__}"
        )

        log(
            f"ERROR MESSAGE: {exc}"
        )

        log("=" * 70)

        raise RuntimeError(
            "gTTS failed to generate narration audio. "
            "Check GitHub Actions internet access and "
            "confirm that the gTTS package is installed."
        )

    if not TEMP_AUDIO.exists():

        raise RuntimeError(
            "gTTS completed without creating "
            "narration_temp.mp3."
        )

    if TEMP_AUDIO.stat().st_size < 1000:

        raise RuntimeError(
            "gTTS created an invalid or empty MP3."
        )

    validate_audio_file(
        TEMP_AUDIO
    )

    try:

        TEMP_AUDIO.replace(
            AUDIO_FILE
        )

    except Exception as exc:

        raise RuntimeError(
            f"Could not move generated audio into "
            f"{AUDIO_FILE}: {exc}"
        )

    validate_audio_file(
        AUDIO_FILE
    )

    log(
        f"NARRATION CREATED SUCCESSFULLY: "
        f"{AUDIO_FILE}"
    )

    log("=" * 70)

    return AUDIO_FILE


# ============================================================
# MEDIA DURATION
# ============================================================

def get_media_duration(
    path
):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"ffprobe failed: {result.stderr}"
        )

    try:

        return float(
            result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            f"Could not determine duration: {path}"
        )


def calculate_duration(
    audio_path
):

    duration = get_media_duration(
        audio_path
    )

    duration = max(
        MIN_DURATION,
        duration
    )

    duration = min(
        MAX_DURATION,
        duration
    )

    return duration


# ============================================================
# FONT
# ============================================================

def get_font(
    size,
    bold=False
):

    if bold:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]

    else:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for font_path in candidates:

        path = Path(
            font_path
        )

        if path.exists():

            return ImageFont.truetype(
                str(path),
                size
            )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width
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
            font=font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        if text_width <= max_width:

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


def fit_headline(
    draw,
    title
):

    max_width = WIDTH - 120

    for size in range(
        54,
        30,
        -2
    ):

        font = get_font(
            size,
            bold=True
        )

        lines = wrap_text(
            draw,
            title,
            font,
            max_width
        )

        if len(lines) <= 4:

            return font, lines

    font = get_font(
        30,
        bold=True
    )

    lines = wrap_text(
        draw,
        title,
        font,
        max_width
    )

    return font, lines[:4]


# ============================================================
# OVERLAY
# ============================================================

def create_overlay(
    county,
    title
):

    log(
        "CREATING STATIC NEWS OVERLAY"
    )

    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    draw = ImageDraw.Draw(
        image
    )

    # --------------------------------------------------------
    # TOP PANEL
    # --------------------------------------------------------

    top_height = 405

    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            top_height
        ],
        fill=(
            0,
            0,
            0,
            215
        )
    )

    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            8
        ],
        fill=(
            255,
            255,
            255,
            255
        )
    )

    brand_font = get_font(
        34,
        bold=True
    )

    draw.text(
        (
            55,
            42
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(
            255,
            255,
            255,
            255
        )
    )

    county_font = get_font(
        28,
        bold=True
    )

    draw.text(
        (
            55,
            98
        ),
        str(county).upper(),
        font=county_font,
        fill=(
            235,
            235,
            235,
            255
        )
    )

    draw.rectangle(
        [
            55,
            145,
            WIDTH - 55,
            148
        ],
        fill=(
            255,
            255,
            255,
            110
        )
    )

    title = clean_title(
        title
    )

    if len(title) > 180:

        title = (
            title[:177].rstrip()
            + "..."
        )

    headline_font, lines = fit_headline(
        draw,
        title
    )

    y = 175

    for line in lines:

        draw.text(
            (
                55,
                y
            ),
            line,
            font=headline_font,
            fill=(
                255,
                255,
                255,
                255
            )
        )

        bbox = draw.textbbox(
            (
                55,
                y
            ),
            line,
            font=headline_font
        )

        line_height = (
            bbox[3] - bbox[1]
        )

        y += (
            line_height + 8
        )

    # --------------------------------------------------------
    # BOTTOM PANEL
    # --------------------------------------------------------

    bottom_height = 210

    bottom_y = (
        HEIGHT - bottom_height
    )

    draw.rectangle(
        [
            0,
            bottom_y,
            WIDTH,
            HEIGHT
        ],
        fill=(
            0,
            0,
            0,
            205
        )
    )

    footer_font = get_font(
        27,
        bold=True
    )

    draw.text(
        (
            55,
            bottom_y + 70
        ),
        "RIFT VALLEY • KENYA",
        font=footer_font,
        fill=(
            255,
            255,
            255,
            245
        )
    )

    draw.rectangle(
        [
            55,
            bottom_y + 125,
            340,
            bottom_y + 129
        ],
        fill=(
            255,
            255,
            255,
            150
        )
    )

    image.save(
        OVERLAY_FILE,
        "PNG"
    )

    if not OVERLAY_FILE.exists():

        raise RuntimeError(
            "Overlay was not created."
        )

    return OVERLAY_FILE


# ============================================================
# IMAGE URL HELPERS
# ============================================================

def normalize_url(
    url
):

    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):

        url = "https:" + url

    return url


def valid_image_url(
    url
):

    url = normalize_url(
        url
    )

    if not url.startswith(
        (
            "http://",
            "https://",
        )
    ):

        return False

    return True


def image_extension_from_url(
    url
):

    clean = url.lower().split("?")[0]

    for extension in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
    ]:

        if clean.endswith(
            extension
        ):

            return extension

    return ".jpg"


# ============================================================
# ARTICLE IMAGE DISCOVERY
# ============================================================

def extract_image_urls_from_html(
    html,
    page_url
):

    if not html:
        return []

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

    except Exception:

        return []

    candidates = []

    # --------------------------------------------------------
    # OpenGraph / Twitter
    # --------------------------------------------------------

    for meta in soup.find_all(
        "meta"
    ):

        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = (
            meta.get("content")
            or ""
        ).strip()

        if not content:
            continue

        if prop in {
            "og:image",
            "og:image:url",
            "twitter:image",
            "twitter:image:src",
        }:

            candidates.append(
                content
            )

    # --------------------------------------------------------
    # image_src links
    # --------------------------------------------------------

    for link in soup.find_all(
        "link"
    ):

        rel = " ".join(
            link.get(
                "rel",
                []
            )
        ).lower()

        href = (
            link.get(
                "href",
                ""
            )
            or ""
        ).strip()

        if (
            href
            and "image_src" in rel
        ):

            candidates.append(
                href
            )

    # --------------------------------------------------------
    # IMG elements
    # --------------------------------------------------------

    for img in soup.find_all(
        "img"
    ):

        values = [
            img.get("src"),
            img.get("data-src"),
            img.get("data-lazy-src"),
            img.get("data-original"),
        ]

        srcset = img.get(
            "srcset"
        )

        if srcset:

            parts = srcset.split(",")

            for part in parts:

                part = part.strip()

                if not part:
                    continue

                values.append(
                    part.split()[0]
                )

        for value in values:

            if not value:
                continue

            candidates.append(
                value
            )

    unique = []
    seen = set()

    for candidate in candidates:

        candidate = normalize_url(
            candidate
        )

        if not candidate:
            continue

        if not candidate.startswith(
            (
                "http://",
                "https://",
            )
        ):

            continue

        if candidate in seen:
            continue

        seen.add(
            candidate
        )

        unique.append(
            candidate
        )

    return unique


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    destination
):

    try:

        response = SESSION.get(
            url,
            timeout=IMAGE_TIMEOUT,
            stream=True,
            allow_redirects=True
        )

        if response.status_code != 200:

            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                ""
            ).lower()
        )

        if (
            "image" not in content_type
            and not url.lower().split("?")[0].endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".avif",
                )
            )
        ):

            return False

        temporary = Path(
            str(destination) + ".tmp"
        )

        total = 0

        with temporary.open(
            "wb"
        ) as handle:

            for chunk in response.iter_content(
                chunk_size=65536
            ):

                if not chunk:
                    continue

                total += len(
                    chunk
                )

                if total > MAX_IMAGE_BYTES:

                    temporary.unlink(
                        missing_ok=True
                    )

                    return False

                handle.write(
                    chunk
                )

        try:

            with Image.open(
                temporary
            ) as image:

                image.verify()

        except Exception:

            temporary.unlink(
                missing_ok=True
            )

            return False

        temporary.replace(
            destination
        )

        return True

    except Exception as exc:

        log(
            f"IMAGE DOWNLOAD FAILED: "
            f"{url} | {exc}"
        )

        try:

            Path(
                str(destination) + ".tmp"
            ).unlink(
                missing_ok=True
            )

        except Exception:
            pass

        return False


# ============================================================
# IMAGE QUALITY
# ============================================================

def image_is_usable(
    path
):

    if not path.exists():
        return False

    try:

        with Image.open(
            path
        ) as image:

            width, height = image.size

            if width < 300:
                return False

            if height < 200:
                return False

            if width * height < 150000:
                return False

            return True

    except Exception:

        return False


def image_fingerprint(
    path
):

    try:

        with Image.open(
            path
        ) as image:

            image = image.convert(
                "RGB"
            )

            image.thumbnail(
                (
                    32,
                    32
                )
            )

            image_bytes = image.tobytes()

            return hashlib.sha1(
                image_bytes
            ).hexdigest()

    except Exception:

        return ""


# ============================================================
# PREPARE ARTICLE PHOTOS
# ============================================================

def collect_article_image_urls(
    story
):

    urls = []

    if not isinstance(
        story,
        dict
    ):

        return urls

    # --------------------------------------------------------
    # First choice:
    # URLs already discovered by the main story engine.
    # --------------------------------------------------------

    image_urls = story.get(
        "image_urls",
        []
    )

    if isinstance(
        image_urls,
        list
    ):

        for url in image_urls:

            url = normalize_url(
                url
            )

            if valid_image_url(
                url
            ):

                urls.append(
                    url
                )

    # --------------------------------------------------------
    # Support additional possible fields.
    # --------------------------------------------------------

    for key in [
        "image_url",
        "image",
        "photo",
        "featured_image",
        "thumbnail",
    ]:

        value = story.get(
            key,
            ""
        )

        if isinstance(
            value,
            str
        ):

            value = normalize_url(
                value
            )

            if valid_image_url(
                value
            ):

                urls.append(
                    value
                )

    # --------------------------------------------------------
    # Remove duplicates.
    # --------------------------------------------------------

    unique = []
    seen = set()

    for url in urls:

        key = url.split(
            "#"
        )[0]

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            url
        )

    return unique


def discover_more_article_images(
    story
):

    article_url = ""

    if isinstance(
        story,
        dict
    ):

        article_url = story.get(
            "url",
            ""
        )

    if not article_url:
        return []

    log(
        "ARTICLE IMAGE FALLBACK: "
        "FETCHING ARTICLE PAGE FOR MORE REAL PHOTOS"
    )

    try:

        response = SESSION.get(
            article_url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        if response.status_code != 200:

            log(
                f"ARTICLE PAGE IMAGE FETCH FAILED: "
                f"HTTP {response.status_code}"
            )

            return []

        return extract_image_urls_from_html(
            response.text,
            response.url
        )

    except Exception as exc:

        log(
            f"ARTICLE PAGE IMAGE FETCH ERROR: {exc}"
        )

        return []


def prepare_article_photos(
    story
):

    log("")
    log("=" * 70)
    log("PREPARING REAL ARTICLE PHOTOS")
    log("=" * 70)

    # --------------------------------------------------------
    # Clean old scene images.
    # --------------------------------------------------------

    for path in WORK_DIR.glob(
        "article_photo_*.jpg"
    ):

        try:
            path.unlink()
        except Exception:
            pass

    urls = collect_article_image_urls(
        story
    )

    log(
        f"IMAGE URLS ALREADY IN STORY: "
        f"{len(urls)}"
    )

    # --------------------------------------------------------
    # If main engine gave too few URLs, fetch article page
    # directly for additional real photos.
    # --------------------------------------------------------

    if len(urls) < MAX_REAL_PHOTOS:

        extra_urls = discover_more_article_images(
            story
        )

        for url in extra_urls:

            if url not in urls:

                urls.append(
                    url
                )

            if len(urls) >= 30:
                break

    log(
        f"TOTAL IMAGE URL CANDIDATES: "
        f"{len(urls)}"
    )

    prepared = []
    fingerprints = set()

    # --------------------------------------------------------
    # Download real article photos.
    # --------------------------------------------------------

    for index, url in enumerate(
        urls,
        start=1
    ):

        if len(prepared) >= MAX_REAL_PHOTOS:
            break

        destination = (
            WORK_DIR
            / f"article_photo_{len(prepared) + 1}.jpg"
        )

        log(
            f"TRYING REAL ARTICLE PHOTO "
            f"{index}: {url}"
        )

        destination.unlink(
            missing_ok=True
        )

        if not download_image(
            url,
            destination
        ):

            continue

        if not image_is_usable(
            destination
        ):

            log(
                "REJECTED: IMAGE TOO SMALL OR INVALID"
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        # Convert everything to JPEG.
        try:

            with Image.open(
                destination
            ) as image:

                image = image.convert(
                    "RGB"
                )

                image.save(
                    destination,
                    "JPEG",
                    quality=95
                )

        except Exception:

            destination.unlink(
                missing_ok=True
            )

            continue

        fingerprint = image_fingerprint(
            destination
        )

        if (
            fingerprint
            and fingerprint in fingerprints
        ):

            log(
                "REJECTED: DUPLICATE PHOTO"
            )

            destination.unlink(
                missing_ok=True
            )

            continue

        if fingerprint:

            fingerprints.add(
                fingerprint
            )

        try:

            with Image.open(
                destination
            ) as image:

                log(
                    "REAL ARTICLE PHOTO ACCEPTED: "
                    f"{image.width}x{image.height}"
                )

        except Exception:
            pass

        prepared.append(
            destination
        )

    # --------------------------------------------------------
    # Use the already-selected main image as a fallback.
    # --------------------------------------------------------

    if (
        len(prepared) == 0
        and IMAGE_FILE.exists()
    ):

        fallback = (
            WORK_DIR
            / "article_photo_1.jpg"
        )

        try:

            with Image.open(
                IMAGE_FILE
            ) as image:

                image = image.convert(
                    "RGB"
                )

                image.save(
                    fallback,
                    "JPEG",
                    quality=95
                )

            if image_is_usable(
                fallback
            ):

                prepared.append(
                    fallback
                )

                log(
                    "FALLBACK PHOTO: "
                    f"{IMAGE_FILE}"
                )

        except Exception as exc:

            log(
                f"FALLBACK PHOTO FAILED: {exc}"
            )

    # --------------------------------------------------------
    # Final safety check.
    # --------------------------------------------------------

    if not prepared:

        raise RuntimeError(
            "No usable real article photos were available."
        )

    log("")
    log(
        f"REAL ARTICLE PHOTOS SELECTED: "
        f"{len(prepared)}"
    )

    for index, path in enumerate(
        prepared,
        start=1
    ):

        log(
            f"PHOTO {index}: {path}"
        )

    if len(prepared) < MIN_REAL_PHOTOS:

        log(
            "WARNING: Fewer than 2 distinct article "
            "photos were available."
        )

        log(
            "The generator will use multiple "
            "motion treatments of the available photo."
        )

    log("=" * 70)

    return prepared


# ============================================================
# PREPARE IMAGE FOR A SCENE
# ============================================================

def prepare_scene_image(
    source_path,
    scene_index
):

    if not source_path.exists():

        raise RuntimeError(
            f"Source image not found: {source_path}"
        )

    try:

        image = Image.open(
            source_path
        ).convert(
            "RGB"
        )

    except Exception as exc:

        raise RuntimeError(
            f"Could not open article image: {exc}"
        )

    if (
        image.width < 200
        or image.height < 200
    ):

        raise RuntimeError(
            f"Article image is too small: {source_path}"
        )

    source_ratio = (
        image.width /
        image.height
    )

    target_ratio = (
        WIDTH /
        HEIGHT
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            new_height *
            source_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
            new_width /
            source_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )

    # --------------------------------------------------------
    # Different crop positions prevent every photo from
    # looking mechanically identical.
    # --------------------------------------------------------

    max_left = max(
        0,
        new_width - WIDTH
    )

    max_top = max(
        0,
        new_height - HEIGHT
    )

    crop_modes = [
        (
            0.50,
            0.50
        ),
        (
            0.35,
            0.50
        ),
        (
            0.65,
            0.50
        ),
        (
            0.50,
            0.40
        ),
        (
            0.50,
            0.60
        ),
    ]

    position = crop_modes[
        scene_index % len(crop_modes)
    ]

    left = int(
        max_left * position[0]
    )

    top = int(
        max_top * position[1]
    )

    left = max(
        0,
        min(
            left,
            max_left
        )
    )

    top = max(
        0,
        min(
            top,
            max_top
        )
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    destination = (
        WORK_DIR
        / f"prepared_scene_{scene_index + 1}.jpg"
    )

    image.save(
        destination,
        "JPEG",
        quality=95
    )

    return destination


# ============================================================
# SCENE DURATION
# ============================================================

def calculate_scene_durations(
    total_duration,
    scene_count
):

    if scene_count <= 0:

        return []

    if scene_count == 1:

        return [
            total_duration
        ]

    base = (
        total_duration /
        scene_count
    )

    durations = []

    for index in range(
        scene_count
    ):

        # Small variation makes the reel feel less mechanical.
        if index % 3 == 0:

            duration = base * 1.08

        elif index % 3 == 1:

            duration = base * 0.96

        else:

            duration = base * 0.96

        durations.append(
            duration
        )

    difference = (
        total_duration -
        sum(durations)
    )

    durations[-1] += difference

    return durations


# ============================================================
# CREATE INDIVIDUAL SCENE
# ============================================================

def create_scene_video(
    image_path,
    overlay_path,
    duration,
    scene_index
):

    scene_output = (
        WORK_DIR
        / f"scene_{scene_index + 1}.mp4"
    )

    scene_output.unlink(
        missing_ok=True
    )

    # Different motion directions.
    motion_modes = [
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "zoom_in",
    ]

    motion = motion_modes[
        scene_index % len(motion_modes)
    ]

    log(
        f"CREATING SCENE {scene_index + 1}: "
        f"{motion} | {duration:.2f}s"
    )

    if motion == "zoom_in":

        zoom_expression = (
            "min(1+on*0.00016,1.12)"
        )

        x_expression = (
            "iw/2-(iw/zoom/2)"
        )

        y_expression = (
            "ih/2-(ih/zoom/2)"
        )

    elif motion == "zoom_out":

        zoom_expression = (
            "max(1.12-on*0.00016,1.0)"
        )

        x_expression = (
            "iw/2-(iw/zoom/2)"
        )

        y_expression = (
            "ih/2-(ih/zoom/2)"
        )

    elif motion == "pan_left":

        zoom_expression = (
            "min(1.10,1+on*0.00008)"
        )

        x_expression = (
            "max(0,(iw-iw/zoom)*(1-on/"
            f"{max(duration * FPS, 1):.0f}))"
        )

        y_expression = (
            "ih/2-(ih/zoom/2)"
        )

    elif motion == "pan_right":

        zoom_expression = (
            "min(1.10,1+on*0.00008)"
        )

        x_expression = (
            "(iw-iw/zoom)*(on/"
            f"{max(duration * FPS, 1):.0f})"
        )

        y_expression = (
            "ih/2-(ih/zoom/2)"
        )

    else:

        zoom_expression = (
            "min(1+on*0.00012,1.10)"
        )

        x_expression = (
            "iw/2-(iw/zoom/2)"
        )

        y_expression = (
            "ih/2-(ih/zoom/2)"
        )

    filter_complex = (
        "[0:v]"
        "scale="
        f"{WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        "zoompan="
        f"z='{zoom_expression}':"
        f"x='{x_expression}':"
        f"y='{y_expression}':"
        "d=1:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps={FPS}"
        "[bg];"
        "[bg][1:v]"
        "overlay=0:0:format=auto"
        "[v]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",
        "-i",
        str(image_path),

        "-loop",
        "1",
        "-i",
        str(overlay_path),

        "-filter_complex",
        filter_complex,

        "-map",
        "[v]",

        "-t",
        f"{duration:.3f}",

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

        str(scene_output)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print(
            result.stdout,
            flush=True
        )

        print(
            result.stderr,
            flush=True
        )

        raise RuntimeError(
            f"FFmpeg failed while creating scene "
            f"{scene_index + 1}."
        )

    if not scene_output.exists():

        raise RuntimeError(
            f"Scene {scene_index + 1} was not created."
        )

    if scene_output.stat().st_size < 50000:

        raise RuntimeError(
            f"Scene {scene_index + 1} is unexpectedly small."
        )

    log(
        f"SCENE {scene_index + 1} CREATED: "
        f"{scene_output.stat().st_size:,} bytes"
    )

    return scene_output


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(
    scene_paths
):

    if not scene_paths:

        raise RuntimeError(
            "No scene videos were created."
        )

    concat_file = (
        WORK_DIR
        / "scene_concat.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8"
    ) as handle:

        for path in scene_paths:

            safe_path = (
                str(path)
                .replace(
                    "\\",
                    "/"
                )
                .replace(
                    "'",
                    "'\\''"
                )
            )

            handle.write(
                f"file '{safe_path}'\n"
            )

    TEMP_VIDEO.unlink(
        missing_ok=True
    )

    log(
        f"CONCATENATING {len(scene_paths)} REAL PHOTO SCENES"
    )

    command = [
        "ffmpeg",
        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(concat_file),

        "-c",
        "copy",

        "-movflags",
        "+faststart",

        str(TEMP_VIDEO)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print(
            result.stdout,
            flush=True
        )

        print(
            result.stderr,
            flush=True
        )

        raise RuntimeError(
            "FFmpeg failed while concatenating "
            "the article photo scenes."
        )

    if not TEMP_VIDEO.exists():

        raise RuntimeError(
            "Multi-scene video was not created."
        )

    if TEMP_VIDEO.stat().st_size < 100000:

        raise RuntimeError(
            "Multi-scene video is unexpectedly small."
        )

    log(
        f"MULTI-SCENE VIDEO CREATED: "
        f"{TEMP_VIDEO.stat().st_size:,} bytes"
    )

    return TEMP_VIDEO


# ============================================================
# MULTI-SCENE VIDEO
# ============================================================

def create_motion_video(
    image_paths,
    overlay_path,
    duration
):

    log("")
    log("=" * 70)
    log("CREATING MULTI-SCENE NEWS VISUAL")
    log("=" * 70)

    if not image_paths:

        raise RuntimeError(
            "No article images were supplied."
        )

    # --------------------------------------------------------
    # Limit scenes.
    # --------------------------------------------------------

    images = list(
        image_paths[:MAX_REAL_PHOTOS]
    )

    # --------------------------------------------------------
    # If only one real photo is available, create multiple
    # scenes from that same real article photo using different
    # crops/motion. This prevents failure.
    # --------------------------------------------------------

    if len(images) == 1:

        log(
            "ONLY ONE DISTINCT ARTICLE PHOTO AVAILABLE."
        )

        log(
            "USING MULTIPLE MOTION SCENES "
            "FROM THE SAME REAL PHOTO."
        )

        images = [
            images[0],
            images[0],
            images[0],
            images[0],
        ]

    log(
        f"SCENE COUNT: {len(images)}"
    )

    log(
        "REAL ARTICLE PHOTOS: ENABLED"
    )

    log(
        "CONTINUOUS MOTION: ENABLED"
    )

    log(
        "SLIDE COUNTER: REMOVED"
    )

    # --------------------------------------------------------
    # Prepare scene images.
    # --------------------------------------------------------

    prepared_images = []

    for index, source in enumerate(
        images
    ):

        prepared = prepare_scene_image(
            source,
            index
        )

        prepared_images.append(
            prepared
        )

    # --------------------------------------------------------
    # Scene durations.
    # --------------------------------------------------------

    durations = calculate_scene_durations(
        duration,
        len(prepared_images)
    )

    # --------------------------------------------------------
    # Create each scene.
    # --------------------------------------------------------

    scene_paths = []

    for index, (
        image_path,
        scene_duration
    ) in enumerate(
        zip(
            prepared_images,
            durations
        )
    ):

        scene_path = create_scene_video(
            image_path,
            overlay_path,
            scene_duration,
            index
        )

        scene_paths.append(
            scene_path
        )

    # --------------------------------------------------------
    # Concatenate.
    # --------------------------------------------------------

    return concatenate_scenes(
        scene_paths
    )


# ============================================================
# COMBINE AUDIO
# ============================================================

def combine_audio(
    video_path,
    audio_path
):

    log(
        "ADDING NARRATION AUDIO"
    )

    if not audio_path.exists():

        raise RuntimeError(
            f"Audio file missing before muxing: "
            f"{audio_path}"
        )

    OUTPUT_FILE.unlink(
        missing_ok=True
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(video_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        "-shortest",

        "-movflags",
        "+faststart",

        str(OUTPUT_FILE)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print(
            result.stdout,
            flush=True
        )

        print(
            result.stderr,
            flush=True
        )

        raise RuntimeError(
            "FFmpeg failed while adding audio."
        )

    if not OUTPUT_FILE.exists():

        raise RuntimeError(
            "Final MP4 was not created."
        )

    if OUTPUT_FILE.stat().st_size < 100000:

        raise RuntimeError(
            "Final MP4 is unexpectedly small."
        )

    return OUTPUT_FILE


# ============================================================
# FINAL QC
# ============================================================

def verify_final_video(
    path,
    image_count
):

    log("")
    log("=" * 70)
    log("FINAL MP4 QUALITY CONTROL")
    log("=" * 70)

    if not path.exists():

        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100000:

        raise RuntimeError(
            "Final MP4 is too small."
        )

    duration = get_media_duration(
        path
    )

    probe_command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,codec_name",
        "-of",
        "default=noprint_wrappers=1",
        str(path)
    ]

    result = subprocess.run(
        probe_command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Could not inspect final MP4."
        )

    probe = result.stdout.lower()

    if "width=1080" not in probe:

        raise RuntimeError(
            "Final MP4 width is not 1080."
        )

    if "height=1920" not in probe:

        raise RuntimeError(
            "Final MP4 height is not 1920."
        )

    audio_command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    audio_result = subprocess.run(
        audio_command,
        capture_output=True,
        text=True
    )

    if (
        audio_result.returncode != 0
        or not audio_result.stdout.strip()
    ):

        raise RuntimeError(
            "Final MP4 does not contain audio."
        )

    log(
        f"FINAL FILE: {path}"
    )

    log(
        f"SIZE: {size:,} bytes"
    )

    log(
        f"DURATION: {duration:.2f} seconds"
    )

    log(
        "VIDEO: 1080x1920"
    )

    log(
        f"AUDIO CODEC: "
        f"{audio_result.stdout.strip()}"
    )

    log(
        f"REAL ARTICLE PHOTO COUNT: {image_count}"
    )

    log(
        "MULTI-SCENE VISUALS: ENABLED"
    )

    log(
        "MOTION: CONTINUOUS"
    )

    log(
        "SLIDE COUNTER: REMOVED"
    )

    log(
        "SOURCE/PUBLISHER ON SCREEN: NONE"
    )

    log("=" * 70)
    log("FINAL MP4 QC PASSED")
    log("=" * 70)


# ============================================================
# CLEAN WORK FILES
# ============================================================

def cleanup_work_files():

    patterns = [
        "article_photo_*.jpg",
        "prepared_scene_*.jpg",
        "scene_*.mp4",
    ]

    for pattern in patterns:

        for path in WORK_DIR.glob(
            pattern
        ):

            try:

                path.unlink()

            except Exception as exc:

                log(
                    f"WARNING: Could not remove "
                    f"{path}: {exc}"
                )

    for path in [
        TEMP_VIDEO,
        OVERLAY_FILE,
        PREPARED_IMAGE,
        TEMP_AUDIO,
        WORK_DIR / "scene_concat.txt",
    ]:

        try:

            if path.exists():

                path.unlink()

        except Exception as exc:

            log(
                f"WARNING: Could not remove "
                f"{path}: {exc}"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH VIDEO GENERATOR")
    log("VERSION: RVW_VIDEO_V16_MULTI_REAL_PHOTOS")
    log("=" * 70)

    ensure_directories()

    check_command(
        "ffmpeg"
    )

    check_command(
        "ffprobe"
    )

    story = load_story()

    script = load_script()

    county = story.get(
        "county",
        "Rift Valley"
    )

    title = clean_title(
        story.get(
            "title",
            "Latest Rift Valley Update"
        )
    )

    log(
        f"COUNTY: {county}"
    )

    log(
        f"HEADLINE: {title}"
    )

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = get_narration(
        story,
        script
    )

    narration_words = word_count(
        narration
    )

    log("")
    log("=" * 70)
    log("FINAL NARRATION")
    log("=" * 70)

    log(
        f"NARRATION WORDS: "
        f"{narration_words}"
    )

    log(
        f"MINIMUM REQUIRED: "
        f"{MIN_NARRATION_WORDS}"
    )

    log(
        f"MAXIMUM ALLOWED: "
        f"{MAX_NARRATION_WORDS}"
    )

    log(
        "NARRATION TEXT:"
    )

    log(
        narration
    )

    log("=" * 70)

    if narration_words < MIN_NARRATION_WORDS:

        raise RuntimeError(
            f"Narration is too short: "
            f"{narration_words} words. "
            f"Minimum required: "
            f"{MIN_NARRATION_WORDS}."
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    log(
        f"NARRATION FILE: "
        f"{audio_path}"
    )

    duration = calculate_duration(
        audio_path
    )

    log(
        f"TARGET DURATION: "
        f"{duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # REAL ARTICLE PHOTOS
    # --------------------------------------------------------

    article_images = prepare_article_photos(
        story
    )

    log("")
    log("=" * 70)
    log("ARTICLE VISUALS READY")
    log("=" * 70)

    log(
        f"REAL ARTICLE PHOTOS AVAILABLE: "
        f"{len(article_images)}"
    )

    for index, image in enumerate(
        article_images,
        start=1
    ):

        log(
            f"PHOTO {index}: {image}"
        )

    log("=" * 70)

    # --------------------------------------------------------
    # OVERLAY
    # --------------------------------------------------------

    overlay_path = create_overlay(
        county,
        title
    )

    # --------------------------------------------------------
    # MULTI-SCENE VIDEO
    # --------------------------------------------------------

    motion_video = create_motion_video(
        article_images,
        overlay_path,
        duration
    )

    # --------------------------------------------------------
    # AUDIO + VIDEO
    # --------------------------------------------------------

    final_video = combine_audio(
        motion_video,
        audio_path
    )

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    verify_final_video(
        final_video,
        len(article_images)
    )

    cleanup_work_files()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATION COMPLETE")
    log("=" * 70)

    log(
        f"FINAL MP4: "
        f"{final_video}"
    )

    log(
        f"NARRATION MP3: "
        f"{audio_path}"
    )

    log(
        f"REAL ARTICLE PHOTOS USED: "
        f"{len(article_images)}"
    )

    log("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH VIDEO GENERATION FAILED")
        log("=" * 70)

        log(
            f"ERROR TYPE: "
            f"{type(exc).__name__}"
        )

        log(
            f"ERROR: {exc}"
        )

        log("=" * 70)

        sys.exit(1)
