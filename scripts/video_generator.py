import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME REGIONAL NEWS VIDEO GENERATOR
# V2 - REAL PHOTO / BROADCAST NEWS STYLE
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
REPORT_FILE = ROOT / "data" / "visual_report.json"

SOURCE_DIR = ROOT / "assets" / "source"
OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

OPENER_DURATION = 4
STORY_DURATION = 9
OUTRO_DURATION = 4

MAX_STORIES = 10


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SCENES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):

    if bold:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            str(ROOT / "fonts" / "DejaVuSans-Bold.ttf"),
        ]

    else:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            str(ROOT / "fonts" / "DejaVuSans.ttf"),
        ]

    for candidate in candidates:

        path = Path(candidate)

        if path.exists():

            try:

                return ImageFont.truetype(
                    str(path),
                    size
                )

            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# JSON
# ============================================================

def load_story_data():

    if not STORY_FILE.exists():

        raise RuntimeError(
            "data/story.json was not found."
        )

    with open(
        STORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def is_story(item):

    if not isinstance(item, dict):
        return False

    keys = {
        "title",
        "headline",
        "description",
        "summary",
        "narration",
        "county",
        "category",
        "source",
        "url",
        "published",
        "score",
    }

    return (
        len(
            keys.intersection(
                item.keys()
            )
        ) >= 2
    )


def find_stories(data):

    found = []

    if isinstance(data, dict):

        if is_story(data):
            found.append(data)

        for value in data.values():

            found.extend(
                find_stories(value)
            )

    elif isinstance(data, list):

        for value in data:

            found.extend(
                find_stories(value)
            )

    return found


def get_stories(data):

    raw_stories = find_stories(data)

    unique = []
    seen = set()

    for story in raw_stories:

        identifier = (
            story.get("url")
            or story.get("title")
            or story.get("headline")
            or story.get("description")
            or ""
        )

        identifier = (
            str(identifier)
            .strip()
            .lower()
        )

        if not identifier:

            identifier = str(
                len(unique)
            )

        if identifier in seen:
            continue

        seen.add(identifier)
        unique.append(story)

    return unique[:MAX_STORIES]


# ============================================================
# TEXT
# ============================================================

def text_width(draw, text, font):

    box = draw.textbbox(
        (0, 0),
        str(text),
        font=font
    )

    return box[2] - box[0]


def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = str(
        text or ""
    ).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        test = (
            current
            + " "
            + word
        )

        if (
            text_width(
                draw,
                test,
                font
            )
            <= max_width
        ):

            current = test

        else:

            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped(
    draw,
    text,
    x,
    y,
    font,
    fill,
    max_width,
    max_lines=4,
    gap=8
):

    lines = wrap_text(
        draw,
        text,
        font,
        max_width
    )

    if len(lines) > max_lines:

        lines = lines[:max_lines]

        lines[-1] = (
            lines[-1].rstrip(".")
            + "..."
        )

    box = font.getbbox("Ag")

    line_height = (
        box[3]
        - box[1]
    )

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += (
            line_height
            + gap
        )

    return y


# ============================================================
# PHOTOS
# ============================================================

def get_photo_path(story):

    keys = [
        "image_path",
        "photo_path",
        "image_file",
        "photo_file",
    ]

    for key in keys:

        value = story.get(key)

        if not value:
            continue

        value = str(value)

        candidates = [
            ROOT / value,
            Path(value),
        ]

        for path in candidates:

            if (
                path.exists()
                and path.is_file()
            ):

                return path

    return None


def load_photo(path):

    if path is None:
        return None

    try:

        image = Image.open(path)

        image.load()

        return image.convert(
            "RGB"
        )

    except Exception as exc:

        log(
            "PHOTO WARNING: "
            + str(path)
            + " -> "
            + str(exc)
        )

        return None


def crop_photo(
    image,
    width,
    height
):

    if image is None:
        return None

    source_ratio = (
        image.width
        / image.height
    )

    target_ratio = (
        width
        / height
    )

    if source_ratio > target_ratio:

        new_height = image.height

        new_width = int(
            image.height
            * target_ratio
        )

    else:

        new_width = image.width

        new_height = int(
            image.width
            / target_ratio
        )

    left = max(
        0,
        (
            image.width
            - new_width
        )
        // 2
    )

    top = max(
        0,
        (
            image.height
            - new_height
        )
        // 2
    )

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height
        )
    )

    return image.resize(
        (
            width,
            height
        ),
        Image.Resampling.LANCZOS
    )


# ============================================================
# BRANDING
# ============================================================

def draw_header(draw):

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            96
        ),
        fill=(8, 11, 17)
    )

    draw.rectangle(
        (
            0,
            0,
            14,
            96
        ),
        fill=(220, 35, 45)
    )

    logo_font = get_font(
        30,
        True
    )

    draw.text(
        (
            38,
            28
        ),
        "RIFT VALLEY WATCH",
        font=logo_font,
        fill=(255, 255, 255)
    )

    small_font = get_font(
        21,
        True
    )

    label = "REGIONAL NEWS"

    tw = text_width(
        draw,
        label,
        small_font
    )

    draw.text(
        (
            WIDTH - tw - 38,
            34
        ),
        label,
        font=small_font,
        fill=(180, 187, 197)
    )


def draw_footer(draw):

    y = HEIGHT - 74

    draw.rectangle(
        (
            0,
            y,
            WIDTH,
            HEIGHT
        ),
        fill=(7, 10, 15)
    )

    font = get_font(
        20,
        True
    )

    draw.text(
        (
            38,
            y + 25
        ),
        "RIFT VALLEY WATCH",
        font=font,
        fill=(170, 177, 188)
    )


def draw_county(
    draw,
    county
):

    if not county:
        return

    county = str(
        county
    ).upper()

    font = get_font(
        25,
        True
    )

    tw = text_width(
        draw,
        county,
        font
    )

    draw.rounded_rectangle(
        (
            38,
            125,
            38 + tw + 40,
            180
        ),
        radius=7,
        fill=(220, 35, 45)
    )

    draw.text(
        (
            58,
            138
        ),
        county,
        font=font,
        fill=(255, 255, 255)
    )


# ============================================================
# OPENER
# ============================================================

def create_opener():

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (9, 12, 18)
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.rectangle(
        (
            0,
            0,
            15,
            HEIGHT
        ),
        fill=(220, 35, 45)
    )

    for y in range(
        250,
        1650,
        120
    ):

        draw.line(
            (
                60,
                y,
                WIDTH - 60,
                y
            ),
            fill=(27, 32, 41),
            width=2
        )

    small_font = get_font(
        34,
        True
    )

    title_font = get_font(
        92,
        True
    )

    subtitle_font = get_font(
        32,
        True
    )

    draw.text(
        (
            70,
            610
        ),
        "RIFT VALLEY",
        font=small_font,
        fill=(205, 211, 220)
    )

    draw.text(
        (
            65,
            670
        ),
        "WATCH",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw.rectangle(
        (
            70,
            795,
            400,
            803
        ),
        fill=(220, 35, 45)
    )

    draw.text(
        (
            70,
            850
        ),
        "REGIONAL NEWS BULLETIN",
        font=subtitle_font,
        fill=(185, 192, 202)
    )

    draw.text(
        (
            70,
            910
        ),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(
            23,
            True
        ),
        fill=(130, 138, 149)
    )

    draw_footer(draw)

    path = (
        SCENES_DIR
        / "opener.png"
    )

    image.save(
        path,
        "PNG"
    )

    return path


# ============================================================
# STORY IMAGE
# ============================================================

def create_story_image(
    story,
    number
):

    photo_path = get_photo_path(
        story
    )

    photo = load_photo(
        photo_path
    )

    canvas = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (10, 14, 20)
    )

    # --------------------------------------------------------
    # FULL BACKGROUND PHOTO
    # --------------------------------------------------------

    if photo is not None:

        background = crop_photo(
            photo,
            WIDTH,
            HEIGHT
        )

        background = background.filter(
            ImageFilter.GaussianBlur(18)
        )

        dark = Image.new(
            "RGBA",
            (
                WIDTH,
                HEIGHT
            ),
            (0, 0, 0, 150)
