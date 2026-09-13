from pathlib import Path
import json
import re
import subprocess
import sys
import shutil

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V14_AUDIO_STABLE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
ASSET_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = ASSET_DIR / "story_image.jpg"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

TEMP_VIDEO = WORK_DIR / "motion_background.mp4"
OVERLAY_FILE = WORK_DIR / "overlay.png"
PREPARED_IMAGE = WORK_DIR / "prepared_image.jpg"

AUDIO_FILE = AUDIO_DIR / "narration.mp3"
TEMP_AUDIO = AUDIO_DIR / "narration_temp.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_DURATION = 15
MAX_DURATION = 60


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[RIFT VALLEY WATCH] {message}",
        flush=True
    )


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    for directory in [
        OUTPUT_DIR,
        DATA_DIR,
        ASSET_DIR,
        WORK_DIR,
        AUDIO_DIR,
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True
        )

    log(f"BASE DIR: {BASE_DIR}")
    log(f"AUDIO DIR: {AUDIO_DIR}")
    log(f"AUDIO FILE: {AUDIO_FILE}")


# ============================================================
# PUBLISHER NAMES
# ============================================================

SOURCE_NAMES = [
    "KBC Digital",
    "KBC News",
    "Citizen Digital",
    "Citizen",
    "Daily Nation",
    "Nation Africa",
    "The Star",
    "People Daily",
    "The Standard",
    "Standard Media",
    "Capital News",
    "NTV Kenya",
    "NTV",
    "TV47",
    "Tuko",
]


# ============================================================
# TEXT CLEANING
# ============================================================

def remove_source_language(text):
    if not text:
        return ""

    text = str(text)

    text = re.sub(
        r"https?://\S+|www\.\S+",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bAdvertisement\b",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bAdvert\b",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\[[^\]]*\]",
        "",
        text
    )

    for source in SOURCE_NAMES:
        text = re.sub(
            rf"\b{re.escape(source)}\b",
            "",
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(
        r"\bas reported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\breported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text
    )

    return text.strip()


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    if not title:
        return "Latest Rift Valley Update"

    title = str(title)

    title = re.sub(
        r"\s*[\|\-–—:]\s*(KBC Digital|KBC News|KBC|"
        r"Citizen Digital|Citizen|Daily Nation|Nation Africa|"
        r"The Star|People Daily|The Standard|Standard Media|"
        r"Capital News|NTV Kenya|NTV|TV47|Tuko).*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    title = re.sub(
        r"\[[^\]]*\]",
        "",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception as exc:
        log(
            f"WARNING: Could not read {path}: {exc}"
        )

        return {}


def load_story():
    story = load_json(STORY_FILE)

    if not story:
        raise RuntimeError(
            f"Selected story file not found or empty: {STORY_FILE}"
        )

    return story


def load_script():
    return load_json(SCRIPT_FILE)


# ============================================================
# SENTENCE PROCESSING
# ============================================================

def normalize_sentences(text):
    if not text:
        return []

    text = remove_source_language(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    cleaned = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        if len(sentence.split()) < 4:
            continue

        cleaned.append(sentence)

    return cleaned


def sentence_similarity(a, b):
    a_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            a.lower()
        )
    )

    b_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            b.lower()
        )
    )

    if not a_words or not b_words:
        return 0

    return len(
        a_words & b_words
    ) / max(
        1,
        min(
            len(a_words),
            len(b_words)
        )
    )


def deduplicate_sentences(sentences):
    result = []

    for sentence in sentences:
        duplicate = False

        for previous in result:
            if sentence_similarity(
                sentence,
                previous
            ) >= 0.82:
                duplicate = True
                break

        if not duplicate:
            result.append(sentence)

    return result


# ============================================================
# NARRATION
# ============================================================

def get_narration(story, script):
    narration = ""

    if isinstance(script, dict):
        narration = (
            script.get("narration", "")
            or ""
        )

    if not narration and isinstance(story, dict):
        narration = (
            story.get("script", "")
            or ""
        )

    if not narration and isinstance(story, dict):
        body = story.get(
            "body",
            ""
        ) or ""

        sentences = normalize_sentences(
            body
        )

        sentences = deduplicate_sentences(
            sentences
        )

        narration = " ".join(
            sentences[:10]
        )

    narration = remove_source_language(
        narration
    )

    narration = re.sub(
        r"^\s*Here is the latest development from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE
    )

    narration = re.sub(
        r"^\s*Here is the latest update from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE
    )

    narration = re.sub(
        r"^\s*Latest development from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE
    )

    narration = re.sub(
        r"\s+",
        " ",
        narration
    ).strip()

    if not narration:
        body = story.get(
            "body",
            ""
        ) or ""

        sentences = normalize_sentences(
            body
        )

        sentences = deduplicate_sentences(
            sentences
        )

        if sentences:
            narration = " ".join(
                sentences[:10]
            )
        else:
            county = story.get(
                "county",
                "the Rift Valley"
            )

            narration = (
                f"New developments are being "
                f"reported in {county}."
            )

    return narration.strip()


# ============================================================
# AUDIO UTILITIES
# ============================================================

def remove_old_audio():
    for path in [
        AUDIO_FILE,
        TEMP_AUDIO,
    ]:
        try:
            if path.exists():
                path.unlink()
                log(
                    f"REMOVED OLD AUDIO: {path}"
                )
        except Exception as exc:
            raise RuntimeError(
                f"Could not remove old audio {path}: {exc}"
            )


def check_command(command_name):
    path = shutil.which(command_name)

    if not path:
        raise RuntimeError(
            f"Required command not found: {command_name}"
        )

    log(
        f"{command_name.upper()}: {path}"
    )

    return path


def validate_audio_file(path):
    if not path.exists():
        raise RuntimeError(
            f"Narration MP3 does not exist: {path}"
        )

    size = path.stat().st_size

    log(
        f"NARRATION SIZE: {size:,} bytes"
    )

    if size < 1000:
        raise RuntimeError(
            f"Narration MP3 is too small: {size} bytes"
        )

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
        str(path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not read narration MP3.\n"
            + result.stderr
        )

    codec = result.stdout.strip()

    if not codec:
        raise RuntimeError(
            "Narration MP3 contains no audio stream."
        )

    log(
        f"NARRATION CODEC: {codec}"
    )

    return True


# ============================================================
# GENERATE AUDIO
# ============================================================

def generate_audio(narration):
    log("")
    log("=" * 70)
    log("GENERATING NARRATION AUDIO")
    log("=" * 70)

    if not narration.strip():
        raise RuntimeError(
            "Narration text is empty."
        )

    log(
        f"NARRATION CHARACTERS: {len(narration)}"
    )

    log(
        f"NARRATION WORDS: {len(narration.split())}"
    )

    log(
        "TTS ENGINE: gTTS"
    )

    remove_old_audio()

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        from gtts import gTTS
    except Exception as exc:
        raise RuntimeError(
            "gTTS could not be imported. "
            "Install it with: pip install gTTS\n"
            f"Import error: {exc}"
        )

    try:
        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
            lang_check=True
        )

        log(
            "gTTS OBJECT CREATED"
        )

        tts.save(
            str(TEMP_AUDIO)
        )

        log(
            f"gTTS SAVE COMPLETED: {TEMP_AUDIO}"
        )

    except Exception as exc:
        log("")
        log("=" * 70)
        log("G TTS FAILED")
        log("=" * 70)
        log(
            f"ERROR TYPE: {type(exc).__name__}"
        )
        log(
            f"ERROR MESSAGE: {exc}"
        )
        log("=" * 70)

        raise RuntimeError(
            "gTTS failed to generate narration audio. "
            "Check GitHub Actions internet access and "
            "confirm that the gTTS package is installed."
        )

    if not TEMP_AUDIO.exists():
        raise RuntimeError(
            "gTTS completed without creating narration_temp.mp3."
        )

    if TEMP_AUDIO.stat().st_size < 1000:
        raise RuntimeError(
            "gTTS created an invalid or empty MP3."
        )

    # Validate temporary MP3 before moving it.
    validate_audio_file(
        TEMP_AUDIO
    )

    try:
        TEMP_AUDIO.replace(
            AUDIO_FILE
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not move generated audio into "
            f"{AUDIO_FILE}: {exc}"
        )

    validate_audio_file(
        AUDIO_FILE
    )

    log(
        f"NARRATION CREATED SUCCESSFULLY: {AUDIO_FILE}"
    )

    log("=" * 70)

    return AUDIO_FILE


# ============================================================
# MEDIA DURATION
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
        str(path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed: {result.stderr}"
        )

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        raise RuntimeError(
            f"Could not determine duration: {path}"
        )


def calculate_duration(audio_path):
    duration = get_media_duration(
        audio_path
    )

    duration = max(
        MIN_DURATION,
        duration
    )

    duration = min(
        MAX_DURATION,
        duration
    )

    return duration


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):
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

    for font_path in candidates:
        path = Path(font_path)

        if path.exists():
            return ImageFont.truetype(
                str(path),
                size
            )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
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
            font=font
        )

        text_width = (
            bbox[2] - bbox[0]
        )

        if text_width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def fit_headline(draw, title):
    max_width = WIDTH - 120

    for size in range(
        54,
        30,
        -2
    ):
        font = get_font(
            size,
            bold=True
        )

        lines = wrap_text(
            draw,
            title,
            font,
            max_width
        )

        if len(lines) <= 4:
            return font, lines

    font = get_font(
        30,
        bold=True
    )

    lines = wrap_text(
        draw,
        title,
        font,
        max_width
    )

    return font, lines[:4]


# ============================================================
# OVERLAY
# ============================================================

def create_overlay(county, title):
    log(
        "CREATING STATIC NEWS OVERLAY"
    )

    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    draw = ImageDraw.Draw(
        image
    )

    # --------------------------------------------------------
    # TOP PANEL
    # --------------------------------------------------------

    top_height = 405

    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            top_height
        ],
        fill=(
            0,
            0,
            0,
            215
        )
    )

    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            8
        ],
        fill=(
            255,
            255,
            255,
            255
        )
    )

    brand_font = get_font(
        34,
        bold=True
    )

    draw.text(
        (
            55,
            42
        ),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(
            255,
            255,
            255,
            255
        )
    )

    county_font = get_font(
        28,
        bold=True
    )

    draw.text(
        (
            55,
            98
        ),
        str(county).upper(),
        font=county_font,
        fill=(
            235,
            235,
            235,
            255
        )
    )

    draw.rectangle(
        [
            55,
            145,
            WIDTH - 55,
            148
        ],
        fill=(
            255,
            255,
            255,
            110
        )
    )

    title = clean_title(
        title
    )

    if len(title) > 180:
        title = (
            title[:177].rstrip()
            + "..."
        )

    headline_font, lines = fit_headline(
        draw,
        title
    )

    y = 175

    for line in lines:
        draw.text(
            (
                55,
                y
            ),
            line,
            font=headline_font,
            fill=(
                255,
                255,
                255,
                255
            )
        )

        bbox = draw.textbbox(
            (
                55,
                y
            ),
            line,
            font=headline_font
        )

        line_height = (
            bbox[3] - bbox[1]
        )

        y += line_height + 8

    # --------------------------------------------------------
    # BOTTOM PANEL
    # --------------------------------------------------------

    bottom_height = 210

    bottom_y = (
        HEIGHT - bottom_height
    )

    draw.rectangle(
        [
            0,
            bottom_y,
            WIDTH,
            HEIGHT
        ],
        fill=(
            0,
            0,
            0,
            205
        )
    )

    footer_font = get_font(
        27,
        bold=True
    )

    draw.text(
        (
            55,
            bottom_y + 70
        ),
        "RIFT VALLEY • KENYA",
        font=footer_font,
        fill=(
            255,
            255,
            255,
            245
        )
    )

    draw.rectangle(
        [
            55,
            bottom_y + 125,
            340,
            bottom_y + 129
        ],
        fill=(
            255,
            255,
            255,
            150
        )
    )

    image.save(
        OVERLAY_FILE,
        "PNG"
    )

    if not OVERLAY_FILE.exists():
        raise RuntimeError(
            "Overlay was not created."
        )

    return OVERLAY_FILE


# ============================================================
# PREPARE IMAGE
# ============================================================

def prepare_source_image(source_path):
    if not source_path.exists():
        raise RuntimeError(
            f"Story image not found: {source_path}"
        )

    try:
        image = Image.open(
            source_path
        ).convert("RGB")
    except Exception as exc:
        raise RuntimeError(
            f"Could not open story image: {exc}"
        )

    if (
        image.width < 200
        or image.height < 200
    ):
        raise RuntimeError(
            "Story image is too small."
        )

    log(
        f"STORY IMAGE: "
        f"{image.width}x{image.height}"
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
            new_height
        ),
        Image.Resampling.LANCZOS
    )

    left = max(
        0,
        (
            new_width - WIDTH
        ) // 2
    )

    top = max(
        0,
        (
            new_height - HEIGHT
        ) // 2
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    image.save(
        PREPARED_IMAGE,
        "JPEG",
        quality=95
    )

    return PREPARED_IMAGE


# ============================================================
# CONTINUOUS MOTION VIDEO
# ============================================================

def create_motion_video(
    image_path,
    overlay_path,
    duration
):
    log(
        "CREATING CONTINUOUS NEWS VISUAL"
    )

    log(
        "IMAGE COUNT: 1"
    )

    log(
        "SLIDE COUNTER: REMOVED"
    )

    log(
        "CONTINUOUS MOTION: ENABLED"
    )

    zoom_expression = (
        "min(1+on*0.00012,1.11)"
    )

    x_expression = (
        "iw/2-(iw/zoom/2)"
    )

    y_expression = (
        "ih/2-(ih/zoom/2)"
    )

    filter_complex = (
        "[0:v]"
        "scale="
        f"{WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        "zoompan="
        f"z='{zoom_expression}':"
        f"x='{x_expression}':"
        f"y='{y_expression}':"
        "d=1:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps={FPS}"
        "[bg];"
        "[bg][1:v]"
        "overlay=0:0:format=auto"
        "[v]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",
        "-i",
        str(image_path),

        "-loop",
        "1",
        "-i",
        str(overlay_path),

        "-filter_complex",
        filter_complex,

        "-map",
        "[v]",

        "-t",
        str(duration),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(TEMP_VIDEO)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(
            result.stdout,
            flush=True
        )

        print(
            result.stderr,
            flush=True
        )

        raise RuntimeError(
            "FFmpeg failed while creating "
            "continuous motion video."
        )

    if not TEMP_VIDEO.exists():
        raise RuntimeError(
            "Motion video was not created."
        )

    if TEMP_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Motion video is unexpectedly small."
        )

    log(
        f"MOTION VIDEO CREATED: "
        f"{TEMP_VIDEO.stat().st_size:,} bytes"
    )

    return TEMP_VIDEO


# ============================================================
# COMBINE AUDIO
# ============================================================

def combine_audio(
    video_path,
    audio_path
):
    log(
        "ADDING NARRATION AUDIO"
    )

    if not audio_path.exists():
        raise RuntimeError(
            f"Audio file missing before muxing: {audio_path}"
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

        "-ar",
        "44100",

        "-ac",
        "2",

        "-shortest",

        "-movflags",
        "+faststart",

        str(OUTPUT_FILE)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(
            result.stdout,
            flush=True
        )

        print(
            result.stderr,
            flush=True
        )

        raise RuntimeError(
            "FFmpeg failed while adding audio."
        )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    if OUTPUT_FILE.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is unexpectedly small."
        )

    return OUTPUT_FILE


# ============================================================
# FINAL QC
# ============================================================

def verify_final_video(path):
    log("")
    log("=" * 70)
    log("FINAL MP4 QUALITY CONTROL")
    log("=" * 70)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    duration = get_media_duration(
        path
    )

    probe_command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,codec_name",
        "-of",
        "default=noprint_wrappers=1",
        str(path)
    ]

    result = subprocess.run(
        probe_command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not inspect final MP4."
        )

    probe = result.stdout.lower()

    if "width=1080" not in probe:
        raise RuntimeError(
            "Final MP4 width is not 1080."
        )

    if "height=1920" not in probe:
        raise RuntimeError(
            "Final MP4 height is not 1920."
        )

    audio_command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    audio_result = subprocess.run(
        audio_command,
        capture_output=True,
        text=True
    )

    if (
        audio_result.returncode != 0
        or not audio_result.stdout.strip()
    ):
        raise RuntimeError(
            "Final MP4 does not contain audio."
        )

    log(
        f"FINAL FILE: {path}"
    )

    log(
        f"SIZE: {size:,} bytes"
    )

    log(
        f"DURATION: {duration:.2f} seconds"
    )

    log(
        "VIDEO: 1080x1920"
    )

    log(
        f"AUDIO CODEC: {audio_result.stdout.strip()}"
    )

    log(
        "IMAGE COUNT: 1"
    )

    log(
        "MOTION: CONTINUOUS"
    )

    log(
        "SLIDE COUNTER: REMOVED"
    )

    log(
        "SOURCE/PUBLISHER ON SCREEN: NONE"
    )

    log("=" * 70)
    log("FINAL MP4 QC PASSED")
    log("=" * 70)


# ============================================================
# CLEAN WORK FILES
# ============================================================

def cleanup_work_files():
    for path in [
        TEMP_VIDEO,
        OVERLAY_FILE,
        PREPARED_IMAGE,
        TEMP_AUDIO,
    ]:
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            log(
                f"WARNING: Could not remove {path}: {exc}"
            )


# ============================================================
# MAIN
# ============================================================

def main():
    log("")
    log("=" * 70)
    log("STARTING RIFT VALLEY WATCH VIDEO GENERATOR")
    log("VERSION: RVW_VIDEO_V14_AUDIO_STABLE")
    log("=" * 70)

    ensure_directories()

    check_command("ffmpeg")
    check_command("ffprobe")

    story = load_story()
    script = load_script()

    county = story.get(
        "county",
        "Rift Valley"
    )

    title = clean_title(
        story.get(
            "title",
            "Latest Rift Valley Update"
        )
    )

    log(
        f"COUNTY: {county}"
    )

    log(
        f"HEADLINE: {title}"
    )

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = get_narration(
        story,
        script
    )

    log("")
    log("NARRATION PREVIEW:")
    log(
        narration[:700]
    )

    if len(narration.split()) < 8:
        raise RuntimeError(
            "Narration is too short."
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    log(
        f"NARRATION FILE: {audio_path}"
    )

    duration = calculate_duration(
        audio_path
    )

    log(
        f"TARGET DURATION: "
        f"{duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_path = prepare_source_image(
        IMAGE_FILE
    )

    log(
        f"ONE ARTICLE IMAGE: {image_path}"
    )

    # --------------------------------------------------------
    # OVERLAY
    # --------------------------------------------------------

    overlay_path = create_overlay(
        county,
        title
    )

    # --------------------------------------------------------
    # CONTINUOUS VIDEO
    # --------------------------------------------------------

    motion_video = create_motion_video(
        image_path,
        overlay_path,
        duration
    )

    # --------------------------------------------------------
    # AUDIO + VIDEO
    # --------------------------------------------------------

    final_video = combine_audio(
        motion_video,
        audio_path
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    verify_final_video(
        final_video
    )

    cleanup_work_files()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATION COMPLETE")
    log("=" * 70)

    log(
        f"FINAL MP4: {final_video}"
    )

    log(
        f"NARRATION MP3: {audio_path}"
    )

    log("=" * 70)


if __name__ == "__main__":
    try:
        main()

    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH VIDEO GENERATION FAILED")
        log("=" * 70)
        log(
            f"ERROR TYPE: {type(exc).__name__}"
        )
        log(
            f"ERROR: {exc}"
        )
        log("=" * 70)

        sys.exit(1)
