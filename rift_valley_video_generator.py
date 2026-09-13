from pathlib import Path
import json
import re
import subprocess
import sys
import math

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V12_CONTINUOUS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
ASSET_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = ASSET_DIR / "story_image.jpg"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
TEMP_VIDEO = WORK_DIR / "motion_background.mp4"
OVERLAY_FILE = WORK_DIR / "overlay.png"
AUDIO_FILE = WORK_DIR / "narration.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_DURATION = 15
MAX_DURATION = 60


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


# ============================================================
# DIRECTORY SETUP
# ============================================================

def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEXT CLEANING
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


def remove_source_language(text):
    if not text:
        return ""

    text = str(text)

    # Remove URLs
    text = re.sub(
        r"https?://\S+|www\.\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove advertisement markers
    text = re.sub(
        r"\bAdvertisement\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bAdvert\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove bracketed junk
    text = re.sub(
        r"\[[^\]]*\]",
        "",
        text,
    )

    # Remove common publisher attribution
    for source in SOURCE_NAMES:
        pattern = rf"\b{re.escape(source)}\b"
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    # Remove common attribution phrases
    text = re.sub(
        r"\bas reported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\breported by\b.*?(?=[.!?]|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\baccording to\s+[^.!?]+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove repeated whitespace
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Clean punctuation spacing
    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text,
    )

    return text.strip()


# ============================================================
# TITLE CLEANING
# ============================================================

def clean_title(title):
    if not title:
        return "Latest Rift Valley Update"

    title = remove_source_language(title)

    title = re.sub(
        r"\s*[\|\-–—:]\s*$",
        "",
        title,
    )

    title = re.sub(
        r"\s*[\|\-–—:]\s*(KBC|Citizen|Nation|The Star|People Daily|"
        r"The Standard|Standard Media|Capital News|NTV|TV47|Tuko).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


# ============================================================
# LOAD STORY
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log(f"WARNING: Could not read {path}: {exc}")
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
# NARRATION
# ============================================================

def normalize_sentences(text):
    if not text:
        return []

    text = remove_source_language(text)

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    cleaned = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        words = sentence.split()

        if len(words) < 4:
            continue

        cleaned.append(sentence)

    return cleaned


def sentence_similarity(a, b):
    a_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            a.lower(),
        )
    )

    b_words = set(
        re.findall(
            r"[a-zA-Z0-9']+",
            b.lower(),
        )
    )

    if not a_words or not b_words:
        return 0

    intersection = len(a_words & b_words)

    return intersection / max(
        1,
        min(len(a_words), len(b_words)),
    )


def deduplicate_sentences(sentences):
    result = []

    for sentence in sentences:
        duplicate = False

        for previous in result:
            if sentence_similarity(sentence, previous) >= 0.82:
                duplicate = True
                break

        if not duplicate:
            result.append(sentence)

    return result


def get_narration(story, script):
    narration = ""

    # Preferred location
    if isinstance(script, dict):
        narration = script.get("narration", "") or ""

    # Secondary location
    if not narration and isinstance(story, dict):
        narration = story.get("script", "") or ""

    # Body fallback
    if not narration and isinstance(story, dict):
        body = story.get("body", "") or ""

        sentences = normalize_sentences(body)
        sentences = deduplicate_sentences(sentences)

        narration = " ".join(sentences[:10])

    narration = remove_source_language(narration)

    # Remove common artificial intros
    narration = re.sub(
        r"^\s*Here is the latest development from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE,
    )

    narration = re.sub(
        r"^\s*Here is the latest update from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE,
    )

    narration = re.sub(
        r"^\s*Latest development from [^.]+\.?\s*",
        "",
        narration,
        flags=re.IGNORECASE,
    )

    # Remove publisher-like title fragments
    for source in SOURCE_NAMES:
        narration = re.sub(
            rf"\b{re.escape(source)}\b",
            "",
            narration,
            flags=re.IGNORECASE,
        )

    # Clean whitespace
    narration = re.sub(
        r"\s+",
        " ",
        narration,
    ).strip()

    if not narration:
        county = str(
            story.get(
                "county",
                "the Rift Valley",
            )
        )

        body = story.get("body", "") or ""

        sentences = normalize_sentences(body)
        sentences = deduplicate_sentences(sentences)

        if sentences:
            narration = " ".join(sentences[:10])
        else:
            narration = (
                f"New developments are being reported in {county}."
            )

    return narration


# ============================================================
# AUDIO
# ============================================================

def find_audio():
    candidates = [
        AUDIO_FILE,
        BASE_DIR / "audio" / "narration.mp3",
        DATA_DIR / "narration.mp3",
    ]

    for path in candidates:
        if path.exists() and path.stat().st_size > 1000:
            return path

    return None


def generate_audio(narration):
    audio_path = find_audio()

    # If main script already generated narration.mp3,
    # use it rather than unnecessarily generating another file.
    if audio_path:
        log(f"USING EXISTING NARRATION: {audio_path}")
        return audio_path

    log("GENERATING NARRATION AUDIO")

    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError(
            "gTTS is not installed. Run: pip install gTTS"
        )

    AUDIO_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tts = gTTS(
        text=narration,
        lang="en",
        slow=False,
    )

    tts.save(str(AUDIO_FILE))

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration audio was not generated."
        )

    if AUDIO_FILE.stat().st_size < 1000:
        raise RuntimeError(
            "Narration audio file is unexpectedly small."
        )

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
            f"ffprobe failed for {path}: {result.stderr}"
        )

    try:
        return float(result.stdout.strip())
    except Exception:
        raise RuntimeError(
            f"Could not determine duration for {path}"
        )


def calculate_duration(audio_path):
    duration = get_media_duration(audio_path)

    duration = max(
        MIN_DURATION,
        duration,
    )

    duration = min(
        MAX_DURATION,
        duration,
    )

    return duration


# ============================================================
# FONT
# ============================================================

def get_font(size, bold=False):
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

    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])

    for font_path in candidates:
        path = Path(font_path)

        if path.exists():
            return ImageFont.truetype(
                str(path),
                size,
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


def fit_headline(draw, title):
    max_width = WIDTH - 120

    for size in range(54, 30, -2):
        font = get_font(
            size,
            bold=True,
        )

        lines = wrap_text(
            draw,
            title,
            font,
            max_width,
        )

        if len(lines) <= 4:
            return font, lines

    font = get_font(
        30,
        bold=True,
    )

    lines = wrap_text(
        draw,
        title,
        font,
        max_width,
    )

    return font, lines[:4]


# ============================================================
# CREATE STATIC OVERLAY
# ============================================================

def create_overlay(county, title):
    log("CREATING STATIC NEWS OVERLAY")

    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # TOP NEWS PANEL
    # --------------------------------------------------------

    top_height = 405

    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            top_height,
        ],
        fill=(0, 0, 0, 215),
    )

    # Small accent line
    draw.rectangle(
        [
            0,
            0,
            WIDTH,
            8,
        ],
        fill=(255, 255, 255, 255),
    )

    # Brand
    brand_font = get_font(
        34,
        bold=True,
    )

    draw.text(
        (55, 42),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(255, 255, 255, 255),
    )

    # County
    county_font = get_font(
        28,
        bold=True,
    )

    county_text = str(county).upper()

    draw.text(
        (55, 98),
        county_text,
        font=county_font,
        fill=(235, 235, 235, 255),
    )

    # Divider
    draw.rectangle(
        [
            55,
            145,
            WIDTH - 55,
            148,
        ],
        fill=(255, 255, 255, 110),
    )

    # Headline
    title = clean_title(title)

    # Prevent extreme headline length
    if len(title) > 180:
        title = title[:177].rstrip() + "..."

    headline_font, lines = fit_headline(
        draw,
        title,
    )

    y = 175

    for line in lines:
        draw.text(
            (55, y),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
        )

        bbox = draw.textbbox(
            (55, y),
            line,
            font=headline_font,
        )

        line_height = bbox[3] - bbox[1]

        y += line_height + 8

    # --------------------------------------------------------
    # BOTTOM PANEL
    # --------------------------------------------------------

    bottom_height = 210
    bottom_y = HEIGHT - bottom_height

    draw.rectangle(
        [
            0,
            bottom_y,
            WIDTH,
            HEIGHT,
        ],
        fill=(0, 0, 0, 205),
    )

    footer_font = get_font(
        27,
        bold=True,
    )

    draw.text(
        (55, bottom_y + 70),
        "RIFT VALLEY • KENYA",
        font=footer_font,
        fill=(255, 255, 255, 245),
    )

    # Small live-style divider
    draw.rectangle(
        [
            55,
            bottom_y + 125,
            340,
            bottom_y + 129,
        ],
        fill=(255, 255, 255, 150),
    )

    save_path = OVERLAY_FILE

    image.save(
        save_path,
        "PNG",
    )

    if not save_path.exists():
        raise RuntimeError(
            "Overlay image was not created."
        )

    log(f"OVERLAY: {save_path}")

    return save_path


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_source_image(source_path):
    if not source_path.exists():
        raise RuntimeError(
            f"Story image not found: {source_path}"
        )

    try:
        image = Image.open(source_path).convert("RGB")
    except Exception as exc:
        raise RuntimeError(
            f"Could not open story image: {exc}"
        )

    if image.width < 200 or image.height < 200:
        raise RuntimeError(
            "Story image is too small."
        )

    log(
        f"STORY IMAGE: "
        f"{image.width}x{image.height}"
    )

    # Cover 1080x1920
    source_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT

    if source_ratio > target_ratio:
        # Source too wide
        new_height = HEIGHT
        new_width = int(
            new_height * source_ratio
        )
    else:
        # Source too tall
        new_width = WIDTH
        new_height = int(
            new_width / source_ratio
        )

    image = image.resize(
        (new_width, new_height),
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

    prepared = WORK_DIR / "prepared_image.jpg"

    image.save(
        prepared,
        "JPEG",
        quality=95,
    )

    return prepared


# ============================================================
# CREATE CONTINUOUS MOTION VIDEO
# ============================================================

def create_motion_video(
    image_path,
    overlay_path,
    duration,
):
    log("CREATING CONTINUOUS KEN BURNS VIDEO")
    log("IMAGE COUNT: 1")
    log("SLIDE COUNTER: REMOVED")
    log("CONTINUOUS MOTION: ENABLED")

    # Continuous, very slow zoom.
    #
    # The background image moves continuously.
    # The text overlay remains completely stable.
    #
    # This avoids the old:
    #   Scene 1
    #   Scene 2
    #   Scene 3
    #   Scene 4
    #   Scene 5
    #
    # slideshow appearance.

    zoom_expression = (
        "min("
        "1+on*0.00012,"
        "1.11"
        ")"
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
        "overlay="
        "0:0:"
        "format=auto"
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

        str(TEMP_VIDEO),
    ]

    log("RUNNING FFMPEG MOTION GENERATION")

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)

        raise RuntimeError(
            "FFmpeg failed while creating "
            "continuous motion video."
        )

    if not TEMP_VIDEO.exists():
        raise RuntimeError(
            "Temporary motion video was not created."
        )

    if TEMP_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Temporary motion video is unexpectedly small."
        )

    log(
        f"MOTION VIDEO CREATED: "
        f"{TEMP_VIDEO.stat().st_size:,} bytes"
    )

    return TEMP_VIDEO


# ============================================================
# ADD AUDIO
# ============================================================

def combine_audio(video_path, audio_path):
    log("ADDING NARRATION AUDIO")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
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

        str(OUTPUT_FILE),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout, flush=True)
        print(result.stderr, flush=True)

        raise RuntimeError(
            "FFmpeg failed while adding narration."
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
# FINAL QUALITY CONTROL
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
            f"Final MP4 too small: {size} bytes"
        )

    duration = get_media_duration(path)

    # Probe dimensions
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,codec_name",
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

    # Check audio stream
    command_audio = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    audio_result = subprocess.run(
        command_audio,
        capture_output=True,
        text=True,
    )

    audio_codec = (
        audio_result.stdout.strip()
        if audio_result.returncode == 0
        else ""
    )

    if not audio_codec:
        raise RuntimeError(
            "Final MP4 does not contain an audio stream."
        )

    log(f"FINAL FILE: {path}")
    log(f"SIZE: {size:,} bytes")
    log(f"DURATION: {duration:.2f} seconds")
    log("VIDEO: 1080x1920")
    log("AUDIO: PRESENT")
    log("IMAGE COUNT: 1")
    log("MOTION: CONTINUOUS")
    log("SLIDE COUNTER: REMOVED")
    log("SOURCE/PUBLISHER ON SCREEN: NONE")
    log("=" * 70)
    log("FINAL MP4 QC PASSED")
    log("=" * 70)

    return True


# ============================================================
# CLEAN WORK FILES
# ============================================================

def cleanup_work_files():
    for path in [
        TEMP_VIDEO,
        OVERLAY_FILE,
        WORK_DIR / "prepared_image.jpg",
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
    log("VERSION: RVW_VIDEO_V12_CONTINUOUS")
    log("=" * 70)

    ensure_directories()

    # --------------------------------------------------------
    # LOAD STORY
    # --------------------------------------------------------

    story = load_story()
    script = load_script()

    county = story.get(
        "county",
        "Rift Valley",
    )

    title = clean_title(
        story.get(
            "title",
            "Latest Rift Valley Update",
        )
    )

    log(f"COUNTY: {county}")
    log(f"HEADLINE: {title}")

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = get_narration(
        story,
        script,
    )

    log("")
    log("NARRATION PREVIEW:")
    log(narration[:500])

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration,
    )

    duration = calculate_duration(
        audio_path,
    )

    log(
        f"TARGET VIDEO DURATION: "
        f"{duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_path = prepare_source_image(
        IMAGE_FILE,
    )

    log(
        f"ONE ARTICLE IMAGE: {image_path}"
    )

    # --------------------------------------------------------
    # OVERLAY
    # --------------------------------------------------------

    overlay_path = create_overlay(
        county,
        title,
    )

    # --------------------------------------------------------
    # CONTINUOUS MOTION
    # --------------------------------------------------------

    motion_video = create_motion_video(
        image_path,
        overlay_path,
        duration,
    )

    # --------------------------------------------------------
    # AUDIO + VIDEO
    # --------------------------------------------------------

    final_video = combine_audio(
        motion_video,
        audio_path,
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    verify_final_video(
        final_video,
    )

    # --------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------

    cleanup_work_files()

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATION COMPLETE")
    log("=" * 70)
    log(f"FINAL MP4: {final_video}")
    log("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH VIDEO GENERATION FAILED")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)
        sys.exit(1)
