import json
import subprocess
import sys
import shutil
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME REGIONAL NEWS VIDEO GENERATOR
# V2 - REAL PHOTO / BROADCAST NEWS STYLE
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
REPORT_FILE = ROOT / "data" / "visual_report.json"

SOURCE_DIR = ROOT / "assets" / "source"

OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

OPENER_DURATION = 4
STORY_DURATION = 9
OUTRO_DURATION = 4

MAX_STORIES = 10


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SCENES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):

    if bold:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            str(ROOT / "fonts" / "DejaVuSans-Bold.ttf"),
        ]

    else:

        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            str(ROOT / "fonts" / "DejaVuSans.ttf"),
        ]

    for candidate in candidates:

        path = Path(candidate)

        if path.exists():

            try:
                return ImageFont.truetype(
                    str(path),
                    size
                )
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# JSON
# ============================================================

def load_story_data():

    if not STORY_FILE.exists():

        raise RuntimeError(
            "data/story.json was not found."
        )

    with open(
        STORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def is_story(item):

    if not isinstance(item, dict):
        return False

    keys = {
        "title",
        "headline",
        "description",
        "summary",
        "narration",
        "county",
        "category",
        "source",
        "url",
        "published",
        "score",
    }

    return (
        len(
            keys.intersection(
                item.keys()
            )
        ) >= 2
    )


def find_stories(data):

    found = []

    if isinstance(data, dict):

        if is_story(data):
            found.append(data)

        for value in data.values():

            found.extend(
                find_stories(value)
            )

    elif isinstance(data, list):

        for value in data:

            found.extend(
                find_stories(value)
            )

    return found


def get_stories(data):

    raw_stories = find_stories(data)

    unique = []
    seen = set()

    for story in raw_stories:

        identifier = (
            story.get("url")
            or story.get("title")
            or story.get("headline")
            or story.get("description")
            or ""
        )

        identifier = (
            str(identifier)
            .strip()
            .lower()
        )

        if not identifier:

            identifier = str(
                len(unique)
            )

        if identifier in seen:
            continue

        seen.add(identifier)
        unique.append(story)

    return unique[:MAX_STORIES]


# ============================================================
# TEXT
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def text_width(draw, text, font):

    box = draw.textbbox(
        (0, 0),
        str(text),
        font=font
    )

    return box[2] - box[0]


def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = str(
        text or ""
    ).split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        test = (
            current
            + " "
            + word
        )

        if (
            text_width(
                draw,
                test,
                font
            )
            <= max_width
        ):

            current = test

        else:

            lines.append(current)
            current = word

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
    max_lines=4,
    gap=8
):

    lines = wrap_text(
        draw,
        text,
        font,
        max_width
    )

    if len(lines) > max_lines:

        lines = lines[:max_lines]

        lines[-1] = (
            lines[-1].rstrip(".")
            + "..."
        )

    box = font.getbbox("Ag")

    line_height = (
        box[3]
        - box[1]
    )

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += (
            line_height
            + gap
        )

    return y


# ============================================================
# PHOTOS
# ============================================================

def get_photo_path(story):

    keys = [
        "image_path",
        "photo_path",
        "image_file",
        "photo_file",
    ]

    for key in keys:

        value = story.get(key)

        if not value:
            continue

        value = str(value)

        candidates = [
            ROOT / value,
            Path(value),
            SOURCE_DIR / Path(value).name,
        ]

        for path in candidates:

            try:
                if (
                    path.exists()
                    and path.is_file()
                ):
                    return path
            except Exception:
                pass

    return None


def load_photo(path):

    if path is None:
        return None

    try:

        image = Image.open(path)

        image.load()

        return image.convert(
            "RGB"
        )

    except Exception as exc:

        log(
            "PHOTO WARNING: "
            + str(path)
            + " -> "
            + str(exc)
        )

        return None


def crop_photo(
    image,
    width,
    height
):

    if image is None:
        return None

    source_ratio = (
        image.width
        / image.height
    )

    target_ratio = (
        width
        / height
    )

    if source_ratio > target_ratio:

        new_height = image.height

        new_width = int(
            image.height
            * target_ratio
        )

    else:

        new_width = image.width

        new_height = int(
            image.width
            / target_ratio
        )

    left = max(
        0,
        (
            image.width
            - new_width
        )
        // 2
    )

    top = max(
        0,
        (
            image.height
            - new_height
        )
        // 2
    )

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height
        )
    )

    return image.resize(
        (
            width,
            height
        ),
        Image.Resampling.LANCZOS
    )


# ============================================================
# BRANDING
# ============================================================

def draw_header(draw):

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            96
        ),
        fill=(8, 11, 17)
    )

    draw.rectangle(
        (
            0,
            0,
            14,
            96
        ),
        fill=(220, 35, 45)
    )

    logo_font = get_font(
        30,
        True
    )

    draw.text(
        (
            38,
            28
        ),
        "RIFT VALLEY WATCH",
        font=logo_font,
        fill=(255, 255, 255)
    )

    small_font = get_font(
        21,
        True
    )

    label = "REGIONAL NEWS"

    tw = text_width(
        draw,
        label,
        small_font
    )

    draw.text(
        (
            WIDTH - tw - 38,
            34
        ),
        label,
        font=small_font,
        fill=(180, 187, 197)
    )


def draw_footer(draw):

    y = HEIGHT - 74

    draw.rectangle(
        (
            0,
            y,
            WIDTH,
            HEIGHT
        ),
        fill=(7, 10, 15)
    )

    font = get_font(
        20,
        True
    )

    draw.text(
        (
            38,
            y + 25
        ),
        "RIFT VALLEY WATCH",
        font=font,
        fill=(170, 177, 188)
    )


def draw_county(
    draw,
    county
):

    if not county:
        return

    county = str(
        county
    ).upper()

    font = get_font(
        25,
        True
    )

    tw = text_width(
        draw,
        county,
        font
    )

    draw.rounded_rectangle(
        (
            38,
            125,
            38 + tw + 40,
            180
        ),
        radius=7,
        fill=(220, 35, 45)
    )

    draw.text(
        (
            58,
            138
        ),
        county,
        font=font,
        fill=(255, 255, 255)
    )


# ============================================================
# OPENER
# ============================================================

def create_opener():

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (9, 12, 18)
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.rectangle(
        (
            0,
            0,
            15,
            HEIGHT
        ),
        fill=(220, 35, 45)
    )

    for y in range(
        250,
        1650,
        120
    ):

        draw.line(
            (
                60,
                y,
                WIDTH - 60,
                y
            ),
            fill=(27, 32, 41),
            width=2
        )

    small_font = get_font(
        34,
        True
    )

    title_font = get_font(
        92,
        True
    )

    subtitle_font = get_font(
        32,
        True
    )

    draw.text(
        (
            70,
            610
        ),
        "RIFT VALLEY",
        font=small_font,
        fill=(205, 211, 220)
    )

    draw.text(
        (
            65,
            670
        ),
        "WATCH",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw.rectangle(
        (
            70,
            795,
            400,
            803
        ),
        fill=(220, 35, 45)
    )

    draw.text(
        (
            70,
            850
        ),
        "REGIONAL NEWS BULLETIN",
        font=subtitle_font,
        fill=(185, 192, 202)
    )

    draw.text(
        (
            70,
            910
        ),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(
            23,
            True
        ),
        fill=(130, 138, 149)
    )

    draw_footer(draw)

    path = (
        SCENES_DIR
        / "opener.png"
    )

    image.save(
        path,
        "PNG"
    )

    return path


# ============================================================
# STORY IMAGE
# ============================================================

def create_story_image(
    story,
    number
):

    photo_path = get_photo_path(
        story
    )

    photo = load_photo(
        photo_path
    )

    canvas = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (10, 14, 20)
    )

    # --------------------------------------------------------
    # PHOTO BACKGROUND
    # --------------------------------------------------------

    if photo is not None:

        background = crop_photo(
            photo,
            WIDTH,
            HEIGHT
        )

        # Keep the photo recognizable while creating room
        # for readable broadcast graphics.
        background = background.filter(
            ImageFilter.GaussianBlur(3)
        )

        canvas.paste(
            background,
            (0, 0)
        )

        overlay = Image.new(
            "RGBA",
            (
                WIDTH,
                HEIGHT
            ),
            (0, 0, 0, 80)
        )

        canvas = Image.alpha_composite(
            canvas.convert("RGBA"),
            overlay
        ).convert("RGB")

    else:

        # Professional fallback if an article has no usable photo.
        canvas = Image.new(
            "RGB",
            (
                WIDTH,
                HEIGHT
            ),
            (12, 16, 23)
        )

        draw_bg = ImageDraw.Draw(
            canvas
        )

        for y in range(
            200,
            HEIGHT,
            100
        ):

            draw_bg.line(
                (
                    0,
                    y,
                    WIDTH,
                    y
                ),
                fill=(27, 32, 41),
                width=2
            )

    draw = ImageDraw.Draw(
        canvas,
        "RGBA"
    )

    # --------------------------------------------------------
    # BROADCAST DARK GRADIENT / LOWER THIRD
    # --------------------------------------------------------

    lower = Image.new(
        "RGBA",
        (
            WIDTH,
            960
        ),
        (4, 7, 12, 0)
    )

    lower_draw = ImageDraw.Draw(
        lower,
        "RGBA"
    )

    for y in range(
        960
    ):

        alpha = int(
            15
            + (
                205
                * y
                / 960
            )
        )

        lower_draw.line(
            (
                0,
                y,
                WIDTH,
                y
            ),
            fill=(4, 7, 12, alpha)
        )

    canvas = canvas.convert(
        "RGBA"
    )

    canvas.alpha_composite(
        lower,
        (
            0,
            HEIGHT - 960
        )
    )

    draw = ImageDraw.Draw(
        canvas,
        "RGBA"
    )

    # --------------------------------------------------------
    # TOP HEADER
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            100
        ),
        fill=(7, 10, 15, 235)
    )

    draw.rectangle(
        (
            0,
            0,
            15,
            100
        ),
        fill=(220, 35, 45, 255)
    )

    logo_font = get_font(
        29,
        True
    )

    draw.text(
        (
            40,
            30
        ),
        "RIFT VALLEY WATCH",
        font=logo_font,
        fill=(255, 255, 255, 255)
    )

    live_font = get_font(
        20,
        True
    )

    live = "LATEST"

    tw = text_width(
        draw,
        live,
        live_font
    )

    draw.rounded_rectangle(
        (
            WIDTH - tw - 70,
            27,
            WIDTH - 35,
            70
        ),
        radius=5,
        fill=(220, 35, 45, 255)
    )

    draw.text(
        (
            WIDTH - tw - 52,
            35
        ),
        live,
        font=live_font,
        fill=(255, 255, 255, 255)
    )

    # --------------------------------------------------------
    # COUNTY BADGE
    # --------------------------------------------------------

    county = clean_text(
        story.get("county")
        or "RIFT VALLEY"
    )

    draw_county(
        draw,
        county
    )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    category = clean_text(
        story.get("category")
        or "NEWS"
    ).upper()

    category_font = get_font(
        24,
        True
    )

    draw.text(
        (
            40,
            205
        ),
        category,
        font=category_font,
        fill=(230, 235, 242, 255)
    )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    headline = clean_text(
        story.get("title")
        or story.get("headline")
        or "Rift Valley News Update"
    )

    headline_font = get_font(
        64,
        True
    )

    headline_y = 1170

    headline_y = draw_wrapped(
        draw,
        headline,
        40,
        headline_y,
        headline_font,
        (255, 255, 255, 255),
        WIDTH - 80,
        max_lines=4,
        gap=12
    )

    # --------------------------------------------------------
    # SOURCE / DATE
    # --------------------------------------------------------

    source = clean_text(
        story.get("source")
        or "Rift Valley Watch"
    )

    published = clean_text(
        story.get("published")
        or ""
    )

    meta = source

    if published:
        meta += "  •  " + published

    meta_font = get_font(
        23,
        True
    )

    draw.text(
        (
            40,
            min(
                headline_y + 22,
                HEIGHT - 180
            )
        ),
        meta[:90],
        font=meta_font,
        fill=(200, 208, 218, 255)
    )

    # --------------------------------------------------------
    # STORY NUMBER
    # --------------------------------------------------------

    number_font = get_font(
        22,
        True
    )

    label = (
        "STORY "
        + str(number).zfill(2)
    )

    draw.text(
        (
            WIDTH - 180,
            HEIGHT - 125
        ),
        label,
        font=number_font,
        fill=(150, 158, 170, 255)
    )

    # --------------------------------------------------------
    # BOTTOM BRAND BAR
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            HEIGHT - 75,
            WIDTH,
            HEIGHT
        ),
        fill=(5, 8, 13, 245)
    )

    draw.text(
        (
            40,
            HEIGHT - 51
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            20,
            True
        ),
        fill=(175, 182, 192, 255)
    )

    # --------------------------------------------------------
    # REAL PHOTO INDICATOR
    # --------------------------------------------------------

    if photo_path is not None:

        draw.text(
            (
                WIDTH - 260,
                HEIGHT - 51
            ),
            "SOURCE PHOTO",
            font=get_font(
                18,
                True
            ),
            fill=(165, 173, 184, 255)
        )

    output_path = (
        SCENES_DIR
        / (
            "story_"
            + str(number).zfill(2)
            + ".png"
        )
    )

    canvas.convert(
        "RGB"
    ).save(
        output_path,
        "PNG",
        optimize=True
    )

    return output_path


# ============================================================
# OUTRO
# ============================================================

def create_outro():

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        (9, 12, 18)
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.rectangle(
        (
            0,
            0,
            15,
            HEIGHT
        ),
        fill=(220, 35, 45)
    )

    title_font = get_font(
        72,
        True
    )

    subtitle_font = get_font(
        30,
        True
    )

    draw.text(
        (
            65,
            650
        ),
        "RIFT VALLEY",
        font=subtitle_font,
        fill=(190, 198, 208)
    )

    draw.text(
        (
            60,
            705
        ),
        "WATCH",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw.rectangle(
        (
            65,
            815,
            410,
            823
        ),
        fill=(220, 35, 45)
    )

    draw.text(
        (
            65,
            870
        ),
        "STAY INFORMED",
        font=get_font(
            34,
            True
        ),
        fill=(215, 221, 229)
    )

    draw.text(
        (
            65,
            925
        ),
        "REGIONAL NEWS • RIFT VALLEY",
        font=get_font(
            23,
            True
        ),
        fill=(130, 138, 149)
    )

    draw_footer(draw)

    path = (
        SCENES_DIR
        / "outro.png"
    )

    image.save(
        path,
        "PNG"
    )

    return path


# ============================================================
# AUDIO
# ============================================================

def create_audio(
    text,
    output_path
):

    text = clean_text(text)

    if not text:

        return None

    try:

        if output_path.exists():
            output_path.unlink()

        tts = gTTS(
            text=text,
            lang="en",
            slow=False
        )

        tts.save(
            str(output_path)
        )

        if (
            output_path.exists()
            and output_path.stat().st_size > 1000
        ):

            return output_path

    except Exception as exc:

        log(
            "AUDIO WARNING: "
            + str(exc)
        )

    return None


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(path):

    if path is None:
        return 0.0

    if not path.exists():
        return 0.0

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0:

            return float(
                result.stdout.strip()
            )

    except Exception:
        pass

    return 0.0


# ============================================================
# VIDEO SCENE RENDERING
# ============================================================

def render_scene(
    image_path,
    output_path,
    duration,
    audio_path=None
):

    image_path = Path(
        image_path
    )

    output_path = Path(
        output_path
    )

    duration = max(
        1.0,
        float(duration)
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
    ]

    has_audio = (
        audio_path is not None
        and Path(audio_path).exists()
    )

    if has_audio:

        command += [
            "-i",
            str(audio_path),
        ]

    else:

        command += [
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]

    command += [
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        str(duration),
        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1"
        ),
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    log(
        "RUNNING: "
        + " ".join(
            str(x)
            for x in command
        )
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    log(result.stdout)

    if result.returncode != 0:

        raise RuntimeError(
            "FFmpeg failed while rendering scene: "
            + str(output_path)
        )

    if not output_path.exists():

        raise RuntimeError(
            "Scene was not created: "
            + str(output_path)
        )

    if output_path.stat().st_size < 10000:

        raise RuntimeError(
            "Scene is suspiciously small: "
            + str(output_path)
        )


# ============================================================
# FINAL ASSEMBLY
# ============================================================

def assemble_final(scene_files):

    if not scene_files:

        raise RuntimeError(
            "No scene files available for assembly."
        )

    if FINAL_VIDEO.exists():

        FINAL_VIDEO.unlink()

    temp_file = (
        OUTPUT_DIR
        / "rift_valley_watch_temp.mp4"
    )

    if temp_file.exists():
        temp_file.unlink()

    command = [
        "ffmpeg",
        "-y",
    ]

    for scene in scene_files:

        scene = Path(scene)

        if not scene.exists():

            raise RuntimeError(
                "Scene does not exist: "
                + str(scene)
            )

        command += [
            "-i",
            str(scene),
        ]

    filters = []

    for index in range(
        len(scene_files)
    ):

        video_label = (
            "v"
            + str(index)
        )

        audio_label = (
            "a"
            + str(index)
        )

        filters.append(
            (
                f"[{index}:v:0]"
                f"scale={WIDTH}:{HEIGHT}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,"
                f"fps={FPS},"
                f"format=yuv420p"
                f"[{video_label}]"
            )
        )

        filters.append(
            (
                f"[{index}:a:0]"
                f"aformat="
                f"sample_rates=44100:"
                f"channel_layouts=stereo,"
                f"aresample=44100"
                f"[{audio_label}]"
            )
        )

    concat_inputs = ""

    for index in range(
        len(scene_files)
    ):

        concat_inputs += (
            f"[v{index}]"
            f"[a{index}]"
        )

    filters.append(
        concat_inputs
        + (
            f"concat="
            f"n={len(scene_files)}:"
            f"v=1:"
            f"a=1"
        )
        + "[vout][aout]"
    )

    filter_complex = ";".join(
        filters
    )

    command += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
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
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(temp_file),
    ]

    log(
        "============================================================"
    )

    log(
        "ASSEMBLING FINAL MP4"
    )

    log(
        "============================================================"
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    log(result.stdout)

    if result.returncode != 0:

        raise RuntimeError(
            "FFmpeg failed during final assembly."
        )

    if not temp_file.exists():

        raise RuntimeError(
            "Final temporary MP4 was not created."
        )

    if temp_file.stat().st_size < 100000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    temp_file.replace(
        FINAL_VIDEO
    )

    log(
        "FINAL MP4 CREATED:"
    )

    log(
        str(FINAL_VIDEO)
    )


# ============================================================
# VIDEO VALIDATION
# ============================================================

def validate_final_video():

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100000:

        raise RuntimeError(
            "Final MP4 is too small: "
            + str(size)
            + " bytes"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,"
        "r_frame_rate,channels",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(FINAL_VIDEO)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "ffprobe could not inspect final MP4."
        )

    try:

        info = json.loads(
            result.stdout
        )

    except Exception:

        raise RuntimeError(
            "Could not parse ffprobe output."
        )

    streams = info.get(
        "streams",
        []
    )

    video_stream = None
    audio_stream = None

    for stream in streams:

        if (
            stream.get("codec_type")
            == "video"
        ):

            video_stream = stream

        if (
            stream.get("codec_type")
            == "audio"
        ):

            audio_stream = stream

    if video_stream is None:

        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio_stream is None:

        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    width = video_stream.get(
        "width"
    )

    height = video_stream.get(
        "height"
    )

    if width != WIDTH:

        raise RuntimeError(
            "Invalid video width: "
            + str(width)
        )

    if height != HEIGHT:

        raise RuntimeError(
            "Invalid video height: "
            + str(height)
        )

    duration = float(
        info.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
        or 0
    )

    log(
        "============================================================"
    )

    log(
        "FINAL VIDEO VALIDATION"
    )

    log(
        "============================================================"
    )

    log(
        "File: "
        + str(FINAL_VIDEO)
    )

    log(
        "Size: "
        + str(size)
        + " bytes"
    )

    log(
        "Resolution: "
        + str(width)
        + "x"
        + str(height)
    )

    log(
        "Duration: "
        + f"{duration:.2f}"
        + " seconds"
    )

    log(
        "Video codec: "
        + str(
            video_stream.get(
                "codec_name"
            )
        )
    )

    log(
        "Audio codec: "
        + str(
            audio_stream.get(
                "codec_name"
            )
        )
    )

    log(
        "FINAL MP4 VALIDATION PASSED"
    )


# ============================================================
# VISUAL REPORT
# ============================================================

def create_visual_report(
    stories,
    scene_files
):

    report = {
        "project": "Rift Valley Watch",
        "
