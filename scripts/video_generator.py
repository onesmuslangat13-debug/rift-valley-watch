# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# 1080 x 1920 VERTICAL NEWS REEL
# ============================================================

import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import requests

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
)

from gtts import gTTS


# ============================================================
# CONFIGURATION
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

OUTPUT = Path(
    "output/rift_valley_watch_reel.mp4"
)

SOURCE_DIR = Path(
    "assets/source"
)

AUDIO_DIR = Path(
    "assets/audio"
)

DATA_DIR = Path(
    "data"
)

FONT_REGULAR = [
    Path(
        "fonts/DejaVuSans.ttf"
    ),
    Path(
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans.ttf"
    ),
]

FONT_BOLD = [
    Path(
        "fonts/DejaVuSans-Bold.ttf"
    ),
    Path(
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf"
    ),
]


# ============================================================
# COLORS
# ============================================================

WHITE = (
    255,
    255,
    255,
    255,
)

BLACK = (
    0,
    0,
    0,
    255,
)

DARK_PANEL = (
    0,
    0,
    0,
    235,
)

DARK_TOP = (
    0,
    0,
    0,
    225,
)

RED = (
    220,
    35,
    35,
    255,
)

LIGHT_GREY = (
    220,
    220,
    220,
    255,
)

YELLOW = (
    255,
    210,
    60,
    255,
)


# ============================================================
# FONT
# ============================================================

def get_font(
    size,
    bold=False,
):

    candidates = (
        FONT_BOLD
        if bold
        else FONT_REGULAR
    )

    for path in candidates:

        if path.exists():

            return ImageFont.truetype(
                str(path),
                size,
            )

    return ImageFont.load_default()


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(
    value
):

    if value is None:
        return ""

    value = str(value)

    value = (
        value
        .replace(
            "\n",
            " ",
        )
        .replace(
            "\r",
            " ",
        )
        .replace(
            "\t",
            " ",
        )
    )

    while "  " in value:

        value = value.replace(
            "  ",
            " ",
        )

    return value.strip()


def shorten_text(
    text,
    maximum=420,
):

    text = clean_text(
        text
    )

    if len(text) <= maximum:
        return text

    text = text[:maximum]

    if " " in text:

        text = text.rsplit(
            " ",
            1,
        )[0]

    return text.rstrip(
        " ,.;:-"
    ) + "..."


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    text = clean_text(
        text
    )

    if not text:
        return []

    words = text.split()

    lines = []

    current = ""

    for word in words:

        test = (
            current
            + " "
            + word
        ).strip()

        box = draw.textbbox(
            (
                0,
                0,
            ),
            test,
            font=font,
        )

        width = (
            box[2]
            - box[0]
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


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url
):

    url = clean_text(
        url
    )

    if not url:

        raise RuntimeError(
            "No story image URL supplied."
        )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        SOURCE_DIR
        / "story_image.jpg"
    )

    print()
    print(
        "============================================================"
    )

    print(
        "DOWNLOADING REAL ARTICLE IMAGE"
    )

    print(
        "============================================================"
    )

    print(
        "Image URL:"
    )

    print(
        url
    )

    headers = {

        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/153.0 Safari/537.36"
        ),

        "Accept": (
            "image/avif,"
            "image/webp,"
            "image/apng,"
            "image/svg+xml,"
            "image/*,*/*;q=0.8"
        ),

        "Referer": url,
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=25,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:

        raise RuntimeError(
            "Unable to download article image: "
            + str(exc)
        ) from exc

    content = response.content

    if len(content) < 5000:

        raise RuntimeError(
            "Downloaded article image is "
            "too small."
        )

    path.write_bytes(
        content
    )

    try:

        with Image.open(
            path
        ) as check:

            check.verify()

    except Exception as exc:

        raise RuntimeError(
            "Downloaded file is not a valid "
            "image: "
            + str(exc)
        ) from exc

    try:

        image = Image.open(
            path
        ).convert(
            "RGB"
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not open downloaded "
            "article image: "
            + str(exc)
        ) from exc

    # --------------------------------------------------------
    # Reject unusably tiny images
    # --------------------------------------------------------

    if (
        image.width < 300
        or image.height < 200
    ):

        raise RuntimeError(
            "Article image resolution is "
            "too small: "
            f"{image.width}x{image.height}"
        )

    # --------------------------------------------------------
    # Save normalized JPEG
    # --------------------------------------------------------

    image.save(
        path,
        "JPEG",
        quality=95,
    )

    print(
        "REAL ARTICLE IMAGE FOUND"
    )

    print(
        f"Image size: "
        f"{image.width}x{image.height}"
    )

    print(
        f"Saved: {path}"
    )

    return path


# ============================================================
# PREPARE IMAGE
# ============================================================

def prepare_image(
    image_path
):

    image = Image.open(
        image_path
    ).convert(
        "RGB"
    )

    image_ratio = (
        image.width
        / image.height
    )

    target_ratio = (
        WIDTH
        / HEIGHT
    )

    # --------------------------------------------------------
    # Crop to 9:16
    # --------------------------------------------------------

    if image_ratio > target_ratio:

        new_width = int(
            image.height
            * target_ratio
        )

        left = (
            image.width
            - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                image.height,
            )
        )

    else:

        new_height = int(
            image.width
            / target_ratio
        )

        top = (
            image.height
            - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                image.width,
                top + new_height,
            )
        )

    image = image.resize(
        (
            WIDTH,
            HEIGHT,
        ),
        Image.Resampling.LANCZOS,
    )

    return image


# ============================================================
# ZOOM FRAME
# ============================================================

def make_zoom_frame(
    base_image,
    zoom,
    vertical_shift=0,
):

    if zoom <= 1.0:

        return base_image.copy()

    new_width = int(
        WIDTH * zoom
    )

    new_height = int(
        HEIGHT * zoom
    )

    enlarged = base_image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
    )

    max_x = (
        new_width
        - WIDTH
    )

    max_y = (
        new_height
        - HEIGHT
    )

    x = max_x // 2

    y = (
        max_y // 2
        + vertical_shift
    )

    y = max(
        0,
        min(
            y,
            max_y,
        ),
    )

    return enlarged.crop(
        (
            x,
            y,
            x + WIDTH,
            y + HEIGHT,
        )
    )


# ============================================================
# DRAW TEXT WITH SHADOW
# ============================================================

def draw_text_shadow(
    draw,
    position,
    text,
    font,
    fill=WHITE,
    shadow_offset=3,
):

    x, y = position

    draw.text(
        (
            x + shadow_offset,
            y + shadow_offset,
        ),
        text,
        font=font,
        fill=(
            0,
            0,
            0,
            220,
        ),
    )

    draw.text(
        (
            x,
            y,
        ),
        text,
        font=font,
        fill=fill,
    )


# ============================================================
# CREATE SCENE
# ============================================================

def create_scene(
    image,
    label,
    title,
    body,
    scene_number,
    total_scenes,
    county,
    source,
    zoom=1.0,
    vertical_shift=0,
):

    frame = make_zoom_frame(
        image,
        zoom,
        vertical_shift,
    )

    canvas = frame.convert(
        "RGBA"
    )

    overlay = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        (
            0,
            0,
            0,
            0,
        ),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    # ========================================================
    # TOP NEWS HEADER
    # ========================================================

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            245,
        ),
        fill=DARK_TOP,
    )

    # Red breaking indicator

    draw.rectangle(
        (
            0,
            0,
            18,
            245,
        ),
        fill=RED,
    )

    draw_text_shadow(
        draw,
        (
            48,
            35,
        ),
        "RIFT VALLEY WATCH",
        get_font(
            50,
            True,
        ),
    )

    # County

    county_text = (
        clean_text(
            county
        ).upper()
        or "RIFT VALLEY"
    )

    draw.text(
        (
            50,
            112,
        ),
        county_text,
        font=get_font(
            31,
            True,
        ),
        fill=YELLOW,
    )

    # Scene label

    draw.text(
        (
            50,
            163,
        ),
        clean_text(
            label
        ).upper(),
        font=get_font(
            27,
            True,
        ),
        fill=WHITE,
    )

    # ========================================================
    # LOWER STORY PANEL
    # ========================================================

    panel_top = 1010

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            HEIGHT,
        ),
        fill=DARK_PANEL,
    )

    # Top red accent

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            panel_top + 10,
        ),
        fill=RED,
    )

    # ========================================================
    # HEADLINE
    # ========================================================

    title_font = get_font(
        57,
        True,
    )

    title_text = clean_text(
        title
    )

    title_lines = wrap_text(
        draw,
        title_text,
        title_font,
        WIDTH - 100,
    )

    y = panel_top + 42

    for line in title_lines[:5]:

        draw_text_shadow(
            draw,
            (
                50,
                y,
            ),
            line,
            title_font,
        )

        y += 70

    # ========================================================
    # BODY
    # ========================================================

    y += 18

    body_font = get_font(
        34,
        False,
    )

    body_text = clean_text(
        body
    )

    body_lines = wrap_text(
        draw,
        body_text,
        body_font,
        WIDTH - 100,
    )

    for line in body_lines[:7]:

        if y > HEIGHT - 250:
            break

        draw.text(
            (
                50,
                y,
            ),
            line,
            font=body_font,
            fill=LIGHT_GREY,
        )

        y += 48

    # ========================================================
    # SOURCE
    # ========================================================

    source_text = clean_text(
        source
    )

    if source_text:

        source_font = get_font(
            25,
            True,
        )

        source_y = HEIGHT - 190

        draw.text(
            (
                50,
                source_y,
            ),
            "SOURCE: "
            + source_text[:65],
            font=source_font,
            fill=WHITE,
        )

    # ========================================================
    # FOOTER
    # ========================================================

    footer_y = HEIGHT - 92

    draw.text(
        (
            50,
            footer_y,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            23,
            True,
        ),
        fill=WHITE,
    )

    # Progress bar

    progress_width = 330

    progress_x = (
        WIDTH
        - progress_width
        - 50
    )

    progress_y = (
        HEIGHT
        - 76
    )

    draw.rounded_rectangle(
        (
            progress_x,
            progress_y,
            progress_x
            + progress_width,
            progress_y + 8,
        ),
        radius=4,
        fill=(
            255,
            255,
            255,
            70,
        ),
    )

    completed = int(
        progress_width
        * (
            scene_number
            / max(
                total_scenes,
                1,
            )
        )
    )

    draw.rounded_rectangle(
        (
            progress_x,
            progress_y,
            progress_x
            + completed,
            progress_y + 8,
        ),
        radius=4,
        fill=WHITE,
    )

    # ========================================================
    # FINAL COMPOSITE
    # ========================================================

    return Image.alpha_composite(
        canvas,
        overlay,
    ).convert(
        "RGB"
    )


# ============================================================
# NARRATION DURATION
# ============================================================

def estimate_duration(
    narration
):

    words = len(
        clean_text(
            narration
        ).split()
    )

    if words <= 1:
        return 5.0

    duration = (
        words
        / 145.0
        * 60.0
    )

    return max(
        12.0,
        min(
            duration,
            90.0,
        ),
    )


# ============================================================
# AUDIO
# ============================================================

def create_audio(
    narration
):

    narration = clean_text(
        narration
    )

    if not narration:

        raise RuntimeError(
            "No narration was provided."
        )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    audio_path = (
        AUDIO_DIR
        / "narration.mp3"
    )

    print()
    print(
        "GENERATING NARRATION"
    )

    print(
        narration
    )

    gTTS(
        text=narration,
        lang="en",
        slow=False,
    ).save(
        str(audio_path)
    )

    if not audio_path.exists():

        raise RuntimeError(
            "Narration audio was not created."
        )

    if audio_path.stat().st_size < 5000:

        raise RuntimeError(
            "Narration audio is too small."
        )

    print(
        f"Audio saved: {audio_path}"
    )

    return audio_path


# ============================================================
# FFMPEG SILENT VIDEO
# ============================================================

def create_silent_video(
    scene_paths,
    scene_durations,
    output_path,
):

    if not scene_paths:

        raise RuntimeError(
            "No scene images were created."
        )

    concat_file = (
        output_path.parent
        / "concat.txt"
    )

    lines = []

    for path, duration in zip(
        scene_paths,
        scene_durations,
    ):

        escaped = (
            str(
                path.resolve()
            )
            .replace(
                "'",
                "'\\''",
            )
        )

        lines.append(
            f"file '{escaped}'"
        )

        lines.append(
            f"duration {duration:.3f}"
        )

    last_path = (
        str(
            scene_paths[-1].resolve()
        )
        .replace(
            "'",
            "'\\''",
        )
    )

    lines.append(
        f"file '{last_path}'"
    )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print(
        "CREATING SILENT VIDEO"
    )

    command = [

        "ffmpeg",

        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(
            concat_file
        ),

        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2,"
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

    subprocess.run(
        command,
        check=True,
    )

    if not output_path.exists():

        raise RuntimeError(
            "Silent video was not created."
        )


# ============================================================
# FINAL VIDEO
# ============================================================

def combine_video_audio(
    silent_video,
    audio_path,
):

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print(
        "COMBINING VIDEO + NARRATION"
    )

    command = [

        "ffmpeg",

        "-y",

        "-i",
        str(silent_video),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-shortest",

        "-movflags",
        "+faststart",

        str(OUTPUT),
    ]

    subprocess.run(
        command,
        check=True,
    )

    if not OUTPUT.exists():

        raise RuntimeError(
            "Final MP4 was not created."
        )

    if OUTPUT.stat().st_size < 50_000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )


# ============================================================
# FFPROBE
# ============================================================

def probe_video():

    command = [

        "ffprobe",

        "-v",
        "error",

        "-show_entries",

        (
            "format=duration,size:"
            "stream=codec_type,"
            "codec_name,width,height,"
            "sample_rate,channels,duration"
        ),

        "-of",
        "json",

        str(OUTPUT),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(
        result.stdout
    )


# ============================================================
# VIDEO QC
# ============================================================

def validate_video():

    print()
    print(
        "============================================================"
    )

    print(
        "RUNNING FINAL VIDEO QC"
    )

    print(
        "============================================================"
    )

    info = probe_video()

    streams = info.get(
        "streams",
        [],
    )

    video_streams = [

        stream

        for stream in streams

        if stream.get(
            "codec_type"
        ) == "video"
    ]

    audio_streams = [

        stream

        for stream in streams

        if stream.get(
            "codec_type"
        ) == "audio"
    ]

    if not video_streams:

        raise RuntimeError(
            "Video QC failed: "
            "no video stream."
        )

    if not audio_streams:

        raise RuntimeError(
            "Video QC failed: "
            "no audio stream."
        )

    video = video_streams[0]

    audio = audio_streams[0]

    if video.get(
        "codec_name"
    ) != "h264":

        raise RuntimeError(
            "Video QC failed: "
            "video is not H.264."
        )

    if int(
        video.get(
            "width",
            0,
        )
    ) != WIDTH:

        raise RuntimeError(
            "Video QC failed: "
            "width is not 1080."
        )

    if int(
        video.get(
            "height",
            0,
        )
    ) != HEIGHT:

        raise RuntimeError(
            "Video QC failed: "
            "height is not 1920."
        )

    if audio.get(
        "codec_name"
    ) != "aac":

        raise RuntimeError(
            "Video QC failed: "
            "audio is not AAC."
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
            "Video QC failed: "
            "duration is too short."
        )

    size = int(
        float(
            info.get(
                "format",
                {},
            ).get(
                "size",
                0,
            )
            or 0
        )
    )

    if size < 50_000:

        raise RuntimeError(
            "Video QC failed: "
            "file size is too small."
        )

    print(
        "VIDEO QC PASSED"
    )

    print(
        f"Resolution: "
        f"{video['width']}x{video['height']}"
    )

    print(
        f"Video codec: "
        f"{video['codec_name']}"
    )

    print(
        f"Audio codec: "
        f"{audio['codec_name']}"
    )

    print(
        f"Duration: "
        f"{duration:.2f} seconds"
    )

    print(
        f"File size: "
        f"{size:,} bytes"
    )

    return True


# ============================================================
# VISUAL METADATA
# ============================================================

def save_visual_metadata(
    story,
    image_path,
):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {

        "brand":
            "Rift Valley Watch",

        "title":
            story.get(
                "title",
                "",
            ),

        "summary":
            story.get(
                "summary",
                "",
            ),

        "county":
            story.get(
                "county",
                "",
            ),

        "category":
            story.get(
                "category",
                "",
            ),

        "source":
            story.get(
                "source_name",
                "",
            ),

        "source_url": (
            story.get(
                "resolved_url"
            )
            or story.get(
                "url"
            )
        ),

        "source_image":
            str(
                image_path
            ),

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "video": {

            "width":
                WIDTH,

            "height":
                HEIGHT,

            "fps":
                FPS,

            "output":
                str(
                    OUTPUT
                ),
        },
    }

    (
        DATA_DIR
        / "visual_metadata.json"
    ).write_text(

        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),

        encoding="utf-8",
    )


# ============================================================
# DEBUG STORY DATA
# ============================================================

def print_story_data(
    story,
    script,
):

    print()
    print(
        "============================================================"
    )

    print(
        "STORY DATA RECEIVED BY VIDEO GENERATOR"
    )

    print(
        "============================================================"
    )

    print(
        "TITLE:"
    )

    print(
        clean_text(
            story.get(
                "title",
                "",
            )
        )
    )

    print(
        "COUNTY:"
    )

    print(
        clean_text(
            story.get(
                "county",
                "",
            )
        )
    )

    print(
        "CATEGORY:"
    )

    print(
        clean_text(
            story.get(
                "category",
                "",
            )
        )
    )

    print(
        "SUMMARY:"
    )

    print(
        clean_text(
            story.get(
                "summary",
                "",
            )
        )
    )

    print(
        "SOURCE:"
    )

    print(
        clean_text(
            story.get(
                "source_name",
                "",
            )
        )
    )

    print(
        "IMAGE:"
    )

    print(
        clean_text(
            story.get(
                "image",
                ""
            )
        )
    )

    print(
        "NARRATION:"
    )

    print(
        clean_text(
            script.get(
                "narration"
            )
            or story.get(
                "narration",
                "",
            )
        )
    )

    print(
        "============================================================"
    )


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_video(
    story,
    script=None,
):

    # --------------------------------------------------------
    # Validate story
    # --------------------------------------------------------

    if not isinstance(
        story,
        dict,
    ):

        raise RuntimeError(
            "Story must be a dictionary."
        )

    if script is None:

        script = {}

    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Script must be a dictionary."
        )

    # --------------------------------------------------------
    # Print received data
    # --------------------------------------------------------

    print_story_data(
        story,
        script,
    )

    # --------------------------------------------------------
    # Resolve IMAGE
    # --------------------------------------------------------

    image_url = clean_text(
        story.get(
            "image"
        )
        or story.get(
            "image_url"
        )
        or script.get(
            "image"
        )
        or script.get(
            "image_url"
        )
    )

    if not image_url:

        raise RuntimeError(
            "No real article image URL "
            "was supplied to the video generator."
        )

    # --------------------------------------------------------
    # Resolve NARRATION
    # --------------------------------------------------------

    narration = clean_text(
        script.get(
            "narration"
        )
        or story.get(
            "narration"
        )
    )

    if not narration:

        raise RuntimeError(
            "No narration was provided."
        )

    # --------------------------------------------------------
    # Resolve STORY FIELDS
    # --------------------------------------------------------

    title = clean_text(
        story.get(
            "title"
        )
        or script.get(
            "title"
        )
    )

    if not title:

        raise RuntimeError(
            "No story title was provided."
        )

    summary = clean_text(
        story.get(
            "summary"
        )
        or script.get(
            "summary"
        )
    )

    if not summary:

        summary = (
            "Latest verified "
            "regional news update."
        )

    county = clean_text(
        story.get(
            "county"
        )
        or script.get(
            "county"
        )
        or "Rift Valley"
    )

    category = clean_text(
        story.get(
            "category"
        )
        or script.get(
            "category"
        )
        or "County News"
    )

    source = clean_text(
        story.get(
            "source_name"
        )
        or script.get(
            "source_name"
        )
        or story.get(
            "source"
        )
        or "Verified report"
    )

    source_url = clean_text(
        story.get(
            "resolved_url"
        )
        or story.get(
            "url"
        )
        or script.get(
            "url"
        )
        or script.get(
            "source"
        )
        or ""
    )

    # --------------------------------------------------------
    # Print final resolved data
    # --------------------------------------------------------

    print()
    print(
        "FINAL VIDEO CONTENT"
    )

    print(
        f"Headline: {title}"
    )

    print(
        f"County: {county}"
    )

    print(
        f"Category: {category}"
    )

    print(
        f"Source: {source}"
    )

    print(
        f"Image URL: {image_url}"
    )

    # --------------------------------------------------------
    # Directories
    # --------------------------------------------------------

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Download actual article image
    # --------------------------------------------------------

    image_path = download_image(
        image_url
    )

    base_image = prepare_image(
        image_path
    )

    print(
        "Article image prepared "
        "for 1080x1920 reel."
    )

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio_path = create_audio(
        narration
    )

    estimated_duration = (
        estimate_duration(
            narration
        )
    )

    print(
        f"Estimated narration duration: "
        f"{estimated_duration:.2f} seconds"
    )

    # ========================================================
    # SCENE PLAN
    # ========================================================

    scene_plan = [

        {
            "label":
                "BREAKING / REGIONAL UPDATE",

            "title":
                title,

            "body":
                summary,

            "zoom":
                1.00,

            "shift":
                0,

            "weight":
                0.27,
        },

        {
            "label":
                "WHAT WE KNOW",

            "title":
                title,

            "body":
                summary,

            "zoom":
                1.07,

            "shift":
                -25,

            "weight":
                0.25,
        },

        {
            "label":
                "WHY IT MATTERS",

            "title":
                f"{county} | {category}",

            "body":
                summary,

            "zoom":
                1.14,

            "shift":
                25,

            "weight":
                0.25,
        },

        {
            "label":
                "SOURCE / VERIFIED REPORT",

            "title":
                title,

            "body":
                (
                    f"Reported by {source}. "
                    f"This update covers "
                    f"developments in "
                    f"{county}."
                ),

            "zoom":
                1.20,

            "shift":
                0,

            "weight":
                0.23,
        },
    ]

    # --------------------------------------------------------
    # Visual duration
    # --------------------------------------------------------

    total_visual_duration = (
        estimated_duration
        + 1.0
    )

    scene_durations = [

        total_visual_duration
        * scene["weight"]

        for scene in scene_plan
    ]

    # ========================================================
    # CREATE SCENES
    # ========================================================

    scene_paths = []

    with tempfile.TemporaryDirectory() as temp_dir:

        temp = Path(
            temp_dir
        )

        print()
        print(
            "CREATING NEWS SCENES"
        )

        for index, scene in enumerate(
            scene_plan
        ):

            scene_path = (
                temp
                / f"scene_{index + 1:02d}.png"
            )

            frame = create_scene(

                base_image,

                scene["label"],

                scene["title"],

                scene["body"],

                index + 1,

                len(scene_plan),

                county,

                source,

                scene["zoom"],

                scene["shift"],
            )

            frame.save(
                scene_path,
                "PNG",
            )

            if not scene_path.exists():

                raise RuntimeError(
                    f"Scene {index + 1} "
                    "was not created."
                )

            if scene_path.stat().st_size < 10_000:

                raise RuntimeError(
                    f"Scene {index + 1} "
                    "is suspiciously small."
                )

            scene_paths.append(
                scene_path
            )

            print(
                f"Scene {index + 1}/"
                f"{len(scene_plan)} created: "
                f"{scene_path}"
            )

        # ====================================================
        # SILENT VIDEO
        # ====================================================

        silent_video = (
            temp
            / "silent.mp4"
        )

        create_silent_video(

            scene_paths,

            scene_durations,

            silent_video,
        )

        # ====================================================
        # FINAL VIDEO
        # ====================================================

        combine_video_audio(

            silent_video,

            audio_path,
        )

    # ========================================================
    # QC
    # ========================================================

    validate_video()

    # ========================================================
    # METADATA
    # ========================================================

    save_visual_metadata(
        story,
        image_path,
    )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print(
        "============================================================"
    )

    print(
        "RIFT VALLEY WATCH VIDEO SUCCESSFUL"
    )

    print(
        "============================================================"
    )

    print(
        f"Created: {OUTPUT}"
    )

    print(
        f"Headline: {title}"
    )

    print(
        f"County: {county}"
    )

    print(
        f"Category: {category}"
    )

    print(
        f"Source: {source}"
    )

    print(
        f"Image: {image_path}"
    )

    print(
        "============================================================"
    )

    return str(
        OUTPUT
    )


# ============================================================
# JSON LOADER
# ============================================================

def load_json(
    path
):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


# ============================================================
# STANDALONE MODE
# ============================================================

if __name__ == "__main__":

    print(
        "Running Rift Valley Watch "
        "video generator directly..."
    )

    # Support the filenames produced
    # by the main pipeline first.

    story_candidates = [

        Path(
            "data/selected_story.json"
        ),

        Path(
            "data/story.json"
        ),
    ]

    script_candidates = [

        Path(
            "data/selected_script.json"
        ),

        Path(
            "data/script.json"
        ),
    ]

    story_path = next(
        (
            path
            for path in story_candidates
            if path.exists()
        ),
        None,
    )

    script_path = next(
        (
            path
            for path in script_candidates
            if path.exists()
        ),
        None,
    )

    if story_path is None:

        raise RuntimeError(
            "No story JSON file found. "
            "Expected data/selected_story.json "
            "or data/story.json."
        )

    if script_path is None:

        raise RuntimeError(
            "No script JSON file found. "
            "Expected data/selected_script.json "
            "or data/script.json."
        )

    print(
        f"Loading story: {story_path}"
    )

    print(
        f"Loading script: {script_path}"
    )

    story = load_json(
        story_path
    )

    script = load_json(
        script_path
    )

    generate_video(
        story,
        script,
    )
