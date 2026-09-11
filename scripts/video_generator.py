import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

ASSET_DIR = ROOT / "assets"
MUSIC_FILE = ASSET_DIR / "music" / "news_bed.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MAX_STORIES = 10


# ============================================================
# COLORS
# ============================================================

BG = (9, 14, 24)
PANEL = (18, 27, 42)
WHITE = (245, 248, 252)
MUTED = (165, 177, 194)
RED = (220, 45, 55)
BLUE = (45, 105, 210)


# ============================================================
# BASIC FUNCTIONS
# ============================================================

def clean(value):
    if value is None:
        return ""

    text = str(value)

    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&apos;", "'")

    return " ".join(text.split())


def load_json(path):
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run(command):
    print()
    print("RUNNING:")
    print(" ".join(str(x) for x in command))
    print()

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def font(size, bold=False):
    candidates = []

    if bold:
        candidates = [
            ROOT / "fonts" / "Inter-Bold.ttf",
            ROOT / "fonts" / "Montserrat-Bold.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
        ]
    else:
        candidates = [
            ROOT / "fonts" / "Inter-Regular.ttf",
            ROOT / "fonts" / "Montserrat-Regular.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
        ]

    for item in candidates:
        if item.exists():
            try:
                return ImageFont.truetype(
                    str(item),
                    size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


def text_width(draw, text, fnt):
    box = draw.textbbox(
        (0, 0),
        text,
        font=fnt,
    )
    return box[2] - box[0]


def wrap(draw, text, fnt, max_width):
    text = clean(text)

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = word

        if current:
            candidate = current + " " + word

        if text_width(
            draw,
            candidate,
            fnt,
        ) <= max_width:
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
    spacing=12,
):
    lines = wrap(
        draw,
        text,
        fnt,
        max_width,
    )

    box = fnt.getbbox("Ag")
    line_height = (
        box[3] - box[1] + spacing
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill,
        )
        y += line_height

    return y


# ============================================================
# OUTPUT PREPARATION
# ============================================================

def prepare():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    (ASSET_DIR / "music").mkdir(
        parents=True,
        exist_ok=True,
    )

    for folder in [
        SCENE_DIR,
        AUDIO_DIR,
    ]:
        for item in folder.glob("*"):
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass


# ============================================================
# DATA
# ============================================================

def get_stories(data):
    stories = data.get(
        "stories",
        [],
    )

    if isinstance(stories, list) and stories:
        return stories[:MAX_STORIES]

    # Legacy compatibility
    title = clean(
        data.get(
            "title",
            "",
        )
    )

    if not title:
        return []

    facts = data.get(
        "verified_facts",
        {},
    )

    description = ""

    if isinstance(facts, dict):
        values = []

        for key in [
            "LOCATION",
            "STATUS",
            "IMPACT",
        ]:
            if facts.get(key):
                values.append(
                    clean(facts[key])
                )

        description = " ".join(values)

    return [
        {
            "title": title,
            "county": clean(
                data.get(
                    "county",
                    "Rift Valley",
                )
            ),
            "category": clean(
                data.get(
                    "category",
                    "NEWS",
                )
            ),
            "description": description,
            "source": clean(
                data.get(
                    "source",
                    "",
                )
            ),
            "url": clean(
                data.get(
                    "source_url",
                    "",
                )
            ),
            "published": clean(
                data.get(
                    "date",
                    "",
                )
            ),
        }
    ]


# ============================================================
# BACKGROUND
# ============================================================

def background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(
            9 + (17 * ratio)
        )

        g = int(
            14 + (14 * ratio)
        )

        b = int(
            24 + (18 * ratio)
        )

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(r, g, b),
        )

    return image


# ============================================================
# HEADER
# ============================================================

def header(draw, label):
    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=RED,
    )

    logo = font(
        48,
        True,
    )

    small = font(
        24,
        True,
    )

    draw.text(
        (55, 50),
        "RIFT VALLEY",
        font=logo,
        fill=WHITE,
    )

    draw.text(
        (55, 108),
        "WATCH",
        font=logo,
        fill=RED,
    )

    draw.text(
        (55, 178),
        clean(label).upper(),
        font=small,
        fill=MUTED,
    )

    draw.ellipse(
        (875, 68, 902, 95),
        fill=RED,
    )

    draw.text(
        (915, 60),
        "LIVE",
        font=small,
        fill=WHITE,
    )


# ============================================================
# FOOTER
# ============================================================

def footer(draw, source=""):
    y = HEIGHT - 145

    draw.rectangle(
        (45, y, WIDTH - 45, HEIGHT - 45),
        fill=(12, 19, 30),
    )

    small = font(
        22,
        False,
    )

    draw.text(
        (70, y + 18),
        "RIFT VALLEY WATCH",
        font=small,
        fill=WHITE,
    )

    if source:
        draw.text(
            (70, y + 55),
            "Source: " + clean(source)[:70],
            font=small,
            fill=MUTED,
        )


# ============================================================
# OPENER
# ============================================================

def opener_image():
    image = background()
    draw = ImageDraw.Draw(image)

    header(
        draw,
        "LIVE REGIONAL BULLETIN",
    )

    title = font(
        76,
        True,
    )

    subtitle = font(
        34,
        False,
    )

    draw.rounded_rectangle(
        (55, 500, WIDTH - 55, 1160),
        radius=35,
        fill=PANEL,
    )

    draw.text(
        (95, 565),
        "LATEST",
        font=font(30, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        "RIFT VALLEY WATCH",
        95,
        650,
        title,
        WHITE,
        850,
        14,
    )

    draw_wrapped(
        draw,
        "Fresh developments from across "
        "Kenya's Rift Valley.",
        95,
        875,
        subtitle,
        MUTED,
        820,
        16,
    )

    draw.rectangle(
        (0, 1300, WIDTH, 1385),
        fill=RED,
    )

    draw.text(
        (55, 1323),
        "POLITICS  •  BUSINESS  •  DEVELOPMENT  •  COMMUNITY",
        font=font(27, True),
        fill=WHITE,
    )

    footer(
        draw,
        "Live news feeds",
    )

    return image


# ============================================================
# COVERAGE
# ============================================================

def coverage_image(counties, date):
    image = background()
    draw = ImageDraw.Draw(image)

    header(
        draw,
        "REGIONAL COVERAGE",
    )

    draw.text(
        (60, 315),
        "TODAY'S RIFT VALLEY",
        font=font(52, True),
        fill=WHITE,
    )

    draw.text(
        (60, 390),
        clean(date),
        font=font(30, False),
        fill=MUTED,
    )

    card_font = font(
        27,
        True,
    )

    for i, county in enumerate(counties[:12]):
        row = i // 2
        col = i % 2

        x = 60 + (col * 485)
        y = 500 + (row * 165)

        draw.rounded_rectangle(
            (
                x,
                y,
                x + 450,
                y + 125,
            ),
            radius=18,
            fill=PANEL,
        )

        draw.ellipse(
            (
                x + 25,
                y + 40,
                x + 58,
                y + 73,
            ),
            fill=RED,
        )

        draw.text(
            (x + 78, y + 30),
            clean(county).upper(),
            font=card_font,
            fill=WHITE,
        )

        draw.text(
            (x + 78, y + 70),
            "FRESH UPDATE",
            font=font(21, False),
            fill=MUTED,
        )

    footer(
        draw,
        "Rift Valley Watch",
    )

    return image


# ============================================================
# STORY
# ============================================================

def story_image(story, number, total):
    image = background()
    draw = ImageDraw.Draw(image)

    county = clean(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    category = clean(
        story.get(
            "category",
            "NEWS",
        )
    )

    title = clean(
        story.get(
            "title",
            "Regional Update",
        )
    )

    description = clean(
        story.get(
            "description",
            "",
        )
    )

    source = clean(
        story.get(
            "source",
            "",
        )
    )

    header(
        draw,
        category,
    )

    draw.text(
        (870, 180),
        f"{number:02d}/{total:02d}",
        font=font(23, True),
        fill=MUTED,
    )

    # Broadcast visual block.
    draw.rounded_rectangle(
        (45, 310, WIDTH - 45, 690),
        radius=30,
        fill=(22, 34, 53),
    )

    # Decorative newsroom grid.
    for x in range(90, 1000, 120):
        draw.line(
            (x, 340, x, 660),
            fill=(36, 53, 77),
            width=1,
        )

    for y in range(350, 680, 80):
        draw.line(
            (70, y, 1010, y),
            fill=(36, 53, 77),
            width=1,
        )

    draw.text(
        (85, 370),
        "REGIONAL UPDATE",
        font=font(25, True),
        fill=RED,
    )

    draw.text(
        (85, 425),
        county.upper(),
        font=font(48, True),
        fill=WHITE,
    )

    draw.text(
        (85, 500),
        category.upper(),
        font=font(27, True),
        fill=MUTED,
    )

    draw.text(
        (870, 400),
        "LIVE",
        font=font(30, True),
        fill=RED,
    )

    # Main story panel.
    draw.rounded_rectangle(
        (45, 750, WIDTH - 45, HEIGHT - 205),
        radius=32,
        fill=PANEL,
    )

    title_font = font(
        53,
        True,
    )

    body_font = font(
        30,
        False,
    )

    draw.text(
        (85, 810),
        "HEADLINE",
        font=font(24, True),
        fill=RED,
    )

    title_y = draw_wrapped(
        draw,
        title,
        85,
        870,
        title_font,
        WHITE,
        850,
        14,
    )

    body_y = max(
        title_y + 45,
        1200,
    )

    if description:
        draw_wrapped(
            draw,
            description[:500],
            85,
            body_y,
            body_font,
            MUTED,
            850,
            14,
        )

    footer(
        draw,
        source,
    )

    return image


# ============================================================
# EMPTY UPDATE
# ============================================================

def empty_image():
    image = background()
    draw = ImageDraw.Draw(image)

    header(
        draw,
        "LIVE REGIONAL UPDATE",
    )

    draw.text(
        (70, 620),
        "NO FRESH UPDATE",
        font=font(58, True),
        fill=WHITE,
    )

    draw_wrapped(
        draw,
        "No qualifying regional stories "
        "were retrieved during this automated run.",
        70,
        750,
        font(32, False),
        MUTED,
        850,
        15,
    )

    footer(
        draw,
        "Live news feeds",
    )

    return image


# ============================================================
# OUTRO
# ============================================================

def outro_image():
    image = background()
    draw = ImageDraw.Draw(image)

    header(
        draw,
        "END OF BULLETIN",
    )

    draw.text(
        (70, 650),
        "RIFT VALLEY",
        font=font(65, True),
        fill=WHITE,
    )

    draw.text(
        (70, 735),
        "WATCH",
        font=font(65, True),
        fill=RED,
    )

    draw_wrapped(
        draw,
        "Follow for fresh regional "
        "developments.",
        70,
        900,
        font(34, False),
        MUTED,
        820,
        15,
    )

    draw.rectangle(
        (70, 1090, 850, 1098),
        fill=RED,
    )

    footer(
        draw,
        "Rift Valley Watch",
    )

    return image


# ============================================================
# AUDIO
# ============================================================

def make_audio(text, path):
    text = clean(text)

    if not text:
        return False

    try:
        speech = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        speech.save(
            str(path)
        )

        return path.exists()

    except Exception as exc:
        print(
            "WARNING: TTS failed:",
            exc,
        )
        return False


def duration(path):
    result = subprocess.run(
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        return 5.0


# ============================================================
# RENDER SCENE
# ============================================================

def render_scene(
    image,
    narration,
    number,
):
    png = (
        SCENE_DIR
        / f"scene_{number:02d}.png"
    )

    silent = (
        SCENE_DIR
        / f"scene_{number:02d}_silent.mp4"
    )

    audio = (
        AUDIO_DIR
        / f"scene_{number:02d}.mp3"
    )

    final = (
        SCENE_DIR
        / f"scene_{number:02d}.mp4"
    )

    image.save(
        png,
        quality=95,
    )

    has_audio = make_audio(
        narration,
        audio,
    )

    if has_audio:
        length = duration(audio) + 0.7

        if length < 4:
            length = 4

        if length > 12:
            length = 12
    else:
        length = 5

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-t",
            f"{length:.2f}",
            "-r",
            str(FPS),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(silent),
        ]
    )

    if not has_audio:
        shutil.copy2(
            silent,
            final,
        )

        return final

    if MUSIC_FILE.exists():
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent),
                "-i",
                str(audio),
                "-stream_loop",
                "-1",
                "-i",
                str(MUSIC_FILE),
                "-filter_complex",
                (
                    "[1:a]volume=1.0[n];"
                    "[2:a]volume=0.10[m];"
                    "[n][m]"
                    "amix=inputs=2:"
                    "duration=first:"
                    "dropout_transition=2[a]"
                ),
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-t",
                f"{length:.2f}",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                str(final),
            ]
        )
    else:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent),
                "-i",
                str(audio),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-t",
                f"{length:.2f}",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                str(final),
            ]
        )

    return final


# ============================================================
# CONCATENATE
# ============================================================

def concatenate(files):
    if not files:
        raise RuntimeError(
            "No scenes were created."
        )

    list_file = (
        OUTPUT_DIR
        / "concat.txt"
    )

    with open(
        list_file,
        "w",
        encoding="utf-8",
    ) as f:

        for item in files:
            path = str(
                item.resolve()
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{path}'\n"
            )

    temp = (
        OUTPUT_DIR
        / "final_temp.mp4"
    )

    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp),
        ]
    )

    if not temp.exists():
        raise RuntimeError(
            "FFmpeg did not create final_temp.mp4."
        )

    if temp.stat().st_size < 10000:
        raise RuntimeError(
            "Generated MP4 is too small."
        )

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    temp.replace(
        OUTPUT_FILE
    )


# ============================================================
# VALIDATION
# ============================================================

def validate():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "output/rift_valley_watch.mp4 "
            "was not created."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 is smaller than 10 KB."
        )

    result = subprocess.run(
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
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Final MP4 failed ffprobe validation."
        )

    data = json.loads(
        result.stdout
    )

    streams = data.get(
        "streams",
        [],
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
            "Final MP4 has no video stream."
        )

    if audio is None:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    if video.get("width") != WIDTH:
        raise RuntimeError
