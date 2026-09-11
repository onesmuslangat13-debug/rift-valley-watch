import os
import re
import json
import math
import html
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — V4 EDITORIAL VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

SOURCE_DIR = ROOT / "assets" / "source"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"
TEMP_VIDEO = OUTPUT_DIR / "rift_valley_watch_temp.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

BG = (8, 12, 20)
BG2 = (15, 21, 32)
WHITE = (245, 247, 250)
MUTED = (174, 184, 198)
RED = (215, 45, 45)
BLUE = (35, 100, 190)
GOLD = (220, 170, 55)
GREEN = (55, 160, 100)
CARD = (19, 27, 40)
CARD2 = (25, 34, 49)

FONT_DIRS = [
    ROOT / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
]

REGULAR_FONT = None
BOLD_FONT = None


# ============================================================
# BASIC HELPERS
# ============================================================

def log(message):
    print(message, flush=True)


def ensure_dirs():
    for directory in [
        OUTPUT_DIR,
        SCENES_DIR,
        AUDIO_DIR,
        SOURCE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def run_command(command, label="COMMAND"):
    log("")
    log("=" * 70)
    log(label)
    log("=" * 70)
    log(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {result.returncode}"
        )

    return result


def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        for key in ["text", "description", "summary", "title", "name"]:
            if key in value and value[key]:
                return clean_text(value[key])
        return ""

    if isinstance(value, list):
        parts = []
        for item in value:
            text = clean_text(item)
            if text:
                parts.append(text)
        return " ".join(parts)

    text = str(value)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def source_name(story):
    """
    NEVER display a Python dictionary representation.

    Handles:
      "Bomet County Government"
      {"name": "Bomet County Government", "url": "..."}
      {"source": "..."}
      [{"name": "..."}]
    """

    source = story.get("source", "")

    if isinstance(source, dict):
        for key in [
            "name",
            "title",
            "publisher",
            "organization",
            "source",
        ]:
            value = source.get(key)
            if value:
                return clean_text(value)

        return "Official/source reporting"

    if isinstance(source, list):
        for item in source:
            value = clean_text(item)
            if value:
                return value
        return "Official/source reporting"

    text = clean_text(source)

    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text.replace("'", '"'))
            if isinstance(parsed, dict):
                for key in ["name", "title", "publisher", "source"]:
                    if parsed.get(key):
                        return clean_text(parsed[key])
        except Exception:
            pass

    return text or "Official/source reporting"


def story_url(story):
    source = story.get("source")

    if isinstance(source, dict):
        return clean_text(
            source.get("url")
            or story.get("url")
            or ""
        )

    return clean_text(story.get("url") or "")


def county_name(story):
    value = story.get("county") or story.get("location") or ""

    if isinstance(value, dict):
        value = value.get("name") or value.get("county") or ""

    text = clean_text(value)

    if text:
        return text

    return "Rift Valley"


def category_name(story):
    value = story.get("category") or story.get("topic") or "Regional News"
    return clean_text(value).title()


def story_title(story):
    return clean_text(
        story.get("title")
        or story.get("headline")
        or "Rift Valley News Update"
    )


def story_description(story):
    return clean_text(
        story.get("description")
        or story.get("summary")
        or story.get("narration")
        or ""
    )


def published_text(story):
    value = clean_text(
        story.get("published")
        or story.get("date")
        or story.get("published_at")
        or ""
    )

    if not value:
        return "Latest report"

    return value


# ============================================================
# FONT SYSTEM
# ============================================================

def locate_font(names):
    for directory in FONT_DIRS:
        if not directory.exists():
            continue

        for name in names:
            candidate = directory / name
            if candidate.exists():
                return str(candidate)

    return None


def setup_fonts():
    global REGULAR_FONT
    global BOLD_FONT

    REGULAR_FONT = locate_font([
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
    ])

    BOLD_FONT = locate_font([
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
    ])

    if REGULAR_FONT is None or BOLD_FONT is None:
        raise RuntimeError("Could not locate system fonts.")


def font(size, bold=False):
    path = BOLD_FONT if bold else REGULAR_FONT
    return ImageFont.truetype(path, size)


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font_obj, max_width):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word
        bbox = draw.textbbox((0, 0), test, font=font_obj)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def draw_wrapped(
    draw,
    text,
    xy,
    font_obj,
    fill,
    max_width,
    line_gap=12,
    max_lines=None,
):
    x, y = xy

    lines = wrap_text(
        draw,
        text,
        font_obj,
        max_width,
    )

    if max_lines:
        if len(lines) > max_lines:
            lines = lines[:max_lines]

            last = lines[-1]
            if not last.endswith("…"):
                lines[-1] = last.rstrip(" .,;:") + "…"

    bbox = draw.textbbox(
        (x, y),
        "Ag",
        font=font_obj,
    )

    line_height = bbox[3] - bbox[1]

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font_obj,
            fill=fill,
        )
        y += line_height + line_gap

    return y


# ============================================================
# GENERAL GRAPHICS
# ============================================================

def rounded_rectangle(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def draw_header(draw, county, category, story_number=None):
    draw.rectangle(
        (0, 0, WIDTH, 145),
        fill=(6, 10, 17),
    )

    draw.rectangle(
        (0, 140, WIDTH, 145),
        fill=RED,
    )

    draw.text(
        (55, 28),
        "RIFT VALLEY WATCH",
        font=font(42, True),
        fill=WHITE,
    )

    right = f"{county.upper()}  •  {category.upper()}"

    if story_number is not None:
        right = f"STORY {story_number:02d}  •  {right}"

    bbox = draw.textbbox(
        (0, 0),
        right,
        font=font(22, True),
    )

    draw.text(
        (
            WIDTH - 55 - (bbox[2] - bbox[0]),
            88,
        ),
        right,
        font=font(22, True),
        fill=MUTED,
    )


def draw_footer(draw):
    y = HEIGHT - 105

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(6, 10, 17),
    )

    draw.rectangle(
        (0, y, WIDTH, y + 4),
        fill=RED,
    )

    draw.text(
        (55, y + 35),
        "RIFT VALLEY WATCH",
        font=font(24, True),
        fill=WHITE,
    )

    draw.text(
        (WIDTH - 320, y + 35),
        "REGIONAL NEWS",
        font=font(22, True),
        fill=MUTED,
    )


def save_image(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(
        path,
        quality=94,
        optimize=True,
    )


# ============================================================
# PHOTO HANDLING
# ============================================================

def find_story_photo(story):
    candidates = []

    for key in [
        "image_path",
        "photo",
        "image",
        "image_url",
        "photo_url",
    ]:
        value = story.get(key)

        if value:
            if isinstance(value, dict):
                value = (
                    value.get("path")
                    or value.get("url")
                    or value.get("src")
                )

            if value:
                candidates.append(str(value))

    for candidate in candidates:
        path = Path(candidate)

        if not path.is_absolute():
            path = ROOT / candidate

        if path.exists() and path.is_file():
            return path

    return None


def crop_photo(photo_path, target_size=(WIDTH, 1050)):
    target_w, target_h = target_size

    try:
        image = Image.open(photo_path).convert("RGB")
    except Exception:
        return None

    image.thumbnail(
        (target_w * 2, target_h * 2),
        Image.Resampling.LANCZOS,
    )

    source_ratio = image.width / image.height
    target_ratio = target_w / target_h

    if source_ratio > target_ratio:
        new_height = image.height
        new_width = int(new_height * target_ratio)
    else:
        new_width = image.width
        new_height = int(new_width / target_ratio)

    left = max(0, (image.width - new_width) // 2)
    top = max(0, (image.height - new_height) // 2)

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height,
        )
    )

    image = image.resize(
        (target_w, target_h),
        Image.Resampling.LANCZOS,
    )

    return image


def add_photo_overlay(image):
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    height = image.height

    for i in range(height):
        alpha = int(
            170 * (i / max(1, height - 1))
        )

        draw.line(
            (0, i, image.width, i),
            fill=(0, 0, 0, alpha),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


# ============================================================
# SCENE 1 — HEADLINE / REAL PHOTO
# ============================================================

def create_headline_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    photo_path = find_story_photo(story)

    if photo_path:
        photo = crop_photo(
            photo_path,
            (WIDTH, 1050),
        )

        if photo:
            photo = add_photo_overlay(photo)

            image.paste(
                photo,
                (0, 145),
            )

    else:
        draw.rectangle(
            (0, 145, WIDTH, 1195),
            fill=BG2,
        )

        draw.text(
            (55, 550),
            "REAL-TIME\nREGIONAL NEWS",
            font=font(70, True),
            fill=MUTED,
        )

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    # Breaking-news label
    rounded_rectangle(
        draw,
        (55, 190, 390, 250),
        12,
        RED,
    )

    draw.text(
        (78, 205),
        "LATEST REPORT",
        font=font(25, True),
        fill=WHITE,
    )

    # Headline area
    title = story_title(story)

    y = 1200

    y = draw_wrapped(
        draw,
        title,
        (55, y),
        font(62, True),
        WHITE,
        WIDTH - 110,
        line_gap=14,
        max_lines=4,
    )

    y += 35

    draw.rectangle(
        (55, y, 175, y + 6),
        fill=RED,
    )

    y += 30

    draw.text(
        (55, y),
        f"{county_name(story)}  •  {category_name(story)}",
        font=font(27, True),
        fill=MUTED,
    )

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# SCENE 2 — KEY FACTS
# ============================================================

def create_key_facts_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    draw.text(
        (55, 225),
        "KEY FACTS",
        font=font(64, True),
        fill=WHITE,
    )

    draw.rectangle(
        (55, 305, 200, 311),
        fill=RED,
    )

    description = story_description(story)

    title = story_title(story)

    facts = [
        title,
        description,
        f"Location: {county_name(story)}",
        f"Category: {category_name(story)}",
        f"Reported: {published_text(story)}",
    ]

    y = 380

    for index, fact in enumerate(facts):
        rounded_rectangle(
            draw,
            (
                55,
                y,
                WIDTH - 55,
                y + 235,
            ),
            20,
            CARD,
        )

        draw.ellipse(
            (85, y + 45, 130, y + 90),
            fill=RED,
        )

        draw.text(
            (101, y + 50),
            str(index + 1),
            font=font(22, True),
            fill=WHITE,
        )

        draw_wrapped(
            draw,
            fact,
            (160, y + 38),
            font(31, True if index == 0 else False),
            WHITE if index == 0 else MUTED,
            WIDTH - 250,
            line_gap=9,
            max_lines=5,
        )

        y += 260

        if y > HEIGHT - 300:
            break

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# SCENE 3 — ROUTE / REGIONAL CORRIDOR
# ============================================================

def is_infrastructure_story(story):
    text = (
        story_title(story)
        + " "
        + story_description(story)
        + " "
        + category_name(story)
    ).lower()

    keywords = [
        "road",
        "highway",
        "corridor",
        "bridge",
        "construction",
        "infrastructure",
        "expressway",
        "bypass",
        "airport",
        "rail",
        "water project",
        "pipeline",
    ]

    return any(word in text for word in keywords)


def extract_route_points(story):
    text = (
        story_title(story)
        + " "
        + story_description(story)
    )

    county = county_name(story)

    possible = [
        "Bomet",
        "Kericho",
        "Nakuru",
        "Narok",
        "Nandi",
        "Eldoret",
        "Uasin Gishu",
        "Kapsabet",
        "Kisii",
        "Longisa",
        "Sigor",
        "Kipreres",
        "Sotik",
        "Litein",
        "Kisumu",
        "Mau Summit",
        "Naivasha",
        "Turkana",
        "Kitale",
        "Kapenguria",
        "Maralal",
        "Kajiado",
        "Kilgoris",
        "Lodwar",
    ]

    found = []

    lowered = text.lower()

    for place in possible:
        if place.lower() in lowered and place not in found:
            found.append(place)

    if county not in found:
        found.insert(0, county)

    return found[:6]


def create_route_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    if is_infrastructure_story(story):
        heading = "ROUTE CORRIDOR"
        subtitle = "Regional infrastructure focus"
    else:
        heading = "REGIONAL FOCUS"
        subtitle = "Where the story is unfolding"

    draw.text(
        (55, 225),
        heading,
        font=font(60, True),
        fill=WHITE,
    )

    draw.text(
        (55, 305),
        subtitle,
        font=font(28),
        fill=MUTED,
    )

    points = extract_route_points(story)

    if not points:
        points = [county_name(story)]

    center_y = 760

    line_x = 140

    if len(points) == 1:
        ys = [center_y]
    else:
        top = 500
        bottom = 1050
        spacing = (bottom - top) / (len(points) - 1)
        ys = [
            int(top + i * spacing)
            for i in range(len(points))
        ]

    if len(ys) > 1:
        draw.line(
            (
                line_x,
                ys[0],
                line_x,
                ys[-1],
            ),
            fill=BLUE,
            width=16,
        )

    for i, (point, y) in enumerate(zip(points, ys)):
        draw.ellipse(
            (
                line_x - 25,
                y - 25,
                line_x + 25,
                y + 25,
            ),
            fill=RED if i == 0 else BLUE,
        )

        draw.text(
            (215, y - 30),
            point,
            font=font(38, True),
            fill=WHITE,
        )

        if i == 0:
            label = "CURRENT FOCUS"
        elif i == len(points) - 1:
            label = "REGIONAL LINK"
        else:
            label = "CORRIDOR"

        draw.text(
            (215, y + 25),
            label,
            font=font(21, True),
            fill=MUTED,
        )

    description = story_description(story)

    rounded_rectangle(
        draw,
        (55, 1200, WIDTH - 55, 1570),
        25,
        CARD,
    )

    draw.text(
        (90, 1245),
        "WHAT THIS MEANS",
        font=font(30, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        description or "The development is being monitored across the wider Rift Valley region.",
        (90, 1310),
        font(31),
        WHITE,
        WIDTH - 180,
        line_gap=12,
        max_lines=7,
    )

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# SCENE 4 — IMPACT
# ============================================================

def create_impact_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    draw.text(
        (55, 225),
        "IMPACT",
        font=font(68, True),
        fill=WHITE,
    )

    draw.rectangle(
        (55, 315, 180, 321),
        fill=RED,
    )

    title = story_title(story)
    description = story_description(story)

    # Determine likely impact areas
    text = (
        title
        + " "
        + description
    ).lower()

    impacts = []

    if any(x in text for x in ["road", "highway", "bridge", "transport"]):
        impacts.append(
            ("TRANSPORT", "Road connectivity and movement across the affected area.")
        )

    if any(x in text for x in ["farmer", "agriculture", "crop", "livestock", "milk"]):
        impacts.append(
            ("AGRICULTURE", "Potential implications for farmers, markets and supply chains.")
        )

    if any(x in text for x in ["business", "trade", "economy", "investment", "market"]):
        impacts.append(
            ("BUSINESS", "Potential effects on trade, investment and local economic activity.")
        )

    if any(x in text for x in ["hospital", "health", "clinic", "medical"]):
        impacts.append(
            ("HEALTH", "Possible implications for access to health services.")
        )

    if any(x in text for x in ["school", "education", "student", "university"]):
        impacts.append(
            ("EDUCATION", "Potential implications for learners and education services.")
        )

    if any(x in text for x in ["security", "police", "crime", "accident"]):
        impacts.append(
            ("SECURITY", "Potential implications for safety and public security.")
        )

    if not impacts:
        impacts = [
            (
                "REGIONAL",
                "The development is relevant to residents, institutions and economic activity in the region.",
            ),
            (
                "COUNTY",
                f"The immediate focus is {county_name(story)} and the communities affected by the development.",
            ),
            (
                "PUBLIC INTEREST",
                "Residents and stakeholders will be watching for implementation, response and next steps.",
            ),
        ]

    y = 410

    for label, explanation in impacts[:3]:
        rounded_rectangle(
            draw,
            (
                55,
                y,
                WIDTH - 55,
                y + 290,
            ),
            22,
            CARD,
        )

        draw.text(
            (90, y + 45),
            label,
            font=font(31, True),
            fill=RED,
        )

        draw_wrapped(
            draw,
            explanation,
            (90, y + 105),
            font(33),
            WHITE,
            WIDTH - 180,
            line_gap=12,
            max_lines=4,
        )

        y += 330

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# SCENE 5 — OFFICIAL STATEMENT
# ============================================================

def create_statement_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    draw.text(
        (55, 225),
        "OFFICIAL STATEMENT",
        font=font(56, True),
        fill=WHITE,
    )

    draw.rectangle(
        (55, 315, 220, 321),
        fill=RED,
    )

    source = source_name(story)

    description = story_description(story)

    narration = clean_text(story.get("narration", ""))

    statement = ""

    # Only use existing source material.
    # Never invent quotation marks.
    if description:
        statement = description
    elif narration:
        statement = narration

    if not statement:
        statement = (
            "The latest available information is being monitored "
            "as the situation develops."
        )

    rounded_rectangle(
        draw,
        (55, 405, WIDTH - 55, 1330),
        30,
        CARD,
    )

    draw.text(
        (100, 470),
        "REPORT",
        font=font(30, True),
        fill=RED,
    )

    # Quote-style visual without claiming it is a direct quote
    draw.rectangle(
        (100, 555, 110, 1040),
        fill=BLUE,
    )

    draw_wrapped(
        draw,
        statement,
        (155, 555),
        font(38),
        WHITE,
        WIDTH - 255,
        line_gap=18,
        max_lines=10,
    )

    draw.text(
        (100, 1150),
        "SOURCE",
        font=font(25, True),
        fill=MUTED,
    )

    draw_wrapped(
        draw,
        source,
        (100, 1190),
        font(31, True),
        WHITE,
        WIDTH - 200,
        line_gap=10,
        max_lines=2,
    )

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# SCENE 6 — SOURCE
# ============================================================

def create_source_scene(story, story_number, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        county_name(story),
        category_name(story),
        story_number,
    )

    draw.text(
        (55, 240),
        "SOURCE",
        font=font(72, True),
        fill=WHITE,
    )

    draw.rectangle(
        (55, 335, 170, 341),
        fill=RED,
    )

    source = source_name(story)
    url = story_url(story)

    rounded_rectangle(
        draw,
        (55, 460, WIDTH - 55, 1040),
        30,
        CARD,
    )

    draw.text(
        (100, 535),
        "REPORTING SOURCE",
        font=font(29, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        source,
        (100, 625),
        font(52, True),
        WHITE,
        WIDTH - 200,
        line_gap=15,
        max_lines=5,
    )

    draw.text(
        (100, 870),
        "PUBLISHED / UPDATED",
        font=font(25, True),
        fill=MUTED,
    )

    draw_wrapped(
        draw,
        published_text(story),
        (100, 915),
        font(31, True),
        WHITE,
        WIDTH - 200,
        line_gap=10,
        max_lines=2,
    )

    # Show domain only, never the raw URL
    domain = ""

    if url:
        match = re.search(
            r"https?://(?:www\.)?([^/]+)",
            url,
        )

        if match:
            domain = match.group(1)

    if domain:
        rounded_rectangle(
            draw,
            (55, 1110, WIDTH - 55, 1285),
            20,
            CARD2,
        )

        draw.text(
            (95, 1150),
            "ONLINE SOURCE",
            font=font(25, True),
            fill=MUTED,
        )

        draw.text(
            (95, 1195),
            domain,
            font=font(34, True),
            fill=WHITE,
        )

    rounded_rectangle(
        draw,
        (55, 1360, WIDTH - 55, 1580),
        20,
        (27, 43, 60),
    )

    draw.text(
        (95, 1410),
        "RIFT VALLEY WATCH",
        font=font(29, True),
        fill=WHITE,
    )

    draw.text(
        (95, 1460),
        "Independent regional news presentation",
        font=font(25),
        fill=MUTED,
    )

    draw_footer(draw)

    save_image(image, path)


# ============================================================
# OUTRO
# ============================================================

def create_outro_scene(path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=RED,
    )

    draw.text(
        (55, 580),
        "RIFT VALLEY",
        font=font(78, True),
        fill=WHITE,
    )

    draw.text(
        (55, 690),
        "WATCH",
        font=font(110, True),
        fill=RED,
    )

    draw.rectangle(
        (55, 840, 360, 847),
        fill=BLUE,
    )

    draw.text(
        (55, 910),
        "REGIONAL NEWS.",
        font=font(40, True),
        fill=WHITE,
    )

    draw.text(
        (55, 975),
        "REAL DEVELOPMENTS.",
        font=font(40, True),
        fill=WHITE,
    )

    draw.text(
        (55, 1040),
        "RIFT VALLEY VOICES.",
        font=font(40, True),
        fill=WHITE,
    )

    draw.text(
        (55, 1200),
        "FOLLOW FOR THE LATEST",
        font=font(31, True),
        fill=MUTED,
    )

    draw.text(
        (55, 1260),
        "Rift Valley regional bulletin",
        font=font(29),
        fill=MUTED,
    )

    draw.rectangle(
        (0, HEIGHT - 18, WIDTH, HEIGHT),
        fill=RED,
    )

    save_image(image, path)


# ============================================================
# NARRATION
# ============================================================

def shorten(text, max_words):
    words = clean_text(text).split()

    if len(words) <= max_words:
        return " ".join(words)

    return " ".join(words[:max_words]).rstrip(" .,;:") + "."


def headline_narration(story):
    title = story_title(story)
    county = county_name(story)

    return (
        f"Rift Valley Watch. "
        f"Here is the latest regional report from {county}. "
        f"{title}."
    )


def facts_narration(story):
    description = story_description(story)

    if description:
        return (
            "Key facts. "
            + shorten(description, 65)
        )

    return (
        f"The latest report concerns {story_title(story)} "
        f"in {county_name(story)}."
    )


def route_narration(story):
    points = extract_route_points(story)

    if is_infrastructure_story(story):
        if len(points) >= 2:
            return (
                "Route corridor. "
                + "The development links "
                + ", ".join(points[:-1])
                + f", toward {points[-1]}."
            )

        return (
            f"Route corridor. "
            f"The infrastructure focus is in {county_name(story)}."
        )

    return (
        f"Regional focus. "
        f"The story is unfolding in {county_name(story)} "
        f"and is relevant to the wider Rift Valley region."
    )


def impact_narration(story):
    text = (
        story_title(story)
        + " "
        + story_description(story)
    ).lower()

    areas = []

    if any(x in text for x in ["road", "highway", "bridge", "transport"]):
        areas.append("transport")

    if any(x in text for x in ["farmer", "agriculture", "crop", "livestock"]):
        areas.append("agriculture")

    if any(x in text for x in ["business", "trade", "economy", "investment"]):
        areas.append("business")

    if any(x in text for x in ["hospital", "health", "clinic", "medical"]):
        areas.append("health")

    if any(x in text for x in ["school", "education", "student"]):
        areas.append("education")

    if areas:
        return (
            "Impact. "
            "The development could affect "
            + ", ".join(areas[:3])
            + " across the affected communities."
        )

    return (
        "Impact. "
        f"The development is significant for residents and stakeholders "
        f"in {county_name(story)} and the wider region."
    )


def statement_narration(story):
    source = source_name(story)
    description = story_description(story)

    if description:
        return (
            "Official and source information. "
            f"{shorten(description, 60)} "
            f"This report is based on information from {source}."
        )

    return (
        f"The latest available information comes from {source}. "
        "Rift Valley Watch will continue monitoring developments."
    )


def source_narration(story):
    source = source_name(story)

    return (
        f"Source. "
        f"This report is based on reporting from {source}."
    )


def outro_narration():
    return (
        "That is the latest regional bulletin from Rift Valley Watch. "
        "Follow for more developments across the Rift Valley."
    )


def create_audio(text, path):
    text = clean_text(text)

    if not text:
        raise ValueError("Cannot create audio from empty text.")

    if path.exists() and path.stat().st_size > 1000:
        return path

    log(f"Creating narration: {text}")

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    temp = path.with_suffix(".mp3.tmp")

    if temp.exists():
        temp.unlink()

    tts.save(str(temp))

    temp.replace(path)

    return path


def get_audio_duration(path):
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
        return 5.0

    try:
        return max(3.0, float(result.stdout.strip()))
    except Exception:
        return 5.0


# ============================================================
# SCENE RENDERING
# ============================================================

def render_scene(image_path, audio_path, output_path):
    duration = get_audio_duration(audio_path)

    # Add a small tail so speech is not clipped.
    duration += 0.25

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-framerate",
        str(FPS),

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-t",
        f"{duration:.3f}",

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "22",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        "-shortest",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run_command(
        command,
        f"RENDERING {output_path.name}",
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene was not created: {output_path}"
        )

    if output_path.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene is suspiciously small: {output_path}"
        )


# ============================================================
# FINAL ASSEMBLY
# ============================================================

def assemble_final(scene_files):
    if not scene_files:
        raise RuntimeError("No scene files to assemble.")

    log("")
    log("=" * 70)
    log("ASSEMBLING FINAL MP4")
    log("=" * 70)

    command = [
        "ffmpeg",
        "-y",
    ]

    for scene in scene_files:
        command += [
            "-i",
            str(scene),
        ]

    filters = []
    pairs = []

    for index in range(len(scene_files)):
        video_label = f"v{index}"
        audio_label = f"a{index}"

        filters.append(
            f"[{index}:v:0]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,"
            "fps=30,"
            "format=yuv420p"
            f"[{video_label}]"
        )

        filters.append(
            f"[{index}:a:0]"
            "aformat="
            "sample_rates=44100:"
            "channel_layouts=stereo,"
            "aresample=44100"
            f"[{audio_label}]"
        )

        pairs.append(
            f"[{video_label}][{audio_label}]"
        )

    filters.append(
        "".join(pairs)
        + f"concat=n={len(scene_files)}:v=1:a=1"
        "[vout][aout]"
    )

    command += [
        "-filter_complex",
        ";".join(filters),

        "-map",
        "[vout]",

        "-map",
        "[aout]",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "22",

        "-pix_fmt",
        "yuv420p",

        "-r",
        "30",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        "-movflags",
        "+faststart",

        str(TEMP_VIDEO),
    ]

    run_command(
        command,
        "FINAL VIDEO ASSEMBLY",
    )

    if not TEMP_VIDEO.exists():
        raise RuntimeError(
            "Temporary final MP4 was not created."
        )

    if TEMP_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Temporary final MP4 is suspiciously small."
        )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    TEMP_VIDEO.replace(FINAL_VIDEO)

    log("")
    log("=" * 70)
    log("FINAL MP4 CREATED")
    log("=" * 70)
    log(str(FINAL_VIDEO))
    log(f"Size: {FINAL_VIDEO.stat().st_size:,} bytes")


# ============================================================
# VIDEO VALIDATION
# ============================================================

def validate_final_video():
    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,"
        "sample_rate,channels,r_frame_rate",
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
            "Final MP4 failed ffprobe validation."
        )

    data = json.loads(result.stdout)

    log("")
    log("=" * 70)
    log("FINAL MP4 VALIDATION")
    log("=" * 70)

    log(json.dumps(data, indent=2))

    streams = data.get("streams", [])

    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream

        if stream.get("codec_type") == "audio":
            audio_stream = stream

    if not video_stream:
        raise RuntimeError(
            "No video stream found."
        )

    if video_stream.get("width") != WIDTH:
        raise RuntimeError(
            f"Wrong width: {video_stream.get('width')}"
        )

    if video_stream.get("height") != HEIGHT:
        raise RuntimeError(
            f"Wrong height: {video_stream.get('height')}"
        )

    if not audio_stream:
        raise RuntimeError(
            "No audio stream found."
        )

    log("")
    log("VIDEO: 1080x1920")
    log("AUDIO: stereo / 44.1kHz")
    log("VALIDATION: PASSED")


# ============================================================
# LOAD NEWS
# ============================================================

def load_stories():
    if not STORY_FILE.exists():
        raise RuntimeError(
            f"Missing story file: {STORY_FILE}"
        )

    with STORY_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if isinstance(data, list):
        stories = data

    elif isinstance(data, dict):
        stories = (
            data.get("stories")
            or data.get("articles")
            or data.get("items")
            or []
        )

        if not stories and data.get("title"):
            stories = [data]

    else:
        stories = []

    cleaned = []

    for story in stories:
        if isinstance(story, dict):
            cleaned.append(story)

    return cleaned


# ============================================================
# CREATE STORY SCENES
# ============================================================

def create_story_scenes(story, story_number):
    prefix = f"story_{story_number:02d}"

    scene_definitions = [
        (
            "headline",
            create_headline_scene,
            headline_narration,
        ),
        (
            "facts",
            create_key_facts_scene,
            facts_narration,
        ),
        (
            "route",
            create_route_scene,
            route_narration,
        ),
        (
            "impact",
            create_impact_scene,
            impact_narration,
        ),
        (
            "statement",
            create_statement_scene,
            statement_narration,
        ),
        (
            "source",
            create_source_scene,
            source_narration,
        ),
    ]

    scene_files = []

    for index, (
        name,
        image_function,
        narration_function,
    ) in enumerate(scene_definitions):

        image_path = (
            SCENES_DIR
            / f"{prefix}_{index + 1:02d}_{name}.jpg"
        )

        audio_path = (
            AUDIO_DIR
            / f"{prefix}_{index + 1:02d}_{name}.mp3"
        )

        video_path = (
            SCENES_DIR
            / f"{prefix}_{index + 1:02d}_{name}.mp4"
        )

        log("")
        log(
            f"STORY {story_number:02d} "
            f"SCENE {index + 1:02d}: "
            f"{name.upper()}"
        )

        image_function(
            story,
            story_number,
            image_path,
        )

        narration = narration_function(story)

        create_audio(
            narration,
            audio_path,
        )

        render_scene(
            image_path,
            audio_path,
            video_path,
        )

        scene_files.append(video_path)

    return scene_files


# ============================================================
# OUTRO SCENE
# ============================================================

def create_outro_files():
    image_path = SCENES_DIR / "outro.jpg"
    audio_path = AUDIO_DIR / "outro.mp3"
    video_path = SCENES_DIR / "outro.mp4"

    create_outro_scene(image_path)

    create_audio(
        outro_narration(),
        audio_path,
    )

    render_scene(
        image_path,
        audio_path,
        video_path,
    )

    return video_path


# ============================================================
# WRITE VISUAL REPORT
# ============================================================

def write_visual_report(stories, scene_files):
    report = {
        "project": "Rift Valley Watch",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "format": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "orientation": "vertical",
        },
        "architecture": [
            "headline",
            "key_facts",
            "route_corridor",
            "impact",
            "official_statement",
            "source",
            "outro",
        ],
        "stories": [],
        "scene_count": len(scene_files),
        "real_photos_used": 0,
    }

    for index, story in enumerate(stories, start=1):
        photo = find_story_photo(story)

        item = {
            "story_number": index,
            "title": story_title(story),
            "county": county_name(story),
            "category": category_name(story),
            "source": source_name(story),
            "photo": str(photo) if photo else None,
        }

        if photo:
            report["real_photos_used"] += 1

        report["stories"].append(item)

    report_path = ROOT / "data" / "visual_report.json"

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    log(f"Created: {report_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH V4 VIDEO GENERATOR")
    log("=" * 70)
    log("")

    ensure_dirs()
    setup_fonts()

    stories = load_stories()

    if not stories:
        raise RuntimeError(
            "No stories found in data/story.json"
        )

    # Limit bulletin length while preserving regional coverage.
    stories = stories[:4]

    log(
        f"Stories loaded: {len(stories)}"
    )

    for index, story in enumerate(stories, start=1):
        log(
            f"{index}. "
            f"{county_name(story)} — "
            f"{story_title(story)}"
        )

    all_scene_files = []

    # --------------------------------------------------------
    # STORY SCENES
    # --------------------------------------------------------

    for story_number, story in enumerate(
        stories,
        start=1,
    ):
        story_scene_files = create_story_scenes(
            story,
            story_number,
        )

        all_scene_files.extend(
            story_scene_files
        )

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    outro = create_outro_files()
    all_scene_files.append(outro)

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    write_visual_report(
        stories,
        all_scene_files,
    )

    # --------------------------------------------------------
    # ASSEMBLE
    # --------------------------------------------------------

    assemble_final(
        all_scene_files
    )

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    validate_final_video()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATION SUCCESSFUL")
    log("=" * 70)
    log(f"Stories: {len(stories)}")
    log(f"Scenes: {len(all_scene_files)}")
    log(f"Output: {FINAL_VIDEO}")
    log("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("")
        log("=" * 70)
        log("VIDEO GENERATOR FAILED")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)
        raise
