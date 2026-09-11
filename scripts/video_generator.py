# ============================================================
# RIFT VALLEY WATCH V2
# PROFESSIONAL NEWS VIDEO GENERATOR
# ============================================================

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

SCRIPT_FILE = BASE_DIR / "data" / "script.json"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30


# ============================================================
# FONTS
# ============================================================

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

if not Path(FONT_BOLD).exists():
    FONT_BOLD = "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"

if not Path(FONT_REGULAR).exists():
    FONT_REGULAR = "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"


def font(size, bold=False):
    return ImageFont.truetype(
        FONT_BOLD if bold else FONT_REGULAR,
        size
    )


# ============================================================
# COLORS
# ============================================================

NAVY = (7, 17, 30)
NAVY_2 = (14, 30, 50)
WHITE = (245, 248, 252)
LIGHT = (205, 214, 225)
RED = (220, 38, 38)
DARK_BOX = (17, 35, 55)
BLACK = (0, 0, 0)


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(command):

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            "FFmpeg command failed."
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):

    if not path.exists():
        raise RuntimeError(
            f"Required file not found: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def clean_editorial_text(text):

    text = clean_text(text)

    # Fix known typo without changing other editorial content.
    text = re.sub(
        r"\bRoad\s+lenght\b",
        "Road length",
        text,
        flags=re.IGNORECASE
    )

    return text


def wrap_text(
    draw,
    text,
    selected_font,
    max_width
):

    words = clean_text(text).split()

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
            font=selected_font
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
    selected_font,
    fill,
    max_width,
    line_spacing=12
):

    lines = wrap_text(
        draw,
        text,
        selected_font,
        max_width
    )

    current_y = y

    for line in lines:

        draw.text(
            (x, current_y),
            line,
            font=selected_font,
            fill=fill
        )

        bbox = draw.textbbox(
            (x, current_y),
            line,
            font=selected_font
        )

        height = bbox[3] - bbox[1]

        current_y += height + line_spacing

    return current_y


# ============================================================
# BACKGROUND
# ============================================================

def add_gradient_background(image):

    draw = ImageDraw.Draw(image)

    for y in range(VIDEO_HEIGHT):

        ratio = y / VIDEO_HEIGHT

        r = int(
            NAVY[0]
            + (NAVY_2[0] - NAVY[0]) * ratio
        )

        g = int(
            NAVY[1]
            + (NAVY_2[1] - NAVY[1]) * ratio
        )

        b = int(
            NAVY[2]
            + (NAVY_2[2] - NAVY[2]) * ratio
        )

        draw.line(
            [(0, y), (VIDEO_WIDTH, y)],
            fill=(r, g, b)
        )


# ============================================================
# BRANDING
# ============================================================

def add_top_branding(
    draw,
    category
):

    draw.text(
        (70, 55),
        "RIFT VALLEY WATCH",
        font=font(42, True),
        fill=WHITE
    )

    category_text = clean_text(
        category
    ).upper()

    category_font = font(
        28,
        True
    )

    bbox = draw.textbbox(
        (0, 0),
        category_text,
        font=category_font
    )

    category_width = (
        bbox[2] - bbox[0]
    )

    right = VIDEO_WIDTH - 55
    left = right - category_width - 55

    draw.rounded_rectangle(
        (
            left,
            52,
            right,
            105
        ),
        radius=18,
        fill=RED
    )

    draw.text(
        (
            left + 28,
            61
        ),
        category_text,
        font=category_font,
        fill=WHITE
    )

    draw.rectangle(
        (
            70,
            130,
            VIDEO_WIDTH - 70,
            136
        ),
        fill=RED
    )


def add_footer(
    draw,
    source,
    date
):

    footer_y = VIDEO_HEIGHT - 135

    draw.rectangle(
        (
            50,
            footer_y,
            VIDEO_WIDTH - 50,
            VIDEO_HEIGHT - 45
        ),
        fill=(4, 11, 20)
    )

    draw.text(
        (75, footer_y + 17),
        "SOURCE: " + clean_text(source),
        font=font(27, True),
        fill=WHITE
    )

    draw.text(
        (75, footer_y + 57),
        clean_text(date),
        font=font(24),
        fill=LIGHT
    )


# ============================================================
# CARD BASE
# ============================================================

def new_card(story):

    image = Image.new(
        "RGB",
        (
            VIDEO_WIDTH,
            VIDEO_HEIGHT
        )
    )

    add_gradient_background(image)

    draw = ImageDraw.Draw(image)

    add_top_branding(
        draw,
        story["category"]
    )

    return image, draw


# ============================================================
# HOOK CARD
# ============================================================

def create_hook_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 235),
        "LATEST",
        font=font(48, True),
        fill=RED
    )

    draw_wrapped_text(
        draw,
        story["title"],
        70,
        330,
        font(70, True),
        WHITE,
        VIDEO_WIDTH - 140,
        18
    )

    draw.rounded_rectangle(
        (
            70,
            930,
            VIDEO_WIDTH - 70,
            1170
        ),
        radius=28,
        fill=DARK_BOX
    )

    draw.text(
        (110, 980),
        story["county"],
        font=font(42, True),
        fill=WHITE
    )

    draw.text(
        (110, 1050),
        "VERIFIED REGIONAL UPDATE",
        font=font(29, True),
        fill=LIGHT
    )

    add_footer(
        draw,
        story["source"]["name"],
        story["date"]
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# KEY FACTS CARD
# ============================================================

def create_facts_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 225),
        "KEY FACTS",
        font=font(58, True),
        fill=WHITE
    )

    draw.rectangle(
        (
            70,
            305,
            260,
            315
        ),
        fill=RED
    )

    facts = story.get(
        "verified_facts",
        []
    )

    y = 390

    for index, fact in enumerate(facts[:6]):

        draw.text(
            (75, y),
            f"{index + 1:02d}",
            font=font(36, True),
            fill=RED
        )

        label = clean_text(
            fact.get("label", "")
        ).upper()

        value = clean_text(
            fact.get("value", "")
        )

        draw.text(
            (165, y),
            label,
            font=font(27, True),
            fill=LIGHT
        )

        draw_wrapped_text(
            draw,
            value,
            165,
            y + 48,
            font(38, True),
            WHITE,
            VIDEO_WIDTH - 235,
            8
        )

        y += 210

        if y > 1500:
            break

    add_footer(
        draw,
        story["source"]["name"],
        story["date"]
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# CONTEXT CARD
# ============================================================

def create_context_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 230),
        "WHAT WE KNOW",
        font=font(55, True),
        fill=WHITE
    )

    draw.rectangle(
        (
            70,
            315,
            VIDEO_WIDTH - 70,
            322
        ),
        fill=RED
    )

    editorial = story.get(
        "editorial",
        {}
    )

    confirmed = editorial.get(
        "confirmed",
        []
    )

    unconfirmed = editorial.get(
        "unconfirmed",
        []
    )

    y = 390

    for item in confirmed[:5]:

        draw.ellipse(
            (
                75,
                y + 12,
                100,
                y + 37
            ),
            fill=RED
        )

        y = draw_wrapped_text(
            draw,
            clean_editorial_text(item),
            135,
            y,
            font(37),
            WHITE,
            VIDEO_WIDTH - 205,
            10
        )

        y += 45

    if unconfirmed:

        box_top = max(
            y + 25,
            1050
        )

        box_bottom = min(
            box_top + 480,
            VIDEO_HEIGHT - 230
        )

        draw.rounded_rectangle(
            (
                70,
                box_top,
                VIDEO_WIDTH - 70,
                box_bottom
            ),
            radius=28,
            fill=(29, 38, 50)
        )

        draw.text(
            (110, box_top + 35),
            "DETAILS TO CONFIRM",
            font=font(30, True),
            fill=RED
        )

        yy = box_top + 100

        for item in unconfirmed[:5]:

            fixed_item = clean_editorial_text(item)

            yy = draw_wrapped_text(
                draw,
                "• " + fixed_item,
                115,
                yy,
                font(29),
                LIGHT,
                VIDEO_WIDTH - 230,
                8
            )

            yy += 20

    add_footer(
        draw,
        story["source"]["name"],
        story["date"]
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# WHY IT MATTERS CARD
# ============================================================

def create_impact_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 230),
        "WHY IT MATTERS",
        font=font(55, True),
        fill=WHITE
    )

    draw.rectangle(
        (
            70,
            315,
            300,
            323
        ),
        fill=RED
    )

    impact = clean_text(
        story.get(
            "sections",
            {}
        ).get(
            "impact",
            story.get(
                "summary",
                ""
            )
        )
    )

    draw.rounded_rectangle(
        (
            70,
            430,
            VIDEO_WIDTH - 70,
            1250
        ),
        radius=35,
        fill=DARK_BOX
    )

    draw_wrapped_text(
        draw,
        impact,
        115,
        500,
        font(41),
        WHITE,
        VIDEO_WIDTH - 230,
        17
    )

    # IMPORTANT:
    # No outro/end-card is embedded in this scene.
    # The outro is now its own final scene.

    add_footer(
        draw,
        story["source"]["name"],
        story["date"]
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# SOURCE CARD
# ============================================================

def create_source_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 250),
        "SOURCE",
        font=font(58, True),
        fill=RED
    )

    draw_wrapped_text(
        draw,
        story["source"]["name"],
        70,
        380,
        font(52, True),
        WHITE,
        VIDEO_WIDTH - 140,
        12
    )

    draw.text(
        (70, 610),
        "SOURCE TYPE",
        font=font(29, True),
        fill=LIGHT
    )

    draw.text(
        (70, 665),
        story["source"]["type"],
        font=font(38, True),
        fill=WHITE
    )

    draw.text(
        (70, 810),
        "PUBLICATION DATE",
        font=font(29, True),
        fill=LIGHT
    )

    draw.text(
        (70, 865),
        str(story["date"]),
        font=font(42, True),
        fill=WHITE
    )

    if story["source"].get("url"):

        draw.text(
            (70, 1020),
            "SOURCE LINK",
            font=font(30, True),
            fill=RED
        )

        draw_wrapped_text(
            draw,
            story["source"]["url"],
            70,
            1080,
            font(26),
            LIGHT,
            VIDEO_WIDTH - 140,
            8
        )

    draw.rectangle(
        (
            70,
            1330,
            VIDEO_WIDTH - 70,
            1337
        ),
        fill=RED
    )

    draw.text(
        (70, 1400),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=font(36, True),
        fill=WHITE
    )

    draw.text(
        (70, 1465),
        "RIFT VALLEY WATCH",
        font=font(34, True),
        fill=LIGHT
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# OUTRO CARD
# ============================================================

def create_outro_card(
    story,
    output_path
):

    image, draw = new_card(story)

    draw.text(
        (70, 650),
        "RIFT VALLEY WATCH",
        font=font(58, True),
        fill=WHITE
    )

    draw.rectangle(
        (
            70,
            760,
            600,
            768
        ),
        fill=RED
    )

    draw_wrapped_text(
        draw,
        "Tracking verified developments across the region.",
        70,
        850,
        font(42),
        LIGHT,
        VIDEO_WIDTH - 140,
        15
    )

    draw.text(
        (70, 1130),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=font(32, True),
        fill=RED
    )

    add_footer(
        draw,
        story["source"]["name"],
        story["date"]
    )

    image.save(
        output_path,
        quality=95
    )


# ============================================================
# NARRATION
# ============================================================

def create_narration(
    script,
    audio_path
):

    text = clean_text(
        script.get(
            "full_script",
            ""
        )
    )

    if not text:
        raise RuntimeError(
            "Narration text is empty."
        )

    print(
        "      Generating narration..."
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(audio_path)
    )

    if not audio_path.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )


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

    result = run_command(command)

    return float(
        result.stdout.strip()
    )


# ============================================================
# CARD VIDEO
# ============================================================

def create_card_video(
    image_path,
    duration,
    output_path
):

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-vf",
        (
            "scale="
            "1134:2016,"
            "crop=1080:1920:"
            "27:48"
        ),

        "-t",
        f"{duration:.3f}",

        "-r",
        str(FPS),

        "-pix_fmt",
        "yuv420p",

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "21",

        "-an",

        "-movflags",
        "+faststart",

        str(output_path)
    ]

    run_command(command)


# ============================================================
# CONCATENATE - SAFE TIMELINE VERSION
# ============================================================

def concatenate_videos(
    video_files,
    output_path
):

    if not video_files:
        raise RuntimeError(
            "No video scenes supplied."
        )

    # Re-encode through FFmpeg's concat filter rather than
    # stream-copying independently encoded files.
    #
    # This gives every scene a clean continuous timeline and
    # prevents timestamp/scene-boundary artifacts.

    inputs = []

    for video in video_files:
        inputs.extend(
            [
                "-i",
                str(video)
            ]
        )

    filter_parts = []

    for index in range(len(video_files)):
        filter_parts.append(
            f"[{index}:v]"
            "settb=AVTB,"
            "setpts=PTS-STARTPTS,"
            f"fps={FPS},"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
            f"[v{index}]"
        )

    concat_inputs = "".join(
        f"[v{index}]"
        for index in range(len(video_files))
    )

    filter_parts.append(
        concat_inputs
        + f"concat=n={len(video_files)}:v=1:a=0"
        "[vout]"
    )

    filter_complex = ";".join(
        filter_parts
    )

    command = [
        "ffmpeg",
        "-y"
    ]

    command.extend(inputs)

    command.extend(
        [
            "-filter_complex",
            filter_complex,

            "-map",
            "[vout]",

            "-an",

            "-r",
            str(FPS),

            "-c:v",
            "libx264",

            "-preset",
            "medium",

            "-crf",
            "21",

            "-pix_fmt",
            "yuv420p",

            "-movflags",
            "+faststart",

            str(output_path)
        ]
    )

    run_command(command)


# ============================================================
# ADD NARRATION
# ============================================================

def add_audio(
    video_path,
    audio_path,
    output_path
):

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

        "-af",
        (
            "loudnorm="
            "I=-16:"
            "TP=-1.5:"
            "LRA=11"
        ),

        "-shortest",

        "-movflags",
        "+faststart",

        str(output_path)
    ]

    run_command(command)


# ============================================================
# CAPTION CHUNKS
# ============================================================

def create_caption_chunks(
    text,
    total_duration
):

    sentences = re.split(
        r"(?<=[.!?])\s+",
        clean_text(text)
    )

    sentences = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]

    if not sentences:
        return []

    total_words = sum(
        len(sentence.split())
        for sentence in sentences
    )

    chunks = []

    current = 0.0

    for sentence in sentences:

        words = len(
            sentence.split()
        )

        duration = (
            total_duration
            * words
            / max(total_words, 1)
        )

        chunks.append(
            {
                "text": sentence,
                "start": current,
                "end": current + duration
            }
        )

        current += duration

    return chunks


# ============================================================
# CAPTION IMAGE
# ============================================================

def create_caption_image(
    text,
    output_path
):

    image = Image.new(
        "RGBA",
        (
            VIDEO_WIDTH,
            300
        ),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    selected_font = font(
        43,
        True
    )

    lines = wrap_text(
        draw,
        text,
        selected_font,
        VIDEO_WIDTH - 150
    )

    line_height = 58

    box_height = (
        len(lines)
        * line_height
        + 40
    )

    top = max(
        10,
        (300 - box_height) // 2
    )

    draw.rounded_rectangle(
        (
            45,
            top,
            VIDEO_WIDTH - 45,
            top + box_height
        ),
        radius=22,
        fill=(0, 0, 0, 220)
    )

    y = top + 18

    for line in lines:

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=selected_font
        )

        width = (
            bbox[2] - bbox[0]
        )

        x = (
            VIDEO_WIDTH - width
        ) // 2

        draw.text(
            (x, y),
            line,
            font=selected_font,
            fill=WHITE
        )

        y += line_height

    image.save(
        output_path
    )


# ============================================================
# BURN CAPTIONS
# ============================================================

def burn_captions(
    video_path,
    script,
    output_path
):

    duration = get_media_duration(
        video_path
    )

    chunks = create_caption_chunks(
        script["full_script"],
        duration
    )

    if not chunks:
        shutil.copy2(
            video_path,
            output_path
        )
        return

    with tempfile.TemporaryDirectory() as temp_dir:

        temp_dir = Path(temp_dir)

        inputs = [
            "-i",
            str(video_path)
        ]

        filters = []

        for index, chunk in enumerate(chunks):

            caption_file = (
                temp_dir
                / f"caption_{index}.png"
            )

            create_caption_image(
                chunk["text"],
                caption_file
            )

            inputs.extend(
                [
                    "-loop",
                    "1",
                    "-i",
                    str(caption_file)
                ]
            )

            filters.append(
                f"[{index + 1}:v]"
                "format=rgba"
                f"[cap{index}]"
            )

        current = "[0:v]"

        for index, chunk in enumerate(chunks):

            output_label = f"[v{index}]"

            filters.append(
                f"{current}"
                f"[cap{index}]"
                "overlay="
                "0:H-h-170:"
                f"enable='between(t,"
                f"{chunk['start']:.3f},"
                f"{chunk['end']:.3f})'"
                f"{output_label}"
            )

            current = output_label

        filter_complex = ";".join(
            filters
        )

        command = [
            "ffmpeg",
            "-y"
        ]

        command.extend(inputs)

        command.extend(
            [
                "-filter_complex",
                filter_complex,

                "-map",
                current,

                "-map",
                "0:a?",

                "-c:v",
                "libx264",

                "-preset",
                "medium",

                "-crf",
                "20",

                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",

                "-b:a",
                "128k",

                "-movflags",
                "+faststart",

                "-shortest",

                str(output_path)
            ]
        )

        run_command(command)


# ============================================================
# FINAL QC
# ============================================================

def validate_video(
    video_path
):

    if not video_path.exists():
        raise RuntimeError(
            "QC FAILED: MP4 does not exist."
        )

    size = video_path.stat().st_size

    if size < 100_000:
        raise RuntimeError(
            "QC FAILED: MP4 is unexpectedly small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "stream=codec_type,width,height,codec_name",

        "-show_entries",
        "format=duration",

        "-of",
        "json",

        str(video_path)
    ]

    result = run_command(command)

    info = json.loads(
        result.stdout
    )

    streams = info.get(
        "streams",
        []
    )

    if not streams:
        raise RuntimeError(
            "QC FAILED: no streams detected."
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
            "QC FAILED: video stream missing."
        )

    if audio_stream is None:
        raise RuntimeError(
            "QC FAILED: audio stream missing."
        )

    width = video_stream.get("width")
    height = video_stream.get("height")

    if width != VIDEO_WIDTH:
        raise RuntimeError(
            f"QC FAILED: width {width}; "
            f"expected {VIDEO_WIDTH}."
        )

    if height != VIDEO_HEIGHT:
        raise RuntimeError(
            f"QC FAILED: height {height}; "
            f"expected {VIDEO_HEIGHT}."
        )

    duration = float(
        info.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
    )

    if duration < 5:
        raise RuntimeError(
            "QC FAILED: video duration too short."
        )

    print()
    print("=" * 60)
    print("FINAL VIDEO QC")
    print("=" * 60)
    print(
        f"Resolution : {width}x{height}"
    )
    print(
        f"Duration   : {duration:.2f} seconds"
    )
    print(
        f"File size  : {size / 1024 / 1024:.2f} MB"
    )
    print(
        f"Video      : {video_stream.get('codec_name')}"
    )
    print(
        f"Audio      : {audio_stream.get('codec_name')}"
    )
    print(
        "QC STATUS  : PASS"
    )


# ============================================================
# GENERATE VIDEO
# ============================================================

def generate_video():

    print("=" * 60)
    print("RIFT VALLEY WATCH V2")
    print("PROFESSIONAL NEWS VIDEO GENERATOR")
    print("=" * 60)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    script = load_json(
        SCRIPT_FILE
    )

    print()
    print("[1/7] Loading verified script...")

    story = {
        "title": script["title"],
        "county": script["county"],
        "category": script["category"],
        "date": script["date"],
        "source": script["source"],
        "verified_facts": script.get(
            "verified_facts",
            []
        ),
        "editorial": script.get(
            "editorial",
            {}
        ),
        "sections": script.get(
            "sections",
            {}
        ),
        "summary": script.get(
            "full_script",
            ""
        )
    }

    print(
        f"      {story['title']}"
    )

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="rift_valley_watch_v2_"
        )
    )

    try:

        print()
        print("[2/7] Creating visual cards...")

        hook_image = work_dir / "hook.jpg"
        facts_image = work_dir / "facts.jpg"
        context_image = work_dir / "context.jpg"
        impact_image = work_dir / "impact.jpg"
        source_image = work_dir / "source.jpg"
        outro_image = work_dir / "outro.jpg"

        create_hook_card(
            story,
            hook_image
        )

        create_facts_card(
            story,
            facts_image
        )

        create_context_card(
            story,
            context_image
        )

        create_impact_card(
            story,
            impact_image
        )

        create_source_card(
            story,
            source_image
        )

        create_outro_card(
            story,
            outro_image
        )

        print()
        print("[3/7] Generating narration...")

        audio_file = (
            work_dir
            / "narration.mp3"
        )

        create_narration(
            script,
            audio_file
        )

        audio_duration = get_media_duration(
            audio_file
        )

        print(
            f"      Audio duration: "
            f"{audio_duration:.2f}s"
        )

        print()
        print("[4/7] Building explicit scene timeline...")

        images = [
            hook_image,
            facts_image,
            context_image,
            impact_image,
            source_image,
            outro_image
        ]

        # The outro is intentionally short.
        # The main reporting scenes receive the majority
        # of the narration time.
        weights = [
            0.16,
            0.22,
            0.18,
            0.20,
            0.16,
            0.08
        ]

        durations = [
            max(
                2.5,
                audio_duration * weight
            )
            for weight in weights
        ]

        duration_total = sum(
            durations
        )

        multiplier = (
            audio_duration
            / duration_total
        )

        durations = [
            duration * multiplier
            for duration in durations
        ]

        # Explicit scene timeline.
        scene_start = 0.0

        for index, duration in enumerate(durations):

            scene_end = scene_start + duration

            print(
                f"      Scene {index + 1}: "
                f"{scene_start:.2f}s -> "
                f"{scene_end:.2f}s"
            )

            scene_start = scene_end

        card_videos = []

        for index, (
            image,
            duration
        ) in enumerate(
            zip(images, durations)
        ):

            card_video = (
                work_dir
                / f"card_{index}.mp4"
            )

            create_card_video(
                image,
                duration,
                card_video
            )

            card_videos.append(
                card_video
            )

        silent_video = (
            work_dir
            / "silent.mp4"
        )

        concatenate_videos(
            card_videos,
            silent_video
        )

        print()
        print("[5/7] Adding narration...")

        narrated_video = (
            work_dir
            / "narrated.mp4"
        )

        add_audio(
            silent_video,
            audio_file,
            narrated_video
        )

        print()
        print("[6/7] Adding burned-in captions...")

        final_video = (
            work_dir
            / "final.mp4"
        )

        burn_captions(
            narrated_video,
            script,
            final_video
        )

        shutil.copy2(
            final_video,
            OUTPUT_FILE
        )

        print()
        print("[7/7] Running automatic QC...")

        validate_video(
            OUTPUT_FILE
        )

        print()
        print("=" * 60)
        print("RIFT VALLEY WATCH V2 COMPLETE")
        print("=" * 60)
        print()
        print(
            f"OUTPUT: {OUTPUT_FILE}"
        )

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    generate_video()
