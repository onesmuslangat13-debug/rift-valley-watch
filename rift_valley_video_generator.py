# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION:
# RVW_VIDEO_V31_STABLE_MULTIPHOTO_EDITORIAL
#
# PURPOSE
# - 1080 x 1920 vertical news reel
# - Genuine article photographs only
# - One scene per genuinely unique photograph
# - Never repeats one photograph as fake different scenes
# - Uses multiple real photos when available
# - Uses one real photo when only one is available
# - Uses narration.mp3 from /audio
# - Uses selected story/script from /data
# - Professional editorial/news presentation
# - No Citizen TV / Citizen Digital branding
# - No generic avatars
# - No placeholders
# - No World Cup graphics
# - No unrelated stock imagery
# - Final output: output/rift_valley_watch_reel.mp4
# ============================================================

from pathlib import Path
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont, ImageFilter


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
# FORBIDDEN IMAGE / BRAND TERMS
# ============================================================

FORBIDDEN_IMAGE_TERMS = [
    "citizen",
    "citizen_tv",
    "citizen-tv",
    "citizen digital",
    "ctv",
    "world_cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "generic-avatar",
    "generic_avatar",
    "profile-picture",
    "profile_picture",
    "profilepicture",
    "dummy",
    "stock-avatar",
]


# ============================================================
# COLORS
# ============================================================

BLACK = (8, 8, 10)
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
# DIRECTORY SETUP
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# COMMAND EXECUTION
# ============================================================

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
            f"{result.returncode}: "
            f"{' '.join(str(x) for x in command)}"
        )

    return result


# ============================================================
# TEXT HELPERS
# ============================================================

def safe_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def clean_display_text(value):
    text = safe_text(value)

    # Never display Citizen branding.
    text = re.sub(
        r"\bCitizen\s+Digital\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bCitizen\s+TV\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bCTV\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(" -|")


def shorten_text(text, max_chars):
    text = clean_display_text(text)

    if len(text) <= max_chars:
        return text

    shortened = text[:max_chars].rsplit(
        " ",
        1,
    )[0]

    return shortened.rstrip(" ,.;:") + "…"


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


# ============================================================
# STORY OBJECT
# ============================================================

def get_story_object(story_data):
    if not isinstance(story_data, dict):
        raise RuntimeError(
            "selected_story.json must contain a JSON object."
        )

    nested_story = story_data.get("story")

    if isinstance(nested_story, dict):
        return nested_story

    stories = story_data.get("stories")

    if isinstance(stories, list):
        for story in stories:
            if isinstance(story, dict):
                return story

    if story_data.get("title"):
        return story_data

    raise RuntimeError(
        "Could not identify a story object in selected_story.json."
    )


def get_script_object(script_data):
    if not isinstance(script_data, dict):
        return {}

    nested_story = script_data.get("story")

    if isinstance(nested_story, dict):
        return nested_story

    scripts = script_data.get("scripts")

    if isinstance(scripts, list):
        for script in scripts:
            if isinstance(script, dict):
                return script

    return script_data


# ============================================================
# STORY FIELDS
# ============================================================

def get_source_name(story):
    source = story.get(
        "source",
        "",
    )

    if isinstance(source, dict):
        name = source.get(
            "name",
            "",
        )
    else:
        name = source

    name = clean_display_text(name)

    if not name:
        return "Rift Valley Watch"

    # Avoid displaying Citizen branding.
    if "citizen" in name.lower():
        return "Rift Valley Watch"

    return name


def get_county(story):
    county = clean_display_text(
        story.get(
            "county",
            "",
        )
    )

    return county or "Rift Valley"


def get_category(story):
    category = clean_display_text(
        story.get(
            "category",
            "",
        )
    )

    return category.upper() or "REGIONAL NEWS"


def get_title(story):
    title = clean_display_text(
        story.get(
            "title",
            "",
        )
    )

    return title or "Rift Valley Update"


def get_published(story):
    value = (
        story.get("published")
        or story.get("date")
        or ""
    )

    return clean_display_text(value)


# ============================================================
# IMAGE PATH RESOLUTION
# ============================================================

def resolve_local_path(value):
    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    candidate = Path(value)

    if candidate.is_absolute():
        try:
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            pass

    candidate = BASE_DIR / value

    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        pass

    candidate = SOURCE_DIR / Path(value).name

    try:
        if candidate.exists():
            return candidate.resolve()
    except Exception:
        pass

    return None


# ============================================================
# FORBIDDEN IMAGE CHECK
# ============================================================

def contains_forbidden_term(path):
    text = str(path).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term.lower() in text:
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

    if contains_forbidden_term(path):
        print(
            "REJECTED FORBIDDEN IMAGE:",
            path,
        )
        return False

    try:
        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False
    except Exception:
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
# EXACT IMAGE HASH
# ============================================================

def exact_file_hash(path):
    digest = hashlib.sha256()

    try:
        with open(
            path,
            "rb",
        ) as f:

            while True:
                block = f.read(
                    1024 * 1024
                )

                if not block:
                    break

                digest.update(block)

        return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# VISUAL IMAGE HASH
# ============================================================

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

            brightness = []

            for r, g, b in pixels:
                value = (
                    0.299 * r
                    + 0.587 * g
                    + 0.114 * b
                )

                brightness.append(
                    value
                )

            average = sum(
                brightness
            ) / len(brightness)

            bits = []

            for value in brightness:
                bits.append(
                    "1"
                    if value >= average
                    else "0"
                )

            return "".join(bits)

    except Exception:
        return ""


# ============================================================
# HAMMING DISTANCE
# ============================================================

def hamming_distance(a, b):
    if not a or not b:
        return 999999

    if len(a) != len(b):
        return 999999

    distance = 0

    for left, right in zip(a, b):
        if left != right:
            distance += 1

    return distance


# ============================================================
# COLLECT STORY IMAGES
# ============================================================

def collect_candidate_images(story):
    candidates = []

    # --------------------------------------------------------
    # Story-provided multi-photo paths
    # --------------------------------------------------------

    image_paths = story.get(
        "image_paths",
        [],
    )

    if isinstance(
        image_paths,
        str,
    ):
        image_paths = [
            image_paths
        ]

    if isinstance(
        image_paths,
        list,
    ):
        for value in image_paths:
            path = resolve_local_path(
                value
            )

            if path:
                candidates.append(
                    path
                )

    # --------------------------------------------------------
    # Legacy image fields
    # --------------------------------------------------------

    for key in [
        "image_path",
        "local_image",
        "image",
        "photo",
        "photo_path",
    ]:

        value = story.get(
            key,
            "",
        )

        if isinstance(
            value,
            list,
        ):
            for item in value:
                path = resolve_local_path(
                    item
                )

                if path:
                    candidates.append(
                        path
                    )

        else:
            path = resolve_local_path(
                value
            )

            if path:
                candidates.append(
                    path
                )

    # --------------------------------------------------------
    # Source-directory fallback
    # --------------------------------------------------------

    try:
        source_files = sorted(
            SOURCE_DIR.iterdir(),
            key=lambda p: p.name.lower(),
        )
    except Exception:
        source_files = []

    for path in source_files:

        if not path.is_file():
            continue

        if not path.name.lower().startswith(
            "story_image"
        ):
            continue

        candidates.append(
            path
        )

    return candidates


# ============================================================
# DEDUPLICATE REAL PHOTOS
# ============================================================

def unique_valid_images(story):
    candidates = collect_candidate_images(
        story
    )

    unique = []

    exact_hashes = set()
    visual_hashes = []

    for path in candidates:

        if not validate_image(path):
            continue

        exact = exact_file_hash(path)

        if exact and exact in exact_hashes:
            print(
                "SKIPPED EXACT DUPLICATE:",
                path.name,
            )
            continue

        visual = visual_hash(path)

        if visual:
            duplicate_visual = False

            for previous in visual_hashes:

                distance = hamming_distance(
                    visual,
                    previous,
                )

                # Very similar photographs are treated as duplicates.
                if distance <= 8:
                    duplicate_visual = True
                    break

            if duplicate_visual:
                print(
                    "SKIPPED VISUAL DUPLICATE:",
                    path.name,
                )
                continue

        if exact:
            exact_hashes.add(
                exact
            )

        if visual:
            visual_hashes.append(
                visual
            )

        unique.append(
            path
        )

        if len(unique) >= MAX_SCENES:
            break

    return unique


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(size, bold=False):
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
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    )

    for candidate in candidates:

        try:
            if Path(candidate).exists():
                return ImageFont.truetype(
                    candidate,
                    size,
                )
        except Exception:
            pass

    try:
        return ImageFont.load_default()
    except Exception:
        return None


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):
    text = clean_display_text(
        text
    )

    if not text:
        return []

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            word
            if not current
            else current + " " + word
        )

        try:
            bbox = draw.textbbox(
                (0, 0),
                test,
                font=font,
            )

            width = bbox[2] - bbox[0]

        except Exception:
            width = len(test) * 20

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
# FIT IMAGE TO VERTICAL CANVAS
# ============================================================

def crop_to_vertical(
    image,
    width=WIDTH,
    height=HEIGHT,
):
    image = image.convert(
        "RGB"
    )

    source_width, source_height = image.size

    if source_width <= 0 or source_height <= 0:
        raise RuntimeError(
            "Invalid source image dimensions."
        )

    target_ratio = (
        width / height
    )

    source_ratio = (
        source_width / source_height
    )

    if source_ratio > target_ratio:

        # Source is wider.
        new_width = int(
            source_height
            * target_ratio
        )

        left = (
            source_width
            - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                source_height,
            )
        )

    else:

        # Source is taller.
        new_height = int(
            source_width
            / target_ratio
        )

        top = (
            source_height
            - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                source_width,
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
# PREPARE PHOTO
# ============================================================

def prepare_photo(path):
    try:
        with Image.open(path) as image:
            image = image.convert(
                "RGB"
            )

            image = crop_to_vertical(
                image,
                WIDTH,
                HEIGHT,
            )

            # Mild professional sharpening.
            image = image.filter(
                ImageFilter.UnsharpMask(
                    radius=1.0,
                    percent=105,
                    threshold=3,
                )
            )

            return image

    except Exception as exc:
        raise RuntimeError(
            f"Could not prepare image {path}: {exc}"
        ) from exc


# ============================================================
# DARKEN PHOTO SLIGHTLY FOR TEXT
# ============================================================

def apply_photo_overlay(
    image,
    top_strength=0.48,
    bottom_strength=0.62,
):
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    width, height = image.size

    # Top gradient.
    top_height = int(
        height * 0.32
    )

    for y in range(top_height):
        ratio = (
            1
            - y / max(
                1,
                top_height,
            )
        )

        alpha = int(
            255
            * top_strength
            * ratio
        )

        draw.line(
            (
                0,
                y,
                width,
                y,
            ),
            fill=(
                0,
                0,
                0,
                alpha,
            ),
        )

    # Bottom gradient.
    bottom_start = int(
        height * 0.58
    )

    bottom_height = (
        height
        - bottom_start
    )

    for index in range(
        bottom_height
    ):
        ratio = (
            index
            / max(
                1,
                bottom_height - 1,
            )
        )

        alpha = int(
            255
            * bottom_strength
            * ratio
        )

        y = (
            bottom_start
            + index
        )

        draw.line(
            (
                0,
                y,
                width,
                y,
            ),
            fill=(
                0,
                0,
                0,
                alpha,
            ),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


# ============================================================
# DRAW TOP BRANDING
# ============================================================

def draw_top_bar(
    draw,
    story,
):
    county = get_county(
        story
    )

    category = get_category(
        story
    )

    # Main top bar.
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            150,
        ),
        fill=BLACK,
    )

    # Red editorial accent.
    draw.rectangle(
        (
            0,
            145,
            WIDTH,
            150,
        ),
        fill=RED,
    )

    logo_font = find_font(
        44,
        bold=True,
    )

    county_font = find_font(
        27,
        bold=True,
    )

    category_font = find_font(
        23,
        bold=True,
    )

    draw.text(
        (
            48,
            34,
        ),
        "RIFT VALLEY",
        font=logo_font,
        fill=WHITE,
    )

    draw.text(
        (
            48,
            91,
        ),
        "WATCH",
        font=logo_font,
        fill=RED,
    )

    county_text = shorten_text(
        county,
        30,
    )

    try:
        county_box = draw.textbbox(
            (0, 0),
            county_text,
            font=county_font,
        )

        county_width = (
            county_box[2]
            - county_box[0]
        )

    except Exception:
        county_width = 250

    draw.rounded_rectangle(
        (
            WIDTH
            - county_width
            - 78,
            32,
            WIDTH
            - 30,
            82,
        ),
        radius=12,
        fill=DARK_GREY,
    )

    draw.text(
        (
            WIDTH
            - county_width
            - 54,
            42,
        ),
        county_text,
        font=county_font,
        fill=WHITE,
    )

    draw.text(
        (
            WIDTH - 48,
            104,
        ),
        category,
        font=category_font,
        fill=YELLOW,
        anchor="ra",
    )


# ============================================================
# DRAW STORY TITLE
# ============================================================

def draw_title_block(
    draw,
    story,
):
    title = get_title(
        story
    )

    title_font = find_font(
        62,
        bold=True,
    )

    category_font = find_font(
        25,
        bold=True,
    )

    title_width = WIDTH - 100

    lines = wrap_text(
        draw,
        title,
        title_font,
        title_width,
    )

    # Limit title to a practical number of lines.
    if len(lines) > 4:
        lines = lines[:4]

        if lines:
            lines[-1] = shorten_text(
                lines[-1],
                30,
            )

    line_height = 76

    # Place title toward lower portion.
    title_y = 1210

    # Small category label.
    draw.rounded_rectangle(
        (
            48,
            title_y - 55,
            48 + 260,
            title_y - 10,
        ),
        radius=10,
        fill=RED,
    )

    draw.text(
        (
            66,
            title_y - 47,
        ),
        get_category(story),
        font=category_font,
        fill=WHITE,
    )

    current_y = title_y

    for line in lines:
        draw.text(
            (
                50,
                current_y,
            ),
            line,
            font=title_font,
            fill=WHITE,
            stroke_width=2,
            stroke_fill=BLACK,
        )

        current_y += line_height


# ============================================================
# DRAW STORY FACTS
# ============================================================

def get_fact_items(story):
    facts = []

    verified = story.get(
        "verified_facts",
        [],
    )

    if isinstance(
        verified,
        list,
    ):
        for item in verified:
            if not isinstance(
                item,
                dict,
            ):
                continue

            label = clean_display_text(
                item.get(
                    "label",
                    "",
                )
            )

            value = clean_display_text(
                item.get(
                    "value",
                    "",
                )
            )

            if label and value:
                facts.append(
                    (
                        label,
                        value,
                    )
                )

    return facts


def draw_fact_strip(
    draw,
    story,
):
    facts = get_fact_items(
        story
    )

    if not facts:
        return

    # Use at most three facts.
    facts = facts[:3]

    panel_y = 1575
    panel_height = 155

    draw.rounded_rectangle(
        (
            40,
            panel_y,
            WIDTH - 40,
            panel_y + panel_height,
        ),
        radius=18,
        fill=(
            15,
            15,
            18,
        ),
    )

    cell_width = (
        WIDTH - 80
    ) / len(facts)

    label_font = find_font(
        21,
        bold=True,
    )

    value_font = find_font(
        30,
        bold=True,
    )

    for index, (
        label,
        value,
    ) in enumerate(facts):

        left = int(
            40
            + index * cell_width
        )

        right = int(
            40
            + (index + 1)
            * cell_width
        )

        if index > 0:
            draw.line(
                (
                    left,
                    panel_y + 22,
                    left,
                    panel_y
                    + panel_height
                    - 22,
                ),
                fill=DARK_GREY,
                width=2,
            )

        label_text = shorten_text(
            label.replace(
                "_",
                " ",
            ),
            22,
        )

        value_text = shorten_text(
            value,
            28,
        )

        draw.text(
            (
                left + 18,
                panel_y + 25,
            ),
            label_text.upper(),
            font=label_font,
            fill=YELLOW,
        )

        value_lines = wrap_text(
            draw,
            value_text,
            value_font,
            int(cell_width - 36),
        )

        if len(value_lines) > 2:
            value_lines = value_lines[:2]

        for line_index, line in enumerate(
            value_lines
        ):
            draw.text(
                (
                    left + 18,
                    panel_y
                    + 58
                    + line_index * 37,
                ),
                line,
                font=value_font,
                fill=WHITE,
            )


# ============================================================
# DRAW SOURCE FOOTER
# ============================================================

def draw_source_footer(
    draw,
    story,
):
    source = get_source_name(
        story
    )

    published = get_published(
        story
    )

    footer_y = HEIGHT - 105

    draw.rectangle(
        (
            0,
            footer_y,
            WIDTH,
            HEIGHT,
        ),
        fill=BLACK,
    )

    source_font = find_font(
        23,
        bold=True,
    )

    date_font = find_font(
        20,
        bold=False,
    )

    source_text = shorten_text(
        source,
        50,
    )

    draw.text(
        (
            45,
            footer_y + 25,
        ),
        f"Source: {source_text}",
        font=source_font,
        fill=WHITE,
    )

    if published:
        draw.text(
            (
                WIDTH - 45,
                footer_y + 28,
            ),
            published,
            font=date_font,
            fill=GREY,
            anchor="ra",
        )

    draw.text(
        (
            WIDTH - 45,
            footer_y + 62,
        ),
        "RIFT VALLEY WATCH",
        font=date_font,
        fill=RED,
        anchor="ra",
    )


# ============================================================
# DRAW SCENE
# ============================================================

def draw_scene(
    image,
    story,
):
    image = apply_photo_overlay(
        image
    )

    draw = ImageDraw.Draw(
        image
    )

    draw_top_bar(
        draw,
        story,
    )

    draw_title_block(
        draw,
        story,
    )

    draw_fact_strip(
        draw,
        story,
    )

    draw_source_footer(
        draw,
        story,
    )

    return image


# ============================================================
# GET AUDIO DURATION
# ============================================================

def get_audio_duration():
    if not NARRATION_FILE.exists():
        raise RuntimeError(
            f"Narration file does not exist:\n{NARRATION_FILE}"
        )

    ffprobe = shutil.which(
        "ffprobe"
    )

    if not ffprobe:
        raise RuntimeError(
            "ffprobe is required but was not found."
        )

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(NARRATION_FILE),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not determine narration duration."
        )

    try:
        duration = float(
            result.stdout.strip()
        )
    except Exception as exc:
        raise RuntimeError(
            "Invalid narration duration."
        ) from exc

    if duration <= 0:
        raise RuntimeError(
            "Narration duration is zero."
        )

    return duration


# ============================================================
# SCENE DURATIONS
# ============================================================

def calculate_scene_durations(
    total_duration,
    scene_count,
):
    if scene_count <= 0:
        return []

    # Avoid very short flashes.
    minimum_scene = 3.0

    if (
        total_duration
        >= minimum_scene * scene_count
    ):
        base = (
            total_duration
            / scene_count
        )

        return [
            base
            for _ in range(scene_count)
        ]

    # If narration is short, distribute proportionally
    # while ensuring a valid positive duration.
    duration = max(
        total_duration / scene_count,
        1.5,
    )

    durations = [
        duration
        for _ in range(scene_count)
    ]

    difference = (
        total_duration
        - sum(durations)
    )

    durations[-1] += difference

    if durations[-1] <= 0.5:
        durations[-1] = 0.5

    return durations


# ============================================================
# CREATE SCENE IMAGE
# ============================================================

def create_scene_image(
    source_path,
    story,
    output_path,
):
    image = prepare_photo(
        source_path
    )

    image = draw_scene(
        image,
        story,
    )

    image.save(
        output_path,
        "JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene image was not created: {output_path}"
        )

    if output_path.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene image is too small: {output_path}"
        )


# ============================================================
# CREATE SILENT SCENE VIDEO
# ============================================================

def create_scene_video(
    image_path,
    duration,
    output_path,
):
    duration = max(
        float(duration),
        0.5,
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-t",
        f"{duration:.3
