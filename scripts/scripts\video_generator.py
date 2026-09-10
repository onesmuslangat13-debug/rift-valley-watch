# ============================================================
# RIFT VALLEY WATCH V1.0
# PROFESSIONAL NEWSROOM VIDEO GENERATOR
# ============================================================

from pathlib import Path
import json
import math
import subprocess
import sys
import textwrap
import shutil

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
AUDIO_DIR = ROOT / "audio"

SCRIPT_FILE = DATA_DIR / "script.json"
OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
AUDIO_FILE = AUDIO_DIR / "rift_valley_watch_narration.mp3"
FRAMES_DIR = OUTPUT_DIR / "frames"

OUTPUT_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
FRAMES_DIR.mkdir(exist_ok=True)


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

BACKGROUND = (14, 18, 24)
PANEL = (24, 30, 40)
WHITE = (245, 247, 250)
LIGHT = (190, 198, 210)
RED = (210, 45, 55)
GOLD = (224, 176, 65)
DARK_RED = (105, 24, 31)

FONT_DIR = ASSETS_DIR / "fonts"


# ============================================================
# FONT LOADING
# ============================================================

def find_font(names, size):
    candidates = []

    for name in names:
        candidates.append(FONT_DIR / name)

    candidates.extend([
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/Arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/Calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    ])

    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass

    return ImageFont.load_default()


def get_fonts():
    return {
        "title": find_font(
            [
                "Montserrat-Bold.ttf",
                "Montserrat-ExtraBold.ttf",
                "Arial-Bold.ttf",
            ],
            62,
        ),
        "headline": find_font(
            [
                "Montserrat-Bold.ttf",
                "Arial-Bold.ttf",
            ],
            46,
        ),
        "body": find_font(
            [
                "Montserrat-Regular.ttf",
                "Arial.ttf",
            ],
            34,
        ),
        "small": find_font(
            [
                "Montserrat-Regular.ttf",
                "Arial.ttf",
            ],
            27,
        ),
        "ticker": find_font(
            [
                "Montserrat-Bold.ttf",
                "Arial-Bold.ttf",
            ],
            25,
        ),
        "number": find_font(
            [
                "Montserrat-Bold.ttf",
                "Arial-Bold.ttf",
            ],
            75,
        ),
    }


FONTS = get_fonts()


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return " ".join(str(value).replace("\n", " ").split()).strip()


def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word

        bbox = draw.textbbox((0, 0), test, font=font)
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


def draw_wrapped(
    draw,
    text,
    x,
    y,
    font,
    fill,
    max_width,
    line_gap=12,
):
    lines = wrap_text(draw, text, font, max_width)

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

        current_y += (
            bbox[3] - bbox[1] + line_gap
        )

    return current_y


# ============================================================
# SCRIPT LOADING
# ============================================================

def load_script():
    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            f"Script file not found:\n{SCRIPT_FILE}"
        )

    try:
        with open(
            SCRIPT_FILE,
            "r",
            encoding="utf-8",
        ) as f:
            data = json.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read script.json: {exc}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            "script.json must contain a JSON object."
        )

    return data


# ============================================================
# STORY EXTRACTION
# ============================================================

def extract_story(data):
    story = data.get("story", {})

    if not isinstance(story, dict):
        story = {}

    title = clean_text(
        data.get("title")
        or story.get("title")
        or "Rift Valley Development Update"
    )

    county = clean_text(
        data.get("county")
        or story.get("county")
        or "Rift Valley"
    )

    category = clean_text(
        data.get("category")
        or story.get("category")
        or "NEWS"
    ).upper()

    script = clean_text(
        data.get("script")
        or data.get("text")
        or story.get("script")
        or story.get("text")
        or data.get("body")
        or ""
    )

    if not script:
        sections = []

        for key in [
            "hook",
            "what_happened",
            "key_facts",
            "why_it_matters",
            "impact",
            "close",
        ]:
            value = data.get(key)

            if value:
                sections.append(
                    clean_text(value)
                )

        script = " ".join(sections)

    if not script:
        raise RuntimeError(
            "No usable script text found in script.json."
        )

    return {
        "title": title,
        "county": county,
        "category": category,
        "script": script,
    }


# ============================================================
# AUDIO
# ============================================================

def find_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")

    if ffmpeg:
        return ffmpeg

    raise RuntimeError(
        "FFmpeg was not found. Install FFmpeg and make sure "
        "it is available in PATH."
    )


def find_python():
    return sys.executable


def generate_audio(text):
    print("[AUDIO] Preparing narration...")

    try:
        from gtts import gTTS
    except ImportError:
        raise RuntimeError(
            "gTTS is missing. Run:\n"
            "py -m pip install gTTS"
        )

    if AUDIO_FILE.exists():
        AUDIO_FILE.unlink()

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(str(AUDIO_FILE))

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )

    print(
        f"[AUDIO] Saved: {AUDIO_FILE}"
    )

    return AUDIO_FILE


def get_audio_duration(audio_path):
    ffmpeg = find_ffmpeg()

    command = [
        ffmpeg,
        "-i",
        str(audio_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stderr = result.stderr

    import re

    match = re.search(
        r"Duration:\s*(\d+):(\d+):([\d.]+)",
        stderr,
    )

    if not match:
        raise RuntimeError(
            "Could not determine narration duration."
        )

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    return (
        hours * 3600
        + minutes * 60
        + seconds
    )


# ============================================================
# NEWSROOM GRAPHICS
# ============================================================

def draw_top_bar(draw, category):
    draw.rectangle(
        [0, 0, WIDTH, 115],
        fill=(9, 12, 17),
    )

    draw.rectangle(
        [0, 0, 18, 115],
        fill=RED,
    )

    draw.text(
        (48, 27),
        "RIFT VALLEY WATCH",
        font=FONTS["headline"],
        fill=WHITE,
    )

    category_text = category.upper()

    bbox = draw.textbbox(
        (0, 0),
        category_text,
        font=FONTS["small"],
    )

    tw = bbox[2] - bbox[0]

    draw.rounded_rectangle(
        [
            WIDTH - tw - 70,
            30,
            WIDTH - 30,
            83,
        ],
        radius=12,
        fill=DARK_RED,
    )

    draw.text(
        (
            WIDTH - tw - 50,
            41,
        ),
        category_text,
        font=FONTS["small"],
        fill=WHITE,
    )


def draw_live_indicator(draw):
    x = 50
    y = 140

    draw.ellipse(
        [x, y, x + 18, y + 18],
        fill=RED,
    )

    draw.text(
        (x + 32, y - 8),
        "REGIONAL NEWS",
        font=FONTS["small"],
        fill=LIGHT,
    )


def draw_bottom_ticker(draw):
    y = HEIGHT - 105

    draw.rectangle(
        [0, y, WIDTH, HEIGHT],
        fill=(9, 12, 17),
    )

    draw.rectangle(
        [0, y, 190, HEIGHT],
        fill=RED,
    )

    draw.text(
        (32, y + 28),
        "RIFT VALLEY",
        font=FONTS["ticker"],
        fill=WHITE,
    )

    draw.text(
        (220, y + 28),
        "VERIFIED REGIONAL NEWS  •  DEVELOPMENT  •  ACCOUNTABILITY",
        font=FONTS["ticker"],
        fill=LIGHT,
    )


def draw_progress(draw, progress):
    y = HEIGHT - 135

    draw.rectangle(
        [0, y, WIDTH, y + 5],
        fill=(55, 60, 70),
    )

    draw.rectangle(
        [
            0,
            y,
            int(WIDTH * progress),
            y + 5,
        ],
        fill=RED,
    )


# ============================================================
# FRAME CREATION
# ============================================================

def create_frame(
    story,
    frame_index,
    total_frames,
):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(image)

    progress = (
        frame_index / max(1, total_frames - 1)
    )

    draw_top_bar(
        draw,
        story["category"],
    )

    draw_live_indicator(draw)

    # --------------------------------------------------------
    # Main newsroom panel
    # --------------------------------------------------------

    panel_left = 48
    panel_right = WIDTH - 48
    panel_top = 205
    panel_bottom = HEIGHT - 165

    draw.rounded_rectangle(
        [
            panel_left,
            panel_top,
            panel_right,
            panel_bottom,
        ],
        radius=28,
        fill=PANEL,
    )

    # Accent line

    draw.rectangle(
        [
            panel_left,
            panel_top,
            panel_left + 12,
            panel_bottom,
        ],
        fill=RED,
    )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    title = story["title"]

    draw.text(
        (
            panel_left + 45,
            panel_top + 45,
        ),
        "DEVELOPMENT UPDATE",
        font=FONTS["small"],
        fill=GOLD,
    )

    headline_y = panel_top + 105

    headline_bottom = draw_wrapped(
        draw,
        title,
        panel_left + 45,
        headline_y,
        FONTS["title"],
        WHITE,
        panel_right - panel_left - 90,
        line_gap=15,
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location_y = max(
        headline_bottom + 35,
        panel_top + 330,
    )

    draw.rounded_rectangle(
        [
            panel_left + 45,
            location_y,
            panel_right - 45,
            location_y + 70,
        ],
        radius=14,
        fill=(33, 40, 52),
    )

    draw.text(
        (
            panel_left + 70,
            location_y + 19,
        ),
        story["county"].upper(),
        font=FONTS["small"],
        fill=WHITE,
    )

    draw.text(
        (
            panel_right - 300,
            location_y + 19,
        ),
        story["category"].upper(),
        font=FONTS["small"],
        fill=GOLD,
    )

    # --------------------------------------------------------
    # KEY STORY TEXT
    # --------------------------------------------------------

    body_y = location_y + 120

    body_height = (
        panel_bottom
        - body_y
        - 80
    )

    # Reveal script progressively to create movement.

    script_words = story["script"].split()

    reveal_ratio = min(
        1.0,
        max(
            0.20,
            progress * 1.35,
        ),
    )

    reveal_count = max(
        20,
        int(
            len(script_words)
            * reveal_ratio
        ),
    )

    visible_words = script_words[
        :reveal_count
    ]

    visible_text = " ".join(
        visible_words
    )

    draw_wrapped(
        draw,
        visible_text,
        panel_left + 45,
        body_y,
        FONTS["body"],
        LIGHT,
        panel_right - panel_left - 90,
        line_gap=13,
    )

    # --------------------------------------------------------
    # KEY FACT CARD
    # --------------------------------------------------------

    card_y = panel_bottom - 220

    draw.rounded_rectangle(
        [
            panel_left + 45,
            card_y,
            panel_right - 45,
            panel_bottom - 45,
        ],
        radius=18,
        fill=(17, 22, 30),
    )

    draw.text(
        (
            panel_left + 70,
            card_y + 25,
        ),
        "WHY IT MATTERS",
        font=FONTS["small"],
        fill=GOLD,
    )

    impact_text = (
        "Residents will be watching delivery, "
        "timelines, public value and accountability."
    )

    draw_wrapped(
        draw,
        impact_text,
        panel_left + 70,
        card_y + 75,
        FONTS["small"],
        WHITE,
        panel_right - panel_left - 140,
        line_gap=8,
    )

    draw_bottom_ticker(draw)

    draw_progress(
        draw,
        progress,
    )

    return image


# ============================================================
# RENDER VIDEO
# ============================================================

def render_video(
    story,
    audio_path,
    output_path,
):
    ffmpeg = find_ffmpeg()

    print("[VIDEO] Measuring narration...")

    audio_duration = get_audio_duration(
        audio_path
    )

    target_duration = (
        audio_duration + 0.5
    )

    total_frames = max(
        1,
        int(
            math.ceil(
                target_duration * FPS
            )
        ),
    )

    print(
        f"[VIDEO] Audio duration: "
        f"{audio_duration:.2f}s"
    )

    print(
        f"[VIDEO] Target duration: "
        f"{target_duration:.2f}s"
    )

    print(
        f"[VIDEO] Frames: "
        f"{total_frames}"
    )

    if FRAMES_DIR.exists():
        for old_frame in FRAMES_DIR.glob(
            "frame_*.png"
        ):
            try:
                old_frame.unlink()
            except Exception:
                pass

    print("[VIDEO] Creating newsroom frames...")

    for i in range(total_frames):
        image = create_frame(
            story,
            i,
            total_frames,
        )

        frame_path = (
            FRAMES_DIR
            / f"frame_{i:06d}.png"
        )

        image.save(
            frame_path,
            "PNG",
        )

        if i % max(1, FPS * 5) == 0:
            percent = (
                i / total_frames
            ) * 100

            print(
                f"       {percent:5.1f}%"
            )

    print("[VIDEO] Encoding MP4...")

    command = [
        ffmpeg,
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(
            FRAMES_DIR
            / "frame_%06d.png"
        ),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr)

        raise RuntimeError(
            "FFmpeg failed while creating the MP4."
        )

    if not output_path.exists():
        raise RuntimeError(
            "MP4 was not created."
        )

    print(
        f"[VIDEO] MP4 created:\n"
        f"{output_path}"
    )


# ============================================================
# VIDEO QC
# ============================================================

def validate_video(
    video_path,
    audio_duration,
):
    ffmpeg = find_ffmpeg()

    if not video_path.exists():
        raise RuntimeError(
            "QC failed: MP4 file does not exist."
        )

    command = [
        ffmpeg,
        "-i",
        str(video_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stderr = result.stderr

    import re

    match = re.search(
        r"Duration:\s*(\d+):(\d+):([\d.]+)",
        stderr,
    )

    if not match:
        raise RuntimeError(
            "QC failed: could not determine MP4 duration."
        )

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))

    video_duration = (
        hours * 3600
        + minutes * 60
        + seconds
    )

    print(
        f"[QC] Video duration: "
        f"{video_duration:.2f}s"
    )

    print(
        f"[QC] Audio duration: "
        f"{audio_duration:.2f}s"
    )

    if video_duration + 0.1 < audio_duration:
        raise RuntimeError(
            "QC FAILED: narration is longer than the video."
        )

    if video_duration <= 0:
        raise RuntimeError(
            "QC FAILED: invalid video duration."
        )

    print("[QC] PASSED")


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V1.0")
    print("PROFESSIONAL NEWSROOM VIDEO GENERATOR")
    print("=" * 60)
    print()

    print("[1/4] Loading professional script...")

    data = load_script()

    story = extract_story(data)

    print(
        f"      County: {story['county']}"
    )

    print(
        f"      Category: {story['category']}"
    )

    print(
        f"      Headline: {story['title']}"
    )

    print(
        f"      Words: "
        f"{len(story['script'].split())}"
    )

    print()
    print("[2/4] Generating narration...")

    audio_path = generate_audio(
        story["script"]
    )

    audio_duration = get_audio_duration(
        audio_path
    )

    print(
        f"      Narration: "
        f"{audio_duration:.2f}s"
    )

    print()
    print("[3/4] Building professional MP4...")

    render_video(
        story,
        audio_path,
        OUTPUT_FILE,
    )

    print()
    print("[4/4] Running final QC...")

    validate_video(
        OUTPUT_FILE,
        audio_duration,
    )

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH VIDEO COMPLETE")
    print("=" * 60)
    print()
    print(
        f"MP4: {OUTPUT_FILE}"
    )
    print()


if __name__ == "__main__":
    main()
