import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# STABLE V3 VIDEO GENERATOR
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

BG = (8, 13, 22)
CARD = (19, 28, 43)
WHITE = (245, 247, 250)
MUTED = (165, 175, 190)
RED = (220, 45, 55)
BLUE = (65, 130, 220)
GREEN = (45, 185, 115)
GOLD = (220, 170, 65)
GRID = (25, 35, 50)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_command(command, label):
    print()
    print("=" * 60)
    print(label)
    print("=" * 60)
    print("COMMAND:")
    print(" ".join(str(x) for x in command))
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
            f"{label} failed with exit code {result.returncode}"
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
            "FFmpeg/FFprobe is not installed or unavailable."
        )


def font(size, bold=False):
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

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def fact(story, label, default=""):
    for item in story.get("verified_facts", []):
        if clean(item.get("label", "")).upper() == label.upper():
            return clean(item.get("value", default))

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


def story_date(story):
    return clean(
        story.get(
            "date",
            ""
        )
    )


# ============================================================
# TEXT DRAWING
# ============================================================

def wrapped_lines(draw, text, fnt, max_width):
    words = clean(text).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word

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
    line_gap=14
):
    lines = wrapped_lines(
        draw,
        text,
        fnt,
        max_width
    )

    for line in lines:
        bbox = draw.textbbox(
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
            bbox[3] -
            bbox[1] +
            line_gap
        )

    return y


def centered_text(
    draw,
    text,
    y,
    fnt,
    fill
):
    bbox = draw.textbbox(
        (0, 0),
        text,
        font=fnt
    )

    width = bbox[2] - bbox[0]

    x = (WIDTH - width) // 2

    draw.text(
        (x, y),
        text,
        font=fnt,
        fill=fill
    )


# ============================================================
# BACKGROUND / BRANDING
# ============================================================

def background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG
    )

    draw = ImageDraw.Draw(image)

    # Subtle broadcast grid
    for y in range(120, HEIGHT, 100):
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=GRID,
            width=1
        )

    for x in range(0, WIDTH, 120):
        draw.line(
            [(x, 0), (x, HEIGHT)],
            fill=GRID,
            width=1
        )

    # Decorative vertical broadcast bars
    draw.rectangle(
        [0, 0, 16, HEIGHT],
        fill=RED
    )

    draw.rectangle(
        [16, 0, 22, HEIGHT],
        fill=(35, 45, 60)
    )

    return image


def header(image, section):
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        [22, 0, WIDTH, 125],
        fill=(5, 8, 14)
    )

    draw.rectangle(
        [22, 118, WIDTH, 126],
        fill=RED
    )

    draw.text(
        (55, 35),
        "RIFT VALLEY WATCH",
        font=font(35, True),
        fill=WHITE
    )

    draw.text(
        (55, 82),
        "VERIFIED REGIONAL DEVELOPMENTS",
        font=font(19),
        fill=MUTED
    )

    section = clean(section).upper()

    bbox = draw.textbbox(
        (0, 0),
        section,
        font=font(23, True)
    )

    section_width = bbox[2] - bbox[0]

    draw.text(
        (WIDTH - section_width - 55, 48),
        section,
        font=font(23, True),
        fill=MUTED
    )


def footer(image, story):
    draw = ImageDraw.Draw(image)

    draw.line(
        [(55, 1775), (1025, 1775)],
        fill=(60, 70, 85),
        width=2
    )

    draw.text(
        (55, 1810),
        "RIFT VALLEY WATCH",
        font=font(20, True),
        fill=MUTED
    )

    source = source_name(story)

    draw.text(
        (55, 1850),
        "SOURCE: " + source[:55],
        font=font(18),
        fill=MUTED
    )

    date = story_date(story)

    if date:
        bbox = draw.textbbox(
            (0, 0),
            date,
            font=font(18)
        )

        date_width = bbox[2] - bbox[0]

        draw.text(
            (1025 - date_width, 1850),
            date,
            font=font(18),
            fill=MUTED
        )


def section_label(draw, text, x, y, color=RED):
    draw.text(
        (x, y),
        clean(text).upper(),
        font=font(27, True),
        fill=color
    )


def card(draw, x1, y1, x2, y2):
    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=28,
        fill=CARD,
        outline=(40, 52, 70),
        width=2
    )


# ============================================================
# SCENE 1 — BREAKING / LATEST
# ============================================================

def scene_latest(story):
    image = background()
    header(image, "THE LATEST")

    draw = ImageDraw.Draw(image)

    section_label(
        draw,
        "DEVELOPMENT",
        60,
        190,
        RED
    )

    y = draw_wrapped(
        draw,
        story_title(story),
        60,
        275,
        font(63, True),
        WHITE,
        920,
        18
    )

    draw.line(
        [(60, y + 30), (1020, y + 30)],
        fill=RED,
        width=6
    )

    card(
        draw,
        60,
        y + 90,
        1020,
        1120
    )

    draw_wrapped(
        draw,
        clean(story.get("summary", "")),
        95,
        y + 145,
        font(31),
        WHITE,
        860,
        14
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 2 — LOCATION
# ============================================================

def scene_location(story):
    image = background()
    header(image, "WHERE IT IS")

    draw = ImageDraw.Draw(image)

    section_label(
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
        280,
        font(70, True),
        WHITE,
        900,
        16
    )

    card(
        draw,
        60,
        570,
        1020,
        930
    )

    section_label(
        draw,
        "LOCATION",
        95,
        630,
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
        705,
        font(43, True),
        WHITE,
        850,
        16
    )

    card(
        draw,
        60,
        1010,
        1020,
        1325
    )

    section_label(
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
        font(40, True),
        WHITE,
        850,
        14
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 3 — KEY NUMBERS
# ============================================================

def scene_facts(story):
    image = background()
    header(image, "KEY FACTS")

    draw = ImageDraw.Draw(image)

    section_label(
        draw,
        "AT A GLANCE",
        60,
        190,
        GOLD
    )

    # Road length
    card(
        draw,
        60,
        330,
        1020,
        720
    )

    draw.text(
        (100, 385),
        "ROAD LENGTH",
        font=font(27, True),
        fill=GOLD
    )

    draw.text(
        (100, 470),
        fact(story, "ROAD_LENGTH", "65 kilometres"),
        font=font(70, True),
        fill=WHITE
    )

    # Cost
    card(
        draw,
        60,
        780,
        1020,
        1170
    )

    draw.text(
        (100, 835),
        "PROJECT COST",
        font=font(27, True),
        fill=GOLD
    )

    draw.text(
        (100, 920),
        fact(story, "COST", "Not stated"),
        font=font(66, True),
        fill=WHITE
    )

    # Category
    card(
        draw,
        60,
        1230,
        1020,
        1510
    )

    draw.text(
        (100, 1280),
        "CATEGORY",
        font=font(27, True),
        fill=GOLD
    )

    draw.text(
        (100, 1360),
        clean(story.get("category", "DEVELOPMENT")).upper(),
        font=font(48, True),
        fill=WHITE
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 4 — ROUTE
# ============================================================

def scene_route(story):
    image = background()
    header(image, "PROJECT ROUTE")

    draw = ImageDraw.Draw(image)

    section_label(
        draw,
        "ROUTE",
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
        project = clean(
            story.get(
                "visuals",
                [{}]
            )[0].get(
                "description",
                "Road project"
            )
        )

    card(
        draw,
        60,
        300,
        1020,
        1200
    )

    draw_wrapped(
        draw,
        project,
        100,
        390,
        font(45, True),
        WHITE,
        840,
        18
    )

    # Route line
    route_y = 1320

    draw.line(
        [(120, route_y), (960, route_y)],
        fill=RED,
        width=8
    )

    points = [
        "KYOGONG",
        "KAPKESOSIO",
        "SIGOR",
        "CHEBUNYO"
    ]

    positions = [140, 365, 590, 815]

    for label, x in zip(points, positions):
        draw.ellipse(
            [x - 18, route_y - 18, x + 18, route_y + 18],
            fill=RED
        )

        centered_text(
            draw,
            label,
            route_y + 45,
            font(18, True),
            WHITE
        )

    footer(image, story)

    return image


# ============================================================
# SCENE 5 — IMPACT
# ============================================================

def scene_impact(story):
    image = background()
    header(image, "WHY IT MATTERS")

    draw = ImageDraw.Draw(image)

    section_label(
        draw,
        "EXPECTED IMPACT",
        60,
        190,
        GREEN
    )

    impact = fact(
        story,
        "IMPACT",
        clean(
            story.get(
                "summary",
                ""
            )
        )
    )

    card(
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
        font(46, True),
        WHITE,
        840,
        20
    )

    draw.line(
        [(100, 1060), (980, 1060)],
        fill=GREEN,
        width=5
    )

    draw.text(
        (100, 1110),
        "ECONOMIC POTENTIAL",
        font=font(30, True),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        "The county government says the project is expected to unlock economic potential in the area and wider Bomet County.",
        100,
        1170,
        font(29),
        MUTED,
        840,
        12
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 6 — OFFICIAL STATEMENT
# ============================================================

def scene_statement(story):
    image = background()
    header(image, "OFFICIAL STATEMENT")

    draw = ImageDraw.Draw(image)

    statement = story.get(
        "official_statement",
        {}
    )

    speaker = clean(
        statement.get(
            "speaker",
            "Official statement"
        )
    )

    quote = clean(
        statement.get(
            "quote",
            ""
        )
    )

    section_label(
        draw,
        "OFFICIAL STATEMENT",
        60,
        190,
        RED
    )

    card(
        draw,
        60,
        330,
        1020,
        1350
    )

    draw.text(
        (100, 410),
        "“",
        font=font(100, True),
        fill=RED
    )

    draw_wrapped(
        draw,
        quote,
        115,
        520,
        font(39, True),
        WHITE,
        820,
        18
    )

    draw.line(
        [(115, 1130), (965, 1130)],
        fill=(60, 70, 85),
        width=2
    )

    draw.text(
        (115, 1180),
        speaker,
        font=font(30, True),
        fill=WHITE
    )

    draw.text(
        (115, 1230),
        "OFFICIAL STATEMENT",
        font=font(20),
        fill=MUTED
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 7 — SOURCE
# ============================================================

def scene_source(story):
    image = background()
    header(image, "SOURCE")

    draw = ImageDraw.Draw(image)

    section_label(
        draw,
        "SOURCE & VERIFICATION",
        60,
        190,
        BLUE
    )

    card(
        draw,
        60,
        340,
        1020,
        1050
    )

    draw.text(
        (100, 420),
        "PRIMARY SOURCE",
        font=font(27, True),
        fill=BLUE
    )

    draw_wrapped(
        draw,
        source_name(story),
        100,
        500,
        font(45, True),
        WHITE,
        830,
        16
    )

    draw.text(
        (100, 690),
        "SOURCE TYPE",
        font=font(25, True),
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
        (100, 755),
        source_type,
        font=font(34, True),
        fill=GREEN
    )

    card(
        draw,
        60,
        1130,
        1020,
        1440
    )

    draw.text(
        (100, 1200),
        "VERIFIED REPORTING",
        font=font(27, True),
        fill=GREEN
    )

    draw_wrapped(
        draw,
        "Facts shown in this report are based on the supplied verified story record.",
        100,
        1270,
        font(28),
        WHITE,
        830,
        12
    )

    footer(image, story)

    return image


# ============================================================
# SCENE 8 — OUTRO
# ============================================================

def scene_outro(story):
    image = background()
    header(image, "RIFT VALLEY WATCH")

    draw = ImageDraw.Draw(image)

    centered_text(
        draw,
        "RIFT VALLEY",
        600,
        font(75, True),
        WHITE
    )

    centered_text(
        draw,
        "WATCH",
        700,
        font(90, True),
        RED
    )

    draw.line(
        [(180, 850), (900, 850)],
        fill=RED,
        width=7
    )

    centered_text(
        draw,
        "Tracking verified developments",
        930,
        font(35, True),
        WHITE
    )

    centered_text(
        draw,
        "across the Rift Valley region",
        990,
        font(31),
        MUTED
    )

    centered_text(
        draw,
        story_county(story),
        1160,
        font(32, True),
        BLUE
    )

    footer(image, story)

    return image


# ============================================================
# NARRATION
# ============================================================

def get_script_sections(script):
    sections = []

    preferred = [
        ("hook", "HOOK"),
        ("what_happened", "WHAT HAPPENED"),
        ("key_facts", "KEY FACTS"),
        ("context", "CONTEXT"),
        ("attribution", "ATTRIBUTION"),
        ("impact", "WHY IT MATTERS"),
        ("close", "CLOSE"),
    ]

    for key, label in preferred:
        value = script.get(key, "")

        if isinstance(value, list):
            value = " ".join(
                clean(x) for x in value
            )

        value = clean(value)

        if value:
            sections.append(
                (label, value)
            )

    if not sections:
        fallback = clean(
            script.get(
                "narration",
                ""
            )
        )

        if fallback:
            sections.append(
                ("REPORT", fallback)
            )

    return sections


def create_audio(text, path):
    text = clean(text)

    if not text:
        raise ValueError(
            f"Cannot create audio for empty text: {path}"
        )

    print(
        f"Creating narration: {path.name}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(str(path))

    if not path.exists():
        raise RuntimeError(
            f"Audio was not created: {path}"
        )

    if path.stat().st_size < 1000:
        raise RuntimeError(
            f"Audio file appears invalid: {path}"
        )


# ============================================================
# IMAGE -> VIDEO
# ============================================================

def render_scene(image_path, audio_path, output_path):
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
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
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

        str(output_path)
    ]

    run_command(
        command,
        f"RENDERING {output_path.name}"
    )


# ============================================================
# FINAL CONCATENATION
# ============================================================

def concatenate_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files available for final MP4."
        )

    print()
    print("=" * 60)
    print("FINAL MP4 CONCATENATION")
    print("=" * 60)

    inputs = []

    for path in scene_files:
        inputs.extend(
            [
                "-i",
                str(path)
            ]
        )

    filter_parts = []

    for index in range(len(scene_files)):
        filter_parts.append(
            f"[{index}:v:0]"
            "setpts=PTS-STARTPTS,"
            f"scale={WIDTH}:{HEIGHT},"
            "setsar=1"
            f"[v{index}]"
        )

        filter_parts.append(
            f"[{index}:a:0]"
            "asetpts=PTS-STARTPTS,"
            "aresample=44100"
            f"[a{index}]"
        )

    concat_inputs = ""

    for index in range(len(scene_files)):
        concat_inputs += (
            f"[v{index}][a{index}]"
        )

    filter_parts.append(
        concat_inputs
        + f"concat=n={len(scene_files)}:v=1:a=1"
        "[vout][aout]"
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
            "[vout]",

            "-map",
            "[aout]",

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
            "FFmpeg completed but final MP4 does not exist."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 exists but is suspiciously small."
        )


# ============================================================
# MP4 VALIDATION
# ============================================================

def validate_mp4():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Validation failed: MP4 does not exist."
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
    print("=" * 60)
    print("MP4 QUALITY CONTROL")
    print("=" * 60)
    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not validate the final MP4."
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
        if stream.get("codec_type") == "video":
            video = stream

        elif stream.get("codec_type") == "audio":
            audio = stream

    errors = []

    if video is None:
        errors.append(
            "No video stream found."
        )

    if audio is None:
        errors.append(
            "No audio stream found."
        )

    if duration <= 1:
        errors.append(
            "Video duration is too short."
        )

    if size < 10000:
        errors.append(
            "MP4 file is too small."
        )

    if video:
        if video.get("codec_name") != "h264":
            errors.append(
                "Video codec is not H.264."
            )

        if int(video.get("width", 0)) != WIDTH:
            errors.append(
                f"Video width is not {WIDTH}."
            )

        if int(video.get("height", 0)) != HEIGHT:
            errors.append(
                f"Video height is not {HEIGHT}."
            )

    if audio:
        if audio.get("codec_name") != "aac":
            errors.append(
                "Audio codec is not AAC."
            )

    if errors:
        print()
        print("QC FAILED:")

        for error in errors:
            print(
                " - " + error
            )

        raise RuntimeError(
            "Final MP4 failed quality control."
        )

    print()
    print("QC PASSED")
    print(
        f"Duration: {duration:.2f} seconds"
    )
    print(
        f"Size: {size / 1024 / 1024:.2f} MB"
    )
    print(
        f"Resolution: {WIDTH}x{HEIGHT}"
    )
    print("Video: H.264")
    print("Audio: AAC")


# ============================================================
# VISUAL REPORT
# ============================================================

def write_visual_report(story, script, scene_files):
    report = {
        "project": "Rift Valley Watch",
        "generator": "Stable V3",
        "output": str(
            OUTPUT_FILE.relative_to(ROOT)
        ),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "scene_count": len(scene_files),
        "source": source_name(story),
        "source_url": source_url(story),
        "date": story_date(story),
        "title": story_title(story),
        "ready_for_publish": True,
        "verified_story": True
    }

    path = OUTPUT_DIR / "visual_report.json"

    with open(
        path,
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
        f"Visual report written: {path}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V3")
    print("STABLE VIDEO GENERATOR")
    print("=" * 60)

    check_ffmpeg()

    story = load_json(
        STORY_FILE
    )

    script = load_json(
        SCRIPT_FILE
    )

    print()
    print("STORY:")
    print(
        story_title(story)
    )

    print(
        "COUNTY:",
        story_county(story)
    )

    print(
        "SOURCE:",
        source_name(story)
    )

    sections = get_script_sections(
        script
    )

    if not sections:
        raise RuntimeError(
            "No usable narration sections found in data/script.json."
        )

    print()
    print(
        f"Narration sections: {len(sections)}"
    )

    # --------------------------------------------------------
    # CLEAN OUTPUT
    # --------------------------------------------------------

    if OUTPUT_DIR.exists():
        for item in OUTPUT_DIR.iterdir():
            if item.name != ".gitkeep":
                if item.is_dir():
                    shutil.rmtree(item)
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
    # SCENE DEFINITIONS
    # --------------------------------------------------------

    scenes = [
        (
            "01_latest",
            scene_latest
        ),
        (
            "02_location",
            scene_location
        ),
        (
            "03_facts",
            scene_facts
        ),
        (
            "04_route",
            scene_route
        ),
        (
            "05_impact",
            scene_impact
        ),
        (
            "06_statement",
            scene_statement
        ),
        (
            "07_source",
            scene_source
        ),
        (
            "08_outro",
            scene_outro
        )
    ]

    scene_files = []

    # --------------------------------------------------------
    # BUILD SCENES
    # --------------------------------------------------------

    for index, (scene_name, renderer) in enumerate(
        scenes,
        start=1
    ):
        print()
        print("=" * 60)
        print(
            f"SCENE {index}/{len(scenes)}: {scene_name}"
        )
        print("=" * 60)

        image_path = (
            SCENE_DIR /
            f"{scene_name}.png"
        )

        audio_path = (
            AUDIO_DIR /
            f"{scene_name}.mp3"
        )

        video_path = (
            SCENE_DIR /
            f"{scene_name}.mp4"
        )

        image = renderer(
            story
        )

        image.save(
            image_path,
            "PNG"
        )

        if not image_path.exists():
            raise RuntimeError(
                f"Scene image not created: {image_path}"
            )

        # Assign narration to scenes.
        # The last scene always gets a clean closing line.
        if index <= len(sections):
            narration = sections[index - 1][1]
        else:
            narration = ""

        if index == len(scenes):
            narration = (
                "This is Rift Valley Watch, "
                "tracking verified developments "
                "across the region."
            )

        if not narration:
            narration = (
                "Rift Valley Watch. "
                "Verified regional developments."
            )

        create_audio(
            narration,
            audio_path
        )

        render_scene(
            image_path,
            audio_path,
            video_path
        )

        if not video_path.exists():
            raise RuntimeError(
                f"Scene video was not created: {video_path}"
            )

        if video_path.stat().st_size < 10000:
            raise RuntimeError(
                f"Scene video is suspiciously small: {video_path}"
            )

        scene_files.append(
            video_path
        )

        print(
            f"SCENE READY: {video_path.name}"
        )

    # --------------------------------------------------------
    # FINAL MP4
    # --------------------------------------------------------

    concatenate_scenes(
        scene_files
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    validate_mp4()

    write_visual_report(
        story,
        script,
        scene_files
    )

    # --------------------------------------------------------
    # FINAL OUTPUT
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("SUCCESS")
    print("=" * 60)

    print(
        f"FINAL MP4: {OUTPUT_FILE}"
    )

    print(
        f"FILE SIZE: "
        f"{OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print()
    print(
        "RIFT VALLEY WATCH VIDEO GENERATION COMPLETE."
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        print()
        print("=" * 60)
        print("GENERATION FAILED")
        print("=" * 60)
        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
