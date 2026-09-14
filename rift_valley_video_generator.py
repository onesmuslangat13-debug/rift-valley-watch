from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION:
# RVW_VIDEO_V29_STABLE_MULTIPHOTO_EDITORIAL
#
# PURPOSE
# ------------------------------------------------------------
# - Read data/selected_story.json
# - Read data/selected_script.json
# - Use real article photographs
# - Never fake multiple photographs
# - Deduplicate photographs
# - Use genuinely unique photographs as separate scenes
# - Never show a fake 1/5 -> 5/5 counter
# - Never repeat one photograph as multiple scenes
# - Reject obvious Citizen TV / placeholder / avatar images
# - Match scene duration to narration
# - Use FFmpeg directly
# - Produce:
#
#     output/rift_valley_watch_reel.mp4
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

NARRATION_FILE = AUDIO_DIR / "narration.mp3"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

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

MAX_SCENES = 6

MIN_FINAL_DURATION = 5.0
MAX_FINAL_DURATION = 120.0

JPEG_QUALITY = 94

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 300

HASH_SIZE = 32

DUPLICATE_HASH_THRESHOLD = 8


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


# ============================================================
# FONTS
# ============================================================

BOLD_FONT = None
REGULAR_FONT = None


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


def ensure_directories():
    directories = [
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
        VIDEO_WORK_DIR,
        AUDIO_DIR,
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def remove_old_render_files():
    print("")
    print("=" * 68)
    print("CLEANING OLD VIDEO WORK FILES")
    print("=" * 68)

    files = [
        FINAL_VIDEO,
        VIDEO_ONLY_FILE,
        MUXED_TEMP_FILE,
    ]

    for path in files:
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

    directories = [
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]

    for directory in directories:
        try:
            if directory.exists():
                shutil.rmtree(directory)

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        except Exception as exc:
            print(
                "WARNING: Could not clean",
                directory,
                ":",
                exc,
            )


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file is missing: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)

    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file {path}: {exc}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"JSON object expected: {path}"
        )

    return data


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(
    command,
    description,
    timeout=900,
):
    print("")
    print("=" * 68)
    print(description)
    print("=" * 68)

    print("COMMAND:")
    print(
        " ".join(
            str(item)
            for item in command
        )
    )

    try:
        result = subprocess.run(
            [
                str(item)
                for item in command
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired as exc:
        print("")
        print("ERROR: Command timed out.")

        if exc.stdout:
            print(exc.stdout)

        if exc.stderr:
            print(exc.stderr)

        raise RuntimeError(
            f"{description} timed out after "
            f"{timeout} seconds."
        )

    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Executable not found: "
            f"{command[0]}. {exc}"
        )

    except Exception as exc:
        raise RuntimeError(
            f"Could not execute {description}: {exc}"
        )

    if result.stdout:
        print("")
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
# FFPROBE
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
            f"FFprobe duration failed for "
            f"{path}: {result.stderr.strip()}"
        )

    value = clean(result.stdout)

    try:
        duration = float(value)
    except Exception:
        raise RuntimeError(
            f"Invalid duration returned for {path}: "
            f"{value}"
        )

    if not math.isfinite(duration):
        raise RuntimeError(
            f"Invalid non-finite duration for {path}"
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
            (
                "stream="
                "codec_type,"
                "codec_name,"
                "width,"
                "height,"
                "r_frame_rate,"
                "avg_frame_rate,"
                "sample_rate,"
                "channels"
            ),
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
        data = json.loads(
            result.stdout
        )
    except Exception:
        return []

    return data.get(
        "streams",
        [],
    )


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
            "COUNTY MISMATCH between story "
            "and script."
        )

    story_title = clean(
        story["title"]
    )

    script_title = clean(
        script["title"]
    )

    if story_title != script_title:
        raise RuntimeError(
            "TITLE MISMATCH between story "
            "and script."
        )

    story_url = clean(
        story["article_url"]
    )

    script_url = clean(
        script["article_url"]
    )

    if story_url != script_url:
        raise RuntimeError(
            "ARTICLE URL MISMATCH between story "
            "and script."
        )

    if not isinstance(
        story["image_paths"],
        list,
    ):
        raise RuntimeError(
            "story.image_paths must be a list."
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
        clean(
            story.get("source")
        ),
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
        "Article images supplied:",
        len(
            story["image_paths"]
        ),
    )


# ============================================================
# IMAGE FILTERING
# ============================================================

BAD_IMAGE_TERMS = [
    "citizen-tv",
    "citizentv",
    "citizen_tv",
    "citizen-logo",
    "citizen_logo",
    "citizenlogo",
    "ctv-logo",
    "ctv_logo",
    "ctvlogo",
    "citizen-digital-logo",
    "citizen_digital_logo",
    "citizendigital",
    "world-cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "generic-avatar",
    "generic_avatar",
    "profile-picture",
    "profile_picture",
]


def image_name_is_rejected(path):
    name = (
        path.name
        .lower()
        .replace(
            " ",
            "-",
        )
    )

    for term in BAD_IMAGE_TERMS:
        if term in name:
            return True

    return False


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

        if image_name_is_rejected(path):
            print(
                "REJECTED BRAND/PLACEHOLDER:",
                path.name,
            )
            continue

        unique_paths.append(path)

    if not unique_paths:
        raise RuntimeError(
            "No acceptable article photographs found."
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
            f"Could not validate image "
            f"{path}: {exc}"
        )


# ============================================================
# FILE HASH
# ============================================================

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


# ============================================================
# VISUAL HASH
# ============================================================

def calculate_image_hash(path):
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
    if (
        not hash_a
        or not hash_b
        or len(hash_a) != len(hash_b)
    ):
        return 999999

    return sum(
        first != second
        for first, second in zip(
            hash_a,
            hash_b,
        )
    )


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_images(paths):
    print("")
    print("=" * 68)
    print("DEDUPLICATING ARTICLE PHOTOGRAPHS")
    print("=" * 68)

    accepted = []

    exact_hashes = set()
    visual_hashes = []

    for path in paths:
        exact = file_sha256(path)

        if (
            exact
            and exact in exact_hashes
        ):
            print(
                "DUPLICATE FILE REJECTED:",
                path.name,
            )
            continue

        visual = calculate_image_hash(
            path
        )

        duplicate_visual = False

        if visual:
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

    if not accepted:
        raise RuntimeError(
            "No unique article photographs remain."
        )

    print("")
    print(
        "UNIQUE PHOTOGRAPHS:",
        len(accepted),
    )

    return accepted


# ============================================================
# VALIDATE ALL IMAGES
# ============================================================

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
                "WARNING: SKIPPING IMAGE:",
                path.name,
                "|",
                exc,
            )

    if not valid:
        raise RuntimeError(
            "All article photographs failed validation."
        )

    return valid[:MAX_SCENES]


# ============================================================
# SOURCE PHOTO CLEANUP
# ============================================================

def clean_source_photo(image):
    image = image.convert(
        "RGB"
    )

    width, height = image.size

    left = int(
        width * 0.03
    )

    right = int(
        width * 0.97
    )

    top = int(
        height * 0.02
    )

    bottom = int(
        height * 0.98
    )

    if (
        right - left >= width * 0.85
        and
        bottom - top >= height * 0.85
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
# VERTICAL COVER CROP
# ============================================================

def cover_crop(
    image,
    width=WIDTH,
    height=HEIGHT,
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

    src_width, src_height = image.size

    src_ratio = (
        src_width
        / float(src_height)
    )

    if src_ratio > target_ratio:
        crop_width = int(
            src_height
            * target_ratio
        )

        max_left = max(
            0,
            src_width - crop_width,
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

        max_top = max(
            0,
            src_height - crop_height,
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
    x,
    y,
    font_obj,
    fill,
    max_width,
    line_spacing=10,
):
    lines = wrap_text(
        draw,
        text,
        font_obj,
        max_width,
    )

    if not lines:
        return y

    bbox = font_obj.getbbox(
        "Ag"
    )

    line_height = (
        bbox[3]
        - bbox[1]
        + line_spacing
    )

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
        y
        + len(lines)
        * line_height
    )


# ============================================================
# GRADIENT
# ============================================================

def draw_gradient_overlay(image):
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

    for y in range(
        0,
        700,
    ):
        ratio = y / 700.0

        alpha = int(
            205
            * (
                1.0
                - ratio
            )
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
                        205,
                        alpha,
                    ),
                ),
            ),
        )

    bottom_start = (
        HEIGHT
        - 780
    )

    for y in range(
        bottom_start,
        HEIGHT,
    ):
        ratio = (
            y
            - bottom_start
        ) / 780.0

        alpha = int(
            225
            * ratio
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
                        225,
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
# TOP BAR
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
            150,
        ),
        fill=BLACK,
    )

    draw.rectangle(
        (
            0,
            0,
            16,
            150,
        ),
        fill=RED,
    )

    draw.text(
        (
            48,
            30,
        ),
        "RIFT VALLEY WATCH",
        font=font(
            43,
            True,
        ),
        fill=WHITE,
    )

    county_text = clean(
        county
    ).upper()

    if county_text:
        county_text += (
            "  •  LATEST UPDATE"
        )

    draw.text(
        (
            50,
            92,
        ),
        county_text,
        font=font(
            24,
            True,
        ),
        fill=LIGHT,
    )

    badge_left = (
        WIDTH
        - 205
    )

    draw.rounded_rectangle(
        (
            badge_left,
            36,
            WIDTH - 35,
            92,
        ),
        radius=12,
        fill=RED,
    )

    draw.text(
        (
            badge_left + 85,
            64,
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
    y_top = HEIGHT - 255

    draw.rounded_rectangle(
        (
            38,
            y_top,
            WIDTH - 38,
            HEIGHT - 45,
        ),
        radius=22,
        fill=(
            0,
            0,
            0,
            190,
        ),
        outline=(
            255,
            255,
            255,
        ),
        width=2,
    )

    draw.text(
        (
            65,
            y_top + 28,
        ),
        "SOURCE",
        font=font(
            21,
            True,
        ),
        fill=GRAY,
    )

    source_text = (
        clean(source)
        or "News source"
    )

    draw_wrapped_text(
        draw,
        source_text,
        65,
        y_top + 65,
        font(
            30,
            True,
        ),
        WHITE,
        WIDTH - 130,
        line_spacing=6,
    )

    published_text = clean(
        published
    )

    if published_text:
        draw.text(
            (
                65,
                HEIGHT - 82,
            ),
            published_text,
            font=font(
                19,
                False,
            ),
            fill=LIGHT,
        )


# ============================================================
# STORY GRAPHICS
# ============================================================

def draw_story_graphics(
    image,
    story,
    scene_index,
    scene_total,
):
    draw = ImageDraw.Draw(
        image
    )

    draw_top_bar(
        draw,
        story.get(
            "county",
            "",
        ),
    )

    title = clean(
        story.get(
            "title",
            "",
        )
    )

    if len(title) < 90:
        title_size = 62
    elif len(title) < 135:
        title_size = 54
    else:
        title_size = 48

    title_font = font(
        title_size,
        True,
    )

    title_y = HEIGHT - 690

    draw.rounded_rectangle(
        (
            38,
            title_y - 32,
            WIDTH - 38,
            HEIGHT - 280,
        ),
        radius=24,
        fill=(
            0,
            0,
            0,
            195,
        ),
    )

    draw_wrapped_text(
        draw,
        title,
        65,
        title_y,
        title_font,
        WHITE,
        WIDTH - 130,
        line_spacing=13,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Only display a scene counter when there are genuinely
    # multiple unique photographs.
    #
    # If there is only ONE photo:
    #     no 1/5
    #     no 2/5
    #     no 3/5
    #     etc.
    #
    # This prevents the misleading UI seen in the previous
    # version.
    # --------------------------------------------------------

    if scene_total > 1:
        counter = (
            f"{scene_index + 1}"
            f"/"
            f"{scene_total}"
        )

        draw.rounded_rectangle(
            (
                WIDTH - 165,
                170,
                WIDTH - 38,
                225,
            ),
            radius=14,
            fill=RED,
        )

        draw.text(
            (
                WIDTH - 101,
                197,
            ),
            counter,
            font=font(
                25,
                True,
            ),
            fill=WHITE,
            anchor="mm",
        )

    draw_bottom_source(
        draw,
        story.get(
            "source",
            "",
        ),
        story.get(
            "published_at_kenya",
            "",
        ),
    )

    return image


# ============================================================
# SCENE IMAGE
# ============================================================

def create_scene_image(
    story,
    image_path,
    scene_index,
    scene_total,
):
    with Image.open(
        image_path
    ) as raw:
        image = raw.convert(
            "RGB"
        )

    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=105,
            threshold=3,
        )
    )

    biases = [
        (
            0.45,
            0.48,
        ),
        (
            0.55,
            0.45,
        ),
        (
            0.50,
            0.55,
        ),
        (
            0.40,
            0.50,
        ),
        (
            0.60,
            0.50,
        ),
        (
            0.50,
            0.45,
        ),
    ]

    horizontal_bias, vertical_bias = (
        biases[
            scene_index
            % len(biases)
        ]
    )

    image = cover_crop(
        image,
        WIDTH,
        HEIGHT,
        horizontal_bias,
        vertical_bias,
    )

    image = image.resize(
        (
            WIDTH,
            HEIGHT,
        ),
        Image.Resampling.LANCZOS,
    )

    image = draw_gradient_overlay(
        image
    )

    image = draw_story_graphics(
        image,
        story,
        scene_index,
        scene_total,
    )

    output = (
        SCENE_IMAGE_DIR
        / f"scene_{scene_index + 1:02d}.jpg"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        "JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
    )

    return output


# ============================================================
# SCENE TIMING
# ============================================================

def calculate_scene_durations(
    total_duration,
    scene_count,
):
    if scene_count <= 0:
        raise RuntimeError(
            "Scene count must be positive."
        )

    if scene_count == 1:
        return [
            max(
                total_duration,
                MIN_FINAL_DURATION,
            )
        ]

    base = (
        total_duration
        / float(scene_count)
    )

    durations = []

    for index in range(
        scene_count
    ):
        if index == 0:
            duration = (
                base
                * 1.08
            )

        elif index == scene_count - 1:
            duration = (
                base
                * 0.94
            )

        else:
            duration = (
                base
                * 0.99
            )

        durations.append(
            duration
        )

    total = sum(
        durations
    )

    if total <= 0:
        raise RuntimeError(
            "Invalid scene duration total."
        )

    scale = (
        total_duration
        / total
    )

    return [
        duration * scale
        for duration in durations
    ]


# ============================================================
# SCENE VIDEO
# ============================================================

def create_scene_video(
    image_path,
    duration,
    index,
):
    output = (
        SCENE_VIDEO_DIR
        / f"scene_{index + 1:02d}.mp4"
    )

    run_command(
        [
            FFMPEG,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.3f}",
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
        ],
        f"CREATE SCENE VIDEO {index + 1}",
        timeout=300,
    )

    if not output.exists():
        raise RuntimeError(
            f"Scene video was not created: {output}"
        )

    return output


# ============================================================
# CONCATENATION
# ============================================================

def write_concat_file(
    scene_files
):
    concat_file = (
        VIDEO_WORK_DIR
        / "concat.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for path in scene_files:
            resolved = str(
                Path(path)
                .resolve()
            )

            safe_path = (
                resolved
                .replace(
                    "'",
                    "'\\''",
                )
            )

            handle.write(
                f"file '{safe_path}'\n"
            )

    return concat_file


def concatenate_scenes(
    scene_files
):
    if not scene_files:
        raise RuntimeError(
            "No scene videos supplied."
        )

    concat_file = write_concat_file(
        scene_files
    )

    run_command(
        [
            FFMPEG,
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
            str(VIDEO_ONLY_FILE),
        ],
        "CONCATENATE SCENES",
        timeout=600,
    )

    if not VIDEO_ONLY_FILE.exists():
        raise RuntimeError(
            "FFmpeg did not create video_only.mp4."
        )

    return VIDEO_ONLY_FILE


# ============================================================
# AUDIO MUX
# ============================================================

def mux_audio(
    video_file,
    audio_file,
):
    run_command(
        [
            FFMPEG,
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
            "copy",
            "-c:a",
            AUDIO_CODEC,
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(MUXED_TEMP_FILE),
        ],
        "MUX NARRATION WITH VIDEO",
        timeout=600,
    )

    if not MUXED_TEMP_FILE.exists():
        raise RuntimeError(
            "Audio muxing did not create final temporary MP4."
        )

    return MUXED_TEMP_FILE


# ============================================================
# FINAL VIDEO
# ============================================================

def create_final_video(
    video_file,
    audio_file,
):
    muxed = mux_audio(
        video_file,
        audio_file,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    shutil.copy2(
        muxed,
        FINAL_VIDEO,
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return FINAL_VIDEO


# ============================================================
# FINAL VIDEO VALIDATION
# ============================================================

def validate_final_video(
    path,
    expected_duration,
):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 missing: {path}"
        )

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError(
            f"Final MP4 is suspiciously small: "
            f"{size} bytes"
        )

    duration = probe_duration(
        path
    )

    if duration < MIN_FINAL_DURATION:
        raise RuntimeError(
            "Final MP4 is too short."
        )

    if duration > MAX_FINAL_DURATION:
        raise RuntimeError(
            "Final MP4 exceeds maximum duration."
        )

    difference = abs(
        duration
        - expected_duration
    )

    if difference > 1.5:
        raise RuntimeError(
            "Final duration mismatch. "
            f"Expected approximately "
            f"{expected_duration:.3f}s, "
            f"got {duration:.3f}s."
        )

    streams = probe_streams(
        path
    )

    video_stream = None
    audio_stream = None

    for stream in streams:
        if (
            stream.get("codec_type")
            == "video"
            and video_stream is None
        ):
            video_stream = stream

        if (
            stream.get("codec_type")
            == "audio"
            and audio_stream is None
        ):
            audio_stream = stream

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    width = int(
        video_stream.get(
            "width",
            0,
        )
    )

    height = int(
        video_stream.get(
            "height",
            0,
        )
    )

    if width != WIDTH:
        raise RuntimeError(
            f"Final MP4 width is {width}; "
            f"expected {WIDTH}."
        )

    if height != HEIGHT:
        raise RuntimeError(
            f"Final MP4 height is {height}; "
            f"expected {HEIGHT}."
        )

    print("")
    print("=" * 68)
    print("FINAL MP4 VERIFIED")
    print("=" * 68)

    print(
        "File:",
        path,
    )

    print(
        "Size:",
        size,
        "bytes",
    )

    print(
        "Duration:",
        f"{duration:.3f}",
        "seconds",
    )

    print(
        "Video:",
        video_stream.get(
            "codec_name"
        ),
        width,
        "x",
        height,
    )

    print(
        "Audio:",
        audio_stream.get(
            "codec_name"
        ),
    )

    return duration


# ============================================================
# MAIN GENERATOR
# ============================================================

def main():
    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH")
    print("RVW_VIDEO_V29_STABLE_MULTIPHOTO_EDITORIAL")
    print("=" * 68)

    ensure_directories()

    remove_old_render_files()

    print("")
    print("=" * 68)
    print("LOADING STORY AND SCRIPT")
    print("=" * 68)

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

    print("")
    print("=" * 68)
    print("RESOLVING ARTICLE PHOTOGRAPHS")
    print("=" * 68)

    image_paths = resolve_image_paths(
        story
    )

    image_paths = deduplicate_images(
        image_paths
    )

    image_paths = validate_all_images(
        image_paths
    )

    if len(image_paths) > MAX_SCENES:
        image_paths = image_paths[
            :MAX_SCENES
        ]

    print("")
    print("=" * 68)
    print("FINAL UNIQUE PHOTO COUNT")
    print("=" * 68)

    print(
        "Photographs selected:",
        len(image_paths),
    )

    for index, path in enumerate(
        image_paths,
        1,
    ):
        print(
            f"{index}.",
            path.name,
        )

    # --------------------------------------------------------
    # Synchronize selected_story.json with the exact photographs
    # that the renderer will actually use.
    # --------------------------------------------------------

    relative_paths = []

    for path in image_paths:
        try:
            relative = path.relative_to(
                BASE_DIR
            )

            relative_paths.append(
                str(relative)
            )

        except ValueError:
            relative_paths.append(
                str(path)
            )

    story["image_paths"] = (
        relative_paths
    )

    with STORY_FILE.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            story,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # Verify narration.
    # --------------------------------------------------------

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            f"Narration file missing: "
            f"{NARRATION_FILE}"
        )

    audio_duration = probe_duration(
        NARRATION_FILE
    )

    print("")
    print("=" * 68)
    print("NARRATION VERIFIED")
    print("=" * 68)

    print(
        "Narration:",
        NARRATION_FILE,
    )

    print(
        "Duration:",
        f"{audio_duration:.3f}",
        "seconds",
    )

    if audio_duration < MIN_FINAL_DURATION:
        raise RuntimeError(
            "Narration is too short."
        )

    if audio_duration > MAX_FINAL_DURATION:
        raise RuntimeError(
            "Narration exceeds maximum allowed duration."
        )

    # --------------------------------------------------------
    # IMPORTANT EDITORIAL RULE
    #
    # One unique photograph:
    #     one scene
    #
    # Two unique photographs:
    #     two scenes
    #
    # Three unique photographs:
    #     three scenes
    #
    # No photograph is repeated simply to create more scenes.
    # --------------------------------------------------------

    scene_count = len(
        image_paths
    )

    durations = calculate_scene_durations(
        audio_duration,
        scene_count,
    )

    print("")
    print("=" * 68)
    print("EDITORIAL SCENE PLAN")
    print("=" * 68)

    print(
        "Unique photographs:",
        scene_count,
    )

    for index in range(
        scene_count
    ):
        print(
            f"Scene {index + 1}:",
            image_paths[index].name,
            "|",
            f"{durations[index]:.3f}s",
        )

    # --------------------------------------------------------
    # CREATE SCENES
    # --------------------------------------------------------

    scene_images = []
    scene_videos = []

    print("")
    print("=" * 68)
    print("CREATING SCENE IMAGES")
    print("=" * 68)

    for index, image_path in enumerate(
        image_paths
    ):
        print("")
        print(
            f"CREATING SCENE "
            f"{index + 1}/{scene_count}"
        )

        print(
            "Source photograph:",
            image_path.name,
        )

        scene_image = create_scene_image(
            story,
            image_path,
            index,
            scene_count,
        )

        scene_images.append(
            scene_image
        )

        print(
            "Scene image:",
            scene_image,
        )

    print("")
    print("=" * 68)
    print("CREATING SCENE VIDEOS")
    print("=" * 68)

    for index, scene_image in enumerate(
        scene_images
    ):
        scene_video = create_scene_video(
            scene_image,
            durations[index],
            index,
        )

        scene_videos.append(
            scene_video
        )

        print(
            "Created:",
            scene_video,
        )

    # --------------------------------------------------------
    # CONCATENATE VISUAL SCENES
    # --------------------------------------------------------

    combined_video = concatenate_scenes(
        scene_videos
    )

    combined_duration = probe_duration(
        combined_video
    )

    print("")
    print("=" * 68)
    print("COMBINED VIDEO")
    print("=" * 68)

    print(
        "Duration:",
        f"{combined_duration:.3f}",
        "seconds",
    )

    print(
        "Narration:",
        f"{audio_duration:.3f}",
        "seconds",
    )

    if abs(
        combined_duration
        - audio_duration
    ) > 2.0:
        print(
            "WARNING: Combined video duration "
            "differs from narration by",
            round(
                combined_duration
                - audio_duration,
                3,
            ),
            "seconds.",
        )

    # --------------------------------------------------------
    # MUX NARRATION
    # --------------------------------------------------------

    final_video = create_final_video(
        combined_video,
        NARRATION_FILE,
    )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    final_duration = validate_final_video(
        final_video,
        audio_duration,
    )

    print("")
    print("=" * 68)
    print("RIFT VALLEY WATCH GENERATION COMPLETE")
    print("=" * 68)

    print(
        "Final MP4:",
        final_video,
    )

    print(
        "Duration:",
        f"{final_duration:.3f}",
        "seconds",
    )

    print(
        "Unique photographs used:",
        scene_count,
    )

    print("")
    print(
        "NO FAKE SCENE COUNTER WAS USED."
    )

    print(
        "NO PHOTOGRAPH WAS REPEATED "
        "AS A DIFFERENT SCENE."
    )

    print(
        "FINAL MP4 READY."
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        sys.exit(
            main()
        )

    except KeyboardInterrupt:
        print("")
        print(
            "Generation interrupted."
        )
        sys.exit(130)

    except Exception as exc:
        print("")
        print("=" * 68)
        print("RIFT VALLEY WATCH GENERATION FAILED")
        print("=" * 68)
        print(
            str(exc)
        )
        sys.exit(1)
