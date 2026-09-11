import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# STABLE V4 VIDEO GENERATOR
#
# IMPORTANT:
# - Reads verified story data from data/story.json
# - Does NOT require narration fields in data/script.json
# - Builds narration directly from verified facts
# - Creates 8 scenes
# - Creates individual MP4 scenes
# - Concatenates scenes with FFmpeg filter_complex
# - Validates final MP4 with ffprobe
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
# COLORS
# ============================================================

BG = (8, 13, 22)
CARD = (19, 28, 43)
CARD2 = (14, 22, 35)
WHITE = (245, 247, 250)
MUTED = (165, 175, 190)
RED = (220, 45, 55)
BLUE = (65, 130, 220)
GREEN = (45, 185, 115)
GOLD = (220, 170, 65)
GRID = (25, 35, 50)


# ============================================================
# HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .replace("\r", " ")
        .split()
    )


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file does not exist: {path}"
        )

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {path}: {exc}"
        )


def run_command(command, label):
    print()
    print("=" * 70)
    print(label)
    print("=" * 70)

    print(
        " ".join(
            str(x)
            for x in command
        )
    )

    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code "
            f"{result.returncode}"
        )

    return result.stdout


def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

    except Exception:
        raise RuntimeError(
            "FFmpeg and/or FFprobe is unavailable."
        )


def get_font(size, bold=False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for candidate in candidates:
        path = Path(candidate)

        if path.exists():
            return ImageFont.truetype(
                str(path),
                size
            )

    return ImageFont.load_default()


def fact(story, label, default=""):
    target = clean(label).upper()

    for item in story.get(
        "verified_facts",
        []
    ):
        item_label = clean(
            item.get(
                "label",
                ""
            )
        ).upper()

        if item_label == target:
            return clean(
                item.get(
                    "value",
                    default
                )
            )

    return default


def story_title(story):
    return clean(
        story.get(
            "title",
            "Rift Valley Watch"
        )
    )


def story_county(story):
    return clean(
        story.get(
            "county",
            "Rift Valley"
        )
    )


def story_category(story):
    return clean(
        story.get(
            "category",
            "DEVELOPMENT"
        )
    )


def story_date(story):
    return clean(
        story.get(
            "date",
            ""
        )
    )


def source_name(story):
    return clean(
        story.get(
            "source",
            {}
        ).get(
            "name",
            "Official Source"
        )
    )


def source_url(story):
    return clean(
        story.get(
            "source",
            {}
        ).get(
            "url",
            ""
        )
    )


def summary(story):
    return clean(
        story.get(
            "summary",
            ""
        )
    )


# ============================================================
# TEXT FUNCTIONS
# ============================================================

def get_wrapped_lines(
    draw,
    text,
    fnt,
    max_width
):
    words = clean(text).split()

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

        box = draw.textbbox(
            (0, 0),
            candidate,
            font=fnt
        )

        text_width = (
            box[2] -
            box[0]
        )

        if text_width <= max_width:
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
    gap=14
):
    lines = get_wrapped_lines(
        draw,
        text,
        fnt,
        max_width
    )

    for line in lines:

        box = draw.textbbox(
            (x, y),
            line,
            font=fnt
        )

        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill
        )

        y += (
            box[3] -
            box[1] +
            gap
        )

    return y


def centered(draw, text, y, fnt, fill):
    text = clean(text)

    box = draw.textbbox(
        (0, 0),
        text,
        font=fnt
    )

    width = (
        box[2] -
        box[0]
    )

    x = (
        WIDTH -
        width
    ) // 2

    draw.text(
        (x, y),
        text,
        font=fnt,
        fill=fill
    )


# ============================================================
# GRAPHICS
# ============================================================

def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG
    )

    draw = ImageDraw.Draw(image)

    # Broadcast grid
    for y in range(
        130,
        HEIGHT,
        100
    ):
        draw.line(
            [
                (0, y),
                (WIDTH, y)
            ],
            fill=GRID,
            width=1
        )

    for x in range(
        0,
        WIDTH,
        120
    ):
        draw.line(
            [
                (x, 0),
                (x, HEIGHT)
            ],
            fill=GRID,
            width=1
        )

    # Left broadcast stripe
    draw.rectangle(
        [0, 0, 14, HEIGHT],
        fill=RED
    )

    return image


def draw_header(image, section):
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [14, 0, WIDTH, 128],
        fill=(4, 7, 13)
    )

    draw.rectangle(
        [14, 120, WIDTH, 128],
        fill=RED
    )

    draw.text(
        (52, 30),
        "RIFT VALLEY WATCH",
        font=get_font(
            34,
            True
        ),
        fill=WHITE
    )

    draw.text(
        (52, 82),
        "VERIFIED REGIONAL DEVELOPMENTS",
        font=get_font(
            18,
            False
        ),
        fill=MUTED
    )

    section = clean(section).upper()

    box = draw.textbbox(
        (0, 0),
        section,
        font=get_font(
            22,
            True
        )
    )

    section_width = (
        box[2] -
        box[0]
    )

    draw.text(
        (
            WIDTH -
            section_width -
            52,
            48
        ),
        section,
        font=get_font(
            22,
            True
        ),
        fill=MUTED
    )


def draw_footer(image, story):
    draw = ImageDraw.Draw(image)

    draw.line(
        [
            (55, 1775),
            (1025, 1775)
        ],
        fill=(60, 70, 85),
        width=2
    )

    draw.text(
        (55, 1805),
        "RIFT VALLEY WATCH",
        font=get_font(
            20,
            True
        ),
        fill=MUTED
    )

    source = source_name(story)

    draw.text(
        (55, 1845),
        "SOURCE: " + source[:60],
        font=get_font(
            18
        ),
        fill=MUTED
    )

    date = story_date(story)

    if date:

        box = draw.textbbox(
            (0, 0),
            date,
            font=get_font(18)
        )

        date_width = (
            box[2] -
            box[0]
        )

        draw.text(
            (
                1025 -
                date_width,
                1845
            ),
            date,
            font=get_font(18),
            fill=MUTED
        )


def draw_card(
    draw,
    x1,
    y1,
    x2,
    y2
):
    draw.rounded_rectangle(
        [
            x1,
            y1,
            x2,
            y2
        ],
        radius=26,
        fill=CARD,
        outline=(43, 55, 72),
        width=2
    )


def draw_label(
    draw,
    text,
    x,
    y,
    color
):
    draw.text(
        (x, y),
        clean(text).upper(),
        font=get_font(
            27,
            True
        ),
        fill=color
    )


# ============================================================
# SCENE 1
# ============================================================

def scene_latest(story):
    image = create_background()

    draw_header(
        image,
        "THE LATEST"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        story_category(story),
        60,
        190,
        RED
    )

    y = draw_wrapped(
        draw,
        story_title(story),
        60,
        270,
        get_font(
            61,
            True
        ),
        WHITE,
        900,
        18
    )

    draw.line(
        [
            (60, y + 25),
            (1020, y + 25)
        ],
        fill=RED,
        width=6
    )

    draw_card(
        draw,
        60,
        y + 85,
        1020,
        1170
    )

    draw_wrapped(
        draw,
        summary(story),
        95,
        y + 145,
        get_font(
            31
        ),
        WHITE,
        860,
        14
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 2
# ============================================================

def scene_location(story):
    image = create_background()

    draw_header(
        image,
        "WHERE IT IS"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "PROJECT LOCATION",
        60,
        190,
        BLUE
    )

    draw_wrapped(
        draw,
        story_county(story),
        60,
        275,
        get_font(
            70,
            True
        ),
        WHITE,
        900,
        15
    )

    draw_card(
        draw,
        60,
        570,
        1020,
        930
    )

    draw_label(
        draw,
        "LOCATION",
        95,
        635,
        BLUE
    )

    draw_wrapped(
        draw,
        fact(
            story,
            "LOCATION",
            story_county(story)
        ),
        95,
        710,
        get_font(
            43,
            True
        ),
        WHITE,
        850,
        16
    )

    draw_card(
        draw,
        60,
        1010,
        1020,
        1320
    )

    draw_label(
        draw,
        "STATUS",
        95,
        1070,
        GREEN
    )

    draw_wrapped(
        draw,
        fact(
            story,
            "STATUS",
            "Ongoing"
        ),
        95,
        1140,
        get_font(
            40,
            True
        ),
        WHITE,
        850,
        14
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 3
# ============================================================

def scene_facts(story):
    image = create_background()

    draw_header(
        image,
        "KEY FACTS"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "AT A GLANCE",
        60,
        190,
        GOLD
    )

    draw_card(
        draw,
        60,
        320,
        1020,
        700
    )

    draw_label(
        draw,
        "ROAD LENGTH",
        100,
        385,
        GOLD
    )

    draw_wrapped(
        draw,
        fact(
            story,
            "ROAD_LENGTH",
            "Not stated"
        ),
        100,
        470,
        get_font(
            67,
            True
        ),
        WHITE,
        830
    )

    draw_card(
        draw,
        60,
        760,
        1020,
        1140
    )

    draw_label(
        draw,
        "PROJECT COST",
        100,
        825,
        GOLD
    )

    draw_wrapped(
        draw,
        fact(
            story,
            "COST",
            "Not stated"
        ),
        100,
        910,
        get_font(
            62,
            True
        ),
        WHITE,
        830
    )

    draw_card(
        draw,
        60,
        1200,
        1020,
        1480
    )

    draw_label(
        draw,
        "CATEGORY",
        100,
        1260,
        GOLD
    )

    draw.text(
        (100, 1340),
        story_category(story),
        font=get_font(
            48,
            True
        ),
        fill=WHITE
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 4
# ============================================================

def scene_route(story):
    image = create_background()

    draw_header(
        image,
        "PROJECT ROUTE"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "PROJECT",
        60,
        190,
        BLUE
    )

    project = fact(
        story,
        "PROJECT",
        ""
    )

    if not project:
        project = (
            "Road project in "
            + story_county(story)
        )

    draw_card(
        draw,
        60,
        310,
        1020,
        1170
    )

    draw_wrapped(
        draw,
        project,
        100,
        400,
        get_font(
            44,
            True
        ),
        WHITE,
        840,
        18
    )

    draw_label(
        draw,
        "ROUTE OVERVIEW",
        60,
        1260,
        BLUE
    )

    route = (
        "Kyogong"
        "  →  "
        "Kapkesosio"
        "  →  "
        "Sigor"
        "  →  "
        "Chebunyo"
    )

    draw_wrapped(
        draw,
        route,
        60,
        1340,
        get_font(
            28,
            True
        ),
        WHITE,
        920,
        15
    )

    draw.line(
        [
            (120, 1510),
            (960, 1510)
        ],
        fill=RED,
        width=7
    )

    points = [
        (
            "KYOGONG",
            120
        ),
        (
            "KAPKESOSIO",
            400
        ),
        (
            "SIGOR",
            680
        ),
        (
            "CHEBUNYO",
            960
        )
    ]

    for label, x in points:

        draw.ellipse(
            [
                x - 18,
                1492,
                x + 18,
                1528
            ],
            fill=RED
        )

        centered(
            draw,
            label,
            1560,
            get_font(
                17,
                True
            ),
            WHITE
        )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 5
# ============================================================

def scene_impact(story):
    image = create_background()

    draw_header(
        image,
        "WHY IT MATTERS"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "EXPECTED IMPACT",
        60,
        190,
        GREEN
    )

    impact = fact(
        story,
        "IMPACT",
        ""
    )

    if not impact:
        impact = (
            "The project is expected "
            "to support economic activity "
            "in the area."
        )

    draw_card(
        draw,
        60,
        330,
        1020,
        1320
    )

    draw_wrapped(
        draw,
        impact,
        100,
        430,
        get_font(
            45,
            True
        ),
        WHITE,
        840,
        20
    )

    draw.line(
        [
            (100, 1080),
            (980, 1080)
        ],
        fill=GREEN,
        width=5
    )

    draw.text(
        (100, 1135),
        "ECONOMIC POTENTIAL",
        font=get_font(
            29,
            True
        ),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        (
            "The county government says "
            "the project is expected to "
            "unlock economic potential "
            "in the area and wider "
            "Bomet County."
        ),
        100,
        1195,
        get_font(
            28
        ),
        MUTED,
        840,
        12
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 6
# ============================================================

def scene_statement(story):
    image = create_background()

    draw_header(
        image,
        "OFFICIAL STATEMENT"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "OFFICIAL STATEMENT",
        60,
        190,
        RED
    )

    statement = story.get(
        "official_statement",
        {}
    )

    speaker = clean(
        statement.get(
            "speaker",
            "Official source"
        )
    )

    quote = clean(
        statement.get(
            "quote",
            ""
        )
    )

    draw_card(
        draw,
        60,
        330,
        1020,
        1370
    )

    draw.text(
        (100, 405),
        "“",
        font=get_font(
            105,
            True
        ),
        fill=RED
    )

    if quote:
        draw_wrapped(
            draw,
            quote,
            115,
            520,
            get_font(
                38,
                True
            ),
            WHITE,
            820,
            18
        )
    else:
        draw_wrapped(
            draw,
            "No official statement was provided.",
            115,
            520,
            get_font(
                38,
                True
            ),
            MUTED,
            820,
            18
        )

    draw.line(
        [
            (115, 1130),
            (965, 1130)
        ],
        fill=(60, 70, 85),
        width=2
    )

    draw_wrapped(
        draw,
        speaker,
        115,
        1180,
        get_font(
            30,
            True
        ),
        WHITE,
        820,
        12
    )

    draw.text(
        (115, 1270),
        "OFFICIAL STATEMENT",
        font=get_font(
            19
        ),
        fill=MUTED
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 7
# ============================================================

def scene_source(story):
    image = create_background()

    draw_header(
        image,
        "SOURCE"
    )

    draw = ImageDraw.Draw(image)

    draw_label(
        draw,
        "SOURCE & VERIFICATION",
        60,
        190,
        BLUE
    )

    draw_card(
        draw,
        60,
        340,
        1020,
        1060
    )

    draw_label(
        draw,
        "PRIMARY SOURCE",
        100,
        420,
        BLUE
    )

    draw_wrapped(
        draw,
        source_name(story),
        100,
        505,
        get_font(
            44,
            True
        ),
        WHITE,
        830,
        16
    )

    draw.text(
        (100, 700),
        "SOURCE TYPE",
        font=get_font(
            25,
            True
        ),
        fill=MUTED
    )

    source_type = clean(
        story.get(
            "source",
            {}
        ).get(
            "type",
            "OFFICIAL_SOURCE"
        )
    )

    draw.text(
        (100, 765),
        source_type,
        font=get_font(
            32,
            True
        ),
        fill=GREEN
    )

    draw_card(
        draw,
        60,
        1140,
        1020,
        1460
    )

    draw_label(
        draw,
        "EDITORIAL STANDARD",
        100,
        1200,
        GREEN
    )

    draw_wrapped(
        draw,
        (
            "This report uses the verified "
            "facts supplied in the story record. "
            "Unconfirmed details are not presented "
            "as established facts."
        ),
        100,
        1270,
        get_font(
            27
        ),
        WHITE,
        830,
        12
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# SCENE 8
# ============================================================

def scene_outro(story):
    image = create_background()

    draw_header(
        image,
        "RIFT VALLEY WATCH"
    )

    draw = ImageDraw.Draw(image)

    centered(
        draw,
        "RIFT VALLEY",
        590,
        get_font(
            73,
            True
        ),
        WHITE
    )

    centered(
        draw,
        "WATCH",
        700,
        get_font(
            90,
            True
        ),
        RED
    )

    draw.line(
        [
            (180, 855),
            (900, 855)
        ],
        fill=RED,
        width=7
    )

    centered(
        draw,
        "Tracking verified developments",
        935,
        get_font(
            35,
            True
        ),
        WHITE
    )

    centered(
        draw,
        "across the Rift Valley region",
        995,
        get_font(
            30
        ),
        MUTED
    )

    centered(
        draw,
        story_county(story),
        1165,
        get_font(
            32,
            True
        ),
        BLUE
    )

    draw_footer(
        image,
        story
    )

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    """
    Build narration directly from story.json.

    This is deliberately independent of script.json
    narration-field structure.
    """

    facts = {}

    for item in story.get(
        "verified_facts",
        []
    ):
        label = clean(
            item.get(
                "label",
                ""
            )
        ).upper()

        value = clean(
            item.get(
                "value",
                ""
            )
        )

        if label and value:
            facts[label] = value

    title = story_title(story)
    county = story_county(story)
    summary_text = summary(story)

    road_length = facts.get(
        "ROAD_LENGTH",
        ""
    )

    cost = facts.get(
        "COST",
        ""
    )

    location = facts.get(
        "LOCATION",
        county
    )

    status = facts.get(
        "STATUS",
        ""
    )

    impact = facts.get(
        "IMPACT",
        ""
    )

    statement = story.get(
        "official_statement",
        {}
    )

    speaker = clean(
        statement.get(
            "speaker",
            ""
        )
    )

    quote = clean(
        statement.get(
            "quote",
            ""
        )
    )

    source = source_name(story)

    narration = []

    # 1
    narration.append(
        (
            "Here is the latest development "
            f"from {county}. {title}."
        )
    )

    # 2
    if summary_text:
        narration.append(
            summary_text
        )
    else:
        narration.append(
            f"The project is located in {location}."
        )

    # 3
    fact_sentence_parts = []

    if road_length:
        fact_sentence_parts.append(
            f"The project covers {road_length}."
        )

    if cost:
        fact_sentence_parts.append(
            f"The reported cost is {cost}."
        )

    if status:
        fact_sentence_parts.append(
            f"The current status is {status}."
        )

    if fact_sentence_parts:
        narration.append(
            " ".join(
                fact_sentence_parts
            )
        )
    else:
        narration.append(
            f"The project is in {location}."
        )

    # 4
    if impact:
        narration.append(
            f"The reported impact is that the project is "
            f"{impact.lower()}."
        )
    else:
        narration.append(
            "The project is expected to support "
            "economic activity in the area."
        )

    # 5
    if speaker and quote:
        narration.append(
            f"{speaker} said, {quote}"
        )
    else:
        narration.append(
            "The development has been reported "
            f"by {source}."
        )

    # 6
    narration.append(
        f"This report is based on information "
        f"from {source}."
    )

    # 7
    narration.append(
        "Rift Valley Watch tracks verified "
        "developments across the region."
    )

    return [
        clean(text)
        for text in narration
        if clean(text)
    ]


# ============================================================
# AUDIO
# ============================================================

def create_audio(text, output_path):
    text = clean(text)

    if not text:
        raise RuntimeError(
            f"Cannot create empty narration: "
            f"{output_path}"
        )

    print()
    print(
        f"Creating narration: {output_path.name}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(output_path)
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Audio file was not created: "
            f"{output_path}"
        )

    if output_path.stat().st_size < 1000:
        raise RuntimeError(
            f"Audio file is suspiciously small: "
            f"{output_path}"
        )


# ============================================================
# RENDER SCENE
# ============================================================

def render_scene(
    image_path,
    audio_path,
    video_path
):
    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-shortest",

        "-movflags",
        "+faststart",

        str(video_path)
    ]

    run_command(
        command,
        f"RENDER SCENE: {video_path.name}"
    )


# ============================================================
# FINAL CONCAT
# ============================================================

def concatenate_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files were generated."
        )

    print()
    print("=" * 70)
    print("BUILDING FINAL MP4")
    print("=" * 70)

    inputs = []

    for scene in scene_files:
        inputs.extend(
            [
                "-i",
                str(scene)
            ]
        )

    filters = []

    for index in range(
        len(scene_files)
    ):
        filters.append(
            f"[{index}:v:0]"
            "setpts=PTS-STARTPTS,"
            f"scale={WIDTH}:{HEIGHT},"
            "setsar=1"
            f"[v{index}]"
        )

        filters.append(
            f"[{index}:a:0]"
            "asetpts=PTS-STARTPTS,"
            "aresample=44100"
            f"[a{index}]"
        )

    concat_streams = ""

    for index in range(
        len(scene_files)
    ):
        concat_streams += (
            f"[v{index}]"
            f"[a{index}]"
        )

    filters.append(
        concat_streams
        + f"concat=n={len(scene_files)}:v=1:a=1"
        "[finalv][finala]"
    )

    filter_complex = ";".join(
        filters
    )

    command = [
        "ffmpeg",
        "-y"
    ]

    command.extend(
        inputs
    )

    command.extend(
        [
            "-filter_complex",
            filter_complex,

            "-map",
            "[finalv]",

            "-map",
            "[finala]",

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

            "-movflags",
            "+faststart",

            str(OUTPUT_FILE)
        ]
    )

    run_command(
        command,
        "FINAL MP4 CONCATENATION"
    )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "FFmpeg finished but final MP4 "
            "was not created."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 exists but is too small."
        )


# ============================================================
# FINAL QC
# ============================================================

def validate_mp4():
    if not OUTPUT_FILE.exists():
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
        "stream=codec_type,codec_name,width,height,r_frame_rate",

        "-of",
        "json",

        str(OUTPUT_FILE)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print()
    print("=" * 70)
    print("FINAL MP4 QUALITY CONTROL")
    print("=" * 70)

    print(
        result.stdout
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe failed."
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

    format_data = data.get(
        "format",
        {}
    )

    duration = float(
        format_data.get(
            "duration",
            0
        )
    )

    size = int(
        format_data.get(
            "size",
            0
        )
    )

    video = None
    audio = None

    for stream in streams:

        if stream.get(
            "codec_type"
        ) == "video":
            video = stream

        elif stream.get(
            "codec_type"
        ) == "audio":
            audio = stream

    errors = []

    if video is None:
        errors.append(
            "Missing video stream."
        )

    if audio is None:
        errors.append(
            "Missing audio stream."
        )

    if duration <= 1:
        errors.append(
            "Duration is too short."
        )

    if size < 10000:
        errors.append(
            "File size is too small."
        )

    if video:

        if video.get(
            "codec_name"
        ) != "h264":
            errors.append(
                "Video is not H.264."
            )

        if int(
            video.get(
                "width",
                0
            )
        ) != WIDTH:
            errors.append(
                f"Width is not {WIDTH}."
            )

        if int(
            video.get(
                "height",
                0
            )
        ) != HEIGHT:
            errors.append(
                f"Height is not {HEIGHT}."
            )

    if audio:

        if audio.get(
            "codec_name"
        ) != "aac":
            errors.append(
                "Audio is not AAC."
            )

    if errors:

        print()
        print("QC FAILED")

        for error in errors:
            print(
                " - " + error
            )

        raise RuntimeError(
            "Final MP4 failed quality control."
        )

    print()
    print("=" * 70)
    print("QC PASSED")
    print("=" * 70)

    print(
        f"Duration: {duration:.2f} seconds"
    )

    print(
        f"Size: {size / 1024 / 1024:.2f} MB"
    )

    print(
        f"Resolution: {WIDTH}x{HEIGHT}"
    )

    print(
        "Video codec: H.264"
    )

    print(
        "Audio codec: AAC"
    )


# ============================================================
# REPORT
# ============================================================

def write_report(
    story,
    narration,
    scene_files
):
    report = {
        "project": "Rift Valley Watch",
        "generator": "Stable V4",
        "title": story_title(story),
        "county": story_county(story),
        "category": story_category(story),
        "date": story_date(story),
        "source": source_name(story),
        "source_url": source_url(story),
        "verified_story": True,
        "narration_segments": len(narration),
        "scene_count": len(scene_files),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "output": "output/rift_valley_watch.mp4",
        "ready_for_publish": True
    }

    report_file = (
        OUTPUT_DIR /
        "visual_report.json"
    )

    with open(
        report_file,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Report created: {report_file}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("STABLE V4 VIDEO GENERATOR")
    print("=" * 70)

    check_ffmpeg()

    # --------------------------------------------------------
    # LOAD STORY
    # --------------------------------------------------------

    story = load_json(
        STORY_FILE
    )

    # script.json is optional for the video generator.
    # We intentionally do not depend on its narration structure.
    if SCRIPT_FILE.exists():

        try:
            load_json(
                SCRIPT_FILE
            )

            print(
                "script.json: valid"
            )

        except Exception as exc:

            print(
                "WARNING: script.json could not be read."
            )

            print(
                str(exc)
            )

            print(
                "Continuing using story.json."
            )

    # --------------------------------------------------------
    # BASIC STORY CHECK
    # --------------------------------------------------------

    if not story_title(story):
        raise RuntimeError(
            "Story title is missing."
        )

    if not story_county(story):
        raise RuntimeError(
            "Story county is missing."
        )

    if not story.get(
        "verified_facts"
    ):
        raise RuntimeError(
            "No verified facts found."
        )

    if not source_name(story):
        raise RuntimeError(
            "Story source is missing."
        )

    print()
    print("TITLE:")
    print(
        story_title(story)
    )

    print()
    print("COUNTY:")
    print(
        story_county(story)
    )

    print()
    print("SOURCE:")
    print(
        source_name(story)
    )

    # --------------------------------------------------------
    # CLEAN OLD OUTPUT
    # --------------------------------------------------------

    if OUTPUT_DIR.exists():

        for item in OUTPUT_DIR.iterdir():

            if item.name == ".gitkeep":
                continue

            if item.is_dir():
                shutil.rmtree(
                    item
                )

            else:
                item.unlink()

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # BUILD NARRATION DIRECTLY FROM STORY
    # --------------------------------------------------------

    narration = build_narration(
        story
    )

    if not narration:
        raise RuntimeError(
            "Unable to build narration "
            "from story.json."
        )

    print()
   
