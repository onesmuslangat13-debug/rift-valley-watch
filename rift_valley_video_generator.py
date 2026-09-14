from pathlib import Path
from datetime import datetime
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION:
# RVW_VIDEO_V28_REAL_MULTIPHOTO_EDITORIAL
#
# PURPOSE
# ------------------------------------------------------------
# - Read data/selected_story.json
# - Read data/selected_script.json
# - Use real article photographs
# - NEVER fake multiple photographs
# - Deduplicate photographs
# - Use all genuinely available unique photographs
# - Use editorial information cards when photos are insufficient
# - No fake 1/5 -> 5/5 gallery counter
# - No repeated photograph masquerading as another scene
# - Generate narration
# - Measure narration duration
# - Build video to match narration
# - Use FFmpeg directly
# - Preserve successful V27 audio/video architecture
# - Produce:
#
#       output/rift_valley_watch_reel.mp4
#
# OUTPUT
# ------------------------------------------------------------
# 1080 x 1920
# 30 FPS
# H.264 video
# AAC audio
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

SCENE_IMAGE_DIR = VIDEO_WORK_DIR / "scene_images"
SCENE_VIDEO_DIR = VIDEO_WORK_DIR / "scene_videos"

VIDEO_ONLY_FILE = VIDEO_WORK_DIR / "video_only.mp4"
MUXED_TEMP_FILE = VIDEO_WORK_DIR / "final_mux_temp.mp4"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


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

# Maximum number of visual scenes.
MAX_SCENES = 6

MIN_FINAL_DURATION = 5.0
MAX_FINAL_DURATION = 120.0

AUDIO_PADDING_SECONDS = 0.20

JPEG_QUALITY = 94

# Minimum photo dimensions.
MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 300

# Visual fingerprint resize.
HASH_SIZE = 32

# A visual hash distance at or below this is considered
# essentially the same photograph.
DUPLICATE_HASH_THRESHOLD = 8


# ============================================================
# FONTS
# ============================================================

BOLD_FONT = None
REGULAR_FONT = None


# ============================================================
# COLORS
# ============================================================

BLACK = (8, 10, 14)
WHITE = (255, 255, 255)
LIGHT = (235, 238, 242)

RED = (215, 30, 45)
DARK_RED = (115, 12, 23)

GRAY = (145, 150, 158)
DARK_GRAY = (35, 39, 46)
MID_GRAY = (85, 90, 98)

GREEN = (50, 190, 115)
GOLD = (225, 178, 70)

TRANSPARENT_BLACK = (0, 0, 0, 185)


# ============================================================
# FONT INITIALIZATION
# ============================================================

def find_font(bold=True):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            return path

    return None


BOLD_FONT = find_font(True)
REGULAR_FONT = find_font(False)


def font(size, bold=True):
    path = BOLD_FONT if bold else REGULAR_FONT

    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass

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


def safe_upper(value):
    return clean(value).upper()


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    SCENE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def remove_old_render_files():
    print("")
    print("=" * 68)
    print("CLEANING OLD VIDEO WORK FILES")
    print("=" * 68)

    files_to_remove = [
        FINAL_VIDEO,
        NARRATION_FILE,
        VIDEO_ONLY_FILE,
        MUXED_TEMP_FILE,
    ]

    for path in files_to_remove:
        try:
            if path.exists():
                path.unlink()
                print("Removed:", path)
        except Exception as exc:
            print(
                "WARNING: Could not remove",
                path,
                ":",
                exc,
            )

    for directory in [
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]:
        try:
            if directory.exists():
                shutil.rmtree(directory)
                print(
                    "Removed directory:",
                    directory,
                )

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        except Exception as exc:
            print(
                "WARNING: Could not clean directory",
                directory,
                ":",
                exc,
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


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(
    command,
    timeout=900,
    description="FFmpeg command",
):
    print("")
    print("=" * 68)
    print(description)
    print("=" * 68)

    print("COMMAND:")
    print(" ".join(str(x) for x in command))
    print("")

    try:
        result = subprocess.run(
            [str(x) for x in command],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired as exc:
        print("")
        print("ERROR: Command timed out.")
        print(
            "Timeout:",
            timeout,
            "seconds",
        )

        if exc.stdout:
            print("")
            print("STDOUT:")
            print(exc.stdout)

        if exc.stderr:
            print("")
            print("STDERR:")
            print(exc.stderr)

        raise RuntimeError(
            f"{description} timed out after "
            f"{timeout} seconds."
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required executable was not found: "
            f"{command[0]}. Original error: {exc}"
        )

    except Exception as exc:
        raise RuntimeError(
            f"Could not execute {description}: {exc}"
        )

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("")
        print("STDERR:")
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code "
            f"{result.returncode}."
        )

    return result


# ============================================================
# FFPROBE HELPERS
# ============================================================

def probe_duration(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Cannot probe missing file: {path}"
        )

    result = subprocess.run(
        [
            FFPROBE,
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
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFprobe duration check failed for "
            f"{path}: {result.stderr.strip()}"
        )

    value = clean(result.stdout)

    if not value:
        raise RuntimeError(
            f"FFprobe returned no duration for {path}."
        )

    try:
        duration = float(value)
    except ValueError:
        raise RuntimeError(
            f"Invalid duration returned for "
            f"{path}: {value}"
        )

    if not math.isfinite(duration):
        raise RuntimeError(
            f"Invalid non-finite duration for {path}."
        )

    return duration


def probe_streams(path):
    path = Path(path)

    if not path.exists():
        return []

    result = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,"
            "r_frame_rate,avg_frame_rate,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    try:
        data = json.loads(result.stdout)
    except Exception:
        return []

    return data.get("streams", [])


def validate_video_file(
    path,
    require_audio=False,
    expected_duration=None,
    label="video",
):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"{label} does not exist: {path}"
        )

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError(
            f"{label} is suspiciously small: "
            f"{size} bytes"
        )

    duration = probe_duration(path)

    if duration < MIN_FINAL_DURATION:
        raise RuntimeError(
            f"{label} duration is too short: "
            f"{duration:.3f} seconds"
        )

    streams = probe_streams(path)

    video_stream = None
    audio_stream = None

    for stream in streams:
        codec_type = stream.get("codec_type")

        if (
            codec_type == "video"
            and video_stream is None
        ):
            video_stream = stream

        if (
            codec_type == "audio"
            and audio_stream is None
        ):
            audio_stream = stream

    if video_stream is None:
        raise RuntimeError(
            f"{label} contains no video stream."
        )

    if require_audio and audio_stream is None:
        raise RuntimeError(
            f"{label} contains no audio stream."
        )

    if video_stream.get("width") is not None:
        if int(video_stream["width"]) != WIDTH:
            raise RuntimeError(
                f"{label} width is "
                f"{video_stream['width']}, "
                f"expected {WIDTH}."
            )

    if video_stream.get("height") is not None:
        if int(video_stream["height"]) != HEIGHT:
            raise RuntimeError(
                f"{label} height is "
                f"{video_stream['height']}, "
                f"expected {HEIGHT}."
            )

    if expected_duration is not None:
        difference = abs(
            duration
            - float(expected_duration)
        )

        if difference > 1.0:
            raise RuntimeError(
                f"{label} duration mismatch. "
                f"Expected approximately "
                f"{expected_duration:.3f}s, "
                f"got {duration:.3f}s."
            )

    print("")
    print("=" * 68)
    print(f"{label.upper()} VERIFIED")
    print("=" * 68)
    print("File:", path)
    print("Size:", size, "bytes")
    print(
        "Duration:",
        f"{duration:.3f}",
        "seconds",
    )
    print(
        "Video:",
        video_stream.get("codec_name"),
        video_stream.get("width"),
        "x",
        video_stream.get("height"),
    )

    if audio_stream:
        print(
            "Audio:",
            audio_stream.get("codec_name"),
            audio_stream.get("sample_rate"),
            "Hz",
            audio_stream.get("channels"),
            "channels",
        )

    return duration


# ============================================================
# STORY / SCRIPT VALIDATION
# ============================================================

def validate_story_and_script(
    story,
    script,
):
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

    story_county = clean(
        story["county"]
    )

    script_county = clean(
        script["county"]
    )

    if (
        story_county.lower()
        != script_county.lower()
    ):
        raise RuntimeError(
            "COUNTY MISMATCH between story and script."
        )

    story_title = clean(
        story["title"]
    )

    script_title = clean(
        script["title"]
    )

    if story_title != script_title:
        raise RuntimeError(
            "TITLE MISMATCH between story and script."
        )

    story_url = clean(
        story["article_url"]
    )

    script_url = clean(
        script["article_url"]
    )

    if story_url != script_url:
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

    print(
        "County:",
        story_county,
    )

    print(
        "Title:",
        story_title,
    )

    print(
        "Source:",
        clean(story.get("source")),
    )

    print(
        "Published:",
        clean(
            story.get(
                "published_at_kenya"
            )
        ),
    )

    print(
        "Age:",
        clean(
            story.get("age_hours")
        ),
        "hours",
    )

    print(
        "Article:",
        story_url,
    )

    print(
        "Article images supplied:",
        len(story["image_paths"]),
    )


# ============================================================
# IMAGE RESOLUTION
# ============================================================

def resolve_image_paths(story):
    paths = []

    supplied = story.get(
        "image_paths",
        [],
    )

    if isinstance(
        supplied,
        list,
    ):
        for item in supplied:

            if not item:
                continue

            raw = str(item).strip()

            candidates = [
                BASE_DIR / raw,
                SOURCE_DIR / Path(raw).name,
            ]

            for candidate in candidates:

                try:

                    if (
                        candidate.exists()
                        and candidate.is_file()
                    ):
                        paths.append(
                            candidate.resolve()
                        )
                        break

                except Exception:
                    continue

    # Discover downloaded article images.
    patterns = [
        "story_image*.jpg",
        "story_image*.jpeg",
        "story_image*.png",
        "story_image*.webp",
    ]

    for pattern in patterns:

        for candidate in sorted(
            SOURCE_DIR.glob(pattern)
        ):

            try:

                if (
                    candidate.exists()
                    and candidate.is_file()
                ):
                    paths.append(
                        candidate.resolve()
                    )

            except Exception:
                continue

    unique_paths = []
    seen = set()

    for path in paths:

        key = str(path)

        if key in seen:
            continue

        seen.add(key)
        unique_paths.append(
            Path(path)
        )

    if not unique_paths:
        raise RuntimeError(
            "No article photographs found."
        )

    print("")
    print("=" * 68)
    print("ARTICLE PHOTOGRAPHS DISCOVERED")
    print("=" * 68)

    for index, path in enumerate(
        unique_paths,
        1,
    ):
        print(
            index,
            ":",
            path,
        )

    return unique_paths


# ============================================================
# IMAGE VALIDATION
# ============================================================

def prepare_image(path):
    path = Path(path)

    try:

        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:

            image.load()

            image = image.convert(
                "RGB"
            )

        if (
            image.width
            < MIN_IMAGE_WIDTH
            or image.height
            < MIN_IMAGE_HEIGHT
        ):
            raise RuntimeError(
                "Image resolution is too small."
            )

        return image

    except Exception as exc:

        raise RuntimeError(
            f"Could not validate article image "
            f"{path}: {exc}"
        )


# ============================================================
# VISUAL HASH / DEDUPLICATION
# ============================================================

def calculate_image_hash(path):
    """
    Creates a compact perceptual-style grayscale hash.

    This catches duplicate files that have different filenames
    and catches many resized/compressed copies of the same image.
    """

    try:

        with Image.open(path) as image:

            image = image.convert(
                "L"
            )

            image = ImageOps.fit(
                image,
                (
                    HASH_SIZE,
                    HASH_SIZE,
                ),
                method=Image.Resampling.LANCZOS,
            )

            pixels = list(
                image.getdata()
            )

        if not pixels:
            return None

        average = (
            sum(pixels)
            / float(len(pixels))
        )

        bits = "".join(
            "1"
            if value >= average
            else "0"
            for value in pixels
        )

        return bits

    except Exception:
        return None


def hamming_distance(
    hash_a,
    hash_b,
):
    if not hash_a or not hash_b:
        return 999999

    if len(hash_a) != len(hash_b):
        return 999999

    return sum(
        a != b
        for a, b in zip(
            hash_a,
            hash_b,
        )
    )


def file_sha256(path):
    try:

        digest = hashlib.sha256()

        with open(
            path,
            "rb",
        ) as handle:

            while True:

                chunk = handle.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    except Exception:
        return None


def deduplicate_images(paths):
    """
    Removes:
    - exact duplicate files
    - duplicate filenames resolving to same file
    - visually near-identical images
    """

    print("")
    print("=" * 68)
    print("DEDUPLICATING ARTICLE PHOTOGRAPHS")
    print("=" * 68)

    accepted = []

    exact_hashes = set()
    visual_hashes = []

    for path in paths:

        try:

            exact = file_sha256(path)

            if exact and exact in exact_hashes:

                print(
                    "DUPLICATE FILE REJECTED:",
                    path.name,
                )

                continue

            visual = calculate_image_hash(
                path
            )

            if visual:

                duplicate_visual = False

                for previous in visual_hashes:

                    distance = hamming_distance(
                        visual,
                        previous,
                    )

                    if (
                        distance
                        <= DUPLICATE_HASH_THRESHOLD
                    ):

                        duplicate_visual = True

                        print(
                            "VISUAL DUPLICATE REJECTED:",
                            path.name,
                            "| distance:",
                            distance,
                        )

                        break

                if duplicate_visual:
                    continue

            if exact:
                exact_hashes.add(
                    exact
                )

            if visual:
                visual_hashes.append(
                    visual
                )

            accepted.append(path)

            print(
                "UNIQUE PHOTO ACCEPTED:",
                path.name,
            )

        except Exception as exc:

            print(
                "WARNING: Deduplication failed "
                "for",
                path,
                ":",
                exc,
            )

            accepted.append(path)

    if not accepted:
        raise RuntimeError(
            "No unique article photographs "
            "remain after deduplication."
        )

    print("")
    print(
        "Unique photographs:",
        len(accepted),
    )

    return accepted


def validate_all_images(paths):
    valid = []

    print("")
    print("=" * 68)
    print("VALIDATING ARTICLE PHOTOGRAPHS")
    print("=" * 68)

    for path in paths:

        try:

            image = prepare_image(
                path
            )

            print(
                "VALID:",
                path.name,
                "|",
                image.width,
                "x",
                image.height,
            )

            valid.append(path)

        except Exception as exc:

            print(
                "WARNING: Skipping invalid image:",
                path,
                "|",
                exc,
            )

    if not valid:
        raise RuntimeError(
            "All supplied article photographs "
            "failed validation."
        )

    return valid


# ============================================================
# SOURCE PHOTO CLEANUP
# ============================================================

def clean_source_photo(image):
    """
    Makes a conservative editorial crop.

    Purpose:
    - remove obvious browser/page-edge artifacts
    - reduce visible broadcaster/page branding at extreme edges
    - preserve the central news photograph

    This is NOT intended to alter the actual event photo.
    """

    image = image.convert(
        "RGB"
    )

    width, height = image.size

    # Conservative crop: 3% from horizontal edges,
    # 2% from top/bottom.
    left = int(width * 0.03)
    right = int(width * 0.97)

    top = int(height * 0.02)
    bottom = int(height * 0.98)

    if (
        right - left
        >= width * 0.85
        and
        bottom - top
        >= height * 0.85
    ):
        image = image.crop(
            (
                left,
                top,
                right,
                bottom,
            )
        )

    return image


# ============================================================
# IMAGE CROPPING
# ============================================================

def cover_crop(
    image,
    width=WIDTH,
    height=HEIGHT,
    zoom=1.0,
    horizontal_bias=0.5,
    vertical_bias=0.5,
):
    image = clean_source_photo(
        image
    )

    target_ratio = (
        width
        / float(height)
    )

    src_width, src_height = (
        image.size
    )

    src_ratio = (
        src_width
        / float(src_height)
    )

    if src_ratio > target_ratio:

        crop_width = int(
            src_height
            * target_ratio
        )

        max_left = (
            src_width
            - crop_width
        )

        left = int(
            max_left
            * horizontal_bias
        )

        left = max(
            0,
            min(
                left,
                max_left,
            ),
        )

        image = image.crop(
            (
                left,
                0,
                left + crop_width,
                src_height,
            )
        )

    else:

        crop_height = int(
            src_width
            / target_ratio
        )

        max_top = (
            src_height
            - crop_height
        )

        top = int(
            max_top
            * vertical_bias
        )

        top = max(
            0,
            min(
                top,
                max_top,
            ),
        )

        image = image.crop(
            (
                0,
                top,
                src_width,
                top + crop_height,
            )
        )

    image = image.resize(
        (
            width,
            height,
        ),
        Image.Resampling.LANCZOS,
    )

    if zoom != 1.0:

        zoom_width = max(
            1,
            int(width / zoom),
        )

        zoom_height = max(
            1,
            int(height / zoom),
        )

        left = (
            width
            - zoom_width
        ) // 2

        top = (
            height
            - zoom_height
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
            (
                width,
                height,
            ),
            Image.Resampling.LANCZOS,
        )

    return image


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font_obj,
    max_width,
):
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
            (
                0,
                0,
            ),
            test,
            font=font_obj,
        )

        text_width = (
            bbox[2]
            - bbox[0]
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


def draw_wrapped_text(
    draw,
    text,
    xy,
    font_obj,
    fill,
    max_width,
    line_spacing=10,
):
    x, y = xy

    lines = wrap_text(
        draw,
        text,
        font_obj,
        max_width,
    )

    if not lines:
        return 0

    bbox = font_obj.getbbox(
        "Ag"
    )

    line_height = (
        bbox[3]
        - bbox[1]
    ) + line_spacing

    for index, line in enumerate(
        lines
    ):

        draw.text(
            (
                x,
                y
                + index * line_height,
            ),
            line,
            font=font_obj,
            fill=fill,
        )

    return (
        len(lines)
        * line_height
    )


# ============================================================
# GRADIENT
# ============================================================

def draw_gradient_overlay(
    image,
):
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
            0,
        ),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    # Top gradient.
    for y in range(
        0,
        650,
    ):

        ratio = y / 650.0

        alpha = int(
            210
            * (1.0 - ratio)
        )

        draw.line(
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                0,
                0,
                0,
                max(
                    0,
                    min(
                        210,
                        alpha,
                    ),
                ),
            ),
        )

    # Bottom gradient.
    bottom_start = (
        HEIGHT
        - 750
    )

    for y in range(
        bottom_start,
        HEIGHT,
    ):

        ratio = (
            y
            - bottom_start
        ) / 750.0

        alpha = int(
            220 * ratio
        )

        draw.line(
            (
                0,
                y,
                WIDTH,
                y,
            ),
            fill=(
                0,
                0,
                0,
                max(
                    0,
                    min(
                        220,
                        alpha,
                    ),
                ),
            ),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    )


# ============================================================
# TOP BRANDING
# ============================================================

def draw_top_bar(
    draw,
    county,
):
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            145,
        ),
        fill=BLACK,
    )

    draw.rectangle(
        (
            0,
            0,
            16,
            145,
        ),
        fill=RED,
    )

    draw.text(
        (
            48,
            32,
        ),
        "RIFT VALLEY WATCH",
        font=font(
            43,
            True,
        ),
        fill=WHITE,
    )

    county_text = (
        clean(county)
        .upper()
    )

    if county_text:
        county_text += (
            "  •  LATEST UPDATE"
        )

    draw.text(
        (
            50,
            91,
        ),
        county_text,
        font=font(
            24,
            True,
        ),
        fill=LIGHT,
    )

    badge_x = (
        WIDTH
        - 205
    )

    draw.rounded_rectangle(
        (
            badge_x,
            36,
            WIDTH - 35,
            91,
        ),
        radius=12,
        fill=RED,
    )

    draw.text(
        (
            badge_x + 85,
            63,
        ),
        "NEWS",
        font=font(
            24,
            True,
        ),
        fill=WHITE,
        anchor="mm",
    )


# ============================================================
# SOURCE FOOTER
# ============================================================

def draw_bottom_source(
    draw,
    source,
    published,
):
    y_top = (
        HEIGHT
        - 245
