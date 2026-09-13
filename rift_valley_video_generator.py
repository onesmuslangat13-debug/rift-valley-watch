from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import traceback
import time

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V19_STABLE_SHORT_REEL
#
# PURPOSE
# - One selected real news story
# - 15-30 second vertical reel
# - Automatic narration shortening
# - Multiple genuine article photos when available
# - Never scrape random/unrelated page images
# - If only one genuine photo exists, reuse it safely
# - Full photo remains visible
# - No publisher/source/URL shown on video
# - 1080x1920 MP4
# - Final audio/video QC
# ============================================================

VERSION = "RVW_VIDEO_V19_STABLE_SHORT_REEL"

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
NARRATION_FILE = AUDIO_DIR / "narration.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_REEL_DURATION = 15.0
TARGET_REEL_DURATION = 25.0
MAX_REEL_DURATION = 30.0

SAFE_AUDIO_MAX = 29.0

MIN_NARRATION_WORDS = 40
TARGET_NARRATION_WORDS = 54
MAX_NARRATION_WORDS = 68

MAX_PHOTOS = 5

REQUEST_TIMEOUT = 20


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


def section(title):
    log("")
    log("=" * 70)
    log(title)
    log("=" * 70)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(command, check=True):
    log("RUNNING: " + " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def require_command(name):
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command not found: {name}")


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Required file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Could not read {path}: {exc}")


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_headline(value):
    text = clean_text(value)

    # Remove common publisher suffixes.
    text = re.sub(
        r"\s*\|\s*(KBC(?: Digital)?|Citizen(?: Digital)?|The Star|Nation|Nation Africa|Daily Nation)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*-\s*(KBC(?: Digital)?|Citizen(?: Digital)?|The Star|Nation|Nation Africa|Daily Nation)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip(" -|")


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+", text)

    output = []

    for part in parts:
        part = part.strip()

        if not part:
            continue

        if len(part.split()) < 4:
            continue

        output.append(part)

    return output


def word_count(text):
    return len(re.findall(r"\b[\w’'-]+\b", text))


# ============================================================
# STORY / NARRATION
# ============================================================

def get_value(data, keys):
    for key in keys:
        value = data.get(key)

        if value is not None:
            value = clean_text(value)

            if value:
                return value

    return ""


def extract_story_text(story):
    candidates = []

    fields = [
        "summary",
        "description",
        "content",
        "body",
        "article_text",
        "text",
        "story",
        "details",
        "excerpt"
    ]

    for field in fields:
        value = story.get(field)

        if isinstance(value, str) and value.strip():
            candidates.append(value)

    nested = story.get("article")

    if isinstance(nested, dict):
        for field in fields:
            value = nested.get(field)

            if isinstance(value, str) and value.strip():
                candidates.append(value)

    return " ".join(candidates)


def get_headline(story):
    headline = get_value(
        story,
        [
            "headline",
            "title",
            "story_title",
            "name"
        ]
    )

    return clean_headline(headline)


def build_base_narration(story, script):
    headline = get_headline(story)

    candidates = []

    for source in [script, story]:
        if not isinstance(source, dict):
            continue

        for field in [
            "narration",
            "script",
            "voiceover",
            "summary",
            "description",
            "content",
            "body",
            "article_text",
            "text",
            "story"
        ]:
            value = source.get(field)

            if isinstance(value, str) and value.strip():
                candidates.append(clean_text(value))

    article_text = extract_story_text(story)

    if article_text:
        candidates.append(article_text)

    sentences = []

    if headline:
        sentences.append(headline + ".")

    for block in candidates:
        for sentence in split_sentences(block):
            if sentence not in sentences:
                sentences.append(sentence)

    if not sentences:
        raise RuntimeError("No usable narration text found.")

    result = []

    current_words = 0

    for sentence in sentences:
        words = word_count(sentence)

        if current_words >= MAX_NARRATION_WORDS:
            break

        result.append(sentence)
        current_words += words

        if current_words >= TARGET_NARRATION_WORDS:
            break

    narration = " ".join(result).strip()

    return narration


def shorten_narration(text, target_words):
    sentences = split_sentences(text)

    if not sentences:
        return text

    selected = []
    count = 0

    for sentence in sentences:
        words = word_count(sentence)

        if count + words <= target_words:
            selected.append(sentence)
            count += words
        elif not selected:
            selected.append(sentence)
            break

        if count >= target_words:
            break

    shortened = " ".join(selected).strip()

    if word_count(shortened) < MIN_NARRATION_WORDS:
        words = re.findall(r"\S+", text)

        shortened = " ".join(words[:target_words])

    return shortened


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================
