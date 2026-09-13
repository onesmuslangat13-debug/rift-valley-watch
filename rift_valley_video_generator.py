import os
import re
import json
import shutil
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageOps, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: V11 ROBUST
# ============================================================

GENERATOR_VERSION = "RIFT_VALLEY_WATCH_GENERATOR_V11"

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ROOT / "audio"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"
AUDIO_FILE = AUDIO_DIR / "narration.mp3"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

WIDTH = 1080
HEIGHT = 1920


# ============================================================
# LOG
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Required JSON file not found: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        raise RuntimeError(
            f"Could not read {path}: {exc}"
        )


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def first_nonempty(*values):
    for value in values:
        text = clean_text(value)

        if text:
            return text

    return ""


def remove_source_language(text):
    text = clean_text(text)

    patterns = [
        r"\baccording to\s+[^.]+",
        r"\breported by\s+[^.]+",
        r"\breport from\s+[^.]+",
        r"\bsource\s*:\s*[^.]+",
        r"\bvia\s+[^.]+",
        r"\bas reported by\s+[^.]+",
        r"\bthe source said\b",
        r"\bthe publisher said\b",
    ]

    for pattern in patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    return re.sub(
        r"\s+([,.])",
        r"\1",
        text,
    ).strip()


# ============================================================
# STORY FIELDS
# ============================================================

def get_story_title(story):
    return first_nonempty(
        story.get("title"),
        story.get("headline"),
        story.get("story_title"),
    )


def get_story_county(story):
    return first_nonempty(
        story.get("county"),
        story.get("location"),
        "Rift Valley",
    )


def get_narration(story, script):
    candidates = [
        script.get("narration"),
        script.get("voiceover"),
        script.get("text"),
        story.get("script"),
        story.get("narration"),
        story.get("voiceover"),
    ]

    for candidate in candidates:
        text = remove_source_language(
            candidate
        )

        if text:
            return text

    title = get_story_title(story)
    county = get_story_county(story)

    summary = first_nonempty(
        story.get("summary"),
        story.get("description"),
        story.get("excerpt"),
        story.get("body"),
    )

    if title and summary:
        return remove_source_language(
            f"Here is the latest development from "
            f"{county}. {title}. {summary}"
        )

    if title:
        return (
            f"Rift Valley Watch. {title}."
        )

    raise RuntimeError(
        "No usable narration was provided."
    )


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_file(path):
    path = Path(path)

    if not path.exists():
        return False

    if not path.is_file():
        return False

    try:
        if path.stat().st_size < 5000:
            return False
    except Exception:
        return False

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            if image.width < 250:
                return False

            if image.height < 180:
                return False

        return True

    except Exception:
        return False


# ============================================================
# IMAGE URL
# ============================================================

def clean_image_url(value):
    value = clean_text(value)

    if not value:
        return ""

    if value.startswith("//"):
        value = "https:" + value

    if not value.startswith(
        ("http://", "https://")
    ):
        return ""

    return value


# ============================================================
# DOWNLOAD REMOTE IMAGE
# ============================================================

def download_image(image_url, article_url=""):
    image_url = clean_image_url(
        image_url
    )

    if not image_url:
        raise RuntimeError(
            "Remote image URL is empty."
        )

    log(
        f"Downloading article image: {image_url}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": (
            "image/avif,image/webp,"
            "image/apng,image/svg+xml,"
            "image/*,*/*;q=0.8"
        ),
    }

    if article_url:
        headers["Referer"] = article_url

    try:
        response = requests.get(
            image_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:
        raise RuntimeError(
            f"Could not download article image: {exc}"
        )

    if len(response.content) < 10000:
        raise RuntimeError(
            "Downloaded article image is too small."
        )

    temporary_file = (
        SOURCE_DIR /
        "downloaded_source_image"
    )

    try:
        with temporary_file.open(
            "wb"
        ) as file:
            file.write(
                response.content
            )

        if not validate_image_file(
            temporary_file
        ):
            raise RuntimeError(
                "Downloaded image failed validation."
            )

        with Image.open(
            temporary_file
        ) as image:
            image = ImageOps.exif_transpose(
                image
            )

            image = image.convert(
                "RGB"
            )

            image.save(
                SOURCE_IMAGE,
                "JPEG",
                quality=95,
                optimize=True,
            )

        temporary_file.unlink(
            missing_ok=True
        )

        if not validate_image_file(
            SOURCE_IMAGE
        ):
            raise RuntimeError(
                "Converted article image failed validation."
            )

        log(
            f"REMOTE IMAGE SAVED: {SOURCE_IMAGE}"
        )

        return SOURCE_IMAGE

    except Exception:
        temporary_file.unlink(
            missing_ok=True
        )
        raise


# ============================================================
# IMAGE RESOLUTION
# ============================================================

def resolve_image(story, script):
    log("")
    log("=" * 60)
    log("IMAGE RESOLUTION")
    log("=" * 60)

    local_candidates = [
        story.get("local_image"),
        script.get("local_image"),
        story.get("image_path"),
        script.get("image_path"),
        SOURCE_IMAGE,
    ]

    checked = set()

    for candidate in local_candidates:
        if not candidate:
            continue

        candidate = Path(
            str(candidate)
        )

        if not candidate.is_absolute():
            candidate = ROOT / candidate

        try:
            candidate = candidate.resolve()
        except Exception:
            pass

        key = str(candidate)

        if key in checked:
            continue

        checked.add(key)

        log(
            f"Checking local image: {candidate}"
        )

        if validate_image_file(
            candidate
        ):
            log(
                "VERIFIED LOCAL ARTICLE IMAGE FOUND"
            )

            return candidate

    image_url = first_nonempty(
        story.get("image"),
        story.get("image_url"),
        story.get("imageUrl"),
        script.get("image"),
        script.get("image_url"),
        script.get("imageUrl"),
    )

    if image_url:
        return download_image(
            image_url,
            story.get("url", ""),
        )

    raise RuntimeError(
        "No valid local article image exists "
        "and no remote article image URL was supplied."
    )


# ============================================================
# BASE IMAGE
# ============================================================

def prepare_base_image(image_path):
    image_path = Path(
        image_path
    )

    if not validate_image_file(
        image_path
    ):
        raise RuntimeError(
            f"Invalid source image: {image_path}"
        )

    with Image.open(
        image_path
    ) as image:
        image = ImageOps.exif_transpose(
            image
        )

        image = image.convert(
            "RGB"
        )

        source_ratio = (
            image.width /
            image.height
        )

        target_ratio = (
            WIDTH /
            HEIGHT
        )

        if source_ratio > target_ratio:
            new_height = HEIGHT

            new_width = int(
                new_height *
                source_ratio
            )

        else:
            new_width = WIDTH

            new_height = int(
                new_width /
                source_ratio
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
            (image.width - WIDTH) // 2,
        )

        top = max(
            0,
            (image.height - HEIGHT) // 2,
        )

        image = image.crop(
            (
                left,
                top,
                left + WIDTH,
                top + HEIGHT,
            )
        )

        return image.copy()


# ============================================================
# FONTS
# ============================================================

def find_font(bold=False):
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
        if os.path.exists(path):
            return path

    return None


FONT_BOLD = find_font(True)
FONT_REGULAR = find_font(False)


def get_font(size, bold=False):
    path = (
        FONT_BOLD
        if bold
        else FONT_REGULAR
    )

    if path:
        return ImageFont.truetype(
            path,
            size,
        )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAP
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):
    words = text.split()

    lines = []
    current = ""

    for word in words:
        test = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = (
            bbox[2] -
            bbox[0]
        )

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    return lines


def draw_wrapped_text(
    draw,
    text,
    x,
    y,
    font,
    max_width,
    line_gap=10,
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
            (
                x,
                current_y,
            ),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

        bbox = draw.textbbox(
            (
                x,
                current_y,
            ),
            line,
            font=font,
        )

        current_y += (
            bbox[3] -
            bbox[1] +
            line_gap
        )

    return current_y


# ============================================================
# SCENE IMAGE
# ============================================================

def create_scene_image(
    base_image,
    title,
    county,
    scene_index,
    scene_count,
    output_path,
):
    image = base_image.copy()

    draw = ImageDraw.Draw(
        image
    )

    top_height = 330

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            top_height,
        ),
        fill=(0, 0, 0),
    )

    brand_font = get_font(
        42,
        bold=True,
    )

    draw.text(
        (
            55,
            45,
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(255, 255, 255),
    )

    county_font = get_font(
        30,
        bold=True,
    )

    draw.text(
        (
            55,
            112,
        ),
        county.upper(),
        font=county_font,
        fill=(225, 225, 225),
    )

    title_font = get_font(
        45,
        bold=True,
    )

    draw_wrapped_text(
        draw,
        title,
        55,
        165,
        title_font,
        WIDTH - 110,
        line_gap=7,
    )

    bottom_height = 210

    draw.rectangle(
        (
            0,
            HEIGHT - bottom_height,
            WIDTH,
            HEIGHT,
        ),
        fill=(0, 0, 0),
    )

    footer_font = get_font(
        28,
        bold=True,
    )

    draw.text(
        (
            55,
            HEIGHT - 165,
        ),
        "RIFT VALLEY • KENYA",
        font=footer_font,
        fill=(230, 230, 230),
    )

    scene_font = get_font(
        24,
        bold=True,
    )

    scene_text = (
        f"{scene_index}/{scene_count}"
    )

    bbox = draw.textbbox(
        (
            0,
            0,
        ),
        scene_text,
        font=scene_font,
    )

    draw.text(
        (
            WIDTH -
            55 -
            (
                bbox[2] -
                bbox[0]
            ),
            HEIGHT - 75,
        ),
        scene_text,
        font=scene_font,
        fill=(200, 200, 200),
    )

    image.save(
        output_path,
        "JPEG",
        quality=94,
        optimize=True,
    )


# ============================================================
# AUDIO
# ============================================================

def generate_audio(narration):
    narration = remove_source_language(
        narration
    )

    narration = clean_text(
        narration
    )

    if not narration:
        raise RuntimeError(
            "Narration is empty."
        )

    if len(narration.split()) < 50:
        raise RuntimeError(
            "Narration is too short."
        )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if AUDIO_FILE.exists():
        AUDIO_FILE.unlink()

    log("")
    log(
        "GENERATING NARRATION"
    )

    try:
        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(
            str(AUDIO_FILE)
        )

    except Exception as exc:
        raise RuntimeError(
            f"gTTS narration failed: {exc}"
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration MP3 was not created."
        )

    if AUDIO_FILE.stat().st_size < 1000:
        raise RuntimeError(
            "Narration MP3 is suspiciously small."
        )

    log(
        f"AUDIO: {AUDIO_FILE}"
    )

    return AUDIO_FILE


# ============================================================
# DURATION
# ============================================================

def get_media_duration(path):
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
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Could not determine duration of {path}: "
            f"{result.stderr}"
        )

    try:
        return float(
            result.stdout.strip()
        )

    except Exception:
        raise RuntimeError(
            f"Invalid duration returned for {path}"
        )


# ============================================================
# SILENT VIDEO
# ============================================================

def create_silent_video(
    scene_files,
    duration,
    output_path,
):
    output_path = Path(
        output_path
    )

    if output_path.exists():
        output_path.unlink()

    if not scene_files:
        raise RuntimeError(
            "No scene images were created."
        )

    scene_duration = (
        duration /
        len(scene_files)
    )

    concat_file = (
        WORK_DIR /
        "scenes.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        for scene in scene_files:
            scene_path = (
                Path(scene)
                .resolve()
            )

            safe_path = str(
                scene_path
            ).replace(
                "'",
                "'\\''",
            )

            file.write(
                f"file '{safe_path}'\n"
            )

            file.write(
                f"duration {scene_duration:.6f}\n"
            )

        last_scene = (
            Path(
                scene_files[-1]
            ).resolve()
        )

        safe_last = str(
            last_scene
        ).replace(
            "'",
            "'\\''",
        )

        file.write(
            f"file '{safe_last}'\n"
        )

    log("")
    log(
        "CREATING VIDEO"
    )

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
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:"
            "(ow-iw)/2:(oh-ih)/2"
        ),
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log(result.stdout)
        log(result.stderr)

        raise RuntimeError(
            "FFmpeg failed while creating silent video."
        )

    if not output_path.exists():
        raise RuntimeError(
            "Silent video was not created."
        )

    return output_path


# ============================================================
# COMBINE AUDIO
# ============================================================

def combine_video_audio(
    video_path,
    audio_path,
    output_path,
):
    output_path = Path(
        output_path
    )

    if output_path.exists():
        output_path.unlink()

    log("")
    log(
        "COMBINING VIDEO + NARRATION"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
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
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log(result.stdout)
        log(result.stderr)

        raise RuntimeError(
            "FFmpeg failed while combining video and audio."
        )

    if not output_path.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return output_path


# ============================================================
# FINAL QC
# ============================================================

def verify_video(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 does not exist: {path}"
        )

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:
        raise RuntimeError(
            "Final MP4 failed FFprobe validation."
        )

    try:
        info = json.loads(
            probe.stdout
        )
    except Exception:
        raise RuntimeError(
            "Could not parse FFprobe output."
        )

    streams = info.get(
        "streams",
        [],
    )

    video_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
    ]

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    if not video_streams:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if not audio_streams:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    video = video_streams[0]

    if video.get("width") != 1080:
        raise RuntimeError(
            f"Video width is {video.get('width')}, expected 1080."
        )

    if video.get("height") != 1920:
        raise RuntimeError(
            f"Video height is {video.get('height')}, expected 1920."
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

    if duration < 5:
        raise RuntimeError(
            "Final video is shorter than 5 seconds."
        )

    log("")
    log("=" * 70)
    log("FINAL VIDEO QC")
    log("=" * 70)
    log(
        f"FILE: {path}"
    )
    log(
        f"SIZE: {size:,} bytes"
    )
    log(
        f"DURATION: {duration:.2f}s"
    )
    log(
        "VIDEO: 1080x1920"
    )
    log(
        "AUDIO: PRESENT"
    )
    log(
        "FINAL MP4 QC PASSED"
    )


# ============================================================
# CLEAN WORK
# ============================================================

def clean_work_files():
    if not WORK_DIR.exists():
        return

    for item in WORK_DIR.iterdir():
        try:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except Exception:
            pass


# ============================================================
# GENERATE
# ============================================================

def generate_video(
    story,
    script=None,
):
    if script is None:
        script = {}

    prepare_directories()
    clean_work_files()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATOR")
    log("=" * 70)
    log(
        f"GENERATOR VERSION: {GENERATOR_VERSION}"
    )

    title = get_story_title(
        story
    )

    county = get_story_county(
        story
    )

    narration = get_narration(
        story,
        script,
    )

    if not title:
        raise RuntimeError(
            "Selected story has no title."
        )

    if not narration:
        raise RuntimeError(
            "Selected story has no narration."
        )

    log("")
    log(
        "SELECTED STORY"
    )
    log(
        f"TITLE : {title}"
    )
    log(
        f"COUNTY: {county}"
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_path = resolve_image(
        story,
        script,
    )

    if not validate_image_file(
        image_path
    ):
        raise RuntimeError(
            f"Resolved image is invalid: {image_path}"
        )

    log(
        f"ARTICLE IMAGE: {image_path}"
    )

    base_image = prepare_base_image(
        image_path
    )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    audio_duration = get_media_duration(
        audio_path
    )

    if audio_duration < 5:
        raise RuntimeError(
            "Narration audio is too short."
        )

    target_duration = min(
        max(audio_duration, 15.0),
        60.0,
    )

    # --------------------------------------------------------
    # SCENES
    # --------------------------------------------------------

    scene_count = 5

    scene_dir = (
        WORK_DIR /
        "scenes"
    )

    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    scene_files = []

    for index in range(
        scene_count
    ):
        scene_path = (
            scene_dir /
            f"scene_{index + 1:02d}.jpg"
        )

        zoom_factor = (
            1.0 +
            (0.02 * index)
        )

        scene_image = base_image.copy()

        if zoom_factor > 1.0:
            new_width = int(
                WIDTH *
                zoom_factor
            )

            new_height = int(
                HEIGHT *
                zoom_factor
            )

            scene_image = scene_image.resize(
                (
                    new_width,
                    new_height,
                ),
                Image.Resampling.LANCZOS,
            )

            left = (
                new_width -
                WIDTH
            ) // 2

            top = (
                new_height -
                HEIGHT
            ) // 2

            scene_image = scene_image.crop(
                (
                    left,
                    top,
                    left + WIDTH,
                    top + HEIGHT,
                )
            )

        create_scene_image(
            scene_image,
            title,
            county,
            index + 1,
            scene_count,
            scene_path,
        )

        if not validate_image_file(
            scene_path
        ):
            raise RuntimeError(
                f"Scene image failed validation: {scene_path}"
            )

        scene_files.append(
            scene_path
        )

    # --------------------------------------------------------
    # SILENT VIDEO
    # --------------------------------------------------------

    silent_video = (
        WORK_DIR /
        "silent.mp4"
    )

    create_silent_video(
        scene_files,
        target_duration,
        silent_video,
    )

    # --------------------------------------------------------
    # FINAL VIDEO
    # --------------------------------------------------------

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    combine_video_audio(
        silent_video,
        audio_path,
        OUTPUT_FILE,
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    verify_video(
        OUTPUT_FILE
    )

    log("")
    log("=" * 70)
    log(
        "RIFT VALLEY WATCH VIDEO GENERATED SUCCESSFULLY"
    )
    log("=" * 70)
    log(
        f"OUTPUT: {OUTPUT_FILE}"
    )

    return OUTPUT_FILE


# ============================================================
# MAIN
# ============================================================

def main():
    prepare_directories()

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH VIDEO GENERATOR")
    log("=" * 70)

    if not STORY_FILE.exists():
        raise RuntimeError(
            f"Missing selected story: {STORY_FILE}"
        )

    story = load_json(
        STORY_FILE
    )

    if SCRIPT_FILE.exists():
        script = load_json(
            SCRIPT_FILE
        )
    else:
        script = {}

    generate_video(
        story,
        script,
    )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Generator finished but final MP4 does not exist."
        )

    log("")
    log(
        f"FINAL MP4: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log(
            f"ERROR: {exc}"
        )
        log("=" * 70)
        raise
