import sys
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH V3 VIDEO GENERATOR
# REAL PHOTOS + NEWS GRAPHICS + NARRATION
# FINAL ASSEMBLY: FORCED FFMPEG RE-ENCODE
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"

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
# LOG
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
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing JSON file: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def looks_like_story(value):

    if not isinstance(value, dict):
        return False

    keys = [
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
    ]

    return sum(
        1 for key in keys
        if key in value
    ) >= 2


def recursive_story_search(value, results=None):

    if results is None:
        results = []

    if isinstance(value, dict):

        if looks_like_story(value):
            results.append(value)

        for child in value.values():

            recursive_story_search(
                child,
                results,
            )

    elif isinstance(value, list):

        for child in value:

            recursive_story_search(
                child,
                results,
            )

    return results


def extract_stories(data):

    if isinstance(data, list):

        direct = [
            item
            for item in data
            if looks_like_story(item)
        ]

        if direct:
            return direct

    if isinstance(data, dict):

        preferred = [
            "stories",
            "articles",
            "items",
            "news",
            "results",
            "selected",
            "selected_stories",
            "top_stories",
            "top_articles",
            "news_items",
            "bulletin",
            "data",
        ]

        for key in preferred:

            value = data.get(key)

            if isinstance(value, list):

                direct = [
                    item
                    for item in value
                    if looks_like_story(item)
                ]

                if direct:
                    return direct

        found = recursive_story_search(data)

        if found:
            return found

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


def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        test = current + " " + word

        width, _ = text_size(
            draw,
            test,
            font,
        )

        if width <= max_width:
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
    spacing=8,
):

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    if len(lines) > max_lines:

        lines = lines[:max_lines]

        if not lines[-1].endswith("..."):
            lines[-1] = (
                lines[-1].rstrip(".")
                + "..."
            )

    bbox = font.getbbox("Ag")
    line_height = bbox[3] - bbox[1]

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

def find_photo(story):

    keys = [
        "image_path",
        "photo_path",
        "image_file",
        "photo_file",
        "image",
        "photo",
    ]

    for key in keys:

        value = story.get(key)

        if not value:
            continue

        value = str(value)

        candidates = [
            ROOT / value,
            Path(value),
        ]

        for path in candidates:

            if path.exists() and path.is_file():
                return path

    return None


def load_photo(path):

    if path is None:
        return None

    try:

        with Image.open(path) as img:

            img.load()

            return img.convert("RGB")

    except Exception as exc:

        log(
            f"PHOTO WARNING: {path} -> {exc}"
        )

        return None


def crop_fill(
    image,
    width,
    height,
):

    if image is None:
        return None

    source_ratio = (
        image.width / image.height
    )

    target_ratio = (
        width / height
    )

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

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height,
        )
    )

    return image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )


def create_background(photo):

    if photo is None:

        return Image.new(
            "RGB",
            (WIDTH, HEIGHT),
            (12, 16, 23),
        )

    bg = crop_fill(
        photo,
        WIDTH,
        HEIGHT,
    )

    bg = bg.filter(
        ImageFilter.GaussianBlur(18)
    )

    dark = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 125),
    )

    bg = bg.convert("RGBA")

    bg.alpha_composite(dark)

    return bg.convert("RGB")


# ============================================================
# BRANDING
# ============================================================

def header(draw):

    draw.rectangle(
        (0, 0, WIDTH, 92),
        fill=(7, 10, 16),
    )

    draw.rectangle(
        (0, 0, 15, 92),
        fill=(220, 35, 45),
    )

    logo = get_font(
        31,
        bold=True,
    )

    draw.text(
        (40, 27),
        "RIFT VALLEY WATCH",
        font=logo,
        fill=(255, 255, 255),
    )

    right = get_font(
        23,
        bold=True,
    )

    text = "REGIONAL NEWS"

    tw, _ = text_size(
        draw,
        text,
        right,
    )

    draw.text(
        (
            WIDTH - tw - 40,
            32,
        ),
        text,
        font=right,
        fill=(190, 196, 205),
    )


def footer(draw):

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
        fill=(200, 205, 214),
    )


def county_badge(draw, county):

    if not county:
        return

    county = str(county).upper()

    font = get_font(
        26,
        bold=True,
    )

    tw, th = text_size(
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
            x + tw + 42,
            y + th + 24,
        ),
        radius=8,
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

    for y in range(
        300,
        1600,
        110,
    ):

        draw.line(
            (60, y, WIDTH - 60, y),
            fill=(26, 31, 40),
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

    subtitle = get_font(
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
        font=subtitle,
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

    footer(draw)

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

def create_story_scene(
    story,
    number,
):

    photo_path = find_photo(story)

    photo = load_photo(
        photo_path
    )

    canvas = create_background(
        photo
    )

    draw = ImageDraw.Draw(canvas)

    header(draw)

    county_badge(
        draw,
        story.get(
            "county",
            "RIFT VALLEY",
        ),
    )

    # --------------------------------------------------------
    # REAL PHOTO
    # --------------------------------------------------------

    photo_top = 175
    photo_bottom = 1010

    if photo is not None:

        main_photo = crop_fill(
            photo,
            WIDTH - 80,
            photo_bottom - photo_top,
        )

        canvas.paste(
            main_photo,
            (40, photo_top),
        )

        draw = ImageDraw.Draw(canvas)

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
            fill=(25, 30, 40),
        )

        fallback = get_font(
            32,
            bold=True,
        )

        text = "RIFT VALLEY NEWS"

        tw, th = text_size(
            draw,
            text,
            fallback,
        )

        draw.text(
            (
                (WIDTH - tw) // 2,
                560,
            ),
            text,
            font=fallback,
            fill=(155, 162, 172),
        )

    # --------------------------------------------------------
    # NEWS PANEL
    # --------------------------------------------------------

    panel_top = 970

    overlay = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT - panel_top,
        ),
        (5, 8, 13, 247),
    )

    canvas = canvas.convert("RGBA")

    canvas.alpha_composite(
        overlay,
        (0, panel_top),
    )

    draw = ImageDraw.Draw(canvas)

    category = story.get(
        "category",
        "NEWS",
    )

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

    number_font = get_font(
        28,
        bold=True,
    )

    number_text = f"{number:02d}"

    nw, _ = text_size(
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

    footer(draw)

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

    subtitle_font = get_font(
        31,
        bold=True,
    )

    title = "RIFT VALLEY WATCH"

    tw, _ = text_size(
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

    subtitle = (
        "MORE REGIONAL NEWS • MORE UPDATES"
    )

    sw, _ = text_size(
        draw,
        subtitle,
        subtitle_font,
    )

    draw.text(
        (
            (WIDTH - sw) // 2,
            810,
        ),
        subtitle,
        font=subtitle_font,
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

    footer(draw)

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

def make_narration(story):

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

    return " ".join(
        str(value).strip()
        for value in [
            f"Rift Valley Watch. {county}.",
            f"{category}.",
            title,
            description,
        ]
        if value
    )


def create_audio(
    text,
    number,
):

    if not text:
        return None

    output = (
        AUDIO_DIR /
        f"story_{number:02d}.mp3"
    )

    try:

        log(
            f"Creating narration for story {number}"
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
# RENDER SCENE
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
        "-framerate",
        str(FPS),
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
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
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

        command.extend(
            [
                "-an",
            ]
        )

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
            f"Scene rendering failed: "
            f"{output_path.name}"
        )

    if not output_path.exists():

        raise RuntimeError(
            f"Missing scene: {output_path}"
        )

    if output_path.stat().st_size < 5000:

        raise RuntimeError(
            f"Scene too small: {output_path}"
        )


# ============================================================
# FINAL ASSEMBLY
# ============================================================

def create_concat_file(
    scene_files,
):

    concat_file = (
        OUTPUT_DIR /
        "concat.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_files:

            absolute = str(
                scene.resolve()
            )

            # Escape apostrophes for concat demuxer.
            absolute = absolute.replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{absolute}'\n"
            )

    return concat_file


def assemble_final_video(
    scene_files,
):

    concat_file = create_concat_file(
        scene_files
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    temp_video = (
        OUTPUT_DIR /
        "rift_valley_watch_temp.mp4"
    )

    if temp_video.exists():
        temp_video.unlink()

    log("")
    log("=" * 70)
    log("FORCED FINAL RE-ENCODE")
    log("=" * 70)

    # --------------------------------------------------------
    # IMPORTANT:
    # No -c copy.
    # Everything is decoded and re-encoded.
    # --------------------------------------------------------

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
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
        "-movflags",
        "+faststart",
        str(temp_video),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    log(result.stdout)

    if result.returncode != 0:

        raise RuntimeError(
            "FFmpeg final re-encode failed."
        )

    if not temp_video.exists():

        raise RuntimeError(
            "Temporary final MP4 was not created."
        )

    size = temp_video.stat().st_size

    log(
        f"Temporary MP4 size: {size:,} bytes"
    )

    if size < 100000:

        raise RuntimeError(
            "Temporary final MP4 is too small."
        )

    temp_video.replace(
        FINAL_VIDEO
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_video():

    if not FINAL_VIDEO.exists():

        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = FINAL_VIDEO.stat().st_size

    if size < 100000:

        raise RuntimeError(
            f"Final MP4 is too small: {size} bytes"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt,"
        "r_frame_rate",
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
            "ffprobe validation failed."
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

    video = streams[0]

    width = int(
        video.get(
            "width",
            0,
        )
    )

    height = int(
        video.get(
            "height",
            0,
        )
    )

    duration = float(
        info.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
        or 0
    )

    log("")
    log("=" * 70)
    log("FINAL MP4 VALIDATION")
    log("=" * 70)

    log(
        f"File size: {size:,} bytes"
    )

    log(
        f"Duration: {duration:.2f} seconds"
    )

    log(
        f"Resolution: {width}x{height}"
    )

    log(
        f"Codec: {video.get('codec_name')}"
    )

    log(
        f"Pixel format: {video.get('pix_fmt')}"
    )

    if width != WIDTH:

        raise RuntimeError(
            f"Expected width {WIDTH}, got {width}"
        )

    if height != HEIGHT:

        raise RuntimeError(
            f"Expected height {HEIGHT}, got {height}"
        )

    if duration <= 1:

        raise RuntimeError(
            "Final video duration is invalid."
        )


# ============================================================
# REPORT
# ============================================================

def write_report(records):

    report = {
        "project": "Rift Valley Watch
