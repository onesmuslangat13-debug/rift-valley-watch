from pathlib import Path
import json
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION:
# RVW_VIDEO_V30_REAL_PHOTO_EDITORIAL
#
# PURPOSE
# - 1080 x 1920 vertical news reel
# - Uses genuine article photographs only
# - Uses one scene per genuinely unique photograph
# - Never creates fake multi-photo counters
# - Supports one or multiple real article photos
# - Uses narration.mp3 from /audio
# - Uses selected story/script from /data
# - Professional editorial/news presentation
# - No Citizen TV branding
# - No generic avatars
# - No placeholders
# - No World Cup graphics
# - No unrelated stock imagery
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"

FINAL_OUTPUT = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 30

MAX_SCENES = 6

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 300
MIN_IMAGE_BYTES = 10000

JPEG_QUALITY = 94

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

VIDEO_PRESET = "medium"
VIDEO_CRF = "20"

AUDIO_BITRATE = "128k"

REQUEST_TIMEOUT = 20


# ============================================================
# FORBIDDEN VISUALS
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizen_tv",
    "citizen-tv",
    "ctv",
    "world_cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "generic",
    "profile-picture",
    "profile_picture",
    "profilepicture",
    "dummy",
    "stock-avatar",
]


# ============================================================
# COLORS
# ============================================================

BLACK = (10, 10, 12)
DARK = (18, 18, 22)
WHITE = (248, 248, 248)
LIGHT = (225, 225, 228)
GREY = (155, 155, 162)
DARK_GREY = (55, 55, 62)

RED = (205, 28, 38)
YELLOW = (245, 190, 45)
GREEN = (35, 155, 85)

PANEL = (20, 20, 25)


# ============================================================
# BASIC HELPERS
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def run_command(command, check=True):
    print()
    print("RUNNING:")
    print(" ".join(str(x) for x in command))
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}: {' '.join(str(x) for x in command)}"
        )

    return result


def safe_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"<[^>]+>", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_display_text(value):
    text = safe_text(value)

    text = text.replace(
        "Citizen Digital",
        "",
    )

    text = text.replace(
        "Citizen TV",
        "",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(" -|")


# ============================================================
# JSON
# ============================================================

def load_json(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Required JSON file does not exist:\n{path}"
        )

    if path.stat().st_size < 2:
        raise RuntimeError(
            f"Required JSON file is empty:\n{path}"
        )

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as exc:
        raise RuntimeError(
            f"Unable to load JSON file:\n{path}\n{exc}"
        ) from exc


def save_json(path, payload):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
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
# STORY NORMALIZATION
# ============================================================

def get_story_object(story_data):
    """
    Supports:
      1. selected_story.json containing one story object
      2. selected_story.json containing {"story": {...}}
      3. selected_story.json containing {"stories": [...]}
    """

    if not isinstance(story_data, dict):
        raise RuntimeError(
            "selected_story.json must contain a JSON object."
        )

    if isinstance(
        story_data.get("story"),
        dict,
    ):
        return story_data["story"]

    stories = story_data.get("stories")

    if isinstance(stories, list) and stories:
        first = stories[0]

        if isinstance(first, dict):
            return first

    if story_data.get("title"):
        return story_data

    raise RuntimeError(
        "Could not identify a story object in selected_story.json."
    )


def get_script_object(script_data):
    if not isinstance(script_data, dict):
        return {}

    if isinstance(
        script_data.get("story"),
        dict,
    ):
        return script_data["story"]

    stories = script_data.get("stories")

    if isinstance(stories, list) and stories:
        first = stories[0]

        if isinstance(first, dict):
            return first

    return script_data


# ============================================================
# SOURCE NAME
# ============================================================

def get_source_name(story):
    source = story.get("source", "")

    if isinstance(source, dict):
        name = source.get("name", "")
    else:
        name = source

    return clean_display_text(name)


# ============================================================
# COUNTY
# ============================================================

def get_county(story):
    county = clean_display_text(
        story.get("county", "")
    )

    if not county:
        return "Rift Valley"

    return county


# ============================================================
# CATEGORY
# ============================================================

def get_category(story):
    category = clean_display_text(
        story.get("category", "")
    )

    if not category:
        return "REGIONAL NEWS"

    return category.upper()


# ============================================================
# TITLE
# ============================================================

def get_title(story):
    title = clean_display_text(
        story.get("title", "")
    )

    if not title:
        title = "Rift Valley Update"

    return title


# ============================================================
# PUBLISHED DATE
# ============================================================

def get_published(story):
    value = (
        story.get("published")
        or story.get("date")
        or ""
    )

    return clean_display_text(value)


# ============================================================
# IMAGE PATH HELPERS
# ============================================================

def resolve_local_path(value):
    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    candidate = Path(value)

    if candidate.is_absolute() and candidate.exists():
        return candidate

    candidate = BASE_DIR / value

    if candidate.exists():
        return candidate

    candidate = SOURCE_DIR / Path(value).name

    if candidate.exists():
        return candidate

    return None


def contains_forbidden_term(path):
    name = Path(path).name.lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term.lower() in name:
            return True

    return False


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(path):
    path = Path(path)

    if not path.exists():
        return False

    if not path.is_file():
        return False

    try:
        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False
    except Exception:
        return False

    if contains_forbidden_term(path):
        print(
            "REJECTED IMAGE FILENAME:",
            path,
        )
        return False

    try:
        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            image.verify()

        return True

    except Exception:
        return False


# ============================================================
# IMAGE HASH
# ============================================================

def exact_file_hash(path):
    digest = hashlib.sha256()

    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(1024 * 1024)

                if not block:
                    break

                digest.update(block)

        return digest.hexdigest()

    except Exception:
        return ""


def visual_hash(path):
    try:
        with Image.open(path) as image:

            image = image.convert("RGB")

            image.thumbnail(
                (32, 32),
                Image.Resampling.LANCZOS,
            )

            image = image.resize(
                (32, 32),
                Image.Resampling.LANCZOS,
            )

            pixels = list(
                image.getdata()
            )

            if not pixels:
                return ""

            brightness = [
                (
                    r * 
