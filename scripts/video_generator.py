# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR V7
#
# REBUILT FROM SCRATCH
#
# OUTPUT:
#   output/rift_valley_watch.mp4
#
# FORMAT:
#   1080 x 1920
#   30 FPS
#   H.264 + AAC
#   Vertical 9:16
#
# DESIGN:
#   Professional regional-news bulletin
#   Real photographs
#   Strong headline presentation
#   Key facts
#   Regional/location graphic
#   Route/project visual
#   Impact
#   Official statement
#   Clean outro
#
# IMPORTANT:
#   NO SOURCE CARD
#   NO RAW PYTHON DICTIONARIES ON SCREEN
#   NO SOURCE URL ON SCREEN
#   NO STATIC SINGLE-CARD FREEZE
# ============================================================

import os
import re
import json
import math
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ROOT / "output" / "audio"
SCENES_DIR = ROOT / "output" / "scenes"
OUTPUT_DIR = ROOT / "output"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"
VISUAL_REPORT = DATA_DIR / "visual_report.json"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

VIDEO_BITRATE = "6500k"
AUDIO_BITRATE = "192k"

FONT_DIRS = [
    ROOT / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
]

# ============================================================
# COLORS
# ============================================================

BLACK = (7, 10, 15)
WHITE = (248, 249, 250)
LIGHT = (220, 225, 232)
GREY = (150, 158, 170)
DARK_GREY = (35, 41, 50)

RED = (210, 35, 45)
YELLOW = (242, 190, 55)
GREEN = (45, 170, 105)
BLUE = (45, 105, 190)

# ============================================================
# UTILITIES
# ============================================================


def run_command(command):
    print()
    print("COMMAND:")
    print(" ".join(str(x) for x in command))
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}"
        )

    return result


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def ffprobe_exists():
    return shutil.which("ffprobe") is not None


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def safe_filename(value):
    value = clean_text(value)

    value = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        value,
    )

    return value[:80]


# ============================================================
# FONT HANDLING
# ============================================================


def find_font(bold=False):
    if bold:
        names = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
        ]
    else:
        names = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
        ]

    for directory in FONT_DIRS:
        if not directory.exists():
            continue

        for name in names:
            path = directory / name

            if path.exists():
                return str(path)

    return None


FONT_REGULAR = find_font(False)
FONT_BOLD = find_font(True)


def get_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR

    if path:
        return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================


def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    text,
    x,
    y,
    max_width,
    font,
    fill,
    line_gap=12,
):
    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=font,
        )

        current_y += (
            bbox[3] - bbox[1] + line_gap
        )

    return current_y


# ============================================================
# PHOTO HANDLING
# ============================================================


def find_story_photo(story):
    candidates = []

    image_path = story.get("image_path")

    if image_path:
        candidates.append(ROOT / image_path)

    image_url = story.get("image_url")

    # URL is not downloaded here.
    # news_engine.py is responsible for downloading it.

    story_id = story.get("id")

    if story_id:
        candidates.extend(
            SOURCE_DIR.glob(
                f"*{safe_filename(story_id)}*"
            )
        )

    title = safe_filename(
        story.get("title", "")
    )

    if title:
        candidates.extend(
            SOURCE_DIR.glob(
                f"*{title[:30]}*"
            )
        )

    candidates.extend(
        SOURCE_DIR.glob("story_*")
    )

    seen = set()

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        if str(candidate) in seen:
            continue

        seen.add(str(candidate))

        if not candidate.exists():
            continue

        try:
            with Image.open(candidate) as image:
                width, height = image.size

                if width < 300 or height < 300:
                    continue

                if width * height < 150000:
                    continue

                return candidate

        except Exception:
            continue

    return None


def crop_photo(photo_path):
    try:
        image = Image.open(photo_path).convert("RGB")
    except Exception:
        return None

    target_ratio = WIDTH / HEIGHT
    source_ratio = image.width / image.height

    if source_ratio > target_ratio:
        new_width = int(
            image.height * target_ratio
        )

        left = (
            image.width - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                image.height,
            )
        )

    else:
        new_height = int(
            image.width / target_ratio
        )

        top = (
            image.height - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                image.width,
                top + new_height,
            )
        )

    image = image.resize(
        (WIDTH, HEIGHT),
        Image.Resampling.LANCZOS,
    )

    return image


def create_photo_background(photo_path):
    if not photo_path:
        return None

    image = crop_photo(photo_path)

    if image is None:
        return None

    # Slightly darken photo so typography remains broadcast-clean.
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 90),
    )

    image = image.convert("RGBA")

    image.alpha_composite(overlay)

    return image.convert("RGB")


# ============================================================
# GRAPHIC BACKGROUNDS
# ============================================================


def create_news_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BLACK,
    )

    draw = ImageDraw.Draw(image)

    # Broadcast-style horizontal bands
    for y in range(0, HEIGHT, 120):
        shade = int(
            12 + (y / HEIGHT) * 15
        )

        draw.rectangle(
            (0, y, WIDTH, y + 118),
            fill=(
                shade,
                shade + 3,
                shade + 8,
            ),
        )

    # Fine grid
    for x in range(0, WIDTH, 90):
        draw.line(
            (x, 0, x, HEIGHT),
            fill=(24, 29, 36),
            width=1,
        )

    for y in range(0, HEIGHT, 90):
        draw.line(
            (0, y, WIDTH, y),
            fill=(24, 29, 36),
            width=1,
        )

    # Red broadcast accent
    draw.rectangle(
        (0, 0, WIDTH, 16),
        fill=RED,
    )

    return image


def add_header(
    image,
    section,
    county="",
    breaking=False,
):
    draw = ImageDraw.Draw(image)

    # Header
    draw.rectangle(
        (0, 16, WIDTH, 135),
        fill=(8, 12, 18),
    )

    draw.rectangle(
        (0, 135, WIDTH, 141),
        fill=RED,
    )

    logo_font = get_font(
        44,
        bold=True,
    )

    draw.text(
        (55, 48),
        "RIFT VALLEY",
        font=logo_font,
        fill=WHITE,
    )

    draw.text(
        (55, 91),
        "WATCH",
        font=get_font(
            25,
            bold=True,
        ),
        fill=YELLOW,
    )

    section_font = get_font(
        27,
        bold=True,
    )

    section_text = clean_text(
        section
    ).upper()

    bbox = draw.textbbox(
        (0, 0),
        section_text,
        font=section_font,
    )

    section_width = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            WIDTH - section_width - 55,
            53,
        ),
        section_text,
        font=section_font,
        fill=WHITE,
    )

    if county:
        county_font = get_font(
            23,
            bold=True,
        )

        draw.text(
            (55, 150),
            clean_text(county).upper(),
            font=county_font,
            fill=YELLOW,
        )

    if breaking:
        draw.rectangle(
            (
                WIDTH - 245,
                150,
                WIDTH - 35,
                198,
            ),
            fill=RED,
        )

        draw.text(
            (
                WIDTH - 220,
                159,
            ),
            "LATEST",
            font=get_font(
                22,
                bold=True,
            ),
            fill=WHITE,
        )


# ============================================================
# CARD / PANEL HELPERS
# ============================================================


def rounded_panel(
    draw,
    box,
    fill=(15, 20, 28),
    outline=(55, 63, 74),
    radius=28,
    width=2,
):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def accent_bar(
    draw,
    x,
    y,
    width=90,
    height=8,
):
    draw.rounded_rectangle(
        (
            x,
            y,
            x + width,
            y + height,
        ),
        radius=4,
        fill=RED,
    )


# ============================================================
# INTRO
# ============================================================


def create_intro():
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(7, 10, 15),
    )

    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=RED,
    )

    # Large broadcast mark
    draw.text(
        (70, 610),
        "RIFT VALLEY",
        font=get_font(
            82,
            bold=True,
        ),
        fill=WHITE,
    )

    draw.text(
        (70, 710),
        "WATCH",
        font=get_font(
            105,
            bold=True,
        ),
        fill=YELLOW,
    )

    accent_bar(
        draw,
        75,
        850,
        180,
        10,
    )

    draw.text(
        (75, 900),
        "REGIONAL NEWS BULLETIN",
        font=get_font(
            34,
            bold=True,
        ),
        fill=LIGHT,
    )

    draw.text(
        (75, 955),
        "Bomet • Kericho • Nakuru • Narok • Nandi",
        font=get_font(
            25,
            bold=False,
        ),
        fill=GREY,
    )

    draw.text(
        (75, 1000),
        "Uasin Gishu • Trans Nzoia • Turkana • Samburu",
        font=get_font(
            25,
            bold=False,
        ),
        fill=GREY,
    )

    draw.text(
        (75, 1060),
        "Elgeyo-Marakwet • West Pokot • Laikipia • Kajiado",
        font=get_font(
            25,
            bold=False,
        ),
        fill=GREY,
    )

    now = datetime.now().strftime(
        "%d %b %Y"
    )

    draw.text(
        (75, 1160),
        now.upper(),
        font=get_font(
            26,
            bold=True,
        ),
        fill=YELLOW,
    )

    return image


# ============================================================
# HEADLINE SCENE
# ============================================================


def create_headline_scene(story):
    photo = find_story_photo(story)

    if photo:
        image = create_photo_background(
            photo
        )
    else:
        image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        story.get("category", "REGIONAL NEWS"),
        story.get("county", ""),
        breaking=True,
    )

    # Dark lower panel
    panel_top = 720

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            HEIGHT,
        ),
        fill=(6, 9, 14),
    )

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            panel_top + 8,
        ),
        fill=RED,
    )

    label_font = get_font(
        26,
        bold=True,
    )

    draw.text(
        (60, 790),
        "REGIONAL UPDATE",
        font=label_font,
        fill=YELLOW,
    )

    title = clean_text(
        story.get("title", "")
    )

    draw_wrapped_text(
        draw,
        title,
        60,
        850,
        WIDTH - 120,
        get_font(
            57,
            bold=True,
        ),
        WHITE,
        line_gap=16,
    )

    summary = clean_text(
        story.get("summary", "")
    )

    if summary:
        draw_wrapped_text(
            draw,
            summary,
            60,
            1230,
            WIDTH - 120,
            get_font(
                29,
                bold=False,
            ),
            LIGHT,
            line_gap=12,
        )

    # Bottom ticker
    draw.rectangle(
        (
            0,
            HEIGHT - 105,
            WIDTH,
            HEIGHT,
        ),
        fill=(10, 14, 20),
    )

    draw.text(
        (55, HEIGHT - 75),
        "RIFT VALLEY WATCH",
        font=get_font(
            24,
            bold=True,
        ),
        fill=RED,
    )

    return image


# ============================================================
# KEY FACTS SCENE
# ============================================================


def create_key_facts_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "KEY FACTS",
        story.get("county", ""),
    )

    draw.text(
        (60, 270),
        "WHAT WE KNOW",
        font=get_font(
            48,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        345,
        125,
        9,
    )

    facts = story.get(
        "verified_facts",
        [],
    )

    # Accept both:
    # [{"label": "...", "value": "..."}]
    # and strings.
    normalized = []

    for fact in facts:
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            )

            value = clean_text(
                fact.get("value", "")
            )

            if value:
                normalized.append(
                    (
                        label,
                        value,
                    )
                )

        elif isinstance(fact, str):
            if fact.strip():
                normalized.append(
                    (
                        "FACT",
                        clean_text(fact),
                    )
                )

    y = 420

    for index, (label, value) in enumerate(
        normalized[:6],
        start=1,
    ):
        panel_height = 185

        rounded_panel(
            draw,
            (
                50,
                y,
                WIDTH - 50,
                y + panel_height,
            ),
        )

        number = f"{index:02d}"

        draw.text(
            (80, y + 30),
            number,
            font=get_font(
                34,
                bold=True,
            ),
            fill=RED,
        )

        label_text = clean_text(
            label
        ).replace("_", " ").upper()

        draw.text(
            (155, y + 34),
            label_text,
            font=get_font(
                22,
                bold=True,
            ),
            fill=YELLOW,
        )

        draw_wrapped_text(
            draw,
            value,
            155,
            y + 82,
            WIDTH - 235,
            get_font(
                28,
                bold=True,
            ),
            WHITE,
            line_gap=8,
        )

        y += panel_height + 25

        if y > HEIGHT - 240:
            break

    return image


# ============================================================
# LOCATION SCENE
# ============================================================


def create_location_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "REGIONAL FOCUS",
        story.get("county", ""),
    )

    county = clean_text(
        story.get("county", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    draw.text(
        (60, 280),
        "WHERE IT IS HAPPENING",
        font=get_font(
            43,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        355,
        130,
        9,
    )

    rounded_panel(
        draw,
        (
            55,
            430,
            WIDTH - 55,
            790,
        ),
        fill=(13, 28, 45),
        outline=BLUE,
    )

    draw.text(
        (95, 500),
        county.upper(),
        font=get_font(
            67,
            bold=True,
        ),
        fill=YELLOW,
    )

    location = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            ).upper()

            if label == "LOCATION":
                location = clean_text(
                    fact.get("value", "")
                )

    if location:
        draw_wrapped_text(
            draw,
            location,
            95,
            625,
            WIDTH - 190,
            get_font(
                34,
                bold=True,
            ),
            WHITE,
            line_gap=10,
        )

    # Regional visual strip
    y = 900

    draw.text(
        (60, y),
        "RIFT VALLEY",
        font=get_font(
            34,
            bold=True,
        ),
        fill=WHITE,
    )

    y += 85

    # Stylized regional corridor graphic.
    points = [
        (100, y + 80),
        (270, y + 20),
        (450, y + 110),
        (650, y + 40),
        (860, y + 130),
        (980, y + 60),
    ]

    for i in range(len(points) - 1):
        draw.line(
            (
                points[i][0],
                points[i][1],
                points[i + 1][0],
                points[i + 1][1],
            ),
            fill=RED,
            width=12,
        )

    for point in points:
        x, py = point

        draw.ellipse(
            (
                x - 16,
                py - 16,
                x + 16,
                py + 16,
            ),
            fill=YELLOW,
        )

    draw_wrapped_text(
        draw,
        summary,
        60,
        1330,
        WIDTH - 120,
        get_font(
            29,
            bold=False,
        ),
        LIGHT,
        line_gap=12,
    )

    return image


# ============================================================
# DATA CARD
# ============================================================


def create_data_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "PROJECT DATA",
        story.get("county", ""),
    )

    facts = {}

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            ).upper()

            value = clean_text(
                fact.get("value", "")
            )

            facts[label] = value

    draw.text(
        (60, 285),
        "THE NUMBERS",
        font=get_font(
            50,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        360,
        120,
        9,
    )

    cards = []

    if facts.get("ROAD_LENGTH"):
        cards.append(
            (
                "ROAD LENGTH",
                facts["ROAD_LENGTH"],
            )
        )

    if facts.get("COST"):
        cards.append(
            (
                "PROJECT COST",
                facts["COST"],
            )
        )

    if facts.get("STATUS"):
        cards.append(
            (
                "STATUS",
                facts["STATUS"],
            )
        )

    if facts.get("LOCATION"):
        cards.append(
            (
                "LOCATION",
                facts["LOCATION"],
            )
        )

    y = 450

    for label, value in cards[:4]:
        rounded_panel(
            draw,
            (
                55,
                y,
                WIDTH - 55,
                y + 260,
            ),
            fill=(15, 23, 32),
            outline=(55, 70, 88),
        )

        draw.text(
            (95, y + 45),
            label,
            font=get_font(
                24,
                bold=True,
            ),
            fill=YELLOW,
        )

        draw_wrapped_text(
            draw,
            value,
            95,
            y + 100,
            WIDTH - 190,
            get_font(
                52,
                bold=True,
            ),
            WHITE,
            line_gap=12,
        )

        y += 300

    return image


# ============================================================
# ROUTE SCENE
# ============================================================


def create_route_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "ROUTE CORRIDOR",
        story.get("county", ""),
    )

    route = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            ).upper()

            if label == "PROJECT":
                route = clean_text(
                    fact.get("value", "")
                )

    draw.text(
        (60, 285),
        "PROJECT CORRIDOR",
        font=get_font(
            48,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        360,
        135,
        9,
    )

    # Split route around slash.
    segments = [
        x.strip()
        for x in route.split("/")
        if x.strip()
    ]

    if not segments:
        segments = [route]

    y = 470

    for segment_index, segment in enumerate(
        segments[:2]
    ):
        rounded_panel(
            draw,
            (
                55,
                y,
                WIDTH - 55,
                y + 430,
            ),
            fill=(12, 20, 29),
            outline=(55, 68, 84),
        )

        label = (
            f"CORRIDOR {segment_index + 1}"
        )

        draw.text(
            (95, y + 45),
            label,
            font=get_font(
                24,
                bold=True,
            ),
            fill=YELLOW,
        )

        # Extract locations.
        stops = [
            x.strip()
            for x in re.split(
                r"[-–—>/]+",
                segment,
            )
            if x.strip()
        ]

        if len(stops) > 1:
            line_y = y + 200

            start_x = 110
            end_x = WIDTH - 110

            draw.line(
                (
                    start_x,
                    line_y,
                    end_x,
                    line_y,
                ),
                fill=RED,
                width=10,
            )

            usable_width = (
                end_x - start_x
            )

            for i, stop in enumerate(
                stops[:7]
            ):
                if len(stops) == 1:
                    x = start_x
                else:
                    x = int(
                        start_x
                        + (
                            usable_width
                            * i
                            / (len(stops) - 1)
                        )
                    )

                draw.ellipse(
                    (
                        x - 18,
                        line_y - 18,
                        x + 18,
                        line_y + 18,
                    ),
                    fill=YELLOW,
                )

                stop_text = clean_text(
                    stop
                )

                # Remove redundant "road".
                stop_text = re.sub(
                    r"\s+road$",
                    "",
                    stop_text,
                    flags=re.IGNORECASE,
                )

                stop_lines = wrap_text(
                    draw,
                    stop_text,
                    get_font(
                        21,
                        bold=True,
                    ),
                    150,
                )

                draw.text(
                    (
                        x - 70,
                        line_y + 45,
                    ),
                    "\n".join(
                        stop_lines[:2]
                    ),
                    font=get_font(
                        21,
                        bold=True,
                    ),
                    fill=WHITE,
                )

        else:
            draw_wrapped_text(
                draw,
                segment,
                95,
                y + 150,
                WIDTH - 190,
                get_font(
                    31,
                    bold=True,
                ),
                WHITE,
                line_gap=10,
            )

        y += 470

    return image


# ============================================================
# IMPACT SCENE
# ============================================================


def create_impact_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "WHY IT MATTERS",
        story.get("county", ""),
    )

    draw.text(
        (60, 285),
        "EXPECTED IMPACT",
        font=get_font(
            48,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        360,
        135,
        9,
    )

    impact = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            ).upper()

            if label == "IMPACT":
                impact = clean_text(
                    fact.get("value", "")
                )

    if not impact:
        impact = clean_text(
            story.get("summary", "")
        )

    rounded_panel(
        draw,
        (
            55,
            470,
            WIDTH - 55,
            1170,
        ),
        fill=(13, 25, 29),
        outline=GREEN,
    )

    draw.ellipse(
        (
            95,
            530,
            175,
            610,
        ),
        fill=GREEN,
    )

    draw.text(
        (205, 525),
        "REGIONAL SIGNIFICANCE",
        font=get_font(
            25,
            bold=True,
        ),
        fill=YELLOW,
    )

    draw_wrapped_text(
        draw,
        impact,
        95,
        690,
        WIDTH - 190,
        get_font(
            43,
            bold=True,
        ),
        WHITE,
        line_gap=18,
    )

    # Supporting factual status
    status = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            if (
                clean_text(
                    fact.get("label", "")
                ).upper()
                == "STATUS"
            ):
                status = clean_text(
                    fact.get("value", "")
                )

    if status:
        draw.text(
            (95, 1280),
            "CURRENT STATUS",
            font=get_font(
                24,
                bold=True,
            ),
            fill=YELLOW,
        )

        draw_wrapped_text(
            draw,
            status,
            95,
            1340,
            WIDTH - 190,
            get_font(
                31,
                bold=True,
            ),
            LIGHT,
            line_gap=10,
        )

    return image


# ============================================================
# OFFICIAL STATEMENT
# ============================================================


def create_statement_scene(story):
    image = create_news_background()

    draw = ImageDraw.Draw(image)

    add_header(
        image,
        "OFFICIAL STATEMENT",
        story.get("county", ""),
    )

    statement = story.get(
        "official_statement",
        {},
    )

    speaker = clean_text(
        statement.get(
            "speaker",
            "",
        )
    )

    quote = clean_text(
        statement.get(
            "quote",
            "",
        )
    )

    draw.text(
        (60, 285),
        "WHAT WAS SAID",
        font=get_font(
            48,
            bold=True,
        ),
        fill=WHITE,
    )

    accent_bar(
        draw,
        60,
        360,
        125,
        9,
    )

    if speaker:
        rounded_panel(
            draw,
            (
                55,
                455,
                WIDTH - 55,
                700,
            ),
            fill=(18, 25, 36),
            outline=(55, 75, 100),
        )

        draw.text(
            (95, 515),
            "SPEAKER",
            font=get_font(
                23,
                bold=True,
            ),
            fill=YELLOW,
        )

        draw_wrapped_text(
            draw,
            speaker,
            95,
            575,
            WIDTH - 190,
            get_font(
                37,
                bold=True,
            ),
            WHITE,
            line_gap=10,
        )

    if quote:
        rounded_panel(
            draw,
            (
                55,
                790,
                WIDTH - 55,
                1370,
            ),
            fill=(12, 17, 24),
            outline=RED,
        )

        draw.text(
            (95, 845),
            "STATEMENT",
            font=get_font(
                23,
                bold=True,
            ),
            fill=YELLOW,
        )

        # Quote mark
        draw.text(
            (80, 915),
            "“",
            font=get_font(
                100,
                bold=True,
            ),
            fill=RED,
        )

        draw_wrapped_text(
            draw,
            quote,
            130,
            955,
            WIDTH - 220,
            get_font(
                36,
                bold=False,
            ),
            WHITE,
            line_gap=18,
        )

    return image


# ============================================================
# OUTRO
# ============================================================


def create_outro():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BLACK,
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=RED,
    )

    draw.text(
        (70, 700),
        "RIFT VALLEY",
        font=get_font(
            76,
            bold=True,
        ),
        fill=WHITE,
    )

    draw.text(
        (70, 795),
        "WATCH",
        font=get_font(
            105,
            bold=True,
        ),
        fill=YELLOW,
    )

    accent_bar(
        draw,
        75,
        930,
        180,
        10,
    )

    draw.text(
        (75, 1000),
        "REGIONAL NEWS.",
        font=get_font(
            36,
            bold=True,
        ),
        fill=LIGHT,
    )

    draw.text(
        (75, 1060),
        "DEVELOPMENTS.",
        font=get_font(
            36,
            bold=True,
        ),
        fill=LIGHT,
    )

    draw.text(
        (75, 1120),
        "THE RIFT VALLEY.",
        font=get_font(
            36,
            bold=True,
        ),
        fill=LIGHT,
    )

    draw.text(
        (75, 1240),
        "FOLLOW FOR THE NEXT UPDATE",
        font=get_font(
            28,
            bold=True,
        ),
        fill=GREY,
    )

    return image


# ============================================================
# SAVE PNG
# ============================================================


def save_image(image, path):
    image.save(
        path,
        "PNG",
        optimize=True,
    )


# ============================================================
# NARRATION
# ============================================================


def narration_intro():
    return (
        "This is Rift Valley Watch. "
        "Here is the latest regional development."
    )


def narration_headline(story):
    county = clean_text(
        story.get("county", "")
    )

    title = clean_text(
        story.get("title", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    parts = [
        f"{county}.",
        title + ".",
    ]

    if summary:
        parts.append(summary)

    return " ".join(parts)


def narration_facts(story):
    parts = [
        "Here are the key facts."
    ]

    for fact in story.get(
        "verified_facts",
        [],
    )[:6]:
        if not isinstance(fact, dict):
            continue

        label = clean_text(
            fact.get("label", "")
        ).replace("_", " ")

        value = clean_text(
            fact.get("value", "")
        )

        if value:
            parts.append(
                f"{label}: {value}."
            )

    return " ".join(parts)


def narration_location(story):
    county = clean_text(
        story.get("county", "")
    )

    location = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            label = clean_text(
                fact.get("label", "")
            ).upper()

            if label == "LOCATION":
                location = clean_text(
                    fact.get("value", "")
                )

    if location:
        return (
            f"The project is located in "
            f"{location}, within {county}."
        )

    return (
        f"The development is located in "
        f"{county}."
    )


def narration_route(story):
    route = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            if (
                clean_text(
                    fact.get("label", "")
                ).upper()
                == "PROJECT"
            ):
                route = clean_text(
                    fact.get("value", "")
                )

    if route:
        return (
            "The project corridor covers "
            f"{route}."
        )

    return (
        "The project covers multiple "
        "locations within the county."
    )


def narration_impact(story):
    impact = ""

    for fact in story.get(
        "verified_facts",
        [],
    ):
        if isinstance(fact, dict):
            if (
                clean_text(
                    fact.get("label", "")
                ).upper()
                == "IMPACT"
            ):
                impact = clean_text(
                    fact.get("value", "")
                )

    if impact:
        return (
            "Why it matters. "
            f"{impact}."
        )

    return (
        "The development remains significant "
        "for the affected area and residents."
    )


def narration_statement(story):
    statement = story.get(
        "official_statement",
        {},
    )

    speaker = clean_text(
        statement.get(
            "speaker",
            "",
        )
    )

    quote = clean_text(
        statement.get(
            "quote",
            "",
        )
    )

    if speaker and quote:
        return (
            f"{speaker} said: "
            f"{quote}"
        )

    if speaker:
        return (
            f"An official statement was issued "
            f"by {speaker}."
        )

    return (
        "An official statement was issued "
        "on the development."
    )


# ============================================================
# TTS
# ============================================================


def create_audio(text, output_path):
    text = clean_text(text)

    if not text:
        raise RuntimeError(
            "Cannot create narration from empty text."
        )

    print(
        f"Generating narration: "
        f"{output_path.name}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(
        str(output_path)
    )


# ============================================================
# AUDIO DURATION
# ============================================================


def get_duration(path):
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        return 0.0

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        return 0.0


# ============================================================
# CREATE SCENE VIDEO
# ============================================================


def create_scene_video(
    image_path,
    audio_path,
    output_path,
    scene_name,
):
    duration = get_duration(
        audio_path
    )

    if duration <= 0:
        raise RuntimeError(
            f"Could not determine audio duration "
            f"for {scene_name}"
        )

    # Small safety extension prevents
    # narration clipping at scene boundaries.
    duration += 0.12

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-filter_complex",
        (
            "[0:v]"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "zoompan="
            "z='min(zoom+0.00018,1.045)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d={max(1, int(duration * FPS))}:"
            "s=1080x1920:"
            "fps=30,"
            "format=yuv420p"
            "[v]"
        ),

        "-map",
        "[v]",

        "-map",
        "1:a",

        "-t",
        f"{duration:.3f}",

        "-r",
        str(FPS),

        "-c:v",
        VIDEO_CODEC,

        "-preset",
        "medium",

        "-crf",
        "20",

        "-b:v",
        VIDEO_BITRATE,

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        "44100",

        "-ac",
        "2",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run_command(command)

    return duration


# ============================================================
# CONCATENATE SCENES
# ============================================================


def concat_scenes(scene_paths):
    concat_file = OUTPUT_DIR / "concat.txt"

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:
        for path in scene_paths:
            absolute = Path(
                path
            ).resolve()

            escaped = str(
                absolute
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{escaped}'\n"
            )

    command = [
        "ffmpeg",
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

        str(FINAL_VIDEO),
    ]

    run_command(command)


# ============================================================
# NORMALIZE STORY JSON
# ============================================================


def load_stories():
    if not STORY_FILE.exists():
        raise FileNotFoundError(
            f"Missing {STORY_FILE}"
        )

    with open(
        STORY_FILE,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    # New engine format:
    #
    # {
    #   "stories": [...]
    # }
    if isinstance(data, dict):
        stories = data.get(
            "stories"
        )

        if isinstance(stories, list):
            return stories

        # Also accept one-story JSON
        if "title" in data:
            return [data]

    # Direct list
    if isinstance(data, list):
        return data

    raise RuntimeError(
        "Unsupported story.json format."
    )


# ============================================================
# STORY SANITIZATION
# ============================================================


def sanitize_story(story):
    result = dict(story)

    result["title"] = clean_text(
        result.get("title", "")
    )

    result["county"] = clean_text(
        result.get(
            "county",
            "Rift Valley",
        )
    )

    result["category"] = clean_text(
        result.get(
            "category",
            "REGIONAL NEWS",
        )
    )

    result["summary"] = clean_text(
        result.get(
            "summary",
            "",
        )
    )

    if not isinstance(
        result.get(
            "verified_facts"
        ),
        list,
    ):
        result["verified_facts"] = []

    if not isinstance(
        result.get(
            "official_statement"
        ),
        dict,
    ):
        result[
            "official_statement"
        ] = {}

    return result


# ============================================================
# STORY SCENE CREATION
# ============================================================


def create_story_scenes(
    story,
    story_number,
):
    story = sanitize_story(
        story
    )

    prefix = (
        f"story_{story_number:02d}"
    )

    scenes = []

    # --------------------------------------------------------
    # 1. HEADLINE
    # --------------------------------------------------------

    headline_image = (
        SCENES_DIR
        / f"{prefix}_01_headline.png"
    )

    save_image(
        create_headline_scene(
            story
        ),
        headline_image,
    )

    headline_audio = (
        AUDIO_DIR
        / f"{prefix}_01_headline.mp3"
    )

    create_audio(
        narration_headline(
            story
        ),
        headline_audio,
    )

    headline_video = (
        SCENES_DIR
        / f"{prefix}_01_headline.mp4"
    )

    duration = create_scene_video(
        headline_image,
        headline_audio,
        headline_video,
        "headline",
    )

    scenes.append(
        {
            "name": "headline",
            "image": str(
                headline_image
            ),
            "audio": str(
                headline_audio
            ),
            "video": str(
                headline_video
            ),
            "duration": duration,
        }
    )

    # --------------------------------------------------------
    # 2. KEY FACTS
    # --------------------------------------------------------

    facts = story.get(
        "verified_facts",
        [],
    )

    if facts:
        facts_image = (
            SCENES_DIR
            / f"{prefix}_02_key_facts.png"
        )

        save_image(
            create_key_facts_scene(
                story
            ),
            facts_image,
        )

        facts_audio = (
            AUDIO_DIR
            / f"{prefix}_02_key_facts.mp3"
        )

        create_audio(
            narration_facts(
                story
            ),
            facts_audio,
        )

        facts_video = (
            SCENES_DIR
            / f"{prefix}_02_key_facts.mp4"
        )

        duration = create_scene_video(
            facts_image,
            facts_audio,
            facts_video,
            "key facts",
        )

        scenes.append(
            {
                "name": "key_facts",
                "image": str(
                    facts_image
                ),
                "audio": str(
                    facts_audio
                ),
                "video": str(
                    facts_video
                ),
                "duration": duration,
            }
        )

    # --------------------------------------------------------
    # 3. LOCATION
    # --------------------------------------------------------

    location_image = (
        SCENES_DIR
        / f"{prefix}_03_location.png"
    )

    save_image(
        create_location_scene(
            story
        ),
        location_image,
    )

    location_audio = (
        AUDIO_DIR
        / f"{prefix}_03_location.mp3"
    )

    create_audio(
        narration_location(
            story
        ),
        location_audio,
    )

    location_video = (
        SCENES_DIR
        / f"{prefix}_03_location.mp4"
    )

    duration = create_scene_video(
        location_image,
        location_audio,
        location_video,
        "location",
    )

    scenes.append(
        {
            "name": "location",
            "image": str(
                location_image
            ),
            "audio": str(
                location_audio
            ),
            "video": str(
                location_video
            ),
            "duration": duration,
        }
    )

    # --------------------------------------------------------
    # 4. DATA
    # --------------------------------------------------------

    data_image = (
        SCENES_DIR
        / f"{prefix}_04_data.png"
    )

    save_image(
        create_data_scene(
            story
        ),
        data_image,
    )

    data_audio = (
        AUDIO_DIR
        / f"{prefix}_04_data.mp3"
    )

    create_audio(
        narration_facts(
            story
        ),
        data_audio,
    )

    data_video = (
        SCENES_DIR
        / f"{prefix}_04_data.mp4"
    )

    duration = create_scene_video(
        data_image,
        data_audio,
        data_video,
        "data",
    )

    scenes.append(
        {
            "name": "data",
            "image": str(
                data_image
            ),
            "audio": str(
                data_audio
            ),
            "video": str(
                data_video
            ),
            "duration": duration,
        }
    )

    # --------------------------------------------------------
    # 5. ROUTE
    # --------------------------------------------------------

    route_image = (
        SCENES_DIR
        / f"{prefix}_05_route.png"
    )

    save_image(
        create_route_scene(
            story
        ),
        route_image,
    )

    route_audio = (
        AUDIO_DIR
        / f"{prefix}_05_route.mp3"
    )

    create_audio(
        narration_route(
            story
        ),
        route_audio,
    )

    route_video = (
        SCENES_DIR
        / f"{prefix}_05_route.mp4"
    )

    duration = create_scene_video(
        route_image,
        route_audio,
        route_video,
        "route",
    )

    scenes.append(
        {
            "name": "route",
            "image": str(
                route_image
            ),
            "audio": str(
                route_audio
            ),
            "video": str(
                route_video
            ),
            "duration": duration,
        }
    )

    # --------------------------------------------------------
    # 6. IMPACT
    # --------------------------------------------------------

    impact_image = (
        SCENES_DIR
        / f"{prefix}_06_impact.png"
    )

    save_image(
        create_impact_scene(
            story
        ),
        impact_image,
    )

    impact_audio = (
        AUDIO_DIR
        / f"{prefix}_06_impact.mp3"
    )

    create_audio(
        narration_impact(
            story
        ),
        impact_audio,
    )

    impact_video = (
        SCENES_DIR
        / f"{prefix}_06_impact.mp4"
    )

    duration = create_scene_video(
        impact_image,
        impact_audio,
        impact_video,
        "impact",
    )

    scenes.append(
        {
            "name": "impact",
            "image": str(
                impact_image
            ),
            "audio": str(
                impact_audio
            ),
            "video": str(
                impact_video
            ),
            "duration": duration,
        }
    )

    # --------------------------------------------------------
    # 7. OFFICIAL STATEMENT
    # --------------------------------------------------------

    statement = story.get(
        "official_statement",
        {},
    )

    if statement.get(
        "available",
        True,
    ) and (
        statement.get(
            "speaker"
        )
        or statement.get(
            "quote"
        )
    ):
        statement_image = (
            SCENES_DIR
            / f"{prefix}_07_statement.png"
        )

        save_image(
            create_statement_scene(
                story
            ),
            statement_image,
        )

        statement_audio = (
            AUDIO_DIR
            / f"{prefix}_07_statement.mp3"
        )

        create_audio(
            narration_statement(
                story
            ),
            statement_audio,
        )

        statement_video = (
            SCENES_DIR
            / f"{prefix}_07_statement.mp4"
        )

        duration = create_scene_video(
            statement_image,
            statement_audio,
            statement_video,
            "official statement",
        )

        scenes.append(
            {
                "name": "official_statement",
                "image": str(
                    statement_image
                ),
                "audio": str(
                    statement_audio
                ),
                "video": str(
                    statement_video
                ),
                "duration": duration,
            }
        )

    return scenes


# ============================================================
# FINAL VALIDATION
# ============================================================


def validate_final_video():
    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "FINAL MP4 WAS NOT CREATED."
        )

    size = FINAL_VIDEO.stat().st_size

    print()
    print("=" * 70)
    print("FINAL VIDEO VALIDATION")
    print("=" * 70)

    print(
        "File:",
        FINAL_VIDEO,
    )

    print(
        "Size:",
        size,
        "bytes",
    )

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not inspect final MP4."
        )

    print(
        result.stdout
    )

    data = json.loads(
        result.stdout
    )

    streams = data.get(
        "streams",
        [],
    )

    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get(
            "codec_type"
        ) == "video":
            video_stream = stream

        if stream.get(
            "codec_type"
        ) == "audio":
            audio_stream = stream

    if not video_stream:
        raise RuntimeError(
            "FINAL VIDEO HAS NO VIDEO STREAM."
        )

    if not audio_stream:
        raise RuntimeError(
            "FINAL VIDEO HAS NO AUDIO STREAM."
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
            f"Expected width {WIDTH}, got {width}"
        )

    if height != HEIGHT:
        raise RuntimeError(
            f"Expected height {HEIGHT}, got {height}"
        )

    duration = float(
        data.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
    )

    if duration < 5:
        raise RuntimeError(
            "Final video is too short."
        )

    print(
        "Resolution:",
        f"{width}x{height}",
    )

    print(
        "Duration:",
        f"{duration:.2f}s",
    )

    print(
        "Video:",
        video_stream.get(
            "codec_name"
        ),
    )

    print(
        "Audio:",
        audio_stream.get(
            "codec_name"
        ),
    )

    print(
        "FINAL MP4 VALIDATION PASSED."
    )

    return {
        "width": width,
        "height": height,
        "duration": duration,
        "size": size,
        "video_codec": video_stream.get(
            "codec_name"
        ),
        "audio_codec": audio_stream.get(
            "codec_name"
        ),
    }


# ============================================================
# VISUAL REPORT
# ============================================================


def write_visual_report(
    stories,
    all_scenes,
    validation,
):
    report = {
        "version": "RIFT VALLEY WATCH V7 VIDEO",
        "generated_at": datetime.utcnow().isoformat()
        + "Z",
        "video": {
            "path": str(
                FINAL_VIDEO
            ),
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "duration": validation[
                "duration"
            ],
            "size": validation[
                "size"
            ],
        },
        "source_card": False,
        "stories": [],
    }

    for index, story in enumerate(
        stories,
        start=1,
    ):
        story_scenes = []

        for scene in all_scenes:
            if scene.get(
                "story_number"
            ) == index:
                story_scenes.append(
                    {
                        "name": scene[
                            "name"
                        ],
                        "duration": scene[
                            "duration"
                        ],
                    }
                )

        report["stories"].append(
            {
                "number": index,
                "title": story.get(
                    "title",
                    "",
                ),
                "county": story.get(
                    "county",
                    "",
                ),
                "category": story.get(
                    "category",
                    "",
                ),
                "photo": bool(
                    find_story_photo(
                        story
                    )
                ),
                "scenes": story_scenes,
            }
        )

    with open(
        VISUAL_REPORT,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# MAIN
# ============================================================


def main():
    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH V7 VIDEO GENERATOR")
    print("=" * 70)
    print()
    print(
        "Professional regional-news video engine"
    )
    print(
        "1080x1920 / 30 FPS"
    )
    print(
        "SOURCE CARD: DISABLED"
    )
    print(
        "RAW SOURCE DATA DISPLAY: DISABLED"
    )
    print()

    if not ffmpeg_exists():
        raise RuntimeError(
            "FFmpeg is not installed."
        )

    if not ffprobe_exists():
        raise RuntimeError(
            "FFprobe is not installed."
        )

    ensure_directories()

    stories = load_stories()

    if not stories:
        raise RuntimeError(
            "No stories found."
        )

    print(
        "Stories loaded:",
        len(stories),
    )

    # Limit to 4 bulletin stories.
    stories = stories[:4]

    # Remove old generated scenes/audio.
    for directory in [
        AUDIO_DIR,
        SCENES_DIR,
    ]:
        for file in directory.iterdir():
            if file.is_file():
                try:
                    file.unlink()
                except Exception:
                    pass

    scene_paths = []
    all_scene_data = []

    # --------------------------------------------------------
    # INTRO
    # --------------------------------------------------------

    intro_image = (
        SCENES_DIR
        / "00_intro.png"
    )

    save_image(
        create_intro(),
        intro_image,
    )

    intro_audio = (
        AUDIO_DIR
        / "00_intro.mp3"
    )

    create_audio(
        narration_intro(),
        intro_audio,
    )

    intro_video = (
        SCENES_DIR
        / "00_intro.mp4"
    )

    intro_duration = create_scene_video(
        intro_image,
        intro_audio,
        intro_video,
        "intro",
    )

    scene_paths.append(
        intro_video
    )

    all_scene_data.append(
        {
            "story_number": 0,
            "name": "intro",
            "duration": intro_duration,
        }
    )

    # --------------------------------------------------------
    # STORIES
    # --------------------------------------------------------

    for index, story in enumerate(
        stories,
        start=1,
    ):
        print()
        print("=" * 70)
        print(
            f"BUILDING STORY {index:02d}"
        )
        print("=" * 70)

        print(
            "Headline:",
            story.get(
                "title",
                "",
            ),
        )

        print(
            "County:",
            story.get(
                "county",
                "",
            ),
        )

        photo = find_story_photo(
            story
        )

        print(
            "Real photo:",
            "YES" if photo else "NO",
        )

        scenes = create_story_scenes(
            story,
            index,
        )

        for scene in scenes:
            scene_paths.append(
                Path(
                    scene["video"]
                )
            )

            all_scene_data.append(
                {
                    "story_number": index,
                    "name": scene[
                        "name"
                    ],
                    "duration": scene[
                        "duration"
                    ],
                }
            )

        print(
            f"STORY {index:02d} COMPLETE"
        )

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    outro_image = (
        SCENES_DIR
        / "99_outro.png"
    )

    save_image(
        create_outro(),
        outro_image,
    )

    outro_audio = (
        AUDIO_DIR
        / "99_outro.mp3"
    )

    create_audio(
        "This is Rift Valley Watch. "
        "Follow for the next regional update.",
        outro_audio,
    )

    outro_video = (
        SCENES_DIR
        / "99_outro.mp4"
    )

    outro_duration = create_scene_video(
        outro_image,
        outro_audio,
        outro_video,
        "outro",
    )

    scene_paths.append(
        outro_video
    )

    all_scene_data.append(
        {
            "story_number": 99,
            "name": "outro",
            "duration": outro_duration,
        }
    )

    # --------------------------------------------------------
    # ASSEMBLY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("ASSEMBLING FINAL MP4")
    print("=" * 70)

    print(
        "Total scenes:",
        len(scene_paths),
    )

    concat_scenes(
        scene_paths
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    validation = (
        validate_final_video()
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    write_visual_report(
        stories,
        all_scene_data,
        validation,
    )

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH V7 COMPLETE")
    print("=" * 70)

    print()
    print(
        "FINAL MP4:",
        FINAL_VIDEO,
    )

    print(
        "VISUAL REPORT:",
        VISUAL_REPORT,
    )

    print()
    print(
        "Stories:",
        len(stories),
    )

    print(
        "Scenes:",
        len(scene_paths),
    )

    print(
        "Duration:",
        f"{validation['duration']:.2f}s",
    )

    print(
        "Resolution:",
        f"{WIDTH}x{HEIGHT}",
    )

    print(
        "Source card:",
        "DISABLED",
    )

    print()
    print(
        "VIDEO GENERATION SUCCESSFUL."
    )


if __name__ == "__main__":
    main()
