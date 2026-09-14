from pathlib import Path
from datetime import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION: RVW_VIDEO_V27_STABLE_FINAL_MP4
#
# PURPOSE
# ------------------------------------------------------------
# - Read data/selected_story.json
# - Read data/selected_script.json
# - Use real article photographs
# - Use multiple article-photo scenes
# - Generate narration
# - Measure narration duration
# - Build video to match narration duration
# - Avoid premature video ending
# - Avoid fragile MoviePy rendering
# - Use FFmpeg directly
# - Capture FFmpeg errors
# - Validate every intermediate file
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

SCENE_COUNT = 5

MIN_FINAL_DURATION = 5.0
MAX_FINAL_DURATION = 120.0

AUDIO_PADDING_SECONDS = 0.20

JPEG_QUALITY = 94


# ============================================================
# FONTS
# ============================================================

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSansNarrow-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSansNarrow-Regular.ttf",
]

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
TRANSPARENT_BLACK = (0, 0, 0, 175)


# ============================================================
# FONT INITIALIZATION
# ============================================================

def find_font(bold=True):
    candidates = []

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
            print("WARNING: Could not remove", path, ":", exc)

    for directory in [
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]:
        try:
            if directory.exists():
                shutil.rmtree(directory)
                print("Removed directory:", directory)

            directory.mkdir(parents=True, exist_ok=True)

        except Exception as exc:
            print(
                "WARNING: Could not clean directory",
                directory,
                ":",
                exc,
            )

    print("Old render files cleaned.")


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
        print("Timeout:", timeout, "seconds")

        if exc.stdout:
            print("")
            print("STDOUT:")
            print(exc.stdout)

        if exc.stderr:
            print("")
            print("STDERR:")
            print(exc.stderr)

        raise RuntimeError(
            f"{description} timed out after {timeout} seconds."
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required executable was not found: {command[0]}. "
            f"Original error: {exc}"
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
    if not Path(path).exists():
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
            f"FFprobe duration check failed for {path}: "
            f"{result.stderr.strip()}"
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
            f"Invalid duration returned for {path}: {value}"
        )

    if not math.isfinite(duration):
        raise RuntimeError(
            f"Invalid non-finite duration for {path}."
        )

    return duration


def probe_streams(path):
    if not Path(path).exists():
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

        if codec_type == "video" and video_stream is None:
            video_stream = stream

        if codec_type == "audio" and audio_stream is None:
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
                f"{video_stream['width']}, expected {WIDTH}."
            )

    if video_stream.get("height") is not None:
        if int(video_stream["height"]) != HEIGHT:
            raise RuntimeError(
                f"{label} height is "
                f"{video_stream['height']}, expected {HEIGHT}."
            )

    if expected_duration is not None:
        difference = abs(
            duration - float(expected_duration)
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
    print("Duration:", f"{duration:.3f}", "seconds")
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

    story_county = clean(story["county"])
    script_county = clean(script["county"])

    if story_county.lower() != script_county.lower():
        raise RuntimeError(
            "COUNTY MISMATCH between story and script."
        )

    story_title = clean(story["title"])
    script_title = clean(script["title"])

    if story_title != script_title:
        raise RuntimeError(
            "TITLE MISMATCH between story and script."
        )

    story_url = clean(story["article_url"])
    script_url = clean(script["article_url"])

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
    print("County:", story_county)
    print("Title:", story_title)
    print("Source:", clean(story.get("source")))
    print(
        "Published:",
        clean(story.get("published_at_kenya"))
    )
    print(
        "Age:",
        clean(story.get("age_hours")),
        "hours"
    )
    print("Article:", story_url)
    print(
        "Article images supplied:",
        len(story["image_paths"])
    )


# ============================================================
# IMAGE RESOLUTION
# ============================================================

def resolve_image_paths(story):
    paths = []

    supplied = story.get("image_paths", [])

    if isinstance(supplied, list):
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
                        paths.append(candidate.resolve())
                        break
                except Exception:
                    continue

    # Also discover all downloaded story images.
    discovered = sorted(
        SOURCE_DIR.glob("story_image*.jpg")
    )

    for candidate in discovered:
        if candidate.exists() and candidate.is_file():
            paths.append(candidate.resolve())

    # Other valid image extensions if available.
    for pattern in [
        "story_image*.jpeg",
        "story_image*.png",
        "story_image*.webp",
    ]:
        for candidate in sorted(
            SOURCE_DIR.glob(pattern)
        ):
            if candidate.exists() and candidate.is_file():
                paths.append(candidate.resolve())

    unique = []
    seen = set()

    for path in paths:
        key = str(path)

        if key in seen:
            continue

        seen.add(key)
        unique.append(Path(path))

    if not unique:
        raise RuntimeError(
            "No real article photographs found."
        )

    print("")
    print("=" * 68)
    print("ARTICLE PHOTOGRAPHS FOUND")
    print("=" * 68)

    for index, path in enumerate(unique, 1):
        print(index, ":", path)

    return unique


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
            image = image.convert("RGB")

        if image.width < 200 or image.height < 200:
            raise RuntimeError(
                "Image resolution is too small."
            )

        return image

    except Exception as exc:
        raise RuntimeError(
            f"Could not validate article image "
            f"{path}: {exc}"
        )


def validate_all_images(paths):
    valid = []

    print("")
    print("=" * 68)
    print("VALIDATING ARTICLE PHOTOGRAPHS")
    print("=" * 68)

    for path in paths:
        try:
            image = prepare_image(path)

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
            "All supplied article photographs failed validation."
        )

    return valid


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
    image = image.copy()

    target_ratio = width / float(height)

    src_width, src_height = image.size
    src_ratio = src_width / float(src_height)

    if src_ratio > target_ratio:
        crop_width = int(
            src_height * target_ratio
        )

        max_left = src_width - crop_width

        left = int(
            max_left * horizontal_bias
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
            src_width / target_ratio
        )

        max_top = src_height - crop_height

        top = int(
            max_top * vertical_bias
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
        (width, height),
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
        )

    return len(lines) * line_height


# ============================================================
# GRAPHICS
# ============================================================

def draw_top_bar(
    draw,
    county,
    source,
    published,
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
        font=font(43, True),
        fill=WHITE,
    )

    county_text = clean(county).upper()

    if county_text:
        county_text += "  •  LATEST UPDATE"

    draw.text(
        (
            50,
            91,
        ),
        county_text,
        font=font(24, True),
        fill=LIGHT,
    )

    badge_x = WIDTH - 205

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
        font=font(24, True),
        fill=WHITE,
        anchor="mm",
    )


def draw_bottom_source(
    draw,
    source,
    published,
):
    y_top = HEIGHT - 245

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

    source_display = clean(source).upper()

    if not source_display:
        source_display = "NEWS SOURCE"

    draw.text(
        (
            48,
            y_top + 38,
        ),
        "SOURCE",
        font=font(22, True),
        fill=GRAY,
    )

    draw.text(
        (
            48,
            y_top + 75,
        ),
        source_display,
        font=font(32, True),
        fill=WHITE,
    )

    published_display = clean(published)

    if published_display:
        draw.text(
            (
                48,
                y_top + 126,
            ),
            "PUBLISHED  " + published_display,
            font=font(21, False),
            fill=LIGHT,
        )

    draw.text(
        (
            48,
            y_top + 184,
        ),
        "RIFT VALLEY WATCH  •  VERIFIED NEWS UPDATE",
        font=font(20, True),
        fill=GRAY,
    )


def draw_gradient_overlay(image):
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    pixels = overlay.load()

    top_start = 0
    top_end = 600

    bottom_start = HEIGHT - 700
    bottom_end = HEIGHT

    for y in range(HEIGHT):
        if y < top_end:
            ratio = (
                (y - top_start)
                / float(top_end - top_start)
            )

            alpha = int(
                210 * (1.0 - ratio)
            )

        elif y >= bottom_start:
            ratio = (
                (y - bottom_start)
                / float(bottom_end - bottom_start)
            )

            alpha = int(
                210 * ratio
            )

        else:
            alpha = 25

        for x in range(WIDTH):
            pixels[x, y] = (
                0,
                0,
                0,
                max(0, min(210, alpha)),
            )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    )


def add_scene_graphics(
    image,
    title,
    county,
    source,
    published,
    scene_number,
    scene_total,
    zoom,
    horizontal_bias,
    vertical_bias,
):
    base = cover_crop(
        image,
        WIDTH,
        HEIGHT,
        zoom=zoom,
        horizontal_bias=horizontal_bias,
        vertical_bias=vertical_bias,
    )

    base = draw_gradient_overlay(
        base
    )

    draw = ImageDraw.Draw(base)

    # Top newsroom bar.
    draw_top_bar(
        draw,
        county,
        source,
        published,
    )

    # Scene counter.
    counter_text = (
        f"{scene_number}/{scene_total}"
    )

    draw.rounded_rectangle(
        (
            WIDTH - 145,
            158,
            WIDTH - 35,
            210,
        ),
        radius=12,
        fill=(0, 0, 0, 185),
        outline=RED,
        width=2,
    )

    draw.text(
        (
            WIDTH - 90,
            184,
        ),
        counter_text,
        font=font(22, True),
        fill=WHITE,
        anchor="mm",
    )

    # Main headline panel.
    panel_top = 1040
    panel_bottom = 1510

    draw.rounded_rectangle(
        (
            38,
            panel_top,
            WIDTH - 38,
            panel_bottom,
        ),
        radius=24,
        fill=(5, 7, 10, 205),
        outline=(255, 255, 255, 38),
        width=2,
    )

    draw.rectangle(
        (
            38,
            panel_top,
            54,
            panel_bottom,
        ),
        fill=RED,
    )

    draw.text(
        (
            82,
            panel_top + 42,
        ),
        "LATEST",
        font=font(25, True),
        fill=RED,
    )

    title_font = font(48, True)

    draw_wrapped_text(
        draw,
        title,
        (
            82,
            panel_top + 95,
        ),
        title_font,
        WHITE,
        WIDTH - 160,
        line_spacing=13,
    )

    draw_bottom_source(
        draw,
        source,
        published,
    )

    # Small branding mark.
    draw.text(
        (
            WIDTH - 52,
            HEIGHT - 270,
        ),
        "RVW",
        font=font(22, True),
        fill=GRAY,
        anchor="ra",
    )

    return base.convert("RGB")


# ============================================================
# NARRATION
# ============================================================

def normalize_script(text):
    text = clean(text)

    if not text:
        raise RuntimeError(
            "Narration script is empty."
        )

    # Remove accidental markdown.
    text = re.sub(
        r"[*_`#]+",
        "",
        text,
    )

    # Prevent extremely long whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def generate_narration(script_text):
    script_text = normalize_script(
        script_text
    )

    print("")
    print("=" * 68)
    print("GENERATING NARRATION")
    print("=" * 68)

    print("Characters:", len(script_text))
    print("")
    print(script_text)
    print("")

    # Generate to temporary file first.
    temporary = AUDIO_DIR / "narration_temp.mp3"

    try:
        if temporary.exists():
            temporary.unlink()
    except Exception:
        pass

    try:
        tts = gTTS(
            text=script_text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(temporary)
        )

    except Exception as exc:
        raise RuntimeError(
            f"gTTS narration generation failed: {exc}"
        )

    if not temporary.exists():
        raise RuntimeError(
            "gTTS did not create narration_temp.mp3."
        )

    size = temporary.stat().st_size

    if size < 1000:
        raise RuntimeError(
            f"Narration MP3 is too small: {size} bytes."
        )

    # Validate audio with ffprobe.
    result = subprocess.run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(temporary),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFprobe could not validate generated narration: "
            + result.stderr.strip()
        )

    try:
        duration = float(
            result.stdout.strip()
        )
    except Exception:
        raise RuntimeError(
            "Generated narration has no valid duration."
        )

    if duration < 1.0:
        raise RuntimeError(
            f"Narration duration is too short: {duration:.3f}s"
        )

    shutil.move(
        str(temporary),
        str(NARRATION_FILE),
    )

    print("")
    print("Narration generated successfully.")
    print("File:", NARRATION_FILE)
    print("Size:", NARRATION_FILE.stat().st_size)
    print(
        "Duration:",
        f"{duration:.3f}",
        "seconds",
    )

    return duration


# ============================================================
# SCENE TIMING
# ============================================================

def calculate_scene_durations(
    narration_duration,
):
    duration = max(
        float(narration_duration),
        MIN_FINAL_DURATION,
    )

    # Keep five scenes even for short narration.
    if duration < SCENE_COUNT:
        SCENE_COUNT_LOCAL = 1
    else:
        SCENE_COUNT_LOCAL = SCENE_COUNT

    if SCENE_COUNT_LOCAL == 1:
        return [duration]

    base = duration / float(
        SCENE_COUNT_LOCAL
    )

    durations = [
        base
        for _ in range(SCENE_COUNT_LOCAL)
    ]

    # Correct floating-point rounding.
    durations[-1] = duration - sum(
        durations[:-1]
    )

    return durations


# ============================================================
# SCENE IMAGE CREATION
# ============================================================

def create_scene_images(
    image_paths,
    story,
    narration_duration,
):
    title = clean(story.get("title"))
    county = clean(story.get("county"))
    source = clean(story.get("source"))
    published = clean(
        story.get("published_at_kenya")
    )

    scene_durations = calculate_scene_durations(
        narration_duration
    )

    scene_count = len(scene_durations)

    if not image_paths:
        raise RuntimeError(
            "No images available for scene generation."
        )

    print("")
    print("=" * 68)
    print("CREATING SCENE IMAGES")
    print("=" * 68)

    generated = []

    for index in range(scene_count):
        source_path = image_paths[
            index % len(image_paths)
        ]

        image = prepare_image(
            source_path
        )

        # Slightly vary framing between scenes.
        zoom_values = [
            1.00,
            1.035,
            1.06,
            1.025,
            1.045,
        ]

        horizontal_values = [
            0.50,
            0.42,
            0.58,
            0.47,
            0.53,
        ]

        vertical_values = [
            0.50,
            0.46,
            0.54,
            0.48,
            0.52,
        ]

        zoom = zoom_values[
            index % len(zoom_values)
        ]

        horizontal_bias = horizontal_values[
            index % len(horizontal_values)
        ]

        vertical_bias = vertical_values[
            index % len(vertical_values)
        ]

        scene = add_scene_graphics(
            image=image,
            title=title,
            county=county,
            source=source,
            published=published,
            scene_number=index + 1,
            scene_total=scene_count,
            zoom=zoom,
            horizontal_bias=horizontal_bias,
            vertical_bias=vertical_bias,
        )

        scene_path = (
            SCENE_IMAGE_DIR
            / f"scene_{index + 1:02d}.jpg"
        )

        scene.save(
            scene_path,
            "JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
        )

        if not scene_path.exists():
            raise RuntimeError(
                f"Scene image was not generated: {scene_path}"
            )

        if scene_path.stat().st_size < 10000:
            raise RuntimeError(
                f"Scene image is too small: {scene_path}"
            )

        print(
            f"Scene {index + 1}:",
            scene_path.name,
            "| source:",
            source_path.name,
            "| duration:",
            f"{scene_durations[index]:.3f}s",
        )

        generated.append(
            (
                scene_path,
                scene_durations[index],
            )
        )

    if len(generated) != scene_count:
        raise RuntimeError(
            "Not all scene images were generated."
        )

    return generated


# ============================================================
# INDIVIDUAL SCENE VIDEO
# ============================================================

def create_scene_video(
    image_path,
    duration,
    scene_number,
):
    output = (
        SCENE_VIDEO_DIR
        / f"scene_{scene_number:02d}.mp4"
    )

    if output.exists():
        output.unlink()

    # Use one still image as a video source.
    #
    # -loop 1 keeps image available for entire duration.
    # -t sets exact scene duration.
    # -pix_fmt yuv420p makes it broadly compatible.
    command = [
        FFMPEG,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(image_path),
        "-t",
        f"{float(duration):.3f}",
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
        VIDEO_CODEC,
        "-preset",
        PRESET,
        "-crf",
        str(CRF),
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(output),
    ]

    run_command(
        command,
        timeout=300,
        description=(
            f"RENDERING SCENE {scene_number}"
        ),
    )

    if not output.exists():
        raise RuntimeError(
            f"Scene video was not generated: {output}"
        )

    validate_video_file(
        output,
        require_audio=False,
        expected_duration=duration,
        label=f"Scene {scene_number}",
    )

    return output


# ============================================================
# CREATE ALL SCENE VIDEOS
# ============================================================

def create_scene_videos(scene_data):
    print("")
    print("=" * 68)
    print("CREATING SCENE VIDEOS")
    print("=" * 68)

    videos = []

    for index, (image_path, duration) in enumerate(
        scene_data,
        start=1,
    ):
        video = create_scene_video(
            image_path=image_path,
            duration=duration,
            scene_number=index,
        )

        videos.append(video)

    if not videos:
        raise RuntimeError(
            "No scene videos were generated."
        )

    print("")
    print(
        "Scene videos generated:",
        len(videos),
    )

    return videos


# ============================================================
# CONCATENATE SCENE VIDEOS
# ============================================================

def create_concat_file(scene_videos):
    concat_file = (
        VIDEO_WORK_DIR
        / "scenes_concat.txt"
    )

    lines = []

    for video in scene_videos:
        absolute_path = Path(video).resolve()

        # FFmpeg concat demuxer escaping.
        escaped = str(
            absolute_path
        ).replace(
            "'",
            "'\\''",
        )

        lines.append(
            f"file '{escaped}'"
        )

    concat_file.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return concat_file


def concatenate_scene_videos(
    scene_videos,
):
    print("")
    print("=" * 68)
    print("CONCATENATING SCENE VIDEOS")
    print("=" * 68)

    concat_file = create_concat_file(
        scene_videos
    )

    if VIDEO_ONLY_FILE.exists():
        VIDEO_ONLY_FILE.unlink()

    command = [
        FFMPEG,
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
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        PRESET,
        "-crf",
        str(CRF),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-an",
        "-movflags",
        "+faststart",
        str(VIDEO_ONLY_FILE),
    ]

    run_command(
        command,
        timeout=600,
        description="CONCATENATING SCENES",
    )

    if not VIDEO_ONLY_FILE.exists():
        raise RuntimeError(
            "FFmpeg finished but video_only.mp4 "
            "was not generated."
        )

    validate_video_file(
        VIDEO_ONLY_FILE,
        require_audio=False,
        label="Concatenated video",
    )

    return VIDEO_ONLY_FILE


# ============================================================
# AUDIO NORMALIZATION / MUX
# ============================================================

def mux_audio_and_video(
    video_file,
    narration_duration,
):
    print("")
    print("=" * 68)
    print("MUXING VIDEO + NARRATION")
    print("=" * 68)

    if MUXED_TEMP_FILE.exists():
        MUXED_TEMP_FILE.unlink()

    # The video is deliberately made slightly longer than the
    # narration. The audio is padded very slightly and then the
    # final duration is forced to the narration duration plus
    # a tiny safety margin.
    #
    # Crucially, -shortest is NOT used.
    final_duration = max(
        float(narration_duration)
        + AUDIO_PADDING_SECONDS,
        MIN_FINAL_DURATION,
    )

    command = [
        FFMPEG,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_file),
        "-i",
        str(NARRATION_FILE),
        "-filter_complex",
        (
            "[1:a]"
            "aresample=async=1:first_pts=0,"
            "apad"
            "[a]"
        ),
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-t",
        f"{final_duration:.3f}",
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        PRESET,
        "-crf",
        str(CRF),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(MUXED_TEMP_FILE),
    ]

    run_command(
        command,
        timeout=900,
        description="MUXING FINAL VIDEO AND AUDIO",
    )

    if not MUXED_TEMP_FILE.exists():
        raise RuntimeError(
            "FFmpeg completed but final temporary MP4 "
            "was not generated."
        )

    validate_video_file(
        MUXED_TEMP_FILE,
        require_audio=True,
        label="Muxed final video",
    )

    return MUXED_TEMP_FILE


# ============================================================
# FINAL VIDEO SAFETY PASS
# ============================================================

def final_duration_safety_pass(
    source_file,
    narration_duration,
):
    print("")
    print("=" * 68)
    print("FINAL DURATION SAFETY PASS")
    print("=" * 68)

    current_duration = probe_duration(
        source_file
    )

    target_duration = max(
        float(narration_duration)
        + AUDIO_PADDING_SECONDS,
        MIN_FINAL_DURATION,
    )

    print(
        "Current duration:",
        f"{current_duration:.3f}s",
    )

    print(
        "Target duration:",
        f"{target_duration:.3f}s",
    )

    # If current file is already appropriate,
    # simply copy it into the final destination.
    if current_duration >= (
        float(narration_duration) - 0.25
    ):
        print(
            "Duration is sufficient. "
            "No additional trim required."
        )

        if FINAL_VIDEO.exists():
            FINAL_VIDEO.unlink()

        shutil.copy2(
            source_file,
            FINAL_VIDEO,
        )

        return FINAL_VIDEO

    # Emergency fallback:
    # extend the video using the final frame while
    # keeping the full narration.
    print(
        "WARNING: Video is shorter than narration."
    )

    print(
        "Applying final-frame extension fallback."
    )

    fallback = (
        VIDEO_WORK_DIR
        / "duration_fallback.mp4"
    )

    if fallback.exists():
        fallback.unlink()

    extension_command = [
        FFMPEG,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_file),
        "-vf",
        (
            f"tpad=stop_mode=clone:"
            f"stop_duration={max(0.5, target_duration - current_duration):.3f}"
        ),
        "-t",
        f"{target_duration:.3f}",
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        PRESET,
        "-crf",
        str(CRF),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(fallback),
    ]

    run_command(
        extension_command,
        timeout=600,
        description="FINAL FRAME EXTENSION FALLBACK",
    )

    if not fallback.exists():
        raise RuntimeError(
            "Final-frame fallback failed to create MP4."
        )

    validate_video_file(
        fallback,
        require_audio=True,
        label="Fallback final video",
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    shutil.copy2(
        fallback,
        FINAL_VIDEO,
    )

    return FINAL_VIDEO


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_final_output(
    narration_duration,
):
    print("")
    print("=" * 68)
    print("VALIDATING FINAL RIFT VALLEY WATCH MP4")
    print("=" * 68)

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not generated."
        )

    size = FINAL_VIDEO.stat().st_size

    print(
        "Final file:",
        FINAL_VIDEO,
    )

    print(
        "Final size:",
        size,
        "bytes",
    )

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    duration = validate_video_file(
        FINAL_VIDEO,
        require_audio=True,
        label="Final MP4",
    )

    difference = abs(
        duration
        - float(narration_duration)
    )

    print("")
    print(
        "Narration duration:",
        f"{float(narration_duration):.3f}s",
    )

    print(
        "Final MP4 duration:",
        f"{duration:.3f}s",
    )

    print(
        "Duration difference:",
        f"{difference:.3f}s",
    )

    # The final video may contain a tiny safety margin.
    # It must never be substantially shorter than narration.
    if duration + 0.35 < float(
        narration_duration
    ):
        raise RuntimeError(
            "FINAL MP4 IS SHORTER THAN NARRATION. "
            "Narration would be cut."
        )

    streams = probe_streams(
        FINAL_VIDEO
    )

    has_video = any(
        stream.get("codec_type") == "video"
        for stream in streams
    )

    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in streams
    )

    if not has_video:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if not has_audio:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    print("")
    print("=" * 68)
    print("FINAL MP4 VALIDATION PASSED")
    print("=" * 68)
    print("File:", FINAL_VIDEO)
    print("Size:", size, "bytes")
    print(
        "Resolution:",
        WIDTH,
        "x",
        HEIGHT,
    )
    print(
        "FPS target:",
        FPS,
    )
    print(
        "Duration:",
        f"{duration:.3f}s",
    )
    print("Video stream: YES")
    print("Audio stream: YES")

    return True


# ============================================================
# CLEANUP TEMPORARY FILES
# ============================================================

def cleanup_temporary_files():
    print("")
    print("=" * 68)
    print("CLEANING TEMPORARY RENDER FILES")
    print("=" * 68)

    temporary_names = [
        "narration_temp.mp3",
        "final_mux_temp.mp4",
        "duration_fallback.mp4",
    ]

    for name in temporary_names:
        path = (
            AUDIO_DIR / name
            if name.endswith(".mp3")
            else VIDEO_WORK_DIR / name
        )

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


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("VERSION: RVW_VIDEO_V27_STABLE_FINAL_MP4")
    print("=" * 68)

    ensure_dirs()

    print("")
    print("Base directory:")
    print(BASE_DIR)

    print("")
    print("Story file:")
    print(STORY_FILE)

    print("")
    print("Script file:")
    print(SCRIPT_FILE)

    print("")
    print("Output file:")
    print(FINAL_VIDEO)

    # --------------------------------------------------------
    # 1. Confirm FFmpeg
    # --------------------------------------------------------

    print("")
    print("=" * 68)
    print("VERIFYING FFMPEG")
    print("=" * 68)

    ffmpeg_check = subprocess.run(
        [
            FFMPEG,
            "-version",
        ],
        capture_output=True,
        text=True,
    )

    if ffmpeg_check.returncode != 0:
        raise RuntimeError(
            "FFmpeg is not available."
        )

    ffmpeg_first_line = (
        ffmpeg_check.stdout.splitlines()[0]
        if ffmpeg_check.stdout
        else "FFmpeg available"
    )

    print(ffmpeg_first_line)

    ffprobe_check = subprocess.run(
        [
            FFPROBE,
            "-version",
        ],
        capture_output=True,
        text=True,
    )

    if ffprobe_check.returncode != 0:
        raise RuntimeError(
            "FFprobe is not available."
        )

    ffprobe_first_line = (
        ffprobe_check.stdout.splitlines()[0]
        if ffprobe_check.stdout
        else "FFprobe available"
    )

    print(ffprobe_first_line)

    # --------------------------------------------------------
    # 2. Load story and script
    # --------------------------------------------------------

    story = load_json(
        STORY_FILE
    )

    script = load_json(
        SCRIPT_FILE
    )

    validate_story_and_script(
        story,
        script,
    )

    # --------------------------------------------------------
    # 3. Resolve article photos
    # --------------------------------------------------------

    image_paths = resolve_image_paths(
        story
    )

    image_paths = validate_all_images(
        image_paths
    )

    # --------------------------------------------------------
    # 4. Generate narration
    # --------------------------------------------------------

    narration_text = script.get(
        "script",
        "",
    )

    narration_duration = generate_narration(
        narration_text
    )

    # --------------------------------------------------------
    # 5. Create scene images
    # --------------------------------------------------------

    scene_data = create_scene_images(
        image_paths=image_paths,
        story=story,
        narration_duration=narration_duration,
    )

    # --------------------------------------------------------
    # 6. Create scene videos
    # --------------------------------------------------------

    scene_videos = create_scene_videos(
        scene_data
    )

    # --------------------------------------------------------
    # 7. Concatenate scene videos
    # --------------------------------------------------------

    concatenated_video = (
        concatenate_scene_videos(
            scene_videos
        )
    )

    # --------------------------------------------------------
    # 8. Mux narration
    # --------------------------------------------------------

    muxed_video = mux_audio_and_video(
        video_file=concatenated_video,
        narration_duration=narration_duration,
    )

    # --------------------------------------------------------
    # 9. Final duration safety
    # --------------------------------------------------------

    final_video = final_duration_safety_pass(
        source_file=muxed_video,
        narration_duration=narration_duration,
    )

    # --------------------------------------------------------
    # 10. Final validation
    # --------------------------------------------------------

    validate_final_output(
        narration_duration=narration_duration,
    )

    # --------------------------------------------------------
    # 11. Cleanup
    # --------------------------------------------------------

    cleanup_temporary_files()

    elapsed = (
        time.time()
        - start_time
    )

    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH GENERATION SUCCESSFUL")
    print("=" * 68)
    print("")
    print("FINAL MP4:")
    print(FINAL_VIDEO)
    print("")
    print("Narration duration:")
    print(
        f"{narration_duration:.3f} seconds"
    )
    print("")
    print("Final video duration:")
    print(
        f"{probe_duration(FINAL_VIDEO):.3f} seconds"
    )
    print("")
    print("Resolution:")
    print(
        f"{WIDTH} x {HEIGHT}"
    )
    print("")
    print("Scenes:")
    print(len(scene_videos))
    print("")
    print("Article photographs used:")
    print(len(image_paths))
    print("")
    print(
        "Generation time:",
        f"{elapsed:.1f} seconds",
    )
    print("")
    print("=" * 68)
    print("READY FOR GITHUB ACTIONS ARTIFACT")
    print("=" * 68)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("")
        print("=" * 68)
        print("GENERATION INTERRUPTED")
        print("=" * 68)
        sys.exit(130)

    except Exception as exc:
        print("")
        print("=" * 68)
        print("RIFT VALLEY WATCH GENERATION FAILED")
        print("=" * 68)
        print("")
        print("ERROR:", exc)
        print("")
        print("Working directory:")
        print(BASE_DIR)
        print("")
        print("Expected final MP4:")
        print(FINAL_VIDEO)
        print("")
        print("Existing MP4 files:")

        try:
            mp4_files = list(
                BASE_DIR.rglob("*.mp4")
            )

            if mp4_files:
                for path in mp4_files:
                    try:
                        print(
                            " -",
                            path,
                            "|",
                            path.stat().st_size,
                            "bytes",
                        )
                    except Exception:
                        print(
                            " -",
                            path,
                        )
            else:
                print(
                    "No MP4 files found."
                )

        except Exception as listing_error:
            print(
                "Could not list MP4 files:",
                listing_error,
            )

        print("")
        print("Audio files:")

        try:
            audio_files = list(
                AUDIO_DIR.glob("*")
            )

            if audio_files:
                for path in audio_files:
                    try:
                        print(
                            " -",
                            path,
                            "|",
                            path.stat().st_size,
                            "bytes",
                        )
                    except Exception:
                        print(
                            " -",
                            path,
                        )
            else:
                print(
                    "No audio files found."
                )

        except Exception as listing_error:
            print(
                "Could not list audio files:",
                listing_error,
            )

        print("")
        print("Video work files:")

        try:
            work_files = list(
                VIDEO_WORK_DIR.rglob("*")
            )

            if work_files:
                for path in work_files:
                    if path.is_file():
                        try:
                            print(
                                " -",
                                path,
                                "|",
                                path.stat().st_size,
                                "bytes",
                            )
                        except Exception:
                            print(
                                " -",
                                path,
                            )
            else:
                print(
                    "No video work files found."
                )

        except Exception as listing_error:
            print(
                "Could not list video work files:",
                listing_error,
            )

        print("")
        print(
            "The detailed FFmpeg/FFprobe error above "
            "is the actual failure point."
        )
        print("=" * 68)

        sys.exit(1)
