# ============================================================
# RIFT VALLEY WATCH
# COMPLETE VIDEO GENERATOR
#
# Output:
#   output/rift_valley_watch_reel.mp4
#
# Target:
#   1080x1920
#   H.264
#   AAC
#   ~35 seconds
#   One verified story
#   Real article image
#   6 professional news scenes
# ============================================================

import os
import json
import time
import shutil
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = ROOT / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"
AUDIO_FILE = OUTPUT_DIR / "narration.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

SCENE_DIR = OUTPUT_DIR / "scenes"

VISUAL_METADATA = DATA_DIR / "visual_metadata.json"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

TARGET_DURATION = 35.0

FPS = 30

MIN_DURATION = 31.5
MAX_DURATION = 38.5


# ============================================================
# COLORS
# ============================================================

BLACK = (8, 10, 14)
WHITE = (255, 255, 255)
LIGHT = (235, 238, 242)
GRAY = (165, 170, 180)
DARK_GRAY = (35, 39, 46)

RED = (220, 35, 45)
GOLD = (224, 173, 58)
GREEN = (35, 170, 100)


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    if isinstance(
        value,
        (dict, list),
    ):
        return ""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .split()
    ).strip()


def first_nonempty(*values):

    for value in values:

        value = clean_text(
            value
        )

        if value:
            return value

    return ""


def shorten(text, maximum):

    text = clean_text(
        text
    )

    if len(text) <= maximum:
        return text

    value = text[:maximum]

    if " " in value:
        value = value.rsplit(
            " ",
            1,
        )[0]

    return value.rstrip(
        ".,;:"
    ) + "..."


# ============================================================
# JSON
# ============================================================

def read_json(path):

    path = Path(path)

    if not path.exists():
        return {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def write_json(path, data):

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# FONTS
# ============================================================

def find_font(
    size,
    bold=False,
):

    candidates = []

    if bold:

        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )

    else:

        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )

    for candidate in candidates:

        if os.path.exists(
            candidate
        ):

            return ImageFont.truetype(
                candidate,
                size=size,
            )

    return ImageFont.load_default()


FONT_HUGE = find_font(
    82,
    True,
)

FONT_TITLE = find_font(
    66,
    True,
)

FONT_SUBTITLE = find_font(
    46,
    True,
)

FONT_BODY = find_font(
    39,
    False,
)

FONT_BODY_BOLD = find_font(
    40,
    True,
)

FONT_SMALL = find_font(
    30,
    False,
)

FONT_SMALL_BOLD = find_font(
    31,
    True,
)

FONT_TINY = find_font(
    25,
    False,
)


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image_file(
    path
):

    path = Path(path)

    if not path.exists():
        return False

    if path.stat().st_size < 5000:
        return False

    try:

        with Image.open(
            path
        ) as image:

            image.verify()

        return True

    except Exception:

        return False


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    image_url
):

    if not image_url:

        raise RuntimeError(
            "No article image URL was provided."
        )

    blocked_terms = [
        "google",
        "facebook",
        "instagram",
        "youtube",
        "tiktok",
        "favicon",
        "placeholder",
        "avatar",
    ]

    url_low = image_url.lower()

    if any(
        term in url_low
        for term in blocked_terms
    ):

        raise RuntimeError(
            f"Rejected platform/logo image: {image_url}"
        )

    headers = {
        "User-Agent":
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/120 Safari/537.36",
    }

    print()
    print(
        "Downloading real article image..."
    )

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
            f"Image download failed: {exc}"
        )

    final_url = response.url

    final_low = final_url.lower()

    if any(
        term in final_low
        for term in blocked_terms
    ):

        raise RuntimeError(
            f"Image redirected to blocked platform: "
            f"{final_url}"
        )

    try:

        from io import BytesIO

        image = Image.open(
            BytesIO(
                response.content
            )
        )

        width, height = image.size

        if width < 400 or height < 250:

            raise RuntimeError(
                f"Article image too small: "
                f"{width}x{height}"
            )

        image = image.convert(
            "RGB"
        )

        image.save(
            IMAGE_FILE,
            "JPEG",
            quality=95,
        )

    except Exception as exc:

        raise RuntimeError(
            f"Downloaded image is invalid: {exc}"
        )

    print(
        f"REAL ARTICLE IMAGE SAVED: {IMAGE_FILE}"
    )

    return IMAGE_FILE


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_image():

    if not validate_image_file(
        IMAGE_FILE
    ):

        raise RuntimeError(
            "No valid article image exists at "
            f"{IMAGE_FILE}"
        )

    image = Image.open(
        IMAGE_FILE
    ).convert(
        "RGB"
    )

    source_width, source_height = image.size

    target_ratio = (
        WIDTH / HEIGHT
    )

    source_ratio = (
        source_width / source_height
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            source_width
            * HEIGHT
            / source_height
        )

    else:

        new_width = WIDTH

        new_height = int(
            source_height
            * WIDTH
            / source_width
        )

    image = image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - WIDTH
    ) // 2

    top = (
        new_height - HEIGHT
    ) // 2

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )

    prepared = SOURCE_DIR / "prepared_story_image.jpg"

    image.save(
        prepared,
        "JPEG",
        quality=94,
    )

    return prepared


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = clean_text(
        text
    ).split()

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
            bbox[2] - bbox[0]
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
    fill,
    max_width,
    line_spacing=12,
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
            fill=fill,
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=font,
        )

        height = (
            bbox[3] - bbox[1]
        )

        current_y += (
            height
            + line_spacing
        )

    return current_y


# ============================================================
# BASE SCENE
# ============================================================

def base_scene(
    background
):

    image = background.copy()

    draw = ImageDraw.Draw(
        image
    )

    # Top broadcast bar
    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            150,
        ),
        fill=BLACK,
    )

    draw.rectangle(
        (
            0,
            145,
            WIDTH,
            152,
        ),
        fill=RED,
    )

    draw.text(
        (
            60,
            42,
        ),
        "RIFT VALLEY WATCH",
        font=FONT_SMALL_BOLD,
        fill=WHITE,
    )

    draw.text(
        (
            60,
            88,
        ),
        "REGIONAL NEWS",
        font=FONT_TINY,
        fill=GRAY,
    )

    return image, draw


# ============================================================
# BOTTOM PANEL
# ============================================================

def bottom_panel(
    draw,
    height=680,
):

    top = HEIGHT - height

    draw.rectangle(
        (
            0,
            top,
            WIDTH,
            HEIGHT,
        ),
        fill=BLACK,
    )

    draw.rectangle(
        (
            0,
            top,
            14,
            HEIGHT,
        ),
        fill=RED,
    )

    return top


# ============================================================
# SCENE 1
# ============================================================

def create_title_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    draw.rectangle(
        (
            0,
            150,
            WIDTH,
            HEIGHT,
        ),
        fill=None,
    )

    # Dark lower overlay
    top = bottom_panel(
        draw,
        760,
    )

    draw.text(
        (
            60,
            top + 55,
        ),
        "BREAKING REGIONAL UPDATE",
        font=FONT_SMALL_BOLD,
        fill=RED,
    )

    title = first_nonempty(
        story.get("title"),
        "Regional Update",
    )

    draw_wrapped_text(
        draw,
        title,
        60,
        top + 115,
        FONT_TITLE,
        WHITE,
        WIDTH - 120,
        15,
    )

    county = first_nonempty(
        story.get("county"),
        "Rift Valley",
    )

    draw.text(
        (
            60,
            HEIGHT - 120,
        ),
        county.upper(),
        font=FONT_SMALL_BOLD,
        fill=GOLD,
    )

    return image


# ============================================================
# SCENE 2
# ============================================================

def create_context_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    top = bottom_panel(
        draw,
        800,
    )

    draw.text(
        (
            60,
            top + 55,
        ),
        "WHERE IT HAPPENED",
        font=FONT_SMALL_BOLD,
        fill=GOLD,
    )

    county = first_nonempty(
        story.get("county"),
        "Rift Valley",
    )

    location = first_nonempty(
        story.get("location"),
        story.get("area"),
        county,
    )

    draw.text(
        (
            60,
            top + 125,
        ),
        county.upper(),
        font=FONT_HUGE,
        fill=WHITE,
    )

    draw_wrapped_text(
        draw,
        location,
        60,
        top + 235,
        FONT_SUBTITLE,
        LIGHT,
        WIDTH - 120,
        12,
    )

    summary = first_nonempty(
        story.get("summary"),
        story.get("description"),
    )

    draw_wrapped_text(
        draw,
        shorten(summary, 420),
        60,
        top + 370,
        FONT_BODY,
        WHITE,
        WIDTH - 120,
        12,
    )

    return image


# ============================================================
# SCENE 3
# ============================================================

def create_facts_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    top = bottom_panel(
        draw,
        820,
    )

    draw.text(
        (
            60,
            top + 55,
        ),
        "KEY FACTS",
        font=FONT_SMALL_BOLD,
        fill=RED,
    )

    facts = story.get(
        "verified_facts"
    )

    if isinstance(
        facts,
        dict,
    ):

        fact_list = []

        for key, value in facts.items():

            value = clean_text(
                value
            )

            if value:
                fact_list.append(
                    f"{key}: {value}"
                )

    elif isinstance(
        facts,
        list,
    ):

        fact_list = [
            clean_text(x)
            for x in facts
            if clean_text(x)
        ]

    else:

        fact_list = []

    if not fact_list:

        fact_list = [
            first_nonempty(
                story.get("summary"),
                "Verified regional development.",
            )
        ]

    y = top + 125

    for index, fact in enumerate(
        fact_list[:4],
        start=1,
    ):

        draw.ellipse(
            (
                60,
                y + 7,
                90,
                y + 37,
            ),
            fill=RED,
        )

        draw.text(
            (
                69,
                y + 4,
            ),
            str(index),
            font=FONT_TINY,
            fill=WHITE,
        )

        y = draw_wrapped_text(
            draw,
            shorten(
                fact,
                240,
            ),
            120,
            y,
            FONT_BODY,
            WHITE,
            WIDTH - 180,
            10,
        )

        y += 30

    return image


# ============================================================
# SCENE 4
# ============================================================

def create_details_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    top = bottom_panel(
        draw,
        800,
    )

    draw.text(
        (
            60,
            top + 55,
        ),
        "PROJECT / DEVELOPMENT DETAILS",
        font=FONT_SMALL_BOLD,
        fill=GOLD,
    )

    title = first_nonempty(
        story.get("title"),
        "Regional Development",
    )

    draw_wrapped_text(
        draw,
        title,
        60,
        top + 125,
        FONT_SUBTITLE,
        WHITE,
        WIDTH - 120,
        12,
    )

    details = []

    for key in [
        "amount",
        "value",
        "budget",
        "cost",
        "distance",
        "length",
        "project",
        "route",
        "location",
        "area",
    ]:

        value = clean_text(
            story.get(key)
        )

        if value:
            details.append(
                value
            )

    if not details:

        details = [
            shorten(
                first_nonempty(
                    story.get("summary"),
                    story.get("description"),
                ),
                500,
            )
        ]

    y = top + 300

    for detail in details[:4]:

        draw.rectangle(
            (
                60,
                y,
                1020,
                y + 105,
            ),
            fill=DARK_GRAY,
        )

        draw_wrapped_text(
            draw,
            detail,
            90,
            y + 24,
            FONT_BODY,
            WHITE,
            900,
            8,
        )

        y += 125

    return image


# ============================================================
# SCENE 5
# ============================================================

def create_statement_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    top = bottom_panel(
        draw,
        820,
    )

    draw.text(
        (
            60,
            top + 55,
        ),
        "OFFICIAL STATEMENT",
        font=FONT_SMALL_BOLD,
        fill=RED,
    )

    statement = first_nonempty(
        story.get("official_statement"),
        story.get("official_quote"),
        story.get("statement"),
    )

    if not statement:

        statement = (
            "Officials have confirmed "
            "the reported development."
        )

    draw_wrapped_text(
        draw,
        "“"
        + shorten(
            statement,
            520,
        )
        + "”",
        60,
        top + 140,
        FONT_SUBTITLE,
        WHITE,
        WIDTH - 120,
        15,
    )

    speaker = first_nonempty(
        story.get("official_source"),
        story.get("speaker"),
        story.get("quoted_person"),
    )

    if speaker:

        draw.text(
            (
                60,
                HEIGHT - 170,
            ),
            "— "
            + shorten(
                speaker,
                80,
            ),
            font=FONT_SMALL_BOLD,
            fill=GOLD,
        )

    return image


# ============================================================
# SCENE 6
# ============================================================

def create_source_scene(
    background,
    story,
):

    image, draw = base_scene(
        background
    )

    top = bottom_panel(
        draw,
        780,
    )

    draw.text(
        (
            60,
            top + 60,
        ),
        "SOURCE",
        font=FONT_SMALL_BOLD,
        fill=GOLD,
    )

    source = first_nonempty(
        story.get("source_name"),
        story.get("publisher"),
        story.get("source"),
        "Verified report",
    )

    # NEVER render raw URL.
    draw_wrapped_text(
        draw,
        source,
        60,
        top + 145,
        FONT_HUGE,
        WHITE,
        WIDTH - 120,
        15,
    )

    county = first_nonempty(
        story.get("county"),
        "Rift Valley",
    )

    draw.text(
        (
            60,
            top + 330,
        ),
        county,
        font=FONT_SUBTITLE,
        fill=LIGHT,
    )

    draw.text(
        (
            60,
            HEIGHT - 180,
        ),
        "RIFT VALLEY WATCH",
        font=FONT_SMALL_BOLD,
        fill=RED,
    )

    draw.text(
        (
            60,
            HEIGHT - 125,
        ),
        "Verified regional reporting",
        font=FONT_SMALL,
        fill=GRAY,
    )

    return image


# ============================================================
# SCENE CREATION
# ============================================================

def create_scenes(
    background,
    story,
):

    scenes = [
        create_title_scene(
            background,
            story,
        ),

        create_context_scene(
            background,
            story,
        ),

        create_facts_scene(
            background,
            story,
        ),

        create_details_scene(
            background,
            story,
        ),

        create_statement_scene(
            background,
            story,
        ),

        create_source_scene(
            background,
            story,
        ),
    ]

    paths = []

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        path = (
            SCENE_DIR
            / f"scene_{index:02d}.jpg"
        )

        scene.save(
            path,
            "JPEG",
            quality=94,
        )

        paths.append(
            path
        )

    return paths


# ============================================================
# NARRATION
# ============================================================

def build_narration(
    story,
    script,
):

    narration = first_nonempty(
        script.get("narration"),
        story.get("narration"),
    )

    if not narration:

        title = first_nonempty(
            story.get("title"),
            "Regional update",
        )

        county = first_nonempty(
            story.get("county"),
            "the Rift Valley",
        )

        summary = first_nonempty(
            story.get("summary"),
            story.get("description"),
        )

        narration = (
            f"Here is the latest verified "
            f"update from {county}. "
            f"{title}. "
            f"{summary}. "
            f"Rift Valley Watch will continue "
            f"tracking verified developments "
            f"across the region."
        )

    # Remove bad legacy attribution.
    banned_phrases = [
        "this is a county news story",
        "reported by facebook.com",
        "reported by facebook",
        "google news",
        "news from around the web",
    ]

    low = narration.lower()

    for phrase in banned_phrases:

        if phrase in low:

            narration = narration.replace(
                phrase,
                "",
            )

            narration = narration.replace(
                phrase.title(),
                "",
            )

    narration = clean_text(
        narration
    )

    return narration


# ============================================================
# AUDIO
# ============================================================

def create_audio(
    narration
):

    if not narration:

        raise RuntimeError(
            "No narration was provided."
        )

    print()
    print(
        "Creating narration..."
    )

    temp_audio = OUTPUT_DIR / (
        "narration_temp.mp3"
    )

    try:

        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(
            str(temp_audio)
        )

    except Exception as exc:

        raise RuntimeError(
            f"gTTS failed: {exc}"
        )

    if not temp_audio.exists():
        raise RuntimeError(
            "Narration file was not created."
        )

    shutil.copy2(
        temp_audio,
        AUDIO_FILE,
    )

    print(
        f"Narration saved: {AUDIO_FILE}"
    )

    return AUDIO_FILE


# ============================================================
# AUDIO DURATION
# ============================================================

def get_duration(
    path
):

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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        return 0.0

    try:
        return float(
            result.stdout.strip()
        )

    except Exception:
        return 0.0


# ============================================================
# SCENE VIDEO
# ============================================================

def create_silent_video(
    scene_paths,
    duration,
):

    print()
    print(
        "Creating six-scene video..."
    )

    # Six scenes.
    # Slightly different durations prevent the reel from
    # feeling like a static slide deck.

    weights = [
        1.10,
        1.00,
        1.00,
        1.00,
        0.95,
        0.95,
    ]

    total_weight = sum(
        weights
    )

    durations = [
        duration
        * weight
        / total_weight
        for weight in weights
    ]

    concat_file = OUTPUT_DIR / (
        "scenes_concat.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for path, scene_duration in zip(
            scene_paths,
            durations,
        ):

            f.write(
                f"file '{path.resolve()}'\n"
            )

            f.write(
                f"duration {scene_duration:.3f}\n"
            )

        # FFmpeg concat requires the final file
        # to be repeated.
        f.write(
            f"file '{scene_paths[-1].resolve()}'\n"
        )

    silent_video = OUTPUT_DIR / (
        "silent_video.mp4"
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
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2"
        ),
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(silent_video),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            "FFmpeg failed while creating "
            "the silent video."
        )

    return silent_video


# ============================================================
# COMBINE AUDIO
# ============================================================

def combine_video_audio(
    silent_video,
    audio,
):

    print()
    print(
        "Combining video and narration..."
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(silent_video),
        "-i",
        str(audio),
        "-filter_complex",
        (
            "[1:a]"
            "loudnorm="
            "I=-16:"
            "TP=-1.5:"
            "LRA=11"
            "[audio]"
        ),
        "-map",
        "0:v:0",
        "-map",
        "[audio]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUTPUT_FILE),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-6000:]
        )

        raise RuntimeError(
            "FFmpeg failed while combining "
            "video and audio."
        )

    if not OUTPUT_FILE.exists():

        raise RuntimeError(
            "Final MP4 was not created."
        )

    return OUTPUT_FILE


# ============================================================
# EXTEND VIDEO TO TARGET
# ============================================================

def enforce_target_duration(
    video_path,
    target_duration,
):

    current = get_duration(
        video_path
    )

    if current <= 0:
        raise RuntimeError(
            "Unable to determine generated video duration."
        )

    # Within acceptable range.
    if (
        MIN_DURATION
        <= current
        <= MAX_DURATION
    ):
        return video_path

    print(
        f"Duration before correction: "
        f"{current:.2f}s"
    )

    corrected = OUTPUT_DIR / (
        "corrected_duration.mp4"
    )

    # If video is too short, use a video filter to slow it
    # slightly. This is preferable to producing a 17-second
    # reel when the target is approximately 35 seconds.
    if current < MIN_DURATION:

        speed = (
            current
            / target_duration
        )

        speed = max(
            0.45,
            min(
                speed,
                0.98,
            ),
        )

        video_filter = (
            f"setpts={1/speed:.6f}*PTS"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-filter:v",
            video_filter,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            str(corrected),
        ]

    else:

        # Too long: trim to target.
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-t",
            str(target_duration),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            str(corrected),
        ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            "Duration correction failed."
        )

    if not corrected.exists():

        raise RuntimeError(
            "Duration-corrected video was not created."
        )

    # Recombine audio if correction removed it.
    final_corrected = OUTPUT_DIR / (
        "final_corrected.mp4"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(corrected),
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
        str(final_corrected),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            "Failed to restore narration after "
            "duration correction."
        )

    shutil.copy2(
        final_corrected,
        OUTPUT_FILE,
    )

    return OUTPUT_FILE


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_video(
    path
):

    if not path.exists():

        raise RuntimeError(
            f"Final video missing: {path}"
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "ffprobe could not inspect the final MP4."
        )

    try:

        data = json.loads(
            result.stdout
        )

    except Exception:

        raise RuntimeError(
            "Invalid ffprobe response."
        )

    streams = data.get(
        "streams",
        [],
    )

    video = None
    audio = None

    for stream in streams:

        if stream.get(
            "codec_type"
        ) == "video":

            video = stream

        elif stream.get(
            "codec_type"
        ) == "audio":

            audio = stream

    if video is None:

        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio is None:

        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

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

    codec = video.get(
        "codec_name"
    )

    audio_codec = audio.get(
        "codec_name"
    )

    duration = float(
        data.get(
            "format",
            {},
        ).get(
            "duration",
            0,
        )
    )

    if width != WIDTH:

        raise RuntimeError(
            f"Wrong width: {width}"
        )

    if height != HEIGHT:

        raise RuntimeError(
            f"Wrong height: {height}"
        )

    if codec != "h264":

        raise RuntimeError(
            f"Wrong video codec: {codec}"
        )

    if audio_codec != "aac":

        raise RuntimeError(
            f"Wrong audio codec: {audio_codec}"
        )

    if duration < MIN_DURATION:

        raise RuntimeError(
            f"FINAL VIDEO TOO SHORT: "
            f"{duration:.2f}s. "
            f"Required at least {MIN_DURATION}s."
        )

    if duration > MAX_DURATION:

        raise RuntimeError(
            f"FINAL VIDEO TOO LONG: "
            f"{duration:.2f}s. "
            f"Maximum {MAX_DURATION}s."
        )

    print()
    print(
        "============================================================"
    )
    print(
        "FINAL VIDEO QC PASSED"
    )
    print(
        "============================================================"
    )

    print(
        f"Resolution: {width}x{height}"
    )

    print(
        f"Duration:   {duration:.2f}s"
    )

    print(
        f"Video:      {codec}"
    )

    print(
        f"Audio:      {audio_codec}"
    )

    print(
        f"File size:  "
        f"{path.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print(
        "============================================================"
    )

    return {
        "duration": round(
            duration,
            2,
        ),
        "width": width,
        "height": height,
        "video_codec": codec,
        "audio_codec": audio_codec,
        "size_mb": round(
            path.stat().st_size
            / 1024
            / 1024,
            2,
        ),
    }


# ============================================================
# VISUAL METADATA
# ============================================================

def save_visual_metadata(
    story,
    scene_paths,
    video_info,
):

    metadata = {
        "project": "Rift Valley Watch",
        "title": story.get(
            "title"
        ),
        "county": story.get(
            "county"
        ),
        "source": first_nonempty(
            story.get("source_name"),
            story.get("source"),
            "Verified report",
        ),
        "source_url": story.get(
            "source_url"
        ),
        "image_url": story.get(
            "image"
        ),
        "image_file": str(
            IMAGE_FILE
        ),
        "scene_count": len(
            scene_paths
        ),
        "scenes": [
            {
                "scene": index + 1,
                "file": str(path),
            }
            for index, path in enumerate(
                scene_paths
            )
        ],
        "duration_target": TARGET_DURATION,
        "video": video_info,
    }

    write_json(
        VISUAL_METADATA,
        metadata,
    )


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_video(
    story,
    script=None,
):

    ensure_directories()

    story = dict(
        story or {}
    )

    script = dict(
        script or {}
    )

    print()
    print(
        "============================================================"
    )
    print(
        "RIFT VALLEY WATCH VIDEO GENERATOR"
    )
    print(
        "============================================================"
    )

    # --------------------------------------------------------
    # IMAGE RECOVERY
    # --------------------------------------------------------

    image_url = first_nonempty(
        story.get("image"),
        story.get("image_url"),
        story.get("imageUrl"),
        story.get("featured_image"),
        story.get("thumbnail"),
        script.get("image"),
        script.get("image_url"),
    )

    local_image = first_nonempty(
        story.get("local_image"),
        script.get("local_image"),
    )

    if local_image:

        local_path = Path(
            local_image
        )

        if (
            local_path.exists()
            and validate_image_file(
                local_path
            )
        ):

            print()
            print(
                "IMAGE RECOVERY"
            )

            print(
                "Using existing verified local article image:"
            )

            print(
                local_path
            )

            if (
                local_path.resolve()
                != IMAGE_FILE.resolve()
            ):

                shutil.copy2(
                    local_path,
                    IMAGE_FILE,
                )

    if not validate_image_file(
        IMAGE_FILE
    ):

        if image_url:

            download_image(
                image_url
            )

        else:

            raise RuntimeError(
                "No usable article image URL "
                "or local article image was provided."
            )

    # --------------------------------------------------------
    # PREPARE IMAGE
    # --------------------------------------------------------

    prepared_image = prepare_image()

    background = Image.open(
        prepared_image
    ).convert(
        "RGB"
    )

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = build_narration(
        story,
        script,
    )

    if not narration:

        raise RuntimeError(
            "No narration was provided."
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    create_audio(
        narration
    )

    audio_duration = get_duration(
        AUDIO_FILE
    )

    if audio_duration <= 0:

        raise RuntimeError(
            "Could not determine narration duration."
        )

    print(
        f"Narration duration: "
        f"{audio_duration:.2f}s"
    )

    # --------------------------------------------------------
    # TARGET VIDEO DURATION
    #
    # We deliberately target 35 seconds instead of simply
    # accepting the narration length. This prevents the old
    # ~17-second output problem.
    # --------------------------------------------------------

    render_duration = TARGET_DURATION

    # --------------------------------------------------------
    # SCENES
    # --------------------------------------------------------

    scene_paths = create_scenes(
        background,
        story,
    )

    if len(scene_paths) != 6:

        raise RuntimeError(
            "Exactly six scenes are required."
        )

    print(
        f"Created {len(scene_paths)} scenes."
    )

    # --------------------------------------------------------
    # SILENT VIDEO
    # --------------------------------------------------------

    silent_video = create_silent_video(
        scene_paths,
        render_duration,
    )

    # --------------------------------------------------------
    # COMBINE AUDIO
    # --------------------------------------------------------

    combine_video_audio(
        silent_video,
        AUDIO_FILE,
    )

    # --------------------------------------------------------
    # DURATION CORRECTION
    # --------------------------------------------------------

    enforce_target_duration(
        OUTPUT_FILE,
        TARGET_DURATION,
    )

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    video_info = validate_video(
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    save_visual_metadata(
        story,
        scene_paths,
        video_info,
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    print()
    print(
        "============================================================"
    )
    print(
        "VIDEO GENERATION COMPLETE"
    )
    print(
        "============================================================"
    )

    print(
        f"Title: "
        f"{story.get('title', 'Regional Update')}"
    )

    print(
        f"County: "
        f"{story.get('county', 'Rift Valley')}"
    )

    print(
        f"Image: "
        f"{IMAGE_FILE}"
    )

    print(
        f"Output: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Duration: "
        f"{video_info['duration']} seconds"
    )

    print(
        "Status: SUCCESS"
    )

    print(
        "============================================================"
    )

    return OUTPUT_FILE


# ============================================================
# STANDALONE MODE
# ============================================================

def standalone():

    ensure_directories()

    story = read_json(
        STORY_FILE
    )

    script = read_json(
        SCRIPT_FILE
    )

    # Prefer selected story.
    if not story:

        fallback = DATA_DIR / "story.json"

        story = read_json(
            fallback
        )

    if not script:

        fallback = DATA_DIR / "script.json"

        script = read_json(
            fallback
        )

    if not story:

        raise RuntimeError(
            "No story JSON was found."
        )

    # Recover local image automatically.
    if not story.get(
        "local_image"
    ):

        if validate_image_file(
            IMAGE_FILE
        ):

            story["local_image"] = str(
                IMAGE_FILE
            )

    return generate_video(
        story,
        script,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        standalone()

    except Exception as exc:

        print()
        print(
            "============================================================"
        )

        print(
            "RIFT VALLEY WATCH VIDEO GENERATOR FAILED"
        )

        print(
            "============================================================"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "============================================================"
        )

        raise
