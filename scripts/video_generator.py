import json
import re
import html
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# PATHS / SETTINGS
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


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def run_command(command, allow_failure=False):
    command = [str(x) for x in command]

    print()
    print("=" * 70)
    print("RUNNING:")
    print(" ".join(command))
    print("=" * 70)

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0 and not allow_failure:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}:\n"
            + result.stdout[-5000:]
        )

    return result


def ensure_directories():
    for directory in [
        OUTPUT_DIR,
        SCENE_DIR,
        ASSET_DIR,
        AUDIO_DIR,
        SOURCE_DIR,
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True
        )


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required file does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file {path}: {exc}"
        )


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
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
            "NEWS"
        )
    ).upper()


def story_date(story):
    return clean_text(
        story.get(
            "date",
            ""
        )
    )


def fact(story, label, default=""):
    for item in story.get(
        "verified_facts",
        []
    ):
        if not isinstance(item, dict):
            continue

        if clean_text(
            item.get("label", "")
        ).upper() == label.upper():

            return clean_text(
                item.get(
                    "value",
                    default
                )
            )

    return clean_text(default)


def location(story):
    return fact(
        story,
        "LOCATION",
        story_county(story)
    )


def road_length(story):
    return fact(
        story,
        "ROAD_LENGTH",
        "Not stated"
    )


def cost(story):
    return fact(
        story,
        "COST",
        "Not stated"
    )


def status(story):
    return fact(
        story,
        "STATUS",
        "Not stated"
    )


def route(story):
    return fact(
        story,
        "PROJECT",
        "Not stated"
    )


def impact(story):
    return fact(
        story,
        "IMPACT",
        "Not stated"
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


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for font_path in candidates:
        if Path(font_path).exists():
            return ImageFont.truetype(
                font_path,
                size
            )

    return ImageFont.load_default()


# ============================================================
# TEXT DRAWING
# ============================================================

def wrapped_lines(
    draw,
    text,
    font,
    max_width
):
    words = clean_text(text).split()

    lines = []
    current = ""

    for word in words:
        test = (
            f"{current} {word}"
            .strip()
        )

        width = draw.textbbox(
            (0, 0),
            test,
            font=font
        )[2]

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
    width,
    font,
    fill=(245, 245, 245),
    spacing=14,
    max_lines=None
):
    lines = wrapped_lines(
        draw,
        text,
        font,
        width
    )

    if max_lines:
        lines = lines[:max_lines]

        if len(lines) == max_lines:
            if lines[-1] and not lines[-1].endswith("..."):
                lines[-1] = (
                    lines[-1].rstrip(".")
                    + "..."
                )

    bbox = font.getbbox("Ag")

    line_height = (
        bbox[3]
        - bbox[1]
        + spacing
    )

    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill
        )

        current_y += line_height

    return current_y


# ============================================================
# VISUAL DESIGN
# ============================================================

def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (7, 14, 28)
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(7 + 8 * ratio)
        g = int(14 + 10 * ratio)
        b = int(28 + 18 * ratio)

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
            fill=(22, 34, 55),
            width=1
        )

    for y in range(
        0,
        HEIGHT,
        90
    ):
        draw.line(
            (0, y, WIDTH, y),
            fill=(22, 34, 55),
            width=1
        )


def top_bar(
    draw,
    label="RIFT VALLEY WATCH"
):
    draw.rectangle(
        (0, 0, WIDTH, 120),
        fill=(5, 10, 21)
    )

    draw.rectangle(
        (0, 114, WIDTH, 120),
        fill=(205, 38, 48)
    )

    draw.text(
        (52, 36),
        clean_text(label),
        font=get_font(
            38,
            True
        ),
        fill=(245, 245, 248)
    )


def section(draw, title):
    draw.text(
        (55, 180),
        clean_text(title).upper(),
        font=get_font(
            30,
            True
        ),
        fill=(225, 55, 65)
    )


def footer(draw, story):
    text = story_county(story)

    if story_date(story):
        text += f"  |  {story_date(story)}"

    draw.text(
        (55, HEIGHT - 95),
        text,
        font=get_font(25),
        fill=(170, 180, 195)
    )


def source_badge(draw, story):
    draw.rounded_rectangle(
        (
            55,
            HEIGHT - 175,
            WIDTH - 55,
            HEIGHT - 120
        ),
        radius=15,
        fill=(20, 32, 50)
    )

    draw.text(
        (75, HEIGHT - 163),
        "SOURCE: " + source_name(story),
        font=get_font(
            22,
            True
        ),
        fill=(220, 225, 235)
    )


# ============================================================
# SCENE GRAPHICS
# ============================================================

def scene_latest(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "THE LATEST")

    draw_wrapped(
        draw,
        story_title(story),
        55,
        300,
        WIDTH - 110,
        get_font(68, True),
        max_lines=6,
        spacing=18
    )

    draw.text(
        (55, 1050),
        story_category(story),
        font=get_font(
            34,
            True
        ),
        fill=(225, 225, 230)
    )

    draw.text(
        (55, 1160),
        "SOURCE-LED REGIONAL REPORT",
        font=get_font(27, True),
        fill=(175, 185, 200)
    )

    footer(draw, story)

    return image


def scene_location(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "WHERE IT IS")

    draw.rounded_rectangle(
        (
            55,
            300,
            WIDTH - 55,
            1080
        ),
        radius=35,
        fill=(15, 29, 48),
        outline=(55, 70, 95),
        width=3
    )

    draw.text(
        (95, 390),
        story_county(story).upper(),
        font=get_font(
            52,
            True
        ),
        fill=(225, 55, 65)
    )

    draw_wrapped(
        draw,
        location(story),
        95,
        520,
        WIDTH - 190,
        get_font(58, True),
        max_lines=6,
        spacing=18
    )

    draw.text(
        (95, 1010),
        "VERIFIED STORY LOCATION",
        font=get_font(
            26,
            True
        ),
        fill=(170, 180, 195)
    )

    footer(draw, story)

    return image


def scene_facts(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "KEY FACTS")

    cards = [
        ("ROAD LENGTH", road_length(story)),
        ("PROJECT COST", cost(story)),
        ("STATUS", status(story)),
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
            font=get_font(
                27,
                True
            ),
            fill=(225, 55, 65)
        )

        draw_wrapped(
            draw,
            value,
            90,
            y + 110,
            WIDTH - 180,
            get_font(
                52,
                True
            ),
            max_lines=3,
            spacing=12
        )

        y += 390

    footer(draw, story)

    return image


def scene_route(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "THE ROUTE")

    draw.rounded_rectangle(
        (
            55,
            300,
            WIDTH - 55,
            1350
        ),
        radius=35,
        fill=(15, 29, 48),
        outline=(55, 70, 95),
        width=3
    )

    draw.text(
        (95, 370),
        "PROJECT",
        font=get_font(
            30,
            True
        ),
        fill=(225, 55, 65)
    )

    draw_wrapped(
        draw,
        route(story),
        95,
        465,
        WIDTH - 190,
        get_font(
            50,
            True
        ),
        max_lines=11,
        spacing=17
    )

    draw.text(
        (95, 1260),
        "ROUTE IDENTIFIED IN VERIFIED STORY",
        font=get_font(
            25,
            True
        ),
        fill=(170, 180, 195)
    )

    footer(draw, story)

    return image


def scene_impact(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "WHY IT MATTERS")

    draw_wrapped(
        draw,
        impact(story),
        65,
        330,
        WIDTH - 130,
        get_font(
            56,
            True
        ),
        max_lines=10,
        spacing=20
    )

    draw.text(
        (65, 1380),
        "EDITORIAL NOTE",
        font=get_font(
            28,
            True
        ),
        fill=(225, 55, 65)
    )

    draw_wrapped(
        draw,
        "This card uses only the impact stated in the verified story.",
        65,
        1445,
        WIDTH - 130,
        get_font(30),
        max_lines=4,
        spacing=12
    )

    footer(draw, story)

    return image


def scene_statement(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "OFFICIAL STATEMENT")

    speaker, quote = official_statement(story)

    if quote:
        draw.text(
            (65, 330),
            speaker or "Official source",
            font=get_font(
                38,
                True
            ),
            fill=(225, 55, 65)
        )

        draw_wrapped(
            draw,
            '"' + quote + '"',
            65,
            455,
            WIDTH - 130,
            get_font(48),
            max_lines=13,
            spacing=20
        )
    else:
        draw_wrapped(
            draw,
            "No separate official statement was provided in the verified story.",
            65,
            430,
            WIDTH - 130,
            get_font(46, True),
            max_lines=7,
            spacing=18
        )

    footer(draw, story)

    return image


def scene_source(story):
    image = create_background()
    draw = ImageDraw.Draw(image)

    add_grid(draw)
    top_bar(draw)
    section(draw, "SOURCE")

    draw.text(
        (65, 330),
        source_name(story),
        font=get_font(
            42,
            True
        ),
        fill=(240, 240, 245)
    )

    draw_wrapped(
        draw,
        source_url(story) or "Source URL not provided",
        65,
        450,
        WIDTH - 130,
        get_font(29),
        max_lines=8,
        spacing=15
    )

    draw.text(
        (65, 1080),
        "REPORT DATE",
        font=get_font(
            28,
            True
        ),
        fill=(225, 55, 65)
    )

    draw.text(
        (65, 1150),
        story_date(story) or "Not stated",
        font=get_font(
            48,
            True
        ),
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
        font=get_font(
            58,
            True
        ),
        fill=(225, 55, 65)
    )

    draw.text(
        (55, 610),
        "WATCH",
        font=get_font(
            100,
            True
        ),
        fill=(245, 245, 248)
    )

    draw_wrapped(
        draw,
        "Verified regional news. Clear facts. Source-led reporting.",
        55,
        800,
        WIDTH - 110,
        get_font(42),
        max_lines=5,
        spacing=14
    )

    draw.text(
        (55, 1260),
        "FOLLOW FOR MORE",
        font=get_font(
            35,
            True
        ),
        fill=(225, 55, 65)
    )

    footer(draw, story)

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    speaker, quote = official_statement(story)

    segments = [
        story_title(story),

        (
            f"The project is located in {location(story)}. "
            f"Construction status is {status(story)}."
        ),

        (
            f"Key figures: the project covers "
            f"{road_length(story)}, with a reported cost of "
            f"{cost(story)}."
        ),

        (
            f"The reported route is {route(story)}."
        ),

        (
            f"Why it matters: {impact(story)}."
        ),
    ]

    if quote:
        segments.append(
            f"{speaker or 'An official'} said: {quote}"
        )
    else:
        segments.append(
            "No separate official statement was provided in the verified story."
        )

    segments.append(
        f"This report is based on {source_name(story)}, "
        f"dated {story_date(story) or 'the reported date'}."
    )

    segments.append(
        "Rift Valley Watch. Verified regional news. Follow for more."
    )

    return [
        clean_text(x)
        for x in segments
        if clean_text(x)
    ]


def create_audio(text, index):
    path = AUDIO_DIR / f"segment_{index:02d}.mp3"

    if path.exists() and path.stat().st_size > 1000:
        print(f"Using existing audio: {path}")
        return path

    print()
    print("=" * 70)
    print(f"CREATING NARRATION {index}")
    print(text)
    print("=" * 70)

    try:
        tts = gTTS(
            text=text,
            lang="en",
            slow=False
        )

        tts.save(str(path))

    except Exception as exc:
        raise RuntimeError(
            f"gTTS failed for narration {index}: {exc}"
        )

    if not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(
            f"Audio file was not created correctly: {path}"
        )

    return path


def audio_duration(audio_path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
    )

    try:
        duration = float(
            result.stdout.strip()
        )
    except Exception:
        raise RuntimeError(
            f"Could not determine audio duration for {audio_path}"
        )

    if duration <= 0:
        raise RuntimeError(
            f"Invalid audio duration: {duration}"
        )

    return duration


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

    words = clean_text(text).split()

    groups = []

    for i in range(
        0,
        len(words),
        7
    ):
        groups.append(
            words[i:i + 7]
        )

    if not groups:
        groups = [[""]]

    total_words = sum(
        len(group)
        for group in groups
    )

    current = 0.0
    entries = []

    for index, group in enumerate(
        groups,
        start=1
    ):
        part = (
            duration
            * len(group)
            / max(total_words, 1)
        )

        start = current
        end = min(
            duration,
            current + part
        )

        current = end

        entries.extend(
            [
                str(index),
                f"{srt_time(start)} --> {srt_time(end)}",
                " ".join(group),
                ""
            ]
        )

    path.write_text(
        "\n".join(entries),
        encoding="utf-8"
    )

    return path


# ============================================================
# SCENE VIDEO CREATION
# ============================================================

def render_scene(
    image_path,
    audio_path,
    caption,
    scene_number
):
    duration = audio_duration(
        audio_path
    )

    srt_path = create_srt(
        caption,
        duration,
        scene_number
    )

    output = (
        SCENE_DIR
        / f"scene_{scene_number:02d}.mp4"
    )

    subtitle_path = (
        str(srt_path.resolve())
        .replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
    )

    subtitle_filter = (
        f"subtitles='{subtitle_path}':"
        "force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=22,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00101010,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=95'"
    )

    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:"
        "(ow-iw)/2:"
        "(oh-ih)/2,"
        "setsar=1,"
        + subtitle_filter
    )

    run_command(
        [
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
            video_filter,

            "-t",
            f"{duration:.3f}",

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

    if not output.exists():
        raise RuntimeError(
            f"Scene MP4 was not created: {output}"
        )

    if output.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene MP4 is suspiciously small: {output}"
        )

    print(
        f"SCENE CREATED: {output} "
        f"({output.stat().st_size:,} bytes)"
    )

    return output, duration, srt_path


# ============================================================
# CONCATENATION
# ============================================================

def concat_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files were generated."
        )

    print()
    print("=" * 70)
    print("FINAL VIDEO CONCATENATION")
    print("=" * 70)

    concat_file = (
        SCENE_DIR
        / "concat.txt"
    )

    lines = []

    for scene in scene_files:
        absolute = (
            Path(scene)
            .resolve()
            .as_posix()
        )

        escaped = absolute.replace(
            "'",
            "'\\''"
        )

        lines.append(
            f"file '{escaped}'"
        )

    concat_file.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    # First try stream-copy concat.
    copy_result = run_command(
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
            str(OUTPUT_FILE)
        ],
        allow_failure=True
    )

    if (
        copy_result.returncode == 0
        and OUTPUT_FILE.exists()
        and OUTPUT_FILE.stat().st_size > 50000
    ):
        print(
            "FINAL MP4 CREATED USING STREAM COPY"
        )
        return OUTPUT_FILE

    print(
        "Stream-copy concat failed."
    )

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    # Reliable fallback: re-encode concat.
    reencode_result = run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
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
            "-movflags",
            "+faststart",
            str(OUTPUT_FILE)
        ],
        allow_failure=True
    )

    if (
        reencode_result.returncode != 0
        or not OUTPUT_FILE.exists()
        or OUTPUT_FILE.stat().st_size < 50000
    ):
        raise RuntimeError(
            "FINAL MP4 CONCATENATION FAILED.\n"
            "No valid rift_valley_watch.mp4 was created."
        )

    print(
        "FINAL MP4 CREATED USING RE-ENCODE FALLBACK"
    )

    return OUTPUT_FILE


# ============================================================
# MP4 VALIDATION
# ============================================================

def validate_mp4(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 does not exist: {path}"
        )

    if path.stat().st_size < 50000:
        raise RuntimeError(
            f"Final MP4 is too small: {path.stat().st_size} bytes"
        )

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
            str(path)
        ]
    )

    try:
        info = json.loads(
            result.stdout
        )
    except Exception:
        raise RuntimeError(
            "FFprobe returned invalid JSON."
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

    if duration <= 0:
        raise RuntimeError(
            "Final MP4 has invalid duration."
        )

    streams = info.get(
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

    if not video_stream:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if not audio_stream:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
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
            f"Unexpected video dimensions: "
            f"{width}x{height}"
        )

    print()
    print("=" * 70)
    print("FINAL MP4 VALIDATION PASSED")
    print("=" * 70)
    print(f"FILE: {path}")
    print(f"SIZE: {path.stat().st_size:,} bytes")
    print(f"DURATION: {duration:.2f} seconds")
    print(f"VIDEO: {width}x{height}")
    print(
        f"VIDEO CODEC: "
        f"{video_stream.get('codec_name')}"
    )
    print(
        f"AUDIO CODEC: "
        f"{audio_stream.get('codec_name')}"
    )
    print("=" * 70)

    return {
        "path": str(path),
        "size": path.stat().st_size,
        "duration": duration,
        "width": width,
        "height": height,
        "video_codec": video_stream.get(
            "codec_name"
        ),
        "audio_codec": audio_stream.get(
            "codec_name"
        ),
    }


# ============================================================
# CLEANUP
# ============================================================

def clean_previous_output():
    print()
    print("=" * 70)
    print("CLEANING PREVIOUS GENERATED FILES")
    print("=" * 70)

    if SCENE_DIR.exists():
        for item in SCENE_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    # Old generated narration is deliberately removed so every
    # GitHub run gets fresh audio.
    if AUDIO_DIR.exists():
        for item in AUDIO_DIR.glob("segment_*.mp3"):
            try:
                item.unlink()
            except Exception:
                pass


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(story):
    return [
        (
            "latest",
            scene_latest,
            0
        ),
        (
            "location",
            scene_location,
            1
        ),
        (
            "facts",
            scene_facts,
            2
        ),
        (
            "route",
            scene_route,
            3
        ),
        (
            "impact",
            scene_impact,
            4
        ),
        (
            "statement",
            scene_statement,
            5
        ),
        (
            "source",
            scene_source,
            6
        ),
        (
            "outro",
            scene_outro,
            7
        ),
    ]


# ============================================================
# VISUAL REPORT
# ============================================================

def write_visual_report(
    story,
    scene_records,
    validation
):
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "project": "Rift Valley Watch V2",
        "title": story_title(story),
        "county": story_county(story),
        "category": story_category(story),
        "source": source_name(story),
        "source_url": source_url(story),
        "scene_count": len(scene_records),
        "scenes": scene_records,
        "final_video": validation,
        "quality_control": {
            "video_created": True,
            "audio_present": True,
            "resolution": f"{WIDTH}x{HEIGHT}",
            "fps": FPS,
            "source_attribution": True,
            "verified_story_data": True
        }
    }

    save_json(
        REPORT_FILE,
        report
    )

    print(
        f"Visual report written: {REPORT_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH V2 VIDEO GENERATOR")
    print("=" * 70)

    ensure_directories()

    print()
    print("[1/8] Loading story...")

    story = load_json(
        STORY_FILE
    )

    print(
        "TITLE:",
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

    print()
    print("[2/8] Loading generated script...")

    if SCRIPT_FILE.exists():
        script = load_json(
            SCRIPT_FILE
        )

        print(
            "Script loaded."
        )

        if script.get(
            "ready_for_video",
            True
        ) is False:
            raise RuntimeError(
                "Generated script is not marked ready_for_video."
            )
    else:
        script = {}

        print(
            "No script.json found. "
            "Using verified story data."
        )

    print()
    print("[3/8] Cleaning previous output...")

    clean_previous_output()

    ensure_directories()

    print()
    print("[4/8] Building narration...")

    narration = build_narration(
        story
    )

    print(
        f"NARRATION SEGMENTS: {len(narration)}"
    )

    audio_files = []

    for index, text in enumerate(
        narration,
        start=1
    ):
        audio_files.append(
            create_audio(
                text,
                index
            )
        )

    if not audio_files:
        raise RuntimeError(
            "No narration audio was created."
        )

    print()
    print("[5/8] Rendering scenes...")

    scene_plan = build_scene_plan(
        story
    )

    scene_files = []
    scene_records = []

    for scene_number, (
        scene_name,
        scene_function,
        narration_index
    ) in enumerate(
        scene_plan,
        start=1
    ):
        print()
        print("=" * 70)
        print(
            f"SCENE {scene_number}/{len(scene_plan)}: "
            f"{scene_name.upper()}"
        )
        print("=" * 70)

        image = scene_function(
            story
        )

        image_path = (
            SCENE_DIR
            / f"scene_{scene_number:02d}.png"
        )

        image.save(
            image_path,
            "PNG",
            optimize=True
        )

        if not image_path.exists():
            raise RuntimeError(
                f"Scene image was
