# ============================================================
# RIFT VALLEY WATCH
# Video Generator
# 1080 x 1920 Vertical News Reel
# ============================================================

import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont
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

FONT_REGULAR = [
    Path("fonts/DejaVuSans.ttf"),
    Path(
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans.ttf"
    ),
]

FONT_BOLD = [
    Path("fonts/DejaVuSans-Bold.ttf"),
    Path(
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf"
    ),
]


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
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):
    text = str(
        text or ""
    )

    words = text.split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:

        test = (
            current
            + " "
            + word
        ).strip()

        box = draw.textbbox(
            (0, 0),
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
# IMAGE DOWNLOAD
# ============================================================

def download_image(
    url
):
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

    print(
        f"Downloading story image:"
    )

    print(
        url
    )

    response = requests.get(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "(compatible; "
                "RiftValleyWatch/1.0)"
        },
        timeout=20,
    )

    response.raise_for_status()

    if len(
        response.content
    ) < 5000:

        raise RuntimeError(
            "Downloaded image is too small."
        )

    path.write_bytes(
        response.content
    )

    try:

        image = Image.open(
            path
        ).convert(
            "RGB"
        )

    except Exception as exc:

        raise RuntimeError(
            f"Downloaded file is not a valid "
            f"image: {exc}"
        ) from exc

    image.save(
        path,
        "JPEG",
        quality=94,
    )

    print(
        f"Image saved: {path}"
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

    if image_ratio > target_ratio:

        # Landscape -> crop sides
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

        # Portrait -> crop top/bottom
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
# SCENE
# ============================================================

def create_scene(
    image,
    label,
    title,
    body,
    scene_number,
    total_scenes,
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

    # --------------------------------------------------------
    # TOP NEWS BAR
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            235,
        ),
        fill=(
            0,
            0,
            0,
            205,
        ),
    )

    # Brand
    draw.text(
        (
            50,
            45,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            50,
            True,
        ),
        fill="white",
    )

    draw.text(
        (
            52,
            125,
        ),
        label.upper(),
        font=get_font(
            30,
            True,
        ),
        fill="white",
    )

    # --------------------------------------------------------
    # LOWER INFORMATION PANEL
    # --------------------------------------------------------

    panel_top = 1080

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            HEIGHT,
        ),
        fill=(
            0,
            0,
            0,
            220,
        ),
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title_font = get_font(
        61,
        True,
    )

    body_font = get_font(
        37,
        False,
    )

    title_lines = wrap_text(
        draw,
        title,
        title_font,
        WIDTH - 100,
    )

    y = (
        panel_top
        + 55
    )

    for line in title_lines[:5]:

        draw.text(
            (
                50,
                y,
            ),
            line,
            font=title_font,
            fill="white",
        )

        y += 76

    # --------------------------------------------------------
    # BODY
    # --------------------------------------------------------

    y += 15

    body_lines = wrap_text(
        draw,
        body,
        body_font,
        WIDTH - 100,
    )

    for line in body_lines[:9]:

        if y > HEIGHT - 190:
            break

        draw.text(
            (
                50,
                y,
            ),
            line,
            font=body_font,
            fill="white",
        )

        y += 51

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    draw.text(
        (
            50,
            HEIGHT - 100,
        ),
        "RIFT VALLEY WATCH",
        font=get_font(
            24,
            True,
        ),
        fill="white",
    )

    # Progress indicator
    progress_width = 300

    progress_x = (
        WIDTH
        - progress_width
        - 50
    )

    progress_y = (
        HEIGHT
        - 80
    )

    draw.rectangle(
        (
            progress_x,
            progress_y,
            progress_x
            + progress_width,
            progress_y
            + 7,
        ),
        fill=(
            255,
            255,
            255,
            80,
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

    draw.rectangle(
        (
            progress_x,
            progress_y,
            progress_x
            + completed,
            progress_y
            + 7,
        ),
        fill="white",
    )

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
    """
    Approximate spoken duration.
    gTTS normally speaks around 135-160
    words per minute.
    """

    words = len(
        str(
            narration or ""
        ).split()
    )

    if words <= 1:
        return 5.0

    duration = (
        words
        / 145.0
        * 60.0
    )

    # Reasonable reel bounds
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
    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    audio_path = (
        AUDIO_DIR
        / "narration.mp3"
    )

    print(
        "Generating narration..."
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

    # Required by FFmpeg concat demuxer
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

    print(
        "Creating silent video..."
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

    print(
        "Combining video and narration..."
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
            "format=duration,size:stream="
            "codec_type,codec_name,width,height,"
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
        "Running final video QC..."
    )

    info = probe_video()

    streams = info.get(
        "streams",
        [],
    )

    video_streams = [
        s
        for s in streams
        if s.get(
            "codec_type"
        ) == "video"
    ]

    audio_streams = [
        s
        for s in streams
        if s.get(
            "codec_type"
        ) == "audio"
    ]

    if not video_streams:
        raise RuntimeError(
            "Video QC failed: no video stream."
        )

    if not audio_streams:
        raise RuntimeError(
            "Video QC failed: no audio stream."
        )

    video = video_streams[0]
    audio = audio_streams[0]

    if video.get(
        "codec_name"
    ) != "h264":

        raise RuntimeError(
            "Video QC failed: video "
            "is not H.264."
        )

    if int(
        video.get(
            "width",
            0,
        )
    ) != WIDTH:

        raise RuntimeError(
            "Video QC failed: width "
            "is not 1080."
        )

    if int(
        video.get(
            "height",
            0,
        )
    ) != HEIGHT:

        raise RuntimeError(
            "Video QC failed: height "
            "is not 1920."
        )

    if audio.get(
        "codec_name"
    ) != "aac":

        raise RuntimeError(
            "Video QC failed: audio "
            "is not AAC."
        )

    duration = float(
        info.get(
            "format",
            {}
        ).get(
            "duration",
            0,
        )
        or 0
    )

    if duration < 5:
        raise RuntimeError(
            "Video QC failed: duration "
            "is too short."
        )

    size = int(
        float(
            info.get(
                "format",
                {}
            ).get(
                "size",
                0,
            )
            or 0
        )
    )

    if size < 50_000:
        raise RuntimeError(
            "Video QC failed: file "
            "size is too small."
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
    Path(
        "data"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata = {
        "brand": "Rift Valley Watch",
        "title": story.get(
            "title",
            "",
        ),
        "county": story.get(
            "county",
            "",
        ),
        "source": story.get(
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
        "source_image": str(
            image_path
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "video": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "output": str(
                OUTPUT
            ),
        },
    }

    Path(
        "data/visual_metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_video(
    story,
    script=None,
):
    """
    Compatible with:

        generate_video(story, script)

    Also supports legacy:

        generate_video(story)
    """

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
    # Resolve fields
    # --------------------------------------------------------

    image_url = (
        story.get(
            "image"
        )
        or story.get(
            "image_url"
        )
    )

    if not image_url:
        raise RuntimeError(
            "Story does not contain an image URL."
        )

    narration = (
        script.get(
            "narration"
        )
        or story.get(
            "narration"
        )
    )

    if not narration:
        raise RuntimeError(
            "No narration found."
        )

    title = (
        story.get(
            "title"
        )
        or script.get(
            "title"
        )
        or "Regional Update"
    )

    summary = (
        story.get(
            "summary"
        )
        or "Latest regional development."
    )

    county = (
        story.get(
            "county"
        )
        or script.get(
            "county"
        )
        or "Rift Valley"
    )

    source = (
        story.get(
            "source_name"
        )
        or story.get(
            "source"
        )
        or script.get(
            "source"
        )
        or "Published report"
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
    # Download image
    # --------------------------------------------------------

    image_path = download_image(
        image_url
    )

    base_image = prepare_image(
        image_path
    )

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio_path = create_audio(
        narration
    )

    estimated_duration = estimate_duration(
        narration
    )

    print(
        f"Estimated narration duration: "
        f"{estimated_duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Four scenes
    # --------------------------------------------------------

    scene_plan = [
        {
            "label": "BREAKING / REGIONAL UPDATE",
            "title": title,
            "body": summary,
            "zoom": 1.00,
            "shift": 0,
            "weight": 0.27,
        },
        {
            "label": "WHAT WE KNOW",
            "title": title,
            "body": summary,
            "zoom": 1.08,
            "shift": -30,
            "weight": 0.25,
        },
        {
            "label": "WHY IT MATTERS",
            "title": f"{county} regional impact",
            "body": (
                "The report is being followed "
                "for its implications for "
                "communities, services, "
                "business and development."
            ),
            "zoom": 1.15,
            "shift": 35,
            "weight": 0.25,
        },
        {
            "label": "SOURCE",
            "title": source,
            "body": (
                story.get(
                    "resolved_url"
                )
                or story.get(
                    "url"
                )
                or "Published report"
            ),
            "zoom": 1.22,
            "shift": 0,
            "weight": 0.23,
        },
    ]

    # Add small safety margin so the video
    # is not shorter than narration.
    total_visual_duration = (
        estimated_duration
        + 0.8
    )

    scene_durations = [
        total_visual_duration
        * scene["weight"]
        for scene in scene_plan
    ]

    # --------------------------------------------------------
    # Create scene images
    # --------------------------------------------------------

    scene_paths = []

    with tempfile.TemporaryDirectory() as temp_dir:

        temp = Path(
            temp_dir
        )

        for index, scene in enumerate(
            scene_plan
        ):

            scene_path = (
                temp
                / f"scene_{index:02d}.png"
            )

            frame = create_scene(
                base_image,
                scene["label"],
                scene["title"],
                scene["body"],
                index + 1,
                len(scene_plan),
                scene["zoom"],
                scene["shift"],
            )

            frame.save(
                scene_path,
                "PNG",
            )

            scene_paths.append(
                scene_path
            )

        # ----------------------------------------------------
        # Silent video
        # ----------------------------------------------------

        silent_video = (
            temp
            / "silent.mp4"
        )

        create_silent_video(
            scene_paths,
            scene_durations,
            silent_video,
        )

        # ----------------------------------------------------
        # Final video
        # ----------------------------------------------------

        combine_video_audio(
            silent_video,
            audio_path,
        )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    validate_video()

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    save_visual_metadata(
        story,
        image_path,
    )

    print()
    print(
        "=" * 70
    )

    print(
        "VIDEO GENERATION COMPLETE"
    )

    print(
        f"Output: {OUTPUT}"
    )

    print(
        "=" * 70
    )

    return str(
        OUTPUT
    )


# ============================================================
# STANDALONE MODE
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


if __name__ == "__main__":

    print(
        "Running Rift Valley Watch "
        "video generator directly..."
    )

    story_path = Path(
        "data/story.json"
    )

    script_path = Path(
        "data/script.json"
    )

    if not story_path.exists():
        raise RuntimeError(
            "data/story.json not found."
        )

    if not script_path.exists():
        raise RuntimeError(
            "data/script.json not found."
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
