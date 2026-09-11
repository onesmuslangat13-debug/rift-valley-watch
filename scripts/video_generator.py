import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — V5.1 VIDEO GENERATOR
# Stable GitHub Actions build
# 1080x1920 / 30 FPS / H.264 / AAC
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = OUTPUT_DIR / "v5_work"
IMAGE_DIR = ROOT / "assets" / "source_images"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = DATA_DIR / "visual_report.json"

W = 1080
H = 1920
FPS = 30


# ============================================================
# FONT DISCOVERY
# ============================================================

FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]


def find_font(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


FONT_REGULAR = find_font(FONT_CANDIDATES_REGULAR)
FONT_BOLD = find_font(FONT_CANDIDATES_BOLD)


def get_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR

    if path:
        return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# COMMAND HELPERS
# ============================================================

def run_command(command):
    print("$", " ".join(str(x) for x in command))

    result = subprocess.run(
        [str(x) for x in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def safe_name(value):
    value = clean_text(value)

    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value
    )

    return value[:100]


def wrap_text(draw, text, fnt, max_width):
    words = clean_text(text).split()

    if not words:
        return []

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
            font=fnt
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

    return lines


def draw_wrapped(
    draw,
    text,
    x,
    y,
    fnt,
    fill,
    max_width,
    spacing=12
):
    lines = wrap_text(
        draw,
        text,
        fnt,
        max_width
    )

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill
        )

        bbox = draw.textbbox(
            (x, y),
            line,
            font=fnt
        )

        y += (
            bbox[3] -
            bbox[1] +
            spacing
        )

    return y


# ============================================================
# IMAGE FETCHING
# ============================================================

def fetch_bytes(url, timeout=20):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/131 Safari/537.36"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        return response.read()


def make_absolute(base, value):

    if not value:
        return None

    value = value.strip()

    if value.startswith("//"):
        return "https:" + value

    return urllib.parse.urljoin(
        base,
        value
    )


def discover_images(story):

    source = story.get(
        "source",
        {}
    )

    source_url = source.get(
        "url"
    )

    if not source_url:
        return []

    print("\nSearching official source for images...")

    try:
        html = fetch_bytes(
            source_url
        ).decode(
            "utf-8",
            errors="ignore"
        )

    except Exception as exc:

        print(
            "Source image search failed:",
            str(exc)
        )

        return []

    candidates = []

    # --------------------------------------------------------
    # OpenGraph image
    # --------------------------------------------------------

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            re.I
        )

        for value in matches:

            url = make_absolute(
                source_url,
                value
            )

            if url:
                candidates.append(
                    ("metadata", url)
                )

    # --------------------------------------------------------
    # HTML images
    # --------------------------------------------------------

    img_pattern = (
        r"<img[^>]+"
        r"(?:src|data-src|data-lazy-src|data-original)"
        r'=["\']([^"\']+)["\']'
        r"[^>]*>"
    )

    matches = re.findall(
        img_pattern,
        html,
        re.I
    )

    title_words = set(
        re.findall(
            r"[a-z0-9]{4,}",
            (
                clean_text(
                    story.get(
                        "title",
                        ""
                    )
                )
                + " "
                + clean_text(
                    story.get(
                        "county",
                        ""
                    )
                )
            ).lower()
        )
    )

    reject_words = [
        "logo",
        "icon",
        "favicon",
        "avatar",
        "sprite",
        "placeholder",
        "advert",
        "banner-ad",
        "facebook",
        "twitter-icon",
        "youtube-icon",
        "linkedin-icon",
        "pixel",
    ]

    scored = []

    for value in matches:

        url = make_absolute(
            source_url,
            value
        )

        if not url:
            continue

        low = url.lower()

        score = 10

        if any(
            word in low
            for word in reject_words
        ):
            score -= 100

        for word in title_words:

            if word in low:
                score += 5

        scored.append(
            (
                score,
                "html",
                url
            )
        )

    for item in candidates:

        score = 100

        url = item[1].lower()

        if any(
            word in url
            for word in reject_words
        ):
            score -= 100

        scored.append(
            (
                score,
                item[0],
                item[1]
            )
        )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    output = []
    seen = set()

    for score, kind, url in scored:

        if url in seen:
            continue

        seen.add(url)

        if score < 0:
            continue

        output.append(
            (
                score,
                kind,
                url
            )
        )

        if len(output) >= 15:
            break

    print(
        f"Image candidates found: {len(output)}"
    )

    return output


def download_image(url, destination):

    try:

        raw = fetch_bytes(
            url,
            timeout=25
        )

        temp = destination.with_suffix(
            ".tmp"
        )

        with open(
            temp,
            "wb"
        ) as f:

            f.write(raw)

        with Image.open(temp) as img:

            img.load()

            width, height = img.size

            print(
                f"Candidate image: "
                f"{width}x{height}"
            )

            if width < 500:
                temp.unlink(
                    missing_ok=True
                )
                return False

            if height < 300:
                temp.unlink(
                    missing_ok=True
                )
                return False

            ratio = (
                width /
                float(height)
            )

            if ratio < 0.35 or ratio > 4.5:
                temp.unlink(
                    missing_ok=True
                )
                return False

            converted = img.convert(
                "RGB"
            )

            converted.save(
                destination,
                "JPEG",
                quality=92
            )

        temp.unlink(
            missing_ok=True
        )

        return True

    except Exception as exc:

        print(
            "Rejected image:",
            str(exc)[:150]
        )

        try:
            destination.unlink()
        except Exception:
            pass

        return False


def get_source_image(story):

    candidates = discover_images(
        story
    )

    story_name = safe_name(
        story.get(
            "title",
            "story"
        )
    )

    for index, (_, _, url) in enumerate(
        candidates
    ):

        destination = (
            IMAGE_DIR /
            f"{story_name}_{index}.jpg"
        )

        if destination.exists():

            try:

                with Image.open(
                    destination
                ) as img:

                    if (
                        img.width >= 500
                        and
                        img.height >= 300
                    ):

                        print(
                            "Using cached image:",
                            destination
                        )

                        return destination

            except Exception:
                destination.unlink(
                    missing_ok=True
                )

        print(
            f"Downloading candidate "
            f"{index + 1}/{len(candidates)}"
        )

        if download_image(
            url,
            destination
        ):

            print(
                "Official source image accepted."
            )

            return destination

    print(
        "No usable official image found."
    )

    return None


# ============================================================
# BACKGROUNDS
# ============================================================

def create_background():

    image = Image.new(
        "RGB",
        (W, H)
    )

    pixels = image.load()

    for y in range(H):

        ratio = y / float(H)

        r = int(
            4 +
            5 * ratio
        )

        g = int(
            12 +
            9 * ratio
        )

        b = int(
            25 +
            17 * ratio
        )

        for x in range(W):

            pixels[x, y] = (
                r,
                g,
                b
            )

    return image


def photo_background(path):

    with Image.open(path) as source:

        source = source.convert(
            "RGB"
        )

        source_ratio = (
            source.width /
            float(source.height)
        )

        target_ratio = (
            W /
            float(H)
        )

        if source_ratio > target_ratio:

            new_height = H

            new_width = int(
                H *
                source_ratio
            )

        else:

            new_width = W

            new_height = int(
                W /
                source_ratio
            )

        source = source.resize(
            (
                new_width,
                new_height
            ),
            Image.Resampling.LANCZOS
        )

        left = (
            new_width -
            W
        ) // 2

        top = (
            new_height -
            H
        ) // 2

        image = source.crop(
            (
                left,
                top,
                left + W,
                top + H
            )
        )

    # Dark newsroom overlay
    overlay = Image.new(
        "RGBA",
        (W, H),
        (3, 10, 20, 100)
    )

    image = image.convert(
        "RGBA"
    )

    image.alpha_composite(
        overlay
    )

    # Bottom readability layer
    draw = ImageDraw.Draw(
        image
    )

    for y in range(
        int(H * 0.45),
        H
    ):

        ratio = (
            y -
            H * 0.45
        ) / (
            H * 0.55
        )

        alpha = int(
            min(
                200,
                200 * ratio
            )
        )

        draw.line(
            (
                0,
                y,
                W,
                y
            ),
            fill=(
                0,
                0,
                0,
                alpha
            )
        )

    return image.convert(
        "RGB"
    )


# ============================================================
# NEWSROOM COMPONENTS
# ============================================================

def top_bar(draw, section):

    draw.rectangle(
        (0, 0, W, 108),
        fill=(4, 13, 27)
    )

    draw.rectangle(
        (0, 100, W, 108),
        fill=(225, 35, 42)
    )

    draw.text(
        (50, 30),
        "RIFT VALLEY WATCH",
        font=get_font(
            31,
            True
        ),
        fill=(245, 247, 250)
    )

    label = clean_text(
        section
    ).upper()

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=get_font(
            24,
            True
        )
    )

    draw.text(
        (
            W -
            (bbox[2] - bbox[0]) -
            50,
            35
        ),
        label,
        font=get_font(
            24,
            True
        ),
        fill=(225, 35, 42)
    )


def footer(draw, story):

    draw.rectangle(
        (0, H - 90, W, H),
        fill=(3, 9, 18)
    )

    county = clean_text(
        story.get(
            "county",
            ""
        )
    )

    date = clean_text(
        story.get(
            "date",
            ""
        )
    )

    draw.text(
        (50, H - 63),
        county,
        font=get_font(
            22,
            True
        ),
        fill=(235, 238, 242)
    )

    bbox = draw.textbbox(
        (0, 0),
        date,
        font=get_font(
            21,
            True
        )
    )

    draw.text(
        (
            W -
            (bbox[2] - bbox[0]) -
            50,
            H - 63
        ),
        date,
        font=get_font(
            21,
            True
        ),
        fill=(160, 170, 185)
    )


def section_label(
    draw,
    text,
    y=160
):

    text = clean_text(
        text
    ).upper()

    fnt = get_font(
        26,
        True
    )

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=fnt
    )

    width = (
        bbox[2] -
        bbox[0] +
        42
    )

    draw.rounded_rectangle(
        (
            50,
            y,
            50 + width,
            y + 54
        ),
        radius=12,
        fill=(225, 35, 42)
    )

    draw.text(
        (
            71,
            y + 10
        ),
        text,
        font=fnt,
        fill=(255, 255, 255)
    )


def source_badge(draw):

    draw.rounded_rectangle(
        (
            50,
            H - 170,
            330,
            H - 115
        ),
        radius=12,
        fill=(17, 35, 43)
    )

    draw.text(
        (
            70,
            H - 156
        ),
        "VERIFIED SOURCE",
        font=get_font(
            21,
            True
        ),
        fill=(130, 220, 170)
    )


# ============================================================
# SCENES
# ============================================================

def scene_latest(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "THE LATEST"
    )

    section_label(
        draw,
        "DEVELOPMENT"
    )

    draw.text(
        (50, 320),
        "65 KM",
        font=get_font(
            125,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 475),
        "ROAD PROJECT",
        font=get_font(
            56,
            True
        ),
        fill=(225, 35, 42)
    )

    draw_wrapped(
        draw,
        story.get(
            "title",
            ""
        ),
        55,
        620,
        get_font(
            52,
            True
        ),
        (238, 242, 247),
        950,
        14
    )

    draw.text(
        (55, 1060),
        "PROJECT VALUE",
        font=get_font(
            27,
            True
        ),
        fill=(145, 160, 180)
    )

    draw.text(
        (55, 1110),
        "KSh 2.1 BILLION",
        font=get_font(
            65,
            True
        ),
        fill=(255, 255, 255)
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

    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "VISUAL EVIDENCE"
    )

    section_label(
        draw,
        "OFFICIAL SOURCE"
    )

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    draw_wrapped(
        draw,
        title,
        50,
        1300,
        get_font(
            54,
            True
        ),
        (255, 255, 255),
        950,
        14
    )

    draw.text(
        (55, 1635),
        clean_text(
            story.get(
                "source",
                {}
            ).get(
                "name",
                ""
            )
        ),
        font=get_font(
            25,
            True
        ),
        fill=(225, 35, 42)
    )

    source_badge(
        draw
    )

    footer(
        draw,
        story
    )

    return image


def scene_location(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "WHERE IT IS"
    )

    section_label(
        draw,
        "LOCATION"
    )

    draw.text(
        (55, 320),
        "BOMET",
        font=get_font(
            105,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (58, 450),
        "CHEPALUNGU CONSTITUENCY",
        font=get_font(
            38,
            True
        ),
        fill=(225, 35, 42)
    )

    # Stylised location panel
    draw.rounded_rectangle(
        (
            95,
            650,
            985,
            1160
        ),
        radius=30,
        fill=(8, 25, 42),
        outline=(55, 80, 105),
        width=3
    )

    # Kenya-inspired abstract outline.
    # This is deliberately a visual locator,
    # not an exact administrative map.
    points = [
        (430, 735),
        (650, 700),
        (790, 790),
        (755, 930),
        (650, 1080),
        (470, 1110),
        (350, 970),
        (340, 830)
    ]

    draw.polygon(
        points,
        fill=(15, 42, 65),
        outline=(105, 130, 155)
    )

    marker_x = 560
    marker_y = 875

    draw.ellipse(
        (
            marker_x - 16,
            marker_y - 16,
            marker_x + 16,
            marker_y + 16
        ),
        fill=(225, 35, 42)
    )

    draw.ellipse(
        (
            marker_x - 30,
            marker_y - 30,
            marker_x + 30,
            marker_y + 30
        ),
        outline=(225, 35, 42),
        width=3
    )

    draw.text(
        (
            615,
            835
        ),
        "BOMET",
        font=get_font(
            32,
            True
        ),
        fill=(255, 255, 255)
    )

    draw_wrapped(
        draw,
        "The project is located in Chepalungu Constituency, Bomet County.",
        55,
        1270,
        get_font(
            39,
            True
        ),
        (230, 235, 242),
        950,
        13
    )

    footer(
        draw,
        story
    )

    return image


def scene_facts(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "KEY FACTS"
    )

    section_label(
        draw,
        "VERIFIED DATA"
    )

    cards = [
        (
            "ROAD LENGTH",
            "65 KM"
        ),
        (
            "PROJECT COST",
            "KSh 2.1B"
        ),
        (
            "STATUS",
            "ONGOING"
        )
    ]

    y = 350

    for label, value in cards:

        draw.rounded_rectangle(
            (
                50,
                y,
                1030,
                y + 285
            ),
            radius=25,
            fill=(9, 27, 46),
            outline=(48, 70, 94),
            width=2
        )

        draw.text(
            (
                85,
                y + 42
            ),
            label,
            font=get_font(
                27,
                True
            ),
            fill=(145, 162, 182)
        )

        draw.text(
            (
                85,
                y + 105
            ),
            value,
            font=get_font(
                72,
                True
            ),
            fill=(255, 255, 255)
        )

        y += 345

    footer(
        draw,
        story
    )

    return image


def scene_route(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "THE ROUTE"
    )

    section_label(
        draw,
        "ROAD CORRIDOR"
    )

    draw.text(
        (55, 320),
        "65-KILOMETRE",
        font=get_font(
            65,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 410),
        "ROAD CONNECTION",
        font=get_font(
            62,
            True
        ),
        fill=(225, 35, 42)
    )

    points = [
        (100, 720),
        (310, 620),
        (520, 780),
        (715, 650),
        (940, 810)
    ]

    labels = [
        "Kyogong",
        "Kapkesosio",
        "Sigor",
        "Chebunyo",
        "Longisa"
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
            width=12
        )

    for point, label in zip(
        points,
        labels
    ):

        x, y = point

        draw.ellipse(
            (
                x - 20,
                y - 20,
                x + 20,
                y + 20
            ),
            fill=(255, 255, 255),
            outline=(225, 35, 42),
            width=5
        )

        draw.text(
            (
                x - 5,
                y + 40
            ),
            label,
            font=get_font(
                23,
                True
            ),
            fill=(230, 235, 242)
        )

    route_text = (
        "Kyogong-Kapkesosio-Sigor-Chebunyo / "
        "Sigor-Lelaitich-Kipreres-Longisa"
    )

    draw_wrapped(
        draw,
        route_text,
        55,
        1060,
        get_font(
            36,
            True
        ),
        (228, 233, 240),
        950,
        14
    )

    footer(
        draw,
        story
    )

    return image


def scene_impact(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "WHY IT MATTERS"
    )

    section_label(
        draw,
        "EXPECTED IMPACT"
    )

    draw.text(
        (55, 330),
        "ECONOMIC",
        font=get_font(
            75,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 425),
        "POTENTIAL",
        font=get_font(
            75,
            True
        ),
        fill=(225, 35, 42)
    )

    impact = (
        "Bomet County Government says the project "
        "is expected to unlock the economic potential "
        "of the area and the wider county."
    )

    draw_wrapped(
        draw,
        impact,
        55,
        620,
        get_font(
            44,
            True
        ),
        (232, 237, 243),
        950,
        16
    )

    # Economic network graphic
    nodes = [
        (180, 1200),
        (540, 1050),
        (880, 1200),
        (350, 1460),
        (750, 1470)
    ]

    for i in range(
        len(nodes)
    ):

        for j in range(
            i + 1,
            len(nodes)
        ):

            draw.line(
                (
                    nodes[i][0],
                    nodes[i][1],
                    nodes[j][0],
                    nodes[j][1]
                ),
                fill=(45, 70, 95),
                width=4
            )

    for x, y in nodes:

        draw.ellipse(
            (
                x - 28,
                y - 28,
                x + 28,
                y + 28
            ),
            fill=(225, 35, 42)
        )

    footer(
        draw,
        story
    )

    return image


def scene_statement(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "OFFICIAL STATEMENT"
    )

    section_label(
        draw,
        "GOVERNMENT STATEMENT"
    )

    statement = story.get(
        "official_statement",
        {}
    )

    speaker = clean_text(
        statement.get(
            "speaker",
            ""
        )
    )

    quote = clean_text(
        statement.get(
            "quote",
            ""
        )
    )

    draw.text(
        (55, 330),
        speaker,
        font=get_font(
            43,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.line(
        (
            55,
            440,
            1025,
            440
        ),
        fill=(225, 35, 42),
        width=5
    )

    draw_wrapped(
        draw,
        quote,
        55,
        540,
        get_font(
            43,
            False
        ),
        (230, 235, 242),
        950,
        18
    )

    footer(
        draw,
        story
    )

    return image


def scene_source(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "SOURCE"
    )

    section_label(
        draw,
        "VERIFICATION"
    )

    source = story.get(
        "source",
        {}
    )

    draw.text(
        (55, 340),
        "OFFICIAL SOURCE",
        font=get_font(
            52,
            True
        ),
        fill=(130, 220, 170)
    )

    draw_wrapped(
        draw,
        source.get(
            "name",
            ""
        ),
        55,
        475,
        get_font(
            46,
            True
        ),
        (255, 255, 255),
        950,
        15
    )

    draw.text(
        (55, 680),
        "REPORT DATE",
        font=get_font(
            26,
            True
        ),
        fill=(145, 160, 180)
    )

    draw.text(
        (55, 735),
        clean_text(
            story.get(
                "date",
                ""
            )
        ),
        font=get_font(
            43,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 900),
        "EDITORIAL STANDARD",
        font=get_font(
            27,
            True
        ),
        fill=(145, 160, 180)
    )

    editorial = (
        "Confirmed facts are presented separately "
        "from information that has not been verified."
    )

    draw_wrapped(
        draw,
        editorial,
        55,
        960,
        get_font(
            34,
            True
        ),
        (220, 227, 236),
        950,
        14
    )

    draw.text(
        (55, 1300),
        "SOURCE URL",
        font=get_font(
            26,
            True
        ),
        fill=(145, 160, 180)
    )

    draw_wrapped(
        draw,
        source.get(
            "url",
            ""
        ),
        55,
        1360,
        get_font(
            28,
            False
        ),
        (180, 195, 212),
        950,
        12
    )

    footer(
        draw,
        story
    )

    return image


def scene_outro(story):

    image = create_background()
    draw = ImageDraw.Draw(
        image
    )

    draw.rectangle(
        (
            0,
            0,
            W,
            12
        ),
        fill=(225, 35, 42)
    )

    draw.text(
        (55, 530),
        "RIFT VALLEY",
        font=get_font(
            75,
            True
        ),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 625),
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
            805,
            1025,
            805
        ),
        fill=(65, 82, 103),
        width=3
    )

    draw_wrapped(
        draw,
        "Tracking verified developments across the region.",
        55,
        915,
        get_font(
            43,
            True
        ),
        (225, 231, 238),
        900,
        15
    )

    draw.text(
        (55, 1260),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=get_font(
            29,
            True
        ),
        fill=(145, 160, 180)
    )

    return image


# ============================================================
# NARRATION
# ============================================================

def narration_segments(story):

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    statement = story.get(
        "official_statement",
        {}
    )

    quote = clean_text(
        statement.get(
            "quote",
            ""
        )
    )

    source_name = clean_text(
        story.get(
            "source",
            {}
        ).get(
            "name",
            ""
        )
    )

    return [

        (
            "THE LATEST",
            (
                f"{title}. "
                "Construction works are currently ongoing "
                "in Bomet County."
            )
        ),

        (
            "WHERE IT IS",
            (
                "The project is located in "
                "Chepalungu Constituency in Bomet County."
            )
        ),

        (
            "KEY FACTS",
            (
                "The road project covers 65 kilometres "
                "and has a reported cost of "
                "2.1 billion Kenyan shillings. "
                "Construction is ongoing."
            )
        ),

        (
            "THE ROUTE",
            (
                "The reported corridor covers "
                "Kyogong, Kapkesosio, Sigor and Chebunyo, "
                "with another section through Lelaitich, "
                "Kipreres and Longisa."
            )
        ),

        (
            "WHY IT MATTERS",
            (
                "Bomet County Government says the project "
                "is expected to unlock economic potential "
                "in the area and the wider county."
            )
        ),

        (
            "OFFICIAL STATEMENT",
            (
                f"Deputy President Kithure Kindiki said: "
                f"{quote}"
                if quote
                else
                "Government officials have called for "
                "close monitoring of road construction."
            )
        ),

        (
            "SOURCE",
            (
                f"This report is based on information "
                f"published by {source_name}."
            )
        ),

        (
            "OUTRO",
            (
                "Rift Valley Watch. "
                "Tracking verified developments "
                "across the region."
            )
        )
    ]


def create_voice(text, output):

    text = clean_text(
        text
    )

    if not text:
        raise RuntimeError(
            "Empty narration text."
        )

    speaker = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    speaker.save(
        str(output)
    )


def get_duration(audio):

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio)
        ]
    )

    return float(
        result.stdout.strip()
    )


# ============================================================
# TIMED CAPTIONS
# ============================================================

def caption_groups(text):

    words = clean_text(
        text
    ).split()

    groups = []

    current = []

    for word in words:

        current.append(
            word
        )

        if len(current) >= 7:

            groups.append(
                " ".join(current)
            )

            current = []

    if current:
        groups.append(
            " ".join(current)
        )

    return groups


def srt_time(seconds):

    seconds = max(
        0.0,
        float(seconds)
    )

    hours = int(
        seconds // 3600
    )

    minutes = int(
        (seconds % 3600) // 60
    )

    secs = int(
        seconds % 60
    )

    milliseconds = int(
        round(
            (
                seconds -
                int(seconds)
            ) *
            1000
        )
    )

    if milliseconds >= 1000:
        milliseconds = 0
        secs += 1

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def create_srt(text, duration, output):

    groups = caption_groups(
        text
    )

    if not groups:
        groups = [text]

    weights = [
        max(
            1,
            len(group.split())
        )
        for group in groups
    ]

    total = sum(
        weights
    )

    current = 0.0
    entries = []

    for index, group in enumerate(
        groups
    ):

        segment = (
            duration *
            weights[index] /
            total
        )

        start = current
        end = min(
            duration,
            current + segment
        )

        entries.append(
            str(index + 1)
        )

        entries.append(
            f"{srt_time(start)} --> "
            f"{srt_time(end)}"
        )

        entries.append(
            group
        )

        entries.append("")

        current = end

    with open(
        output,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(entries)
        )


# ============================================================
# SAFE FFMPEG PATH
# ============================================================

def ffmpeg_filter_path(path):

    value = str(
        Path(path).resolve()
    )

    # FFmpeg filter syntax escaping
    value = value.replace(
        "\\",
        "/"
    )

    value = value.replace(
        "'",
        r"\'"
    )

    value = value.replace(
        ":",
        r"\:"
    )

    value = value.replace(
        "[",
        r"\["
    )

    value = value.replace(
        "]",
        r"\]"
    )

    return value


# ============================================================
# SCENE VIDEO
# ============================================================

def create_scene_video(
    image_path,
    audio_path,
    subtitle_path,
    output_path,
    motion=False
):

    duration = get_duration(
        audio_path
    )

    if duration < 1:
        duration = 1.5

    image_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920"
    )

    if motion:

        # Stable slow zoom.
        # No dynamic crop expressions.
        image_filter = (
            "scale=1188:2112,"
            "crop=1080:1920:"
            "(iw-1080)/2:"
            "(ih-1920)/2"
        )

    subtitle_file = ffmpeg_filter_path(
        subtitle_path
    )

    subtitle_filter = (
        f"subtitles='{subtitle_file}'"
        ":force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=18,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginL=55,"
        "MarginR=55,"
        "MarginV=145'"
    )

    vf = (
        image_filter +
        "," +
        subtitle_filter
    )

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

        "-vf",
        vf,

        "-t",
        f"{duration:.3f}",

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-shortest",

        str(output_path)
    ]

    run_command(
        command
    )

    return duration


# ============================================================
# CONCATENATION
# ============================================================

def concatenate(scene_files):

    inputs = []

    for scene in scene_files:
        inputs.extend(
            [
                "-i",
                str(scene)
            ]
        )

    video_labels = []

    audio_labels = []

    filters = []

    for index in range(
        len(scene_files)
    ):

        video_labels.append(
            f"[v{index}]"
        )

        audio_labels.append(
            f"[a{index}]"
        )

        filters.append(
            f"[{index}:v]"
            f"setpts=PTS-STARTPTS"
            f"[v{index}]"
        )

        filters.append(
            f"[{index}:a]"
            f"asetpts=PTS-STARTPTS"
            f"[a{index}]"
        )

    filters.append(
        "".join(video_labels)
        +
        f"concat=n={len(scene_files)}:"
        "v=1:a=0[outv]"
    )

    filters.append(
        "".join(audio_labels)
        +
        f"concat=n={len(scene_files)}:"
        "v=0:a=1[outa]"
    )

    filter_complex = ";".join(
        filters
    )

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    run_command(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            str(OUTPUT_FILE)
        ]
    )


# ============================================================
# FINAL QC
# ============================================================

def inspect_video():

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
            str(OUTPUT_FILE)
        ]
    )

    return json.loads(
        result.stdout
    )


def final_qc():

    print("\n==========================================")
    print("FINAL VIDEO QC")
    print("==========================================")

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "QC FAILED: MP4 does not exist."
        )

    size = OUTPUT_FILE.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "QC FAILED: MP4 is too small."
        )

    info = inspect_video()

    streams = info.get(
        "streams",
        []
    )

    video = None
    audio = None

    for stream in streams:

        if stream.get(
            "codec_type"
        ) == "video":

            video = stream

        if stream.get(
            "codec_type"
        ) == "audio":

            audio = stream

    if video is None:
        raise RuntimeError(
            "QC FAILED: no video stream."
        )

    if audio is None:
        raise RuntimeError(
            "QC FAILED: no audio stream."
        )

    if video.get(
        "codec_name"
    ) != "h264":

        raise RuntimeError(
            "QC FAILED: video is not H.264."
        )

    if int(
        video.get(
            "width",
            0
        )
    ) != 1080:

        raise RuntimeError(
            "QC FAILED: width is not 1080."
        )

    if int(
        video.get(
            "height",
            0
        )
    ) != 1920:

        raise RuntimeError(
            "QC FAILED: height is not 1920."
        )

    duration = float(
        info.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
    )

    if duration < 10:
        raise RuntimeError(
            "QC FAILED: video is shorter than 10 seconds."
        )

    if duration > 180:
        raise RuntimeError(
            "QC FAILED: video exceeds 180 seconds."
        )

    print(
        f"MP4 size: {size / 1024 / 1024:.2f} MB"
    )

    print(
        f"Duration: {duration:.2f} seconds"
    )

    print(
        "Resolution: 1080x1920"
    )

    print(
        "Video codec:",
        video.get("codec_name")
    )

    print(
        "Audio codec:",
        audio.get("codec_name")
    )

    print(
        "FINAL QC: PASSED"
    )

    return {
        "passed": True,
        "size_bytes": size,
        "duration_seconds": round(
            duration,
            2
        ),
        "width": 1080,
        "height": 1920,
        "video_codec": video.get(
            "codec_name"
        ),
        "audio_codec": audio.get(
            "codec_name"
        )
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("RIFT VALLEY WATCH V5.1")
    print("STABLE REAL-NEWS VIDEO GENERATOR")
    print("=" * 70)

    ensure_directories()

    # --------------------------------------------------------
    # Check required files
    # --------------------------------------------------------

    if not STORY_FILE.exists():

        raise FileNotFoundError(
            f"Missing {STORY_FILE}"
        )

    if not SCRIPT_FILE.exists():

        raise FileNotFoundError(
            f"Missing {SCRIPT_FILE}"
        )

    story = load_json(
        STORY_FILE
    )

    script = load_json(
        SCRIPT_FILE
    )

    print("\nTITLE:")
    print(
        clean_text(
            story.get(
                "title",
                ""
            )
        )
    )

    print("\nCOUNTY:")
    print(
        clean_text(
            story.get(
                "county",
                ""
            )
        )
    )

    print("\nSOURCE:")
    print(
        clean_text(
            story.get(
                "source",
                {}
            ).get(
                "name",
                ""
            )
        )
    )

    # --------------------------------------------------------
    # Source image
    # --------------------------------------------------------

    print("\n[1/7] Finding official source visual...")

    source_image = get_source_image(
        story
    )

    # --------------------------------------------------------
    # Narration
    # --------------------------------------------------------

    print("\n[2/7] Building narration...")

    segments = narration_segments(
        story
    )

    # --------------------------------------------------------
    # Scenes
    # --------------------------------------------------------

    print("\n[3/7] Creating scenes...")

    scene_files = []
    visual_report = []

    for index, (
        scene_name,
        narration
    ) in enumerate(
        segments
    ):

        print("\n" + "-" * 60)

        print(
            f"SCENE {index + 1}/{len(segments)}"
        )

        print(
            scene_name
        )

        scene_dir = (
            WORK_DIR /
            f"scene_{index + 1:02d}"
        )

        scene_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        image_path = (
            scene_dir /
            "scene.jpg"
        )

        audio_path = (
            scene_dir /
            "voice.mp3"
        )

        subtitle_path = (
            scene_dir /
            "captions.srt"
        )

        video_path = (
            scene_dir /
            "scene.mp4"
        )

        # ----------------------------------------------------
        # Build scene image
        # ----------------------------------------------------

        if (
            scene_name == "OFFICIAL STATEMENT"
        ):

            image = scene_statement(
                story
            )

        elif (
            scene_name == "SOURCE"
        ):

            image = scene_source(
                story
            )

        elif (
            scene_name == "OUTRO"
        ):

            image = scene_outro(
                story
            )

        elif (
            scene_name == "THE LATEST"
            and
            source_image is not None
        ):

            image = scene_photo(
                story,
                source_image
            )

        elif scene_name == "THE LATEST":

            image = scene_latest(
                story
            )

        elif scene_name == "WHERE IT IS":

            image = scene_location(
                story
            )

        elif scene_name == "KEY FACTS":

            image = scene_facts(
                story
            )

        elif scene_name == "THE ROUTE":

            image = scene_route(
                story
            )

        elif scene_name == "WHY IT MATTERS":

            image = scene_impact(
                story
            )

        else:

            image = scene_latest(
                story
            )

        image.save(
            image_path,
            "JPEG",
            quality=94
        )

        # ----------------------------------------------------
        # Voice
        # ----------------------------------------------------

        print(
            "Generating voice..."
        )

        create_voice(
            narration,
            audio_path
        )

        duration = get_duration(
            audio_path
        )

        print(
            f"Voice duration: "
            f"{duration:.2f}s"
        )

        # ----------------------------------------------------
        # Timed captions
        # ----------------------------------------------------

        create_srt(
            narration,
            duration,
            subtitle_path
        )

        # ----------------------------------------------------
        # Scene video
        # ----------------------------------------------------

        print(
            "Rendering scene..."
        )

        motion = (
            scene_name == "THE LATEST"
            and
            source_image is not None
        )

        create_scene_video(
            image_path,
            audio_path,
            subtitle_path,
            video_path,
            motion=motion
        )

        scene_files.append(
            video_path
        )

        visual_report.append(
            {
                "scene": scene_name,
                "duration_seconds": round(
                    duration,
                    2
                ),
                "source_photo_used": (
                    scene_name ==
                    "THE LATEST"
                    and
                    source_image is not None
                ),
                "image": str(
                    image_path
                ),
                "captions": str(
                    subtitle_path
                ),
                "video": str(
                    video_path
                )
            }
        )

    # --------------------------------------------------------
    # Concatenate
    # --------------------------------------------------------

    print("\n[5/7] Combining scenes...")

    concatenate(
        scene_files
    )

    # --------------------------------------------------------
    # Visual report
    # --------------------------------------------------------

    print("\n[6/7] Writing visual report...")

    report = {
        "version": "V5.1",
        "generator": (
            "Rift Valley Watch "
            "V5.1"
        ),
        "story_title": clean_text(
            story.get(
                "title",
                ""
            )
        ),
        "source_image_found": (
            source_image is not None
        ),
        "source_image": (
            str(source_image)
            if source_image
            else None
        ),
        "scene_count": len(
            scene_files
        ),
        "scenes": visual_report,
        "output": str(
            OUTPUT_FILE
        )
    }

    save_json(
        REPORT_FILE,
        report
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    print("\n[7/7] Running final QC...")

    qc = final_qc()

    report["qc"] = qc

    save_json(
        REPORT_FILE,
        report
    )

    print("\n")
    print("=" * 70)
    print("RIFT VALLEY WATCH V5.1 COMPLETE")
    print("=" * 70)
    print(
        f"MP4: {OUTPUT_FILE}"
    )
    print(
        f"REPORT: {REPORT_FILE}"
    )
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print("\n")
        print("=" * 70)
        print("VIDEO GENERATION FAILED")
        print("=" * 70)

        print(
            f"\nError: {exc}"
        )

        sys.exit(1)
