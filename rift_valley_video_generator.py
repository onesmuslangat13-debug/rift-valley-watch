from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION: RVW_VIDEO_V35_EXACT_PHOTO_RECOVERY
#
# PURPOSE
# - Read data/selected_story.json
# - Resolve the exact selected article photographs
# - Recover exact files even when path formatting differs
# - Handle escaped underscores such as story\_1\_image.jpg
# - Handle extension mismatches safely
# - Never mix photos from unrelated stories
# - Never use Citizen / CTV / World Cup / avatar / placeholder
# - One scene per genuinely unique article photograph
# - 1080x1920 vertical MP4
# - Narration from audio/narration.mp3
# ============================================================


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

AUDIO_FILE = AUDIO_DIR / "narration.mp3"

FINAL_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_IMAGE_BYTES = 10000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

MIN_AUDIO_BYTES = 1000
MIN_VIDEO_BYTES = 100000


# ============================================================
# FORBIDDEN VISUAL TERMS
# ============================================================

FORBIDDEN_TERMS = (
    "citizen",
    "citizen digital",
    "citizen tv",
    "ctv",
    "worldcup",
    "world_cup",
    "world cup",
    "avatar",
    "placeholder",
    "default_image",
    "default-image",
    "default image",
    "profile_picture",
    "profile-picture",
    "profile picture",
    "dummy",
    "generic",
    "generic image",
    "generic-image",
    "logo",
    "icon",
    "advert",
    "advertisement",
)


# ============================================================
# RUN COMMAND
# ============================================================

def run(command, label):
    print()
    print("=" * 72)
    print("RUNNING:", label)
    print("=" * 72)

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {result.returncode}"
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Missing JSON file: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"JSON file is empty: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except Exception as error:
        raise RuntimeError(
            f"Could not read JSON file {path}: {error}"
        )

    if not data:
        raise RuntimeError(
            f"JSON file contains no data: {path}"
        )

    return data


def get_story(data):
    if isinstance(data, dict):

        if isinstance(
            data.get("story"),
            dict,
        ):
            return data["story"]

        if isinstance(
            data.get("stories"),
            list,
        ):
            for item in data["stories"]:
                if isinstance(item, dict):
                    return item

            raise RuntimeError(
                "Selected story list contains no story object"
            )

        return data

    raise RuntimeError(
        "Selected story JSON is not an object"
    )


# ============================================================
# TEXT
# ============================================================

def clean_text(value, fallback=""):
    if value is None:
        return fallback

    if isinstance(
        value,
        (dict, list),
    ):
        return fallback

    value = re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()

    return value or fallback


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ]

    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]

    for candidate in candidates:

        path = Path(candidate)

        if path.exists():
            try:
                return ImageFont.truetype(
                    str(path),
                    size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    value,
    selected_font,
    max_width,
    maximum=5,
):
    words = clean_text(value).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:

        trial = (
            f"{current} {word}"
            .strip()
        )

        try:
            box = draw.textbbox(
                (0, 0),
                trial,
                font=selected_font,
            )

            trial_width = (
                box[2] - box[0]
            )

        except Exception:
            trial_width = len(trial) * 20

        if trial_width <= max_width:
            current = trial

        else:

            if current:
                lines.append(current)

            current = word

            if len(lines) >= maximum:
                break

    if current and len(lines) < maximum:
        lines.append(current)

    return lines[:maximum]


def draw_wrapped_text(
    draw,
    value,
    x,
    y,
    max_width,
    selected_font,
    fill,
    gap=10,
    maximum=5,
):
    lines = wrap_text(
        draw,
        value,
        selected_font,
        max_width,
        maximum,
    )

    if not lines:
        return y

    try:
        bbox = selected_font.getbbox("Ag")
        line_height = bbox[3] - bbox[1]
    except Exception:
        line_height = 40

    for index, line in enumerate(lines):

        draw.text(
            (
                x,
                y + index * (
                    line_height + gap
                ),
            ),
            line,
            font=selected_font,
            fill=fill,
        )

    return y + len(lines) * (
        line_height + gap
    )


# ============================================================
# IMAGE PATH NORMALIZATION
# ============================================================

def normalize_path_string(value):
    """
    Normalizes path strings coming from JSON.

    Handles:
        story_1_image.jpg
        story\\_1\\_image.jpg
        assets/source/story_1_image.jpg
        ./assets/source/story_1_image.jpg
    """

    value = str(value).strip()

    # Remove accidental escaping of underscores.
    value = value.replace(
        "\\_",
        "_",
    )

    # Normalize separators.
    value = value.replace(
        "\\",
        "/",
    )

    # Remove surrounding quotes.
    value = value.strip(
        "\"'"
    )

    # Remove leading ./.
    while value.startswith("./"):
        value = value[2:]

    return value


# ============================================================
# VALID IMAGE
# ============================================================

def valid_image(path):

    if not path:
        return False

    try:
        path = Path(path)
    except Exception:
        return False

    if not path.exists():
        return False

    if not path.is_file():
        return False

    try:
        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False
    except Exception:
        return False

    lowered = str(path).lower()

    for term in FORBIDDEN_TERMS:
        if term in lowered:
            return False

    try:

        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            image.load()

        return True

    except Exception:
        return False


# ============================================================
# IMAGE SIGNATURE
# ============================================================

def image_signature(path):

    try:

        with Image.open(path) as image:

            image = ImageOps.exif_transpose(
                image
            )

            image = image.convert(
                "RGB"
            )

            image = image.resize(
                (64, 64),
                Image.Resampling.LANCZOS,
            )

            return hashlib.sha256(
                image.tobytes()
            ).hexdigest()

    except Exception:
        return ""


# ============================================================
# EXACT FILE SEARCH
# ============================================================

def exact_source_search(filename):
    """
    Searches assets/source ONLY for the exact filename.

    It does NOT select arbitrary images.
    """

    if not filename:
        return None

    filename = normalize_path_string(
        filename
    )

    wanted = Path(filename).name

    if not wanted:
        return None

    # Direct location first.
    direct = SOURCE_DIR / wanted

    if valid_image(direct):
        print(
            "[IMAGE] Exact source match:",
            direct,
        )
        return direct.resolve()

    # Recursive exact filename search.
    try:

        matches = SOURCE_DIR.rglob(
            wanted
        )

        for match in matches:

            if valid_image(match):

                print(
                    "[IMAGE] Recursive exact match:",
                    match,
                )

                return match.resolve()

    except Exception:
        pass

    return None


# ============================================================
# IMAGE STEM SEARCH
# ============================================================

def exact_stem_search(filename):
    """
    Handles extension mismatch.

    Example:

        selected story:
            story_1_image.jpg

        actual file:
            story_1_image.webp

    This is still considered the SAME requested file
    because the basename/stem is identical.
    """

    if not filename:
        return None

    filename = normalize_path_string(
        filename
    )

    requested = Path(filename)

    stem = requested.stem.lower()

    if not stem:
        return None

    try:

        for match in SOURCE_DIR.rglob("*"):

            if not match.is_file():
                continue

            if match.stem.lower() != stem:
                continue

            if valid_image(match):

                print(
                    "[IMAGE] Extension-mismatch recovery:",
                    match,
                )

                return match.resolve()

    except Exception:
        pass

    return None


# ============================================================
# RESOLVE EXACT IMAGE
# ============================================================

def resolve_image_path(value):

    if value is None:
        return None

    if isinstance(value, dict):

        value = (
            value.get("local_path")
            or value.get("path")
            or value.get("file")
            or value.get("image_path")
            or value.get("local_image")
            or value.get("photo_path")
        )

    if not value:
        return None

    value = normalize_path_string(
        value
    )

    if not value:
        return None

    candidate = Path(value)

    candidates = []

    # --------------------------------------------------------
    # Absolute path
    # --------------------------------------------------------

    if candidate.is_absolute():
        candidates.append(
            candidate
        )

    else:

        candidates.extend(
            [
                BASE_DIR / candidate,
                DATA_DIR / candidate,
                SOURCE_DIR / candidate,
            ]
        )

        # Filename only.
        if len(candidate.parts) == 1:

            candidates.append(
                SOURCE_DIR / candidate.name
            )

    # --------------------------------------------------------
    # Try direct candidates
    # --------------------------------------------------------

    seen = set()

    for item in candidates:

        try:
            item = item.resolve()
        except Exception:
            pass

        key = str(item)

        if key in seen:
            continue

        seen.add(key)

        print(
            "[IMAGE] Checking:",
            item,
        )

        if valid_image(item):

            print(
                "[IMAGE] VALID:",
                item,
            )

            return item

    # --------------------------------------------------------
    # Exact filename recovery
    # --------------------------------------------------------

    recovered = exact_source_search(
        candidate.name
    )

    if recovered:
        return recovered

    # --------------------------------------------------------
    # Extension recovery
    # --------------------------------------------------------

    recovered = exact_stem_search(
        candidate.name
    )

    if recovered:
        return recovered

    print(
        "[IMAGE] FAILED TO RESOLVE:",
        value,
    )

    return None


# ============================================================
# EXTRACT IMAGE REFERENCES
# ============================================================

def append_image_candidate(
    candidates,
    value,
):

    if value is None:
        return

    if isinstance(value, str):

        value = value.strip()

        if value:
            candidates.append(value)

        return

    if isinstance(value, dict):

        possible = (
            value.get("local_path")
            or value.get("path")
            or value.get("file")
            or value.get("image_path")
            or value.get("local_image")
            or value.get("photo_path")
        )

        if possible:
            append_image_candidate(
                candidates,
                possible,
            )

        return

    if isinstance(value, list):

        for item in value:

            append_image_candidate(
                candidates,
                item,
            )


# ============================================================
# FIND SELECTED IMAGES
# ============================================================

def find_selected_images(story):

    candidates = []

    fields = (
        "image_paths",
        "images",
        "image_path",
        "local_image",
        "local_images",
        "photo",
        "photos",
        "photo_path",
        "photo_paths",
        "image",
    )

    print()
    print("=" * 72)
    print("SELECTED STORY IMAGE REFERENCES")
    print("=" * 72)

    for field in fields:

        if field not in story:
            continue

        value = story.get(field)

        print(
            f"{field}:",
            repr(value),
        )

        append_image_candidate(
            candidates,
            value,
        )

    # --------------------------------------------------------
    # Resolve exact references
    # --------------------------------------------------------

    resolved = []
    seen_paths = set()
    seen_signatures = set()

    for candidate in candidates:

        path = resolve_image_path(
            candidate
        )

        if path is None:
            continue

        path_key = str(path)

        if path_key in seen_paths:
            continue

        seen_paths.add(path_key)

        signature = image_signature(
            path
        )

        if signature:

            if signature in seen_signatures:

                print(
                    "[IMAGE] Duplicate photo skipped:",
                    path.name,
                )

                continue

            seen_signatures.add(
                signature
            )

        resolved.append(path)

        print(
            "[IMAGE] ACCEPTED ARTICLE PHOTO:",
            path,
        )

        if len(resolved) >= 6:
            break

    return resolved


# ============================================================
# STORY INFORMATION
# ============================================================

def story_title(story):

    return clean_text(
        story.get("title")
        or story.get("headline"),
        "Rift Valley Regional Update",
    )


def story_county(story):

    return clean_text(
        story.get("county")
        or story.get("location"),
        "Rift Valley",
    )


def story_category(story):

    return clean_text(
        story.get("category"),
        "REGIONAL UPDATE",
    ).upper()


def story_summary(story):

    return clean_text(
        story.get("summary")
        or story.get("description")
        or story.get("excerpt"),
        "",
    )


def story_source(story):

    source_data = story.get(
        "source",
        "",
    )

    if isinstance(
        source_data,
        dict,
    ):

        source = clean_text(
            source_data.get("name")
            or source_data.get("title"),
            "Rift Valley Watch",
        )

    else:

        source = clean_text(
            source_data,
            "Rift Valley Watch",
        )

    lowered = source.lower()

    if (
        "citizen" in lowered
        or lowered == "ctv"
        or "citizen digital" in lowered
        or "citizen tv" in lowered
    ):
        return "Rift Valley Watch"

    return source


# ============================================================
# PREPARE IMAGE
# ============================================================

def prepare_image(path):

    with Image.open(path) as original:

        image = ImageOps.exif_transpose(
            original
        )

        image = image.convert(
            "RGB"
        )

    source_width, source_height = (
        image.size
    )

    if (
        source_width <= 0
        or source_height <= 0
    ):
        raise RuntimeError(
            f"Invalid image dimensions: {path}"
        )

    target_ratio = (
        WIDTH / HEIGHT
    )

    source_ratio = (
        source_width / source_height
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            new_height * source_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
            new_width / source_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
    )

    left = max(
        0,
        (new_width - WIDTH) // 2,
    )

    top = max(
        0,
        (new_height - HEIGHT) // 2,
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )

    return image


# ============================================================
# GRADIENT
# ============================================================

def add_gradient_overlay(image):

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    for y in range(HEIGHT):

        position = y / HEIGHT

        if position < 0.38:

            alpha = int(
                205
                * (
                    1
                    - position / 0.38
                )
            )

        else:

            alpha = int(
                175
                * (
                    (position - 0.38)
                    / 0.62
                )
            )

        alpha = max(
            0,
            min(205, alpha),
        )

        draw.line(
            (0, y, WIDTH, y),
            fill=(
                0,
                0,
                0,
                alpha,
            ),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


# ============================================================
# DECORATE SCENE
# ============================================================

def decorate_scene(
    image,
    story,
):

    image = add_gradient_overlay(
        image
    )

    draw = ImageDraw.Draw(
        image
    )

    white = (
        255,
        255,
        255,
    )

    muted = (
        218,
        225,
        232,
    )

    yellow = (
        245,
        185,
        62,
    )

    dark = (
        5,
        12,
        21,
    )

    darker = (
        4,
        10,
        17,
    )

    brand_font = get_font(
        42,
        True,
    )

    label_font = get_font(
        30,
        True,
    )

    title_font = get_font(
        65,
        True,
    )

    body_font = get_font(
        33,
        False,
    )

    footer_font = get_font(
        23,
        False,
    )

    title = story_title(
        story
    )

    county = story_county(
        story
    )

    category = story_category(
        story
    )

    summary = story_summary(
        story
    )

    source = story_source(
        story
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            126,
        ),
        fill=dark,
    )

    draw.rectangle(
        (
            0,
            122,
            WIDTH,
            130,
        ),
        fill=yellow,
    )

    draw.text(
        (
            58,
            35,
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=white,
    )

    # --------------------------------------------------------
    # COUNTY / CATEGORY
    # --------------------------------------------------------

    draw.text(
        (
            58,
            150,
        ),
        f"{county.upper()}  |  {category}",
        font=label_font,
        fill=yellow,
    )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    title_y = draw_wrapped_text(
        draw,
        title,
        58,
        240,
        WIDTH - 116,
        title_font,
        white,
        gap=12,
        maximum=5,
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if summary:

        summary_y = max(
            title_y + 55,
            930,
        )

        draw_wrapped_text(
            draw,
            summary,
            58,
            summary_y,
            WIDTH - 116,
            body_font,
            muted,
            gap=10,
            maximum=6,
        )

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    footer_y = HEIGHT - 110

    draw.rectangle(
        (
            0,
            footer_y - 25,
            WIDTH,
            HEIGHT,
        ),
        fill=darker,
    )

    draw.text(
        (
            58,
            footer_y + 10,
        ),
        f"SOURCE: {source}",
        font=footer_font,
        fill=muted,
    )

    return image


# ============================================================
# CREATE SCENE IMAGE
# ============================================================

def create_scene_image(
    source_path,
    story,
    output_path,
):

    print()
    print(
        "[SCENE] Source photo:",
        source_path,
    )

    image = prepare_image(
        source_path
    )

    image = decorate_scene(
        image,
        story,
    )

    image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene image was not created: {output_path}"
        )

    if output_path.stat().st_size < 50000:
        raise RuntimeError(
            f"Scene image is unexpectedly small: {output_path}"
        )


# ============================================================
# AUDIO DURATION
# ============================================================

def audio_duration():

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Missing narration file: {AUDIO_FILE}"
        )

    if AUDIO_FILE.stat().st_size < MIN_AUDIO_BYTES:
        raise RuntimeError(
            "Narration file is empty or too small"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(AUDIO_FILE),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not read narration duration:\n"
            + result.stdout
        )

    try:

        duration = float(
            result.stdout.strip()
        )

    except Exception:

        raise RuntimeError(
            "Narration duration could not be parsed:\n"
            + result.stdout
        )

    if duration <= 0:
        raise RuntimeError(
            "Narration duration is invalid"
        )

    print(
        "[AUDIO] Duration:",
        f"{duration:.2f}",
        "seconds",
    )

    return duration


# ============================================================
# CREATE SCENE VIDEO
# ============================================================

def create_scene_video(
    scene_image,
    output_path,
    duration,
):

    duration = max(
        1.0,
        float(duration),
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-loop",
        "1",

        "-i",
        str(scene_image),

        "-t",
        f"{duration:.3f}",

        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
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

        str(output_path),
    ]

    run(
        command,
        f"Creating {output_path.name}",
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene video was not created: {output_path}"
        )

    if output_path.stat().st_size < 50000:
        raise RuntimeError(
            f"Scene video is unexpectedly small: {output_path}"
        )


# ============================================================
# CONCATENATE
# ============================================================

def concatenate_scene_videos(
    scene_videos,
    output_path,
):

    if not scene_videos:
        raise RuntimeError(
            "No scene videos available"
        )

    concat_file = (
        WORK_DIR
        / "concat.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        for video in scene_videos:

            resolved = video.resolve()

            safe_path = str(
                resolved
            ).replace(
                "'",
                "'\\''",
            )

            file.write(
                f"file '{safe_path}'\n"
            )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

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

        "-an",

        str(output_path),
    ]

    run(
        command,
        "Concatenating scene videos",
    )

    if not output_path.exists():
        raise RuntimeError(
            "Silent video was not created"
        )


# ============================================================
# ADD AUDIO
# ============================================================

def add_audio(
    silent_video,
):

    if not silent_video.exists():
        raise RuntimeError(
            f"Silent video does not exist: {silent_video}"
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Narration does not exist: {AUDIO_FILE}"
        )

    if FINAL_FILE.exists():
        FINAL_FILE.unlink()

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-i",
        str(silent_video),

        "-i",
        str(AUDIO_FILE),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "copy",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-shortest",

        "-movflags",
        "+faststart",

        str(FINAL_FILE),
    ]

    run(
        command,
        "Adding narration",
    )


# ============================================================
# VALIDATE VIDEO
# ============================================================

def validate_final_video():

    if not FINAL_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created"
        )

    size = FINAL_FILE.stat().st_size

    if size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            f"Final MP4 is too small: {size} bytes"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_FILE),
    ]

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not inspect final MP4:\n"
            + result.stdout
        )

    output = result.stdout

    print()
    print("=" * 72)
    print("FINAL VIDEO PROBE")
    print("=" * 72)
    print(output)

    compact = output.replace(
        " ",
        "",
    ).lower()

    if "codec_type=video" not in compact:
        raise RuntimeError(
            "Final MP4 has no video stream"
        )

    if "codec_type=audio" not in compact:
        raise RuntimeError(
            "Final MP4 has no audio stream"
        )

    if "width=1080" not in compact:
        raise RuntimeError(
            "Final MP4 width is not 1080"
        )

    if "height=1920" not in compact:
        raise RuntimeError(
            "Final MP4 height is not 1920"
        )

    print()
    print("=" * 72)
    print("FINAL VIDEO VALIDATED")
    print("=" * 72)
    print(
        "FILE:",
        FINAL_FILE,
    )
    print(
        "SIZE:",
        size,
        "bytes",
    )


# ============================================================
# CLEAN WORK DIRECTORY
# ============================================================

def clean_work_directory():

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in WORK_DIR.iterdir():

        try:

            if (
                item.is_file()
                or item.is_symlink()
            ):
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception as error:

            print(
                "[WORK] Could not remove:",
                item,
                error,
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 72)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("VERSION: RVW_VIDEO_V35_EXACT_PHOTO_RECOVERY")
    print("=" * 72)

    # --------------------------------------------------------
    # Directories
    # --------------------------------------------------------

    for directory in (
        DATA_DIR,
        SOURCE_DIR,
        WORK_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------------
    # Required files
    # --------------------------------------------------------

    if not STORY_FILE.exists():
        raise RuntimeError(
            f"Missing selected story: {STORY_FILE}"
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            f"Missing selected script: {SCRIPT_FILE}"
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Missing narration: {AUDIO_FILE}"
        )

    print()
    print(
        "[INPUT] Story:",
        STORY_FILE,
    )

    print(
        "[INPUT] Script:",
        SCRIPT_FILE,
    )

    print(
        "[INPUT] Audio:",
        AUDIO_FILE,
    )

    # --------------------------------------------------------
    # Load selected story
    # --------------------------------------------------------

    story_data = load_json(
        STORY_FILE
    )

    story = get_story(
        story_data
    )

    print()
    print("=" * 72)
    print("SELECTED STORY")
    print("=" * 72)

    print(
        "TITLE:",
        story_title(story),
    )

    print(
        "COUNTY:",
        story_county(story),
    )

    print(
        "CATEGORY:",
        story_category(story),
    )

    print(
        "SOURCE:",
        story_source(story),
    )

    # --------------------------------------------------------
    # Find exact selected photos
    # --------------------------------------------------------

    images = find_selected_images(
        story
    )

    if not images:

        print()
        print("=" * 72)
        print("IMAGE RESOLUTION FAILURE")
        print("=" * 72)

        print(
            "The selected story contains image references,"
        )

        print(
            "but none could be resolved to a valid physical image."
        )

        print()
        print(
            "SOURCE DIRECTORY:",
            SOURCE_DIR,
        )

        if SOURCE_DIR.exists():

            print()
            print(
                "FILES CURRENTLY IN assets/source:"
            )

            for item in sorted(
                SOURCE_DIR.rglob("*")
            ):

                if item.is_file():

                    try:
                        size = item.stat().st_size
                    except Exception:
                        size = 0

                    print(
                        " -",
                        item.name,
                        "(",
                        size,
                        "bytes )",
                    )

        raise RuntimeError(
            "No valid real article photographs found in selected_story.json"
        )

    # --------------------------------------------------------
    # Selected image summary
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("REAL ARTICLE PHOTOS READY")
    print("=" * 72)

    for index, image in enumerate(
        images,
        start=1,
    ):

        print(
            f"{index}.",
            image,
        )

    print()
    print(
        "UNIQUE ARTICLE PHOTOS:",
        len(images),
    )

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    duration = audio_duration()

    # --------------------------------------------------------
    # Clean work directory
    # --------------------------------------------------------

    clean_work_directory()

    # --------------------------------------------------------
    # Scene durations
    # --------------------------------------------------------

    scene_count = len(images)

    if scene_count == 1:

        durations = [
            duration
        ]

    else:

        each = (
            duration
            / scene_count
        )

        durations = [
            each
            for _ in range(scene_count)
        ]

        durations[-1] = (
            duration
            - sum(durations[:-1])
        )

    # --------------------------------------------------------
    # Create scenes
    # --------------------------------------------------------

    scene_videos = []

    for index, image_path in enumerate(
        images,
        start=1,
    ):

        scene_image = (
            WORK_DIR
            / f"scene_{index:02d}.jpg"
        )

        scene_video = (
            WORK_DIR
            / f"scene_{index:02d}.mp4"
        )

        print()
        print("=" * 72)
        print(
            f"CREATING SCENE {index}/{scene_count}"
        )
        print("=" * 72)

        print(
            "ARTICLE PHOTO:",
            image_path,
        )

        print(
            "SCENE DURATION:",
            f"{durations[index - 1]:.2f}",
            "seconds",
        )

        create_scene_image(
            image_path,
            story,
            scene_image,
        )

        create_scene_video(
            scene_image,
            scene_video,
            durations[index - 1],
        )

        scene_videos.append(
            scene_video
        )

    # --------------------------------------------------------
    # Concatenate
    # --------------------------------------------------------

    silent_video = (
        WORK_DIR
        / "silent_video.mp4"
    )

    concatenate_scene_videos(
        scene_videos,
        silent_video,
    )

    # --------------------------------------------------------
    # Narration
    # --------------------------------------------------------

    add_audio(
        silent_video
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_final_video()

    print()
    print("=" * 72)
    print("GENERATION COMPLETED SUCCESSFULLY")
    print("=" * 72)

    print(
        "FINAL MP4:",
        FINAL_FILE,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print()
        print("=" * 72)
        print("RIFT VALLEY WATCH GENERATOR FAILED")
        print("=" * 72)
        print(
            "ERROR:",
            error,
        )
        print("=" * 72)

        sys.exit(1)
