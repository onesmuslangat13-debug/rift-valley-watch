from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib

import requests
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V17_REAL_STORY_IMAGES_FULL_AUDIO
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

AUDIO_FILE = AUDIO_DIR / "narration.mp3"
TEMP_AUDIO = AUDIO_DIR / "narration_temp.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_DURATION = 15

MIN_NARRATION_WORDS = 80
MAX_NARRATION_WORDS = 145

# Maximum number of DISTINCT real article photos.
MAX_REAL_PHOTOS = 5

# Number of visual scenes when only one real photo exists.
SINGLE_PHOTO_SCENES = 4

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
            "image/avif,image/webp,image/apng,"
            "image/svg+xml,image/*,*/*;q=0.8"
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

        duration = float(
            result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            f"Could not determine duration: {path}"
        )

    if duration <= 0:

        raise RuntimeError(
            f"Invalid media duration: {duration}"
        )

    return duration


def calculate_duration(
    audio_path
):

    # IMPORTANT:
    # The narration is now the master timeline.
    # There is deliberately NO 60-second cap.

    duration = get_media_duration(
        audio_path
    )

    duration = max(
        MIN_DURATION,
        duration
    )

    log(
        f"AUDIO MASTER DURATION: "
        f"{duration:.3f} seconds"
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
            "/usr/share/fonts/truetype
