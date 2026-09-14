from pathlib import Path
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION: RVW_VIDEO_V36_FULL_NEWS_REEL
#
# PURPOSE
# - Read data/selected_story.json
# - Resolve ONLY the exact selected article photographs
# - Never search Google for replacement images
# - Never use unrelated source-directory photographs
# - Recover exact files when path formatting differs
# - Handle escaped underscores
# - Handle extension mismatches safely
# - Remove duplicate photographs
# - Use every genuinely unique selected article photograph
# - Build a complete vertical news reel
# - Use the FULL narration duration
# - Never prematurely terminate the video because of -shortest
# - Add controlled photo movement
# - Add opening / story / update / source visual treatment
# - 1080x1920 vertical MP4
# - Narration from audio/narration.mp3
# - Reject Citizen / CTV / World Cup / avatar / placeholder
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

AUDIO_FILE = AUDIO_DIR / "narration.mp3"

FINAL_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_IMAGE_BYTES = 10000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

MIN_AUDIO_BYTES = 1000
MIN_VIDEO_BYTES = 100000

MAX_IMAGES = 6

# Small safety extension so video is never shorter than narration.
VIDEO_SAFETY_SECONDS = 1.50

# Opening / closing cards consume part of the narration timeline.
OPENING_SECONDS = 2.50
CLOSING_SECONDS = 2.50


# ============================================================
# FORBIDDEN VISUAL TERMS
# ============================================================

FORBIDDEN_TERMS = (
    "citizen",
    "citizen digital",
    "citizen tv",
    "ctv",
    "worldcup",
    "world_cup",
    "world cup",
    "avatar",
    "placeholder",
    "default_image",
    "default-image",
    "default image",
    "profile_picture",
    "profile-picture",
    "profile picture",
    "dummy",
    "generic",
    "generic image",
    "logo",
    "icon",
    "advert",
    "advertisement",
)


# ============================================================
# SUBPROCESS
# ============================================================

def run(command, label):
    print()
    print("=" * 72)
    print("RUNNING:", label)
    print("=" * 72)

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {result.returncode}"
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Missing JSON file: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"JSON file is empty: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except Exception as error:
        raise RuntimeError(
            f"Could not read JSON file {path}: {error}"
        )

    if not data:
        raise RuntimeError(
            f"JSON file contains no data: {path}"
        )

    return data


def get_story(data):
    """
    Supports all currently used selected-story schemas:

        {
            "story": {...}
        }

        {
            "stories": [{...}]
        }

        [
            {...}
        ]

        {
            "title": "...",
            "image_path": "..."
        }
    """

    if isinstance(data, dict):

        story_value = data.get("story")

        if isinstance(story_value, dict):
            return story_value

        stories_value = data.get("stories")

        if isinstance(stories_value, list):

            for item in stories_value:

                if isinstance(item, dict):
                    return item

            raise RuntimeError(
                "Selected story list contains no story object"
            )

        if isinstance(
            data.get("selected_story"),
            dict,
        ):
            return data["selected_story"]

        return data

    if isinstance(data, list):

        for item in data:

            if isinstance(item, dict):
                return item

        raise RuntimeError(
            "Selected story array contains no story object"
        )

    raise RuntimeError(
        "Selected story JSON has an unsupported structure"
    )


# ============================================================
# TEXT
# ============================================================

def clean_text(value, fallback=""):

    if value is None:
        return fallback

    if isinstance(
        value,
        (dict, list),
    ):
        return fallback

    value = str(value)

    value = value.replace(
        "\\_",
        "_",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value or fallback


def truncate_text(value, maximum):

    value = clean_text(value)

    if len(value) <= maximum:
        return value

    truncated = value[:maximum].rsplit(
        " ",
        1,
    )[0]

    return truncated.rstrip(
        " ,.;:-"
    ) + "…"


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):

    if bold:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]

    else:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for candidate in candidates:

        path = Path(candidate)

        if path.exists():

            try:
                return ImageFont.truetype(
                    str(path),
                    size,
                )

            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    value,
    selected_font,
    max_width,
    maximum=5,
):

    words = clean_text(value).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:

        trial = (
            f"{current} {word}"
        ).strip()

        try:

            box = draw.textbbox(
                (0, 0),
                trial,
                font=selected_font,
            )

            trial_width = (
                box[2] - box[0]
            )

        except Exception:

            trial_width = len(trial) * 20

        if trial_width <= max_width:

            current = trial

        else:

            if current:
                lines.append(current)

            current = word

            if len(lines) >= maximum:
                break

    if current and len(lines) < maximum:
        lines.append(current)

    return lines[:maximum]


def draw_wrapped_text(
    draw,
    value,
    x,
    y,
    max_width,
    selected_font,
    fill,
    gap=10,
    maximum=5,
):

    lines = wrap_text(
        draw,
        value,
        selected_font,
        max_width,
        maximum,
    )

    if not lines:
        return y

    try:

        bbox = selected_font.getbbox(
            "Ag"
        )

        line_height = (
            bbox[3] - bbox[1]
        )

    except Exception:

        line_height = 40

    for index, line in enumerate(lines):

        draw.text(
            (
                x,
                y + index * (
                    line_height + gap
                ),
            ),
            line,
            font=selected_font,
            fill=fill,
        )

    return y + len(lines) * (
        line_height + gap
    )


# ============================================================
# IMAGE PATH NORMALIZATION
# ============================================================

def normalize_path_string(value):

    value = str(value).strip()

    value = value.replace(
        "\\_",
        "_",
    )

    value = value.replace(
        "\\",
        "/",
    )

    value = value.strip(
        "\"'"
    )

    while value.startswith("./"):
        value = value[2:]

    return value


# ============================================================
# VALID IMAGE
# ============================================================

def valid_image(path):

    if not path:
        return False

    try:
        path = Path(path)

    except Exception:
        return False

    if not path.exists():
        return False

    if not path.is_file():
        return False

    try:

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

    except Exception:

        return False

    lowered = str(path).lower()

    for term in FORBIDDEN_TERMS:

        if term in lowered:
            return False

    try:

        with Image.open(path) as image:

            image.verify()

        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            image.load()

        return True

    except Exception:

        return False


# ============================================================
# IMAGE SIGNATURE
# ============================================================

def image_signature(path):

    try:

        with Image.open(path) as image:

            image = ImageOps.exif_transpose(
                image
            )

            image = image.convert(
                "RGB"
            )

            image.thumbnail(
                (96, 96),
                Image.Resampling.LANCZOS,
            )

            canvas = Image.new(
                "RGB",
                (96, 96),
                (0, 0, 0),
            )

            left = (
                96 - image.width
            ) // 2

            top = (
                96 - image.height
            ) // 2

            canvas.paste(
                image,
                (
                    left,
                    top,
                ),
            )

            return hashlib.sha256(
                canvas.tobytes()
            ).hexdigest()

    except Exception:

        return ""


# ============================================================
# EXACT SOURCE SEARCH
# ============================================================

def exact_source_search(filename):

    if not filename:
        return None

    filename = normalize_path_string(
        filename
    )

    wanted = Path(
        filename
    ).name

    if not wanted:
        return None

    direct = SOURCE_DIR / wanted

    if valid_image(direct):

        print(
            "[IMAGE] Exact source match:",
            direct,
        )

        return direct.resolve()

    try:

        for match in SOURCE_DIR.rglob(
            wanted
        ):

            if valid_image(match):

                print(
                    "[IMAGE] Recursive exact match:",
                    match,
                )

                return match.resolve()

    except Exception:
        pass

    return None


# ============================================================
# EXTENSION MISMATCH SEARCH
# ============================================================

def exact_stem_search(filename):

    if not filename:
        return None

    filename = normalize_path_string(
        filename
    )

    requested = Path(
        filename
    )

    stem = requested.stem.lower()

    if not stem:
        return None

    try:

        for match in SOURCE_DIR.rglob("*"):

            if not match.is_file():
                continue

            if match.stem.lower() != stem:
                continue

            if valid_image(match):

                print(
                    "[IMAGE] Extension mismatch recovery:",
                    match,
                )

                return match.resolve()

    except Exception:
        pass

    return None


# ============================================================
# RESOLVE EXACT IMAGE
# ============================================================

def resolve_image_path(value):

    if value is None:
        return None

    if isinstance(value, dict):

        value = (
            value.get("local_path")
            or value.get("path")
            or value.get("file")
            or value.get("image_path")
            or value.get("local_image")
            or value.get("photo_path")
        )

    if not value:
        return None

    value = normalize_path_string(
        value
    )

    if not value:
        return None

    candidate = Path(
        value
    )

    candidates = []

    if candidate.is_absolute():

        candidates.append(
            candidate
        )

    else:

        candidates.extend(
            [
                BASE_DIR / candidate,
                DATA_DIR / candidate,
                SOURCE_DIR / candidate,
            ]
        )

        if len(candidate.parts) == 1:

            candidates.append(
                SOURCE_DIR / candidate.name
            )

    seen = set()

    for item in candidates:

        try:
            item = item.resolve()

        except Exception:
            pass

        key = str(item)

        if key in seen:
            continue

        seen.add(key)

        print(
            "[IMAGE] Checking:",
            item,
        )

        if valid_image(item):

            print(
                "[IMAGE] VALID:",
                item,
            )

            return item

    recovered = exact_source_search(
        candidate.name
    )

    if recovered:
        return recovered

    recovered = exact_stem_search(
        candidate.name
    )

    if recovered:
        return recovered

    print(
        "[IMAGE] FAILED TO RESOLVE:",
        value,
    )

    return None


# ============================================================
# IMAGE REFERENCE EXTRACTION
# ============================================================

def append_image_candidate(
    candidates,
    value,
):

    if value is None:
        return

    if isinstance(value, str):

        value = value.strip()

        if value:
            candidates.append(
                value
            )

        return

    if isinstance(value, dict):

        possible = (
            value.get("local_path")
            or value.get("path")
            or value.get("file")
            or value.get("image_path")
            or value.get("local_image")
            or value.get("photo_path")
        )

        if possible:

            append_image_candidate(
                candidates,
                possible,
            )

        return

    if isinstance(value, list):

        for item in value:

            append_image_candidate(
                candidates,
                item,
            )


def find_selected_images(story):

    candidates = []

    fields = (
        "image_paths",
        "images",
        "image_path",
        "local_image",
        "local_images",
        "photo",
        "photos",
        "photo_path",
        "photo_paths",
        "image",
    )

    print()
    print("=" * 72)
    print("SELECTED STORY IMAGE REFERENCES")
    print("=" * 72)

    for field in fields:

        if field not in story:
            continue

        value = story.get(
            field
        )

        print(
            f"{field}:",
            repr(value),
        )

        append_image_candidate(
            candidates,
            value,
        )

    resolved = []
    seen_paths = set()
    seen_signatures = set()

    for candidate in candidates:

        path = resolve_image_path(
            candidate
        )

        if path is None:
            continue

        try:
            path = path.resolve()
        except Exception:
            pass

        path_key = str(path)

        if path_key in seen_paths:
            continue

        seen_paths.add(
            path_key
        )

        signature = image_signature(
            path
        )

        if signature:

            if signature in seen_signatures:

                print(
                    "[IMAGE] Duplicate photo skipped:",
                    path.name,
                )

                continue

            seen_signatures.add(
                signature
            )

        resolved.append(
            path
        )

        print(
            "[IMAGE] ACCEPTED ARTICLE PHOTO:",
            path,
        )

        if len(resolved) >= MAX_IMAGES:
            break

    return resolved


# ============================================================
# STORY INFORMATION
# ============================================================

def story_title(story):

    return clean_text(
        story.get("title")
        or story.get("headline")
        or story.get("name"),
        "Rift Valley Regional Update",
    )


def story_county(story):

    return clean_text(
        story.get("county")
        or story.get("location")
        or story.get("region"),
        "Rift Valley",
    )


def story_category(story):

    return clean_text(
        story.get("category")
        or story.get("section")
        or story.get("type"),
        "REGIONAL UPDATE",
    ).upper()


def story_summary(story):

    return clean_text(
        story.get("summary")
        or story.get("description")
        or story.get("excerpt")
        or story.get("body"),
        "",
    )


def story_source(story):

    source_data = story.get(
        "source",
        "",
    )

    if isinstance(
        source_data,
        dict,
    ):

        source = clean_text(
            source_data.get("name")
            or source_data.get("title")
            or source_data.get("source"),
            "Rift Valley Watch",
        )

    else:

        source = clean_text(
            source_data,
            "Rift Valley Watch",
        )

    lowered = source.lower()

    if (
        "citizen" in lowered
        or lowered == "ctv"
        or "citizen digital" in lowered
        or "citizen tv" in lowered
    ):

        return "Rift Valley Watch"

    return source


def story_date(story):

    return clean_text(
        story.get("published")
        or story.get("published_at")
        or story.get("date")
        or story.get("pub_date"),
        "",
    )


# ============================================================
# PREPARE IMAGE
# ============================================================

def prepare_image(path):

    with Image.open(path) as original:

        image = ImageOps.exif_transpose(
            original
        )

        image = image.convert(
            "RGB"
        )

    source_width, source_height = image.size

    if (
        source_width <= 0
        or source_height <= 0
    ):

        raise RuntimeError(
            f"Invalid image dimensions: {path}"
        )

    target_ratio = (
        WIDTH / HEIGHT
    )

    source_ratio = (
        source_width / source_height
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            new_height * source_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
            new_width / source_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
    )

    left = max(
        0,
        (new_width - WIDTH) // 2,
    )

    top = max(
        0,
        (new_height - HEIGHT) // 2,
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )

    return image


# ============================================================
# GRADIENT
# ============================================================

def add_gradient_overlay(image):

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    for y in range(
        HEIGHT
    ):

        position = y / HEIGHT

        if position < 0.40:

            alpha = int(
                175
                * (
                    1
                    - position / 0.40
                )
            )

        else:

            alpha = int(
                210
                * (
                    (position - 0.40)
                    / 0.60
                )
            )

        alpha = max(
            0,
            min(
                210,
                alpha,
            ),
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
                alpha,
            ),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


# ============================================================
# DRAW BACKGROUND STORY SCENE
# ============================================================

def decorate_scene(
    image,
    story,
    scene_number,
    scene_total,
):

    image = add_gradient_overlay(
        image
    )

    draw = ImageDraw.Draw(
        image
    )

    white = (
        255,
        255,
        255,
    )

    muted = (
        220,
        226,
        233,
    )

    yellow = (
        245,
        185,
        62,
    )

    dark = (
        5,
        12,
        21,
    )

    darker = (
        4,
        10,
        17,
    )

    brand_font = get_font(
        42,
        True,
    )

    label_font = get_font(
        30,
        True,
    )

    title_font = get_font(
        64,
        True,
    )

    body_font = get_font(
        34,
        False,
    )

    footer_font = get_font(
        23,
        False,
    )

    scene_font = get_font(
        22,
        True,
    )

    title = story_title(
        story
    )

    county = story_county(
        story
    )

    category = story_category(
        story
    )

    summary = story_summary(
        story
    )

    source = story_source(
        story
    )

    # --------------------------------------------------------
    # TOP BRAND BAR
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            132,
        ),
        fill=dark,
    )

    draw.rectangle(
        (
            0,
            126,
            WIDTH,
            134,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            38,
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=white,
    )

    # --------------------------------------------------------
    # STORY POSITION
    # --------------------------------------------------------

    if scene_total > 1:

        scene_label = (
            f"REGIONAL UPDATE  •  "
            f"{scene_number}/{scene_total}"
        )

    else:

        scene_label = "REGIONAL UPDATE"

    draw.text(
        (
            58,
            158,
        ),
        scene_label,
        font=scene_font,
        fill=muted,
    )

    # --------------------------------------------------------
    # COUNTY / CATEGORY
    # --------------------------------------------------------

    draw.text(
        (
            58,
            205,
        ),
        f"{county.upper()}  |  {category}",
        font=label_font,
        fill=yellow,
    )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    title_y = draw_wrapped_text(
        draw,
        title,
        58,
        290,
        WIDTH - 116,
        title_font,
        white,
        gap=12,
        maximum=5,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if summary:

        summary_y = max(
            title_y + 45,
            970,
        )

        summary_text = truncate_text(
            summary,
            430,
        )

        draw_wrapped_text(
            draw,
            summary_text,
            58,
            summary_y,
            WIDTH - 116,
            body_font,
            muted,
            gap=10,
            maximum=6,
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    published = story_date(
        story
    )

    if published:

        date_font = get_font(
            24,
            False,
        )

        draw.text(
            (
                58,
                HEIGHT - 175,
            ),
            published,
            font=date_font,
            fill=muted,
        )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    footer_y = HEIGHT - 125

    draw.rectangle(
        (
            0,
            footer_y - 25,
            WIDTH,
            HEIGHT,
        ),
        fill=darker,
    )

    draw.text(
        (
            58,
            footer_y + 15,
        ),
        f"SOURCE: {source}",
        font=footer_font,
        fill=muted,
    )

    return image


# ============================================================
# CREATE STORY SCENE IMAGE
# ============================================================

def create_scene_image(
    source_path,
    story,
    scene_number,
    scene_total,
    output_path,
):

    print()
    print(
        "[SCENE] Source photo:",
        source_path,
    )

    image = prepare_image(
        source_path
    )

    image = decorate_scene(
        image,
        story,
        scene_number,
        scene_total,
    )

    image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )

    if not output_path.exists():

        raise RuntimeError(
            f"Scene image was not created: {output_path}"
        )

    if output_path.stat().st_size < 50000:

        raise RuntimeError(
            f"Scene image is unexpectedly small: {output_path}"
        )


# ============================================================
# CREATE OPENING CARD
# ============================================================

def create_opening_card(
    story,
    output_path,
):

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT,
        ),
        (
            5,
            12,
            21,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    white = (
        255,
        255,
        255,
    )

    muted = (
        205,
        214,
        224,
    )

    yellow = (
        245,
        185,
        62,
    )

    brand_font = get_font(
        54,
        True,
    )

    label_font = get_font(
        32,
        True,
    )

    title_font = get_font(
        67,
        True,
    )

    county_font = get_font(
        31,
        True,
    )

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            150,
        ),
        fill=(
            3,
            8,
            15,
        ),
    )

    draw.rectangle(
        (
            0,
            142,
            WIDTH,
            151,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            48,
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=white,
    )

    draw.text(
        (
            58,
            245,
        ),
        "LATEST REGIONAL UPDATE",
        font=label_font,
        fill=yellow,
    )

    title = story_title(
        story
    )

    draw_wrapped_text(
        draw,
        title,
        58,
        350,
        WIDTH - 116,
        title_font,
        white,
        gap=14,
        maximum=6,
    )

    county = story_county(
        story
    )

    category = story_category(
        story
    )

    draw.text(
        (
            58,
            1260,
        ),
        f"{county.upper()}  |  {category}",
        font=county_font,
        fill=muted,
    )

    draw.rectangle(
        (
            58,
            1370,
            220,
            1378,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            1435,
        ),
        "ONE STORY • VERIFIED PHOTO • RIFT VALLEY",
        font=get_font(
            27,
            True,
        ),
        fill=muted,
    )

    draw.rectangle(
        (
            0,
            HEIGHT - 180,
            WIDTH,
            HEIGHT,
        ),
        fill=(
            3,
            8,
            15,
        ),
    )

    draw.text(
        (
            58,
            HEIGHT - 115,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            28,
            True,
        ),
        fill=white,
    )

    image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )


# ============================================================
# CREATE CLOSING CARD
# ============================================================

def create_closing_card(
    story,
    output_path,
):

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT,
        ),
        (
            5,
            12,
            21,
        ),
    )

    draw = ImageDraw.Draw(
        image
    )

    white = (
        255,
        255,
        255,
    )

    muted = (
        205,
        214,
        224,
    )

    yellow = (
        245,
        185,
        62,
    )

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            150,
        ),
        fill=(
            3,
            8,
            15,
        ),
    )

    draw.rectangle(
        (
            0,
            142,
            WIDTH,
            151,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            48,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            54,
            True,
        ),
        fill=white,
    )

    draw.text(
        (
            58,
            310,
        ),
        "STORY SOURCE",
        font=get_font(
            32,
            True,
        ),
        fill=yellow,
    )

    source = story_source(
        story
    )

    draw_wrapped_text(
        draw,
        source,
        58,
        410,
        WIDTH - 116,
        get_font(
            58,
            True,
        ),
        white,
        gap=12,
        maximum=4,
    )

    title = story_title(
        story
    )

    draw_wrapped_text(
        draw,
        title,
        58,
        720,
        WIDTH - 116,
        get_font(
            38,
            False,
        ),
        muted,
        gap=10,
        maximum=6,
    )

    draw.rectangle(
        (
            58,
            1210,
            WIDTH - 58,
            1218,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            1300,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            44,
            True,
        ),
        fill=white,
    )

    draw.text(
        (
            58,
            1380,
        ),
        "Regional news and current affairs",
        font=get_font(
            30,
            False,
        ),
        fill=muted,
    )

    draw.rectangle(
        (
            0,
            HEIGHT - 180,
            WIDTH,
            HEIGHT,
        ),
        fill=(
            3,
            8,
            15,
        ),
    )

    draw.text(
        (
            58,
            HEIGHT - 115,
        ),
        "END OF UPDATE",
        font=get_font(
            28,
            True,
        ),
        fill=yellow,
    )

    image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )


# ============================================================
# AUDIO DURATION
# ============================================================

def audio_duration():

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            f"Missing narration file: {AUDIO_FILE}"
        )

    if AUDIO_FILE.stat().st_size < MIN_AUDIO_BYTES:

        raise RuntimeError(
            "Narration file is empty or too small"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(AUDIO_FILE),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Could not read narration duration:\n"
            + result.stdout
        )

    try:

        duration = float(
            result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Narration duration could not be parsed:\n"
            + result.stdout
        )

    if duration <= 0:

        raise RuntimeError(
            "Narration duration is invalid"
        )

    print(
        "[AUDIO] Duration:",
        f"{duration:.3f}",
        "seconds",
    )

    return duration


# ============================================================
# GENERIC IMAGE SCENE VIDEO
# ============================================================

def create_scene_video(
    scene_image,
    output_path,
    duration,
    movement_index=0,
):

    duration = max(
        1.0,
        float(duration),
    )

    # --------------------------------------------------------
    # Controlled Ken Burns movement.
    #
    # Different scenes use slightly different directions.
    # The photo remains the SAME selected article photo.
    # --------------------------------------------------------

    zoom_in = (
        movement_index % 2 == 0
    )

    if zoom_in:

        zoom_filter = (
            "scale="
            f"{WIDTH * 1.08:.0f}:"
            f"{HEIGHT * 1.08:.0f},"
            "crop="
            f"{WIDTH}:{HEIGHT}:"
            "(iw-ow)/2:"
            "(ih-oh)/2"
        )

    else:

        zoom_filter = (
            "scale="
            f"{WIDTH * 1.05:.0f}:"
            f"{HEIGHT * 1.05:.0f},"
            "crop="
            f"{WIDTH}:{HEIGHT}:"
            "(iw-ow)/2:"
            "(ih-oh)/2"
        )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-loop",
        "1",

        "-framerate",
        str(FPS),

        "-i",
        str(scene_image),

        "-t",
        f"{duration:.3f}",

        "-vf",
        (
            zoom_filter
            + ",format=yuv420p"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-an",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run(
        command,
        f"Creating {output_path.name}",
    )

    if not output_path.exists():

        raise RuntimeError(
            f"Scene video was not created: {output_path}"
        )

    if output_path.stat().st_size < 50000:

        raise RuntimeError(
            f"Scene video is unexpectedly small: {output_path}"
        )


# ============================================================
# CONCATENATE
# ============================================================

def concatenate_scene_videos(
    scene_videos,
    output_path,
):

    if not scene_videos:

        raise RuntimeError(
            "No scene videos available"
        )

    concat_file = (
        WORK_DIR
        / "concat.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        for video in scene_videos:

            resolved = video.resolve()

            safe_path = str(
                resolved
            ).replace(
                "'",
                "'\\''",
            )

            file.write(
                f"file '{safe_path}'\n"
            )

    command = [
        "ffmpeg",
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
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-an",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run(
        command,
        "Concatenating scene videos",
    )

    if not output_path.exists():

        raise RuntimeError(
            "Silent video was not created"
        )

    if output_path.stat().st_size < MIN_VIDEO_BYTES:

        raise RuntimeError(
            "Concatenated silent video is too small"
        )


# ============================================================
# VIDEO DURATION
# ============================================================

def video_duration(path):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Could not read video duration:\n"
            + result.stdout
        )

    try:

        value = float(
            result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Video duration could not be parsed:\n"
            + result.stdout
        )

    return value


# ============================================================
# ADD AUDIO
# ============================================================

def add_audio(
    silent_video,
    narration_duration,
):

    if not silent_video.exists():

        raise RuntimeError(
            f"Silent video does not exist: {silent_video}"
        )

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            f"Narration does not exist: {AUDIO_FILE}"
        )

    silent_duration = video_duration(
        silent_video
    )

    print(
        "[VIDEO] Silent video duration:",
        f"{silent_duration:.3f}",
        "seconds",
    )

    print(
        "[AUDIO] Required narration duration:",
        f"{narration_duration:.3f}",
        "seconds",
    )

    # The silent video must be longer than the narration.
    if silent_duration + 0.10 < narration_duration:

        raise RuntimeError(
            "Silent video is shorter than narration. "
            f"Video={silent_duration:.3f}s "
            f"Audio={narration_duration:.3f}s"
        )

    if FINAL_FILE.exists():

        FINAL_FILE.unlink()

    # --------------------------------------------------------
    # IMPORTANT:
    # NO -shortest.
    #
    # The video is deliberately longer than narration.
    # The audio is therefore allowed to finish naturally.
    # --------------------------------------------------------

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-i",
        str(silent_video),

        "-i",
        str(AUDIO_FILE),

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

        "-t",
        f"{narration_duration + 0.20:.3f}",

        "-movflags",
        "+faststart",

        str(FINAL_FILE),
    ]

    run(
        command,
        "Adding narration",
    )


# ============================================================
# FINAL VIDEO PROBE
# ============================================================

def probe_final_video():

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_FILE),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Could not inspect final MP4:\n"
            + result.stdout
        )

    print()
    print("=" * 72)
    print("FINAL VIDEO PROBE")
    print("=" * 72)
    print(result.stdout)

    return result.stdout


# ============================================================
# VALIDATE FINAL VIDEO
# ============================================================

def validate_final_video(
    narration_duration,
):

    if not FINAL_FILE.exists():

        raise RuntimeError(
            "Final MP4 was not created"
        )

    size = FINAL_FILE.stat().st_size

    if size < MIN_VIDEO_BYTES:

        raise RuntimeError(
            f"Final MP4 is too small: {size} bytes"
        )

    output = probe_final_video()

    compact = output.replace(
        " ",
        "",
    ).lower()

    if "codec_type=video" not in compact:

        raise RuntimeError(
            "Final MP4 has no video stream"
        )

    if "codec_type=audio" not in compact:

        raise RuntimeError(
            "Final MP4 has no audio stream"
        )

    if "width=1080" not in compact:

        raise RuntimeError(
            "Final MP4 width is not 1080"
        )

    if "height=1920" not in compact:

        raise RuntimeError(
            "Final MP4 height is not 1920"
        )

    final_duration = video_duration(
        FINAL_FILE
    )

    print(
        "[FINAL] Duration:",
        f"{final_duration:.3f}",
        "seconds",
    )

    print(
        "[FINAL] Narration:",
        f"{narration_duration:.3f}",
        "seconds",
    )

    # Final MP4 must contain essentially the entire narration.
    if final_duration + 0.25 < narration_duration:

        raise RuntimeError(
            "FINAL VIDEO IS SHORTER THAN NARRATION. "
            f"Video={final_duration:.3f}s "
            f"Audio={narration_duration:.3f}s"
        )

    # Prevent accidental tiny/truncated output.
    minimum_expected = max(
        5.0,
        narration_duration - 0.25,
    )

    if final_duration < minimum_expected:

        raise RuntimeError(
            "Final video appears prematurely truncated. "
            f"Expected at least {minimum_expected:.3f}s, "
            f"got {final_duration:.3f}s"
        )

    print()
    print("=" * 72)
    print("FINAL VIDEO VALIDATED")
    print("=" * 72)

    print(
        "FILE:",
        FINAL_FILE,
    )

    print(
        "SIZE:",
        size,
        "bytes",
    )

    print(
        "DURATION:",
        f"{final_duration:.3f}",
        "seconds",
    )

    return final_duration


# ============================================================
# CLEAN WORK DIRECTORY
# ============================================================

def clean_work_directory():

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in WORK_DIR.iterdir():

        try:

            if (
                item.is_file()
                or item.is_symlink()
            ):

                item.unlink()

            elif item.is_dir():

                shutil.rmtree(
                    item
                )

        except Exception as error:

            print(
                "[WORK] Could not remove:",
                item,
                error,
            )


# ============================================================
# SCENE DURATION PLANNER
# ============================================================

def calculate_scene_durations(
    narration_duration,
    image_count,
):

    if image_count <= 0:

        raise RuntimeError(
            "Cannot calculate scene durations without images"
        )

    # --------------------------------------------------------
    # ONE PHOTO
    #
    # The single real article photo receives the entire
    # narration duration. No premature short clip.
    # --------------------------------------------------------

    if image_count == 1:

        return [
            narration_duration
        ]

    # --------------------------------------------------------
    # MULTIPLE PHOTOS
    #
    # Reserve time for opening and closing cards while still
    # allowing article photos to occupy the majority of the reel.
    # --------------------------------------------------------

    usable = (
        narration_duration
        - OPENING_SECONDS
        - CLOSING_SECONDS
    )

    if usable < (
        image_count * 2.0
    ):

        usable = narration_duration

    each = (
        usable
        / image_count
    )

    durations = [
        each
        for _ in range(image_count)
    ]

    total = sum(
        durations
    )

    difference = (
        usable - total
    )

    durations[-1] += difference

    # If opening/closing cards are included, return the full
    # sequence durations separately through the caller.
    return durations


# ============================================================
# CREATE CARD VIDEO
# ============================================================

def create_card_video(
    image_path,
    output_path,
    duration,
):

    duration = max(
        1.0,
        float(duration),
    )

    command = [
        "ffmpeg",
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
        f"{duration:.3f}",

        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT},"
            "format=yuv420p"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-an",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run(
        command,
        f"Creating card {output_path.name}",
    )

    if not output_path.exists():

        raise RuntimeError(
            f"Card video was not created: {output_path}"
        )


# ============================================================
# CREATE STORY REEL
# ============================================================

def create_story_reel(
    story,
    images,
    narration_duration,
):

    clean_work_directory()

    scene_videos = []

    image_count = len(
        images
    )

    print()
    print("=" * 72)
    print("VIDEO STRUCTURE")
    print("=" * 72)

    print(
        "NARRATION:",
        f"{narration_duration:.2f}s",
    )

    print(
        "ARTICLE PHOTOS:",
        image_count,
    )

    # --------------------------------------------------------
    # VERY SHORT NARRATION
    #
    # For very short audio, avoid allocating too much time
    # to separate opening/closing cards.
    # --------------------------------------------------------

    use_cards = (
        image_count > 1
        and narration_duration >= 12.0
    )

    if use_cards:

        opening_duration = min(
            OPENING_SECONDS,
            narration_duration * 0.12,
        )

        closing_duration = min(
            CLOSING_SECONDS,
            narration_duration * 0.12,
        )

        article_duration = (
            narration_duration
            - opening_duration
            - closing_duration
        )

        if article_duration <= (
            image_count * 1.5
        ):

            use_cards = False

    # --------------------------------------------------------
    # OPENING CARD
    # --------------------------------------------------------

    if use_cards:

        opening_image = (
            WORK_DIR
            / "opening_card.jpg"
        )

        opening_video = (
            WORK_DIR
            / "opening_card.mp4"
        )

        create_opening_card(
            story,
            opening_image,
        )

        create_card_video(
            opening_image,
            opening_video,
            opening_duration,
        )

        scene_videos.append(
            opening_video
        )

    # --------------------------------------------------------
    # ARTICLE PHOTO DURATIONS
    # --------------------------------------------------------

    if use_cards:

        photo_total = article_duration

    else:

        photo_total = narration_duration

    each = (
        photo_total
        / image_count
    )

    photo_durations = [
        each
        for _ in range(image_count)
    ]

    photo_durations[-1] = (
        photo_total
        - sum(
            photo_durations[:-1]
        )
    )

    # --------------------------------------------------------
    # ARTICLE PHOTOS
    # --------------------------------------------------------

    for index, image_path in enumerate(
        images,
        start=1,
    ):

        scene_image = (
            WORK_DIR
            / f"scene_{index:02d}.jpg"
        )

        scene_video = (
            WORK_DIR
            / f"scene_{index:02d}.mp4"
        )

        scene_duration = (
            photo_durations[index - 1]
        )

        print()
        print("=" * 72)
        print(
            f"ARTICLE PHOTO SCENE {index}/{image_count}"
        )
        print("=" * 72)

        print(
            "REAL ARTICLE PHOTO:",
            image_path,
        )

        print(
            "DURATION:",
            f"{scene_duration:.3f}",
            "seconds",
        )

        create_scene_image(
            image_path,
            story,
            index,
            image_count,
            scene_image,
        )

        create_scene_video(
            scene_image,
            scene_video,
            scene_duration,
            movement_index=index - 1,
        )

        scene_videos.append(
            scene_video
        )

    # --------------------------------------------------------
    # CLOSING CARD
    # --------------------------------------------------------

    if use_cards:

        closing_image = (
            WORK_DIR
            / "closing_card.jpg"
        )

        closing_video = (
            WORK_DIR
            / "closing_card.mp4"
        )

        create_closing_card(
            story,
            closing_image,
        )

        create_card_video(
            closing_image,
            closing_video,
            closing_duration,
        )

        scene_videos.append(
            closing_video
        )

    # --------------------------------------------------------
    # SAFETY DURATION CHECK
    # --------------------------------------------------------

    planned_duration = sum(
        video_duration(video)
        for video in scene_videos
    )

    required_duration = (
        narration_duration
        + VIDEO_SAFETY_SECONDS
    )

    print()
    print(
        "[VIDEO] Planned duration:",
        f"{planned_duration:.3f}s",
    )

    print(
        "[VIDEO] Required duration:",
        f"{required_duration:.3f}s",
    )

    # --------------------------------------------------------
    # If ffmpeg rounding made the planned duration too short,
    # create an extra safety tail using the final article scene.
    # --------------------------------------------------------

    if planned_duration < required_duration:

        extra_duration = (
            required_duration
            - planned_duration
            + 0.25
        )

        safety_image = (
            WORK_DIR
            / "safety_tail.jpg"
        )

        safety_video = (
            WORK_DIR
            / "safety_tail.mp4"
        )

        # Reuse the LAST SELECTED ARTICLE PHOTO only.
        # This is not a new photo and not an unrelated image.
        last_photo = images[-1]

        create_scene_image(
            last_photo,
            story,
            image_count,
            image_count,
            safety_image,
        )

        create_scene_video(
            safety_image,
            safety_video,
            extra_duration,
            movement_index=image_count,
        )

        scene_videos.append(
            safety_video
        )

    # --------------------------------------------------------
    # CONCATENATE
    # --------------------------------------------------------

    silent_video = (
        WORK_DIR
        / "silent_video.mp4"
    )

    concatenate_scene_videos(
        scene_videos,
        silent_video,
    )

    final_silent_duration = video_duration(
        silent_video
    )

    print()
    print(
        "[VIDEO] Final silent duration:",
        f"{final_silent_duration:.3f}s",
    )

    if final_silent_duration + 0.10 < narration_duration:

        raise RuntimeError(
            "Silent video is shorter than narration after "
            "scene concatenation."
        )

    return silent_video


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 72)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("VERSION: RVW_VIDEO_V36_FULL_NEWS_REEL")
    print("=" * 72)

    # --------------------------------------------------------
    # DIRECTORIES
    # --------------------------------------------------------

    for directory in (
        DATA_DIR,
        SOURCE_DIR,
        WORK_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
    ):

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------------
    # REQUIRED FILES
    # --------------------------------------------------------

    if not STORY_FILE.exists():

        raise RuntimeError(
            f"Missing selected story: {STORY_FILE}"
        )

    if not SCRIPT_FILE.exists():

        raise RuntimeError(
            f"Missing selected script: {SCRIPT_FILE}"
        )

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            f"Missing narration: {AUDIO_FILE}"
        )

    print()
    print(
        "[INPUT] Story:",
        STORY_FILE,
    )

    print(
        "[INPUT] Script:",
        SCRIPT_FILE,
    )

    print(
        "[INPUT] Audio:",
        AUDIO_FILE,
    )

    # --------------------------------------------------------
    # LOAD STORY
    # --------------------------------------------------------

    story_data = load_json(
        STORY_FILE
    )

    story = get_story(
        story_data
    )

    print()
    print("=" * 72)
    print("SELECTED STORY")
    print("=" * 72)

    print(
        "TITLE:",
        story_title(story),
    )

    print(
        "COUNTY:",
        story_county(story),
    )

    print(
        "CATEGORY:",
        story_category(story),
    )

    print(
        "SOURCE:",
        story_source(story),
    )

    # --------------------------------------------------------
    # HARD FORBIDDEN STORY CHECK
    # --------------------------------------------------------

    title_lower = (
        story_title(story)
        .lower()
    )

    source_lower = (
        story_source(story)
        .lower()
    )

    if (
        "gachagua" in title_lower
        or "rigathi gachagua" in title_lower
        or "gachagua" in source_lower
    ):

        raise RuntimeError(
            "Forbidden Rigathi Gachagua story reached renderer"
        )

    # --------------------------------------------------------
    # FIND EXACT SELECTED ARTICLE PHOTOS
    # --------------------------------------------------------

    images = find_selected_images(
        story
    )

    if not images:

        print()
        print("=" * 72)
        print("IMAGE RESOLUTION FAILURE")
        print("=" * 72)

        print(
            "The selected story contains image references,"
        )

        print(
            "but none could be resolved to valid physical article photographs."
        )

        print()
        print(
            "SOURCE DIRECTORY:",
            SOURCE_DIR,
        )

        if SOURCE_DIR.exists():

            print()
            print(
                "FILES CURRENTLY IN assets/source:"
            )

            for item in sorted(
                SOURCE_DIR.rglob("*")
            ):

                if item.is_file():

                    try:
                        size = item.stat().st_size
                    except Exception:
                        size = 0

                    print(
                        " -",
                        item.name,
                        "(",
                        size,
                        "bytes )",
                    )

        raise RuntimeError(
            "No valid real article photographs found "
            "in selected_story.json"
        )

    # --------------------------------------------------------
    # PHOTO SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("REAL ARTICLE PHOTOS READY")
    print("=" * 72)

    for index, image in enumerate(
        images,
        start=1,
    ):

        print(
            f"{index}.",
            image,
        )

    print()
    print(
        "UNIQUE ARTICLE PHOTOS:",
        len(images),
    )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    narration_duration = audio_duration()

    # --------------------------------------------------------
    # BUILD COMPLETE STORY REEL
    # --------------------------------------------------------

    silent_video = create_story_reel(
        story,
        images,
        narration_duration,
    )

    # --------------------------------------------------------
    # ADD FULL NARRATION
    # --------------------------------------------------------

    add_audio(
        silent_video,
        narration_duration,
    )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    validate_final_video(
        narration_duration
    )

    print()
    print("=" * 72)
    print("GENERATION COMPLETED SUCCESSFULLY")
    print("=" * 72)

    print(
        "FINAL MP4:",
        FINAL_FILE,
    )

    print(
        "ARTICLE PHOTOS USED:",
        len(images),
    )

    print(
        "NARRATION DURATION:",
        f"{narration_duration:.3f}s",
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print()
        print("=" * 72)
        print("RIFT VALLEY WATCH GENERATOR FAILED")
        print("=" * 72)

        print(
            "ERROR:",
            error,
        )

        print("=" * 72)

        sys.exit(1)
