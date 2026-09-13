# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: LOCAL-IMAGE-FIRST V3
# ============================================================

import os
import re
import json
import math
import shutil
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageOps, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# VERSION / PATHS
# ============================================================

GENERATOR_VERSION = "RIFT_VALLEY_WATCH_GENERATOR_LOCAL_IMAGE_FIRST_V3"

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = ROOT / "audio"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

WIDTH = 1080
HEIGHT = 1920

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"
AUDIO_FILE = AUDIO_DIR / "narration.mp3"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
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
        raise RuntimeError(f"Required JSON file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Could not read JSON file {path}: {exc}")


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    text = str(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def first_nonempty(*values):
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def normalize_source_name(value):
    source = clean_text(value)

    if not source:
        return "Rift Valley Watch"

    source = re.sub(r"^https?://", "", source, flags=re.I)
    source = source.split("/")[0]
    source = source.replace("www.", "")

    known = {
        "peopledaily.digital": "People Daily",
        "topnews.ke": "Top News",
        "citizen.digital": "Citizen Digital",
        "nation.africa": "Nation",
        "standardmedia.co.ke": "The Standard",
        "the-star.co.ke": "The Star",
        "capitalfm.co.ke": "Capital FM",
        "kbc.co.ke": "KBC",
        "kenyanews.go.ke": "KNA",
        "bomet.go.ke": "Bomet County Government",
        "kericho.go.ke": "Kericho County Government",
        "nakuru.go.ke": "Nakuru County Government",
        "nandi.go.ke": "Nandi County Government",
        "uasingishu.go.ke": "Uasin Gishu County Government",
        "elgeyomarakwet.go.ke": "Elgeyo-Marakwet County Government",
        "westpokot.go.ke": "West Pokot County Government",
        "narok.go.ke": "Narok County Government",
    }

    return known.get(source, source)


# ============================================================
# STORY / SCRIPT TEXT
# ============================================================

def get_story_title(story):
    return first_nonempty(
        story.get("title"),
        story.get("headline"),
        story.get("story_title"),
    )


def get_story_summary(story):
    return first_nonempty(
        story.get("summary"),
        story.get("description"),
        story.get("excerpt"),
        story.get("body"),
        story.get("content"),
    )


def get_county(story):
    return first_nonempty(
        story.get("county"),
        story.get("location"),
        "Rift Valley",
    )


def get_source(story):
    return normalize_source_name(
        first_nonempty(
            story.get("source_name"),
            story.get("publisher"),
            story.get("source"),
        )
    )


def get_story_url(story):
    return first_nonempty(
        story.get("url"),
        story.get("article_url"),
        story.get("link"),
    )


def get_narration(story, script):
    candidates = [
        script.get("narration"),
        script.get("voiceover"),
        script.get("text"),
        story.get("narration"),
        story.get("voiceover"),
    ]

    for candidate in candidates:
        text = clean_text(candidate)
        if text:
            return text

    title = get_story_title(story)
    summary = get_story_summary(story)
    county = get_county(story)

    if title and summary:
        return (
            f"Rift Valley Watch. {title}. "
            f"In {county}, {summary}"
        )

    if title:
        return f"Rift Valley Watch. {title}."

    raise RuntimeError("No usable narration was provided.")


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
        with Image.open(path) as img:
            img.verify()

        with Image.open(path) as img:
            width, height = img.size

            if width < 250 or height < 180:
                return False

        return True

    except Exception:
        return False


# ============================================================
# IMAGE URL CLEANING
# ============================================================

def clean_image_url(value):
    value = clean_text(value)

    if not value:
        return ""

    if value.startswith("//"):
        return "https:" + value

    if not value.lower().startswith(("http://", "https://")):
        return ""

    return value


# ============================================================
# REMOTE IMAGE DOWNLOAD
# ============================================================

def download_image(image_url):
    """
    Remote fallback only.

    IMPORTANT:
    This function is NOT called directly by generate_video().
    generate_video() always calls resolve_image() first.
    """

    image_url = clean_image_url(image_url)

    if not image_url:
        raise RuntimeError("Remote image URL is empty.")

    log(f"Downloading fallback article image: {image_url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

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

    temporary_file = SOURCE_DIR / "downloaded_source_image"

    try:
        with temporary_file.open("wb") as f:
            f.write(response.content)

        if not validate_image_file(temporary_file):
            raise RuntimeError(
                "Downloaded image failed validation."
            )

        final_file = SOURCE_DIR / "story_image.jpg"

        with Image.open(temporary_file) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.save(
                final_file,
                "JPEG",
                quality=95,
                optimize=True,
            )

        temporary_file.unlink(missing_ok=True)

        if not validate_image_file(final_file):
            raise RuntimeError(
                "Converted article image failed validation."
            )

        log(f"REMOTE IMAGE SAVED: {final_file}")
        return final_file

    except Exception:
        temporary_file.unlink(missing_ok=True)
        raise


# ============================================================
# LOCAL IMAGE RESOLUTION
# ============================================================

def resolve_image(story, script):
    """
    LOCAL IMAGE FIRST.

    The news engine already recovers the real article image and
    stores it at:

        assets/source/story_image.jpg

    That file is always checked before any remote image download.
    """

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
        ROOT / "assets" / "source" / "story_image.jpg",
    ]

    checked = set()

    for candidate in local_candidates:

        if candidate is None:
            continue

        candidate = Path(str(candidate))

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

        log(f"Checking local image: {candidate}")

        if validate_image_file(candidate):
            log("")
            log("VERIFIED LOCAL ARTICLE IMAGE FOUND")
            log(f"IMAGE: {candidate}")
            log("")
            return candidate

    # --------------------------------------------------------
    # Remote fallback
    # --------------------------------------------------------

    image_url = first_nonempty(
        story.get("image"),
        story.get("image_url"),
        story.get("imageUrl"),
        script.get("image"),
        script.get("image_url"),
        script.get("imageUrl"),
    )

    image_url = clean_image_url(image_url)

    if image_url:
        log("No valid local image found.")
        log("Using remote image URL fallback.")
        return download_image(image_url)

    raise RuntimeError(
        "No valid local article image exists and no remote "
        "article image URL was supplied."
    )


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_base_image(image_path):
    image_path = Path(image_path)

    if not validate_image_file(image_path):
        raise RuntimeError(
            f"Invalid source image: {image_path}"
        )

    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")

        # Cover the complete vertical canvas.
        source_ratio = img.width / img.height
        target_ratio = WIDTH / HEIGHT

        if source_ratio > target_ratio:
            # Source is wider.
            new_height = HEIGHT
            new_width = int(new_height * source_ratio)
        else:
            # Source is taller.
            new_width = WIDTH
            new_height = int(new_width / source_ratio)

        img = img.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS,
        )

        left = max(0, (img.width - WIDTH) // 2)
        top = max(0, (img.height - HEIGHT) // 2)

        img = img.crop(
            (
                left,
                top,
                left + WIDTH,
                top + HEIGHT,
            )
        )

        return img.copy()


# ============================================================
# FONT
# ============================================================

def find_font(bold=False):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ])

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


FONT_BOLD = find_font(True)
FONT_REGULAR = find_font(False)


def get_font(size, bold=False):
    font_path = FONT_BOLD if bold else FONT_REGULAR

    if font_path:
        return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    text,
    x,
    y,
    font,
    max_width,
    line_gap=12,
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
            fill=(255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=font,
        )

        current_y += (
            bbox[3] - bbox[1] + line_gap
        )

    return current_y


# ============================================================
# SCENE CREATION
# ============================================================

def create_scene_image(
    base_image,
    title,
    county,
    source,
    scene_index,
    scene_count,
    output_path,
):
    img = base_image.copy()
    draw = ImageDraw.Draw(img)

    # --------------------------------------------------------
    # Dark top area
    # --------------------------------------------------------

    top_height = 310

    draw.rectangle(
        (0, 0, WIDTH, top_height),
        fill=(0, 0, 0),
    )

    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    brand_font = get_font(
        42,
        bold=True,
    )

    draw.text(
        (55, 48),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(255, 255, 255),
    )

    # --------------------------------------------------------
    # County
    # --------------------------------------------------------

    county_font = get_font(
        30,
        bold=True,
    )

    draw.text(
        (55, 115),
        county.upper(),
        font=county_font,
        fill=(225, 225, 225),
    )

    # --------------------------------------------------------
    # Story title
    # --------------------------------------------------------

    title_font = get_font(
        45,
        bold=True,
    )

    title_text = title

    draw_wrapped_text(
        draw,
        title_text,
        55,
        165,
        title_font,
        WIDTH - 110,
        line_gap=7,
    )

    # --------------------------------------------------------
    # Bottom source panel
    # --------------------------------------------------------

    bottom_height = 245

    draw.rectangle(
        (
            0,
            HEIGHT - bottom_height,
            WIDTH,
            HEIGHT,
        ),
        fill=(0, 0, 0),
    )

    source_font = get_font(
        31,
        bold=True,
    )

    source_text = f"SOURCE: {source}"

    draw.text(
        (55, HEIGHT - 205),
        source_text,
        font=source_font,
        fill=(255, 255, 255),
    )

    update_font = get_font(
        26,
        bold=False,
    )

    draw.text(
        (55, HEIGHT - 145),
        "Verified report • Rift Valley, Kenya",
        font=update_font,
        fill=(220, 220, 220),
    )

    # --------------------------------------------------------
    # Scene indicator
    # --------------------------------------------------------

    scene_font = get_font(
        24,
        bold=True,
    )

    scene_text = f"{scene_index}/{scene_count}"

    bbox = draw.textbbox(
        (0, 0),
        scene_text,
        font=scene_font,
    )

    draw.text(
        (
            WIDTH - 55 - (bbox[2] - bbox[0]),
            HEIGHT - 70,
        ),
        scene_text,
        font=scene_font,
        fill=(200, 200, 200),
    )

    img.save(
        output_path,
        "JPEG",
        quality=94,
        optimize=True,
    )


# ============================================================
# AUDIO
# ============================================================

def generate_audio(narration):
    narration = clean_text(narration)

    if not narration:
        raise RuntimeError(
            "No narration was provided."
        )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if AUDIO_FILE.exists():
        AUDIO_FILE.unlink()

    log("")
    log("Generating narration...")

    try:
        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(str(AUDIO_FILE))

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

    log(f"AUDIO: {AUDIO_FILE}")

    return AUDIO_FILE


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Could not determine duration of {path}: "
            f"{result.stderr}"
        )

    try:
        return float(result.stdout.strip())
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
    output_path = Path(output_path)

    if output_path.exists():
        output_path.unlink()

    if not scene_files:
        raise RuntimeError(
            "No scene images were created."
        )

    scene_duration = duration / len(scene_files)

    log("")
    log("Creating broadcast video scenes...")
    log(f"Scenes: {len(scene_files)}")
    log(f"Duration: {duration:.2f}s")
    log(f"Scene duration: {scene_duration:.2f}s")

    concat_file = WORK_DIR / "scenes.txt"

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        for scene in scene_files:
            f.write(
                f"file '{Path(scene).resolve()}'\n"
            )
            f.write(
                f"duration {scene_duration:.6f}\n"
            )

        # FFmpeg concat requires the final file
        # to be repeated to apply the final duration.
        f.write(
            f"file '{Path(scene_files[-1]).resolve()}'\n"
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
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
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
# COMBINE VIDEO + AUDIO
# ============================================================

def combine_video_audio(
    video_path,
    audio_path,
    output_path,
):
    output_path = Path(output_path)

    if output_path.exists():
        output_path.unlink()

    log("")
    log("Combining video and narration...")

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
# VIDEO QC
# ============================================================

def verify_video(path):
    path = Path(path)

    log("")
    log("=" * 60)
    log("FINAL VIDEO QC")
    log("=" * 60)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 does not exist: {path}"
        )

    size = path.stat().st_size

    log(f"FILE: {path}")
    log(f"SIZE: {size:,} bytes")

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size:"
            "stream=codec_name,width,height,"
            "r_frame_rate"
        ),
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Final MP4 failed FFprobe validation: "
            f"{result.stderr}"
        )

    log(result.stdout)

    duration = get_media_duration(path)

    if duration < 5:
        raise RuntimeError(
            "Final video is too short."
        )

    log(f"VERIFIED DURATION: {duration:.2f}s")
    log("FINAL MP4 QC PASSED")

    return True


# ============================================================
# CLEAN WORK FILES
# ============================================================

def clean_work_files():
    if WORK_DIR.exists():
        for item in WORK_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass


# ============================================================
# GENERATE VIDEO
# ============================================================

def generate_video(story, script=None):

    if script is None:
        script = {}

    prepare_directories()
    clean_work_files()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATOR")
    log("=" * 70)
    log(f"GENERATOR VERSION: {GENERATOR_VERSION}")
    log(f"RUNNING FILE: {Path(__file__).resolve()}")
    log("=" * 70)

    title = get_story_title(story)
    county = get_county(story)
    source = get_source(story)
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
    log("SELECTED STORY")
    log(f"TITLE : {title}")
    log(f"COUNTY: {county}")
    log(f"SOURCE: {source}")

    # --------------------------------------------------------
    # CRITICAL IMAGE STEP
    # --------------------------------------------------------

    log("")
    log("Downloading source image...")

    # NEVER replace this with:
    #
    # image_path = download_image(...)
    #
    # The correct path is always resolve_image().
    image_path = resolve_image(
        story,
        script,
    )

    if not validate_image_file(image_path):
        raise RuntimeError(
            f"Resolved image is invalid: {image_path}"
        )

    log("")
    log("ARTICLE IMAGE VERIFIED")
    log(f"IMAGE PATH: {image_path}")

    # --------------------------------------------------------
    # Prepare image
    # --------------------------------------------------------

    base_image = prepare_base_image(
        image_path
    )

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    audio_duration = get_media_duration(
        audio_path
    )

    # Keep the reel natural while allowing
    # the narration to determine final length.
    target_duration = max(
        15.0,
        min(audio_duration, 60.0),
    )

    # --------------------------------------------------------
    # Scenes
    # --------------------------------------------------------

    # One real story, multiple visual treatments.
    # This is NOT multiple stories.
    scene_count = 5

    scene_dir = WORK_DIR / "scenes"
    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    scene_files = []

    for index in range(scene_count):

        scene_path = (
            scene_dir /
            f"scene_{index + 1:02d}.jpg"
        )

        # Slight zoom/pan treatment.
        # The underlying image remains the real article image.
        zoom_factor = 1.0 + (
            0.025 * index
        )

        scene_image = base_image.copy()

        if zoom_factor > 1.0:
            new_width = int(
                WIDTH * zoom_factor
            )
            new_height = int(
                HEIGHT * zoom_factor
            )

            scene_image = scene_image.resize(
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
            source,
            index + 1,
            scene_count,
            scene_path,
        )

        scene_files.append(scene_path)

    # --------------------------------------------------------
    # Silent video
    # --------------------------------------------------------

    silent_video = WORK_DIR / "silent.mp4"

    create_silent_video(
        scene_files,
        target_duration,
        silent_video,
    )

    # --------------------------------------------------------
    # Final MP4
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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
    log("RIFT VALLEY WATCH VIDEO GENERATED SUCCESSFULLY")
    log("=" * 70)
    log(f"OUTPUT: {OUTPUT_FILE}")
    log(f"SIZE  : {OUTPUT_FILE.stat().st_size:,} bytes")
    log("=" * 70)

    return OUTPUT_FILE


# ============================================================
# MAIN
# ============================================================

def main():

    prepare_directories()

    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH")
    log("=" * 70)
    log(f"GENERATOR VERSION: {GENERATOR_VERSION}")
    log(f"FILE: {Path(__file__).resolve()}")
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
        log(
            "selected_script.json not found. "
            "Using story narration."
        )
        script = {}

    output = generate_video(
        story,
        script,
    )

    if not output.exists():
        raise RuntimeError(
            "Generator finished but final MP4 does not exist."
        )

    log("")
    log("SUCCESS")
    log(f"FINAL MP4: {output}")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)
        log(f"ERROR: {exc}")
        log("=" * 70)
        raise
