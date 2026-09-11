import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH V3
# BROADCAST-STYLE VERTICAL NEWS VIDEO GENERATOR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

SCRIPT_FILE = BASE_DIR / "data" / "script.json"
OUTPUT_DIR = BASE_DIR / "output"

VIDEO_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

BG = (7, 16, 29)
BG2 = (12, 28, 47)
WHITE = (245, 248, 252)
LIGHT = (190, 202, 216)
MUTED = (120, 142, 163)
RED = (220, 40, 48)
RED_DARK = (115, 24, 32)
BLUE = (25, 76, 125)
CYAN = (45, 170, 205)
GREEN = (52, 170, 105)
GOLD = (225, 174, 62)
BLACK = (2, 6, 12)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

REGULAR_FONT = (
    FONT_DIR / "DejaVuSans.ttf"
)

BOLD_FONT = (
    FONT_DIR / "DejaVuSans-Bold.ttf"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command, check=True):
    print("RUN:", " ".join(map(str, command)))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def load_script():

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            f"Missing {SCRIPT_FILE}"
        )

    with open(
        SCRIPT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def font(size, bold=False):

    path = BOLD_FONT if bold else REGULAR_FONT

    if path.exists():
        return ImageFont.truetype(
            str(path),
            size
        )

    return ImageFont.load_default()


def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    text = text.replace(
        "Road lenght",
        "Road length"
    )

    text = text.replace(
        "road lenght",
        "road length"
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def wrap_text(
    draw,
    text,
    fnt,
    max_width
):

    words = clean_text(text).split()

    lines = []
    current = ""

    for word in words:

        test = (
            f"{current} {word}"
        ).strip()

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=fnt
        )

        width = bbox[2] - bbox[0]

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

    line_height = (
        fnt.getbbox("Ag")[3]
        - fnt.getbbox("Ag")[1]
        + spacing
    )

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill
        )

        y += line_height

    return y


def gradient_background():

    image = Image.new(
        "RGB",
        (VIDEO_WIDTH, VIDEO_HEIGHT)
    )

    pixels = image.load()

    for y in range(VIDEO_HEIGHT):

        ratio = y / VIDEO_HEIGHT

        r = int(
            BG[0] * (1 - ratio)
            + BG2[0] * ratio
        )

        g = int(
            BG[1] * (1 - ratio)
            + BG2[1] * ratio
        )

        b = int(
            BG[2] * (1 - ratio)
            + BG2[2] * ratio
        )

        for x in range(VIDEO_WIDTH):
            pixels[x, y] = (
                r,
                g,
                b
            )

    return image


def add_brand_header(
    draw,
    section,
    category="DEVELOPMENT"
):

    draw.rectangle(
        (0, 0, VIDEO_WIDTH, 155),
        fill=BLACK
    )

    draw.text(
        (55, 38),
        "RIFT VALLEY WATCH",
        font=font(40, True),
        fill=WHITE
    )

    draw.text(
        (55, 91),
        section.upper(),
        font=font(23, True),
        fill=RED
    )

    category_text = clean_text(
        category
    ).upper()

    bbox = draw.textbbox(
        (0, 0),
        category_text,
        font=font(22, True)
    )

    badge_width = (
        bbox[2] - bbox[0] + 46
    )

    draw.rounded_rectangle(
        (
            VIDEO_WIDTH - badge_width - 45,
            45,
            VIDEO_WIDTH - 45,
            92
        ),
        radius=22,
        fill=RED_DARK,
        outline=RED,
        width=2
    )

    draw.text(
        (
            VIDEO_WIDTH
            - badge_width
            - 22,
            57
        ),
        category_text,
        font=font(22, True),
        fill=WHITE
    )


def add_footer(
    draw,
    source,
    date
):

    draw.rectangle(
        (
            0,
            VIDEO_HEIGHT - 100,
            VIDEO_WIDTH,
            VIDEO_HEIGHT
        ),
        fill=BLACK
    )

    source = clean_text(source)

    draw.text(
        (50, VIDEO_HEIGHT - 78),
        f"SOURCE: {source}",
        font=font(21, True),
        fill=LIGHT
    )

    draw.text(
        (
            VIDEO_WIDTH - 280,
            VIDEO_HEIGHT - 78
        ),
        clean_text(date),
        font=font(21),
        fill=MUTED
    )


def add_red_line(
    draw,
    y,
    width=360
):

    draw.rectangle(
        (
            55,
            y,
            55 + width,
            y + 8
        ),
        fill=RED
    )


# ============================================================
# STORY HELPERS
# ============================================================

def get_fact(
    script,
    label
):

    for fact in script.get(
        "verified_facts",
        []
    ):

        if str(
            fact.get("label", "")
        ).upper() == label.upper():

            return clean_text(
                fact.get("value", "")
            )

    return ""


def get_section(
    script,
    key
):

    return clean_text(
        script.get(
            "sections",
            {}
        ).get(
            key,
            ""
        )
    )


def story_meta(script):

    return (
        clean_text(
            script.get(
                "source",
                {}
            ).get(
                "name",
                "Official Source"
            )
        ),
        clean_text(
            script.get(
                "date",
                ""
            )
        ),
        clean_text(
            script.get(
                "category",
                "NEWS"
            )
        )
    )


# ============================================================
# SCENE 1 — BREAKING HOOK
# ============================================================

def create_hook_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "THE LATEST",
        category
    )

    draw.text(
        (60, 245),
        "DEVELOPMENT",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        305,
        300
    )

    title = clean_text(
        script.get(
            "title",
            ""
        )
    )

    draw_wrapped(
        draw,
        title,
        60,
        390,
        font(64, True),
        WHITE,
        VIDEO_WIDTH - 120,
        18
    )

    county = clean_text(
        script.get(
            "county",
            ""
        )
    )

    draw.rounded_rectangle(
        (60, 1050, 600, 1140),
        radius=18,
        fill=RED
    )

    draw.text(
        (88, 1074),
        county.upper(),
        font=font(32, True),
        fill=WHITE
    )

    draw.text(
        (60, 1270),
        "VERIFIED DEVELOPMENT UPDATE",
        font=font(26, True),
        fill=CYAN
    )

    draw.text(
        (60, 1330),
        "Tracking verified developments across the region.",
        font=font(28),
        fill=LIGHT
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 2 — PROJECT / LOCATION
# ============================================================

def create_location_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "WHERE IT IS",
        category
    )

    county = clean_text(
        script.get(
            "county",
            ""
        )
    )

    location = get_fact(
        script,
        "LOCATION"
    )

    project = get_fact(
        script,
        "PROJECT"
    )

    draw.text(
        (60, 235),
        "LOCATION",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        290,
        230
    )

    # Stylized county map panel.
    draw.rounded_rectangle(
        (55, 380, 1025, 1060),
        radius=35,
        fill=(10, 31, 50),
        outline=(43, 77, 103),
        width=3
    )

    # Abstract Kenya silhouette / regional locator.
    points = [
        (470, 460),
        (560, 430),
        (640, 485),
        (680, 570),
        (645, 660),
        (690, 760),
        (620, 875),
        (530, 920),
        (450, 835),
        (430, 735),
        (385, 650),
        (420, 550)
    ]

    draw.polygon(
        points,
        fill=(21, 53, 76),
        outline=CYAN
    )

    # Bomet locator.
    cx = 525
    cy = 675

    for radius in (
        80,
        55,
        30
    ):

        draw.ellipse(
            (
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius
            ),
            outline=RED,
            width=4
        )

    draw.ellipse(
        (
            cx - 12,
            cy - 12,
            cx + 12,
            cy + 12
        ),
        fill=RED
    )

    draw.text(
        (700, 620),
        county.upper(),
        font=font(36, True),
        fill=WHITE
    )

    draw.text(
        (700, 680),
        "PROJECT AREA",
        font=font(23, True),
        fill=RED
    )

    draw_wrapped(
        draw,
        location,
        700,
        730,
        font(28),
        LIGHT,
        280,
        10
    )

    draw.text(
        (60, 1120),
        "PROJECT",
        font=font(25, True),
        fill=RED
    )

    draw_wrapped(
        draw,
        project,
        60,
        1170,
        font(32, True),
        WHITE,
        VIDEO_WIDTH - 120,
        12
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 3 — KEY DATA
# ============================================================

def create_data_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "KEY FACTS",
        category
    )

    length = get_fact(
        script,
        "ROAD_LENGTH"
    )

    cost = get_fact(
        script,
        "COST"
    )

    status = get_fact(
        script,
        "STATUS"
    )

    draw.text(
        (60, 235),
        "THE NUMBERS",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        290,
        250
    )

    # 65 KM card.
    draw.rounded_rectangle(
        (55, 375, 1025, 680),
        radius=32,
        fill=(11, 39, 61),
        outline=BLUE,
        width=3
    )

    draw.text(
        (90, 425),
        "ROAD LENGTH",
        font=font(25, True),
        fill=CYAN
    )

    draw.text(
        (90, 480),
        length or "Not specified",
        font=font(76, True),
        fill=WHITE
    )

    # Cost card.
    draw.rounded_rectangle(
        (55, 725, 1025, 1030),
        radius=32,
        fill=(35, 28, 32),
        outline=RED_DARK,
        width=3
    )

    draw.text(
        (90, 775),
        "PROJECT COST",
        font=font(25, True),
        fill=RED
    )

    draw.text(
        (90, 830),
        cost or "Not specified",
        font=font(70, True),
        fill=WHITE
    )

    # Status strip.
    draw.rounded_rectangle(
        (55, 1080, 1025, 1280),
        radius=25,
        fill=(17, 48, 38),
        outline=GREEN,
        width=3
    )

    draw.text(
        (90, 1120),
        "STATUS",
        font=font(23, True),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        status or "Status not specified",
        90,
        1170,
        font(30, True),
        WHITE,
        880,
        8
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 4 — ROUTE / CONTEXT
# ============================================================

def create_route_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "THE ROUTE",
        category
    )

    project = get_fact(
        script,
        "PROJECT"
    )

    context = get_section(
        script,
        "context"
    )

    draw.text(
        (60, 235),
        "PROJECT CORRIDOR",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        290,
        310
    )

    # Route visualization.
    x1 = 120
    x2 = 930
    y = 600

    draw.line(
        (x1, y, x2, y),
        fill=(60, 84, 104),
        width=18
    )

    # Red progress/route line.
    draw.line(
        (x1, y, 720, y),
        fill=RED,
        width=18
    )

    nodes = [
        (150, "KYOGONG"),
        (330, "SIGOR"),
        (510, "CHEBUNYO"),
        (690, "KIPRERES"),
        (880, "LONGISA")
    ]

    for x, label in nodes:

        draw.ellipse(
            (
                x - 18,
                y - 18,
                x + 18,
                y + 18
            ),
            fill=WHITE,
            outline=RED,
            width=5
        )

        draw.text(
            (x - 55, y + 45),
            label,
            font=font(19, True),
            fill=LIGHT
        )

    draw.text(
        (60, 800),
        "ROUTE",
        font=font(24, True),
        fill=CYAN
    )

    draw_wrapped(
        draw,
        project,
        60,
        850,
        font(32, True),
        WHITE,
        VIDEO_WIDTH - 120,
        12
    )

    draw.text(
        (60, 1110),
        "EDITORIAL NOTE",
        font=font(24, True),
        fill=RED
    )

    draw_wrapped(
        draw,
        context,
        60,
        1160,
        font(29),
        LIGHT,
        VIDEO_WIDTH - 120,
        10
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 5 — IMPACT
# ============================================================

def create_impact_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "WHY IT MATTERS",
        category
    )

    impact = get_section(
        script,
        "impact"
    )

    draw.text(
        (60, 245),
        "EXPECTED IMPACT",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        300,
        300
    )

    # Large quotation-style visual.
    draw.text(
        (65, 420),
        "“",
        font=font(170, True),
        fill=RED
    )

    draw_wrapped(
        draw,
        impact,
        115,
        520,
        font(43, True),
        WHITE,
        VIDEO_WIDTH - 180,
        16
    )

    draw.rounded_rectangle(
        (60, 1160, 1020, 1370),
        radius=25,
        fill=(13, 37, 55),
        outline=BLUE,
        width=2
    )

    draw.text(
        (95, 1200),
        "VERIFIED REPORTING",
        font=font(23, True),
        fill=CYAN
    )

    draw_wrapped(
        draw,
        "Impact is presented only from information "
        "confirmed in the source material.",
        95,
        1250,
        font(28),
        LIGHT,
        870,
        8
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 6 — SOURCE
# ============================================================

def create_source_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    add_brand_header(
        draw,
        "SOURCE",
        category
    )

    source_url = clean_text(
        script.get(
            "source",
            {}
        ).get(
            "url",
            ""
        )
    )

    statement = script.get(
        "official_statement",
        {}
    )

    speaker = clean_text(
        statement.get(
            "speaker",
            ""
        )
    )

    draw.text(
        (60, 250),
        "REPORTING SOURCE",
        font=font(30, True),
        fill=RED
    )

    add_red_line(
        draw,
        305,
        280
    )

    draw.rounded_rectangle(
        (55, 410, 1025, 760),
        radius=30,
        fill=(12, 37, 56),
        outline=CYAN,
        width=3
    )

    draw.text(
        (95, 470),
        source,
        font=font(42, True),
        fill=WHITE
    )

    draw.text(
        (95, 555),
        "OFFICIAL SOURCE",
        font=font(25, True),
        fill=CYAN
    )

    draw.text(
        (95, 630),
        date,
        font=font(30, True),
        fill=LIGHT
    )

    if speaker:

        draw.text(
            (60, 870),
            "OFFICIAL STATEMENT",
            font=font(26, True),
            fill=RED
        )

        draw_wrapped(
            draw,
            f"{speaker} provided the cited official "
            "statement associated with this report.",
            60,
            925,
            font(30),
            LIGHT,
            VIDEO_WIDTH - 120,
            10
        )

    if source_url:

        draw.text(
            (60, 1190),
            "SOURCE LINK",
            font=font(24, True),
            fill=CYAN
        )

        draw_wrapped(
            draw,
            source_url,
            60,
            1240,
            font(22),
            LIGHT,
            VIDEO_WIDTH - 120,
            8
        )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# SCENE 7 — OUTRO
# ============================================================

def create_outro_card(
    script,
    output
):

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    source, date, category = story_meta(
        script
    )

    draw.rectangle(
        (0, 0, VIDEO_WIDTH, VIDEO_HEIGHT),
        fill=BLACK
    )

    # Broadcast accent.
    draw.rectangle(
        (0, 0, 22, VIDEO_HEIGHT),
        fill=RED
    )

    draw.text(
        (75, 610),
        "RIFT VALLEY",
        font=font(66, True),
        fill=WHITE
    )

    draw.text(
        (75, 700),
        "WATCH",
        font=font(96, True),
        fill=RED
    )

    draw.rectangle(
        (75, 830, 620, 838),
        fill=WHITE
    )

    draw_wrapped(
        draw,
        "Tracking verified developments "
        "across the region.",
        75,
        910,
        font(42),
        LIGHT,
        850,
        14
    )

    draw.text(
        (75, 1190),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=font(29, True),
        fill=WHITE
    )

    draw.text(
        (75, 1260),
        "NEWS • DEVELOPMENT • COMMUNITY",
        font=font(23, True),
        fill=MUTED
    )

    add_footer(
        draw,
        source,
        date
    )

    image.save(
        output,
        quality=95
    )


# ============================================================
# CREATE STILL SCENES
# ============================================================

def create_scenes(
    script,
    scene_dir
):

    scene_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    scenes = [
        (
            "01_hook.png",
            create_hook_card
        ),
        (
            "02_location.png",
            create_location_card
        ),
        (
            "03_data.png",
            create_data_card
        ),
        (
            "04_route.png",
            create_route_card
        ),
        (
            "05_impact.png",
            create_impact_card
        ),
        (
            "06_source.png",
            create_source_card
        ),
        (
            "07_outro.png",
            create_outro_card
        )
    ]

    paths = []

    for index, (
        filename,
        function
    ) in enumerate(scenes, 1):

        print(
            f"[SCENE {index}/{len(scenes)}] "
            f"Creating {filename}"
        )

        path = scene_dir / filename

        function(
            script,
            path
        )

        paths.append(path)

    return paths


# ============================================================
# TEXT TO SPEECH
# ============================================================

def create_narration(
    script,
    output
):

    text = clean_text(
        script.get(
            "full_script",
            ""
        )
    )

    if not text:

        raise RuntimeError(
            "No full_script found in script.json."
        )

    print(
        f"Narration words: {len(text.split())}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(output)
    )

    if not output.exists():
        raise RuntimeError(
            "Narration file was not created."
        )


# ============================================================
# IMAGE TO VIDEO
# ============================================================

def still_to_video(
    image,
    output,
    duration
):

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image),

        "-t",
        f"{duration:.3f}",

        "-vf",
        (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-an",

        str(output)
    ]

    run_command(command)


# ============================================================
# GET AUDIO DURATION
# ============================================================

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
            str(path)
        ]
    )

    return float(
        result.stdout.strip()
    )


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(
    video_files,
    output
):

    if not video_files:
        raise RuntimeError(
            "No scene videos supplied."
        )

    inputs = []

    for video in video_files:

        inputs.extend(
            [
                "-i",
                str(video)
            ]
        )

    filter_parts = []

    for index in range(
        len(video_files)
    ):

        filter_parts.append(
            f"[{index}:v]"
            "settb=AVTB,"
            "setpts=PTS-STARTPTS,"
            f"fps={FPS},"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
            f"[v{index}]"
        )

    concat_inputs = "".join(
        f"[v{index}]"
        for index in range(
            len(video_files)
        )
    )

    filter_parts.append(
        concat_inputs
        + f"concat=n={len(video_files)}:v=1:a=0"
        "[vout]"
    )

    command = [
        "ffmpeg",
        "-y"
    ]

    command.extend(inputs)

    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),

            "-map",
            "[vout]",

            "-r",
            str(FPS),

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-pix_fmt",
            "yuv420p",

            "-movflags",
            "+faststart",

            str(output)
        ]
    )

    run_command(command)


# ============================================================
# AUDIO NORMALIZATION + FINAL MIX
# ============================================================

def add_narration(
    video,
    narration,
    output
):

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(video),

        "-i",
        str(narration),

        "-filter_complex",
        (
            "[1:a]"
            "loudnorm="
            "I=-16:"
            "TP=-1.5:"
            "LRA=11,"
            "aresample=48000"
            "[voice]"
        ),

        "-map",
        "0:v:0",

        "-map",
        "[voice]",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "48000",

        "-shortest",

        "-movflags",
        "+faststart",

        str(output)
    ]

    run_command(command)


# ============================================================
# CAPTION TIMING
# ============================================================

def split_caption_text(
    text
):

    sentences = re.split(
        r"(?<=[.!?])\s+",
        clean_text(text)
    )

    sentences = [
        s.strip()
        for s in sentences
        if s.strip()
    ]

    return sentences


def escape_drawtext(text):

    text = text.replace(
        "\\",
        "\\\\"
    )

    text = text.replace(
        ":",
        "\\:"
    )

    text = text.replace(
        "'",
        "\\'"
    )

    text = text.replace(
        "%",
        "\\%"
    )

    return text


# ============================================================
# BURN CAPTIONS
# ============================================================

def burn_captions(
    video,
    script,
    output
):

    narration = clean_text(
        script.get(
            "full_script",
            ""
        )
    )

    sentences = split_caption_text(
        narration
    )

    if not sentences:

        shutil.copy2(
            video,
            output
        )

        return

    duration = get_duration(
        video
    )

    total_words = sum(
        len(sentence.split())
        for sentence in sentences
    )

    if total_words <= 0:

        shutil.copy2(
            video,
            output
        )

        return

    filters = []

    current_time = 0.0

    for sentence in sentences:

        words = len(
            sentence.split()
        )

        segment_duration = (
            duration
            * words
            / total_words
        )

        start = current_time
        end = (
            current_time
            + segment_duration
        )

        safe = escape_drawtext(
            sentence
        )

        filters.append(
            "drawtext="
            f"fontfile={BOLD_FONT}:"
            f"text='{safe}':"
            "fontcolor=white:"
            "fontsize=42:"
            "line_spacing=8:"
            "box=1:"
            "boxcolor=black@0.78:"
            "boxborderw=22:"
            "x=(w-text_w)/2:"
            "y=h-280:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )

        current_time = end

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(video),

        "-vf",
        ",".join(filters),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "copy",

        "-movflags",
        "+faststart",

        str(output)
    ]

    run_command(command)


# ============================================================
# FINAL QC
# ============================================================

def validate_video(
    path
):

    if not path.exists():

        raise RuntimeError(
            "QC FAILED: output MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100000:

        raise RuntimeError(
            "QC FAILED: output MP4 is suspiciously small."
        )

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",

            "-show_entries",
            "stream=codec_type,width,height,codec_name",

            "-show_entries",
            "format=duration,size",

            "-of",
            "json",

            str(path)
        ]
    )

    try:
        info = json.loads(
            result.stdout
        )
    except json.JSONDecodeError:

        raise RuntimeError(
            "QC FAILED: ffprobe returned invalid JSON."
        )

    streams = info.get(
        "streams",
        []
    )

    video_stream = None
    audio_stream = None

    for stream in streams:

        if stream.get(
            "codec_type"
        ) == "video":

            video_stream = stream

        elif stream.get(
            "codec_type"
        ) == "audio":

            audio_stream = stream

    if video_stream is None:

        raise RuntimeError(
            "QC FAILED: video stream missing."
        )

    if audio_stream is None:

        raise RuntimeError(
            "QC FAILED: audio stream missing."
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

    if width != VIDEO_WIDTH or height != VIDEO_HEIGHT:

        raise RuntimeError(
            "QC FAILED: expected "
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}, "
            f"got {width}x{height}."
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

    if duration < 5:

        raise RuntimeError(
            "QC FAILED: video duration is too short."
        )

    print()
    print("=" * 60)
    print("FINAL VIDEO QC")
    print("=" * 60)
    print(
        f"Video stream: PASS"
    )
    print(
        f"Audio stream: PASS"
    )
    print(
        f"Resolution: {width}x{height} PASS"
    )
    print(
        f"Duration: {duration:.2f}s PASS"
    )
    print(
        f"File size: {size / 1024 / 1024:.2f} MB PASS"
    )
    print("=" * 60)


# ============================================================
# MAIN PIPELINE
# ============================================================

def main():

    print("=" * 70)
    print("RIFT VALLEY WATCH V3 VIDEO GENERATOR")
    print("=" * 70)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    script = load_script()

    title = clean_text(
        script.get(
            "title",
            ""
        )
    )

    print()
    print("TITLE:")
    print(title)

    print()
    print("WORD COUNT:")
    print(
        script.get(
            "word_count",
            "unknown"
        )
    )

    with tempfile.TemporaryDirectory(
        dir=str(OUTPUT_DIR)
    ) as temp:

        temp_dir = Path(
            temp
        )

        scene_dir = (
            temp_dir
            / "scenes"
        )

        video_scene_dir = (
            temp_dir
            / "scene_videos"
        )

        video_scene_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        narration_file = (
            temp_dir
            / "narration.mp3"
        )

        concatenated = (
            temp_dir
            / "concatenated.mp4"
        )

        narrated = (
            temp_dir
            / "narrated.mp4"
        )

        captioned = (
            temp_dir
            / "captioned.mp4"
        )

        # ----------------------------------------------------
        # 1. CREATE VISUAL SCENES
        # ----------------------------------------------------

        print()
        print(
            "[1/6] Creating broadcast visual scenes..."
        )

        images = create_scenes(
            script,
            scene_dir
        )

        # ----------------------------------------------------
        # 2. CREATE NARRATION
        # ----------------------------------------------------

        print()
        print(
            "[2/6] Creating narration..."
        )

        create_narration(
            script,
            narration_file
        )

        narration_duration = get_duration(
            narration_file
        )

        print(
            f"Narration duration: "
            f"{narration_duration:.2f}s"
        )

        # ----------------------------------------------------
        # 3. CALCULATE SCENE TIMELINE
        # ----------------------------------------------------

        print()
        print(
            "[3/6] Building scene timeline..."
        )

        weights = [
            0.13,
            0.14,
            0.15,
            0.16,
            0.16,
            0.14,
            0.12
        ]

        if len(weights) != len(images):

            raise RuntimeError(
                "Scene weight count does not match image count."
            )

        weight_total = sum(
            weights
        )

        durations = [
            narration_duration
            * weight
            / weight_total
            for weight in weights
        ]

        scene_names = [
            "LATEST",
            "LOCATION",
            "KEY FACTS",
            "ROUTE",
            "WHY IT MATTERS",
            "SOURCE",
            "OUTRO"
        ]

        current = 0.0

        for name, duration in zip(
            scene_names,
            durations
        ):

            print(
                f"  {name:<18} "
                f"{current:7.2f}s - "
                f"{current + duration:7.2f}s "
                f"({duration:.2f}s)"
            )

            current += duration

        # ----------------------------------------------------
        # 4. RENDER INDIVIDUAL SCENES
        # ----------------------------------------------------

        print()
        print(
            "[4/6] Rendering scene videos..."
        )

        video_files = []

        for index, (
            image,
            duration
        ) in enumerate(
            zip(
                images,
                durations
            ),
            1
        ):

            output = (
                video_scene_dir
                / f"scene_{index:02d}.mp4"
            )

            still_to_video(
                image,
                output,
                duration
            )

            video_files.append(
                output
            )

        # ----------------------------------------------------
        # 5. CONCAT + NARRATION + CAPTIONS
        # ----------------------------------------------------

        print()
        print(
            "[5/6] Assembling final video..."
        )

        concatenate_scenes(
            video_files,
            concatenated
        )

        add_narration(
            concatenated,
            narration_file,
            narrated
        )

        burn_captions(
            narrated,
            script,
            captioned
        )

        # ----------------------------------------------------
        # 6. FINAL OUTPUT
        # ----------------------------------------------------

        print()
        print(
            "[6/6] Finalizing and running QC..."
        )

        shutil.copy2(
            captioned,
            VIDEO_FILE
        )

    validate_video(
        VIDEO_FILE
    )

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH V3 COMPLETE")
    print("=" * 70)
    print(
        f"OUTPUT: {VIDEO_FILE}"
    )
    print()
    print(
        "READY FOR GITHUB ARTIFACT UPLOAD."
    )


if __name__ == "__main__":
    main()
