import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME REGIONAL VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

ASSET_DIR = ROOT / "assets"
SOURCE_IMAGE_DIR = ASSET_DIR / "source"
MUSIC_FILE = ASSET_DIR / "music" / "news_bed.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MAX_STORIES = 12

BG = (9, 14, 24)
PANEL = (17, 25, 39)
PANEL_2 = (23, 32, 49)
WHITE = (245, 248, 252)
MUTED = (165, 177, 194)
RED = (220, 45, 55)
BLUE = (48, 110, 220)
GREEN = (44, 175, 112)
GOLD = (226, 176, 61)
BLACK = (0, 0, 0)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", "&")
    value = value.replace("&quot;", '"')
    value = value.replace("&#39;", "'")
    value = value.replace("&apos;", "'")
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def load_json(path, default=None):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"WARNING: Could not read {path}: {exc}")
        return default


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
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def ffprobe_exists():
    return shutil.which("ffprobe") is not None


def prepare_output():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (ASSET_DIR / "music").mkdir(
        parents=True,
        exist_ok=True,
    )

    for folder in [SCENE_DIR, AUDIO_DIR]:
        for item in folder.glob("*"):
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass


# ============================================================
# FONTS
# ============================================================

def font_candidates():
    return [
        ROOT / "fonts" / "Inter-Bold.ttf",
        ROOT / "fonts" / "Inter-Regular.ttf",
        ROOT / "fonts" / "Montserrat-Bold.ttf",
        ROOT / "fonts" / "Montserrat-Regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def get_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend([
            ROOT / "fonts" / "Inter-Bold.ttf",
            ROOT / "fonts" / "Montserrat-Bold.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
        ])
    else:
        candidates.extend([
            ROOT / "fonts" / "Inter-Regular.ttf",
            ROOT / "fonts" / "Montserrat-Regular.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
        ])

    for path in candidates:
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
# TEXT HELPERS
# ============================================================

def text_width(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )
    return box[2] - box[0]


def wrap_text(draw, text, font, max_width):
    text = clean_text(text)

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = (
            word
            if not current
            else current + " " + word
        )

        if text_width(
            draw,
            candidate,
            font,
        ) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    line_gap=12,
):
    x, y = xy

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    bbox = font.getbbox("Ag")
    line_height = (
        bbox[3] - bbox[1] + line_gap
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )
        y += line_height

    return y


def shorten(text, max_chars):
    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    return (
        text[: max_chars - 3]
        .rstrip()
        + "..."
    )


# ============================================================
# IMAGE HELPERS
# ============================================================

def gradient_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    # Subtle vertical gradient.
    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(
            BG[0] +
            (18 - BG[0]) * ratio
        )

        g = int(
            BG[1] +
            (25 - BG[1]) * ratio
        )

        b = int(
            BG[2] +
            (39 - BG[2]) * ratio
        )

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(r, g, b),
        )

    return image


def crop_to_cover(image, width, height):
    image = image.convert("RGB")

    source_ratio = (
        image.width / image.height
    )

    target_ratio = width / height

    if source_ratio > target_ratio:
        new_height = height
        new_width = int(
            height * source_ratio
        )
    else:
        new_width = width
        new_height = int(
            width / source_ratio
        )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - width
    ) // 2

    top = (
        new_height - height
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + width,
            top + height,
        )
    )


def load_source_image(story):
    possible = []

    url = story.get("image_url", "")
    if url:
        possible.append(url)

    story_url = story.get("url", "")
    if story_url:
        possible.append(story_url)

    for candidate in possible:
        if not candidate:
            continue

        if candidate.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            try:
                filename = (
                    SOURCE_IMAGE_DIR
                    / "story_visual.jpg"
                )

                request = urllib.request.Request(
                    candidate,
                    headers={
                        "User-Agent":
                        "Mozilla/5.0"
                    },
                )

                with urllib.request.urlopen(
                    request,
                    timeout=12,
                ) as response:
                    data = response.read()

                filename.write_bytes(data)

                image = Image.open(
                    filename
                ).convert("RGB")

                return image

            except Exception:
                pass

    return None


# ============================================================
# BROADCAST HEADER / FOOTER
# ============================================================

def draw_header(
    draw,
    section="LIVE REGIONAL NEWS",
):
    # Top red breaking strip.
    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=RED,
    )

    logo_font = get_font(
        48,
        bold=True,
    )

    small_font = get_font(
        25,
        bold=True,
    )

    draw.text(
        (60, 55),
        "RIFT VALLEY",
        font=logo_font,
        fill=WHITE,
    )

    draw.text(
        (60, 112),
        "WATCH",
        font=logo_font,
        fill=RED,
    )

    draw.text(
        (60, 180),
        section.upper(),
        font=small_font,
        fill=MUTED,
    )

    # Live indicator.
    draw.ellipse(
        (875, 70, 900, 95),
        fill=RED,
    )

    draw.text(
        (915, 62),
        "LIVE",
        font=small_font,
        fill=WHITE,
    )


def draw_footer(
    draw,
    source="",
):
    draw.rectangle(
        (
            45,
            HEIGHT - 155,
            WIDTH - 45,
            HEIGHT - 50,
        ),
        fill=(12, 19, 30),
    )

    font = get_font(
        23,
        bold=False,
    )

    draw.text(
        (70, HEIGHT - 130),
        "RIFT VALLEY WATCH",
        font=font,
        fill=WHITE,
    )

    if source:
        source_text = shorten(
            f"Source: {source}",
            72,
        )

        draw.text(
            (70, HEIGHT - 92),
            source_text,
            font=font,
            fill=MUTED,
        )


def draw_page_number(
    draw,
    current,
    total,
):
    font = get_font(
        22,
        bold=True,
    )

    text = f"{current:02d} / {total:02d}"

    draw.text(
        (WIDTH - 180, 180),
        text,
        font=font,
        fill=MUTED,
    )


# ============================================================
# SCENE IMAGE CREATION
# ============================================================

def create_opener():
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "LIVE REGIONAL BULLETIN",
    )

    # Central breaking-news block.
    draw.rounded_rectangle(
        (
            55,
            470,
            WIDTH - 55,
            1170,
        ),
        radius=35,
        fill=PANEL,
        outline=(53, 70, 96),
        width=2,
    )

    label_font = get_font(
        30,
        bold=True,
    )

    title_font = get_font(
        75,
        bold=True,
    )

    sub_font = get_font(
        34,
        bold=False,
    )

    draw.text(
        (100, 545),
        "REGIONAL NEWS",
        font=label_font,
        fill=RED,
    )

    draw_wrapped(
        draw,
        "RIFT VALLEY WATCH",
        (100, 625),
        title_font,
        WHITE,
        850,
        12,
    )

    draw_wrapped(
        draw,
        "Fresh developments from across "
        "Kenya's Rift Valley.",
        (100, 830),
        sub_font,
        MUTED,
        820,
        14,
    )

    # News ticker.
    draw.rectangle(
        (
            0,
            1310,
            WIDTH,
            1390,
        ),
        fill=RED,
    )

    ticker_font = get_font(
        30,
        bold=True,
    )

    draw.text(
        (60, 1330),
        "LATEST • VERIFIED SOURCES • REGIONAL COVERAGE",
        font=ticker_font,
        fill=WHITE,
    )

    draw_footer(
        draw,
        "Live news feeds",
    )

    return image


def create_coverage_scene(
    counties,
    date_text,
):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "REGIONAL COVERAGE",
    )

    title_font = get_font(
        55,
        bold=True,
    )

    body_font = get_font(
        31,
        bold=False,
    )

    small_font = get_font(
        25,
        bold=True,
    )

    draw.text(
        (60, 300),
        "TODAY'S COVERAGE",
        font=title_font,
        fill=WHITE,
    )

    draw.text(
        (60, 390),
        date_text,
        font=body_font,
        fill=MUTED,
    )

    # County cards.
    x = 60
    y = 510

    card_w = 455
    card_h = 130

    for index, county in enumerate(
        counties
    ):

        if index >= 12:
            break

        col = index % 2
        row = index // 2

        x = 60 + col * 485
        y = 510 + row * 165

        draw.rounded_rectangle(
            (
                x,
                y,
                x + card_w,
                y + card_h,
            ),
            radius=20,
            fill=PANEL,
            outline=(49, 67, 92),
            width=2,
        )

        draw.ellipse(
            (
                x + 25,
                y + 35,
                x + 60,
                y + 70,
            ),
            fill=RED,
        )

        draw.text(
            (x + 80, y + 27),
            county.upper(),
            font=small_font,
            fill=WHITE,
        )

        draw.text(
            (x + 80, y + 68),
            "FRESH UPDATE",
            font=get_font(
                22,
                bold=False,
            ),
            fill=MUTED,
        )

    draw_footer(
        draw,
        "Rift Valley Watch",
    )

    return image


def create_story_scene(
    story,
    number,
    total,
):
    image = gradient_background()

    # Try real visual first.
    source_image = load_source_image(
        story
    )

    if source_image is not None:
        visual = crop_to_cover(
            source_image,
            WIDTH,
            820,
        )

        # Darken visual for readability.
        overlay = Image.new(
            "RGBA",
            visual.size,
            (0, 0, 0, 95),
        )

        visual = visual.convert(
            "RGBA"
        )

        visual.alpha_composite(
            overlay
        )

        image.paste(
            visual.convert("RGB"),
            (0, 0),
        )

    draw = ImageDraw.Draw(image)

    # Header.
    draw_header(
        draw,
        story.get(
            "category",
            "REGIONAL NEWS",
        ),
    )

    draw_page_number(
        draw,
        number,
        total,
    )

    # Visual label.
    if source_image is not None:
        draw.rounded_rectangle(
            (60, 650, 360, 715),
            radius=16,
            fill=RED,
        )

        draw.text(
            (85, 665),
            "NEWS VISUAL",
            font=get_font(
                24,
                bold=True,
            ),
            fill=WHITE,
        )

    # Story panel.
    panel_top = 760

    draw.rounded_rectangle(
        (
            45,
            panel_top,
            WIDTH - 45,
            HEIGHT - 205,
        ),
        radius=35,
        fill=PANEL,
        outline=(55, 73, 101),
        width=2,
    )

    county = clean_text(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    category = clean_text(
        story.get(
            "category",
            "NEWS",
        )
    )

    title = clean_text(
        story.get(
            "title",
            "Regional Update",
        )
    )

    description = clean_text(
        story.get(
            "description",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source",
            "",
        )
    )

    # County/category line.
    draw.text(
        (90, panel_top + 45),
        county.upper(),
        font=get_font(
            28,
            bold=True,
        ),
        fill=RED,
    )

    draw.text(
        (90, panel_top + 92),
        category.upper(),
        font=get_font(
            23,
            bold=True,
        ),
        fill=MUTED,
    )

    # Main headline.
    headline_font = get_font(
        54,
        bold=True,
    )

    headline_y = (
        panel_top + 160
    )

    headline_bottom = draw_wrapped(
        draw,
        title,
        (90, headline_y),
        headline_font,
        WHITE,
        850,
        13,
    )

    # Description.
    description_y = max(
        headline_bottom + 45,
        panel_top + 420,
    )

    body_font = get_font(
        31,
        bold=False,
    )

    draw_wrapped(
        draw,
        shorten(
            description,
            480,
        ),
        (90, description_y),
        body_font,
        MUTED,
        850,
        14,
    )

    draw_footer(
        draw,
        source,
    )

    return image


def create_empty_scene():
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "LIVE REGIONAL UPDATE",
    )

    title_font = get_font(
        55,
        bold=True,
   
