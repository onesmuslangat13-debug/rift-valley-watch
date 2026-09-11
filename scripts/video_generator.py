import os
import re
import json
import math
import html
import shutil
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH V6
# DATA-DRIVEN NEWSROOM VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"
OUTPUT_DIR = ROOT / "output"
ASSET_DIR = ROOT / "assets"
SOURCE_IMAGE_DIR = ASSET_DIR / "source_images"
AUDIO_DIR = ASSET_DIR / "audio"
SCENE_DIR = OUTPUT_DIR / "scenes"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FONT_DIRS = [
    ROOT / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
]

FONT_REGULAR = None
FONT_BOLD = None


# ============================================================
# BASIC UTILITIES
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def safe_filename(value):
    value = clean_text(value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:100] or "file"


def run_command(command, check=True):
    print()
    print("RUNNING:")
    print(" ".join(str(x) for x in command))
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# FONTS
# ============================================================

def find_font(bold=False):
    candidates = []

    if bold:
        candidates = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "Arial Bold.ttf",
        ]
    else:
        candidates = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "Arial.ttf",
        ]

    for directory in FONT_DIRS:
        if not directory.exists():
            continue

        for candidate in candidates:
            path = directory / candidate
            if path.exists():
                return str(path)

    return None


def get_font(size, bold=False):
    global FONT_REGULAR, FONT_BOLD

    if bold:
        if FONT_BOLD is None:
            FONT_BOLD = find_font(True)

        font_path = FONT_BOLD
    else:
        if FONT_REGULAR is None:
            FONT_REGULAR = find_font(False)

        font_path = FONT_REGULAR

    if font_path:
        return ImageFont.truetype(font_path, int(size))

    return ImageFont.load_default()


# ============================================================
# STORY / SCRIPT
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fact_value(story, *labels):
    wanted = {
        clean_text(x).upper()
        for x in labels
    }

    for fact in story.get("verified_facts", []):
        if not isinstance(fact, dict):
            continue

        label = clean_text(
            fact.get("label", "")
        ).upper()

        if label in wanted:
            return clean_text(
                fact.get("value", "")
            )

    return ""


def story_title(story):
    return clean_text(
        story.get("title", "")
    )


def story_category(story):
    value = clean_text(
        story.get("category", "NEWS")
    ).upper()

    return value or "NEWS"


def story_county(story):
    return clean_text(
        story.get("county", "")
    )


def story_location(story):
    return (
        fact_value(
            story,
            "LOCATION",
            "AREA",
            "COUNTY"
        )
        or story_county(story)
        or "Rift Valley"
    )


def story_cost(story):
    return fact_value(
        story,
        "COST",
        "PROJECT_COST",
        "VALUE",
        "BUDGET"
    )


def story_length(story):
    return fact_value(
        story,
        "ROAD_LENGTH",
        "LENGTH",
        "DISTANCE",
        "COVERAGE"
    )


def story_status(story):
    return fact_value(
        story,
        "STATUS",
        "PROJECT_STATUS"
    )


def story_route(story):
    return fact_value(
        story,
        "PROJECT",
        "ROUTE",
        "ROAD",
        "CORRIDOR"
    )


def story_impact(story):
    return (
        fact_value(
            story,
            "IMPACT",
            "SIGNIFICANCE",
            "BENEFIT"
        )
        or clean_text(
            story.get("summary", "")
        )
    )


def source_name(story):
    source = story.get("source", {})

    if isinstance(source, dict):
        return clean_text(
            source.get("name", "")
        )

    return ""


def source_url(story):
    source = story.get("source", {})

    if isinstance(source, dict):
        return clean_text(
            source.get("url", "")
        )

    return ""


def story_date(story):
    return clean_text(
        story.get("date", "")
    )


def official_statement(story):
    statement = story.get(
        "official_statement",
        {}
    )

    if not isinstance(statement, dict):
        return "", ""

    speaker = clean_text(
        statement.get("speaker", "")
    )

    quote = clean_text(
        statement.get("quote", "")
    )

    return speaker, quote


def get_script_text(story):
    if SCRIPT_FILE.exists():
        try:
            generated = load_json(
                SCRIPT_FILE
            )

            script = clean_text(
                generated.get(
                    "full_script",
                    ""
                )
            )

            if script:
                return script
        except Exception:
            pass

    parts = []

    if story_title(story):
        parts.append(
            story_title(story)
        )

    if story.get("summary"):
        parts.append(
            clean_text(
                story["summary"]
            )
        )

    speaker, quote = official_statement(
        story
    )

    if speaker and quote:
        parts.append(
            f"{speaker} said {quote}"
        )

    return " ".join(parts)


# ============================================================
# VISUAL DESIGN
# ============================================================

def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (5, 11, 20)
    )

    pixels = image.load()

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(5 + 4 * ratio)
        g = int(11 + 8 * ratio)
        b = int(20 + 14 * ratio)

        for x in range(WIDTH):
            pixels[x, y] = (
                r,
                g,
                b
            )

    return image


def add_grid(draw):
    for x in range(
        0,
        WIDTH,
        90
    ):
        draw.line(
            (x, 0, x, HEIGHT),
            fill=(14, 28, 43),
            width=1
        )

    for y in range(
        0,
        HEIGHT,
        90
    ):
        draw.line(
            (0, y, WIDTH, y),
            fill=(14, 28, 43),
            width=1
        )


def top_bar(draw, label):
    draw.rectangle(
        (0, 0, WIDTH, 145),
        fill=(4, 10, 18)
    )

    draw.rectangle(
        (0, 138, WIDTH, 145),
        fill=(220, 35, 42)
    )

    draw.text(
        (55, 45),
        "RIFT VALLEY WATCH",
        font=get_font(
            31,
            True
        ),
        fill=(245, 247, 250)
    )

    draw.text(
        (755, 49),
        label.upper(),
        font=get_font(
            25,
            True
        ),
        fill=(225, 35, 42)
    )


def section_label(draw, text):
    draw.text(
        (55, 190),
        clean_text(text).upper(),
        font=get_font(
            25,
            True
        ),
        fill=(140, 158, 178)
    )


def footer(draw, story):
    date = story_date(story)

    source = source_name(story)

    footer_text = " | ".join(
        x for x in [
            date,
            source
        ]
        if x
    )

    if not footer_text:
        footer_text = "VERIFIED DEVELOPMENT"

    draw.rectangle(
        (
            0,
            1800,
            WIDTH,
            HEIGHT
        ),
        fill=(3, 8, 15)
    )

    draw.text(
        (55, 1840),
        footer_text,
        font=get_font(
            23,
            True
        ),
        fill=(160, 172, 188)
    )


def source_badge(draw):
    draw.rounded_rectangle(
        (
            700,
            1510,
            1015,
            1580
        ),
        radius=18,
        fill=(220, 35, 42)
    )

    draw.text(
        (735, 1528),
        "VERIFIED SOURCE",
        font=get_font(
            21,
            True
        ),
        fill=(255, 255, 255)
    )


def draw_wrapped(
    draw,
    text,
    x,
    y,
    font,
    fill,
    max_width,
    line_spacing=10,
    max_lines=None
):
    text = clean_text(text)

    if not text:
        return y

    words = text.split()
    lines = []
    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    if max_lines:
        if len(lines) > max_lines:
            lines = lines[:max_lines]

            if lines:
                last = lines[-1]

                while True:
                    test = last + "..."

                    bbox = draw.textbbox(
                        (0, 0),
                        test,
                        font=font
                    )

                    if (
                        bbox[2] - bbox[0]
                        <= max_width
                    ):
                        lines[-1] = test
                        break

                    parts = last.split()

                    if len(parts) <= 1:
                        lines[-1] = "..."
                        break

                    last = " ".join(
                        parts[:-1]
                    )

    line_height = (
        font.getbbox("Ag")[3]
        - font.getbbox("Ag")[1]
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += line_height + line_spacing

    return y


# ============================================================
# PHOTO HANDLING
# ============================================================

def is_bad_image_url(url):
    lowered = url.lower()

    bad_terms = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        "placeholder",
        "sprite",
        "pixel",
        "tracking",
        "1x1",
        "facebook",
        "twitter"
    ]

    return any(
        term in lowered
        for term in bad_terms
    )


def extract_image_candidates(
    html_text,
    base_url,
    story
):
    candidates = []

    # OG image first.
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']'
    ]

    for pattern in patterns:
        for match in re.findall(
            pattern,
            html_text,
            flags=re.I
        ):
            candidates.append(
                (
                    urllib.parse.urljoin(
                        base_url,
                        html.unescape(match)
                    ),
                    100
                )
            )

    # IMG tags.
    img_pattern = re.compile(
        r"<img\b([^>]+)>",
        re.I
    )

    src_pattern = re.compile(
        r'(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
        re.I
    )

    alt_pattern = re.compile(
        r'alt=["\']([^"\']*)["\']',
        re.I
    )

    keywords = []

    title = story_title(story)

    keywords.extend(
        re.findall(
            r"[A-Za-z0-9]+",
            title.lower()
        )
    )

    keywords.extend(
        re.findall(
            r"[A-Za-z0-9]+",
            story_county(story).lower()
        )
    )

    route = story_route(story)

    keywords.extend(
        re.findall(
            r"[A-Za-z0-9]+",
            route.lower()
        )
    )

    for tag_match in img_pattern.finditer(
        html_text
    ):
        attrs = tag_match.group(1)

        src_match = src_pattern.search(
            attrs
        )

        if not src_match:
            continue

        url = urllib.parse.urljoin(
            base_url,
            html.unescape(
                src_match.group(1)
            )
        )

        if is_bad_image_url(url):
            continue

        alt_match = alt_pattern.search(
            attrs
        )

        alt = (
            alt_match.group(1).lower()
            if alt_match
            else ""
        )

        score = 25

        for keyword in keywords:
            if (
                keyword
                and len(keyword) >= 4
                and keyword in alt
            ):
                score += 12

            if (
                keyword
                and len(keyword) >= 4
                and keyword in url.lower()
            ):
                score += 5

        candidates.append(
            (url, score)
        )

    # De-duplicate.
    seen = set()
    unique = []

    for url, score in candidates:
        if url in seen:
            continue

        seen.add(url)

        unique.append(
            (url, score)
        )

    unique.sort(
        key=lambda x: x[1],
        reverse=True
    )

    return unique[:12]


def download_image(url, destination):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(compatible; "
                    "RiftValleyWatch/6.0)"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:

            data = response.read()

        with open(
            destination,
            "wb"
        ) as f:
            f.write(data)

        return True

    except Exception as exc:
        print(
            f"Image download failed: {exc}"
        )

        return False


def validate_image(path):
    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        if width < 500 or height < 300:
            return False

        ratio = width / height

        if ratio < 0.45 or ratio > 3.5:
            return False

        return True

    except Exception:
        return False


def find_source_image(story):
    source = story.get(
        "source",
        {}
    )

    if not isinstance(source, dict):
        return None, []

    url = clean_text(
        source.get("url", "")
    )

    if not url.startswith(
        ("http://", "https://")
    ):
        return None, []

    print(
        "Searching official source for "
        "relevant visual..."
    )

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(compatible; "
                    "RiftValleyWatch/6.0)"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=25
        ) as response:

            html_text = response.read().decode(
                "utf-8",
                errors="ignore"
            )

    except Exception as exc:
        print(
            f"Could not fetch source page: {exc}"
        )

        return None, []

    candidates = extract_image_candidates(
        html_text,
        url,
        story
    )

    accepted = []

    for index, (
        image_url,
        score
    ) in enumerate(candidates):

        if score < 25:
            continue

        extension = ".jpg"

        destination = (
            SOURCE_IMAGE_DIR
            / f"source_{index}{extension}"
        )

        if not download_image(
            image_url,
            destination
        ):
            continue

        if not validate_image(
            destination
        ):
            try:
                destination.unlink()
            except Exception:
                pass

            continue

        try:
            with Image.open(
                destination
            ) as image:

                image = image.convert(
                    "RGB"
                )

                # Reject obvious tiny/flat assets.
                width, height = image.size

                if width < 700 or height < 400:
                    continue

                image.save(
                    destination,
                    "JPEG",
                    quality=94
                )

        except Exception:
            continue

        accepted.append(
            {
                "path": str(destination),
                "url": image_url,
                "score": score
            }
        )

        # We only need a few good candidates.
        if len(accepted) >= 3:
            break

    if not accepted:
        print(
            "No sufficiently relevant source "
            "photo found. Using editorial graphics."
        )

        return None, []

    accepted.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    print(
        "Accepted source image:",
        accepted[0]["path"]
    )

    return (
        accepted[0]["path"],
        accepted
    )


def photo_background(path):
    with Image.open(path) as original:

        original = original.convert(
            "RGB"
        )

        image_ratio = (
            original.width
            / original.height
        )

        target_ratio = (
            WIDTH / HEIGHT
        )

        if image_ratio > target_ratio:

            new_height = HEIGHT

            new_width = int(
                new_height * image_ratio
            )

            resized = original.resize(
                (
                    new_width,
                    new_height
                ),
                Image.Resampling.LANCZOS
            )

            left = (
                new_width - WIDTH
            ) // 2

            resized = resized.crop(
                (
                    left,
                    0,
                    left + WIDTH,
                    HEIGHT
                )
            )

        else:

            new_width = WIDTH

            new_height = int(
                new_width / image_ratio
            )

            resized = original.resize(
                (
                    new_width,
                    new_height
                ),
                Image.Resampling.LANCZOS
            )

            top = (
                new_height - HEIGHT
            ) // 2

            resized = resized.crop(
                (
                    0,
                    top,
                    WIDTH,
                    top + HEIGHT
                )
            )

        # Dark editorial treatment.
        overlay = Image.new(
            "RGBA",
            (WIDTH, HEIGHT),
            (0, 0, 0, 75)
        )

        resized = resized.convert(
            "RGBA"
        )

        resized.alpha_composite(
            overlay
        )

        return resized.convert(
            "RGB"
        )


# ============================================================
# SCENES
# ============================================================

def scene_latest(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "THE LATEST"
    )

    section_label(
        draw,
        story_category(story)
    )

    title = story_title(story)

    draw_wrapped(
        draw,
        title,
        55,
        300,
        get_font(62, True),
        (250, 252, 255),
        950,
        15,
        5
    )

    location = story_location(
        story
    )

    draw.text(
        (55, 735),
        "LOCATION",
        font=get_font(
            25,
            True
        ),
        fill=(145, 162, 182)
    )

    draw_wrapped(
        draw,
        location,
        55,
        790,
        get_font(
            43,
            True
        ),
        (225, 35, 42),
        950,
        10,
        3
    )

    length = story_length(story)
    cost = story_cost(story)

    card_y = 1050

    if length:
        draw.rounded_rectangle(
            (
                50,
                card_y,
                505,
                card_y + 280
            ),
            radius=25,
            fill=(9, 28, 47),
            outline=(53, 76, 100),
            width=2
        )

        draw.text(
            (85, card_y + 40),
            "SCALE",
            font=get_font(
                25,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            length,
            85,
            card_y + 105,
            get_font(
                58,
                True
            ),
            (255, 255, 255),
            370,
            8,
            2
        )

    if cost:
        draw.rounded_rectangle(
            (
                540,
                card_y,
                1030,
                card_y + 280
            ),
            radius=25,
            fill=(9, 28, 47),
            outline=(53, 76, 100),
            width=2
        )

        draw.text(
            (575, card_y + 40),
            "REPORTED VALUE",
            font=get_font(
                25,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            cost,
            575,
            card_y + 105,
            get_font(
                48,
                True
            ),
            (255, 255, 255),
            390,
            8,
            2
        )

    footer(
        draw,
        story
    )

    return image


def scene_photo(story, image_path):
    image = photo_background(
        image_path
    )

    draw = ImageDraw.Draw(image)

    top_bar(
        draw,
        "VISUAL EVIDENCE"
    )

    section_label(
        draw,
        "OFFICIAL SOURCE VISUAL"
    )

    # Lower newsroom information panel.
    draw.rounded_rectangle(
        (
            35,
            1120,
            1045,
            1710
        ),
        radius=30,
        fill=(2, 8, 16)
    )

    draw_wrapped(
        draw,
        story_title(story),
        70,
        1190,
        get_font(
            48,
            True
        ),
        (255, 255, 255),
        900,
        13,
        5
    )

    source = source_name(story)

    if source:
        draw.text(
            (70, 1535),
            source.upper(),
            font=get_font(
                28,
                True
            ),
            fill=(225, 35, 42)
        )

    source_badge(draw)

    footer(
        draw,
        story
    )

    return image


def scene_location(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "WHERE IT IS"
    )

    section_label(
        draw,
        "LOCATION"
    )

    county = story_county(
        story
    )

    location = story_location(
        story
    )

    draw_wrapped(
        draw,
        county.upper()
        if county
        else "RIFT VALLEY",
        55,
        300,
        get_font(
            78,
            True
        ),
        (255, 255, 255),
        950,
        10,
        3
    )

    draw.text(
        (55, 570),
        "PROJECT AREA",
        font=get_font(
            27,
            True
        ),
        fill=(145, 162, 182)
    )

    draw_wrapped(
        draw,
        location,
        55,
        625,
        get_font(
            47,
            True
        ),
        (225, 35, 42),
        950,
        12,
        4
    )

    # Editorial locator graphic.
    draw.rounded_rectangle(
        (
            70,
            930,
            1010,
            1360
        ),
        radius=30,
        fill=(8, 26, 44),
        outline=(55, 80, 105),
        width=2
    )

    draw.ellipse(
        (
            475,
            1035,
            605,
            1165
        ),
        fill=(225, 35, 42)
    )

    draw.ellipse(
        (
            505,
            1065,
            575,
            1135
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (110, 980),
        "VERIFIED LOCATION",
        font=get_font(
            25,
            True
        ),
        fill=(145, 162, 182)
    )

    draw_wrapped(
        draw,
        location,
        110,
        1200,
        get_font(
            35,
            True
        ),
        (235, 239, 244),
        820,
        10,
        3
    )

    footer(
        draw,
        story
    )

    return image


def scene_facts(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "KEY FACTS"
    )

    section_label(
        draw,
        "VERIFIED DATA"
    )

    facts = []

    length = story_length(story)
    cost = story_cost(story)
    status = story_status(story)
    location = story_location(story)

    if length:
        facts.append(
            ("SCALE / LENGTH", length)
        )

    if cost:
        facts.append(
            ("REPORTED COST", cost)
        )

    if status:
        facts.append(
            ("CURRENT STATUS", status)
        )

    if location and len(facts) < 3:
        facts.append(
            ("LOCATION", location)
        )

    y = 335

    for label, value in facts[:3]:

        draw.rounded_rectangle(
            (
                50,
                y,
                1030,
                y + 330
            ),
            radius=28,
            fill=(9, 28, 47),
            outline=(52, 76, 101),
            width=2
        )

        draw.text(
            (85, y + 42),
            label,
            font=get_font(
                25,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            value,
            85,
            y + 115,
            get_font(
                52,
                True
            ),
            (255, 255, 255),
            870,
            10,
            3
        )

        y += 385

    footer(
        draw,
        story
    )

    return image


def scene_route(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "THE ROUTE"
    )

    section_label(
        draw,
        "PROJECT CORRIDOR"
    )

    route = story_route(
        story
    )

    length = story_length(
        story
    )

    draw_wrapped(
        draw,
        length.upper()
        if length
        else "PROJECT ROUTE",
        55,
        300,
        get_font(
            66,
            True
        ),
        (255, 255, 255),
        950,
        10,
        2
    )

    draw.text(
        (55, 505),
        "CONNECTION",
        font=get_font(
            28,
            True
        ),
        fill=(225, 35, 42)
    )

    # Abstract route visual.
    # Clearly editorial — not presented as a geographic map.
    points = [
        (120, 760),
        (300, 660),
        (480, 790),
        (665, 625),
        (850, 770),
        (960, 650)
    ]

    for i in range(
        len(points) - 1
    ):
        draw.line(
            (
                points[i][0],
                points[i][1],
                points[i + 1][0],
                points[i + 1][1]
            ),
            fill=(225, 35, 42),
            width=14
        )

    for i, (x, y) in enumerate(
        points
    ):
        draw.ellipse(
            (
                x - 23,
                y - 23,
                x + 23,
                y + 23
            ),
            fill=(255, 255, 255),
            outline=(225, 35, 42),
            width=6
        )

        draw.text(
            (x - 7, y + 38),
            str(i + 1),
            font=get_font(
                23,
                True
            ),
            fill=(220, 228, 236)
        )

    draw.rounded_rectangle(
        (
            50,
            1060,
            1030,
            1515
        ),
        radius=28,
        fill=(9, 28, 47),
        outline=(52, 76, 101),
        width=2
    )

    draw.text(
        (85, 1115),
        "VERIFIED ROUTE / PROJECT",
        font=get_font(
            25,
            True
        ),
        fill=(145, 162, 182)
    )

    if route:
        draw_wrapped(
            draw,
            route,
            85,
            1185,
            get_font(
                38,
                True
            ),
            (255, 255, 255),
            875,
            12,
            5
        )
    else:
        draw_wrapped(
            draw,
            "Specific route details were not included in the verified facts.",
            85,
            1190,
            get_font(
                34,
                True
            ),
            (230, 235, 242),
            875,
            12,
            4
        )

    footer(
        draw,
        story
    )

    return image


def scene_impact(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "WHY IT MATTERS"
    )

    section_label(
        draw,
        "EDITORIAL CONTEXT"
    )

    impact = story_impact(
        story
    )

    draw.text(
        (55, 315),
        "IMPACT",
        font=get_font(
            31,
            True
        ),
        fill=(225, 35, 42)
    )

    draw_wrapped(
        draw,
        impact,
        55,
        395,
        get_font(
            48,
            True
        ),
        (245, 248, 251),
        950,
        15,
        10
    )

    status = story_status(
        story
    )

    if status:

        draw.rounded_rectangle(
            (
                55,
                1370,
                1025,
                1570
            ),
            radius=25,
            fill=(9, 28, 47)
        )

        draw.text(
            (90, 1415),
            "CURRENT STATUS",
            font=get_font(
                24,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            status,
            90,
            1470,
            get_font(
                32,
                True
            ),
            (255, 255, 255),
            870,
            8,
            2
        )

    footer(
        draw,
        story
    )

    return image


def scene_statement(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "OFFICIAL STATEMENT"
    )

    section_label(
        draw,
        "ON THE RECORD"
    )

    speaker, quote = official_statement(
        story
    )

    if not quote:
        draw_wrapped(
            draw,
            "No official statement was supplied in the verified story record.",
            55,
            400,
            get_font(
                43,
                True
            ),
            (230, 235, 242),
            950,
            14,
            6
        )

    else:

        draw.text(
            (55, 340),
            "“",
            font=get_font(
                110,
                True
            ),
            fill=(225, 35, 42)
        )

        draw_wrapped(
            draw,
            quote,
            95,
            455,
            get_font(
                43,
                True
            ),
            (247, 249, 251),
            880,
            15,
            12
        )

        if speaker:
            draw.text(
                (95, 1435),
                speaker,
                font=get_font(
                    31,
                    True
                ),
                fill=(225, 35, 42)
            )

            draw.text(
                (95, 1490),
                "OFFICIAL STATEMENT",
                font=get_font(
                    22,
                    True
                ),
                fill=(145, 162, 182)
            )

    footer(
        draw,
        story
    )

    return image


def scene_source(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    top_bar(
        draw,
        "SOURCE"
    )

    section_label(
        draw,
        "VERIFICATION"
    )

    source = source_name(
        story
    )

    url = source_url(
        story
    )

    date = story_date(
        story
    )

    draw.text(
        (55, 340),
        "REPORTING SOURCE",
        font=get_font(
            28,
            True
        ),
        fill=(145, 162, 182)
    )

    draw_wrapped(
        draw,
        source or "Official source",
        55,
        405,
        get_font(
            55,
            True
        ),
        (255, 255, 255),
        950,
        12,
        4
    )

    if date:

        draw.text(
            (55, 680),
            "DATE",
            font=get_font(
                26,
                True
            ),
            fill=(145, 162, 182)
        )

        draw.text(
            (55, 735),
            date,
            font=get_font(
                42,
                True
            ),
            fill=(225, 35, 42)
        )

    draw.rounded_rectangle(
        (
            50,
            900,
            1030,
            1435
        ),
        radius=28,
        fill=(9, 28, 47),
        outline=(52, 76, 101),
        width=2
    )

    draw.text(
        (85, 955),
        "SOURCE URL",
        font=get_font(
            25,
            True
        ),
        fill=(145, 162, 182)
    )

    if url:
        display_url = url.replace(
            "https://",
            ""
        ).replace(
            "http://",
            ""
        )

        draw_wrapped(
            draw,
            display_url,
            85,
            1025,
            get_font(
                32,
                True
            ),
            (240, 244, 248),
            875,
            12,
            7
        )

    else:
        draw.text(
            (85, 1030),
            "No source URL supplied.",
            font=get_font(
                32,
                True
            ),
            fill=(225, 35, 42)
        )

    source_badge(draw)

    footer(
        draw,
        story
    )

    return image


def scene_outro(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            12
        ),
        fill=(225, 35, 42)
    )

    draw.text(
        (55, 590),
        "RIFT VALLEY",
        font=get_font(
            82,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 700),
        "WATCH",
        font=get_font(
            110,
            True
        ),
        fill=(225, 35, 42)
    )

    draw.line(
        (
            55,
            865,
            1025,
            865
        ),
        fill=(65, 83, 104),
        width=3
    )

    draw_wrapped(
        draw,
        "Tracking verified developments across the region.",
        55,
        950,
        get_font(
            43,
            True
        ),
        (225, 231, 238),
        950,
        14,
        4
    )

    draw.text(
        (55, 1190),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=get_font(
            29,
            True
        ),
        fill=(145, 162, 182)
    )

    draw.text(
        (55, 1280),
        "RIFT VALLEY WATCH",
        font=get_font(
            36,
            True
        ),
        fill=(255, 255, 255)
    )

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration_segments(story):
    title = story_title(story)
    summary = clean_text(
        story.get("summary", "")
    )

    location = story_location(
        story
    )

    length = story_length(
        story
    )

    cost = story_cost(
        story
    )

    route = story_route(
        story
    )

    status = story_status(
        story
    )

    impact = story_impact(
        story
    )

    speaker, quote = official_statement(
        story
    )

    segments = []

    if title:
        segments.append(
            title + "."
        )

    if summary:
        segments.append(
            summary
        )

    location_sentence = (
        f"The project is located in "
        f"{location}."
    )

    if location:
        segments.append(
            location_sentence
        )

    fact_parts = []

    if length:
        fact_parts.append(
            f"The reported scale is {length}."
        )

    if cost:
        fact_parts.append(
            f"The reported cost is {cost}."
        )

    if status:
        fact_parts.append(
            f"Current status: {status}."
        )

    if fact_parts:
        segments.append(
            " ".join(fact_parts)
        )

    if route:
        segments.append(
            f"The reported project route is {route}."
        )

    if impact:
        segments.append(
            f"Why it matters: {impact}"
        )

    if speaker and quote:
        segments.append(
            f"{speaker} said: {quote}"
        )

    if not segments:
        segments.append(
            "Rift Valley Watch. "
            "Verified regional news."
        )

    return segments


def create_audio(text, index):
    text = clean_text(text)

    output = (
        AUDIO_DIR
        / f"segment_{index:02d}.mp3"
    )

    if output.exists() and output.stat().st_size > 1000:
        return output

    print(
        f"Generating narration segment {index}..."
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(output)
    )

    return output


def audio_duration(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
    )

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        return 2.0


# ============================================================
# CAPTIONS
# ============================================================

def split_caption_words(text):
    words = clean_text(
        text
    ).split()

    groups = []

    for i in range(
        0,
        len(words),
        6
    ):
        groups.append(
            words[i:i + 6]
        )

    return groups


def create_srt(text, duration, path):
    groups = split_caption_words(
        text
    )

    if not groups:
        groups = [[""]]

    total_words = sum(
        len(group)
        for group in groups
    )

    if total_words <= 0:
        total_words = 1

    current = 0.0
    entries = []

    for index, group in enumerate(
        groups,
        start=1
    ):

        word_count = len(group)

        segment = (
            duration
            * word_count
            / total_words
        )

        start = current
        end = min(
            duration,
            current + segment
        )

        caption = " ".join(
            group
        )

        # Prevent very short flashes.
        if end - start < 0.75:
            end = min(
                duration,
                start + 0.75
            )

        entries.append(
            (
                index,
                start,
                end,
                caption
            )
        )

        current = end

    def timestamp(seconds):
        milliseconds = int(
            round(seconds * 1000)
        )

        hours = milliseconds // 3600000
        milliseconds %= 3600000

        minutes = milliseconds // 60000
        milliseconds %= 60000

        seconds_int = milliseconds // 1000
        milliseconds %= 1000

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds_int:02d},"
            f"{milliseconds:03d}"
        )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        for number, start, end, caption in entries:

            f.write(
                f"{number}\n"
            )

            f.write(
                f"{timestamp(start)} --> "
                f"{timestamp(end)}\n"
            )

            f.write(
                caption
                + "\n\n"
            )

    return path


# ============================================================
# IMAGE SCENE CREATION
# ============================================================

def save_scene(image, index):
    path = (
        SCENE_DIR
        / f"scene_{index:02d}.png"
    )

    image.save(
        path,
        "PNG",
        optimize=True
    )

    return path


def create_scene_video(
    image_path,
    audio_path,
    caption_text,
    scene_index
):
    duration = audio_duration(
        audio_path
    )

    srt_path = (
        SCENE_DIR
        / f"scene_{scene_index:02d}.srt"
    )

    create_srt(
        caption_text,
        duration,
        srt_path
    )

    output = (
        SCENE_DIR
        / f"scene_{scene_index:02d}.mp4"
    )

    # FFmpeg-safe subtitle path.
    subtitle_path = str(
        srt_path.resolve()
    ).replace(
        "\\",
        "/"
    )

    subtitle_path = (
        subtitle_path
        .replace(":", r"\:")
        .replace("'", r"\'")
    )

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,"
        f"subtitles='{subtitle_path}'"
        ":force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=17,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=180'"
        "[v]"
    )

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
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "1:a:0",
        "-t",
        f"{duration:.3f}",
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
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(output)
    ]

    run_command(
        command
    )

    if not output.exists():
        raise RuntimeError(
            f"Scene was not created: {output}"
        )

    if output.stat().st_size < 50000:
        raise RuntimeError(
            f"Scene file is suspiciously small: {output}"
        )

    return output, duration, srt_path


# ============================================================
# FINAL CONCAT
# ============================================================

def concat_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene videos available."
        )

    inputs = []

    for path in scene_files:
        inputs.extend(
            [
                "-i",
                str(path)
            ]
        )

    filter_parts = []

    for i in range(
        len(scene_files)
    ):
        filter_parts.append(
            f"[{i}:v:0]"
            f"[{i}:a:0]"
            f"setpts=PTS-STARTPTS"
            f"[v{i}][a{i}]"
        )

    concat_inputs = "".join(
        f"[v{i}][a{i}]"
        for i in range(
            len(scene_files)
        )
    )

    filter_parts.append(
        concat_inputs
        + f"concat=n={len(scene_files)}:v=1:a=1"
        "[v][a]"
    )

    filter_complex = ";".join(
        filter_parts
    )

    command = [
        "ffmpeg",
        "-y"
    ]

    command.extend(inputs)

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
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
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(OUTPUT_FILE)
        ]
    )

    run_command(
        command
    )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return OUTPUT_FILE


# ============================================================
# FINAL QC
# ============================================================

def inspect_mp4(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path)
        ]
    )

    try:
        return json.loads(
            result.stdout
        )
    except Exception:
        return {}


def validate_final_mp4(path):
    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    metadata = inspect_mp4(
        path
    )

    streams = metadata.get(
        "streams",
        []
    )

    video = [
        s for s in streams
        if s.get("codec_type") == "video"
    ]

    audio = [
        s for s in streams
        if s.get("codec_type") == "audio"
    ]

    if not video:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if not audio:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    video_stream = video[0]

    if video_stream.get(
        "codec_name"
    ) != "h264":
        raise RuntimeError(
            "Final video is not H.264."
        )

    if int(
        video_stream.get("width", 0)
    ) != WIDTH:
        raise RuntimeError(
            "Final video width is not 1080."
        )

    if int(
        video_stream.get("height", 0)
    ) != HEIGHT:
        raise RuntimeError(
            "Final video height is not 1920."
        )

    duration = float(
        metadata.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
    )

    if duration < 8:
        raise RuntimeError(
            "Final video is too short."
        )

    if duration > 180:
        raise RuntimeError(
            "Final video exceeds 180 seconds."
        )

    return {
        "valid": True,
        "size_bytes": size,
        "duration_seconds": round(
            duration,
            2
        ),
        "video_codec": video_stream.get(
            "codec_name"
        ),
        "width": video_stream.get(
            "width"
        ),
        "height": video_stream.get(
            "height"
        ),
        "audio_codec": audio[0].get(
            "codec_name"
        )
    }


# ============================================================
# VISUAL REPORT
# ============================================================

def write_visual_report(
    story,
    scene_records,
    source_candidates,
    source_image
):
    report = {
        "version": "V6",
        "generated_at": datetime.utcnow().isoformat()
        + "Z",

        "title": story_title(
            story
        ),

        "county": story_county(
            story
        ),

        "source": {
            "name": source_name(
                story
            ),
            "url": source_url(
                story
            )
        },

        "source_visual": {
            "found": bool(source_image),
            "selected": source_image,
            "candidate_count": len(
                source_candidates
            ),
            "candidates": source_candidates
        },

        "scenes": scene_records,

        "requirements": {
            "vertical_1080x1920": True,
            "fps": 30,
            "burned_in_captions": True,
            "official_source_visual_attempted": True,
            "data_driven": True,
            "automatic_qc": True
        }
    }

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("RIFT VALLEY WATCH V6")
    print("DATA-DRIVEN NEWSROOM VIDEO GENERATOR")
    print("=" * 70)

    ensure_directories()

    if OUTPUT_DIR.exists():
        for item in SCENE_DIR.glob("*"):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass

    story = load_json(
        STORY_FILE
    )

    print()
    print("STORY:")
    print(story_title(story))
    print()
    print("COUNTY:")
    print(story_county(story))
    print()
    print("SOURCE:")
    print(source_name(story))
    print()

    # --------------------------------------------------------
    # SOURCE IMAGE
    # --------------------------------------------------------

    source_image = None
    source_candidates = []

    try:
        (
            source_image,
            source_candidates
        ) = find_source_image(
            story
        )
    except Exception as exc:
        print(
            "Source image discovery failed:"
        )
        print(exc)

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration_segments = (
        build_narration_segments(
            story
        )
    )

    print()
    print(
        f"Narration segments: "
        f"{len(narration_segments)}"
    )

    audio_files = []

    for index, text in enumerate(
        narration_segments,
        start=1
    ):
        audio_files.append(
            create_audio(
                text,
                index
            )
        )

    # --------------------------------------------------------
    # VISUAL SCENE PLAN
    # --------------------------------------------------------

    scene_plan = []

    if source_image:
        scene_plan.append(
            (
                "VISUAL EVIDENCE",
                scene_photo,
                source_image
            )
        )

    scene_plan.extend(
        [
            (
                "WHERE IT IS",
                scene_location,
                None
            ),
            (
                "KEY FACTS",
                scene_facts,
                None
            ),
            (
                "THE ROUTE",
                scene_route,
                None
            ),
            (
                "WHY IT MATTERS",
                scene_impact,
                None
            ),
            (
                "OFFICIAL STATEMENT",
                scene_statement,
                None
            ),
            (
                "SOURCE",
                scene_source,
                None
            ),
            (
                "OUTRO",
                scene_outro,
                None
            )
        ]
    )

    # --------------------------------------------------------
    # SCENES
    # --------------------------------------------------------

    scene_records = []
    scene_files = []

    audio_index = 0

    for scene_number, (
        scene_name,
        renderer,
        argument
    ) in enumerate(
        scene_plan,
        start=1
    ):

        print()
        print("=" * 70)
        print(
            f"SCENE {scene_number}: "
            f"{scene_name}"
        )
        print("=" * 70)

        # Use narration sequentially.
        if audio_index >= len(
            audio_files
        ):
            audio_index = len(
                audio_files
            ) - 1

        if audio_index < 0:
            audio_index = 0

        audio_path = audio_files[
            audio_index
        ]

        if argument:
            image = renderer(
                story,
                argument
            )
        else:
            image = renderer(
                story
            )

        image_path = save_scene(
            image,
            scene_number
        )

        # Give the scene an appropriate
        # narration segment.
        caption_text = (
            narration_segments[
                min(
                    audio_index,
                    len(
                        narration_segments
                    ) - 1
                )
            ]
        )

        scene_video, duration, srt = (
            create_scene_video(
                image_path,
                audio_path,
                caption_text,
                scene_number
            )
        )

        scene_files.append(
            scene_video
        )

        scene_records.append(
            {
                "scene": scene_number,
                "name": scene_name,
                "image": str(
                    image_path
                ),
                "video": str(
                    scene_video
                ),
                "caption": str(
                    srt
                ),
                "duration": round(
                    duration,
                    2
                )
            }
        )

        audio_index += 1

    # --------------------------------------------------------
    # FINAL OUTRO NARRATION
    # --------------------------------------------------------
    # If there are more scenes than narration
    # segments, the final scenes use the last
    # segment. This keeps the render stable.

    print()
    print("=" * 70)
    print("ASSEMBLING FINAL MP4")
    print("=" * 70)

    concat_scenes(
        scene_files
    )

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL QUALITY CONTROL")
    print("=" * 70)

    qc = validate_final_mp4(
        OUTPUT_FILE
    )

    print(
        json.dumps(
            qc,
            indent=2
        )
    )

    write_visual_report(
        story,
        scene_records,
        source_candidates,
        source_image
    )

    print()
    print("=" * 70)
    print("VIDEO GENERATION SUCCESSFUL")
    print("=" * 70)
    print()
    print(
        f"MP4: {OUTPUT_FILE}"
    )
    print(
        f"Size: {qc['size_bytes']} bytes"
    )
    print(
        f"Duration: "
        f"{qc['duration_seconds']} seconds"
    )
    print(
        f"Resolution: "
        f"{qc['width']}x{qc['height']}"
    )
    print(
        f"Video: {qc['video_codec']}"
    )
    print(
        f"Audio: {qc['audio_codec']}"
    )
    print(
        f"Visual report: {REPORT_FILE}"
    )
    print()


if __name__ == "__main__":
    main()
