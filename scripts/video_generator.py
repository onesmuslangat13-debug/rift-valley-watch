import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — VIDEO GENERATOR V4
# ============================================================
#
# Visual pipeline:
#   verified story
#        ↓
#   official-source visual discovery
#        ↓
#   real source image when available
#        ↓
#   professional newsroom graphics fallback
#        ↓
#   narration
#        ↓
#   captions
#        ↓
#   MP4 QC
#
# Output:
#   1080x1920
#   30 FPS
#   H.264
#   AAC
# ============================================================


WIDTH = 1080
HEIGHT = 1920
FPS = 30

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSET_DIR = ROOT / "assets"
SOURCE_IMAGE_DIR = ASSET_DIR / "source_images"
TEMP_DIR = ROOT / "tmp_video"

SCRIPT_FILE = DATA_DIR / "script.json"
OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"

# Network timeout for official-source image discovery.
NETWORK_TIMEOUT = 15

# Never allow an external image to dominate the story.
MAX_SOURCE_IMAGE_BYTES = 12 * 1024 * 1024


# ============================================================
# BRAND
# ============================================================

BRAND = "RIFT VALLEY WATCH"
TAGLINE = "TRACKING VERIFIED DEVELOPMENTS ACROSS THE REGION"

BG = (8, 15, 27)
BG_2 = (13, 24, 42)
WHITE = (248, 250, 252)
LIGHT = (211, 220, 231)
MUTED = (145, 158, 176)
RED = (218, 38, 48)
RED_DARK = (120, 25, 33)
BLUE = (32, 105, 175)
BLUE_DARK = (15, 51, 91)
GREEN = (46, 156, 96)
BLACK = (0, 0, 0)


# ============================================================
# COMMAND HELPERS
# ============================================================

def run_command(command, check=True):
    print("\n$ " + " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.stdout.strip():
        print(result.stdout[-5000:])

    if result.stderr.strip():
        print(result.stderr[-5000:])

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# STORY / SCRIPT
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_script():
    if not SCRIPT_FILE.exists():
        raise FileNotFoundError(
            f"Missing generated script: {SCRIPT_FILE}"
        )

    data = load_json(SCRIPT_FILE)

    if not data.get("qc", {}).get("ready_for_video", False):
        raise RuntimeError(
            "Editorial QC rejected the story. "
            "Video generation stopped."
        )

    return data


def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    replacements = {
        "Road lenght": "Road length",
        "road lenght": "road length",
        "Ksh": "KSh",
        "KSH": "KSh",
        "  ": " ",
        "\n\n": "\n",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return value.strip()


def get_fact(script, label, default=""):
    for fact in script.get("verified_facts", []):
        if fact.get("label") == label:
            return clean_text(fact.get("value", default))

    return default


def get_section(script, name, default=""):
    return clean_text(
        script.get("sections", {}).get(name, default)
    )


def story_meta(script):
    return {
        "title": clean_text(script.get("title", "")),
        "county": clean_text(script.get("county", "")),
        "category": clean_text(script.get("category", "NEWS")),
        "date": clean_text(script.get("date", "")),
    }


# ============================================================
# FONT / DRAWING
# ============================================================

def font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR

    if not path.exists():
        return ImageFont.load_default()

    return ImageFont.truetype(str(path), size)


def text_width(draw, text, fnt):
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0]


def wrap_text(draw, text, fnt, max_width):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word

        if text_width(draw, candidate, fnt) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped(
    draw,
    text,
    xy,
    fnt,
    fill,
    max_width,
    line_spacing=12,
    max_lines=None,
):
    x, y = xy
    lines = wrap_text(draw, text, fnt, max_width)

    if max_lines:
        if len(lines) > max_lines:
            lines = lines[:max_lines]

            last = lines[-1]

            while (
                text_width(draw, last + "...", fnt)
                > max_width
                and len(last) > 3
            ):
                last = last[:-1]

            lines[-1] = last.rstrip() + "..."

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill,
        )

        box = draw.textbbox((x, y), line, font=fnt)
        y += (box[3] - box[1]) + line_spacing

    return y


def rounded_rectangle(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def gradient_background():
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    pixels = image.load()

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(BG[0] * (1 - ratio) + BG_2[0] * ratio)
        g = int(BG[1] * (1 - ratio) + BG_2[1] * ratio)
        b = int(BG[2] * (1 - ratio) + BG_2[2] * ratio)

        for x in range(WIDTH):
            pixels[x, y] = (r, g, b)

    return image


# ============================================================
# BRAND ELEMENTS
# ============================================================

def add_brand_header(draw, category="NEWS"):
    draw.rectangle(
        (0, 0, WIDTH, 115),
        fill=(5, 10, 19),
    )

    draw.rectangle(
        (0, 112, WIDTH, 116),
        fill=RED,
    )

    draw.text(
        (60, 34),
        BRAND,
        font=font(40, True),
        fill=WHITE,
    )

    cat = clean_text(category).upper()

    draw.text(
        (WIDTH - 60 - text_width(draw, cat, font(25, True)), 43),
        cat,
        font=font(25, True),
        fill=RED,
    )


def add_footer(draw, date_text=""):
    draw.rectangle(
        (0, HEIGHT - 105, WIDTH, HEIGHT),
        fill=(5, 10, 19),
    )

    draw.text(
        (55, HEIGHT - 78),
        TAGLINE,
        font=font(19, True),
        fill=MUTED,
    )

    if date_text:
        date_text = clean_text(date_text)

        w = text_width(draw, date_text, font(19, True))

        draw.text(
            (WIDTH - 55 - w, HEIGHT - 78),
            date_text,
            font=font(19, True),
            fill=WHITE,
        )


def add_red_line(draw, y):
    draw.rectangle(
        (60, y, WIDTH - 60, y + 5),
        fill=RED,
    )


def add_section_label(draw, label, y=150):
    label = clean_text(label).upper()

    draw.text(
        (60, y),
        label,
        font=font(25, True),
        fill=RED,
    )


# ============================================================
# SOURCE IMAGE DISCOVERY
# ============================================================

def safe_filename(text):
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", text)
    return text[:100].strip("_") or "source_image"


def source_image_path(script):
    title = safe_filename(script.get("title", "story"))
    return SOURCE_IMAGE_DIR / f"{title}.jpg"


def download_url(url, destination):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; RiftValleyWatch/4.0)"
                )
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=NETWORK_TIMEOUT,
        ) as response:

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if "image" not in content_type:
                return False

            data = response.read(MAX_SOURCE_IMAGE_BYTES + 1)

            if len(data) > MAX_SOURCE_IMAGE_BYTES:
                return False

        with open(destination, "wb") as f:
            f.write(data)

        return True

    except Exception as exc:
        print(
            f"Source image download failed: {exc}"
        )

        return False


def validate_image(path):
    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        if width < 300 or height < 200:
            return False

        return True

    except Exception:
        return False


def extract_image_urls_from_html(html, base_url):
    urls = []

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image',
        r'<img[^>]+src=["\']([^"\']+)',
        r'<img[^>]+data-src=["\']([^"\']+)',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for item in matches:
            item = item.strip()

            if not item:
                continue

            absolute = urllib.parse.urljoin(
                base_url,
                item,
            )

            if absolute not in urls:
                urls.append(absolute)

    return urls


def fetch_source_html(url):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; RiftValleyWatch/4.0)"
                )
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=NETWORK_TIMEOUT,
        ) as response:

            content_type = response.headers.get(
                "Content-Type",
                "",
            ).lower()

            if "text/html" not in content_type:
                return ""

            data = response.read(3 * 1024 * 1024)

        return data.decode(
            "utf-8",
            errors="ignore",
        )

    except Exception as exc:
        print(
            f"Official source request failed: {exc}"
        )

        return ""


def discover_source_image(script):
    source = script.get("source", {})

    source_url = clean_text(
        source.get("url", "")
    )

    if not source_url.startswith(
        ("http://", "https://")
    ):
        print(
            "No valid official source URL. "
            "Using newsroom graphics."
        )
        return None

    destination = source_image_path(script)

    if destination.exists() and validate_image(destination):
        print(
            f"Using cached source image: {destination}"
        )
        return destination

    print("\n==========================================")
    print("SOURCE VISUAL DISCOVERY")
    print("==========================================")
    print(f"Official source: {source_url}")

    html = fetch_source_html(source_url)

    if not html:
        print(
            "Official source could not be read."
        )
        print(
            "Fallback: professional newsroom graphics."
        )
        return None

    image_urls = extract_image_urls_from_html(
        html,
        source_url,
    )

    print(
        f"Candidate image URLs found: "
        f"{len(image_urls)}"
    )

    for index, image_url in enumerate(
        image_urls[:12],
        start=1,
    ):
        print(
            f"[{index}] {image_url}"
        )

        temporary = destination.with_suffix(
            f".candidate{index}.jpg"
        )

        if download_url(
            image_url,
            temporary,
        ):
            if validate_image(temporary):
                try:
                    normalize_source_image(
                        temporary,
                        destination,
                    )

                    temporary.unlink(
                        missing_ok=True
                    )

                    if validate_image(destination):
                        print(
                            "REAL SOURCE IMAGE FOUND."
                        )

                        return destination

                except Exception as exc:
                    print(
                        f"Image normalization failed: {exc}"
                    )

        temporary.unlink(
            missing_ok=True
        )

    print(
        "No usable official-source image found."
    )

    print(
        "Fallback: professional newsroom graphics."
    )

    return None


def normalize_source_image(source_path, destination):
    with Image.open(source_path) as original:
        image = original.convert("RGB")

        # Preserve the photograph while ensuring
        # reasonable resolution.
        max_dimension = 2200

        if max(image.size) > max_dimension:
            scale = max_dimension / max(image.size)

            new_size = (
                max(1, int(image.width * scale)),
                max(1, int(image.height * scale)),
            )

            image = image.resize(
                new_size,
                Image.Resampling.LANCZOS,
            )

        image.save(
            destination,
            "JPEG",
            quality=92,
            optimize=True,
        )


# ============================================================
# PHOTO PROCESSING
# ============================================================

def crop_cover(image, width, height):
    image = image.convert("RGB")

    source_ratio = image.width / image.height
    target_ratio = width / height

    if source_ratio > target_ratio:
        new_height = image.height
        new_width = int(new_height * target_ratio)

        left = (image.width - new_width) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                new_height,
            )
        )

    else:
        new_width = image.width
        new_height = int(new_width / target_ratio)

        top = (image.height - new_height) // 2

        image = image.crop(
            (
                0,
                top,
                new_width,
                top + new_height,
            )
        )

    return image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


def photo_background(path):
    with Image.open(path) as source:
        photo = crop_cover(
            source,
            WIDTH,
            HEIGHT,
        )

    # Slight blur keeps text readable.
    photo = photo.filter(
        ImageFilter.GaussianBlur(radius=0.7)
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    overlay_draw = ImageDraw.Draw(overlay)

    # Professional newsroom darkening.
    for y in range(HEIGHT):
        alpha = int(
            65 +
            125 *
            (y / HEIGHT)
        )

        overlay_draw.line(
            (0, y, WIDTH, y),
            fill=(3, 8, 15, alpha),
        )

    photo = photo.convert("RGBA")
    photo.alpha_composite(overlay)

    return photo.convert("RGB")


# ============================================================
# REAL PHOTO CARD
# ============================================================

def create_photo_card(script, image_path):
    image = photo_background(image_path)
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    # Breaking-news tag.
    rounded_rectangle(
        draw,
        (55, 155, 325, 215),
        18,
        RED,
    )

    draw.text(
        (80, 171),
        "DEVELOPMENT UPDATE",
        font=font(20, True),
        fill=WHITE,
    )

    # Lower-third.
    panel_top = 1320

    rounded_rectangle(
        draw,
        (
            35,
            panel_top,
            WIDTH - 35,
            1760,
        ),
        30,
        (4, 10, 18),
    )

    add_red_line(
        draw,
        panel_top + 35,
    )

    title = meta["title"]

    draw_wrapped(
        draw,
        title,
        (70, panel_top + 75),
        font(49, True),
        WHITE,
        WIDTH - 140,
        line_spacing=12,
        max_lines=4,
    )

    county = meta["county"]

    draw.text(
        (70, 1685),
        county.upper(),
        font=font(27, True),
        fill=RED,
    )

    add_footer(
        draw,
        meta["date"],
    )

    return image


# ============================================================
# GRAPHIC FALLBACK CARDS
# ============================================================

def create_hook_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "THE LATEST",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    draw_wrapped(
        draw,
        meta["title"],
        (60, 320),
        font(67, True),
        WHITE,
        WIDTH - 120,
        line_spacing=18,
        max_lines=5,
    )

    summary = get_section(
        script,
        "hook",
        "",
    )

    if summary:
        draw_wrapped(
            draw,
            summary,
            (65, 780),
            font(31, False),
            LIGHT,
            WIDTH - 130,
            line_spacing=16,
            max_lines=5,
        )

    rounded_rectangle(
        draw,
        (60, 1110, WIDTH - 60, 1310),
        28,
        (15, 30, 52),
        outline=RED,
        width=3,
    )

    draw.text(
        (95, 1160),
        "VERIFIED REPORT",
        font=font(29, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        f"{meta['county']} • {meta['date']}",
        (95, 1210),
        font(27, True),
        WHITE,
        WIDTH - 190,
        line_spacing=8,
    )

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_location_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "WHERE IT IS",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    county = meta["county"]
    location = get_fact(
        script,
        "LOCATION",
        county,
    )

    rounded_rectangle(
        draw,
        (55, 330, WIDTH - 55, 1040),
        35,
        (10, 25, 43),
        outline=(43, 76, 112),
        width=3,
    )

    # Stylized Kenya locator.
    kenya = [
        (470, 430),
        (560, 390),
        (650, 440),
        (705, 530),
        (670, 650),
        (735, 760),
        (665, 885),
        (545, 930),
        (485, 850),
        (430, 730),
        (450, 600),
    ]

    draw.polygon(
        kenya,
        fill=(19, 54, 82),
        outline=(84, 123, 157),
    )

    # Bomet marker.
    marker_x = 575
    marker_y = 600

    draw.ellipse(
        (
            marker_x - 18,
            marker_y - 18,
            marker_x + 18,
            marker_y + 18,
        ),
        fill=RED,
    )

    draw.ellipse(
        (
            marker_x - 8,
            marker_y - 8,
            marker_x + 8,
            marker_y + 8,
        ),
        fill=WHITE,
    )

    draw.line(
        (
            marker_x,
            marker_y + 18,
            marker_x,
            marker_y + 80,
        ),
        fill=RED,
        width=5,
    )

    draw_wrapped(
        draw,
        location,
        (70, 1100),
        font(42, True),
        WHITE,
        WIDTH - 140,
        line_spacing=14,
        max_lines=4,
    )

    draw.text(
        (70, 1390),
        county.upper(),
        font=font(28, True),
        fill=RED,
    )

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_data_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "KEY FACTS",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    road_length = get_fact(
        script,
        "ROAD_LENGTH",
        "—",
    )

    cost = get_fact(
        script,
        "COST",
        "—",
    )

    status = get_fact(
        script,
        "STATUS",
        "—",
    )

    cards = [
        ("ROAD LENGTH", road_length),
        ("PROJECT COST", cost),
        ("STATUS", status),
    ]

    y = 330

    for label, value in cards:
        rounded_rectangle(
            draw,
            (55, y, WIDTH - 55, y + 270),
            28,
            (12, 29, 48),
            outline=(41, 73, 106),
            width=2,
        )

        draw.text(
            (90, y + 45),
            label,
            font=font(23, True),
            fill=RED,
        )

        draw_wrapped(
            draw,
            value,
            (90, y + 95),
            font(44, True),
            WHITE,
            WIDTH - 180,
            line_spacing=10,
            max_lines=3,
        )

        y += 315

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_route_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "THE ROUTE",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    route = get_fact(
        script,
        "PROJECT",
        "",
    )

    rounded_rectangle(
        draw,
        (50, 320, WIDTH - 50, 1420),
        32,
        (8, 22, 38),
    )

    # Route line.
    points = [
        (140, 520),
        (350, 700),
        (590, 610),
        (800, 830),
        (900, 1080),
        (700, 1250),
        (420, 1180),
    ]

    draw.line(
        points,
        fill=RED,
        width=12,
        joint="curve",
    )

    labels = [
        "Kyogong",
        "Kapkesosio",
        "Sigor",
        "Chebunyo",
        "Lelaitich",
        "Kipreres",
        "Longisa",
    ]

    for index, point in enumerate(points):
        x, y = point

        draw.ellipse(
            (
                x - 17,
                y - 17,
                x + 17,
                y + 17,
            ),
            fill=WHITE,
        )

        label = labels[index]

        draw.text(
            (x + 25, y - 18),
            label,
            font=font(22, True),
            fill=WHITE,
        )

    draw_wrapped(
        draw,
        route,
        (70, 1480),
        font(31, True),
        WHITE,
        WIDTH - 140,
        line_spacing=12,
        max_lines=5,
    )

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_impact_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "WHY IT MATTERS",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    impact = get_fact(
        script,
        "IMPACT",
        "",
    )

    if not impact:
        impact = get_section(
            script,
            "impact",
            "The project is expected to support connectivity and economic activity in the affected area.",
        )

    rounded_rectangle(
        draw,
        (55, 350, WIDTH - 55, 1250),
        35,
        (11, 29, 48),
        outline=(42, 75, 108),
        width=3,
    )

    draw.text(
        (90, 420),
        "ECONOMIC IMPACT",
        font=font(27, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        impact,
        (90, 510),
        font(44, True),
        WHITE,
        WIDTH - 180,
        line_spacing=18,
        max_lines=8,
    )

    context = get_section(
        script,
        "context",
        "",
    )

    if context:
        rounded_rectangle(
            draw,
            (55, 1320, WIDTH - 55, 1600),
            30,
            (7, 18, 31),
        )

        draw.text(
            (90, 1370),
            "CONTEXT",
            font=font(24, True),
            fill=RED,
        )

        draw_wrapped(
            draw,
            context,
            (90, 1430),
            font(29, False),
            LIGHT,
            WIDTH - 180,
            line_spacing=10,
            max_lines=4,
        )

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_source_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    meta = story_meta(script)

    add_brand_header(
        draw,
        meta["category"],
    )

    add_section_label(
        draw,
        "SOURCE",
        170,
    )

    add_red_line(
        draw,
        225,
    )

    source = script.get("source", {})

    source_name = clean_text(
        source.get(
            "name",
            "Official source",
        )
    )

    source_url = clean_text(
        source.get(
            "url",
            "",
        )
    )

    rounded_rectangle(
        draw,
        (55, 360, WIDTH - 55, 1150),
        35,
        (11, 29, 48),
        outline=(42, 75, 108),
        width=3,
    )

    draw.text(
        (90, 430),
        "REPORTING SOURCE",
        font=font(26, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        source_name,
        (90, 510),
        font(48, True),
        WHITE,
        WIDTH - 180,
        line_spacing=15,
        max_lines=3,
    )

    draw.text(
        (90, 700),
        "PUBLISHED / REPORTED",
        font=font(23, True),
        fill=RED,
    )

    draw.text(
        (90, 750),
        meta["date"],
        font=font(38, True),
        fill=WHITE,
    )

    draw.text(
        (90, 850),
        "OFFICIAL SOURCE URL",
        font=font(23, True),
        fill=RED,
    )

    display_url = source_url

    if len(display_url) > 55:
        display_url = display_url[:52] + "..."

    draw_wrapped(
        draw,
        display_url,
        (90, 900),
        font(25, False),
        LIGHT,
        WIDTH - 180,
        line_spacing=8,
        max_lines=4,
    )

    draw.text(
        (90, 1210),
        "VERIFIED FACTS ONLY",
        font=font(28, True),
        fill=WHITE,
    )

    draw_wrapped(
        draw,
        "This report is generated from verified editorial data. Unconfirmed details are not presented as facts.",
        (90, 1280),
        font(29, False),
        LIGHT,
        WIDTH - 180,
        line_spacing=12,
        max_lines=5,
    )

    add_footer(
        draw,
        meta["date"],
    )

    return image


def create_outro_card(script):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 9),
        fill=RED,
    )

    draw.text(
        (60, 500),
        BRAND,
        font=font(64, True),
        fill=WHITE,
    )

    add_red_line(
        draw,
        620,
    )

    draw_wrapped(
        draw,
        TAGLINE,
        (60, 700),
        font(34, True),
        LIGHT,
        WIDTH - 120,
        line_spacing=15,
        max_lines=4,
    )

    draw.text(
        (60, 1050),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=font(27, True),
        fill=RED,
    )

    add_footer(
        draw,
        story_meta(script)["date"],
    )

    return image


# ============================================================
# SCENE MANAGEMENT
# ============================================================

def create_scenes(script, source_image=None):
    scenes = []

    if source_image:
        print(
            "\nREAL PHOTO SCENE ENABLED."
        )

        scenes.append(
            (
                "REAL SOURCE PHOTO",
                create_photo_card(
                    script,
                    source_image,
                ),
            )
        )

    scenes.extend(
        [
            (
                "THE LATEST",
                create_hook_card(script),
            ),
            (
                "LOCATION",
                create_location_card(script),
            ),
            (
                "KEY FACTS",
                create_data_card(script),
            ),
            (
                "THE ROUTE",
                create_route_card(script),
            ),
            (
                "WHY IT MATTERS",
                create_impact_card(script),
            ),
            (
                "SOURCE",
                create_source_card(script),
            ),
            (
                "OUTRO",
                create_outro_card(script),
            ),
        ]
    )

    return scenes


# ============================================================
# NARRATION
# ============================================================

def create_narration(script, work_dir):
    narration_text = clean_text(
        script.get("full_script", "")
    )

    if not narration_text:
        raise RuntimeError(
            "No narration text found."
        )

    output = work_dir / "narration.mp3"

    print("\n==========================================")
    print("CREATING NARRATION")
    print("==========================================")

    tts = gTTS(
        text=narration_text,
        lang="en",
        slow=False,
    )

    tts.save(str(output))

    if not output.exists():
        raise RuntimeError(
            "Narration file was not created."
        )

    return output


# ============================================================
# IMAGE → VIDEO
# ============================================================

def still_to_video(image_path, duration, output_path):
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            f"{duration:.3f}",
            "-r",
            str(FPS),
            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output_path),
        ]
    )


def get_duration(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )

    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_audio_duration(path):
    return get_duration(path)


# ============================================================
# TIMELINE
# ============================================================

def calculate_scene_durations(scene_count, narration_duration):
    if scene_count <= 0:
        return []

    # Professional short-form pacing.
    # Minimum duration prevents unreadable cards.
    minimum = 2.8

    if narration_duration <= 0:
        base = 3.8
    else:
        # Leave room for source and outro.
        base = narration_duration / max(
            1,
            scene_count - 1,
        )

    base = max(minimum, base)

    weights = [
        0.15,
        0.14,
        0.14,
        0.15,
        0.15,
        0.15,
        0.12,
    ]

    if scene_count == 8:
        weights = [
            0.13,
            0.12,
            0.12,
            0.13,
            0.14,
            0.14,
            0.12,
            0.10,
        ]

    weights = weights[:scene_count]

    total = sum(weights)

    weights = [
        w / total
        for w in weights
    ]

    target = max(
        narration_duration + 3.5,
        22.0,
    )

    durations = [
        max(
            minimum,
            target * weight,
        )
        for weight in weights
    ]

    return durations


# ============================================================
# CONCATENATION
# ============================================================

def concatenate_scenes(scene_files, output_path):
    if not scene_files:
        raise RuntimeError(
            "No scene files available."
        )

    inputs = []

    for path in scene_files:
        inputs.extend(
            [
                "-i",
                str(path),
            ]
        )

    concat_inputs = "".join(
        f"[{i}:v:0]"
        for i in range(len(scene_files))
    )

    filter_complex = (
        f"{concat_inputs}"
        f"concat=n={len(scene_files)}:v=1:a=0,"
        "format=yuv420p,"
        "settb=AVTB,"
        "setpts=N/FRAME_RATE/TB[v]"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ]
    )


# ============================================================
# AUDIO
# ============================================================

def add_narration(video_path, narration_path, output_path):
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-af",
            (
                "loudnorm="
                "I=-16:"
                "TP=-1.5:"
                "LRA=11"
            ),
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


# ============================================================
# CAPTIONS
# ============================================================

def split_caption_text(text, max_chars=42):
    words = clean_text(text).split()

    lines = []
    current = ""

    for word in words:
        candidate = (
            word
            if not current
            else current + " " + word
        )

        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def escape_drawtext(text):
    return (
        clean_text(text)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def create_caption_file(script, work_dir):
    text = clean_text(
        script.get("full_script", "")
    )

    caption_file = work_dir / "captions.txt"

    with open(
        caption_file,
        "w",
        encoding="utf-8",
    ) as f:
        for line in split_caption_text(text):
            f.write(line + "\n")

    return caption_file


def burn_captions(video_path, script, output_path):
    caption_file = create_caption_file(
        script,
        TEMP_DIR,
    )

    # Use a timed drawtext stream based on the entire
    # narration. This produces permanent readable captions.
    #
    # The captions are deliberately placed above the
    # bottom branding bar.
    filter_text = (
        f"drawtext="
        f"fontfile={FONT_BOLD}:"
        f"textfile={caption_file}:"
        "fontcolor=white:"
        "fontsize=34:"
        "line_spacing=8:"
        "borderw=3:"
        "bordercolor=black:"
        "box=1:"
        "boxcolor=black@0.62:"
        "boxborderw=18:"
        "x=(w-text_w)/2:"
        "y=h-300"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            filter_text,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


# ============================================================
# VIDEO QC
# ============================================================

def validate_video(path):
    print("\n==========================================")
    print("VIDEO QC")
    print("==========================================")

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration,size:"
                "stream=codec_type,codec_name,"
                "width,height,r_frame_rate"
            ),
            "-of",
            "json",
            str(path),
        ]
    )

    data = json.loads(
        result.stdout
    )

    streams = data.get(
        "streams",
        [],
    )

    video_streams = [
        s for s in streams
        if s.get("codec_type") == "video"
    ]

    audio_streams = [
        s for s in streams
        if s.get("codec_type") == "audio"
    ]

    if not video_streams:
        raise RuntimeError(
            "QC failed: no video stream."
        )

    if not audio_streams:
        raise RuntimeError(
            "QC failed: no audio stream."
        )

    video = video_streams[0]

    if video.get("codec_name") != "h264":
        raise RuntimeError(
            "QC failed: video codec is not H.264."
        )

    if int(video.get("width", 0)) != WIDTH:
        raise RuntimeError(
            f"QC failed: width is not {WIDTH}."
        )

    if int(video.get("height", 0)) != HEIGHT:
        raise RuntimeError(
            f"QC failed: height is not {HEIGHT}."
        )

    duration = float(
        data.get("format", {})
        .get("duration", 0)
    )

    if duration < 10:
        raise RuntimeError(
            "QC failed: video is too short."
        )

    if duration > 180:
        raise RuntimeError(
            "QC failed: video exceeds 180 seconds."
        )

    print(
        f"Duration: {duration:.2f} seconds"
    )

    print(
        f"Resolution: "
        f"{video.get('width')}x"
        f"{video.get('height')}"
    )

    print(
        f"Video codec: "
        f"{video.get('codec_name')}"
    )

    print(
        f"Audio streams: "
        f"{len(audio_streams)}"
    )

    print(
        f"File size: "
        f"{size / 1024 / 1024:.2f} MB"
    )

    print(
        "QC RESULT: PASS"
    )

    return True


# ============================================================
# SAVE VISUAL PLAN
# ============================================================

def write_visual_report(script, source_image, scene_names):
    report = {
        "version": "V4",
        "real_source_visual_used": bool(source_image),
        "source_image": (
            str(source_image.relative_to(ROOT))
            if source_image
            else None
        ),
        "scenes": scene_names,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "visual_policy": {
            "real_source_visual_first": True,
            "professional_graphics_fallback": True,
            "invented_photographs": False,
        },
    }

    output = DATA_DIR / "visual_report.json"

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return output


# ============================================================
# MAIN
# ============================================================

def main():
    print("\n")
    print("==========================================")
    print("RIFT VALLEY WATCH — VIDEO GENERATOR V4")
    print("==========================================")

    ensure_directories()

    script = load_script()

    meta = story_meta(script)

    print(
        f"\nTITLE: {meta['title']}"
    )

    print(
        f"COUNTY: {meta['county']}"
    )

    print(
        f"CATEGORY: {meta['category']}"
    )

    print(
        f"DATE: {meta['date']}"
    )

    print("\nEditorial QC:")
    print(
        json.dumps(
            script.get("qc", {}),
            indent=2,
        )
    )

    # --------------------------------------------------------
    # REAL SOURCE IMAGE
    # --------------------------------------------------------

    source_image = discover_source_image(
        script
    )

    if source_image:
        print(
            "\nVISUAL MODE: "
            "REAL OFFICIAL-SOURCE IMAGE + GRAPHICS"
        )
    else:
        print(
            "\nVISUAL MODE: "
            "PROFESSIONAL GRAPHICS FALLBACK"
        )

    # --------------------------------------------------------
    # WORK DIRECTORY
    # --------------------------------------------------------

    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    scene_files = []

    try:
        # ----------------------------------------------------
        # NARRATION
        # ----------------------------------------------------

        narration_path = create_narration(
            script,
            TEMP_DIR,
        )

        narration_duration = get_audio_duration(
            narration_path
        )

        print(
            f"Narration duration: "
            f"{narration_duration:.2f}s"
        )

        # ----------------------------------------------------
        # SCENES
        # ----------------------------------------------------

        scenes = create_scenes(
            script,
            source_image,
        )

        scene_names = [
            name
            for name, _ in scenes
        ]

        durations = calculate_scene_durations(
            len(scenes),
            narration_duration,
        )

        print("\n==========================================")
        print("SCENE TIMELINE")
        print("==========================================")

        for index, (
            scene_name,
            image,
        ) in enumerate(scenes):

            duration = durations[index]

            image_path = (
                TEMP_DIR /
                f"scene_{index + 1:02d}.png"
            )

            video_path = (
                TEMP_DIR /
                f"scene_{index + 1:02d}.mp4"
            )

            image.save(
                image_path,
                "PNG",
            )

            still_to_video(
                image_path,
                duration,
                video_path,
            )

            scene_files.append(
                video_path
            )

            print(
                f"{index + 1:02d}. "
                f"{scene_name:<22} "
                f"{duration:.2f}s"
            )

        # ----------------------------------------------------
        # VISUAL REPORT
        # ----------------------------------------------------

        report_path = write_visual_report(
            script,
            source_image,
            scene_names,
        )

        print(
            f"\nVisual report: {report_path}"
        )

        # ----------------------------------------------------
        # CONCAT
        # ----------------------------------------------------

        silent_video = (
            TEMP_DIR /
            "silent_video.mp4"
        )

        concatenate_scenes(
            scene_files,
            silent_video,
        )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        narrated_video = (
            TEMP_DIR /
            "narrated_video.mp4"
        )

        add_narration(
            silent_video,
            narration_path,
            narrated_video,
        )

        # ----------------------------------------------------
        # CAPTIONS
        # ----------------------------------------------------

        captioned_video = (
            TEMP_DIR /
            "captioned_video.mp4"
        )

        burn_captions(
            narrated_video,
            script,
            captioned_video,
        )

        # ----------------------------------------------------
        # FINAL OUTPUT
        # ----------------------------------------------------

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        if OUTPUT_FILE.exists():
            OUTPUT_FILE.unlink()

        shutil.copy2(
            captioned_video,
            OUTPUT_FILE,
        )

        # ----------------------------------------------------
        # FINAL QC
        # ----------------------------------------------------

        validate_video(
            OUTPUT_FILE
        )

        print("\n==========================================")
        print("GENERATION COMPLETE")
        print("==========================================")

        print(
            f"MP4: {OUTPUT_FILE}"
        )

        print(
            "STATUS: SUCCESS"
        )

    finally:
        # Keep downloaded source images and the final MP4,
        # but remove temporary rendering files.
        if TEMP_DIR.exists():
            shutil.rmtree(
                TEMP_DIR,
                ignore_errors=True,
            )


if __name__ == "__main__":
    main()
