import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME REGIONAL NEWS VIDEO GENERATOR
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


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


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
        len(keys.intersection(item.keys()))
        >= 2
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

    return unique[:10]


# ============================================================
# TEXT
# ============================================================

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

        test = current + " " + word

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
        box[3] - box[1]
    )

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += line_height + gap

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
            Path(value)
        ]

        for path in candidates:

            if (
                path.exists()
                and path.is_file()
            ):

                return path

    return None


def load_photo(path):

    if path is None:
        return None

    try:

        image = Image.open(path)
        image.load()

        return image.convert("RGB")

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
        ) // 2
    )

    top = max(
        0,
        (
            image.height
            - new_height
        ) // 2
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
        (width, height),
        Image.Resampling.LANCZOS
    )


# ============================================================
# BRANDING
# ============================================================

def draw_header(draw):

    draw.rectangle(
        (0, 0, WIDTH, 96),
        fill=(8, 11, 17)
    )

    draw.rectangle(
        (0, 0, 14, 96),
        fill=(220, 35, 45)
    )

    logo_font = get_font(
        30,
        True
    )

    draw.text(
        (38, 28),
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
        (0, y, WIDTH, HEIGHT),
        fill=(7, 10, 15)
    )

    font = get_font(
        20,
        True
    )

    draw.text(
        (38, y + 25),
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
        (58, 138),
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
        (WIDTH, HEIGHT),
        (9, 12, 18)
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, 15, HEIGHT),
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
        (70, 610),
        "RIFT VALLEY",
        font=small_font,
        fill=(205, 211, 220)
    )

    draw.text(
        (65, 670),
        "WATCH",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw.rectangle(
        (70, 795, 400, 803),
        fill=(220, 35, 45)
    )

    draw.text(
        (70, 850),
        "REGIONAL NEWS BULLETIN",
        font=subtitle_font,
        fill=(185, 192, 202)
    )

    draw.text(
        (70, 910),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(
            23,
            True
        ),
        fill=(130, 138, 149)
    )

    draw_footer(draw)

    path = SCENES_DIR / "opener.png"

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
        (WIDTH, HEIGHT),
        (10, 14, 20)
    )

    if photo is not None:

        background = crop_photo(
            photo,
            WIDTH,
            HEIGHT
        )

        background = background.filter(
            ImageFilter.GaussianBlur(18)
        )

        dark = Image.new(
            "RGBA",
            (WIDTH, HEIGHT),
            (0, 0, 0, 150)
        )

        background = background.convert(
            "RGBA"
        )

        background.alpha_composite(
            dark
        )

        canvas = background.convert(
            "RGB"
        )

    draw = ImageDraw.Draw(
        canvas
    )

    draw_header(draw)

    county = story.get(
        "county",
        "RIFT VALLEY"
    )

    draw_county(
        draw,
        county
    )

    # --------------------------------------------------------
    # REAL SOURCE PHOTO
    # --------------------------------------------------------

    photo_top = 195
    photo_height = 800

    if photo is not None:

        main_photo = crop_photo(
            photo,
            WIDTH - 80,
            photo_height
        )

        canvas.paste(
            main_photo,
            (40, photo_top)
        )

        draw = ImageDraw.Draw(
            canvas
        )

        draw.rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_top
                + photo_height
            ),
            outline=(255, 255, 255),
            width=2
        )

    else:

        draw.rounded_rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_top
                + photo_height
            ),
            radius=10,
            fill=(28, 34, 43)
        )

        fallback_font = get_font(
            30,
            True
        )

        fallback = "RIFT VALLEY NEWS"

        tw = text_width(
            draw,
            fallback,
            fallback_font
        )

        draw.text(
            (
                (WIDTH - tw) // 2,
                560
            ),
            fallback,
            font=fallback_font,
            fill=(150, 158, 169)
        )

    # --------------------------------------------------------
    # NEWS PANEL
    # --------------------------------------------------------

    panel_top = 950

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            HEIGHT - 74
        ),
        fill=(6, 9, 15)
    )

    category = str(
        story.get(
            "category",
            "NEWS"
        )
    ).upper()

    category_font = get_font(
        25,
        True
    )

    draw.text(
        (
            40,
            panel_top + 38
        ),
        category,
        font=category_font,
        fill=(220, 35, 45)
    )

    title = (
        story.get("title")
        or story.get("headline")
        or "Rift Valley News Update"
    )

    title_font = get_font(
        48,
        True
    )

    draw_wrapped(
        draw,
        title,
        40,
        panel_top + 85,
        title_font,
        (255, 255, 255),
        WIDTH - 80,
        4,
        9
    )

    source = str(
        story.get(
            "source",
            "Source article"
        )
    )

    source_font = get_font(
        21,
        False
    )

    draw.text(
        (
            40,
            HEIGHT - 152
        ),
        "Source: " + source,
        font=source_font,
        fill=(155, 163, 174)
    )

    if photo_path is not None:

        draw.text(
            (
                40,
                HEIGHT - 116
            ),
            "PHOTO: SOURCE ARTICLE",
            font=get_font(
                18,
                True
            ),
            fill=(115, 123, 134)
        )

    number_font = get_font(
        26,
        True
    )

    number_text = f"{number:02d}"

    nw = text_width(
        draw,
        number_text,
        number_font
    )

    draw.text(
        (
            WIDTH - nw - 42,
            HEIGHT - 150
        ),
        number_text,
        font=number_font,
        fill=(155, 163, 174)
    )

    draw_footer(draw)

    path = (
        SCENES_DIR
        / f"story_{number:02d}.png"
    )

    canvas.save(
        path,
        "PNG"
    )

    return path, photo_path


# ============================================================
# OUTRO
# ============================================================

def create_outro():

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 12, 18)
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, 15, HEIGHT),
        fill=(220, 35, 45)
    )

    title_font = get_font(
        68,
        True
    )

    subtitle_font = get_font(
        30,
        True
    )

    title = "RIFT VALLEY WATCH"

    tw = text_width(
        draw,
        title,
        title_font
    )

    draw.text(
        (
            (WIDTH - tw) // 2,
            700
        ),
        title,
        font=title_font,
        fill=(255, 255, 255)
    )

    subtitle = (
        "MORE REGIONAL NEWS • MORE UPDATES"
    )

    sw = text_width(
        draw,
        subtitle,
        subtitle_font
    )

    draw.text(
        (
            (WIDTH - sw) // 2,
            815
        ),
        subtitle,
        font=subtitle_font,
        fill=(180, 187, 198)
    )

    draw.rectangle(
        (
            340,
            900,
            740,
            908
        ),
        fill=(220, 35, 45)
    )

    draw_footer(draw)

    path = SCENES_DIR / "outro.png"

    image.save(
        path,
        "PNG"
    )

    return path


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):

    existing = story.get(
        "narration"
    )

    if existing:

        return str(
            existing
        ).strip()

    county = story.get(
        "county",
        "the Rift Valley"
    )

    category = story.get(
        "category",
        "news"
    )

    title = (
        story.get("title")
        or story.get("headline")
        or ""
    )

    description = (
        story.get("description")
        or story.get("summary")
        or ""
    )

    parts = [
        "Rift Valley Watch.",
        str(county) + ".",
        str(category) + ".",
        str(title),
        str(description)
    ]

    return " ".join(
        part.strip()
        for part in parts
        if part.strip()
    )


def create_tts(
    text,
    number
):

    if not text:
        return None

    path = (
        AUDIO_DIR
        / f"story_{number:02d}.mp3"
    )

    try:

        log(
            "Creating narration for story "
            + str(number)
        )

        speech = gTTS(
            text=text,
            lang="en",
            slow=False
        )

        speech.save(
            str(path)
        )

        if (
            path.exists()
            and path.stat().st_size > 1000
        ):

            return path

    except Exception as exc:

        log(
            "TTS WARNING: "
            + str(exc)
        )

    return None


# ============================================================
# SCENE RENDERING
# ============================================================

def render_scene(
    image_path,
    output_path,
    duration,
    audio_path=None
):

    # --------------------------------------------------------
    # ALWAYS CREATE A VIDEO INPUT FIRST.
    # --------------------------------------------------------

    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(image_path)
    ]

    # --------------------------------------------------------
    # REAL NARRATION INPUT
    # --------------------------------------------------------

    if (
        audio_path is not None
        and audio_path.exists()
    ):

        command += [
            "-i",
            str(audio_path)
        ]

        audio_input = "1:a:0"

    # --------------------------------------------------------
    # SILENT AUDIO INPUT
    #
    # IMPORTANT:
    # anullsrc MUST appear before -map.
    # --------------------------------------------------------

    else:

        command += [
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100"
        ]

        audio_input = "1:a:0"

    # --------------------------------------------------------
    # MAP INPUTS
    # --------------------------------------------------------

    command += [
        "-map",
        "0:v:0",
        "-map",
        audio_input,
        "-t",
        str(duration),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1",
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
        str(output_path)
    ]

    log("")
    log(
        "FFMPEG SCENE COMMAND: "
        + output_path.name
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.returncode != 0:

        log(result.stdout)

        raise RuntimeError(
            "FFmpeg failed while creating "
            + output_path.name
        )

    if not output_path.exists():

        raise RuntimeError(
            "Scene was not created: "
            + output_path.name
        )

    if output_path.stat().st_size < 5000:

        raise RuntimeError(
            "Scene is too small: "
            + output_path.name
        )


# ============================================================
# SCENE INSPECTION
# ============================================================

def inspect_scene(path):

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,"
        "sample_rate,channels",
        "-of",
        "json",
        str(path)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.returncode != 0:
        return None

    try:

        return json.loads(
            result.stdout
        )

    except Exception:

        return None


# ============================================================
# CONCAT FILE
# ============================================================

def create_concat_file(
    scene_files
):

    path = OUTPUT_DIR / "concat.txt"

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        for scene in scene_files:

            absolute = str(
                scene.resolve()
            )

            absolute = absolute.replace(
                "'",
                "'\\''"
            )

            file.write(
                "file '"
                + absolute
                + "'\n"
            )

    return path


# ============================================================
# FINAL ASSEMBLY
# ============================================================

def assemble_final(
    scene_files
):

    concat_file = create_concat_file(
        scene_files
    )

    temp_file = (
        OUTPUT_DIR
        / "rift_valley_watch_temp.mp4"
    )

    if temp_file.exists():
        temp_file.unlink()

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    log("")
    log("=" * 70)
    log("ASSEMBLING FINAL MP4")
    log("=" * 70)

    command = [
        "ffmpeg",
        "-y",
       
