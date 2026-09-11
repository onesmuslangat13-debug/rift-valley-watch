import os
import re
import json
import html
import shutil
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
ASSET_DIR = ROOT / "assets"
SOURCE_IMAGE_DIR = ASSET_DIR / "source"
AUDIO_DIR = ASSET_DIR / "audio"
SCENE_DIR = OUTPUT_DIR / "scenes"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("Road lenght", "Road length")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def safe_filename(value):
    value = clean_text(value)
    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value
    )

    return value.strip("_") or "file"


def run_command(command, cwd=None):
    command = [str(x) for x in command]

    print("$", " ".join(command))

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code "
            f"{result.returncode}"
        )

    return result.stdout


def ensure_directories():
    directories = [
        OUTPUT_DIR,
        ASSET_DIR,
        SOURCE_IMAGE_DIR,
        AUDIO_DIR,
        SCENE_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True
        )


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Missing required file: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


# ============================================================
# STORY HELPERS
# ============================================================

def fact_value(story, label, default=""):
    facts = story.get(
        "verified_facts",
        []
    )

    for item in facts:
        item_label = str(
            item.get("label", "")
        ).upper()

        if item_label == label.upper():
            return clean_text(
                item.get(
                    "value",
                    default
                )
            )

    return clean_text(default)


def story_title(story):
    return clean_text(
        story.get(
            "title",
            "Rift Valley Watch"
        )
    )


def story_category(story):
    return clean_text(
        story.get(
            "category",
            "NEWS"
        )
    ).upper()


def story_county(story):
    return clean_text(
        story.get(
            "county",
            "Rift Valley"
        )
    )


def story_location(story):
    return fact_value(
        story,
        "LOCATION",
        story_county(story)
    )


def story_cost(story):
    return fact_value(
        story,
        "COST",
        "Not stated"
    )


def story_length(story):
    return fact_value(
        story,
        "ROAD_LENGTH",
        ""
    )


def story_status(story):
    return fact_value(
        story,
        "STATUS",
        "Reported"
    )


def story_route(story):
    return fact_value(
        story,
        "PROJECT",
        ""
    )


def story_impact(story):
    return fact_value(
        story,
        "IMPACT",
        ""
    )


def source_name(story):
    source = story.get(
        "source",
        {}
    )

    return clean_text(
        source.get(
            "name",
            "Source"
        )
    )


def source_url(story):
    source = story.get(
        "source",
        {}
    )

    return clean_text(
        source.get(
            "url",
            ""
        )
    )


def story_date(story):
    return clean_text(
        story.get(
            "date",
            ""
        )
    )


def official_statement(story):
    statement = story.get(
        "official_statement",
        {}
    )

    if not statement.get(
        "available",
        False
    ):
        return "", ""

    return (
        clean_text(
            statement.get(
                "speaker",
                ""
            )
        ),
        clean_text(
            statement.get(
                "quote",
                ""
            )
        )
    )


def get_script_text(story):
    if SCRIPT_FILE.exists():
        data = load_json(
            SCRIPT_FILE
        )

        text = clean_text(
            data.get(
                "full_script",
                ""
            )
        )

        if text:
            return text

    return clean_text(
        story.get(
            "summary",
            ""
        )
    )


# ============================================================
# FONTS
# ============================================================

def font_candidates(bold=False):
    if bold:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]
    else:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    return names


def get_font(size, bold=False):
    for name in font_candidates(bold):
        if Path(name).exists():
            return ImageFont.truetype(
                name,
                size
            )

    return ImageFont.load_default()


# ============================================================
# GRAPHICS
# ============================================================

def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 15, 29)
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(8 + 7 * ratio)
        g = int(15 + 9 * ratio)
        b = int(29 + 16 * ratio)

        draw.line(
            (0, y, WIDTH, y),
            fill=(r, g, b)
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
            fill=(24, 37, 58),
            width=1
        )

    for y in range(
        0,
        HEIGHT,
        90
    ):
        draw.line(
            (0, y, WIDTH, y),
            fill=(24, 37, 58),
            width=1
        )


def top_bar(
    draw,
    label="RIFT VALLEY WATCH"
):
    draw.rectangle(
        (0, 0, WIDTH, 118),
        fill=(6, 12, 24)
    )

    draw.rectangle(
        (0, 112, WIDTH, 118),
        fill=(190, 35, 45)
    )

    draw.text(
        (55, 36),
        clean_text(label),
        font=get_font(40, True),
        fill=(245, 245, 245)
    )


def section_label(
    draw,
    text,
    y=175
):
    draw.text(
        (55, y),
        clean_text(text).upper(),
        font=get_font(30, True),
        fill=(230, 55, 65)
    )


def footer(draw, story):
    county = story_county(story)
    date = story_date(story)

    if date:
        text = f"{county}  |  {date}"
    else:
        text = county

    draw.text(
        (55, HEIGHT - 100),
        text,
        font=get_font(25),
        fill=(175, 185, 200)
    )


def source_badge(draw, story):
    text = source_name(story)

    draw.rounded_rectangle(
        (
            55,
            HEIGHT - 175,
            WIDTH - 55,
            HEIGHT - 125
        ),
        radius=18,
        fill=(22, 34, 52)
    )

    draw.text(
        (75, HEIGHT - 163),
        f"SOURCE: {text}",
        font=get_font(23, True),
        fill=(220, 225, 235)
    )


def draw_wrapped(
    draw,
    text,
    box,
    font,
    fill=(245, 245, 245),
    line_spacing=14,
    max_lines=None
):
    x1, y1, x2, y2 = box

    words = clean_text(text).split()

    lines = []
    current = ""

    for word in words:
        trial = (
            f"{current} {word}"
            .strip()
        )

        width = draw.textbbox(
            (0, 0),
            trial,
            font=font
        )[2]

        if width <= (
            x2 - x1
        ):
            current = trial
        else:
            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(current)

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]

        if lines:
            lines[-1] = (
                lines[-1]
                .rstrip(".")
                + "..."
            )

    y = y1

    bbox = font.getbbox("Ag")

    line_height = (
        bbox[3]
        - bbox[1]
        + line_spacing
    )

    for line in lines:
        if y + line_height > y2:
            break

        draw.text(
            (x1, y),
            line,
            font=font,
            fill=fill
        )

        y += line_height

    return y


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def is_bad_image_url(url):
    value = clean_text(
        url
    ).lower()

    return (
        not value
        or value.startswith("data:")
        or "logo" in value
        or "icon" in value
        or "avatar" in value
        or value.endswith(".svg")
    )


def extract_image_candidates(url):
    candidates = []

    if not url:
        return candidates

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                "Mozilla/5.0 RiftValleyWatch/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:
            raw = response.read()

        page = raw.decode(
            "utf-8",
            errors="ignore"
        )

    except Exception as exc:
        print(
            f"Image source fetch failed: {exc}"
        )
        return candidates

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            page,
            flags=re.I
        )

        for match in matches:
            candidate = urllib.parse.urljoin(
                url,
                html.unescape(match)
            )

            if (
                not is_bad_image_url(
                    candidate
                )
                and candidate not in candidates
            ):
                candidates.append(
                    candidate
                )

    return candidates[:30]


def download_image(
    url,
    destination
):
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                "Mozilla/5.0 RiftValleyWatch/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:
            data = response.read()

        destination.write_bytes(
            data
        )

        return destination

    except Exception as exc:
        print(
            f"Image download failed: {exc}"
        )
        return None


def validate_image(path):
    if not path:
        return False

    path = Path(path)

    if not path.exists():
        return False

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        if width < 400:
            return False

        if height < 300:
            return False

        if width * height < 250000:
            return False

        return True

    except Exception:
        return False


def find_source_image(story):
    url = source_url(story)

    if not url:
        return None, []

    candidates = extract_image_candidates(
        url
    )

    print(
        f"Found {len(candidates)} "
        f"image candidates."
    )

    valid = []

    for index, candidate in enumerate(
        candidates
    ):
        lower = candidate.lower()

        extension = ".jpg"

        if ".png" in lower:
            extension = ".png"
        elif ".webp" in lower:
            extension = ".webp"
        elif ".jpeg" in lower:
            extension = ".jpeg"

        destination = (
            SOURCE_IMAGE_DIR
            / f"source_{index}{extension}"
        )

        downloaded = download_image(
            candidate,
            destination
        )

        if (
            downloaded
            and validate_image(downloaded)
        ):
            valid.append(candidate)

            print(
                f"VALID SOURCE IMAGE: "
                f"{candidate}"
            )

            return (
                downloaded,
                valid
            )

    return None, valid


# ============================================================
# PHOTO BACKGROUND
# ============================================================

def photo_background(source_path):
    image = Image.open(
        source_path
    ).convert("RGB")

    scale = max(
        WIDTH / image.width,
        HEIGHT / image.height
    )

    size = (
        int(image.width * scale),
        int(image.height * scale)
    )

    image = image.resize(
        size,
        Image.Resampling.LANCZOS
    )

    left = (
        image.width - WIDTH
    ) // 2

    top = (
        image.height - HEIGHT
    ) // 2

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    image = image.filter(
        ImageFilter.GaussianBlur(0.2)
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 75)
    )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    ).convert("RGB")


# ============================================================
# SCENES
# ============================================================

def scene_latest(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "THE LATEST"
    )

    draw_wrapped(
        draw,
        story_title(story),
        (
            55,
            290,
            WIDTH - 55,
            900
        ),
        get_font(70, True),
        max_lines=6,
        line_spacing=18
    )

    draw.text(
        (55, 1030),
        story_category(story),
        font=get_font(34, True),
        fill=(220, 220, 225)
    )

    footer(draw, story)

    return image


def scene_photo(
    story,
    source_path
):
    image = photo_background(
        source_path
    )

    draw = ImageDraw.Draw(image)

    top_bar(
        draw,
        "RIFT VALLEY WATCH | VISUAL EVIDENCE"
    )

    draw.rounded_rectangle(
        (
            45,
            HEIGHT - 500,
            WIDTH - 45,
            HEIGHT - 165
        ),
        radius=30,
        fill=(4, 10, 20)
    )

    draw.text(
        (75, HEIGHT - 455),
        "VISUAL EVIDENCE",
        font=get_font(32, True),
        fill=(235, 55, 65)
    )

    draw_wrapped(
        draw,
        story_title(story),
        (
            75,
            HEIGHT - 395,
            WIDTH - 75,
            HEIGHT - 220
        ),
        get_font(45, True),
        max_lines=3,
        line_spacing=10
    )

    footer(draw, story)

    return image


def scene_location(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "WHERE IT IS"
    )

    county = story_county(story)
    location = story_location(story)

    draw.rounded_rectangle(
        (
            55,
            300,
            WIDTH - 55,
            1050
        ),
        radius=35,
        fill=(15, 29, 48),
        outline=(55, 70, 95),
        width=3
    )

    draw.text(
        (100, 390),
        county.upper(),
        font=get_font(52, True),
        fill=(235, 55, 65)
    )

    draw_wrapped(
        draw,
        location,
        (
            100,
            510,
            WIDTH - 100,
            900
        ),
        get_font(60, True),
        max_lines=5,
        line_spacing=18
    )

    draw.text(
        (100, 1000),
        "LOCATION FROM VERIFIED STORY FACTS",
        font=get_font(26),
        fill=(170, 180, 195)
    )

    footer(draw, story)

    return image


def scene_facts(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "KEY FACTS"
    )

    cards = [
        (
            "ROAD LENGTH",
            story_length(story)
        ),
        (
            "PROJECT COST",
            story_cost(story)
        ),
        (
            "STATUS",
            story_status(story)
        ),
    ]

    y = 310

    for label, value in cards:
        draw.rounded_rectangle(
            (
                55,
                y,
                WIDTH - 55,
                y + 350
            ),
            radius=30,
            fill=(15, 29, 48),
            outline=(55, 70, 95),
            width=2
        )

        draw.text(
            (90, y + 45),
            label,
            font=get_font(27, True),
            fill=(230, 55, 65)
        )

        draw_wrapped(
            draw,
            value or "Not stated",
            (
                90,
                y + 105,
                WIDTH - 90,
                y + 300
            ),
            get_font(55, True),
            max_lines=3,
            line_spacing=12
        )

        y += 390

    footer(draw, story)

    return image


def scene_route(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "THE ROUTE"
    )

    route = (
        story_route(story)
        or "Route details not stated"
    )

    draw.rounded_rectangle(
        (
            55,
            300,
            WIDTH - 55,
            1300
        ),
        radius=35,
        fill=(15, 29, 48),
        outline=(55, 70, 95),
        width=3
    )

    draw.text(
        (95, 370),
        "PROJECT",
        font=get_font(30, True),
        fill=(230, 55, 65)
    )

    draw_wrapped(
        draw,
        route,
        (
            95,
            450,
            WIDTH - 95,
            1180
        ),
        get_font(52, True),
        max_lines=10,
        line_spacing=17
    )

    draw.text(
        (95, 1235),
        "ROUTE IDENTIFIED IN THE VERIFIED STORY",
        font=get_font(25),
        fill=(170, 180, 195)
    )

    footer(draw, story)

    return image


def scene_impact(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "WHY IT MATTERS"
    )

    impact = story_impact(story)

    if not impact:
        impact = (
            "The available verified source "
            "does not state a specific impact."
        )

    draw_wrapped(
        draw,
        impact,
        (
            65,
            330,
            WIDTH - 65,
            1250
        ),
        get_font(58, True),
        max_lines=9,
        line_spacing=20
    )

    draw.text(
        (65, 1340),
        "EDITORIAL NOTE",
        font=get_font(28, True),
        fill=(230, 55, 65)
    )

    draw_wrapped(
        draw,
        "This card uses only the stated impact "
        "in the verified source.",
        (
            65,
            1410,
            WIDTH - 65,
            1590
        ),
        get_font(30),
        max_lines=4,
        line_spacing=12
    )

    footer(draw, story)

    return image


def scene_statement(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "OFFICIAL STATEMENT"
    )

    speaker, quote = official_statement(
        story
    )

    if quote:
        draw.text(
            (65, 330),
            speaker or "Official source",
            font=get_font(38, True),
            fill=(230, 55, 65)
        )

        draw_wrapped(
            draw,
            f"“{quote}”",
            (
                65,
                450,
                WIDTH - 65,
                1350
            ),
            get_font(52),
            max_lines=12,
            line_spacing=20
        )
    else:
        draw.text(
            (65, 450),
            "No official statement was provided.",
            font=get_font(45, True),
            fill=(235, 235, 240)
        )

    footer(draw, story)

    return image


def scene_source(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    section_label(
        draw,
        "SOURCE"
    )

    draw_wrapped(
        draw,
        source_name(story),
        (
            65,
            330,
            WIDTH - 65,
            430
        ),
        get_font(42, True),
        max_lines=2,
        line_spacing=10
    )

    draw_wrapped(
        draw,
        source_url(story)
        or "Source URL not provided",
        (
            65,
            470,
            WIDTH - 65,
            1000
        ),
        get_font(30),
        max_lines=8,
        line_spacing=15
    )

    draw.text(
        (65, 1080),
        "REPORT DATE",
        font=get_font(28, True),
        fill=(230, 55, 65)
    )

    draw.text(
        (65, 1150),
        story_date(story) or "Not stated",
        font=get_font(50, True),
        fill=(240, 240, 245)
    )

    source_badge(
        draw,
        story
    )

    footer(draw, story)

    return image


def scene_outro(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)

    draw.text(
        (55, 520),
        "RIFT VALLEY",
        font=get_font(58, True),
        fill=(235, 55, 65)
    )

    draw.text(
        (55, 610),
        "WATCH",
        font=get_font(100, True),
        fill=(245, 245, 248)
    )

    draw_wrapped(
        draw,
        "Verified regional news. "
        "Clear facts. Source-led reporting.",
        (
            55,
            800,
            WIDTH - 55,
            1120
        ),
        get_font(42),
        max_lines=5,
        line_spacing=14
    )

    draw.text(
        (55, 1260),
        "FOLLOW FOR MORE",
        font=get_font(35, True),
        fill=(230, 55, 65)
    )

    footer(draw, story)

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration_segments(story):
    title = story_title(story)
    location = story_location(story)
    length = story_length(story)
    cost = story_cost(story)
    route = story_route(story)
    impact = story_impact(story)
    status = story_status(story)

    speaker, quote = official_statement(
        story
    )

    segments = [
        f"{title}.",

        (
            f"The project is located in "
            f"{location}. "
            f"Construction status: {status}."
        ),

        (
            f"Key figures: "
            f"{length or 'length not stated'}, "
            f"with a reported project cost of "
            f"{cost}."
        ),

        (
            f"The reported route is "
            f"{route or 'not fully stated in the available source'}."
        ),

        (
            f"Why it matters: "
            f"{impact or 'the verified source does not state a specific impact.'}"
        ),
    ]

    if quote:
        segments.append(
            f"{speaker or 'An official'} said: {quote}"
        )
    else:
        segments.append(
            "No separate official statement "
            "was provided in the verified story."
        )

    segments.append(
        f"This report is based on "
        f"{source_name(story)}, dated "
        f"{story_date(story) or 'the reported date'}."
    )

    segments.append(
        "Rift Valley Watch. "
        "Verified regional news. "
        "Follow for more."
    )

    return [
        clean_text(segment)
        for segment in segments
    ]


def create_audio(text, index):
    path = (
        AUDIO_DIR
        / f"segment_{index:02d}.mp3"
    )

    if (
        path.exists()
        and path.stat().st_size > 1000
    ):
        print(
            f"Using existing narration: {path}"
        )
        return path

    print(
        f"Creating narration {index}: {text}"
    )

    try:
        tts = gTTS(
            text=text,
            lang="en",
            slow=False
        )

        tts.save(
            str(path)
        )

    except Exception as exc:
        raise RuntimeError(
            f"gTTS failed for segment "
            f"{index}: {exc}"
        )

    if (
        not path.exists()
        or path.stat().st_size < 1000
    ):
        raise RuntimeError(
            f"Narration failed: {path}"
        )

    return path


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
            result.strip()
        )
    except ValueError:
        raise RuntimeError(
            f"Could not read audio duration: {path}"
        )


# ============================================================
# CAPTIONS
# ============================================================

def split_caption_words(
    text,
    words_per_group=7
):
    words = clean_text(text).split()

    return [
        words[i:i + words_per_group]
        for i in range(
            0,
            len(words),
            words_per_group
        )
    ]


def format_srt_time(seconds):
    milliseconds = int(
        round(seconds * 1000)
    )

    hours = milliseconds // 3600000

    milliseconds %= 3600000

    minutes = milliseconds // 60000

    milliseconds %= 60000

    secs = milliseconds // 1000

    millis = milliseconds % 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def create_srt(
    text,
    duration,
    scene_number
):
    path = (
        SCENE_DIR
        / f"scene_{scene_number:02d}.srt"
    )

    groups = split_caption_words(
        text,
        7
    )

    if not groups:
        groups = [[""]]

    weights = [
        max(1, len(group))
        for group in groups
    ]

    total = sum(weights)

    cursor = 0.0
    lines = []

    for index, group in enumerate(
        groups,
        start=1
    ):
        segment_duration = (
            duration
            * weights[index - 1]
            / total
        )

        start = cursor

        end = min(
            duration,
            cursor + segment_duration
        )

        cursor = end

        lines.extend(
            [
                str(index),
                (
                    f"{format_srt_time(start)}"
                    f" --> "
                    f"{format_srt_time(end)}"
                ),
                " ".join(group),
                ""
            ]
        )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    return path


# ============================================================
# SCENE FILES
# ============================================================

def save_scene(
    image,
    scene_number
):
    path = (
        SCENE_DIR
        / f"scene_{scene_number:02d}.png"
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
    scene_number
):
    duration = audio_duration(
        audio_path
    )

    srt_path = create_srt(
        caption_text,
        duration,
        scene_number
    )

    output = (
        SCENE_DIR
        / f"scene_{scene_number:02d}.mp4"
    )

    subtitle_path = str(
        srt_path.resolve()
    ).replace(
        "\\",
        "/"
    )

    subtitle_path = subtitle_path.replace(
        ":",
        r"\:"
    )

    filter_text = (
        f"scale={WIDTH}:{HEIGHT}:"
        f"force_original_aspect_ratio=cover,"
        f"crop={WIDTH}:{HEIGHT},"
        f"setsar=1,"
        f"subtitles='{subtitle_path}':"
        f"force_style='"
        f"FontName=DejaVu Sans,"
        f"FontSize=22,"
        f"Bold=1,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00101010,"
        f"BorderStyle=1,"
        f"Outline=3,"
        f"Shadow=1,"
        f"Alignment=2,"
        f"MarginV=95'"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-vf",
            filter_text,
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
            "160k",
            "-ar",
            "48000",
            "-shortest",
            str(output)
        ]
    )

    if (
        not output.exists()
        or output.stat().st_size < 10000
    ):
        raise RuntimeError(
            f"Scene video was not created: "
            f"{output}"
        )

    return (
        output,
        duration,
        srt_path
    )


# ============================================================
# CONCATENATION
# ============================================================

def concat_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files were created."
        )

    inputs = []

    for scene in scene_files:
        inputs.extend(
            [
                "-i",
                str(scene)
            ]
        )

    filter
