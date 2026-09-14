from pathlib import Path
from datetime import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION: RVW_VIDEO_V26_DURATION_SYNC
#
# PURPOSE
# ------------------------------------------------------------
# - Read selected_story.json
# - Read selected_script.json
# - Use real article photographs only
# - Use multiple article photos/scenes
# - Generate narration
# - Generate professional 1080x1920 vertical reel
# - Keep video duration synchronized with narration
# - Never intentionally cut narration short
# - Produce:
#       output/rift_valley_watch_reel.mp4
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

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
NARRATION_FILE = AUDIO_DIR / "narration.mp3"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 30

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

CRF = 20
PRESET = "medium"

MIN_FINAL_DURATION = 5.0

SCENE_COUNT = 5

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]

BOLD_FONT = None
REGULAR_FONT = None


# ============================================================
# COLORS
# ============================================================

# Professional newsroom palette.
BLACK = (8, 10, 14)
WHITE = (255, 255, 255)
LIGHT = (235, 238, 242)
RED = (215, 30, 45)
DARK_RED = (115, 12, 23)
GRAY = (145, 150, 158)
DARK_GRAY = (35, 39, 46)
TRANSPARENT_BLACK = (0, 0, 0, 175)


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(bold=True):
    if bold:
        preferred = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        preferred = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for path in preferred:
        if Path(path).exists():
            return path

    return None


BOLD_FONT = find_font(True)
REGULAR_FONT = find_font(False)


def font(size, bold=True):
    path = BOLD_FONT if bold else REGULAR_FONT

    if path:
        return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def ensure_dirs():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file is missing: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file {path}: {exc}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"JSON file is not an object: {path}"
        )

    return data


def run_command(command, timeout=900):
    print("")
    print("COMMAND:")
    print(" ".join(str(x) for x in command))
    print("")

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}"
        )

    return result


# ============================================================
# FFPROBE
# ============================================================

def probe_duration(path):
    try:
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
            capture_output=True,
            text=True,
            check=True,
        )

        return float(
            result.stdout.strip()
        )

    except Exception as exc:
        raise RuntimeError(
            f"Could not determine duration of {path}: {exc}"
        )


def probe_streams(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        return json.loads(
            result.stdout
        ).get("streams", [])

    except Exception:
        return []


# ============================================================
# VALIDATE STORY/SCRIPT
# ============================================================

def validate_story_and_script(story, script):
    required_story = [
        "title",
        "county",
        "article_url",
        "source",
        "image_paths",
    ]

    for key in required_story:
        if not story.get(key):
            raise RuntimeError(
                f"Selected story missing: {key}"
            )

    required_script = [
        "title",
        "county",
        "article_url",
        "script",
    ]

    for key in required_script:
        if not script.get(key):
            raise RuntimeError(
                f"Selected script missing: {key}"
            )

    if story["county"] != script["county"]:
        raise RuntimeError(
            "COUNTY MISMATCH between story and script."
        )

    if story["title"] != script["title"]:
        raise RuntimeError(
            "TITLE MISMATCH between story and script."
        )

    if story["article_url"] != script["article_url"]:
        raise RuntimeError(
            "ARTICLE URL MISMATCH between story and script."
        )

    if not isinstance(
        story["image_paths"],
        list,
    ):
        raise RuntimeError(
            "image_paths is not a list."
        )

    if not story["image_paths"]:
        raise RuntimeError(
            "No article images were supplied."
        )

    print("")
    print("=" * 68)
    print("SELECTED STORY VERIFIED")
    print("=" * 68)
    print("County:", story["county"])
    print("Title:", story["title"])
    print("Source:", story["source"])
    print("Published:", story.get("published_at_kenya", ""))
    print("Age:", story.get("age_hours", ""), "hours")
    print("Article:", story["article_url"])
    print("Images:", len(story["image_paths"]))


# ============================================================
# IMAGE PATHS
# ============================================================

def resolve_image_paths(story):
    paths = []

    # Primary source is image_paths from selected_story.json.
    for item in story.get("image_paths", []):
        if not item:
            continue

        path = BASE_DIR / str(item)

        if not path.exists():
            # Try directly from SOURCE_DIR if only filename was stored.
            candidate = SOURCE_DIR / Path(str(item)).name

            if candidate.exists():
                path = candidate

        if path.exists() and path.is_file():
            paths.append(path)

    # Fallback to actual generated files.
    if not paths:
        paths = sorted(
            SOURCE_DIR.glob(
                "story_image*.jpg"
            )
        )

    # Deduplicate.
    unique = []
    seen = set()

    for path in paths:
        key = str(path.resolve())

        if key in seen:
            continue

        seen.add(key)
        unique.append(path)

    if not unique:
        raise RuntimeError(
            "No real article photographs found."
        )

    return unique


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_image(path):
    try:
        image = Image.open(path)
        image.load()

        image = image.convert("RGB")

        return image

    except Exception as exc:
        raise RuntimeError(
            f"Could not open article image {path}: {exc}"
        )


def cover_crop(image, width=WIDTH, height=HEIGHT, zoom=1.0):
    image = image.copy()

    target_ratio = width / float(height)

    src_width, src_height = image.size
    src_ratio = src_width / float(src_height)

    if src_ratio > target_ratio:
        # Crop width.
        crop_width = int(
            src_height * target_ratio
        )

        left = (
            src_width - crop_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + crop_width,
                src_height,
            )
        )

    else:
        # Crop height.
        crop_height = int(
            src_width / target_ratio
        )

        top = (
            src_height - crop_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                src_width,
                top + crop_height,
            )
        )

    image = image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )

    if zoom != 1.0:
        zoom_width = int(width / zoom)
        zoom_height = int(height / zoom)

        left = (
            width - zoom_width
        ) // 2

        top = (
            height - zoom_height
        ) // 2

        image = image.crop(
            (
                left,
                top,
                left + zoom_width,
                top + zoom_height,
            )
        )

        image = image.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )

    return image


def make_background(image):
    background = cover_crop(
        image,
        WIDTH,
        HEIGHT,
        zoom=1.0,
    )

    # Darken slightly for broadcast text readability.
    overlay = Image.new(
        "RGBA",
        background.size,
        (0, 0, 0, 90),
    )

    background = Image.alpha_composite(
        background.convert("RGBA"),
        overlay,
    )

    return background.convert("RGB")


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font_obj, max_width):
    words = clean(text).split()

    if not words:
        return []

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
            font=font_obj,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    text,
    xy,
    font_obj,
    fill,
    max_width,
    line_spacing=10,
    anchor="la",
):
    x, y = xy

    lines = wrap_text(
        draw,
        text,
        font_obj,
        max_width,
    )

    bbox = font_obj.getbbox("Ag")
    line_height = (
        bbox[3] - bbox[1]
    ) + line_spacing

    for index, line in enumerate(lines):
        draw.text(
            (
                x,
                y + index * line_height,
            ),
            line,
            font=font_obj,
            fill=fill,
            anchor=anchor,
        )

    return len(lines) * line_height


# ============================================================
# NEWSROOM GRAPHICS
# ============================================================

def draw_top_bar(
    draw,
    county,
    source,
    published,
):
    # Main top strip.
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            125,
        ),
        fill=BLACK,
    )

    # Red live indicator.
    draw.rectangle(
        (
            0,
            0,
            15,
            125,
        ),
        fill=RED,
    )

    draw.text(
        (
            48,
            35,
        ),
        "RIFT VALLEY WATCH",
        font=font(42, True),
        fill=WHITE,
    )

    draw.text(
        (
            50,
            82,
        ),
        f"{county.upper()}  •  LATEST UPDATE",
        font=font(24, True),
        fill=LIGHT,
    )

    # Small LIVE badge.
    badge_x = WIDTH - 180

    draw.rounded_rectangle(
        (
            badge_x,
            35,
            WIDTH - 35,
            85,
        ),
        radius=12,
        fill=RED,
    )

    draw.text(
        (
            badge_x + 70,
            60,
        ),
        "NEWS",
        font=font(23, True),
        fill=WHITE,
        anchor="mm",
    )


def draw_bottom_source(
    draw,
    source,
    published,
):
    y_top = HEIGHT - 215

    draw.rectangle(
        (
            0,
            y_top,
            WIDTH,
            HEIGHT,
        ),
        fill=(5, 7, 10),
    )

    draw.rectangle(
        (
            0,
            y_top,
            WIDTH,
            y_top + 7,
        ),
        fill=RED,
    )

    source_display = source.upper()

    if not source_display:
        source_display = "NEWS SOURCE"

    draw.text
