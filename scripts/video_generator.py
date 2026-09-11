import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH - SIMPLE STABLE V2 GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = ROOT / "assets" / "audio"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def font(size, bold=False):
    if bold:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)

    return ImageFont.load_default()


def fact(story, label, default=""):
    for item in story.get("verified_facts", []):
        if str(item.get("label", "")).upper() == label.upper():
            return clean(item.get("value", default))
    return default


def source_name(story):
    return clean(
        story.get("source", {}).get(
            "name",
            "Official Source"
        )
    )


def source_url(story):
    return clean(
        story.get("source", {}).get(
            "url",
            ""
        )
    )


def county(story):
    return clean(
        story.get(
            "county",
            "Rift Valley"
        )
    )


def title(story):
    return clean(
        story.get(
            "title",
            "Rift Valley Watch"
        )
    )


def draw_wrapped(draw, text, x, y, fnt, fill, width, gap=12):
    words = clean(text).split()
    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word
        box = draw.textbbox((0, 0), test, font=fnt)

        if box[2] <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill
        )
        box = draw.textbbox(
            (x, y),
            line,
            font=fnt
        )
        y += (box[3] - box[1]) + gap

    return y


def background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 14, 24)
    )

    draw = ImageDraw.Draw(image)

    for y in range(0, HEIGHT, 80):
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(22, 30, 44),
            width=1
        )

    for x in range(0, WIDTH, 80):
        draw.line(
            [(x, 0), (x, HEIGHT)],
            fill=(22, 30, 44),
            width=1
        )

    return image


def header(image, section):
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, WIDTH, 110],
        fill=(6, 9, 15)
    )

    draw.rectangle(
        [0, 106, WIDTH, 112],
        fill=(220, 45, 55)
    )

    draw.text(
        (50, 30),
        "RIFT VALLEY WATCH",
        font=font(34, True),
        fill=(245, 247, 250)
    )

    draw.text(
        (760, 39),
        section.upper(),
        font=font(23, True),
        fill=(165, 175, 190)
    )


def footer(image, source):
    draw = ImageDraw.Draw(image)

    draw.line(
        [(50, 1790), (1030, 1790)],
        fill=(60, 70, 85),
        width=2
    )

    draw.text(
        (50, 1820),
        "RIFT VALLEY WATCH",
        font=font(21),
        fill=(165, 175, 190)
    )

    draw.text(
        (650, 1820),
        "SOURCE: " + source[:35],
        font=font(20),
        fill=(165, 175, 190)
    )


# ============================================================
# SCENES
# ============================================================

def scene_latest(story):
    image = background()
    header(image, "THE LATEST")

    draw = ImageDraw.Draw(image)

    draw.text(
        (60, 190),
        "DEVELOPMENT",
        font=font(28, True),
        fill=(220, 45, 55)
    )

    draw_wrapped(
        draw,
        title(story),
        60,
        270,
        font(62, True),
        (245, 247, 250),
        920,
        15
    )

    draw.rounded_rectangle(
        [60, 760, 1020, 1120],
        radius=25,
        fill=(20, 28, 43)
    )

    draw_wrapped(
        draw,
        clean(story.get("summary", "")),
        95,
        815,
        font(31),
        (245, 247, 250),
        870,
        12
    )

    footer(image, source_name(story))
    return image


def scene_location(story):
    image = background()
    header(image, "WHERE IT IS")

    draw = ImageDraw.Draw(image)

    draw.text(
        (60, 190),
        "PROJECT LOCATION",
        font=font(29, True),
        fill=(60, 130, 220)
    )

    draw_wrapped(
        draw,
        county(story),
        60,
        270,
        font(70, True),
        (245, 247, 250),
        900
    )

    draw.rounded_rectangle(
        [60, 600, 1020, 950],
        radius=25,
        fill=(20, 28, 43)
    )

    draw.text(
        (95, 655),
        "LOCATION",
        font=font(26, True),
        fill=(60, 130, 220)
    )

    draw_wrapped(
        draw,
        fact(story, "LOCATION", county(story)),
        95,
        725,
        font(42, True),
        (245, 247, 250),
        850
    )

    draw.rounded_rectangle(
        [60, 1020, 1020, 1320],
        radius=25,
        fill=(20, 28, 43)
    )

    draw.text(
        (95, 1075),
        "STATUS",
        font=font(26, True),
        fill=(48, 180, 115)
    )
