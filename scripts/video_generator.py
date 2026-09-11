import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME NEWS VIDEO GENERATOR
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
# FONT
# ============================================================

def get_font(size, bold=False):

    candidates = []

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        ]

    candidates += [
        str(ROOT / "fonts" / "DejaVuSans-Bold.ttf"),
        str(ROOT / "fonts" / "DejaVuSans.ttf"),
    ]

    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
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

    with open(STORY_FILE, "r", encoding="utf-8") as file:
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
    }

    return len(keys.intersection(item.keys())) >= 2


def find_stories(data):

    found = []

    if isinstance(data, dict):

        if is_story(data):
            found.append(data)

        for value in data.values():
            found.extend(find_stories(value))

    elif isinstance(data, list):

        for value in data:
            found.extend(find_stories(value))

    return found


def get_stories(data):

    stories = find_stories(data)

    unique = []
    seen = set()

    for story in stories:

        identifier = (
            story.get("url")
            or story.get("title")
            or story.get("headline")
            or story.get("description")
            or ""
        )

        identifier = str(identifier).strip().lower()

        if not identifier:
            identifier = str(len(unique))

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


def wrap_text(draw, text, font, max_width):

    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:

        test = current + " " + word

        if text_width(draw, test, font) <= max_width:
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
        lines[-1] = lines[-1].rstrip(".") + "..."

    bbox = font.getbbox("Ag")
    line_height = bbox[3] - bbox[1]

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
# PHOTO
# ============================================================

def get_photo_path(story):

    keys = [
        "image_path",
        "photo_path",
        "image_file",
        "photo_file"
    ]

    for key in keys:

        value = story.get(key)

        if not value:
            continue

        value = str(value)

        paths = [
            ROOT / value,
            Path(value)
        ]

        for path in paths:

            if path.exists() and path.is_file():
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


def crop_photo(image, width, height):

    if image is None:
        return None

    source_ratio = image.width / image.height
    target_ratio = width / height

    if source_ratio > target_ratio:

        new_height = image.height
        new_width = int(image.height * target_ratio)

    else:

        new_width = image.width
        new_height = int(image.width / target_ratio)

    left = max(
        0,
        (image.width - new_width) // 2
    )

    top = max(
        0,
        (image.height - new_height) // 2
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
# COMMON BRANDING
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
        (WIDTH - tw - 38, 34),
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


def draw_county(draw, county):

    if not county:
        return

    county = str(county).upper()

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
        (38, 125, 38 + tw + 40, 180),
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

    for y in range(250, 1650, 120):

        draw.line(
            (60, y, WIDTH - 60, y),
            fill=(27, 32, 41),
            width=2
        )

    small = get_font(
        34,
        True
    )

    title = get_font(
        92,
        True
    )

    subtitle = get_font(
        32,
        True
    )

    draw.text(
        (70, 610),
        "RIFT VALLEY",
        font=small,
        fill=(205, 211, 220)
    )

    draw.text(
        (65, 670),
        "WATCH",
        font=title,
        fill=(255, 255, 255)
    )

    draw.rectangle(
        (70, 795, 400, 803),
        fill=(220, 35, 45)
    )

    draw.text(
        (70, 850),
        "REGIONAL NEWS BULLETIN",
        font=subtitle,
        fill=(185, 192, 202)
    )

    draw.text(
        (70, 910),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(23, True),
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

def create_story_image(story, number):

    photo_path = get_photo_path(story)
    photo = load_photo(photo_path)

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

        background = background.convert("RGBA")
        background.alpha_composite(dark)

        canvas = background.convert("RGB")

    draw = ImageDraw.Draw(canvas)

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
    # Main real photograph
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

        draw = ImageDraw.Draw(canvas)

        draw.rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_top + photo_height
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
                photo_top + photo_height
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
    # Information panel
    # --------------------------------------------------------

    panel_top = 950

    draw.rectangle(
        (0, panel_top, WIDTH, HEIGHT - 74),
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
        (40, panel_top + 38),
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
        (40, HEIGHT - 152),
        "Source: " + source,
        font=source_font,
        fill=(155, 163, 174)
    )

    if photo_path is not None:

        draw.text(
            (40, HEIGHT - 116),
            "PHOTO: SOURCE ARTICLE",
            font=get_font(18, True),
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
        (WIDTH - nw - 42, HEIGHT - 150),
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
        ((WIDTH - tw) // 2, 700),
        title,
        font=title_font,
        fill=(255, 255, 255)
    )

    subtitle = "MORE REGIONAL NEWS • MORE UPDATES"

    sw = text_width(
        draw,
        subtitle,
        subtitle_font
    )

    draw.text(
        ((WIDTH - sw) // 2, 815),
        subtitle,
        font=subtitle_font,
        fill=(180, 187, 198)
    )

    draw.rectangle(
        (340, 900, 740, 908),
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

    if story.get("narration"):
        return str(
            story["narration"]
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


def create_tts(text, number):

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

    has_audio = (
        audio_path is not None
        and audio_path.exists()
    )

    if has_audio:

        command += [
            "-i",
            str(audio_path)
        ]

    command += [
        "-map",
        "0:v:0"
    ]

    if has_audio:

        command += [
            "-map",
            "1:a:0"
        ]

    else:

        command += [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map",
            "1:a:0"
        ]

    command += [
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

def create_concat_file(scene_files):

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

def assemble_final(scene_files):

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

    # --------------------------------------------------------
    # Every scene already has:
    # H264 video
    # AAC audio
    # 1080x1920
    # 44100 Hz stereo
    #
    # We still FORCE a final encode for reliability.
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
        str(temp_file)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    log(result.stdout)

    if result.returncode != 0:

        raise RuntimeError(
            "Final FFmpeg assembly failed."
        )

    if not temp_file.exists():

        raise RuntimeError(
            "Final temporary MP4 was not created."
        )

    size = temp_file.stat().st_size

    log(
        "Temporary MP4 size: "
        + f"{size:,}"
        + " bytes"
    )

    if size < 100000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    temp_file.replace(
        FINAL_VIDEO
    )


# ============================================================
# VALIDATION
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
        "format=duration,size",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,"
        "pix_fmt,r_frame_rate,sample_rate,channels",
        "-of",
        "json",
        str(FINAL_VIDEO)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.returncode != 0:

        log(result.stdout)

        raise RuntimeError(
            "ffprobe could not read final MP4."
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

        if stream.get("codec_type") == "video":
            video_stream = stream

        if stream.get("codec_type") == "audio":
            audio_stream = stream

    if video_stream is None:

        raise RuntimeError(
            "Final MP4 has no video stream."
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

    log("")
    log("=" * 70)
    log("FINAL MP4 VALIDATION")
    log("=" * 70)

    log(
        "File size: "
        + f"{size:,}"
        + " bytes"
    )

    log(
        "Duration: "
        + f"{duration:.2f}"
        + " seconds"
    )

    log(
        "Resolution: "
        + str(width)
        + "x"
        + str(height)
    )

    log(
        "Video codec: "
        + str(
            video_stream.get(
                "codec_name"
            )
        )
    )

    if audio_stream:

        log(
            "Audio codec: "
            + str(
                audio_stream.get(
                    "codec_name"
                )
            )
        )

        log(
            "Audio channels: "
            + str(
                audio_stream.get(
                    "channels"
                )
            )
        )

    if width != WIDTH:

        raise RuntimeError(
            "Wrong video width."
        )

    if height != HEIGHT:

        raise RuntimeError(
            "Wrong video height."
        )

    if duration <= 1:

        raise RuntimeError(
            "Invalid video duration."
        )

    if audio_stream is None:

        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    log(
        "1080x1920 vertical video confirmed."
    )

    log(
        "Audio stream confirmed."
    )


# ============================================================
# REPORT
# ============================================================

def write_report(records):

    report = {
        "project": "Rift Valley Watch",
        "version": "V3",
        "resolution": "1080x1920",
        "fps": FPS,
        "real_photos_enabled": True,
        "final_reencode": True,
        "records": records
    }

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# CLEAN OLD FILES
# ============================================================

def clean_old_files():

    for path in SCENES_DIR.glob("*"):

        if path.is_file():

            try:
                path.unlink()
            except Exception:
                pass

    for path in AUDIO_DIR.glob("*"):

        if path.is_file():

            try:
                path.unlink()
            except Exception:
                pass

    for path in [
        OUTPUT_DIR / "concat.txt",
        OUTPUT_DIR / "rift_valley_watch_temp.mp4"
    ]:

        if path.exists():

            try:
                path.unlink()
            except Exception:
                pass

    if FINAL_VIDEO.exists():

        try:
            FINAL_VIDEO.unlink()
        except Exception:
            pass


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 70)
    log("RIFT VALLEY WATCH V3 VIDEO GENERATOR")
    log("=" * 70)

    prepare_directories()
    clean_old_files()

    # --------------------------------------------------------
    # LOAD NEWS
    # --------------------------------------------------------

    log("")
    log("Loading story.json")

    data = load_story_data()

    stories = get_stories(data)

    log(
        "Stories detected: "
        + str(len(stories))
    )

    if not stories:

        log(
            "ERROR: No stories found in story.json."
        )

        return 1

    scene_files = []
    records = []

    # --------------------------------------------------------
    # OPENER
    # --------------------------------------------------------

    try:

        opener_png = create_opener()

        opener_mp4 = (
            SCENES_DIR
            / "scene_00.mp4"
        )

        render_scene(
            opener_png,
            opener_mp4,
            OPENER_DURATION
        )

        scene_files.append(
            opener_mp4
        )

        records.append(
            {
                "scene": "opener",
                "photo": False
            }
        )

        log(
            "Opener completed."
        )

    except Exception as exc:

        log(
            "OPENER ERROR: "
            + str(exc)
        )

        return 1

    # --------------------------------------------------------
    # STORIES
    # --------------------------------------------------------

    for number, story in enumerate(
        stories,
        start=1
    ):

        log("")
        log("=" * 70)
        log(
            "PROCESSING STORY "
            + str(number)
        )
        log("=" * 70)

        title = (
            story.get("title")
            or story.get("headline")
            or "Untitled story"
        )

        county = story.get(
            "county",
            "Rift Valley"
        )

        log(
            "County: "
            + str(county)
        )

        log(
            "Headline: "
            + str(title)
        )

        try:

            image_path, photo_path = (
                create_story_image(
                    story,
                    number
                )
            )

            if photo_path:

                log(
                    "REAL SOURCE PHOTO: "
                    + str(photo_path)
                )

            else:

                log(
                    "No source photo found."
                )

            narration = build_narration(
                story
            )

            audio_path = create_tts(
                narration,
                number
            )

            scene_path = (
                SCENES_DIR
                / f"scene_{number:02d}.mp4"
            )

            render_scene(
                image_path,
                scene_path,
                STORY_DURATION,
                audio_path
            )

            scene_files.append(
                scene_path
            )

            scene_info = inspect_scene(
                scene_path
            )

            records.append(
                {
                    "scene": number,
                    "county": county,
                    "category": story.get(
                        "category",
                        "News"
                    ),
                    "title": title,
                    "photo": bool(
                        photo_path
                    ),
                    "photo_path": (
                        str(photo_path)
                        if photo_path
                        else None
                    ),
                    "audio": bool(
                        audio_path
                    ),
                    "technical": scene_info
                }
            )

            log(
                "STORY "
                + str(number)
                + " COMPLETED."
            )

        except Exception as exc:

            log(
                "STORY "
                + str(number)
                + " ERROR: "
                + str(exc)
            )

            # Continue to the next story.
            continue

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    try:

        outro_png = create_outro()

        outro_mp4 = (
            SCENES_DIR
            / "scene_99.mp4"
        )

        render_scene(
            outro_png,
            outro_mp4,
            OUTRO_DURATION
        )

        scene_files.append(
            outro_mp4
        )

        records.append(
            {
                "scene": "outro",
                "photo": False
            }
        )

        log(
            "Outro completed."
        )

    except Exception as exc:

        log(
            "OUTRO ERROR: "
            + str(exc)
        )

        return 1

    # --------------------------------------------------------
    # SCENE CHECK
    # --------------------------------------------------------

    valid_scenes = []

    log("")
    log("=" * 70)
    log("CHECKING GENERATED SCENES")
    log("=" * 70)

    for scene in scene_files:

        if (
            scene.exists()
            and scene.stat().st_size > 5000
        ):

            valid_scenes.append(scene)

            log(
                scene.name
                + " "
                + f"{scene.stat().st_size:,}"
                + " bytes"
            )

        else:

            log(
                "INVALID SCENE: "
                + scene.name
            )

    if len(valid_scenes) < 2:

        log(
            "ERROR: Not enough valid scenes."
        )

        return 1

    # --------------------------------------------------------
    # FINAL ASSEMBLY
    # --------------------------------------------------------

    try:

        assemble_final(
            valid_scenes
        )

    except Exception as exc:

        log("")
        log("=" * 70)
        log("FINAL ASSEMBLY FAILED")
        log("=" * 70)
        log(str(exc))

        return 1

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    try:

        validate_final_video()

    except Exception as exc:

        log("")
        log("=" * 70)
        log("VALIDATION FAILED")
        log("=" * 70)
        log(str(exc))

        return 1

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    try:

        write_report(records)

    except Exception as exc:

        log(
            "REPORT WARNING: "
            + str(exc)
        )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    real_photo_count = sum(
        1
        for record in records
        if record.get("photo") is True
    )

    story_count = sum(
        1
        for record in records
        if isinstance(
            record.get("scene"),
            int
        )
    )

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO SUCCESSFUL")
    log("=" * 70)

    log(
        "Created: "
        + str(FINAL_VIDEO)
    )

    log(
        "Size: "
        + f"{FINAL_VIDEO.stat().st_size:,}"
        + " bytes"
    )

    log(
        "Stories rendered: "
        + str(story_count)
    )

    log(
        "Real photos used: "
        + str(real_photo_count)
    )

    log(
        "Scenes assembled: "
        + str(len(valid_scenes))
    )

    log("=" * 70)

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        log("Process interrupted.")
        sys.exit(1)

    except Exception as exc:

        log("")
        log("=" * 70)
        log("FATAL ERROR")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)

        sys.exit(1)
