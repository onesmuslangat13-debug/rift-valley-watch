import json
import re
import html
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH V2
# VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"
REPORT_FILE = ROOT / "data" / "visual_report.json"

OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"

ASSET_DIR = ROOT / "assets"
AUDIO_DIR = ASSET_DIR / "audio"
SOURCE_DIR = ASSET_DIR / "source"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

BG = (9, 13, 22)
BG2 = (14, 20, 32)
WHITE = (245, 247, 250)
MUTED = (165, 175, 190)
RED = (220, 45, 55)
GREEN = (48, 180, 115)
BLUE = (60, 130, 220)
YELLOW = (235, 180, 55)
CARD = (20, 28, 43)
CARD2 = (27, 37, 55)
BLACK = (0, 0, 0)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = html.unescape(value)
    value = value.replace("\n", " ")
    value = value.replace("\r", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def run_command(command, check=True):
    print()
    print("RUNNING:")
    print(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            + str(result.returncode)
        )

    return result


def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(
            "Required JSON file not found: "
            + str(path)
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# STORY HELPERS
# ============================================================

def story_title(story):
    return clean_text(
        story.get(
            "title",
            "Rift Valley Watch"
        )
    )


def story_county(story):
    return clean_text(
        story.get(
            "county",
            "Rift Valley"
        )
    )


def story_category(story):
    return clean_text(
        story.get(
            "category",
            "DEVELOPMENT"
        )
    )


def story_date(story):
    return clean_text(
        story.get(
            "date",
            ""
        )
    )


def verified_facts(story):
    facts = story.get(
        "verified_facts",
        []
    )

    if not isinstance(facts, list):
        return []

    return facts


def fact(story, label, default=""):
    target = label.upper()

    for item in verified_facts(story):
        if not isinstance(item, dict):
            continue

        current_label = clean_text(
            item.get("label", "")
        ).upper()

        if current_label == target:
            return clean_text(
                item.get(
                    "value",
                    default
                )
            )

    return default


def story_location(story):
    return fact(
        story,
        "LOCATION",
        story_county(story)
    )


def road_length(story):
    return fact(
        story,
        "ROAD_LENGTH",
        ""
    )


def project_cost(story):
    return fact(
        story,
        "COST",
        ""
    )


def project_status(story):
    return fact(
        story,
        "STATUS",
        ""
    )


def project_route(story):
    return fact(
        story,
        "PROJECT",
        ""
    )


def project_impact(story):
    return fact(
        story,
        "IMPACT",
        ""
    )


def source_name(story):
    source = story.get(
        "source",
        {}
    )

    if isinstance(source, dict):
        return clean_text(
            source.get(
                "name",
                "Official Source"
            )
        )

    return "Official Source"


def source_url(story):
    source = story.get(
        "source",
        {}
    )

    if isinstance(source, dict):
        return clean_text(
            source.get(
                "url",
                ""
            )
        )

    return ""


def official_statement(story):
    statement = story.get(
        "official_statement",
        {}
    )

    if not isinstance(statement, dict):
        return {}

    return statement


# ============================================================
# FONT SYSTEM
# ============================================================

def get_font(size, bold=False):
    candidates = []

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    candidates.extend([
        str(ROOT / "assets" / "DejaVuSans-Bold.ttf"),
        str(ROOT / "assets" / "DejaVuSans.ttf")
    ])

    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(
                    path,
                    size
                )
        except Exception:
            pass

    return ImageFont.load_default()


# ============================================================
# TEXT LAYOUT
# ============================================================

def wrapped_lines(draw, text, font, max_width):
    text = clean_text(text)

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = (
            word
            if not current
            else current + " " + word
        )

        box = draw.textbbox(
            (0, 0),
            test,
            font=font
        )

        width = box[2] - box[0]

        if width <= max_width:
            current = test
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
    font,
    fill,
    max_width,
    line_gap=12,
    max_lines=None
):
    lines = wrapped_lines(
        draw,
        text,
        font,
        max_width
    )

    if max_lines:
        lines = lines[:max_lines]

    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill
        )

        box = draw.textbbox(
            (x, current_y),
            line,
            font=font
        )

        height = box[3] - box[1]

        current_y += height + line_gap

    return current_y


# ============================================================
# BACKGROUND / GRAPHICS
# ============================================================

def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(
            BG[0]
            + (BG2[0] - BG[0]) * ratio
        )

        g = int(
            BG[1]
            + (BG2[1] - BG[1]) * ratio
        )

        b = int(
            BG[2]
            + (BG2[2] - BG[2]) * ratio
        )

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(r, g, b)
        )

    return image


def add_grid(image):
    draw = ImageDraw.Draw(image)

    for x in range(0, WIDTH, 90):
        draw.line(
            [(x, 0), (x, HEIGHT)],
            fill=(22, 30, 45),
            width=1
        )

    for y in range(0, HEIGHT, 90):
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(22, 30, 45),
            width=1
        )


def top_bar(
    image,
    section_name
):
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, WIDTH, 112],
        fill=(7, 10, 17)
    )

    draw.rectangle(
        [0, 108, WIDTH, 112],
        fill=RED
    )

    logo_font = get_font(
        34,
        bold=True
    )

    section_font = get_font(
        25,
        bold=True
    )

    draw.text(
        (55, 32),
        "RIFT VALLEY WATCH",
        font=logo_font,
        fill=WHITE
    )

    draw.text(
        (WIDTH - 420, 38),
        section_name.upper(),
        font=section_font,
        fill=MUTED
    )


def footer(
    image,
    source=""
):
    draw = ImageDraw.Draw(image)

    y = HEIGHT - 105

    draw.line(
        [(45, y), (WIDTH - 45, y)],
        fill=(55, 65, 82),
        width=2
    )

    font = get_font(
        21,
        bold=False
    )

    draw.text(
        (50, y + 25),
        "RIFT VALLEY WATCH",
        font=font,
        fill=MUTED
    )

    if source:
        source_text = (
            "SOURCE: "
            + clean_text(source)
        )

        draw.text(
            (WIDTH - 520, y + 25),
            source_text[:48],
            font=font,
            fill=MUTED
        )


def section_title(
    image,
    title,
    subtitle=""
):
    draw = ImageDraw.Draw(image)

    title_font = get_font(
        62,
        bold=True
    )

    subtitle_font = get_font(
        27,
        bold=False
    )

    draw.text(
        (60, 175),
        title.upper(),
        font=title_font,
        fill=WHITE
    )

    if subtitle:
        draw_wrapped(
            draw,
            subtitle,
            65,
            265,
            subtitle_font,
            MUTED,
            900,
            10
        )


def card(
    draw,
    x,
    y,
    w,
    h,
    title="",
    body="",
    accent=RED
):
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=22,
        fill=CARD,
        outline=(45, 58, 80),
        width=2
    )

    draw.rectangle(
        [x, y, x + 9, y + h],
        fill=accent
    )

    if title:
        title_font = get_font(
            27,
            bold=True
        )

        draw.text(
            (x + 32, y + 28),
            title.upper(),
            font=title_font,
            fill=accent
        )

    if body:
        body_font = get_font(
            31,
            bold=False
        )

        draw_wrapped(
            draw,
            body,
            x + 32,
            y + 78,
            body_font,
            WHITE,
            w - 65,
            10,
            7
        )


def source_badge(
    image,
    source
):
    draw = ImageDraw.Draw(image)

    font = get_font(
        22,
        bold=True
    )

    text = (
        "VERIFIED SOURCE  •  "
        + clean_text(source)
    )

    box = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    w = box[2] - box[0] + 45
    h = box[3] - box[1] + 25

    x = 55
    y = 118

    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=15,
        fill=(30, 45, 48)
    )

    draw.text(
        (x + 22, y + 12),
        text,
        font=font,
        fill=GREEN
    )


# ============================================================
# SCENES
# ============================================================

def scene_latest(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "THE LATEST"
    )

    source_badge(
        image,
        source_name(story)
    )

    draw = ImageDraw.Draw(image)

    category_font = get_font(
        28,
        bold=True
    )

    title_font = get_font(
        66,
        bold=True
    )

    draw.text(
        (60, 260),
        story_category(story),
        font=category_font,
        fill=RED
    )

    draw_wrapped(
        draw,
        story_title(story),
        60,
        325,
        title_font,
        WHITE,
        930,
        15,
        6
    )

    draw.rounded_rectangle(
        [60, 790, WIDTH - 60, 1030],
        radius=28,
        fill=CARD2
    )

    summary = clean_text(
        story.get(
            "summary",
            ""
        )
    )

    summary_font = get_font(
        32,
        bold=False
    )

    draw_wrapped(
        draw,
        summary,
        95,
        835,
        summary_font,
        WHITE,
        875,
        12,
        6
    )

    date = story_date(story)

    if date:
        draw.text(
            (60, 1110),
            "REPORT DATE",
            font=get_font(
                25,
                bold=True
            ),
            fill=MUTED
        )

        draw.text(
            (60, 1155),
            date,
            font=get_font(
                40,
                bold=True
            ),
            fill=WHITE
        )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_location(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "WHERE IT IS"
    )

    section_title(
        image,
        "Where It Is",
        story_location(story)
    )

    draw = ImageDraw.Draw(image)

    county = story_county(story)
    location = story_location(story)

    card(
        draw,
        60,
        410,
        960,
        250,
        "County",
        county,
        BLUE
    )

    card(
        draw,
        60,
        710,
        960,
        300,
        "Project Location",
        location,
        RED
    )

    card(
        draw,
        60,
        1060,
        960,
        320,
        "Status",
        project_status(story),
        GREEN
    )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_facts(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "KEY FACTS"
    )

    section_title(
        image,
        "Key Facts",
        "The verified figures behind the development."
    )

    draw = ImageDraw.Draw(image)

    # Road length
    draw.rounded_rectangle(
        [60, 390, 500, 700],
        radius=28,
        fill=CARD
    )

    draw.text(
        (95, 435),
        "ROAD LENGTH",
        font=get_font(
            27,
            bold=True
        ),
        fill=MUTED
    )

    draw.text(
        (95, 500),
        road_length(story) or "N/A",
        font=get_font(
            70,
            bold=True
        ),
        fill=WHITE
    )

    # Cost
    draw.rounded_rectangle(
        [580, 390, 1020, 700],
        radius=28,
        fill=CARD
    )

    draw.text(
        (615, 435),
        "PROJECT VALUE",
        font=get_font(
            27,
            bold=True
        ),
        fill=MUTED
    )

    draw_wrapped(
        draw,
        project_cost(story) or "N/A",
        615,
        505,
        get_font(
            58,
            bold=True
        ),
        WHITE,
        360,
        8,
        3
    )

    card(
        draw,
        60,
        760,
        960,
        340,
        "PROJECT",
        project_route(story),
        RED
    )

    card(
        draw,
        60,
        1160,
        960,
        300,
        "STATUS",
        project_status(story),
        GREEN
    )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_route(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "THE ROUTE"
    )

    section_title(
        image,
        "The Route",
        "The road sections identified in the verified project information."
    )

    draw = ImageDraw.Draw(image)

    route = project_route(story)

    card(
        draw,
        60,
        430,
        960,
        430,
        "ROAD PROJECT",
        route,
        RED
    )

    # Route timeline
    points = [
        "KYOGONG",
        "KAPKESOSIO",
        "SIGOR",
        "CHEBUNYO",
        "LELAITICH",
        "KIPRERES",
        "LONGISA"
    ]

    start_y = 970

    for index, point in enumerate(points):
        y = start_y + index * 105

        if index < len(points) - 1:
            draw.line(
                [
                    (110, y + 45),
                    (110, y + 125)
                ],
                fill=BLUE,
                width=5
            )

        draw.ellipse(
            [
                88,
                y + 22,
                132,
                y + 66
            ],
            fill=RED
        )

        draw.text(
            (165, y + 18),
            point,
            font=get_font(
                31,
                bold=True
            ),
            fill=WHITE
        )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_impact(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "WHY IT MATTERS"
    )

    section_title(
        image,
        "Why It Matters",
        "The expected economic significance reported by the source."
    )

    draw = ImageDraw.Draw(image)

    impact = project_impact(story)

    card(
        draw,
        60,
        430,
        960,
        420,
        "EXPECTED IMPACT",
        impact,
        GREEN
    )

    card(
        draw,
        60,
        930,
        460,
        390,
        "AREA",
        story_county(story),
        BLUE
    )

    card(
        draw,
        560,
        930,
        460,
        390,
        "PROJECT",
        road_length(story)
        + " of road works",
        RED
    )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_statement(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "OFFICIAL STATEMENT"
    )

    section_title(
        image,
        "Official Statement",
        "Statement attributed to the official source."
    )

    draw = ImageDraw.Draw(image)

    statement = official_statement(story)

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

    if speaker:
        draw.text(
            (65, 420),
            speaker,
            font=get_font(
                38,
                bold=True
            ),
            fill=RED
        )

    draw.rounded_rectangle(
        [60, 520, 1020, 1230],
        radius=30,
        fill=CARD
    )

    draw.text(
        (100, 575),
        "“",
        font=get_font(
            100,
            bold=True
        ),
        fill=RED
    )

    draw_wrapped(
        draw,
        quote,
        125,
        690,
        get_font(
            37,
            bold=False
        ),
        WHITE,
        820,
        18,
        11
    )

    draw.text(
        (100, 1310),
        "ATTRIBUTED STATEMENT",
        font=get_font(
            25,
            bold=True
        ),
        fill=MUTED
    )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_source(story):
    image = create_background()
    add_grid(image)

    top_bar(
        image,
        "SOURCE"
    )

    section_title(
        image,
        "Source",
        "Editorial verification and attribution."
    )

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        [60, 450, 1020, 850],
        radius=30,
        fill=CARD
    )

    draw.text(
        (105, 510),
        "PRIMARY SOURCE",
        font=get_font(
            27,
            bold=True
        ),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        source_name(story),
        105,
        590,
        get_font(
            48,
            bold=True
        ),
        WHITE,
        850,
        12,
        4
    )

    url = source_url(story)

    if url:
        draw.text(
            (105, 730),
            "SOURCE URL",
            font=get_font(
                24,
                bold=True
            ),
            fill=MUTED
        )

        draw_wrapped(
            draw,
            url,
            105,
            775,
            get_font(
                23,
                bold=False
            ),
            WHITE,
            850,
            8,
            4
        )

    draw.rounded_rectangle(
        [60, 930, 1020, 1210],
        radius=30,
        fill=(25, 45, 38)
    )

    draw.text(
        (105, 990),
        "EDITORIAL STANDARD",
        font=get_font(
            27,
            bold=True
        ),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        "Facts shown in this video are based on the verified information supplied by the identified source.",
        105,
        1050,
        get_font(
            31,
            bold=False
        ),
        WHITE,
        850,
        12,
        6
    )

    footer(
        image,
        source_name(story)
    )

    return image


def scene_outro(story):
    image = create_background()
    add_grid(image)

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [0, 0, WIDTH, 14],
        fill=RED
    )

    draw.text(
        (60, 650),
        "RIFT VALLEY",
        font=get_font(
            78,
            bold=True
        ),
        fill=WHITE
    )

    draw.text(
        (60, 755),
        "WATCH",
        font=get_font(
            110,
            bold=True
        ),
        fill=RED
    )

    draw_wrapped(
        draw,
        "Tracking verified developments across the region.",
        65,
        920,
        get_font(
            37,
            bold=False
        ),
        MUTED,
        850,
        14,
        4
    )

    draw.line(
        [(65, 1140), (1015, 1140)],
        fill=(60, 75, 95),
        width=3
    )

    draw.text(
        (65, 1200),
        story_county(story),
        font=get_font(
            34,
            bold=True
        ),
        fill=WHITE
    )

    draw.text(
        (65, 1270),
        story_date(story),
        font=get_font(
            27,
            bold=False
        ),
        fill=MUTED
    )

    footer(
        image,
        source_name(story)
    )

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = story_title(story)
    county = story_county(story)
    location = story_location(story)
    length = road_length(story)
    cost = project_cost(story)
    status = project_status(story)
    route = project_route(story)
    impact = project_impact(story)

    statement = official_statement(story)

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

    narration = [
        (
            "Here is the latest from "
            + county
            + ". "
            + title
        ),

        (
            "The project is located in "
            + location
            + ". "
            + "Construction status is reported as "
            + status
            + "."
        ),

        (
            "The key figures are significant. "
            + "The project covers "
            + length
            + " and has a reported value of "
            + cost
            + "."
        ),

        (
            "The reported route includes "
            + route
            + "."
        ),

        (
            "The county government says the project "
            + impact
            + "."
        )
    ]

    if speaker and quote:
        narration.append(
            speaker
            + " stated: "
            + quote
        )
    else:
        narration.append(
            "The project information is attributed to "
            + source_name(story)
            + "."
        )

    narration.append(
        "The development is being tracked using "
        "verified information from the identified source."
    )

    narration.append(
        "For the latest verified developments across "
        "the region, this is Rift Valley Watch."
    )

    return [
        clean_text(item)
        for item in narration
        if clean_text(item)
    ]


def create_audio(text, index):
    filename = (
        AUDIO_DIR
        / f"narration_{index:02d}.mp3"
    )

    print(
        "Creating narration:",
        filename
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(filename)
    )

    if not filename.exists():
        raise RuntimeError(
            "Narration audio was not created: "
            + str(filename)
        )

    if filename.stat().st_size < 1000:
        raise RuntimeError(
            "Narration audio appears invalid: "
            + str(filename)
        )

    return filename


def audio_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Unable to determine audio duration: "
            + str(path)
        )

    return float(
        result.stdout.strip()
    )


# ============================================================
# CAPTIONS
# ============================================================

def srt_time(seconds):
    milliseconds = int(
        round(seconds * 1000)
    )

    hours = milliseconds // 3600000
    milliseconds %= 3600000

    minutes = milliseconds // 60000
    milliseconds %= 60000

    secs = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def create_srt(
    text,
    duration,
    index
):
    path = (
        SCENE_DIR
        / f"caption_{index:02d}.srt"
    )

    words = text.split()

    if not words:
        words = [""]

    chunks = []

    chunk = []

    for word in words:
        chunk.append(word)

        if len(chunk) >= 7:
            chunks.append(
                " ".join(chunk)
            )
            chunk = []

    if chunk:
        chunks.append(
            " ".join(chunk)
        )

    chunk_duration = (
        duration / max(
            len(chunks),
            1
        )
    )

    lines = []

    for i, chunk_text in enumerate(chunks):
        start = i * chunk_duration
        end = min(
            duration,
            (i + 1) * chunk_duration
        )

        lines.append(
            str(i + 1)
        )

        lines.append(
            srt_time(start)
            + " --> "
            + srt_time(end)
        )

        lines.append(
            chunk_text
        )

        lines.append("")

    path.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    return path


# ============================================================
# SCENE RENDERING
# ============================================================

def render_scene(
    image_path,
    audio_path,
    caption_text,
    scene_number
):
    duration = audio_duration(
        audio_path
    )

    # Keep a minimum scene duration.
    duration = max(
        duration,
        2.5
    )

    srt_path = create_srt(
        caption_text,
        duration,
        scene_number
    )

    output_path = (
        SCENE_DIR
        / f"scene_{scene_number:02d}.mp4"
    )

    subtitle_path = str(
        srt_path.resolve()
    )

    subtitle_path = subtitle_path.replace(
        "\\",
        "/"
    )

    subtitle_path = subtitle_path.replace(
        ":",
        "\\:"
    )

    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p,"
        "subtitles='"
        + subtitle_path
        + "':"
        "force_style='"
        "FontName=DejaVu Sans,"
        "FontSize=18,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=115"
        "'"
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
        "-t",
        f"{duration:.3f}",
        "-vf",
        vf,
        "-r",
        str(FPS),
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-shortest",
        str(output_path)
    ]

    result = run_command(
        command,
        check=False
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg failed while rendering scene "
            + str(scene_number)
        )

    if not output_path.exists():
        raise RuntimeError(
            "Scene video was not created: "
            + str(output_path)
        )

    return (
        output_path,
        duration,
        srt_path
    )


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(story):
    return [
        (
            "The Latest",
            scene_latest,
            0
        ),
        (
            "Where It Is",
            scene_location,
            1
        ),
        (
            "Key Facts",
            scene_facts,
            2
        ),
        (
            "The Route",
            scene_route,
            3
        ),
        (
            "Why It Matters",
            scene_impact,
            4
        ),
        (
            "Official Statement",
            scene_statement,
            5
        ),
        (
            "Source",
            scene_source,
            6
        ),
        (
            "Outro",
            scene_outro,
            7
        )
    ]


# ============================================================
# CONCATENATION
# ============================================================

def concat_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files were supplied."
        )

    concat_file = (
        SCENE_DIR
        / "concat.txt"
    )

    lines = []

    for path in scene_files:
        absolute = Path(path).resolve()

        escaped = str(
            absolute
        ).replace(
            "'",
            "'\\''"
        )

        lines.append(
            "file '" + escaped + "'"
        )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    # First attempt: stream copy.
    command_copy = [
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
        str(OUTPUT_FILE)
    ]

    result = run_command(
        command_copy,
        check=False
    )

    if (
        result.returncode == 0
        and OUTPUT_FILE.exists()
        and OUTPUT_FILE.stat().st_size > 10000
    ):
        return OUTPUT_FILE

    print(
        "Stream-copy concat failed."
    )

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    # Second attempt: re-encode.
    command_reencode = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-movflags",
        "+faststart",
        str(OUTPUT_FILE)
    ]

    result = run_command(
        command_reencode,
        check=False
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg could not concatenate the scene videos."
        )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return OUTPUT_FILE


# ============================================================
# VALIDATION
# ============================================================

def validate_mp4(path):
    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist: "
            + str(path)
        )

    if path.stat().st_size < 50000:
        raise RuntimeError(
            "Final MP4 is suspiciously small: "
            + str(path.stat().st_size)
            + " bytes"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(path)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not validate the MP4."
        )

    try:
        data = json.loads(
            result.stdout
        )
    except json.JSONDecodeError:
        raise RuntimeError(
            "ffprobe returned invalid JSON."
        )

    streams = data.get(
        "streams",
        []
    )

    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream

        if stream.get("codec_type") == "audio":
            audio_stream = stream

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video_stream.get(
            "width",
            0
        )
    )

    height = int(
        video_stream.get(
            "height",
            0
        )
    )

    if width != WIDTH or height != HEIGHT:
        raise RuntimeError(
            "Wrong video resolution: "
            + str(width)
            + "x"
            + str(height)
            + ". Expected "
            + str(WIDTH)
            + "x"
            + str(HEIGHT)
            + "."
        )

    duration = float(
        data.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
    )

    size = int(
        data.get(
            "format",
            {}
        ).get(
            "size",
            path.stat().st_size
        )
    )

    if duration <= 1:
        raise RuntimeError(
            "Final MP4 duration is invalid."
        )

    return {
        "valid": True,
        "duration": duration,
        "size": size,
        "width": width,
        "height": height,
        "video_codec": video_stream.get(
            "codec_name",
            ""
        ),
        "audio_codec": audio_stream.get(
            "codec_name",
            ""
        )
    }


# ============================================================
# CLEANUP
# ============================================================

def clean_previous_output():
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    if SCENE_DIR.exists():
        for item in SCENE_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as exc:
                print(
                    "Warning: could not remove "
                    + str(item)
                    + ": "
                    +
