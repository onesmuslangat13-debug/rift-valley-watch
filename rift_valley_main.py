from pathlib import Path
import json
import subprocess
import sys
import shutil

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V28_STABLE_MULTI_PHOTO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

SCENE_IMAGE_DIR = VIDEO_WORK_DIR / "scene_images"
SCENE_VIDEO_DIR = VIDEO_WORK_DIR / "scene_videos"

CONCAT_FILE = VIDEO_WORK_DIR / "concat.txt"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

VIDEO_CRF = "20"
VIDEO_PRESET = "medium"
AUDIO_BITRATE = "160k"

MIN_IMAGE_WIDTH = 400
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_BYTES = 10000

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

BAD_IMAGE_TERMS = (
    "citizen-tv",
    "citizentv",
    "citizen_tv",
    "citizen-logo",
    "citizen_logo",
    "citizenlogo",
    "ctv-logo",
    "ctv_logo",
    "ctvlogo",
    "avatar",
    "placeholder",
    "world-cup",
    "worldcup",
    "favicon",
    "logo-only",
    "logo_only",
    "profile-placeholder",
    "profile_avatar",
    "generic-placeholder",
)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


def section(title):
    log("")
    log("=" * 64)
    log(title)
    log("=" * 64)


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    directories = [
        DATA_DIR,
        OUTPUT_DIR,
        SOURCE_DIR,
        VIDEO_WORK_DIR,
        AUDIO_DIR,
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def clean_work_directories():
    section("CLEANING VIDEO WORK AREA")

    for directory in [
        SCENE_IMAGE_DIR,
        SCENE_VIDEO_DIR,
    ]:
        if directory.exists():
            shutil.rmtree(directory)

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    for filename in [
        "concat.txt",
        "video_only.mp4",
        "muxed_video.mp4",
        "final_video.mp4",
    ]:
        path = VIDEO_WORK_DIR / filename

        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    log("Video work area cleaned.")


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(command, description):
    log("")
    log(description)
    log("Command:")
    log(" ".join(str(value) for value in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    if result.stdout:
        log(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code "
            f"{result.returncode}."
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file does not exist: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file {path}: {exc}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"JSON file is not an object: {path}"
        )

    return data


# ============================================================
# TEXT
# ============================================================

def safe_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value).split()
    ).strip()


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=True):
    if bold:
        candidates = FONT_CANDIDATES_BOLD
    else:
        candidates = FONT_CANDIDATES_REGULAR

    for candidate in candidates:
        try:
            return ImageFont.truetype(
                candidate,
                size,
            )
        except Exception:
            continue

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):
    text = safe_text(text)

    if not text:
        return []

    words = text.split()

    lines = []

    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        candidate_width = (
            bbox[2] - bbox[0]
        )

        if candidate_width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    text,
    x,
    y,
    font,
    max_width,
    fill,
    line_spacing=10,
):
    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    current_y = y

    for line in lines:
        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=font,
        )

        line_height = (
            bbox[3] - bbox[1]
        )

        current_y += (
            line_height
            + line_spacing
        )

    return current_y


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_path_is_bad(path):
    lowered = str(path).lower()

    for term in BAD_IMAGE_TERMS:
        if term in lowered:
            return True

    return False


def image_is_usable(path):
    try:
        if not path.exists():
            return False

        if image_path_is_bad(path):
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(path) as image:
            width, height = image.size

        if width < MIN_IMAGE_WIDTH:
            return False

        if height < MIN_IMAGE_HEIGHT:
            return False

        return True

    except Exception:
        return False


# ============================================================
# IMAGE FINGERPRINT
# ============================================================

def image_fingerprint(path):
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((64, 64))
            image = image.resize(
                (32, 32),
                Image.Resampling.LANCZOS,
            )

            pixels = list(
                image.getdata()
            )

        if not pixels:
            return None

        total = 0.0

        for red, green, blue in pixels:
            total += (
                red
                + green
                + blue
            ) / 3.0

        average = (
            total / len(pixels)
        )

        result = 0

        for red, green, blue in pixels:
            value = (
                red
                + green
                + blue
            ) / 3.0

            result <<= 1

            if value >= average:
                result |= 1

        return result

    except Exception:
        return None


def fingerprint_distance(
    first,
    second,
):
    if first is None:
        return 999999

    if second is None:
        return 999999

    return (
        first ^ second
    ).bit_count()


def deduplicate_images(paths):
    accepted = []

    fingerprints = []

    for path in paths:
        fingerprint = image_fingerprint(
            path
        )

        duplicate = False

        for previous in fingerprints:
            distance = fingerprint_distance(
                fingerprint,
                previous,
            )

            if distance <= 70:
                duplicate = True
                break

        if duplicate:
            log(
                f"SKIPPING VISUALLY DUPLICATE: "
                f"{path}"
            )
            continue

        accepted.append(path)

        fingerprints.append(
            fingerprint
        )

    return accepted


# ============================================================
# IMAGE PATH RESOLUTION
# ============================================================

def resolve_image_paths(story):
    candidates = []

    raw_paths = story.get(
        "image_paths",
        [],
    )

    if isinstance(raw_paths, list):
        for value in raw_paths:
            if not value:
                continue

            path = Path(
                str(value)
            )

            if not path.is_absolute():
                path = BASE_DIR / path

            candidates.append(path)

    for pattern in [
        "story_image*.jpg",
        "story_image*.jpeg",
        "story_image*.png",
        "story_image*.webp",
    ]:
        for path in sorted(
            SOURCE_DIR.glob(pattern)
        ):
            candidates.append(path)

    unique = []

    seen = set()

    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        key = str(resolved)

        if key in seen:
            continue

        seen.add(key)

        if not image_is_usable(path):
            continue

        unique.append(path)

    return unique


# ============================================================
# IMAGE PREPARATION
# ============================================================

def crop_to_vertical(image):
    source_width, source_height = (
        image.size
    )

    target_ratio = (
        WIDTH / float(HEIGHT)
    )

    source_ratio = (
        source_width
        / float(source_height)
    )

    if source_ratio > target_ratio:
        crop_height = source_height
        crop_width = int(
            crop_height * target_ratio
        )
    else:
        crop_width = source_width
        crop_height = int(
            crop_width / target_ratio
        )

    crop_width = max(
        1,
        min(
            crop_width,
            source_width,
        ),
    )

    crop_height = max(
        1,
        min(
            crop_height,
            source_height,
        ),
    )

    left = (
        source_width - crop_width
    ) // 2

    top = (
        source_height - crop_height
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + crop_width,
            top + crop_height,
        )
    )


def prepare_background(
    image_path,
    scene_index,
):
    with Image.open(
        image_path
    ) as source:
        image = source.convert("RGB")

    image = crop_to_vertical(
        image
    )

    horizontal_positions = [
        0.50,
        0.42,
        0.58,
        0.46,
        0.54,
    ]

    vertical_positions = [
        0.50,
        0.46,
        0.54,
        0.48,
        0.52,
    ]

    if image.width > 100 and image.height > 100:
        h_bias = horizontal_positions[
            scene_index
            % len(horizontal_positions)
        ]

        v_bias = vertical_positions[
            scene_index
            % len(vertical_positions)
        ]

        crop_ratio = 0.96

        crop_width = int(
            image.width * crop_ratio
        )

        crop_height = int(
            image.height * crop_ratio
        )

        crop_width = max(
            1,
            min(
                crop_width,
                image.width,
            ),
        )

        crop_height = max(
            1,
            min(
                crop_height,
                image.height,
            ),
        )

        left_space = (
            image.width
            - crop_width
        )

        top_space = (
            image.height
            - crop_height
        )

        left = int(
            left_space * h_bias
        )

        top = int(
            top_space * v_bias
        )

        image = image.crop(
            (
                left,
                top,
                left + crop_width,
                top + crop_height,
            )
        )

    return image.resize(
        (WIDTH, HEIGHT),
        Image.Resampling.LANCZOS,
    )


# ============================================================
# OVERLAY
# ============================================================

def add_overlay(image):
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            190,
        ),
        fill=(
            0,
            0,
            0,
            185,
        ),
    )

    draw.rectangle(
        (
            0,
            HEIGHT - 540,
            WIDTH,
            HEIGHT,
        ),
        fill=(
            0,
            0,
            0,
            215,
        ),
    )

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            18,
        ),
        fill=(
            220,
            30,
            45,
            255,
        ),
    )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    )


# ============================================================
# STORY GRAPHICS
# ============================================================

def add_story_graphics(
    image,
    story,
    scene_index,
    scene_total,
):
    draw = ImageDraw.Draw(
        image
    )

    county = safe_text(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    title = safe_text(
        story.get(
            "title",
            "Latest regional development",
        )
    )

    source = safe_text(
        story.get(
            "source",
            "Rift Valley Watch",
        )
    )

    header_font = get_font(
        38,
        True,
    )

    county_font = get_font(
        30,
        True,
    )

    title_font = get_font(
        56,
        True,
    )

    source_font = get_font(
        29,
        False,
    )

    draw.text(
        (
            55,
            48,
        ),
        "RIFT VALLEY WATCH",
        font=header_font,
        fill=(
            255,
            255,
            255,
        ),
    )

    draw.text(
        (
            55,
            108,
        ),
        county.upper()
        + " COUNTY",
        font=county_font,
        fill=(
            230,
            230,
            230,
        ),
    )

    title_lines = wrap_text(
        draw,
        title,
        title_font,
        WIDTH - 110,
    )

    title_y = HEIGHT - 470

    for line in title_lines[:4]:
        draw.text(
            (
                55,
                title_y,
            ),
            line,
            font=title_font,
            fill=(
                255,
                255,
                255,
            ),
        )

        bbox = draw.textbbox(
            (
                55,
                title_y,
            ),
            line,
            font=title_font,
        )

        title_y += (
            bbox[3]
            - bbox[1]
            + 12
        )

    draw.text(
        (
            55,
            HEIGHT - 92,
        ),
        "SOURCE: " + source,
        font=source_font,
        fill=(
            220,
            220,
            220,
        ),
    )

    # Only show a scene counter when the reel actually
    # contains different photographs.
    if scene_total > 1:
        counter = (
            f"{scene_index + 1}"
            f"/{scene_total}"
        )

        bbox = draw.textbbox(
            (
                0,
                0,
            ),
            counter,
            font=header_font,
        )

        counter_width = (
            bbox[2]
            - bbox[0]
        )

        box_left = (
            WIDTH
            - counter_width
            - 90
        )

        draw.rounded_rectangle(
            (
                box_left,
                48,
                WIDTH - 45,
                110,
            ),
            radius=12,
            fill=(
                0,
                0,
                0,
                170,
            ),
        )

        draw.text(
            (
                box_left + 22,
                57,
            ),
            counter,
            font=header_font,
            fill=(
                255,
                255,
                255,
            ),
        )

    return image


# ============================================================
# SCENE IMAGE
# ============================================================

def create_scene_image(
    source_path,
    story,
    scene_index,
    scene_total,
):
    background = prepare_background(
        source_path,
        scene_index,
    )

    blurred = background.filter(
        ImageFilter.GaussianBlur(
            radius=6
        )
    )

    canvas = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT,
        ),
    )

    canvas.paste(
        blurred,
        (
            0,
            0,
        ),
    )

    canvas.paste(
        background,
        (
            0,
            0,
        ),
    )

    canvas = add_overlay(
        canvas
    )

    canvas = add_story_graphics(
        canvas,
        story,
        scene_index,
        scene_total,
    )

    output_path = (
        SCENE_IMAGE_DIR
        / f"scene_{scene_index + 1:02d}.jpg"
    )

    canvas.convert(
        "RGB"
    ).save(
        output_path,
        "JPEG",
        quality=94,
        optimize=True,
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene image was not created: "
            f"{output_path}"
        )

    return output_path


# ============================================================
# AUDIO DURATION
# ============================================================

def get_audio_duration():
    if not NARRATION_FILE.exists():
        raise RuntimeError(
            f"Narration file missing: "
            f"{NARRATION_FILE}"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(NARRATION_FILE),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFprobe could not read narration duration."
        )

    try:
        duration = float(
            result.stdout.strip()
        )
    except Exception:
        duration = 0.0

    if duration <= 0:
        raise RuntimeError(
            "Narration duration is invalid."
        )

    return duration


# ============================================================
# SCENE DURATIONS
# ============================================================

def calculate_scene_durations(
    total_duration,
    scene_count,
):
    if scene_count <= 1:
        return [
            max(
                1.0,
                total_duration,
            )
        ]

    duration = (
        total_duration
        / float(scene_count)
    )

    if duration < 2.5:
        return [
            total_duration
        ]

    return [
        duration
        for _ in range(scene_count)
    ]


# ============================================================
# SCENE VIDEO
# ============================================================

def create_scene_video(
    image_path,
    duration,
    scene_index,
):
    output_path = (
        SCENE_VIDEO_DIR
        / f"scene_{scene_index + 1:02d}.mp4"
    )

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
        str(image_path),
        "-t",
        f"{duration:.3f}",
        "-r",
        str(FPS),
        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=disable,"
            "format=yuv420p"
        ),
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        VIDEO_PRESET,
        "-crf",
        VIDEO_CRF,
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]

    run_command(
        command,
        f"Creating scene {scene_index + 1}",
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene video missing: "
            f"{output_path}"
        )

    if output_path.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene video is too small: "
            f"{output_path}"
        )

    return output_path


# ============================================================
# CONCAT FILE
# ============================================================

def write_concat_file(
    scene_videos,
):
    with CONCAT_FILE.open(
        "w",
        encoding="utf-8",
    ) as handle:
        for video in scene_videos:
            resolved = str(
                video.resolve()
            )

            escaped = resolved.replace(
                "'",
                "'\\''",
            )

            handle.write(
                f"file '{escaped}'\n"
            )


# ============================================================
# CONCATENATE
# ============================================================

def concatenate_scenes(
    scene_videos,
):
    if not scene_videos:
        raise RuntimeError(
            "No scene videos exist."
        )

    write_concat_file(
        scene_videos
    )

    output_path = (
        VIDEO_WORK_DIR
        / "video_only.mp4"
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
        str(CONCAT_FILE),
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        VIDEO_PRESET,
        "-crf",
        VIDEO_CRF,
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(output_path),
    ]

    run_command(
        command,
        "Concatenating scene videos",
    )

    if not output_path.exists():
        raise RuntimeError(
            "Video-only MP4 was not created."
        )

    return output_path


# ============================================================
# AUDIO MUX
# ============================================================

def mux_audio(
    video_only,
):
    output_path = (
        VIDEO_WORK_DIR
        / "muxed_video.mp4"
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_only),
        "-i",
        str(NARRATION_FILE),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        VIDEO_CODEC,
        "-preset",
        VIDEO_PRESET,
        "-crf",
        VIDEO_CRF,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        AUDIO_BITRATE,
        "-ar",
        "44100",
        "-af",
        "aresample=async=1:first_pts=0",
        "-shortest",
        str(output_path),
    ]

    run_command(
        command,
        "Muxing narration with video",
    )

    if not output_path.exists():
        raise RuntimeError(
            "Muxed MP4 was not created."
        )

    return output_path


# ============================================================
# FINAL COPY
# ============================================================

def create_final_video(
    muxed_video,
):
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    shutil.copy2(
        muxed_video,
        FINAL_VIDEO,
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 copy failed."
        )

    if FINAL_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is unexpectedly small."
        )


# ============================================================
# FFPROBE
# ============================================================

def probe_video_value(
    field,
):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        f"stream={field}",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    return result.stdout.strip()


def probe_audio_codec():
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    return result.stdout.strip()


def probe_final_duration():
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        return 0.0


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_final_video():
    section("VALIDATING FINAL MP4")

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    file_size = (
        FINAL_VIDEO.stat().st_size
    )

    if file_size < 100000:
        raise RuntimeError(
            "Final MP4 is smaller than 100 KB."
        )

    width = probe_video_value(
        "width"
    )

    height = probe_video_value(
        "height"
    )

    codec = probe_video_value(
        "codec_name"
    )

    audio_codec = probe_audio_codec()

    duration = probe_final_duration()

    log(
        f"MP4 size: {file_size} bytes"
    )

    log(
        f"Width: {width}"
    )

    log(
        f"Height: {height}"
    )

    log(
        f"Video codec: {codec}"
    )

    log(
        f"Audio codec: {audio_codec}"
    )

    log(
        f"Duration: {duration:.2f} seconds"
    )

    if width != "1080":
        raise RuntimeError(
            f"Video width is {width}; expected 1080."
        )

    if height != "1920":
        raise RuntimeError(
            f"Video height is {height}; expected 1920."
        )

    if not audio_codec:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    if duration < 5:
        raise RuntimeError(
            "Final MP4 duration is less than 5 seconds."
        )

    section(
        "FINAL MP4 VALIDATION PASSED"
    )


# ============================================================
# STORY VALIDATION
# ============================================================

def validate_story(story):
    required = [
        "title",
        "county",
        "source",
        "image_paths",
    ]

    for field in required:
        if field not in story:
            raise RuntimeError(
                f"Selected story is missing: {field}"
            )

    if not safe_text(
        story.get("title")
    ):
        raise RuntimeError(
            "Selected story title is empty."
        )

    if not safe_text(
        story.get("county")
    ):
        raise RuntimeError(
            "Selected story county is empty."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    section(
        "RIFT VALLEY WATCH VIDEO GENERATOR"
    )

    log(
        "RVW_VIDEO_V28_STABLE_MULTI_PHOTO"
    )

    log(
        f"Base directory: {BASE_DIR}"
    )

    ensure_directories()

    clean_work_directories()

    section(
        "LOADING SELECTED STORY"
    )

    story = load_json(
        STORY_FILE
    )

    validate_story(
        story
    )

    log(
        f"County: {story.get('county', '')}"
    )

    log(
        f"Source: {story.get('source', '')}"
    )

    log(
        f"Title: {story.get('title', '')}"
    )

    section(
        "CHECKING NARRATION"
    )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            f"Narration MP3 was not found: "
            f"{NARRATION_FILE}"
        )

    narration_size = (
        NARRATION_FILE.stat().st_size
    )

    if narration_size < 1000:
        raise RuntimeError(
            "Narration MP3 is too small."
        )

    narration_duration = (
        get_audio_duration()
    )

    log(
        f"Narration size: "
        f"{narration_size} bytes"
    )

    log(
        f"Narration duration: "
        f"{narration_duration:.2f} seconds"
    )

    section(
        "RESOLVING REAL ARTICLE PHOTOGRAPHS"
    )

    image_paths = resolve_image_paths(
        story
    )

    log(
        f"Usable image files found: "
        f"{len(image_paths)}"
    )

    if not image_paths:
        raise RuntimeError(
            "No usable real article photographs were found."
        )

    image_paths = deduplicate_images(
        image_paths
    )

    log(
        f"Distinct photographs after visual deduplication: "
        f"{len(image_paths)}"
    )

    if not image_paths:
        raise RuntimeError(
            "All image candidates were rejected as duplicates."
        )

    for index, path in enumerate(
        image_paths,
        start=1,
    ):
        log(
            f"{index}. {path}"
        )

    selected_images = image_paths[:5]

    scene_count = len(
        selected_images
    )

    section(
        "SCENE PLAN"
    )

    log(
        f"Distinct photographs available: "
        f"{len(image_paths)}"
    )

    log(
        f"Photographs selected for reel: "
        f"{scene_count}"
    )

    if scene_count == 1:
        log(
            "ONE REAL PHOTOGRAPH AVAILABLE."
        )
        log(
            "No fake multi-photo counter will be displayed."
        )
    else:
        log(
            "Multiple distinct real photographs will be used."
        )

    durations = calculate_scene_durations(
        narration_duration,
        scene_count,
    )

    for index, duration in enumerate(
        durations,
        start=1,
    ):
        log(
            f"Scene {index}: "
            f"{duration:.2f} seconds"
        )

    section(
        "CREATING VISUAL SCENES"
    )

    scene_videos = []

    for index, source_path in enumerate(
        selected_images
    ):
        log("")
        log(
            f"PHOTO {index + 1}/{scene_count}"
        )

        log(
            f"Source: {source_path}"
        )

        scene_image = create_scene_image(
            source_path,
            story,
            index,
            scene_count,
        )

        log(
            f"Scene image: {scene_image}"
        )

        scene_video = create_scene_video(
            scene_image,
            durations[index],
            index,
        )

        log(
            f"Scene video: {scene_video}"
        )

        scene_videos.append(
            scene_video
        )

    if not scene_videos:
        raise RuntimeError(
            "No scene videos were generated."
        )

    section(
        "ASSEMBLING SCENES"
    )

    video_only = concatenate_scenes(
        scene_videos
    )

    section(
        "ADDING NARRATION"
    )

    muxed_video = mux_audio(
        video_only
    )

    section(
        "CREATING FINAL MP4"
    )

    create_final_video(
        muxed_video
    )

    log(
        f"Final video: {FINAL_VIDEO}"
    )

    validate_final_video()

    section(
        "RIFT VALLEY WATCH GENERATION SUCCESSFUL"
    )

    final_duration = (
        probe_final_duration()
    )

    log(
        f"Final MP4: {FINAL_VIDEO}"
    )

    log(
        f"Final size: "
        f"{FINAL_VIDEO.stat().st_size} bytes"
    )

    log(
        f"Final duration: "
        f"{final_duration:.2f} seconds"
    )

    log(
        f"Real photographs used: "
        f"{scene_count}"
    )

    log(
        "No repeated-photo scene counter was used."
    )

    log(
        "Generation completed successfully."
    )

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
        log("")
        log(
            "Generation interrupted."
        )
        sys.exit(130)

    except Exception as exc:
        log("")
        log("=" * 64)
        log(
            "RIFT VALLEY WATCH GENERATION FAILED"
        )
        log("=" * 64)
        log(
            f"ERROR: {exc}"
        )
        log("")

        import traceback

        traceback.print_exc()

        sys.exit(1)
