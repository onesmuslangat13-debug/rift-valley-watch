import json
import sys
import shutil
import subprocess
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


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


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(clean_text(item) for item in value)

    if isinstance(value, dict):
        return " ".join(
            f"{clean_text(key)} {clean_text(item)}"
            for key, item in value.items()
        )

    text = str(value)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def run_command(command, check=True):
    print("RUNNING:")
    print(" ".join(str(item) for item in command))

    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    print(result.stdout)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is not installed.")

    if shutil.which("ffprobe") is None:
        raise RuntimeError("FFprobe is not installed.")


def prepare_output():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (ASSET_DIR / "music").mkdir(
        parents=True,
        exist_ok=True
    )

    for folder in [SCENE_DIR, AUDIO_DIR]:
        for item in folder.iterdir():
            if item.is_file():
                item.unlink()


# ---------------------------------------------------------
# STORY HELPERS
# ---------------------------------------------------------

def fact_value(story, key, default=""):
    facts = story.get("verified_facts", {})

    if isinstance(facts, dict):
        return clean_text(facts.get(key, default))

    if isinstance(facts, list):
        for fact in facts:
            if not isinstance(fact, dict):
                continue

            fact_key = clean_text(
                fact.get("key")
                or fact.get("label")
                or fact.get("name")
            )

            if fact_key.upper() == key.upper():
                return clean_text(
                    fact.get("value")
                    or fact.get("text")
                    or default
                )

    return clean_text(default)


def story_title(story):
    return clean_text(
        story.get("title")
        or story.get("headline")
        or "Rift Valley Watch"
    )


def story_county(story):
    return clean_text(
        story.get("county")
        or fact_value(story, "COUNTY", "Bomet County")
    )


def story_location(story):
    return clean_text(
        fact_value(
            story,
            "LOCATION",
            story.get("location", story_county(story))
        )
    )


def story_route(story):
    return clean_text(
        fact_value(
            story,
            "PROJECT",
            story.get("project", "")
        )
    )


def story_length(story):
    return clean_text(
        fact_value(
            story,
            "ROAD_LENGTH",
            story.get("road_length", "")
        )
    )


def story_cost(story):
    return clean_text(
        fact_value(
            story,
            "COST",
            story.get("cost", "")
        )
    )


def story_status(story):
    return clean_text(
        fact_value(
            story,
            "STATUS",
            story.get("status", "")
        )
    )


def story_impact(story):
    return clean_text(
        fact_value(
            story,
            "IMPACT",
            story.get("impact", "")
        )
    )


def source_name(story):
    source = story.get("source")

    if isinstance(source, dict):
        return clean_text(
            source.get("name")
            or source.get("title")
            or "Official source"
        )

    return clean_text(source or "Official source")


def source_url(story):
    source = story.get("source")

    if isinstance(source, dict):
        return clean_text(
            source.get("url")
            or source.get("link")
            or ""
        )

    return clean_text(
        story.get("source_url")
        or story.get("url")
        or ""
    )


def story_date(story):
    value = clean_text(
        story.get("date")
        or story.get("published")
        or story.get("published_date")
        or ""
    )

    if not value:
        return datetime.now().strftime("%d %B %Y")

    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%d %B %Y")
    except ValueError:
        return value


def official_statement(story):
    statement = story.get("official_statement")

    if isinstance(statement, dict):
        speaker = clean_text(
            statement.get("speaker")
            or statement.get("name")
            or "Official statement"
        )

        quote = clean_text(
            statement.get("quote")
            or statement.get("text")
            or ""
        )

        return speaker, quote

    if isinstance(statement, str):
        return "Official statement", clean_text(statement)

    return "", ""


# ---------------------------------------------------------
# DUPLICATE PROTECTION
# ---------------------------------------------------------

def normalize_sentence(text):
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return text


def remove_duplicate_sentences(text):
    sentences = re.split(r"(?<=[.!?])\s+", clean_text(text))
    result = []
    seen = set()

    for sentence in sentences:
        normalized = normalize_sentence(sentence)

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(sentence.strip())

    return " ".join(result)


def clean_impact(text):
    text = remove_duplicate_sentences(text)

    text = re.sub(
        r"\bthe area and wider bomet county\b",
        "the area and Bomet County",
        text,
        flags=re.I,
    )

    return text.strip()


# ---------------------------------------------------------
# FONTS AND TEXT
# ---------------------------------------------------------

def get_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ])

    candidates.extend([
        str(ROOT / "fonts" / "DejaVuSans-Bold.ttf"),
        str(ROOT / "fonts" / "DejaVuSans.ttf"),
    ])

    for candidate in candidates:
        path = Path(candidate)

        if path.exists():
            return ImageFont.truetype(str(path), size=size)

    return ImageFont.load_default()


def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def text_height(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"

        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def fit_text(draw, text, max_width, max_height, start_size=64, min_size=24):
    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, bold=True)
        lines = wrap_text(draw, text, font, max_width)
        line_height = int(size * 1.25)
        total_height = line_height * len(lines)

        if total_height <= max_height:
            return font, lines, line_height

    font = get_font(min_size, bold=True)
    lines = wrap_text(draw, text, font, max_width)
    line_height = int(min_size * 1.25)

    return font, lines, line_height


def draw_lines(
    draw,
    lines,
    x,
    y,
    font,
    fill,
    line_height,
    anchor="la",
):
    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            anchor=anchor,
        )
        current_y += line_height


def draw_fitted_text(
    draw,
    text,
    box,
    start_size=64,
    min_size=24,
    fill="white",
    bold=True,
    align="left",
):
    x1, y1, x2, y2 = box
    max_width = x2 - x1
    max_height = y2 - y1

    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, bold=bold)
        lines = wrap_text(draw, text, font, max_width)
        line_height = int(size * 1.25)

        if line_height * len(lines) <= max_height:
            break
    else:
        font = get_font(min_size, bold=bold)
        lines = wrap_text(draw, text, font, max_width)
        line_height = int(min_size * 1.25)

    current_y = y1

    for line in lines:
        if align == "center":
            draw.text(
                ((x1 + x2) // 2, current_y),
                line,
                font=font,
                fill=fill,
                anchor="ma",
            )
        elif align == "right":
            draw.text(
                (x2, current_y),
                line,
                font=font,
                fill=fill,
                anchor="ra",
            )
        else:
            draw.text(
                (x1, current_y),
                line,
                font=font,
                fill=fill,
                anchor="la",
            )

        current_y += line_height


# ---------------------------------------------------------
# VISUAL DESIGN
# ---------------------------------------------------------

def make_background(index=0):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 17, 30),
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        red = int(9 + ratio * 10)
        green = int(17 + ratio * 15)
        blue = int(30 + ratio * 25)

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(red, green, blue),
        )

    # Broadcast-style diagonal panels
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    overlay_draw.polygon(
        [
            (0, 0),
            (WIDTH, 0),
            (WIDTH, 420),
            (0, 760),
        ],
        fill=(18, 45, 72, 120),
    )

    overlay_draw.polygon(
        [
            (WIDTH, 1150),
            (WIDTH, HEIGHT),
            (0, HEIGHT),
            (0, 1680),
        ],
        fill=(4, 8, 16, 160),
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")

    return image


def draw_header(draw, section, page_number):
    draw.rectangle(
        [0, 0, WIDTH, 118],
        fill=(5, 12, 23),
    )

    draw.rectangle(
        [0, 112, WIDTH, 120],
        fill=(214, 40, 40),
    )

    draw.text(
        (60, 48),
        "RIFT VALLEY WATCH",
        font=get_font(35, bold=True),
        fill="white",
        anchor="lm",
    )

    draw.text(
        (WIDTH - 60, 48),
        f"{page_number:02d}",
        font=get_font(30, bold=True),
        fill=(220, 226, 235),
        anchor="rm",
    )

    draw.text(
        (60, 170),
        section.upper(),
        font=get_font(25, bold=True),
        fill=(244, 78, 78),
        anchor="la",
    )


def draw_footer(draw, source=None):
    draw.rectangle(
        [0, HEIGHT - 116, WIDTH, HEIGHT],
        fill=(4, 9, 17),
    )

    draw.rectangle(
        [0, HEIGHT - 122, WIDTH, HEIGHT - 116],
        fill=(214, 40, 40),
    )

    footer = (
        "RIFT VALLEY WATCH  |  TRACKING VERIFIED DEVELOPMENTS"
        if not source
        else f"SOURCE: {source}"
    )

    draw.text(
        (60, HEIGHT - 58),
        footer,
        font=get_font(22, bold=True),
        fill=(220, 226, 235),
        anchor="lm",
    )


def draw_section_title(draw, title, subtitle=""):
    draw.text(
        (60, 280),
        title,
        font=get_font(66, bold=True),
        fill="white",
        anchor="la",
    )

    if subtitle:
        draw_fitted_text(
            draw,
            subtitle,
            (60, 390, WIDTH - 60, 590),
            start_size=38,
            min_size=24,
            fill=(188, 202, 220),
            bold=False,
        )


# ---------------------------------------------------------
# SOURCE IMAGE HANDLING
# ---------------------------------------------------------

def bad_image_url(url):
    if not url:
        return True

    lowered = url.lower()

    blocked = [
        "data:image",
        "facebook.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "youtube.com",
        "logo",
        "icon",
        "avatar",
        "sprite",
    ]

    return any(item in lowered for item in blocked)


def extract_image_candidates(url):
    if not url:
        return []

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            html = response.read().decode(
                "utf-8",
                errors="ignore",
            )

    except Exception as error:
        print(f"Source image extraction skipped: {error}")
        return []

    candidates = []

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<img[^>]+src=["\']([^"\']+)',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html,
            flags=re.I,
        )

        for match in matches:
            absolute = urllib.parse.urljoin(url, match)

            if absolute not in candidates:
                candidates.append(absolute)

    return candidates


def download_source_image(story):
    url = source_url(story)

    if not url:
        return None

    candidates = extract_image_candidates(url)

    for image_url in candidates:
        if bad_image_url(image_url):
            continue

        try:
            request = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": "Mozilla/5.0"
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:
                data = response.read()

            output_path = SOURCE_IMAGE_DIR / "source_image.jpg"

            with output_path.open("wb") as file:
                file.write(data)

            image = Image.open(output_path).convert("RGB")

            if image.width < 300 or image.height < 200:
                output_path.unlink(missing_ok=True)
                continue

            print(f"Downloaded source image: {image_url}")
            return output_path

        except Exception as error:
            print(f"Could not download image {image_url}: {error}")

    return None


def photo_background(source_image):
    if not source_image or not source_image.exists():
        return None

    try:
        image = Image.open(source_image).convert("RGB")
        image.thumbnail((WIDTH, HEIGHT))

        canvas = Image.new(
            "RGB",
            (WIDTH, HEIGHT),
            (8, 14, 24),
        )

        x = (WIDTH - image.width) // 2
        y = (HEIGHT - image.height) // 2

        canvas.paste(image, (x, y))

        dark_overlay = Image.new(
            "RGBA",
            (WIDTH, HEIGHT),
            (0, 0, 0, 125),
        )

        canvas = Image.alpha_composite(
            canvas.convert("RGBA"),
            dark_overlay,
        ).convert("RGB")

        return canvas

    except Exception as error:
        print(f"Photo background skipped: {error}")
        return None


# ---------------------------------------------------------
# SCENES
# ---------------------------------------------------------

def scene_latest(story, source_image=None):
    image = photo_background(source_image)

    if image is None:
        image = make_background(1)

    draw = ImageDraw.Draw(image)

    draw_header(draw, "Latest development", 1)

    draw.text(
        (60, 280),
        "BREAKING",
        font=get_font(34, bold=True),
        fill=(244, 78, 78),
        anchor="la",
    )

    draw_fitted_text(
        draw,
        story_title(story),
        (60, 370, WIDTH - 60, 870),
        start_size=76,
        min_size=38,
        fill="white",
        bold=True,
    )

    draw.text(
        (60, 1000),
        story_county(story).upper(),
        font=get_font(32, bold=True),
        fill=(245, 190, 65),
        anchor="la",
    )

    draw_fitted_text(
        draw,
        "A major road construction project is underway, with the development expected to improve movement and unlock economic activity.",
        (60, 1100, WIDTH - 60, 1430),
        start_size=38,
        min_size=25,
        fill=(220, 228, 238),
        bold=False,
    )

    draw_footer(draw)
    return image


def scene_location(story):
    image = make_background(2)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Location", 2)
    draw_section_title(
        draw,
        "WHERE IT IS HAPPENING",
        story_location(story),
    )

    draw.rounded_rectangle(
        [60, 720, WIDTH - 60, 1180],
        radius=30,
        fill=(17, 34, 53),
        outline=(62, 101, 137),
        width=4,
    )

    draw.text(
        (WIDTH // 2, 850),
        "BOMET COUNTY",
        font=get_font(64, bold=True),
        fill=(245, 190, 65),
        anchor="ma",
    )

    draw.text(
        (WIDTH // 2, 980),
        "CHEPALUNGU CONSTITUENCY",
        font=get_font(38, bold=True),
        fill="white",
        anchor="ma",
    )

    draw_fitted_text(
        draw,
        "The project is located in Chepalungu Constituency, Bomet County.",
        (80, 1300, WIDTH - 80, 1530),
        start_size=40,
        min_size=26,
        fill=(220, 228, 238),
        bold=False,
        align="center",
    )

    draw_footer(draw)
    return image


def scene_facts(story):
    image = make_background(3)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Key facts", 3)
    draw_section_title(draw, "THE NUMBERS", "Verified project details")

    cards = [
        ("ROAD LENGTH", story_length(story)),
        ("PROJECT COST", story_cost(story)),
        ("STATUS", story_status(story)),
    ]

    y = 690

    for label, value in cards:
        draw.rounded_rectangle(
            [60, y, WIDTH - 60, y + 270],
            radius=26,
            fill=(17, 34, 53),
            outline=(55, 91, 124),
            width=3,
        )

        draw.text(
            (100, y + 52),
            label,
            font=get_font(26, bold=True),
            fill=(245, 190, 65),
            anchor="la",
        )

        draw_fitted_text(
            draw,
            value,
            (100, y + 105, WIDTH - 100, y + 235),
            start_size=48,
            min_size=25,
            fill="white",
            bold=True,
        )

        y += 315

    draw_footer(draw)
    return image


def split_route(route):
    route = clean_text(route)

    if not route:
        return []

    parts = re.split(
        r"\s*/\s*|\s*-\s*|\s+to\s+",
        route,
        flags=re.I,
    )

    nodes = []

    for part in parts:
        part = clean_text(part)

        if not part:
            continue

        if part not in nodes:
            nodes.append(part)

    nodes = nodes[:8]

    # Remove trailing "road" from route labels.
    nodes = [
        re.sub(
            r"\s+road$",
            "",
            node,
            flags=re.I,
        ).strip()
        for node in nodes
    ]

    return nodes


def draw_route_line(draw, nodes, y, font_size=30):
    if not nodes:
        return

    left = 100
    right = WIDTH - 100
    width = right - left

    if len(nodes) == 1:
        positions = [WIDTH // 2]
    else:
        spacing = width / (len(nodes) - 1)
        positions = [
            int(left + spacing * index)
            for index in range(len(nodes))
        ]

    line_y = y + 40

    draw.line(
        [
            (positions[0], line_y),
            (positions[-1], line_y),
        ],
        fill=(214, 40, 40),
        width=8,
    )

    for index, position in enumerate(positions):
        draw.ellipse(
            [
                position - 17,
                line_y - 17,
                position + 17,
                line_y + 17,
            ],
            fill=(245, 190, 65),
            outline="white",
            width=3,
        )

        label_font = get_font(font_size, bold=True)

        label_lines = wrap_text(
            draw,
            nodes[index],
            label_font,
            180,
        )

        current_y = line_y + 65

        for line in label_lines:
            draw.text(
                (position, current_y),
                line,
                font=label_font,
                fill="white",
                anchor="ma",
            )
            current_y += font_size + 8


def scene_route(story):
    image = make_background(4)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Corridor visual", 4)

    draw.text(
        (60, 280),
        "THE ROAD CORRIDOR",
        font=get_font(62, bold=True),
        fill="white",
        anchor="la",
    )

    draw_fitted_text(
        draw,
        "A connected road corridor linking key locations across the project area.",
        (60, 390, WIDTH - 60, 610),
        start_size=38,
        min_size=25,
        fill=(188, 202, 220),
        bold=False,
    )

    nodes = split_route(story_route(story))

    draw_route_line(
        draw,
        nodes,
        850,
        font_size=29,
    )

    draw.rounded_rectangle(
        [60, 1370, WIDTH - 60, 1580],
        radius=24,
        fill=(17, 34, 53),
        outline=(55, 91, 124),
        width=3,
    )

    draw.text(
        (WIDTH // 2, 1435),
        story_length(story) or "Road project",
        font=get_font(58, bold=True),
        fill=(245, 190, 65),
        anchor="ma",
    )

    draw.text(
        (WIDTH // 2, 1515),
        "ROAD CONSTRUCTION CORRIDOR",
        font=get_font(25, bold=True),
        fill="white",
        anchor="ma",
    )

    draw_footer(draw)
    return image


def scene_impact(story):
    image = make_background(5)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Why it matters", 5)

    draw.text(
        (60, 280),
        "WHY IT MATTERS",
        font=get_font(68, bold=True),
        fill="white",
        anchor="la",
    )

    impact = clean_impact(
        story_impact(story)
        or "The project is expected to improve connectivity and unlock economic potential."
    )

    draw.rounded_rectangle(
        [60, 500, WIDTH - 60, 1300],
        radius=34,
        fill=(17, 34, 53),
        outline=(55, 91, 124),
        width=4,
    )

    draw.text(
        (WIDTH // 2, 650),
        "EXPECTED IMPACT",
        font=get_font(34, bold=True),
        fill=(245, 190, 65),
        anchor="ma",
    )

    draw_fitted_text(
        draw,
        impact,
        (110, 790, WIDTH - 110, 1170),
        start_size=48,
        min_size=28,
        fill="white",
        bold=True,
        align="center",
    )

    draw_footer(draw)
    return image


def scene_statement(story):
    image = make_background(6)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Official statement", 6)

    speaker, quote = official_statement(story)

    if not quote:
        quote = (
            "The Roads and Transport Ministry has been instructed "
            "to closely monitor road construction to ensure speedy "
            "completion and quality works."
        )

    if not speaker:
        speaker = "Deputy President Kithure Kindiki"

    draw.text(
        (60, 280),
        "OFFICIAL STATEMENT",
        font=get_font(62, bold=True),
        fill="white",
        anchor="la",
    )

    draw.rounded_rectangle(
        [60, 500, WIDTH - 60, 1350],
        radius=34,
        fill=(17, 34, 53),
        outline=(55, 91, 124),
        width=4,
    )

    draw.text(
        (110, 620),
        "“",
        font=get_font(130, bold=True),
        fill=(244, 78, 78),
        anchor="la",
    )

    draw_fitted_text(
        draw,
        quote,
        (120, 770, WIDTH - 120, 1120),
        start_size=43,
        min_size=26,
        fill="white",
        bold=True,
    )

    draw.text(
        (120, 1210),
        speaker,
        font=get_font(30, bold=True),
        fill=(245, 190, 65),
        anchor="la",
    )

    draw.text(
        (120, 1260),
        "Office of the Deputy President",
        font=get_font(24, bold=False),
        fill=(188, 202, 220),
        anchor="la",
    )

    draw_footer(draw)
    return image


def scene_source(story):
    image = make_background(7)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Source", 7)

    draw.text(
        (60, 280),
        "SOURCE & VERIFICATION",
        font=get_font(60, bold=True),
        fill="white",
        anchor="la",
    )

    draw.rounded_rectangle(
        [60, 560, WIDTH - 60, 1150],
        radius=30,
        fill=(17, 34, 53),
        outline=(55, 91, 124),
        width=4,
    )

    draw.text(
        (100, 690),
        "OFFICIAL SOURCE",
        font=get_font(28, bold=True),
        fill=(245, 190, 65),
        anchor="la",
    )

    draw_fitted_text(
        draw,
        source_name(story),
        (100, 780, WIDTH - 100, 930),
        start_size=50,
        min_size=28,
        fill="white",
        bold=True,
    )

    draw.text(
        (100, 1010),
        story_date(story),
        font=get_font(30, bold=True),
        fill=(188, 202, 220),
        anchor="la",
    )

    draw_fitted_text(
        draw,
        "This report uses verified project details and official statements.",
        (60, 1300, WIDTH - 60, 1500),
        start_size=36,
        min_size=25,
        fill=(220, 228, 238),
        bold=False,
        align="center",
    )

    draw_footer(draw, source_name(story))
    return image


def scene_outro(story):
    image = make_background(8)
    draw = ImageDraw.Draw(image)

    draw_header(draw, "Rift Valley Watch", 8)

    draw.text(
        (WIDTH // 2, 610),
        "RIFT VALLEY",
        font=get_font(82, bold=True),
        fill="white",
        anchor="ma",
    )

    draw.text(
        (WIDTH // 2, 735),
        "WATCH",
        font=get_font(112, bold=True),
        fill=(244, 78, 78),
        anchor="ma",
    )

    draw.line(
        [(180, 850), (WIDTH - 180, 850)],
        fill=(245, 190, 65),
        width=6,
    )

    draw_fitted_text(
        draw,
        "Tracking verified developments across the region.",
        (100, 980, WIDTH - 100, 1260),
        start_size=46,
        min_size=28,
        fill=(220, 228, 238),
        bold=False,
        align="center",
    )

    draw.text(
        (WIDTH // 2, 1450),
        story_county(story).upper(),
        font=get_font(35, bold=True),
        fill=(245, 190, 65),
        anchor="ma",
    )

    draw_footer(draw)
    return image


def build_scene_plan(story, source_image=None):
    return [
        ("latest", scene_latest(story, source_image)),
        ("location", scene_location(story)),
        ("facts", scene_facts(story)),
        ("route", scene_route(story)),
        ("impact", scene_impact(story)),
        ("statement", scene_statement(story)),
        ("source", scene_source(story)),
        ("outro", scene_outro(story)),
    ]


# ---------------------------------------------------------
# AUDIO
# ---------------------------------------------------------

def create_audio(text, output_path):
    text = clean_text(text)

    if not text:
        text = "Rift Valley Watch. Tracking verified developments across the region."

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(str(output_path))


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
            str(path),
        ],
        check=True,
    )

    try:
        return float(result.stdout.strip())
    except ValueError:
        return 5.0


# ---------------------------------------------------------
# VIDEO RENDERING
# ---------------------------------------------------------

def render_scene(image, narration, output_path):
    image_path = output_path.with_suffix(".png")
    image.save(image_path)

    duration = max(4.0, audio_duration(narration))

    if MUSIC_FILE.exists():
        command = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(narration),
            "-stream_loop",
            "-1",
            "-i",
            str(MUSIC_FILE),
            "-filter_complex",
            (
                "[1:a]volume=1.0[narration];"
                "[2:a]volume=0.10[music];"
                "[narration][music]"
                "amix=inputs=2:duration=first:dropout_transition=2"
                "[mixed]"
            ),
            "-map",
            "0:v:0",
            "-map",
            "[mixed]",
            "-t",
            f"{duration:.2f}",
            "-r",
            str(FPS),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        command = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(narration),
            "-t",
            f"{duration:.2f}",
            "-r",
            str(FPS),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},format=yuv420p",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    run_command(command)

    image_path.unlink(missing_ok=True)

    if not output_path.exists():
        raise RuntimeError(
            f"Scene was not created: {output_path}"
        )


def concatenate_scenes(scene_paths):
    concat_file = OUTPUT_DIR / "concat.txt"

    with concat_file.open("w", encoding="utf-8") as file:
        for scene_path in scene_paths:
            file.write(
                f"file '{scene_path.resolve()}'\n"
            )

    run_command(
        [
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
            str(OUTPUT_FILE),
        ]
    )

    concat_file.unlink(missing_ok=True)


# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

def validate_mp4():
    if not OUTPUT_FILE.exists():
        raise RuntimeError("Final MP4 does not exist.")

    size = OUTPUT_FILE.stat().st_size

    if size < 10_000:
        raise RuntimeError("Final MP4 is unexpectedly small.")

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(OUTPUT_FILE),
        ]
    )

    data = json.loads(result.stdout)

    duration = float(
        data.get("format", {}).get("duration", 0)
    )

    streams = data.get("streams", [])

    has_video = any(
        stream.get("codec_type") == "video"
        for stream in streams
    )

    has_audio = any(
        stream.get("codec_type") == "audio"
        for stream in streams
    )

    if duration <= 1:
        raise RuntimeError("Final MP4 duration is invalid.")

    if not has_video:
        raise RuntimeError("Final MP4 has no video stream.")

    if not has_audio:
        raise RuntimeError("Final MP4 has no audio stream.")

    print("MP4 VALIDATION PASSED")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Size: {size} bytes")
    print(f"Video stream: {has_video}")
    print(f"Audio stream: {has_audio}")

    return {
        "duration_seconds": round(duration, 2),
        "size_bytes": size,
        "has_video": has_video,
        "has_audio": has_audio,
    }


def write_report(validation, story):
    report = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "output_file": str(OUTPUT_FILE),
        "music_used": MUSIC_FILE.exists(),
        "story_title": story_title(story),
        "source": source_name(story),
        "validation": validation,
    }

    with REPORT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ---------------------------------------------------------
# NARRATION
# ---------------------------------------------------------

def build_narrations(story):
    title = story_title(story)
    county = story_county(story)
    location = story_location(story)
    length = story_length(story)
    cost = story_cost(story)
    status = story_status(story)
    route = story_route(story)
    impact = clean_impact(story_impact(story))
    speaker, quote = official_statement(story)

    if not speaker:
        speaker = "Deputy President Kithure Kindiki"

    if not quote:
        quote = (
            "The Roads and Transport Ministry has been instructed "
            "to closely monitor road construction to ensure speedy "
            "completion and quality works."
        )

    return [
        (
            f"Breaking news from {county}. {title}. "
            f"The project is expected to improve connectivity "
            f"and economic activity in the region."
        ),
        (
            f"The project is located in {location}. "
            f"It forms part of a wider road corridor in Bomet County."
        ),
        (
            f"The project covers {length} at a cost of {cost}. "
            f"The current status is {status}."
        ),
        (
            f"The corridor links {route}. "
            f"The route is expected to improve movement between communities."
        ),
        (
            f"Why it matters. {impact}."
        ),
        (
            f"{speaker} said, {quote}"
        ),
        (
            f"The report is based on information from {source_name(story)} "
            f"dated {story_date(story)}."
        ),
        (
            "This is Rift Valley Watch, tracking verified developments "
            "across the region."
        ),
    ]


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    print("=" * 60)
    print("STARTING RIFT VALLEY WATCH VIDEO GENERATOR")
    print("=" * 60)

    check_ffmpeg()
    prepare_output()

    print("[1/6] Loading story...")
    story = load_json(STORY_FILE)

    print(f"Title: {story_title(story)}")
    print(f"Source: {source_name(story)}")

    print("[2/6] Downloading official source image...")
    source_image = download_source_image(story)

    if source_image:
        print(f"Source image ready: {source_image}")
    else:
        print("No source image downloaded. Using broadcast graphics.")

    print("[3/6] Building scene plan...")
    scene_plan = build_scene_plan(
        story,
        source_image,
    )

    print(f"Scenes created: {len(scene_plan)}")

    print("[4/6] Creating narration...")
    narrations = build_narrations(story)

    if len(narrations) != len(scene_plan):
        raise RuntimeError(
            "Narration count does not match scene count."
        )

    print("[5/6] Rendering scenes...")
    scene_paths = []

    for index, ((scene_name, image), narration) in enumerate(
        zip(scene_plan, narrations),
        start=1,
    ):
        audio_path = AUDIO_DIR / f"scene_{index:02d}.mp3"
        scene_path = SCENE_DIR / f"scene_{index:02d}.mp4"

        print(
            f"Rendering scene {index}/{len(scene_plan)}: "
            f"{scene_name}"
        )

        create_audio(
            narration,
            audio_path,
        )

        render_scene(
            image,
            audio_path,
            scene_path,
        )

        scene_paths.append(scene_path)

    print("[6/6] Concatenating scenes...")
    concatenate_scenes(scene_paths)

    print("Validating final MP4...")
    validation = validate_mp4()

    write_report(
        validation,
        story,
    )

    print("=" * 60)
    print("VIDEO GENERATION SUCCESSFUL")
    print(f"MP4: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")
    print(f"Music used: {MUSIC_FILE.exists()}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print()
        print("=" * 60)
        print("VIDEO GENERATOR FAILED")
        print("=" * 60)
        print(str(error))
        print("=" * 60)
        sys.exit(1)
