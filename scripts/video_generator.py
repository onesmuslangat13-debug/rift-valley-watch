import sys
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# V2 REAL PHOTO VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

SOURCE_DIR = ROOT / "assets" / "source"
OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"
VISUAL_REPORT = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

OPENER_SECONDS = 4
STORY_SECONDS = 8
OUTRO_SECONDS = 4

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/noto"),
    ROOT / "fonts",
]


# ============================================================
# LOGGING
# ============================================================

def log(text=""):
    print(text, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def looks_like_story(value):
    if not isinstance(value, dict):
        return False

    story_keys = [
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
    ]

    score = sum(
        1 for key in story_keys
        if key in value
    )

    return score >= 2


def recursively_find_stories(value, found=None):
    """
    Find story dictionaries anywhere inside story.json.

    This deliberately does not depend on one particular
    JSON structure.
    """

    if found is None:
        found = []

    if isinstance(value, dict):

        if looks_like_story(value):
            found.append(value)

        for key, child in value.items():

            # Avoid treating metadata as stories.
            if key in {
                "generated_at",
                "generated",
                "timestamp",
                "created",
                "updated",
                "count",
                "total",
                "status",
                "message",
                "metadata",
            }:
                continue

            recursively_find_stories(
                child,
                found,
            )

    elif isinstance(value, list):

        for child in value:
            recursively_find_stories(
                child,
                found,
            )

    return found


def extract_stories(data):
    """
    Extract actual news stories from any reasonable
    story.json structure.
    """

    # Direct list
    if isinstance(data, list):
        direct = [
            item
            for item in data
            if looks_like_story(item)
        ]

        if direct:
            return direct

    # Common containers first
    if isinstance(data, dict):

        preferred_keys = [
            "stories",
            "articles",
            "items",
            "news",
            "results",
            "selected_stories",
            "selected",
            "top_stories",
            "top_articles",
            "news_items",
            "bulletin",
            "data",
        ]

        for key in preferred_keys:
            value = data.get(key)

            if isinstance(value, list):
                direct = [
                    item
                    for item in value
                    if looks_like_story(item)
                ]

                if direct:
                    return direct

        # Recursive fallback
        recursive = recursively_find_stories(data)

        if recursive:
            return recursive

    return []


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):

    if bold:
        names = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Bold.ttf",
        ]
    else:
        names = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "NotoSans-Regular.ttf",
        ]

    for directory in FONT_DIRS:

        for name in names:

            path = directory / name

            if path.exists():

                try:
                    return ImageFont.truetype(
                        str(path),
                        size,
                    )
                except Exception:
                    pass

    return ImageFont.load_default()


def text_size(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        str(text),
        font=font,
    )

    return (
        box[2] - box[0],
        box[3] - box[1],
    )


def wrap_text(draw, text, font, max_width):

    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        candidate = current + " " + word

        width, _ = text_size(
            draw,
            candidate,
            font,
        )

        if width <= max_width:
            current = candidate
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
    spacing=10,
):

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    if len(lines) > max_lines:

        lines = lines[:max_lines]

        last = lines[-1]

        if not last.endswith("..."):
            lines[-1] = last.rstrip(".") + "..."

    box = font.getbbox("Ag")

    line_height = box[3] - box[1]

    for line in lines:

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        y += line_height + spacing

    return y


# ============================================================
# PHOTO
# ============================================================

def get_photo_path(story):

    possible_keys = [
        "image_path",
        "photo_path",
        "image_file",
        "photo_file",
        "image",
        "photo",
    ]

    for key in possible_keys:

        value = story.get(key)

        if not value:
            continue

        value = str(value)

        candidates = [
            ROOT / value,
            Path(value),
        ]

        for candidate in candidates:

            if candidate.exists() and candidate.is_file():
                return candidate

    return None


def load_photo(path):

    if path is None:
        return None

    try:

        with Image.open(path) as img:

            return img.convert("RGB")

    except Exception as exc:

        log(
            f"PHOTO WARNING: {path} -> {exc}"
        )

        return None


def crop_fill(image, width, height):

    if image is None:
        return None

    source_ratio = image.width / image.height
    target_ratio = width / height

    if source_ratio > target_ratio:

        new_height = image.height
        new_width = int(
            image.height * target_ratio
        )

    else:

        new_width = image.width
        new_height = int(
            image.width / target_ratio
        )

    left = max(
        0,
        (image.width - new_width) // 2,
    )

    top = max(
        0,
        (image.height - new_height) // 2,
    )

    cropped = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height,
        )
    )

    return cropped.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


def make_full_background(photo):

    if photo is None:

        return Image.new(
            "RGB",
            (WIDTH, HEIGHT),
            (14, 18, 25),
        )

    background = crop_fill(
        photo,
        WIDTH,
        HEIGHT,
    )

    background = background.filter(
        ImageFilter.GaussianBlur(18)
    )

    # Darken slightly
    dark = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 110),
    )

    background = background.convert(
        "RGBA"
    )

    background.alpha_composite(dark)

    return background.convert("RGB")


# ============================================================
# BRANDING
# ============================================================

def draw_header(draw):

    draw.rectangle(
        (0, 0, WIDTH, 92),
        fill=(8, 11, 17),
    )

    draw.rectangle(
        (0, 0, 14, 92),
        fill=(220, 35, 45),
    )

    font = get_font(
        32,
        bold=True,
    )

    draw.text(
        (40, 27),
        "RIFT VALLEY WATCH",
        font=font,
        fill=(255, 255, 255),
    )

    live_font = get_font(
        23,
        bold=True,
    )

    live = "REGIONAL NEWS"

    live_w, _ = text_size(
        draw,
        live,
        live_font,
    )

    draw.text(
        (
            WIDTH - live_w - 40,
            31,
        ),
        live,
        font=live_font,
        fill=(205, 210, 218),
    )


def draw_footer(draw):

    y = HEIGHT - 72

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(7, 10, 15),
    )

    font = get_font(
        21,
        bold=True,
    )

    draw.text(
        (40, y + 25),
        "RIFT VALLEY WATCH",
        font=font,
        fill=(205, 210, 218),
    )


def draw_county(draw, county):

    if not county:
        return

    county = str(county).upper()

    font = get_font(
        26,
        bold=True,
    )

    width, height = text_size(
        draw,
        county,
        font,
    )

    x = 40
    y = 120

    draw.rounded_rectangle(
        (
            x,
            y,
            x + width + 42,
            y + height + 24,
        ),
        radius=9,
        fill=(220, 35, 45),
    )

    draw.text(
        (
            x + 21,
            y + 12,
        ),
        county,
        font=font,
        fill=(255, 255, 255),
    )


# ============================================================
# OPENER
# ============================================================

def create_opener():

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 12, 18),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, 16, HEIGHT),
        fill=(220, 35, 45),
    )

    # subtle broadcast lines
    for y in range(300, 1500, 100):

        draw.line(
            (60, y, WIDTH - 60, y),
            fill=(25, 30, 38),
            width=2,
        )

    small = get_font(
        34,
        bold=True,
    )

    title = get_font(
        92,
        bold=True,
    )

    sub = get_font(
        34,
        bold=True,
    )

    draw.text(
        (70, 600),
        "RIFT VALLEY",
        font=small,
        fill=(220, 225, 232),
    )

    draw.text(
        (65, 665),
        "WATCH",
        font=title,
        fill=(255, 255, 255),
    )

    draw.rectangle(
        (70, 790, 390, 799),
        fill=(220, 35, 45),
    )

    draw.text(
        (70, 845),
        "REGIONAL NEWS BULLETIN",
        font=sub,
        fill=(205, 210, 218),
    )

    draw.text(
        (70, 905),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(
            25,
            bold=True,
        ),
        fill=(145, 152, 162),
    )

    draw_footer(draw)

    path = SCENES_DIR / "scene_00.png"

    image.save(
        path,
        "PNG",
        optimize=True,
    )

    return path


# ============================================================
# STORY SCENE
# ============================================================

def create_story_scene(story, number):

    photo_path = get_photo_path(story)
    photo = load_photo(photo_path)

    canvas = make_full_background(photo)

    draw = ImageDraw.Draw(canvas)

    draw_header(draw)

    county = story.get(
        "county",
        "Rift Valley",
    )

    category = story.get(
        "category",
        "NEWS",
    )

    draw_county(
        draw,
        county,
    )

    # --------------------------------------------------------
    # Main photo
    # --------------------------------------------------------

    photo_top = 175
    photo_bottom = 1010

    photo_width = WIDTH - 80
    photo_height = photo_bottom - photo_top

    if photo is not None:

        main_photo = crop_fill(
            photo,
            photo_width,
            photo_height,
        )

        canvas.paste(
            main_photo,
            (40, photo_top),
        )

        # Photo border
        draw.rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_bottom,
            ),
            outline=(255, 255, 255),
            width=2,
        )

    else:

        draw.rounded_rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_bottom,
            ),
            radius=10,
            fill=(22, 27, 36),
        )

        no_photo_font = get_font(
            32,
            bold=True,
        )

        text = "RIFT VALLEY NEWS"

        tw, th = text_size(
            draw,
            text,
            no_photo_font,
        )

        draw.text(
            (
                (WIDTH - tw) // 2,
                560,
            ),
            text,
            font=no_photo_font,
            fill=(155, 162, 172),
        )

    # --------------------------------------------------------
    # Lower news panel
    # --------------------------------------------------------

    panel_top = 970

    panel = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT - panel_top,
        ),
        (5, 8, 13, 245),
    )

    canvas = canvas.convert("RGBA")

    canvas.alpha_composite(
        panel,
        (0, panel_top),
    )

    draw = ImageDraw.Draw(canvas)

    # Category
    category_font = get_font(
        25,
        bold=True,
    )

    draw.text(
        (
            40,
            panel_top + 45,
        ),
        str(category).upper(),
        font=category_font,
        fill=(220, 35, 45),
    )

    # Headline
    title = (
        story.get("title")
        or story.get("headline")
        or "Rift Valley News Update"
    )

    title_font = get_font(
        49,
        bold=True,
    )

    draw_wrapped(
        draw,
        title,
        40,
        panel_top + 90,
        title_font,
        (255, 255, 255),
        WIDTH - 80,
        max_lines=4,
        spacing=8,
    )

    # Source
    source = (
        story.get("source")
        or "News source"
    )

    source_font = get_font(
        22,
        bold=False,
    )

    draw.text(
        (
            40,
            HEIGHT - 150,
        ),
        f"Source: {source}",
        font=source_font,
        fill=(170, 176, 185),
    )

    # Story number
    number_font = get_font(
        28,
        bold=True,
    )

    number_text = f"{number:02d}"

    nw, nh = text_size(
        draw,
        number_text,
        number_font,
    )

    draw.text(
        (
            WIDTH - nw - 45,
            HEIGHT - 150,
        ),
        number_text,
        font=number_font,
        fill=(170, 176, 185),
    )

    # Photo credit indicator
    if photo is not None:

        credit_font = get_font(
            19,
            bold=True,
        )

        draw.text(
            (
                40,
                HEIGHT - 112,
            ),
            "PHOTO • SOURCE ARTICLE",
            font=credit_font,
            fill=(130, 136, 146),
        )

    draw_footer(draw)

    path = (
        SCENES_DIR /
        f"scene_{number:02d}.png"
    )

    canvas.convert("RGB").save(
        path,
        "PNG",
        optimize=True,
    )

    return path, photo_path


# ============================================================
# OUTRO
# ============================================================

def create_outro():

    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 12, 18),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, 16, HEIGHT),
        fill=(220, 35, 45),
    )

    title_font = get_font(
        68,
        bold=True,
    )

    sub_font = get_font(
        31,
        bold=True,
    )

    title = "RIFT VALLEY WATCH"

    tw, th = text_size(
        draw,
        title,
        title_font,
    )

    draw.text(
        (
            (WIDTH - tw) // 2,
            700,
        ),
        title,
        font=title_font,
        fill=(255, 255, 255),
    )

    subtitle = "MORE REGIONAL NEWS • MORE UPDATES"

    sw, sh = text_size(
        draw,
        subtitle,
        sub_font,
    )

    draw.text(
        (
            (WIDTH - sw) // 2,
            810,
        ),
        subtitle,
        font=sub_font,
        fill=(185, 191, 200),
    )

    draw.rectangle(
        (
            340,
            900,
            740,
            908,
        ),
        fill=(220, 35, 45),
    )

    draw_footer(draw)

    path = SCENES_DIR / "scene_99.png"

    image.save(
        path,
        "PNG",
        optimize=True,
    )

    return path


# ============================================================
# NARRATION
# ============================================================

def narration_for_story(story):

    existing = story.get("narration")

    if existing:
        return str(existing).strip()

    county = story.get(
        "county",
        "the Rift Valley",
    )

    category = story.get(
        "category",
        "news",
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
        f"Rift Valley Watch. {county}.",
        f"{category}.",
        title,
    ]

    if description:
        parts.append(description)

    return " ".join(
        str(x).strip()
        for x in parts
        if x
    )


def create_tts(text, number):

    if not text:
        return None

    output = (
        AUDIO_DIR /
        f"story_{number:02d}.mp3"
    )

    try:

        log(
            f"Creating narration {number}..."
        )

        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(output)
        )

        if (
            output.exists()
            and output.stat().st_size > 1000
        ):
            return output

    except Exception as exc:

        log(
            f"TTS WARNING: {exc}"
        )

    return None


# ============================================================
# RENDER IMAGE TO MP4
# ============================================================

def render_scene(
    image_path,
    output_path,
    duration,
    audio_path=None,
):

    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
    ]

    if audio_path and audio_path.exists():

        command.extend(
            [
                "-i",
                str(audio_path),
            ]
        )

    command.extend(
        [
            "-t",
            str(duration),
            "-r",
            str(FPS),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
        ]
    )

    if audio_path and audio_path.exists():

        command.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-shortest",
            ]
        )

    else:

        command.append("-an")

    command.extend(
        [
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:

        log(result.stdout)

        raise RuntimeError(
            f"FFmpeg failed for {output_path.name}"
        )

    if not output_path.exists():

        raise RuntimeError(
            f"MP4 was not created: {output_path}"
        )

    if output_path.stat().st_size < 5000:

        raise RuntimeError(
            f"MP4 is too small: {output_path}"
        )


# ============================================================
# CONCAT
# ============================================================

def create_concat_file(scene_files):

    concat = OUTPUT_DIR / "concat.txt"

    with open(
        concat,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_files:

            path = str(
                scene.resolve()
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{path}'\n"
            )

    return concat


def assemble(scene_files):

    concat = create_concat_file(
        scene_files
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    # First attempt: copy streams
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if (
        result.returncode == 0
        and FINAL_VIDEO.exists()
        and FINAL_VIDEO.stat().st_size > 100000
    ):
        return

    log(
        "Stream-copy concatenation failed."
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    # Reliable fallback
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
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
        "-movflags",
        "+faststart",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:

        log(result.stdout)

        raise RuntimeError(
            "Final MP4 assembly failed."
        )

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final MP4 was not created."
        )


# ============================================================
# VALIDATE
# ============================================================

def validate_final_video():

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if FINAL_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.returncode != 0:

        log(result.stdout)

        raise RuntimeError(
            "ffprobe failed."
        )

    info = json.loads(
        result.stdout
    )

    streams = info.get(
        "streams",
        [],
    )

    if not streams:
        raise RuntimeError(
            "No video stream found."
        )

    stream = streams[0]

    width = int(
        stream.get(
            "width",
            0,
        )
    )

    height = int(
        stream.get(
            "height",
            0,
        )
    )

    log("")
    log("=" * 70)
    log("FINAL VIDEO VALIDATION")
    log("=" * 70)

    log(f"Width: {width}")
    log(f"Height: {height}")
    log(
        f"Codec: {stream.get('codec_name')}"
    )
    log(
        f"Pixel format: {stream.get('pix_fmt')}"
    )
    log(
        f"Duration: {info.get('format', {}).get('duration')}"
    )

    if width != 1080:
        raise RuntimeError(
            f"Wrong width: {width}"
        )

    if height != 1920:
        raise RuntimeError(
            f"Wrong height: {height}"
        )


# ============================================================
# REPORT
# ============================================================

def write_report(records):

    report = {
        "project": "Rift Valley Watch",
        "version": "V2",
        "resolution": "1080x1920",
        "fps": FPS,
        "real_photos": True,
        "stories_rendered": len(records),
        "records": records,
    }

    with open(
        VISUAL_REPORT,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 70)
    log("RIFT VALLEY WATCH V2 VIDEO GENERATOR")
    log("=" * 70)

    prepare_directories()

    # --------------------------------------------------------
    # Load story.json
    # --------------------------------------------------------

    try:

        data = load_json(
            STORY_FILE
        )

    except Exception as exc:

        log(
            f"ERROR loading story.json: {exc}"
        )

        return 1

    log("")
    log("STORY JSON TYPE:")
    log(type(data).__name__)

    # --------------------------------------------------------
    # Extract stories robustly
    # --------------------------------------------------------

    stories = extract_stories(data)

    log("")
    log("=" * 70)
    log("STORY EXTRACTION")
    log("=" * 70)

    log(
        f"Stories detected: {len(stories)}"
    )

    if not stories:

        log("")
        log("ERROR: No news stories could be extracted.")
        log("")
        log("Top-level JSON structure:")

        if isinstance(data, dict):

            log(
                "Keys: "
                + ", ".join(
                    str(k)
                    for k in data.keys()
                )
            )

        elif isinstance(data, list):

            log(
                f"List length: {len(data)}"
            )

            if data:
                log(
                    "First item type: "
                    + type(data[0]).__name__
                )

        return 1

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = []
    seen = set()

    for story in stories:

        title = (
            story.get("title")
            or story.get("headline")
            or story.get("url")
            or ""
        )

        key = str(title).strip().lower()

        if key and key not in seen:

            seen.add(key)
            unique.append(story)

    stories = unique[:10]

    log(
        f"Stories selected: {len(stories)}"
    )

    # --------------------------------------------------------
    # Delete old generated files
    # --------------------------------------------------------

    for path in SCENES_DIR.glob("*"):

        try:

            if path.is_file():
                path.unlink()

        except Exception:
            pass

    for path in AUDIO_DIR.glob("*"):

        try:

            if path.is_file():
                path.unlink()

        except Exception:
            pass

    if FINAL_VIDEO.exists():

        try:
            FINAL_VIDEO.unlink()
        except Exception:
            pass

    # --------------------------------------------------------
    # OPENER
    # --------------------------------------------------------

    scene_files = []
    records = []

    try:

        opener_png = create_opener()

        opener_mp4 = (
            SCENES_DIR /
            "scene_00.mp4"
        )

        render_scene(
            opener_png,
            opener_mp4,
            OPENER_SECONDS,
        )

        scene_files.append(
            opener_mp4
        )

        records.append(
            {
                "scene": "opener",
                "photo": False,
            }
        )

        log("Opener created.")

    except Exception as exc:

        log(
            f"OPENER WARNING: {exc}"
        )

    # --------------------------------------------------------
    # STORIES
    # --------------------------------------------------------

    for number, story in enumerate(
        stories,
        start=1,
    ):

        log("")
        log("=" * 70)
        log(
            f"PROCESSING STORY {number}"
        )
        log("=" * 70)

        title = (
            story.get("title")
            or story.get("headline")
            or "Untitled"
        )

        county = story.get(
            "county",
            "Rift Valley",
        )

        log(f"County: {county}")
        log(f"Title: {title}")

        try:

            png_path, photo_path = (
                create_story_scene(
                    story,
                    number,
                )
            )

            if photo_path:

                log(
                    f"REAL PHOTO: {photo_path}"
                )

            else:

                log(
                    "REAL PHOTO: unavailable — "
                    "using fallback."
                )

            narration = narration_for_story(
                story
            )

            audio_path = create_tts(
                narration,
                number,
            )

            mp4_path = (
                SCENES_DIR /
                f"scene_{number:02d}.mp4"
            )

            render_scene(
                png_path,
                mp4_path,
                STORY_SECONDS,
                audio_path,
            )

            scene_files.append(
                mp4_path
            )

            records.append(
                {
                    "scene": number,
                    "county": county,
                    "category": story.get(
                        "category",
                        "NEWS",
                    ),
                    "title": title,
                    "photo": bool(
                        photo_path
                    ),
                    "photo_path": (
                        str(
                            photo_path.relative_to(
                                ROOT
                            )
                        )
                        if photo_path
                        else None
                    ),
                    "audio": bool(
                        audio_path
                    ),
                }
            )

            log(
                f"STORY {number} SUCCESS"
            )

        except Exception as exc:

            log("")
            log(
                f"STORY {number} FAILED: {exc}"
            )

            # Continue to next story.
            continue

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    try:

        outro_png = create_outro()

        outro_mp4 = (
            SCENES_DIR /
            "scene_99.mp4"
        )

        render_scene(
            outro_png,
            outro_mp4,
            OUTRO_SECONDS,
        )

        scene_files.append(
            outro_mp4
        )

        records.append(
            {
                "scene": "outro",
                "photo": False,
            }
        )

        log("Outro created.")

    except Exception as exc:

        log(
            f"OUTRO WARNING: {exc}"
        )

    # --------------------------------------------------------
    # Check scenes
    # --------------------------------------------------------

    valid_scenes = [
        path
        for path in scene_files
        if path.exists()
        and path.stat().st_size > 5000
    ]

    log("")
    log("=" * 70)
    log("VALID SCENES")
    log("=" * 70)

    for path in valid_scenes:

        log(
            f"{path.name} "
            f"{path.stat().st_size:,} bytes"
        )

    if not valid_scenes:

        log(
            "ERROR: No valid MP4 scenes."
        )

        return 1

    # --------------------------------------------------------
    # Assemble
    # --------------------------------------------------------

    try:

        log("")
        log("=" * 70)
        log("ASSEMBLING FINAL MP4")
        log("=" * 70)

        assemble(
            valid_scenes
        )

    except Exception as exc:

        log("")
        log(
            f"ASSEMBLY ERROR: {exc}"
        )

        return 1

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    try:

        validate_final_video()

    except Exception as exc:

        log("")
        log(
            f"VALIDATION ERROR: {exc}"
        )

        return 1

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    try:

        write_report(
            records
        )

    except Exception as exc:

        log(
            f"REPORT WARNING: {exc}"
        )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    photo_count = sum(
        1
        for record in records
        if record.get("photo") is True
    )

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO SUCCESSFUL")
    log("=" * 70)

    log(
        f"Created: {FINAL_VIDEO}"
    )

    log(
        f"Size: {FINAL_VIDEO.stat().st_size:,} bytes"
    )

    log(
        f"Stories rendered: {len(stories)}"
    )

    log(
        f"Real photos used: {photo_count}"
    )

    log(
        f"Scenes: {len(valid_scenes)}"
    )

    log("=" * 70)

    return 0


if __name__ == "__main__":

    try:
        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        log("Interrupted.")
        sys.exit(1)

    except Exception as exc:

        log("")
        log("=" * 70)
        log("FATAL VIDEO GENERATOR ERROR")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)

        sys.exit(1)
